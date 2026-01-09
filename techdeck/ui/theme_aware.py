"""
TechDeck Theme-Aware Widget Mixin
Provides automatic theme update capability for any widget.
"""

from PySide6.QtCore import QObject


class ThemeAware:
    """
    Mixin class for widgets that need to respond to theme changes.
    
    Usage:
        class MyWidget(QWidget, ThemeAware):
            def __init__(self):
                super().__init__()
                self.setup_theme_awareness()
            
            def apply_theme(self):
                # Update widget's appearance based on current theme
                theme = self.get_theme_manager().get_current_palette()
                self.some_label.setStyleSheet(f"color: {theme.text};")
    """
    
    def setup_theme_awareness(self):
        """
        Connect widget to theme manager for automatic updates.
        Call this in your widget's __init__ after super().__init__().
        """
        from techdeck.ui.theme_manager import get_theme_manager
        
        self._theme_manager = get_theme_manager()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        
        # Apply theme immediately
        self.apply_theme()
    
    def _on_theme_changed(self, theme_name: str):
        """Internal handler for theme changes."""
        self.apply_theme()
    
    def apply_theme(self):
        """
        Override this method to update your widget's appearance.
        This is called automatically when theme changes.
        """
        pass  # Override in subclass
    
    def get_theme_manager(self):
        """Get the theme manager instance."""
        from techdeck.ui.theme_manager import get_theme_manager
        return get_theme_manager()
    
    def get_current_palette(self):
        """Convenience method to get current color palette."""
        return self.get_theme_manager().get_current_palette()
