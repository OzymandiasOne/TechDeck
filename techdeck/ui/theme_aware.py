"""
TechDeck Theme-Aware Widget Mixin

Mix into any QWidget that needs to respond to live theme changes.
Subscribers must override apply_theme() to repaint their surface using
the new palette. setup_theme_awareness() wires the signal and triggers
an initial apply.

Usage:
    class MyWidget(QWidget, ThemeAware):
        def __init__(self):
            super().__init__()
            # build sub-widgets ...
            self.setup_theme_awareness()

        def apply_theme(self):
            theme = self.get_current_palette()
            self.label.setStyleSheet(f"color: {theme.text};")
"""


class ThemeAware:
    def setup_theme_awareness(self):
        """Subscribe to ThemeManager.theme_changed and paint once."""
        from techdeck.ui.theme_manager import get_theme_manager
        self._theme_manager = get_theme_manager()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self.apply_theme()

    def _on_theme_changed(self, theme_name: str):
        del theme_name
        self.apply_theme()

    def apply_theme(self):
        """Override in subclasses to repaint widget surfaces."""
        pass

    def get_theme_manager(self):
        from techdeck.ui.theme_manager import get_theme_manager
        return get_theme_manager()

    def get_current_palette(self):
        return self.get_theme_manager().get_current_palette()
