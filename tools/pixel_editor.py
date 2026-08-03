"""
TechDeck Pixel Art Editor
=========================

A very basic paint tool for authoring TechDeck sprites. Draw with a palette,
save to a compact `.tdart` file (see techdeck/ui/pixel_art.py), and the app
renders it at runtime — no more hand-typing ASCII grids into Python.

Run it:
    python tools/pixel_editor.py
    python tools/pixel_editor.py path/to/sprite.tdart      (open a file)

Tools:  Pencil (paint active color) · Eraser (transparent) · Fill (flood) ·
        Eyedropper (pick a cell's color as active) · Line (drag start→end,
        live preview, paints on release) · Spline (click to drop points on a
        smooth curve, Enter / double-click / right-click paints it, Esc
        cancels; both honor brush size + symmetry) · Select (rectangle) ·
        Lasso (freeform). With a selection: drag inside it to move the pixels,
        arrow keys nudge, Delete clears, Escape (or a click outside) deselects,
        Ctrl+C copies and Ctrl+V pastes the copy back as a floating selection
        (drag it into place; it stamps down on release / click-out; the
        clipboard survives file loads, so copy-across-files works).
Mouse:  left-drag paints. The checkerboard shows transparency.
Files:  New (set size) · Open · Save / Save As (.tdart) · Copy as Python
        (puts a PALETTE + ART snippet on the clipboard for legacy widgets).
        Open/Save default to tools/pixel_playground.
Edit:   Resize (scale art) · Reduce duplicate lines · Add / remove lines
        (signed per-side count: positive adds transparent lines, negative crops) ·
        Mirror H/V (Ctrl+H / Ctrl+Shift+H) · Rotate 90 CW/CCW (Ctrl+] / Ctrl+[)
        — transforms apply to the selection when one exists, else the whole
        canvas. Undo is Ctrl+Z or Ctrl+U; redo Ctrl+Y, Ctrl+R or Ctrl+Shift+Z.
"""

import sys
from pathlib import Path

# Allow `from techdeck...` when run directly from the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QColorDialog, QInputDialog,
    QScrollArea, QMessageBox, QButtonGroup, QFrame, QSpinBox,
    QDialog, QDialogButtonBox, QFormLayout,
    QListWidget, QListWidgetItem, QSlider,
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QImage, QKeySequence

from techdeck.ui import pixel_art


# Characters available to auto-assign to palette colors ("." is transparent).
_CHAR_POOL = (
    "123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "!#$%&*+=?@~"
)

_DEFAULT_PALETTE = {
    "k": "#101018", "w": "#f4f4f8", "r": "#d83f3f", "g": "#3fbf5f",
    "b": "#3f6fd8", "y": "#f4c430", "c": "#3fd0d8", "p": "#7b4fff",
    "s": "#b8c0cc",
}


# Selection clipboard (Ctrl+C / Ctrl+V). Module-level so it survives file
# loads and is shared by every Canvas in the process (copy across files/modes).
_CLIPBOARD = None   # {"cells": {(dx, dy): char}, "palette": {char: hex}, "origin": (x, y)}


def _line_cells(a, b):
    """Bresenham: every cell on the segment a→b (inclusive). Used to close the
    gaps a fast lasso drag leaves between sampled cells."""
    x0, y0 = a
    x1, y1 = b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    out = []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _spline_cells(pts):
    """Every cell on a smooth Catmull-Rom curve through `pts` (in order,
    gap-free). One point is itself; two points fall back to a straight line."""
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(pts) == 1:
        return [pts[0]]
    if len(pts) == 2:
        return _line_cells(pts[0], pts[1])
    ext = [pts[0]] + pts + [pts[-1]]   # clamp ends so the curve hits them
    samples = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ext[i:i + 4]
        steps = 4 * max(abs(x2 - x1), abs(y2 - y1), 1)
        last = i == len(pts) - 2
        for s in range(steps + (1 if last else 0)):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * x1 + (x2 - x0) * t
                       + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2
                       + (3 * x1 - x0 - 3 * x2 + x3) * t3)
            y = 0.5 * (2 * y1 + (y2 - y0) * t
                       + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2
                       + (3 * y1 - y0 - 3 * y2 + y3) * t3)
            samples.append((round(x), round(y)))
    cells = []
    for c in samples:
        if not cells:
            cells.append(c)
        elif c != cells[-1]:
            cells.extend(_line_cells(cells[-1], c)[1:])   # bridge any gap
    return cells


# ── Image → .tdart import ────────────────────────────────────────────────────
def detect_pixel_scale(img: QImage) -> int:
    """Guess how many real pixels make up one art pixel in `img`. Integer-scaled
    pixel art has solid NxN blocks, so the GCD of colour-run lengths (sampled
    across rows and columns) is that block size. Returns 1 for native art."""
    from math import gcd
    from functools import reduce
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return 1
    runs = []
    for y in range(0, h, max(1, h // 40)):
        start, prev = 0, img.pixel(0, y)
        for x in range(1, w):
            p = img.pixel(x, y)
            if p != prev:
                runs.append(x - start)
                start, prev = x, p
        runs.append(w - start)
    for x in range(0, w, max(1, w // 40)):
        start, prev = 0, img.pixel(x, 0)
        for y in range(1, h):
            p = img.pixel(x, y)
            if p != prev:
                runs.append(y - start)
                start, prev = y, p
        runs.append(h - start)
    runs = [r for r in runs if r > 0]
    return max(1, reduce(gcd, runs)) if runs else 1


def image_to_tdart(img: QImage, block: int):
    """Downsample `img` by `block` (sampling each block's centre) into a
    {palette, rows} sprite. Alpha < 128 becomes transparent. If the image has
    more colours than the palette can hold, channels are quantized until they
    fit. Returns (data, note)."""
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    nw, nh = max(1, w // block), max(1, h // block)

    grid = []
    opaque = set()
    for by in range(nh):
        row = []
        for bx in range(nw):
            px = min(w - 1, bx * block + block // 2)
            py = min(h - 1, by * block + block // 2)
            c = img.pixelColor(px, py)
            row.append((c.red(), c.green(), c.blue(), c.alpha()))
            if c.alpha() >= 128:
                opaque.add((c.red(), c.green(), c.blue()))
        grid.append(row)

    def q(rgb, s):
        return (rgb[0] // s * s, rgb[1] // s * s, rgb[2] // s * s)

    step = 1
    while len({q(c, step) for c in opaque}) > len(_CHAR_POOL) and step < 64:
        step *= 2

    palette, color_to_char, chars = {}, {}, iter(_CHAR_POOL)
    rows = []
    for row in grid:
        out = []
        for (r, g, b, a) in row:
            if a < 128:
                out.append(".")
                continue
            key = q((r, g, b), step)
            ch = color_to_char.get(key)
            if ch is None:
                ch = next(chars, None)
                if ch is None:
                    out.append(".")
                    continue
                color_to_char[key] = ch
                palette[ch] = "#%02x%02x%02x" % key
            out.append(ch)
        rows.append("".join(out))
    note = f"quantized (step {step})" if step > 1 else ""
    return {"palette": palette, "rows": rows}, note


class Layer:
    """One sheet in the stack: its own grid, palette, file and undo history.

    Layers exist so multi-part art (a beyblade's top / bottom / centre, a
    character's body / clothes / face) can be edited AS IT WILL BE SEEN --
    overlapping on one canvas -- while each part stays a separate file that
    saves back to its own path.
    """

    def __init__(self, name="Layer", rows=None, palette=None, path=None):
        self.name = name
        self.rows = rows if rows is not None else []
        self.palette = dict(palette or _DEFAULT_PALETTE)
        self.path = Path(path) if path else None
        self.visible = True
        self.opacity = 1.0
        self.dirty = False
        self.undo = []
        self.redo = []

    def size(self):
        return (len(self.rows[0]) if self.rows else 0, len(self.rows))

    def data(self):
        rows = ["".join(r) for r in self.rows]
        used = set("".join(rows)) - set(pixel_art.TRANSPARENT_CHARS)
        return {"format": "tdart", "version": 1,
                "palette": {k: v for k, v in self.palette.items() if k in used},
                "rows": rows}


class Canvas(QWidget):
    """The editable pixel grid — a stack of Layers drawn bottom to top.

    `rows`, `palette`, `_undo` and `_redo` are properties onto the ACTIVE
    layer, so every tool, transform and selection routine keeps working on one
    grid exactly as before and knows nothing about the stack.
    """

    cell_hovered = Signal(int, int)
    color_picked = Signal(str)   # emits a palette char when the eyedropper hits
    modified = Signal()
    palette_changed = Signal()   # paste added colors — swatch rails re-sync
    layers_changed = Signal()    # stack composition changed (add/remove/reorder)
    active_changed = Signal()    # only WHICH layer is active changed

    # ---- the stack ----------------------------------------------------------
    @property
    def layer(self):
        return self.layers[self.active]

    @property
    def rows(self):
        return self.layer.rows

    @rows.setter
    def rows(self, v):
        self.layer.rows = v

    @property
    def palette(self):
        return self.layer.palette

    @palette.setter
    def palette(self, v):
        self.layer.palette = v

    @property
    def _undo(self):
        return self.layer.undo

    @property
    def _redo(self):
        return self.layer.redo

    def set_active(self, i):
        """Change which layer edits go to.

        Deliberately does NOT emit layers_changed: that signal means the STACK
        composition changed and makes listeners rebuild their whole list. A
        drag-reorder fires currentRowChanged mid-drop, so rebuilding on a mere
        selection change would wipe out the drop the user just made.
        """
        if 0 <= i < len(self.layers) and i != self.active:
            self.active = i
            if self.active_char not in self.palette:
                self.active_char = next(iter(self.palette), "k")
            self._clear_selection()
            self.palette_changed.emit()
            self.active_changed.emit()
            self.update()

    def add_layer(self, name=None, rows=None, palette=None, path=None,
                  above=True):
        """Insert a layer, sized to match the stack. Returns its index."""
        w, h = self.grid_size()
        if rows is None:
            rows = [["." for _ in range(w)] for _ in range(h)]
        n = len(self.layers)
        lay = Layer(name or f"Layer {n + 1}", rows, palette, path)
        at = self.active + 1 if above else self.active
        self.layers.insert(at, lay)
        self.active = at
        self._clear_selection()
        self.palette_changed.emit()
        self.layers_changed.emit()
        self.update()
        return at

    def remove_layer(self, i):
        if len(self.layers) <= 1:
            return False
        self.layers.pop(i)
        self.active = min(self.active, len(self.layers) - 1)
        self._clear_selection()
        self.palette_changed.emit()
        self.layers_changed.emit()
        self.update()
        return True

    def move_layer(self, i, delta):
        j = i + delta
        if not (0 <= i < len(self.layers) and 0 <= j < len(self.layers)):
            return False
        self.layers[i], self.layers[j] = self.layers[j], self.layers[i]
        if self.active == i:
            self.active = j
        elif self.active == j:
            self.active = i
        self.layers_changed.emit()
        self.update()
        return True

    def pad_all_to(self, w, h):
        """Grow every layer to at least w x h so the stack stays aligned."""
        for lay in self.layers:
            lw, lh = lay.size()
            for r in lay.rows:
                r.extend(["."] * (w - lw))
            for _ in range(h - lh):
                lay.rows.append(["." for _ in range(w)])

    def __init__(self, w=32, h=32, parent=None):
        self.layers = [Layer("Layer 1",
                             [["." for _ in range(w)] for _ in range(h)])]
        self.active = 0
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)   # Esc/arrows/Delete
        self.cell_px = 16
        self.show_grid = True
        self.symmetry = False     # 4-fold rotational mirror for spinners
        self.brush_size = 1       # N x N pencil/eraser block
        # Selection / move state (select + lasso tools).
        self.selection = None     # committed selection: set of (x, y) cells
        self._sel_path = None     # in-progress lasso trail (list of cells)
        self._sel_anchor = None   # rect-select drag anchor cell
        self._sel_cur = None      # rect-select drag current cell
        self._float = None        # mid-move lift: {"cells", "dx", "dy", "pushed"}
        self._move_anchor = None  # cell the move drag started on
        # Line / spline in-progress state (previewed, painted on commit).
        self._line_anchor = None  # line drag start cell
        self._line_cur = None     # line drag current cell
        self._spline_pts = None   # placed spline points (list of cells)
        self._spline_hover = None # hover cell — previews the next segment
        self.tool = "pencil"
        self.active_char = "k"
        self._resize_to_grid()

    # ---- tool (leaving select/lasso drops the selection) ---------------------
    @property
    def tool(self):
        return self._tool

    @tool.setter
    def tool(self, name):
        self._tool = name
        if name not in ("select", "lasso"):
            self._clear_selection()
            self.unsetCursor()
        if name not in ("line", "spline"):
            self._clear_stroke()

    # ---- model ---------------------------------------------------------------
    def grid_size(self):
        return (len(self.rows[0]) if self.rows else 0, len(self.rows))

    def new_grid(self, w, h):
        """Reset to a single empty layer."""
        self._clear_selection()
        self.layers = [Layer("Layer 1",
                             [["." for _ in range(w)] for _ in range(h)])]
        self.active = 0
        self._resize_to_grid()
        self.update()
        self.layers_changed.emit()
        self.palette_changed.emit()
        self.modified.emit()

    def load(self, data, name=None, path=None):
        """Replace the whole stack with one layer holding `data`."""
        data = pixel_art.normalize(data)
        rows = [list(r) for r in data["rows"]] or \
               [["." for _ in range(32)] for _ in range(32)]
        self._clear_selection()
        self.layers = [Layer(name or "Layer 1", rows,
                             dict(data["palette"]) or dict(_DEFAULT_PALETTE),
                             path)]
        self.active = 0
        if self.active_char not in self.palette:
            self.active_char = next(iter(self.palette), "k")
        self._resize_to_grid()
        self.update()
        self.layers_changed.emit()

    def load_as_layer(self, data, name, path=None):
        """Add `data` as a new layer on top, padding the stack if it is bigger.

        Mismatched sizes are padded, never scaled: rescaling one sheet of a
        multi-part sprite would silently break its alignment with the others.
        """
        data = pixel_art.normalize(data)
        rows = [list(r) for r in data["rows"]]
        nw = max((len(r) for r in rows), default=0)
        nh = len(rows)
        w, h = self.grid_size()
        self.pad_all_to(max(w, nw), max(h, nh))
        w, h = self.grid_size()
        for r in rows:
            r.extend(["."] * (w - len(r)))
        while len(rows) < h:
            rows.append(["." for _ in range(w)])
        i = self.add_layer(name, rows, dict(data["palette"]), path)
        self._resize_to_grid()
        return i, (nw, nh) != (w, h)

    def reduce_duplicate_lines(self):
        """Collapse runs of identical ADJACENT rows and columns into one each.
        Losslessly de-scales an over-large import (where each art pixel is an
        NxN block of identical cells) back toward native resolution without any
        resampling/distortion. Returns (old, new) sizes."""
        self._clear_selection()
        old = self.grid_size()
        # Decide which lines to keep from the COMPOSITE, then cut every layer
        # the same way -- deciding per layer would slide them out of register.
        comp = ["".join(r) for r in self.composite_rows()]
        keep_y = [y for y, r in enumerate(comp)
                  if y == 0 or comp[y - 1] != r]
        if keep_y:
            w = len(comp[0])
            keep_x, prev = [], None
            for x in range(w):
                col = tuple(comp[y][x] for y in keep_y)
                if col != prev:
                    keep_x.append(x)
                    prev = col
            for lay in self.layers:
                lay.rows = [[lay.rows[y][x] for x in keep_x] for y in keep_y]
        else:
            for lay in self.layers:
                lay.rows = []
        self._resize_to_grid()
        self.update()
        self.modified.emit()
        return old, self.grid_size()

    def resize_grid(self, nw, nh):
        """Resample the art to nw x nh by nearest-neighbour. Reuses the existing
        palette (no new colours). Downscaling loses detail (expected)."""
        w, h = self.grid_size()
        if w == 0 or h == 0 or (nw == w and nh == h):
            return
        self._clear_selection()
        for lay in self.layers:
            new = []
            for ty in range(nh):
                sy = min(h - 1, ty * h // nh)
                new.append([lay.rows[sy][min(w - 1, tx * w // nw)]
                            for tx in range(nw)])
            lay.rows = new
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def pad_grid(self, top, bottom, left, right):
        """Grow the canvas by adding transparent rows/columns on each side WITHOUT
        scaling the existing art — room for details that overflow the edges."""
        if top == bottom == left == right == 0:
            return
        self._clear_selection()
        w, _ = self.grid_size()
        nw = w + left + right
        for lay in self.layers:
            new = [["."] * nw for _ in range(top)]
            for r in lay.rows:
                new.append(["."] * left + list(r) + ["."] * right)
            new += [["."] * nw for _ in range(bottom)]
            lay.rows = new
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def crop_grid(self, top, bottom, left, right) -> bool:
        """Remove rows/columns from each side WITHOUT scaling — the inverse of
        pad_grid. Whatever art sits on the removed lines is discarded. Refuses
        a crop that would leave no cells (returns False)."""
        if top == bottom == left == right == 0:
            return True
        w, h = self.grid_size()
        if top + bottom >= h or left + right >= w:
            return False
        self._clear_selection()
        for lay in self.layers:
            lay.rows = [list(r)[left:w - right]
                        for r in lay.rows[top:h - bottom]]
        self._resize_to_grid()
        self.update()
        self.modified.emit()
        return True

    # ---- mirror / rotate -----------------------------------------------------
    _XFORM_LABELS = {
        "flip_h": "Mirrored horizontally", "flip_v": "Mirrored vertically",
        "rot_cw": "Rotated 90 CW", "rot_ccw": "Rotated 90 CCW",
    }

    def transform(self, op):
        """Mirror/rotate: 'flip_h' | 'flip_v' | 'rot_cw' | 'rot_ccw'. Applies
        to the selection when one exists (about its bounding box), otherwise
        to the whole canvas. Returns a status message for the caller."""
        if self._float is not None:
            self._anchor_float()   # commit an airborne paste/move first
        label = self._XFORM_LABELS[op]
        if self.selection:
            self._transform_selection(op)
            return f"{label} (selection)"
        self._transform_canvas(op)
        return label

    def _transform_canvas(self, op):
        if not self.rows:
            return
        self.push_undo()
        if op == "flip_h":
            new = [list(reversed(r)) for r in self.rows]
        elif op == "flip_v":
            new = [r[:] for r in reversed(self.rows)]
        elif op == "rot_cw":
            new = [list(t) for t in zip(*self.rows[::-1])]
        else:   # rot_ccw
            new = [list(t) for t in zip(*self.rows)][::-1]
        if new == self.rows:
            self._undo.pop()   # symmetric art — nothing changed
            return
        self.rows = new
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def _transform_selection(self, op):
        """Remap the selection's pixels (and its mask) about the selection's
        bounding box. Rotating a non-square selection keeps its top-left,
        shifted only as far as needed to stay on the grid; pixels that still
        don't fit are clipped."""
        xs = [x for x, _ in self.selection]
        ys = [y for _, y in self.selection]
        x0, y0 = min(xs), min(ys)
        bw = max(xs) - x0 + 1
        bh = max(ys) - y0 + 1

        def remap(x, y):
            rx, ry = x - x0, y - y0
            if op == "flip_h":
                return bw - 1 - rx, ry
            if op == "flip_v":
                return rx, bh - 1 - ry
            if op == "rot_cw":
                return bh - 1 - ry, rx
            return ry, bw - 1 - rx      # rot_ccw

        nw, nh = (bh, bw) if op in ("rot_cw", "rot_ccw") else (bw, bh)
        w, h = self.grid_size()
        ox = max(0, min(x0, w - nw))
        oy = max(0, min(y0, h - nh))

        lifted = {}
        for (x, y) in self.selection:
            ch = self.rows[y][x]
            if ch not in pixel_art.TRANSPARENT_CHARS and ch in self.palette:
                lifted[(x, y)] = ch
        if lifted:
            self.push_undo()
            for (x, y) in lifted:
                self.rows[y][x] = "."
            for (x, y), ch in lifted.items():
                nx, ny = remap(x, y)
                tx, ty = ox + nx, oy + ny
                if 0 <= tx < w and 0 <= ty < h:
                    self.rows[ty][tx] = ch
            if self.rows == self._undo[-1]:
                self._undo.pop()   # symmetric — nothing changed
            else:
                self.modified.emit()
        self.selection = {
            (ox + nx, oy + ny)
            for nx, ny in (remap(x, y) for (x, y) in self.selection)
            if 0 <= ox + nx < w and 0 <= oy + ny < h
        } or None
        self.update()

    # ---- undo / redo (stroke-level) -----------------------------------------
    def _snapshot(self):
        return [r[:] for r in self.rows]

    def push_undo(self):
        """Record the current grid before a modifying stroke begins."""
        self._undo.append(self._snapshot())
        if len(self._undo) > 200:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return
        self._clear_selection()
        self._redo.append(self._snapshot())
        self.rows = self._undo.pop()
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def redo(self):
        if not self._redo:
            return
        self._clear_selection()
        self._undo.append(self._snapshot())
        self.rows = self._redo.pop()
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def export(self):
        """Flatten the visible stack into one sprite.

        Layers own their palettes independently, so the same char can mean
        different colours on different sheets (top's '7' vs centre's 'w' may
        even be the same hex under different keys). Merging by char alone would
        silently recolour the art, so a colliding char is REMAPPED to a free
        one; identical hexes are folded onto a single key.
        """
        merged, by_hex, remap = {}, {}, []
        for lay in self.layers:
            m = {}
            for ch, hx in lay.palette.items():
                key = hx.lower()
                if key in by_hex:                    # same colour already in
                    m[ch] = by_hex[key]
                elif ch not in merged:               # char free -- keep it
                    merged[ch] = hx
                    by_hex[key] = ch
                    m[ch] = ch
                else:                                # collision -- rename
                    free = next((c for c in _CHAR_POOL
                                 if c not in merged
                                 and c not in pixel_art.TRANSPARENT_CHARS), None)
                    if free is None:
                        m[ch] = ch                   # out of chars; best effort
                        continue
                    merged[free] = hx
                    by_hex[key] = free
                    m[ch] = free
            remap.append(m)

        w, h = self.grid_size()
        out = [["." for _ in range(w)] for _ in range(h)]
        for lay, m in zip(self.layers, remap):
            if not lay.visible:
                continue
            for y in range(min(h, len(lay.rows))):
                row = lay.rows[y]
                for x in range(min(w, len(row))):
                    ch = row[x]
                    if ch not in pixel_art.TRANSPARENT_CHARS:
                        out[y][x] = m.get(ch, ch)
        rows = ["".join(r) for r in out]
        used = set("".join(rows)) - set(pixel_art.TRANSPARENT_CHARS)
        return {"palette": {k: v for k, v in merged.items() if k in used},
                "rows": rows}

    def add_color(self, hexval):
        # Reuse the char if this exact color is already in the palette.
        for ch, hx in self.palette.items():
            if hx.lower() == hexval.lower():
                return ch
        used = set(self.palette)
        for ch in _CHAR_POOL:
            if ch not in used:
                self.palette[ch] = hexval
                return ch
        return None  # palette full (unlikely)

    # ---- view ----------------------------------------------------------------
    def _resize_to_grid(self):
        w, h = self.grid_size()
        self.setFixedSize(QSize(max(w, 1) * self.cell_px, max(h, 1) * self.cell_px))

    def set_zoom(self, cell_px):
        self.cell_px = max(2, min(48, cell_px))
        self._resize_to_grid()
        self.update()

    def composite_rows(self):
        """Flatten the visible stack, bottom to top, into one char grid.
        Opacity is a VIEW property only — it never affects what is saved."""
        w, h = self.grid_size()
        out = [["." for _ in range(w)] for _ in range(h)]
        for lay in self.layers:
            if not lay.visible:
                continue
            for y in range(min(h, len(lay.rows))):
                row = lay.rows[y]
                for x in range(min(w, len(row))):
                    ch = row[x]
                    if ch not in pixel_art.TRANSPARENT_CHARS:
                        out[y][x] = ch
        return out

    def paintEvent(self, _evt):
        p = QPainter(self)
        cp = self.cell_px
        w, h = self.grid_size()
        light = QColor("#3a3a3a")
        dark = QColor("#2c2c2c")
        for y in range(h):
            for x in range(w):
                p.fillRect(x * cp, y * cp, cp, cp,
                           light if (x + y) % 2 == 0 else dark)
        # Draw the stack bottom to top. Each layer's opacity applies to its own
        # pixels, so a lower sheet stays legible while you work on the one above.
        for lay in self.layers:
            if not lay.visible or lay.opacity <= 0.0:
                continue
            alpha = int(round(max(0.0, min(1.0, lay.opacity)) * 255))
            for y in range(min(h, len(lay.rows))):
                row = lay.rows[y]
                for x in range(min(w, len(row))):
                    ch = row[x]
                    if ch in pixel_art.TRANSPARENT_CHARS or ch not in lay.palette:
                        continue
                    col = QColor(lay.palette[ch])
                    if alpha < 255:
                        col.setAlpha(alpha)
                    p.fillRect(x * cp, y * cp, cp, cp, col)
        if self.show_grid and cp >= 6:
            p.setPen(QColor(0, 0, 0, 60))
            for x in range(w + 1):
                p.drawLine(x * cp, 0, x * cp, h * cp)
            for y in range(h + 1):
                p.drawLine(0, y * cp, w * cp, y * cp)

        # --- selection overlays (drawn over the grid) ---
        if self._float:
            fdx, fdy = self._float["dx"], self._float["dy"]
            for (x, y), ch in self._float["cells"].items():
                if ch in self.palette:
                    p.fillRect((x + fdx) * cp, (y + fdy) * cp, cp, cp,
                               QColor(self.palette[ch]))
        sel = self._display_selection()
        if sel:
            self._draw_marquee_edges(p, sel)
        if self._sel_anchor is not None and self._sel_cur is not None:
            ax, ay = self._sel_anchor
            cx, cy = self._sel_cur
            x0, x1 = sorted((ax, cx))
            y0, y1 = sorted((ay, cy))
            rect = (x0 * cp, y0 * cp, (x1 - x0 + 1) * cp, (y1 - y0 + 1) * cp)
            for pen in self._marquee_pens():
                p.setPen(pen)
                p.drawRect(*rect)
        if self._sel_path and len(self._sel_path) > 1:
            pts = [QPoint(x * cp + cp // 2, y * cp + cp // 2)
                   for x, y in self._sel_path]
            for pen in self._marquee_pens():
                p.setPen(pen)
                p.drawPolyline(pts)

        # --- line / spline preview (the exact cells a commit would paint) ---
        path = None
        if self.tool == "line" and self._line_anchor is not None:
            path = _line_cells(self._line_anchor, self._line_cur)
        elif self.tool == "spline" and self._spline_pts:
            path = _spline_cells(self._spline_preview_pts())
        if path:
            ghost = QColor(self.palette.get(self.active_char, "#ffffff"))
            ghost.setAlpha(170)
            for (x, y) in self._stroke_cells(path):
                p.fillRect(x * cp, y * cp, cp, cp, ghost)
        if self.tool == "spline" and self._spline_pts:
            for pen in self._marquee_pens():   # mark the placed points
                p.setPen(pen)
                for (x, y) in self._spline_pts:
                    p.drawRect(x * cp, y * cp, cp - 1, cp - 1)
        p.end()

    @staticmethod
    def _marquee_pens():
        """Solid dark under dashed light — visible on any pixel color."""
        dark = QPen(QColor(0, 0, 0, 200), 1)
        light = QPen(QColor(255, 255, 255, 230), 1)
        light.setStyle(Qt.PenStyle.DashLine)
        return (dark, light)

    def _draw_marquee_edges(self, p, sel):
        """Outline a cell mask: every edge between a selected cell and an
        unselected neighbour."""
        cp = self.cell_px
        segs = []
        for (x, y) in sel:
            if (x, y - 1) not in sel:
                segs.append((x * cp, y * cp, (x + 1) * cp, y * cp))
            if (x, y + 1) not in sel:
                segs.append((x * cp, (y + 1) * cp, (x + 1) * cp, (y + 1) * cp))
            if (x - 1, y) not in sel:
                segs.append((x * cp, y * cp, x * cp, (y + 1) * cp))
            if (x + 1, y) not in sel:
                segs.append(((x + 1) * cp, y * cp, (x + 1) * cp, (y + 1) * cp))
        for pen in self._marquee_pens():
            p.setPen(pen)
            for s in segs:
                p.drawLine(*s)

    # ---- selection / move (select + lasso tools) -----------------------------
    def _clear_selection(self):
        """Drop all selection/move state. Any mid-drag float is discarded (its
        pre-lift snapshot is already on the undo stack, so nothing is lost)."""
        if (self.selection or self._sel_path or self._sel_anchor is not None
                or self._float):
            self.selection = None
            self._sel_path = None
            self._sel_anchor = None
            self._sel_cur = None
            self._float = None
            self._move_anchor = None
            self.update()

    def _clamped_cell(self, pos):
        """The nearest in-grid cell to `pos` — drags may leave the widget."""
        w, h = self.grid_size()
        x = max(0, min(w - 1, pos.x() // self.cell_px))
        y = max(0, min(h - 1, pos.y() // self.cell_px))
        return (int(x), int(y))

    def _display_selection(self):
        """The selection as drawn/hit-tested — offset while a move floats."""
        if not self.selection:
            return None
        if self._float:
            dx, dy = self._float["dx"], self._float["dy"]
            return {(x + dx, y + dy) for (x, y) in self.selection}
        return self.selection

    def _begin_move(self, cell):
        """Lift the selection's opaque pixels off the grid into a floating
        layer. One undo snapshot covers the whole lift-drag-anchor move."""
        if self._float is not None:
            # Already floating (a fresh paste): keep the pixels airborne and
            # rebase the anchor so the drag continues from the current offset.
            self._move_anchor = (cell[0] - self._float["dx"],
                                 cell[1] - self._float["dy"])
            return
        cells = {}
        for (x, y) in self.selection:
            ch = self.rows[y][x]
            if ch not in pixel_art.TRANSPARENT_CHARS and ch in self.palette:
                cells[(x, y)] = ch
        pushed = bool(cells)
        if pushed:
            self.push_undo()
            for (x, y) in cells:
                self.rows[y][x] = "."
        self._float = {"cells": cells, "dx": 0, "dy": 0, "pushed": pushed}
        self._move_anchor = cell

    def _anchor_float(self):
        """Stamp the floating pixels down at their offset and move the
        selection marquee with them (clipped to the grid)."""
        f, self._float = self._float, None
        self._move_anchor = None
        dx, dy = f["dx"], f["dy"]
        # A move-float snapshotted at lift; a paste-float leaves the grid
        # untouched until this stamp, so its snapshot happens here.
        if not f["pushed"] and f["cells"]:
            self.push_undo()
        w, h = self.grid_size()
        for (x, y), ch in f["cells"].items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                self.rows[ny][nx] = ch
        self.selection = {(x + dx, y + dy) for (x, y) in self.selection
                          if 0 <= x + dx < w and 0 <= y + dy < h} or None
        if f["pushed"] and (dx, dy) == (0, 0):
            self._undo.pop()   # lifted and dropped in place — a no-op
        elif f["cells"]:
            self.modified.emit()
        self.update()

    def _lasso_mask(self, path):
        """Rasterize a closed freeform path into a cell mask: the drawn
        boundary (gap-free via Bresenham) plus everything it encloses, found by
        flood-filling the OUTSIDE of the boundary's padded bounding box."""
        boundary = set()
        pts = list(path) + [path[0]]
        for a, b in zip(pts, pts[1:]):
            boundary.update(_line_cells(a, b))
        xs = [x for x, _ in boundary]
        ys = [y for _, y in boundary]
        x0, x1 = min(xs) - 1, max(xs) + 1
        y0, y1 = min(ys) - 1, max(ys) + 1
        outside = set()
        stack = [(x0, y0)]
        while stack:
            c = stack.pop()
            x, y = c
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if c in outside or c in boundary:
                continue
            outside.add(c)
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        w, h = self.grid_size()
        return {(x, y)
                for x in range(max(0, x0), min(w, x1 + 1))
                for y in range(max(0, y0), min(h, y1 + 1))
                if (x, y) not in outside}

    def nudge_selection(self, dx, dy):
        """Move the selected pixels one step (arrow keys). Each nudge is its
        own undoable lift-and-stamp; a floating paste just shifts in the air."""
        if not self.selection:
            return
        if self._float is not None:
            self._float["dx"] += dx
            self._float["dy"] += dy
            self.update()
            return
        self._begin_move((0, 0))
        self._float["dx"], self._float["dy"] = dx, dy
        self._anchor_float()

    def copy_selection(self) -> bool:
        """Ctrl+C: capture the selection's opaque pixels (with their colors)
        into the module clipboard. Copies the floating pixels if a paste/move
        is still airborne."""
        global _CLIPBOARD
        if not self.selection:
            return False
        if self._float is not None:
            fdx, fdy = self._float["dx"], self._float["dy"]
            cells = {(x + fdx, y + fdy): ch
                     for (x, y), ch in self._float["cells"].items()}
        else:
            cells = {}
            for (x, y) in self.selection:
                ch = self.rows[y][x]
                if ch not in pixel_art.TRANSPARENT_CHARS and ch in self.palette:
                    cells[(x, y)] = ch
        if not cells:
            return False
        x0 = min(x for x, _ in cells)
        y0 = min(y for _, y in cells)
        _CLIPBOARD = {
            "cells": {(x - x0, y - y0): ch for (x, y), ch in cells.items()},
            "palette": {ch: self.palette[ch] for ch in set(cells.values())},
            "origin": (x0, y0),
        }
        return True

    def paste_clipboard(self) -> bool:
        """Ctrl+V: drop the clipboard back in as a FLOATING selection at its
        source spot (clamped into the canvas) — drag/nudge it into place, then
        release/click-out/Ctrl+V-again stamps it. Colors are matched into this
        canvas's palette by hex (added if missing), so pasting across files
        keeps the art intact."""
        clip = _CLIPBOARD
        if not clip or not clip["cells"]:
            return False
        if self._float is not None:
            self._anchor_float()   # commit an airborne paste before the next
        w, h = self.grid_size()
        cw = max(x for x, _ in clip["cells"]) + 1
        chh = max(y for _, y in clip["cells"]) + 1
        ox, oy = clip["origin"]
        ox = max(0, min(ox, w - cw))
        oy = max(0, min(oy, h - chh))
        before = set(self.palette)
        charmap = {ch: self.add_color(hexval)
                   for ch, hexval in clip["palette"].items()}
        cells = {}
        for (dx, dy), ch in clip["cells"].items():
            nc = charmap.get(ch)
            tx, ty = ox + dx, oy + dy
            if nc and 0 <= tx < w and 0 <= ty < h:
                cells[(tx, ty)] = nc
        if set(self.palette) != before:
            self.palette_changed.emit()
        if not cells:
            return False
        self.selection = set(cells)
        self._float = {"cells": cells, "dx": 0, "dy": 0, "pushed": False}
        self.update()
        return True

    def delete_selection(self):
        """Clear every pixel inside the selection to transparent."""
        if not self.selection:
            return
        self.push_undo()
        changed = False
        for (x, y) in self.selection:
            if self.rows[y][x] != ".":
                self.rows[y][x] = "."
                changed = True
        if changed:
            self.update()
            self.modified.emit()
        else:
            self._undo.pop()

    # ---- line / spline strokes -----------------------------------------------
    def _clear_stroke(self):
        """Drop any in-progress line drag / spline point trail."""
        if (self._line_anchor is not None or self._spline_pts is not None
                or self._spline_hover is not None):
            self._line_anchor = None
            self._line_cur = None
            self._spline_pts = None
            self._spline_hover = None
            self.update()

    def _stroke_cells(self, cells):
        """Expand a path of cells through the brush and symmetry into the
        final in-grid cell set the stroke would paint."""
        w, h = self.grid_size()
        out = set()
        for cell in cells:
            for bx, by in self._brush_cells(*cell):
                for x, y in self._sym_cells(bx, by):
                    if 0 <= x < w and 0 <= y < h:
                        out.add((x, y))
        return out

    def _commit_stroke(self, cells):
        """Paint the active color along `cells` (brush + symmetry applied) as
        one undoable step. No-op strokes leave the undo stack untouched."""
        new = self.active_char
        targets = [(x, y) for (x, y) in self._stroke_cells(cells)
                   if self.rows[y][x] != new]
        if not targets:
            return
        self.push_undo()
        for (x, y) in targets:
            self.rows[y][x] = new
        self.update()
        self.modified.emit()

    def _spline_preview_pts(self):
        """The placed spline points plus the hover cell as a tentative next
        point, so the curve follows the mouse before each click."""
        pts = list(self._spline_pts)
        if self._spline_hover is not None and \
                (not pts or self._spline_hover != pts[-1]):
            pts.append(self._spline_hover)
        return pts

    def commit_spline(self):
        """Paint the pending spline (Enter / double-click / right-click)."""
        if self._spline_pts:
            self._commit_stroke(_spline_cells(list(self._spline_pts)))
        self._clear_stroke()

    # ---- interaction ---------------------------------------------------------
    def _cell_at(self, pos):
        x, y = pos.x() // self.cell_px, pos.y() // self.cell_px
        w, h = self.grid_size()
        if 0 <= x < w and 0 <= y < h:
            return int(x), int(y)
        return None

    def mousePressEvent(self, evt):
        if self.tool in ("select", "lasso"):
            if evt.button() != Qt.MouseButton.LeftButton:
                return
            cell = self._clamped_cell(evt.position().toPoint())
            sel = self._display_selection()
            if sel and cell in sel:
                self._begin_move(cell)      # grab: drag moves the pixels
            else:
                if self._float is not None:
                    self._anchor_float()    # click-out commits a floating paste
                self._clear_selection()     # start a fresh selection drag
                self._sel_anchor = cell
                if self.tool == "lasso":
                    self._sel_path = [cell]
                else:
                    self._sel_cur = cell
            self.update()
            return
        if self.tool == "line":
            if evt.button() != Qt.MouseButton.LeftButton:
                return
            c = self._clamped_cell(evt.position().toPoint())
            self._line_anchor = c
            self._line_cur = c
            self.update()
            return
        if self.tool == "spline":
            if evt.button() == Qt.MouseButton.RightButton:
                self.commit_spline()
                return
            if evt.button() != Qt.MouseButton.LeftButton:
                return
            c = self._clamped_cell(evt.position().toPoint())
            if self._spline_pts is None:
                self._spline_pts = []
            if not self._spline_pts or self._spline_pts[-1] != c:
                self._spline_pts.append(c)
            self.update()
            return
        cell = self._cell_at(evt.position().toPoint())
        if not cell:
            return
        if self.tool == "eyedropper":
            ch = self.rows[cell[1]][cell[0]]
            if ch in self.palette:
                self.active_char = ch
                self.color_picked.emit(ch)
            return
        # Snapshot once at the start of a modifying stroke (drag = one undo).
        self.push_undo()
        if self.tool == "fill":
            self._flood(cell)
            return
        self._paint(cell)

    def mouseMoveEvent(self, evt):
        cell = self._cell_at(evt.position().toPoint())
        if cell:
            self.cell_hovered.emit(*cell)
        if self.tool in ("select", "lasso"):
            c = self._clamped_cell(evt.position().toPoint())
            if evt.buttons() & Qt.MouseButton.LeftButton:
                if self._float is not None:
                    self._float["dx"] = c[0] - self._move_anchor[0]
                    self._float["dy"] = c[1] - self._move_anchor[1]
                    self.update()
                elif self._sel_path is not None:
                    if self._sel_path[-1] != c:
                        self._sel_path.append(c)
                        self.update()
                elif self._sel_anchor is not None and self._sel_cur != c:
                    self._sel_cur = c
                    self.update()
            else:
                sel = self._display_selection()
                self.setCursor(Qt.CursorShape.SizeAllCursor
                               if sel and c in sel
                               else Qt.CursorShape.ArrowCursor)
            return
        if self.tool == "line":
            if self._line_anchor is not None \
                    and (evt.buttons() & Qt.MouseButton.LeftButton):
                c = self._clamped_cell(evt.position().toPoint())
                if c != self._line_cur:
                    self._line_cur = c
                    self.update()
            return
        if self.tool == "spline":
            c = self._clamped_cell(evt.position().toPoint())
            if c != self._spline_hover:
                self._spline_hover = c
                if self._spline_pts:
                    self.update()
            return
        if cell and (evt.buttons() & Qt.MouseButton.LeftButton) \
                and self.tool in ("pencil", "eraser"):
            self._paint(cell)

    def mouseReleaseEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton and self.tool == "line" \
                and self._line_anchor is not None:
            cells = _line_cells(self._line_anchor, self._line_cur)
            self._line_anchor = None
            self._line_cur = None
            self._commit_stroke(cells)
            self.update()
            return
        if evt.button() != Qt.MouseButton.LeftButton \
                or self.tool not in ("select", "lasso"):
            return super().mouseReleaseEvent(evt)
        if self._float is not None:
            self._anchor_float()
        elif self._sel_path is not None:
            if len(self._sel_path) > 2:
                self.selection = self._lasso_mask(self._sel_path) or None
            self._sel_path = None
        elif self._sel_anchor is not None and self._sel_cur is not None:
            if self._sel_anchor != self._sel_cur:   # a plain click deselects
                ax, ay = self._sel_anchor
                cx, cy = self._sel_cur
                x0, x1 = sorted((ax, cx))
                y0, y1 = sorted((ay, cy))
                self.selection = {(x, y) for x in range(x0, x1 + 1)
                                  for y in range(y0, y1 + 1)}
        self._sel_anchor = None
        self._sel_cur = None
        self.update()

    def mouseDoubleClickEvent(self, evt):
        # Double-click paints the pending spline (its first press already
        # placed the final point).
        if self.tool == "spline" and evt.button() == Qt.MouseButton.LeftButton:
            self.commit_spline()
            return
        super().mouseDoubleClickEvent(evt)

    def keyPressEvent(self, evt):
        # Canvas-level shortcuts so the embedded studio (no menu bar) gets
        # them too; in the standalone editor the menu actions fire first.
        if evt.modifiers() & Qt.KeyboardModifier.ControlModifier:
            key = evt.key()
            shift = bool(evt.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if key == Qt.Key.Key_U or (key == Qt.Key.Key_Z and not shift):
                self.undo()
                return
            if key in (Qt.Key.Key_Y, Qt.Key.Key_R) \
                    or (key == Qt.Key.Key_Z and shift):
                self.redo()
                return
            op = {Qt.Key.Key_H: "flip_v" if shift else "flip_h",
                  Qt.Key.Key_BracketRight: "rot_cw",
                  Qt.Key.Key_BracketLeft: "rot_ccw"}.get(key)
            if op:
                self.transform(op)
                return
        if self.tool == "spline" and self._spline_pts:
            if evt.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.commit_spline()
                return
            if evt.key() == Qt.Key.Key_Escape:
                self._clear_stroke()
                return
        if self.tool == "line" and self._line_anchor is not None \
                and evt.key() == Qt.Key.Key_Escape:
            self._clear_stroke()
            return
        if self.tool in ("select", "lasso") \
                and evt.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if evt.key() == Qt.Key.Key_C and self.copy_selection():
                return
            if evt.key() == Qt.Key.Key_V and self.paste_clipboard():
                return
        if self.tool in ("select", "lasso") and self.selection:
            delta = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                     Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)
                     }.get(evt.key())
            if delta:
                self.nudge_selection(*delta)
                return
            if evt.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selection()
                return
            if evt.key() == Qt.Key.Key_Escape:
                self._clear_selection()
                return
        super().keyPressEvent(evt)

    def wheelEvent(self, evt):
        # Ctrl + wheel zooms; a plain wheel falls through to the scroll area.
        if evt.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 2 if evt.angleDelta().y() > 0 else -2
            self.set_zoom(self.cell_px + step)
            evt.accept()
        else:
            evt.ignore()

    def _sym_cells(self, x, y):
        """The cell plus its 90/180/270 rotation partners when 4-fold symmetry
        is on (square grids only) — so painting one arm fills all four."""
        cells = [(x, y)]
        if self.symmetry:
            w, h = self.grid_size()
            if w == h:
                px, py = x, y
                for _ in range(3):
                    px, py = w - 1 - py, px      # 90 deg: (x,y) -> (w-1-y, x)
                    cells.append((px, py))
        return cells

    def _brush_cells(self, x, y):
        """The N x N block of cells the brush covers, centred on (x, y)."""
        n = self.brush_size
        off = n // 2
        return [(x - off + dx, y - off + dy)
                for dy in range(n) for dx in range(n)]

    def _paint(self, cell):
        new = "." if self.tool == "eraser" else self.active_char
        w, h = self.grid_size()
        changed = False
        for bx, by in self._brush_cells(*cell):
            for x, y in self._sym_cells(bx, by):
                if 0 <= x < w and 0 <= y < h and self.rows[y][x] != new:
                    self.rows[y][x] = new
                    changed = True
        if changed:
            self.update()
            self.modified.emit()

    def _flood(self, cell):
        x, y = cell
        w, h = self.grid_size()
        target = self.rows[y][x]
        repl = self.active_char
        if target == repl:
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if not (0 <= cx < w and 0 <= cy < h):
                continue
            if self.rows[cy][cx] != target:
                continue
            self.rows[cy][cx] = repl
            stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
        self.update()
        self.modified.emit()


class Editor(QMainWindow):
    def __init__(self, open_path=None):
        super().__init__()
        self.setWindowTitle("TechDeck Pixel Editor")
        self.path = None
        self.dirty = False

        self.canvas = Canvas()
        self.canvas.modified.connect(self._on_modified)
        self.canvas.cell_hovered.connect(self._on_hover)
        self.canvas.color_picked.connect(lambda ch: self._select_char(ch))
        self.canvas.palette_changed.connect(self._rebuild_swatches)
        self.canvas.layers_changed.connect(self._refresh_layers)
        self._syncing_layers = False

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("background:#1e1e1e;")

        root = QWidget()
        row = QHBoxLayout(root)
        row.addWidget(self._build_sidebar())
        row.addWidget(self.scroll, 1)
        row.addWidget(self._build_layers_panel())
        self.setCentralWidget(root)

        self._build_menu()
        self._rebuild_swatches()
        self._refresh_layers()
        self.statusBar().showMessage("Ready")
        self.resize(1180, 700)

        if open_path:
            self._open_path(Path(open_path))

    # ---- UI construction -----------------------------------------------------
    def _build_menu(self):
        bar = self.menuBar()
        filem = bar.addMenu("&File")
        for label, slot, sc in [
            ("New", self.new_file, "Ctrl+N"),
            ("Open...", self.open_file, "Ctrl+O"),
            ("Import Image...", self.import_image, "Ctrl+I"),
            ("Save", self.save_file, "Ctrl+S"),
            ("Save As...", self.save_file_as, "Ctrl+Shift+S"),
            ("Open as Layer...", self.open_as_layer, "Ctrl+Shift+O"),
            ("Save All Layers", self.save_all_layers, "Ctrl+Alt+S"),
            ("Copy as Python", self.copy_python, None),
        ]:
            act = filem.addAction(label, slot)
            if sc:
                act.setShortcut(sc)

        editm = bar.addMenu("&Edit")
        editm.addAction("Undo", self.canvas.undo).setShortcuts(
            [QKeySequence("Ctrl+Z"), QKeySequence("Ctrl+U")])
        editm.addAction("Redo", self.canvas.redo).setShortcuts(
            [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+R"),
             QKeySequence("Ctrl+Shift+Z")])
        editm.addSeparator()
        for label, op, sc in [
            ("Mirror Horizontal", "flip_h", "Ctrl+H"),
            ("Mirror Vertical", "flip_v", "Ctrl+Shift+H"),
            ("Rotate 90 CW", "rot_cw", "Ctrl+]"),
            ("Rotate 90 CCW", "rot_ccw", "Ctrl+["),
        ]:
            editm.addAction(label, lambda o=op: self._transform(o)).setShortcut(sc)
        editm.addSeparator()
        # Ctrl+R belongs to Redo now; Resize moved to Ctrl+Shift+R.
        editm.addAction("Resize (scale art)...", self.resize_canvas).setShortcut("Ctrl+Shift+R")
        editm.addAction("Reduce duplicate lines", self.reduce_lines)
        editm.addAction("Add / remove lines...", self.resize_edges)

    def _build_sidebar(self):
        side = QFrame()
        side.setFixedWidth(190)
        v = QVBoxLayout(side)

        v.addWidget(self._heading("Tools"))
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for name in ("pencil", "eraser", "fill", "eyedropper", "line", "spline",
                     "select", "lasso"):
            b = QPushButton(name.capitalize())
            b.setCheckable(True)
            b.clicked.connect(lambda _c, n=name: self._select_tool(n))
            self.tool_group.addButton(b)
            self.tool_buttons[name] = b
            v.addWidget(b)
        self.tool_buttons["pencil"].setChecked(True)

        urow = QHBoxLayout()
        undo_btn = QPushButton("Undo")
        redo_btn = QPushButton("Redo")
        undo_btn.clicked.connect(self.canvas.undo)
        redo_btn.clicked.connect(self.canvas.redo)
        urow.addWidget(undo_btn)
        urow.addWidget(redo_btn)
        v.addLayout(urow)

        v.addWidget(self._heading("Transform"))
        for pairs in (
            (("Mirror H", "flip_h", "Ctrl+H"), ("Mirror V", "flip_v", "Ctrl+Shift+H")),
            (("Rot CW", "rot_cw", "Ctrl+]"), ("Rot CCW", "rot_ccw", "Ctrl+[")),
        ):
            trow = QHBoxLayout()
            for label, op, sc in pairs:
                b = QPushButton(label)
                b.setToolTip(f"{label} ({sc}) — applies to the selection if "
                             "there is one, else the whole canvas")
                b.clicked.connect(lambda _c, o=op: self._transform(o))
                trow.addWidget(b)
            v.addLayout(trow)

        brow = QHBoxLayout()
        brow.addWidget(QLabel("Brush"))
        self.brush_spin = QSpinBox()
        self.brush_spin.setRange(1, 16)
        self.brush_spin.setValue(self.canvas.brush_size)
        self.brush_spin.setSuffix(" px")
        self.brush_spin.valueChanged.connect(
            lambda n: setattr(self.canvas, "brush_size", n))
        brow.addWidget(self.brush_spin)
        v.addLayout(brow)

        v.addWidget(self._heading("Palette"))
        # The swatches live in their OWN scroll area: a sprite imported from an
        # image can have dozens of colours, and stacking that many buttons
        # straight into the sidebar used to push the window taller than the
        # screen (hiding the canvas scrollbars + the buttons below).
        self.swatch_host = QWidget()
        self.swatch_box = QVBoxLayout(self.swatch_host)
        self.swatch_box.setContentsMargins(0, 0, 0, 0)
        self.swatch_box.setSpacing(3)
        pal_scroll = QScrollArea()
        pal_scroll.setWidgetResizable(True)
        pal_scroll.setWidget(self.swatch_host)
        pal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pal_scroll.setMinimumHeight(120)
        pal_scroll.setStyleSheet("QScrollArea { border: none; }")
        v.addWidget(pal_scroll, 1)   # absorbs spare space; scrolls when crowded
        prow = QHBoxLayout()
        add = QPushButton("+ Add")
        add.clicked.connect(self.add_color)
        editb = QPushButton("Edit")
        editb.setToolTip("Change the hex value of the selected palette color "
                         "(recolors every pixel using it)")
        editb.clicked.connect(self.edit_color)
        prow.addWidget(add)
        prow.addWidget(editb)
        v.addLayout(prow)

        v.addWidget(self._heading("View"))
        zrow = QHBoxLayout()
        zout = QPushButton("-")
        zin = QPushButton("+")
        zout.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px - 2))
        zin.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px + 2))
        zrow.addWidget(QLabel("Zoom"))
        zrow.addWidget(zout)
        zrow.addWidget(zin)
        v.addLayout(zrow)
        grid = QPushButton("Toggle Grid")
        grid.clicked.connect(self._toggle_grid)
        v.addWidget(grid)

        self.sym_btn = QPushButton("Symmetry: Off")
        self.sym_btn.setCheckable(True)
        self.sym_btn.setToolTip("4-fold rotation: paint one arm, all four mirror "
                                "(for spinners). Square grids only.")
        self.sym_btn.toggled.connect(self._toggle_symmetry)
        v.addWidget(self.sym_btn)
        return side

    # ---- layers panel --------------------------------------------------------
    def _build_layers_panel(self):
        """Stack list: topmost layer at the top, Photoshop-style.

        Multi-part sprites (a beyblade's top / bottom / centre) are edited here
        as they will be SEEN — overlapping on one canvas — while each part
        stays its own file and saves back to its own path.
        """
        side = QFrame()
        side.setFixedWidth(230)
        v = QVBoxLayout(side)
        v.addWidget(self._heading("Layers"))

        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.layer_list.currentRowChanged.connect(self._layer_row_selected)
        self.layer_list.itemChanged.connect(self._layer_item_changed)
        self.layer_list.model().rowsMoved.connect(self._layer_rows_moved)
        self.layer_list.setToolTip(
            "Click to make a layer active — painting always goes to the active "
            "layer.\nTick to show/hide. Double-click the name to rename. "
            "Drag to reorder.")
        v.addWidget(self.layer_list, 1)

        orow = QHBoxLayout()
        orow.addWidget(QLabel("Opacity"))
        self.op_slider = QSlider(Qt.Orientation.Horizontal)
        self.op_slider.setRange(0, 100)
        self.op_slider.setValue(100)
        self.op_slider.setToolTip("View-only — never affects what is saved.")
        self.op_slider.valueChanged.connect(self._layer_opacity_changed)
        self.op_label = QLabel("100%")
        self.op_label.setFixedWidth(38)
        orow.addWidget(self.op_slider, 1)
        orow.addWidget(self.op_label)
        v.addLayout(orow)

        for pairs in (
            (("Open as Layer...", self.open_as_layer),
             ("New Layer", self.new_layer)),
            (("Move Up", lambda: self._move_layer(-1)),
             ("Move Down", lambda: self._move_layer(1))),
            (("Duplicate", self.duplicate_layer),
             ("Delete", self.delete_layer)),
            (("Save Layer", self.save_layer),
             ("Save All Layers", self.save_all_layers)),
        ):
            row = QHBoxLayout()
            for label, slot in pairs:
                b = QPushButton(label)
                b.clicked.connect(slot)
                row.addWidget(b)
            v.addLayout(row)

        self.layer_path_lbl = QLabel("")
        self.layer_path_lbl.setWordWrap(True)
        self.layer_path_lbl.setStyleSheet("color:#888; font-size:10px;")
        v.addWidget(self.layer_path_lbl)
        return side

    def _refresh_layers(self):
        """Rebuild the list from the canvas stack (topmost first)."""
        self._syncing_layers = True
        self.layer_list.clear()
        for lay in reversed(self.canvas.layers):
            it = QListWidgetItem(lay.name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEditable)
            it.setCheckState(Qt.CheckState.Checked if lay.visible
                             else Qt.CheckState.Unchecked)
            if lay.dirty:
                it.setForeground(QColor("#e0b040"))
            self.layer_list.addItem(it)
        self.layer_list.setCurrentRow(self._row_of(self.canvas.active))
        self._sync_layer_meta()
        self._syncing_layers = False

    def _row_of(self, index):
        """Stack index -> list row (the list shows the stack reversed)."""
        return len(self.canvas.layers) - 1 - index

    def _layer_row_selected(self, row):
        if getattr(self, "_syncing_layers", False) or row < 0:
            return
        self.canvas.set_active(self._row_of(row))
        self._sync_layer_meta()      # NOT _refresh_layers -- see set_active

    def _sync_layer_meta(self):
        """Opacity/path widgets for the active layer, without touching the
        list (rebuilding it mid-drag would undo a reorder)."""
        lay = self.canvas.layer
        self.op_slider.blockSignals(True)
        self.op_slider.setValue(int(round(lay.opacity * 100)))
        self.op_slider.blockSignals(False)
        self.op_label.setText(f"{int(round(lay.opacity * 100))}%")
        self.layer_path_lbl.setText(
            str(lay.path) if lay.path else "(unsaved — Save Layer to give it a file)")

    def _layer_item_changed(self, item):
        if getattr(self, "_syncing_layers", False):
            return
        i = self._row_of(self.layer_list.row(item))
        if not (0 <= i < len(self.canvas.layers)):
            return
        lay = self.canvas.layers[i]
        lay.visible = item.checkState() == Qt.CheckState.Checked
        if item.text() and item.text() != lay.name:
            lay.name = item.text()
        self.canvas.update()

    def _layer_rows_moved(self, *_a):
        """Drag-reorder: rebuild the stack from the list order (reversed)."""
        if getattr(self, "_syncing_layers", False):
            return
        names = [self.layer_list.item(r).text()
                 for r in range(self.layer_list.count())]
        by_name = {lay.name: lay for lay in self.canvas.layers}
        if len(by_name) != len(self.canvas.layers):
            self._refresh_layers()      # duplicate names — can't map safely
            return
        active = self.canvas.layer
        self.canvas.layers = [by_name[n] for n in reversed(names)
                              if n in by_name]
        self.canvas.active = self.canvas.layers.index(active)
        self.canvas.update()
        self._refresh_layers()

    def _layer_opacity_changed(self, val):
        if getattr(self, "_syncing_layers", False):
            return
        self.canvas.layer.opacity = val / 100.0
        self.op_label.setText(f"{val}%")
        self.canvas.update()

    def _move_layer(self, delta):
        # list is reversed, so "up" in the list is +1 in the stack
        if self.canvas.move_layer(self.canvas.active, -delta):
            self._refresh_layers()

    def new_layer(self):
        self.canvas.add_layer()
        self._on_modified()

    def duplicate_layer(self):
        src = self.canvas.layer
        self.canvas.add_layer(f"{src.name} copy",
                              [list(r) for r in src.rows], dict(src.palette))
        self._on_modified()

    def delete_layer(self):
        lay = self.canvas.layer
        if lay.dirty and QMessageBox.question(
                self, "Delete layer",
                f"'{lay.name}' has unsaved edits. Delete it anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        if not self.canvas.remove_layer(self.canvas.active):
            QMessageBox.information(self, "Delete layer",
                                    "The last layer can't be deleted.")
            return
        self._on_modified()

    def open_as_layer(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "Open as layer", str(self._assets_dir()),
            "TechDeck Art (*.tdart)")
        if not fn:
            return
        path = Path(fn)
        try:
            data = pixel_art.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        _, padded = self.canvas.load_as_layer(data, path.stem, path)
        self._rebuild_swatches()
        self._refresh_layers()
        msg = f"Added layer '{path.stem}'"
        if padded:
            msg += " — canvas padded to fit (layers are never rescaled)"
        self.statusBar().showMessage(msg, 6000)

    def save_layer(self):
        lay = self.canvas.layer
        if lay.path is None:
            fn, _ = QFileDialog.getSaveFileName(
                self, f"Save layer '{lay.name}'",
                str(self._assets_dir() / f"{lay.name}.tdart"),
                "TechDeck Art (*.tdart)")
            if not fn:
                return
            lay.path = Path(fn)
        pixel_art.save(lay.path, lay.data())
        lay.dirty = False
        self._refresh_layers()
        self.statusBar().showMessage(f"Saved {lay.path}", 4000)

    def save_all_layers(self):
        """Write every layer back to its OWN file — the point of the stack."""
        saved, skipped = 0, []
        for lay in self.canvas.layers:
            if lay.path is None:
                skipped.append(lay.name)
                continue
            pixel_art.save(lay.path, lay.data())
            lay.dirty = False
            saved += 1
        self._refresh_layers()
        msg = f"Saved {saved} layer(s)"
        if skipped:
            msg += f" — no file yet for: {', '.join(skipped)} (use Save Layer)"
        self.statusBar().showMessage(msg, 8000)

    def _heading(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight:bold; margin-top:8px;")
        return lbl

    def _rebuild_swatches(self):
        while self.swatch_box.count():
            item = self.swatch_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for ch, hexval in self.canvas.palette.items():
            b = QPushButton(ch)
            b.setFixedHeight(24)
            selected = (ch == self.canvas.active_char)
            border = "3px solid #ffffff" if selected else "1px solid #555"
            b.setStyleSheet(
                f"background:{hexval}; color:{self._contrast(hexval)};"
                f"border:{border}; font-weight:bold;"
            )
            b.clicked.connect(lambda _c, c=ch: self._select_char(c))
            self.swatch_box.addWidget(b)

    @staticmethod
    def _contrast(hexval):
        c = QColor(hexval)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        return "#000000" if lum > 140 else "#ffffff"

    # ---- actions -------------------------------------------------------------
    def _select_tool(self, name):
        """Single source of truth for the active tool: sets it on the canvas
        AND syncs the toolbar button (by identity, not by label)."""
        self.canvas.tool = name
        btn = self.tool_buttons.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self.statusBar().showMessage(f"Tool: {name}")

    def _select_char(self, ch):
        self.canvas.active_char = ch
        # Picking a color means you want to draw with it, so leave any
        # non-painting tool (eraser/eyedropper/select/lasso) for the pencil.
        if self.canvas.tool in ("eraser", "eyedropper", "select", "lasso"):
            self._select_tool("pencil")
        self._rebuild_swatches()

    def _transform(self, op):
        self.statusBar().showMessage(self.canvas.transform(op))

    def resize_canvas(self):
        w, h = self.canvas.grid_size()
        nw, ok = QInputDialog.getInt(self, "Resize", "New width (cells):", w, 1, 256)
        if not ok:
            return
        nh, ok = QInputDialog.getInt(self, "Resize", "New height (cells):", h, 1, 256)
        if not ok or (nw, nh) == (w, h):
            return
        self.canvas.push_undo()
        self.canvas.resize_grid(nw, nh)
        if nw != nh and self.canvas.symmetry:
            self.sym_btn.setChecked(False)   # 4-fold needs a square canvas
        self.statusBar().showMessage(f"Resized to {nw}x{nh}")

    def _ask_sides(self, title):
        """Per-side SIGNED line-count dialog. Positive adds lines, negative
        removes them. Returns (top, bottom, left, right) or None on cancel."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        form = QFormLayout(dlg)
        hint = QLabel("Positive = add lines, negative = remove lines.")
        hint.setWordWrap(True)
        form.addRow(hint)
        spins = {}
        for side in ("Top", "Bottom", "Left", "Right"):
            sp = QSpinBox()
            sp.setRange(-256, 256)
            sp.setSuffix(" px")
            spins[side] = sp
            form.addRow(side, sp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return tuple(spins[s].value() for s in ("Top", "Bottom", "Left", "Right"))

    def resize_edges(self):
        """Add or remove rows/columns per side WITHOUT scaling. Each side takes a
        signed count: positive pads transparent lines, negative crops lines
        (art on removed lines is discarded). One undoable step."""
        sides = self._ask_sides("Add / remove lines")
        if sides is None or all(v == 0 for v in sides):
            return
        # split each side into its pad (>=0) and crop (>=0) magnitudes
        pad = tuple(max(v, 0) for v in sides)
        crop = tuple(-min(v, 0) for v in sides)
        self.canvas.push_undo()
        # crop first (so a mixed add/remove can't transiently over-grow), then pad
        if any(crop):
            if not self.canvas.crop_grid(*crop):
                self.canvas._undo.pop()   # nothing changed; drop the snapshot
                self.statusBar().showMessage(
                    "Refused - that would remove the whole canvas")
                return
        if any(pad):
            self.canvas.pad_grid(*pad)
        if self.canvas.symmetry and self.canvas.grid_size()[0] != self.canvas.grid_size()[1]:
            self.sym_btn.setChecked(False)   # 4-fold needs a square canvas
        w, h = self.canvas.grid_size()
        self.statusBar().showMessage(f"Canvas now {w}x{h}")

    def reduce_lines(self):
        self.canvas.push_undo()
        (ow, oh), (nw, nh) = self.canvas.reduce_duplicate_lines()
        if nw != nh and self.canvas.symmetry:
            self.sym_btn.setChecked(False)
        if (ow, oh) == (nw, nh):
            self.statusBar().showMessage("No duplicate adjacent lines to remove")
        else:
            self.statusBar().showMessage(f"Reduced {ow}x{oh} -> {nw}x{nh} (no distortion)")

    def _toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas.update()

    def _toggle_symmetry(self, on):
        w, h = self.canvas.grid_size()
        if on and w != h:
            self.sym_btn.setChecked(False)
            self.statusBar().showMessage("4-fold symmetry needs a square canvas")
            return
        self.canvas.symmetry = on
        self.sym_btn.setText("Symmetry: 4-fold" if on else "Symmetry: Off")
        self.canvas.update()

    def add_color(self):
        # DontUseNativeDialog: the native Windows colour picker leaves the
        # canvas QScrollArea in a stale state (scrollbar breaks until a manual
        # window resize). Qt's own dialog avoids that.
        c = QColorDialog.getColor(
            parent=self, title="Add palette color",
            options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():
            ch = self.canvas.add_color(c.name())
            if ch:
                self._select_char(ch)
        # Belt-and-suspenders: force the scroll area to recompute its scrollbars.
        self.canvas.updateGeometry()
        self.scroll.updateGeometry()

    def edit_color(self):
        """Recolor the SELECTED palette entry: pick a new hex and every pixel
        using that char repaints to it (the char/cells are untouched)."""
        ch = self.canvas.active_char
        cur = self.canvas.palette.get(ch)
        if cur is None:
            self.statusBar().showMessage("Select a palette color first")
            return
        c = QColorDialog.getColor(
            QColor(cur), self, f"Edit color '{ch}'",
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid() and c.name().lower() != cur.lower():
            self.canvas.palette[ch] = c.name()
            self.canvas.update()
            self._rebuild_swatches()
            self._on_modified()
            self.statusBar().showMessage(f"Recolored '{ch}' -> {c.name()}")
        self.canvas.updateGeometry()
        self.scroll.updateGeometry()

    def new_file(self):
        if not self._confirm_discard():
            return
        w, ok = QInputDialog.getInt(self, "New", "Width (cells):", 32, 1, 256)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "New", "Height (cells):", 32, 1, 256)
        if not ok:
            return
        self.canvas.new_grid(w, h)
        self.path = None
        self._mark_clean()

    def open_file(self):
        if not self._confirm_discard():
            return
        fn, _ = QFileDialog.getOpenFileName(
            self, "Open sprite", str(self._assets_dir()), "TechDeck Art (*.tdart)")
        if fn:
            self._open_path(Path(fn))

    def _open_path(self, path: Path):
        try:
            self.canvas.load(pixel_art.load(path), name=path.stem, path=path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.path = path
        self._rebuild_swatches()
        self._refresh_layers()
        self._mark_clean()

    def import_image(self):
        """Bring in a PNG/JPEG of pixel art: auto-detect its pixel block size,
        downsample so 1 source pixel = 1 editor cell, and build a palette."""
        if not self._confirm_discard():
            return
        fn, _ = QFileDialog.getOpenFileName(
            self, "Import pixel-art image", str(self._assets_dir()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not fn:
            return
        img = QImage(fn)
        if img.isNull():
            QMessageBox.critical(self, "Import failed", "Could not read that image.")
            return
        detected = detect_pixel_scale(img)
        block, ok = QInputDialog.getInt(
            self, "Pixel size",
            "How many real pixels = one art pixel?\n(auto-detected; adjust if needed)",
            detected, 1, 256)
        if not ok:
            return
        nw, nh = max(1, img.width() // block), max(1, img.height() // block)
        if nw > 256 or nh > 256:
            r = QMessageBox.question(
                self, "Large canvas",
                f"This will create a {nw}x{nh} grid, which is big and slow to edit.\n"
                "Continue? (A larger pixel size makes it smaller.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        data, note = image_to_tdart(img, block)
        self.canvas.load(data)
        self._rebuild_swatches()
        self.path = None
        self._mark_clean()
        w, h = self.canvas.grid_size()
        self.statusBar().showMessage(
            f"Imported {w}x{h}, {len(self.canvas.palette)} colors"
            + (f" — {note}" if note else "") + ". Save As .tdart to keep it.")

    def save_file(self):
        if self.path is None:
            return self.save_file_as()
        self._write(self.path)

    def save_file_as(self):
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save sprite", str(self._assets_dir()), "TechDeck Art (*.tdart)")
        if not fn:
            return
        if not fn.endswith(".tdart"):
            fn += ".tdart"
        self.path = Path(fn)
        self._write(self.path)

    def _write(self, path: Path):
        """Ctrl+S writes the flattened composite. Individual sheets are saved
        with Save Layer / Save All Layers, each back to its own file."""
        try:
            pixel_art.save(path, self.canvas.export())
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        self._mark_clean()
        self.statusBar().showMessage(f"Saved {path.name}")

    def copy_python(self):
        data = self.canvas.export()
        pal = ",\n".join(f'    "{c}": "{h}"' for c, h in data["palette"].items())
        art = ",\n".join(f'    "{r}"' for r in data["rows"])
        snippet = f"PALETTE = {{\n{pal}\n}}\n\nART = [\n{art}\n]\n"
        QApplication.clipboard().setText(snippet)
        self.statusBar().showMessage("Python snippet copied to clipboard")

    # ---- helpers -------------------------------------------------------------
    def _assets_dir(self):
        # Default browse location for Open/Import/Save. Points at the pixel-art
        # playground (icon sources live there) rather than the app's assets tree.
        return Path(__file__).resolve().parent / "pixel_playground"

    def _on_modified(self):
        self.canvas.layer.dirty = True
        self._refresh_layers()
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _on_hover(self, x, y):
        w, h = self.canvas.grid_size()
        self.statusBar().showMessage(f"{w}x{h}   cell ({x},{y})   active '{self.canvas.active_char}'")

    def _mark_clean(self):
        self.dirty = False
        self._update_title()

    def _update_title(self):
        name = self.path.name if self.path else "untitled"
        self.setWindowTitle(f"TechDeck Pixel Editor — {name}{'*' if self.dirty else ''}")

    def _confirm_discard(self):
        if not self.dirty:
            return True
        r = QMessageBox.question(
            self, "Discard changes?",
            "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return r == QMessageBox.StandardButton.Yes

    def closeEvent(self, evt):
        evt.accept() if self._confirm_discard() else evt.ignore()


def main():
    app = QApplication(sys.argv)
    open_path = sys.argv[1] if len(sys.argv) > 1 else None
    ed = Editor(open_path)
    ed.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
