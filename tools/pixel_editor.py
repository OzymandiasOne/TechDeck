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
        Eyedropper (pick a cell's color as active).
Mouse:  left-drag paints. The checkerboard shows transparency.
Files:  New (set size) · Open · Save / Save As (.tdart) · Copy as Python
        (puts a PALETTE + ART snippet on the clipboard for legacy widgets).
"""

import sys
from pathlib import Path

# Allow `from techdeck...` when run directly from the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QColorDialog, QInputDialog,
    QScrollArea, QMessageBox, QButtonGroup, QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPixmap, QImage

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


class Canvas(QWidget):
    """The editable pixel grid."""

    cell_hovered = Signal(int, int)
    color_picked = Signal(str)   # emits a palette char when the eyedropper hits
    modified = Signal()

    def __init__(self, w=32, h=32, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.cell_px = 16
        self.show_grid = True
        self.symmetry = False     # 4-fold rotational mirror for spinners
        self.tool = "pencil"
        self.active_char = "k"
        self.palette = dict(_DEFAULT_PALETTE)
        self.rows = [["." for _ in range(w)] for _ in range(h)]
        self._undo = []
        self._redo = []
        self._resize_to_grid()

    # ---- model ---------------------------------------------------------------
    def grid_size(self):
        return (len(self.rows[0]) if self.rows else 0, len(self.rows))

    def new_grid(self, w, h):
        self.rows = [["." for _ in range(w)] for _ in range(h)]
        self._undo.clear()
        self._redo.clear()
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def load(self, data):
        data = pixel_art.normalize(data)
        self.palette = dict(data["palette"]) or dict(_DEFAULT_PALETTE)
        self.rows = [list(r) for r in data["rows"]]
        if not self.rows:
            self.rows = [["." for _ in range(32)] for _ in range(32)]
        # Make sure the active char still exists.
        if self.active_char not in self.palette:
            self.active_char = next(iter(self.palette), "k")
        self._undo.clear()
        self._redo.clear()
        self._resize_to_grid()
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
        self._redo.append(self._snapshot())
        self.rows = self._undo.pop()
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self.rows = self._redo.pop()
        self._resize_to_grid()
        self.update()
        self.modified.emit()

    def export(self):
        return {
            "palette": dict(self.palette),
            "rows": ["".join(r) for r in self.rows],
        }

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

    def paintEvent(self, _evt):
        p = QPainter(self)
        cp = self.cell_px
        w, h = self.grid_size()
        light = QColor("#3a3a3a")
        dark = QColor("#2c2c2c")
        for y in range(h):
            for x in range(w):
                ch = self.rows[y][x]
                if ch in pixel_art.TRANSPARENT_CHARS or ch not in self.palette:
                    p.fillRect(x * cp, y * cp, cp, cp,
                               light if (x + y) % 2 == 0 else dark)
                else:
                    p.fillRect(x * cp, y * cp, cp, cp, QColor(self.palette[ch]))
        if self.show_grid and cp >= 6:
            p.setPen(QColor(0, 0, 0, 60))
            for x in range(w + 1):
                p.drawLine(x * cp, 0, x * cp, h * cp)
            for y in range(h + 1):
                p.drawLine(0, y * cp, w * cp, y * cp)
        p.end()

    # ---- interaction ---------------------------------------------------------
    def _cell_at(self, pos):
        x, y = pos.x() // self.cell_px, pos.y() // self.cell_px
        w, h = self.grid_size()
        if 0 <= x < w and 0 <= y < h:
            return int(x), int(y)
        return None

    def mousePressEvent(self, evt):
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
        if cell and (evt.buttons() & Qt.MouseButton.LeftButton) \
                and self.tool in ("pencil", "eraser"):
            self._paint(cell)

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

    def _paint(self, cell):
        new = "." if self.tool == "eraser" else self.active_char
        w, h = self.grid_size()
        changed = False
        for x, y in self._sym_cells(*cell):
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

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setStyleSheet("background:#1e1e1e;")

        root = QWidget()
        row = QHBoxLayout(root)
        row.addWidget(self._build_sidebar())
        row.addWidget(scroll, 1)
        self.setCentralWidget(root)

        self._build_menu()
        self._rebuild_swatches()
        self.statusBar().showMessage("Ready")
        self.resize(900, 640)

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
            ("Copy as Python", self.copy_python, None),
        ]:
            act = filem.addAction(label, slot)
            if sc:
                act.setShortcut(sc)

        editm = bar.addMenu("&Edit")
        editm.addAction("Undo", self.canvas.undo).setShortcut("Ctrl+Z")
        editm.addAction("Redo", self.canvas.redo).setShortcut("Ctrl+Y")

    def _build_sidebar(self):
        side = QFrame()
        side.setFixedWidth(190)
        v = QVBoxLayout(side)

        v.addWidget(self._heading("Tools"))
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for name in ("pencil", "eraser", "fill", "eyedropper"):
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

        v.addWidget(self._heading("Palette"))
        self.swatch_box = QVBoxLayout()
        v.addLayout(self.swatch_box)
        add = QPushButton("+ Add Color")
        add.clicked.connect(self.add_color)
        v.addWidget(add)

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

        v.addStretch()
        return side

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
        # non-painting tool (eraser/eyedropper) and return to the pencil.
        if self.canvas.tool in ("eraser", "eyedropper"):
            self._select_tool("pencil")
        self._rebuild_swatches()

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
        c = QColorDialog.getColor(parent=self, title="Add palette color")
        if c.isValid():
            ch = self.canvas.add_color(c.name())
            if ch:
                self._select_char(ch)

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
            self.canvas.load(pixel_art.load(path))
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.path = path
        self._rebuild_swatches()
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
        return Path(__file__).resolve().parents[1] / "assets"

    def _on_modified(self):
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
