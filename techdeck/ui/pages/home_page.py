"""
TechDeck Home Page - Professional Card Design
PHASE 3: Enhanced tiles with elevation, hover effects, status indicators, and modern card styling
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QScrollArea, QGridLayout, QMessageBox, QCheckBox, QFrame
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QFont

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor, PluginResult
from techdeck.ui.theme import get_missing_tile_style
from pathlib import Path
from techdeck.ui.theme import get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.theme_aware import ThemeAware


class PluginCard(QFrame, ThemeAware):
    """
    PHASE 3: Professional plugin card with elevation, hover effects, and status indicator.
    
    Features:
    - Shadow/elevation on hover
    - Status indicator (idle/running/complete/error)
    - Selection checkbox
    - Smooth animations
    """
    
    toggled = Signal(bool)
    
    def __init__(self, plugin_name: str, plugin_desc: str, tile_id: str, theme, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.theme = theme
        self._is_checked = False
        
        self.setFixedSize(220, 140)  # Slightly larger for better visual weight
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # Top row: checkbox + plugin name
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(20, 20)
        self.checkbox.setStyleSheet("QCheckBox { background-color: transparent; }")
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        
        # Plugin name
        self.name_label = QLabel(plugin_name)
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setWeight(QFont.Weight.DemiBold)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet(f"color: {theme.text}; background-color: transparent;")
        
        top_row.addWidget(self.checkbox)
        top_row.addWidget(self.name_label, 1)
        
        layout.addLayout(top_row)
        
        # Plugin description shown as tooltip on hover with custom styling
        if plugin_desc:
            # Wrap text at approximately 400px for better readability
            wrapped_desc = f'<div style="max-width: 400px; white-space: normal;">{plugin_desc}</div>'
            self.setToolTip(wrapped_desc)
            self.setToolTipDuration(5000)  # Show for 5 seconds
        
        layout.addStretch()
        
        # Apply base styling
        self._update_card_style()
        
        # PROFESSIONAL: Setup theme awareness for live updates
        self.setup_theme_awareness()
    
    def apply_theme(self):
        """PROFESSIONAL: Called automatically when theme changes."""
        # Update theme reference
        self.theme = self.get_current_palette()
        
        # Rebuild all styles with new theme colors
        self._update_card_style()
        
        # Update label colors
        self.name_label.setStyleSheet(f"color: {self.theme.text}; background-color: transparent;")
    
    def _on_checkbox_toggled(self, checked: bool):
        """Handle checkbox toggle."""
        self._is_checked = checked
        self._update_card_style()
        self.toggled.emit(checked)
    
    def is_checked(self) -> bool:
        """Get checked state."""
        return self._is_checked
    
    def set_checked(self, checked: bool):
        """Set checked state programmatically."""
        self.checkbox.setChecked(checked)
    
    def _update_card_style(self):
        """Update card visual style based on state."""
        if self._is_checked:
            # Selected state - accent highlight with shadow
            self.setStyleSheet(f"""
                PluginCard {{
                    background-color: {self.theme.surface};
                    border: 2px solid {self.theme.accent};
                    border-radius: 12px;
                }}
                PluginCard:hover {{
                    background-color: {self.theme.surface_hover};
                    border: 2px solid {self.theme.accent_hover};
                }}
            """)
        else:
            # Default state - elevated card with stronger border
            self.setStyleSheet(f"""
                PluginCard {{
                    background-color: {self.theme.surface};
                    border: 2px solid {self.theme.border_strong};
                    border-radius: 12px;
                }}
                PluginCard:hover {{
                    background-color: {self.theme.surface_hover};
                    border: 2px solid {self.theme.accent};
                }}
            """)
    
    def mousePressEvent(self, event):
        """Handle mouse press - toggle checkbox."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


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
        self.tile_cards = {}  # PHASE 3: Track card widgets by tile_id
        
        self.plugin_loader = PluginLoader()
        self.plugin_loader.discover_plugins()
        self.plugin_executor = PluginExecutor(self.plugin_loader)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        from techdeck.ui.theme import get_current_palette
        # PROFESSIONAL: Get theme from ThemeManager
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        
        self.setStyleSheet(f"HomePage {{ background-color: {theme.background}; }}")
        
        # Profile Controls Container
        profile_container = QWidget()
        profile_container.setFixedHeight(50)
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
        self.profile_combo.setMinimumHeight(36)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        
        # PROFESSIONAL: Get theme from ThemeManager
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        # Select icon folder based on theme (dark/blue use light icons, others use dark icons)
        theme_name = self.settings.get_theme()
        icon_folder = "light" if theme_name in ["dark", "blue"] else "dark"
        icons_dir = Path(__file__).resolve().parents[3] / "assets" / "icons" / icon_folder
        src_arrow = icons_dir / "chevron-down.svg"
        arrow_path = make_tinted_svg_copy(src_arrow, theme.text)
        
        self.profile_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.surface};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px 12px;
                padding-right: 30px;
            }}
            QComboBox:hover {{
                background-color: {theme.surface_hover};
                border: 1px solid {theme.border_strong};
            }}
            QComboBox::drop-down {{
                width: 30px;
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
                border: 1px solid {theme.border_strong};
                border-radius: 8px;
                selection-background-color: {theme.surface_hover};
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {theme.surface_hover};
            }}
        """)
        
        self.btn_add = QPushButton("+ Apps")
        self.btn_add.setMinimumHeight(36)
        self.btn_add.clicked.connect(self._on_add_tiles)
        
        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_pressed};
            }}
        """)
        
        profile_layout.addWidget(profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addStretch()
        profile_layout.addWidget(self.btn_add)
        
        layout.addWidget(profile_container)
        
        # Tile Grid Container (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {theme.background};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {theme.surface};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme.border_strong};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme.text_secondary};
            }}
        """)
        
        grid_widget = QWidget()
        grid_widget.setStyleSheet(f"background-color: {theme.background};")
        
        # PHASE 3: Increase spacing for better card layout
        self.tile_grid = QGridLayout(grid_widget)
        self.tile_grid.setContentsMargins(24, 24, 24, 24)
        self.tile_grid.setSpacing(20)  # More generous spacing
        self.tile_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, 1)
        
        self.refresh_profiles()
    
    def refresh_profiles(self):
        profiles = self.settings.get_profile_names()
        current_profile = self.settings.get_current_profile_name()
        
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(profiles)
        
        if current_profile in profiles:
            self.profile_combo.setCurrentText(current_profile)
        
        self.profile_combo.blockSignals(False)
        
        self._refresh_tiles()
    
    def _refresh_tiles(self):
        # Clear existing tiles
        while self.tile_grid.count():
            item = self.tile_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.tile_cards.clear()
        
        tile_ids = self.settings.get_profile_tiles()
        
        # PROFESSIONAL: Get theme from ThemeManager, not settings
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        
        if not tile_ids:
            label = QLabel("No apps in this kit.\n\nClick '+ Apps' to add some!")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.tile_grid.addWidget(label, 0, 0)
        else:
            row, col = 0, 0
            for tile_id in tile_ids:
                plugin = self.plugin_loader.get_plugin(tile_id)
                
                if plugin:
                    # PHASE 3: Create professional card
                    card = PluginCard(
                        plugin_name=plugin.name,
                        plugin_desc=plugin.description[:60] + "..." if len(plugin.description) > 60 else plugin.description,
                        tile_id=tile_id,
                        theme=theme,
                        parent=self
                    )
                    card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled(tid, checked))
                    
                    self.tile_cards[tile_id] = card
                    self.tile_grid.addWidget(card, row, col)
                else:
                    # Missing plugin - show disabled card
                    card = QFrame()
                    card.setFixedSize(220, 140)
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(16, 16, 16, 16)
                    
                    missing_label = QLabel(f"{tile_id}\n(Missing)")
                    missing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    missing_label.setWordWrap(True)
                    missing_label.setStyleSheet("color: #888; font-size: 11px;")
                    
                    card_layout.addWidget(missing_label)
                    
                    card.setStyleSheet(f"""
                        QFrame {{
                            background-color: {theme.surface};
                            border: 1px dashed {theme.border};
                            border-radius: 12px;
                            opacity: 0.5;
                        }}
                    """)
                    
                    self.tile_grid.addWidget(card, row, col)
                
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
    
    def _on_tile_toggled(self, tile_id: str, checked: bool):
        """PHASE 3: Handle tile selection."""
        if checked:
            self.selected_tiles.add(tile_id)
        else:
            self.selected_tiles.discard(tile_id)
        
        # Enable/disable run button based on selection
        if hasattr(self, 'run_btn') and self.run_btn:
            self.run_btn.setEnabled(len(self.selected_tiles) > 0)
    
    def _on_profile_selected(self, profile_name: str):
        if not profile_name:
            return
        
        self.settings.set_current_profile(profile_name)
        self.selected_tiles.clear()
        
        if hasattr(self, 'run_btn') and self.run_btn:
            self.run_btn.setEnabled(False)
        
        self._refresh_tiles()
        self.profile_changed.emit(profile_name)
    
    def _on_add_tiles(self):
        self.open_library.emit()
    
    def set_run_button(self, btn: QPushButton):
        """Store reference to Run Selected button."""
        self.run_btn = btn
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run_selected_plugins)
    
    def _run_selected_plugins(self):
        """Execute all selected plugins."""
        if not self.selected_tiles:
            return
        
        # Emit signal
        self.run_selected.emit(list(self.selected_tiles))
        
        # PHASE 3: Update card status to "running"
        for tile_id in self.selected_tiles:
            if tile_id in self.tile_cards:
                self.tile_cards[tile_id].set_status("running")
        
        # Execute each selected plugin
        for tile_id in list(self.selected_tiles):
            self.plugin_executor.execute_plugin(
                tile_id,
                log_callback=lambda msg, tid=tile_id: self.plugin_log.emit(tid, msg),
                progress_callback=lambda prog, tid=tile_id: self.plugin_progress.emit(tid, prog),
                completion_callback=lambda result, tid=tile_id: self._on_plugin_complete(tid, result)
            )
    
    def _on_plugin_complete(self, tile_id: str, result: PluginResult):
        """PHASE 3: Handle plugin completion and update card status."""
        # Update card status
        if tile_id in self.tile_cards:
            status_map = {
                "success": "success",
                "error": "error",
                "cancelled": "idle",
                "timeout": "timeout"
            }
            status = status_map.get(result.status.value, "idle")
            self.tile_cards[tile_id].set_status(status)
        
        # Emit completion signal
        self.plugin_completed.emit(tile_id)
