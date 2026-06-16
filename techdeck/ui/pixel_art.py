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
from PySide6.QtCore import Qt


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
    text = (
        "{\n"
        f'  "format": "tdart",\n'
        f'  "version": 1,\n'
        f'  "palette": {json.dumps(out["palette"], ensure_ascii=False)},\n'
        '  "rows": [\n'
        + ",\n".join(f"    {json.dumps(r, ensure_ascii=False)}" for r in out["rows"])
        + "\n  ]\n}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def normalize(data: dict) -> dict:
    """Validate + pad rows to a common width. Returns a clean {palette, rows}."""
    palette = dict(data.get("palette", {}))
    rows = list(data.get("rows", []))
    width = max((len(r) for r in rows), default=0)
    rows = [r.ljust(width, ".") for r in rows]
    return {"palette": palette, "rows": rows}


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
