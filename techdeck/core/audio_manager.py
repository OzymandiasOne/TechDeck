"""
TechDeck AudioManager — singleton for named sound playback.
Expandable: add new SOUND_* constants and entries in _SOUND_FILES to register sounds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtMultimedia import QSoundEffect

# ── Sound ID constants ──────────────────────────────────────────────────────
SOUND_SUCCESS = "success"
SOUND_ERROR = "error"
SOUND_CLICK = "click"
SOUND_NAV = "nav"
SOUND_CLEAR = "clear"
SOUND_EASTER_EGG = "easter_egg"

# Map sound IDs to filenames in assets/sounds/
_SOUND_FILES: Dict[str, str] = {
    SOUND_SUCCESS: "success.wav",
    SOUND_ERROR: "error.wav",
    SOUND_CLICK: "click.wav",
    SOUND_NAV: "nav.wav",
    SOUND_CLEAR: "clear.wav",
    SOUND_EASTER_EGG: "easter_egg.wav",
    **{f"moth_voice_{i}": f"voice{i}.wav" for i in range(1, 12)},
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

    A fresh QSoundEffect is created on every play() call so that audio device
    changes (headphone plug/unplug, mute/unmute) are always picked up.
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
        self._active: List[QSoundEffect] = []  # keeps refs alive until playback ends

    # ── Public API ──────────────────────────────────────────────────────────

    def configure(self, *, enabled: bool, volume: int) -> None:
        """Apply settings. volume is 0–100 (int from SettingsManager)."""
        self._enabled = enabled
        self._volume = max(0, min(100, volume)) / 100.0

    def play(self, sound_id: str) -> None:
        """
        Play a named sound. A fresh QSoundEffect is created each call so that
        audio device changes are always reflected. Silent no-op if disabled or
        file missing.
        """
        if not self._enabled:
            return
        filename = _SOUND_FILES.get(sound_id)
        if not filename:
            return
        path = _sounds_dir() / filename
        if not path.exists():
            return

        effect = QSoundEffect()
        effect.setVolume(self._volume)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        self._active.append(effect)

        def _on_status():
            if effect.status() == QSoundEffect.Status.Ready:
                effect.play()
                # Release our reference a few seconds after playback starts
                QTimer.singleShot(4000, lambda: self._release(effect))
            elif effect.status() not in (
                QSoundEffect.Status.Null, QSoundEffect.Status.Loading
            ):
                self._release(effect)

        if effect.status() == QSoundEffect.Status.Ready:
            effect.play()
            QTimer.singleShot(4000, lambda: self._release(effect))
        else:
            effect.statusChanged.connect(_on_status)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: int) -> None:
        """volume is 0–100. Affects future play() calls only."""
        self._volume = max(0, min(100, volume)) / 100.0

    # ── Internal ────────────────────────────────────────────────────────────

    def _release(self, effect: QSoundEffect) -> None:
        try:
            self._active.remove(effect)
        except ValueError:
            pass


def get_audio_manager() -> AudioManager:
    """Return the global AudioManager singleton."""
    return AudioManager()
