"""
TechDeck Entry Point
Launches the application when run as: python -m techdeck
PROFESSIONAL: Initializes ThemeManager for live theme switching
"""

import sys
from PySide6.QtWidgets import QApplication
from techdeck.core.settings import SettingsManager
from techdeck.ui.shell import MainWindow
from techdeck.core.constants import APP_NAME, APP_VERSION


def main():
    """Main application entry point."""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    
    # Load settings
    settings = SettingsManager()
    
    # Initialize ThemeManager with current theme
    from techdeck.ui.theme_manager import get_theme_manager
    theme_manager = get_theme_manager()
    theme_manager.set_theme(settings.get_theme())
    
    # Apply global stylesheet to entire application
    app.setStyleSheet(theme_manager.get_stylesheet())
    
    # Create and show main window
    window = MainWindow(settings)
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
