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

**Scoped themes.** A widget belonging to a page that may wear its own theme
sets ``THEME_SCOPE`` to that scope's name (see ``theme_manager.SCOPES``).
Everything else is unchanged: ``get_current_palette()`` returns the scope's
palette when one is pinned and the app's when it is not, and the widget
repaints on a change to either. A scoped page (and any top-level dialog it
opens, which is NOT its child in the widget tree and so inherits nothing) also
calls ``scope_stylesheet()`` and sets that sheet on itself.
"""


class ThemeAware:
    # "" = follow the application theme. Set to a scope name (e.g.
    # theme_manager.SCOPE_ASSISTANT) to follow that scope's override instead.
    THEME_SCOPE: str = ""

    def setup_theme_awareness(self):
        """Subscribe to theme changes and paint once."""
        from techdeck.ui.theme_manager import get_theme_manager
        self._theme_manager = get_theme_manager()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._theme_manager.scope_theme_changed.connect(self._on_scope_changed)
        self.apply_theme()

    def _on_theme_changed(self, theme_name: str):
        del theme_name
        self.apply_theme()

    def _on_scope_changed(self, scope: str):
        """Repaint only when it was OUR scope that moved. A widget following
        the app theme must not flicker because another page was re-themed."""
        if scope and scope == getattr(self, "THEME_SCOPE", ""):
            self.apply_theme()

    def apply_theme(self):
        """Override in subclasses to repaint widget surfaces."""
        pass

    def get_theme_manager(self):
        from techdeck.ui.theme_manager import get_theme_manager
        return get_theme_manager()

    def get_current_palette(self):
        return self.get_theme_manager().palette_for_scope(
            getattr(self, "THEME_SCOPE", ""))

    def get_effective_theme_name(self) -> str:
        return self.get_theme_manager().effective_theme(
            getattr(self, "THEME_SCOPE", ""))

    def scope_stylesheet(self) -> str:
        """The full themed sheet this widget must set on itself, or "" when it
        follows the app and the application stylesheet already covers it.

        Prepend it to a widget's own rules rather than replacing them:
        ``self.setStyleSheet(self.scope_stylesheet() + my_rules)``.
        """
        return self.get_theme_manager().scope_stylesheet(
            getattr(self, "THEME_SCOPE", ""))
