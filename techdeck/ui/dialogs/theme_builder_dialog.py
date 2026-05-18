"""
TechDeck Theme Builder Dialog
Lets users create and save custom color themes.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QWidget, QFrame,
    QGridLayout, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from techdeck.ui.theme import (
    THEMES, ColorPalette, palette_to_dict, palette_from_dict,
    save_custom_theme, is_builtin_theme,
)


# Field groups: (group_label, [(palette_field_name, display_label), ...])
_FIELD_GROUPS = [
    ("Background & Surface", [
        ("background",    "App Background"),
        ("surface",       "Surface / Cards"),
        ("surface_hover", "Surface Hover"),
    ]),
    ("Text", [
        ("text",           "Primary Text"),
        ("text_secondary", "Secondary Text"),
    ]),
    ("Primary Accent", [
        ("accent",         "Accent"),
        ("accent_hover",   "Accent Hover"),
        ("accent_pressed", "Accent Pressed"),
    ]),
    ("CTA Accent", [
        ("accent_two",         "CTA Color"),
        ("accent_two_hover",   "CTA Hover"),
        ("accent_two_pressed", "CTA Pressed"),
    ]),
    ("Borders", [
        ("border",        "Border"),
        ("border_strong", "Border Strong"),
        ("divider",       "Divider"),
    ]),
    ("Console", [
        ("console_bg",   "Console Background"),
        ("console_text", "Console Text"),
    ]),
    ("Status Colors", [
        ("success", "Success"),
        ("warning", "Warning"),
        ("error",   "Error"),
        ("info",    "Info"),
    ]),
    ("Tiles", [
        ("tile_selected",      "Tile Selected"),
        ("tile_missing_bg",    "Missing Tile BG"),
        ("tile_missing_text",  "Missing Tile Text"),
        ("tile_missing_border","Missing Tile Border"),
    ]),
]

_FONT_OPTIONS = [
    ('"Segoe UI", Arial, sans-serif',           "Segoe UI (Default)"),
    ('"Consolas", "Courier New", monospace',    "Consolas (Monospace)"),
    ('"Courier New", Consolas, monospace',      "Courier New (Monospace)"),
    ('"Arial", sans-serif',                     "Arial"),
    ('"Georgia", serif',                        "Georgia (Serif)"),
]


class _ColorButton(QPushButton):
    """A button that shows a color swatch and opens QColorDialog on click."""

    color_changed = Signal(str)  # emits hex color string

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(36, 28)
        self._refresh()
        self.clicked.connect(self._pick_color)

    def _refresh(self):
        c = QColor(self._color) if not self._color.startswith("rgba") else QColor(128, 128, 128)
        luma = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        text_color = "#000000" if luma > 0.5 else "#FFFFFF"
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; color: {text_color}; "
            f"border: 1px solid #555; border-radius: 4px; font-size: 10px; }}"
            f"QPushButton:hover {{ border: 2px solid #FFF; }}"
        )
        # Show abbreviated hex in button if it fits
        short = self._color if len(self._color) <= 7 else ""
        self.setText(short)

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        initial = QColor(self._color) if not self._color.startswith("rgba") else QColor(128, 128, 128)
        c = QColorDialog.getColor(initial, self, "Pick Color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.color_changed.emit(self._color)

    def get_color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color
        self._refresh()


class _SwatchPreview(QWidget):
    """Simple color swatch preview showing key palette values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

        title = QLabel("Preview")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 13px; background: transparent; color: #888;")
        self._layout.addWidget(title)

        self._swatches: dict[str, QLabel] = {}
        preview_fields = [
            ("background",   "Background"),
            ("surface",      "Surface"),
            ("text",         "Text"),
            ("accent",       "Primary Accent"),
            ("accent_two",   "CTA Accent"),
            ("console_bg",   "Console BG"),
            ("console_text", "Console Text"),
            ("success",      "Success"),
            ("warning",      "Warning"),
            ("error",        "Error"),
        ]
        for field_name, label_text in preview_fields:
            row = QWidget()
            row.setFixedHeight(28)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            rl.setSpacing(6)

            swatch = QLabel()
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet("border-radius: 4px; border: 1px solid #444;")
            lbl = QLabel(label_text)
            lbl.setStyleSheet("background: transparent; color: #aaa; font-size: 11px;")
            rl.addWidget(swatch)
            rl.addWidget(lbl)
            rl.addStretch()
            self._swatches[field_name] = swatch
            self._layout.addWidget(row)

        self._layout.addStretch()

    def update_color(self, field_name: str, color: str):
        if field_name in self._swatches:
            c = color if not color.startswith("rgba") else "#808080"
            self._swatches[field_name].setStyleSheet(
                f"background-color: {c}; border-radius: 4px; border: 1px solid #444;"
            )

    def refresh_all(self, palette_dict: dict):
        for field_name in self._swatches:
            val = palette_dict.get(field_name, "#888888")
            self.update_color(field_name, val)


class ThemeBuilderDialog(QDialog):
    """Dialog for building and saving custom themes."""

    theme_saved = Signal(str)  # emits the saved theme name

    def __init__(self, settings, parent=None, edit_name: str = ""):
        super().__init__(parent)
        self._settings = settings
        self._color_buttons: dict[str, _ColorButton] = {}
        self._edit_name = edit_name  # non-empty = editing existing theme

        self.setWindowTitle("Theme Builder" if not edit_name else f"Edit Theme: {edit_name}")
        self.setMinimumSize(780, 620)
        self.resize(860, 680)

        self._build_ui()
        self._load_base_theme("dark")

        if edit_name and edit_name in THEMES:
            self._name_input.setText(edit_name)
            self._load_from_palette(THEMES[edit_name])

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        # ── Header ──
        hdr = QHBoxLayout()
        title = QLabel("Theme Builder")
        title.setStyleSheet("font-size: 18px; font-weight: bold; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()

        base_lbl = QLabel("Start from:")
        base_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        self._base_combo = QComboBox()
        self._base_combo.setFixedWidth(150)
        for name in THEMES:
            self._base_combo.addItem(name.capitalize(), name)
        self._base_combo.currentIndexChanged.connect(
            lambda: self._load_base_theme(self._base_combo.currentData())
        )
        hdr.addWidget(base_lbl)
        hdr.addWidget(self._base_combo)
        root.addLayout(hdr)

        # ── Body: color pickers + preview ──
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: scrollable color groups
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(4, 4, 12, 4)
        inner_layout.setSpacing(14)

        for group_label, fields in _FIELD_GROUPS:
            grp_title = QLabel(group_label)
            grp_title.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent; color: #aaa;")
            inner_layout.addWidget(grp_title)

            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)
            for i, (field_name, display_label) in enumerate(fields):
                lbl = QLabel(display_label)
                lbl.setStyleSheet("background: transparent; font-size: 12px;")
                lbl.setFixedWidth(160)
                btn = _ColorButton("#888888")
                btn.color_changed.connect(
                    lambda c, f=field_name: self._on_color_changed(f, c)
                )
                self._color_buttons[field_name] = btn
                grid.addWidget(lbl, i, 0)
                grid.addWidget(btn, i, 1)
                grid.addWidget(QLabel(), i, 2)  # spacer

            inner_layout.addLayout(grid)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("background: #333; max-height: 1px;")
            inner_layout.addWidget(sep)

        # Shadow (text input — rgba format)
        shd_row = QHBoxLayout()
        shd_lbl = QLabel("Shadow")
        shd_lbl.setFixedWidth(160)
        shd_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        self._shadow_input = QLineEdit("rgba(0, 0, 0, 0.3)")
        self._shadow_input.setPlaceholderText("rgba(0, 0, 0, 0.3)")
        self._shadow_input.setFixedWidth(200)
        shd_row.addWidget(shd_lbl)
        shd_row.addWidget(self._shadow_input)
        shd_row.addStretch()
        inner_layout.addLayout(shd_row)

        # Font family
        font_row = QHBoxLayout()
        font_lbl = QLabel("Font")
        font_lbl.setFixedWidth(160)
        font_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        self._font_combo = QComboBox()
        self._font_combo.setFixedWidth(260)
        for val, label in _FONT_OPTIONS:
            self._font_combo.addItem(label, val)
        font_row.addWidget(font_lbl)
        font_row.addWidget(self._font_combo)
        font_row.addStretch()
        inner_layout.addLayout(font_row)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        body.addWidget(scroll, 2)

        # Right: preview
        self._preview = _SwatchPreview()
        body.addWidget(self._preview, 1)

        root.addLayout(body, 1)

        # ── Footer ──
        footer = QHBoxLayout()

        name_lbl = QLabel("Theme Name:")
        name_lbl.setStyleSheet("background: transparent;")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("my_theme")
        self._name_input.setFixedWidth(200)

        footer.addWidget(name_lbl)
        footer.addWidget(self._name_input)
        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Theme")
        save_btn.setFixedHeight(36)
        save_btn.setProperty("class", "primary")
        save_btn.clicked.connect(self._save_theme)

        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        root.addLayout(footer)

    # ── Loading helpers ────────────────────────────────────────────────────

    def _load_base_theme(self, theme_name: str):
        if theme_name not in THEMES:
            return
        self._load_from_palette(THEMES[theme_name])
        if not self._name_input.text():
            self._name_input.setText(f"{theme_name}_custom")

    def _load_from_palette(self, palette: ColorPalette):
        d = palette_to_dict(palette)
        for field_name, btn in self._color_buttons.items():
            val = d.get(field_name, "#888888")
            btn.set_color(val)
        self._shadow_input.setText(d.get("shadow", "rgba(0,0,0,0.3)"))
        font_val = d.get("font_family", '"Segoe UI", Arial, sans-serif')
        for i in range(self._font_combo.count()):
            if self._font_combo.itemData(i) == font_val:
                self._font_combo.setCurrentIndex(i)
                break
        self._preview.refresh_all(d)

    def _on_color_changed(self, field_name: str, color: str):
        self._preview.update_color(field_name, color)

    # ── Build palette from current UI state ────────────────────────────────

    def _build_palette(self) -> ColorPalette:
        d = {}
        for field_name, btn in self._color_buttons.items():
            d[field_name] = btn.get_color()
        d["shadow"] = self._shadow_input.text().strip() or "rgba(0,0,0,0.3)"
        d["font_family"] = self._font_combo.currentData()
        d["extra_stylesheet"] = ""
        return palette_from_dict(d)

    # ── Save ──────────────────────────────────────────────────────────────

    def _save_theme(self):
        name = self._name_input.text().strip().lower().replace(" ", "_")
        if not name:
            QMessageBox.warning(self, "Theme Builder", "Please enter a theme name.")
            return
        if is_builtin_theme(name):
            QMessageBox.warning(
                self, "Theme Builder",
                f"'{name}' is a built-in theme name. Choose a different name."
            )
            return

        palette = self._build_palette()
        custom_dir = self._settings.get_custom_themes_dir()
        save_custom_theme(name, palette, custom_dir)
        self.theme_saved.emit(name)
        self.accept()
