"""
TechDeck Entry Point
Launches the application when run as: python -m techdeck
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
    
    # Create and show main window
    window = MainWindow(settings)
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()