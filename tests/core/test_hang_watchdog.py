"""Tests for the crash/hang capture that makes a post-restart debug report
useful. The end-to-end behaviour (UI thread blocks -> stacks land in hang.log)
is exercised by blocking a real thread; the rest is pure-function coverage of
the snapshot and the file rotation that preserves a dead session's state."""

import json
import sys
import threading
import time

import pytest

from techdeck.core import hang_watchdog


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """Point %LOCALAPPDATA% at a scratch dir so nothing touches the real logs."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(hang_watchdog, "_watchdog", None)
    return tmp_path / "TechDeck" / "logs"


class _Console:
    waiting_for_input = True
    input_prompt = "Enter batch number:"


class _Session:
    queue = ["922_kitting"]
    paused = False
    is_running = True


class _Run:
    session = _Session()


class _Executor:
    # Timestamps are set per-instance (see test) — as class attributes they'd
    # freeze at IMPORT time, and the seconds a loaded full-suite run spends
    # between import and this test inflate the measured silence (bit 2026-08-05:
    # 545.9 vs 540 ± 5 under -q while passing standalone).
    # Mirrors PluginExecutor's accessor methods (the RunningPlugin registry
    # replaced the old start_times/last_activity dicts).
    def __init__(self):
        now = time.time()
        self._started_at = now - 600
        self._last_activity = now - 540

    def get_active_plugins(self):
        return ["902_dxf_prep"]

    def get_execution_time(self, plugin_id):
        return time.time() - self._started_at

    def get_last_activity(self, plugin_id):
        return self._last_activity


class _Settings:
    def get_current_profile_name(self):
        return "Game"


class _Home:
    plugin_executor = _Executor()
    settings = _Settings()
    _run = _Run()


class _Window:
    """Duck-typed stand-in for MainWindow (no Qt needed)."""
    home_page = _Home()
    console = _Console()


def test_snapshot_captures_the_stuck_plugin_and_prompt():
    window = _Window()
    window.home_page.plugin_executor = _Executor()   # fresh timestamps NOW
    state = hang_watchdog._snapshot(window)

    assert state["kit"] == "Game"
    assert state["active_plugins"] == ["902_dxf_prep"]
    # The number that matters: a plugin running 10 min with 9 min of silence
    # is blocked on something, even though the app itself is responsive.
    assert state["silent_for_s"]["902_dxf_prep"] == pytest.approx(540, abs=5)
    assert state["run_elapsed_s"]["902_dxf_prep"] == pytest.approx(600, abs=5)
    assert state["queue"] == ["922_kitting"]
    assert state["is_running"] is True
    assert state["waiting_for_input"] is True
    assert state["input_prompt"] == "Enter batch number:"


def test_snapshot_never_raises_on_a_half_built_window():
    # Startup, teardown, and a bare window must all degrade to a timestamp.
    assert "at" in hang_watchdog._snapshot(None)
    assert "at" in hang_watchdog._snapshot(object())


def test_state_signature_ignores_volatile_counters():
    a = {"at": "12:00:00", "kit": "Game", "silent_for_s": {"x": 1.0}}
    b = {"at": "12:00:05", "kit": "Game", "silent_for_s": {"x": 6.0}}
    c = {"at": "12:00:05", "kit": "Default", "silent_for_s": {"x": 6.0}}

    assert hang_watchdog._state_signature(a) == hang_watchdog._state_signature(b)
    assert hang_watchdog._state_signature(a) != hang_watchdog._state_signature(c)


def test_startup_rotates_the_dead_sessions_state_aside(logs):
    """The whole point: restarting to clear a freeze must NOT destroy the record
    of what froze."""
    live = hang_watchdog.state_path()
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(
        json.dumps({"clean_exit": False, "active_plugins": ["902_dxf_prep"]}),
        encoding="utf-8",
    )

    wd = hang_watchdog.HangWatchdog(main_window=None)  # no Qt -> no heartbeat
    wd.start()
    try:
        prev = hang_watchdog.previous_session()
        assert prev is not None
        assert prev["clean_exit"] is False
        assert prev["active_plugins"] == ["902_dxf_prep"]
    finally:
        wd.mark_clean_exit()


def test_clean_exit_is_recorded_for_the_next_session(logs):
    wd = hang_watchdog.HangWatchdog(main_window=None)
    wd.start()
    wd.mark_clean_exit()

    written = json.loads(hang_watchdog.state_path().read_text(encoding="utf-8"))
    assert written["clean_exit"] is True
    assert "session_started" in written and "pid" in written


def test_previous_session_is_none_when_there_is_no_history(logs):
    assert hang_watchdog.previous_session() is None


def test_hang_log_records_the_session_banner(logs):
    wd = hang_watchdog.HangWatchdog(main_window=None)
    wd.start()
    try:
        text = hang_watchdog.hang_log_path().read_text(encoding="utf-8")
        assert "session start" in text
    finally:
        wd.mark_clean_exit()


def test_watchdog_dumps_stacks_when_the_heartbeat_stops(logs, monkeypatch):
    """A real hang, caught in the act: freeze the heartbeat and confirm every
    thread's stack lands in hang.log with the state at the time."""
    monkeypatch.setattr(hang_watchdog, "_FIRST_DUMP_AFTER", 0.5)
    monkeypatch.setattr(hang_watchdog, "_TICK", 0.1)

    wd = hang_watchdog.HangWatchdog(main_window=None)
    wd.start()
    try:
        # Stand in for the QTimer that a real window would own, then let the
        # heartbeat go stale exactly as a wedged UI thread would.
        wd._timer = object()
        wd._beat()
        wd._state = {"kit": "Game", "active_plugins": ["902_dxf_prep"]}
        time.sleep(1.2)

        text = hang_watchdog.hang_log_path().read_text(encoding="utf-8")
        assert "HANG #1" in text
        assert "902_dxf_prep" in text          # state carried into the dump
        assert "_watch" in text                # real thread stacks, not a stub

        wd._beat()                              # recovery
        time.sleep(0.4)
        assert "recovered" in hang_watchdog.hang_log_path().read_text(encoding="utf-8")
    finally:
        wd.mark_clean_exit()


def test_a_suspended_process_is_not_reported_as_a_hang(logs, monkeypatch):
    """Machine sleep is not a hang, and must not be dumped as one.

    Found in the first field debug report to reach us (2026-10-20): twelve of
    its thirteen stack dumps were the laptop sleeping with TechDeck open - one
    of them 38,913 seconds - each "recovering" one second after the wake. Every
    thread parks in wait() while the process is suspended, so the dump says
    nothing, and 5,644 lines of it is where a real hang goes to hide.

    The tell is that the WATCHDOG's own tick lost the same wall time the UI
    thread did. Simulated faithfully here: the stop event's wait stalls for far
    longer than _TICK (the suspend), the heartbeat stops for exactly that
    window, and it resumes on the wake the way the Qt timer does.
    """
    monkeypatch.setattr(hang_watchdog, "_FIRST_DUMP_AFTER", 0.5)
    monkeypatch.setattr(hang_watchdog, "_TICK", 0.1)
    monkeypatch.setattr(hang_watchdog, "_SUSPEND_SLACK", 0.3)

    wd = hang_watchdog.HangWatchdog(main_window=None)
    wd._timer = object()
    wd._beat()

    suspended = threading.Event()
    real_wait = wd._stop.wait
    stalls = [1.0]

    def wait(timeout=None):
        if stalls:
            suspended.set()
            try:
                return real_wait(stalls.pop(0))
            finally:
                suspended.clear()
        return real_wait(timeout)

    monkeypatch.setattr(wd._stop, "wait", wait)

    # The UI thread: beats every tick, and goes silent for exactly as long as
    # the process is suspended.
    stop_beating = threading.Event()

    def beater():
        while not stop_beating.wait(0.05):
            if not suspended.is_set():
                wd._beat()

    pulse = threading.Thread(target=beater, daemon=True)

    wd.start()
    pulse.start()
    try:
        time.sleep(1.8)
        text = hang_watchdog.hang_log_path().read_text(encoding="utf-8")
        assert "not a hang: the process was suspended" in text
        assert "HANG #" not in text
    finally:
        stop_beating.set()
        pulse.join(timeout=1)
        wd.mark_clean_exit()


def test_a_real_hang_still_dumps_after_a_suspend(logs, monkeypatch):
    """The suspend check must not disarm the watchdog: a wedged UI thread after
    a wake is still a hang, caught on the ticks that follow."""
    monkeypatch.setattr(hang_watchdog, "_FIRST_DUMP_AFTER", 0.5)
    monkeypatch.setattr(hang_watchdog, "_TICK", 0.1)
    monkeypatch.setattr(hang_watchdog, "_SUSPEND_SLACK", 0.3)

    wd = hang_watchdog.HangWatchdog(main_window=None)
    wd._timer = object()
    wd._beat()

    real_wait = wd._stop.wait
    stalls = [1.0]

    def wait(timeout=None):
        if stalls:
            return real_wait(stalls.pop(0))
        return real_wait(timeout)

    monkeypatch.setattr(wd._stop, "wait", wait)
    wd.start()
    try:
        # Never beat again: the wake is the new baseline, and the UI thread
        # staying silent past it is the real thing.
        time.sleep(2.0)
        text = hang_watchdog.hang_log_path().read_text(encoding="utf-8")
        assert "not a hang: the process was suspended" in text
        assert "HANG #1" in text
    finally:
        wd.mark_clean_exit()


def test_dev_runs_get_their_own_watchdog_tree(logs, monkeypatch):
    """Source runs write under logs\\dev; frozen builds keep the shared logs
    dir. All three files must live together either way."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    dev_dir = hang_watchdog._dir()
    assert dev_dir == logs / "dev"
    assert {p.parent for p in (hang_watchdog.hang_log_path(),
                               hang_watchdog.state_path(),
                               hang_watchdog.previous_state_path())} == {dev_dir}

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert hang_watchdog._dir() == logs
    assert hang_watchdog.state_path().parent == logs


def test_a_killed_dev_run_cannot_poison_the_installed_apps_crash_offer(
        logs, monkeypatch):
    """The defect this split exists for: killing `python -m techdeck` is
    routine, but its clean_exit:false used to land in the SAME
    last_session.json the installed exe reads at its next launch - which
    popped the "TechDeck didn't close cleanly" offer for a crash that never
    happened (LAPTOP-VI327KUH, 2026-08-20/21)."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    dev = hang_watchdog.HangWatchdog(main_window=None)
    dev.start()
    dev._write_state()                    # ...and the dev run is killed here
    dev._stop.set()
    written = json.loads(hang_watchdog.state_path().read_text(encoding="utf-8"))
    assert written["clean_exit"] is False and written["frozen"] is False

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen = hang_watchdog.HangWatchdog(main_window=None)
    frozen.start()                        # the installed app's next launch
    try:
        assert hang_watchdog.previous_session() is None   # no ghost crash
    finally:
        frozen.mark_clean_exit()


def test_module_start_is_idempotent(logs):
    first = hang_watchdog.start(None)
    second = hang_watchdog.start(None)
    try:
        assert first is not None and first is second
    finally:
        hang_watchdog.mark_clean_exit()
