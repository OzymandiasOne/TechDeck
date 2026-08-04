"""
TechDeck Pixel Art — format + runtime renderer
==============================================

A tiny, space-efficient sprite format (`.tdart`) and the renderer that turns it
into a QPixmap at runtime. This replaces hand-typing ASCII grids into Python
(like the old SPINNER_ART / MOTH_FRAMES): draw sprites in the paint editor
(`python tools/pixel_editor.py`), save a `.tdart`, and load it here.

Why not just ship a PNG? A `.tdart` is the *recipe* for the image, not the
pixels: a small palette plus one character per cell. A 32x32 sprite is well
under 1 KB of readable JSON, it diffs cleanly in git, and it's hand-editable in
a pinch. The renderer reconstructs the bitmap on demand.

Format (JSON):
    {
      "format": "tdart",
      "version": 1,
      "palette": { "r": "#d83f3f", "b": "#3f6fd8", "s": "#c0c0c0" },
      "rows": [
        "....rr....",
        "...rbbr...",
        "..rbsssbr.",
         ...
      ]
    }

Rules:
  - Each character in `rows` is ONE pixel.
  - "." is ALWAYS transparent (so is " " and any char missing from the palette).
  - Palette maps a single character -> an opaque "#RRGGBB" hex color.
  - Rows should be equal length; short rows are padded transparent, so a file
    is never rejected for a ragged edge.

This module is import-light on purpose (only PySide6.QtGui) so the editor tool
and the app can both use it.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QPixmap, QColor, QPainter
from PySide6.QtCore import Qt, QRect


TRANSPARENT_CHARS = {".", " ", ""}


# ── Load / save ─────────────────────────────────────────────────────────────
def load(path) -> dict:
    """Read a .tdart file into a {palette, rows} dict. Raises on bad JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return normalize(data)


def save(path, data: dict) -> None:
    """Write a {palette, rows} dict to a .tdart file (compact but readable)."""
    out = {
        "format": "tdart",
        "version": 1,
        "palette": dict(data.get("palette", {})),
        "rows": list(data.get("rows", [])),
    }
    # A sprite that declares its rotational order must keep it across a
    # save — the pixel editor round-trips through here, and losing the marker
    # would hand a 2-fold design to the 4-fold enforcer next time it loads.
    sym = ""
    if "symmetry" in data:
        sym = f'  "symmetry": {int(data["symmetry"])},\n'
    text = (
        "{\n"
        f'  "format": "tdart",\n'
        f'  "version": 1,\n'
        + sym
        + f'  "palette": {json.dumps(out["palette"], ensure_ascii=False)},\n'
        '  "rows": [\n'
        + ",\n".join(f"    {json.dumps(r, ensure_ascii=False)}" for r in out["rows"])
        + "\n  ]\n}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def normalize(data: dict) -> dict:
    """Validate + pad rows to a common width. Returns a clean {palette, rows}.

    `symmetry` is carried through when present: a sprite declares its own
    rotational order (2 = 180 deg, 4 = quarter-turn). Dropping it here would
    silently hand a 2-fold design to the 4-fold enforcer, which shreds it.
    """
    palette = dict(data.get("palette", {}))
    rows = list(data.get("rows", []))
    width = max((len(r) for r in rows), default=0)
    rows = [r.ljust(width, ".") for r in rows]
    out = {"palette": palette, "rows": rows}
    if "symmetry" in data:
        out["symmetry"] = int(data["symmetry"])
    return out


# ── Geometry ────────────────────────────────────────────────────────────────
def dimensions(data: dict) -> tuple[int, int]:
    """(width, height) in cells."""
    rows = data.get("rows", [])
    return (max((len(r) for r in rows), default=0), len(rows))


# ── Render ──────────────────────────────────────────────────────────────────
def render(data: dict, scale: int = 1,
           outline: bool = False, outline_color: str = "#101018") -> QPixmap:
    """Render a sprite dict to a crisp (no smoothing) QPixmap.

    scale         : pixels per cell.
    outline       : if True, trace `outline_color` around the silhouette
                    (every transparent cell 4-adjacent to a filled cell), like
                    the old moth/spinner outline. Off by default.
    outline_color : the traced color.
    """
    data = normalize(data)
    palette = data["palette"]
    rows = data["rows"]
    w, h = dimensions(data)

    pix = QPixmap(max(w, 1) * scale, max(h, 1) * scale)
    pix.fill(Qt.GlobalColor.transparent)
    if w == 0 or h == 0:
        return pix

    def filled(x: int, y: int) -> bool:
        if 0 <= y < h and 0 <= x < len(rows[y]):
            return rows[y][x] not in TRANSPARENT_CHARS
        return False

    p = QPainter(pix)
    try:
        # Outline first so colored cells paint over any shared edges.
        if outline:
            oc = QColor(outline_color)
            for y in range(h):
                for x in range(w):
                    if filled(x, y):
                        continue
                    if (filled(x - 1, y) or filled(x + 1, y)
                            or filled(x, y - 1) or filled(x, y + 1)):
                        p.fillRect(x * scale, y * scale, scale, scale, oc)

        for y in range(h):
            row = rows[y]
            for x in range(len(row)):
                ch = row[x]
                if ch in TRANSPARENT_CHARS:
                    continue
                hexval = palette.get(ch)
                if not hexval:
                    continue
                p.fillRect(x * scale, y * scale, scale, scale, QColor(hexval))
    finally:
        p.end()
    return pix


def render_file(path, **kwargs) -> QPixmap:
    """Convenience: load a .tdart and render it."""
    return render(load(path), **kwargs)


# ── 9-slice (resizable panels / word bubbles) ─────────────────────────────────
def render_nine_slice(data, target_w: int, target_h: int,
                      margins=None) -> QPixmap:
    """Stretch a small sprite to (target_w, target_h) as a 9-slice: the four
    corners are kept 1:1 (crisp), the four edges stretch along one axis, and the
    centre fills the rest. One source cell == one target pixel, so a hand-drawn
    bubble renders at the same fidelity as the old procedural panels.

    `margins` = (left, top, right, bottom) source cells that stay un-stretched.
    When omitted it's auto-derived as (dim-1)//2 per side, leaving a 1-2px centre
    strip — so an odd/even square bubble drawn in the editor "just works" with no
    metadata to lose on save.
    """
    data = normalize(data)
    w, h = dimensions(data)
    src = render(data, scale=1)
    if w == 0 or h == 0:
        out = QPixmap(max(target_w, 1), max(target_h, 1))
        out.fill(Qt.GlobalColor.transparent)
        return out
    if margins is None:
        ml = mr = (w - 1) // 2
        mt = mb = (h - 1) // 2
    else:
        ml, mt, mr, mb = margins
    # Never let the corners overlap the (possibly tiny) target.
    ml = min(ml, target_w // 2); mr = min(mr, target_w - ml)
    mt = min(mt, target_h // 2); mb = min(mb, target_h - mt)

    xs_src = [0, ml, w - mr, w]
    ys_src = [0, mt, h - mb, h]
    xs_dst = [0, ml, target_w - mr, target_w]
    ys_dst = [0, mt, target_h - mb, target_h]

    out = QPixmap(max(target_w, 1), max(target_h, 1))
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    try:
        for iy in range(3):
            for ix in range(3):
                sw_ = xs_src[ix + 1] - xs_src[ix]
                sh_ = ys_src[iy + 1] - ys_src[iy]
                dw_ = xs_dst[ix + 1] - xs_dst[ix]
                dh_ = ys_dst[iy + 1] - ys_dst[iy]
                if sw_ <= 0 or sh_ <= 0 or dw_ <= 0 or dh_ <= 0:
                    continue
                p.drawPixmap(QRect(xs_dst[ix], ys_dst[iy], dw_, dh_), src,
                             QRect(xs_src[ix], ys_src[iy], sw_, sh_))
    finally:
        p.end()
    return out


# ── 4-fold symmetry (spinners) ───────────────────────────────────────────────
def enforce_4fold(rows):
    """Return rows made perfectly 4-fold symmetric: for every cell, take the
    value of its 90-degree-rotation orbit member nearest the TOP (then nearest
    the centre column). That stamps the TOP arm into all four quadrants, so a
    spinner is symmetric and dead-centred by construction — you author only the
    top arm and the other three are generated. Requires a SQUARE grid (true
    centre); a non-square grid is returned padded-unchanged. Palette-agnostic:
    operates on raw characters, so it works for any .tdart spinner.
    """
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    g = [r.ljust(w, ".") for r in rows]
    if w != h or h == 0:
        return g
    cx = (w - 1) / 2.0

    def source(x, y):
        pts = [(x, y)]
        px, py = x, y
        for _ in range(3):
            px, py = w - 1 - py, px          # 90 deg: (x,y) -> (w-1-y, x)
            pts.append((px, py))
        return min(pts, key=lambda p: (p[1], abs(p[0] - cx)))   # most-north/central

    out = []
    for y in range(h):
        row = []
        for x in range(w):
            sx, sy = source(x, y)
            row.append(g[sy][sx])
        out.append("".join(row))
    return out


def enforce_4fold_data(data: dict) -> dict:
    """Same as enforce_4fold but on a {palette, rows} sprite dict."""
    data = normalize(data)
    return {"palette": dict(data["palette"]), "rows": enforce_4fold(data["rows"])}
