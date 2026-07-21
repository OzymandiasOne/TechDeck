"""
Pixel Studio — the unified TechDeck pixel-art workbench (embeddable).

One surface that hosts every art-authoring workflow. A top bar carries the
active mode's file/actions on the left and the MODE selector on the right;
each mode swaps the working surface + preview + export target:

    Sprite      .tdart sprites (this phase)          -> reuses pixel_editor.Canvas
    Tile Icon   plugin tile icons + live per-theme    (next phase)
                preview across every colour scheme
    Placement   garden/house furniture, Buddy &       (next phase)
                item animations, nav graph

Sprite mode flanks the canvas with tools on the left and the palette on the
right so the grid stays centred. It mounts inside the DevKit page (source
builds only) and long-term supersedes the standalone tools/*.py editors (still
runnable during the migration). The pixel ENGINE (grid model, undo, paint,
palette ops, .tdart load/save) is reused from pixel_editor.Canvas — only the
surrounding UI is re-expressed here for embedding.
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
    """.tdart authoring: the reused Canvas engine, flanked by a tools rail
    (left) and the palette (right) so the grid stays centred. Its file actions
    live in `action_bar`, which the studio hosts in the shared top bar."""

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

        # File actions — hosted by the studio's top bar (not this panel).
        self.action_bar = self._build_action_bar()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_tools_rail())
        body.addWidget(self.scroll, 1)
        body.addWidget(self._build_palette_rail())
        root.addLayout(body, 1)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self.status)

        self._rebuild_swatches()

    # ---- construction --------------------------------------------------------
    def _build_action_bar(self):
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for label, slot in (
            ("New", self._new), ("Open...", self._open),
            ("Save", self._save), ("Save As...", self._save_as),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        return bar

    def _build_tools_rail(self):
        side = QFrame()
        side.setFixedWidth(150)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

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
        v.addStretch()
        return side

    def _build_palette_rail(self):
        side = QFrame()
        side.setFixedWidth(150)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(self._heading("Palette"))
        self.swatch_host = QWidget()
        self.swatch_box = QVBoxLayout(self.swatch_host)
        self.swatch_box.setContentsMargins(0, 0, 0, 0)
        self.swatch_box.setSpacing(3)
        pal_scroll = QScrollArea()
        pal_scroll.setWidgetResizable(True)
        pal_scroll.setWidget(self.swatch_host)
        pal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        return side

    @staticmethod
    def _heading(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
        return lbl

    # ---- palette -------------------------------------------------------------
    def _rebuild_swatches(self):
        while self.swatch_box.count():
            item = self.swatch_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for ch, hexval in self.canvas.palette.items():
            # No text — just the colour; a white border marks the selection.
            b = QPushButton()
            b.setFixedHeight(22)
            b.setToolTip(hexval)
            selected = (ch == self.canvas.active_char)
            border = "3px solid #ffffff" if selected else "1px solid #555"
            b.setStyleSheet(f"background:{hexval}; border:{border}; border-radius:4px;")
            b.clicked.connect(lambda _c, c=ch: self._select_char(c))
            self.swatch_box.addWidget(b)
        self.swatch_box.addStretch()

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
        self.action_bar = QWidget()   # nothing in the top bar yet
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
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
    """Top bar (active-mode actions on the left, MODE selector right-aligned)
    over a stack of mode panels."""

    _MODES = [
        ("Sprite", "sprite"),
        ("Tile Icon", "icon"),
        ("Placement", "placement"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Top bar: [ active-mode actions ] ....... [ Sprite | Tile Icon | Placement ]
        top = QHBoxLayout()
        top.setSpacing(8)
        self.action_host = QStackedWidget()
        self.action_host.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        top.addWidget(self.action_host)
        top.addStretch()

        self._mode_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        for i, (label, key) in enumerate(self._MODES):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, idx=i: self._set_mode(idx))
            self._mode_group.addButton(btn)
            top.addWidget(btn)

            panel = self._make_panel(key)
            self.stack.addWidget(panel)
            self.action_host.addWidget(panel.action_bar)

        root.addLayout(top)
        root.addWidget(self.stack, 1)

        self._set_mode(0)

    def _set_mode(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.action_host.setCurrentIndex(idx)
        self._mode_group.buttons()[idx].setChecked(True)

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
