"""Little game-style animations for the wide 64x16 panel, all original designs.

terminal: a root prompt types rm -rf /* and reports the files it deleted
fish:     a hungry fish chases a worm along the seabed, a shark behind it
runner:   an adventurer runs along a castle ledge and long-jumps a gap
agent:    an agent shoots at a hovering drone and crouches under its fire

Each render_* takes a frame number; one call per frame. No Home Assistant
imports.
"""

from __future__ import annotations

import math
import random

from PIL import Image

from .gfx import Canvas
from .render import CHAR_GAP, _glyph

W, H = 64, 16
RGB = tuple[int, int, int]
GAMES = ("terminal", "fish", "runner", "agent")


def _blank(bg: RGB = (0, 0, 0)) -> Image.Image:
    return Image.new("RGB", (W, H), bg)


def _small(pixels, text: str, x: int, y: int, color: RGB) -> int:
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and 0 <= x + rx < W and 0 <= y + ry < H:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP
    return x


def _sprite(pixels, rows: tuple[str, ...], x: int, y: int, colors: dict[str, RGB], flip: bool = False) -> None:
    for ry, row in enumerate(rows):
        if flip:
            row = row[::-1]
        for rx, key in enumerate(row):
            if key != "." and 0 <= x + rx < W and 0 <= y + ry < H:
                pixels[x + rx, y + ry] = colors[key]


# ---------------------------------------------------------------- terminal
_PATHS = ("/BIN", "/BOOT", "/DEV", "/ETC", "/HOME", "/LIB", "/OPT", "/ROOT", "/SBIN", "/USR", "/VAR")
GREEN, DIM = (80, 255, 120), (40, 140, 70)


def render_terminal(frame: int, seed: int = 0) -> Image.Image:
    """Three terminal lines: typing, a scroll of removed paths, the count, a blinking cursor."""
    rng = random.Random(seed)
    files = rng.randint(48_000, 260_000)
    command = "RM -RF /*"
    lines: list[tuple[str, RGB]] = []
    if frame < len(command) + 2:  # typing, one character per frame
        typed = command[: max(0, frame - 1)]
        lines = [("#", GREEN), ("", GREEN), ("# " + typed + ("_" if frame % 2 == 0 else ""), GREEN)]
        lines = lines[-1:]
    else:
        step = frame - len(command) - 2
        log = [("# " + command, GREEN)]
        for i in range(min(step, len(_PATHS))):
            log.append(("RM " + _PATHS[i], DIM))
        if step >= len(_PATHS):
            log.append((f"{files} FILES", (255, 210, 80)))
            log.append(("DELETED.", (255, 210, 80)))
            log.append(("#" + (" _" if step % 2 == 0 else ""), GREEN))
        lines = log[-3:]
    image = _blank()
    pixels = image.load()
    for (text, color), y in zip(lines, (0, 6, 11) if len(lines) == 3 else (0, 6) if len(lines) == 2 else (0,)):
        _small(pixels, text, 1, y, color)
    return image


def terminal_frames(seed: int = 0) -> int:
    """Frames for one full run (typing, the scroll, a few cursor blinks)."""
    return len("RM -RF /*") + 2 + len(_PATHS) + 6


# -------------------------------------------------------------------- fish
def _fish(c: Canvas, x: float, y: float, frame: int) -> None:
    """Orange fish facing right, 13 pixels high, tail flapping, mouth opening."""
    body = c.poly_mask([(x + 6.8 * math.cos(a / 24 * 2 * math.pi), y + 6.3 * math.sin(a / 24 * 2 * math.pi))
                        for a in range(24)])
    flap = math.sin(frame * 1.6) * 2.2
    tail = c.poly_mask([(x - 4.5, y), (x - 11.5, y - 5.5 + flap), (x - 11.0, y + 5.5 + flap)])
    c.paint(c.vgrad((255, 170, 40), (220, 80, 20), y - 6, y + 6), tail)
    c.paint(c.vgrad((255, 190, 60), (230, 90, 20), y - 6, y + 6), body)
    fin = c.poly_mask([(x - 2.5, y - 4.8), (x + 2.5, y - 4.8), (x - 3.5, y - 7.5)])
    c.paint((255, 120, 30), fin)
    for k in (-1.5, 1.0):  # stripes
        c.paint((255, 245, 230), c.rrect_mask((x + k - 0.6, y - 4.8, x + k + 0.6, y + 4.8), 0.5), 0.85)
    c.paint((20, 20, 30), c.circle_mask(x + 3.0, y - 1.6, 1.0))
    c.paint((255, 255, 255), c.circle_mask(x + 3.3, y - 1.9, 0.35))
    gape = 1.2 + 1.2 * (0.5 + 0.5 * math.sin(frame * 2.1))
    c.paint((10, 20, 60), c.poly_mask([(x + 6.6, y + 0.8 - gape), (x + 6.6, y + 0.8 + gape), (x + 3.8, y + 0.8)]))


def _shark(c: Canvas, x: float, y: float, frame: int) -> None:
    """Grey shark facing right with a fin and teeth, a bit smaller than the fish."""
    c.paint(c.vgrad((150, 160, 175), (95, 105, 120), y - 4, y + 4),
            c.poly_mask([(x + 7.0, y + 0.5), (x + 2.0, y - 3.8), (x - 6.0, y - 2.5), (x - 6.0, y + 2.5), (x + 2.0, y + 3.6)]))
    c.paint((120, 130, 145), c.poly_mask([(x - 1.0, y - 3.4), (x + 2.2, y - 3.4), (x - 1.5, y - 7.0)]))
    swish = math.sin(frame * 1.4) * 1.8
    c.paint((110, 120, 135), c.poly_mask([(x - 5.5, y), (x - 10.0, y - 4.0 + swish), (x - 9.5, y + 3.5 + swish)]))
    c.paint((235, 235, 240), c.poly_mask([(x + 6.5, y + 0.6), (x + 2.5, y + 1.4), (x + 6.0, y + 1.6)]))
    c.paint((255, 60, 50), c.circle_mask(x + 3.2, y - 1.4, 0.65))


def render_fish(frame: int) -> Image.Image:
    """Seabed board at the bottom; a fish chases a worm, a shark chases the fish."""
    image = _blank((0, 10, 35))
    c = Canvas()
    worm_x = 63 - (frame * 3) % 30  # the worm drifts towards the fish, eaten, comes again
    _shark(c, 7.0 + math.sin(frame * 0.5) * 1.5, 6.5 + math.sin(frame * 0.7), frame)
    image.paste(c.finish().crop((0, 0, 32, 16)), (0, 0))
    c2 = Canvas()
    _fish(c2, 14.0, 6.5 + math.sin(frame * 0.6) * 0.6, frame)
    fish_img = c2.finish().crop((0, 0, 32, 16))
    mask = fish_img.convert("L").point(lambda v: 255 if v > 12 else 0)
    image.paste(fish_img, (20, 0), mask)
    pixels = image.load()
    # the worm: a pink wiggle, until the fish's mouth reaches it
    if worm_x > 41:
        for i in range(4):
            wx = worm_x + i
            wy = 7 + (1 if (i + frame) % 2 else 0)
            if 0 <= wx < W:
                pixels[wx, wy] = (255, 120, 170)
    # seabed: sand with pebbles, swaying weed
    for x in range(W):
        for y in (14, 15):
            pixels[x, y] = (200, 170, 90) if (x * 7 + y * 3) % 11 else (150, 120, 70)
        if (x * 13) % 17 == 0:
            pixels[x, 13] = (120, 120, 130)
    for base in (4, 33, 57):
        for k in range(4):
            sway = 1 if (frame + k + base) % 4 < 2 else 0
            if 0 <= base + sway < W:
                pixels[base + sway, 13 - k] = (40, 170, 70)
    for i in range(3):  # bubbles rising from the fish
        by = 6 - ((frame + i * 3) % 7)
        if 0 <= by < 13:
            pixels[42 + i % 2, by] = (150, 200, 255)
    return image


# ------------------------------------------------------------------ runner
_RUN = {
    "a": ("..HH..", ".HSS..", "..SS..", "RRTT..", "R.TTS.", "..TT.S", "..TT..", "..BB..",
          "..LL..", ".L..L.", "L....L", "F....F"),
    "b": ("..HH..", ".HSS..", "..SS..", "RRTT..", "R.TT..", "..TTS.", "..TT..", "..BB..",
          "..LL..", "..LL..", "..L.L.", "..F.F."),
    "jump": ("..HH..", ".HSS..", "R.SS..", "RRTT.S", "..TTS.", "..TT..", "..BB..", ".LLLL.",
             "L....L", "F....F", "......", "......"),
}
_RUN_COLORS = {"H": (90, 50, 20), "S": (255, 200, 150), "R": (230, 40, 40), "T": (60, 110, 200),
               "B": (130, 80, 30), "L": (150, 110, 70), "F": (110, 70, 40)}
_GAP = (30, 40)  # the gap in the ledge, in world pixels within one 64-pixel stretch


def render_runner(frame: int) -> Image.Image:
    """The ledge scrolls left; the adventurer runs and leaps the gap with an arc."""
    image = _blank((12, 10, 25))
    pixels = image.load()
    scroll = (frame * 3) % 64
    for x in range(W):  # stone ledge with a gap, and the wall behind
        wx = (x + scroll) % 64
        if not (_GAP[0] <= wx < _GAP[1]):
            for y in (13, 14, 15):
                brick = (wx // 4 + (y % 2) * 2) % 3
                pixels[x, y] = ((150, 130, 100), (125, 105, 80), (170, 150, 115))[brick]
        if wx % 16 == 8:  # torch on the wall
            pixels[x, 4] = (255, 200, 60) if frame % 2 else (255, 140, 30)
            pixels[x, 5] = (200, 90, 20)
            pixels[x, 6] = (90, 60, 40)
    hero_x = 14
    feet_world = (hero_x + 3 + scroll) % 64
    ahead = (_GAP[0] - feet_world) % 64
    behind = (feet_world - _GAP[1]) % 64
    in_air = ahead <= 6 or (_GAP[0] <= feet_world < _GAP[1]) or behind <= 2
    if in_air:  # a parabola from take-off to landing
        progress = ((feet_world - (_GAP[0] - 6)) % 64) / (_GAP[1] - _GAP[0] + 9)
        lift = round(math.sin(min(1.0, max(0.0, progress)) * math.pi) * 4)
        _sprite(pixels, _RUN["jump"], hero_x, 1 - lift, _RUN_COLORS)
    else:
        _sprite(pixels, _RUN["a" if frame % 2 == 0 else "b"], hero_x, 1, _RUN_COLORS)
    return image


# ------------------------------------------------------------------- agent
_AGENT = {
    "stand": ("..HH....", ".HSS....", "..SS....", ".CCCGGGG", ".CCC....", ".CCC....", ".CCC....",
              ".PPP....", ".P.P....", ".P.P....", ".P.P....", ".P.P....", "BB.BB..."),
    "crouch": ("........", "........", "........", "........", "..HH....", ".HSS....", "..SS....",
               ".CCCGGGG", ".CCC....", ".PPPP...", "PP..P...", "P...P...", "BB..BB.."),
}
_AGENT_COLORS = {"H": (40, 30, 20), "S": (240, 190, 140), "C": (110, 115, 105), "G": (60, 60, 70),
                 "P": (70, 85, 140), "B": (120, 90, 60)}


def _drone(pixels, x: int, y: int, frame: int, hit: int = 0) -> None:
    if hit:  # sparks flying out
        rng = random.Random(hit)
        for _ in range(10):
            dx, dy = rng.randint(-5, 5), rng.randint(-4, 4)
            if 0 <= x + dx < W and 0 <= y + dy < H:
                pixels[x + dx, y + dy] = (255, rng.randint(120, 230), 40)
        return
    def put(px_, py_, color):
        if 0 <= px_ < W and 0 <= py_ < H:
            pixels[px_, py_] = color

    for dx in range(-4, 5):
        put(x + dx, y, (170, 175, 185))
    for dx in range(-3, 4):
        put(x + dx, y + 1, (120, 125, 135))
    put(x, y + 1, (255, 40, 40) if frame % 2 else (160, 20, 20))
    for dx in (-4, 4):  # rotors
        put(x + dx, y - 1, (220, 220, 230) if (frame + dx) % 2 else (90, 90, 100))


def render_agent(frame: int) -> Image.Image:
    """Shoot, the drone fires back, crouch, stand, shoot again; the drone blows up."""
    image = _blank((5, 8, 18))
    pixels = image.load()
    for x in range(W):  # metal floor
        pixels[x, 15] = (70, 75, 85) if x % 4 else (110, 115, 125)
    phase = frame % 24
    drone_x, drone_y = 50, 4 + round(math.sin(frame * 0.8))
    crouch = 7 <= phase <= 11
    _sprite(pixels, _AGENT["crouch" if crouch else "stand"], 4, 2, _AGENT_COLORS)
    gun_y = 9 if crouch else 5
    if phase in (1, 2, 3, 4, 13, 14, 15, 16):  # our shot flying right
        t = (phase - 1) % 12
        bx = 13 + t * 9
        if phase in (1, 13):
            pixels[12, gun_y] = (255, 240, 150)  # muzzle flash
        for k in range(3):
            if bx + k < W:
                pixels[bx + k, gun_y] = (255, 230, 90)
    if 7 <= phase <= 10:  # the drone's red laser, passing over the crouching agent
        lx = drone_x - 6 - (phase - 7) * 12
        for k in range(5):
            if 0 <= lx - k < W:
                pixels[lx - k, 5] = (255, 50, 50)
    hit = frame // 24 * 7 + 1 if 17 <= phase <= 19 else 0
    if phase < 20:
        _drone(pixels, drone_x, drone_y, frame, hit)
    else:  # a new drone flies in
        _drone(pixels, drone_x + (24 - phase) * 4, drone_y, frame)
    return image


def render_game(name: str, frame: int = 0, seed: int = 0) -> Image.Image:
    if name == "terminal":
        return render_terminal(frame % terminal_frames(seed), seed)
    return {"fish": render_fish, "runner": render_runner, "agent": render_agent}.get(name, render_fish)(frame)
