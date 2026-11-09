"""Forecast screen: a few forecast points, each a small weather picture,
a label (hour or weekday) and the temperature.

64x16: two side by side. 32x32: two stacked. No Home Assistant imports.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from . import font7
from .icons import render_icon
from .render import CHAR_GAP, _glyph, text_width

RGB = tuple[int, int, int]

DAY_NAMES = {
    "pl": ("PON", "WT", "ŚR", "CZW", "PT", "SOB", "NDZ"),
    "en": ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"),
}
TOMORROW = {"pl": "JUTRO", "en": "TMRW"}


def temp_color(t: float | None) -> RGB:
    if t is None:
        return (140, 140, 140)
    if t < 0:
        return (110, 170, 255)
    if t < 10:
        return (190, 225, 255)
    if t < 20:
        return (255, 235, 170)
    if t < 28:
        return (255, 170, 60)
    return (255, 70, 40)


def _small(pixels, text: str, x0: int, x1: int, y: int, color: RGB) -> None:
    text = text.translate(str.maketrans("ĄĆĘŁŃÓŚŹŻ", "ACELNOSZZ"))
    x = x0 + (x1 - x0 - text_width(text)) // 2
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and x0 <= x + rx < x1:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP


def _cell(image: Image.Image, x0: int, y0: int, point: dict[str, Any], frame: int) -> None:
    """16x16 picture, then a 16 pixel column: label on top, temperature below."""
    art = render_icon(point.get("condition") or "cloudy", "", None, frame, night=bool(point.get("night")))
    image.paste(art.resize((16, 16), Image.Resampling.BOX), (x0, y0))
    pixels = image.load()
    _small(pixels, str(point.get("label", ""))[:4], x0 + 16, x0 + 32, y0 + 1, (200, 200, 215))
    t = point.get("temperature")
    text = "--" if t is None else f"{round(t)}°"
    color = temp_color(t)
    if font7.width(text) <= 16:
        font7.draw(pixels, text, x0 + 16 + (16 - font7.width(text)) // 2, y0 + 8, color, (x0 + 16, x0 + 32),
                   height=image.height)
    else:
        _small(pixels, text, x0 + 16, x0 + 32, y0 + 9, color)


def render_forecast(points: list[dict[str, Any]], size: tuple[int, int] = (32, 32), frame: int = 0) -> Image.Image:
    """points: [{condition, label, temperature, night}], the first two are drawn."""
    image = Image.new("RGB", size, (0, 0, 0))
    cells = [(0, 0), (32, 0)] if size == (64, 16) else [(0, 0), (0, 16)]
    for point, (x, y) in zip(points[:2], cells):
        _cell(image, x, y, point, frame)
    return image
