"""Little game-style animations for the wide 64x16 panel, all original designs.

terminal: a root prompt types rm -rf /* and reports the files it deleted
chomper:  a round green monster munches gems in a maze corridor, a bat behind
runner:   an adventurer runs along a castle ledge and long-jumps a gap
agent:    an agent shoots at a hovering drone and crouches under its fire

Each render_* takes a frame number; one call per frame. No Home Assistant
imports.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageChops

from .gfx import Canvas
from .render import CHAR_GAP, _glyph

W, H = 64, 16
RGB = tuple[int, int, int]
GAMES = ("terminal", "chomper", "runner", "agent")


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


# --------------------------------------------------------- jointed figures
# Figures are drawn from limbs at joint angles (degrees from straight down,
# positive = forwards/right), 4x supersampled and shaded: smooth, Amiga-style
# motion instead of blocky sprites. Back limbs are darker for depth.
_LIMB = {"thigh": 3.4, "shin": 3.4, "upper": 2.7, "fore": 2.5, "torso": 4.6}


def _darker(color: RGB, k: float = 0.72) -> RGB:
    return tuple(int(v * k) for v in color)  # type: ignore[return-value]


def _point(x: float, y: float, angle: float, length: float) -> tuple[float, float]:
    a = math.radians(angle)
    return x + math.sin(a) * length, y + math.cos(a) * length


def _figure(c: _Layer, hip: tuple[float, float], pose: dict, pal: dict) -> None:
    """pose: lean, legs [(thigh, knee)]*2 front/back, arms [(upper, elbow)]*2, optional gun."""
    hx, hy = hip
    lean = pose.get("lean", 0.0)
    neck = _point(hx, hy, 180 + lean, _LIMB["torso"])
    shoulder = _point(hx, hy, 180 + lean, _LIMB["torso"] - 0.6)

    def leg(thigh: float, knee: float, color: RGB, boot: RGB) -> None:
        k = _point(hx, hy, thigh, _LIMB["thigh"])
        a = _point(*k, thigh - knee, _LIMB["shin"])
        c.paint(color, c.line_mask([(hx, hy), k], 1.55))
        c.paint(color, c.line_mask([k, a], 1.35))
        toe = _point(*a, thigh - knee + 90, 1.3)
        c.paint(boot, c.line_mask([a, toe], 1.2))

    def arm(upper: float, elbow: float, color: RGB, hand: RGB, gun: bool = False) -> None:
        e = _point(*shoulder, upper, _LIMB["upper"])
        h = _point(*e, upper + elbow, _LIMB["fore"])
        c.paint(color, c.line_mask([shoulder, e], 1.25))
        c.paint(color, c.line_mask([e, h], 1.1))
        c.paint(hand, c.circle_mask(*h, 0.6))
        if gun:
            muzzle = _point(*h, upper + elbow, 1.8)
            c.paint((70, 75, 85), c.line_mask([h, muzzle], 0.9))

    (bt, bk), (ft, fk) = pose["legs"][1], pose["legs"][0]
    (ba, be), (fa, fe) = pose["arms"][1], pose["arms"][0]
    arm(ba, be, _darker(pal["sleeve"]), _darker(pal["skin"]))
    leg(bt, bk, _darker(pal["legs"]), _darker(pal["boots"]))
    c.paint(c.vgrad(pal["torso"], _darker(pal["torso"], 0.75), neck[1], hy),
            c.line_mask([(hx, hy), neck], 2.2))
    if "belt" in pal:
        c.paint(pal["belt"], c.line_mask([_point(hx, hy, 180 + lean, 0.3), _point(hx, hy, 180 + lean, 0.9)], 2.3))
    leg(ft, fk, pal["legs"], pal["boots"])
    head = _point(*neck, 180 + lean, 1.25)
    c.paint(pal["skin"], c.circle_mask(*head, 1.15))
    c.paint(pal["hair"], c.circle_mask(head[0] - 0.35, head[1] - 0.45, 0.95))
    if "scarf" in pal:  # a scarf streaming behind in the wind
        flutter = pose.get("flutter", 0.0)
        tail = [(neck[0], neck[1]), (neck[0] - 1.8, neck[1] - 0.2 + flutter * 0.4),
                (neck[0] - 3.2, neck[1] + 0.3 - flutter * 0.5)]
        c.paint(pal["scarf"], c.line_mask(tail, 0.9))
    arm(fa, fe, pal["sleeve"], pal["skin"], pose.get("gun", False))


class _Layer:
    """A Canvas plus a coverage canvas, so smooth edges blend with any background."""

    def __init__(self) -> None:
        self.color, self.cover = Canvas(), Canvas()

    def __getattr__(self, name):  # mask and gradient helpers come from the colour canvas
        return getattr(self.color, name)

    def paint(self, fill, m, alpha: float = 1.0) -> None:
        self.color.paint(fill, m, alpha)
        self.cover.paint((255, 255, 255), m, alpha)

    def glow(self, *args, **kwargs) -> None:
        self.color.glow(*args, **kwargs)


def _paste_figure(image: Image.Image, layer: _Layer, x0: int, y0: int, box=(0, 0, 16, 16)) -> None:
    """Composite the layer over the image: background * (1 - coverage) + colour."""
    color = layer.color.finish().crop(box)
    alpha = layer.cover.finish().crop(box).convert("L")
    w, h = color.size
    region = image.crop((x0, y0, x0 + w, y0 + h))
    behind = Image.composite(Image.new("RGB", (w, h)), region, alpha)
    image.paste(ImageChops.add(behind, color), (x0, y0))


def _copper(top: RGB, bottom: RGB, bands: int = 8) -> Image.Image:
    """Amiga-style copper gradient: horizontal bands from top to bottom colour."""
    image = Image.new("RGB", (W, H))
    px = image.load()
    for y in range(H):
        k = min(bands - 1, y * bands // H) / (bands - 1)
        color = tuple(int(t + (b - t) * k) for t, b in zip(top, bottom))
        for x in range(W):
            px[x, y] = color
    return image


# ----------------------------------------------------------------- chomper
def _chomper(c: _Layer, x: float, y: float, frame: int) -> None:
    """A round green monster, 13 px high, big eyes, a toothy mouth that snaps."""
    c.paint(c.rgrad(x - 2, y - 3, 8, (150, 255, 120), (20, 130, 50)), c.circle_mask(x, y, 6.4))
    snap = 0.5 + 0.5 * math.sin(frame * 2.4)  # 0 shut .. 1 wide open
    mouth = c.rrect_mask((x - 1.0, y + 1.0, x + 6.2, y + 1.6 + 2.6 * snap), 1.0)
    c.paint((70, 10, 20), mouth)
    for tx in (0.2, 1.9, 3.6, 5.1):  # teeth top and bottom
        c.paint((255, 255, 245), c.poly_mask([(x + tx, y + 1.0), (x + tx + 1.2, y + 1.0), (x + tx + 0.6, y + 2.0)]))
        c.paint((255, 255, 245), c.poly_mask([(x + tx, y + 1.6 + 2.6 * snap), (x + tx + 1.2, y + 1.6 + 2.6 * snap),
                                              (x + tx + 0.6, y + 0.8 + 2.6 * snap)]))
    for ex in (0.6, 3.6):  # big eyes looking ahead
        c.paint((255, 255, 255), c.circle_mask(x + ex, y - 2.6, 1.5))
        c.paint((20, 20, 40), c.circle_mask(x + ex + 0.6, y - 2.5, 0.75))
    c.paint((80, 200, 90), c.poly_mask([(x - 2.0, y - 6.0), (x - 0.5, y - 8.2), (x + 0.6, y - 5.8)]))  # a horn
    step = math.sin(frame * 2.0) * 1.0  # little feet
    c.paint((20, 110, 40), c.rrect_mask((x - 3.5 + step, y + 5.2, x - 1.2 + step, y + 6.6), 0.6))
    c.paint((20, 110, 40), c.rrect_mask((x + 1.2 - step, y + 5.2, x + 3.5 - step, y + 6.6), 0.6))


def _bat(c: _Layer, x: float, y: float, frame: int) -> None:
    flap = math.sin(frame * 2.2) * 2.2
    c.paint((140, 60, 200), c.circle_mask(x, y, 2.0))
    for side in (-1, 1):
        c.paint((110, 40, 170), c.poly_mask([(x, y - 0.5), (x + side * 5.5, y - 2.5 - flap),
                                              (x + side * 4.0, y + 1.0), (x + side * 2.2, y + 0.4)]))
    c.paint((255, 230, 60), c.circle_mask(x + 0.8, y - 0.6, 0.45))
    c.paint((255, 230, 60), c.circle_mask(x - 0.6, y - 0.6, 0.45))


def render_chomper(frame: int) -> Image.Image:
    """Maze corridor board at the bottom; the chomper munches gems, a bat chases it."""
    image = _copper((10, 5, 40), (40, 20, 80))
    px = image.load()
    for x in range(W):  # the corridor walls: stone with a highlight
        for y in (13, 14, 15):
            px[x, y] = (70, 160, 170) if y == 13 else ((40, 110, 120) if (x + y) % 5 else (25, 80, 90))
        px[x, 0] = (70, 160, 170)
    scroll = frame * 2
    for gx in range(-scroll % 8, W, 8):  # gems ahead of the mouth, eaten as it passes
        if gx > 33:
            hue = ((gx + scroll) // 8) % 3
            color = ((255, 80, 120), (90, 220, 255), (255, 210, 60))[hue]
            for dx, dy in ((0, 0), (1, 0), (0, -1), (0, 1), (-1, 0)):
                if 0 <= gx + dx < W:
                    px[gx + dx, 7 + dy] = color if (dx, dy) != (0, 0) else (255, 255, 255)
    apple_x = 63 - (frame * 2) % 40
    if apple_x > 34:  # an apple now and then
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (-1, 1), (0, -1)):
            if 0 <= apple_x + dx < W:
                px[apple_x + dx, 9 + dy] = (230, 30, 40) if dy >= 0 else (60, 160, 40)
    c = _Layer()
    _chomper(c, 8.0, 7.0 + math.sin(frame * 1.2) * 0.4, frame)
    _paste_figure(image, c, 20, 0)
    b = _Layer()
    _bat(b, 7.0, 6.0 + math.sin(frame * 0.9) * 2.0, frame)
    _paste_figure(image, b, 0, 0)
    return image


# ------------------------------------------------------------------ runner
_RUNNER_PAL = {"skin": (255, 205, 160), "hair": (120, 70, 30), "torso": (70, 200, 120), "sleeve": (70, 200, 120),
               "legs": (225, 185, 120), "boots": (160, 95, 45), "belt": (240, 200, 70), "scarf": (255, 50, 50)}
_GAP = (30, 41)
# The ledge: dark, warm sandstone. LEDs make mid-bright beige look almost white
# with a pink cast, so the stones stay low and lean to red-brown.
LEDGE_STONES = ((96, 52, 24), (78, 41, 19), (112, 63, 30))
LEDGE_TOP = ((140, 84, 38), (122, 72, 32), (156, 96, 44))  # the worn top edge, catching torchlight
LEDGE_MORTAR = (38, 18, 8)


def _run_pose(t: float) -> dict:
    """An 8-step running cycle; t = 0..1."""
    p = t * 2 * math.pi
    legs = []
    for phase in (0.0, math.pi):
        swing = math.sin(p + phase)
        thigh = 38 * swing
        knee = 20 + 55 * max(0.0, math.cos(p + phase))  # the knee folds as the leg swings forward
        legs.append((thigh, knee))
    arms = [(-40 * math.sin(p), 70), (-40 * math.sin(p + math.pi), 70)]
    return {"lean": 12, "legs": legs, "arms": arms, "flutter": math.sin(p * 2)}


_JUMP = {"lean": 18, "legs": [(75, 95), (-25, 35)], "arms": [(120, 30), (-60, 60)], "flutter": 1.0}


def render_runner(frame: int) -> Image.Image:
    """A castle ledge scrolls by; the adventurer runs and long-jumps the gap."""
    image = _copper((8, 4, 35), (55, 25, 75))
    px = image.load()
    scroll = (frame * 3) % 64
    for x in range(W):
        wx = (x + scroll) % 64
        if wx % 32 in (10, 11, 12):  # distant pillars (slow parallax)
            pass
        if not (_GAP[0] <= wx < _GAP[1]):
            for y in (13, 14, 15):
                if y > 13 and (wx + (y % 2) * 2) % 4 == 3:  # dark mortar between the stones
                    px[x, y] = LEDGE_MORTAR
                else:
                    brick = (wx // 4 + (y % 2) * 2) % 3
                    px[x, y] = (LEDGE_TOP if y == 13 else LEDGE_STONES)[brick]
        if wx % 21 == 5:  # torches
            px[x, 5] = (255, 230, 120) if frame % 2 else (255, 160, 40)
            px[x, 4] = (255, 120, 30) if frame % 3 else (255, 200, 80)
            px[x, 6] = (110, 70, 40)
    for x in range(W):  # far pillars with parallax
        wx = (x + scroll // 2) % 32
        if wx in (2, 3):
            for y in range(1, 13):
                if px[x, y][0] < 60:
                    px[x, y] = (55, 40, 85) if wx == 2 else (40, 30, 65)
    hero_x = 14
    feet = (hero_x + 8 + scroll) % 64
    take_off, land = _GAP[0] - 6, _GAP[1] + 2
    c = _Layer()
    if take_off <= feet < land:
        t = (feet - take_off) / (land - take_off)
        lift = math.sin(t * math.pi) * 4.0
        _figure(c, (8.0, 8.4 - lift), _JUMP, _RUNNER_PAL)
    else:
        bob = abs(math.sin(frame / 8 * 2 * math.pi)) * 0.5
        _figure(c, (8.0, 8.4 - bob), _run_pose((frame % 8) / 8), _RUNNER_PAL)
    _paste_figure(image, c, hero_x, 0)
    return image


# ------------------------------------------------------------------- agent
_AGENT_PAL = {"skin": (255, 200, 150), "hair": (90, 60, 35), "torso": (175, 180, 160), "sleeve": (175, 180, 160),
              "legs": (90, 115, 200), "boots": (120, 90, 60)}
_AIM = {"lean": 2, "legs": [(18, 5), (-14, 5)], "arms": [(92, 0), (60, 60)], "gun": True}
_CROUCH = {"lean": 25, "legs": [(85, 150), (20, 100)], "arms": [(92, -5), (50, 60)], "gun": True}


def _drone(pixels, x: int, y: int, frame: int, hit: int = 0) -> None:
    def put(px_, py_, color):
        if 0 <= px_ < W and 0 <= py_ < H:
            pixels[px_, py_] = color

    if hit:  # sparks flying out
        rng = random.Random(hit)
        for _ in range(12):
            put(x + rng.randint(-5, 5), y + rng.randint(-4, 4), (255, rng.randint(120, 230), 40))
        return
    for dx in range(-4, 5):
        put(x + dx, y, (200, 205, 215) if abs(dx) < 3 else (150, 155, 165))
    for dx in range(-3, 4):
        put(x + dx, y + 1, (110, 115, 130))
    put(x, y + 1, (255, 40, 40) if frame % 2 else (160, 20, 20))
    for dx in (-4, 4):  # rotors
        put(x + dx, y - 1, (230, 230, 240) if (frame + dx) % 2 else (90, 90, 100))


def render_agent(frame: int) -> Image.Image:
    """Aim and shoot, the drone fires back, crouch, stand, shoot; the drone blows up."""
    image = _copper((5, 20, 30), (20, 50, 60))
    px = image.load()
    for x in range(W):  # metal floor with lights, pipes on the wall
        px[x, 15] = (80, 90, 100) if x % 6 else (140, 150, 160)
        px[x, 14] = (50, 60, 70)
        if x % 12 == 6:
            px[x, 2] = (90, 255, 200) if (frame + x) % 4 else (40, 120, 100)
    for x in range(W):
        px[x, 1] = (60, 70, 80)
    phase = frame % 24
    drone_x, drone_y = 50, 4 + round(math.sin(frame * 0.8))
    crouch = 7 <= phase <= 11
    c = _Layer()
    _figure(c, (6.0, 8.2 + (3.2 if crouch else 0.0)), _CROUCH if crouch else _AIM, _AGENT_PAL)
    _paste_figure(image, c, 2, 0)
    gun_y = 7 if crouch else 4
    if phase in (1, 2, 3, 4, 13, 14, 15, 16):  # our shot flying right
        t = (phase - 1) % 12
        bx = 16 + t * 9
        if phase in (1, 13):
            px[15, gun_y] = (255, 250, 180)  # muzzle flash
            px[15, gun_y - 1] = (255, 200, 80)
        for k in range(3):
            if bx + k < W:
                px[bx + k, gun_y] = (255, 230, 90)
    if 7 <= phase <= 10:  # the drone's red laser, passing over the crouching agent
        lx = drone_x - 6 - (phase - 7) * 12
        for k in range(5):
            if 0 <= lx - k < W:
                px[lx - k, 4] = (255, 50, 50)
    hit = frame // 24 * 7 + 1 if 17 <= phase <= 19 else 0
    if phase < 20:
        _drone(px, drone_x, drone_y, frame, hit)
    else:  # a new drone flies in
        _drone(px, drone_x + (24 - phase) * 4, drone_y, frame)
    return image


def render_game(name: str, frame: int = 0, seed: int = 0) -> Image.Image:
    if name == "terminal":
        return render_terminal(frame % terminal_frames(seed), seed)
    return {"chomper": render_chomper, "runner": render_runner, "agent": render_agent}.get(name, render_chomper)(frame)
