"""
TechDeck Theme Manager - Professional Implementation
Centralized theme management with signal-based updates for live theme switching.
"""

from PySide6.QtCore import QObject, Signal
from typing import Optional
from techdeck.ui.theme import ColorPalette, THEMES, generate_stylesheet


class ThemeManager(QObject):
    """
    Singleton theme manager for professional theme handling.
    
    Features:
    - Signal-based theme change notifications
    - Centralized theme state
    - Live theme switching without restart
    
    Signals:
        theme_changed(str): Emitted when theme changes with new theme name
        palette_changed(ColorPalette): Emitted with new color palette
    """
    
    _instance: Optional['ThemeManager'] = None
    
    # Signals
    theme_changed = Signal(str)  # theme_name
    palette_changed = Signal(object)  # ColorPalette
    
    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize theme manager (only once due to singleton)."""
        if self._initialized:
            return
            
        super().__init__()
        self._current_theme = "dark"
        self._initialized = True
    
    def get_current_theme(self) -> str:
        """Get current theme name."""
        return self._current_theme
    
    def get_current_palette(self) -> ColorPalette:
        """Get current color palette."""
        return THEMES.get(self._current_theme, THEMES["dark"])
    
    def set_theme(self, theme_name: str):
        """
        Change current theme and emit signals.
        
        Args:
            theme_name: Name of theme to activate
        """
        if theme_name not in THEMES:
            theme_name = "dark"
        
        if theme_name == self._current_theme:
            return  # No change needed
        
        old_theme = self._current_theme
        self._current_theme = theme_name
        
        # Emit signals
        self.theme_changed.emit(theme_name)
        self.palette_changed.emit(self.get_current_palette())
    
    def get_stylesheet(self) -> str:
        """Get complete application stylesheet for current theme."""
        return generate_stylesheet(self._current_theme)


# Global instance for easy access
_theme_manager = ThemeManager()


def get_theme_manager() -> ThemeManager:
    """Get the global ThemeManager instance."""
    return _theme_manager
