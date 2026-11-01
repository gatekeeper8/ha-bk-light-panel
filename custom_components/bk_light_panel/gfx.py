"""Smooth drawing for a 32x32 LED panel.

Everything is drawn 4x larger (128x128) with gradients and soft glow,
then scaled down with area averaging. On the panel this gives smooth
edges and shading instead of hard blocky pixels.
Coordinates in all helpers are panel pixels (0..32), floats allowed.
No Home Assistant imports.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 4
SIZE = 32
N = SIZE * SS

RGB = tuple[int, int, int]
Point = tuple[float, float]


def _s(v: float) -> float:
    return v * SS


def _pts(points: Iterable[Point]) -> list[tuple[float, float]]:
    return [(_s(x), _s(y)) for x, y in points]


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


class Canvas:
    """A 4x supersampled RGBA layer stack, finished to a 32x32 RGB image."""

    def __init__(self) -> None:
        self.image = Image.new("RGBA", (N, N), (0, 0, 0, 0))

    # ---------------------------------------------------------- masks
    @staticmethod
    def mask() -> Image.Image:
        return Image.new("L", (N, N), 0)

    @staticmethod
    def circle_mask(cx: float, cy: float, r: float, m: Image.Image | None = None, value: int = 255):
        m = m or Canvas.mask()
        ImageDraw.Draw(m).ellipse((_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)), fill=value)
        return m

    @staticmethod
    def ellipse_mask(box, m: Image.Image | None = None, value: int = 255):
        m = m or Canvas.mask()
        x0, y0, x1, y1 = box
        ImageDraw.Draw(m).ellipse((_s(x0), _s(y0), _s(x1), _s(y1)), fill=value)
        return m

    @staticmethod
    def poly_mask(points, m: Image.Image | None = None, value: int = 255):
        m = m or Canvas.mask()
        ImageDraw.Draw(m).polygon(_pts(points), fill=value)
        return m

    @staticmethod
    def rrect_mask(box, radius: float, m: Image.Image | None = None, value: int = 255):
        m = m or Canvas.mask()
        x0, y0, x1, y1 = box
        ImageDraw.Draw(m).rounded_rectangle(
            (_s(x0), _s(y0), _s(x1), _s(y1)), radius=_s(radius), fill=value
        )
        return m

    @staticmethod
    def line_mask(points, width: float, m: Image.Image | None = None, value: int = 255):
        m = m or Canvas.mask()
        draw = ImageDraw.Draw(m)
        pts = _pts(points)
        draw.line(pts, fill=value, width=max(1, round(_s(width))), joint="curve")
        r = _s(width) / 2  # round caps
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=value)
        return m

    # --------------------------------------------------------- fills
    @staticmethod
    def vgrad(top: RGB, bottom: RGB, y0: float = 0, y1: float = SIZE) -> Image.Image:
        grad = Image.new("RGB", (1, N))
        for y in range(N):
            grad.putpixel((0, y), mix(top, bottom, (y / SS - y0) / max(0.01, y1 - y0)))
        return grad.resize((N, N))

    @staticmethod
    def rgrad(cx: float, cy: float, r: float, inner: RGB, outer: RGB) -> Image.Image:
        grad = Image.new("RGB", (N, N), outer)
        draw = ImageDraw.Draw(grad)
        steps = max(2, int(_s(r)))
        for i in range(steps, 0, -1):
            rr = _s(r) * i / steps
            draw.ellipse(
                (_s(cx) - rr, _s(cy) - rr, _s(cx) + rr, _s(cy) + rr),
                fill=mix(inner, outer, i / steps),
            )
        return grad

    def paint(self, fill: Image.Image | RGB, m: Image.Image, alpha: float = 1.0) -> None:
        """Paint a colour or gradient through a mask."""
        if not isinstance(fill, Image.Image):
            fill = Image.new("RGB", (N, N), fill)
        if alpha < 1:
            m = m.point(lambda v: int(v * alpha))
        layer = fill.convert("RGBA")
        layer.putalpha(m)
        self.image.alpha_composite(layer)

    def glow(self, m: Image.Image, color: RGB, radius: float = 2.0, strength: float = 0.6) -> None:
        """Soft light around a shape (paint the shape itself afterwards)."""
        blurred = m.filter(ImageFilter.GaussianBlur(_s(radius)))
        self.paint(color, blurred, strength)

    # ------------------------------------------------------- finish
    def finish(self, background: RGB = (0, 0, 0), y_offset: int = 0) -> Image.Image:
        base = Image.new("RGBA", (N, N), background + (255,))
        base.alpha_composite(self.image)
        small = base.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BOX)
        if y_offset:
            small = ImageChops.offset(small, 0, y_offset)
            ImageDraw.Draw(small).rectangle((0, 0, SIZE - 1, y_offset - 1), fill=background)
        return small


def rotate(points: Iterable[Point], angle_deg: float, cx: float = 0, cy: float = 0,
           scale: float = 1.0, dx: float = 0, dy: float = 0) -> list[Point]:
    """Rotate (clockwise, screen coordinates) and move a shape."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [
        (cx + dx + (x * ca - y * sa) * scale, cy + dy + (x * sa + y * ca) * scale)
        for x, y in points
    ]


def curve(fn: Callable[[float], Point], t0: float, t1: float, steps: int = 24) -> list[Point]:
    return [fn(t0 + (t1 - t0) * i / steps) for i in range(steps + 1)]
