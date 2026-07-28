"""
Pixel Studio — the unified TechDeck pixel-art workbench (embeddable).

One surface that hosts every art-authoring workflow. A top bar carries the
active mode's file/actions on the left and the MODE selector on the right;
each mode swaps the working surface + preview + export target:

    Sprite      .tdart sprites                        -> reuses pixel_editor.Canvas
    Tile Icon   plugin tile icons with a LIVE         -> reuses the tile-icon
                per-theme preview (every colour          generator's recolor +
                scheme except Professional) +            icon_editor's save-to-
                save-to-generator                        script contract
    Placement   garden/house furniture, Buddy &       (next phase)
                item animations, nav graph

Sprite and Tile Icon share the canvas/tools/palette via _CanvasPanel; Tile Icon
locks the canvas to 32x32 and adds the preview column. It mounts inside the
DevKit page (source builds only) and long-term supersedes the standalone
tools/*.py editors. The pixel ENGINE (grid model, undo, paint, palette ops,
.tdart load/save) is reused from pixel_editor.Canvas.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton, QLabel,
    QScrollArea, QButtonGroup, QFrame, QStackedWidget, QComboBox,
    QFileDialog, QColorDialog, QMessageBox, QInputDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QByteArray, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from techdeck.ui import pixel_art
from techdeck.ui.theme_aware import ThemeAware
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
    # Marquee: corner brackets (scan-style) read as a selection rectangle.
    "select": [
        "M3 7V5a2 2 0 0 1 2-2h2",
        "M17 3h2a2 2 0 0 1 2 2v2",
        "M21 17v2a2 2 0 0 1-2 2h-2",
        "M7 21H5a2 2 0 0 1-2-2v-2",
    ],
    # Lasso: freeform loop with a rope tail + cinch ring.
    "lasso": [
        "M3.3 14A6.8 6.8 0 0 1 2 10c0-4.4 4.5-8 10-8s10 3.6 10 8"
        "-4.5 8-10 8a12 12 0 0 1-5-1",
        "M7 22a5 5 0 0 1-2-4",
        "M2 18a3 3 0 1 0 6 0a3 3 0 1 0 -6 0",
    ],
}

_TOOL_TIPS = {
    "select": "Select (rectangle) — drag inside the selection to move its "
              "pixels; Ctrl+C/Ctrl+V copy/paste, arrows nudge, Del clears, "
              "Esc deselects",
    "lasso": "Lasso (freeform) — close a loop to select; drag inside to move "
             "its pixels; Ctrl+C/Ctrl+V copy/paste",
}

# Undo / redo as back / forward arrows, plus the mirror/rotate transforms
# (Lucide flip-horizontal / flip-vertical / rotate-cw / rotate-ccw).
_NAV_ICONS = {
    "undo": ["M19 12H5", "M12 19l-7-7 7-7"],
    "redo": ["M5 12h14", "M12 5l7 7-7 7"],
    "flip_h": [
        "M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3",
        "M16 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3",
        "M12 20v2", "M12 14v2", "M12 8v2", "M12 2v2",
    ],
    "flip_v": [
        "M21 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v3",
        "M21 16v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3",
        "M4 12H2", "M10 12H8", "M16 12h-2", "M22 12h-2",
    ],
    "rot_cw": [
        "M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8",
        "M21 3v5h-5",
    ],
    "rot_ccw": [
        "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
        "M3 3v5h5",
    ],
}

_NAV_TIPS = {
    "undo": "Undo (Ctrl+Z / Ctrl+U)",
    "redo": "Redo (Ctrl+Y)",
    "flip_h": "Mirror horizontally (Ctrl+H) — selection if present, else canvas",
    "flip_v": "Mirror vertically (Ctrl+Shift+H) — selection if present, else canvas",
    "rot_cw": "Rotate 90 CW (Ctrl+]) — selection if present, else canvas",
    "rot_ccw": "Rotate 90 CCW (Ctrl+[) — selection if present, else canvas",
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


# Preset palettes for the palette dropdown. None = the editor default.
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


# ── tile-icon preview helpers ────────────────────────────────────────────────
def _recolor_tones(tones: dict, theme_name: str) -> dict:
    """Map a {char: hex} tone set onto a theme's PICO-8 subset by luminance
    rank — the exact transform the tile-icon generator uses, so the preview is
    faithful. Returns the recolored {char: hex} for that theme."""
    from tools.generate_tile_icons_32 import (
        _hex, _build_map, THEME_PALETTES, THEME_SUBSTITUTIONS, _DEFAULT_PALETTE)
    if not tones:
        return {}
    palette = [_hex(h) for h in THEME_PALETTES.get(theme_name, _DEFAULT_PALETTE)]
    mapping = _build_map([_hex(h) for h in tones.values()], palette)
    subs = {_hex(a): _hex(b)
            for a, b in THEME_SUBSTITUTIONS.get(theme_name, {}).items()}
    if subs:
        mapping = {k: subs.get(v, v) for k, v in mapping.items()}
    return {ch: "#%02x%02x%02x" % mapping[_hex(h)] for ch, h in tones.items()}


def _preview_themes():
    from tools.generate_tile_icons_32 import THEME_PALETTES
    return list(THEME_PALETTES.keys())


def _theme_surface(theme_name: str) -> str:
    try:
        from techdeck.ui.theme import get_current_palette
        return get_current_palette(theme_name).surface
    except Exception:
        return "#1e1e1e"


# ── shared canvas panel (tools + palette + status) ───────────────────────────
class _CanvasPanel(QWidget, ThemeAware):
    """Base for the paint modes: the reused Canvas engine flanked by a tools
    rail (left) and palette rail (right), plus a status line. Subclasses supply
    the top-bar action set via _build_action_bar() and may extend the body via
    _build_body(). Theme-aware: every color comes from the active palette and
    re-applies on a live theme switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pal = self.get_current_palette()
        self._icon_color = self._pal.text
        self._accent = self._pal.accent

        self.canvas = Canvas()
        self.canvas.color_picked.connect(self._on_pick)
        self.canvas.cell_hovered.connect(self._on_hover)
        self.canvas.palette_changed.connect(self._rebuild_swatches)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Action bar — hosted by the studio's top bar (not this panel).
        self.action_bar = self._build_action_bar()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addLayout(self._build_body(), 1)

        self.status = QLabel("Ready")
        root.addWidget(self.status)

        self.setup_theme_awareness()   # subscribes + styles/swatches once

    def apply_theme(self):
        pal = self.get_current_palette()
        self._pal = pal
        self._icon_color = pal.text
        self._accent = pal.accent
        # Recessed per-theme work surface behind the artboard (never a
        # hardcoded dark gray — it clashed on light themes).
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {pal.console_bg}; "
            f"border: 1px solid {pal.border}; }}")
        self.status.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px;")
        tool_style = self._tool_btn_qss()
        for name, b in self.tool_buttons.items():
            b.setIcon(_svg_icon(_TOOL_ICONS[name], self._icon_color))
            b.setStyleSheet(tool_style)
        nav_style = self._nav_btn_qss()
        for name, b in self._nav_buttons:
            b.setIcon(_svg_icon(_NAV_ICONS[name], self._icon_color))
            b.setStyleSheet(nav_style)
        self._rebuild_swatches()

    def _tool_btn_qss(self) -> str:
        return f"""
            QPushButton {{ background: transparent;
                           border: 1px solid {self._pal.border_strong};
                           border-radius: 6px; }}
            QPushButton:hover {{ background: rgba(127, 127, 127, 0.15); }}
            QPushButton:checked {{ background: rgba(127, 127, 127, 0.28);
                                   border: 2px solid {self._accent}; }}
        """

    def _nav_btn_qss(self) -> str:
        return f"""
            QPushButton {{ background: transparent;
                           border: 1px solid {self._pal.border_strong};
                           border-radius: 6px; }}
            QPushButton:hover {{ background: rgba(127, 127, 127, 0.15); }}
        """

    # ---- overridable hooks ---------------------------------------------------
    def _build_action_bar(self) -> QWidget:
        return QWidget()

    def _build_body(self):
        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_tools_rail())
        body.addWidget(self.scroll, 1)
        body.addWidget(self._build_palette_rail())
        return body

    def _on_appearance_changed(self):
        """Called when the drawn result changes via a palette edit / preset —
        Tile Icon overrides this to refresh its preview."""
        pass

    # ---- tools rail ----------------------------------------------------------
    def _build_tools_rail(self):
        side = QFrame()
        side.setFixedWidth(140)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(self._heading("Tools"))
        tool_style = self._tool_btn_qss()
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for i, name in enumerate(("pencil", "eraser", "fill", "eyedropper",
                                  "select", "lasso")):
            b = QPushButton()
            b.setCheckable(True)
            b.setIcon(_svg_icon(_TOOL_ICONS[name], self._icon_color))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(44, 44)
            b.setToolTip(_TOOL_TIPS.get(name, name.capitalize()))
            b.setStyleSheet(tool_style)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c, n=name: self._select_tool(n))
            self.tool_group.addButton(b)
            self.tool_buttons[name] = b
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(2, 1)
        v.addLayout(grid)
        self.tool_buttons["pencil"].setChecked(True)

        nav_style = self._nav_btn_qss()
        urow = QHBoxLayout()
        urow.setSpacing(4)
        self._nav_buttons = []

        def nav_btn(name, slot):
            b = QPushButton()
            b.setIcon(_svg_icon(_NAV_ICONS[name], self._icon_color, 22))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(44, 44)
            b.setToolTip(_NAV_TIPS.get(name, name.capitalize()))
            b.setStyleSheet(nav_style)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            self._nav_buttons.append((name, b))
            return b

        for name, slot in (("undo", self.canvas.undo), ("redo", self.canvas.redo)):
            urow.addWidget(nav_btn(name, slot))
        urow.addStretch()
        v.addLayout(urow)

        v.addWidget(self._heading("Transform"))
        tgrid = QGridLayout()
        tgrid.setSpacing(4)
        for i, op in enumerate(("flip_h", "flip_v", "rot_cw", "rot_ccw")):
            tgrid.addWidget(
                nav_btn(op, lambda _c=False, o=op: self._transform(o)),
                i // 2, i % 2)
        tgrid.setColumnStretch(2, 1)
        v.addLayout(tgrid)

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

    # ---- palette rail --------------------------------------------------------
    def _build_palette_rail(self):
        side = QFrame()
        side.setFixedWidth(150)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(self._heading("Palette"))
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
        # The app sheet paints scroll viewports/contents with the page
        # background — transparent so the rail shows through instead of a
        # wrong-colored strip under the swatches.
        pal_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget { background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }")
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
        self._on_appearance_changed()

    def _rebuild_swatches(self):
        while self.swatch_box.count():
            item = self.swatch_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for ch, hexval in self.canvas.palette.items():
            # No text — just the colour; an accent border marks the selection.
            b = QPushButton()
            b.setFixedHeight(22)
            b.setToolTip(hexval)
            selected = (ch == self.canvas.active_char)
            border = (f"3px solid {self._accent}" if selected
                      else f"1px solid {self._pal.border_strong}")
            b.setStyleSheet(f"background:{hexval}; border:{border}; border-radius:4px;")
            b.clicked.connect(lambda _c, c=ch: self._select_char(c))
            self.swatch_box.addWidget(b)
        self.swatch_box.addStretch()

    def _select_char(self, ch):
        self.canvas.active_char = ch
        if self.canvas.tool in ("eraser", "eyedropper", "select", "lasso"):
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
            self._on_appearance_changed()
            self.status.setText(f"Recolored '{ch}' -> {c.name()}")

    def _toggle_grid(self):
        self.canvas.show_grid = not self.canvas.show_grid
        self.canvas.update()

    def _transform(self, op):
        self.status.setText(self.canvas.transform(op))

    # ---- signals -------------------------------------------------------------
    def _on_pick(self, ch):
        self._select_char(ch)

    def _on_hover(self, x, y):
        w, h = self.canvas.grid_size()
        self.status.setText(
            f"{w}x{h}   cell ({x},{y})   active '{self.canvas.active_char}'")

    @staticmethod
    def _heading(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
        return lbl


# ── Sprite mode ─────────────────────────────────────────────────────────────
class _SpritePanel(_CanvasPanel):
    """.tdart authoring."""

    def __init__(self, parent=None):
        self.path: "Path | None" = None
        super().__init__(parent)

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


# ── Tile Icon mode ───────────────────────────────────────────────────────────
class _TileIconPanel(_CanvasPanel):
    """32x32 tile-icon authoring with a live preview of the icon recolored into
    every theme, and save-back into the generator scripts."""

    def __init__(self, parent=None):
        self.icon_key = None
        self.icon_static = False
        super().__init__(parent)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(60)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self.canvas.modified.connect(self._schedule_preview)
        self._refresh_preview()

    def showEvent(self, evt):
        super().showEvent(evt)
        # The icon is a fixed 32x32; fit it to the (narrower) canvas column so
        # it reads as a square work area rather than a clipped strip. Deferred
        # a tick so the viewport has its final size after layout settles.
        QTimer.singleShot(0, self._fit_canvas)

    def _fit_canvas(self):
        vp = self.scroll.viewport().size()
        w, h = self.canvas.grid_size()
        if w and h and vp.width() > 20 and vp.height() > 20:
            cell = max(2, min((vp.width() - 4) // w, (vp.height() - 4) // h))
            self.canvas.set_zoom(cell)

    def apply_theme(self):
        super().apply_theme()
        pal = self._pal
        self._preview_note.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 10px;")
        for tile in self._preview_labels.values():
            tile.setStyleSheet(
                f"border: 1px solid {pal.border}; border-radius: 4px;")
        for name in self._preview_names:
            name.setStyleSheet(f"font-size: 10px; color: {pal.text_secondary};")

    def _build_action_bar(self):
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for label, slot in (
            ("Open Icon...", self._open_icon),
            ("Save Icon...", self._save_icon),
            ("Lint", self._lint),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        return bar

    def _lint(self):
        """Run the pixel-style linter on the current grid and show its report
        (the 'logo' profile — the tile-icon ruleset: cluster/chunk/jaggy)."""
        import io
        import contextlib
        from tools.check_pixel_style import lint
        from tools.generate_tile_icons_32 import _hex
        rows, tones = self._used_tones()
        if not tones:
            QMessageBox.information(self, "Lint", "The canvas is empty.")
            return
        grid = [[(*_hex(tones[ch]), 255) if ch in tones else None for ch in row]
                for row in rows]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                level = lint(self.icon_key or "icon", grid, "logo")
        except Exception as exc:
            QMessageBox.critical(self, "Lint failed", str(exc))
            return
        report = buf.getvalue().strip() or f"{level}: no issues"
        box = QMessageBox(self)
        box.setWindowTitle(f"Pixel Style Lint - {level}")
        box.setText(report)
        box.setIcon(QMessageBox.Icon.Information if level == "PASS"
                    else QMessageBox.Icon.Warning)
        box.exec()
        self.status.setText(f"Lint: {level}")

    def _build_body(self):
        body = super()._build_body()
        body.addWidget(self._build_preview_rail())
        return body

    def _build_preview_rail(self):
        side = QFrame()
        side.setFixedWidth(180)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._heading("Preview"))
        self._preview_note = QLabel(
            "Recolored per theme by luminance rank — draw with tonal contrast.")
        self._preview_note.setWordWrap(True)
        v.addWidget(self._preview_note)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._preview_labels = {}
        self._preview_names = []
        for i, theme in enumerate(_preview_themes()):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            tile = QLabel()
            tile.setFixedSize(64, 64)
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview_labels[theme] = tile
            name = QLabel(theme.replace("_", " ").title())
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview_names.append(name)
            cell.addWidget(tile, alignment=Qt.AlignmentFlag.AlignCenter)
            cell.addWidget(name)
            holder = QWidget()
            holder.setObjectName("previewCell")
            holder.setStyleSheet("#previewCell { background: transparent; }")
            holder.setLayout(cell)
            grid.addWidget(holder, i // 2, i % 2)
        v.addLayout(grid)
        v.addStretch()
        return side

    # ---- preview -------------------------------------------------------------
    def _on_appearance_changed(self):
        self._schedule_preview()

    def _schedule_preview(self):
        # Debounce: a drag emits modified per cell; coalesce into one refresh.
        if getattr(self, "_preview_timer", None) is not None:
            self._preview_timer.start()

    def _used_tones(self):
        rows = ["".join(r) for r in self.canvas.rows]
        used = {ch for row in rows for ch in row
                if ch != "." and ch in self.canvas.palette}
        return rows, {ch: self.canvas.palette[ch] for ch in used}

    def _refresh_preview(self):
        rows, tones = self._used_tones()
        n = len(rows) or 32
        cell = max(1, 64 // n)
        side = cell * n
        for theme, label in self._preview_labels.items():
            pm = QPixmap(side, side)
            pm.fill(QColor(_theme_surface(theme)))
            recolored = _recolor_tones(tones, theme)
            p = QPainter(pm)
            for y, row in enumerate(rows):
                for x, ch in enumerate(row):
                    hexv = recolored.get(ch)
                    if hexv:
                        p.fillRect(x * cell, y * cell, cell, cell, QColor(hexv))
            p.end()
            label.setPixmap(pm)

    # ---- open / save ---------------------------------------------------------
    def _open_icon(self):
        from tools.icon_editor import list_icons, parse_icon, THEMED_SCRIPT, PACK_SCRIPT
        icons = list_icons()
        if not icons:
            QMessageBox.information(self, "No icons", "No grid-based icons found.")
            return
        labels = [f"{k}   [{m}]" for k, m in sorted(icons.items())]
        pick, ok = QInputDialog.getItem(
            self, "Open icon", "Icon (from the generator scripts):",
            labels, 0, False)
        if not ok:
            return
        key = pick.split()[0]
        static = icons[key] == "static"
        script = PACK_SCRIPT if static else THEMED_SCRIPT
        rows, tones = parse_icon(script.read_text(encoding="utf-8"), key)
        self.canvas.load({"palette": tones, "rows": rows})
        self._rebuild_swatches()
        self.icon_key, self.icon_static = key, static
        self._refresh_preview()
        self.status.setText(f"Opened {key} ({icons[key]})")

    def _save_icon(self):
        from tools.icon_editor import (
            GRID_SIZE, save_icon_to_script, regenerate, list_icons,
            SaveIconDialog, _KEY_RE)
        w, h = self.canvas.grid_size()
        if (w, h) != (GRID_SIZE, GRID_SIZE):
            QMessageBox.warning(
                self, "Wrong size",
                f"Tile icons are {GRID_SIZE}x{GRID_SIZE}; this canvas is {w}x{h}.")
            return
        rows = ["".join(r) for r in self.canvas.rows]
        used = {ch for row in rows for ch in row if ch != "."}
        if not used:
            QMessageBox.warning(self, "Empty", "The canvas is empty.")
            return
        tones = {ch: self.canvas.palette[ch] for ch in sorted(used)}

        dlg = SaveIconDialog(self.icon_key or "", self.icon_static, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        key, static = dlg.result_values()
        if not _KEY_RE.match(key):
            QMessageBox.warning(self, "Bad name",
                                "Name must be snake_case (a-z, 0-9, _).")
            return
        existing = list_icons()
        if key in existing and (existing[key] == "static") != static:
            QMessageBox.warning(
                self, "Name taken",
                f'"{key}" already exists as a {existing[key]} icon.')
            return
        try:
            script = save_icon_to_script(key, static, rows, tones)
            out = regenerate(static)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.icon_key, self.icon_static = key, static
        msg = f"Saved {key} into {script.name} — {out}"
        if key not in existing:
            msg += ('\n\nNew icon: point a plugin at it via PLUGIN_ICON_KEYS in '
                    f'techdeck/ui/plugin_icon.py:  "<plugin_id>": "{key}"')
            QMessageBox.information(self, "Icon saved", msg)
        self.status.setText(f"Saved {key} + regenerated PNGs")


# ── Placement mode ───────────────────────────────────────────────────────────
class _PlacementPanel(QWidget):
    """Consolidates the four drag-to-place tuning tools (furniture / Buddy
    animation / item animation / nav graph) as sub-tabs. Each reuses its
    standalone placer widget verbatim — including its own Export button, which
    still writes coords to tools/placement_export.py to paste into garden_scene.

    Embedded at SCALE 2 so the whole 384x216 scene fits the studio; precision is
    unaffected (arrow-nudge is 1 native px regardless of scale). Placers are
    built lazily on first view. Note: the mode-toggle button works, but the Tab
    shortcut some placers use may be swallowed by focus navigation when embedded.
    """

    _SPECS = [
        ("Furniture", "tools.furniture_placer", "Placer"),
        ("Buddy Anim", "tools.animation_placer", "Placer"),
        ("Item Anim", "tools.item_anim_placer", "Placer"),
        ("Nav", "tools.nav_editor", "Editor"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.action_bar = QWidget()   # each placer carries its own toolbar

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        tabrow = QHBoxLayout()
        tabrow.setSpacing(6)
        self._group = QButtonGroup(self)
        self.stack = QStackedWidget()
        for i, (label, _mod, _cls) in enumerate(self._SPECS):
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _c, idx=i: self._select(idx))
            self._group.addButton(b)
            tabrow.addWidget(b)
            page = QScrollArea()
            page.setWidgetResizable(False)
            # Keep the area around the embedded placer on the panel surface
            # instead of the page-background fill the app sheet gives
            # scroll viewports.
            page.setStyleSheet(
                "QScrollArea { background: transparent; border: none; }"
                "QScrollArea > QWidget { background: transparent; }")
            self.stack.addWidget(page)
        tabrow.addStretch()
        root.addLayout(tabrow)
        root.addWidget(self.stack, 1)
        self._group.buttons()[0].setChecked(True)

    def showEvent(self, evt):
        super().showEvent(evt)
        self._ensure_built(self.stack.currentIndex())

    def _select(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self._group.buttons()[idx].setChecked(True)
        self._ensure_built(idx)

    def _ensure_built(self, idx: int):
        page = self.stack.widget(idx)
        if page.widget() is not None:
            return
        label, mod, cls = self._SPECS[idx]
        try:
            import importlib
            m = importlib.import_module(mod)
            m.SCALE = 2   # fit the whole scene in the embed area
            page.setWidget(getattr(m, cls)())
        except Exception as exc:
            from techdeck.ui.theme_manager import get_theme_manager
            err = QLabel(f"Could not load {label}:\n{exc}")
            err.setStyleSheet(
                f"color: {get_theme_manager().get_current_palette().error}; "
                f"padding: 20px;")
            err.setWordWrap(True)
            page.setWidget(err)


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

        # Top bar: [ active-mode actions ] ..... [ Sprite | Tile Icon | Placement ]
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
            # Action bars are plain QWidget containers — left alone they paint
            # the global page background and show as a wrong-colored strip
            # inside the surface-colored action host.
            panel.action_bar.setObjectName("studioActionBar")
            panel.action_bar.setStyleSheet(
                "#studioActionBar { background: transparent; }")
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
            return _TileIconPanel()
        return _PlacementPanel()
