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
    QSequentialAnimationGroup, QTimer,
)
from PySide6.QtGui import QColor

import queue as _queue

from techdeck.core.settings import SettingsManager
from techdeck.core.plugin_loader import PluginLoader
from techdeck.core.plugin_executor import PluginExecutor, PluginResult
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
        self._is_running = False  # True while any plugin is executing
        self._restoring = False   # True during programmatic tile checks (no click sound)

        # Use the shared loader if MainWindow gave us one; otherwise scan now.
        if plugin_loader is None:
            plugin_loader = PluginLoader()
            plugin_loader.discover_plugins()
        self.plugin_loader = plugin_loader
        self.plugin_executor = PluginExecutor(self.plugin_loader)
        self._plugin_queue: list = []
        self._plugin_params: dict = {}
        # Per-run, per-family scratch dict. plugin_sdk.request_batch_number
        # caches the first answer here and subsequent same-family plugins reuse
        # it. Cleared when the whole multi-plugin run completes.
        self._shared_state: dict = {"911": {}, "922": {}, "General": {}}
        self.plugin_status_updated.connect(self._apply_plugin_status)
        self._plugins_all_done.connect(self._check_run_complete)
        self._input_idle_requested.connect(self._on_input_idle_requested)

        # Pause / resume state — Phase C. _paused is True between a pause
        # event and the following /resume. _paused_tile_id is the plugin
        # that was running when pause hit; it's re-inserted at the head of
        # _plugin_queue in _on_plugin_complete so /resume picks it up first.
        self._paused: bool = False
        self._paused_tile_id = None
        # Deferred-shelve flag — Phase D. When /shelve is called mid-run, we
        # let the current plugin finish, then save the remainder. The check
        # lives in _on_plugin_complete after the normal-status branches.
        self._shelve_after_current: bool = False

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
        # mode, which reveals the DevKit page in the left nav. Session-only —
        # resets off each launch. Never constructed in a frozen exe, so a
        # shipped build has no way to reach DevKit.
        from techdeck.ui.dev_mode import is_dev_build, get_dev_mode
        if is_dev_build():
            from techdeck.ui.widgets.toggle_switch import ToggleSwitch
            self._dev_label = QLabel("Dev Mode")
            self.dev_switch = ToggleSwitch()
            self.dev_switch.setToolTip(
                "Developer mode (source builds only): reveals the DevKit page "
                "in the sidebar. Resets off each launch.")
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
            if self._is_running:
                self._set_button_cancel_mode()
            else:
                self._set_button_run_mode()
    
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
                card._can_drag = lambda: not self._is_running
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
                tile._can_drag = lambda: not self._is_running
                tile.drag_started.connect(self._tile_ctrl.on_drag_started)
                tile.drag_moved.connect(self._tile_ctrl.on_drag_moved)
                tile.drag_dropped.connect(self._tile_ctrl.on_drag_dropped)
                self._missing_tiles[tile_id] = tile
                widgets[tile_id] = tile

            order.append(tile_id)

        self._tile_ctrl.set_tiles(order, widgets)

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

        from techdeck.core.audio_manager import get_audio_manager, SOUND_CLICK
        get_audio_manager().play(SOUND_CLICK)

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
            # User clicked Cancel — clear queue and abandon any pending shelve.
            self._plugin_queue.clear()
            self._shelve_after_current = False
            self.plugin_executor.cancel_all()
            console = (self._plugin_params or {}).get('console') if hasattr(self, '_plugin_params') else None
            # A plugin blocked at a console prompt never polls cancel_event —
            # abort the input too, or Cancel does nothing until the prompt is
            # answered (bit FormingFinder at its batch prompt, FTOURIGNY-LT).
            if console is not None and getattr(console, 'waiting_for_input', False):
                try:
                    console.abort_input(reason="cancelled")
                except Exception:
                    pass
            # Give immediate feedback — cancellation is cooperative, so the active
            # plugin may take a moment to notice the flag and stop.
            if console is not None:
                console.append_system("Cancelling run — waiting for the current step to stop...")
            # Acknowledge the click on the button itself and swallow further
            # clicks until the run actually reports completion. Without this a
            # double-click's second press could land on the freshly-restored
            # Run Selected button and instantly start a NEW run (FTOURIGNY-LT:
            # run #2 started 32ms after run #1's cancel completed).
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setText("Cancelling...")
                self.run_btn.setEnabled(False)
            return  # button resets when the last plugin reports completion

        if not self.selected_tiles:
            return

        # A fresh "Run Selected" overrides any prior paused state — the user
        # is starting a new run, not resuming. Clear paused tile visual too.
        if self._paused:
            if self._paused_tile_id and self._paused_tile_id in self.tile_cards:
                self.tile_cards[self._paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self._paused = False
            self._paused_tile_id = None
            self._plugin_queue.clear()
            self._shelve_after_current = False

        self.run_selected.emit(list(self.selected_tiles))

        console = None
        parent = self.parent()
        while parent:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS
        # Run plugins in the user-controlled order shown on the Home page
        # (left-to-right, top-to-bottom) — not arbitrary set-iteration order.
        ordered = self.settings.get_profile_tiles()
        self._plugin_queue = [tid for tid in ordered if tid in self.selected_tiles]
        # Append any selected tiles that aren't in the saved order (defensive;
        # shouldn't happen, but don't silently drop selections).
        for tid in self.selected_tiles:
            if tid not in self._plugin_queue:
                self._plugin_queue.append(tid)
        # Remember the largest multi-run for the "run N at once" achievements.
        self.settings.record_run_batch(len(self._plugin_queue))
        # Reset family-shared scratch state at the start of every multi-run.
        self._shared_state = {"911": {}, "922": {}, "General": {}}
        self._plugin_params = {
            'console': console,
            # GUI plugins (requires_main_thread) suppress the auto success sound and call
            # this instead at a meaningful action point (e.g. file saved, code generated).
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            # Family-aware shared scratch (mutated by SDK helpers — same dict
            # is reused across every plugin in this run).
            'shared_state': self._shared_state,
            # Thread-safe hook called by the executor watchdog when a plugin's
            # input prompt has been idle past INPUT_IDLE_PAUSE_THRESHOLD.
            'on_input_idle': self._input_idle_callback,
        }
        self._set_button_cancel_mode()
        if not self._start_next_plugin():
            # Nothing could start (e.g. every queued plugin failed validation)
            # — unwind immediately so the button doesn't stick on Cancel.
            self._plugins_all_done.emit()

    def _start_next_plugin(self) -> bool:
        """Start the next queued plugin. Returns True if a plugin was started."""
        while self._plugin_queue:
            tile_id = self._plugin_queue.pop(0)
            plugin = self.plugin_executor.plugin_loader.get_plugin(tile_id)
            plugin_timeout = getattr(plugin, "timeout", None) if plugin else None

            self.plugin_status_updated.emit(tile_id, PluginCard.STATUS_RUNNING)

            # Games get their own launch jingle (ASA: The Video Game, etc.).
            if plugin is not None and getattr(plugin, "family", "") == "Games":
                from techdeck.core.audio_manager import get_audio_manager, SOUND_GAME_START
                get_audio_manager().play(SOUND_GAME_START)

            started = self.plugin_executor.execute_plugin(
                tile_id,
                params=self._plugin_params,
                log_callback=lambda msg, tid=tile_id: self._log_buffer.put((tid, msg)),
                progress_callback=lambda prog, tid=tile_id: self.plugin_progress.emit(tid, prog),
                completion_callback=lambda result, tid=tile_id: self._on_plugin_complete(tid, result),
                timeout=plugin_timeout
            )
            if started:
                return True

            # The executor refused to start (e.g. validation failed) and will
            # never fire the completion callback, so unwind here — otherwise
            # the run sticks in Cancel mode with nothing to cancel and the
            # user can't start anything else (bit customer_dxf_quoting when a
            # frozen build was missing a hiddenimport).
            self.plugin_status_updated.emit(tile_id, PluginCard.STATUS_ERROR)
            self.plugin_completed.emit(tile_id)
        return False

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

        # Paused: re-queue this tile at the head, halt the run, reset the
        # button — but do NOT start the next plugin. /resume picks up here.
        if status == "paused":
            if not self._plugin_queue or self._plugin_queue[0] != tile_id:
                self._plugin_queue.insert(0, tile_id)
            self._paused = True
            self._paused_tile_id = tile_id
            self._set_button_run_mode()
            # Don't emit _plugins_all_done — the run is parked, not finished.
            return

        # Deferred shelve — Phase D. /shelve was called mid-run; we let the
        # current plugin finish, now save the remaining queue + shared_state.
        if self._shelve_after_current:
            self._shelve_after_current = False
            if self._plugin_queue:
                tiles = list(self._plugin_queue)
                existed = self.settings.get_shelf() is not None
                self._save_shelf(tiles)
                self._plugin_queue.clear()
                prefix = "[SHELF] (Overwriting prior shelf) " if existed else "[SHELF] "
                plural = "s" if len(tiles) != 1 else ""
                self._console_log(
                    f"{prefix}Saved {len(tiles)} plugin{plural}. Type /resume "
                    f"next session to continue."
                )
                self._plugins_all_done.emit()
                return
            self._console_log(
                "[SHELF] Run finished before any plugin remained — nothing to save."
            )

        # Kick off the next plugin; if nothing started, the whole run is done.
        # _plugins_all_done is the ONLY thing that stops the shell's run spinner
        # (see _check_run_complete), so an exception while starting the next
        # plugin must never skip the terminal emit — otherwise the spinner spins
        # forever after the run is effectively over.
        try:
            started_another = self._start_next_plugin()
        except Exception as exc:
            self._console_log(f"[ERROR] Could not start the next plugin: {exc}")
            started_another = False
        if not started_another:
            self._plugins_all_done.emit()

    def _check_run_complete(self):
        """Called on the main thread via queued signal when no more plugins remain."""
        # all_plugins_done is the ONLY thing that stops the shell's run spinner.
        # Restoring the button must never be able to strand the spinner, so emit
        # the completion signal even if _set_button_run_mode raises (a botched
        # refactor once left a NameError there, spinning "Galvanizing..." forever).
        try:
            self._set_button_run_mode()
        finally:
            self.all_plugins_done.emit()

    # ─── Pause / Resume (Phase C) ─────────────────────────────────────

    def _input_idle_callback(self):
        """Thread-safe — fired by the executor watchdog (background thread) when
        the current input prompt has been idle past
        INPUT_IDLE_PAUSE_THRESHOLD. Routes to the GUI thread via signal."""
        self._input_idle_requested.emit()

    def _on_input_idle_requested(self):
        """Main-thread handler for auto-pause."""
        self.pause_run(source="auto-idle")

    def pause_run(self, source: str = "user") -> None:
        """Park the current run at the active input prompt.

        Aborts ``console.request_input`` with reason="paused"; the worker
        raises ``InputAborted("paused")``, the executor marks the result
        ``PluginStatus.PAUSED``, and ``_on_plugin_complete`` re-inserts the
        tile at the head of the queue. ``/resume`` (or resume_run) restarts
        from there.

        ``source``: "user" for an explicit /pause, "auto-idle" for the
        watchdog hitting the idle threshold. Used only for the console
        message — the mechanism is identical.
        """
        if not self._is_running:
            self._console_log("Nothing to pause.")
            return
        console = (self._plugin_params or {}).get('console')
        if console is None or not getattr(console, 'waiting_for_input', False):
            self._console_log(
                "Can only pause while a plugin is waiting for input — try /pause again at the next prompt."
            )
            return
        active = self.plugin_executor.get_active_plugins()
        if not active:
            return  # race: plugin finished between check and now
        tid = active[0]
        self._paused_tile_id = tid
        if source == "auto-idle":
            self._console_log(
                "[AUTO-PAUSE] No response for 60s. Run paused — type /resume to continue."
            )
        else:
            self._console_log("[PAUSED] Run paused — type /resume to continue.")
        console.abort_input(reason="paused")

    def resume_run(self) -> None:
        """Continue a paused run, or load a shelved run from disk.

        Order of preference:
        1. In-memory paused run — pick up the parked plugin.
        2. Else, if the shelf has content and nothing's running, load it.
        3. Else, "Nothing to resume."

        Re-runs the parked/shelved plugin from its start (any pre-input work
        it had done is lost — accepted trade-off per the plan).
        """
        if self._paused and self._plugin_queue:
            self._paused = False
            self._paused_tile_id = None
            next_tile = self._plugin_queue[0]
            plugin = self.plugin_executor.plugin_loader.get_plugin(next_tile)
            name = plugin.name if plugin else next_tile
            self._console_log(f"[RESUMED] Continuing with {name}.")
            self._set_button_cancel_mode()
            if not self._start_next_plugin():
                self._plugins_all_done.emit()
            return
        if self._paused:
            # Paused flag set but queue is empty — clean up the inconsistency.
            self._paused = False
            self._paused_tile_id = None

        # No in-memory paused run; fall back to the disk shelf if present.
        if not self._is_running:
            shelf = self.settings.get_shelf()
            if shelf is not None:
                self._load_shelf_and_run(shelf)
                return

        self._console_log("Nothing to resume.")

    def _console_log(self, msg: str) -> None:
        """Emit a system message to the shared console. Used by pause/resume
        and shelve flows where we don't want to go through plugin_log (which
        is meant for plugin output)."""
        console = (self._plugin_params or {}).get('console')
        if console is None:
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, 'console'):
                    console = parent.console
                    break
                parent = parent.parent()
        if console is not None and hasattr(console, 'append_system'):
            console.append_system(msg)

    # ─── Shelve (Phase D) ─────────────────────────────────────────────

    def shelve_run(self) -> None:
        """Save the rest of the current run to disk so it can be resumed
        across a TechDeck restart. Three cases:

        * **Paused** — snapshot immediately (queue + shared_state), clear
          paused state.
        * **Running** — defer: let the current plugin finish, then snapshot
          the remainder. Acts on the _shelve_after_current flag, consumed
          in _on_plugin_complete.
        * **Idle** — log "Nothing to shelve."
        """
        if self._paused:
            tiles = list(self._plugin_queue)  # already starts with paused tile
            if not tiles:
                self._console_log("Nothing to shelve.")
                return
            existed = self.settings.get_shelf() is not None
            self._save_shelf(tiles)
            self._plugin_queue.clear()
            # Reset paused-tile visual since the run is no longer parked.
            if self._paused_tile_id and self._paused_tile_id in self.tile_cards:
                self.tile_cards[self._paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self._paused = False
            self._paused_tile_id = None
            prefix = "[SHELF] (Overwriting prior shelf) " if existed else "[SHELF] "
            plural = "s" if len(tiles) != 1 else ""
            self._console_log(
                f"{prefix}Saved {len(tiles)} plugin{plural}. Type /resume next session to continue."
            )
            return
        if self._is_running:
            self._shelve_after_current = True
            self._console_log(
                "[SHELF] Will shelve the remainder after the current plugin finishes."
            )
            return
        self._console_log("Nothing to shelve.")

    def view_shelf(self) -> None:
        """Print the current shelf contents."""
        shelf = self.settings.get_shelf()
        if shelf is None:
            self._console_log("Shelf is empty.")
            return
        tile_ids = shelf.get("remaining_tile_ids", [])
        stored_at = shelf.get("stored_at", "?")
        profile = shelf.get("originating_profile", "?")
        shared = shelf.get("shared_state", {})
        lines = [
            f"[SHELF] {len(tile_ids)} plugin{'s' if len(tile_ids) != 1 else ''} "
            f"(saved {stored_at}, profile '{profile}')"
        ]
        for i, tid in enumerate(tile_ids, 1):
            plugin = self.plugin_loader.get_plugin(tid)
            name = plugin.name if plugin else f"{tid} (missing from disk)"
            lines.append(f"  {i}. {name}")
        captured = [
            (fam, info.get("batch_number"))
            for fam, info in shared.items()
            if isinstance(info, dict) and info.get("batch_number")
        ]
        if captured:
            lines.append("  Captured batch numbers:")
            for fam, bn in captured:
                lines.append(f"    {fam}: {bn}")
        self._console_log("\n".join(lines))

    def clear_shelf(self) -> None:
        """Drop any persisted shelf entry."""
        had_one = self.settings.get_shelf() is not None
        self.settings.clear_shelf()
        if had_one:
            self._console_log("[SHELF] Cleared.")
        else:
            self._console_log("Shelf was already empty.")

    def _save_shelf(self, tile_ids: list) -> None:
        """Persist tile_ids + current shared_state as the single shelf entry."""
        from datetime import datetime, timezone
        entry = {
            "stored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "remaining_tile_ids": list(tile_ids),
            "shared_state": {
                k: dict(v) for k, v in (self._shared_state or {}).items()
            },
            "originating_profile": self.settings.get_current_profile_name(),
        }
        self.settings.set_shelf(entry)

    def _load_shelf_and_run(self, shelf: dict) -> None:
        """Pull tiles + shared_state out of a shelf entry and start the run.

        Plugins that no longer exist on disk are skipped with a note (the
        installed plugin set can drift between sessions). The shelf entry
        is cleared as soon as we load it — a partially-failed resume would
        otherwise leave a stale entry around forever.
        """
        tile_ids = shelf.get("remaining_tile_ids", [])
        available = [tid for tid in tile_ids if self.plugin_loader.get_plugin(tid)]
        missing = [tid for tid in tile_ids if not self.plugin_loader.get_plugin(tid)]
        if not available:
            self._console_log(
                "Shelved plugins are all missing from disk; cannot resume. "
                "Use /shelf clear to drop the entry."
            )
            return
        if missing:
            self._console_log(
                f"Skipping {len(missing)} shelved plugin(s) missing from disk: "
                f"{', '.join(missing)}"
            )

        self._plugin_queue = available

        # Restore shared_state, but only into the canonical buckets we know
        # about. A future family added between shelve and resume would be
        # ignored — that's fine; worst case the user gets prompted again.
        shared = shelf.get("shared_state", {})
        self._shared_state = {"911": {}, "922": {}, "General": {}}
        for fam, info in shared.items():
            if fam in self._shared_state and isinstance(info, dict):
                self._shared_state[fam].update(info)

        # Reflect the loaded queue in the UI so the user can see what will run.
        # Programmatic — suppress the per-tile click sound (was a rapid-fire burst).
        self._restoring = True
        try:
            for tid in available:
                self.selected_tiles.add(tid)
                if tid in self.tile_cards:
                    self.tile_cards[tid].set_checked(True)
        finally:
            self._restoring = False

        # Find the console for plugin_params.
        console = None
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS
        self._plugin_params = {
            'console': console,
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            'shared_state': self._shared_state,
            'on_input_idle': self._input_idle_callback,
        }

        # Loaded — consume the shelf entry. If TechDeck crashes mid-run the
        # entry is gone, which is the trade-off we accept for not leaving a
        # stale entry behind forever.
        self.settings.clear_shelf()

        plural = "s" if len(available) != 1 else ""
        self._console_log(
            f"[RESUMED FROM SHELF] Starting {len(available)} plugin{plural} "
            f"(shared state restored)."
        )
        self._set_button_cancel_mode()
        if not self._start_next_plugin():
            self._plugins_all_done.emit()

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
        # Cooldown before accepting clicks again: a double-clicked Cancel's
        # second press must not land on the restored Run Selected button and
        # start a brand-new run (FTOURIGNY-LT: 32ms between cancel completion
        # and the accidental restart).
        self.run_btn.setEnabled(False)

        def _reenable():
            if (not self._is_running and hasattr(self, 'run_btn')
                    and self.run_btn is not None):
                self.run_btn.setEnabled(len(self.selected_tiles) > 0)
        QTimer.singleShot(400, _reenable)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
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
        if len(self.selected_tiles) > 0 and hasattr(self, '_btn_pulse') and self._btn_pulse:
            self._btn_pulse.start()
