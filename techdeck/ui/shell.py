"""
TechDeck Main Window (Shell) - Claude.ai Style
Clean layout with proper dividers and no internal rounded corners.
FIXED: Inline button styling for Run Selected button
PHASE 2 FIX: Removed console height persistence - users drag to preferred height
"""

import time
import random

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSplitter, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT, APP_VERSION
from techdeck.ui.theme import generate_stylesheet, get_current_palette
from techdeck.ui.widgets.sidebar import Sidebar
from techdeck.ui.pages.home_page import HomePage
from techdeck.ui.pages.library_page import LibraryPage
from techdeck.ui.pages.account_page import AccountPage
from techdeck.ui.pages.settings_page import SettingsPage
from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.core.command_handler import CommandHandler
from techdeck.core.update_checker import UpdateChecker
from techdeck.core.flavor import TalkbackState
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
        "typing /rave into the console..."
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
        
        # Connect signal for thread-safe update dialog
        self.show_update_signal.connect(self._show_update_dialog_slot)

        # Personality: talkback pool
        self._talkback = TalkbackState()
        self._last_talkback_plugin: str | None = None

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
        self._spinner_text_idx = 0       # current text index (running phase)
        self._spinner_text_ticks = 0     # ticks elapsed in running phase
        
        # Window properties
        self.setWindowTitle("TechDeck")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        
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

        # Startup fade-in
        self.setWindowOpacity(0.0)
        self._fadein = QPropertyAnimation(self, b"windowOpacity")
        self._fadein.setDuration(400)
        self._fadein.setStartValue(0.0)
        self._fadein.setEndValue(1.0)
        self._fadein.setEasingCurve(QEasingCurve.Type.OutCubic)
        QTimer.singleShot(50, self._fadein.start)
    
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
        
        # ===== Right side: Page Stack (console integrated into home page) =====
        self.page_stack = QStackedWidget()
        
        # Get theme colors from ThemeManager (centralized source of truth)
        from techdeck.ui.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        theme = theme_manager.get_current_palette()
        
        # --- Create Console Widget (shared, but only shown in home page) ---
        self.console = ConsoleWidget()
        self.console.setMinimumHeight(150)
        self.console.setMaximumHeight(400)
        
        # Setup command handler (pass self so commands can reach the window + app)
        self.command_handler = CommandHandler(self.settings, self.console, main_window=self)
        self.console.command_entered.connect(self.command_handler.handle_command)
        self.console.message_entered.connect(self._on_message_entered)
        self.console.input_provided.connect(self._on_console_input_provided)
        self.console.before_input_request.connect(self._flush_plugin_logs)
        
        # Create Run Selected button and add to console header
        self.btn_run = QPushButton("Run Selected")
        self.btn_run.setMinimumHeight(36)  # Match console button height
        self.btn_run.setMinimumWidth(120)
        # Apply primary button styling INLINE - most reliable approach
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent};
                color: #FFFFFF;
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
        """)
        self.console.add_header_button(self.btn_run)
        
        # --- Create Home Page with Console in Splitter ---
        home_container = QWidget()
        home_layout = QVBoxLayout(home_container)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(0)
        
        # Create splitter for home page + console
        self.home_splitter = QSplitter(Qt.Orientation.Vertical)
        self.home_splitter.setStyleSheet(f"""
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
        """)
        
        # Create home page
        self.home_page = HomePage(self.settings)
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
        self.home_splitter.setSizes([600, 250])  # Default: 600px home, 250px console
        
        home_layout.addWidget(self.home_splitter)
        
        # --- Create Other Pages (no console) ---
        # Library page
        self.library_page = LibraryPage(self.settings)
        self.library_page.saved.connect(self._on_library_saved)
        self.library_page.return_home.connect(self._return_to_home)
        
        # Settings page
        self.settings_page = SettingsPage(self.settings)
        self.settings_page.theme_changed.connect(self._on_theme_changed)
        
        # Account page
        self.account_page = AccountPage(self.settings)
        
        # Add all pages to stack
        self.page_stack.addWidget(home_container)  # 0: Home (with console)
        self.page_stack.addWidget(self.library_page)  # 1: Library
        self.page_stack.addWidget(self.settings_page)  # 2: Settings
        self.page_stack.addWidget(self.account_page)  # 3: Account
        
        main_layout.addWidget(self.page_stack, 1)
    
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
        
        # Refresh library page when navigating to it
        if page_id == "library":
            self.library_page.refresh()
    
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
            self._spinner_locked_text = self._SPINNER_TEXTS[0]
            self._spinner_text_idx = 0
            self._spinner_text_ticks = 0
            self._spinner_in_quote = False
            self._spinner_next_quote_tick = random.randint(200, 280)  # first quote ~20-28s in
            self.console.show_spinner(
                self._plugin_spinner_html(self._SPINNER_FRAMES[0], self._SPINNER_TEXTS[0])
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
                # GUI plugins (requires_main_thread) call params['on_success'] themselves
                # at a meaningful moment. Suppress the auto sound for them.
                if not getattr(plugin, 'requires_main_thread', False):
                    get_audio_manager().play(SOUND_SUCCESS)
                # Talkback: ~1 in 5 runs, never the same plugin twice in a row
                if plugin_id != self._last_talkback_plugin and random.random() < 0.20:
                    self.console.append_game(self._talkback.get_line())
                    self._last_talkback_plugin = plugin_id
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
        done_text = random.choice(self._DONE_TEXTS)
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
                self._spinner_text_idx = 0
                self._spinner_text_ticks = 0
                self._spinner_in_quote = False
            text = self._spinner_locked_text
        else:
            # Running phase — slow, free-flowing transitions
            ttick = self._spinner_text_ticks
            self._spinner_text_ticks += 1

            if not self._spinner_in_quote and ttick >= self._spinner_next_quote_tick:
                self._spinner_in_quote = True
                self._spinner_current_quote = random.choice(self._SPINNER_QUOTES)
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
                # Advance text every 80 ticks (8s)
                if ttick > 0 and ttick % 80 == 0:
                    self._spinner_text_idx = (self._spinner_text_idx + 1) % len(self._SPINNER_TEXTS)
                text = self._SPINNER_TEXTS[self._spinner_text_idx]

        self.console.update_spinner(self._plugin_spinner_html(frame, text))

    def _flush_plugin_logs(self):
        """Drain all buffered plugin logs before showing an input prompt."""
        self.home_page._drain_log_buffer_all()

    def _on_console_input_provided(self, _text: str):
        """When user provides input to a plugin, advance spinner to running phase."""
        if self._plugin_spinner_timer.isActive() and self._spinner_phase == "start":
            self._spinner_phase = "running"
            self._spinner_text_idx = random.randint(1, len(self._SPINNER_TEXTS) - 1)
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
        """Handle natural language message (for ChatGPT later)."""
        self.console.append_assistant("ChatGPT integration coming soon!")
        self.console.append_system("For now, try using commands like /help")
    
    def _on_library_saved(self):
        """Handle library save - refresh home page."""
        self.home_page.refresh_profiles()
    
    def _return_to_home(self):
        """Navigate back to home page."""
        self.sidebar.set_current_page("home")
        self._on_page_changed("home")  # Actually switch to home page
    
    def _on_theme_changed(self, theme_name: str):
        """Handle theme change from settings - restart required for full effect."""
        from techdeck.ui.theme_manager import get_theme_manager
        from PySide6.QtWidgets import QApplication
        import sys
        import os
        
        # Update theme manager
        theme_manager = get_theme_manager()
        theme_manager.set_theme(theme_name)
        
        # Show restart dialog
        reply = QMessageBox.question(
            self,
            "Restart Required",
            f"Theme changed to '{theme_name.capitalize()}'.\n\n"
            "TechDeck needs to restart to fully apply the theme.\n\n"
            "Restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.close()

            if getattr(sys, 'frozen', False):
                # Frozen PyInstaller build — restart the exe directly
                os.execl(sys.executable, sys.executable)
            else:
                # Dev mode — relaunch as a module
                os.execl(sys.executable, sys.executable, "-m", "techdeck")
    
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
    
    def closeEvent(self, event):
        """PHASE 2: Cleanup before closing (console height no longer saved)."""
        # Stop update checker
        self.update_checker.stop()
        
        # Cancel any running plugins
        self.home_page.plugin_executor.cancel_all()
        
        event.accept()
