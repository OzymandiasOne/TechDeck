"""
Dev launcher for the chopper-gunner folder picker (chopper_picker.py).

Opens the kill-cam picker standalone — crosshair cursor, lock-on, Run recoil,
1 s shell flight, slow-mo debris burst w/ smoke trails + dust, transmission
knockout — without running 922 Setup or the shell. The picked path prints to
stdout. Any key skips the sequence mid-fire; Cancel/Esc returns None with no
fireworks.

Usage (from the repo root, dev environment):
    python tools/play_chopper_picker.py               # opens at your home dir
    python tools/play_chopper_picker.py "C:\\some\\dir" # opens at a start dir

This is a dev tool: it bypasses the professional-theme gate (which in the
real app downgrades 922 Setup's prompt to the native dialog).
"""
from __future__ import annotations

import os
import sys

# Repo root on path (this file lives in <root>/tools/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    start_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        from techdeck.ui.theme_manager import get_theme_manager
        get_theme_manager().set_theme("dark")
    except Exception:
        pass  # unthemed non-native dialog is fine for a dev harness

    from techdeck.ui.widgets.chopper_picker import pick_folder_chopper
    path = pick_folder_chopper(None, "Select the 922 batch folder", start_dir)
    print(f"PATH ACQUIRED: {path}" if path else "FIRE MISSION ABORTED (cancelled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
