"""Nearest aircraft from ADS-B data (readsb / dump1090 / tar1090 aircraft.json).

pick_nearest() chooses the closest airborne plane to a home position;
render_aircraft() draws it: plane silhouette pointing in its direction
of flight, callsign / type on top, altitude / distance below.
No Home Assistant imports.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image

from .flags import country_for, draw_flag
from .gfx import Canvas, rotate
from .render import _small_line

MAX_AGE_SECONDS = 60
FEET = 0.3048
KNOTS = 1.852

# top view of an airliner pointing up (north), roughly -1..1
_RIGHT = [(0.0, -1.0), (0.09, -0.9), (0.11, -0.3), (0.95, 0.12), (0.95, 0.25),
          (0.11, 0.1), (0.08, 0.62), (0.38, 0.84), (0.38, 0.95), (0.0, 0.86)]
PLANE = _RIGHT + [(-x, y) for x, y in reversed(_RIGHT[1:-1])]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def pick_nearest(
    data: dict[str, Any], lat: float, lon: float, max_km: float = 100.0
) -> dict[str, Any] | None:
    """Closest airborne aircraft with a recent position, or None."""
    best: dict[str, Any] | None = None
    for ac in data.get("aircraft", []):
        if not isinstance(ac, dict) or "lat" not in ac or "lon" not in ac:
            continue
        if ac.get("seen_pos", 0) > MAX_AGE_SECONDS or ac.get("alt_baro") == "ground":
            continue
        try:
            d = distance_km(lat, lon, float(ac["lat"]), float(ac["lon"]))
        except (TypeError, ValueError):
            continue
        if d > max_km or (best and d >= best["distance_km"]):
            continue
        altitude = ac.get("alt_geom", ac.get("alt_baro"))
        best = {
            "hex": ac.get("hex", ""),
            "callsign": (ac.get("flight") or "").strip() or (ac.get("r") or "").strip()
            or ac.get("hex", "?").upper(),
            "type": (ac.get("t") or "").strip(),
            "registration": (ac.get("r") or "").strip(),
            "country": country_for(ac.get("hex"), ac.get("r")),
            "distance_km": round(d, 1),
            "altitude_m": round(altitude * FEET) if isinstance(altitude, (int, float)) else None,
            "speed_kmh": round(ac["gs"] * KNOTS) if isinstance(ac.get("gs"), (int, float)) else None,
            "track": ac.get("track") if isinstance(ac.get("track"), (int, float)) else None,
            "bearing": round(bearing_deg(lat, lon, float(ac["lat"]), float(ac["lon"]))),
            "latitude": ac["lat"],
            "longitude": ac["lon"],
        }
    return best


def _altitude_text(meters: int | None) -> str:
    if meters is None:
        return "--"
    return "↑" + (f"{meters / 1000:.1f}KM" if meters >= 1000 else f"{meters}M")


def render_aircraft(info: dict[str, Any], frame: int = 0) -> Image.Image:
    """Plane turned to its track next to its country flag; text alternates."""
    c = Canvas()
    track = info.get("track") or 0.0
    country = info.get("country")
    has_flag = draw_flag(c, country, 17.5, 10.0, 12.5, 8.5) if country else False
    cx, cy, size = (8.5, 15.5, 5.2) if has_flag else (16, 15.5, 7.0)
    a = math.radians(track)
    for i in range(1, 4):  # short contrail, drifting
        back = size * 0.6 + i * 1.6 - (frame % 4) * 0.4
        m = c.circle_mask(cx - math.sin(a) * back, cy + math.cos(a) * back, 0.6)
        c.paint((150, 200, 255), m, 0.5 - i * 0.12)
    m = c.poly_mask(rotate(PLANE, track, cx, cy, scale=size))
    c.glow(m, (90, 160, 255), radius=1.3, strength=0.5)
    c.paint(c.vgrad((255, 255, 255), (150, 190, 240), cy - size, cy + size), m)
    image = c.finish()

    pixels = image.load()
    for y in list(range(0, 6)) + list(range(26, 32)):  # keep text strips clean
        for x in range(32):
            if pixels[x, y][2] < 60:
                pixels[x, y] = (0, 0, 0)
    if has_flag:
        _small_line_at(pixels, country, 23.75, 20, (170, 170, 180))
    show_second = (frame // 4) % 2 == 1
    top = info.get("type") if show_second and info.get("type") else info.get("callsign", "")
    bottom = (f"↔{round(info.get('distance_km') or 0)}KM" if show_second
              else _altitude_text(info.get("altitude_m")))
    _small_line(pixels, str(top)[:8], 0, (255, 190, 90))
    _small_line(pixels, bottom, 27, (150, 210, 255) if not show_second else (180, 255, 180))
    return image


def _small_line_at(pixels, text: str, center_x: float, y: int, color) -> None:
    """Small text centred on a given x (used for the country code)."""
    from .render import CHAR_GAP, _glyph, text_width

    x = round(center_x - text_width(text) / 2)
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and 0 <= x + rx < 32:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP
