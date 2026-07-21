"""
Pixel Studio — the unified TechDeck pixel-art workbench (embeddable).

One surface that hosts every art-authoring workflow behind a left-hand MODE
rail, each mode swapping the working surface + preview + export target:

    Sprite      .tdart sprites (this phase)          -> reuses pixel_editor.Canvas
    Tile Icon   plugin tile icons + live per-theme    (next phase)
                preview across every colour scheme
    Placement   garden/house furniture, Buddy &       (next phase)
                item animations, nav graph

It mounts inside Settings > DevKit (source builds only). Long-term this
supersedes the standalone tools/*.py editors; they stay runnable during the
migration. The pixel ENGINE (grid model, undo, paint, palette ops, .tdart
load/save) is reused from pixel_editor.Canvas — only the surrounding UI is
re-expressed here for embedding.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QScrollArea,
    QButtonGroup, QFrame, QStackedWidget, QFileDialog, QColorDialog,
    QMessageBox, QInputDialog, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from techdeck.ui import pixel_art
from tools.pixel_editor import Canvas


def _playground_dir() -> Path:
    """Default browse location — the icon-source working area, matching the
    standalone editors so files land in one place."""
    return Path(__file__).resolve().parents[1] / "pixel_playground"


# ── Sprite mode ─────────────────────────────────────────────────────────────
class _SpritePanel(QWidget):
    """.tdart authoring: the reused Canvas engine plus a compact sidebar and
    file actions. Equivalent to the standalone pixel_editor, embeddable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: "Path | None" = None

        self.canvas = Canvas()
        self.canvas.color_picked.connect(self._on_pick)
        self.canvas.cell_hovered.connect(self._on_hover)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background: #1e1e1e; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addLayout(self._build_file_row())
        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_sidebar())
        body.addWidget(self.scroll, 1)
        root.addLayout(body, 1)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.status)

        self._rebuild_swatches()

    # ---- construction --------------------------------------------------------
    def _build_file_row(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        for label, slot in (
            ("New", self._new), ("Open...", self._open),
            ("Save", self._save), ("Save As...", self._save_as),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        return row

    def _build_sidebar(self):
        side = QFrame()
        side.setFixedWidth(180)
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
        for label, slot in (("Undo", self.canvas.undo), ("Redo", self.canvas.redo)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            urow.addWidget(b)
        v.addLayout(urow)

        v.addWidget(self._heading("Palette"))
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
        v.addWidget(pal_scroll, 1)
        prow = QHBoxLayout()
        add = QPushButton("+ Add")
        add.clicked.connect(self._add_color)
        editb = QPushButton("Edit")
        editb.setToolTip("Recolor the selected palette entry (repaints every "
                         "pixel using it)")
        editb.clicked.connect(self._edit_color)
        prow.addWidget(add)
        prow.addWidget(editb)
        v.addLayout(prow)

        v.addWidget(self._heading("View"))
        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("Zoom"))
        zout = QPushButton("-")
        zin = QPushButton("+")
        zout.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px - 2))
        zin.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px + 2))
        zrow.addWidget(zout)
        zrow.addWidget(zin)
        v.addLayout(zrow)
        grid = QPushButton("Toggle Grid")
        grid.clicked.connect(self._toggle_grid)
        v.addWidget(grid)
        return side

    @staticmethod
    def _heading(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        return lbl

    # ---- palette -------------------------------------------------------------
    def _rebuild_swatches(self):
        while self.swatch_box.count():
            item = self.swatch_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for ch, hexval in self.canvas.palette.items():
            b = QPushButton(ch)
            b.setFixedHeight(22)
            selected = (ch == self.canvas.active_char)
            border = "3px solid #ffffff" if selected else "1px solid #555"
            b.setStyleSheet(
                f"background:{hexval}; color:{self._contrast(hexval)};"
                f"border:{border}; font-weight:bold;")
            b.clicked.connect(lambda _c, c=ch: self._select_char(c))
            self.swatch_box.addWidget(b)

    @staticmethod
    def _contrast(hexval):
        c = QColor(hexval)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        return "#000000" if lum > 140 else "#ffffff"

    def _select_char(self, ch):
        self.canvas.active_char = ch
        if self.canvas.tool in ("eraser", "eyedropper"):
            self._select_tool("pencil")
        self._rebuild_swatches()

    def _select_tool(self, name):
        self.canvas.tool = name
        btn = self.tool_buttons.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self.status.setText(f"Tool: {name}")

    def _add_color(self):
        c = QColorDialog.getColor(
            parent=self, title="Add palette color",
            options=QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid():
            ch = self.canvas.add_color(c.name())
            if ch:
                self._select_char(ch)

    def _edit_color(self):
        ch = self.canvas.active_char
        cur = self.canvas.palette.get(ch)
        if cur is None:
            self.status.setText("Select a palette color first")
            return
        c = QColorDialog.getColor(
            QColor(cur), self, f"Edit color '{ch}'",
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if c.isValid() and c.name().lower() != cur.lower():
            self.canvas.palette[ch] = c.name()
            self.canvas.update()
            self._rebuild_swatches()
            self.status.setText(f"Recolored '{ch}' -> {c.name()}")

    def _toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas.update()

    # ---- signals -------------------------------------------------------------
    def _on_pick(self, ch):
        self._select_char(ch)

    def _on_hover(self, x, y):
        w, h = self.canvas.grid_size()
        self.status.setText(
            f"{w}x{h}   cell ({x},{y})   active '{self.canvas.active_char}'")

    # ---- files ---------------------------------------------------------------
    def _new(self):
        w, ok = QInputDialog.getInt(self, "New", "Width (cells):", 32, 1, 256)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "New", "Height (cells):", 32, 1, 256)
        if not ok:
            return
        self.canvas.new_grid(w, h)
        self.path = None
        self._rebuild_swatches()
        self.status.setText(f"New {w}x{h}")

    def _open(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "Open sprite", str(_playground_dir()), "TechDeck Art (*.tdart)")
        if not fn:
            return
        try:
            self.canvas.load(pixel_art.load(Path(fn)))
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.path = Path(fn)
        self._rebuild_swatches()
        self.status.setText(f"Opened {self.path.name}")

    def _save(self):
        if self.path is None:
            return self._save_as()
        self._write(self.path)

    def _save_as(self):
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save sprite", str(_playground_dir()), "TechDeck Art (*.tdart)")
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
        self.status.setText(f"Saved {path.name}")


# ── stub modes (built out in later phases) ──────────────────────────────────
class _StubPanel(QWidget):
    def __init__(self, title: str, blurb: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 40, 40, 40)
        v.setSpacing(10)
        head = QLabel(title)
        head.setStyleSheet("font-size: 20px; font-weight: bold;")
        v.addWidget(head)
        desc = QLabel(blurb)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 13px;")
        v.addWidget(desc)
        v.addStretch()


# ── the studio shell ────────────────────────────────────────────────────────
class PixelStudio(QWidget):
    """Mode rail + stacked panels. The rail selects the active authoring mode."""

    _MODES = [
        ("Sprite", "sprite"),
        ("Tile Icon", "icon"),
        ("Placement", "placement"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # Left mode rail.
        rail = QFrame()
        rail.setFixedWidth(130)
        rail.setStyleSheet("QFrame { border-right: 1px solid #333; }")
        rv = QVBoxLayout(rail)
        rv.setContentsMargins(8, 12, 8, 12)
        rv.setSpacing(6)
        rv.addWidget(self._heading("Mode"))
        self._mode_group = QButtonGroup(self)
        self.stack = QStackedWidget()

        for i, (label, key) in enumerate(self._MODES):
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _c, idx=i: self.stack.setCurrentIndex(idx))
            self._mode_group.addButton(b)
            rv.addWidget(b)
            self.stack.addWidget(self._make_panel(key))
        rv.addStretch()

        row.addWidget(rail)
        row.addWidget(self.stack, 1)

        self._mode_group.buttons()[0].setChecked(True)
        self.stack.setCurrentIndex(0)

    @staticmethod
    def _heading(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold;")
        return lbl

    def _make_panel(self, key: str) -> QWidget:
        if key == "sprite":
            return _SpritePanel()
        if key == "icon":
            return _StubPanel(
                "Tile Icon",
                "Standard-size icon canvas with a live per-theme preview grid "
                "(every colour scheme except Professional), plus save-to-"
                "generator and a style lint. Lands in the next phase.")
        return _StubPanel(
            "Placement",
            "Drag-to-place garden/house furniture, Buddy and item animations, "
            "and the nav graph, with coordinate export. Lands in the next phase.")
