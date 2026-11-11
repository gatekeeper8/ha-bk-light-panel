"""Animations kept in the panel's own memory (stored GIF slots).

The panel plays a stored animation by itself, smoothly and without any
Bluetooth traffic, so the retro screens are uploaded once, each to its own
slot, and afterwards only the playlist is switched. No Home Assistant imports.
"""

from __future__ import annotations

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
        "runner": (64, 150),                                   # ledge 64 px, 3 px a frame
        "agent": (24, 240),                                    # shoot, duck, shoot, boom
    }.get(name, (24, 250))


def retro_frames(name: str, text: str | None = None) -> tuple[list[Image.Image], int]:
    frames, frame_ms = retro_timing(name)
    return [render_retro(name, f, text, RETRO_SEED) for f in range(frames)], frame_ms


def retro_gif(name: str, text: str | None = None, tint=None) -> bytes:
    """A built-in 64x16 animation as a looping GIF, always the same bytes for the same input."""
    frames, frame_ms = retro_frames(name, text)
    return to_gif([apply_tint(frame, tint) for frame in frames], frame_ms)
