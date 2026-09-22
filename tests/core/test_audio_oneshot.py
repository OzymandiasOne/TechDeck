"""A sound must fire exactly once per play() call.

`QSoundEffect.statusChanged` is not a load-finished signal - it fires on every
status transition, and an effect can return to Ready later on. The audio
manager's own docstring says a fresh effect is built per play "so that audio
device changes (headphone plug/unplug, mute/unmute) are always picked up", and
that re-initialisation is exactly what puts a loaded effect back through
Ready.

The old code connected a handler that called play() on ANY Ready and never
disconnected it, so a one-shot click sound could fire again later with nothing
driving it - a sound out of nowhere. These tests pin the transition down as
idempotent, for the one-shot path and the ambient-loop path.
"""

import pytest

from techdeck.core import audio_manager


class FakeStatus:
    Null, Loading, Ready, Error = 0, 1, 2, 3


class FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if not self._slots:
            raise TypeError("nothing connected")
        self._slots = [] if slot is None else [s for s in self._slots if s is not slot]

    def emit(self):
        for slot in list(self._slots):
            slot()

    @property
    def connected(self):
        return len(self._slots)


class FakeEffect:
    """Stands in for QSoundEffect: starts Loading, and its status is drivable."""
    Status = FakeStatus
    Infinite = type("I", (), {"value": -1})()
    made = []

    initial_status = FakeStatus.Loading   # set to Ready to model a cached sample

    def __init__(self):
        self._status = FakeEffect.initial_status
        self.plays = 0
        self.loop_count = None
        self.statusChanged = FakeSignal()
        FakeEffect.made.append(self)

    # the bits AudioManager touches
    def setVolume(self, v): self.volume = v
    def setSource(self, url): self.source = url
    def setLoopCount(self, n): self.loop_count = n
    def status(self): return self._status
    def play(self): self.plays += 1

    def become(self, status):
        """Drive a status transition, as the Qt backend would."""
        self._status = status
        self.statusChanged.emit()


@pytest.fixture
def mgr(monkeypatch, tmp_path):
    FakeEffect.made = []
    monkeypatch.setattr(audio_manager, "QSoundEffect", FakeEffect)
    monkeypatch.setattr(audio_manager, "QUrl", type("U", (), {"fromLocalFile": staticmethod(lambda p: p)}))
    # a real file for the exists() guard, under a real sound id
    sound_id = next(iter(audio_manager._SOUND_FILES))
    (tmp_path / audio_manager._SOUND_FILES[sound_id]).write_bytes(b"RIFF")
    monkeypatch.setattr(audio_manager, "_sounds_dir", lambda: tmp_path)
    # QTimer.singleShot would need an event loop; run the release inline
    monkeypatch.setattr(audio_manager, "QTimer",
                        type("T", (), {"singleShot": staticmethod(lambda ms, fn: fn())}))
    m = audio_manager.AudioManager()
    m.configure(enabled=True, volume=80)
    return m, sound_id


def test_a_one_shot_plays_once_however_often_ready_recurs(mgr):
    m, sound_id = mgr
    m.play(sound_id)
    effect = FakeEffect.made[-1]
    assert effect.plays == 0                      # still Loading, nothing yet

    effect.become(FakeStatus.Ready)
    assert effect.plays == 1                      # the real start

    # the device changes and the backend runs it through Ready again, twice
    effect.become(FakeStatus.Loading)
    effect.become(FakeStatus.Ready)
    effect.become(FakeStatus.Ready)
    assert effect.plays == 1, "a click sound fired again on its own"
    assert effect.statusChanged.connected == 0, "the handler must unhook itself"


def test_an_already_loaded_one_shot_plays_once_and_hooks_nothing(mgr, monkeypatch):
    """A sample already in Qt's cache reports Ready straight away - that path
    must not leave a handler behind either."""
    m, sound_id = mgr
    monkeypatch.setattr(FakeEffect, "initial_status", FakeStatus.Ready)
    m.play(sound_id)
    effect = FakeEffect.made[-1]
    assert effect.plays == 1
    # nothing was connected, so a later transition cannot reach a handler
    assert effect.statusChanged.connected == 0
    effect.become(FakeStatus.Ready)
    assert effect.plays == 1


def test_a_failed_load_never_plays(mgr):
    m, sound_id = mgr
    m.play(sound_id)
    effect = FakeEffect.made[-1]
    effect.become(FakeStatus.Error)
    assert effect.plays == 0
    assert effect not in m._active                # and it is not held forever


def test_an_ambient_loop_is_not_restarted_by_a_later_ready(mgr):
    m, sound_id = mgr
    effect = m.play_loop_effect(sound_id)
    assert effect.loop_count == -1 and effect.plays == 0

    effect.become(FakeStatus.Ready)
    assert effect.plays == 1

    # a restart here would make the bed audibly jump back to zero
    effect.become(FakeStatus.Loading)
    effect.become(FakeStatus.Ready)
    assert effect.plays == 1, "the ambient bed restarted from the top"
    assert effect.statusChanged.connected == 0


def test_sound_disabled_plays_nothing(mgr):
    m, sound_id = mgr
    m.configure(enabled=False, volume=80)
    m.play(sound_id)
    assert m.play_loop_effect(sound_id) is None
    assert FakeEffect.made == []
