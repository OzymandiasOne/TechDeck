"""app.log + excepthook coverage, and the no-print() guard.

Why the guard exists: the shipped exe is a PyInstaller *windowed* build, so
sys.stdout/sys.stderr are None and print() is a silent no-op. 79 print()
calls — including the updater's ENTIRE diagnostic trail and the settings
"save deferred" warnings — shipped for months without a single character
reaching disk on any user machine. Everything now routes through logging
(root handler -> %LOCALAPPDATA%\\TechDeck\\logs\\app.log, see
techdeck/core/logging_setup.py), and the AST scan below keeps new prints
from creeping back in.
"""

import ast
import logging
import sys
import threading
from pathlib import Path

import pytest

from techdeck.core import logging_setup

ROOT = Path(__file__).resolve().parents[2]

# Files under techdeck/ allowed to call print(). Empty today — keep it that
# way unless a file genuinely runs console-attached (a tools/-style script
# living in the package would qualify; nothing does right now).
PRINT_ALLOWLIST: set[str] = set()


@pytest.fixture
def clean_logging(monkeypatch):
    """Run setup_logging against a pristine root logger and pristine hooks,
    then restore everything so other tests' logging is untouched."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_sys_hook = sys.excepthook
    saved_threading_hook = threading.excepthook
    for handler in saved_handlers:
        root.removeHandler(handler)
    monkeypatch.setattr(logging_setup, "_configured", False)

    yield root

    for handler in root.handlers[:]:
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)
    sys.excepthook = saved_sys_hook
    threading.excepthook = saved_threading_hook


def _flush_root():
    for handler in logging.getLogger().handlers:
        handler.flush()


def _app_log_text() -> str:
    return logging_setup.app_log_path().read_text(encoding="utf-8",
                                                  errors="replace")


def test_setup_logging_creates_app_log_and_captures_records(clean_logging):
    logging_setup.setup_logging()
    logging.getLogger("techdeck.test").info("hello from the logging test")
    _flush_root()
    assert "hello from the logging test" in _app_log_text()


def test_setup_logging_is_idempotent(clean_logging):
    logging_setup.setup_logging()
    handler_count = len(logging.getLogger().handlers)
    logging_setup.setup_logging()
    assert len(logging.getLogger().handlers) == handler_count


def test_named_module_loggers_reach_app_log(clean_logging):
    """The 18 orphaned logger.* calls in plugin_loader (and friends) become
    live once the root handler exists — that is the whole point. Emulate one."""
    logging_setup.setup_logging()
    logging.getLogger("techdeck.core.plugin_loader").error(
        "Invalid JSON in plugin.json: fake for test")
    _flush_root()
    assert "Invalid JSON in plugin.json: fake for test" in _app_log_text()


def test_sys_excepthook_logs_the_traceback(clean_logging):
    logging_setup.setup_logging()
    sys.excepthook = lambda *args: None          # silence the chained default
    logging_setup.install_excepthooks()
    try:
        raise RuntimeError("boom for the crash log")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    _flush_root()
    text = _app_log_text()
    assert "Unhandled exception on the main thread" in text
    assert "RuntimeError: boom for the crash log" in text


def test_threading_excepthook_logs_the_traceback(clean_logging):
    logging_setup.setup_logging()
    threading.excepthook = lambda args: None     # silence the chained default
    logging_setup.install_excepthooks()

    worker = threading.Thread(target=lambda: 1 / 0, name="test-crash-thread")
    worker.start()
    worker.join()

    _flush_root()
    text = _app_log_text()
    assert "Unhandled exception in thread 'test-crash-thread'" in text
    assert "ZeroDivisionError" in text


def test_keyboard_interrupt_is_not_logged_as_a_crash(clean_logging):
    """Ctrl+C in a dev console is a normal exit, not a crash report.

    app.log is shared across the test session, so only the portion this
    test appends may be inspected — earlier excepthook tests legitimately
    wrote crash lines above it."""
    logging_setup.setup_logging()
    _flush_root()
    before = len(_app_log_text())
    sys.excepthook = lambda *args: None
    logging_setup.install_excepthooks()
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())
    _flush_root()
    appended = _app_log_text()[before:]
    assert "Unhandled exception" not in appended


def test_startup_profiling_env_override(monkeypatch):
    monkeypatch.delenv("TECHDECK_PROFILE_STARTUP", raising=False)
    assert logging_setup.startup_profiling_enabled() is True  # default ON
    monkeypatch.setenv("TECHDECK_PROFILE_STARTUP", "0")
    assert logging_setup.startup_profiling_enabled() is False
    monkeypatch.setenv("TECHDECK_PROFILE_STARTUP", "1")
    assert logging_setup.startup_profiling_enabled() is True


def _print_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    return [
        f"{rel}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]


def test_no_print_calls_anywhere_in_techdeck():
    offenders = []
    for py in sorted((ROOT / "techdeck").rglob("*.py")):
        if py.relative_to(ROOT).as_posix() in PRINT_ALLOWLIST:
            continue
        offenders.extend(_print_calls(py))
    assert not offenders, (
        "print() is a silent no-op in the shipped windowed build - use "
        "logging (logger = logging.getLogger(__name__)) instead:\n  "
        + "\n  ".join(offenders))


def test_the_print_detector_actually_detects(tmp_path):
    """A guard that can't fire is worse than none — feed it a print()."""
    sample = ROOT / "techdeck" / "__init__.py"
    assert _print_calls(sample) == []
    fake = tmp_path / "fake.py"
    fake.write_text("def f():\n    print('x')\n", encoding="utf-8")
    tree = ast.parse(fake.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "print"]
    assert len(calls) == 1
