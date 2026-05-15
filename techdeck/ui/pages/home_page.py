"""
TechDeck Home Page - Professional Card Design
PHASE 3: Enhanced tiles with elevation, hover effects, status indicators, and modern card styling
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QScrollArea, QGridLayout, QMessageBox, QCheckBox, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Signal, Qt, QPropertyAnimation, QEasingCurve, Property,
    QVariantAnimation, QSequentialAnimationGroup, QTimer,
)
from PySide6.QtGui import QFont, QColor

import queue as _queue

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor, PluginResult
from techdeck.ui.theme import get_missing_tile_style
from pathlib import Path
from techdeck.ui.theme import get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.theme_aware import ThemeAware


class PluginCard(QFrame, ThemeAware):
    """Professional plugin card with shadow elevation, hover lift, pulse, and flash animations."""

    toggled = Signal(bool)

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CANCELLED = "cancelled"
    STATUS_TIMEOUT = "timeout"

    def __init__(self, plugin_name: str, plugin_desc: str, tile_id: str, theme, parent=None):
        super().__init__(parent)
        self.tile_id = tile_id
        self.theme = theme
        self._is_checked = False
        self._status = self.STATUS_IDLE
        self._flash_anim = None
        self._entrance_anim = None

        self.setFixedSize(220, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(20, 20)
        self.checkbox.setStyleSheet("QCheckBox { background-color: transparent; }")
        self.checkbox.toggled.connect(self._on_checkbox_toggled)

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

        if plugin_desc:
            wrapped = f'<div style="max-width: 400px; white-space: normal;">{plugin_desc}</div>'
            self.setToolTip(wrapped)
            self.setToolTipDuration(5000)

        layout.addStretch()
        self._update_card_style()

        # --- Shadow effect (activated after entrance) ---
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 3)
        self._shadow_base_color = self._parse_shadow_color(theme.shadow)
        self._shadow.setColor(self._shadow_base_color)

        # Hover lift animations
        self._hover_in = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_in.setDuration(150)
        self._hover_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_in.setEndValue(20.0)

        self._hover_out = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_out.setDuration(200)
        self._hover_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_out.setEndValue(8.0)

        # Running pulse (shadow breathes)
        pulse_up = QPropertyAnimation(self._shadow, b"blurRadius", self)
        pulse_up.setDuration(700)
        pulse_up.setStartValue(10.0)
        pulse_up.setEndValue(22.0)
        pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        pulse_dn = QPropertyAnimation(self._shadow, b"blurRadius", self)
        pulse_dn.setDuration(700)
        pulse_dn.setStartValue(22.0)
        pulse_dn.setEndValue(10.0)
        pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._pulse_group = QSequentialAnimationGroup(self)
        self._pulse_group.addAnimation(pulse_up)
        self._pulse_group.addAnimation(pulse_dn)
        self._pulse_group.setLoopCount(-1)

        # Entrance: start with opacity effect; swap to shadow when done
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self.setup_theme_awareness()

    @staticmethod
    def _parse_shadow_color(shadow_str: str) -> QColor:
        import re
        m = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', shadow_str)
        if m:
            a = int(float(m.group(4)) * 255)
            return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
        return QColor(0, 0, 0, 60)

    def start_entrance(self, delay_ms: int):
        """Trigger staggered fade-in entrance."""
        self._entrance_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._entrance_anim.setStartValue(0.0)
        self._entrance_anim.setEndValue(1.0)
        self._entrance_anim.setDuration(280)
        self._entrance_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._entrance_anim.finished.connect(self._on_entrance_done)
        QTimer.singleShot(delay_ms, self._entrance_anim.start)

    def _on_entrance_done(self):
        """Swap opacity effect for shadow effect after entrance."""
        self._entrance_anim = None
        self.setGraphicsEffect(self._shadow)
        if self._status == self.STATUS_RUNNING:
            self._start_pulse()

    def apply_theme(self):
        self.theme = self.get_current_palette()
        self._update_card_style()
        self._shadow_base_color = self._parse_shadow_color(self.theme.shadow)
        if self._status != self.STATUS_RUNNING:
            self._shadow.setColor(self._shadow_base_color)
        self.name_label.setStyleSheet(f"color: {self.theme.text}; background-color: transparent;")

    def _on_checkbox_toggled(self, checked: bool):
        self._is_checked = checked
        self._update_card_style()
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._is_checked

    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)

    def set_status(self, status: str):
        prev = self._status
        self._status = status

        if status == self.STATUS_RUNNING:
            self._start_pulse()
        elif prev == self.STATUS_RUNNING:
            self._stop_pulse()

        if status == self.STATUS_SUCCESS:
            self._flash_success()
        else:
            self._update_card_style()

    def _start_pulse(self):
        if self.graphicsEffect() is self._shadow:
            c = QColor(self.theme.accent)
            c.setAlpha(160)
            self._shadow.setColor(c)
            self._pulse_group.start()

    def _stop_pulse(self):
        self._pulse_group.stop()
        if self.graphicsEffect() is self._shadow:
            self._shadow.setBlurRadius(8)
            self._shadow.setColor(self._shadow_base_color)

    def _flash_success(self):
        """Flash green background then fade to normal."""
        self._flash_anim = QVariantAnimation(self)
        self._flash_anim.setStartValue(QColor(self.theme.success))
        self._flash_anim.setEndValue(QColor(self.theme.surface))
        self._flash_anim.setDuration(700)
        self._flash_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._flash_anim.valueChanged.connect(self._on_flash_color)
        self._flash_anim.finished.connect(self._on_flash_done)
        self._flash_anim.start()

    def _on_flash_color(self, color: QColor):
        hex_color = color.name()
        self.setStyleSheet(f"""
            PluginCard {{
                background-color: {hex_color};
                border: 2px solid {self.theme.success};
                border-radius: 12px;
            }}
            PluginCard:hover {{
                background-color: {hex_color};
                border: 2px solid {self.theme.success};
            }}
        """)

    def _on_flash_done(self):
        self._flash_anim = None
        self._update_card_style()

    def _update_card_style(self):
        if self._status == self.STATUS_RUNNING:
            border_color = self.theme.accent
            border_hover = self.theme.accent_hover
        elif self._status in (self.STATUS_ERROR, self.STATUS_TIMEOUT):
            border_color = self.theme.error
            border_hover = self.theme.error
        elif self._status == self.STATUS_CANCELLED:
            border_color = self.theme.warning
            border_hover = self.theme.warning
        elif self._is_checked:
            border_color = self.theme.accent
            border_hover = self.theme.accent_hover
        else:
            border_color = self.theme.border_strong
            border_hover = self.theme.accent

        self.setStyleSheet(f"""
            PluginCard {{
                background-color: {self.theme.surface};
                border: 2px solid {border_color};
                border-radius: 12px;
            }}
            PluginCard:hover {{
                background-color: {self.theme.surface_hover};
                border: 2px solid {border_hover};
            }}
        """)

    def enterEvent(self, event):
        if self.graphicsEffect() is self._shadow and self._status != self.STATUS_RUNNING:
            self._hover_out.stop()
            self._hover_in.setStartValue(self._shadow.blurRadius())
            self._hover_in.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.graphicsEffect() is self._shadow and self._status != self.STATUS_RUNNING:
            self._hover_in.stop()
            self._hover_out.setStartValue(self._shadow.blurRadius())
            self._hover_out.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
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
    plugin_status_updated = Signal(str, str)  # tile_id, status — safe to emit from any thread
    all_plugins_done = Signal()               # emitted on main thread after every plugin in a run finishes
    _plugins_all_done = Signal()              # internal — emitted from worker thread, handled on main thread

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tiles = set()
        self.tile_cards = {}  # PHASE 3: Track card widgets by tile_id
        self._is_running = False  # True while any plugin is executing
        
        self.plugin_loader = PluginLoader()
        self.plugin_loader.discover_plugins()
        self.plugin_executor = PluginExecutor(self.plugin_loader)
        self._plugin_queue: list = []
        self._plugin_params: dict = {}
        self.plugin_status_updated.connect(self._apply_plugin_status)
        self._plugins_all_done.connect(self._check_run_complete)

        # Log buffer: worker threads put messages here; drain timer delivers them
        # to the main thread in batches so the Qt event queue never floods.
        self._log_buffer: _queue.Queue = _queue.Queue()
        self._log_drain_timer = QTimer(self)
        self._log_drain_timer.setInterval(50)
        self._log_drain_timer.timeout.connect(self._drain_log_buffer)
        self._log_drain_timer.start()

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
                    # Missing plugin - show disabled card with remove button
                    card = QFrame()
                    card.setFixedSize(220, 140)
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(16, 12, 16, 12)
                    card_layout.setSpacing(6)

                    missing_label = QLabel(f"{tile_id}\n(Missing)")
                    missing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    missing_label.setWordWrap(True)
                    missing_label.setStyleSheet("color: #888; font-size: 11px;")

                    remove_btn = QPushButton("Remove from Kit")
                    remove_btn.setStyleSheet("""
                        QPushButton {
                            background-color: transparent;
                            color: #EF4444;
                            border: 1px solid #EF4444;
                            border-radius: 4px;
                            font-size: 10px;
                            padding: 4px 8px;
                        }
                        QPushButton:hover {
                            background-color: #EF4444;
                            color: white;
                        }
                    """)
                    remove_btn.clicked.connect(
                        lambda checked=False, tid=tile_id: self._remove_missing_plugin(tid)
                    )

                    card_layout.addWidget(missing_label)
                    card_layout.addWidget(remove_btn)

                    card.setStyleSheet(f"""
                        QFrame {{
                            background-color: {theme.surface};
                            border: 1px dashed {theme.border};
                            border-radius: 12px;
                        }}
                    """)

                    self.tile_grid.addWidget(card, row, col)
                
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        # Staggered entrance for all PluginCards
        for i, card in enumerate(self.tile_cards.values()):
            card.start_entrance(i * 50)
    
    def _on_tile_toggled(self, tile_id: str, checked: bool):
        if checked:
            self.selected_tiles.add(tile_id)
        else:
            self.selected_tiles.discard(tile_id)

        if self._is_running:
            return  # don't disturb button state while plugins are running

        has_selection = len(self.selected_tiles) > 0
        if hasattr(self, 'run_btn') and self.run_btn:
            self.run_btn.setEnabled(has_selection)
        if hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.stop()
            self._btn_glow.setBlurRadius(0)
            if has_selection:
                self._btn_pulse.start()
    
    def _on_profile_selected(self, profile_name: str):
        if not profile_name:
            return

        self.settings.set_current_profile(profile_name)
        self.selected_tiles.clear()

        if not self._is_running:
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setEnabled(False)
            if hasattr(self, '_btn_pulse') and self._btn_pulse:
                self._btn_pulse.stop()
                self._btn_glow.setBlurRadius(0)

        self._refresh_tiles()
        self.profile_changed.emit(profile_name)
    
    def _on_add_tiles(self):
        self.open_library.emit()
    
    def set_run_button(self, btn: QPushButton):
        """Store reference to Run Selected button and wire up glow animation."""
        self.run_btn = btn
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run_selected_plugins)

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        self._btn_glow = QGraphicsDropShadowEffect(self.run_btn)
        self._btn_glow.setBlurRadius(0)
        self._btn_glow.setOffset(0, 0)
        glow_color = QColor(theme.accent)
        glow_color.setAlpha(200)
        self._btn_glow.setColor(glow_color)
        self.run_btn.setGraphicsEffect(self._btn_glow)

        pulse_up = QPropertyAnimation(self._btn_glow, b"blurRadius", self)
        pulse_up.setDuration(600)
        pulse_up.setStartValue(0.0)
        pulse_up.setEndValue(14.0)
        pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        pulse_dn = QPropertyAnimation(self._btn_glow, b"blurRadius", self)
        pulse_dn.setDuration(600)
        pulse_dn.setStartValue(14.0)
        pulse_dn.setEndValue(0.0)
        pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._btn_pulse = QSequentialAnimationGroup(self)
        self._btn_pulse.addAnimation(pulse_up)
        self._btn_pulse.addAnimation(pulse_dn)
        self._btn_pulse.setLoopCount(-1)
    
    def _run_selected_plugins(self):
        """Run selected plugins, or cancel all if already running."""
        if self._is_running:
            # User clicked Cancel — clear queue and signal all active plugins to stop
            self._plugin_queue.clear()
            self.plugin_executor.cancel_all()
            return  # button resets when the last plugin reports completion

        if not self.selected_tiles:
            return

        self.run_selected.emit(list(self.selected_tiles))

        console = None
        parent = self.parent()
        while parent:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        self._plugin_queue = list(self.selected_tiles)
        self._plugin_params = {'console': console}
        self._set_button_cancel_mode()
        self._start_next_plugin()

    def _start_next_plugin(self) -> bool:
        """Start the next queued plugin. Returns True if a plugin was started."""
        if not self._plugin_queue:
            return False

        tile_id = self._plugin_queue.pop(0)
        plugin = self.plugin_executor.plugin_loader.get_plugin(tile_id)
        plugin_timeout = getattr(plugin, "timeout", None) if plugin else None

        self.plugin_status_updated.emit(tile_id, PluginCard.STATUS_RUNNING)

        self.plugin_executor.execute_plugin(
            tile_id,
            params=self._plugin_params,
            log_callback=lambda msg, tid=tile_id: self._log_buffer.put((tid, msg)),
            progress_callback=lambda prog, tid=tile_id: self.plugin_progress.emit(tid, prog),
            completion_callback=lambda result, tid=tile_id: self._on_plugin_complete(tid, result),
            timeout=plugin_timeout
        )
        return True

    def _remove_missing_plugin(self, tile_id: str):
        """Remove a missing plugin from the current kit and refresh the grid."""
        current_tiles = list(self.settings.get_profile_tiles())
        if tile_id in current_tiles:
            current_tiles.remove(tile_id)
            self.settings.set_profile_tiles(current_tiles)
        self._refresh_tiles()

    def _drain_log_buffer(self):
        """Drain buffered log messages in batches to avoid flooding the Qt event queue."""
        count = 0
        while count < 15:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.plugin_log.emit(tid, msg)
            count += 1

    def _drain_log_buffer_all(self):
        """Drain all buffered log messages immediately (called before showing an input prompt)."""
        while True:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.plugin_log.emit(tid, msg)

    def _apply_plugin_status(self, tile_id: str, status: str):
        """Update a card's status indicator. Always runs on main thread via signal."""
        if tile_id in self.tile_cards:
            self.tile_cards[tile_id].set_status(status)

    def _on_plugin_complete(self, tile_id: str, result: PluginResult):
        """Handle plugin completion. Called from background thread."""
        status = result.status.value if result else PluginCard.STATUS_ERROR
        # Success: return card to idle. Failures persist visually until next run.
        final_status = PluginCard.STATUS_IDLE if status == "success" else status
        self.plugin_status_updated.emit(tile_id, final_status)
        self.plugin_completed.emit(tile_id)
        # Kick off the next plugin; if nothing started, the whole run is done
        started_another = self._start_next_plugin()
        if not started_another:
            self._plugins_all_done.emit()

    def _check_run_complete(self):
        """Called on the main thread via queued signal when no more plugins remain."""
        self._set_button_run_mode()
        self.all_plugins_done.emit()

    def _set_button_cancel_mode(self):
        """Switch the Run Selected button to Cancel (red) while plugins run."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self._is_running = True
        if not hasattr(self, 'run_btn') or not self.run_btn:
            return
        self.run_btn.setText("Cancel")
        self.run_btn.setEnabled(True)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.error};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.error};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: {theme.error};
                color: #FFFFFF;
            }}
        """)
        if hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.stop()
        if hasattr(self, '_btn_glow') and self._btn_glow:
            self._btn_glow.setBlurRadius(0)

    def _set_button_run_mode(self):
        """Restore the button to Run Selected (accent) after all plugins finish."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self._is_running = False
        if not hasattr(self, 'run_btn') or not self.run_btn:
            return
        self.run_btn.setText("Run Selected")
        has_selection = len(self.selected_tiles) > 0
        self.run_btn.setEnabled(has_selection)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_pressed};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
        """)
        if has_selection and hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.start()
