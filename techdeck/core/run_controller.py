"""
RunController — orchestrates a Home "Run Selected" run.

Extracted from home_page.py: owns the plugin-queue sequencing, cancellation,
per-plugin completion handling, pause/resume, and shelve (save/restore an
interrupted run), plus the Run/Cancel button state. The low-level threaded
execution stays in PluginExecutor; the run's mutable state lives in RunSession.

HomePage constructs one RunController(self) and delegates its run commands to
it; the controller reaches back into the home page for the view (run button,
tile cards, selected tiles) and emits the home page's run-lifecycle signals.
"""

import queue as _queue

from PySide6.QtCore import QObject, Signal, QTimer

from techdeck.core.plugin_executor import PluginResult
from techdeck.core.run_session import RunSession
from techdeck.ui.widgets.plugin_card import PluginCard


class RunController(QObject):
    # Internal thread -> main-thread handoffs.
    _plugins_all_done = Signal()      # emitted from a worker thread when a run ends
    _input_idle_requested = Signal()  # watchdog (bg thread) -> main-thread auto-pause

    def __init__(self, home):
        super().__init__(home)
        self.home = home
        self.session = RunSession()
        # Log buffer: worker threads put messages here; a drain timer delivers
        # them to the main thread in batches so the Qt event queue never floods.
        self._log_buffer: _queue.Queue = _queue.Queue()
        self._log_drain_timer = QTimer(self)
        self._log_drain_timer.setInterval(50)
        self._log_drain_timer.timeout.connect(self._drain_log_buffer)
        self._log_drain_timer.start()
        self._plugins_all_done.connect(self._check_run_complete)
        self._input_idle_requested.connect(self._on_input_idle_requested)
        # Card status updates are emitted (possibly cross-thread) on the home
        # page's signal; route them to this main-thread handler.
        home.plugin_status_updated.connect(self._apply_plugin_status)

    @property
    def is_running(self) -> bool:
        return self.session.is_running

    def run_selected_plugins(self):
        """Run selected plugins, or cancel all if already running."""
        if self.session.is_running:
            # User clicked Cancel — clear queue and abandon any pending shelve.
            self.session.queue.clear()
            self.session.shelve_after_current = False
            self.home.plugin_executor.cancel_all()
            console = (self.session.params or {}).get('console')
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
            if hasattr(self.home, 'run_btn') and self.home.run_btn:
                self.home.run_btn.setText("Cancelling...")
                self.home.run_btn.setEnabled(False)
            return  # button resets when the last plugin reports completion

        if not self.home.selected_tiles:
            return

        # A fresh "Run Selected" overrides any prior paused state — the user
        # is starting a new run, not resuming. Clear paused tile visual too.
        if self.session.paused:
            if self.session.paused_tile_id and self.session.paused_tile_id in self.home.tile_cards:
                self.home.tile_cards[self.session.paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self.session.paused = False
            self.session.paused_tile_id = None
            self.session.queue.clear()
            self.session.shelve_after_current = False

        self.home.run_selected.emit(list(self.home.selected_tiles))

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
        ordered = self.home.settings.get_profile_tiles()
        self.session.queue = [tid for tid in ordered if tid in self.home.selected_tiles]
        # Append any selected tiles that aren't in the saved order (defensive;
        # shouldn't happen, but don't silently drop selections).
        for tid in self.home.selected_tiles:
            if tid not in self.session.queue:
                self.session.queue.append(tid)
        # Remember the largest multi-run for the "run N at once" achievements.
        self.home.settings.record_run_batch(len(self.session.queue))
        # Reset family-shared scratch state at the start of every multi-run.
        self.session.shared_state = {"911": {}, "922": {}, "General": {}}
        self.session.params = {
            'console': console,
            # GUI plugins (requires_main_thread) suppress the auto success sound and call
            # this instead at a meaningful action point (e.g. file saved, code generated).
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            # Family-aware shared scratch (mutated by SDK helpers — same dict
            # is reused across every plugin in this run).
            'shared_state': self.session.shared_state,
            # Thread-safe hook called by the executor watchdog when a plugin's
            # input prompt has been idle past INPUT_IDLE_PAUSE_THRESHOLD.
            'on_input_idle': self._input_idle_callback,
        }
        self.set_button_cancel_mode()
        if not self._start_next_plugin():
            # Nothing could start (e.g. every queued plugin failed validation)
            # — unwind immediately so the button doesn't stick on Cancel.
            self._plugins_all_done.emit()

    def _start_next_plugin(self) -> bool:
        """Start the next queued plugin. Returns True if a plugin was started."""
        while self.session.queue:
            tile_id = self.session.queue.pop(0)
            plugin = self.home.plugin_executor.plugin_loader.get_plugin(tile_id)
            plugin_timeout = getattr(plugin, "timeout", None) if plugin else None

            self.home.plugin_status_updated.emit(tile_id, PluginCard.STATUS_RUNNING)

            # Games get their own launch jingle (ASA: The Video Game, etc.).
            if plugin is not None and getattr(plugin, "family", "") == "Games":
                from techdeck.core.audio_manager import get_audio_manager, SOUND_GAME_START
                get_audio_manager().play(SOUND_GAME_START)

            started = self.home.plugin_executor.execute_plugin(
                tile_id,
                params=self.session.params,
                log_callback=lambda msg, tid=tile_id: self._log_buffer.put((tid, msg)),
                progress_callback=lambda prog, tid=tile_id: self.home.plugin_progress.emit(tid, prog),
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
            self.home.plugin_status_updated.emit(tile_id, PluginCard.STATUS_ERROR)
            self.home.plugin_completed.emit(tile_id)
        return False

    def _drain_log_buffer(self):
        """Drain buffered log messages in batches to avoid flooding the Qt event queue."""
        count = 0
        while count < 15:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.home.plugin_log.emit(tid, msg)
            count += 1

    def drain_log_buffer_all(self):
        """Drain all buffered log messages immediately (called before showing an input prompt)."""
        while True:
            try:
                tid, msg = self._log_buffer.get_nowait()
            except _queue.Empty:
                break
            self.home.plugin_log.emit(tid, msg)

    def _apply_plugin_status(self, tile_id: str, status: str):
        """Update a card's status indicator. Always runs on main thread via signal."""
        if tile_id in self.home.tile_cards:
            self.home.tile_cards[tile_id].set_status(status)

    def _on_plugin_complete(self, tile_id: str, result: PluginResult):
        """Handle plugin completion. Called from background thread."""
        status = result.status.value if result else PluginCard.STATUS_ERROR
        # Success: return card to idle. Failures persist visually until next run.
        final_status = PluginCard.STATUS_IDLE if status == "success" else status
        self.home.plugin_status_updated.emit(tile_id, final_status)
        self.home.plugin_completed.emit(tile_id)

        # Paused: re-queue this tile at the head, halt the run, reset the
        # button — but do NOT start the next plugin. /resume picks up here.
        if status == "paused":
            if not self.session.queue or self.session.queue[0] != tile_id:
                self.session.queue.insert(0, tile_id)
            self.session.paused = True
            self.session.paused_tile_id = tile_id
            self.set_button_run_mode()
            # Don't emit _plugins_all_done — the run is parked, not finished.
            return

        # Deferred shelve — Phase D. /shelve was called mid-run; we let the
        # current plugin finish, now save the remaining queue + shared_state.
        if self.session.shelve_after_current:
            self.session.shelve_after_current = False
            if self.session.queue:
                tiles = list(self.session.queue)
                existed = self.home.settings.get_shelf() is not None
                self._save_shelf(tiles)
                self.session.queue.clear()
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
            self.set_button_run_mode()
        finally:
            self.home.all_plugins_done.emit()

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
        if not self.session.is_running:
            self._console_log("Nothing to pause.")
            return
        console = (self.session.params or {}).get('console')
        if console is None or not getattr(console, 'waiting_for_input', False):
            self._console_log(
                "Can only pause while a plugin is waiting for input — try /pause again at the next prompt."
            )
            return
        active = self.home.plugin_executor.get_active_plugins()
        if not active:
            return  # race: plugin finished between check and now
        tid = active[0]
        self.session.paused_tile_id = tid
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
        if self.session.paused and self.session.queue:
            self.session.paused = False
            self.session.paused_tile_id = None
            next_tile = self.session.queue[0]
            plugin = self.home.plugin_executor.plugin_loader.get_plugin(next_tile)
            name = plugin.name if plugin else next_tile
            self._console_log(f"[RESUMED] Continuing with {name}.")
            self.set_button_cancel_mode()
            if not self._start_next_plugin():
                self._plugins_all_done.emit()
            return
        if self.session.paused:
            # Paused flag set but queue is empty — clean up the inconsistency.
            self.session.paused = False
            self.session.paused_tile_id = None

        # No in-memory paused run; fall back to the disk shelf if present.
        if not self.session.is_running:
            shelf = self.home.settings.get_shelf()
            if shelf is not None:
                self._load_shelf_and_run(shelf)
                return

        self._console_log("Nothing to resume.")

    def _console_log(self, msg: str) -> None:
        """Emit a system message to the shared console. Used by pause/resume
        and shelve flows where we don't want to go through plugin_log (which
        is meant for plugin output)."""
        console = (self.session.params or {}).get('console')
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
        if self.session.paused:
            tiles = list(self.session.queue)  # already starts with paused tile
            if not tiles:
                self._console_log("Nothing to shelve.")
                return
            existed = self.home.settings.get_shelf() is not None
            self._save_shelf(tiles)
            self.session.queue.clear()
            # Reset paused-tile visual since the run is no longer parked.
            if self.session.paused_tile_id and self.session.paused_tile_id in self.home.tile_cards:
                self.home.tile_cards[self.session.paused_tile_id].set_status(PluginCard.STATUS_IDLE)
            self.session.paused = False
            self.session.paused_tile_id = None
            prefix = "[SHELF] (Overwriting prior shelf) " if existed else "[SHELF] "
            plural = "s" if len(tiles) != 1 else ""
            self._console_log(
                f"{prefix}Saved {len(tiles)} plugin{plural}. Type /resume next session to continue."
            )
            return
        if self.session.is_running:
            self.session.shelve_after_current = True
            self._console_log(
                "[SHELF] Will shelve the remainder after the current plugin finishes."
            )
            return
        self._console_log("Nothing to shelve.")

    def view_shelf(self) -> None:
        """Print the current shelf contents."""
        shelf = self.home.settings.get_shelf()
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
            plugin = self.home.plugin_loader.get_plugin(tid)
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
        had_one = self.home.settings.get_shelf() is not None
        self.home.settings.clear_shelf()
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
                k: dict(v) for k, v in (self.session.shared_state or {}).items()
            },
            "originating_profile": self.home.settings.get_current_profile_name(),
        }
        self.home.settings.set_shelf(entry)

    def _load_shelf_and_run(self, shelf: dict) -> None:
        """Pull tiles + shared_state out of a shelf entry and start the run.

        Plugins that no longer exist on disk are skipped with a note (the
        installed plugin set can drift between sessions). The shelf entry
        is cleared as soon as we load it — a partially-failed resume would
        otherwise leave a stale entry around forever.
        """
        tile_ids = shelf.get("remaining_tile_ids", [])
        available = [tid for tid in tile_ids if self.home.plugin_loader.get_plugin(tid)]
        missing = [tid for tid in tile_ids if not self.home.plugin_loader.get_plugin(tid)]
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

        self.session.queue = available

        # Restore shared_state, but only into the canonical buckets we know
        # about. A future family added between shelve and resume would be
        # ignored — that's fine; worst case the user gets prompted again.
        shared = shelf.get("shared_state", {})
        self.session.shared_state = {"911": {}, "922": {}, "General": {}}
        for fam, info in shared.items():
            if fam in self.session.shared_state and isinstance(info, dict):
                self.session.shared_state[fam].update(info)

        # Reflect the loaded queue in the UI so the user can see what will run.
        # Programmatic — suppress the per-tile click sound (was a rapid-fire burst).
        self.home._restoring = True
        try:
            for tid in available:
                self.home.selected_tiles.add(tid)
                if tid in self.home.tile_cards:
                    self.home.tile_cards[tid].set_checked(True)
        finally:
            self.home._restoring = False

        # Find the console for plugin_params.
        console = None
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, 'console'):
                console = parent.console
                break
            parent = parent.parent()

        from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS
        self.session.params = {
            'console': console,
            'on_success': lambda: get_audio_manager().play(SOUND_SUCCESS),
            'shared_state': self.session.shared_state,
            'on_input_idle': self._input_idle_callback,
        }

        # Loaded — consume the shelf entry. If TechDeck crashes mid-run the
        # entry is gone, which is the trade-off we accept for not leaving a
        # stale entry behind forever.
        self.home.settings.clear_shelf()

        plural = "s" if len(available) != 1 else ""
        self._console_log(
            f"[RESUMED FROM SHELF] Starting {len(available)} plugin{plural} "
            f"(shared state restored)."
        )
        self.set_button_cancel_mode()
        if not self._start_next_plugin():
            self._plugins_all_done.emit()

    def set_button_cancel_mode(self):
        """Switch the Run Selected button to Cancel (red) while plugins run."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self.session.is_running = True
        if not hasattr(self.home, 'run_btn') or not self.home.run_btn:
            return
        self.home.run_btn.setText("Cancel")
        self.home.run_btn.setEnabled(True)
        self.home.run_btn.setStyleSheet(f"""
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
        if hasattr(self.home, '_btn_pulse') and self.home._btn_pulse:
            self.home._btn_pulse.stop()
        if hasattr(self.home, '_btn_glow') and self.home._btn_glow:
            self.home._btn_glow.setBlurRadius(0)

    def set_button_run_mode(self):
        """Restore the button to Run Selected (accent) after all plugins finish."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        self.session.is_running = False
        if not hasattr(self.home, 'run_btn') or not self.home.run_btn:
            return
        self.home.run_btn.setText("Run Selected")
        # Cooldown before accepting clicks again: a double-clicked Cancel's
        # second press must not land on the restored Run Selected button and
        # start a brand-new run (FTOURIGNY-LT: 32ms between cancel completion
        # and the accidental restart).
        self.home.run_btn.setEnabled(False)

        def _reenable():
            if (not self.session.is_running and hasattr(self.home, 'run_btn')
                    and self.home.run_btn is not None):
                self.home.run_btn.setEnabled(len(self.home.selected_tiles) > 0)
        QTimer.singleShot(400, _reenable)
        self.home.run_btn.setStyleSheet(f"""
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
        if len(self.home.selected_tiles) > 0 and hasattr(self.home, '_btn_pulse') and self.home._btn_pulse:
            self.home._btn_pulse.start()
