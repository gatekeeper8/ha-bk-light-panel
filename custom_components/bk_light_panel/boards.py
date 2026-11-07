"""Extra screens for the wide 64x16 panel.

Flight board, sky graph (24 h temperature with day and night), room board,
network traffic graph and retro computer screens (Atari, Commodore 64,
Space Invaders). No Home Assistant imports.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from PIL import Image

from . import font7
from .aircraft import PLANE, _altitude_text
from .flags import draw_flag
from .gfx import Canvas, rotate
from .render import BAR_COLORS, CHAR_GAP, _glyph, _scaled, text_width

W, H = 64, 16
RGB = tuple[int, int, int]


def _blank(bg: RGB = (0, 0, 0)) -> Image.Image:
    return Image.new("RGB", (W, H), bg)


def _small(pixels, text: str, x: int, y: int, color: RGB, x_max: int = W) -> int:
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and 0 <= x + rx < x_max and 0 <= y + ry < H:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP
    return x


def _strip(text: str, color: RGB, bg: RGB = (0, 0, 0), y: int = 4, gap: int = 12) -> Image.Image:
    """The text drawn once on a long image, for scrolling."""
    width = font7.width(text) + gap
    image = Image.new("RGB", (width, H), bg)
    font7.draw(image.load(), text, 0, y, color, (0, width))
    return image


def _scrolled(strip: Image.Image, offset: int, bg: RGB = (0, 0, 0)) -> Image.Image:
    """A 64-pixel window into a strip that repeats endlessly."""
    offset %= strip.width
    frame = Image.new("RGB", (W, H), bg)
    x = -offset
    while x < W:
        frame.paste(strip, (x, 0))
        x += strip.width
    return frame


# ------------------------------------------------------------ flight board
def _plane_icon(track: float, frame: int) -> Image.Image:
    c = Canvas()
    cx, cy, size = 7.5, 7.5, 5.6
    a = math.radians(track)
    for i in range(1, 4):  # short contrail, drifting
        back = size * 0.6 + i * 1.4 - (frame % 4) * 0.4
        c.paint((150, 200, 255), c.circle_mask(cx - math.sin(a) * back, cy + math.cos(a) * back, 0.55),
                0.5 - i * 0.12)
    m = c.poly_mask(rotate(PLANE, track, cx, cy, scale=size))
    c.glow(m, (90, 160, 255), radius=1.0, strength=0.4)
    c.paint(c.vgrad((255, 255, 255), (150, 190, 240), cy - size, cy + size), m)
    return c.finish().crop((0, 0, 15, 15)).resize((10, 10), Image.Resampling.BOX)


def render_flight_board(info: dict[str, Any], frame: int = 0, max_km: float = 100.0) -> Image.Image:
    """Flag, callsign and the plane on its track; altitude, distance and a closeness bar."""
    image = _blank()
    flag = Canvas()
    has_flag = draw_flag(flag, info.get("country"), 1.0, 1.0, 11.0, 7.0) if info.get("country") else False
    x0 = 0
    if has_flag:
        image.paste(flag.finish().crop((1, 1, 12, 8)), (0, 0))
        x0 = 13
    image.paste(_plane_icon(info.get("track") or 0.0, frame), (54, 0))
    pixels = image.load()
    show_type = (frame // 4) % 2 == 1 and info.get("type")
    name = str(info.get("type") if show_type else info.get("callsign", ""))
    while name and font7.width(name) > 53 - x0:
        name = name[:-1]
    font7.draw(pixels, name, x0, 0, (255, 190, 90), (0, 53))
    _small(pixels, _altitude_text(info.get("altitude_m")), 0, 9, (150, 210, 255))
    distance = f"↔{round(info.get('distance_km') or 0)}KM"
    _small(pixels, distance, W - text_width(distance), 9, (180, 255, 180))
    near = max(0.0, min(1.0, 1 - (info.get("distance_km") or 0) / max_km))
    lit = max(1, round(W * near))
    for x in range(W):  # closeness: grows and turns red as the plane comes nearer
        color = BAR_COLORS[min(3, int(x / W * 4))]
        pixels[x, 15] = color if x < lit else _scaled(color, 0.1)
    return image


# --------------------------------------------------------------- sky graph
SKY_DAY_LINE, SKY_DAY_FILL = (255, 215, 110), (120, 85, 20)
SKY_NIGHT_LINE, SKY_NIGHT_FILL = (150, 175, 255), (30, 40, 120)
_STARS = ((3, 2), (11, 5), (19, 1), (27, 4), (36, 2), (44, 6), (52, 1), (60, 4), (7, 7), (32, 6), (57, 7))


def render_sky_graph(
    temps: list[float | None], daylight: list[bool], now_col: int, frame: int = 0
) -> Image.Image:
    """64 columns of temperature; day columns warm with a sun, night blue with stars.

    temps / daylight: one value per column (None = no data); now_col: the
    column of 'now' (a dotted line that blinks).
    """
    image = _blank()
    pixels = image.load()
    known = [t for t in temps if t is not None]
    if not known:
        _small(pixels, "NO DATA", 18, 5, (140, 140, 140))
        return image
    lo, hi = min(known), max(known)
    span = max(hi - lo, 4.0)  # flat days do not get exaggerated
    base = lo - (span - (hi - lo)) / 2

    def y_of(t: float) -> int:
        return round(14 - (t - base) / span * 7)  # curve between y 7 and 14

    # night: stars in the sky above the curve, twinkling
    for i, (x, y) in enumerate(_STARS):
        if 0 <= x < W and not daylight[x] and (frame + i) % 5 != 0:
            pixels[x, y] = (150, 150, 190) if (frame + i) % 3 else (230, 230, 255)
    # day: a sun at the middle of each daylight stretch
    x = 0
    while x < W:
        if daylight[x]:
            start = x
            while x < W and daylight[x]:
                x += 1
            cx = max(14, min(48, (start + x - 1) // 2))  # clear of the corner labels
            if x - start >= 8 and start <= cx < x:
                for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    pixels[cx + dx, 2 + dy] = (255, 200, 60)
                for dx, dy in ((2, 2), (-2, 2), (2, -2), (-2, -2)):
                    if frame % 2 == 0:
                        pixels[cx + dx, 2 + dy] = (200, 140, 20)
        x += 1
    for x, t in enumerate(temps):
        if t is None:
            continue
        y = y_of(t)
        line, fill = (SKY_DAY_LINE, SKY_DAY_FILL) if daylight[x] else (SKY_NIGHT_LINE, SKY_NIGHT_FILL)
        for yy in range(y + 1, H):
            pixels[x, yy] = fill
        pixels[x, y] = line
    # highest and lowest value, small, top corners
    _small(pixels, f"{round(hi)}°", 0, 0, (255, 190, 110))
    low = f"{round(lo)}°"
    _small(pixels, low, W - text_width(low), 0, (140, 180, 255))
    if 0 <= now_col < W and frame % 2 == 0:
        for y in range(0, H, 2):
            pixels[now_col, y] = (255, 255, 255)
    return image


def sky_columns(
    points: list[tuple[datetime, float]],
    start: datetime,
    is_day,
    hours: float = 24.0,
) -> tuple[list[float | None], list[bool]]:
    """Interpolate (time, value) points into 64 columns from start; is_day(time) -> bool."""
    points = sorted(points)
    step = timedelta(hours=hours) / W
    temps: list[float | None] = []
    daylight: list[bool] = []
    j = 0
    for i in range(W):
        t = start + step * i + step / 2
        daylight.append(bool(is_day(t)))
        while j + 1 < len(points) and points[j + 1][0] <= t:
            j += 1
        if not points or t < points[0][0] or t > points[-1][0] + timedelta(hours=1):
            temps.append(None)
            continue
        if j + 1 < len(points) and points[j][0] <= t:
            (t0, v0), (t1, v1) = points[j], points[j + 1]
            k = (t - t0).total_seconds() / max(1.0, (t1 - t0).total_seconds())
            temps.append(v0 + (v1 - v0) * k)
        else:
            temps.append(points[j][1])
    return temps, daylight


# -------------------------------------------------------------- room board
def comfort_color(temperature: float | None) -> RGB:
    if temperature is None:
        return (140, 140, 140)
    if temperature < 19:
        return (120, 180, 255)
    if temperature <= 23.5:
        return (110, 235, 140)
    return (255, 150, 60)


def _house(frame: int) -> Image.Image:
    c = Canvas()
    c.paint(c.vgrad((235, 120, 70), (170, 60, 40), 1, 7), c.poly_mask([(7.5, 1.0), (14.5, 7.5), (0.5, 7.5)]))
    c.paint(c.vgrad((225, 220, 205), (160, 150, 135), 7, 15), c.rrect_mask((2.5, 7.0, 12.5, 15.0), 0.5))
    glow = 0.75 + 0.25 * math.sin(frame * 0.9)
    window = c.rrect_mask((4.0, 8.5, 7.5, 11.5), 0.3)
    c.glow(window, (255, 190, 80), radius=1.0, strength=0.5 * glow)
    c.paint((255, int(190 * glow), 80), window)
    c.paint((110, 70, 40), c.rrect_mask((9.0, 10.0, 11.0, 15.0), 0.3))
    return c.finish().crop((0, 0, 16, 16))


def render_room(
    name: str, temperature: float | None, humidity: float | None = None, frame: int = 0
) -> Image.Image:
    """House with a lit window; room name, temperature (comfort colour), humidity."""
    image = _blank()
    image.paste(_house(frame), (0, 0))
    pixels = image.load()
    label = name.upper()
    while label and font7.width(label) > 46:
        label = label[:-1]
    font7.draw(pixels, label, 18, 0, (235, 225, 205))
    temp = "--°" if temperature is None else (
        f"{temperature:.1f}°" if abs(temperature) < 100 else f"{temperature:.0f}°")
    font7.draw(pixels, temp, 18, 9, comfort_color(temperature))
    if humidity is not None:
        hum = f"{humidity:.0f}%"
        font7.draw(pixels, hum, W - font7.width(hum), 9, (90, 170, 255))
    return image


# ----------------------------------------------------------------- network
def _rate_text(mbit: float) -> str:
    if mbit >= 1000:
        return f"{mbit / 1000:.1f}G"
    if mbit >= 10:
        return f"{mbit:.0f}M"
    return f"{mbit:.1f}M" if mbit >= 1 else f"{mbit * 1000:.0f}K"


def render_traffic(down: list[float], up: list[float], frame: int = 0, scale: float | None = None) -> Image.Image:
    """Mirrored traffic graph: download up from the middle, upload down; newest on the right.

    down / up: Mbit/s, oldest first (the last 64 are used). Particles run
    along the middle, faster with more traffic.
    """
    image = _blank()
    pixels = image.load()
    down, up = list(down)[-W:], list(up)[-W:]
    top = scale or max([1.0, *down, *(u * 2 for u in up)])
    offset = W - len(down)
    for i, value in enumerate(down):
        x = offset + i
        h = round(min(1.0, value / top) * 7)
        for k in range(h):
            t = k / 6
            pixels[x, 6 - k] = (int(40 + 60 * t), int(200 + 55 * t), int(120 + 135 * t))
    offset = W - len(up)
    for i, value in enumerate(up):
        x = offset + i
        h = round(min(1.0, value * 2 / top) * 7)
        for k in range(h):
            t = k / 6
            pixels[x, 9 + k] = (int(150 + 105 * t), int(70 + 30 * t), int(255))
    # the wire in the middle with packets flowing to the right
    now = (down[-1] if down else 0) + (up[-1] if up else 0)
    speed = 1 + min(5, int(now / max(top, 1) * 6))
    for x in range(W):
        pixels[x, 7] = pixels[x, 8] = (25, 25, 40)
    for p in range(0, W, 9):
        x = (p + frame * speed) % W
        pixels[x, 7] = pixels[x, 8] = (255, 255, 255)
    # current rates in the corners, on a dark plate
    for text, y, color in ((f"↓{_rate_text(down[-1] if down else 0)}", 0, (120, 255, 190)),
                           (f"↑{_rate_text(up[-1] if up else 0)}", 11, (210, 140, 255))):
        width = text_width(text)
        for xx in range(W - width - 2, W):
            for yy in range(y, y + 5):
                pixels[xx, yy] = _scaled(pixels[xx, yy], 0.2)
        _small(pixels, text, W - width - 1, y, color)
    return image


# ------------------------------------------------------------------- retro
ATARI_BG, ATARI_FG = (20, 50, 130), (110, 160, 255)
C64_BORDER, C64_BG, C64_FG = (124, 112, 218), (34, 26, 96), (165, 155, 255)
_INVADER = (
    ("..#.....#..", "...#...#...", "..#######..", ".##.###.##.", "###########", "#.#######.#",
     "#.#.....#.#", "...##.##..."),
    ("..#.....#..", "#..#...#..#", "#.#######.#", "###.###.###", "###########", ".#########.",
     "..#.....#..", ".#.......#."),
)
RETRO = ("atari", "c64", "invaders")


def _atari(frame: int, text: str | None) -> Image.Image:
    phase = frame % 40
    if phase < 10:  # READY. with a blinking cursor
        image = _blank(ATARI_BG)
        pixels = image.load()
        font7.draw(pixels, "READY.", 1, 0, ATARI_FG)
        if frame % 2 == 0:
            for x in range(1, 5):
                for y in range(9, 16):
                    pixels[x, y] = ATARI_FG
        return image
    banner = _strip(text or "READY. ATARI 65XE · 64K RAM · ", ATARI_FG, ATARI_BG)
    return _scrolled(banner, (phase - 10) * 4, ATARI_BG)


def _c64(frame: int, text: str | None) -> Image.Image:
    image = _blank(C64_BORDER)
    inner = Image.new("RGB", (W - 4, H - 2), C64_BG)
    image.paste(inner, (2, 1))
    pixels = image.load()
    # the start-up line scrolls along the top in the small font
    boot = text or "**** COMMODORE 64 BASIC V2 **** 64K RAM SYSTEM 38911 BASIC BYTES FREE ****"
    width = text_width(boot) + 20
    offset = (frame * 4) % width
    x = 3 - offset
    while x < W - 2:
        _small(pixels, boot, x, 2, C64_FG, W - 2)
        x += width
    for xx in range(0, 3):  # keep the border clean where the text was clipped
        for yy in range(1, 15):
            if xx < 2:
                pixels[xx, yy] = C64_BORDER
    font7.draw(pixels, "READY.", 3, 8, C64_FG, (2, W - 2))
    if frame % 2 == 0:  # cursor block below READY.
        for xx in range(31, 35):
            for yy in range(8, 15):
                pixels[xx, yy] = C64_FG
    return image


def _invaders(frame: int, text: str | None) -> Image.Image:
    image = _blank()
    pixels = image.load()
    shift = (0, 1, 2, 3, 2, 1)[frame % 6]
    rows = _INVADER[frame % 2]
    for k in range(4):
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                x = shift + k * 16 + rx
                if pixel == "#" and x < W:
                    pixels[x, ry] = (90, 255, 90) if k % 2 == 0 else (255, 90, 220)
    if text:
        label = text.upper()
        _small(pixels, label, (W - text_width(label)) // 2, 10, (255, 255, 255))
    else:  # the player's cannon, moving and shooting
        cx = 8 + (frame * 5) % 48
        for x in range(cx - 3, cx + 4):
            pixels[x, 15] = (90, 200, 255)
        pixels[cx, 14] = (90, 200, 255)
        if frame % 3 == 0:
            for y in (10, 11):
                pixels[cx, y] = (255, 255, 255)
    return image


def render_retro(name: str, frame: int = 0, text: str | None = None) -> Image.Image:
    """atari (READY. + banner), c64 (start-up screen), invaders (marching, optional caption)."""
    return {"atari": _atari, "c64": _c64, "invaders": _invaders}.get(name, _invaders)(frame, text)
