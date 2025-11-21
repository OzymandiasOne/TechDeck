"""
TechDeck Home Page - FIXED
Inline styling for reliable button appearance and rounded corners
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QScrollArea, QGridLayout, QMessageBox
)
from PySide6.QtCore import Signal, Qt

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor, PluginResult
from techdeck.ui.theme import get_missing_tile_style
from pathlib import Path
from techdeck.ui.theme import get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy


class HomePage(QWidget):
    profile_changed = Signal(str)
    open_library = Signal()
    run_selected = Signal(list)
    plugin_log = Signal(str, str)
    plugin_progress = Signal(str, int)
    plugin_completed = Signal(str)
    
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tiles = set()
        
        self.plugin_loader = PluginLoader()
        self.plugin_loader.discover_plugins()
        self.plugin_executor = PluginExecutor(self.plugin_loader)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        
        self.setStyleSheet(f"HomePage {{ background-color: {theme.background}; }}")
        
        # Profile Controls Container
        profile_container = QWidget()
        profile_container.setFixedHeight(50)  # Slightly taller for better spacing
        profile_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QWidget QLabel {{
                background-color: transparent;
            }}
        """)
        profile_layout = QHBoxLayout(profile_container)
        profile_layout.setContentsMargins(20, 8, 20, 8)
        profile_layout.setSpacing(12)
        
        profile_label = QLabel("Active Kit   /")
        profile_label.setStyleSheet("font-size: 14px;")
        
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)  # Match button height
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        # Apply rounded corners and proper styling to dropdown - INLINE
        
        theme = get_current_palette(self.settings.get_theme())

        # ✅ Select icon folder based on theme (dark=white icons, light=black icons)
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)  # -> themed copy on disk
        
        self.profile_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 10px;
                padding-right: 28px;
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
        """)
        
        self.btn_add_tiles = QPushButton("+Apps")
        self.btn_add_tiles.setMinimumHeight(36)  # Increased to prevent text cutoff
        self.btn_add_tiles.setMinimumWidth(40)  # Increased for better fit
        # Apply second accent CTA styling INLINE - most reliable approach
        self.btn_add_tiles.setStyleSheet(f"""
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
        self.btn_add_tiles.clicked.connect(self.open_library.emit)
        
        profile_layout.addWidget(profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(self.btn_add_tiles)
        profile_layout.addStretch()
        
        layout.addWidget(profile_container)
        
        # Tile Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {theme.background};
                border-radius: 0px;
            }}
            QScrollArea > QWidget {{
                background-color: {theme.background};
            }}
        """)
        
        self.tile_container = QWidget()
        self.tile_container.setStyleSheet(f"QWidget {{ background-color: {theme.background}; }}")
        
        tile_container_layout = QVBoxLayout(self.tile_container)
        tile_container_layout.setContentsMargins(20, 20, 20, 20)
        
        tile_grid_widget = QWidget()
        tile_grid_widget.setStyleSheet(f"QWidget {{ background-color: {theme.background}; }}")
        self.tile_grid = QGridLayout(tile_grid_widget)
        self.tile_grid.setSpacing(12)
        self.tile_grid.setContentsMargins(0, 0, 0, 0)
        
        tile_container_layout.addWidget(tile_grid_widget)
        tile_container_layout.addStretch()
        
        scroll.setWidget(self.tile_container)
        layout.addWidget(scroll, 1)
        
        # Load profiles into dropdown on initialization
        self.refresh_profiles()

    def set_run_button(self, button: QPushButton):
        self.btn_run = button
        self.btn_run.clicked.connect(self._on_run_clicked)

    def refresh_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        
        profiles = self.settings.get_profile_names()
        self.profile_combo.addItems(profiles)
        
        current = self.settings.get_current_profile_name()
        index = self.profile_combo.findText(current)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        
        self.profile_combo.blockSignals(False)
        self._refresh_tiles()
    
    def _refresh_tiles(self):
        while self.tile_grid.count():
            item = self.tile_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        tile_ids = self.settings.get_profile_tiles()
        
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        current_theme_name = self.settings.get_theme()
        
        if not tile_ids:
            label = QLabel("No tiles in this profile.\nClick '+ Apps' to add some!")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.tile_grid.addWidget(label, 0, 0)
        else:
            row, col = 0, 0
            for tile_id in tile_ids:
                plugin = self.plugin_loader.get_plugin(tile_id)
                
                if plugin:
                    tile_btn = QPushButton(plugin.name)
                    tile_btn.setToolTip(plugin.description)
                    tile_btn.setProperty("tile", True)
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
                            border: 1px solid {theme.accent};
                            outline: none;
                        }}
                        QPushButton:checked:hover {{
                            background-color: {theme.tile_selected};
                            border: 1px solid {theme.accent_hover};
                        }}
                        QPushButton:checked:pressed {{
                            background-color: {theme.tile_selected};
                            border: 1px solid {theme.accent_pressed};
                        }}
                        QPushButton:focus {{
                            outline: none;
                            border: 1px solid {theme.border};
                        }}
                        QPushButton:checked:focus {{
                            outline: none;
                            border: 2px solid {theme.accent};
                        }}

                        /* override: hide border when selected (wins because it's last) */
                        QPushButton:checked,
                        QPushButton:checked:hover,
                        QPushButton:checked:pressed,
                        QPushButton:checked:focus {{
                            border: 1px solid transparent;
                        }}
                    """)
                else:
                    tile_btn = QPushButton(f"{tile_id}\n(Missing)")
                    tile_btn.setToolTip("This plugin is not installed or was removed.")
                    tile_btn.setEnabled(False)
                    tile_btn.setProperty("tile", True)
                    tile_btn.setStyleSheet(get_missing_tile_style(current_theme_name))
                
                tile_btn.setMinimumSize(150, 120)
                tile_btn.setCheckable(True)
                tile_btn.setProperty("tile_id", tile_id)
                tile_btn.toggled.connect(self._on_tile_toggled)
                tile_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                
                self.tile_grid.addWidget(tile_btn, row, col)
                
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
    
    def _on_tile_toggled(self, checked: bool):
        sender = self.sender()
        tile_id = sender.property("tile_id")
        
        if checked:
            self.selected_tiles.add(tile_id)
        else:
            self.selected_tiles.discard(tile_id)
    
    def _on_profile_selected(self, profile_name: str):
        if profile_name:
            self.settings.set_current_profile(profile_name)
            self._refresh_tiles()
            self.profile_changed.emit(profile_name)
    
    def _on_run_clicked(self):
        if not self.selected_tiles:
            QMessageBox.information(self, "No Selection", "Please select at least one tile to run.")
            return
        
        tile_count = len(self.selected_tiles)
        reply = QMessageBox.question(
            self, "Run Selected?", f"Run {tile_count} selected tile(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.run_selected.emit(list(self.selected_tiles))
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Running...")
            self._execute_selected_plugins()
    
    def _execute_selected_plugins(self):
        plugins_to_run = list(self.selected_tiles)
        self.completed_count = 0
        self.total_plugins = len(plugins_to_run)
        
        for plugin_id in plugins_to_run:
            def make_log_callback(pid):
                def log_callback(message):
                    self.plugin_log.emit(pid, message)
                return log_callback
            
            def make_progress_callback(pid):
                def progress_callback(progress):
                    self.plugin_progress.emit(pid, progress)
                return progress_callback
            
            def make_completion_callback(pid):
                def completion_callback(result):
                    self.completed_count += 1
                    self.plugin_completed.emit(pid)
                    self._check_all_plugins_done()
                return completion_callback
            
            success = self.plugin_executor.execute_plugin(
                plugin_id=plugin_id, params={},
                log_callback=make_log_callback(plugin_id),
                progress_callback=make_progress_callback(plugin_id),
                completion_callback=make_completion_callback(plugin_id)
            )
            
            if not success:
                self.completed_count += 1
                self.plugin_log.emit(plugin_id, f"Failed to start plugin: {plugin_id}")
                self._check_all_plugins_done()
    
    def _check_all_plugins_done(self):
        if hasattr(self, 'completed_count') and hasattr(self, 'total_plugins'):
            if self.completed_count >= self.total_plugins:
                self.btn_run.setEnabled(True)
                self.btn_run.setText("Run Selected")
                
                for i in range(self.tile_grid.count()):
                    widget = self.tile_grid.itemAt(i).widget()
                    if widget and hasattr(widget, 'setChecked'):
                        widget.setChecked(False)
                
                self.selected_tiles.clear()
                del self.completed_count
                del self.total_plugins