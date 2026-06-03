"""
Generate TechDeck's pixel-art tile icons.

Each icon is drawn ONCE in its own natural colors, then recolored per theme into
a curated PICO-8 palette. Recoloring is by TONAL ROLE (value), not hue: an icon's
unique source colors are sorted by luminance and mapped monotonically onto the
theme palette (also sorted by luminance) — darkest source -> darkest palette,
lightest -> lightest. The mapping is strictly increasing where the palette allows,
so borders stay darker than fills and highlights stay lighter than fills, and
distinct parts keep separation. Only the active theme palette's colors are used.

Per-theme palettes are tasteful PICO-8 subsets that mostly match each theme's
mood, with enough tonal/hue variety to avoid a single-hue wash.

Drawn on a 16x16 grid (flat colors, no AA), scaled x4 (NEAREST) to 64px.
Output: assets/icons/tile icons/TechDeck pixel/<theme>/<key>.png

Run:  python tools/generate_tile_icons.py [theme ...]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from techdeck.ui.theme import THEMES  # noqa: E402

OUT_DIR = ROOT / "assets" / "icons" / "tile icons" / "TechDeck pixel"
BASE = 16
SCALE = 4

# The one master palette every icon is recolored into: the canonical PICO-8 16.
# Per theme we just pick a tasteful SUBSET of these (no other colors allowed).
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

# Per-theme 1:1 color substitutions applied AFTER recoloring. Use this to force a
# specific palette color into a tonal role the luminance sort wouldn't pick — it
# swaps one output color for another and leaves everything else untouched.
# matrix: render the white highlight tier as green (the "rest" stays identical).
THEME_SUBSTITUTIONS = {
    "matrix": {"#FFF1E8": "#00E436"},
}


# ── colour helpers ──────────────────────────────────────────────────────────
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


def _new():
    im = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


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


def _save(im, theme, key):
    d = OUT_DIR / theme
    d.mkdir(parents=True, exist_ok=True)
    im.resize((BASE * SCALE, BASE * SCALE), Image.NEAREST).save(d / f"{key}.png")


# ── icons (16x16 pixel grids; one char per pixel, "." = transparent) ─────
# Each icon is a hand-editable grid plus a TONES map (char -> natural-color hex).
# Tweak a pixel by changing its char; the colors are recolored per theme at
# generation time (see _build_map). Tones are listed darkest -> lightest.
def _draw_grid(d, grid, tones):
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                d.point((x, y), fill=tones[ch])


_CLIPBOARD_GRID = [
    "................",
    "......aaaa......",
    "...aaaabbaaaa...",
    "...accaaaacca...",
    "...acccccccca...",
    "...acccccccca...",
    "...acddddddca...",
    "...acccccccca...",
    "...acccccccca...",
    "...acddddddca...",
    "...acccccccca...",
    "...acccccccca...",
    "...acddddddca...",
    "...acccccccca...",
    "...acccccccca...",
    "...aaaaaaaaaa...",
]
_CLIPBOARD_TONES = {"a": "#3A2A14", "b": "#5E3A1C", "c": "#C68A43", "d": "#F4ECDC"}

def clipboard(d):       # 911 setup
    _draw_grid(d, _CLIPBOARD_GRID, _CLIPBOARD_TONES)


_REPEAT_GRID = [
    "................",
    "................",
    ".....bbbbbb.....",
    "....bbbbbbbb.a..",
    "...bbb....baaa..",
    "..bbb......aaa..",
    "..bb......aaaa..",
    "..bb............",
    "..bb........bb..",
    "..bb........bb..",
    "..bbb......bbb..",
    "...bbb....bbb...",
    "....bbbbbbbb....",
    ".....bbbbbb.....",
    "................",
    "................",
]
_REPEAT_TONES = {"a": "#1E3A8A", "b": "#3B82F6"}

def repeat(d):          # 911 batch repeater
    _draw_grid(d, _REPEAT_GRID, _REPEAT_TONES)


_SCISSORS_GRID = [
    "................",
    "................",
    "................",
    "................",
    "...c........c...",
    "....c......c....",
    ".....c....c.....",
    "......c..c......",
    ".......ab.......",
    "......c..c......",
    "...bbc....cbb...",
    "..b.cb....bc.b..",
    "..b..b....b..b..",
    "...bb......bb...",
    "................",
    "................",
]
_SCISSORS_TONES = {"a": "#5A5A5A", "b": "#E0483C", "c": "#C3CDD5"}

def scissors(d):        # 911 remove ticket
    _draw_grid(d, _SCISSORS_GRID, _SCISSORS_TONES)


_INVOICE_GRID = [
    "................",
    "....aaaaaaaa....",
    "....aeeeeeea....",
    "....aebbbbea....",
    "....aeeeeeea....",
    "....aebbbbea....",
    "....aeeeeeea....",
    "....aeeeeeea....",
    "....aeeaaeea....",
    "....aeadcaea....",
    "....aeaccaea....",
    "....aeeaaeea....",
    "....aeeeeeea....",
    "....aeeeeeea....",
    "....aaaaaaaa....",
    "................",
]
_INVOICE_TONES = {"a": "#37474F", "b": "#90A4AE", "c": "#F4B400", "d": "#FFE082", "e": "#ECEFF1"}

def invoice(d):         # 911 PO PDF extractor
    _draw_grid(d, _INVOICE_GRID, _INVOICE_TONES)


_PICTURE_GRID = [
    "................",
    "................",
    "................",
    "..bbbbbbbbbbbb..",
    "..baaaaaaaaaab..",
    "..baaaaaaadaab..",
    "..baaaaaadddab..",
    "..baaaacaadaab..",
    "..baaacccaaaab..",
    "..baaacccaaaab..",
    "..baacccccaaab..",
    "..bacccccccaab..",
    "..bbbbbbbbbbbb..",
    "................",
    "................",
    "................",
]
_PICTURE_TONES = {"a": "#2B3A55", "b": "#5A4423", "c": "#4C9A5A", "d": "#FBC02D"}

def picture(d):         # 911 sketch extractor
    _draw_grid(d, _PICTURE_GRID, _PICTURE_TONES)


_RULER_GRID = [
    "................",
    "................",
    "................",
    "................",
    "................",
    ".bbabababababab.",
    ".bcacacacacacab.",
    ".bcacccacccaccb.",
    ".bccccccccccccb.",
    ".bccccccccccccb.",
    ".bbbbbbbbbbbbbb.",
    "................",
    "................",
    "................",
    "................",
    "................",
]
_RULER_TONES = {"a": "#5A4A1A", "b": "#6B4A1A", "c": "#E8C15A"}

def ruler(d):           # 911 linear inch calc
    _draw_grid(d, _RULER_GRID, _RULER_TONES)


_STAMP_GRID = [
    "................",
    "......aaaa......",
    "......acca......",
    "......cccc......",
    "......cccc......",
    "......cccc......",
    "...aaaaaaaaaa...",
    "...adddddddda...",
    "...adddddddda...",
    "...aaaaaaaaaa...",
    "................",
    "................",
    "..bbbbbbbbbbbb..",
    "................",
    "................",
    "................",
]
_STAMP_TONES = {"a": "#3A2A18", "b": "#A12E26", "c": "#7A4A24", "d": "#CF4436"}

def stamp(d):           # 922 pallet stamper
    _draw_grid(d, _STAMP_GRID, _STAMP_TONES)


_MAGNIFIER_GRID = [
    "................",
    "................",
    ".....bbb........",
    "...bbdddbb......",
    "...bdcccdb......",
    "..bdcdddcdb.....",
    "..bdcdddcdb.....",
    "..bdcdddcdb.....",
    "...bdcccdb......",
    "...bbdddbba.....",
    ".....bbb.aaa....",
    "..........aaa...",
    "...........aaa..",
    "............aaa.",
    ".............aaa",
    "..............a.",
]
_MAGNIFIER_TONES = {"a": "#244E5A", "b": "#2A7D8C", "c": "#7FCFC4", "d": "#CDEEF0"}

def magnifier(d):       # 922 form seeker
    _draw_grid(d, _MAGNIFIER_GRID, _MAGNIFIER_TONES)


_TOOLBOX_GRID = [
    "................",
    "................",
    "................",
    "......cccc......",
    "......c..c......",
    "..aaaaaaaaaaaa..",
    "..abbbbeebbbba..",
    "..aaaaaeeaaaaa..",
    "..addddeedddda..",
    "..addddeedddda..",
    "..adddddddddda..",
    "..adddddddddda..",
    "..adddddddddda..",
    "..adddddddddda..",
    "..aaaaaaaaaaaa..",
    "................",
]
_TOOLBOX_TONES = {"a": "#5A1A12", "b": "#96281B", "c": "#455A64", "d": "#C0392B", "e": "#F4B400"}

def toolbox(d):         # 922 kitting
    _draw_grid(d, _TOOLBOX_GRID, _TOOLBOX_TONES)


_FOLDERS_GRID = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "..aaaaaaaaaaa...",
    "..abbbbbbbbba...",
    "..abcccccbbba...",
    "..abaaaaaaaaaaa.",
    "..abaccccccccca.",
    "..abaccccccccca.",
    "..abaccccccccca.",
    "..aaaccccccccca.",
    "....accccccccca.",
    "....accccccccca.",
    "....aaaaaaaaaaa.",
]
_FOLDERS_TONES = {"a": "#6B4A1A", "b": "#C8923C", "c": "#E8C15A"}

def folders(d):         # 922 LST organizer
    _draw_grid(d, _FOLDERS_GRID, _FOLDERS_TONES)


_STOPWATCH_GRID = [
    ".......bb.......",
    ".......bb.......",
    ".......bb.......",
    "......bbbbb.....",
    ".....bdddddb....",
    "....bdddcdddb...",
    "...bddddcddddb..",
    "...bddddcddddb..",
    "...bddddacdddb..",
    "...bddddddccdb..",
    "...bdddddddddb..",
    "....bdddddddb...",
    ".....bdddddb....",
    "......bbbbb.....",
    "................",
    "................",
]
_STOPWATCH_TONES = {"a": "#1A2233", "b": "#2B3A55", "c": "#C0392B", "d": "#F4E9C1"}

def stopwatch(d):       # 922 runtime genie
    _draw_grid(d, _STOPWATCH_GRID, _STOPWATCH_TONES)


_COPY_GRID = [
    "................",
    "................",
    "...aaaaaaa......",
    "...accccca......",
    "...accccca......",
    "...accaaaaaaaa..",
    "...accadddddda..",
    "...accadddddda..",
    "...accadbbbbda..",
    "...accadddddda..",
    "...aaaadddddda..",
    "......adbbbbda..",
    "......adddddda..",
    "......adddddda..",
    "......aaaaaaaa..",
    "................",
]
_COPY_TONES = {"a": "#37474F", "b": "#90A4AE", "c": "#B0BEC5", "d": "#ECEFF1"}

def copy(d):            # 922 batch repeater
    _draw_grid(d, _COPY_GRID, _COPY_TONES)


_BADGE_GRID = [
    "................",
    "................",
    "......aaaa......",
    "....aabbbbaa....",
    "...abbbbbbbba...",
    "...abbbbbbbca...",
    "..abbbbbbbcbba..",
    "..abbbbbbbcbba..",
    "..abbcbbbcbbba..",
    "..abbbcbcbbbba..",
    "...abbcccbbba...",
    "...abbbcbbbba...",
    "....aabbbbaa....",
    "......aaaa......",
    "................",
    "................",
]
_BADGE_TONES = {"a": "#1B6E36", "b": "#2E9E4F", "c": "#FFFFFF"}

def badge(d):           # batch auditor
    _draw_grid(d, _BADGE_GRID, _BADGE_TONES)


_QR_GRID = [
    "................",
    "................",
    "..aaaaccccaaaa..",
    "..aacaccbcaaca..",
    "..accaccccacca..",
    "..aaaacbccabaa..",
    "..cccccccbcccc..",
    "..ccccbccccbcc..",
    "..ccccccbccccc..",
    "..cccbccccccbc..",
    "..aaaacccccccc..",
    "..aacaccccbccc..",
    "..accacbccccbc..",
    "..aaaacccccccc..",
    "................",
    "................",
]
_QR_TONES = {"a": "#263238", "b": "#37474F", "c": "#ECEFF1"}

def qr(d):              # qr code generator
    _draw_grid(d, _QR_GRID, _QR_TONES)


ICONS = {
    "clipboard": clipboard, "repeat": repeat, "scissors": scissors,
    "invoice": invoice, "picture": picture, "ruler": ruler, "stamp": stamp,
    "magnifier": magnifier, "toolbox": toolbox, "folders": folders,
    "stopwatch": stopwatch, "copy": copy, "badge": badge, "qr": qr,
}



# >>> GENERATED: Icons8 symbols (do not edit between markers) >>>
# Icons8 symbols pack, themed via the same luminance recolor as the plugin
# icons. Snapped to each icon's true palette, then merged to a few tonal
# tiers. Keys are sym_-prefixed so they never collide with plugin tiles.

_SYM_BINOCULARS_GRID = [
    "................",
    "................",
    "................",
    "..aaa..bb..aaa..",
    ".aaaaabbbbaaaaa.",
    ".aaaaabbbbaaaaa.",
    ".aaaaabbbbaaaaa.",
    ".aaaaabddbaaaaa.",
    ".aaaaabbbbaaaaa.",
    ".acccab..baccca.",
    ".accca....accca.",
    ".accca....accca.",
    "..aaa......aaa..",
    "................",
    "................",
    "................",
]
_SYM_BINOCULARS_TONES = {"a": "#085295", "b": "#706D67", "c": "#589BD4", "d": "#B6B5B5"}

def sym_binoculars(d):      # symbol: binoculars
    _draw_grid(d, _SYM_BINOCULARS_GRID, _SYM_BINOCULARS_TONES)


_SYM_BOOKMARK_GRID = [
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaa..aaaa...",
    "....aaa..aaa....",
    "...aa......aa...",
    "...aa......aa...",
    "................",
]
_SYM_BOOKMARK_TONES = {"a": "#E41E2F"}

def sym_bookmark(d):        # symbol: bookmark
    _draw_grid(d, _SYM_BOOKMARK_GRID, _SYM_BOOKMARK_TONES)


_SYM_BOX_GRID = [
    "................",
    "................",
    "...cccccccccc...",
    "..cccccccccccc..",
    "..ccccbbbbcccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccbcbcc..",
    "..cccccccacacc..",
    "..cccccccacacc..",
    "..cccccccccccc..",
    "...cccccccccc...",
    "................",
    "................",
]
_SYM_BOX_TONES = {"a": "#706D67", "b": "#F18F06", "c": "#FCC201"}

def sym_box(d):             # symbol: box
    _draw_grid(d, _SYM_BOX_GRID, _SYM_BOX_TONES)


_SYM_CHECKMARK_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaab...",
    "..aaaaaaaaabba..",
    "..aaaaaaaabbaa..",
    "..aabbaaabbaaa..",
    "..aaabbabbaaaa..",
    "..aaaabbbaaaaa..",
    "..aaaaabaaaaaa..",
    "...aaaaaaaaaa...",
    "....aaaaaaaa....",
    ".....aaaaaa.....",
    "................",
    "................",
]
_SYM_CHECKMARK_TONES = {"a": "#00953F", "b": "#E6E5E5"}

def sym_checkmark(d):       # symbol: checkmark
    _draw_grid(d, _SYM_CHECKMARK_GRID, _SYM_CHECKMARK_TONES)


_SYM_CLOCK_GRID = [
    "................",
    "................",
    "....bbccccbb....",
    "...bccccccccb...",
    "..bccccaaccccb..",
    "..bccccaaccccb..",
    ".bcccccaacccccb.",
    "..cccccaaccccc..",
    "..ccccccaccccc..",
    ".bcccccccaccccb.",
    "..bccccccccccb..",
    "..bccccccccccb..",
    "...bccccccccb...",
    "....bbccccbb....",
    "................",
    "................",
]
_SYM_CLOCK_TONES = {"a": "#726F69", "b": "#5A9CD5", "c": "#E4E4E4"}

def sym_clock(d):           # symbol: clock
    _draw_grid(d, _SYM_CLOCK_GRID, _SYM_CLOCK_TONES)


_SYM_CLOSE_GRID = [
    "................",
    "................",
    "................",
    "...aa......aa...",
    "...aaa....aaa...",
    "....aaa..aaa....",
    ".....aaaaaa.....",
    "......aaaa......",
    "......aaaa......",
    ".....aaaaaa.....",
    "....aaa..aaa....",
    "...aaa....aaa...",
    "...aa......aa...",
    "................",
    "................",
    "................",
]
_SYM_CLOSE_TONES = {"a": "#E41E2F"}

def sym_close(d):           # symbol: close
    _draw_grid(d, _SYM_CLOSE_GRID, _SYM_CLOSE_TONES)


_SYM_CONNECT_GRID = [
    "................",
    "................",
    "..........aaaa..",
    ".........aaaaaa.",
    "..........aaaaa.",
    "...aa....baaaa..",
    "..aaaa..b..aa...",
    ".aaaaaab........",
    ".aaaaaab........",
    "..aaaa..b..aa...",
    "...aa....baaaa..",
    "..........aaaaa.",
    ".........aaaaaa.",
    "..........aaaa..",
    "................",
    "................",
]
_SYM_CONNECT_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_connect(d):         # symbol: connect
    _draw_grid(d, _SYM_CONNECT_GRID, _SYM_CONNECT_TONES)


_SYM_CONTACTS_GRID = [
    "................",
    "................",
    "...bbcccccccc...",
    "...bbcccccccc...",
    "...bbcccaaccc...",
    "...bbccaaaacc...",
    "...bbccaaaacc...",
    "...bbcccccccc...",
    "...bbcccccccc...",
    "...bbcaaaaaac...",
    "...bbcacccccc...",
    "...bbcccccccc...",
    "...bddddddddc...",
    "...bddddddddc...",
    "................",
    "................",
]
_SYM_CONTACTS_TONES = {"a": "#064678", "b": "#B5282E", "c": "#589BD4", "d": "#F8C091"}

def sym_contacts(d):        # symbol: contacts
    _draw_grid(d, _SYM_CONTACTS_GRID, _SYM_CONTACTS_TONES)


_SYM_CURSOR_GRID = [
    "................",
    "....aa..........",
    "....aa..........",
    "....abba........",
    "....abbba.......",
    "....abbbba......",
    "....abbbbba.....",
    "....abbbbbb.....",
    "....abbbbbbaa...",
    "....abbbba..a...",
    "....aaabbb......",
    "....aa.abba.....",
    ".......abbb.....",
    "........abba....",
    ".........ba.....",
    ".........aa.....",
]
_SYM_CURSOR_TONES = {"a": "#706D67", "b": "#E4E3E3"}

def sym_cursor(d):          # symbol: cursor
    _draw_grid(d, _SYM_CURSOR_GRID, _SYM_CURSOR_TONES)


_SYM_DOCUMENT_GRID = [
    "................",
    "...ccccccc......",
    "..ccccccccbb....",
    "...ccccccbbbb...",
    "..ccccccccbbb...",
    "..cccccccccccc..",
    "..ccbaaabccccc..",
    "..cccccccccccc..",
    "..ccbaaaaaabcc..",
    "..cccccccccccc..",
    "..ccbaaabccccc..",
    "..cccccccccccc..",
    "...cbaaaaaabcc..",
    "..cccccccccccc..",
    "...cccccccccc...",
    "................",
]
_SYM_DOCUMENT_TONES = {"a": "#716E68", "b": "#B5B4B4", "c": "#E5E4E4"}

def sym_document(d):        # symbol: document
    _draw_grid(d, _SYM_DOCUMENT_GRID, _SYM_DOCUMENT_TONES)


_SYM_DONE_GRID = [
    "................",
    "................",
    "................",
    ".............aa.",
    "............aaa.",
    "...........aaa..",
    "..........aaa...",
    ".aa......aaa....",
    ".aaa....aaa.....",
    "..aaa..aaa......",
    "...aaaaaa.......",
    "....aaaa........",
    ".....aa.........",
    "................",
    "................",
    "................",
]
_SYM_DONE_TONES = {"a": "#00953F"}

def sym_done(d):            # symbol: done
    _draw_grid(d, _SYM_DONE_GRID, _SYM_DONE_TONES)


_SYM_DOWNLOAD_FROM_THE_CLOUD_GRID = [
    "................",
    "................",
    ".......bb.......",
    ".....bbbbbb.....",
    "....bbbbbbbb....",
    "....bbbbbbbb....",
    "...bbbbaabbbbb..",
    "..bbbbbaabbbbbb.",
    ".bbbbbaaaabbbbb.",
    ".bbbbbaaaabbbbb.",
    ".bbbbbbaabbbbbb.",
    "..bbbbbbbbbbbb..",
    "...bbbbbbbbbb...",
    "................",
    "................",
    "................",
]
_SYM_DOWNLOAD_FROM_THE_CLOUD_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_download_from_the_cloud(d): # symbol: download from the cloud
    _draw_grid(d, _SYM_DOWNLOAD_FROM_THE_CLOUD_GRID, _SYM_DOWNLOAD_FROM_THE_CLOUD_TONES)


_SYM_EDIT_PENCIL_GRID = [
    ".......aa.......",
    "......aaaa......",
    ".....accccc.....",
    "......cccc......",
    ".....aaaaa......",
    ".....aaaaa......",
    ".....aaaaa......",
    ".....aaaaa......",
    ".....aaaaa......",
    ".....aaaaa......",
    "......aaaa......",
    ".....bbaabb.....",
    "......bbbb......",
    "......bbb.......",
    ".......bb.......",
    "................",
]
_SYM_EDIT_PENCIL_TONES = {"a": "#26659F", "b": "#FAC102", "c": "#E4E3E3"}

def sym_edit_pencil(d):     # symbol: edit pencil
    _draw_grid(d, _SYM_EDIT_PENCIL_GRID, _SYM_EDIT_PENCIL_TONES)


_SYM_FOLDER_GRID = [
    "................",
    "................",
    "..aaaaa.........",
    "..aaaaaa........",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbbb.",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbbb.",
    "..bbbbbbbbbbbb..",
    "..bbbbbbbbbbbb..",
    "................",
    "................",
]
_SYM_FOLDER_TONES = {"a": "#F18F06", "b": "#FCC201"}

def sym_folder(d):          # symbol: folder
    _draw_grid(d, _SYM_FOLDER_GRID, _SYM_FOLDER_TONES)


_SYM_HAND_CURSOR_GRID = [
    "................",
    ".....aaa........",
    ".....aba........",
    ".....aba........",
    ".....abaaa......",
    ".....ababaaa....",
    ".....abababaaa..",
    "..aaaabbbbbbba..",
    "..abbabbbbbbba..",
    "...bbbbbbbbbba..",
    "...abbbbbbbbba..",
    "....bbbbbbbbba..",
    "....abbbbbbbba..",
    "....abbbbbbbba..",
    ".....abbbbbba...",
    ".....aaaaaaaa...",
]
_SYM_HAND_CURSOR_TONES = {"a": "#726F69", "b": "#E4E3E3"}

def sym_hand_cursor(d):     # symbol: hand cursor
    _draw_grid(d, _SYM_HAND_CURSOR_GRID, _SYM_HAND_CURSOR_TONES)


_SYM_HOME_GRID = [
    "................",
    ".......aa.......",
    "......aaa.cc....",
    ".....aabbabc....",
    "....aabccbaa....",
    "...aabccccbaa...",
    "..aabccccccbaa..",
    "..abccccccccba..",
    "..cccccccccccc..",
    "...ccbccccdcc...",
    "..ccbbbccdddcc..",
    "...cbbbccddcc...",
    "..cccbbccccccc..",
    "...cbbbcccccc...",
    "................",
    "................",
]
_SYM_HOME_TONES = {"a": "#E41E2D", "b": "#F19106", "c": "#FFCB03", "d": "#FFED8E"}

def sym_home(d):            # symbol: home
    _draw_grid(d, _SYM_HOME_GRID, _SYM_HOME_TONES)


_SYM_INFO_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "..aaaaaaaaaaaa..",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "...aaaabbaaaa...",
    "....aaaaaaaa....",
    ".....aaaaaa.....",
    "................",
    "................",
]
_SYM_INFO_TONES = {"a": "#26659F", "b": "#E6E5E5"}

def sym_info(d):            # symbol: info
    _draw_grid(d, _SYM_INFO_GRID, _SYM_INFO_TONES)


_SYM_LOCK_GRID = [
    "................",
    ".....cccccc.....",
    "....cccccccc....",
    "...cc......cc...",
    "....c......c....",
    "...bcbbbbbbcb...",
    "..bbbbbbbbbbbb..",
    "...bbbbbbbbbb...",
    "..bbbbbaabbbbb..",
    "..bbbbaaaabbbb..",
    "..bbbbbaabbbbb..",
    "...bbbbaabbbb...",
    "..bbbbbaabbbbb..",
    "...bbbbbbbbbb...",
    "....bbbbbbbb....",
    "................",
]
_SYM_LOCK_TONES = {"a": "#064678", "b": "#589BD4", "c": "#B6B5B5"}

def sym_lock(d):            # symbol: lock
    _draw_grid(d, _SYM_LOCK_GRID, _SYM_LOCK_TONES)


_SYM_MALE_USER_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "..aaaaaaccaaaa..",
    "...aaaaccccaa...",
    "..aaacccccccaa..",
    "...cccccccccc...",
    "..cccccccccccc..",
    "...cccccccccc...",
    "...ccccbbccc....",
    "....cccbbccc....",
    ".....cccccc.....",
    "................",
    "................",
]
_SYM_MALE_USER_TONES = {"a": "#726E68", "b": "#F18F08", "c": "#F9C292"}

def sym_male_user(d):       # symbol: male user
    _draw_grid(d, _SYM_MALE_USER_GRID, _SYM_MALE_USER_TONES)


_SYM_MENU_GRID = [
    "................",
    "................",
    "................",
    ".aaaaaaaaaaaaaa.",
    "................",
    "................",
    "................",
    "..aaaaaaaaaaaa..",
    "..aaaaaaaaaaaa..",
    "................",
    "................",
    "................",
    ".aaaaaaaaaaaaaa.",
    "................",
    "................",
    "................",
]
_SYM_MENU_TONES = {"a": "#706D67"}

def sym_menu(d):            # symbol: menu
    _draw_grid(d, _SYM_MENU_GRID, _SYM_MENU_TONES)


_SYM_MUSIC_GRID = [
    "................",
    "................",
    ".......bba......",
    "........baa.....",
    "........baaaa...",
    ".......bb.a.aba.",
    ".......bb.......",
    "....bb.bb.......",
    "...bbbbbb.......",
    "..bcbbbb........",
    ".bccbbbb........",
    ".bbbbbbbb.......",
    "..bbbbbb........",
    "...bbbb.........",
    "................",
    "................",
]
_SYM_MUSIC_TONES = {"a": "#064678", "b": "#26669F", "c": "#589BD4"}

def sym_music(d):           # symbol: music
    _draw_grid(d, _SYM_MUSIC_GRID, _SYM_MUSIC_TONES)


_SYM_OPENED_FOLDER_GRID = [
    "................",
    "................",
    "..aaaa..........",
    ".aaaaaa.........",
    ".aaaaaaaaaaaa...",
    ".aaaaaaaaaaaaa..",
    ".aaabbbbbbbbbb..",
    ".aabbbbbbbbbbbb.",
    ".aabbbbbbbbbbbb.",
    ".aabbbbbbbbbbbb.",
    ".abbbbbbbbbbbb..",
    ".abbbbbbbbbbbb..",
    ".abbbbbbbbbbbb..",
    ".bbbbbbbbbbbb...",
    "................",
    "................",
]
_SYM_OPENED_FOLDER_TONES = {"a": "#F19006", "b": "#FCC201"}

def sym_opened_folder(d):   # symbol: opened folder
    _draw_grid(d, _SYM_OPENED_FOLDER_GRID, _SYM_OPENED_FOLDER_TONES)


_SYM_PICTURE_GRID = [
    "................",
    "................",
    "..cccccccccccc..",
    ".ccccccccccccdc.",
    ".cccccccccccddc.",
    ".cccccccccccccc.",
    ".cccbbbcccccccc.",
    ".ccbbbbbccaaacc.",
    ".ccbbbbbbaaaacc.",
    ".bbbbbbbbaaaaaa.",
    ".bbbbbbbbbbaaaa.",
    ".bbbbbbbbbbaaaa.",
    ".bbbbbbbbbbbbaa.",
    "..b.bbbbbbbb.a..",
    "................",
    "................",
]
_SYM_PICTURE_TONES = {"a": "#B4252C", "b": "#EF816E", "c": "#FCC201", "d": "#FFEC8E"}

def sym_picture(d):         # symbol: picture
    _draw_grid(d, _SYM_PICTURE_GRID, _SYM_PICTURE_TONES)


_SYM_PLUS_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "..aaabbbbbbaaa..",
    "..aaabbbbbbaaa..",
    "..aaaaabbaaaaa..",
    "..aaaaabbaaaaa..",
    "...aaaaaaaaaa...",
    "....aaaaaaaa....",
    ".....aaaaaa.....",
    "................",
    "................",
]
_SYM_PLUS_TONES = {"a": "#00953F", "b": "#E6E5E5"}

def sym_plus(d):            # symbol: plus
    _draw_grid(d, _SYM_PLUS_GRID, _SYM_PLUS_TONES)


_SYM_PUZZLE_GRID = [
    "................",
    ".......aa.......",
    "......aaaa......",
    "......aaaa......",
    ".......aa.......",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "...a..aaaaaaa...",
    ".......aaaaaa...",
    ".......aaaaaa...",
    "...a..aaaaaaa...",
    "...aaaaaaaaaa...",
    "...aaaaaaaaaa...",
    "....aaaaaaaa....",
    "................",
]
_SYM_PUZZLE_TONES = {"a": "#00953F"}

def sym_puzzle(d):          # symbol: puzzle
    _draw_grid(d, _SYM_PUZZLE_GRID, _SYM_PUZZLE_TONES)


_SYM_REFRESH_GRID = [
    "................",
    "................",
    "....aaaaaaaa....",
    "...aaaa..aaaa...",
    "....aa....aaa...",
    "....a...........",
    "..aaaaa.........",
    "..aaaaa...aaa...",
    "...aaa...aaaaa..",
    ".........aaaaa..",
    "...........a....",
    "...aaa....aa....",
    "...aaaa..aaaa...",
    "....aaaaaaaa....",
    "................",
    "................",
]
_SYM_REFRESH_TONES = {"a": "#085295"}

def sym_refresh(d):         # symbol: refresh
    _draw_grid(d, _SYM_REFRESH_GRID, _SYM_REFRESH_TONES)


_SYM_RESTART_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa.a..",
    "...aaa....aaaa..",
    "..aaa......aaa..",
    "..aa......aaaa..",
    "..aa............",
    "..aa........aa..",
    "..aa........aa..",
    "..aaa......aaa..",
    "...aaa....aaa...",
    "....aaaaaaaa....",
    ".....aaaaaa.....",
    "................",
    "................",
]
_SYM_RESTART_TONES = {"a": "#00953F"}

def sym_restart(d):         # symbol: restart
    _draw_grid(d, _SYM_RESTART_GRID, _SYM_RESTART_TONES)


_SYM_SETTINGS_GRID = [
    "................",
    "................",
    "....b..bb..b....",
    "...bbbbbbbbbb...",
    "..bbbbbaabbbbb..",
    "...bbbaaaabbb...",
    "...bbaaaaaabb...",
    ".bbbaa....aabbb.",
    ".bbbaa....aabbb.",
    "...bbaa..aabb...",
    "...bbbaaaabbb...",
    "..bbbbbaabbbbb..",
    "...bbbbbbbbbb...",
    "....b..bb..b....",
    "................",
    "................",
]
_SYM_SETTINGS_TONES = {"a": "#716E68", "b": "#B6B5B5"}

def sym_settings(d):        # symbol: settings
    _draw_grid(d, _SYM_SETTINGS_GRID, _SYM_SETTINGS_TONES)


_SYM_SHARE_GRID = [
    "................",
    "................",
    "..........aaaa..",
    "..........aaaaa.",
    "........baaaaaa.",
    "...aa..bbbaaaa..",
    "..aaaabb....a...",
    ".aaaaa..........",
    ".aaaaa..........",
    "..aaaabb....a...",
    "...aa..bbbaaaa..",
    "........baaaaaa.",
    "..........aaaaa.",
    "..........aaaa..",
    "................",
    "................",
]
_SYM_SHARE_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_share(d):           # symbol: share
    _draw_grid(d, _SYM_SHARE_GRID, _SYM_SHARE_TONES)


_SYM_SPEECH_BUBBLE_GRID = [
    "................",
    "................",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "..aaaaaaaaaaaa..",
    ".aaaaaaaaaaaaaa.",
    ".aaaaaaaaaaaaaa.",
    ".aaaaaaaaaaaaaa.",
    ".aaaaaaaaaaaaaa.",
    ".aaaaaaaaaaaaaa.",
    "..aaaaaaaaaaaa..",
    "...aaaaaaaaaa...",
    "...aaaaaaaaa....",
    "..aaa...........",
    "................",
    "................",
]
_SYM_SPEECH_BUBBLE_TONES = {"a": "#589BD4"}

def sym_speech_bubble(d):   # symbol: speech bubble
    _draw_grid(d, _SYM_SPEECH_BUBBLE_GRID, _SYM_SPEECH_BUBBLE_TONES)


_SYM_SUN_GRID = [
    "................",
    ".......aa.......",
    "......aaaa......",
    "...a.abaaba.a...",
    "....abbbbbba....",
    "...abbbbbbbba...",
    "..abbbbbbbbbba..",
    ".aaabbbbbbbbaaa.",
    ".aaabbbbbbbbaaa.",
    "..abbbbbbbbbba..",
    "...abbbbbbbba...",
    "....abbbbbba....",
    "...a.abaaba.a...",
    "......aaaa......",
    ".......aa.......",
    "................",
]
_SYM_SUN_TONES = {"a": "#FCC303", "b": "#FFEC8E"}

def sym_sun(d):             # symbol: sun
    _draw_grid(d, _SYM_SUN_GRID, _SYM_SUN_TONES)


_SYM_TOOLBOX_GRID = [
    "................",
    "......aaaa......",
    ".....aa..aa.....",
    "...b.bb..bb.b...",
    "..bbbbbbbbbbbb..",
    ".bbbcbbbbbbcbbb.",
    "..ccdcbccbcdcc..",
    "..ccdccccccdcc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    "..cccccccccccc..",
    ".cccccccccccccc.",
    "................",
    "................",
]
_SYM_TOOLBOX_TONES = {"a": "#064678", "b": "#706D67", "c": "#FCC201", "d": "#E6E5E5"}

def sym_toolbox(d):         # symbol: toolbox
    _draw_grid(d, _SYM_TOOLBOX_GRID, _SYM_TOOLBOX_TONES)


_SYM_TRASH_GRID = [
    "................",
    ".......bb.......",
    "...cccccccccc...",
    "...bbbbbbbbbb...",
    "....bbbbbbbb....",
    "...bbabaababb...",
    "...bbabaabab....",
    "...bbabaabab....",
    "...bbabaabab....",
    "...bbabaabab....",
    "...bbabaabab....",
    "....babaabab....",
    "...bbabaababb...",
    "....bbbbbbbb....",
    ".....bbbbbb.....",
    "................",
]
_SYM_TRASH_TONES = {"a": "#064679", "b": "#2765A0", "c": "#589BD4"}

def sym_trash(d):           # symbol: trash
    _draw_grid(d, _SYM_TRASH_GRID, _SYM_TRASH_TONES)


_SYM_UPLOAD_TO_THE_CLOUD_GRID = [
    "................",
    "................",
    ".......bb.......",
    ".....bbbbbb.....",
    "....bbbbbbbb....",
    "....bbbbbbbb....",
    "...bbbbaabbbbb..",
    "..bbbbaaaabbbbb.",
    ".bbbbbaaaabbbbb.",
    ".bbbbbbaabbbbbb.",
    ".bbbbbbaabbbbbb.",
    "..bbbbbbbbbbbb..",
    "...bbbbbbbbbb...",
    "................",
    "................",
    "................",
]
_SYM_UPLOAD_TO_THE_CLOUD_TONES = {"a": "#085295", "b": "#589BD4"}

def sym_upload_to_the_cloud(d): # symbol: upload to the cloud
    _draw_grid(d, _SYM_UPLOAD_TO_THE_CLOUD_GRID, _SYM_UPLOAD_TO_THE_CLOUD_TONES)


_SYM_USER_FEMALE_GRID = [
    "................",
    "................",
    ".....aaaaaa.....",
    "....aaaaaaaa....",
    "...aaaaaaaaaa...",
    "..aaaaaacaaaaa..",
    "...aaaacccaaa...",
    "..aaaacccccaaa..",
    ".aaaacccccccaaa.",
    "..aaccccccccaa..",
    ".aaaaccccccaaaa.",
    "..aaaccbbccaaa..",
    "..aacccbbcccaa..",
    "...aaccccccaa...",
    "................",
    "................",
]
_SYM_USER_FEMALE_TONES = {"a": "#716E68", "b": "#F18F07", "c": "#F8C191"}

def sym_user_female(d):     # symbol: user female
    _draw_grid(d, _SYM_USER_FEMALE_GRID, _SYM_USER_FEMALE_TONES)


_SYM_WRENCH_GRID = [
    "................",
    ".....bb..bb.....",
    "....bb....bb....",
    "...bb......bb...",
    "....bb....bb....",
    "...bbbb..bbbb...",
    "....bbbbbbbb....",
    ".....bbbbbb.....",
    "......bbbb......",
    ".......aa.......",
    ".......aa.......",
    "......aaaa......",
    ".....aaaaaa.....",
    ".....aaaaaa.....",
    "......aaaa......",
    ".......aa.......",
]
_SYM_WRENCH_TONES = {"a": "#706D67", "b": "#B6B5B5"}

def sym_wrench(d):          # symbol: wrench
    _draw_grid(d, _SYM_WRENCH_GRID, _SYM_WRENCH_TONES)

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
# <<< GENERATED: Icons8 symbols <<<


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
