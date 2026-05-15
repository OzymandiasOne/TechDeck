"""
TechDeck AudioManager — singleton for named sound playback.
Expandable: add new SOUND_* constants and entries in _SOUND_FILES to register sounds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

# ── Sound ID constants ──────────────────────────────────────────────────────
SOUND_SUCCESS = "success"
SOUND_ERROR = "error"
SOUND_CLICK = "click"
SOUND_EASTER_EGG = "easter_egg"

# Map sound IDs to filenames in assets/sounds/
_SOUND_FILES: Dict[str, str] = {
    SOUND_SUCCESS: "success.wav",
    SOUND_ERROR: "error.wav",
    SOUND_CLICK: "click.wav",
    SOUND_EASTER_EGG: "easter_egg.wav",
}


def _sounds_dir() -> Path:
    """Resolve assets/sounds/ for both dev and frozen (PyInstaller) builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "sounds"
    # dev: techdeck/core/ -> techdeck/ -> project root -> assets/sounds/
    return Path(__file__).resolve().parents[2] / "assets" / "sounds"


class AudioManager:
    """
    Singleton audio manager. Call configure() once at startup with saved settings,
    then play(sound_id) anywhere to fire a sound.
    """

    _instance: Optional["AudioManager"] = None

    def __new__(cls) -> "AudioManager":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._enabled: bool = True
        self._volume: float = 0.8          # 0.0–1.0 internally
        self._effects: Dict[str, QSoundEffect] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    def configure(self, *, enabled: bool, volume: int) -> None:
        """Apply settings. volume is 0–100 (int from SettingsManager)."""
        self._enabled = enabled
        self._volume = max(0, min(100, volume)) / 100.0
        for effect in self._effects.values():
            effect.setVolume(self._volume)

    def play(self, sound_id: str) -> None:
        """Play a named sound. Silent no-op if disabled, missing, or unregistered."""
        if not self._enabled:
            return
        if sound_id not in self._effects:
            self._load(sound_id)
        effect = self._effects.get(sound_id)
        if effect and effect.isLoaded():
            effect.play()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: int) -> None:
        """volume is 0–100."""
        self._volume = max(0, min(100, volume)) / 100.0
        for effect in self._effects.values():
            effect.setVolume(self._volume)

    # ── Internal ────────────────────────────────────────────────────────────

    def _load(self, sound_id: str) -> None:
        filename = _SOUND_FILES.get(sound_id)
        if not filename:
            return
        path = _sounds_dir() / filename
        if not path.exists():
            return
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(self._volume)
        self._effects[sound_id] = effect


def get_audio_manager() -> AudioManager:
    """Return the global AudioManager singleton."""
    return AudioManager()
