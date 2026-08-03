"""Tests for the crash/hang capture that makes a post-restart debug report
useful. The end-to-end behaviour (UI thread blocks -> stacks land in hang.log)
is exercised by blocking a real thread; the rest is pure-function coverage of
the snapshot and the file rotation that preserves a dead session's state."""

import json
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
    start_times = {"902_dxf_prep": time.time() - 600}
    last_activity = {"902_dxf_prep": time.time() - 540}

    def get_active_plugins(self):
        return ["902_dxf_prep"]


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
    state = hang_watchdog._snapshot(_Window())

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
    logs.mkdir(parents=True)
    (logs / "session_state.json").write_text(
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


def test_module_start_is_idempotent(logs):
    first = hang_watchdog.start(None)
    second = hang_watchdog.start(None)
    try:
        assert first is not None and first is second
    finally:
        hang_watchdog.mark_clean_exit()
