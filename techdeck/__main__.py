"""
TechDeck Entry Point
Launches the application when run as: python -m techdeck

The splash is rendered by a separate process (techdeck.splash_process) so
its GIF animation stays smooth regardless of what the main process is doing
during startup. The subprocess is launched as the very first thing in this
file — before PySide6 is imported — so both processes load their imports
in parallel.
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


# ── UTF-8 stdio ─────────────────────────────────────────────────────────────
# Force stdout/stderr to UTF-8 so non-ASCII in any log or print (emoji,
# arrows, checkmarks, accented chars) can never crash on a cp1252 Windows
# console. Guarded for frozen windowed builds where stdio may be None, and
# for streams that don't implement reconfigure().
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


# ── Startup timing (set TECHDECK_PROFILE_STARTUP=1 to enable verbose logs) ──
_PROFILE_STARTUP = True
_STARTUP_T0 = time.perf_counter()


def _log_step(name: str):
    if not _PROFILE_STARTUP:
        return
    elapsed_ms = (time.perf_counter() - _STARTUP_T0) * 1000.0
    print(f"[startup +{elapsed_ms:6.0f} ms] {name}", file=sys.stderr, flush=True)


# ── Asset paths ────────────────────────────────────────────────────────────
def _asset_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[1] / "assets"


def _icon_path() -> Path:
    return _asset_root() / "TechDeck.ico"


def _current_theme_name() -> str:
    """Read the active theme from settings.json directly. We can't use
    SettingsManager here because importing it pulls in PySide6 indirectly,
    and the whole point of the splash subprocess is to launch BEFORE the
    main process touches PySide6. Falls back to "dark" on any error."""
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        settings_file = base / "TechDeck" / "settings.json"
        if not settings_file.exists():
            return "dark"
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("settings", {}).get("theme", "dark")
    except Exception:
        return "dark"


def _splash_gif_path() -> Path:
    """Pick the splash GIF matching the active theme. Falls back to dark.gif
    if the theme-specific GIF is missing (e.g. user is on a custom theme
    that has no dedicated splash)."""
    images_dir = _asset_root() / "images"
    theme_name = _current_theme_name()
    candidate = images_dir / f"{theme_name}.gif"
    if candidate.exists():
        return candidate
    return images_dir / "dark.gif"


# ── Splash subprocess launch ───────────────────────────────────────────────
def _launch_splash() -> "subprocess.Popen | None":
    """Launch the splash subprocess. Returns the Popen handle or None if
    the GIF is missing or the launch fails. Designed to never block or
    raise — splash failures must never prevent the app from starting."""
    gif_path = _splash_gif_path()
    if not gif_path.exists():
        return None

    if getattr(sys, "frozen", False):
        # Frozen build: re-launch our own exe with --splash-mode flag.
        cmd = [sys.executable, "--splash-mode", str(gif_path)]
    else:
        # Dev mode: run the splash module under the same Python interpreter.
        cmd = [sys.executable, "-m", "techdeck.splash_process", str(gif_path)]

    creationflags = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW (0x08000000) hides the splash subprocess's console window
        creationflags = 0x08000000

    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as exc:
        print(f"[splash] subprocess launch failed: {exc}", file=sys.stderr)
        return None


def _close_splash(splash_proc):
    """Signal the splash to close by sending EOF, then wait briefly."""
    if not splash_proc:
        return
    try:
        if splash_proc.stdin and not splash_proc.stdin.closed:
            splash_proc.stdin.close()
        splash_proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            splash_proc.terminate()
        except Exception:
            pass
    except Exception:
        pass


# ── Frozen-build splash dispatch ───────────────────────────────────────────
def _handle_frozen_splash_mode() -> bool:
    """In frozen builds, the same exe is reused for the splash process via
    the --splash-mode flag. If we detect that flag, run splash mode and
    return True; otherwise return False so normal startup proceeds."""
    if "--splash-mode" in sys.argv:
        idx = sys.argv.index("--splash-mode")
        gif_arg = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if gif_arg:
            from techdeck.splash_process import run_splash
            sys.exit(run_splash(Path(gif_arg)))
        sys.exit(1)
    return False


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    """Main application entry point."""
    # Frozen-build splash-mode handler: must run before anything else.
    if _handle_frozen_splash_mode():
        return

    _log_step("main() entered")

    # Launch the splash subprocess FIRST. Its PySide6 import runs in
    # parallel with this process's imports below.
    splash_proc = _launch_splash()
    _log_step("splash subprocess launched")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from techdeck.core.constants import APP_NAME, APP_VERSION

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    _log_step("QApplication ready")

    ico = _icon_path()
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    from techdeck.core.settings import SettingsManager
    settings = SettingsManager()
    # First-run seed: copy the bundled default Rogue Mode track into the
    # user's library so /roguemode isn't empty on a fresh install.
    settings.ensure_roguemode_default_track()
    _log_step("SettingsManager loaded")

    from techdeck.ui.theme import load_custom_themes
    load_custom_themes(settings.get_custom_themes_dir())

    from techdeck.ui.theme_manager import get_theme_manager
    theme_manager = get_theme_manager()
    theme_manager.set_theme(settings.get_theme())
    _log_step("theme manager set")

    def _reapply_stylesheet(_theme_name: str):
        app.setStyleSheet(theme_manager.get_stylesheet())
    app.setStyleSheet(theme_manager.get_stylesheet())
    theme_manager.theme_changed.connect(_reapply_stylesheet)

    from techdeck.ui.shell import MainWindow
    window = MainWindow(settings)
    _log_step("MainWindow constructed")

    window.show()
    _log_step("MainWindow.show() called")

    # Pre-warm every page while the splash still covers the window. This
    # forces Qt to do first-paint + any lazy widget setup for Library,
    # Settings, and Account so the user's first click is instant.
    window.warmup_pages()
    _log_step("pages warmed up")

    # Close splash now that MainWindow is fully ready. The window is still
    # at opacity 0 (set in MainWindow.__init__) so closing the splash leaves
    # nothing on screen for a single frame before the fade-in begins.
    _close_splash(splash_proc)
    _log_step("splash closed")

    # Now start the fade-in. Splash -> 400ms fade -> solid TechDeck. The
    # fade-in is the first thing the user sees in place of the splash
    # rather than running concurrently with it.
    window.start_fadein()
    _log_step("fade-in started")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
