"""
TechDeck Hang Watchdog
======================
Captures what a freeze or a hard crash looks like from the INSIDE, on disk,
so a colleague's "it locked up so I restarted it" is still diagnosable after
the restart. Three independent captures, all landing in
%LOCALAPPDATA%\\TechDeck\\logs:

  hang.log            Stack dumps. `faulthandler` is armed at startup against
                      this file, so a hard crash (access violation in Qt/C++,
                      abort) writes its traceback here — in a frozen windowed
                      build that output otherwise goes nowhere and the app just
                      vanishes. The watchdog thread also dumps EVERY thread's
                      stack when the UI thread stops heartbeating, which is a
                      real hang caught in the act rather than reconstructed.

  session_state.json  A rolling snapshot of what the app is doing (page, kit,
                      running plugins and how long since each last printed,
                      queue, paused, open input prompt, open modal dialog).
                      Written by the watchdog thread from a dict the UI thread
                      refreshes on each heartbeat — so no Qt access off the UI
                      thread, and no disk I/O on it.

  last_session.json   The PREVIOUS process's final session_state, rotated here
                      at startup. This is the one that matters after a restart:
                      `clean_exit: false` means that session was killed or died,
                      and the snapshot tells you what it was doing at the time.

Why the heartbeat is the right hang signal: a modal dialog does NOT count as a
hang — Qt keeps pumping timers inside a modal loop, so waiting on a prompt
heartbeats normally. The snapshot records the open dialog instead. What DOES
trip it is the real thing: blocking I/O on the UI thread, a deadlock, or an
infinite loop in a main-thread (GUI) plugin.

Rules: never raises (every entry point is guarded), never blocks the UI thread
on I/O, and costs one dict rebuild per second.
"""

from __future__ import annotations

import faulthandler
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from techdeck.core.plugin_executor import _run_log_dir

# UI-thread heartbeat interval. Also how often the state snapshot is rebuilt.
_HEARTBEAT_MS = 1000
# Seconds without a heartbeat before the first stack dump. Comfortably above a
# slow-but-alive UI (theme restyle, big grid relayout) so a dump means trouble.
_FIRST_DUMP_AFTER = 10.0
# Dumps per hang episode, at doubling intervals (10s, 20s, 40s, 80s). Several
# samples distinguish "wedged in one place" from "crawling".
_MAX_DUMPS_PER_EPISODE = 4
# Watchdog thread tick.
_TICK = 1.0
# Force a state write this often even when nothing changed (keeps the file's
# timestamp close to the moment of death).
_STATE_MAX_AGE = 30.0
_HANG_LOG_MAX_BYTES = 1_000_000

_watchdog: Optional["HangWatchdog"] = None


def hang_log_path() -> Path:
    return _run_log_dir() / "hang.log"


def state_path() -> Path:
    return _run_log_dir() / "session_state.json"


def previous_state_path() -> Path:
    return _run_log_dir() / "last_session.json"


def previous_session() -> Optional[dict]:
    """The previous process's final state snapshot, or None. `clean_exit`
    False means that session was killed / crashed / froze."""
    try:
        return json.loads(previous_state_path().read_text(encoding="utf-8"))
    except Exception:
        return None


def _snapshot(main_window) -> dict:
    """What the app is doing right now. MUST run on the UI thread (it touches
    Qt objects); every field is individually guarded so a half-built window
    during startup can't break the heartbeat."""
    state: dict = {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if main_window is None:
        return state

    home = getattr(main_window, "home_page", None)

    try:
        stack = main_window.page_stack
        state["page"] = type(stack.currentWidget()).__name__
    except Exception:
        pass

    try:
        state["kit"] = home.settings.get_current_profile_name()
    except Exception:
        pass

    # Running plugins + how long since each last printed anything. A plugin
    # blocked on a prompt or wedged in a network/OneDrive call shows a large
    # silence here while the app itself is perfectly responsive.
    try:
        executor = home.plugin_executor
        active = list(executor.get_active_plugins())
        state["active_plugins"] = active
        now = time.time()
        state["silent_for_s"] = {
            pid: round(now - executor.last_activity.get(pid, now), 1)
            for pid in active
        }
        state["run_elapsed_s"] = {
            pid: round(now - executor.start_times.get(pid, now), 1)
            for pid in active
        }
    except Exception:
        pass

    try:
        session = home._run.session
        state["queue"] = list(session.queue)
        state["paused"] = bool(session.paused)
        state["is_running"] = bool(session.is_running)
    except Exception:
        pass

    try:
        console = main_window.console
        state["waiting_for_input"] = bool(console.waiting_for_input)
        if console.waiting_for_input:
            state["input_prompt"] = str(console.input_prompt)[:200]
    except Exception:
        pass

    # An open modal dialog is the single most common "the whole app is frozen"
    # report that isn't a hang at all (CPENG_TOWERPC 2026-08-03: a folder picker
    # from a plugin the user never meant to run). Name it explicitly.
    try:
        from PySide6.QtWidgets import QApplication
        modal = QApplication.activeModalWidget()
        if modal is not None:
            state["modal_dialog"] = {
                "class": type(modal).__name__,
                "title": modal.windowTitle(),
            }
    except Exception:
        pass

    try:
        state["spinner_active"] = bool(main_window._plugin_spinner_timer.isActive())
    except Exception:
        pass

    return state


def _state_signature(state: dict) -> str:
    """The parts of a snapshot worth rewriting the file for — excludes the
    timestamp and the per-second silence counters, which always differ."""
    keys = ("page", "kit", "active_plugins", "queue", "paused", "is_running",
            "waiting_for_input", "input_prompt", "modal_dialog", "spinner_active")
    return json.dumps({k: state.get(k) for k in keys}, sort_keys=True, default=str)


class HangWatchdog:
    """Heartbeat monitor + crash/hang stack dumper. One per process."""

    def __init__(self, main_window=None):
        self.main_window = main_window
        self._fh = None
        self._timer = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clean_exit = False

        self._last_beat = time.monotonic()
        self._state: dict = {}
        self._started_at = datetime.now()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        log_dir = _run_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_hang_log()
        self._rotate_state_file()

        # Keep this handle open for the whole process: faulthandler writes to
        # the raw fd from its signal handler, so closing it would disarm the
        # crash dump (or crash the crash handler).
        try:
            self._fh = open(hang_log_path(), "a", encoding="utf-8")
        except OSError:
            self._fh = None

        if self._fh is not None:
            try:
                from techdeck.core.constants import APP_VERSION
                version = APP_VERSION
            except Exception:
                version = "?"
            self._emit(
                f"\n=== session start {self._started_at:%Y-%m-%d %H:%M:%S} "
                f"v{version} pid {os.getpid()} ==="
            )
            try:
                # Arms hard-crash dumps (access violation, abort). This is the
                # only reason a frozen windowed build's fatal error leaves a
                # trace at all — there is no stderr to print it to.
                faulthandler.enable(file=self._fh, all_threads=True)
            except Exception:
                pass

        self._start_heartbeat()

        self._thread = threading.Thread(
            target=self._watch, name="TechDeckHangWatchdog", daemon=True
        )
        self._thread.start()

    def _start_heartbeat(self) -> None:
        """QTimer on the UI thread. Its callback is the ONLY place Qt state is
        read, and it does no I/O."""
        if self.main_window is None:
            return
        try:
            from PySide6.QtCore import QTimer
            self._timer = QTimer(self.main_window)
            self._timer.setInterval(_HEARTBEAT_MS)
            self._timer.timeout.connect(self._beat)
            self._timer.start()
            self._beat()  # seed a snapshot immediately
        except Exception:
            self._timer = None

    def _beat(self) -> None:
        self._last_beat = time.monotonic()
        try:
            self._state = _snapshot(self.main_window)
        except Exception:
            pass

    def mark_clean_exit(self) -> None:
        """Called from MainWindow.closeEvent once the close is going through.
        Anything else — kill, crash, power loss — leaves clean_exit false, which
        is exactly the signal the next session's debug report reports on."""
        self._clean_exit = True
        self._stop.set()
        try:
            if self._timer is not None:
                self._timer.stop()
        except Exception:
            pass
        self._write_state()
        self._emit(f"=== session end (clean) {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    # -- watchdog thread ---------------------------------------------------

    def _watch(self) -> None:
        episode_dumps = 0
        next_dump_at = _FIRST_DUMP_AFTER
        last_state_write = 0.0
        last_signature = None

        while not self._stop.wait(_TICK):
            try:
                stale = time.monotonic() - self._last_beat

                if self._timer is not None and stale >= next_dump_at:
                    if episode_dumps < _MAX_DUMPS_PER_EPISODE:
                        episode_dumps += 1
                        self._dump(stale, episode_dumps)
                        next_dump_at *= 2
                elif stale < _FIRST_DUMP_AFTER and episode_dumps:
                    self._emit(
                        f"--- UI thread recovered at {datetime.now():%H:%M:%S} "
                        f"after {episode_dumps} dump(s) ---"
                    )
                    episode_dumps = 0
                    next_dump_at = _FIRST_DUMP_AFTER

                state = self._state
                signature = _state_signature(state)
                age = time.monotonic() - last_state_write
                if signature != last_signature or age >= _STATE_MAX_AGE:
                    self._write_state()
                    last_signature = signature
                    last_state_write = time.monotonic()
            except Exception:
                # A watchdog that can die is worse than no watchdog.
                pass

    def _dump(self, stale: float, n: int) -> None:
        self._emit(
            f"\n--- HANG #{n}: UI thread has not ticked for {stale:.1f}s "
            f"(at {datetime.now():%Y-%m-%d %H:%M:%S}) ---\n"
            f"last known state: {json.dumps(self._state, default=str)}"
        )
        if self._fh is None:
            return
        try:
            faulthandler.dump_traceback(file=self._fh, all_threads=True)
            self._fh.flush()
        except Exception:
            pass

    # -- files -------------------------------------------------------------

    def _write_state(self) -> None:
        payload = dict(self._state)
        payload["pid"] = os.getpid()
        payload["session_started"] = self._started_at.strftime("%Y-%m-%d %H:%M:%S")
        payload["written"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload["clean_exit"] = self._clean_exit
        payload["ui_thread_stale_s"] = round(time.monotonic() - self._last_beat, 1)
        try:
            state_path().write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
        except OSError:
            pass

    def _emit(self, text: str) -> None:
        if self._fh is None:
            return
        try:
            self._fh.write(text + "\n")
            self._fh.flush()
        except (OSError, ValueError):
            pass

    @staticmethod
    def _rotate_hang_log() -> None:
        path = hang_log_path()
        try:
            if path.is_file() and path.stat().st_size > _HANG_LOG_MAX_BYTES:
                backup = path.with_name(path.name + ".1")
                backup.unlink(missing_ok=True)
                path.rename(backup)
        except OSError:
            pass

    @staticmethod
    def _rotate_state_file() -> None:
        """Move the previous process's final snapshot aside BEFORE this one
        starts overwriting it — otherwise restarting to clear a freeze destroys
        the only record of what the frozen session was doing."""
        live = state_path()
        try:
            if live.is_file():
                previous = previous_state_path()
                previous.unlink(missing_ok=True)
                live.rename(previous)
        except OSError:
            pass


# ---------------------------------------------------------------- module API

def start(main_window=None) -> Optional[HangWatchdog]:
    """Arm crash + hang capture for this process. Safe to call once; later
    calls return the existing watchdog. Never raises."""
    global _watchdog
    if _watchdog is not None:
        return _watchdog
    try:
        wd = HangWatchdog(main_window)
        wd.start()
        _watchdog = wd
        return wd
    except Exception:
        return None


def mark_clean_exit() -> None:
    """Record that this session is shutting down on purpose. Never raises."""
    if _watchdog is None:
        return
    try:
        _watchdog.mark_clean_exit()
    except Exception:
        pass
