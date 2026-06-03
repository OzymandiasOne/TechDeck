"""
32x32 variants of the TechDeck pixel tile icons.

A 2x mirror of generate_tile_icons.py: every icon (the 14 plugin tiles AND the
36 sym_ symbols) is its 16x16 original doubled into 2x2 blocks, so each rendered
PNG is identical to the 16x16 set until you hand-refine it. The point is the
bigger canvas: edit these grids to add detail the 16x16 grid can't hold. Same
per-theme luminance recolor as the 16x16 set (palettes/helpers are imported from
generate_tile_icons.py, so theme tweaks there flow through here too).

Drawn on a 32x32 grid (flat colors, no AA), scaled x2 (NEAREST) to 64px.
Output: assets/icons/tile icons/TechDeck pixel 32/<theme>/<key>.png

Run:  python tools/generate_tile_icons_32.py [theme ...]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# Reuse the palette table + recolor pipeline from the 16x16 generator (these are
# resolution-independent), so the two sets stay perfectly in sync on theming.
from generate_tile_icons import (  # noqa: E402
    THEME_PALETTES, THEME_SUBSTITUTIONS, _DEFAULT_PALETTE,
    _hex, _build_map, _unique_colors, _recolor, _draw_grid,
)

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
    "....bbbb................bbbb....",
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


_INVOICE_GRID = [
    "................................",
    "................................",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeebbbbbbbbeeaa........",
    "........aaeebbbbbbbbeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeebbbbbbbbeeaa........",
    "........aaeebbbbbbbbeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeaaaaeeeeaa........",
    "........aaeeeeaaaaeeeeaa........",
    "........aaeeaaddccaaeeaa........",
    "........aaeeaaddccaaeeaa........",
    "........aaeeaaccccaaeeaa........",
    "........aaeeaaccccaaeeaa........",
    "........aaeeeeaaaaeeeeaa........",
    "........aaeeeeaaaaeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaeeeeeeeeeeeeaa........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "................................",
    "................................",
]
_INVOICE_TONES = {"a": "#37474F", "b": "#90A4AE", "c": "#F4B400", "d": "#FFE082", "e": "#ECEFF1"}

def invoice(d):             # 911 PO PDF extractor
    _draw_grid(d, _INVOICE_GRID, _INVOICE_TONES)


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
    "..bbbbaabbaabbaabbaabbaabbaabb..",
    "..bbbbaabbaabbaabbaabbaabbaabb..",
    "..bbccaaccaaccaaccaaccaaccaabb..",
    "..bbccaaccaaccaaccaaccaaccaabb..",
    "..bbccaaccccccaaccccccaaccccbb..",
    "..bbccaaccccccaaccccccaaccccbb..",
    "..bbccccccccccccccccccccccccbb..",
    "..bbccccccccccccccccccccccccbb..",
    "..bbccccccccccccccccccccccccbb..",
    "..bbccccccccccccccccccccccccbb..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbbbbb..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbbbbb..",
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
_RULER_TONES = {"a": "#5A4A1A", "b": "#6B4A1A", "c": "#E8C15A"}

def ruler(d):               # 911 linear inch calc
    _draw_grid(d, _RULER_GRID, _RULER_TONES)


_STAMP_GRID = [
    "................................",
    "................................",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "............aaccccaa............",
    "............aaccccaa............",
    "............cccccccc............",
    "............cccccccc............",
    "............cccccccc............",
    "............cccccccc............",
    "............cccccccc............",
    "............cccccccc............",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaddddddddddddddddaa......",
    "......aaddddddddddddddddaa......",
    "......aaddddddddddddddddaa......",
    "......aaddddddddddddddddaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "................................",
    "................................",
    "................................",
    "................................",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_STAMP_TONES = {"a": "#3A2A18", "b": "#A12E26", "c": "#7A4A24", "d": "#CF4436"}

def stamp(d):               # 922 pallet stamper
    _draw_grid(d, _STAMP_GRID, _STAMP_TONES)


_MAGNIFIER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........bbbbbb................",
    "..........bbbbbb................",
    "......bbbbddddddbbbb............",
    "......bbbbddddddbbbb............",
    "......bbddccccccddbb............",
    "......bbddccccccddbb............",
    "....bbddccddddddccddbb..........",
    "....bbddccddddddccddbb..........",
    "....bbddccddddddccddbb..........",
    "....bbddccddddddccddbb..........",
    "....bbddccddddddccddbb..........",
    "....bbddccddddddccddbb..........",
    "......bbddccccccddbb............",
    "......bbddccccccddbb............",
    "......bbbbddddddbbbbaa..........",
    "......bbbbddddddbbbbaa..........",
    "..........bbbbbb..aaaaaa........",
    "..........bbbbbb..aaaaaa........",
    "....................aaaaaa......",
    "....................aaaaaa......",
    "......................aaaaaa....",
    "......................aaaaaa....",
    "........................aaaaaa..",
    "........................aaaaaa..",
    "..........................aaaaaa",
    "..........................aaaaaa",
    "............................aa..",
    "............................aa..",
]
_MAGNIFIER_TONES = {"a": "#244E5A", "b": "#2A7D8C", "c": "#7FCFC4", "d": "#CDEEF0"}

def magnifier(d):           # 922 forming finder
    _draw_grid(d, _MAGNIFIER_GRID, _MAGNIFIER_TONES)


_TOOLBOX_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "............cccccccc............",
    "............cccccccc............",
    "............cc....cc............",
    "............cc....cc............",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aabbbbbbbbeeeebbbbbbbbaa....",
    "....aabbbbbbbbeeeebbbbbbbbaa....",
    "....aaaaaaaaaaeeeeaaaaaaaaaa....",
    "....aaaaaaaaaaeeeeaaaaaaaaaa....",
    "....aaddddddddeeeeddddddddaa....",
    "....aaddddddddeeeeddddddddaa....",
    "....aaddddddddeeeeddddddddaa....",
    "....aaddddddddeeeeddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaddddddddddddddddddddaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
]
_TOOLBOX_TONES = {"a": "#5A1A12", "b": "#96281B", "c": "#455A64", "d": "#C0392B", "e": "#F4B400"}

def toolbox(d):             # 922 kitting
    _draw_grid(d, _TOOLBOX_GRID, _TOOLBOX_TONES)


_FOLDERS_GRID = [
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
]
_FOLDERS_TONES = {"a": "#6B4A1A", "b": "#C8923C", "c": "#E8C15A"}

def folders(d):             # 922 LST organizer
    _draw_grid(d, _FOLDERS_GRID, _FOLDERS_TONES)


_STOPWATCH_GRID = [
    "..............bbbb..............",
    "..............bbbb..............",
    "..............bbbb..............",
    "..............bbbb..............",
    "..............bbbb..............",
    "..............bbbb..............",
    "............bbbbbbbbbb..........",
    "............bbbbbbbbbb..........",
    "..........bbddddddddddbb........",
    "..........bbddddddddddbb........",
    "........bbddddddccddddddbb......",
    "........bbddddddccddddddbb......",
    "......bbddddddddccddddddddbb....",
    "......bbddddddddccddddddddbb....",
    "......bbddddddddccddddddddbb....",
    "......bbddddddddccddddddddbb....",
    "......bbddddddddaaccddddddbb....",
    "......bbddddddddaaccddddddbb....",
    "......bbddddddddddddccccddbb....",
    "......bbddddddddddddccccddbb....",
    "......bbddddddddddddddddddbb....",
    "......bbddddddddddddddddddbb....",
    "........bbddddddddddddddbb......",
    "........bbddddddddddddddbb......",
    "..........bbddddddddddbb........",
    "..........bbddddddddddbb........",
    "............bbbbbbbbbb..........",
    "............bbbbbbbbbb..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_STOPWATCH_TONES = {"a": "#1A2233", "b": "#2B3A55", "c": "#C0392B", "d": "#F4E9C1"}

def stopwatch(d):           # 922 runtime genie
    _draw_grid(d, _STOPWATCH_GRID, _STOPWATCH_TONES)


_COPY_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......aaaaaaaaaaaaaa............",
    "......aaaaaaaaaaaaaa............",
    "......aaccccccccccaa............",
    "......aaccccccccccaa............",
    "......aaccccccccccaa............",
    "......aaccccccccccaa............",
    "......aaccccaaaaaaaaaaaaaaaa....",
    "......aaccccaaaaaaaaaaaaaaaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaccccaaddbbbbbbbbddaa....",
    "......aaccccaaddbbbbbbbbddaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaccccaaddddddddddddaa....",
    "......aaaaaaaaddddddddddddaa....",
    "......aaaaaaaaddddddddddddaa....",
    "............aaddbbbbbbbbddaa....",
    "............aaddbbbbbbbbddaa....",
    "............aaddddddddddddaa....",
    "............aaddddddddddddaa....",
    "............aaddddddddddddaa....",
    "............aaddddddddddddaa....",
    "............aaaaaaaaaaaaaaaa....",
    "............aaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
]
_COPY_TONES = {"a": "#37474F", "b": "#90A4AE", "c": "#B0BEC5", "d": "#ECEFF1"}

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
    "....aaaaaaaaccbbccccaabbaaaa....",
    "....aaaaaaaaccbbccccaabbaaaa....",
    "....ccccccccccccccbbcccccccc....",
    "....ccccccccccccccbbcccccccc....",
    "....ccccccccbbccccccccbbcccc....",
    "....ccccccccbbccccccccbbcccc....",
    "....ccccccccccccbbcccccccccc....",
    "....ccccccccccccbbcccccccccc....",
    "....ccccccbbccccccccccccbbcc....",
    "....ccccccbbccccccccccccbbcc....",
    "....aaaaaaaacccccccccccccccc....",
    "....aaaaaaaacccccccccccccccc....",
    "....aaaaccaaccccccccbbcccccc....",
    "....aaaaccaaccccccccbbcccccc....",
    "....aaccccaaccbbccccccccbbcc....",
    "....aaccccaaccbbccccccccbbcc....",
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
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaa....aaaaaaaa......",
    "......aaaaaaaa....aaaaaaaa......",
    "........aaaaaa....aaaaaa........",
    "........aaaaaa....aaaaaa........",
    "......aaaa............aaaa......",
    "......aaaa............aaaa......",
    "......aaaa............aaaa......",
    "......aaaa............aaaa......",
    "................................",
    "................................",
]
_SYM_BOOKMARK_TONES = {"a": "#E41E2F"}

def sym_bookmark(d):        # symbol: bookmark
    _draw_grid(d, _SYM_BOOKMARK_GRID, _SYM_BOOKMARK_TONES)


_SYM_BOX_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccccccbbbbbbbbcccccccc....",
    "....ccccccccbbbbbbbbcccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....ccccccccccccccbbccbbcccc....",
    "....ccccccccccccccbbccbbcccc....",
    "....ccccccccccccccaaccaacccc....",
    "....ccccccccccccccaaccaacccc....",
    "....ccccccccccccccaaccaacccc....",
    "....ccccccccccccccaaccaacccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_BOX_TONES = {"a": "#706D67", "b": "#F18F06", "c": "#FCC201"}

def sym_box(d):             # symbol: box
    _draw_grid(d, _SYM_BOX_GRID, _SYM_BOX_TONES)


_SYM_CHECKMARK_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaabb......",
    "......aaaaaaaaaaaaaaaaaabb......",
    "....aaaaaaaaaaaaaaaaaabbbbaa....",
    "....aaaaaaaaaaaaaaaaaabbbbaa....",
    "....aaaaaaaaaaaaaaaabbbbaaaa....",
    "....aaaaaaaaaaaaaaaabbbbaaaa....",
    "....aaaabbbbaaaaaabbbbaaaaaa....",
    "....aaaabbbbaaaaaabbbbaaaaaa....",
    "....aaaaaabbbbaabbbbaaaaaaaa....",
    "....aaaaaabbbbaabbbbaaaaaaaa....",
    "....aaaaaaaabbbbbbaaaaaaaaaa....",
    "....aaaaaaaabbbbbbaaaaaaaaaa....",
    "....aaaaaaaaaabbaaaaaaaaaaaa....",
    "....aaaaaaaaaabbaaaaaaaaaaaa....",
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
_SYM_CHECKMARK_TONES = {"a": "#00953F", "b": "#E6E5E5"}

def sym_checkmark(d):       # symbol: checkmark
    _draw_grid(d, _SYM_CHECKMARK_GRID, _SYM_CHECKMARK_TONES)


_SYM_CLOCK_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "........bbbbccccccccbbbb........",
    "........bbbbccccccccbbbb........",
    "......bbccccccccccccccccbb......",
    "......bbccccccccccccccccbb......",
    "....bbccccccccaaaaccccccccbb....",
    "....bbccccccccaaaaccccccccbb....",
    "....bbccccccccaaaaccccccccbb....",
    "....bbccccccccaaaaccccccccbb....",
    "..bbccccccccccaaaaccccccccccbb..",
    "..bbccccccccccaaaaccccccccccbb..",
    "....ccccccccccaaaacccccccccc....",
    "....ccccccccccaaaacccccccccc....",
    "....ccccccccccccaacccccccccc....",
    "....ccccccccccccaacccccccccc....",
    "..bbccccccccccccccaaccccccccbb..",
    "..bbccccccccccccccaaccccccccbb..",
    "....bbccccccccccccccccccccbb....",
    "....bbccccccccccccccccccccbb....",
    "....bbccccccccccccccccccccbb....",
    "....bbccccccccccccccccccccbb....",
    "......bbccccccccccccccccbb......",
    "......bbccccccccccccccccbb......",
    "........bbbbccccccccbbbb........",
    "........bbbbccccccccbbbb........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_CLOCK_TONES = {"a": "#726F69", "b": "#5A9CD5", "c": "#E4E4E4"}

def sym_clock(d):           # symbol: clock
    _draw_grid(d, _SYM_CLOCK_GRID, _SYM_CLOCK_TONES)


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
    "................................",
    "........aaaa....................",
    "........aaaa....................",
    "........aaaa....................",
    "........aaaa....................",
    "........aabbbbaa................",
    "........aabbbbaa................",
    "........aabbbbbbaa..............",
    "........aabbbbbbaa..............",
    "........aabbbbbbbbaa............",
    "........aabbbbbbbbaa............",
    "........aabbbbbbbbbbaa..........",
    "........aabbbbbbbbbbaa..........",
    "........aabbbbbbbbbbbb..........",
    "........aabbbbbbbbbbbb..........",
    "........aabbbbbbbbbbbbaaaa......",
    "........aabbbbbbbbbbbbaaaa......",
    "........aabbbbbbbbaa....aa......",
    "........aabbbbbbbbaa....aa......",
    "........aaaaaabbbbbb............",
    "........aaaaaabbbbbb............",
    "........aaaa..aabbbbaa..........",
    "........aaaa..aabbbbaa..........",
    "..............aabbbbbb..........",
    "..............aabbbbbb..........",
    "................aabbbbaa........",
    "................aabbbbaa........",
    "..................bbaa..........",
    "..................bbaa..........",
    "..................aaaa..........",
    "..................aaaa..........",
]
_SYM_CURSOR_TONES = {"a": "#706D67", "b": "#E4E3E3"}

def sym_cursor(d):          # symbol: cursor
    _draw_grid(d, _SYM_CURSOR_GRID, _SYM_CURSOR_TONES)


_SYM_DOCUMENT_GRID = [
    "................................",
    "................................",
    "......cccccccccccccc............",
    "......cccccccccccccc............",
    "....ccccccccccccccccbbbb........",
    "....ccccccccccccccccbbbb........",
    "......ccccccccccccbbbbbbbb......",
    "......ccccccccccccbbbbbbbb......",
    "....ccccccccccccccccbbbbbb......",
    "....ccccccccccccccccbbbbbb......",
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
    "......ccbbaaaaaaaaaaaabbcccc....",
    "......ccbbaaaaaaaaaaaabbcccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
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
    "............cccccccc............",
    "............cccccccc............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "..........aaaaaaaaaa............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..........bbbbaaaabbbb..........",
    "..........bbbbaaaabbbb..........",
    "............bbbbbbbb............",
    "............bbbbbbbb............",
    "............bbbbbb..............",
    "............bbbbbb..............",
    "..............bbbb..............",
    "..............bbbb..............",
    "................................",
    "................................",
]
_SYM_EDIT_PENCIL_TONES = {"a": "#26659F", "b": "#FAC102", "c": "#E4E3E3"}

def sym_edit_pencil(d):     # symbol: edit pencil
    _draw_grid(d, _SYM_EDIT_PENCIL_GRID, _SYM_EDIT_PENCIL_TONES)


_SYM_FOLDER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaaaaaaa..................",
    "....aaaaaaaaaa..................",
    "....aaaaaaaaaaaa................",
    "....aaaaaaaaaaaa................",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbbbb..",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_FOLDER_TONES = {"a": "#F18F06", "b": "#FCC201"}

def sym_folder(d):          # symbol: folder
    _draw_grid(d, _SYM_FOLDER_GRID, _SYM_FOLDER_TONES)


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
    "....cccccccccccccccccccccccc....",
    "......ccccbbccccccccddcccc......",
    "......ccccbbccccccccddcccc......",
    "....ccccbbbbbbccccddddddcccc....",
    "....ccccbbbbbbccccddddddcccc....",
    "......ccbbbbbbccccddddcccc......",
    "......ccbbbbbbccccddddcccc......",
    "....ccccccbbbbcccccccccccccc....",
    "....ccccccbbbbcccccccccccccc....",
    "......ccbbbbbbcccccccccccc......",
    "......ccbbbbbbcccccccccccc......",
    "................................",
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
    "........cc............cc........",
    "........cc............cc........",
    "......bbccbbbbbbbbbbbbccbb......",
    "......bbccbbbbbbbbbbbbccbb......",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbaaaaaaaabbbbbbbb....",
    "....bbbbbbbbaaaaaaaabbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbbbaaaabbbbbbbb......",
    "......bbbbbbbbaaaabbbbbbbb......",
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
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaccccaaaaaaaa....",
    "....aaaaaaaaaaaaccccaaaaaaaa....",
    "......aaaaaaaaccccccccaaaa......",
    "......aaaaaaaaccccccccaaaa......",
    "....aaaaaaccccccccccccccaaaa....",
    "....aaaaaaccccccccccccccaaaa....",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "......ccccccccbbbbcccccc........",
    "......ccccccccbbbbcccccc........",
    "........ccccccbbbbcccccc........",
    "........ccccccbbbbcccccc........",
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


_SYM_MENU_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
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
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_MENU_TONES = {"a": "#706D67"}

def sym_menu(d):            # symbol: menu
    _draw_grid(d, _SYM_MENU_GRID, _SYM_MENU_TONES)


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
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "..ccccccccccccccccccccccccddcc..",
    "..ccccccccccccccccccccccccddcc..",
    "..ccccccccccccccccccccccddddcc..",
    "..ccccccccccccccccccccccddddcc..",
    "..cccccccccccccccccccccccccccc..",
    "..cccccccccccccccccccccccccccc..",
    "..ccccccbbbbbbcccccccccccccccc..",
    "..ccccccbbbbbbcccccccccccccccc..",
    "..ccccbbbbbbbbbbccccaaaaaacccc..",
    "..ccccbbbbbbbbbbccccaaaaaacccc..",
    "..ccccbbbbbbbbbbbbaaaaaaaacccc..",
    "..ccccbbbbbbbbbbbbaaaaaaaacccc..",
    "..bbbbbbbbbbbbbbbbaaaaaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbaaaaaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbaaaaaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbaaaa..",
    "..bbbbbbbbbbbbbbbbbbbbbbbbaaaa..",
    "....bb..bbbbbbbbbbbbbbbb..aa....",
    "....bb..bbbbbbbbbbbbbbbb..aa....",
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
    "................................",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaa....aaaaaaaa......",
    "......aaaaaaaa....aaaaaaaa......",
    "........aaaa........aaaaaa......",
    "........aaaa........aaaaaa......",
    "........aa......................",
    "........aa......................",
    "....aaaaaaaaaa..................",
    "....aaaaaaaaaa..................",
    "....aaaaaaaaaa......aaaaaa......",
    "....aaaaaaaaaa......aaaaaa......",
    "......aaaaaa......aaaaaaaaaa....",
    "......aaaaaa......aaaaaaaaaa....",
    "..................aaaaaaaaaa....",
    "..................aaaaaaaaaa....",
    "......................aa........",
    "......................aa........",
    "......aaaaaa........aaaa........",
    "......aaaaaa........aaaa........",
    "......aaaaaaaa....aaaaaaaa......",
    "......aaaaaaaa....aaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_REFRESH_TONES = {"a": "#085295"}

def sym_refresh(d):         # symbol: refresh
    _draw_grid(d, _SYM_REFRESH_GRID, _SYM_REFRESH_TONES)


_SYM_RESTART_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa..aa....",
    "........aaaaaaaaaaaaaaaa..aa....",
    "......aaaaaa........aaaaaaaa....",
    "......aaaaaa........aaaaaaaa....",
    "....aaaaaa............aaaaaa....",
    "....aaaaaa............aaaaaa....",
    "....aaaa............aaaaaaaa....",
    "....aaaa............aaaaaaaa....",
    "....aaaa........................",
    "....aaaa........................",
    "....aaaa................aaaa....",
    "....aaaa................aaaa....",
    "....aaaa................aaaa....",
    "....aaaa................aaaa....",
    "....aaaaaa............aaaaaa....",
    "....aaaaaa............aaaaaa....",
    "......aaaaaa........aaaaaa......",
    "......aaaaaa........aaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_RESTART_TONES = {"a": "#00953F"}

def sym_restart(d):         # symbol: restart
    _draw_grid(d, _SYM_RESTART_GRID, _SYM_RESTART_TONES)


_SYM_SETTINGS_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "........bb....bbbb....bb........",
    "........bb....bbbb....bb........",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbaaaaaaaabbbbbb......",
    "......bbbbbbaaaaaaaabbbbbb......",
    "......bbbbaaaaaaaaaaaabbbb......",
    "......bbbbaaaaaaaaaaaabbbb......",
    "..bbbbbbaaaa........aaaabbbbbb..",
    "..bbbbbbaaaa........aaaabbbbbb..",
    "..bbbbbbaaaa........aaaabbbbbb..",
    "..bbbbbbaaaa........aaaabbbbbb..",
    "......bbbbaaaa....aaaabbbb......",
    "......bbbbaaaa....aaaabbbb......",
    "......bbbbbbaaaaaaaabbbbbb......",
    "......bbbbbbaaaaaaaabbbbbb......",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "....bbbbbbbbbbaaaabbbbbbbbbb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "........bb....bbbb....bb........",
    "........bb....bbbb....bb........",
    "................................",
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
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..........aaaa....aaaa..........",
    "..........aaaa....aaaa..........",
    "......bb..bbbb....bbbb..bb......",
    "......bb..bbbb....bbbb..bb......",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "....bbbbbbbbbbbbbbbbbbbbbbbb....",
    "..bbbbbbccbbbbbbbbbbbbccbbbbbb..",
    "..bbbbbbccbbbbbbbbbbbbccbbbbbb..",
    "....ccccddccbbccccbbccddcccc....",
    "....ccccddccbbccccbbccddcccc....",
    "....ccccddccccccccccccddcccc....",
    "....ccccddccccccccccccddcccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "....cccccccccccccccccccccccc....",
    "..cccccccccccccccccccccccccccc..",
    "..cccccccccccccccccccccccccccc..",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SYM_TOOLBOX_TONES = {"a": "#064678", "b": "#706D67", "c": "#FCC201", "d": "#E6E5E5"}

def sym_toolbox(d):         # symbol: toolbox
    _draw_grid(d, _SYM_TOOLBOX_GRID, _SYM_TOOLBOX_TONES)


_SYM_TRASH_GRID = [
    "................................",
    "................................",
    "..............bbbb..............",
    "..............bbbb..............",
    "......cccccccccccccccccccc......",
    "......cccccccccccccccccccc......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "......bbbbaabbaaaabbaabbbb......",
    "......bbbbaabbaaaabbaabbbb......",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabb........",
    "........bbaabbaaaabbaabb........",
    "........bbaabbaaaabbaabb........",
    "......bbbbaabbaaaabbaabbbb......",
    "......bbbbaabbaaaabbaabbbb......",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
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
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaccaaaaaaaaaa....",
    "....aaaaaaaaaaaaccaaaaaaaaaa....",
    "......aaaaaaaaccccccaaaaaa......",
    "......aaaaaaaaccccccaaaaaa......",
    "....aaaaaaaaccccccccccaaaaaa....",
    "....aaaaaaaaccccccccccaaaaaa....",
    "..aaaaaaaaccccccccccccccaaaaaa..",
    "..aaaaaaaaccccccccccccccaaaaaa..",
    "....aaaaccccccccccccccccaaaa....",
    "....aaaaccccccccccccccccaaaa....",
    "..aaaaaaaaccccccccccccaaaaaaaa..",
    "..aaaaaaaaccccccccccccaaaaaaaa..",
    "....aaaaaaccccbbbbccccaaaaaa....",
    "....aaaaaaccccbbbbccccaaaaaa....",
    "....aaaaccccccbbbbccccccaaaa....",
    "....aaaaccccccbbbbccccccaaaa....",
    "......aaaaccccccccccccaaaa......",
    "......aaaaccccccccccccaaaa......",
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
    "..........bbbb....bbbb..........",
    "..........bbbb....bbbb..........",
    "........bbbb........bbbb........",
    "........bbbb........bbbb........",
    "......bbbb............bbbb......",
    "......bbbb............bbbb......",
    "........bbbb........bbbb........",
    "........bbbb........bbbb........",
    "......bbbbbbbb....bbbbbbbb......",
    "......bbbbbbbb....bbbbbbbb......",
    "........bbbbbbbbbbbbbbbb........",
    "........bbbbbbbbbbbbbbbb........",
    "..........bbbbbbbbbbbb..........",
    "..........bbbbbbbbbbbb..........",
    "............bbbbbbbb............",
    "............bbbbbbbb............",
    "..............aaaa..............",
    "..............aaaa..............",
    "..............aaaa..............",
    "..............aaaa..............",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "............aaaaaaaa............",
    "............aaaaaaaa............",
    "..............aaaa..............",
    "..............aaaa..............",
]
_SYM_WRENCH_TONES = {"a": "#706D67", "b": "#B6B5B5"}

def sym_wrench(d):          # symbol: wrench
    _draw_grid(d, _SYM_WRENCH_GRID, _SYM_WRENCH_TONES)

ICONS = {
    "clipboard": clipboard,
    "repeat": repeat,
    "scissors": scissors,
    "invoice": invoice,
    "picture": picture,
    "ruler": ruler,
    "stamp": stamp,
    "magnifier": magnifier,
    "toolbox": toolbox,
    "folders": folders,
    "stopwatch": stopwatch,
    "copy": copy,
    "badge": badge,
    "qr": qr,
}
# Icons8 symbols (themed like the plugin tiles; sym_-prefixed keys).
ICONS.update({
    "sym_binoculars": sym_binoculars,
    "sym_bookmark": sym_bookmark,
    "sym_box": sym_box,
    "sym_checkmark": sym_checkmark,
    "sym_clock": sym_clock,
    "sym_close": sym_close,
    "sym_connect": sym_connect,
    "sym_contacts": sym_contacts,
    "sym_cursor": sym_cursor,
    "sym_document": sym_document,
    "sym_done": sym_done,
    "sym_download_from_the_cloud": sym_download_from_the_cloud,
    "sym_edit_pencil": sym_edit_pencil,
    "sym_folder": sym_folder,
    "sym_hand_cursor": sym_hand_cursor,
    "sym_home": sym_home,
    "sym_info": sym_info,
    "sym_lock": sym_lock,
    "sym_male_user": sym_male_user,
    "sym_menu": sym_menu,
    "sym_music": sym_music,
    "sym_opened_folder": sym_opened_folder,
    "sym_picture": sym_picture,
    "sym_plus": sym_plus,
    "sym_puzzle": sym_puzzle,
    "sym_refresh": sym_refresh,
    "sym_restart": sym_restart,
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
            _save(im, tname, key)
    print(f"Generated {len(ICONS)} icons x {len(themes)} theme(s): {', '.join(themes)}")


if __name__ == "__main__":
    main()
