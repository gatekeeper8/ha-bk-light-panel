"""Animations kept in the panel's own memory (stored GIF slots).

The panel plays a stored animation by itself, smoothly and without any
Bluetooth traffic, so the retro screens are uploaded once, each to its own
slot, and afterwards only the playlist is switched. No Home Assistant imports.
"""

from __future__ import annotations

import math

from PIL import Image

from .boards import RETRO, render_retro
from .games import terminal_frames
from .render import apply_tint, text_width, to_gif

# Slots used by the integration. The phone app numbers its own animations from 1,
# so ours start at 20, clear of them.
SAFETY_SLOT = 20        # calm animation shown while nothing is connected (day)
SAFETY_NIGHT_SLOT = 21  # the same in the night tint
SAFETY_DARK_SLOT = 22   # black: while the display is switched off
RETRO_SLOTS = {name: 23 + i for i, name in enumerate(RETRO)}  # atari 23 .. agent 29

# A fixed seed: the same screen gives the same GIF (and CRC) every time, so it
# is uploaded only once.
RETRO_SEED = 64

_C64_LINE = "**** 8-BIT BASIC **** 64K RAM SYSTEM **** READY TO PLAY ****"


def retro_timing(name: str) -> tuple[int, int]:
    """(frames for one seamless loop, ms per frame) of a built-in animation.

    Frames were drawn as steps for a live stream (~0.6 s each); stored, the
    panel plays them faster and evenly, but not so fast that text gets hard to read.
    """
    return {
        "atari": (40, 300),                                    # READY. + banner, then again
        "c64": ((text_width(_C64_LINE) + 20) // 4, 300),       # the start-up line scrolls once round
        "invaders": (48, 280),                                 # march 6 x cannon 48
        "terminal": (terminal_frames(RETRO_SEED), 260),        # type, delete, count, blink
        "chomper": (20, 200),                                  # gems 4 x apple 20
        "runner": (32, 200),                                   # every 2nd step: 6 px a frame
        "agent": (24, 240),                                    # shoot, duck, shoot, boom
    }.get(name, (24, 250))


def retro_frames(name: str, text: str | None = None) -> tuple[list[Image.Image], int]:
    frames, frame_ms = retro_timing(name)
    step = RETRO_STEP.get(name, 1)
    return [render_retro(name, f * step, text, RETRO_SEED) for f in range(frames)], frame_ms


# drawing steps skipped in the stored version, to keep the GIF small: every
# upload costs about 0.5 s per KB, and it must fit the gap between two clocks
RETRO_STEP = {"runner": 2}


def retro_gif(name: str, text: str | None = None, tint=None) -> bytes:
    """A built-in 64x16 animation as a looping GIF, always the same bytes for the same input."""
    frames, frame_ms = retro_frames(name, text)
    return to_gif([apply_tint(frame, tint) for frame in frames], frame_ms)


# ------------------------------------------------------------ safety
SAFETY_FRAMES, SAFETY_FRAME_MS = 32, 160  # one slow breath every ~5 s
_EMBER_CORE, _EMBER_EDGE = (255, 160, 70), (190, 55, 8)  # warm, never near white


def render_safety(size: tuple[int, int], frame: int, frames: int = SAFETY_FRAMES) -> Image.Image:
    """A calm ember breathing in the middle, a few stars twinkling slowly.

    Frame 0 is the darkest, so the moment the panel switches to this
    animation (just before a live picture replaces it) shows almost nothing.
    """
    w, h = size
    breath = (1 - math.cos(2 * math.pi * frame / frames)) / 2  # 0 .. 1 .. 0
    level = 0.05 + 0.75 * breath  # calm: never full strength
    cx, cy = (w - 1) / 2, (h - 1) / 2
    radius = min(w, h) * ((0.15 if w == h else 0.20) + 0.05 * breath)
    image = Image.new("RGB", size)
    px = image.load()
    for y in range(h):
        for x in range(w):
            d = math.hypot(x - cx, y - cy) / radius
            glow = math.exp(-d * d) * level
            if glow < 0.02:
                continue
            k = min(1.0, d / 1.6)  # warm white core fading to deep orange
            color = tuple(c + (e - c) * k for c, e in zip(_EMBER_CORE, _EMBER_EDGE))
            px[x, y] = tuple(round(v * glow) for v in color)
    # stars: fixed places away from the ember, each on its own slow beat
    for i in range(7 if w > h else 6):
        sx = round((i * 37 + 5) % w)
        sy = round((i * 23 + 3) % h)
        if math.hypot(sx - cx, sy - cy) < radius * 1.8:
            continue
        twinkle = (1 + math.sin(2 * math.pi * (frame / frames * (1 + i % 2)) + i * 1.9)) / 2
        v = round(70 + 110 * twinkle)
        px[sx, sy] = (v, v, min(255, v + 30))
    return image


def safety_gif(size: tuple[int, int], style: str = "calm", tint=None) -> bytes:
    """The animation the panel plays while nothing is connected.

    calm: the breathing ember (tint e.g. red for night); black: a dark screen,
    for when the display is switched off.
    """
    if style == "black":
        frames = [Image.new("RGB", size)] * 2
        return to_gif(frames, 1000, colors=2)
    frames = [apply_tint(render_safety(size, f), tint) for f in range(SAFETY_FRAMES)]
    return to_gif(frames, SAFETY_FRAME_MS)
