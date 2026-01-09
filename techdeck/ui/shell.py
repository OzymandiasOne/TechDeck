"""
TechDeck Main Window (Shell) - Claude.ai Style
Clean layout with proper dividers and no internal rounded corners.
FIXED: Inline button styling for Run Selected button
PHASE 2 FIX: Removed console height persistence - users drag to preferred height
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QStackedWidget, QSplitter, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal

from techdeck.core.settings import SettingsManager
from techdeck.core.constants import WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT, APP_VERSION
from techdeck.ui.theme import generate_stylesheet, get_current_palette
from techdeck.ui.widgets.sidebar import Sidebar
from techdeck.ui.pages.home_page import HomePage
from techdeck.ui.pages.library_page import LibraryPage
from techdeck.ui.pages.account_page import AccountPage
from techdeck.ui.pages.settings_page import SettingsPage
from techdeck.ui.pages.forgeai_page import ForgeAIPage
from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.core.command_handler import CommandHandler
from techdeck.core.update_checker import UpdateChecker
from techdeck.ui.dialogs.update_dialog import UpdateDialog


class MainWindow(QMainWindow):
    """
    Main application window - Claude.ai style layout.
    Console only appears on Home page.
    """
    
    # Signal for showing update dialog on main thread
    show_update_signal = Signal(object, bool)  # (update_info, mandatory)
    
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        
        # Connect signal for thread-safe update dialog
        self.show_update_signal.connect(self._show_update_dialog_slot)
        
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
        
        # Setup command handler
        self.command_handler = CommandHandler(self.settings, self.console)
        self.console.command_entered.connect(self.command_handler.handle_command)
        self.console.message_entered.connect(self._on_message_entered)
        
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
        
        # ForgeAI page
        self.forgeai_page = ForgeAIPage(self.settings)
        
        # Settings page
        self.settings_page = SettingsPage(self.settings)
        self.settings_page.theme_changed.connect(self._on_theme_changed)
        
        # Account page
        self.account_page = AccountPage(self.settings)
        
        # Add all pages to stack
        self.page_stack.addWidget(home_container)  # 0: Home (with console)
        self.page_stack.addWidget(self.library_page)  # 1: Library
        self.page_stack.addWidget(self.forgeai_page)  # 2: ForgeAI
        self.page_stack.addWidget(self.settings_page)  # 3: Settings
        self.page_stack.addWidget(self.account_page)  # 4: Account
        
        main_layout.addWidget(self.page_stack, 1)
    
    def _on_page_changed(self, page_id: str):
        """Handle sidebar navigation."""
        page_map = {
            "home": 0,
            "library": 1,
            "forgeai": 2,
            "settings": 3,
            "account": 4
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
        """Handle run selected tiles - Log to console."""
        self.console.append_system(f"Starting execution of {len(tile_ids)} plugin(s)...")
        for tile_id in tile_ids:
            plugin = self.home_page.plugin_loader.get_plugin(tile_id)
            plugin_name = plugin.name if plugin else tile_id
            self.console.append_system(f"Queued: {plugin_name}")
    
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
                self.console.append_system(f"âœ… {plugin_name} completed successfully")
            elif result.status.value == "cancelled":
                self.console.append_system(f"âš ï¸ {plugin_name} was cancelled")
            elif result.status.value == "timeout":  # PHASE 2: Handle timeout status
                self.console.append_error(f"â±ï¸ {plugin_name} timed out: {result.message}")
            elif result.status.value == "error":
                self.console.append_error(f"âŒ {plugin_name} failed: {result.error}")
        
        # Check if all plugins are done
        active = self.home_page.plugin_executor.get_active_plugins()
        if not active:
            self.console.append_system("All plugins completed.")
    
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
            # Get the Python executable and script path
            python = sys.executable
            
            # Close current window
            self.close()
            
            # Restart the application
            os.execl(python, python, "-m", "techdeck")
    
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
