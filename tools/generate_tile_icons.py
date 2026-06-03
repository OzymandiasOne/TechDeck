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
    "......cccc......",
    ".......ac.......",
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
    "..bbbbb.........",
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
    "...bddddabdddb..",
    "...bddddddbbdb..",
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
