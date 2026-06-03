"""
32x32 variants of the TechDeck plugin pixel icons.

Each icon starts as a 2x doubling of its 16x16 original in generate_tile_icons.py
(every source pixel -> a 2x2 block), so the rendered PNG is identical to the 16x16
set until you hand-refine it. The point is the bigger canvas: edit these grids to
add detail the 16x16 grid can't hold. Same per-theme luminance recolor as the
16x16 set (palettes/helpers are imported from generate_tile_icons.py, so theme
tweaks there flow through here too).

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


# ── icons (32x32 grids; hand-editable, "." = transparent) ────────────────────
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

def clipboard(d):       # 911 setup
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

def repeat(d):          # 911 batch repeater
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

def scissors(d):        # 911 remove ticket
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

def invoice(d):         # 911 PO PDF extractor
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

def picture(d):         # 911 sketch extractor
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

def ruler(d):           # 911 linear inch calc
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

def stamp(d):           # 922 pallet stamper
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

def magnifier(d):       # 922 forming finder
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

def toolbox(d):         # 922 kitting
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

def folders(d):         # 922 LST organizer
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

def stopwatch(d):       # 922 runtime genie
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

def copy(d):            # 922 batch repeater
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

def badge(d):           # batch auditor
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

def qr(d):              # qr code generator
    _draw_grid(d, _QR_GRID, _QR_TONES)

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
