"""Readings screen: up to four values with small icons, coloured by level.

64x16: a 2x2 grid. 32x32: four rows. No Home Assistant imports.
"""

from __future__ import annotations

from PIL import Image

from .render import CHAR_GAP, _glyph, text_width

RGB = tuple[int, int, int]

# 5x5 icons
ICONS: dict[str, tuple[str, ...]] = {
    "temperature": (".#.#.", ".#...", ".#.#.", "###..", "###.."),
    "humidity": ("..#..", ".###.", "#####", "#####", ".###."),
    "pm25": ("#.#.#", ".#.#.", "#.#.#", ".#.#.", "#.#.#"),
    "pm10": ("#...#", "..#..", "#...#", "..#..", "#...#"),
    "pressure": (".###.", "#.#.#", "#.#.#", "#...#", ".###."),
}
ORDER = ("temperature", "humidity", "pm25", "pm10", "pressure")


def _level(value: float, limits: tuple[float, ...], colors: tuple[RGB, ...]) -> RGB:
    for limit, color in zip(limits, colors):
        if value < limit:
            return color
    return colors[-1]


AIR = ((0, 220, 90), (255, 210, 0), (255, 120, 0), (255, 30, 30))


def color_for(kind: str, value: float) -> RGB:
    if kind == "temperature":
        return _level(value, (0, 10, 20, 28),
                      ((110, 170, 255), (190, 225, 255), (255, 235, 170), (255, 170, 60), (255, 70, 40)))
    if kind == "humidity":
        return (90, 170, 255)
    if kind == "pm25":
        return _level(value, (15, 35, 55), AIR)
    if kind == "pm10":
        return _level(value, (25, 50, 80), AIR)
    return (200, 200, 215)


def text_for(kind: str, value: float) -> str:
    if kind == "temperature":
        return f"{value:.0f}°" if abs(value) >= 10 else f"{value:.1f}°"
    if kind == "humidity":
        return f"{value:.0f}%"
    return f"{value:.0f}"


def _draw(pixels, size, x: int, y: int, kind: str, value: float | None, width: int) -> None:
    w, h = size
    known = value is not None
    color = color_for(kind, value) if known else (120, 120, 120)
    for ry, row in enumerate(ICONS[kind]):
        for rx, pixel in enumerate(row):
            if pixel == "#":
                pixels[x + 1 + rx, y + ry] = color
    text = text_for(kind, value) if known else "--"
    tx = x + 7 + max(0, (width - 7 - text_width(text)) // 2)
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and tx + rx < min(w, x + width) and y + ry < h:
                    pixels[tx + rx, y + ry] = color
        tx += len(rows[0]) + CHAR_GAP


def render_readings(values: dict[str, float | None], size: tuple[int, int] = (32, 32)) -> Image.Image:
    """values: kind -> number (None = unavailable); at most four are shown, in ORDER."""
    image = Image.new("RGB", size, (0, 0, 0))
    pixels = image.load()
    kinds = [k for k in ORDER if k in values][:4]
    if size == (64, 16):
        cells = [(0, 2), (32, 2), (0, 9), (32, 9)]
        width = 32
        if len(kinds) <= 2:
            cells = [(0, 5), (32, 5)]
    else:
        top = (size[1] - (len(kinds) * 7 - 2)) // 2
        cells = [(4, top + i * 7) for i in range(4)]
        width = size[0] - 8
    for kind, (x, y) in zip(kinds, cells):
        _draw(pixels, size, x, y, kind, values[kind], width)
    return image
