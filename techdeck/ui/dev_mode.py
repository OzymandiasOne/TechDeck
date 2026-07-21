"""
TechDeck dev-mode gate + session state.

DevKit (the developer-tools surface, including the Pixel Studio) must never be
reachable in a shipped build. Two independent guards enforce that:

1. ``is_dev_build()`` is False in any PyInstaller-frozen exe, so the Home
   dev-mode toggle is never even constructed there and dev-mode can never
   become active.
2. All dev-tool CODE lives under ``tools/`` (excluded from the frozen build),
   so there is nothing to import even if a gate were somehow bypassed.

The toggle's on/off state is SESSION-ONLY — it resets to off on every launch
and is intentionally never persisted to settings. Opting in is a per-session
action on the developer's own machine. Home (the toggle) and Settings (the
DevKit tab) both react to state changes via the ``changed`` signal.
"""

import sys

from PySide6.QtCore import QObject, Signal


def is_dev_build() -> bool:
    """True only when running from source (``python -m techdeck``); False in a
    PyInstaller-frozen exe. This is the hard gate that keeps DevKit off every
    shipped build."""
    return not getattr(sys, "frozen", False)


class _DevMode(QObject):
    """Session-only dev-mode switch. Off at every launch."""

    changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self._active = False

    def is_active(self) -> bool:
        # Belt-and-suspenders: can never report active in a frozen build even
        # if set_active(True) were somehow called.
        return is_dev_build() and self._active

    def set_active(self, on: bool) -> None:
        on = bool(on) and is_dev_build()
        if on != self._active:
            self._active = on
            self.changed.emit(on)


_instance: "_DevMode | None" = None


def get_dev_mode() -> _DevMode:
    """Return the process-wide dev-mode singleton."""
    global _instance
    if _instance is None:
        _instance = _DevMode()
    return _instance
