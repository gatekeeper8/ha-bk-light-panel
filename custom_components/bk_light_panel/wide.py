"""Layouts for the wide 64x16 panel (Action ACT1025 / ACT1033).

The 32x32 drawings are reused where they fit: the flip-clock cards are
exactly 16 pixels high, pictures are drawn at 32x32 and scaled to 16x16.
Text goes in the space to the right. No Home Assistant imports.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from PIL import Image

from . import font7
from .aircraft import PLANE, _altitude_text
from .aurora import kp_color
from .flags import draw_flag
from .gfx import Canvas, curve, rotate
from .icons import CHARGING, SEASON_NAMES, SEASONS, language_for, season_for, moon_name, moon_phase, render_icon
from .render import (
    _BIG,
    BAR_COLORS,
    CHAR_GAP,
    _color,
    _glyph,
    _scaled,
    render_clock,
    render_flip_clock,
    text_width,
)

WIDTH, HEIGHT = 64, 16
# smaller, rounder flip cards for the 16 pixel high panel
# 15 wide: pin, 1 free, 11 digits, 1 free, pin - the same on both sides
FLIP_CARDS = {"cards": ((0, 15), (16, 31)), "top": 2, "bottom": 14, "hinge": 8,
              "digit_top": 4, "radius": 2.6, "centred": True}
# a shorter clock band at the top, with a date line under it
DATE_CARDS = {"cards": ((0, 15), (16, 31)), "top": 0, "bottom": 9, "hinge": 4,
              "digit_top": 1, "radius": 2.0, "centred": True,
              "split_shade": 0.85}  # 7-pixel digits: keep the split faint
_FOLD = str.maketrans("ĄĆĘŁŃÓŚŹŻąćęłńóśźż", "ACELNOSZZACELNOSZZ")
SIZE = (WIDTH, HEIGHT)
RGB = tuple[int, int, int]


def is_wide(size: tuple[int, int] | None) -> bool:
    return size == SIZE


def slide_frames(old: Image.Image, new: Image.Image, steps: int = 3) -> list[Image.Image]:
    """In-between pictures: the new screen pushes the old one out to the left."""
    width, height = new.size
    frames = []
    for i in range(1, steps + 1):
        shift = round(width * i / (steps + 1))
        frame = Image.new("RGB", new.size, (0, 0, 0))
        frame.paste(old.crop((shift, 0, width, height)), (0, 0))
        frame.paste(new.crop((0, 0, shift, height)), (width - shift, 0))
        frames.append(frame)
    return frames


def _blank() -> Image.Image:
    return Image.new("RGB", SIZE, (0, 0, 0))


def _text(pixels, text: str, x0: int, x1: int, y: int, color: RGB) -> None:
    """Small 3x5 text centred between x0 and x1 (clipped to the panel)."""
    text = text.translate(_FOLD)
    x = x0 + (x1 - x0 - text_width(text)) // 2
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and x0 <= x + rx < x1 and 0 <= y + ry < HEIGHT:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP


def _big(pixels, text: str, x0: int, x1: int, y: int, color: RGB) -> None:
    """Rounded 7-pixel text centred between x0 and x1; the small font if it does not fit."""
    if font7.fits(text) and font7.width(text) <= x1 - x0:
        font7.draw(pixels, text, x0 + (x1 - x0 - font7.width(text)) // 2, y, color, (x0, x1))
    else:
        _text(pixels, text, x0, x1, y + 1, color)


# the clock's 5x7 digits plus what a temperature needs
_CLOCK_GLYPHS = {**_BIG,
                 ".": (".", ".", ".", ".", ".", ".", "#"),
                 "°": (".#.", "#.#", ".#.", "...", "...", "...", "...")}


def _clock_digits(pixels, text: str, x0: int, x1: int, y: int, color: RGB) -> bool:
    """Text in the clock's own digits, centred; False if a character is missing."""
    if not all(ch in _CLOCK_GLYPHS for ch in text):
        return False
    width = sum(len(_CLOCK_GLYPHS[ch][0]) for ch in text) + len(text) - 1
    if width > x1 - x0:
        return False
    x = x0 + (x1 - x0 - width) // 2
    for ch in text:
        rows = _CLOCK_GLYPHS[ch]
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#":
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + 1
    return True


def _two_lines(pixels, lines: list[tuple[str, RGB]], x0: int, x1: int) -> None:
    """One line centred vertically, or two lines at y 0 and 9 (big rounded font)."""
    lines = [(t, c) for t, c in lines if t][:2]
    if len(lines) == 1:
        _big(pixels, lines[0][0], x0, x1, 4, lines[0][1])
    else:
        for (text, color), y in zip(lines, (0, 9)):
            _big(pixels, text, x0, x1, y, color)


def _bar(pixels, value: float | None, maximum: float, x0: int, x1: int, y: int) -> None:
    if value is None:
        return
    level = max(0.0, min(1.0, value / maximum if maximum else 0))
    n = x1 - x0
    for i in range(n):
        seg = BAR_COLORS[min(3, int(i / max(1, n - 1) * 4))]
        on = (i + 0.5) / n <= level or (i == 0 and level > 0)
        pixels[x0 + i, y] = seg if on else _scaled(seg, 0.12)


# ------------------------------------------------------------------ clock
def render_clock_wide(
    time_text: str,
    previous: str | None = None,
    step: int = 2,
    style: str = "flip",
    time_color: list[int] | None = None,
    line1: str = "",
    line1_color: list[int] | None = None,
    line2: str = "",
    line2_color: list[int] | None = None,
    bar_value: float | None = None,
    bar_max: float = 75.0,
    date_text: str = "",
    date_color: list[int] | None = None,
) -> Image.Image:
    """Clock on the left half, the two lines and the level bar on the right.

    date_text: the clock moves up into a shorter band, the date goes under it.
    """
    image = _blank()
    if date_text:
        if style == "flip":
            face = render_flip_clock(time_text, previous, step, time_color, geometry=DATE_CARDS)
            image.paste(face.crop((0, 0, 32, 10)), (0, 0))
        else:
            face = render_clock(time_text, time_color)
            image.paste(face.crop((0, 1, 32, 10)), (0, 0))  # digits at y 1..7
        pixels = image.load()
        _text(pixels, date_text, 0, 32, 11, _color(date_color, (255, 190, 110)))
        # right side in the same sizes and rows: line 1 in the clock's digits
        # (y 1-7, level with the time), line 2 in the date's small font (y 11)
        color1 = _color(line1_color, (255, 190, 110))
        if line1 and not _clock_digits(pixels, line1, 32, 64, 1, color1):
            _big(pixels, line1, 32, 64, 1, color1)
        if line2:
            _text(pixels, line2, 32, 64, 11, _color(line2_color, (200, 200, 200)))
        return image
    elif style == "flip":
        face = render_flip_clock(time_text, previous, step, time_color, geometry=FLIP_CARDS)
        image.paste(face.crop((0, 0, 32, 16)), (0, 0))
    else:
        face = render_clock(time_text, time_color)
        image.paste(face.crop((0, 0, 32, 11)), (0, 2))  # digits sit at y 4..10
    pixels = image.load()
    lines = [(line1, _color(line1_color, (255, 190, 110))),
             (line2, _color(line2_color, (200, 200, 200)))]
    if bar_value is None:
        _two_lines(pixels, lines, 32, 64)
    else:
        for (text, color), y in zip(lines, (1, 7)):
            if text:
                _text(pixels, text, 32, 64, y, color)
        _bar(pixels, bar_value, bar_max, 35, 61, 14)
    return image


# --------------------------------------------------------------- pictures
def auto_caption(name: str, lang: str, now: datetime | None = None) -> str | None:
    """The caption a 32x32 picture would get on its own."""
    if name == "moon":
        return moon_name(moon_phase(now), lang)
    if name == "heating":
        return CHARGING[language_for(lang)]
    if name in SEASONS:  # room for the name beside the picture
        return SEASON_NAMES[language_for(lang)][name]
    return None


def _picture(name: str, frame: int, night: bool, now: datetime | None = None) -> Image.Image:
    """The 32x32 picture without caption, scaled to 16x16."""
    art = render_icon(name, "", None, frame, now=now, night=night)
    return art.resize((16, 16), Image.Resampling.BOX)


def render_icon_wide(
    name: str,
    caption: str | None = None,
    caption_color: list[int] | None = None,
    frame: int = 0,
    lang: str = "en",
    night: bool = False,
    now: datetime | None = None,
) -> Image.Image:
    """Picture on the left (16x16), caption in up to two lines beside it."""
    name = (name or "").lower().strip()
    if name == "season":
        name = season_for(now)
    image = _blank()
    if caption is None:
        caption = auto_caption(name, lang, now)
    if caption:
        image.paste(_picture(name, frame, night, now), (0, 0))
        pixels = image.load()
        color = _color(caption_color, (255, 255, 255))
        lines = font7.wrap(caption, 46)[:2]
        _two_lines(pixels, [(line, color) for line in lines], 17, 64)
    else:
        image.paste(_picture(name, frame, night, now), (24, 0))
    return image


# ---------------------------------------------------------------- aircraft
def render_aircraft_wide(info: dict[str, Any], frame: int = 0) -> Image.Image:
    """Flight-board line: plane on its track, flag, callsign / type, altitude / distance."""
    plane = Canvas()
    track = info.get("track") or 0.0
    a = math.radians(track)
    cx, cy, size = 8.0, 8.0, 5.6
    for i in range(1, 4):  # short contrail, drifting
        back = size * 0.6 + i * 1.5 - (frame % 4) * 0.4
        m = plane.circle_mask(cx - math.sin(a) * back, cy + math.cos(a) * back, 0.6)
        plane.paint((150, 200, 255), m, 0.5 - i * 0.12)
    m = plane.poly_mask(rotate(PLANE, track, cx, cy, scale=size))
    plane.glow(m, (90, 160, 255), radius=1.2, strength=0.5)
    plane.paint(plane.vgrad((255, 255, 255), (150, 190, 240), cy - size, cy + size), m)

    image = _blank()
    image.paste(plane.finish().crop((0, 0, 16, 16)), (0, 0))
    country = info.get("country")
    flag = Canvas()
    has_flag = draw_flag(flag, country, 1.0, 1.0, 11.0, 7.0) if country else False
    line2_end = 64
    if has_flag:  # flag bottom right, beside the second line
        image.paste(flag.finish().crop((1, 1, 12, 8)), (53, 9))
        line2_end = 52
    pixels = image.load()

    show_second = (frame // 4) % 2 == 1
    top = info.get("type") if show_second and info.get("type") else info.get("callsign", "")
    bottom = (f"↔{round(info.get('distance_km') or 0)}KM" if show_second
              else _altitude_text(info.get("altitude_m")))
    _big(pixels, str(top)[:8], 17, 64, 0, (255, 190, 90))
    _big(pixels, bottom, 17, line2_end, 9, (180, 255, 180) if show_second else (150, 210, 255))
    return image


# ------------------------------------------------------------------ aurora
def render_aurora_wide(slots: list[dict[str, Any]], frame: int = 0, local_tz=None) -> Image.Image:
    """Moving curtains with Kp bars for the next 24 h; peak Kp and hour on the right."""
    peak = max((r["kp"] for r in slots), default=0.0)
    strength = 0.35 + 0.65 * min(1.0, peak / 7)
    image = _blank()
    for half in (0, 1):
        c = Canvas()
        for i, (col, ph) in enumerate((((40, 255, 140), 0.0), ((130, 80, 255), 1.7), ((40, 220, 210), 3.1))):
            wave = curve(
                lambda t, ph=ph, i=i: (
                    t * 32 / 6,
                    3.5 + i * 2.6 + math.sin((t + half * 6) * 1.3 + ph + frame * 0.6) * 2.0,
                ),
                0, 6, 30,
            )
            m = c.line_mask(wave, 1.3)
            c.glow(m, col, radius=1.6, strength=0.45 * strength)
            c.paint(col, m, (0.45 if half == 0 else 0.3) * strength)
        image.paste(c.finish().crop((0, 0, 32, 16)), (half * 32, 0))

    bars = Canvas()
    for i, slot in enumerate(slots[:8]):
        k = slot["kp"]
        x0 = 0.5 + i * 3.9
        h = max(0.8, k / 9 * 14)
        col = kp_color(k)
        bars.paint(bars.vgrad(col, tuple(v // 2 for v in col), 16 - h, 16),
                   bars.rrect_mask((x0, 16 - h, x0 + 2.9, 16), 0.5))
    layer = bars.finish().crop((0, 0, 32, 16))
    mask = layer.convert("L").point(lambda v: 255 if v > 8 else 0)
    image.paste(layer, (0, 0), mask)

    pixels = image.load()
    for y in range(HEIGHT):  # calm background behind the text
        for x in range(34, 64):
            pixels[x, y] = _scaled(pixels[x, y], 0.35)
    if slots:
        best = max(slots, key=lambda r: r["kp"])
        color = kp_color(best["kp"])
        _big(pixels, f"KP {round(best['kp'])}", 33, 64, 0, color)
        when = best["time"].astimezone(local_tz) if local_tz else best["time"]
        _big(pixels, f"{when.hour:02d}H", 33, 64, 9, (200, 200, 210))
    else:
        _big(pixels, "KP --", 33, 64, 4, (140, 140, 140))
    return image
