"""Tests for the protocol and rendering parts (no Home Assistant needed).

Run: python -m pytest tests -q   (needs pytest and Pillow)
"""

from __future__ import annotations

import ast
import asyncio
import binascii
import importlib.util
import sys
import types
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "bk_light_panel"

# Load const/protocol/render as a package without running __init__.py
pkg = types.ModuleType("bkpkg")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["bkpkg"] = pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"bkpkg.{name}", PKG_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"bkpkg.{name}"] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
protocol = _load("protocol")
render = _load("render")
protocol.STEP_DELAY = 0  # fast tests


# ------------------------------------------------------------ protocol
def _reference_build_frame():
    """build_frame() from the original toolkit, if it is checked out next to us."""
    candidates = list(Path("/tmp").glob("**/bklight/bk_light/display_session.py"))
    if not candidates:
        return None
    tree = ast.parse(candidates[0].read_text())
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_frame")
    namespace = {"binascii": binascii}
    exec(compile(ast.Module(body=[func], type_ignores=[]), "ref", "exec"), namespace)
    return namespace["build_frame"]


def test_build_frame_matches_reference_layout():
    png = render.to_png(render.render_text("HI"))
    frame = protocol.build_frame(png)
    assert int.from_bytes(frame[0:2], "little") == len(png) + 15
    assert frame[2] == 0x02
    assert int.from_bytes(frame[5:7], "little") == len(png)
    assert int.from_bytes(frame[9:13], "little") == binascii.crc32(png)
    assert frame[13:15] == b"\x00\x65"
    assert frame[15:] == png
    reference = _reference_build_frame()
    if reference is not None:
        assert reference(png) == frame


def test_chunking():
    data = bytes(range(256)) * 5
    pieces = protocol.chunk(data, 100)
    assert b"".join(pieces) == data
    assert all(len(p) <= 100 for p in pieces)
    assert all(len(p) >= 20 for p in protocol.chunk(data, 5)[:-1])  # minimum size


class FakePanel:
    """Behaves like the panel: answers handshake and complete frames."""

    def __init__(self, answer_stage_two: bool = True, wide: bool = False) -> None:
        self.wide = wide
        self.callback = None
        self.writes: list[tuple[bytes, bool]] = []
        self.buffer = b""
        self.answer_stage_two = answer_stage_two

    async def start_notify(self, uuid, callback):
        assert uuid == protocol.UUID_NOTIFY
        self.callback = callback

    def _notify(self, hex_payload: str) -> None:
        asyncio.get_running_loop().call_soon(self.callback, 0, bytearray.fromhex(hex_payload))

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == protocol.UUID_WRITE
        data = bytes(data)
        self.writes.append((data, response))
        if data == protocol.HANDSHAKE_FIRST:
            if self.wide:  # 64x16 (ACT1025 / ACT1033)
                self._notify("0B 00 01 80 83 06 32 00 00 01 00")
            else:
                self._notify("0C 00 01 80 81 06 32 00 00 01 00 01")
        elif data == protocol.HANDSHAKE_SECOND:
            if self.answer_stage_two:
                self._notify("08 00 05 80 0B 03 07 02")
        elif data == protocol.FRAME_VALIDATION:
            pass
        else:
            self.buffer += data
            expected = int.from_bytes(self.buffer[0:2], "little")
            if len(self.buffer) >= expected:
                self.frame = self.buffer
                self.buffer = b""
                if self.frame[3:4] == b"\x80":  # a short command (playlist 08, brightness 04)
                    self._notify(f"05 00 {self.frame[2]:02x} 80 01")
                else:  # a picture (02) or a stored animation (03)
                    self._notify(f"05 00 {self.frame[2]:02x} 00 03")


def test_session_handshake_and_chunked_frame():
    async def run():
        fake = FakePanel()
        session = protocol.PanelSession(fake, max_write=64)
        await session.start()
        png = render.to_png(render.render_text("21:45\n12°C", scale=1))
        await session.send_png(png)
        await session.send_png(png)  # second frame: no new handshake
        return fake, png

    fake, png = asyncio.run(run())
    handshakes = [w for w, _ in fake.writes if w == protocol.HANDSHAKE_FIRST]
    assert len(handshakes) == 1
    assert fake.frame == protocol.build_frame(png)
    frame_writes = [(w, r) for w, r in fake.writes if w not in (protocol.HANDSHAKE_FIRST, protocol.HANDSHAKE_SECOND)]
    assert all(r is False for _, r in frame_writes)  # write commands by default
    assert all(len(w) <= 64 for w, _ in frame_writes)


def test_acknowledged_writes_when_asked():
    async def run():
        fake = FakePanel()
        session = protocol.PanelSession(fake, max_write=64, acknowledged=True)
        await session.start()
        await session.send_png(render.to_png(render.render_fill([9, 9, 9])))
        return fake

    fake = asyncio.run(run())
    frame_writes = [r for w, r in fake.writes if w not in (protocol.HANDSHAKE_FIRST, protocol.HANDSHAKE_SECOND)]
    assert frame_writes and all(frame_writes)


def test_session_tolerates_missing_second_ack():
    async def run():
        protocol.ACK_TIMEOUT = 0.2
        fake = FakePanel(answer_stage_two=False)
        session = protocol.PanelSession(fake, max_write=509)
        await session.start()
        await session.send_png(render.to_png(render.render_fill([255, 0, 0])))
        protocol.ACK_TIMEOUT = 5.0
        return fake

    fake = asyncio.run(run())
    assert fake.frame  # the frame arrived complete
    assert len(fake.writes) >= 3


# ------------------------------------------------------------- render
def test_all_glyphs_well_formed():
    for char, rows in render._GLYPHS.items():
        assert len(rows) == render.GLYPH_HEIGHT, char
        assert len({len(r) for r in rows}) == 1, char
        assert set("".join(rows)) <= {"#", "."}, char


def test_capacity_scale_1_and_2():
    assert render.text_width("88888888") <= 32  # 8 digits per line at scale 1
    assert render.text_width("8888") * 2 <= 32  # 4 per line at scale 2
    assert render.wrap_lines("HELLO WORLD FROM HA", 32) == ["HELLO", "WORLD", "FROM HA"]


def test_render_sizes_and_png():
    for image in (
        render.render_text("Zażółć gęślą", scale=1),
        render.render_text("21\n45", scale=2, color=[255, 160, 0]),
        render.render_fill([0, 0, 255]),
    ):
        assert image.size == (32, 32)
        png = render.to_png(image, brightness=50)
        assert Image.open(BytesIO(png)).size == (32, 32)
        assert len(png) < 509 * 4  # a few BLE writes at most


def test_render_file_fits(tmp_path):
    source = tmp_path / "wide.png"
    Image.new("RGB", (200, 100), (255, 0, 0)).save(source)
    for fit in ("contain", "cover", "stretch"):
        assert render.render_file(str(source), fit).size == (32, 32)


# --------------------------------------------------------------- icons
gfx = _load("gfx")
icons = _load("icons")
flags = _load("flags")
aircraft = _load("aircraft")


def test_every_icon_renders_and_encodes():
    from datetime import datetime
    for name in icons.ICONS + ["something-new"]:
        for caption in (None, "", "12°C"):
            image = icons.render_icon(name, caption, now=datetime(2026, 10, 22))
            assert image.size == (32, 32)
            assert len(render.to_png(image)) < 2500


def test_animation_moves():
    for name in ("autumn", "winter", "spring", "summer", "rainy", "snowy", "sunny", "fog"):
        frames = {icons.render_icon(name, frame=f).tobytes() for f in range(4)}
        assert len(frames) > 1, name


def test_moon_phase_known_dates():
    from datetime import UTC, datetime
    full = icons.moon_phase(datetime(2026, 10, 26, 4, 12, tzinfo=UTC))
    new = icons.moon_phase(datetime(2026, 11, 9, 7, 2, tzinfo=UTC))
    # the mean cycle is within about a day of the real moon (1 day = 0.034)
    assert abs(full - 0.5) < 0.034
    assert min(new, 1 - new) < 0.034
    assert icons.moon_name(full) == "FULL"
    assert icons.moon_name(full, "pl") == "PEŁNIA"


def test_season():
    from datetime import datetime
    assert icons.season_for(datetime(2026, 10, 22)) == "autumn"
    assert icons.season_for(datetime(2026, 1, 5)) == "winter"


def test_alert_pictures_animate():
    for name in ("smog", "heating"):
        frames = {icons.render_icon(name, "PM 48", frame=f).tobytes() for f in range(4)}
        assert len(frames) > 1, name
    assert "heating" in icons.ANIMATED and "smog" in icons.ICONS


# --------------------------------------------------------------- clock
def test_clock_face():
    image = render.render_clock("17:36", [120, 230, 140], "9.6°C", None, "PM 12", [0, 220, 90], 12)
    assert image.size == (32, 32)
    assert image.getpixel((16, 11)) != (0, 0, 0)  # divider
    assert image.getpixel((3, 28)) != (0, 0, 0)  # bar started
    blank = render.render_clock("--:--")
    assert blank.getpixel((3, 28)) == (0, 0, 0)  # no bar without a value


# ------------------------------------------------------------ aircraft
ADSB = {"aircraft": [
    {"hex": "48ae01", "flight": "LOT3KA  ", "t": "B38M", "lat": 50.20, "lon": 20.10,
     "alt_baro": 35000, "gs": 450, "track": 290, "seen_pos": 1.2},
    {"hex": "4b1801", "flight": "SWR1488", "lat": 50.10, "lon": 19.90, "alt_baro": "ground"},
    {"hex": "3c6589", "flight": "DLH4AB", "lat": 50.00, "lon": 19.80, "alt_baro": 24000, "seen_pos": 80},
    {"hex": "471f8a", "lat": 49.90, "lon": 19.70, "alt_baro": 5200, "track": 45, "seen_pos": 3},
    {"hex": "noposition"},
]}


def test_nearest_aircraft_skips_ground_and_stale():
    nearest = aircraft.pick_nearest(ADSB, 50.06, 19.94)
    assert nearest["callsign"] == "LOT3KA"
    assert 15 < nearest["distance_km"] < 25
    assert nearest["altitude_m"] == round(35000 * 0.3048)
    assert aircraft.pick_nearest(ADSB, 50.06, 19.94, max_km=5) is None
    assert aircraft.pick_nearest({}, 50, 20) is None


def test_nearest_aircraft_without_callsign_uses_hex():
    nearest = aircraft.pick_nearest({"aircraft": [ADSB["aircraft"][3]]}, 49.9, 19.7)
    assert nearest["callsign"] == "471F8A"


def test_aircraft_picture():
    info = aircraft.pick_nearest(ADSB, 50.06, 19.94)
    first, later = aircraft.render_aircraft(info, 0), aircraft.render_aircraft(info, 5)
    assert first.size == (32, 32)
    assert first.tobytes() != later.tobytes()  # text alternates
    assert len(render.to_png(first)) < 2500


# --------------------------------------------------------- flip clock
def test_flip_clock_frames():
    final = render.render_flip_clock("18:00", line1="9.6°C", line2="PM 12", bar_value=12)
    mid0 = render.render_flip_clock("18:00", "17:59", 0)
    mid1 = render.render_flip_clock("18:00", "17:59", 1)
    plain = render.render_flip_clock("18:00")
    assert final.size == (32, 32)
    assert len({mid0.tobytes(), mid1.tobytes(), plain.tobytes()}) == 3  # motion frames differ
    assert render.render_flip_clock("18:00", "18:00", 0).tobytes() == plain.tobytes()


# -------------------------------------------------------------- flags
def test_country_from_icao_and_registration():
    assert flags.country_for("48ae01") == "PL"
    assert flags.country_for("4CA8F1") == "IE"
    assert flags.country_for("3c6589") == "DE"
    assert flags.country_for("4d2153") == "MT"
    assert flags.country_for("~2a1b3c") is None
    assert flags.country_for(None, "SP-LVA") == "PL"
    assert flags.country_for("", "N123AB") == "US"
    assert flags.country_for("", "9H-QAA") == "MT"


def test_every_known_country_has_a_flag():
    for *_, code in flags.ICAO_BLOCKS:
        c = gfx.Canvas()
        assert flags.draw_flag(c, code, 17, 10, 13, 9), code


def test_plane_with_flag():
    info = aircraft.pick_nearest(ADSB, 50.06, 19.94)
    assert info["country"] == "PL"
    with_flag = aircraft.render_aircraft(info, 0)
    without = aircraft.render_aircraft(dict(info, country=None), 0)
    assert with_flag.getpixel((24, 12)) != without.getpixel((24, 12))


def test_night_tint_is_red_only():
    image = render.apply_tint(render.render_flip_clock("23:15", line1="6.1°C", line2="PM 41", bar_value=41), [255, 25, 0])
    colours = {px for px in image.getdata() if px != (0, 0, 0)}
    assert colours and all(r >= g and b == 0 for r, g, b in colours)
    assert render.apply_tint(image, None) is image


# -------------------------------------------------------------- aurora
aurora = _load("aurora")
NEW_FORMAT = [{"time_tag": f"2026-11-01T{h:02d}:00:00", "kp": k, "observed": o, "noaa_scale": None}
              for h, k, o in ((9, 2.3, "observed"), (12, 2.7, "observed"), (15, 3.3, "estimated"),
                              (18, 4.7, "predicted"), (21, 6.3, "predicted"))] + \
             [{"time_tag": f"2026-11-02T{h:02d}:00:00", "kp": k, "observed": "predicted", "noaa_scale": None}
              for h, k in ((0, 5.7, ), (3, 4.3), (6, 3.0), (9, 2.3), (12, 2.0))]
OLD_FORMAT = [["time_tag", "kp", "observed", "noaa_scale"]] + \
             [[r["time_tag"].replace("T", " "), f"{r['kp']:.2f}", r["observed"], None] for r in NEW_FORMAT]


def test_aurora_both_formats_same_result():
    from datetime import UTC, datetime
    now = datetime(2026, 11, 1, 16, 30, tzinfo=UTC)  # inside the 15:00 slot
    a, b = aurora.next_hours(NEW_FORMAT, now), aurora.next_hours(OLD_FORMAT, now)
    assert [r["kp"] for r in a] == [r["kp"] for r in b] == [3.3, 4.7, 6.3, 5.7, 4.3, 3.0, 2.3, 2.0]
    info = aurora.summary(a)
    assert info["max_kp"] == 6.3 and info["peak_time"].startswith("2026-11-01T21:00")
    assert aurora.next_hours({"bad": 1}, now) == [] and aurora.summary([])["max_kp"] is None


def test_aurora_picture():
    from datetime import UTC, datetime
    slots = aurora.next_hours(NEW_FORMAT, datetime(2026, 11, 1, 16, tzinfo=UTC))
    first, later = aurora.render_aurora(slots, 0), aurora.render_aurora(slots, 3)
    assert first.size == (32, 32) and first.tobytes() != later.tobytes()
    assert len(render.to_png(first)) < 2500
    assert aurora.render_aurora([], 0).size == (32, 32)


def test_captions_in_both_languages_fit_the_panel():
    for lang in icons.LANGUAGES:
        words = icons.MOON_NAMES[lang] + [icons.CHARGING[lang]] + list(icons.SEASON_NAMES[lang].values())
        for word in words:
            assert render.text_width(word) <= 32, (lang, word)
    assert icons.language_for("pl-PL") == "pl" and icons.language_for("de") == "en" and icons.language_for(None) == "en"
    en = icons.render_icon("heating", None, frame=0, lang="en")
    pl = icons.render_icon("heating", None, frame=0, lang="pl")
    assert en.tobytes() != pl.tobytes()


def test_night_versions_replace_the_sun():
    from datetime import datetime
    for name in ("sunny", "partlycloudy", "summer"):
        day = icons.render_icon(name, "", frame=1, now=datetime(2026, 7, 1))
        night = icons.render_icon(name, "", frame=1, now=datetime(2026, 7, 1), night=True)
        assert day.tobytes() != night.tobytes(), name
        # the sun's strong orange (high red, mid green, low blue) is gone at night
        orange = [p for p in night.getdata() if p[0] > 200 and 80 < p[1] < 190 and p[2] < 60]
        assert len(orange) < 5, name
    # pictures without a sun do not change
    assert icons.render_icon("rainy", "", frame=1).tobytes() == icons.render_icon("rainy", "", frame=1, night=True).tobytes()


def test_ovation_nowcast_at_home_and_north():
    grid = [[lon, lat, 0] for lon in range(360) for lat in range(-90, 91)]
    values = {(19, 50): 3, (19, 54): 18, (22, 56): 25, (19, 60): 90, (30, 55): 70}
    data = {"Forecast Time": "2026-11-06T06:40:00Z",
            "coordinates": [[lo, la, values.get((lo, la), v)] for lo, la, v in grid]}
    now = aurora.ovation_at(data, 50.2547, 19.0146)
    assert now["nowcast_local"] == 3
    # within 6 deg north and 4 deg east/west: (22,56)=25 counts, (19,60) and (30,55) are too far
    assert now["nowcast_horizon"] == 25
    assert now["nowcast_time"] == "2026-11-06T06:40:00Z"
    # western longitudes are stored 0..359
    west = aurora.ovation_at({"coordinates": [[358, 52, 40]]}, 52.0, -2.0)
    assert west["nowcast_local"] == 40
    assert aurora.ovation_at({}, 50, 19)["nowcast_local"] is None


def test_no_validation_command_by_default():
    """The validation command makes the panel flash its stored animations."""
    async def run():
        fake = FakePanel()
        session = protocol.PanelSession(fake, max_write=509)
        protocol.STEP_DELAY, saved = 0, protocol.STEP_DELAY
        try:
            await session.start()
            png = render.to_png(render.render_fill([255, 0, 0]))
            for _ in range(65):
                await session.send_png(png)
        finally:
            protocol.STEP_DELAY = saved
        return fake

    fake = asyncio.run(run())
    assert not [w for w, _ in fake.writes if w == protocol.FRAME_VALIDATION]


def test_size_from_handshake():
    async def run(wide):
        session = protocol.PanelSession(FakePanel(wide=wide))
        await session.start()
        assert session.size is None
        await session.ensure_primed()
        return session.size

    assert asyncio.run(run(False)) == (32, 32)
    assert asyncio.run(run(True)) == (64, 16)


# ------------------------------------------------------------ wide panel
def _load_all():
    for name in ("gfx", "flags", "icons", "aircraft", "aurora", "wide"):
        if f"bkpkg.{name}" not in sys.modules:
            _load(name)
    return sys.modules["bkpkg.wide"], sys.modules["bkpkg.icons"]


def test_wide_layouts_are_64x16():
    from datetime import UTC, datetime, timedelta

    wide, icons = _load_all()
    images = [
        wide.render_clock_wide("21:47", line1="9°C", line2="PM 12", bar_value=12),
        wide.render_clock_wide("21:48", "21:47", 0, line1="9°C"),
        wide.render_clock_wide("07:05", style="classic", line1="12°C", line2="PM 8"),
        wide.render_aircraft_wide({"callsign": "LOT3925", "type": "B738", "country": "PL",
                                   "track": 250, "altitude_m": 10500, "distance_km": 23}),
        wide.render_aircraft_wide({"callsign": "N123", "track": 90}, 5),  # no country
        wide.render_aurora_wide([{"time": datetime(2026, 11, 7, tzinfo=UTC) + timedelta(hours=3 * i),
                                  "kp": k} for i, k in enumerate([2, 4, 6.3, 5])], 1),
        wide.render_aurora_wide([]),
        render.render_text("HELLO WORLD", size=(64, 16)),
        render.render_fill([1, 2, 3], (64, 16)),
    ]
    for name in icons.ICONS:
        images.append(wide.render_icon_wide(name, frame=2))
        images.append(wide.render_icon_wide(name, "", frame=1, night=True))
    assert all(image.size == (64, 16) for image in images)
    # the clock leaves the right half for the text lines
    assert images[0].crop((32, 0, 64, 16)).getbbox() is not None


def test_wide_captions_fit():
    wide, icons = _load_all()
    for lang in icons.LANGUAGES:
        for name in ("moon", "heating", "spring", "summer", "autumn", "winter"):
            caption = wide.auto_caption(name, lang)
            assert caption and render.text_width(caption) <= 46, (lang, caption)


def test_readings_both_sizes():
    readings = _load("readings")
    values = {"temperature": -12.3, "humidity": 81.0, "pm25": 88.0, "pressure": None}
    for size in ((64, 16), (32, 32)):
        image = readings.render_readings(values, size)
        assert image.size == size and image.getbbox() is not None
    assert readings.text_for("temperature", 6.14) == "6.1°"
    assert readings.text_for("temperature", -12.3) == "-12°"
    assert readings.color_for("pm25", 88) == (255, 30, 30)


def test_slide_frames_push_left():
    from PIL import Image as PILImage

    wide, _ = _load_all()
    old = PILImage.new("RGB", (64, 16), (255, 0, 0))
    new = PILImage.new("RGB", (64, 16), (0, 0, 255))
    frames = wide.slide_frames(old, new)
    assert len(frames) == 3
    assert frames[0].getpixel((0, 0)) == (255, 0, 0) and frames[0].getpixel((63, 0)) == (0, 0, 255)
    assert frames[1].getpixel((31, 0)) == (255, 0, 0) and frames[1].getpixel((32, 0)) == (0, 0, 255)


def test_font7_glyphs_are_consistent():
    font7 = _load("font7")
    for char, rows in font7.GLYPHS.items():
        assert len(rows) == 7, char
        assert len({len(r) for r in rows}) == 1, char
    assert font7.fits("SAT 7") and font7.width("SAT 7") <= 30
    for word in ("CHARGING", "CRESCENT", "AUTUMN", "LOT3925", "↑10.5KM"):
        assert font7.width(word) <= 46, word


def test_wide_boards():
    from datetime import UTC, datetime, timedelta

    _load_all()
    boards = _load("boards")
    plane = {"callsign": "LOT3925", "type": "B738", "country": "PL", "track": 250,
             "altitude_m": 10500, "distance_km": 23}
    start = datetime(2026, 11, 7, 14, tzinfo=UTC)
    points = [(start + timedelta(hours=h), 5.0 + h * 0.2) for h in range(25)]
    temps, day = boards.sky_columns(points, start, lambda t: 7 <= t.hour < 16)
    assert len(temps) == 64 and None not in temps and day[0] and not day[20]
    images = [
        boards.render_flight_board(plane, 0, 80), boards.render_flight_board({"callsign": "X"}, 5),
        boards.render_sky_graph(temps, day, 16, 1), boards.render_sky_graph([None] * 64, [True] * 64, 0),
        boards.render_room("Kitchen", 22.4, 45, 2), boards.render_room("Kitchen", None),
        boards.render_traffic([10, 50, 120], [2, 5, 9], 3), boards.render_traffic([], [], 0),
    ]
    images += [boards.render_retro(name, f) for name in boards.RETRO for f in (0, 7, 15)]
    assert all(image.size == (64, 16) for image in images)
    assert boards.comfort_color(22) == (110, 235, 140)


def test_frame_in_small_pieces():
    """244-byte pieces: the frame arrives whole, in more writes."""
    async def run():
        fake = FakePanel()
        session = protocol.PanelSession(fake, max_write=244)
        protocol.STEP_DELAY, saved = 0, protocol.STEP_DELAY
        try:
            await session.start()
            png = render.to_png(render.render_text("HELLO WORLD 123"), 100)
            fake.writes.clear()
            await session.send_png(png)
        finally:
            protocol.STEP_DELAY = saved
        return fake, png

    fake, png = asyncio.run(run())
    pieces = [w for w, _ in fake.writes]
    assert not any(response for _, response in fake.writes)  # write commands by default
    assert all(len(p) <= 244 for p in pieces)
    assert png in b"".join(pieces)


def test_unconfirmed_picture_raises():
    """No 05 00 02 00 03 after the pieces: FrameNotConfirmed (panel then falls back)."""
    class Silent(FakePanel):
        def _notify(self, text):
            if not text.startswith("05"):
                super()._notify(text)

    async def run():
        session = protocol.PanelSession(Silent(), max_write=244)
        saved = protocol.STEP_DELAY, protocol.ACK_TIMEOUT
        protocol.STEP_DELAY, protocol.ACK_TIMEOUT = 0, 0.2
        try:
            await session.start()
            await session.send_png(render.to_png(render.render_fill([1, 2, 3])))
        finally:
            protocol.STEP_DELAY, protocol.ACK_TIMEOUT = saved

    try:
        asyncio.run(run())
    except protocol.FrameNotConfirmed:
        pass
    else:
        raise AssertionError("expected FrameNotConfirmed")


def test_forecast_and_date_clock():
    _load_all()
    forecast = _load("forecast")
    wide = sys.modules["bkpkg.wide"]
    points = [{"condition": "rainy", "label": "10H", "temperature": 6.4},
              {"condition": "partlycloudy", "label": "ŚR", "temperature": -12}]
    for size in ((64, 16), (32, 32)):
        image = forecast.render_forecast(points, size, 1)
        assert image.size == size
    # the second temperature on 32x32 sits low (y 24..30) and must be drawn
    square = forecast.render_forecast(points, (32, 32))
    assert square.crop((16, 24, 32, 31)).getbbox() is not None
    clock = wide.render_clock_wide("07:24", line1="6.4°", line2="PM 27", date_text="PON 9.11")
    assert clock.size == (64, 16)
    assert clock.crop((0, 11, 32, 16)).getbbox() is not None  # the date line
    assert forecast.DAY_NAMES["pl"][2] == "ŚR"


def test_date_clock_rows_line_up():
    """Left (time, date) and right (temperature, PM) use the same rows and sizes."""
    _load_all()
    wide = sys.modules["bkpkg.wide"]
    img = wide.render_clock_wide("18:52", line1="-12.3°", line2="PM 112", date_text="ŚR 11.11",
                                 time_color=[255, 255, 255])
    px = img.load()

    def rows(x0, x1):
        return [y for y in range(16) if any(max(px[x, y]) > 100 for x in range(x0, x1))]

    assert rows(2, 30) == rows(33, 64) == [1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15]


def test_games():
    _load_all()
    games = _load("games")
    for name in games.GAMES:
        for f in range(0, 50, 7):
            image = games.render_game(name, f, seed=3)
            assert image.size == (64, 16) and image.getbbox() is not None
    # the terminal ends with a file count
    last = games.render_terminal(games.terminal_frames(3) - 2, 3)
    assert last.getbbox() is not None


# Bytes recorded from the panel's phone app (2026-11-11), to check our frames.
APP_GIF_HEADER = bytes.fromhex("53 01 03 00 00 44 01 00 00 eb 35 82 3f 02 04")
APP_PLAYLIST_ONE = bytes.fromhex("07 00 08 80 01 00 08")
APP_PLAYLIST_TWO = bytes.fromhex("08 00 08 80 02 00 07 08")


def test_frames_match_the_app():
    gif = b"G" * 324
    frame = protocol.build_frame(gif, protocol.KIND_GIF, mode=0x02, slot=4)
    assert frame[:9] == APP_GIF_HEADER[:9] and frame[13:15] == APP_GIF_HEADER[13:15]
    assert len(frame) == 339
    assert protocol.playlist_command([8]) == APP_PLAYLIST_ONE
    assert protocol.playlist_command([7, 8]) == APP_PLAYLIST_TWO
    assert protocol.brightness_command(94) == bytes.fromhex("05 00 04 80 5e")
    assert protocol.is_ack_frame(bytes.fromhex("05 00 03 00 03"))
    assert protocol.command_ack(bytes.fromhex("05 00 08 80 01")) == 0x08
    # a live picture keeps slot 101
    assert protocol.build_frame(b"P" * 10)[13:15] == b"\x00\x65"


def test_store_gif_and_commands():
    from PIL import Image as PILImage

    async def run():
        fake = FakePanel(wide=True)
        session = protocol.PanelSession(fake, max_write=244, acknowledged=True)
        await session.start()
        frames = [PILImage.new("RGB", (64, 16), (255 * (i % 2), 0, 255)) for i in range(4)]
        gif = render.to_gif(frames, 90)
        await session.command(protocol.playlist_command([3]))
        await session.send_gif(gif, 3)
        await session.command(protocol.brightness_command(40))
        return fake, gif

    fake, gif = asyncio.run(run())
    assert fake.frame[2] == 0x04  # the last command: brightness
    with PILImage.open(__import__("io").BytesIO(gif)) as image:
        assert image.size == (64, 16) and image.n_frames == 4


def test_runner_ledge_is_dark_and_warm():
    """The ledge looked almost white-pink on the panel: keep it dark red-brown."""
    _load_all()
    games = _load("games")
    image = games.render_runner(0)
    px = image.load()
    ledge = [px[x, y] for x in range(64) if not 12 <= x < 32  # not under the runner
             for y in (13, 14, 15) if px[x, y][0] > px[x, y][2]]  # not the sky in the gap
    assert len(ledge) > 60
    for r, g, b in ledge:
        assert max(r, g, b) <= 160 and r > g > b


# ------------------------------------------------- panel state (HA stubbed)
def _panel_module():
    """panel.py with the few Home Assistant / bleak names it imports stubbed out."""
    if "bkpkg.panel" in sys.modules:
        return sys.modules["bkpkg.panel"]

    def stub(name: str, **attrs):
        module = sys.modules.get(name) or types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module
        return module

    class HomeAssistantError(Exception):
        pass

    stub("bleak"), stub("bleak.exc", BleakError=type("BleakError", (Exception,), {}))
    stub("bleak_retry_connector", BleakClientWithServiceCache=object, establish_connection=None)
    stub("homeassistant"), stub("homeassistant.components")
    stub("homeassistant.components.bluetooth", async_ble_device_from_address=None)
    sys.modules["homeassistant.components"].bluetooth = sys.modules["homeassistant.components.bluetooth"]
    stub("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    stub("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    stub("homeassistant.helpers"), stub("homeassistant.helpers.event", async_call_later=None)
    return _load("panel")


class RecordingPanel(FakePanel):
    """FakePanel that keeps every complete frame / command, and can refuse GIFs."""

    def __init__(self, refuse_gifs: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.frames: list[bytes] = []
        self.refuse_gifs = refuse_gifs
        self.is_connected = True

    def _notify(self, hex_payload: str) -> None:
        if self.refuse_gifs and hex_payload.startswith("05 00 03"):
            return
        super()._notify(hex_payload)

    async def write_gatt_char(self, uuid, data, response):
        before = getattr(self, "frame", None)
        await super().write_gatt_char(uuid, data, response)
        if getattr(self, "frame", None) is not before:
            self.frames.append(self.frame)


def _connected_panel(fake: RecordingPanel):
    panel_mod = _panel_module()
    panel = panel_mod.BkLightPanel(None, "AA:BB:CC:DD:EE:FF", "test panel")

    async def ensure_connected() -> None:
        if panel._session is None:
            panel._client = fake
            panel._session = protocol.PanelSession(fake, max_write=244, acknowledged=True)
            await panel._session.start()

    async def disconnect() -> None:
        panel._client = panel._session = None

    panel._ensure_connected = ensure_connected
    panel._disconnect = disconnect
    return panel_mod, panel


def _kinds(frames: list[bytes]) -> list[str]:
    """playlist [..] / brightness n / gif slot n / png, in order."""
    out = []
    for f in frames:
        if f[2:4] == b"\x08\x80":
            out.append(f"playlist {list(f[6:])}")
        elif f[2:4] == b"\x04\x80":
            out.append(f"brightness {f[4]}")
        elif f[2] == protocol.KIND_GIF:
            out.append(f"gif {f[14]}")
        else:
            out.append("png")
    return out


def test_stored_animation_then_live_picture():
    """Upload once (CRC), play by playlist, then a live picture restores the background."""
    stored = _load("stored")
    gif = stored.retro_gif("agent")
    png = render.to_png(Image.new("RGB", (64, 16), (10, 20, 30)))
    saved = []

    async def run():
        fake = RecordingPanel(wide=True)
        _, panel = _connected_panel(fake)
        panel.on_stored_change = saved.append
        await panel.async_set_playlist([20])          # background, e.g. the safety animation
        await panel.async_send_png(png)
        assert await panel.async_play_stored(gif, 29, brightness=60) is True
        await panel.async_send_png(png)               # back to the clock
        assert await panel.async_play_stored(gif, 29, brightness=60) is False  # same CRC: no upload
        await panel.async_send_png(png)
        return fake

    fake = asyncio.run(run())
    assert _kinds(fake.frames) == [
        "playlist [20]", "png",
        "brightness 60", "playlist [29]", "gif 29",
        "playlist [20]", "brightness 100", "png",
        "brightness 60", "playlist [29]",
        "playlist [20]", "brightness 100", "png",
    ]
    assert saved[-1] == {29: binascii.crc32(gif)}


def test_stored_animation_dims_relative_to_wanted_brightness():
    gif = _load("stored").retro_gif("terminal")

    async def run():
        fake = RecordingPanel(wide=True)
        _, panel = _connected_panel(fake)
        panel.load_stored({"26": binascii.crc32(gif)})  # known from an earlier run
        await panel.async_set_brightness(50)
        await panel.async_play_stored(gif, 26, brightness=60)
        await panel.async_send_png(render.to_png(Image.new("RGB", (64, 16))))
        return fake

    assert _kinds(asyncio.run(run()).frames) == [
        "brightness 50", "brightness 30", "playlist [26]", "brightness 50", "png"]


def test_refused_upload_is_not_retried():
    gif = _load("stored").retro_gif("chomper")
    protocol.ACK_TIMEOUT = 0.05

    async def run():
        fake = RecordingPanel(refuse_gifs=True, wide=True)
        panel_mod, panel = _connected_panel(fake)
        try:
            await panel.async_play_stored(gif, 27)
        except panel_mod.UploadRefused:
            pass
        else:
            raise AssertionError("expected UploadRefused")
        return fake, panel

    try:
        fake, panel = asyncio.run(run())
    finally:
        protocol.ACK_TIMEOUT = 5.0
    assert _kinds(fake.frames).count("gif 27") == 1
    assert panel.upload_refused_recently(27) and not panel.is_stored(27, gif)


def test_retro_gifs_are_stable_and_small():
    stored = _load("stored")
    assert len(set(stored.RETRO_SLOTS.values())) == len(stored.RETRO_SLOTS)
    assert min(stored.RETRO_SLOTS.values()) > stored.SAFETY_DARK_SLOT
    for name in stored.RETRO_SLOTS:
        gif = stored.retro_gif(name)
        assert gif == stored.retro_gif(name)  # same bytes, so the CRC check skips the upload
        assert len(gif) < 32_000
        with Image.open(BytesIO(gif)) as image:
            assert image.size == (64, 16) and image.n_frames == stored.retro_timing(name)[0]


def test_safety_animation_becomes_the_background():
    stored = _load("stored")
    gif = stored.safety_gif((32, 32), "calm")
    png = render.to_png(Image.new("RGB", (32, 32), (40, 0, 0)))

    async def run():
        fake = RecordingPanel()
        _, panel = _connected_panel(fake)
        await panel.async_send_png(png)
        assert await panel.async_set_background(gif, 20) is True
        assert await panel.async_set_background(gif, 20) is False  # same CRC: playlist only
        await panel.async_play_stored(stored.retro_gif("agent"), 29)
        await panel.async_send_png(png)
        return fake

    assert _kinds(asyncio.run(run()).frames) == [
        "png",
        "playlist [20]", "gif 20", "png",        # live picture back straight away
        "playlist [20]", "png",
        "playlist [29]", "gif 29",
        "playlist [20]", "png",                  # after an animation: background again
    ]


def test_safety_frames_are_calm():
    stored = _load("stored")
    for size in ((32, 32), (64, 16)):
        first = stored.render_safety(size, 0)
        peak = stored.render_safety(size, stored.SAFETY_FRAMES // 2)
        ember = lambda im: max(sum(p) for p in [im.getpixel((size[0] // 2, size[1] // 2))])
        assert ember(first) < 60 < ember(peak)       # starts dark, so a switch does not flash
        assert max(max(p) for p in peak.get_flattened_data()) <= 220  # never glaring
        with Image.open(BytesIO(stored.safety_gif(size))) as gif:
            total = 0
            for i in range(gif.n_frames):  # identical neighbours may be merged: count time
                gif.seek(i)
                total += gif.info["duration"]
            assert gif.size == size and total == stored.SAFETY_FRAMES * stored.SAFETY_FRAME_MS
    with Image.open(BytesIO(stored.safety_gif((64, 16), "black"))) as dark:
        assert dark.convert("RGB").getbbox() is None


def test_brightness_and_background_come_back_after_a_reconnect():
    png = render.to_png(Image.new("RGB", (64, 16), (255, 25, 0)))
    gif = _load("stored").safety_gif((64, 16), "calm", [255, 25, 0])

    async def run():
        fake = RecordingPanel(wide=True)
        panel_mod, panel = _connected_panel(fake)
        real = panel_mod.BkLightPanel._ensure_connected
        await panel.async_set_brightness(30)          # night: the panel dims, pixels stay full
        await panel.async_set_background(gif, 21)
        await panel.async_send_png(png)
        # a dropped link: the real _ensure_connected forgets the panel's state
        panel._session = None
        panel._brightness, panel._playlist = 30, [21]
        panel._client = None
        if panel._wanted_brightness is not None:
            panel._brightness = None
        if panel._background:
            panel._playlist = None
        assert "self._brightness = None" in __import__("inspect").getsource(real)
        await panel.async_send_png(render.to_png(Image.new("RGB", (64, 16), (200, 20, 0))))
        await panel.async_set_brightness(30)          # unchanged: nothing sent
        return fake

    assert _kinds(asyncio.run(run()).frames) == [
        "brightness 30", "playlist [21]", "gif 21", "png",
        "playlist [21]", "brightness 30", "png",
    ]
