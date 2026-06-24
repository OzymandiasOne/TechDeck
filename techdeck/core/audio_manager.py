"""
TechDeck AudioManager — singleton for named sound playback.
Expandable: add new SOUND_* constants and entries in _SOUND_FILES to register sounds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QUrl, QTimer, QObject, Slot, QMetaObject, Qt, Q_ARG
from PySide6.QtMultimedia import QSoundEffect

# ── Sound ID constants ──────────────────────────────────────────────────────
SOUND_SUCCESS = "success"
SOUND_ERROR = "error"
SOUND_CLICK = "click"
SOUND_NAV = "nav"
SOUND_CLEAR = "clear"
SOUND_EASTER_EGG = "easter_egg"
SOUND_CARD_DEAL = "card_deal"
SOUND_CARD_DEALER_FINAL = "card_dealer_final"
SOUND_RAVE_MUSIC = "rave_music"

# ── My Account / Emporium UI (UFO 50 "library" SFX) ─────────────────────────
SOUND_UI_TAB = "ui_tab"          # switching tabs (My Account tab bar)
SOUND_UI_FILTER = "ui_filter"    # switching store category
SOUND_UI_SELECT = "ui_select"    # selecting / buying anything
SOUND_UI_CLAIM = "ui_claim"      # claiming achievement tickets
SOUND_GAME_START = "game_start"  # launching a game (ASA: The Video Game, etc.)

# ── My House / Garden (UFO 50 "pet" SFX) ────────────────────────────────────
SOUND_PET_DOOR_OPEN = "pet_door_open"    # facade lifts to reveal interior
SOUND_PET_DOOR_CLOSE = "pet_door_close"  # facade drops back down
SOUND_PET_VOICE = "pet_voice"            # Buddy's occasional ambient chirp
SOUND_PET_JUMP = "pet_jump"              # (reserved) Buddy hop
SOUND_PET_SPLASH = "pet_splash"          # (reserved) water interactions

# Map sound IDs to filenames in assets/sounds/
_SOUND_FILES: Dict[str, str] = {
    SOUND_SUCCESS: "success.wav",
    SOUND_ERROR: "error.wav",
    SOUND_CLICK: "click.wav",
    SOUND_NAV: "nav.wav",
    SOUND_CLEAR: "clear.wav",
    SOUND_EASTER_EGG: "easter_egg.wav",
    SOUND_CARD_DEAL: "UI_HighAndLow_Card_1.wav",
    SOUND_CARD_DEALER_FINAL: "UI_HighAndLow_Card_2.wav",
    SOUND_RAVE_MUSIC: "DaftPunkAlive2007.wav",
    # My Account UI
    SOUND_UI_TAB: "sfx__libPauseMenu00a.wav",
    SOUND_UI_FILTER: "sfx__libFilter00.wav",
    SOUND_UI_SELECT: "sfx__libFavorite00a.wav",
    SOUND_UI_CLAIM: "sfx__libIntro00f.wav",
    SOUND_GAME_START: "sfx__libIntro00g.wav",
    # My House / Garden
    SOUND_PET_DOOR_OPEN: "sfx__petDoor00a.wav",
    SOUND_PET_DOOR_CLOSE: "sfx__petDoor00b.wav",
    SOUND_PET_VOICE: "sfx__petLx00.wav",
    SOUND_PET_JUMP: "sfx__petJump00.wav",
    SOUND_PET_SPLASH: "sfx__petSplash00.wav",
    **{f"moth_voice_{i}": f"voice{i}.wav" for i in range(1, 12)},
}


class _AudioRelay(QObject):
    """QObject relay so worker threads can marshal play() to the main thread."""
    @Slot(str)
    def play_sound(self, sound_id: str) -> None:
        AudioManager().play(sound_id)


_relay: Optional[_AudioRelay] = None


def _get_relay() -> _AudioRelay:
    global _relay
    if _relay is None:
        _relay = _AudioRelay()
    return _relay


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
        _get_relay()  # create relay now, on the main thread, so invokeMethod works from worker threads

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

    def safe_play(self, sound_id: str) -> None:
        """Thread-safe play: marshals the call to the main Qt thread via queued connection."""
        QMetaObject.invokeMethod(
            _get_relay(),
            "play_sound",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, sound_id),
        )

    def play_music_stoppable(self, sound_id: str) -> Optional[tuple]:
        """Play a longer audio file via QMediaPlayer (buffered, no skipping).
        Returns (QMediaPlayer, QAudioOutput) so the caller can call player.stop().
        Caller must keep both objects alive for the duration of playback."""
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        if not self._enabled:
            return None
        filename = _SOUND_FILES.get(sound_id)
        if not filename:
            return None
        path = _sounds_dir() / filename
        if not path.exists():
            return None

        player = QMediaPlayer()
        audio_out = QAudioOutput()
        player.setAudioOutput(audio_out)
        audio_out.setVolume(self._volume)
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        return (player, audio_out)

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
