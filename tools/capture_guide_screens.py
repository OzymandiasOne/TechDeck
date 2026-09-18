"""Capture screenshots for the User Guide (docs/user_guide/images/).

Dev tool, run from the repo root:

    python tools/capture_guide_screens.py            # all shell shots
    python tools/capture_guide_screens.py --list     # name every shot and exit
    python tools/capture_guide_screens.py --only shell_home settings_apps

The app boots against a FRESH sandbox profile (LOCALAPPDATA redirected to a
scratch dir) so every picture shows what a brand-new user sees: default theme,
no tickets, no personal data. Rendering is offscreen; nothing pops on screen.

Re-run whenever the UI changes, then rebuild the guide PDF.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "user_guide" / "images"
WINDOW_SIZE = (1280, 800)

# ── Sandbox BEFORE any techdeck/Qt import ───────────────────────────────────
# Per-process dir so parallel capture runs cannot trash each other's profile.
_SANDBOX = Path(tempfile.gettempdir()) / f"techdeck_guide_capture_{os.getpid()}"
if _SANDBOX.exists():
    shutil.rmtree(_SANDBOX, ignore_errors=True)
_SANDBOX.mkdir(parents=True, exist_ok=True)
os.environ["LOCALAPPDATA"] = str(_SANDBOX)
# NOTE: not QT_QPA_PLATFORM=offscreen — that platform has no system fonts on
# Windows and every glyph renders as a box. We use the real windows platform
# and mark the window WA_DontShowOnScreen instead: full render, nothing pops up.
os.environ.setdefault("TECHDECK_PROFILE_STARTUP", "0")

sys.path.insert(0, str(REPO))


def pump(app, ms: int = 300) -> None:
    """Process Qt events for roughly `ms` milliseconds."""
    from PySide6.QtCore import QDeadlineTimer

    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        app.processEvents()


def boot():
    """Boot the app the way __main__ does, minus splash/watchdog/fade."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    # The profile seeds its display name from %USERNAME%; a manual must not
    # carry the capturing machine's real account name in every picture.
    os.environ["USERNAME"] = "TechDeck User"

    from techdeck.core.settings import SettingsManager
    settings = SettingsManager()

    # A fresh profile has an empty Home. Stage a realistic everyday kit so
    # the pictures look like a working install, not a blank page.
    settings.set_profile_tiles([
        "911_setup", "911_batch_repeater", "911_remove_ticket",
        "922_setup", "922_kitting", "922_formingfinder",
        "batch_auditor", "qr_code_generator",
    ])

    from techdeck.ui.theme import load_custom_themes
    load_custom_themes(settings.get_custom_themes_dir())

    from techdeck.ui.theme_manager import get_theme_manager
    tm = get_theme_manager()
    tm.set_theme(settings.get_theme())
    app.setStyleSheet(tm.get_stylesheet())

    from PySide6.QtCore import Qt
    from techdeck.ui.shell import MainWindow
    window = MainWindow(settings)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.resize(*WINDOW_SIZE)
    window.setWindowOpacity(1.0)
    window.show()
    window.warmup_pages()

    # Hide the source-build-only Dev Mode toggle: colleagues never see it.
    for attr in ("_dev_label", "dev_switch"):
        w = getattr(window.home_page, attr, None)
        if w is not None:
            w.hide()

    pump(app, 800)
    return app, window, settings


def save(widget, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pix = widget.grab()
    path = OUT_DIR / f"{name}.png"
    pix.save(str(path))
    print(f"  {name}.png  ({pix.width()}x{pix.height()})")


def goto(app, window, page_id: str) -> None:
    window.sidebar._on_nav_clicked(page_id)
    pump(app, 400)


# ── App-flow helpers (step-by-step captures) ───────────────────────────────
# A worker-thread app blocks on the console/its windows while the GUI thread
# (this script) stays free to pump, inspect, and grab. NOTE: app-created
# top-level windows do NOT inherit WA_DontShowOnScreen, so plugin windows
# flash on screen briefly during capture. Manual-run tool; acceptable.

def start_app(app, window, plugin_id: str) -> None:
    goto(app, window, "home")
    window.home_page.selected_tiles = {plugin_id}
    window.home_page._run.run_selected_plugins()
    pump(app, 300)


def wait_console_prompt(app, window, timeout_ms: int = 20000,
                        contains: str | None = None) -> bool:
    from PySide6.QtCore import QDeadlineTimer

    con = window.console
    dl = QDeadlineTimer(timeout_ms)
    while not dl.hasExpired():
        app.processEvents()
        if con.waiting_for_input:
            prompt = getattr(con, "input_prompt", "") or ""
            if contains is None or contains.lower() in prompt.lower():
                pump(app, 300)
                return True
    return False


def answer_console(app, window, text: str) -> None:
    con = window.console
    con.input_field.setText(text)
    con._on_input_submitted()
    pump(app, 400)


def wait_window(app, title_contains: str, timeout_ms: int = 20000):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QDeadlineTimer

    dl = QDeadlineTimer(timeout_ms)
    while not dl.hasExpired():
        app.processEvents()
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and title_contains.lower() in (w.windowTitle() or "").lower():
                pump(app, 400)
                return w
    return None


def cancel_run(app, window, wait_ms: int = 4000) -> None:
    """The Run button doubles as Cancel while a run is active."""
    if window.home_page._run.session.is_running:
        window.home_page._run.run_selected_plugins()
    pump(app, wait_ms)


def console_tail(window, lines: int = 12) -> str:
    doc = window.console.output.toPlainText()
    return "\n".join(doc.splitlines()[-lines:])


def probe(app, window, plugin_id: str, seconds: int = 20) -> None:
    """Exploration mode: run an app and report/grab whatever appears.

    Event-driven: a QTimer scans for new top-level windows and console
    prompts, so a modal dialog's nested event loop can't freeze us. After
    `seconds`, everything is closed and the process hard-exits.
    """
    import time as _time
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    seen: dict = {}
    t0 = _time.time()

    def tick():
        for w in QApplication.topLevelWidgets():
            if w is window or not w.isVisible():
                continue
            key = (type(w).__name__, w.windowTitle())
            if key not in seen:
                seen[key] = w
                print(f"-- window: {key}", flush=True)
                save(w, f"probe_{plugin_id}_{type(w).__name__}")
        con = window.console
        if con.waiting_for_input and "prompt" not in seen:
            seen["prompt"] = True
            print(f"-- prompt: {getattr(con, 'input_prompt', '')!r}", flush=True)
            save(con, f"probe_{plugin_id}_console")
        if _time.time() - t0 > seconds:
            print("-- probe timeout: console tail:", flush=True)
            print(console_tail(window), flush=True)
            sys.stdout.flush()
            os._exit(0)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(400)
    start_app(app, window, plugin_id)
    app.exec()


# ── Shot registry ───────────────────────────────────────────────────────────
# name -> function(app, window). Ordered; --only filters by name.

def _shell_shots():
    shots = {}

    def home(app, window):
        goto(app, window, "home")
        save(window, "shell_home")

    def library(app, window):
        goto(app, window, "library")
        save(window, "shell_library")

    def assistant(app, window):
        goto(app, window, "assistant")
        # Stage the page's two key behaviors: free text is just conversation,
        # while "remind me to ..." actually files a task. Both answers are the
        # app's own real responses.
        window.assistant_page.submit("onedrive is being slow again")
        pump(app, 1200)
        window.assistant_page.submit("remind me to check the 911 schedule at 9am")
        pump(app, 1500)
        save(window, "shell_assistant")

    def settings_tabs(app, window):
        goto(app, window, "settings")
        page = window.settings_page
        for idx, name in [(0, "settings_personalization"), (1, "settings_apps"),
                          (2, "settings_help_feedback")]:
            page.tabs.setCurrentIndex(idx)
            pump(app, 400)
            save(window, name)

    def account_tabs(app, window):
        goto(app, window, "account")
        page = window.account_page
        tab_names = {"My Account": "account_my_account",
                     "Ticket Counter": "account_emporium",
                     "My Stuff": "account_my_stuff",
                     "Achievements": "account_achievements",
                     "My House": "account_my_house"}
        for idx in range(page.tabs.count()):
            label = page.tabs.tabText(idx).replace("&", "")
            key = tab_names.get(label)
            if key is None:
                continue
            page.tabs.setCurrentIndex(idx)
            # The Emporium's dialogue types itself out; wait for the line to finish.
            pump(app, 4500 if key == "account_emporium" else 600)
            save(window, key)

    shots["shell_home"] = home
    shots["shell_library"] = library
    shots["shell_assistant"] = assistant
    shots["settings_tabs"] = settings_tabs
    shots["account_tabs"] = account_tabs
    return shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    help="run only these shot groups")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--probe", metavar="PLUGIN_ID",
                    help="run one app, report prompts/windows, grab everything")
    args = ap.parse_args()

    shots = _shell_shots()
    if args.list:
        print("\n".join(shots))
        return

    if args.probe:
        app, window, settings = boot()
        probe(app, window, args.probe)
        # Blocked plugin worker threads are non-daemon and would keep the
        # process alive forever after a cancel; this is a capture tool, so
        # a hard exit is the right ending.
        sys.stdout.flush()
        os._exit(0)

    wanted = {k: v for k, v in shots.items()
              if args.only is None or k in args.only}
    if not wanted:
        sys.exit(f"No matching shots. Available: {', '.join(shots)}")

    print(f"Sandbox profile: {_SANDBOX}")
    app, window, settings = boot()
    for name, fn in wanted.items():
        print(f"[{name}]")
        fn(app, window)
    print("Done.")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
