"""
TechDeck Theme Manager
Singleton that owns the active theme and emits signals when it changes,
so widgets can repaint live without an application restart.

**Scoped themes.** One page may wear a different theme from the rest of the
app. That exists because of a real report: the Halloween theme is a pumpkin,
and the Assistant is the one page people read dense text on all day -- the
contrast that reads as fun on the Library reads as hard work there. So a scope
("assistant") can be pinned to its own theme while everything else follows the
app. A widget opts in with ``ThemeAware.THEME_SCOPE``; nothing else changes.

A scope is a *page-level* override, not a second app theme: the QApplication
stylesheet still comes from the app theme, and the scoped page sets the scoped
sheet on itself (Qt resolves a widget's own stylesheet ahead of an ancestor's).
"""

from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal

from techdeck.ui.theme import ColorPalette, THEMES, generate_stylesheet

# The scopes that exist. Kept as a tuple so a typo in a scope name is a test
# failure rather than a page that silently never follows its own setting.
SCOPE_ASSISTANT = "assistant"
SCOPES = (SCOPE_ASSISTANT,)


class ThemeManager(QObject):
    """Centralized theme state with signal-based change notifications."""

    _instance: Optional["ThemeManager"] = None

    # Signals
    theme_changed = Signal(str)       # new theme name
    palette_changed = Signal(object)  # ColorPalette
    # A scope's own theme was set or cleared. Carries the scope name, not the
    # theme: a listener only cares whether it was ITS scope.
    scope_theme_changed = Signal(str)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._current_theme = "dark"
        # scope name -> theme name. Absent or "" means "follow the app".
        self._scope_themes: Dict[str, str] = {}
        self._initialized = True

    def get_current_theme(self) -> str:
        return self._current_theme

    def get_current_palette(self) -> ColorPalette:
        return THEMES.get(self._current_theme, THEMES["dark"])

    def set_theme(self, theme_name: str):
        if theme_name not in THEMES:
            theme_name = "dark"
        if theme_name == self._current_theme:
            return
        self._current_theme = theme_name
        self.theme_changed.emit(theme_name)
        self.palette_changed.emit(self.get_current_palette())

    def get_stylesheet(self) -> str:
        return generate_stylesheet(self._current_theme)

    # ── scopes ───────────────────────────────────────────────────────────────

    def scope_theme(self, scope: str) -> str:
        """The theme pinned to ``scope``, or "" when it follows the app."""
        name = self._scope_themes.get(scope or "", "")
        return name if name in THEMES else ""

    def set_scope_theme(self, scope: str, theme_name: str) -> None:
        """Pin ``scope`` to a theme, or pass "" to put it back on the app's.

        An unknown theme name clears the scope rather than falling back to
        dark: a custom theme that has since been deleted should leave the page
        following the app, not drag it somewhere the user never chose.
        """
        if not scope:
            return
        name = theme_name if theme_name in THEMES else ""
        if self.scope_theme(scope) == name:
            return
        if name:
            self._scope_themes[scope] = name
        else:
            self._scope_themes.pop(scope, None)
        self.scope_theme_changed.emit(scope)

    def effective_theme(self, scope: str = "") -> str:
        """The theme a widget in ``scope`` should actually paint with."""
        return self.scope_theme(scope) or self._current_theme

    def palette_for_scope(self, scope: str = "") -> ColorPalette:
        return THEMES.get(self.effective_theme(scope), THEMES["dark"])

    def scope_stylesheet(self, scope: str = "") -> str:
        """The full sheet a scoped page sets on itself, or "" when the scope
        follows the app (and the application sheet already covers it)."""
        name = self.scope_theme(scope)
        return generate_stylesheet(name) if name else ""


_theme_manager = ThemeManager()


def get_theme_manager() -> ThemeManager:
    return _theme_manager
