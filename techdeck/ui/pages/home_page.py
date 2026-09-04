"""
TechDeck Home Page - Professional Card Design
PHASE 3: Enhanced tiles with elevation, hover effects, status indicators, and modern card styling
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QScrollArea,
    QGraphicsDropShadowEffect, QApplication,
)
from PySide6.QtCore import (
    Signal, Qt, QPropertyAnimation, QEasingCurve,
    QSequentialAnimationGroup,
)
from PySide6.QtGui import QColor


from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor
from techdeck.core.run_controller import RunController
from pathlib import Path
from techdeck.ui.utils import make_tinted_svg_copy
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import get_theme_manager

# Tile widgets, the grid controller, and the tile-geometry constants were
# extracted to sibling modules; import them back and re-export so shell.py /
# library_page.py keep working with `from ...home_page import HOME_TILE_H / TILE_*`.
from techdeck.ui.widgets.plugin_card import (
    TILE_W, TILE_H, TILE_ICON, TILE_ICON_BOX,
    HOME_TILE_W, HOME_TILE_H, HOME_TILE_ICON, HOME_TILE_ICON_BOX,
    _FAMILY_BADGE_COLORS, _strip_family_prefix, _EyeFollow,
    PluginCard, _MissingTile,
)
from techdeck.ui.widgets.tile_grid import _GridSurface, TileGridController

class HomePage(QWidget, ThemeAware):
    profile_changed = Signal(str)
    kit_changed = Signal()  # tile membership of the current kit changed from Home (e.g. missing-tile Remove)
    open_library = Signal()
    run_selected = Signal(list)
    plugin_log = Signal(str, str)
    plugin_progress = Signal(str, int)
    plugin_completed = Signal(str)
    plugin_status_updated = Signal(str, str)  # tile_id, status — safe to emit from any thread
    all_plugins_done = Signal()               # emitted on main thread after every plugin in a run finishes
    _plugins_all_done = Signal()              # internal — emitted from worker thread, handled on main thread
    # Fired by the executor watchdog (background thread) when a plugin's input
    # prompt has been idle past the auto-pause threshold. We route it through
    # a Qt signal so the actual pause work runs on the GUI thread.
    _input_idle_requested = Signal()

    def __init__(self, settings: SettingsManager, parent=None, plugin_loader: 'PluginLoader' = None):
        super().__init__(parent)
        self.settings = settings
        self.selected_tiles = set()
        self.tile_cards = {}  # PHASE 3: Track card widgets by tile_id
        self._missing_tiles: dict = {}  # tile_id -> _MissingTile for tiles whose plugin folder is gone
        self._restoring = False   # True during programmatic tile checks (no click sound)

        # Use the shared loader if MainWindow gave us one; otherwise scan now.
        if plugin_loader is None:
            plugin_loader = PluginLoader()
            plugin_loader.discover_plugins()
        self.plugin_loader = plugin_loader
        self.plugin_executor = PluginExecutor(self.plugin_loader)

        # Run orchestration (queue, cancel, pause/resume, shelve) lives in
        # RunController; the run STATE lives in its RunSession. HomePage keeps
        # the view (tiles + run button) and delegates the run commands below.
        self._run = RunController(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Profile Controls Container
        self._profile_container = QWidget()
        self._profile_container.setFixedHeight(50)
        profile_layout = QHBoxLayout(self._profile_container)
        profile_layout.setContentsMargins(20, 8, 20, 8)
        profile_layout.setSpacing(12)

        self._profile_label = QLabel("Active Kit   /")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.setMinimumHeight(36)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)

        self.btn_add = QPushButton("+ Apps")
        self.btn_add.setMinimumHeight(36)
        self.btn_add.clicked.connect(self._on_add_tiles)

        profile_layout.addWidget(self._profile_label)
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addStretch()
        # Dev-mode toggle (source builds only). Switches the shell into dev
        # mode, which reveals the DevKit page in the left nav. Persists across
        # sessions (settings.json). Never constructed in a frozen exe, so a
        # shipped build has no way to reach DevKit.
        from techdeck.ui.dev_mode import is_dev_build, get_dev_mode
        if is_dev_build():
            from techdeck.ui.widgets.toggle_switch import ToggleSwitch
            self._dev_label = QLabel("Dev Mode")
            self.dev_switch = ToggleSwitch()
            self.dev_switch.setToolTip(
                "Developer mode (source builds only): reveals the DevKit page "
                "in the sidebar. Remembered between sessions.")
            self.dev_switch.setChecked(get_dev_mode().is_active())
            self.dev_switch.toggled.connect(get_dev_mode().set_active)
            profile_layout.addWidget(self._dev_label)
            profile_layout.addWidget(self.dev_switch)
        profile_layout.addWidget(self.btn_add)

        layout.addWidget(self._profile_container)

        # Tile Grid Container (scrollable). Replaces QGridLayout with absolute
        # positioning managed by TileGridController so we can animate per-tile
        # pos for drag-reorder (Phase A.2 of multi-plugin-run UX overhaul).
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = _GridSurface()
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._tile_ctrl = TileGridController(self._grid_widget, self.settings, self)
        self._tile_ctrl.set_scroll_area(self._scroll)

        # Empty-state label is a child of the surface (not managed by the controller).
        self._empty_label = QLabel("", self._grid_widget)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        self._grid_widget.resized.connect(self._reposition_empty_label)

        # Subscribes to theme_changed and applies immediately.
        self.setup_theme_awareness()

        self.refresh_profiles()

    # ========== Theme handling =====================================

    def apply_theme(self):
        """Re-style every theme-sensitive surface owned by HomePage.

        Tile cards subscribe individually (PluginCard mixes in
        ThemeAware). This method covers the profile bar, scroll area,
        and the run button.
        """
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        theme_name = get_theme_manager().get_current_theme()

        self.setStyleSheet(f"HomePage {{ background-color: {theme.background}; }}")

        self._profile_container.setStyleSheet(f"""
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

        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
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

        self._scroll.setStyleSheet(f"""
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
        self._grid_widget.setStyleSheet(f"background-color: {theme.background};")

        # Missing-tile placeholders bake their colors in, so re-stamp them here
        # (PluginCards re-theme themselves via ThemeAware).
        for tile in self._missing_tiles.values():
            tile.restyle(theme)

        # Run button (shell hands this off to us via set_run_button).
        # Re-style based on its current mode (Run vs Cancel).
        if hasattr(self, "run_btn") and self.run_btn:
            if self._run.is_running:
                self._run.set_button_cancel_mode()
            else:
                self._run.set_button_run_mode()
    

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
        # Tear down any previous widgets the controller was managing.
        self._tile_ctrl.clear()
        for w in list(self._managed_tile_widgets()):
            w.setParent(None)
            w.deleteLater()
        self.tile_cards.clear()
        self._missing_tiles = {}

        tile_ids = self.settings.get_profile_tiles()

        # Selection lives in self.selected_tiles, but the cards are rebuilt from
        # scratch here — so drop any selection whose tile just left the kit, then
        # re-check the survivors below so the set and the cards always agree.
        # Without the drop a tile removed in the Library stayed ARMED with no card
        # to show it, and ran on every subsequent Run Selected (CPENG_TOWERPC
        # 2026-08-03: 902 DXF Prep, removed from the 'Game' kit, kept starting
        # alongside the game and popping its folder picker over everything).
        self.selected_tiles &= set(tile_ids)
        self._sync_run_button()

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        if not tile_ids:
            self._empty_label.setText("No apps in this kit.\n\nClick '+ Apps' to add some!")
            self._empty_label.setStyleSheet(
                f"color: {theme.text_secondary}; font-size: 14px; padding: 40px; "
                f"background: transparent;"
            )
            self._empty_label.show()
            self._reposition_empty_label()
            return

        self._empty_label.hide()

        order: list = []
        widgets: dict = {}
        for tile_id in tile_ids:
            plugin = self.plugin_loader.get_plugin(tile_id)

            if plugin:
                desc = plugin.description
                if len(desc) > 60:
                    desc = desc[:60] + "..."
                card = PluginCard(
                    plugin=plugin,
                    plugin_desc=desc,
                    tile_id=tile_id,
                    theme=theme,
                    parent=self._grid_widget,
                )
                card.toggled.connect(lambda checked, tid=tile_id: self._on_tile_toggled(tid, checked))
                card._can_drag = lambda: not self._run.is_running
                card.drag_started.connect(self._tile_ctrl.on_drag_started)
                card.drag_moved.connect(self._tile_ctrl.on_drag_moved)
                card.drag_dropped.connect(self._tile_ctrl.on_drag_dropped)
                self.tile_cards[tile_id] = card
                widgets[tile_id] = card
                # Yield to event loop between cards so the splash GIF can advance
                QApplication.processEvents()
            else:
                tile = _MissingTile(
                    tile_id=tile_id,
                    theme=theme,
                    on_remove=self._remove_missing_plugin,
                    parent=self._grid_widget,
                )
                tile._can_drag = lambda: not self._run.is_running
                tile.drag_started.connect(self._tile_ctrl.on_drag_started)
                tile.drag_moved.connect(self._tile_ctrl.on_drag_moved)
                tile.drag_dropped.connect(self._tile_ctrl.on_drag_dropped)
                self._missing_tiles[tile_id] = tile
                widgets[tile_id] = tile

            order.append(tile_id)

        self._tile_ctrl.set_tiles(order, widgets)

        # Re-check the cards that survived the prune above — set_checked emits
        # toggled, so flag it as programmatic (no per-tile click sound).
        if self.selected_tiles:
            self._restoring = True
            try:
                for tid in self.selected_tiles:
                    card = self.tile_cards.get(tid)
                    if card is not None:
                        card.set_checked(True)
            finally:
                self._restoring = False

        # Staggered entrance for the live PluginCards (missing tiles stay solid).
        for i, tid in enumerate(tid for tid in order if tid in self.tile_cards):
            self.tile_cards[tid].start_entrance(i * 50)

    def _managed_tile_widgets(self):
        """Generator over both live cards and missing-tile placeholders for cleanup."""
        for w in self.tile_cards.values():
            yield w
        for w in getattr(self, "_missing_tiles", {}).values():
            yield w

    def _reposition_empty_label(self):
        if not self._empty_label.isVisible():
            return
        w = self._grid_widget.width()
        h = self._grid_widget.height()
        lw = min(400, max(200, w - 80))
        # Height from the wrapped content, not a fixed constant — the fixed
        # 120px clipped the message (3 text lines + the QSS padding > 120).
        hfw = self._empty_label.heightForWidth(lw)
        lh = max(150, hfw if hfw > 0 else 0)
        self._empty_label.setGeometry((w - lw) // 2, max(20, (h - lh) // 2), lw, lh)
    

    def _on_tile_toggled(self, tile_id: str, checked: bool):
        if checked:
            self.selected_tiles.add(tile_id)
        else:
            self.selected_tiles.discard(tile_id)

        # Only a genuine user click should click; programmatic restores (e.g.
        # resuming a shelved run, which checks every queued tile) stay silent.
        if not self._restoring:
            from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
            get_audio_manager().play(SOUND_CLICK)

        self._sync_run_button()

    def _sync_run_button(self) -> None:
        """Match the Run button (enabled state + glow pulse) to the selection.

        Called on every toggle AND after a tile refresh — a refresh can change
        the selection by pruning tiles that left the kit, and the button must
        not stay lit for a selection that no longer exists.
        """
        if self._run.is_running:
            return  # don't disturb button state while plugins are running

        has_selection = len(self.selected_tiles) > 0
        # run_btn is wired later by the shell, so this can run before it exists.
        if getattr(self, 'run_btn', None):
            self.run_btn.setEnabled(has_selection)
        if getattr(self, '_btn_pulse', None):
            self._btn_pulse.stop()
            self._btn_glow.setColor(self._glow_off_color)
            if has_selection:
                self._btn_pulse.start()


    def _on_profile_selected(self, profile_name: str):
        if not profile_name:
            return

        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)

        self.settings.set_current_profile(profile_name)
        self.selected_tiles.clear()

        if not self._run.is_running:
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setEnabled(False)
            if hasattr(self, '_btn_pulse') and self._btn_pulse:
                self._btn_pulse.stop()
                self._btn_glow.setColor(self._glow_off_color)

        self._refresh_tiles()
        self.profile_changed.emit(profile_name)
    

    def _on_add_tiles(self):
        self.open_library.emit()
    

    def set_run_button(self, btn: QPushButton):
        """Store reference to Run Selected button and wire up glow animation."""
        self.run_btn = btn
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run.run_selected_plugins)

        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()

        self._btn_glow = QGraphicsDropShadowEffect(self.run_btn)
        # FIXED blur radius — never animated. Animating a shadow's SIZE makes
        # Qt re-rasterize the widget into a differently-sized rect every frame,
        # and on fractional Windows display scaling (125%/150%) the rounding
        # lands on different pixels frame to frame, so the button visibly
        # "vibrates" (reported 2026-09-03). The glow breathes by COLOR ALPHA at
        # constant geometry instead — same look, same pixels every frame.
        # Gate: tests/ui/test_no_blur_animations.py.
        self._btn_glow.setBlurRadius(14)
        self._btn_glow.setOffset(0, 0)
        self._glow_on_color = QColor(theme.accent)
        self._glow_on_color.setAlpha(200)
        self._glow_off_color = QColor(theme.accent)
        self._glow_off_color.setAlpha(0)
        self._btn_glow.setColor(self._glow_off_color)   # idle = invisible glow
        self.run_btn.setGraphicsEffect(self._btn_glow)

        pulse_up = QPropertyAnimation(self._btn_glow, b"color", self)
        pulse_up.setDuration(600)
        pulse_up.setStartValue(self._glow_off_color)
        pulse_up.setEndValue(self._glow_on_color)
        pulse_up.setEasingCurve(QEasingCurve.Type.InOutSine)

        pulse_dn = QPropertyAnimation(self._btn_glow, b"color", self)
        pulse_dn.setDuration(600)
        pulse_dn.setStartValue(self._glow_on_color)
        pulse_dn.setEndValue(self._glow_off_color)
        pulse_dn.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._btn_pulse = QSequentialAnimationGroup(self)
        self._btn_pulse.addAnimation(pulse_up)
        self._btn_pulse.addAnimation(pulse_dn)
        self._btn_pulse.setLoopCount(-1)
    

    def _remove_missing_plugin(self, tile_id: str):
        """Remove a missing plugin from the current kit and refresh the grid."""
        current_tiles = list(self.settings.get_profile_tiles())
        if tile_id in current_tiles:
            current_tiles.remove(tile_id)
            self.settings.set_profile_tiles(current_tiles)
        self._refresh_tiles()
        # Keep the Library page in sync — it doesn't refresh on navigation, so
        # without this it keeps showing (and re-saving!) the removed tile.
        self.kit_changed.emit()

    # -- Run commands (delegated to RunController) ------------------------------
    def pause_run(self, source: str = "user") -> None:
        self._run.pause_run(source)

    def resume_run(self) -> None:
        self._run.resume_run()

    def shelve_run(self) -> None:
        self._run.shelve_run()

    def view_shelf(self) -> None:
        self._run.view_shelf()

    def clear_shelf(self) -> None:
        self._run.clear_shelf()

    def _drain_log_buffer_all(self) -> None:
        """Flush buffered plugin logs now (shell calls this before an input prompt)."""
        self._run.drain_log_buffer_all()
