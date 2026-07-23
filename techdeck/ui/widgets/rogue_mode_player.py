"""
TechDeck Rogue Mode Player
Popup audio player for focus/work sessions.
Uses QMediaPlayer for playlist playback with loop options.
"""

import sys
from pathlib import Path
from typing import ClassVar

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QListWidget, QListWidgetItem, QComboBox, QWidget,
    QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QSize
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QFont, QIcon

from techdeck.ui.theme import get_current_palette
from techdeck.ui.utils import make_tinted_svg_copy

LOOP_ALL  = "loop_all"
LOOP_ONE  = "loop_one"
NO_LOOP   = "no_loop"

_LOOP_LABELS = {
    LOOP_ALL: "Loop All",
    LOOP_ONE: "Loop One",
    NO_LOOP:  "Play Once",
}


class RogueModePlayer(QDialog):
    """
    Popup audio player.  Persists its playlist/loop/volume state via SettingsManager.
    Use RogueModePlayer.get_or_create() to ensure only one instance exists at a time.
    """

    _instance: ClassVar['RogueModePlayer | None'] = None

    @classmethod
    def get_or_create(cls, settings, parent=None) -> 'RogueModePlayer':
        """Return existing player (show/raise it) or create a fresh one."""
        if cls._instance is not None:
            try:
                cls._instance.show()
                cls._instance.raise_()
                cls._instance.activateWindow()
                return cls._instance
            except RuntimeError:
                cls._instance = None
        cls._instance = cls(settings, parent)
        cls._instance.show()
        return cls._instance

    def __init__(self, settings, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._settings = settings
        self._playlist: list[Path] = []   # absolute paths of queued tracks
        self._current_idx: int = -1
        self._is_playing: bool = False
        self._seeking: bool = False        # True while user drags progress slider

        # QMediaPlayer + audio output
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)

        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.errorOccurred.connect(self._on_error)

        self.setWindowTitle("Rogue Mode")
        self.setMinimumWidth(380)
        self.setMaximumWidth(520)
        self.resize(420, 460)

        self._build_ui()
        self._restore_state()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Resolve theme + icon paths once for the whole UI ──
        _tn = self._settings.get_theme()
        _tp = get_current_palette(_tn)
        _idir = (
            Path(sys._MEIPASS) / "assets" / "icons"
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
            else Path(__file__).resolve().parents[3] / "assets" / "icons"
        )
        _ifolder = "light" if _tn in ["dark", "blue", "cyberpunk", "matrix"] else "dark"

        def _media_icon(name: str) -> QIcon:
            tinted = make_tinted_svg_copy(_idir / "light" / name, _tp.text)
            return QIcon(tinted)

        self._icon_play  = _media_icon("play.svg")
        self._icon_pause = _media_icon("pause.svg")

        # ── Header ──
        hdr = QHBoxLayout()
        icon_lbl = QLabel("⚔")
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent;")
        title_lbl = QLabel("ROGUE MODE")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; letter-spacing: 2px; background: transparent;")
        hdr.addWidget(icon_lbl)
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMaximumHeight(1)
        root.addWidget(sep)

        # ── Now playing ──
        self._track_lbl = QLabel("No track loaded")
        self._track_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_lbl.setWordWrap(True)
        self._track_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent; padding: 4px 0;"
        )
        root.addWidget(self._track_lbl)

        # ── Progress bar ──
        prog_row = QVBoxLayout()
        self._progress = QSlider(Qt.Orientation.Horizontal)
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.sliderPressed.connect(self._on_seek_start)
        self._progress.sliderReleased.connect(self._on_seek_end)
        prog_row.addWidget(self._progress)

        time_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setStyleSheet(f"font-size: 11px; background: transparent; color: {_tp.text_secondary};")
        self._total_lbl = QLabel("0:00")
        self._total_lbl.setStyleSheet(f"font-size: 11px; background: transparent; color: {_tp.text_secondary};")
        time_row.addWidget(self._elapsed_lbl)
        time_row.addStretch()
        time_row.addWidget(self._total_lbl)
        prog_row.addLayout(time_row)
        root.addLayout(prog_row)

        # ── Transport controls ──
        transport = QHBoxLayout()
        transport.setSpacing(6)

        self._prev_btn  = self._mk_icon_btn(_media_icon("back.svg"), self._prev_track,  tip="Previous", w=46)
        self._play_btn  = self._mk_icon_btn(self._icon_play, self._toggle_play, tip="Play / Pause", w=56)
        self._next_btn  = self._mk_icon_btn(_media_icon("next.svg"), self._next_track, tip="Next", w=46)
        self._play_btn.setIconSize(QSize(26, 26))
        transport.addStretch()
        transport.addWidget(self._prev_btn)
        transport.addWidget(self._play_btn)
        transport.addWidget(self._next_btn)
        transport.addStretch()
        root.addLayout(transport)

        # ── Volume ──
        vol_row = QHBoxLayout()
        vol_icon = QLabel("🔊")
        vol_icon.setStyleSheet("background: transparent;")
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(75)
        self._vol_slider.setFixedWidth(160)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        self._vol_lbl = QLabel("75%")
        self._vol_lbl.setFixedWidth(36)
        self._vol_lbl.setStyleSheet(f"background: transparent; font-size: 11px; color: {_tp.text_secondary};")
        vol_row.addStretch()
        vol_row.addWidget(vol_icon)
        vol_row.addWidget(self._vol_slider)
        vol_row.addWidget(self._vol_lbl)
        vol_row.addStretch()
        root.addLayout(vol_row)

        # ── Loop mode ──
        loop_row = QHBoxLayout()
        loop_row.setSpacing(6)
        loop_row.addStretch()
        self._loop_btns: dict[str, QPushButton] = {}
        for mode, label in _LOOP_LABELS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda checked, m=mode: self._set_loop_mode(m))
            self._loop_btns[mode] = btn
            loop_row.addWidget(btn)
        loop_row.addStretch()
        root.addLayout(loop_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setMaximumHeight(1)
        root.addWidget(sep2)

        # ── Playlist selector ──
        _arrow = make_tinted_svg_copy(_idir / _ifolder / "chevron-down.svg", _tp.text)
        _pl_css = f"""
            QComboBox {{
                background-color: {_tp.surface};
                color: {_tp.text};
                border: 1px solid {_tp.border};
                border-radius: 6px;
                padding: 4px 8px;
                padding-right: 26px;
            }}
            QComboBox:hover {{ border-color: {_tp.border_strong}; }}
            QComboBox::drop-down {{
                width: 22px; border: none; background: transparent;
                subcontrol-origin: padding; subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: url("{_arrow}"); width: 12px; height: 12px;
                background: transparent; border: none; margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {_tp.surface}; color: {_tp.text};
                border: 1px solid {_tp.border}; border-radius: 4px;
                selection-background-color: {_tp.tile_selected}; outline: none;
            }}
        """

        pl_row = QHBoxLayout()
        pl_lbl = QLabel("Playlist:")
        pl_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        pl_lbl.setFixedWidth(60)
        self._pl_combo = QComboBox()
        self._pl_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._pl_combo.setStyleSheet(_pl_css)
        self._pl_combo.currentIndexChanged.connect(self._on_playlist_selected)
        pl_row.addWidget(pl_lbl)
        pl_row.addWidget(self._pl_combo)
        root.addLayout(pl_row)

        # ── Playlist track list ──
        self._track_list = QListWidget()
        self._track_list.setFixedHeight(130)
        self._track_list.itemDoubleClicked.connect(self._on_track_double_clicked)
        root.addWidget(self._track_list)

    def _mk_icon_btn(self, icon: QIcon, slot, tip: str = "", w: int = 36) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(22, 22))
        btn.setFixedSize(w, 42)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    # ── State restore / persist ───────────────────────────────────────────

    def _restore_state(self):
        rm = self._settings.get_roguemode_settings()

        vol = rm.get("volume", 75)
        self._vol_slider.setValue(vol)
        self._audio_out.setVolume(vol / 100.0)

        loop = rm.get("loop_mode", LOOP_ALL)
        self._loop_mode = loop
        self._update_loop_buttons(loop)

        self._refresh_playlist_combo(rm)

        # Autoplay: start playing if enabled and playlist has tracks
        if rm.get("autoplay", True) and self._playlist:
            self._play_index(0)

    def _refresh_playlist_combo(self, rm: dict = None):
        if rm is None:
            rm = self._settings.get_roguemode_settings()
        playlists = rm.get("playlists", {})
        current_pl = rm.get("current_playlist", "")

        self._pl_combo.blockSignals(True)
        self._pl_combo.clear()
        for name in playlists:
            self._pl_combo.addItem(name, name)
        self._pl_combo.blockSignals(False)

        idx = self._pl_combo.findData(current_pl)
        if idx >= 0:
            self._pl_combo.setCurrentIndex(idx)
            self._load_playlist(current_pl, playlists.get(current_pl, []))
        elif self._pl_combo.count() > 0:
            self._pl_combo.setCurrentIndex(0)
            name = self._pl_combo.currentData()
            self._load_playlist(name, playlists.get(name, []))

    def _load_playlist(self, name: str, filenames: list):
        audio_dir = self._settings.get_roguemode_audio_dir()
        self._playlist = []
        self._track_list.clear()
        for fn in filenames:
            p = audio_dir / fn
            if p.exists():
                self._playlist.append(p)
                item = QListWidgetItem(p.stem)
                item.setToolTip(str(p))
                self._track_list.addItem(item)

    # ── Playback controls ─────────────────────────────────────────────────

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            if self._current_idx < 0 and self._playlist:
                self._play_index(0)
            else:
                self._player.play()

    def _play_index(self, idx: int):
        if not self._playlist or idx < 0 or idx >= len(self._playlist):
            return
        self._current_idx = idx
        path = self._playlist[idx]
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        self._track_lbl.setText(path.stem)
        self._highlight_current()

    def _prev_track(self):
        if self._current_idx > 0:
            self._play_index(self._current_idx - 1)
        elif self._loop_mode == LOOP_ALL and self._playlist:
            self._play_index(len(self._playlist) - 1)

    def _next_track(self):
        next_idx = self._current_idx + 1
        if next_idx < len(self._playlist):
            self._play_index(next_idx)
        elif self._loop_mode == LOOP_ALL and self._playlist:
            self._play_index(0)
        else:
            self._player.stop()

    def _highlight_current(self):
        for i in range(self._track_list.count()):
            item = self._track_list.item(i)
            item.setText(("▶  " if i == self._current_idx else "    ") + self._playlist[i].stem)

    # ── Loop mode ────────────────────────────────────────────────────────

    def _set_loop_mode(self, mode: str):
        self._loop_mode = mode
        self._update_loop_buttons(mode)
        self._settings.update_roguemode_setting("loop_mode", mode)

    def _update_loop_buttons(self, mode: str):
        for m, btn in self._loop_btns.items():
            btn.blockSignals(True)
            btn.setChecked(m == mode)
            btn.blockSignals(False)

    # ── Qt signal handlers ────────────────────────────────────────────────

    def _on_playback_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setIcon(self._icon_pause if playing else self._icon_play)

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._loop_mode == LOOP_ONE:
                self._player.setPosition(0)
                self._player.play()
            else:
                self._next_track()

    def _on_position_changed(self, pos_ms: int):
        if not self._seeking:
            duration = self._player.duration()
            if duration > 0:
                self._progress.setValue(int(pos_ms * 1000 / duration))
            self._elapsed_lbl.setText(self._fmt_ms(pos_ms))

    def _on_duration_changed(self, dur_ms: int):
        self._total_lbl.setText(self._fmt_ms(dur_ms))

    def _on_error(self, error, error_string: str):
        self._track_lbl.setText(f"Error: {error_string}")

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        dur = self._player.duration()
        if dur > 0:
            pos = int(self._progress.value() * dur / 1000)
            self._player.setPosition(pos)

    def _on_volume_changed(self, val: int):
        self._audio_out.setVolume(val / 100.0)
        self._vol_lbl.setText(f"{val}%")
        self._settings.update_roguemode_setting("volume", val)

    def _on_playlist_selected(self, idx: int):
        if idx < 0:
            return
        name = self._pl_combo.currentData()
        rm = self._settings.get_roguemode_settings()
        playlists = rm.get("playlists", {})
        self._load_playlist(name, playlists.get(name, []))
        self._settings.update_roguemode_setting("current_playlist", name)
        self._current_idx = -1
        self._player.stop()
        self._track_lbl.setText("No track loaded")
        self._progress.setValue(0)

    def _on_track_double_clicked(self, item: QListWidgetItem):
        row = self._track_list.row(item)
        self._play_index(row)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def refresh_playlists(self):
        """Called when playlists are changed from Settings page."""
        current_pl = self._settings.get_roguemode_settings().get("current_playlist", "")
        was_playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._refresh_playlist_combo()
        # Restore playback if still on same playlist
        if was_playing and self._pl_combo.currentData() == current_pl:
            pass  # playlist unchanged, keep playing

    def closeEvent(self, event):
        self._player.stop()
        self.hide()
        event.ignore()  # prevent Qt from destroying the window; singleton stays valid
