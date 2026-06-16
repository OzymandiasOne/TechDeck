"""
TechDeck Main Window (Shell) - Claude.ai Style
Clean layout with proper dividers and no internal rounded corners.
FIXED: Inline button styling for Run Selected button
PHASE 2 FIX: Removed console height persistence - users drag to preferred height
"""

import sys
import time
import random
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSplitter, QPushButton, QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QIcon

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import (
    WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT, APP_VERSION, TICKETS_PER_RUN,
)
from techdeck.ui.theme import generate_stylesheet, get_current_palette
from techdeck.ui.widgets.sidebar import Sidebar
from techdeck.ui.pages.home_page import HomePage, HOME_TILE_H

# Smallest the Home apps pane may get when the console is dragged up:
# profile bar (50) + grid top margin (24) + one full tile row + a little slack.
HOME_APPS_MIN_HEIGHT = 50 + 24 + HOME_TILE_H + 10
from techdeck.ui.pages.library_page import LibraryPage
from techdeck.ui.pages.account_page import AccountPage
from techdeck.ui.pages.settings_page import SettingsPage
from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.core.command_handler import CommandHandler
from techdeck.core.update_checker import UpdateChecker
from techdeck.core.flavor import TalkbackState, TechTipState, CompendiumState
from techdeck.core.audio_manager import get_audio_manager, SOUND_SUCCESS, SOUND_ERROR
from techdeck.ui.dialogs.update_dialog import UpdateDialog


class MainWindow(QMainWindow):
    """
    Main application window - Claude.ai style layout.
    Console only appears on Home page.
    """
    
    # Signal for showing update dialog on main thread
    show_update_signal = Signal(object, bool)  # (update_info, mandatory)

    # Plugin spinner
    _SPINNER_COLOR = "#93C5FD"
    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _SPINNER_TEXTS = [
        "Combobulating...",
        "Moonwalking...",
        "Bamboozling...",
        "Flibbertigibbeting...",
        "Spelunking...",
        "Caramelizing...",
        "Skedaddling through folders...",
        "Faffing about with PDFs...",
        "Enchanting...",
        "Cattywampusing...",
        "Concocting...",
        "Determining...",
        "Negotiating with Excel...",
        "Herding the data...",
        "Convincing the files...",
        "Gallivanting...",
        "Galvanizing...",
        "Rustling the paperwork...",
        "Bothering the PDFs...",
        "Vibing...",
        "Warping...",
        "Transfiguring...",
        "Sprouting...",
        "Simmering...",
        "Pollinating...",
        "Mulling...",
        "Inferring...",
        "Hashing...",
        "Simmering...",
        "Levitating...",
        "Slithering...",
        "Spaghettifying the data...",
        "Making weekend plans...",
        "Shaking fist angrily at the Old Gods...",
        "Typing /rave into the console...",
        "Honking...",
        "Gandalf-maxxing...",
    ]
    _DONE_TEXTS = [
        "Combobulated for",
        "Moonwalked for",
        "Bamboozled in",
        "Flibbertigibbeted through that in",
        "Spelunked for",
        "Caramelized for",
        "Skedaddling for",
        "Waffled about for",
        "Enchanted for",
        "Cattywampused for",
        "Concocted and loaded in",
        "Negotiated with Excel for",
        "Herded all the data in",
        "Convinced the files in",
        "Rustled that paperwork in",
        "PDF bothered and quit their jobs in"
        "Hullaballooed for",
        "Did the thing in",
        "Knocked that out in",
        "Jim Carrey Grinch'd through it in",
        "Vibed in",
        "Warped with minor casualties in...",
        "Transfigured faces in",
        "Bloomed in",
        "Simmered in",
        "Pollinated in",
        "Dan Mullin'd it in",
        "Inferred in",
        "Hashbrowned in",
        "Levitated for",
        "Gandalf-maxxed for",

    ]
    _SPINNER_QUOTES = [
        "They're eating her! And then they're gonna eat me! Oh my GOD!",
        "I am inevitable.",
        "Just keep swimming... just keep swimming...",
        "It's a trap!",
        "WITNESS ME!",
        "You can't handle the truth.",
        "I feel the need, the need for speed!",
        "My name is Inigo Montoya. You processed my files. Prepare to be compiled.",
        "Get to the chopper!",
        "Definitely not sentient.",
        "Do or do not. There is no try.",
        "We're gonna need a bigger boat.",
        "Roads? Where we're going, we don't need roads.",
        "If you can dodge a wrench you can dodge a ball",
        "The files are IN the computer.",
        "But why male models?",
        "What is this? A document for ants?",
        "With great power comes great electricity bills.",
        "I'm kind of a big deal.",
        "Bees? Not the bees!",
        "Why so serious?",
        "Making them an offer they can't refuse.",
        "When the world crashes down around you, the only airbag you have is family. ~Vin Diesel",
        "The suspense is terrible, I hope it will last.",
    ]
    
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings

        # Startup profiling — mirrors the helper in __main__.py
        import time as _time
        self._t0 = _time.perf_counter()

        def _step(name: str):
            ms = (_time.perf_counter() - self._t0) * 1000.0
            print(f"[MainWindow +{ms:6.0f} ms] {name}", file=sys.stderr, flush=True)

        self._step = _step

        # Single shared PluginLoader — discover plugins ONCE here, then pass
        # to each page. Eliminates the triple disk scan that was the main
        # cause of startup lag.
        from techdeck.core.plugin_loader import PluginLoader
        self._plugin_loader = PluginLoader()
        self._plugin_loader.discover_plugins()
        _step("plugin discovery done")
        QApplication.processEvents()

        # Connect signal for thread-safe update dialog
        self.show_update_signal.connect(self._show_update_dialog_slot)

        # Personality: talkback + tech tip pools
        self._talkback = TalkbackState()
        self._techtip = TechTipState()
        self._last_talkback_plugin: str | None = None

        # Spinner pools — shuffled, no back-to-back repeats, exhaust before recycling.
        # State persists across plugin runs so successive runs don't pick the same line.
        self._spinner_text_pool = CompendiumState(self._SPINNER_TEXTS)
        self._spinner_quote_pool = CompendiumState(self._SPINNER_QUOTES)
        self._spinner_done_pool = CompendiumState(self._DONE_TEXTS)

        # Audio: configure singleton from saved settings
        audio = settings.get_audio_settings()
        get_audio_manager().configure(enabled=audio.get("enabled", True), volume=audio.get("volume", 80))

        # Plugin spinner state
        self._plugin_spinner_timer = QTimer(self)
        self._plugin_spinner_timer.setInterval(100)
        self._plugin_spinner_timer.timeout.connect(self._on_plugin_spinner_tick)
        self._plugin_spinner_tick = 0
        self._plugin_run_start = 0.0
        self._spinner_in_quote = False
        self._spinner_quote_end_tick = 0
        self._spinner_current_quote = ""
        self._spinner_next_quote_tick = 0
        self._spinner_phase = "start"    # "start" | "running"
        self._spinner_locked_text = ""   # frozen during "start" phase
        self._spinner_current_text = "" # current text (running phase)
        self._spinner_text_ticks = 0     # ticks elapsed since current text shown
        
        # Window properties
        self.setWindowTitle("TechDeck")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        # Center on the primary screen's *available* geometry (which
        # excludes the taskbar) so the title bar is always reachable on
        # boot. Without this, Qt sometimes positions the window with
        # part of the frame above the desktop on multi-monitor or
        # high-DPI setups.
        self._center_on_primary_screen()
        
        # Theme is already applied by __main__.py via app.setStyleSheet()
        # DO NOT call setStyleSheet() here - it overrides the app stylesheet!
        
        # Initialize update checker
        self.update_checker = UpdateChecker(
            current_version=APP_VERSION,
            update_url="https://ozymandiasone.github.io/TechDeck-updates/manifest.json",
            check_interval_hours=24
        )
        self.update_checker.set_update_callback(self._on_update_available)
        self.update_checker.set_mandatory_update_callback(self._on_mandatory_update)
        
        # Create main layout
        self._setup_ui()
        
        # Start update checker after UI is ready (delayed by 3 seconds)
        QTimer.singleShot(3000, self.update_checker.start)

        # Startup fade-in. Window opens at opacity 0 so it is invisible behind
        # the splash subprocess while warmup_pages() runs. __main__.py calls
        # start_fadein() AFTER the splash closes, so the user sees a clean
        # splash -> fade -> solid TechDeck transition with no overlap.
        self.setWindowOpacity(0.0)
        self._fadein = QPropertyAnimation(self, b"windowOpacity")
        self._fadein.setDuration(400)
        self._fadein.setStartValue(0.0)
        self._fadein.setEndValue(1.0)
        self._fadein.setEasingCurve(QEasingCurve.Type.OutCubic)

    def start_fadein(self):
        """Begin the startup fade-in animation. Called by __main__.py once
        the splash has closed, so the fade is the FIRST thing the user sees
        in place of the splash (rather than competing with it)."""
        self._fadein.start()
    
    def _setup_ui(self):
        """Set up the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== Sidebar =====
        self.sidebar = Sidebar(settings_manager=self.settings)
        self.sidebar.page_changed.connect(self._on_page_changed)
        main_layout.addWidget(self.sidebar)
        self._step("sidebar built")
        QApplication.processEvents()

        # ===== Right side: Page Stack (console integrated into home page) =====
        self.page_stack = QStackedWidget()
        
        # Get theme colors from ThemeManager (centralized source of truth)
        from techdeck.ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        theme = theme_manager.get_current_palette()
        
        # --- Create Console Widget (shared, but only shown in home page) ---
        self.console = ConsoleWidget()
        self.console.setMinimumHeight(150)
        # No max height — the splitter range is bounded by the Home pane's
        # minimum instead, so the console can be dragged up until only the
        # profile bar + top tile row remain visible.
        
        # Setup command handler (pass self so commands can reach the window + app)
        self.command_handler = CommandHandler(self.settings, self.console, main_window=self)
        self.console.command_entered.connect(self.command_handler.handle_command)
        self.console.cleared.connect(self.command_handler.stop_session_effects)
        self.console.message_entered.connect(self._on_message_entered)
        self.console.input_provided.connect(self._on_console_input_provided)
        self.console.before_input_request.connect(self._flush_plugin_logs)
        self.console.dashboard_shown.connect(self._on_dashboard_shown)
        self.console.dashboard.set_idle_provider(self._idle_dashboard_data)

        # Create Run Selected button and add to console header
        self.btn_run = QPushButton("Run Selected")
        self.btn_run.setMinimumHeight(36)  # Match console button height
        self.btn_run.setMinimumWidth(120)
        # Inline styling (re-stamped on theme change via _on_theme_changed).
        self.btn_run.setStyleSheet(self._run_button_style(theme))
        self.console.add_header_button(self.btn_run)

        # Subtle icon-only control to collapse the console panel. Sits at the
        # far-right of the console header. Styling + icon are applied in
        # _restyle_console_controls() so they follow the active theme.
        self.btn_collapse_console = QPushButton()
        self.btn_collapse_console.setObjectName("consoleCollapseBtn")
        self.btn_collapse_console.setFixedSize(26, 26)
        self.btn_collapse_console.setIconSize(QSize(16, 16))
        self.btn_collapse_console.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse_console.setToolTip("Collapse console")
        self.btn_collapse_console.clicked.connect(self._collapse_console)
        self.console.add_header_button(self.btn_collapse_console, far_right=True)
        self._step("console + run button built")
        QApplication.processEvents()

        # --- Create Home Page with Console in Splitter ---
        home_container = QWidget()
        home_layout = QVBoxLayout(home_container)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(0)
        
        # Create splitter for home page + console. Style is applied via
        # _restyle_home_splitter() so it can be refreshed on theme change.
        self.home_splitter = QSplitter(Qt.Orientation.Vertical)
        self._restyle_home_splitter()
        
        # Create home page — uses the shared PluginLoader (no rediscovery)
        self.home_page = HomePage(self.settings, plugin_loader=self._plugin_loader)
        # Floor for the splitter: console drag stops just below the top tile row.
        self.home_page.setMinimumHeight(HOME_APPS_MIN_HEIGHT)
        self._step("home page built")
        QApplication.processEvents()
        self.home_page.open_library.connect(self._open_library)
        self.home_page.run_selected.connect(self._on_run_selected)
        
        # Connect plugin execution signals to console
        self.home_page.plugin_log.connect(self._on_plugin_log)
        self.home_page.plugin_progress.connect(self._on_plugin_progress)
        self.home_page.plugin_completed.connect(self._on_plugin_completed)
        self.home_page.all_plugins_done.connect(self._on_all_plugins_done)
        
        # Connect run button to home page
        self.home_page.set_run_button(self.btn_run)
        
        # Add home page and console to splitter
        self.home_splitter.addWidget(self.home_page)
        self.home_splitter.addWidget(self.console)

        # PHASE 2: Set default splitter sizes (no persistence)
        # Users can drag to preferred height each session
        self.home_splitter.setSizes([520, 280])  # Default: ~280px console at the default window size

        # Dragging the divider all the way down still collapses the console
        # (kept intentionally); we detect that and surface the restore bar.
        self.home_splitter.splitterMoved.connect(self._on_home_splitter_moved)

        home_layout.addWidget(self.home_splitter)

        # Slim bar shown only while the console is collapsed. It's a container:
        # a full-width restore button on the left, and the Run Selected button
        # (reparented here for the duration of the collapse) on the right, so
        # collapsing the console never hides Run.
        self.console_restore_bar = QWidget()
        self.console_restore_bar.setObjectName("consoleRestoreWrap")
        self.console_restore_bar.setFixedHeight(44)
        self._restore_bar_layout = QHBoxLayout(self.console_restore_bar)
        self._restore_bar_layout.setContentsMargins(0, 0, 8, 0)
        self._restore_bar_layout.setSpacing(8)
        self.btn_restore_console = QPushButton()
        self.btn_restore_console.setObjectName("consoleRestoreBar")
        self.btn_restore_console.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_console.setToolTip("Show console")
        self.btn_restore_console.clicked.connect(self._expand_console)
        self._restore_bar_layout.addWidget(self.btn_restore_console, 1)
        self.console_restore_bar.hide()
        home_layout.addWidget(self.console_restore_bar)

        # Remembered console height for restore; styled controls follow theme.
        self._saved_console_height = 280
        self._restyle_console_controls()
        QApplication.processEvents()

        # --- Create Other Pages (no console) ---
        # Library page — reuses the shared loader
        self.library_page = LibraryPage(self.settings, plugin_loader=self._plugin_loader)
        self.library_page.saved.connect(self._on_library_saved)
        self.library_page.return_home.connect(self._return_to_home)
        # Library doesn't refresh on navigation (perf), so re-sync it whenever
        # Home changes the kit (missing-tile Remove) or switches profile —
        # otherwise its stale selection re-saves removed tiles back into the kit.
        self.home_page.kit_changed.connect(self.library_page.refresh)
        self.home_page.profile_changed.connect(lambda _name: self.library_page.refresh())
        self._step("library page built")
        QApplication.processEvents()

        # Settings page — reuses the shared loader
        self.settings_page = SettingsPage(self.settings, plugin_loader=self._plugin_loader)
        self.settings_page.theme_changed.connect(self._on_theme_changed)
        self._step("settings page built")
        QApplication.processEvents()

        # Account page
        self.account_page = AccountPage(self.settings)
        self._step("account page built")
        QApplication.processEvents()

        # Add all pages to stack
        self.page_stack.addWidget(home_container)     # 0: Home (with console)
        self.page_stack.addWidget(self.library_page)  # 1: Library
        self.page_stack.addWidget(self.settings_page) # 2: Settings
        self.page_stack.addWidget(self.account_page)  # 3: Account
        
        main_layout.addWidget(self.page_stack, 1)
    
    def warmup_pages(self):
        """Trigger first-paint and any one-time lazy setup on every page in
        the stack so the user's first navigation click is instant. Called
        from __main__.py while the splash subprocess is still covering the
        window — Qt does the work behind the splash and the user never
        sees the cycling."""
        # Cycle through every stacked page so each one fires its first-show
        # / first-paint pipeline (style polish, layout, paint).
        for i in range(1, self.page_stack.count()):
            self.page_stack.setCurrentIndex(i)
            QApplication.processEvents()

            page = self.page_stack.widget(i)
            if page is not None:
                page.ensurePolished()
                # If the page hosts a QTabWidget, walk through every tab too —
                # tab content is typically only laid out / painted on first
                # selection, and SettingsPage has 3 tabs (Apps in particular
                # builds per-plugin widgets on demand).
                from PySide6.QtWidgets import QTabWidget
                for tab_widget in page.findChildren(QTabWidget):
                    original = tab_widget.currentIndex()
                    for t in range(tab_widget.count()):
                        tab_widget.setCurrentIndex(t)
                        QApplication.processEvents()
                    tab_widget.setCurrentIndex(original)
                    QApplication.processEvents()

        # Library has a refresh-on-show; do it once now.
        if self.library_page is not None:
            self.library_page.refresh()
            QApplication.processEvents()

        # Back to home.
        self.page_stack.setCurrentIndex(0)
        QApplication.processEvents()

    def _on_page_changed(self, page_id: str):
        """Handle sidebar navigation."""
        page_map = {
            "home": 0,
            "library": 1,
            "settings": 2,
            "account": 3
        }

        index = page_map.get(page_id, 0)
        self.page_stack.setCurrentIndex(index)

        # NOTE: we used to call library_page.refresh() here on every Library
        # click, which rebuilt all 10 plugin cards from scratch and caused a
        # ~1-second lag. The library is already kept in sync by:
        #   - __init__ (initial load)
        #   - warmup_pages() (startup pre-warm)
        #   - internal handlers when the user changes profile / saves /
        #     creates / edits / deletes a profile
        # If you ever need an external force-refresh (e.g. after the user
        # drops a new plugin folder), call self.library_page.refresh()
        # explicitly at that point — don't bring this back on every nav.
    
    def _open_library(self):
        """Navigate to library page."""
        self.sidebar.set_current_page("library")
        self._on_page_changed("library")  # ensure the stack switches + refresh
    
    def _on_run_selected(self, tile_ids: list):
        """Handle run selected tiles - Log to console and start spinner."""
        self.console.append_system(f"Starting execution of {len(tile_ids)} plugin(s)...")
        for tile_id in tile_ids:
            plugin = self.home_page.plugin_loader.get_plugin(tile_id)
            plugin_name = plugin.name if plugin else tile_id
            self.console.append_system(f"Queued: {plugin_name}")

        if not self._plugin_spinner_timer.isActive():
            self._plugin_run_start = time.time()
            self._plugin_spinner_tick = 0
            self._spinner_phase = "start"
            self._spinner_locked_text = self._spinner_text_pool.get_line()
            self._spinner_current_text = self._spinner_locked_text
            self._spinner_text_ticks = 0
            self._spinner_in_quote = False
            self._spinner_next_quote_tick = random.randint(200, 280)  # first quote ~20-28s in
            self.console.show_spinner(
                self._plugin_spinner_html(self._SPINNER_FRAMES[0], self._spinner_locked_text)
            )
            self._plugin_spinner_timer.start()
    
    def _on_plugin_log(self, plugin_id: str, message: str):
        """Handle plugin log message."""
        plugin = self.home_page.plugin_loader.get_plugin(plugin_id)
        plugin_name = plugin.name if plugin else plugin_id
        self.console.append_plugin_output(plugin_name, message)
    
    def _on_plugin_progress(self, plugin_id: str, progress: int):
        """Handle plugin progress update."""
        # Log progress milestones
        if progress in [25, 50, 75, 100]:
            plugin = self.home_page.plugin_loader.get_plugin(plugin_id)
            plugin_name = plugin.name if plugin else plugin_id
            self.console.append_plugin_output(plugin_name, f"Progress: {progress}%")
    
    def _on_plugin_completed(self, plugin_id: str):
        """Handle plugin completion."""
        plugin = self.home_page.plugin_loader.get_plugin(plugin_id)
        plugin_name = plugin.name if plugin else plugin_id
        
        # Get result from executor
        result = self.home_page.plugin_executor.get_result(plugin_id)
        
        if result:
            if result.status.value == "success":
                self.console.append_system(f"✅ {plugin_name} completed successfully")
                # Reward tickets for a successful run (spendable at Woogy's Emporium).
                bal = self.settings.add_tickets(TICKETS_PER_RUN)
                self.console.append_game(f"🎟 +{TICKETS_PER_RUN} tickets (balance: {bal})")
                # GUI plugins (requires_main_thread) call params['on_success'] themselves
                # at a meaningful moment. Suppress the auto sound for them.
                if not getattr(plugin, 'requires_main_thread', False):
                    get_audio_manager().play(SOUND_SUCCESS)
                # Talkback ~1 in 5; tech tip ~1 in 12 if talkback didn't fire
                if plugin_id != self._last_talkback_plugin and random.random() < 0.20:
                    self.console.append_game(self._talkback.get_line())
                    self._last_talkback_plugin = plugin_id
                elif random.random() < 0.08:
                    self.console.append_system(self._techtip.get_line())
                    self._last_talkback_plugin = None
                else:
                    self._last_talkback_plugin = None
            elif result.status.value == "cancelled":
                self.console.append_system(f"⚠️ {plugin_name} was cancelled")
            elif result.status.value == "timeout":
                self.console.append_error(f"⏰ {plugin_name} timed out: {result.message}")
                get_audio_manager().play(SOUND_ERROR)
            elif result.status.value == "error":
                self.console.append_error(f"❌ {plugin_name} failed: {result.error}")
                get_audio_manager().play(SOUND_ERROR)
    
    def _on_all_plugins_done(self):
        """Handle the end of a full run (all queued plugins finished or cancelled)."""
        self._plugin_spinner_timer.stop()
        elapsed = time.time() - self._plugin_run_start
        done_text = self._spinner_done_pool.get_line()
        done_html = self._plugin_spinner_html(
            "✓", f"{done_text} {self._format_elapsed(elapsed)}."
        )
        self.console.show_spinner(done_html)
        QTimer.singleShot(4000, self.console.hide_spinner)

    def _plugin_spinner_html(self, frame: str, text: str) -> str:
        return (
            f'<span style="color: {self._SPINNER_COLOR}; font-weight: bold; '
            f'font-family: Consolas, monospace; font-size: 10pt;">'
            f'{frame}&nbsp;&nbsp;{text}</span>'
        )

    def _on_plugin_spinner_tick(self):
        tick = self._plugin_spinner_tick
        self._plugin_spinner_tick += 1
        frame = self._SPINNER_FRAMES[tick % len(self._SPINNER_FRAMES)]

        if self._spinner_phase == "start":
            # Freeze on initial text; auto-transition once the plugin is clearly running
            if not self.console.waiting_for_input and tick >= 15:
                self._spinner_phase = "running"
                self._spinner_text_ticks = 0
                self._spinner_in_quote = False
                # Keep the locked text as the first running-phase text so the
                # transition is seamless; the next 80-tick boundary will pull
                # a fresh entry from the shuffled pool.
            text = self._spinner_locked_text
        else:
            # Running phase — slow, free-flowing transitions
            ttick = self._spinner_text_ticks
            self._spinner_text_ticks += 1

            if not self._spinner_in_quote and ttick >= self._spinner_next_quote_tick:
                self._spinner_in_quote = True
                self._spinner_current_quote = self._spinner_quote_pool.get_line()
                self._spinner_quote_end_tick = ttick + 50  # ~5s
                self._spinner_next_quote_tick = ttick + 50 + random.randint(200, 300)

            if self._spinner_in_quote:
                if ttick >= self._spinner_quote_end_tick:
                    # Quote finished — reset per-text counter so the next text
                    # always gets a full 8 s display window, not a partial one.
                    self._spinner_in_quote = False
                    self._spinner_text_ticks = 0
                text = self._spinner_current_quote
            else:
                # Advance text every 80 ticks (8s) — pull next from shuffled pool
                if ttick > 0 and ttick % 80 == 0:
                    self._spinner_current_text = self._spinner_text_pool.get_line()
                text = self._spinner_current_text

        self.console.update_spinner(self._plugin_spinner_html(frame, text))

    def _flush_plugin_logs(self):
        """Drain all buffered plugin logs before showing an input prompt."""
        self.home_page._drain_log_buffer_all()

    def _on_console_input_provided(self, _text: str):
        """When user provides input to a plugin, advance spinner to running phase."""
        if self._plugin_spinner_timer.isActive() and self._spinner_phase == "start":
            self._spinner_phase = "running"
            self._spinner_current_text = self._spinner_text_pool.get_line()
            self._spinner_text_ticks = 0
            self._spinner_in_quote = False

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        return f"{m}m {s:02d}s"

    def _on_message_entered(self, message: str):
        """Free-text (non-command) console input — point the user at /help."""
        self.console.append_system(
            "Commands start with a slash — type /help to see everything "
            "the console can do.")
    
    def _on_library_saved(self):
        """Handle library save - refresh home page."""
        self.home_page.refresh_profiles()
    
    def _return_to_home(self):
        """Navigate back to home page."""
        self.sidebar.set_current_page("home")
        self._on_page_changed("home")  # Actually switch to home page
    
    def _on_theme_changed(self, theme_name: str):
        """Apply theme live — no restart required.

        ThemeManager.set_theme emits theme_changed; __main__.py reapplies
        the QApplication stylesheet on that signal, and any widget that
        mixes in ThemeAware repaints its own inline styles via the same
        signal. Widgets that haven't been migrated still display
        correctly until the next full repaint.
        """
        from techdeck.ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        theme_manager.set_theme(theme_name)
        # The home splitter handle uses inline styling, so refresh it
        # explicitly — it's the visible bar between the apps area and
        # the console.
        self._restyle_home_splitter()
        self._restyle_console_controls()
        self.btn_run.setStyleSheet(self._run_button_style(theme_manager.get_current_palette()))

    @staticmethod
    def _run_button_style(theme) -> str:
        return f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.accent_text};
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_pressed};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
        """

    def _restyle_home_splitter(self):
        """Re-apply the splitter handle/background colors for the active theme."""
        from techdeck.ui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_palette()
        sheet = f"""
            QSplitter {{
                background-color: {theme.background};
            }}
            QSplitter::handle {{
                background-color: {theme.divider};
                height: 2px;
            }}
            QSplitter::handle:hover {{
                background-color: {theme.border_strong};
            }}
        """
        # Clear first + force polish so Qt actually repaints the handle.
        self.home_splitter.setStyleSheet("")
        self.home_splitter.setStyleSheet(sheet)
        style = self.home_splitter.style()
        style.unpolish(self.home_splitter)
        style.polish(self.home_splitter)
        # The handle is a child widget of the splitter; repolish it too,
        # otherwise the bar's pixel color stays stale.
        if self.home_splitter.count() > 0:
            handle = self.home_splitter.handle(1)
            if handle is not None:
                style.unpolish(handle)
                style.polish(handle)
                handle.update()
        self.home_splitter.update()

    def _restyle_console_controls(self):
        """Re-tint + restyle the console collapse button and restore bar."""
        from techdeck.ui.theme_manager import get_theme_manager
        from techdeck.ui.widgets.sidebar import _tint_svg, _icon_folder_for_theme
        tm = get_theme_manager()
        theme = tm.get_current_palette()
        folder = _icon_folder_for_theme(tm.get_current_theme())
        icons_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons" / folder

        self.btn_collapse_console.setIcon(
            QIcon(_tint_svg(icons_dir / "chevron-down.svg", theme.text_secondary, 16))
        )
        self.btn_collapse_console.setStyleSheet(f"""
            QPushButton#consoleCollapseBtn {{
                border: none;
                background: transparent;
                border-radius: 4px;
            }}
            QPushButton#consoleCollapseBtn:hover {{
                background-color: {theme.surface_hover};
            }}
        """)

        self.console_restore_bar.setStyleSheet(f"""
            QWidget#consoleRestoreWrap {{
                background-color: {theme.surface};
                border-top: 1px solid {theme.divider};
            }}
        """)
        self.btn_restore_console.setIcon(
            QIcon(_tint_svg(icons_dir / "chevron-up.svg", theme.text_secondary, 16))
        )
        self.btn_restore_console.setStyleSheet(f"""
            QPushButton#consoleRestoreBar {{
                border: none;
                background-color: transparent;
                color: {theme.text_secondary};
                text-align: left;
                padding-left: 12px;
                font-size: 12px;
            }}
            QPushButton#consoleRestoreBar:hover {{
                background-color: {theme.surface_hover};
                color: {theme.text};
            }}
        """)

    def _collapse_console(self):
        """Hide the console panel and reveal the slim restore bar."""
        sizes = self.home_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._saved_console_height = sizes[1]
        self.console.hide()
        # Keep Run reachable while collapsed: move the actual button (with its
        # state, glow, and Run/Cancel mode intact) onto the restore bar.
        # addWidget reparents it out of the console header automatically.
        self._run_btn_header_index = self.console.header.indexOf(self.btn_run)
        self._restore_bar_layout.addWidget(
            self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
        self.console_restore_bar.show()

    def _expand_console(self):
        """Restore the console panel to its last height."""
        self.console_restore_bar.hide()
        # Give the Run button back to its original console-header slot.
        idx = getattr(self, "_run_btn_header_index", -1)
        if idx >= 0 and self.btn_run.parent() is self.console_restore_bar:
            self._restore_bar_layout.removeWidget(self.btn_run)
            self.console.header.insertWidget(
                idx, self.btn_run, 0, Qt.AlignmentFlag.AlignTop)
        self.console.show()
        height = max(150, self._saved_console_height or 280)
        total = sum(self.home_splitter.sizes())
        height = min(height, max(150, total - HOME_APPS_MIN_HEIGHT))
        self.home_splitter.setSizes([max(total - height, HOME_APPS_MIN_HEIGHT), height])

    def _on_home_splitter_moved(self, pos, index):
        """Convert a drag-to-bottom collapse into the restore-bar state."""
        if not self.console.isVisible():
            return
        sizes = self.home_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] <= 1:
            self._collapse_console()

    def _idle_dashboard_data(self):
        """Data for the idle (no-plugin) dashboard: top-5 most-used tools,
        the blackjack bankroll, and a Sal one-liner."""
        from techdeck.core.flavor import get_sal_line
        usage = []
        for plugin in self._plugin_loader.get_all_plugins():
            count = self.settings.get_plugin_stats(plugin.id).get("run_count", 0)
            if count > 0:
                usage.append((plugin.name, count))
        usage.sort(key=lambda x: x[1], reverse=True)
        return {
            "usage": usage[:5],
            "bankroll": self.settings.get_blackjack_bankroll(),
            "sal_message": get_sal_line(),
        }

    def _on_dashboard_shown(self):
        """A plugin rendered a dashboard: make sure the console is visible and
        tall enough for charts to be readable."""
        if not self.console.isVisible():
            self._expand_console()
        sizes = self.home_splitter.sizes()
        if len(sizes) >= 2:
            total = sum(sizes)
            desired = min(max(sizes[1], 460), max(total - 200, 200))
            self.home_splitter.setSizes([max(total - desired, 200), desired])

    def _on_update_available(self, update_info):
        """Handle optional update notification (called from background thread)."""
        print(f"[SHELL] _on_update_available called! Version: {update_info.version}", flush=True)
        # Emit signal to show dialog on main thread
        print("[SHELL] Emitting show_update_signal", flush=True)
        self.show_update_signal.emit(update_info, False)
    
    def _on_mandatory_update(self, update_info):
        """Handle mandatory update notification (called from background thread)."""
        print(f"[SHELL] _on_mandatory_update called! Version: {update_info.version}", flush=True)
        # Emit signal to show dialog on main thread
        print("[SHELL] Emitting show_update_signal (mandatory)", flush=True)
        self.show_update_signal.emit(update_info, True)
    
    def _show_update_dialog_slot(self, update_info, mandatory):
        """Show update dialog (Qt slot - always runs on main GUI thread)."""
        print(f"[SHELL] _show_update_dialog_slot called! Mandatory: {mandatory}", flush=True)
        dialog = UpdateDialog(update_info, mandatory=mandatory, parent=self)
        print("[SHELL] Calling dialog.exec()", flush=True)
        dialog.exec()
        print("[SHELL] Dialog closed", flush=True)
    
    def check_for_updates_manual(self):
        """Manually check for updates (called from Settings page)."""
        update_info = self.update_checker.check_now()
        
        if update_info is None:
            # No update available
            QMessageBox.information(
                self,
                "No Updates",
                f"You're running the latest version of TechDeck ({APP_VERSION}).",
                QMessageBox.StandardButton.Ok
            )
        # If update found, callbacks will handle showing the dialog
    
    def _center_on_primary_screen(self):
        """Position the window centered within the primary screen's
        available geometry. Used at startup and as a safety clamp if
        the window ever ends up with its title bar off-screen.
        """
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        # Cap the window to the available area so it can't be larger
        # than the desktop (which would still push the title bar off).
        w = min(self.width(), avail.width())
        h = min(self.height(), avail.height())
        if w != self.width() or h != self.height():
            self.resize(w, h)
        x = avail.left() + (avail.width() - w) // 2
        y = avail.top() + (avail.height() - h) // 2
        self.move(x, y)

    def _ensure_title_bar_visible(self):
        """Safety net: if our top edge is above the primary screen's
        available area, snap the window back inside. Called from
        changeEvent so a bad maximize/restore never traps the title bar.
        """
        # A maximized window's frame legitimately extends a few px past every
        # screen edge on Windows (hidden resize borders), so the clamp below
        # would misfire: it re-positioned the still-maximized window one
        # title-bar height too low, clipping the bottom of the app behind the
        # taskbar (and hiding the collapsed-console restore bar entirely).
        # Maximize/fullscreen placement is the OS's job — only clamp normal.
        if self.isMaximized() or self.isFullScreen():
            return
        from PySide6.QtGui import QGuiApplication
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        if frame.top() < avail.top() or frame.left() < avail.left() \
                or frame.right() > avail.right() or frame.bottom() > avail.bottom():
            # Re-center on the screen we're actually on
            w = min(self.width(), avail.width())
            h = min(self.height(), avail.height())
            if w != self.width() or h != self.height():
                self.resize(w, h)
            x = avail.left() + (avail.width() - w) // 2
            y = avail.top() + (avail.height() - h) // 2
            self.move(x, y)

    def nativeEvent(self, eventType, message):
        """Easter egg: left-clicking the TechDeck icon in the native Windows
        title bar (the system-menu icon, top-left of the frame) pops a hidden
        photo instead of opening the system menu. Only the left single-click is
        repurposed -- double-click-to-close, right-click title menu, and
        Alt+Space all still work normally.
        """
        if eventType == "windows_generic_MSG":
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                WM_NCLBUTTONDOWN = 0x00A1
                HTSYSMENU = 3
                if msg.message == WM_NCLBUTTONDOWN and msg.wParam == HTSYSMENU:
                    from techdeck.ui.widgets.pickle_egg import show_pickle_egg
                    show_pickle_egg(self)
                    return True, 0
            except Exception:
                pass  # never let an egg break native event handling
        return super().nativeEvent(eventType, message)

    def changeEvent(self, event):
        """Watch for window-state changes so a maximize/restore that
        leaves the title bar off-screen gets corrected on the next tick.
        """
        if event.type() == event.Type.WindowStateChange:
            # Defer so Qt finishes applying the state change first.
            QTimer.singleShot(0, self._ensure_title_bar_visible)
        super().changeEvent(event)

    def closeEvent(self, event):
        """PHASE 2: Cleanup before closing (console height no longer saved)."""
        # Stop update checker
        self.update_checker.stop()

        # Cancel any running plugins
        self.home_page.plugin_executor.cancel_all()

        event.accept()
