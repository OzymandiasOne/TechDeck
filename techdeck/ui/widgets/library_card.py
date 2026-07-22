"""Library tile widgets — the selectable plugin card, the missing-plugin
placeholder, and the full-description info popup. Extracted siblings of
LibraryPage; tile geometry/badge constants are shared with Home via
techdeck.ui.widgets.plugin_card."""

from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QDialog, QDialogButtonBox, QFrame,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.plugin_icon import plugin_icon_pixmap
from techdeck.ui.widgets.plugin_card import (
    TILE_W, TILE_H, TILE_ICON, TILE_ICON_BOX,
    _FAMILY_BADGE_COLORS, _strip_family_prefix,
)


class PluginInfoDialog(QDialog):
    """Small popup window showing a plugin's full description (Library info button)."""

    def __init__(self, name: str, description: str, theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle(name)
        self.setMinimumWidth(360)
        self.setMaximumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel(name)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {theme.text}; background: transparent;")

        body = QLabel(description)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {theme.text_secondary}; background: transparent; font-size: 13px;"
        )

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        layout.addWidget(title)
        layout.addWidget(body, 1)
        layout.addWidget(button_box)

        self.setStyleSheet(f"""
            QDialog {{ background-color: {theme.background}; }}
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ background-color: {theme.accent_hover}; }}
        """)


class LibraryPluginCard(QFrame, ThemeAware):
    """
    PHASE 3: Professional plugin card for library page.
    Similar to home page cards but for selection/browsing.
    """

    toggled = Signal(bool)

    def __init__(self, plugin, plugin_desc: str, tile_id: str, theme, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.theme = theme
        self._is_checked = is_selected
        self._plugin = plugin
        self._plugin_name = getattr(plugin, "name", tile_id)
        # Full (untruncated) description for the info popup.
        self._full_desc = getattr(plugin, "description", "") or "No description provided."

        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Main layout: centered icon over the app name (Windows-Settings style).
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 8)
        layout.setSpacing(5)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(TILE_ICON_BOX, TILE_ICON_BOX)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(plugin_icon_pixmap(plugin, TILE_ICON))
        # Transparent so the tile's (selected/hover) background shows through —
        # without this the box picks up a dark fill that clashes when selected.
        self.icon_label.setStyleSheet("background: transparent;")

        # Name without the family prefix — the family shows as a corner badge,
        # matching Home ("911 Setup" → badge "911" + name "Setup"). The info
        # popup keeps the full name for context.
        self._family = getattr(plugin, "family", "General")
        self.name_label = QLabel(
            _strip_family_prefix(getattr(plugin, "name", tile_id), self._family))
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name_font = QFont()
        name_font.setPointSize(9)
        name_font.setWeight(QFont.Weight.Medium)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet(f"color: {theme.text}; background-color: transparent;")

        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label, 1)

        # Family badge in the top-left corner (matches Home; shown for every
        # family). Absolutely-positioned child; the info "i" button owns the
        # top-right corner, so the two never collide.
        self.family_badge = QLabel(
            self._family if self._family in _FAMILY_BADGE_COLORS else "", self)
        self.family_badge.move(7, 5)
        self.family_badge.setVisible(bool(self.family_badge.text()))
        self._style_family_badge()

        # Corner "i" button → opens a window with the full description. It's a
        # child positioned absolutely in the top-right; because QPushButton
        # consumes its own mouse press, clicking it does NOT toggle the tile's
        # selection. (No hover tooltip — the description lives behind this button.)
        self.info_btn = QPushButton("i", self)
        self.info_btn.setFixedSize(18, 18)
        self.info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_btn.setToolTip("About this app")
        self.info_btn.move(TILE_W - 22, 5)
        self.info_btn.clicked.connect(self._show_info)

        # Apply base styling
        self._update_card_style()

        # PROFESSIONAL: Setup theme awareness for live updates
        self.setup_theme_awareness()

    def apply_theme(self):
        """Called automatically when theme changes."""
        self.theme = self.get_current_palette()
        self._update_card_style()
        self.name_label.setStyleSheet(f"color: {self.theme.text}; background-color: transparent;")
        self.icon_label.setPixmap(plugin_icon_pixmap(self._plugin, TILE_ICON))
        self._style_family_badge()

    def _style_family_badge(self):
        """Same look as Home's badge: text-only, colored with the theme accent.
        `_FAMILY_BADGE_COLORS` gates which families get a tag (all of them now)."""
        if self._family not in _FAMILY_BADGE_COLORS:
            self.family_badge.setVisible(False)
            return
        self.family_badge.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: {self.theme.accent}; "
            f"font-size: 8pt; font-weight: bold; border-radius: 5px; padding: 0px 4px; }}"
        )
        self.family_badge.adjustSize()
        self.family_badge.raise_()

    def is_checked(self) -> bool:
        """Get checked state."""
        return self._is_checked

    def set_checked(self, checked: bool):
        """Set checked state programmatically (no signal emitted)."""
        self._is_checked = checked
        self._update_card_style()

    def _update_card_style(self):
        """Solid background; selection/hover follow the same logic as Home."""
        bg = self.theme.tile_selected if self._is_checked else self.theme.surface
        self.setStyleSheet(f"""
            LibraryPluginCard {{
                background-color: {bg};
                border-radius: 10px;
            }}
            LibraryPluginCard:hover {{
                background-color: {self.theme.surface_hover};
            }}
        """)
        if hasattr(self, "info_btn"):
            self.info_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {self.theme.text_secondary};
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-style: italic;
                    font-weight: bold;
                    font-size: 13px;
                }}
                QPushButton:hover {{ color: {self.theme.accent}; }}
            """)
            self.info_btn.raise_()

    def _show_info(self):
        """Open a small window with the plugin's full description."""
        PluginInfoDialog(self._plugin_name, self._full_desc, self.theme, self).exec()

    def mousePressEvent(self, event):
        """Handle mouse press - toggle the pure-highlight selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_checked = not self._is_checked
            self._update_card_style()
            self.toggled.emit(self._is_checked)
        super().mousePressEvent(event)


class _MissingLibraryTile(QFrame):
    """Placeholder card for a kit tile whose plugin folder is gone from disk.

    Toggleable like LibraryPluginCard: it starts CHECKED (it's still in the
    kit), and the user can click to deselect it so the next Save drops it from
    the profile. Without this, Save would silently write the dead id back.
    """

    toggled = Signal(bool)

    def __init__(self, tile_id: str, theme, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.theme = theme
        self._is_checked = True
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(6, 10, 6, 8)
        card_layout.setSpacing(5)

        self._icon_box = QLabel("?")
        self._icon_box.setObjectName("missingIcon")
        self._icon_box.setFixedSize(TILE_ICON_BOX, TILE_ICON_BOX)
        self._icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._missing_label = QLabel("Missing")
        self._missing_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._missing_label.setWordWrap(True)

        self.setToolTip(
            f"{tile_id}\n(plugin missing from disk)\n"
            f"Click to deselect, then Save to remove it from this kit."
        )

        card_layout.addWidget(self._icon_box, 0, Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(self._missing_label)

        self.restyle(theme)

    def restyle(self, theme):
        """Apply theme colors. Called at construction and on live theme change
        (this widget isn't ThemeAware, so LibraryPage.apply_theme re-stamps it)."""
        self.theme = theme
        self._icon_box.setStyleSheet(
            f"#missingIcon {{ color: {theme.tile_missing_text}; "
            f"font-size: 22px; font-weight: bold; background: transparent; "
            f"border: 2px dashed {theme.tile_missing_border}; border-radius: 16px; }}"
        )
        self._missing_label.setStyleSheet(
            f"color: {theme.tile_missing_text}; font-size: 9pt; "
            f"background-color: transparent;"
        )
        self._update_card_style()

    def _update_card_style(self):
        # Same selection visual as LibraryPluginCard so checked state reads
        # the same way across the grid.
        bg = self.theme.tile_selected if self._is_checked else self.theme.surface
        self.setStyleSheet(f"""
            _MissingLibraryTile {{
                background-color: {bg};
                border-radius: 10px;
            }}
            _MissingLibraryTile:hover {{
                background-color: {self.theme.surface_hover};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_checked = not self._is_checked
            self._update_card_style()
            self.toggled.emit(self._is_checked)
        super().mousePressEvent(event)
