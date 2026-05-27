"""
TechDeck Splash Subprocess
==========================
Standalone process that displays the splash GIF in its own Qt event loop.
Launched by techdeck/__main__.py at the very start of startup — before the
main process imports PySide6 — so both processes load PySide6 in parallel
and the splash GIF stays smooth no matter what the main process is doing.

Closes when the parent closes its stdin pipe (EOF on this process's stdin).

Usage (dev):
    python -m techdeck.splash_process /path/to/splash.gif
Usage (frozen):
    TechDeck.exe --splash-mode /path/to/splash.gif
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path


# Force UTF-8 on stdio (guarded) so non-ASCII output never crashes a cp1252
# console. stdin stays binary (read via sys.stdin.buffer below).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def run_splash(gif_path: Path) -> int:
    """Run the splash subprocess event loop. Returns the Qt exit code."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    app = QApplication(sys.argv)

    from techdeck.ui.splash import SplashScreen
    splash = SplashScreen(gif_path)
    splash.show()

    # Watch stdin in a background thread. When the parent closes the stdin
    # pipe, read() returns and we schedule app.quit() on the main thread.
    # QTimer.singleShot is documented as safe to call from any thread when
    # a QApplication exists.
    def _watch_stdin():
        try:
            sys.stdin.buffer.read()  # blocks until EOF
        except Exception:
            pass
        QTimer.singleShot(0, app.quit)

    threading.Thread(target=_watch_stdin, daemon=True, name="stdin-watch").start()

    return app.exec()


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    gif_path = Path(sys.argv[1])
    if not gif_path.exists():
        return 1
    return run_splash(gif_path)


if __name__ == "__main__":
    sys.exit(main())
