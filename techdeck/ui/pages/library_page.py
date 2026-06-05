"""
TechDeck Library Page - FIXED
Inline styling for reliable button appearance, rounded corners, and Open Plugin Folder button
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QScrollArea, QGridLayout,
    QMessageBox, QDialog, QLineEdit, QDialogButtonBox, QFrame, QCheckBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import DEFAULT_PROFILE_NAME
from techdeck.ui.utils import make_tinted_svg_copy
from pathlib import Path
from techdeck.ui.theme import get_current_palette
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.plugin_icon import plugin_icon_pixmap
from techdeck.ui.pages.home_page import TILE_W, TILE_H, TILE_ICON, TILE_ICON_BOX


class ProfileDialog(QDialog):
    """Dialog for creating or editing a profile."""
    
    def __init__(self, mode: str, current_name: str = "", parent=None):
        """
        Args:
            mode: "create" or "edit"
            current_name: Current profile name (for edit mode)
        """
        super().__init__(parent)
        self.mode = mode
        self.current_name = current_name
        self.delete_requested = False
        
        self.setWindowTitle("Create Profile" if mode == "create" else "Edit Profile")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Title
        title = QLabel("Create New Profile" if mode == "create" else "Edit Profile")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Name input
        name_layout = QVBoxLayout()
        name_layout.setSpacing(6)
        
        name_label = QLabel("Profile Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Engineering, QA, Weekend...")
        
        if mode == "edit":
            self.name_input.setText(current_name)
        
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        if mode == "edit":
            # Delete button on left for edit mode
            self.delete_btn = QPushButton("Delete")
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #DC2626;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #B91C1C;
                }
            """)
            self.delete_btn.clicked.connect(self._on_delete)
            button_layout.addWidget(self.delete_btn)
        
        button_layout.addStretch()
        
        # Standard buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        
        button_layout.addWidget(button_box)
        layout.addLayout(button_layout)
    
    def _on_save(self):
        """Validate and accept the dialog."""
        name = self.name_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a profile name.")
            return
        
        self.accept()
    
    def _on_delete(self):
        """Handle delete button click."""
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{self.current_name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested = True
            self.reject()
    
    def get_name(self) -> str:
        """Get the entered profile name."""
        return self.name_input.text().strip()


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

        self.name_label = QLabel(getattr(plugin, "name", tile_id))
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name_font = QFont()
        name_font.setPointSize(9)
        name_font.setWeight(QFont.Weight.Medium)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet(f"color: {theme.text}; background-color: transparent;")

        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label, 1)

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


class LibraryPage(QWidget, ThemeAware):
    """
    Library page for browsing and selecting tiles.
    NOW: Shows missing plugins as selected with (Missing) label, allows deselecting them!
    UPDATED: Save button in header bar for better UX, with Open Plugin Folder button in footer.

    Signals:
        saved(): Emitted when user saves tile selection
        return_home(): Emitted when user wants to go back to home
    """

    saved = Signal()
    return_home = Signal()

    def __init__(self, settings: SettingsManager, parent=None, plugin_loader=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tile_ids = set()

        # Use the shared loader if MainWindow gave us one; otherwise scan now.
        from techdeck.core.plugin_loader import PluginLoader
        if plugin_loader is None:
            plugin_loader = PluginLoader()
            plugin_loader.discover_plugins()
        self.plugin_loader = plugin_loader

        self.available_plugins = list(plugin_loader.plugins.values())
        self.available_tiles = [p.id for p in self.available_plugins]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ===== Header with Profile Controls =====
        self._header_container = QWidget()
        self._header_container.setFixedHeight(50)
        header_layout = QHBoxLayout(self._header_container)
        header_layout.setContentsMargins(20, 8, 20, 8)
        header_layout.setSpacing(12)

        self._profile_label = QLabel("My Kits")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)

        self.btn_create = QPushButton("Create")
        self.btn_create.setMinimumHeight(36)
        self.btn_create.setMinimumWidth(90)
        self.btn_create.clicked.connect(self._on_create_profile)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setMinimumHeight(36)
        self.btn_edit.setMinimumWidth(90)
        self.btn_edit.clicked.connect(self._on_edit_profile)

        self.btn_save = QPushButton("Save")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setMinimumWidth(110)
        self.btn_save.clicked.connect(self._on_save)

        # Sort control: alphabetical vs. by family. Persists in settings so the
        # user's choice survives restarts.
        self._sort_label = QLabel("Sort:")
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Alphabetical", "alphabetical")
        self.sort_combo.addItem("By Family", "family")
        self.sort_combo.setMinimumHeight(36)
        self.sort_combo.setMinimumWidth(140)
        _initial_sort = self.settings.get_library_sort_mode()
        _idx = self.sort_combo.findData(_initial_sort)
        if _idx >= 0:
            self.sort_combo.setCurrentIndex(_idx)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)

        header_layout.addWidget(self._profile_label)
        header_layout.addWidget(self.profile_combo)
        header_layout.addWidget(self.btn_create)
        header_layout.addWidget(self.btn_edit)
        header_layout.addStretch()
        header_layout.addWidget(self._sort_label)
        header_layout.addWidget(self.sort_combo)
        header_layout.addWidget(self.btn_save)

        layout.addWidget(self._header_container)

        # ===== Tile Grid (scrollable) =====
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        self._tile_container = QWidget()
        self.tile_grid = QGridLayout(self._tile_container)
        self.tile_grid.setSpacing(20)
        self.tile_grid.setContentsMargins(24, 24, 24, 24)

        self._scroll.setWidget(self._tile_container)
        layout.addWidget(self._scroll, 1)

        # ===== Footer with Open Plugin Folder button =====
        self._footer_container = QWidget()
        self._footer_container.setFixedHeight(60)
        footer_layout = QHBoxLayout(self._footer_container)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        footer_layout.setSpacing(12)

        footer_layout.addStretch()

        self.btn_open_plugins = QPushButton("Open Plugin Folder")
        self.btn_open_plugins.setMinimumHeight(36)
        self.btn_open_plugins.setMinimumWidth(170)
        self.btn_open_plugins.clicked.connect(self._open_plugin_folder)

        footer_layout.addWidget(self.btn_open_plugins)
        layout.addWidget(self._footer_container)

        # Subscribes to theme_changed and applies immediately.
        self.setup_theme_awareness()

        # Load initial data
        self.refresh()

    # ========== Theme handling =====================================

    def apply_theme(self):
        """Re-style every theme-sensitive surface owned by LibraryPage."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        theme_name = get_theme_manager().get_current_theme()

        self.setStyleSheet(f"""
            LibraryPage {{ background-color: {theme.background}; }}
            LibraryPage QLabel {{ background-color: transparent; }}
        """)

        self._header_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QWidget QLabel {{
                background-color: transparent;
            }}
        """)
        self._profile_label.setStyleSheet(
            f"font-size: 14px; color: {theme.text}; background: transparent;"
        )

        icon_folder = "light" if theme_name in ["dark", "blue", "cyberpunk", "matrix"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        arrow_path = make_tinted_svg_copy(icons_dir / "chevron-down.svg", theme.text)

        combo_style = f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QComboBox:hover {{
                border-color: {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 24px;
                border: none;
                background: transparent;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_path}");
                width: 12px;
                height: 12px;
                background: transparent;
                border: none;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                selection-background-color: {theme.tile_selected};
                outline: none;
            }}
        """
        self.profile_combo.setStyleSheet(combo_style)
        self.sort_combo.setStyleSheet(combo_style)
        self._sort_label.setStyleSheet(
            f"font-size: 14px; color: {theme.text}; background: transparent;"
        )

        surface_btn_style = f"""
            QPushButton {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                font-weight: 500;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.surface_hover};
                border-color: {theme.border_strong};
            }}
            QPushButton:pressed {{
                background-color: {theme.border_strong};
            }}
        """
        self.btn_create.setStyleSheet(surface_btn_style)
        self.btn_edit.setStyleSheet(surface_btn_style)
        self.btn_open_plugins.setStyleSheet(surface_btn_style)

        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_two};
                color: {theme.accent_two_text};
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_two_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_two_pressed};
            }}
        """)

        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {theme.background};
            }}
            QScrollArea > QWidget {{
                background-color: {theme.background};
            }}
        """)
        self._tile_container.setStyleSheet(
            f"QWidget {{ background-color: {theme.background}; }}"
        )

        self._footer_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
        """)
    
    def refresh(self):
        """Reload profiles and current selection."""
        # Update profile dropdown
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        
        profiles = self.settings.get_profile_names()
        self.profile_combo.addItems(profiles)
        
        current = self.settings.get_current_profile_name()
        index = self.profile_combo.findText(current)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        
        self.profile_combo.blockSignals(False)
        
        # Rebuild tile grid
        self._build_tile_grid()
        
        # Update Edit button state (disable for Default)
        self.btn_edit.setEnabled(current != DEFAULT_PROFILE_NAME)
    
    def _build_tile_grid(self):
        """Build the grid of available tiles + missing tiles from current profile."""
        # Clear existing tiles
        while self.tile_grid.count():
            item = self.tile_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get currently selected profile's tiles and sync selected_tile_ids to match
        current_profile_tiles = set(self.settings.get_profile_tiles())
        self.selected_tile_ids = current_profile_tiles.copy()
        
        # Get current theme for tile styling
        from techdeck.ui.theme import get_current_palette
        # PROFESSIONAL: Get theme from ThemeManager
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        current_theme = self.settings.get_theme()
        
        # Import theme helper for missing tiles
        from techdeck.ui.theme import get_missing_tile_style
        
        # Combine available tiles + missing tiles from profile
        all_tile_ids = list(set(self.available_tiles) | current_profile_tiles)

        # Sort according to user-selected mode. "alphabetical" by display name,
        # "family" groups 911 -> 922 -> other (alphabetical within each group).
        sort_mode = self.settings.get_library_sort_mode()
        _family_rank = {"911": 0, "922": 1, "other": 2}

        def _name_no_family(name: str) -> str:
            # Drop a leading family number ("911 ", "922 ") so Alphabetical sorts
            # by the descriptive part of the name. Without this it just mirrors
            # the By-Family grouping (names are family-prefixed), so the two modes
            # would look identical.
            head, _, rest = name.partition(" ")
            return rest if head.isdigit() and rest else name

        def _sort_key(tid: str):
            p = self.plugin_loader.get_plugin(tid)
            name = (p.name if p else tid).lower()
            if sort_mode == "family":
                # Group 911 -> 922 -> other; alphabetical within each group.
                family = (p.family if p else "other")
                return (_family_rank.get(family, 2), name)
            # Flat A-Z by the descriptive name (family number ignored).
            return (_name_no_family(name),)

        row, col = 0, 0

        for tile_id in sorted(all_tile_ids, key=_sort_key):
            plugin = self.plugin_loader.get_plugin(tile_id)
            
            # Check if this tile is selected in current profile
            is_selected = tile_id in current_profile_tiles
            
            if plugin:
                # PHASE 3: Use LibraryPluginCard instead of QPushButton
                desc = plugin.description[:60] + "..." if len(plugin.description) > 60 else plugin.description
                
                card = LibraryPluginCard(
                    plugin=plugin,
                    plugin_desc=desc,
                    tile_id=tile_id,
                    theme=theme,
                    is_selected=is_selected,
                    parent=self
                )
                card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled_card(tid, checked))

                self.tile_grid.addWidget(card, row, col)
            else:
                # Missing plugin - show disabled placeholder tile
                card = QFrame()
                card.setFixedSize(TILE_W, TILE_H)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(6, 10, 6, 8)
                card_layout.setSpacing(5)

                icon_box = QLabel("?")
                icon_box.setObjectName("missingIcon")
                icon_box.setFixedSize(TILE_ICON_BOX, TILE_ICON_BOX)
                icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_box.setStyleSheet(
                    f"#missingIcon {{ color: {theme.tile_missing_text}; "
                    f"font-size: 22px; font-weight: bold; background: transparent; "
                    f"border: 2px dashed {theme.tile_missing_border}; border-radius: 16px; }}"
                )

                missing_label = QLabel("Missing")
                missing_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                missing_label.setWordWrap(True)
                missing_label.setStyleSheet(
                    f"color: {theme.tile_missing_text}; font-size: 9pt; "
                    f"background-color: transparent;"
                )
                missing_label.setToolTip(f"{tile_id}\n(plugin missing from disk)")

                card_layout.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignHCenter)
                card_layout.addWidget(missing_label)

                card.setStyleSheet(
                    "QFrame { background-color: transparent; border-radius: 10px; }"
                )

                self.tile_grid.addWidget(card, row, col)

            col += 1
            if col >= 5:
                col = 0
                row += 1
        
        # No need for _load_profile_selection anymore - selection is set during card creation
    
    def _load_profile_selection(self):
        """Load and display current profile's tile selection."""
        current_profile = self.profile_combo.currentText()
        if not current_profile:
            return
        
        # Get tiles for this profile (includes missing ones)
        profile_tiles = set(self.settings.get_profile_tiles(current_profile))
        self.selected_tile_ids = profile_tiles.copy()
        
        # Update tile button states
        for i in range(self.tile_grid.count()):
            widget = self.tile_grid.itemAt(i).widget()
            if widget and hasattr(widget, 'property'):
                tile_id = widget.property("tile_id")
                widget.blockSignals(True)
                widget.setChecked(tile_id in profile_tiles)
                widget.blockSignals(False)
    
    def _on_tile_toggled_card(self, tile_id: str, checked: bool):
        """PHASE 3: Handle card selection toggle."""
        if checked:
            self.selected_tile_ids.add(tile_id)
        else:
            self.selected_tile_ids.discard(tile_id)
        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)
    
    def _on_tile_toggled(self, checked: bool):
        """Handle tile selection toggle (legacy method for backward compatibility)."""
        sender = self.sender()
        tile_id = sender.property("tile_id")
        
        if checked:
            self.selected_tile_ids.add(tile_id)
        else:
            self.selected_tile_ids.discard(tile_id)
    
    def _on_profile_changed(self, profile_name: str):
        """Handle profile selection change."""
        if profile_name:
            self.settings.set_current_profile(profile_name)
            self._build_tile_grid()
            self.btn_edit.setEnabled(profile_name != DEFAULT_PROFILE_NAME)

    def _on_sort_mode_changed(self, _index: int):
        """Persist the new sort mode and rebuild the grid."""
        mode = self.sort_combo.currentData() or "alphabetical"
        self.settings.set_library_sort_mode(mode)
        self._build_tile_grid()
    
    def _on_create_profile(self):
        """Show dialog to create new profile."""
        dialog = ProfileDialog("create", parent=self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_name()
            
            # Check if name already exists
            if name in self.settings.get_profile_names():
                QMessageBox.warning(
                    self,
                    "Duplicate Name",
                    f"A profile named '{name}' already exists."
                )
                return
            
            # Create profile
            if self.settings.create_profile(name):
                self.settings.set_current_profile(name)
                self.refresh()
                QMessageBox.information(
                    self,
                    "Profile Created",
                    f"Profile '{name}' created successfully!"
                )
    
    def _on_edit_profile(self):
        """Show dialog to edit current profile."""
        current = self.profile_combo.currentText()
        
        if not current:
            return
        
        if current == DEFAULT_PROFILE_NAME:
            QMessageBox.information(
                self,
                "Cannot Edit Default",
                "The Default profile cannot be renamed or deleted."
            )
            return
        
        dialog = ProfileDialog("edit", current_name=current, parent=self)
        result = dialog.exec()
        
        # Check if delete was requested
        if dialog.delete_requested:
            if self.settings.delete_profile(current):
                self.refresh()
                QMessageBox.information(
                    self,
                    "Profile Deleted",
                    f"Profile '{current}' has been deleted."
                )
            return
        
        # Handle rename
        if result == QDialog.DialogCode.Accepted:
            new_name = dialog.get_name()
            
            if new_name != current:
                # Check if new name already exists
                if new_name in self.settings.get_profile_names():
                    QMessageBox.warning(
                        self,
                        "Duplicate Name",
                        f"A profile named '{new_name}' already exists."
                    )
                    return
                
                # Rename profile
                if self.settings.rename_profile(current, new_name):
                    self.refresh()
                    QMessageBox.information(
                        self,
                        "Profile Renamed",
                        f"Profile renamed to '{new_name}'."
                    )
    
    def _open_plugin_folder(self):
        """Open the plugins directory in the system file explorer."""
        import subprocess
        import os
        import platform
        
        plugins_dir = self.plugin_loader.get_plugins_dir()
        
        # Ensure directory exists
        plugins_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Open file explorer based on OS
            if platform.system() == 'Windows':
                os.startfile(plugins_dir)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(plugins_dir)])
            else:  # Linux
                subprocess.run(['xdg-open', str(plugins_dir)])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error Opening Folder",
                f"Could not open plugin folder:\n{plugins_dir}\n\nError: {str(e)}"
            )
    
    def _on_save(self):
        """Save tile selection to current profile and return to home."""
        current_profile = self.profile_combo.currentText()
        
        if not current_profile:
            return
        
        # Save tiles to profile (only selected ones, missing tiles can be removed!)
        self.settings.set_profile_tiles(list(self.selected_tile_ids), current_profile)
        
        # Emit signals
        self.saved.emit()
        self.return_home.emit()