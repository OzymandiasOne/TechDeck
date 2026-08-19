"""
TechDeck Application Logging
============================
One rotating application log for everything that is not a plugin run:
%LOCALAPPDATA%\\TechDeck\\logs\\app.log

Why this exists: the shipped exe is a PyInstaller *windowed* build, so
sys.stdout/sys.stderr are None and every print() is a no-op — the updater's
entire diagnostic trail, settings-save warnings, and plugin-discovery errors
all vanished in the field. This module gives the ROOT logger a rotating file
handler, which also makes every pre-existing `logging.getLogger(__name__)`
module (plugin_loader, feedback_writer, command_handler, sentry_mode) start
landing on disk with no changes to those modules.

It also installs sys.excepthook / threading.excepthook so an unhandled
exception outside a plugin run — in a Qt slot, a background thread, or during
startup — leaves a traceback in app.log instead of dying silently.

The two plugin logs (plugin_runs.log / plugin_detail.log, owned by
plugin_executor.py) keep their own handlers with propagate=False and are
unaffected. The hang watchdog's hang.log is likewise untouched.

Call setup_logging() once, first thing in __main__.main(). Safe to call
again (idempotent) — tests and tools may re-enter.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

from techdeck.core.constants import LOG_FORMAT, LOG_DATE_FORMAT

APP_LOG_NAME = "app.log"
_MAX_BYTES = 1 * 1024 * 1024  # match plugin_runs.log sizing
_BACKUP_COUNT = 3

_configured = False

# Startup step timings ([startup +N ms] lines from __main__ and MainWindow).
# ON by default so every field machine records real startup numbers in
# app.log; set TECHDECK_PROFILE_STARTUP=0 to silence them.
_TRUTHY = {"1", "true", "yes", "on"}


def startup_profiling_enabled() -> bool:
    val = os.environ.get("TECHDECK_PROFILE_STARTUP", "").strip().lower()
    if val:
        return val in _TRUTHY
    return True


def startup_logger() -> logging.Logger:
    return logging.getLogger("techdeck.startup")


def log_dir() -> Path:
    """%LOCALAPPDATA%\\TechDeck\\logs — same resolution as plugin_executor's
    run/detail logs so every log lands in one folder for the debug report."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "TechDeck" / "logs"


def app_log_path() -> Path:
    return log_dir() / APP_LOG_NAME


def setup_logging() -> None:
    """Attach a rotating app.log handler to the root logger (idempotent).

    In dev runs (stderr exists) a stream handler is added too, so converting
    print() calls to logger calls doesn't hide their output from the terminal.
    Never raises: an app that can't log must still start.
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    try:
        target = log_dir()
        target.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            target / APP_LOG_NAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception:
        # Disk-full / locked profile / redirected LOCALAPPDATA — fall through
        # to the stream handler (if any) rather than blocking startup.
        pass

    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    _configured = True


def install_excepthooks() -> None:
    """Route unhandled exceptions (main thread + worker threads) into the log,
    then defer to the previous hooks so dev-console behavior is unchanged."""
    crash_log = logging.getLogger("techdeck.crash")
    previous_sys_hook = sys.excepthook
    previous_threading_hook = threading.excepthook

    def _sys_hook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            crash_log.critical(
                "Unhandled exception on the main thread",
                exc_info=(exc_type, exc, tb),
            )
        previous_sys_hook(exc_type, exc, tb)

    def _threading_hook(args):
        if not issubclass(args.exc_type, SystemExit):
            thread_name = args.thread.name if args.thread else "?"
            crash_log.critical(
                "Unhandled exception in thread %r",
                thread_name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        previous_threading_hook(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _threading_hook
