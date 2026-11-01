"""Aurora forecast: NOAA SWPC planetary Kp forecast as a 32x32 picture.

Data: https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json
3-hour steps, observed + predicted. Two formats are accepted:
  old: [["time_tag","kp","observed","noaa_scale"], ["2026-02-19 00:00:00","3.33",...], ...]
  new (2026): [{"time_tag":"2026-02-19T00:00:00","kp":3.33,"observed":"observed",...}, ...]
Times are UTC. No Home Assistant imports.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image

from .gfx import Canvas, curve
from .render import _small_line

DEFAULT_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
SLOT = timedelta(hours=3)


def _rows(data: Any) -> list[dict[str, Any]]:
    """Both formats -> list of {'time': datetime UTC, 'kp': float, 'kind': str}."""
    rows: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return rows
    header = None
    for item in data:
        if isinstance(item, list):
            if header is None:
                header = [str(h) for h in item]
                continue
            item = dict(zip(header, item))
        if not isinstance(item, dict):
            continue
        try:
            stamp = str(item["time_tag"]).replace(" ", "T").rstrip("Z")
            when = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
            kp = float(item["kp"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"time": when, "kp": kp, "kind": str(item.get("observed", ""))})
    rows.sort(key=lambda r: r["time"])
    return rows


def next_hours(data: Any, now: datetime | None = None, hours: int = 24) -> list[dict[str, Any]]:
    """The 3-hour slots from the one running now, covering the next `hours`."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    rows = _rows(data)
    upcoming = [r for r in rows if r["time"] + SLOT > now]
    return upcoming[: max(1, hours // 3)]


def summary(slots: list[dict[str, Any]]) -> dict[str, Any]:
    if not slots:
        return {"max_kp": None, "peak_time": None, "kp": []}
    peak = max(slots, key=lambda r: r["kp"])
    return {
        "max_kp": round(peak["kp"], 2),
        "peak_time": peak["time"].isoformat(),
        "kp": [round(r["kp"], 2) for r in slots],
    }


def kp_color(kp: float) -> tuple[int, int, int]:
    if kp < 4:
        return (0, 200, 90)
    if kp < 5:
        return (255, 210, 0)
    if kp < 6:
        return (255, 120, 0)
    return (255, 40, 40)


def render_aurora(
    slots: list[dict[str, Any]], frame: int = 0, local_tz=None
) -> Image.Image:
    """Moving aurora curtains, Kp bars for the coming hours, peak caption."""
    c = Canvas()
    peak = max((r["kp"] for r in slots), default=0.0)
    strength = 0.35 + 0.65 * min(1.0, peak / 7)  # livelier curtains for a stronger forecast
    for i, (col, ph) in enumerate((((40, 255, 140), 0.0), ((130, 80, 255), 1.7), ((40, 220, 210), 3.1))):
        wave = curve(
            lambda t, ph=ph, i=i: (t * 32 / 6, 5.5 + i * 2.2 + math.sin(t * 1.3 + ph + frame * 0.6) * 2.2),
            0, 6, 30,
        )
        m = c.line_mask(wave, 1.4)
        c.glow(m, col, radius=1.8, strength=0.6 * strength)
        c.paint(col, m, 0.75 * strength)
    for i, slot in enumerate(slots[:8]):
        k = slot["kp"]
        x0 = 1 + i * 3.9
        h = max(0.8, k / 9 * 11)
        bar = c.rrect_mask((x0, 25 - h, x0 + 2.9, 25), 0.5)
        col = kp_color(k)
        c.paint(c.vgrad(col, tuple(v // 2 for v in col), 25 - h, 25), bar)
    image = c.finish()
    px = image.load()
    for y in range(26, 32):
        for x in range(32):
            px[x, y] = (0, 0, 0)
    if slots:
        best = max(slots, key=lambda r: r["kp"])
        text = f"KP{round(best['kp'])}"
        if best["kp"] >= 5:
            when = best["time"].astimezone(local_tz) if local_tz else best["time"]
            text += f" {when.hour:02d}H"
        _small_line(px, text, 27, kp_color(best["kp"]))
    else:
        _small_line(px, "KP --", 27, (140, 140, 140))
    return image
