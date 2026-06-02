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
    "light":          _pal("black", "brown", "dgrey", "lgrey", "peach", "white", "orange"),
    "cherry_blossom": _pal("black", "brown", "dpurple", "pink", "peach", "white"),
    "blue":           _pal("lavender", "blue", "lgrey", "white", "orange"),
    "cyberpunk":      _pal("dpurple", "red", "pink", "blue", "yellow", "white"),
    "matrix":         _pal("black", "dgreen", "green", "dgrey", "lgrey", "white", "orange"),
}
_DEFAULT_PALETTE = THEME_PALETTES["dark"]


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


# ── icons (natural colors; recolored per theme at generation time) ──────────
def clipboard(d):          # 911 setup
    d.rectangle([3, 2, 12, 15], fill="#C68A43", outline="#3A2A14")
    d.rectangle([6, 1, 9, 3], fill="#5E3A1C", outline="#3A2A14")
    for y in (6, 9, 12):
        d.line([5, y, 10, y], fill="#F4ECDC")


_REPEAT_GRID = [               # hand-drawn circular arrow (reverse-engineered);
    "................",        # d = arrowhead (dark), m = ring (mid), l = highlight
    "................",
    ".....mmmmmm.....",
    "....mmmmmmmm.d..",
    "...mmm....mddd..",
    "..mmm......ddd..",
    "..mm......dddd..",
    "..mm............",
    "..mm........mm..",
    "..mm........mm..",
    "..mmm......mmm..",
    "...mmm....mmm...",
    "....mmmmmmmm....",
    ".....mmmmmm.....",
    "................",
    "................",
]
_REPEAT_TONES = {"d": "#1E3A8A", "m": "#3B82F6", "l": "#93C5FD"}


def repeat(d):             # 911 batch repeater — a single arrow curving in a circle
    for y, row in enumerate(_REPEAT_GRID):
        for x, ch in enumerate(row):
            if ch in _REPEAT_TONES:
                d.point((x, y), fill=_REPEAT_TONES[ch])


def scissors(d):           # 911 remove ticket
    d.ellipse([2, 10, 5, 13], outline="#E0483C")
    d.ellipse([10, 10, 13, 13], outline="#E0483C")
    d.line([4, 11, 12, 4], fill="#C3CDD5")
    d.line([11, 11, 3, 4], fill="#C3CDD5")
    d.point((7, 8), fill="#5A5A5A")


def invoice(d):            # 911 PO PDF extractor
    d.rectangle([4, 1, 11, 14], fill="#ECEFF1", outline="#37474F")
    for y in (3, 5):
        d.line([6, y, 9, y], fill="#90A4AE")
    d.ellipse([6, 8, 9, 11], fill="#F4B400", outline="#37474F")
    d.point((7, 9), fill="#FFE082")


def picture(d):            # 911 sketch extractor
    d.rectangle([2, 3, 13, 12], fill="#C8923C", outline="#5A4423")
    d.rectangle([3, 4, 12, 11], fill="#2B3A55")
    d.polygon([(4, 11), (7, 7), (10, 11)], fill="#4C9A5A")
    d.ellipse([9, 5, 11, 7], fill="#FBC02D")


def ruler(d):              # 911 linear inch calc
    d.rectangle([1, 5, 14, 10], fill="#E8C15A", outline="#6B4A1A")
    for i, x in enumerate(range(3, 14, 2)):
        d.line([x, 5, x, 7 if i % 2 == 0 else 6], fill="#5A4A1A")


def stamp(d):              # 922 pallet stamper
    d.rectangle([6, 1, 9, 3], fill="#7A4A24", outline="#3A2A18")
    d.rectangle([6, 3, 9, 6], fill="#7A4A24")
    d.rectangle([3, 6, 12, 9], fill="#CF4436", outline="#3A2A18")
    d.line([2, 12, 13, 12], fill="#A12E26")


def magnifier(d):          # 922 form seeker
    d.ellipse([2, 2, 10, 10], fill="#CDEEF0", outline="#2A7D8C")
    d.ellipse([4, 4, 8, 8], outline="#7FCFC4")
    d.line([9, 9, 14, 14], fill="#244E5A", width=2)
    d.line([10, 10, 14, 14], fill="#244E5A", width=2)


def toolbox(d):            # 922 kitting
    d.rectangle([6, 3, 9, 5], outline="#455A64")
    d.rectangle([2, 5, 13, 7], fill="#96281B", outline="#5A1A12")
    d.rectangle([2, 7, 13, 14], fill="#C0392B", outline="#5A1A12")
    d.rectangle([7, 6, 8, 9], fill="#F4B400")


def folders(d):            # 922 LST organizer
    d.rectangle([2, 4, 6, 5], fill="#C8923C")
    d.rectangle([2, 5, 12, 12], fill="#C8923C", outline="#6B4A1A")
    d.rectangle([4, 7, 8, 8], fill="#E8C15A")
    d.rectangle([4, 8, 14, 15], fill="#E8C15A", outline="#6B4A1A")


def stopwatch(d):          # 922 runtime genie
    d.rectangle([7, 0, 8, 2], fill="#2B3A55")
    d.ellipse([3, 3, 13, 13], fill="#F4E9C1", outline="#2B3A55")
    d.line([8, 8, 8, 5], fill="#C0392B")
    d.line([8, 8, 11, 9], fill="#2B3A55")
    d.point((8, 8), fill="#1A2233")


def copy(d):               # 922 batch repeater
    d.rectangle([3, 2, 9, 10], fill="#B0BEC5", outline="#37474F")
    d.rectangle([6, 5, 13, 14], fill="#ECEFF1", outline="#37474F")
    for y in (8, 11):
        d.line([8, y, 11, y], fill="#90A4AE")


def badge(d):              # batch auditor
    d.ellipse([2, 2, 13, 13], fill="#2E9E4F", outline="#1B6E36")
    d.line([5, 8, 7, 11], fill="#FFFFFF")
    d.line([7, 11, 11, 5], fill="#FFFFFF")
    d.line([5, 8, 7, 10], fill="#FFFFFF")


def qr(d):                 # qr code generator
    d.rectangle([2, 2, 13, 13], fill="#ECEFF1")

    def finder(x, y):
        d.rectangle([x, y, x + 3, y + 3], fill="#263238")
        d.rectangle([x + 1, y + 1, x + 2, y + 2], fill="#ECEFF1")
        d.point((x + 1, y + 1), fill="#263238")

    finder(2, 2); finder(10, 2); finder(2, 10)
    for x, y in [(8, 3), (7, 5), (9, 6), (11, 7), (6, 7), (12, 9),
                 (8, 8), (10, 11), (12, 12), (7, 12), (5, 9), (11, 5)]:
        d.point((x, y), fill="#37474F")


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
        for key, fn in ICONS.items():
            im, d = _new()
            fn(d)
            mapping = _build_map(_unique_colors(im), palette)
            _recolor(im, mapping)
            _save(im, tname, key)
    print(f"Generated {len(ICONS)} icons x {len(themes)} theme(s): {', '.join(themes)}")


if __name__ == "__main__":
    main()
