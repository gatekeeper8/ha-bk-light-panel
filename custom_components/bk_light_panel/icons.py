"""Built-in 32x32 pictures: weather, moon phase, seasons, alerts.

Drawn with smooth shapes, gradients and soft glow (see gfx.py), all
original artwork. Most pictures are animated: frame 0, 1, 2 ... turns
the sun's rays, moves rain, snow, fog, leaves and heat.
No Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from PIL import Image

from .const import PANEL_HEIGHT, PANEL_WIDTH
from .gfx import Canvas, curve, mix, rotate
from .render import CHAR_GAP, GLYPH_HEIGHT, _glyph, text_width

ART_H = 25  # picture area when there is a caption below

WEATHER = {
    "sunny", "clear-night", "partlycloudy", "cloudy", "rainy", "pouring",
    "snowy", "snowy-rainy", "hail", "lightning", "lightning-rainy", "fog",
    "windy", "windy-variant", "exceptional",
}
SEASONS = {"spring", "summer", "autumn", "winter"}
ALERTS = {"smog", "heating"}
ANIMATED = (WEATHER - {"exceptional"}) | SEASONS | ALERTS
ICONS = sorted(WEATHER | SEASONS | ALERTS | {"moon", "season"})

# automatic captions; every text fits the 32-pixel width of the panel
LANGUAGES = ("en", "pl")
MOON_NAMES = {
    "en": ["NEW", "CRESCENT", "1ST QTR", "WAXING", "FULL", "WANING", "LAST QTR", "CRESCENT"],
    "pl": ["NÓW", "SIERP", "I KW", "ROŚNIE", "PEŁNIA", "UBYWA", "III KW", "SIERP"],
}
CHARGING = {"en": "CHARGING", "pl": "ŁADUJE"}
SEASON_NAMES = {
    "en": {"spring": "SPRING", "summer": "SUMMER", "autumn": "AUTUMN", "winter": "WINTER"},
    "pl": {"spring": "WIOSNA", "summer": "LATO", "autumn": "JESIEŃ", "winter": "ZIMA"},
}


def language_for(code: str | None) -> str:
    """'pl', 'pl-PL' -> 'pl'; anything else -> 'en'."""
    code = (code or "en").lower()[:2]
    return code if code in LANGUAGES else "en"

# palette
SUN_CORE, SUN_EDGE, SUN_GLOW = (255, 248, 190), (255, 168, 0), (255, 120, 0)
RAY_IN, RAY_OUT = (255, 205, 60), (255, 112, 0)
CLOUD_TOP, CLOUD_BOTTOM = (255, 255, 255), (150, 162, 186)
DARK_TOP, DARK_BOTTOM = (176, 184, 200), (70, 78, 98)
RAIN = (80, 165, 255)
SNOW = (245, 250, 255)
MOON_LIGHT, MOON_SHADE, MOON_NIGHT = (255, 246, 214), (214, 198, 150), (26, 28, 44)


# ------------------------------------------------------------- helpers
def _caption(image: Image.Image, text: str, color) -> None:
    pixels = image.load()
    x = (PANEL_WIDTH - text_width(text)) // 2
    y = PANEL_HEIGHT - GLYPH_HEIGHT - 1
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and 0 <= x + rx < PANEL_WIDTH:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP


def _sun(c: Canvas, cx: float, cy: float, r: float, frame: int, rays: bool = True) -> None:
    c.glow(c.circle_mask(cx, cy, r + 1.5), SUN_GLOW, radius=2.2, strength=0.55)
    if rays:
        spin = frame * 6
        for i in range(12):
            a = math.radians(i * 30 + spin)
            long = i % 2 == 0
            r0, r1, half = r + 1.0, r + (4.6 if long else 3.2), math.radians(9 if long else 7)
            tip = (cx + math.cos(a) * r1, cy + math.sin(a) * r1)
            b1 = (cx + math.cos(a - half) * r0, cy + math.sin(a - half) * r0)
            b2 = (cx + math.cos(a + half) * r0, cy + math.sin(a + half) * r0)
            c.paint(c.rgrad(cx, cy, r + 4.6, RAY_IN, RAY_OUT), c.poly_mask([b1, tip, b2]))
    c.paint(c.rgrad(cx - r * 0.3, cy - r * 0.3, r * 1.4, SUN_CORE, SUN_EDGE), c.circle_mask(cx, cy, r))


def _cloud_mask(dx: float = 0, dy: float = 0, k: float = 1.0):
    def p(x, y):
        return 16 + (x - 16) * k + dx, 13 + (y - 13) * k + dy

    m = Canvas.mask()
    for (x, y), r in (((16, 9.5), 6.2), ((9.8, 13.0), 4.3), ((22.4, 12.4), 4.9)):
        cx, cy = p(x, y)
        Canvas.circle_mask(cx, cy, r * k, m)
    x0, y0 = p(6.0, 12.0)
    x1, y1 = p(27.2, 17.6)
    Canvas.rrect_mask((x0, y0, x1, y1), 3.0 * k, m)
    return m


def _cloud(c: Canvas, dx=0.0, dy=0.0, k=1.0, dark=False) -> None:
    m = _cloud_mask(dx, dy, k)
    top, bottom = (DARK_TOP, DARK_BOTTOM) if dark else (CLOUD_TOP, CLOUD_BOTTOM)
    c.glow(m, (120, 130, 150) if not dark else (40, 44, 60), radius=1.2, strength=0.35)
    c.paint(c.vgrad(top, bottom, 3 + dy, 18 + dy), m)


def _rain(c: Canvas, frame: int, heavy: bool, top: float = 18.5) -> None:
    xs = (8.5, 12.5, 16.5, 20.5, 24.5) if not heavy else (6.5, 9.5, 12.5, 15.5, 18.5, 21.5, 24.5, 27.5)
    for i, x in enumerate(xs):
        y = top + ((frame * 1.7 + i * 2.3) % 6.0)
        dx = -0.25 * (y - top)
        m = c.line_mask([(x + dx, y), (x + dx - 0.8, y + 2.4)], 0.75)
        c.paint(c.vgrad((150, 205, 255), RAIN, y, y + 2.4), m, 0.95)


def _snow(c: Canvas, frame: int, top: float = 18.5, color=SNOW, big: float = 0.85) -> None:
    for i, x in enumerate((8.5, 13, 17.5, 22, 26)):
        y = top + ((frame * 1.1 + i * 2.7) % 6.0)
        x += math.sin((frame + i * 2) / 2.0) * 0.8
        m = c.circle_mask(x, y, big)
        c.glow(m, (180, 210, 255), radius=0.7, strength=0.5)
        c.paint(color, m)


def _bolt(c: Canvas, frame: int) -> None:
    pts = [(17.2, 13.5), (12.4, 20.2), (15.6, 20.2), (13.3, 25.0), (21.2, 17.4), (17.8, 17.4), (20.0, 13.5)]
    m = c.poly_mask(pts)
    bright = frame % 5 in (0, 1)
    c.glow(m, (255, 210, 60), radius=2.0 if bright else 1.0, strength=0.8 if bright else 0.35)
    c.paint(c.vgrad((255, 252, 200), (255, 180, 0), 13.5, 25), m)


def _stars(c: Canvas, frame: int, stars) -> None:
    for i, (x, y, s) in enumerate(stars):
        tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(frame * 0.9 + i * 1.7))
        m = c.line_mask([(x - s, y), (x + s, y)], 0.35)
        c.line_mask([(x, y - s), (x, y + s)], 0.35, m)
        c.glow(m, (200, 210, 255), radius=0.6, strength=0.5 * tw)
        c.paint((240, 244, 255), m, tw)


# ------------------------------------------------------------- moon
def moon_phase(now: datetime | None = None) -> float:
    """0 = new moon, 0.25 = first quarter, 0.5 = full, 0.75 = last quarter.

    Mean lunar cycle: accurate to within about a day, plenty for a picture.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    reference = datetime(2000, 1, 6, 18, 14, tzinfo=UTC)  # a known new moon
    days = (now - reference).total_seconds() / 86400
    return (days % 29.530588853) / 29.530588853


def moon_name(phase: float, lang: str = "en") -> str:
    return MOON_NAMES[language_for(lang)][int((phase * 8 + 0.5)) % 8]


_MARIA = ((-0.30, -0.25, 0.28), (0.15, -0.35, 0.18), (0.10, 0.20, 0.30), (-0.35, 0.30, 0.16), (0.42, 0.05, 0.12))


def _moon(c: Canvas, phase: float, cx: float, cy: float, r: float) -> None:
    """Lit part with shading, soft terminator, faint earthshine on the dark side."""
    from .gfx import N, SS  # local: pixel loop at full resolution

    lit_fraction = (1 - math.cos(2 * math.pi * phase)) / 2
    halo = c.circle_mask(cx, cy, r)
    c.glow(halo, (255, 236, 170), radius=2.5, strength=0.12 + 0.35 * lit_fraction)

    k = math.cos(2 * math.pi * phase)
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    px = img.load()
    R = r * SS
    CX, CY = cx * SS, cy * SS
    for y in range(int(CY - R) - 1, int(CY + R) + 2):
        for x in range(int(CX - R) - 1, int(CX + R) + 2):
            dx, dy = (x + 0.5 - CX) / R, (y + 0.5 - CY) / R
            d2 = dx * dx + dy * dy
            if d2 > 1:
                continue
            w = math.sqrt(1 - dy * dy)
            lit = dx >= k * w if phase < 0.5 else dx <= -k * w
            if lit:
                limb = 0.72 + 0.28 * math.sqrt(1 - d2)
                color = mix(MOON_SHADE, MOON_LIGHT, limb)
                for mx, my, mr in _MARIA:
                    if (dx - mx) ** 2 + (dy - my) ** 2 < mr * mr:
                        color = mix(color, (180, 168, 136), 0.2)
                        break
            else:
                color = mix(MOON_NIGHT, (40, 44, 64), 1 - d2)
            px[x, y] = color + (255,)
    c.image.alpha_composite(img)


# ------------------------------------------------------------- seasons
def season_for(now: datetime | None = None) -> str:
    month = (now or datetime.now()).month
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring",
            5: "spring", 6: "summer", 7: "summer", 8: "summer"}.get(month, "autumn")


def _maple(size: float) -> list[tuple[float, float]]:
    """A five-lobed leaf outline around (0, 0)."""
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60
        r = size * (0.55 + 0.45 * abs(math.cos(2.5 * (t + math.pi / 2))) ** 0.6)
        if math.sin(t) > 0.85:  # notch at the stem
            r *= 0.75
        pts.append((math.cos(t) * r, math.sin(t) * r))
    return pts


LEAF_PALETTES = [((255, 190, 60), (225, 70, 10)), ((255, 220, 80), (235, 135, 0)),
                 ((215, 70, 25), (130, 25, 10)), ((205, 135, 50), (120, 65, 20)),
                 ((255, 120, 40), (190, 40, 10))]


def _autumn(c: Canvas, frame: int) -> None:
    # branch in the top corner
    branch = c.line_mask([(-1, 2.5), (8, 4.2), (15, 3.4)], 1.4)
    c.line_mask([(8, 4.2), (11, 7.5)], 0.8, branch)
    c.paint(c.vgrad((120, 75, 40), (70, 40, 20), 2, 8), branch)
    for (x, y, pal) in ((11.2, 8.6, 0), (15.6, 3.0, 2)):
        m = c.poly_mask(rotate(_maple(1.9), 30, x, y))
        c.paint(c.vgrad(*LEAF_PALETTES[pal], y - 2, y + 2), m)
    # pile on the ground
    ground = c.mask()
    for i in range(14):
        x = i * 2.4 + (i % 3) * 0.6
        c.ellipse_mask((x - 1.8, 29.2 - (i % 2) * 0.8, x + 1.8, 33), ground)
    c.paint(c.vgrad((255, 160, 40), (150, 45, 10), 28, 32), ground)
    # falling leaves: drift down, sway and spin
    for i in range(5):
        y = (i * 7.1 + frame * 1.3) % 34 - 2
        x = 3 + (i * 9.7) % 26 + math.sin((frame + i * 2.1) / 1.7) * 1.8
        m = c.poly_mask(rotate(_maple(2.4 + (i % 3) * 0.4), frame * 23 + i * 60, x, y))
        top, bottom = LEAF_PALETTES[i % len(LEAF_PALETTES)]
        c.paint(c.vgrad(top, bottom, y - 2.5, y + 2.5), m)


def _snowflake(c: Canvas, x: float, y: float, r: float, angle: float, alpha: float = 1.0) -> None:
    m = c.mask()
    for k in range(6):
        a = math.radians(angle + k * 60)
        ex, ey = x + math.cos(a) * r, y + math.sin(a) * r
        c.line_mask([(x, y), (ex, ey)], 0.32, m)
        for f in (0.55,):  # little side branches
            bx, by = x + math.cos(a) * r * f, y + math.sin(a) * r * f
            for side in (-1, 1):
                b = a + side * math.radians(45)
                c.line_mask([(bx, by), (bx + math.cos(b) * r * 0.35, by + math.sin(b) * r * 0.35)], 0.28, m)
    c.glow(m, (170, 200, 255), radius=0.8, strength=0.5 * alpha)
    c.paint(SNOW, m, alpha)


def _pine(c: Canvas, x: float, base: float, h: float) -> None:
    m = c.mask()
    for i in range(3):
        top = base - h + i * h * 0.28
        half = h * (0.22 + i * 0.1)
        c.poly_mask([(x, top), (x - half, top + h * 0.42), (x + half, top + h * 0.42)], m)
    c.paint(c.vgrad((40, 120, 70), (10, 60, 35), base - h, base), m)
    snow = c.mask()
    for i in range(3):
        top = base - h + i * h * 0.28
        half = h * (0.22 + i * 0.1)
        c.poly_mask([(x, top), (x - half * 0.45, top + h * 0.17), (x + half * 0.45, top + h * 0.17)], snow)
    c.paint((235, 242, 255), snow, 0.9)


def _winter(c: Canvas, frame: int) -> None:
    _pine(c, 7, 29, 11)
    _pine(c, 25.5, 29.5, 8)
    ground = c.ellipse_mask((-8, 27, 20, 38))
    c.ellipse_mask((10, 28, 42, 38), ground)
    c.paint(c.vgrad((255, 255, 255), (170, 195, 230), 27, 32), ground)
    for i in range(7):
        y = (i * 5.1 + frame * 0.9) % 32 - 2
        x = 2 + (i * 11.3) % 28 + math.sin((frame + i * 1.3) / 2.2) * 1.2
        if i % 2 == 0:
            _snowflake(c, x, y, 2.5, frame * 12 + i * 20)
        else:
            m = c.circle_mask(x, y, 0.85)
            c.glow(m, (180, 210, 255), radius=0.7, strength=0.55)
            c.paint(SNOW, m)


def _spring(c: Canvas, frame: int) -> None:
    grass = c.mask()
    for i in range(16):
        x = i * 2.1 + 0.5
        sway = math.sin((frame + i) / 2.0) * 0.6
        c.poly_mask([(x - 0.7, 32), (x + 0.7, 32), (x + sway + 0.2, 26.5 - (i % 3) * 1.2)], grass)
    c.paint(c.vgrad((120, 220, 90), (20, 110, 40), 25, 32), grass)
    for x, top, petal in ((7, 15, ((255, 160, 210), (230, 60, 140))),
                          (16, 9, ((255, 245, 140), (240, 170, 0))),
                          (25, 17, ((205, 160, 255), (130, 70, 230)))):
        sway = math.sin((frame + x) / 2.5) * 0.7
        stem = c.line_mask([(x, 31), (x + sway * 0.5, (31 + top) / 2), (x + sway, top)], 0.7)
        c.paint((50, 160, 60), stem)
        fx, fy = x + sway, top
        m = c.mask()
        for k in range(5):
            a = math.radians(k * 72 + frame * 4)
            px, py = fx + math.cos(a) * 2.0, fy + math.sin(a) * 2.0
            c.circle_mask(px, py, 1.55, m)
        c.paint(c.rgrad(fx, fy, 3.6, *petal), m)
        core = c.circle_mask(fx, fy, 1.05)
        c.paint(c.rgrad(fx - 0.3, fy - 0.3, 1.2, (255, 240, 150), (230, 140, 0)), core)


def _summer(c: Canvas, frame: int) -> None:
    _sun(c, 16, 11, 5.0, frame)
    sea = c.mask()
    c.rrect_mask((-1, 23, 33, 33), 0, sea)
    c.paint(c.vgrad((40, 160, 255), (0, 50, 140), 23, 32), sea)
    # sun reflection and moving wave highlights
    for i in range(5):
        y = 24 + i * 1.6
        w = 3.0 - i * 0.4
        m = c.line_mask([(16 - w, y), (16 + w, y)], 0.45)
        c.paint((255, 220, 120), m, 0.75 - i * 0.12)
    for i in range(7):
        x = (i * 5.3 + frame * 0.8) % 36 - 2
        y = 25 + (i % 3) * 2.2
        m = c.line_mask([(x, y), (x + 1.8, y)], 0.4)
        c.paint((190, 230, 255), m, 0.8)
    # a small sailboat
    bx = 24 + math.sin(frame / 3) * 0.4
    sail = c.poly_mask([(bx, 17.5), (bx, 23), (bx + 3.2, 23)])
    c.poly_mask([(bx - 0.4, 18.5), (bx - 0.4, 23), (bx - 2.6, 23)], sail)
    c.paint((250, 250, 250), sail)
    hull = c.poly_mask([(bx - 3, 23.3), (bx + 3.6, 23.3), (bx + 2.6, 24.6), (bx - 2.2, 24.6)])
    c.paint((150, 70, 40), hull)


# ------------------------------------------------------------- alerts
_SKYLINE = ((0, 5.5, 15.5), (6, 11.5, 11.5), (12, 15.5, 17.5), (16, 22.5, 13.5), (23, 26.5, 9.5), (27, 32, 15))


def _smog(c: Canvas, frame: int) -> None:
    city = c.mask()
    for x0, x1, top in _SKYLINE:
        c.rrect_mask((x0, top, x1, 26), 0.4, city)
    c.paint(c.vgrad((110, 112, 132), (50, 50, 64), 9, 25), city)
    windows = c.mask()
    for x0, x1, top in _SKYLINE:
        for wy in range(int(top) + 2, 24, 3):
            for wx in range(int(x0) + 1, int(x1), 2):
                if (wx * 7 + wy * 3) % 4 == 0:
                    c.rrect_mask((wx, wy, wx + 0.9, wy + 1.1), 0.2, windows)
    c.paint((255, 190, 90), windows, 0.7)
    # drifting haze clouds
    for i in range(7):
        x = (i * 7.3 + frame * 0.9) % 44 - 6
        y = 3 + (i * 5) % 18
        m = c.ellipse_mask((x - 5, y - 2.2, x + 5, y + 2.2))
        c.glow(m, (175, 140, 95), radius=1.6, strength=0.65)
    haze = c.mask()
    c.rrect_mask((-1, -1, 33, 26), 0, haze)
    c.paint(c.vgrad((120, 90, 55), (60, 45, 30), 0, 25), haze, 0.28)


def _heating(c: Canvas, frame: int) -> None:
    for i, x in enumerate(range(6, 27, 4)):
        fin = c.rrect_mask((x, 13, x + 2.6, 24), 1.0)
        c.paint(c.vgrad((240, 242, 250), (140, 144, 160), 13, 24), fin)
    pipes = c.line_mask([(4, 15.2), (28.6, 15.2)], 0.8)
    c.line_mask([(4, 21.8), (28.6, 21.8)], 0.8, pipes)
    c.line_mask([(7.2, 24), (7.2, 25)], 0.8, pipes)
    c.line_mask([(25.2, 24), (25.2, 25)], 0.8, pipes)
    c.paint((160, 164, 180), pipes)
    for i, x0 in enumerate((9.5, 16.0, 22.5)):
        phase = frame * 0.9 + i * 1.3
        wave = curve(lambda t: (x0 + math.sin(t * 1.6 + phase) * 1.2, 11.5 - t * 1.7), 0, 6, 30)
        m = c.line_mask(wave, 0.8)
        c.glow(m, (255, 110, 0), radius=1.2, strength=0.5)
        c.paint(c.vgrad((255, 240, 120), (255, 80, 0), 1.0, 11.5), m)


# ------------------------------------------------------------- main
def _weather(c: Canvas, name: str, frame: int) -> None:
    if name == "sunny":
        _sun(c, 16, 12.5, 5.5, frame)
    elif name == "clear-night":
        crescent = c.circle_mask(14, 12, 8)
        cut = c.circle_mask(18.5, 8.5, 7.6)
        crescent.paste(0, mask=cut)
        c.glow(crescent, (255, 230, 160), radius=2.0, strength=0.35)
        c.paint(c.rgrad(10, 14, 9, MOON_LIGHT, MOON_SHADE), crescent)
        _stars(c, frame, ((25.5, 6, 1.1), (28, 17, 0.8), (4, 3.5, 0.8), (22, 22, 0.9), (27, 1.5, 0.6)))
    elif name == "partlycloudy":
        _sun(c, 11, 9, 4.6, frame)
        _cloud(c, 2.5, 4.5, 0.85)
    elif name == "cloudy":
        drift = math.sin(frame / 3) * 0.8
        _cloud(c, -3.5 + drift, -2.5, 0.8, dark=True)
        _cloud(c, 2.5 - drift, 4.0, 0.9)
    elif name in ("rainy", "pouring"):
        _cloud(c, 0, -1.5, 1.0, dark=name == "pouring")
        _rain(c, frame, name == "pouring", 17.5)
    elif name == "snowy":
        _cloud(c, 0, -1.5)
        _snow(c, frame, 17.5)
    elif name == "snowy-rainy":
        _cloud(c, 0, -1.5, dark=True)
        _rain(c, frame, False, 17.5)
        _snow(c, frame + 3, 17.5)
    elif name == "hail":
        _cloud(c, 0, -1.5, dark=True)
        _snow(c, frame, 17.5, (210, 235, 255), 1.0)
    elif name in ("lightning", "lightning-rainy"):
        _cloud(c, 0, -2.5, dark=True)
        if name == "lightning-rainy":
            _rain(c, frame, False, 16.5)
        _bolt(c, frame)
    elif name == "fog":
        for i, y in enumerate((5, 9, 13, 17, 21)):
            shift = math.sin(frame / 2.5 + i * 1.4) * 2.0
            x0, x1 = 4 + 3 * (i % 2) + shift, 28 - 3 * ((i + 1) % 2) + shift
            m = c.line_mask([(x0, y), (x1, y)], 1.6)
            c.paint(c.vgrad((225, 228, 236), (150, 156, 170), y - 1, y + 1), m, 0.85)
    elif name in ("windy", "windy-variant"):
        if name == "windy-variant":
            _cloud(c, 0, -4, 0.85, dark=True)
        for i, (y, end) in enumerate(((13.0, 21.0), (17.5, 25.5), (22.0, 16.5))):
            s = math.sin(frame / 2 + i) * 1.0
            path = [(3 + s, y), (end + s, y)] + curve(
                lambda t, e=end + s, yy=y: (e + math.sin(t) * 2.2, yy - 2.2 + math.cos(t) * 2.2), 3.14, 6.0, 12
            )
            m = c.line_mask(path, 0.9)
            c.paint((185, 225, 255), m)
    else:  # exceptional / unknown
        tri = c.poly_mask([(16, 2), (29.5, 23.5), (2.5, 23.5)])
        c.glow(tri, (255, 40, 30), radius=1.5, strength=0.4)
        c.paint(c.vgrad((255, 90, 70), (190, 10, 10), 2, 24), tri)
        mark = c.rrect_mask((14.8, 8, 17.2, 17), 1.0)
        c.circle_mask(16, 20, 1.3, mark)
        c.paint((255, 255, 255), mark)


def render_icon(
    name: str,
    caption: str | None = None,
    caption_color=None,
    frame: int = 0,
    now: datetime | None = None,
    lang: str = "en",
) -> Image.Image:
    """Draw one picture. 'season' and 'moon' work out today's season / phase.

    caption None = automatic (moon phase name, "CHARGING" for heating) in
    the given language (en / pl); "" = no caption.
    """
    name = (name or "").lower().strip()
    if name == "season":
        name = season_for(now)
    if name not in ICONS:
        name = "exceptional"

    c = Canvas()
    if name in SEASONS:
        {"autumn": _autumn, "winter": _winter, "spring": _spring, "summer": _summer}[name](c, frame)
        image = c.finish()
        if caption:
            for y in range(PANEL_HEIGHT - GLYPH_HEIGHT - 2, PANEL_HEIGHT):
                for x in range(PANEL_WIDTH):
                    image.putpixel((x, y), (0, 0, 0))
            _caption(image, caption, tuple(caption_color or (255, 255, 255)))
        return image

    if name == "moon":
        phase = moon_phase(now)
        _moon(c, phase, 16, 12.5, 11)
        if caption is None:
            caption = moon_name(phase, lang)
    elif name == "smog":
        _smog(c, frame)
    elif name == "heating":
        _heating(c, frame)
        if caption is None:
            caption = CHARGING[language_for(lang)]
    else:
        _weather(c, name, frame)

    if caption:
        image = c.finish()
        for y in range(ART_H, PANEL_HEIGHT):  # clean strip for the caption
            for x in range(PANEL_WIDTH):
                image.putpixel((x, y), (0, 0, 0))
        _caption(image, caption, tuple(caption_color or (255, 255, 255)))
        return image
    return c.finish(y_offset=(PANEL_HEIGHT - ART_H) // 2 + 1)
