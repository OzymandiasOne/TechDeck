"""
Generate TechDeck's pixel-art tile icons.

For every built-in theme we render the full icon set in a 5-colour palette derived
from that theme's accent — specifically the COMPLEMENTARY hue, so the icons
coordinate with the theme without reusing its exact swatches. Icons are drawn on a
16x16 grid with flat colours and no anti-aliasing, then scaled x4 (NEAREST) to 64px
so the pixels stay crisp.

Output: assets/icons/tile icons/TechDeck pixel/<theme>/<key>.png

Run:  python tools/generate_tile_icons.py
"""

import colorsys
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from techdeck.ui.theme import THEMES  # noqa: E402

OUT_DIR = ROOT / "assets" / "icons" / "tile icons" / "TechDeck pixel"
BASE = 16          # grid size
SCALE = 4          # -> 64px


# ── palette derivation ──────────────────────────────────────────────────────
def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _c(hue, sat, val):
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, max(0, min(1, sat)), max(0, min(1, val)))
    return (int(r * 255), int(g * 255), int(b * 255), 255)


def derive_palette(theme) -> dict:
    """5-colour ramp from the accent's complementary hue + a theme-accent pop."""
    ar, ag, ab = _hex(theme.accent)
    h, s, v = colorsys.rgb_to_hsv(ar / 255, ag / 255, ab / 255)
    ch = (h + 0.5) % 1.0  # complementary hue
    sat = max(0.45, min(0.9, s + 0.15))
    return {
        "OUT":   _c(ch, min(0.9, sat + 0.1), 0.20),   # dark outline
        "DARK":  _c(ch, sat + 0.05, 0.52),            # shadow / deep fill
        "MID":   _c(ch, sat, 0.78),                   # main fill
        "LIGHT": _c(ch, max(0.18, sat - 0.45), 0.95),  # highlight / paper
        "ACC":   _c(h, min(0.95, s + 0.2), min(0.98, v + 0.18)),  # theme-accent pop
    }


# ── drawing helpers ─────────────────────────────────────────────────────────
def _new():
    im = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _save(im, theme, key):
    d = OUT_DIR / theme
    d.mkdir(parents=True, exist_ok=True)
    im.resize((BASE * SCALE, BASE * SCALE), Image.NEAREST).save(d / f"{key}.png")


# ── icons (each: draw on d using palette P) ─────────────────────────────────
def clipboard(d, P):       # 911 setup
    d.rectangle([3, 2, 12, 15], fill=P["MID"], outline=P["OUT"])
    d.rectangle([6, 1, 9, 3], fill=P["DARK"], outline=P["OUT"])
    for y in (6, 9, 12):
        d.line([5, y, 10, y], fill=P["LIGHT"])


def repeat(d, P):          # 911 batch repeater — two arrows looping (find/copy repeats)
    # top arrow body pointing right, bottom arrow body pointing left, joined by
    # short vertical connectors so it reads as a clear "repeat / loop" glyph.
    d.line([4, 5, 11, 5], fill=P["MID"], width=2)              # top bar ->
    d.line([11, 5, 11, 7], fill=P["MID"], width=2)             # right connector
    d.polygon([(13, 5), (10, 2), (10, 8)], fill=P["ACC"])      # right-end head (up/over)
    d.line([5, 11, 12, 11], fill=P["MID"], width=2)            # bottom bar <-
    d.line([5, 9, 5, 11], fill=P["MID"], width=2)              # left connector
    d.polygon([(3, 11), (6, 8), (6, 14)], fill=P["ACC"])       # left-end head


def scissors(d, P):        # 911 remove ticket
    d.ellipse([2, 10, 5, 13], outline=P["MID"])
    d.ellipse([10, 10, 13, 13], outline=P["MID"])
    d.line([4, 11, 12, 4], fill=P["LIGHT"])                    # blade
    d.line([11, 11, 3, 4], fill=P["LIGHT"])                    # blade
    d.point((7, 8), fill=P["ACC"])                             # pivot


def invoice(d, P):         # 911 PO PDF extractor
    d.rectangle([4, 1, 11, 14], fill=P["LIGHT"], outline=P["OUT"])
    for y in (3, 5):
        d.line([6, y, 9, y], fill=P["MID"])
    d.ellipse([6, 8, 9, 11], fill=P["ACC"], outline=P["OUT"])  # coin / value
    d.point((7, 9), fill=P["LIGHT"])


def picture(d, P):         # 911 sketch extractor
    d.rectangle([2, 3, 13, 12], fill=P["LIGHT"], outline=P["OUT"])
    d.rectangle([3, 4, 12, 11], fill=P["DARK"])
    d.polygon([(4, 11), (7, 7), (10, 11)], fill=P["MID"])      # mountain
    d.ellipse([9, 5, 11, 7], fill=P["ACC"])                    # sun


def ruler(d, P):           # 911 linear inch calc
    d.rectangle([1, 5, 14, 10], fill=P["MID"], outline=P["OUT"])
    for i, x in enumerate(range(3, 14, 2)):
        d.line([x, 5, x, 7 if i % 2 == 0 else 6], fill=P["OUT"])


def stamp(d, P):           # 922 pallet stamper
    d.rectangle([6, 1, 9, 3], fill=P["DARK"], outline=P["OUT"])  # knob
    d.rectangle([6, 3, 9, 6], fill=P["MID"])                     # neck
    d.rectangle([3, 6, 12, 9], fill=P["MID"], outline=P["OUT"])  # head
    d.line([2, 12, 13, 12], fill=P["ACC"])                       # impression


def magnifier(d, P):       # 922 form seeker
    d.ellipse([2, 2, 10, 10], fill=P["LIGHT"], outline=P["OUT"])
    d.ellipse([4, 4, 8, 8], outline=P["MID"])
    d.line([9, 9, 14, 14], fill=P["DARK"], width=2)
    d.line([10, 10, 14, 14], fill=P["DARK"], width=2)


def toolbox(d, P):         # 922 kitting
    d.rectangle([6, 3, 9, 5], outline=P["DARK"])                # handle
    d.rectangle([2, 5, 13, 7], fill=P["DARK"], outline=P["OUT"])  # lid
    d.rectangle([2, 7, 13, 14], fill=P["MID"], outline=P["OUT"])  # body
    d.rectangle([7, 6, 8, 9], fill=P["ACC"])                    # latch


def folders(d, P):         # 922 LST organizer
    d.rectangle([2, 4, 6, 5], fill=P["DARK"])                   # back tab
    d.rectangle([2, 5, 12, 12], fill=P["DARK"], outline=P["OUT"])
    d.rectangle([4, 7, 8, 8], fill=P["MID"])                    # front tab
    d.rectangle([4, 8, 14, 15], fill=P["MID"], outline=P["OUT"])


def stopwatch(d, P):       # 922 runtime genie
    d.rectangle([7, 0, 8, 2], fill=P["DARK"])                   # button
    d.ellipse([3, 3, 13, 13], fill=P["LIGHT"], outline=P["OUT"])
    d.line([8, 8, 8, 5], fill=P["ACC"])                         # hand
    d.line([8, 8, 11, 9], fill=P["DARK"])
    d.point((8, 8), fill=P["OUT"])


def copy(d, P):            # 922 batch repeater
    d.rectangle([3, 2, 9, 10], fill=P["DARK"], outline=P["OUT"])  # back page
    d.rectangle([6, 5, 13, 14], fill=P["LIGHT"], outline=P["OUT"])  # front page
    for y in (8, 11):
        d.line([8, y, 11, y], fill=P["MID"])


def badge(d, P):           # batch auditor
    d.ellipse([2, 2, 13, 13], fill=P["ACC"], outline=P["OUT"])
    d.line([5, 8, 7, 11], fill=P["LIGHT"], width=1)
    d.line([7, 11, 11, 5], fill=P["LIGHT"], width=1)
    d.line([5, 8, 7, 10], fill=P["LIGHT"])


def qr(d, P):              # qr code generator
    d.rectangle([2, 2, 13, 13], fill=P["LIGHT"])

    def finder(x, y):
        d.rectangle([x, y, x + 3, y + 3], fill=P["OUT"])
        d.rectangle([x + 1, y + 1, x + 2, y + 2], fill=P["LIGHT"])
        d.point((x + 1, y + 1), fill=P["OUT"])

    finder(2, 2); finder(10, 2); finder(2, 10)
    mods = [(8, 3), (7, 5), (9, 6), (11, 7), (6, 7), (12, 9),
            (8, 8), (10, 11), (12, 12), (7, 12), (5, 9), (11, 5)]
    for x, y in mods:
        d.point((x, y), fill=P["MID"])


ICONS = {
    "clipboard": clipboard, "repeat": repeat, "scissors": scissors,
    "invoice": invoice, "picture": picture, "ruler": ruler, "stamp": stamp,
    "magnifier": magnifier, "toolbox": toolbox, "folders": folders,
    "stopwatch": stopwatch, "copy": copy, "badge": badge, "qr": qr,
}


def main():
    themes = sys.argv[1:] or list(THEMES.keys())
    for tname in themes:
        theme = THEMES[tname]
        P = derive_palette(theme)
        for key, fn in ICONS.items():
            im, d = _new()
            fn(d, P)
            _save(im, tname, key)
    print(f"Generated {len(ICONS)} icons x {len(themes)} themes -> {OUT_DIR}")


if __name__ == "__main__":
    main()
