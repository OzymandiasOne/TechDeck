"""PluginExecutor coverage: the pure outcome logic AND the actual execution
paths (threaded + main-thread), which had essentially no tests while being
the riskiest concurrency code in the app.

The execution tests drive the real executor with a stub PluginLoader whose
"modules" are plain namespaces with a run() function — no plugin folders, no
Qt widgets. Main-thread (GUI) runs are exercised through the same
QTimer.singleShot(0, ...) scheduling the app uses, fired via qapp
processEvents.
"""

import threading
import types

import pytest

from techdeck.core.plugin_executor import (
    PluginExecutor, PluginResult, PluginStatus,
)
from techdeck.core.plugin_sdk import PluginCancelled
from techdeck.ui.widgets.console import InputAborted


# ---------------------------------------------------------------- pure logic

def test_ticket_units_clamped_to_1_20():
    f = PluginExecutor._ticket_units_from
    assert f({}) == 1
    assert f({"ticket_units": 5}) == 5
    assert f({"ticket_units": 0}) == 1        # never zeroes out
    assert f({"ticket_units": 999}) == 20     # never inflates absurdly
    assert f({"ticket_units": "junk"}) == 1
    assert f({"ticket_units": None}) == 1


def test_run_outcome_honors_only_warning_and_partial():
    f = PluginExecutor._run_outcome_from
    assert f({}) == (None, "")
    assert f({"run_outcome": "nope"}) == (None, "")            # not a dict
    assert f({"run_outcome": {"status": "success"}}) == (None, "")
    assert f({"run_outcome": {"status": "warning", "message": "m"}}) == ("warning", "m")
    assert f({"run_outcome": {"status": "PARTIAL", "message": "x"}}) == ("partial", "x")
    assert f({"run_outcome": {"status": "warning"}}) == ("warning", "")


def test_plugin_result_defaults():
    r = PluginResult(plugin_id="p", status=PluginStatus.SUCCESS, message="ok")
    assert r.ticket_units == 1
    assert r.is_user_error is False
    assert r.user_fix is None
    assert r.outcome_message == ""
    assert r.progress == 0


# ---------------------------------------------------------------- harness

class FakePlugin:
    def __init__(self, plugin_id, requires_main_thread=False):
        self.id = plugin_id
        self.name = plugin_id.replace("_", " ").title()
        self.version = "1.0.0"
        self.family = "General"
        self.requires_main_thread = requires_main_thread
        self.timeout = None


class FakeLoader:
    """Stub of the two PluginLoader methods the executor calls, plus module
    delivery — run() functions are injected per test."""

    def __init__(self):
        self.plugins = {}
        self.modules = {}

    def add(self, plugin_id, run_fn, requires_main_thread=False):
        self.plugins[plugin_id] = FakePlugin(plugin_id, requires_main_thread)
        self.modules[plugin_id] = types.SimpleNamespace(run=run_fn)

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)

    def validate_plugin(self, plugin_id):
        return True, None

    def load_plugin_module(self, plugin_id):
        return self.modules[plugin_id]


@pytest.fixture
def loader():
    return FakeLoader()


@pytest.fixture
def executor(loader):
    # timeout=0 by default: no monitor thread unless a test asks for one.
    return PluginExecutor(loader, default_timeout=0)


def _wait_for_result(executor, plugin_id, timeout=10.0):
    """Wait until the run leaves the registry (works for thread runs)."""
    assert executor.wait_for_completion(plugin_id, timeout=timeout)
    return executor.get_result(plugin_id)


# ---------------------------------------------------------------- threaded

def test_threaded_success_path(executor, loader):
    loader.add("demo", lambda params, progress, cancel: progress(50))
    done = threading.Event()
    results = []

    assert executor.execute_plugin(
        "demo", completion_callback=lambda r: (results.append(r), done.set()))
    assert done.wait(10)

    result = executor.get_result("demo")
    assert result.status == PluginStatus.SUCCESS
    assert result.progress == 100
    assert results and results[0] is result
    assert not executor.is_plugin_running("demo")
    assert executor.get_active_plugins() == []


def test_threaded_error_path(executor, loader):
    def boom(params, progress, cancel):
        raise ValueError("the disk caught fire")
    loader.add("demo", boom)

    executor.execute_plugin("demo")
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.ERROR
    assert "the disk caught fire" in (result.error or "")
    assert not executor.is_plugin_running("demo")


def test_cooperative_cancel_is_cancelled(executor, loader):
    def cancels(params, progress, cancel):
        raise PluginCancelled()
    loader.add("demo", cancels)

    executor.execute_plugin("demo")
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.CANCELLED


def test_cancel_flag_set_at_return_is_never_success(executor, loader):
    """The executor's one success signal: cancel_event clear at return."""
    def backs_out(params, progress, cancel):
        cancel.set()          # what sdk._user_cancelled does on a backed-out prompt
        return None
    loader.add("demo", backs_out)

    executor.execute_plugin("demo")
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.CANCELLED


def test_input_aborted_paused_parks_the_run(executor, loader):
    def pauses(params, progress, cancel):
        raise InputAborted(reason="paused")
    loader.add("demo", pauses)

    executor.execute_plugin("demo")
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.PAUSED


def test_double_start_is_refused_while_running(executor, loader):
    release = threading.Event()
    loader.add("demo", lambda params, progress, cancel: release.wait(10))

    assert executor.execute_plugin("demo")
    try:
        assert executor.is_plugin_running("demo")
        assert executor.execute_plugin("demo") is False
        # Live-run introspection used by the hang watchdog's snapshot:
        assert executor.get_execution_time("demo") is not None
        assert executor.get_last_activity("demo") is not None
    finally:
        release.set()
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.SUCCESS


def test_cancel_plugin_sets_the_flag(executor, loader):
    seen = threading.Event()

    def waits_for_cancel(params, progress, cancel):
        seen.set()
        if not cancel.wait(10):
            raise RuntimeError("cancel flag never arrived")
        raise PluginCancelled()
    loader.add("demo", waits_for_cancel)

    executor.execute_plugin("demo")
    assert seen.wait(10)
    assert executor.cancel_plugin("demo") is True
    result = _wait_for_result(executor, "demo")
    assert result.status == PluginStatus.CANCELLED
    # Nothing left to cancel once the run is gone.
    assert executor.cancel_plugin("demo") is False


def test_inactivity_timeout_cancels_a_silent_run(executor, loader):
    """A run that stops logging/progressing gets cancelled by the monitor
    and scored TIMEOUT (uses a 2s idle limit; the monitor polls at 1s)."""
    def silent(params, progress, cancel):
        # No activity at all — just wait for the watchdog's cancel.
        if not cancel.wait(15):
            raise RuntimeError("watchdog never fired")
        return None
    loader.add("demo", silent)

    executor.execute_plugin("demo", timeout=2)
    result = _wait_for_result(executor, "demo", timeout=20)
    assert result.status == PluginStatus.TIMEOUT
    assert "inactivity" in (result.error or "")


# ---------------------------------------------------------------- main-thread

def test_gui_plugin_is_registered_and_visible(qapp, executor, loader):
    """The fix under test: a requires_main_thread plugin must be visible to
    is_plugin_running / get_active_plugins between scheduling and completion
    — before, the close-warning, the hang watchdog and the double-start
    guard were all blind to it."""
    ran = []
    loader.add("gui_demo", lambda params, progress, cancel: ran.append(True),
               requires_main_thread=True)

    assert executor.execute_plugin("gui_demo")
    # Scheduled but not yet run (QTimer.singleShot hasn't fired): visible.
    assert executor.is_plugin_running("gui_demo")
    assert "gui_demo" in executor.get_active_plugins()
    # A second click cannot start it twice.
    assert executor.execute_plugin("gui_demo") is False
    # And nothing can (dead)wait on a main-thread run.
    assert executor.wait_for_completion("gui_demo", timeout=0.1) is False

    qapp.processEvents()   # fire the singleShot -> run on this (main) thread

    assert ran == [True]
    result = executor.get_result("gui_demo")
    assert result.status == PluginStatus.SUCCESS
    assert not executor.is_plugin_running("gui_demo")
    assert executor.get_active_plugins() == []


def test_gui_cancelled_run_is_not_success(qapp, executor, loader):
    """Merged-body behavior: the old main-thread copy skipped the post-run
    cancel check, so backing out of a GUI plugin's dialog still chimed
    SUCCESS and paid tickets. Now both paths score it CANCELLED."""
    def backs_out(params, progress, cancel):
        cancel.set()
        return None
    loader.add("gui_demo", backs_out, requires_main_thread=True)

    executor.execute_plugin("gui_demo")
    qapp.processEvents()

    result = executor.get_result("gui_demo")
    assert result.status == PluginStatus.CANCELLED
