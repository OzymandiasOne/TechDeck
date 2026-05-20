"""
TechDeck Entry Point
Launches the application when run as: python -m techdeck
PROFESSIONAL: Initializes ThemeManager for live theme switching
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from techdeck.core.settings import SettingsManager
from techdeck.ui.shell import MainWindow
from techdeck.core.constants import APP_NAME, APP_VERSION


def _icon_path() -> Path:
    """Locate TechDeck.ico in both dev mode and frozen PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "TechDeck.ico"
    return Path(__file__).resolve().parents[1] / "assets" / "TechDeck.ico"


def main():
    """Main application entry point."""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Window icon (title bar + taskbar). Setting it on the QApplication
    # makes it the default for every window the app creates.
    ico = _icon_path()
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    
    # Load settings
    settings = SettingsManager()

    # Load user-created custom themes before initializing ThemeManager
    from techdeck.ui.theme import load_custom_themes
    load_custom_themes(settings.get_custom_themes_dir())

    # Initialize ThemeManager with current theme
    from techdeck.ui.theme_manager import get_theme_manager
    theme_manager = get_theme_manager()
    theme_manager.set_theme(settings.get_theme())

    # Apply global stylesheet now, and re-apply on every subsequent
    # theme change so live switching doesn't require a restart.
    # ThemeAware widgets subscribe to theme_changed individually to
    # refresh their own inline styles.
    def _reapply_stylesheet(_theme_name: str):
        app.setStyleSheet(theme_manager.get_stylesheet())
    app.setStyleSheet(theme_manager.get_stylesheet())
    theme_manager.theme_changed.connect(_reapply_stylesheet)
    
    # Create and show main window
    window = MainWindow(settings)
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
