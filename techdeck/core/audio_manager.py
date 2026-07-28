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
SOUND_UI_CLOSE = "ui_close"      # closing a store category window (the X)
SOUND_UI_SELECT = "ui_select"    # selecting / buying anything
SOUND_UI_CLAIM = "ui_claim"      # claiming achievement tickets
SOUND_GAME_START = "game_start"  # launching a game (ASA: The Video Game, etc.)

# ── Chopper-gunner folder picker (922 Setup) ────────────────────────────────
SOUND_CHOPPER_FIRE = "chopper_fire"        # railgun shot / recoil
SOUND_CHOPPER_IMPACT = "chopper_impact"    # detonation on the folder
SOUND_CHOPPER_LOCK = "chopper_lock"        # designator lock-on
SOUND_CHOPPER_AMBIENT = "chopper_ambient"  # looping gunship interior bed (mp3)

# ── My House / Garden (UFO 50 "pet" SFX) ────────────────────────────────────
SOUND_PET_DOOR_OPEN = "pet_door_open"    # facade lifts to reveal interior
SOUND_PET_DOOR_CLOSE = "pet_door_close"  # facade drops back down
SOUND_PET_VOICE = "pet_voice"            # Buddy's chirp / tree-growth jingle
SOUND_PET_JUMP = "pet_jump"              # Buddy jump-rope
SOUND_PET_SPLASH = "pet_splash"          # Buddy hot-tub bath
SOUND_PET_EAT = "pet_eat"                # Buddy picnic
SOUND_PET_WATER = "pet_water"            # Buddy garden plot
SOUND_PET_FISH = "pet_fish"              # Buddy fishing at the pond
# Interior interactions
SOUND_PET_TV = "pet_tv"                  # Buddy watches TV
SOUND_PET_DESK = "pet_desk"              # Buddy at the desk
SOUND_PET_GUITAR = "pet_guitar"          # Buddy plays guitar
SOUND_PET_FRIDGE = "pet_fridge"          # Buddy raids the fridge
SOUND_PET_BOOK = "pet_book"              # Buddy reads
SOUND_PET_COOK = "pet_cook"              # Buddy cooks at the stove
SOUND_PET_SLEEP = "pet_sleep"            # Buddy sleeps in bed

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
    SOUND_UI_CLOSE: "sfx__libPauseMenu00d.wav",
    SOUND_UI_SELECT: "sfx__libFavorite00a.wav",
    SOUND_UI_CLAIM: "sfx__libIntro00f.wav",
    SOUND_GAME_START: "sfx__libIntro00g.wav",
    # My House / Garden
    SOUND_PET_DOOR_OPEN: "sfx__petDoor00a.wav",
    SOUND_PET_DOOR_CLOSE: "sfx__petDoor00b.wav",
    SOUND_PET_VOICE: "sfx__petLx00.wav",
    SOUND_PET_JUMP: "sfx__petJump00.wav",
    SOUND_PET_SPLASH: "sfx__petSplash00.wav",
    SOUND_PET_EAT: "sfx__petEat00.wav",
    SOUND_PET_WATER: "sfx__petWater00.wav",
    SOUND_PET_FISH: "sfx__petFishingStart00.wav",
    SOUND_PET_TV: "sfx__petTv00.wav",
    SOUND_PET_DESK: "sfx__petDesk00.wav",
    SOUND_PET_GUITAR: "sfx__petGuitar00.wav",
    SOUND_PET_FRIDGE: "sfx__petFridge00.wav",
    SOUND_PET_BOOK: "sfx__petBook00.wav",
    SOUND_PET_COOK: "sfx__petCook00.wav",
    SOUND_PET_SLEEP: "sfx__petFallAsleep00.wav",
    # Chopper-gunner picker
    SOUND_CHOPPER_FIRE: "chopper_fire.wav",
    SOUND_CHOPPER_IMPACT: "chopper_impact.wav",
    SOUND_CHOPPER_LOCK: "chopper_lock.wav",
    SOUND_CHOPPER_AMBIENT: "chopper_ambient.wav",
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

    def play(self, sound_id: str, *, volume_scale: float = 1.0) -> None:
        """
        Play a named sound. A fresh QSoundEffect is created each call so that
        audio device changes are always reflected. Silent no-op if disabled or
        file missing. ``volume_scale`` is a 0.0–1.0 multiplier on the app
        volume for this one shot (e.g. a drone-strike barrage ramping up).
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
        effect.setVolume(self._volume * max(0.0, min(1.0, volume_scale)))
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

    def play_music_stoppable(self, sound_id: str, *, loop: bool = False,
                             volume_scale: float = 1.0) -> Optional[tuple]:
        """Play a longer audio file via QMediaPlayer (buffered, no skipping;
        handles mp3, unlike the WAV-only QSoundEffect path).
        Returns (QMediaPlayer, QAudioOutput) so the caller can call player.stop().
        Caller must keep both objects alive for the duration of playback.

        ``loop=True`` loops forever (for ambient beds). ``volume_scale`` is a
        0.0–1.0 multiplier on the app volume for this one track — e.g. 0.5 to
        run an ambient bed at half the normal level."""
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
        audio_out.setVolume(self._volume * max(0.0, min(1.0, volume_scale)))
        if loop:
            player.setLoops(QMediaPlayer.Loops.Infinite)
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        return (player, audio_out)

    def play_loop_effect(self, sound_id: str, *, volume_scale: float = 1.0):
        """Loop a WAV forever via QSoundEffect (no QMediaPlayer/ffmpeg backend,
        so no codec banner in the console and reliable in the frozen build).
        Returns the QSoundEffect (call .stop() to end it) or None. Use for
        short ambient beds; ``volume_scale`` multiplies the app volume."""
        if not self._enabled:
            return None
        filename = _SOUND_FILES.get(sound_id)
        if not filename:
            return None
        path = _sounds_dir() / filename
        if not path.exists():
            return None

        effect = QSoundEffect()
        effect.setLoopCount(int(QSoundEffect.Infinite.value))
        effect.setVolume(self._volume * max(0.0, min(1.0, volume_scale)))
        effect.setSource(QUrl.fromLocalFile(str(path)))
        if effect.status() == QSoundEffect.Status.Ready:
            effect.play()
        else:
            effect.statusChanged.connect(
                lambda: effect.play()
                if effect.status() == QSoundEffect.Status.Ready else None)
        return effect

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
