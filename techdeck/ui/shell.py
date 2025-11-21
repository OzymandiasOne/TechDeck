"""
TechDeck Main Window (Shell) - Claude.ai Style
Clean layout with proper dividers and no internal rounded corners.
FIXED: Inline button styling for Run Selected button
UPDATED: Integrated UpdateChecker for automatic updates
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QStackedWidget, QSplitter, QPushButton
)
from PySide6.QtCore import Qt

from techdeck.core.settings import SettingsManager
from techdeck.core.admin_config import AdminConfigManager
from techdeck.core.update_checker import UpdateChecker
from techdeck.core.constants import WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT, APP_VERSION
from techdeck.ui.theme import generate_stylesheet, get_current_palette
from techdeck.ui.widgets.sidebar import Sidebar
from techdeck.ui.pages.home_page import HomePage
from techdeck.ui.pages.library_page import LibraryPage
from techdeck.ui.pages.account_page import AccountPage
from techdeck.ui.pages.settings_page import SettingsPage
from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.core.command_handler import CommandHandler


class MainWindow(QMainWindow):
    """
    Main application window - Claude.ai style layout.
    Console only appears on Home page.
    """
    
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        
        # Initialize admin config and update checker
        self.admin_config = AdminConfigManager()
        self.update_checker = None
        
        # Start update checker if configured
        update_url = self.admin_config.get_update_url()
        if update_url:
            self.update_checker = UpdateChecker(
                current_version=APP_VERSION,
                update_url=update_url,
                check_interval_hours=24
            )
            
            # Connect update available signal
            self.update_checker.update_available.connect(self._on_update_available)
            
            # Start checking
            self.update_checker.start()
        
        # Window properties
        self.setWindowTitle("TechDeck")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        
        # Apply theme
        theme_name = self.settings.get_theme()
        self.setStyleSheet(generate_stylesheet(theme_name))
        
        # Create main layout
        self._setup_ui()
    
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
        
        # Get theme colors
        from techdeck.ui.theme import get_current_palette
        theme = get_current_palette(self.settings.get_theme())
        
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
        
        # Set initial splitter sizes
        saved_height = self.settings.get_console_height()
        self.home_splitter.setSizes([600, saved_height])
        
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
                self.console.append_system(f"✓ {plugin_name} completed successfully")
            elif result.status.value == "cancelled":
                self.console.append_system(f"✗ {plugin_name} was cancelled")
            elif result.status.value == "error":
                self.console.append_error(f"✗ {plugin_name} failed: {result.error}")
        
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
        """Handle theme change from settings."""
        # Theme will apply on next restart
        pass
    
    def _on_update_available(self, version: str, is_mandatory: bool, download_url: str):
        """Handle update available notification."""
        from PySide6.QtWidgets import QMessageBox
        
        if is_mandatory:
            # Mandatory update - must install
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Update Required")
            msg.setText(f"TechDeck {version} is now available.")
            msg.setInformativeText("This is a mandatory update. The application will close after you click OK.\n\n"
                                  f"Download the update from:\n{download_url}")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            
            # Close application
            self.close()
        else:
            # Optional update - notify but allow continue
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Update Available")
            msg.setText(f"TechDeck {version} is now available.")
            msg.setInformativeText(f"You can download the update from:\n{download_url}\n\n"
                                  "Or continue using the current version.")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
    
    def closeEvent(self, event):
        """Save settings before closing."""
        # Save console height from home splitter
        sizes = self.home_splitter.sizes()
        if len(sizes) >= 2:
            self.settings.set_console_height(sizes[1])
        
        # Cancel any running plugins
        self.home_page.plugin_executor.cancel_all()
        
        # Stop update checker
        if self.update_checker:
            self.update_checker.stop()
        
        event.accept()