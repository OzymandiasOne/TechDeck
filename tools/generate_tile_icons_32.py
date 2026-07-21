"""
TechDeck's 32x32 pixel-art tile icons (the live set the app renders).

Each icon is drawn once on a 32x32 grid in its own natural colors, then recolored
per theme into a curated PICO-8 subset. Recoloring is by TONAL ROLE (luminance
rank), not hue: an icon's unique source colors are sorted by value and mapped
monotonically onto the theme palette, so outlines stay darkest and highlights
stay lightest. The palette table + recolor pipeline live in this file (they used
to be shared with a 16x16 generator, generate_tile_icons.py, that has since been
retired — so this script is now fully standalone).

Drawn on a 32x32 grid (flat colors, no AA), scaled x2 (NEAREST) to 64px.
Output: assets/icons/tile icons/TechDeck pixel 32/<theme>/<key>.png

Run:  python tools/generate_tile_icons_32.py [theme ...]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

# ── theme palettes + recolor pipeline ───────────────────────────────────────
# The one master palette every icon is recolored into: the canonical PICO-8 16.
# Per theme we pick a tasteful SUBSET of these (no other colors allowed).
PICO8 = {
    "black": "#000000", "dblue": "#1D2B53", "dpurple": "#7E2553", "dgreen": "#008751",
    "brown": "#AB5236", "dgrey": "#5F574F", "lgrey": "#C2C3C7", "white": "#FFF1E8",
    "red": "#FF004D", "orange": "#FFA300", "yellow": "#FFEC27", "green": "#00E436",
    "blue": "#29ADFF", "lavender": "#83769C", "pink": "#FF77A8", "peach": "#FFCCAA",
}


def _pal(*names):
    return [PICO8[n] for n in names]


# Per-theme subset of the PICO-8 16, chosen to match each theme's mood with
# tasteful tonal/hue variety (not a single-hue wash). Code re-sorts by luminance.
THEME_PALETTES = {
    "dark":           _pal("dgrey", "lavender", "blue", "orange", "lgrey", "white"),
    "light":          _pal("black", "dgrey", "brown", "orange", "lgrey"),
    "cherry_blossom": _pal("black", "brown", "dpurple", "pink", "peach", "white"),
    "blue":           _pal("lavender", "blue", "lgrey", "white", "orange"),
    "cyberpunk":      _pal("dpurple", "red", "pink", "blue", "yellow", "white"),
    "matrix":         _pal("dgreen", "green", "dgrey", "lgrey", "white"),
}
_DEFAULT_PALETTE = THEME_PALETTES["dark"]

# Per-theme 1:1 color substitutions applied AFTER recoloring. matrix: render the
# white highlight tier as a LIGHT green. It must stay distinct from the palette's
# "green" (#00E436) -- mapping it to the same green collapsed the highlight and
# mid tiers into one color, so detailed icons (stopwatch face/hands, badge
# checkmark) blended into a flat green blob.
THEME_SUBSTITUTIONS = {
    "matrix": {"#FFF1E8": "#9BFFB0"},
}

# Per-(theme, icon-key) final-color swaps, applied AFTER recolor + substitution.
# Scoped to ONE icon in ONE theme so it never bleeds into other themes' tiles.
# matrix stopwatch: swap the hands (#00E436) and face (#9BFFB0) colors so the
# hands read as the bright highlight against a green face.
THEME_ICON_SWAPS = {
    ("matrix", "stopwatch"): ("#00E436", "#9BFFB0"),
}


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _build_map(src_colors, palette):
    """Map unique source colors onto the palette by luminance rank (monotonic).

    Darkest source -> darkest palette, lightest -> lightest; strictly increasing
    palette indices where possible so value order (outline<shadow<fill<highlight)
    and part separation are preserved.
    """
    src = sorted(set(src_colors), key=_lum)
    pal = sorted(palette, key=_lum)
    pl = [_lum(c) for c in pal]
    n, m = len(src), len(pal)
    lmin, lmax = _lum(src[0]), _lum(src[-1])
    span = (lmax - lmin) or 1.0
    pmin, pspan = pl[0], (pl[-1] - pl[0]) or 1.0

    mapping = {}
    prev = -1
    for i, c in enumerate(src):
        frac = (_lum(c) - lmin) / span
        target = pmin + frac * pspan
        lo = min(prev + 1, m - 1)                 # keep strictly increasing
        hi = m - 1 - (n - 1 - i)                  # leave room for lighter colors
        hi = max(hi, lo)
        best, bestd = lo, abs(pl[lo] - target)
        for j in range(lo, hi + 1):
            dd = abs(pl[j] - target)
            if dd < bestd:
                best, bestd = j, dd
        mapping[c] = pal[best]
        prev = best
    return mapping


def _unique_colors(im):
    px = im.load()
    seen = set()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a:
                seen.add((r, g, b))
    return seen


def _recolor(im, mapping):
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (*mapping[(r, g, b)], a)
    return im


def _swap_colors(im, hex_a, hex_b):
    """Swap two exact colors in-place (used for per-theme, per-icon tweaks)."""
    ca, cb = _hex(hex_a), _hex(hex_b)
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            if (r, g, b) == ca:
                px[x, y] = (*cb, a)
            elif (r, g, b) == cb:
                px[x, y] = (*ca, a)
    return im


def _draw_grid(d, grid, tones):
    """Paint a char-grid: each non-'.' char -> its TONES hex (one pixel)."""
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                d.point((x, y), fill=tones[ch])


OUT_DIR = ROOT / "assets" / "icons" / "tile icons" / "TechDeck pixel 32"
BASE = 32
SCALE = 2


def _new():
    im = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _save(im, theme, key):
    d = OUT_DIR / theme
    d.mkdir(parents=True, exist_ok=True)
    im.resize((BASE * SCALE, BASE * SCALE), Image.NEAREST).save(d / f"{key}.png")


# ── plugin tile icons (32x32 grids; hand-editable, "." = transparent) ────────
_CLIPBOARD_GRID = [
    "................................",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "......aaaaaaaabbbbaaaaaaaa......",
    "......aaaaaaaabbbbaaaaaaaa......",
    "......aaccccaaaaaaaaccccaa......",
    "......aaccccaaaaaaaaccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccddddddddddddccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaccccccccccccccccaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "................................",
]
_CLIPBOARD_TONES = {"a": "#3A2A14", "b": "#5E3A1C", "c": "#C68A43", "d": "#F4ECDC"}

def clipboard(d):           # 911 setup
    _draw_grid(d, _CLIPBOARD_GRID, _CLIPBOARD_TONES)


_REPEAT_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "........bbbbbbbbbbbbbbbb..aa....",
    "........bbbbbbbbbbbbbbbb..aa....",
    "......bbbbbb........bbaaaaaa....",
    "......bbbbbb........bbaaaaaa....",
    "....bbbbbb............aaaaaa....",
    "....bbbbbb............aaaaaa....",
    "....bbbb............aaaaaaaa....",
    "....bbbb............aaaaaaaa....",
    "....bbbb........................",
    "....bbbb........................",
    "....bbbb........................",
    "....bbbb................bbbb....",
    "....bbbb................bbbb....",
    "....bbbb................bbbb....",
    "....bbbbbb............bbbbbb....",
    "....bbbbbb............bbbbbb....",
    "......bbbbbb........bbbbbb......",
    "......bbbbbb........bbbbbb......",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_REPEAT_TONES = {"a": "#1E3A8A", "b": "#3B82F6"}

def repeat(d):              # 911 batch repeater
    _draw_grid(d, _REPEAT_GRID, _REPEAT_TONES)


_SCISSORS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "......cc................cc......",
    "......cc................cc......",
    "........cc............cc........",
    "........cc............cc........",
    "..........cc........cc..........",
    "..........cc........cc..........",
    "............cc....cc............",
    "............cc....cc............",
    "..............aabb..............",
    "..............aabb..............",
    "............cc....cc............",
    "............cc....cc............",
    "......bbbbcc........ccbbbb......",
    "......bbbbcc........ccbbbb......",
    "....bb..ccbb........bbcc..bb....",
    "....bb..ccbb........bbcc..bb....",
    "....bb....bb........bb....bb....",
    "....bb....bb........bb....bb....",
    "......bbbb............bbbb......",
    "......bbbb............bbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SCISSORS_TONES = {"a": "#5A5A5A", "b": "#E0483C", "c": "#C3CDD5"}

def scissors(d):            # 911 remove ticket
    _draw_grid(d, _SCISSORS_GRID, _SCISSORS_TONES)


_CLAW_GRID = [
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aeeeeeeeeeea..........",
    "..........abbbbbbbbbba..........",
    "..........abbbbbbbbbba..........",
    ".....aaaaaaaaaaaaaaaaaaaaaa.....",
    ".....aaccccccccccccccccccaa.....",
    ".....aaddddddddccddddddddaa.....",
    ".....aaddddddddccddddddddaa.....",
    ".....aaddddddccccccddddddaa.....",
    ".....aadddddddccccdddddddaa.....",
    ".....aadddddccdccdccdddddaa.....",
    ".....aaddddccddccddccddddaa.....",
    ".....aadddddccddddccdddddaa.....",
    ".....aadddddddcddcdddddddaa.....",
    ".....aaddddddddddddddddddaa.....",
    ".....aaddddddddddddddddddaa.....",
    ".....aaddeeedddbbbdddeeedaa.....",
    ".....aadeeeeedbbbbbdeeeeeaa.....",
    ".....aadeeeeedbbbbbdeeeeeaa.....",
    ".....aaddeeedddbbbdddeeedaa.....",
    ".....aaaaaaaaaaaaaaaaaaaaaa.....",
    ".....aabbbbbbbbbbbbbbbbbbaa.....",
    ".....aabbbbbbbbbbbbbbbbbbaa.....",
    ".....aabaddddddabbbaaebbbaa.....",
    ".....aabaddddddabbbbbbbbbaa.....",
    ".....aabaaaaaaaabbbbbbbbbaa.....",
    ".....aaaaaaaaaaaaaaaaaaaaaa.....",
    "......aaa..............aaa......",
    "................................",
    "................................",
]
# a: cabinet frame / outline (darkest)   b: red cabinet body + prizes
# c: claw + rail (metal)   d: glass interior   e: marquee lights + prize highlights
_CLAW_TONES = {"a": "#26303A", "b": "#D23B2E", "c": "#9BA6B0", "d": "#BEE3F0", "e": "#FFD23E"}

def claw(d):                # 911 PO PDF extractor
    _draw_grid(d, _CLAW_GRID, _CLAW_TONES)


_PICTURE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaddaaaabb....",
    "....bbaaaaaaaaaaaaaaddaaaabb....",
    "....bbaaaaaaaaaaaaddddddaabb....",
    "....bbaaaaaaaaaaaaddddddaabb....",
    "....bbaaaaaaaaccaaaaddaaaabb....",
    "....bbaaaaaaaaccaaaaddaaaabb....",
    "....bbaaaaaaccccccaaaaaaaabb....",
    "....bbaaaaaaccccccaaaaaaaabb....",
    "....bbaaaaaaccccccaaaaaaaabb....",
    "....bbaaaaaaccccccaaaaaaaabb....",
    "....bbaaaaccccccccccaaaaaabb....",
    "....bbaaaaccccccccccaaaaaabb....",
    "....bbaaccccccccccccccaaaabb....",
    "....bbaaccccccccccccccaaaabb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_PICTURE_TONES = {"a": "#2B3A55", "b": "#5A4423", "c": "#4C9A5A", "d": "#FBC02D"}

def picture(d):             # 911 sketch extractor
    _draw_grid(d, _PICTURE_GRID, _PICTURE_TONES)


_RULER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "..aaaattaattaattaattaattaattaa..",
    "..aaaattaattaattaattaattaattaa..",
    "..aaaattaaaaaattaaaaaattaaaaaa..",
    "..aaaattaaaaaattaaaaaattaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_RULER_TONES = {"a": "#E6E5E5", "t": "#064678"}

def ruler(d):               # 911 linear inch calc
    _draw_grid(d, _RULER_GRID, _RULER_TONES)


_CALCULATOR_GRID = [
    "................................",
    "................................",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aawwwwwwwwwwwwwwwwaa......",
    "......aawwwwwwwwwwwwwwwwaa......",
    "......aawwwwwwwwwwwwwwwwaa......",
    "......aawwwwwwwwwwwwwwwwaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aabbbbaabbbbaabbbbaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aabbbbaabbbbaaooooaa......",
    "......aabbbbaabbbbaaooooaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "................................",
    "................................",
    "................................",
    "................................",
]
# Dark steel body -> mid casing -> light buttons -> lit display (luminance ramp).
_CALCULATOR_TONES = {"a": "#064678", "w": "#E6E5E5", "b": "#589BD4", "o": "#F08F08"}

def calculator(d):          # sheet_metal_calculators
    _draw_grid(d, _CALCULATOR_GRID, _CALCULATOR_TONES)


_STAMP_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......aaaaaaaa..................",
    "......aaaaaaaa..................",
    "......aaaaaaaa..................",
    "......aaaaaaaa..................",
    "........bbbb....................",
    "........bbbb....................",
    "........bbbb....................",
    "........bbbb....................",
    "....bbbbbbbbbbbb................",
    "....bbbbbbbbbbbb................",
    "..aaaaaaaaaaaaaaaa..............",
    "..aaaaaaaaaaaaaaaa..............",
    "..aaaaaaaaaaaaaaaa..............",
    "..aaaaaaaaaaaaaaaa..............",
    "................................",
    "................................",
    "................rrrrrrrrrrrr....",
    "................rrrrrrrrrrrr....",
    "..............rrrrrrrrrrrrrrrr..",
    "..............rrrrrrrrrrrrrrrr..",
    "..............aaaaaaaaaaaaaaaa..",
    "..............aaaaaaaaaaaaaaaa..",
    "..............aaaaaaaaaaaaaaaa..",
    "..............aaaaaaaaaaaaaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
]
_STAMP_TONES = {"a": "#064678", "b": "#085295", "r": "#E41E2F"}

def stamp(d):               # 922 pallet stamper
    _draw_grid(d, _STAMP_GRID, _STAMP_TONES)


_MAGNIFIER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..............aaaaaaaa..........",
    "..............aaaaaaaa..........",
    "..........aaaaaaaaaaaaaaaa......",
    "..........aaaaaaaaaaaaaaaa......",
    "..........aaaawwwwggggaaaa......",
    "..........aaaawwwwggggaaaa......",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "........aaaaggggggggggggaaaa....",
    "..........aaaaggggggggaaaa......",
    "..........aaaaggggggggaaaa......",
    "..........aaaaaaaaaaaaaaaa......",
    "..........aaaaaaaaaaaaaaaa......",
    "......aaaa....aaaaaaaa..........",
    "......aaaa....aaaaaaaa..........",
    "......aaaa......................",
    "......aaaa......................",
    "..aaaa..........................",
    "..aaaa..........................",
    "..aaaa..........................",
    "..aaaa..........................",
    "................................",
    "................................",
]
_MAGNIFIER_TONES = {"a": "#064678", "g": "#589BD4", "w": "#E6E5E5"}

def magnifier(d):           # 922 forming finder
    _draw_grid(d, _MAGNIFIER_GRID, _MAGNIFIER_TONES)


_TOOLBOX_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........hhhhhhhhhhhh..........",
    "..........hhhhhhhhhhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "....dddddddddddddddddddddddd....",
    "....dddddddddddddddddddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_TOOLBOX_TONES = {"a": "#F08F08", "d": "#064678", "h": "#706D67", "l": "#B7B6B6"}

def toolbox(d):             # 922 kitting
    _draw_grid(d, _TOOLBOX_GRID, _TOOLBOX_TONES)


_FOLDERS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....bbbbbbbbbb..................",
    "....bbbbbbbbbb..................",
    "....aaaaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaa......",
    "....aabbbbbbbbbbbbbbbbbbaa......",
    "....aabbbbbbbbbbbbbbbbbbaa......",
    "....aabbccccccccccbbbbbbaa......",
    "....aabbccccccccccbbbbbbaa......",
    "....aabbaaaaaaaaaaaaaaaaaaaaaa..",
    "....aabbaaaaaaaaaaaaaaaaaaaaaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aabbaaccccccccccccccccccaa..",
    "....aaaaaaccccccccccccccccccaa..",
    "....aaaaaaccccccccccccccccccaa..",
    "........aaccccccccccccccccccaa..",
    "........aaccccccccccccccccccaa..",
    "........aaccccccccccccccccccaa..",
    "........aaccccccccccccccccccaa..",
    "........aaaaaaaaaaaaaaaaaaaaaa..",
    "........aaaaaaaaaaaaaaaaaaaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
]
_FOLDERS_TONES = {"a": "#6B4A1A", "b": "#C8923C", "c": "#E8C15A"}

def folders(d):             # 922 LST organizer
    _draw_grid(d, _FOLDERS_GRID, _FOLDERS_TONES)


_STOPWATCH_GRID = [
    "................................",
    "................................",
    "................................",
    "............bbbbbbbbbb..........",
    "............bbbbbbbbbb..........",
    "........bbbbddddddddddbbbb......",
    "........bbbbddddddddddbbbb......",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddccddddddddbb....",
    "......bbddddddddccddddddddbb....",
    "....bbddddddddddccddddddddddbb..",
    "....bbddddddddddccddddddddddbb..",
    "....bbddddddddddccddddddddddbb..",
    "....bbddddddddddccddddddddddbb..",
    "....bbddddddddddaaccddddddddbb..",
    "....bbddddddddddaaccddddddddbb..",
    "....bbddddddddddddddccccddddbb..",
    "....bbddddddddddddddccccddddbb..",
    "....bbddddddddddddddddddddddbb..",
    "....bbddddddddddddddddddddddbb..",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddddddddddddbb....",
    "........bbbbddddddddddbbbb......",
    "........bbbbddddddddddbbbb......",
    "............bbbbbbbbbb..........",
    "............bbbbbbbbbb..........",
    "................................",
    "................................",
    "................................",
]
_STOPWATCH_TONES = {"a": "#1A2233", "b": "#2B3A55", "c": "#C0392B", "d": "#F4E9C1"}

def stopwatch(d):           # 922 runtime genie (legacy; kept available)
    _draw_grid(d, _STOPWATCH_GRID, _STOPWATCH_TONES)


_LAMP_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "..............cccc..............",
    "..............cccc..............",
    "............cccccccc............",
    "............cccccccc............",
    "..cccc....ccddccccddcccccccc....",
    "..cccc....ccddccccddcccccccc....",
    "..cccccccccccccccccccc....cccc..",
    "..cccccccccccccccccccc....cccc..",
    "......cccccccccccccccc....cccc..",
    "......cccccccccccccccc....cccc..",
    "........dddddddddddddd..cccc....",
    "........dddddddddddddd..cccc....",
    "..............dddd..............",
    "..............dddd..............",
    "......dddddddddddddddddddd......",
    "......dddddddddddddddddddd......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_LAMP_TONES = {"c": "#FCC201", "d": "#F08F08", "w": "#FFEC8E"}

def lamp(d):                # 922 runtime genie (genie/Aladdin lamp)
    _draw_grid(d, _LAMP_GRID, _LAMP_TONES)


_COPY_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "........aaaaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaa..........",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwbbbbbbbbwwww......",
    "........aaaawwbbbbbbbbwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwbbbbbbwwwwww......",
    "........aaaawwbbbbbbwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwwwwwwwwwwwww......",
    "........aaaawwbbbbbbbbwwww......",
    "........aaaawwbbbbbbbbwwww......",
    "............wwwwwwwwwwwwww......",
    "............wwwwwwwwwwwwww......",
    "............wwwwwwwwwwwwww......",
    "............wwwwwwwwwwwwww......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_COPY_TONES = {"a": "#064678", "w": "#E6E5E5", "b": "#F08F08"}

def copy(d):                # 922 batch repeater
    _draw_grid(d, _COPY_GRID, _COPY_TONES)


_BADGE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "........aaaabbbbbbbbaaaa........",
    "........aaaabbbbbbbbaaaa........",
    "......aabbbbbbbbbbbbbbbbaa......",
    "......aabbbbbbbbbbbbbbbbaa......",
    "......aabbbbbbbbbbbbbbccaa......",
    "......aabbbbbbbbbbbbbbccaa......",
    "....aabbbbbbbbbbbbbbccbbbbaa....",
    "....aabbbbbbbbbbbbbbccbbbbaa....",
    "....aabbbbbbbbbbbbbbccbbbbaa....",
    "....aabbbbbbbbbbbbbbccbbbbaa....",
    "....aabbbbccbbbbbbccbbbbbbaa....",
    "....aabbbbccbbbbbbccbbbbbbaa....",
    "....aabbbbbbccbbccbbbbbbbbaa....",
    "....aabbbbbbccbbccbbbbbbbbaa....",
    "......aabbbbccccccbbbbbbaa......",
    "......aabbbbccccccbbbbbbaa......",
    "......aabbbbbbccbbbbbbbbaa......",
    "......aabbbbbbccbbbbbbbbaa......",
    "........aaaabbbbbbbbaaaa........",
    "........aaaabbbbbbbbaaaa........",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "................................",
    "................................",
    "................................",
    "................................",
]
_BADGE_TONES = {"a": "#1B6E36", "b": "#2E9E4F", "c": "#FFFFFF"}

def badge(d):               # batch auditor
    _draw_grid(d, _BADGE_GRID, _BADGE_TONES)


_QR_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaaaaaccccccccaaaaaaaa....",
    "....aaaaaaaaccccccccaaaaaaaa....",
    "....aaaaccaaccccbbccaaaaccaa....",
    "....aaaaccaaccccbbccaaaaccaa....",
    "....aaccccaaccccccccaaccccaa....",
    "....aaccccaaccccccccaaccccaa....",
    "....aaaaaaaaccbbccccaaaaaaaa....",
    "....aaaaaaaaccbbccccaaaaaaaa....",
    "....ccccccccccccbbbbcccccccc....",
    "....ccbbccccccccbbbbcccccccc....",
    "....ccbbccccbbccccccccbbcccc....",
    "....ccccbbccbbccccccccbbcccc....",
    "....ccccbbccbbccbbbbccccbbcc....",
    "....ccccccccbbccbbbbccccbbcc....",
    "....ccccccbbbbccccccbbccbbcc....",
    "....ccccccbbbbccccccbbccbbcc....",
    "....aaaaaaaacccccccccccccccc....",
    "....aaaaaaaacccccccccccccccc....",
    "....aaaaccaaccccccbbbbcccccc....",
    "....aaaaccaaccccccbbbbcccccc....",
    "....aaccccaaccbbccccbbccbbcc....",
    "....aaccccaaccbbccccbbccbbcc....",
    "....aaaaaaaacccccccccccccccc....",
    "....aaaaaaaacccccccccccccccc....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_QR_TONES = {"a": "#263238", "b": "#37474F", "c": "#ECEFF1"}

def qr(d):                  # qr code generator
    _draw_grid(d, _QR_GRID, _QR_TONES)


_SYM_BINOCULARS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaaa....bbbb....aaaaaa....",
    "....aaaaaa....bbbb....aaaaaa....",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbddddbbaaaaaaaaaa..",
    "..aaaaaaaaaabbddddbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbbbaaaaaaaaaa..",
    "..aaccccccaabb....bbaaccccccaa..",
    "..aaccccccaabb....bbaaccccccaa..",
    "..aaccccccaa........aaccccccaa..",
    "..aaccccccaa........aaccccccaa..",
    "..aaccccccaa........aaccccccaa..",
    "..aaccccccaa........aaccccccaa..",
    "....aaaaaa............aaaaaa....",
    "....aaaaaa............aaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_BINOCULARS_TONES = {"a": "#085295", "b": "#706D67", "c": "#589BD4", "d": "#B6B5B5"}

def sym_binoculars(d):      # symbol: binoculars
    _draw_grid(d, _SYM_BINOCULARS_GRID, _SYM_BINOCULARS_TONES)


_SYM_BOOKMARK_GRID = [
    "................................",
    "................................",
    ".........aaaaaaaaaaaaaa.........",
    ".........aaaaaaaaaaaaaa.........",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaa..aaaaaaaa.......",
    ".......aaaaaaaa..aaaaaaaa.......",
    ".......aaaaaa......aaaaaa.......",
    ".......aaaaaa......aaaaaa.......",
    ".......aaaa..........aaaa.......",
    ".......aaaa..........aaaa.......",
    ".......aa..............aa.......",
    ".......aa..............aa.......",
    "................................",
    "................................",
]
_SYM_BOOKMARK_TONES = {"a": "#E41E2F"}

def sym_bookmark(d):        # symbol: bookmark
    _draw_grid(d, _SYM_BOOKMARK_GRID, _SYM_BOOKMARK_TONES)


_SYM_CLOSE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "......aaaa............aaaa......",
    "......aaaa............aaaa......",
    "......aaaaaa........aaaaaa......",
    "......aaaaaa........aaaaaa......",
    "........aaaaaa....aaaaaa........",
    "........aaaaaa....aaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaa....aaaaaa........",
    "........aaaaaa....aaaaaa........",
    "......aaaaaa........aaaaaa......",
    "......aaaaaa........aaaaaa......",
    "......aaaa............aaaa......",
    "......aaaa............aaaa......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_CLOSE_TONES = {"a": "#E41E2F"}

def sym_close(d):           # symbol: close
    _draw_grid(d, _SYM_CLOSE_GRID, _SYM_CLOSE_TONES)


_SYM_CONNECT_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....................aaaaaaaa....",
    "....................aaaaaaaa....",
    "..................aaaaaaaaaaaa..",
    "..................aaaaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "......aaaa........bbaaaaaaaa....",
    "......aaaa........bbaaaaaaaa....",
    "....aaaaaaaa....bb....aaaa......",
    "....aaaaaaaa....bb....aaaa......",
    "..aaaaaaaaaaaabb................",
    "..aaaaaaaaaaaabb................",
    "..aaaaaaaaaaaabb................",
    "..aaaaaaaaaaaabb................",
    "....aaaaaaaa....bb....aaaa......",
    "....aaaaaaaa....bb....aaaa......",
    "......aaaa........bbaaaaaaaa....",
    "......aaaa........bbaaaaaaaa....",
    "....................aaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "..................aaaaaaaaaaaa..",
    "..................aaaaaaaaaaaa..",
    "....................aaaaaaaa....",
    "....................aaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_CONNECT_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_connect(d):         # symbol: connect
    _draw_grid(d, _SYM_CONNECT_GRID, _SYM_CONNECT_TONES)


_SYM_CONTACTS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbccccccaaaacccccc......",
    "......bbbbccccccaaaacccccc......",
    "......bbbbccccaaaaaaaacccc......",
    "......bbbbccccaaaaaaaacccc......",
    "......bbbbccccaaaaaaaacccc......",
    "......bbbbccccaaaaaaaacccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbccaaaaaaaaaaaacc......",
    "......bbbbccaaaaaaaaaaaacc......",
    "......bbbbccaacccccccccccc......",
    "......bbbbccaacccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbbbcccccccccccccccc......",
    "......bbddddddddddddddddcc......",
    "......bbddddddddddddddddcc......",
    "......bbddddddddddddddddcc......",
    "......bbddddddddddddddddcc......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_CONTACTS_TONES = {"a": "#064678", "b": "#B5282E", "c": "#589BD4", "d": "#F8C091"}

def sym_contacts(d):        # symbol: contacts
    _draw_grid(d, _SYM_CONTACTS_GRID, _SYM_CONTACTS_TONES)


_SYM_CURSOR_GRID = [
    "................................",
    "........aa......................",
    "........aa......................",
    "........aaaa....................",
    "........aaaa....................",
    "........aabbaa..................",
    "........aabbaa..................",
    "........aabbbbaa................",
    "........aabbbbaa................",
    "........aabbbbbbaa..............",
    "........aabbbbbbaa..............",
    "........aabbbbbbbbaa............",
    "........aabbbbbbbbaa............",
    "........aabbbbbbbbbbaa..........",
    "........aabbbbbbbbbbaa..........",
    "........aabbbbbbbbbbbbaa........",
    "........aabbbbbbbbbbbbaa........",
    "........aabbbbbbbbaaaaaaaa......",
    "........aabbbbbbbbaaaaaaaa......",
    "........aabbaabbbbaa............",
    "........aabbaabbbbaa............",
    "........aaaa..aabbbbaa..........",
    "........aaaa..aabbbbaa..........",
    "........aa....aabbbbaa..........",
    "........aa....aabbbbaa..........",
    "................aabbbbaa........",
    "................aabbbbaa........",
    "................aabbbbaa........",
    "................aabbbbaa........",
    "..................aaaa..........",
    "..................aaaa..........",
    "................................",
]
_SYM_CURSOR_TONES = {"a": "#706D67", "b": "#E4E3E3"}

def sym_cursor(d):          # symbol: cursor
    _draw_grid(d, _SYM_CURSOR_GRID, _SYM_CURSOR_TONES)


_SYM_DOCUMENT_GRID = [
    "................................",
    "................................",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccccccccccccccbbbbbbcc....",
    "....ccccccccccccccccbbbbbbcc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccccccccccccccbbbbbbcc....",
    "....ccccccccccccccccbbbbbbcc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccbbaaaaaabbcccccccccc....",
    "....ccccbbaaaaaabbcccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccbbaaaaaaaaaaaabbcccc....",
    "....ccccbbaaaaaaaaaaaabbcccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccbbaaaaaabbcccccccccc....",
    "....ccccbbaaaaaabbcccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccbbaaaaaaaaaaaabbcccc....",
    "....ccccbbaaaaaaaaaaaabbcccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "................................",
    "................................",
]
_SYM_DOCUMENT_TONES = {"a": "#716E68", "b": "#B5B4B4", "c": "#E5E4E4"}

def sym_document(d):        # symbol: document
    _draw_grid(d, _SYM_DOCUMENT_GRID, _SYM_DOCUMENT_TONES)


_SYM_DONE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "..........................aaaa..",
    "..........................aaaa..",
    "........................aaaaaa..",
    "........................aaaaaa..",
    "......................aaaaaa....",
    "......................aaaaaa....",
    "....................aaaaaa......",
    "....................aaaaaa......",
    "..aaaa............aaaaaa........",
    "..aaaa............aaaaaa........",
    "..aaaaaa........aaaaaa..........",
    "..aaaaaa........aaaaaa..........",
    "....aaaaaa....aaaaaa............",
    "....aaaaaa....aaaaaa............",
    "......aaaaaaaaaaaa..............",
    "......aaaaaaaaaaaa..............",
    "........aaaaaaaa................",
    "........aaaaaaaa................",
    "..........aaaa..................",
    "..........aaaa..................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_DONE_TONES = {"a": "#00953F"}

def sym_done(d):            # symbol: done
    _draw_grid(d, _SYM_DONE_GRID, _SYM_DONE_TONES)


_SYM_DOWNLOAD_FROM_THE_CLOUD_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..............bbbb..............",
    "..............bbbb..............",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "......bbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbbbb..",
    "....bbbbbbbbbbaaaabbbbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_DOWNLOAD_FROM_THE_CLOUD_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_download_from_the_cloud(d): # symbol: download from the cloud
    _draw_grid(d, _SYM_DOWNLOAD_FROM_THE_CLOUD_GRID, _SYM_DOWNLOAD_FROM_THE_CLOUD_TONES)


_SYM_EDIT_PENCIL_GRID = [
    "..............aaaa..............",
    "..............aaaa..............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..........aacccccccccc..........",
    "..........aacccccccccc..........",
    "..........cccccccccccc..........",
    "..........cccccccccccc..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........bbbbaaaabbbb..........",
    "..........bbbbaaaabbbb..........",
    "............bbbbbbbb............",
    "............bbbbbbbb............",
    "............bbbbbbbb............",
    "............bbbbbbbb............",
    "..............bbbb..............",
    "..............bbbb..............",
    "................................",
    "................................",
]
_SYM_EDIT_PENCIL_TONES = {"a": "#26659F", "b": "#FAC102", "c": "#E4E3E3"}

def sym_edit_pencil(d):     # symbol: edit pencil
    _draw_grid(d, _SYM_EDIT_PENCIL_GRID, _SYM_EDIT_PENCIL_TONES)


_SYM_HAND_CURSOR_GRID = [
    "................................",
    "................................",
    "..........aaaaaa................",
    "..........aaaaaa................",
    "..........aabbaa................",
    "..........aabbaa................",
    "..........aabbaa................",
    "..........aabbaa................",
    "..........aabbaaaaaa............",
    "..........aabbaaaaaa............",
    "..........aabbaabbaaaaaa........",
    "..........aabbaabbaaaaaa........",
    "..........aabbaabbaabbaaaaaa....",
    "..........aabbaabbaabbaaaaaa....",
    "....aaaaaaaabbbbbbbbbbbbbbaa....",
    "....aaaaaaaabbbbbbbbbbbbbbaa....",
    "....aabbbbaabbbbbbbbbbbbbbaa....",
    "....aabbbbaabbbbbbbbbbbbbbaa....",
    "......bbbbbbbbbbbbbbbbbbbbaa....",
    "......bbbbbbbbbbbbbbbbbbbbaa....",
    "......aabbbbbbbbbbbbbbbbbbaa....",
    "......aabbbbbbbbbbbbbbbbbbaa....",
    "........bbbbbbbbbbbbbbbbbbaa....",
    "........bbbbbbbbbbbbbbbbbbaa....",
    "........aabbbbbbbbbbbbbbbbaa....",
    "........aabbbbbbbbbbbbbbbbaa....",
    "........aabbbbbbbbbbbbbbbbaa....",
    "........aabbbbbbbbbbbbbbbbaa....",
    "..........aabbbbbbbbbbbbaa......",
    "..........aabbbbbbbbbbbbaa......",
    "..........aaaaaaaaaaaaaaaa......",
    "..........aaaaaaaaaaaaaaaa......",
]
_SYM_HAND_CURSOR_TONES = {"a": "#726F69", "b": "#E4E3E3"}

def sym_hand_cursor(d):     # symbol: hand cursor
    _draw_grid(d, _SYM_HAND_CURSOR_GRID, _SYM_HAND_CURSOR_TONES)


_SYM_HOME_GRID = [
    "................................",
    "................................",
    "................................",
    "..............aaaa..............",
    "..............aaaa..............",
    "............aaaaaa..cccc........",
    "............aaaaaa..cccc........",
    "..........aaaabbbbaabbcc........",
    "..........aaaabbbbaabbcc........",
    "........aaaabbccccbbaaaa........",
    "........aaaabbccccbbaaaa........",
    "......aaaabbccccccccbbaaaa......",
    "......aaaabbccccccccbbaaaa......",
    "....aaaabbccccccccccccbbaaaa....",
    "....aaaabbccccccccccccbbaaaa....",
    "....aabbccccccccccccccccbbaa....",
    "....aabbccccccccccccccccbbaa....",
    "....cccccccccccccccccccccccc....",
    "....ccccccbbcccccccccccccccc....",
    "....cccccbbbbccccccccccccccc....",
    "....ccccbbbbbbcccccccccccccc....",
    "....ccccbbbbbbccccddddddcccc....",
    "....ccccbbbbbbccccddddddcccc....",
    "....ccccbbbbbbccccddddddcccc....",
    "....ccccbbbbbbccccddddddcccc....",
    "....ccccbbbbbbcccccccccccccc....",
    "....ccccbbbbbbcccccccccccccc....",
    "....ccccbbbbbbcccccccccccccc....",
    "....ccccbbbbbbcccccccccccccc....",
    "................................",
    "................................",
    "................................",
]
_SYM_HOME_TONES = {"a": "#E41E2D", "b": "#F19106", "c": "#FFCB03", "d": "#FFED8E"}

def sym_home(d):            # symbol: home
    _draw_grid(d, _SYM_HOME_GRID, _SYM_HOME_TONES)


_SYM_INFO_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "......aaaaaaaabbbbaaaaaaaa......",
    "......aaaaaaaabbbbaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_INFO_TONES = {"a": "#26659F", "b": "#E6E5E5"}

def sym_info(d):            # symbol: info
    _draw_grid(d, _SYM_INFO_GRID, _SYM_INFO_TONES)


_SYM_LOCK_GRID = [
    "................................",
    "................................",
    "..........cccccccccccc..........",
    "..........cccccccccccc..........",
    "........cccccccccccccccc........",
    "........cccccccccccccccc........",
    "......cccc............cccc......",
    "......cccc............cccc......",
    "......cccc............cccc......",
    "......cccc............cccc......",
    "......ccccbbbbbbbbbbbbcccc......",
    "......ccccbbbbbbbbbbbbcccc......",
    "....bbccccbbbbbbbbbbbbccccbb....",
    "....bbccccbbbbbbbbbbbbccccbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbaaaaaaaabbbbbbbb....",
    "....bbbbbbbbaaaaaaaabbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "................................",
    "................................",
]
_SYM_LOCK_TONES = {"a": "#064678", "b": "#589BD4", "c": "#B6B5B5"}

def sym_lock(d):            # symbol: lock
    _draw_grid(d, _SYM_LOCK_GRID, _SYM_LOCK_TONES)


_SYM_MALE_USER_GRID = [
    "................................",
    "................................",
    "..........aaaaaaaaa.............",
    "..........aaaaaaaaa.............",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaccccccaaaaaaaa....",
    "....aaaaaaaaaaccccccaaaaaaaa....",
    "....aaaaaaaaccccccccccaaaaaa....",
    "....aaaaaaaaccccccccccaaaaaa....",
    "....aaaaccccccccccccccccaaaa....",
    "....aaaaccccccccccccccccaaaa....",
    "....ccccccbbccccccccbbcccccc....",
    "....ccccccbbccccccccbbcccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "......ccccccbbbbbbbbcccccc......",
    "......ccccccbbbbbbbbcccccc......",
    "........cccccccccccccccc........",
    "........cccccccccccccccc........",
    "..........cccccccccccc..........",
    "..........cccccccccccc..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_MALE_USER_TONES = {"a": "#726E68", "b": "#F18F08", "c": "#F9C292"}

def sym_male_user(d):       # symbol: male user
    _draw_grid(d, _SYM_MALE_USER_GRID, _SYM_MALE_USER_TONES)


_SYM_MUSIC_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..............bbbbaa............",
    "..............bbbbaa............",
    "................bbaaaa..........",
    "................bbaaaa..........",
    "................bbaaaaaaaa......",
    "................bbaaaaaaaa......",
    "..............bbbb..aa..aabbaa..",
    "..............bbbb..aa..aabbaa..",
    "..............bbbb..............",
    "..............bbbb..............",
    "........bbbb..bbbb..............",
    "........bbbb..bbbb..............",
    "......bbbbbbbbbbbb..............",
    "......bbbbbbbbbbbb..............",
    "....bbccbbbbbbbb................",
    "....bbccbbbbbbbb................",
    "..bbccccbbbbbbbb................",
    "..bbccccbbbbbbbb................",
    "..bbbbbbbbbbbbbbbb..............",
    "..bbbbbbbbbbbbbbbb..............",
    "....bbbbbbbbbbbb................",
    "....bbbbbbbbbbbb................",
    "......bbbbbbbb..................",
    "......bbbbbbbb..................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_MUSIC_TONES = {"a": "#064678", "b": "#26669F", "c": "#589BD4"}

def sym_music(d):           # symbol: music
    _draw_grid(d, _SYM_MUSIC_GRID, _SYM_MUSIC_TONES)


_SYM_OPENED_FOLDER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaaaaa....................",
    "....aaaaaaaa....................",
    "..aaaaaaaaaaaa..................",
    "..aaaaaaaaaaaa..................",
    "..aaaaaaaaaaaaaaaaaaaaaaaa......",
    "..aaaaaaaaaaaaaaaaaaaaaaaa......",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaa....",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaa....",
    "..aaaaaabbbbbbbbbbbbbbbbbbbb....",
    "..aaaaaabbbbbbbbbbbbbbbbbbbb....",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aaaabbbbbbbbbbbbbbbbbbbbbbbb..",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..aabbbbbbbbbbbbbbbbbbbbbbbb....",
    "..bbbbbbbbbbbbbbbbbbbbbbbb......",
    "..bbbbbbbbbbbbbbbbbbbbbbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_OPENED_FOLDER_TONES = {"a": "#F19006", "b": "#FCC201"}

def sym_opened_folder(d):   # symbol: opened folder
    _draw_grid(d, _SYM_OPENED_FOLDER_GRID, _SYM_OPENED_FOLDER_TONES)


_SYM_PICTURE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..cccccccccccccccccccccccccccc..",
    "..cccccccccccccccccccccccccccc..",
    "..cccccccccccccccccccccccccccc..",
    "..cccccccccccccccccccccccccccc..",
    "..ccccccccccccccccccccccddddcc..",
    "..ccccccccccccccccccccccddddcc..",
    "..ccccccccccccccccccccccddddcc..",
    "..ccccccccccccccccccccccddddcc..",
    "..ccccccccbbcccccccccccccccccc..",
    "..ccccccccbbcccccccccccccccccc..",
    "..ccccccbbbbbbccccccccaacccccc..",
    "..ccccccbbbbbbccccccccaacccccc..",
    "..ccccbbbbbbbbbbccccaaaaaacccc..",
    "..ccccbbbbbbbbbbccccaaaaaacccc..",
    "..ccbbbbbbbbbbbbbbaaaaaaaaaacc..",
    "..ccbbbbbbbbbbbbbbaaaaaaaaaacc..",
    "..bbbbbbbbbbbbbbbbbbaaaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbaaaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_PICTURE_TONES = {"a": "#B4252C", "b": "#EF816E", "c": "#FCC201", "d": "#FFEC8E"}

def sym_picture(d):         # symbol: picture
    _draw_grid(d, _SYM_PICTURE_GRID, _SYM_PICTURE_TONES)


_SYM_PLUS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaabbbbbbbbbbbbaaaaaa....",
    "....aaaaaabbbbbbbbbbbbaaaaaa....",
    "....aaaaaabbbbbbbbbbbbaaaaaa....",
    "....aaaaaabbbbbbbbbbbbaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbbbaaaaaaaaaa....",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_PLUS_TONES = {"a": "#00953F", "b": "#E6E5E5"}

def sym_plus(d):            # symbol: plus
    _draw_grid(d, _SYM_PLUS_GRID, _SYM_PLUS_TONES)


_SYM_PUZZLE_GRID = [
    "................................",
    "................................",
    "..............aaaa..............",
    "..............aaaa..............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..............aaaa..............",
    "..............aaaa..............",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aa....aaaaaaaaaaaaaa......",
    "......aa....aaaaaaaaaaaaaa......",
    "..............aaaaaaaaaaaa......",
    "..............aaaaaaaaaaaa......",
    "..............aaaaaaaaaaaa......",
    "..............aaaaaaaaaaaa......",
    "......aa....aaaaaaaaaaaaaa......",
    "......aa....aaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "................................",
    "................................",
]
_SYM_PUZZLE_TONES = {"a": "#00953F"}

def sym_puzzle(d):          # symbol: puzzle
    _draw_grid(d, _SYM_PUZZLE_GRID, _SYM_PUZZLE_TONES)


_SYM_REFRESH_GRID = [
    "................................",
    "................................",
    "................................",
    ".........aaaaaaaaaaaaa..........",
    ".........aaaaaaaaaaaaa..........",
    ".......aaaaaaaaaaaaaaaaa........",
    ".......aaaaaaaaaaaaaaaaa........",
    ".......aaaaaa.....aaaaaa........",
    ".......aaaaaa.....aaaaaa........",
    ".......aaaa.........aaaa........",
    ".......aaaa.........aaaa........",
    ".......aaaa.....................",
    ".......aaaa.....................",
    "....aaaaaaaaaa........aa........",
    "....aaaaaaaaaa........aa........",
    "......aaaaaa........aaaaaa......",
    "......aaaaaa........aaaaaa......",
    "........aa........aaaaaaaaaa....",
    "........aa........aaaaaaaaaa....",
    ".....................aaaa.......",
    ".....................aaaa.......",
    "........aaaa.........aaaa.......",
    "........aaaa.........aaaa.......",
    "........aaaaaa.....aaaaaa......",
    "........aaaaaa.....aaaaaa.......",
    "........aaaaaaaaaaaaaaaaa.......",
    "........aaaaaaaaaaaaaaaaa.......",
    "..........aaaaaaaaaaaaa.........",
    "..........aaaaaaaaaaaaa.........",
    "................................",
    "................................",
    "................................",
]
_SYM_REFRESH_TONES = {"a": "#085295"}

def sym_refresh(d):         # symbol: refresh
    _draw_grid(d, _SYM_REFRESH_GRID, _SYM_REFRESH_TONES)


_SYM_SETTINGS_GRID = [
    "................................",
    "................................",
    "................................",
    ".............bbbbbb.............",
    ".............bbbbbb.............",
    ".......bbbb..bbbbbb..bbbb.......",
    ".......bbbb..bbbbbb..bbbb.......",
    ".....bbbbbbbbbbbbbbbbbbbbbb.....",
    ".....bbbbbbbbbbbbbbbbbbbbbb.....",
    ".....bbbbbbbbaaaaaabbbbbbbb.....",
    ".....bbbbbbbbaaaaaabbbbbbbb......",
    "......bbbbbaaaaaaaaaabbbbb......",
    "......bbbbbaaaaaaaaaabbbbb......",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "...bbbbbbaaaa......aaaabbbbbb...",
    "......bbbbbaaaaaaaaaabbbbb......",
    "......bbbbbaaaaaaaaaabbbbb......",
    ".....bbbbbbbbaaaaaabbbbbbbb.....",
    ".....bbbbbbbbaaaaaabbbbbbbb.....",
    ".....bbbbbbbbbbbbbbbbbbbbbb.....",
    ".....bbbbbbbbbbbbbbbbbbbbbb.....",
    ".......bbbb..bbbbbb..bbbb.......",
    ".......bbbb..bbbbbb..bbbb.......",
    ".............bbbbbb.............",
    ".............bbbbbb.............",
    "................................",
    "................................",
    "................................",
]
_SYM_SETTINGS_TONES = {"a": "#716E68", "b": "#B6B5B5"}

def sym_settings(d):        # symbol: settings
    _draw_grid(d, _SYM_SETTINGS_GRID, _SYM_SETTINGS_TONES)


_SYM_SHARE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....................aaaaaaaa....",
    "....................aaaaaaaa....",
    "....................aaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "................bbaaaaaaaaaaaa..",
    "................bbaaaaaaaaaaaa..",
    "......aaaa....bbbbbbaaaaaaaa....",
    "......aaaa....bbbbbbaaaaaaaa....",
    "....aaaaaaaabbbb........aa......",
    "....aaaaaaaabbbb........aa......",
    "..aaaaaaaaaa....................",
    "..aaaaaaaaaa....................",
    "..aaaaaaaaaa....................",
    "..aaaaaaaaaa....................",
    "....aaaaaaaabbbb........aa......",
    "....aaaaaaaabbbb........aa......",
    "......aaaa....bbbbbbaaaaaaaa....",
    "......aaaa....bbbbbbaaaaaaaa....",
    "................bbaaaaaaaaaaaa..",
    "................bbaaaaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "....................aaaaaaaaaa..",
    "....................aaaaaaaa....",
    "....................aaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_SHARE_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_share(d):           # symbol: share
    _draw_grid(d, _SYM_SHARE_GRID, _SYM_SHARE_TONES)


_SYM_SPEECH_BUBBLE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaa........",
    "....aaaaaa......................",
    "....aaaaaa......................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_SPEECH_BUBBLE_TONES = {"a": "#589BD4"}

def sym_speech_bubble(d):   # symbol: speech bubble
    _draw_grid(d, _SYM_SPEECH_BUBBLE_GRID, _SYM_SPEECH_BUBBLE_TONES)


_SYM_SUN_GRID = [
    "................................",
    "................................",
    "..............aaaa..............",
    "..............aaaa..............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "......aa..aabbaaaabbaa..aa......",
    "......aa..aabbaaaabbaa..aa......",
    "........aabbbbbbbbbbbbaa........",
    "........aabbbbbbbbbbbbaa........",
    "......aabbbbbbbbbbbbbbbbaa......",
    "......aabbbbbbbbbbbbbbbbaa......",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "..aaaaaabbbbbbbbbbbbbbbbaaaaaa..",
    "..aaaaaabbbbbbbbbbbbbbbbaaaaaa..",
    "..aaaaaabbbbbbbbbbbbbbbbaaaaaa..",
    "..aaaaaabbbbbbbbbbbbbbbbaaaaaa..",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "......aabbbbbbbbbbbbbbbbaa......",
    "......aabbbbbbbbbbbbbbbbaa......",
    "........aabbbbbbbbbbbbaa........",
    "........aabbbbbbbbbbbbaa........",
    "......aa..aabbaaaabbaa..aa......",
    "......aa..aabbaaaabbaa..aa......",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..............aaaa..............",
    "..............aaaa..............",
    "................................",
    "................................",
]
_SYM_SUN_TONES = {"a": "#FCC303", "b": "#FFEC8E"}

def sym_sun(d):             # symbol: sun
    _draw_grid(d, _SYM_SUN_GRID, _SYM_SUN_TONES)


_SYM_TOOLBOX_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........hhhhhhhhhhhh..........",
    "..........hhhhhhhhhhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "..........hhhh....hhhh..........",
    "....dddddddddddddddddddddddd....",
    "....dddddddddddddddddddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....ddddddddddddlllldddddddd....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_TOOLBOX_TONES = {"a": "#F08F08", "d": "#064678", "h": "#706D67", "l": "#B7B6B6"}

def sym_toolbox(d):         # symbol: toolbox
    _draw_grid(d, _SYM_TOOLBOX_GRID, _SYM_TOOLBOX_TONES)


_SYM_TRASH_GRID = [
    "................................",
    "................................",
    ".............bbbbbb.............",
    ".............bbbbbb.............",
    ".....cccccccccccccccccccccc.....",
    ".....cccccccccccccccccccccc.....",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbaabbbbaabbbbaabb.......",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".......bbbbbbbbbbbbbbbbbb.......",
    ".........bbbbbbbbbbbbbb.........",
    ".........bbbbbbbbbbbbbb.........",
    "................................",
    "................................",
]
_SYM_TRASH_TONES = {"a": "#064679", "b": "#2765A0", "c": "#589BD4"}

def sym_trash(d):           # symbol: trash
    _draw_grid(d, _SYM_TRASH_GRID, _SYM_TRASH_TONES)


_SYM_UPLOAD_TO_THE_CLOUD_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..............bbbb..............",
    "..............bbbb..............",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "......bbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbaaaaaaaabbbbbbbbbb..",
    "....bbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbaaaaaaaabbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "..bbbbbbbbbbbbaaaabbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_UPLOAD_TO_THE_CLOUD_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_upload_to_the_cloud(d): # symbol: upload to the cloud
    _draw_grid(d, _SYM_UPLOAD_TO_THE_CLOUD_GRID, _SYM_UPLOAD_TO_THE_CLOUD_TONES)


_SYM_USER_FEMALE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaa..............",
    "..........aaaaaaaa..............",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa.....",
    "....aaaaaaaaaaccccaaaaaaaaaa....",
    "....aaaaaaaaaaccccaaaaaaaaaa....",
    "....aaaaaaaaccccccccaaaaaaaa....",
    "....aaaaaaaaccccccccaaaaaaaa....",
    "....aaaaaaccccccccccccaaaaaa....",
    "....aaaaaaccccccccccccaaaaaa....",
    "..aaaaaaccaaccccccccaaccaaaaaa..",
    "..aaaaaaccaaccccccccaaccaaaaaa..",
    "..aaaaaaccccccccccccccccaaaaaa..",
    "..aaaaaaccccccccccccccccaaaaaa..",
    "..aaaaaaccccccccccccccccaaaaaa..",
    "..aaaaaaccccccccccccccccaaaaaa..",
    "..aaaaaaccccbbbbbbbbccccaaaaaa.",
    "..aaaaaaccccbbbbbbbbccccaaaaaa..",
    "....aaaaccccccccccccccccaaaa....",
    "....aaaaccccccccccccccccaaaa....",
    "......aaaaaaccccccccaaaaaa......",
    "......aaaaaaccccccccaaaaaa......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_USER_FEMALE_TONES = {"a": "#716E68", "b": "#F18F07", "c": "#F8C191"}

def sym_user_female(d):     # symbol: user female
    _draw_grid(d, _SYM_USER_FEMALE_GRID, _SYM_USER_FEMALE_TONES)


_SYM_WRENCH_GRID = [
    "................................",
    "................................",
    "................................",
    "............bb....bb............",
    "............bb....bb............",
    "..........bbbb....bbbb..........",
    "..........bbbb....bbbb..........",
    "........bbbb........bbbb........",
    "........bbbb........bbbb........",
    "........bbbb........bbbb........",
    "........bbbb........bbbb........",
    "........bbbbbb....bbbbbb........",
    "........bbbbbb....bbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    "...........aaaaaaaaaa...........",
    "...........aaaaaaaaaa...........",
    "...........aaaa..aaaa...........",
    "...........aaaa..aaaa...........",
    "...........aaaaaaaaaa...........",
    "...........aaaaaaaaaa...........",
    ".............aaaaaa.............",
    ".............aaaaaa.............",
    "................................",

]
_SYM_WRENCH_TONES = {"a": "#706D67", "b": "#B6B5B5"}

def sym_wrench(d):          # symbol: wrench
    _draw_grid(d, _SYM_WRENCH_GRID, _SYM_WRENCH_TONES)

ICONS = {
    "clipboard": clipboard,
    "repeat": repeat,
    "scissors": scissors,
    "claw": claw,
    "picture": picture,
    "ruler": ruler,
    "calculator": calculator,
    "stamp": stamp,
    "magnifier": magnifier,
    "toolbox": toolbox,
    "folders": folders,
    "stopwatch": stopwatch,
    "lamp": lamp,
    "copy": copy,
    "badge": badge,
    "qr": qr,
}
# Icons8 symbols (themed like the plugin tiles; sym_-prefixed keys).
ICONS.update({
    "sym_binoculars": sym_binoculars,
    "sym_bookmark": sym_bookmark,
    "sym_close": sym_close,
    "sym_connect": sym_connect,
    "sym_contacts": sym_contacts,
    "sym_cursor": sym_cursor,
    "sym_document": sym_document,
    "sym_done": sym_done,
    "sym_download_from_the_cloud": sym_download_from_the_cloud,
    "sym_edit_pencil": sym_edit_pencil,
    "sym_hand_cursor": sym_hand_cursor,
    "sym_home": sym_home,
    "sym_info": sym_info,
    "sym_lock": sym_lock,
    "sym_male_user": sym_male_user,
    "sym_music": sym_music,
    "sym_opened_folder": sym_opened_folder,
    "sym_picture": sym_picture,
    "sym_plus": sym_plus,
    "sym_puzzle": sym_puzzle,
    "sym_refresh": sym_refresh,
    "sym_settings": sym_settings,
    "sym_share": sym_share,
    "sym_speech_bubble": sym_speech_bubble,
    "sym_sun": sym_sun,
    "sym_toolbox": sym_toolbox,
    "sym_trash": sym_trash,
    "sym_upload_to_the_cloud": sym_upload_to_the_cloud,
    "sym_user_female": sym_user_female,
    "sym_wrench": sym_wrench,
})


def main():
    themes = sys.argv[1:] or list(THEME_PALETTES.keys())
    for tname in themes:
        palette = [_hex(h) for h in THEME_PALETTES.get(tname, _DEFAULT_PALETTE)]
        subs = {_hex(a): _hex(b) for a, b in THEME_SUBSTITUTIONS.get(tname, {}).items()}
        for key, fn in ICONS.items():
            im, d = _new()
            fn(d)
            mapping = _build_map(_unique_colors(im), palette)
            if subs:
                mapping = {k: subs.get(v, v) for k, v in mapping.items()}
            _recolor(im, mapping)
            swap = THEME_ICON_SWAPS.get((tname, key))
            if swap:
                _swap_colors(im, *swap)
            _save(im, tname, key)
    print(f"Generated {len(ICONS)} icons x {len(themes)} theme(s): {', '.join(themes)}")


if __name__ == "__main__":
    main()
