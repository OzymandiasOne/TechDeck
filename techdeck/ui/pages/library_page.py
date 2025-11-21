"""
TechDeck Library Page - FIXED
Inline styling for reliable button appearance, rounded corners, and Open Plugin Folder button
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QScrollArea, QGridLayout,
    QMessageBox, QDialog, QLineEdit, QDialogButtonBox
)
from PySide6.QtCore import Signal, Qt

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import DEFAULT_PROFILE_NAME
from techdeck.ui.utils import make_tinted_svg_copy
from pathlib import Path
from techdeck.ui.theme import get_current_palette


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


class LibraryPage(QWidget):
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
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tile_ids = set()
        
        # Import plugin loader
        from techdeck.core.plugin_loader import PluginLoader
        self.plugin_loader = PluginLoader()
        
        # Discover available plugins
        self.available_plugins = self.plugin_loader.discover_plugins()
        self.available_tiles = [p.id for p in self.available_plugins]
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Get theme colors
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        
        # Set explicit background color for this page
        self.setStyleSheet(f"LibraryPage {{ background-color: {theme.background}; }}")
        
        # ===== Header with Profile Controls =====
        header_container = QWidget()
        header_container.setFixedHeight(50)  # Slightly taller for better spacing
        header_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QWidget QLabel {{
                background-color: transparent;
            }}
        """)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(20, 8, 20, 8)
        header_layout.setSpacing(12)
        
        profile_label = QLabel("My Kits")
        profile_label.setStyleSheet("font-size: 14px;")
        
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)  # Match button height
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        
        theme = get_current_palette(self.settings.get_theme())
        # ✅ Select icon folder based on theme
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir  = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow  = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)  # themed copy -> file path
        
        self.profile_combo.setStyleSheet(f"""
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
                background: transparent;   /* kills faint white rectangle */
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
        """)
        
        self.btn_create = QPushButton("Create")
        self.btn_create.setMinimumHeight(36)
        self.btn_create.setMinimumWidth(90)
        # Apply surface color styling - INLINE
        self.btn_create.setStyleSheet(f"""
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
        """)
        self.btn_create.clicked.connect(self._on_create_profile)
        
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setMinimumHeight(36)
        self.btn_edit.setMinimumWidth(90)
        # Apply surface color styling - INLINE
        self.btn_edit.setStyleSheet(f"""
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
        """)
        self.btn_edit.clicked.connect(self._on_edit_profile)
        
        # Save button - Orange CTA styling INLINE
        self.btn_save = QPushButton("Save")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setMinimumWidth(110)
        # Apply orange CTA styling INLINE
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_two};
                color: #FFFFFF;
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
        self.btn_save.clicked.connect(self._on_save)
        
        header_layout.addWidget(profile_label)
        header_layout.addWidget(self.profile_combo)
        header_layout.addWidget(self.btn_create)
        header_layout.addWidget(self.btn_edit)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_save)
        
        layout.addWidget(header_container)
        
        # ===== Tile Grid (scrollable) =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # Set scroll area and viewport backgrounds to match theme
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {theme.background};
            }}
            QScrollArea > QWidget {{
                background-color: {theme.background};
            }}
        """)
        
        tile_container = QWidget()
        # Set explicit background for tile container
        tile_container.setStyleSheet(f"QWidget {{ background-color: {theme.background}; }}")
        self.tile_grid = QGridLayout(tile_container)
        self.tile_grid.setSpacing(12)
        self.tile_grid.setContentsMargins(20, 20, 20, 20)
        
        scroll.setWidget(tile_container)
        layout.addWidget(scroll, 1)
        
        # ===== Footer with Open Plugin Folder button =====
        footer_container = QWidget()
        footer_container.setFixedHeight(60)
        footer_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
        """)
        footer_layout = QHBoxLayout(footer_container)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        footer_layout.setSpacing(12)
        
        footer_layout.addStretch()
        
        # Open Plugin Folder button - styled with surface color
        self.btn_open_plugins = QPushButton("Open Plugin Folder")
        self.btn_open_plugins.setMinimumHeight(36)
        self.btn_open_plugins.setMinimumWidth(170)
        self.btn_open_plugins.setStyleSheet(f"""
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
        """)
        self.btn_open_plugins.clicked.connect(self._open_plugin_folder)
        
        footer_layout.addWidget(self.btn_open_plugins)
        
        layout.addWidget(footer_container)
        
        # Load initial data
        self.refresh()
    
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
        
        # Get currently selected profile's tiles
        current_profile_tiles = set(self.settings.get_profile_tiles())
        
        # Get current theme for tile styling
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        current_theme = self.settings.get_theme()
        
        # Import theme helper for missing tiles
        from techdeck.ui.theme import get_missing_tile_style
        
        # Combine available tiles + missing tiles from profile
        all_tile_ids = list(set(self.available_tiles) | current_profile_tiles)
        
        row, col = 0, 0
        
        for tile_id in sorted(all_tile_ids):
            plugin = self.plugin_loader.get_plugin(tile_id)
            
            if plugin:
                # Normal plugin - available with full styling
                tile_btn = QPushButton(plugin.name)
                tile_btn.setToolTip(plugin.description)
                tile_btn.setProperty("tile", True)
                # Apply explicit inline styling (like home_page.py does)
                tile_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {theme.surface};
                        color: {theme.text};
                        border: 1px solid {theme.border};
                        border-radius: 12px;
                        padding: 8px 16px;
                        outline: none;
                    }}
                    QPushButton:hover {{
                        background-color: {theme.surface_hover};
                        border: 1px solid {theme.border};
                    }}
                    QPushButton:pressed {{
                        background-color: {theme.surface_hover};
                        border: 1px solid {theme.border_strong};
                    }}
                    QPushButton:checked {{
                        background-color: {theme.tile_selected};
                        border: 2px solid {theme.accent};
                        outline: none;
                    }}
                    QPushButton:checked:hover {{
                        background-color: {theme.tile_selected};
                        border: 2px solid {theme.accent_hover};
                    }}
                    QPushButton:checked:pressed {{
                        background-color: {theme.tile_selected};
                        border: 2px solid {theme.accent_pressed};
                    }}
                    QPushButton:focus {{
                        outline: none;
                        border: 1px solid {theme.border};
                    }}
                    QPushButton:checked:focus {{
                        outline: none;
                        border: 2px solid {theme.accent};
                    }}
                    QPushButton:checked,
                    QPushButton:checked:hover,
                    QPushButton:checked:pressed,
                    QPushButton:checked:focus {{
                        border: 1px solid transparent;
                    }}
                """)
            else:
                # Missing plugin - use themed colors
                tile_btn = QPushButton(f"{tile_id}\n(Missing)")
                tile_btn.setToolTip("This plugin is not installed or was removed.\nYou can deselect it to remove from profile.")
                tile_btn.setProperty("tile", True)
                # Apply themed missing tile style
                tile_btn.setStyleSheet(get_missing_tile_style(current_theme))
            
            tile_btn.setMinimumSize(150, 120)
            tile_btn.setCheckable(True)
            tile_btn.setProperty("tile_id", tile_id)
            tile_btn.toggled.connect(self._on_tile_toggled)
            
            # Disable focus rectangle to prevent default blue border
            tile_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            self.tile_grid.addWidget(tile_btn, row, col)
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        # Load and apply selection state
        self._load_profile_selection()
    
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
    
    def _on_tile_toggled(self, checked: bool):
        """Handle tile selection toggle."""
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