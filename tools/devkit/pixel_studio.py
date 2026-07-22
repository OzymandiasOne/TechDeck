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
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton, QLabel,
    QScrollArea, QButtonGroup, QFrame, QStackedWidget, QComboBox,
    QFileDialog, QColorDialog, QMessageBox, QInputDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QByteArray
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from techdeck.ui import pixel_art
from tools.pixel_editor import Canvas, _DEFAULT_PALETTE, _CHAR_POOL


def _playground_dir() -> Path:
    """Default browse location — the icon-source working area, matching the
    standalone editors so files land in one place."""
    return Path(__file__).resolve().parents[1] / "pixel_playground"


# Tool glyphs — Feather/Lucide-style stroke paths, rendered + tinted at build.
_TOOL_ICONS = {
    "pencil": [
        "M12 20h9",
        "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z",
    ],
    "eraser": [
        "m7 21-4.3-4.3a1 1 0 0 1 0-1.4l10-10a1 1 0 0 1 1.4 0l4.3 4.3"
        "a1 1 0 0 1 0 1.4L13 21",
        "M22 21H7",
    ],
    "fill": ["M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"],
    "eyedropper": [
        "M2 22l1-1h3l9-9",
        "M3 21v-3l9-9",
        "M14 6l4 4 3-3a2.83 2.83 0 0 0-4-4l-3 3z",
    ],
}

# Undo / redo as back / forward arrows.
_NAV_ICONS = {
    "undo": ["M19 12H5", "M12 19l-7-7 7-7"],
    "redo": ["M5 12h14", "M12 5l7 7-7 7"],
}


def _svg_icon(paths, color: str, size: int = 22) -> QIcon:
    """Build a tinted QIcon from a list of stroke path 'd' strings."""
    body = "".join(
        f'<path d="{d}" stroke="{color}" stroke-width="2" fill="none" '
        f'stroke-linecap="round" stroke-linejoin="round"/>' for d in paths)
    svg = f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


# Preset palettes for the Sprite palette dropdown. None = the editor default.
_PRESETS = {
    "Default": None,
    "PICO-8": [
        "#000000", "#1D2B53", "#7E2553", "#008751", "#AB5236", "#5F574F",
        "#C2C3C7", "#FFF1E8", "#FF004D", "#FFA300", "#FFEC27", "#00E436",
        "#29ADFF", "#83769C", "#FF77A8", "#FFCCAA",
    ],
    "Sweetie-16": [
        "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070",
        "#38b764", "#257179", "#29366f", "#3b5dc9", "#41a6f6", "#73eff7",
        "#f4f4f4", "#94b0c2", "#566c86", "#333c57",
    ],
    "Grayscale": ["#000000", "#333333", "#666666", "#999999", "#cccccc", "#ffffff"],
}


# ── Sprite mode ─────────────────────────────────────────────────────────────
class _SpritePanel(QWidget):
    """.tdart authoring: the reused Canvas engine, flanked by a tools rail
    (left) and the palette (right) so the grid stays centred. Its file actions
    live in `action_bar`, which the studio hosts in the shared top bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: "Path | None" = None

        from techdeck.ui.theme_manager import get_theme_manager
        pal = get_theme_manager().get_current_palette()
        self._icon_color = pal.text
        self._accent = pal.accent

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
        side.setFixedWidth(140)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(self._heading("Tools"))
        # Drawing tools as a 2-column icon grid; the name shows on hover.
        tool_style = f"""
            QPushButton {{ background: transparent; border: 1px solid #444;
                           border-radius: 6px; }}
            QPushButton:hover {{ background: rgba(127, 127, 127, 0.15); }}
            QPushButton:checked {{ background: rgba(127, 127, 127, 0.28);
                                   border: 2px solid {self._accent}; }}
        """
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for i, name in enumerate(("pencil", "eraser", "fill", "eyedropper")):
            b = QPushButton()
            b.setCheckable(True)
            b.setIcon(_svg_icon(_TOOL_ICONS[name], self._icon_color))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(44, 44)
            b.setToolTip(name.capitalize())
            b.setStyleSheet(tool_style)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, n=name: self._select_tool(n))
            self.tool_group.addButton(b)
            self.tool_buttons[name] = b
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(2, 1)   # keep the two icon columns left-packed
        v.addLayout(grid)
        self.tool_buttons["pencil"].setChecked(True)

        # Undo / Redo as back / forward arrow icons.
        nav_style = """
            QPushButton { background: transparent; border: 1px solid #444;
                          border-radius: 6px; }
            QPushButton:hover { background: rgba(127, 127, 127, 0.15); }
        """
        urow = QHBoxLayout()
        urow.setSpacing(4)
        for name, slot in (("undo", self.canvas.undo), ("redo", self.canvas.redo)):
            b = QPushButton()
            b.setIcon(_svg_icon(_NAV_ICONS[name], self._icon_color, 22))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(44, 44)   # same box as the tool icons
            b.setToolTip(name.capitalize())
            b.setStyleSheet(nav_style)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            urow.addWidget(b)
        urow.addStretch()
        v.addLayout(urow)

        v.addStretch()

        # View controls pinned to the bottom of the rail so they line up with
        # the palette's Add/Edit row on the other side of the canvas.
        v.addWidget(self._heading("View"))
        zbtn_style = "QPushButton { padding: 2px; font-size: 15px; font-weight: bold; }"
        zrow = QHBoxLayout()
        zrow.setSpacing(4)
        zrow.addWidget(QLabel("Zoom"))
        zout = QPushButton("-")
        zin = QPushButton("+")
        for zb in (zout, zin):
            zb.setFixedSize(32, 28)
            zb.setStyleSheet(zbtn_style)
        zout.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px - 2))
        zin.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.cell_px + 2))
        zrow.addWidget(zout)
        zrow.addWidget(zin)
        zrow.addStretch()
        v.addLayout(zrow)
        gbtn = QPushButton("Toggle Grid")
        gbtn.clicked.connect(self._toggle_grid)
        v.addWidget(gbtn)
        return side

    def _build_palette_rail(self):
        side = QFrame()
        side.setFixedWidth(150)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(self._heading("Palette"))
        # Preset palettes sit above the swatches.
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("Load a preset palette")
        self.preset_combo.addItems(list(_PRESETS.keys()))
        v.addWidget(self.preset_combo)

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
        # Connect AFTER the items are added so the initial population — which
        # emits currentTextChanged once — doesn't clobber the canvas palette.
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        return side

    def _apply_preset(self, name: str):
        """Replace the working palette with a preset. Existing pixels keep
        their chars; any not in the new palette render transparent."""
        hexes = _PRESETS.get(name)
        if hexes is None:
            pal = dict(_DEFAULT_PALETTE)
        else:
            pal = {}
            chars = iter(_CHAR_POOL)
            for hx in hexes:
                ch = next(chars, None)
                if ch is None:
                    break
                pal[ch] = hx
        self.canvas.palette = pal
        self.canvas.active_char = next(iter(pal), "k")
        self.canvas.update()
        self._rebuild_swatches()

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
