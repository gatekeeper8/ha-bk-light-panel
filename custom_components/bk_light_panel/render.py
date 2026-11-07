"""Draw text, colours and pictures into a panel-sized image (Pillow).

Includes a small built-in pixel font (3x5, some letters wider) designed for
32x32 LED panels: up to 8 characters per line and 5 lines at scale 1.
No Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageEnhance

from .const import PANEL_HEIGHT, PANEL_WIDTH

RGB = tuple[int, int, int]

# Each glyph: 5 rows, '#' = lit pixel. Width = length of the row.
_GLYPHS: dict[str, tuple[str, ...]] = {
    " ": ("..", "..", "..", "..", ".."),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "##.", ".##"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    ":": (".", "#", ".", "#", "."),
    ".": (".", ".", ".", ".", "#"),
    ",": (".", ".", ".", "#", "#"),
    "'": ("#", "#", ".", ".", "."),
    "!": ("#", "#", "#", ".", "#"),
    "?": ("##.", "..#", ".#.", "...", ".#."),
    "-": ("...", "...", "###", "...", "..."),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "=": ("...", "###", "...", "###", "..."),
    "_": ("...", "...", "...", "...", "###"),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    "%": ("#.#", "..#", ".#.", "#..", "#.#"),
    "*": ("...", "#.#", ".#.", "#.#", "..."),
    "(": (".#", "#.", "#.", "#.", ".#"),
    ")": ("#.", ".#", ".#", ".#", "#."),
    "<": ("..#", ".#.", "#..", ".#.", "..#"),
    ">": ("#..", ".#.", "..#", ".#.", "#.."),
    "°": (".#.", "#.#", ".#.", "...", "..."),
    "↑": (".#.", "###", "#.#", ".#.", ".#."),
    "↔": (".....", ".#.#.", "#####", ".#.#.", "....."),
}

# Polish (and a few other) letters drawn as their base letter
_FOLD = str.maketrans("ĄĆĘŁŃÓŚŹŻąćęłńóśźżµ", "ACELNOSZZACELNOSZZU")

GLYPH_HEIGHT = 5
CHAR_GAP = 1
LINE_GAP = 1


def _glyph(char: str) -> tuple[str, ...]:
    char = char.translate(_FOLD).upper()
    return _GLYPHS.get(char, _GLYPHS["?"])


def text_width(text: str) -> int:
    """Width in pixels at scale 1."""
    if not text:
        return 0
    return sum(len(_glyph(c)[0]) for c in text) + CHAR_GAP * (len(text) - 1)


def wrap_lines(text: str, max_width: int) -> list[str]:
    """Split on newlines, then wrap words that do not fit."""
    result: list[str] = []
    for raw in text.replace("\\n", "\n").split("\n"):
        words = raw.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if text_width(candidate) <= max_width:
                line = candidate
                continue
            if line:
                result.append(line)
            # a single word wider than the panel is cut character by character
            while text_width(word) > max_width:
                cut = len(word)
                while cut > 1 and text_width(word[:cut]) > max_width:
                    cut -= 1
                result.append(word[:cut])
                word = word[cut:]
            line = word
        result.append(line)
    return result


def _color(value: list[int] | tuple[int, ...] | None, default: RGB) -> RGB:
    if not value:
        return default
    r, g, b = (max(0, min(255, int(v))) for v in list(value)[:3])
    return (r, g, b)


def render_text(
    text: str,
    color: list[int] | None = None,
    background: list[int] | None = None,
    line_colors: list[list[int]] | None = None,
    scale: int = 1,
    size: tuple[int, int] = (PANEL_WIDTH, PANEL_HEIGHT),
) -> Image.Image:
    """Centred multi-line text on a panel-sized image."""
    PANEL_WIDTH, PANEL_HEIGHT = size  # noqa: N806 - local panel size
    scale = max(1, min(4, int(scale)))
    fg = _color(color, (255, 255, 255))
    bg = _color(background, (0, 0, 0))
    image = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), bg)
    pixels = image.load()

    lines = wrap_lines(text, PANEL_WIDTH // scale)
    line_height = (GLYPH_HEIGHT + LINE_GAP) * scale
    max_lines = max(1, (PANEL_HEIGHT + LINE_GAP * scale) // line_height)
    lines = lines[:max_lines]
    block_height = len(lines) * line_height - LINE_GAP * scale
    y0 = (PANEL_HEIGHT - block_height) // 2

    for index, line in enumerate(lines):
        line_fg = fg
        if line_colors and index < len(line_colors):
            line_fg = _color(line_colors[index], fg)
        x = (PANEL_WIDTH - text_width(line) * scale) // 2
        y = y0 + index * line_height
        for char in line:
            rows = _glyph(char)
            for row_index, row in enumerate(rows):
                for col_index, pixel in enumerate(row):
                    if pixel != "#":
                        continue
                    for dy in range(scale):
                        for dx in range(scale):
                            px = x + col_index * scale + dx
                            py = y + row_index * scale + dy
                            if 0 <= px < PANEL_WIDTH and 0 <= py < PANEL_HEIGHT:
                                pixels[px, py] = line_fg
            x += (len(rows[0]) + CHAR_GAP) * scale
    return image


def render_fill(
    color: list[int] | None, size: tuple[int, int] = (PANEL_WIDTH, PANEL_HEIGHT)
) -> Image.Image:
    return Image.new("RGB", size, _color(color, (0, 0, 0)))


def render_file(
    path: str,
    fit: str = "contain",
    background: list[int] | None = None,
    size: tuple[int, int] = (PANEL_WIDTH, PANEL_HEIGHT),
) -> Image.Image:
    """Load a picture and fit it to the panel (blocking: run in executor)."""
    with Image.open(path) as source:
        source = source.convert("RGBA")
        canvas = Image.new("RGBA", size, (*_color(background, (0, 0, 0)), 255))
        if fit == "stretch":
            picture = source.resize(size, Image.Resampling.NEAREST)
            canvas.alpha_composite(picture)
        elif fit == "cover":
            ratio = max(size[0] / source.width, size[1] / source.height)
            scaled = source.resize(
                (max(1, round(source.width * ratio)), max(1, round(source.height * ratio))),
                Image.Resampling.LANCZOS,
            )
            left = (scaled.width - size[0]) // 2
            top = (scaled.height - size[1]) // 2
            canvas.alpha_composite(scaled.crop((left, top, left + size[0], top + size[1])))
        else:  # contain
            source.thumbnail(size, Image.Resampling.LANCZOS)
            canvas.alpha_composite(
                source, ((size[0] - source.width) // 2, (size[1] - source.height) // 2)
            )
        return canvas.convert("RGB")


def to_png(image: Image.Image, brightness: int = 100) -> bytes:
    """Apply brightness (0-100 %) and encode as a compact PNG."""
    image = image.convert("RGB")
    if brightness < 100:
        image = ImageEnhance.Brightness(image).enhance(max(0, brightness) / 100)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ------------------------------------------------------------------ clock
# Large 5x7 digits for the clock face.
_BIG: dict[str, tuple[str, ...]] = {
    "0": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    ":": (".", ".", "#", ".", "#", ".", "."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
}
BAR_COLORS = ((0, 210, 90), (255, 210, 0), (255, 120, 0), (255, 30, 30))


def _scaled(color: RGB, factor: float) -> RGB:
    return tuple(max(0, min(255, round(c * factor))) for c in color)  # type: ignore[return-value]


def _small_line(pixels, text: str, y: int, color: RGB) -> None:
    x = (PANEL_WIDTH - text_width(text)) // 2
    for char in text:
        rows = _glyph(char)
        for ry, row in enumerate(rows):
            for rx, pixel in enumerate(row):
                if pixel == "#" and 0 <= x + rx < PANEL_WIDTH and 0 <= y + ry < PANEL_HEIGHT:
                    pixels[x + rx, y + ry] = color
        x += len(rows[0]) + CHAR_GAP


def render_clock(
    time_text: str,
    time_color: list[int] | None = None,
    line1: str = "",
    line1_color: list[int] | None = None,
    line2: str = "",
    line2_color: list[int] | None = None,
    bar_value: float | None = None,
    bar_max: float = 75.0,
) -> Image.Image:
    """Clock face: big HH:MM, a thin divider, two small lines, a level bar."""
    image = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), (0, 0, 0))
    pixels = image.load()
    tc = _color(time_color, (255, 236, 200))

    glyphs = [_BIG.get(ch, _BIG["-"]) for ch in time_text[:5]]
    width = sum(len(g[0]) for g in glyphs) + len(glyphs) - 1
    x = (PANEL_WIDTH - width) // 2
    for g in glyphs:
        for ry, row in enumerate(g):
            shade = _scaled(tc, 1.0 - ry * 0.045)  # light from above
            for rx, pixel in enumerate(row):
                if pixel == "#":
                    pixels[x + rx, 2 + ry] = shade
        x += len(g[0]) + 1

    # divider fading out to both sides
    for dx in range(-12, 12):
        fade = 1 - abs(dx + 0.5) / 12
        pixels[16 + dx, 11] = _scaled(tc, 0.35 * fade)

    if line1:
        _small_line(pixels, line1, 14, _color(line1_color, (255, 190, 110)))
    if line2:
        _small_line(pixels, line2, 21, _color(line2_color, (200, 200, 200)))

    if bar_value is not None:
        level = max(0.0, min(1.0, bar_value / bar_max if bar_max else 0))
        for i in range(26):
            t = i / 25
            seg = BAR_COLORS[min(3, int(t * 4))]
            on = (i + 0.5) / 26 <= level or (i == 0 and level > 0)
            color = seg if on else _scaled(seg, 0.12)
            pixels[3 + i, 28] = color
            pixels[3 + i, 29] = _scaled(color, 0.6)
    return image


# ------------------------------------------------------------- flip clock
CARD_TOP, CARD_BOTTOM, HINGE = 1, 15, 8
CARDS = ((1, 15), (17, 31))  # x ranges of the hour and minute cards
DIGIT_TOP = 5


def _flip_face(time_text: str, pin_color: RGB) -> Image.Image:
    """Two split-flap cards with the digits, no animation."""
    from .gfx import Canvas  # gfx does not import render, no cycle

    c = Canvas()
    for x0, x1 in CARDS:
        top = c.rrect_mask((x0, CARD_TOP, x1, HINGE), 1.2)
        c.paint(c.vgrad((70, 70, 76), (46, 46, 52), CARD_TOP, HINGE), top)
        bottom = c.rrect_mask((x0, HINGE + 0.25, x1, CARD_BOTTOM), 1.2)
        c.paint(c.vgrad((40, 40, 46), (26, 26, 30), HINGE, CARD_BOTTOM), bottom)
    image = c.finish()
    pixels = image.load()

    digits = (time_text.replace(":", "") + "----")[:4]
    for card, (x0, x1) in enumerate(CARDS):
        pair = digits[card * 2: card * 2 + 2]
        x = x0 + (x1 - x0 - 11) // 2 + 1
        for ch in pair:
            glyph = _BIG.get(ch, _BIG["-"])
            for ry, row in enumerate(glyph):
                y = DIGIT_TOP + ry
                shade = 1.0 if y < HINGE else 0.86
                if y == HINGE:
                    shade = 0.5  # the split runs through the middle
                for rx, pixel in enumerate(row):
                    if pixel == "#":
                        pixels[x + rx, y] = _scaled((245, 238, 222), shade)
            x += 6
        # hinge: dark gap across the card, coloured pins at both ends
        for hx in range(x0, x1):
            if pixels[hx, HINGE][0] < 120:
                pixels[hx, HINGE] = (6, 6, 8)
        pixels[x0, HINGE] = pin_color
        pixels[x1 - 1, HINGE] = pin_color
    return image


def _squash(image: Image.Image, box: tuple[int, int, int, int], height: int) -> Image.Image:
    part = image.crop(box)
    return part.resize((box[2] - box[0], max(1, height)), Image.Resampling.BOX)


def render_flip_clock(
    time_text: str,
    previous: str | None = None,
    step: int = 2,
    time_color: list[int] | None = None,
    line1: str = "",
    line1_color: list[int] | None = None,
    line2: str = "",
    line2_color: list[int] | None = None,
    bar_value: float | None = None,
    bar_max: float = 75.0,
) -> Image.Image:
    """Split-flap clock. step 0 and 1 are the flip in motion, 2 the final face."""
    pin = _color(time_color, (255, 236, 200))
    new = _flip_face(time_text, pin)
    image = new.copy()
    if previous and previous != time_text and step < 2:
        old = _flip_face(previous, pin)
        old_d, new_d = previous.replace(":", ""), time_text.replace(":", "")
        for card, (x0, x1) in enumerate(CARDS):
            if old_d[card * 2: card * 2 + 2] == new_d[card * 2: card * 2 + 2]:
                continue
            # bottom half still shows the old digits
            image.paste(old.crop((x0, HINGE + 1, x1, CARD_BOTTOM)), (x0, HINGE + 1))
            if step == 0:  # old top flap half-way down
                flap = _squash(old, (x0, CARD_TOP, x1, HINGE), (HINGE - CARD_TOP) // 2)
                flap = Image.eval(flap, lambda v: int(v * 0.7))
                image.paste(flap, (x0, HINGE - flap.height))
            else:  # new bottom flap coming down
                flap = _squash(new, (x0, HINGE + 1, x1, CARD_BOTTOM), (CARD_BOTTOM - HINGE - 1) // 2)
                flap = Image.eval(flap, lambda v: int(v * 0.85))
                image.paste(flap, (x0, HINGE + 1))
    pixels = image.load()
    if line1:
        _small_line(pixels, line1, 17, _color(line1_color, (255, 190, 110)))
    if line2:
        _small_line(pixels, line2, 23, _color(line2_color, (200, 200, 200)))
    if bar_value is not None:
        level = max(0.0, min(1.0, bar_value / bar_max if bar_max else 0))
        for i in range(26):
            seg = BAR_COLORS[min(3, int(i / 25 * 4))]
            on = (i + 0.5) / 26 <= level or (i == 0 and level > 0)
            color = seg if on else _scaled(seg, 0.12)
            pixels[3 + i, 30] = color
            pixels[3 + i, 31] = _scaled(color, 0.6)
    return image


def apply_tint(image: Image.Image, tint: list[int] | tuple[int, ...] | None) -> Image.Image:
    """Turn the picture into one colour (e.g. red for night): brightness kept."""
    if not tint:
        return image
    r, g, b = _color(tint, (255, 0, 0))
    gray = image.convert("L")
    return Image.merge("RGB", tuple(gray.point(lambda v, k=k: v * k // 255) for k in (r, g, b)))
