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
from PySide6.QtGui import QPainter, QColor, QPixmap

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

    def _paint(self, cell):
        x, y = cell
        new = "." if self.tool == "eraser" else self.active_char
        if self.rows[y][x] != new:
            self.rows[y][x] = new
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
