"""Country of registration for an aircraft, and small flags to draw.

The country comes from the aircraft's ICAO 24-bit address: every state
of registry has its own block of addresses. The registration prefix
(SP-, D-, EI- ...) is used when the address is not in the table.
Flags are simplified for a few LED pixels: stripes, crosses, discs.
No Home Assistant imports.
"""

from __future__ import annotations

import math

from .gfx import Canvas

# (first, last, ISO code) - ICAO 24-bit address blocks
ICAO_BLOCKS: list[tuple[int, int, str]] = [
    (0x008000, 0x00FFFF, "ZA"), (0x010000, 0x017FFF, "EG"), (0x020000, 0x027FFF, "MA"),
    (0x06A000, 0x06A3FF, "QA"), (0x0D0000, 0x0D7FFF, "MX"), (0x100000, 0x1FFFFF, "RU"),
    (0x300000, 0x33FFFF, "IT"), (0x340000, 0x37FFFF, "ES"), (0x380000, 0x3BFFFF, "FR"),
    (0x3C0000, 0x3FFFFF, "DE"), (0x400000, 0x43FFFF, "GB"), (0x440000, 0x447FFF, "AT"),
    (0x448000, 0x44FFFF, "BE"), (0x450000, 0x457FFF, "BG"), (0x458000, 0x45FFFF, "DK"),
    (0x460000, 0x467FFF, "FI"), (0x468000, 0x46FFFF, "GR"), (0x470000, 0x477FFF, "HU"),
    (0x478000, 0x47FFFF, "NO"), (0x480000, 0x487FFF, "NL"), (0x488000, 0x48FFFF, "PL"),
    (0x490000, 0x497FFF, "PT"), (0x498000, 0x49FFFF, "CZ"), (0x4A0000, 0x4A7FFF, "RO"),
    (0x4A8000, 0x4AFFFF, "SE"), (0x4B0000, 0x4B7FFF, "CH"), (0x4B8000, 0x4BFFFF, "TR"),
    (0x4C0000, 0x4C7FFF, "RS"), (0x4C8000, 0x4C83FF, "CY"), (0x4CA000, 0x4CAFFF, "IE"),
    (0x4CC000, 0x4CCFFF, "IS"), (0x4D0000, 0x4D03FF, "LU"), (0x4D2000, 0x4D23FF, "MT"),
    (0x501C00, 0x501FFF, "HR"), (0x502C00, 0x502FFF, "LV"), (0x503C00, 0x503FFF, "LT"),
    (0x504C00, 0x504FFF, "MD"), (0x505C00, 0x505FFF, "SK"), (0x506C00, 0x506FFF, "SI"),
    (0x508000, 0x50FFFF, "UA"), (0x510000, 0x5103FF, "BY"), (0x511000, 0x5113FF, "EE"),
    (0x514000, 0x5143FF, "GE"), (0x683000, 0x6833FF, "KZ"), (0x710000, 0x717FFF, "SA"),
    (0x718000, 0x71FFFF, "KR"), (0x738000, 0x73FFFF, "IL"), (0x780000, 0x7BFFFF, "CN"),
    (0x7C0000, 0x7FFFFF, "AU"), (0x800000, 0x83FFFF, "IN"), (0x840000, 0x87FFFF, "JP"),
    (0x896000, 0x896FFF, "AE"), (0xA00000, 0xAFFFFF, "US"), (0xC00000, 0xC3FFFF, "CA"),
    (0xC80000, 0xC87FFF, "NZ"), (0xE40000, 0xE7FFFF, "BR"),
]

# registration prefixes, longest first when matching
REG_PREFIXES = {
    "SP": "PL", "D": "DE", "EI": "IE", "G": "GB", "9H": "MT", "OE": "AT", "HB": "CH",
    "OK": "CZ", "OM": "SK", "HA": "HU", "YR": "RO", "LZ": "BG", "TC": "TR", "PH": "NL",
    "OO": "BE", "F": "FR", "I": "IT", "EC": "ES", "CS": "PT", "SE": "SE", "LN": "NO",
    "OY": "DK", "OH": "FI", "ES": "EE", "YL": "LV", "LY": "LT", "UR": "UA", "4X": "IL",
    "A6": "AE", "A7": "QA", "HZ": "SA", "N": "US", "C": "CA", "B": "CN", "JA": "JP",
    "HL": "KR", "VH": "AU", "VT": "IN", "SU": "EG", "SX": "GR", "5B": "CY", "LX": "LU",
    "9A": "HR", "S5": "SI", "YU": "RS", "ER": "MD", "EW": "BY", "RA": "RU", "4L": "GE",
    "TF": "IS", "UP": "KZ", "ZK": "NZ", "ZS": "ZA", "PR": "BR", "PP": "BR", "XA": "MX",
}


def country_for(hex_code: str | None, registration: str | None = None) -> str | None:
    """ISO country code of the state of registry, or None."""
    try:
        address = int((hex_code or "").strip().lstrip("~"), 16)
    except ValueError:
        address = -1
    for first, last, code in ICAO_BLOCKS:
        if first <= address <= last:
            return code
    reg = (registration or "").upper().strip()
    if reg:
        head = reg.split("-")[0] if "-" in reg else reg[:2]
        for size in (2, 1):
            if head[:size] in REG_PREFIXES:
                return REG_PREFIXES[head[:size]]
    return None


# ----------------------------------------------------------------- flags
W, R, B = (240, 240, 240), (215, 25, 40), (0, 56, 168)
Y, G, K, O = (255, 200, 0), (0, 140, 70), (60, 60, 64), (255, 130, 0)
LB = (0, 150, 220)

STRIPES_H = {
    "PL": [W, R], "DE": [K, R, Y], "NL": [(190, 25, 45), W, (30, 70, 150)],
    "LU": [R, W, LB], "AT": [R, W, R], "HU": [R, W, G], "BG": [W, G, R],
    "LT": [Y, G, (190, 40, 40)], "EE": [(0, 114, 206), K, W],
    "LV": [(158, 48, 57), (158, 48, 57), W, (158, 48, 57), (158, 48, 57)],
    "UA": [(0, 87, 183), (255, 215, 0)], "RU": [W, (0, 57, 166), (213, 43, 30)],
    "ES": [R, Y, Y, R], "HR": [R, W, B], "SI": [W, B, R], "SK": [W, B, R],
    "RS": [R, B, W], "BY": [R, R, G], "EG": [R, W, K], "IN": [O, W, G],
    "MD": [B, Y, R], "KZ": [LB, LB],
}
STRIPES_V = {
    "FR": [(0, 50, 160), W, R], "IT": [G, W, R], "IE": [(0, 155, 72), W, O],
    "BE": [K, Y, R], "RO": [B, Y, R], "PT": [(0, 102, 0), (0, 102, 0), R, R, R],
    "MT": [W, R], "CA": [R, W, W, R], "MX": [G, W, R],
}
NORDIC = {  # background, cross, inner cross
    "SE": ((0, 106, 167), (254, 204, 0), None), "NO": (R, W, B),
    "DK": (R, W, None), "FI": (W, (0, 47, 108), None), "IS": (B, W, R),
}


def _rect(c: Canvas, x0, y0, x1, y1, color):
    c.paint(color, c.rrect_mask((x0, y0, x1, y1), 0))


def _union_jack(c: Canvas, x, y, w, h):
    _rect(c, x, y, x + w, y + h, (1, 33, 105))
    for (ax, ay, bx, by) in ((x, y, x + w, y + h), (x, y + h, x + w, y)):
        c.paint(W, c.line_mask([(ax, ay), (bx, by)], h * 0.2))
        c.paint(R, c.line_mask([(ax, ay), (bx, by)], h * 0.08))
    _rect(c, x + w * 0.4, y, x + w * 0.6, y + h, W)
    _rect(c, x, y + h * 0.35, x + w, y + h * 0.65, W)
    _rect(c, x + w * 0.44, y, x + w * 0.56, y + h, R)
    _rect(c, x, y + h * 0.41, x + w, y + h * 0.59, R)


def draw_flag(c: Canvas, code: str | None, x: float, y: float, w: float, h: float) -> bool:
    """Draw the flag into the box; False if there is no flag for the code."""
    if not code:
        return False
    if code in STRIPES_H:
        colors = STRIPES_H[code]
        for i, color in enumerate(colors):
            _rect(c, x, y + h * i / len(colors), x + w, y + h * (i + 1) / len(colors), color)
        if code == "IN":
            c.paint((0, 0, 140), c.circle_mask(x + w / 2, y + h / 2, h * 0.13))
        if code == "KZ":
            c.paint((255, 220, 0), c.circle_mask(x + w / 2, y + h * 0.45, h * 0.18))
        return True
    if code in STRIPES_V:
        colors = STRIPES_V[code]
        for i, color in enumerate(colors):
            _rect(c, x + w * i / len(colors), y, x + w * (i + 1) / len(colors), y + h, color)
        if code == "MX":
            c.paint((140, 90, 40), c.circle_mask(x + w / 2, y + h / 2, h * 0.14))
        if code == "CA":
            c.paint(R, c.poly_mask([(x + w / 2, y + h * 0.18), (x + w * 0.62, y + h * 0.55),
                                    (x + w / 2, y + h * 0.82), (x + w * 0.38, y + h * 0.55)]))
        return True
    if code in NORDIC:
        bg, cross, inner = NORDIC[code]
        _rect(c, x, y, x + w, y + h, bg)
        cx = x + w * 0.36
        _rect(c, cx - h * 0.13, y, cx + h * 0.13, y + h, cross)
        _rect(c, x, y + h * 0.37, x + w, y + h * 0.63, cross)
        if inner:
            _rect(c, cx - h * 0.06, y, cx + h * 0.06, y + h, inner)
            _rect(c, x, y + h * 0.44, x + w, y + h * 0.56, inner)
        return True
    if code == "GB":
        _union_jack(c, x, y, w, h)
    elif code in ("AU", "NZ"):
        _rect(c, x, y, x + w, y + h, (1, 33, 105))
        _union_jack(c, x, y, w * 0.5, h * 0.5)
        for sx, sy in ((0.75, 0.3), (0.62, 0.7), (0.88, 0.62), (0.25, 0.78)):
            c.paint(W if code == "AU" else R, c.circle_mask(x + w * sx, y + h * sy, h * 0.07))
    elif code == "US":
        for i in range(7):
            _rect(c, x, y + h * i / 7, x + w, y + h * (i + 1) / 7, R if i % 2 == 0 else W)
        _rect(c, x, y, x + w * 0.45, y + h * 4 / 7, (40, 50, 120))
    elif code == "CH":
        _rect(c, x, y, x + w, y + h, R)
        cx, cy, s = x + w / 2, y + h / 2, h * 0.32
        _rect(c, cx - s * 0.33, cy - s, cx + s * 0.33, cy + s, W)
        _rect(c, cx - s, cy - s * 0.33, cx + s, cy + s * 0.33, W)
    elif code == "CZ":
        _rect(c, x, y, x + w, y + h / 2, W)
        _rect(c, x, y + h / 2, x + w, y + h, R)
        c.paint((17, 69, 126), c.poly_mask([(x, y), (x + w * 0.5, y + h / 2), (x, y + h)]))
    elif code == "TR":
        _rect(c, x, y, x + w, y + h, (227, 10, 23))
        moon = c.circle_mask(x + w * 0.38, y + h / 2, h * 0.3)
        moon.paste(0, mask=c.circle_mask(x + w * 0.44, y + h / 2, h * 0.24))
        c.paint(W, moon)
        c.paint(W, c.circle_mask(x + w * 0.62, y + h / 2, h * 0.1))
    elif code == "JP":
        _rect(c, x, y, x + w, y + h, W)
        c.paint((188, 0, 45), c.circle_mask(x + w / 2, y + h / 2, h * 0.3))
    elif code == "KR":
        _rect(c, x, y, x + w, y + h, W)
        c.paint((205, 46, 58), c.circle_mask(x + w / 2, y + h / 2 - h * 0.08, h * 0.24))
        c.paint((0, 71, 160), c.circle_mask(x + w / 2, y + h / 2 + h * 0.1, h * 0.2))
    elif code == "CN":
        _rect(c, x, y, x + w, y + h, (222, 41, 16))
        star = [(x + w * 0.2 + math.cos(math.radians(-90 + i * 36)) * h * (0.22 if i % 2 == 0 else 0.09),
                 y + h * 0.32 + math.sin(math.radians(-90 + i * 36)) * h * (0.22 if i % 2 == 0 else 0.09))
                for i in range(10)]
        c.paint((255, 222, 0), c.poly_mask(star))
    elif code == "IL":
        _rect(c, x, y, x + w, y + h, W)
        _rect(c, x, y + h * 0.12, x + w, y + h * 0.25, (0, 56, 184))
        _rect(c, x, y + h * 0.75, x + w, y + h * 0.88, (0, 56, 184))
        c.paint((0, 56, 184), c.circle_mask(x + w / 2, y + h / 2, h * 0.14))
    elif code == "AE":
        for i, color in enumerate(((0, 115, 47), W, K)):
            _rect(c, x, y + h * i / 3, x + w, y + h * (i + 1) / 3, color)
        _rect(c, x, y, x + w * 0.27, y + h, R)
    elif code == "QA":
        _rect(c, x, y, x + w, y + h, (138, 21, 56))
        _rect(c, x, y, x + w * 0.32, y + h, W)
    elif code == "SA":
        _rect(c, x, y, x + w, y + h, (0, 108, 53))
        _rect(c, x + w * 0.25, y + h * 0.62, x + w * 0.75, y + h * 0.7, W)
    elif code == "GR":
        for i in range(5):
            _rect(c, x, y + h * i / 5, x + w, y + h * (i + 1) / 5, (0, 80, 180) if i % 2 == 0 else W)
        _rect(c, x, y, x + w * 0.4, y + h * 0.6, (0, 80, 180))
        _rect(c, x + w * 0.16, y, x + w * 0.24, y + h * 0.6, W)
        _rect(c, x, y + h * 0.25, x + w * 0.4, y + h * 0.35, W)
    elif code == "GE":
        _rect(c, x, y, x + w, y + h, W)
        _rect(c, x + w * 0.44, y, x + w * 0.56, y + h, R)
        _rect(c, x, y + h * 0.4, x + w, y + h * 0.6, R)
    elif code == "CY":
        _rect(c, x, y, x + w, y + h, W)
        c.paint((210, 120, 30), c.ellipse_mask((x + w * 0.3, y + h * 0.25, x + w * 0.7, y + h * 0.55)))
    elif code == "BR":
        _rect(c, x, y, x + w, y + h, (0, 156, 59))
        c.paint((255, 223, 0), c.poly_mask([(x + w / 2, y + h * 0.1), (x + w * 0.92, y + h / 2),
                                            (x + w / 2, y + h * 0.9), (x + w * 0.08, y + h / 2)]))
        c.paint((0, 39, 118), c.circle_mask(x + w / 2, y + h / 2, h * 0.22))
    elif code == "ZA":
        _rect(c, x, y, x + w, y + h / 2, (224, 60, 49))
        _rect(c, x, y + h / 2, x + w, y + h, (0, 35, 149))
        _rect(c, x, y + h * 0.38, x + w, y + h * 0.62, (0, 119, 73))
        c.paint(Y, c.poly_mask([(x, y + h * 0.2), (x + w * 0.35, y + h / 2), (x, y + h * 0.8)]))
    elif code == "MA":
        _rect(c, x, y, x + w, y + h, (193, 39, 45))
        c.paint((0, 98, 51), c.circle_mask(x + w / 2, y + h / 2, h * 0.16))
    else:
        return False
    return True
