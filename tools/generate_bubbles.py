"""
Generate the Emporium "word-bubble" panels as editable 9-slice .tdart sprites.
=============================================================================

These replace the old procedural _panel() drawing in emporium_page.py: the
dialogue box, the WOOGY'S EMPORIUM banner, the ticket-balance chip, and the
store-item tile card. Each is a small square sprite that EmporiumPage renders
with pixel_art.render_nine_slice() — corners stay crisp, the middle stretches —
so the panels render at the SAME sizes as before but can now be repainted in the
pixel editor:

    python tools/pixel_editor.py assets/sprites/bubble_dialogue.tdart

Editing notes: keep the sprite square-ish and small. The renderer keeps the
outer (dim-1)//2 cells of every side un-stretched (corners + border + bevel) and
stretches the 1-2px centre, so leave the dead-centre row/column as plain fill /
straight border.

Run:  python tools/generate_bubbles.py [--preview]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from techdeck.ui import pixel_art

OUT = Path(__file__).resolve().parents[1] / "assets" / "sprites"


def _round_prof(r):
    """Pixel-art quarter-circle corner: inset (px) for each of the top r rows."""
    c = r - 0.5
    prof = []
    for y in range(r):
        ins = r
        for x in range(r):
            if (c - x) ** 2 + (c - y) ** 2 <= r * r:
                ins = x
                break
        prof.append(ins)
    return prof


def _blank(w, h):
    return [["." for _ in range(w)] for _ in range(h)]


def _rfill(g, x, y, w, h, prof, ch):
    """Fill a rounded-corner rect of chars (matches pixel_art._round_fill)."""
    if w <= 0 or h <= 0:
        return
    H, W = len(g), len(g[0])
    n = len(prof)
    for row in range(h):
        if row < n:
            ins = prof[row]
        elif row >= h - n:
            ins = prof[h - 1 - row]
        else:
            ins = 0
        for cx in range(x + ins, x + w - ins):
            yy = y + row
            if 0 <= yy < H and 0 <= cx < W:
                g[yy][cx] = ch


def _rect(g, x, y, w, h, ch):
    H, W = len(g), len(g[0])
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= yy < H and 0 <= xx < W:
                g[yy][xx] = ch


def _bubble(radius, thickness, palette, *, fill, border,
            outline="k", hi=None, lo=None):
    """Author one bubble sprite. Mirrors EmporiumPage._panel's old layering, so
    the 9-slice output matches the previous procedural panels pixel-for-pixel.
    The keys reference single-char palette entries."""
    m = radius + 2                      # un-stretched margin per side
    dim = 2 * m + 1                     # odd -> a clean 1px centre strip
    g = _blank(dim, dim)
    prof = _round_prof(radius)
    w = h = dim
    ox = 0
    if outline is not None:
        _rfill(g, 0, 0, w, h, prof, outline)
        ox = 1
    _rfill(g, ox, ox, w - 2 * ox, h - 2 * ox,
           [max(0, v - ox) for v in prof], border)
    t = ox + thickness
    _rfill(g, t, t, w - 2 * t, h - 2 * t,
           [max(0, v - t) for v in prof], fill)
    bw = max(1, thickness - 1)
    if hi is not None:
        _rect(g, radius, ox, w - 2 * radius, bw, hi)        # top
        _rect(g, ox, radius, bw, h - 2 * radius, hi)        # left
    if lo is not None:
        _rect(g, radius, h - ox - bw, w - 2 * radius, bw, lo)   # bottom
        _rect(g, w - ox - bw, radius, bw, h - 2 * radius, lo)   # right
    return {"palette": palette, "rows": ["".join(r) for r in g]}


# ── the four Emporium bubbles (colours = the EMP palette) ────────────────────
def tile():
    pal = {"k": "#0c0a1e", "f": "#1c1850", "b": "#37c9da",
           "h": "#9af6ff", "l": "#1f6e78"}
    return _bubble(5, 2, pal, fill="f", border="b", outline="k", hi="h", lo="l")


def banner():
    pal = {"k": "#0c0a1e", "f": "#2a1644", "b": "#cf3597",
           "h": "#f2a0d8", "l": "#7a1f5a"}
    return _bubble(5, 2, pal, fill="f", border="b", outline="k", hi="h", lo="l")


def balance():
    pal = {"k": "#0c0a1e", "f": "#2a1644", "b": "#f4c430",
           "h": "#ffe9a0", "l": "#9a7a1a"}
    return _bubble(5, 2, pal, fill="f", border="b", outline="k", hi="h", lo="l")


def dialogue():
    pal = {"k": "#0c0a1e", "f": "#0a0a12", "b": "#f4f4ec", "l": "#c4c4d0"}
    return _bubble(6, 3, pal, fill="f", border="b", outline="k", lo="l")


BUBBLES = {
    "bubble_tile.tdart": tile,
    "bubble_banner.tdart": banner,
    "bubble_balance.tdart": balance,
    "bubble_dialogue.tdart": dialogue,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in BUBBLES.items():
        data = fn()
        pixel_art.save(OUT / name, data)
        w, h = pixel_art.dimensions(data)
        print(f"wrote {name}  ({w}x{h})")

    if "--preview" in sys.argv:
        from PySide6.QtGui import QGuiApplication
        _ = QGuiApplication.instance() or QGuiApplication(sys.argv)
        # stretch each to a representative size and tile them into one PNG
        sizes = {"bubble_tile.tdart": (150, 110), "bubble_banner.tdart": (300, 56),
                 "bubble_balance.tdart": (150, 56), "bubble_dialogue.tdart": (380, 78)}
        from PySide6.QtGui import QPixmap, QPainter, QColor
        sheet = QPixmap(420, 340)
        sheet.fill(QColor("#272273"))
        p = QPainter(sheet)
        y = 8
        for name, fn in BUBBLES.items():
            tw, th = sizes[name]
            pix = pixel_art.render_nine_slice(fn(), tw, th)
            p.drawPixmap(10, y, pix)
            y += th + 10
        p.end()
        png = OUT.parent / "bubbles_preview.png"
        sheet.save(str(png))
        print(f"preview -> {png}")


if __name__ == "__main__":
    main()
