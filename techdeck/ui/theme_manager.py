"""
TechDeck Theme Manager
Singleton that owns the active theme and emits signals when it changes,
so widgets can repaint live without an application restart.
"""

from typing import Optional

from PySide6.QtCore import QObject, Signal

from techdeck.ui.theme import ColorPalette, THEMES, generate_stylesheet


class ThemeManager(QObject):
    """Centralized theme state with signal-based change notifications."""

    _instance: Optional["ThemeManager"] = None

    # Signals
    theme_changed = Signal(str)       # new theme name
    palette_changed = Signal(object)  # ColorPalette

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


_theme_manager = ThemeManager()


def get_theme_manager() -> ThemeManager:
    return _theme_manager
