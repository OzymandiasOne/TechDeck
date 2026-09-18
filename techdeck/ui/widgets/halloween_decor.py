"""Halloween dressing on top of the app: corner cobwebs + one scurrying crawly.

Two cobwebs sit in the top-right (small) and bottom-left (large) corners of the
main window, and every few minutes ONE creepy crawly crosses the window - a
spider, a roach or a centipede, never two at once. A spider sometimes lowers
itself from the top on a thread instead.

Everything here is a click-through child overlay of the main window (the
seance Disturbance contract): no stylesheet swap, no layout participation, so
removing it leaves the app exactly as it was and nothing can ever eat a click.

Gate: the season (constants.halloween_active) AND the halloween theme being the
active theme. Switching to any other theme is the off switch - someone who has
opted out of the look has opted out of bugs on their screen too. Re-checked at
USE time (every spawn, every theme change), never cached, so a session left
open across Nov 2 quietly goes back to normal.

The art is .tdart in assets/sprites/critters/ and opens in Pixel Studio like any
other sprite. Bugs are drawn HEAD-UP, seen from above; this module turns them in
quarter turns to face the way they run (a quarter turn keeps pixels crisp).
"""
from __future__ import annotations

import logging
import math
import random
import sys
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer, QEvent, QObject, QPointF, QTimer, Qt, Signal)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from techdeck.ui import pixel_art

log = logging.getLogger(__name__)

CELL = 3                        # px per art cell, bugs
# Finer than the bugs, and a touch see-through: the big web sits over the
# sidebar's "My Account" / "Submit Feedback", which must stay readable.
WEB_CELL = 2                    # px per art cell, cobwebs
WEB_OPACITY = 0.8
OUTLINE = "#0A0610"             # bugs only: carries them over the orange cards
THREAD = QColor("#E6DEF5")      # the dangling spider's silk (the web's white)

# ── when ─────────────────────────────────────────────────────────────────
FIRST_MS = (45_000, 120_000)    # first visitor after launch
EVERY_MS = (180_000, 480_000)   # then one every 3-8 minutes
DANGLE_CHANCE = 0.35            # a spider's odds of coming down on a thread

# ── who: frames, speed px/s, scurry burst s, freeze s, ms per leg frame ──
KINDS = {
    "spider":    dict(frames=2, speed=240, burst=(0.5, 1.3), rest=(0.15, 0.5),
                      step_ms=70),
    "roach":     dict(frames=2, speed=340, burst=(0.3, 0.9), rest=(0.25, 0.8),
                      step_ms=55),
    # a centipede never freezes: it pours along
    "centipede": dict(frames=4, speed=150, burst=(9.0, 9.0), rest=(0.0, 0.0),
                      step_ms=85),
}
WEBS = {"web_small": "tr", "web_large": "bl"}


def _critter_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parents[3] / "assets"
    return base / "sprites" / "critters"


def _load(name: str, scale: int, outline: bool) -> QPixmap | None:
    """One sprite, or None (logged) if it is missing from the build - decor
    that cannot load simply does not appear; it must never break the app."""
    try:
        data = pixel_art.load(_critter_dir() / f"{name}.tdart")
        return pixel_art.render(data, scale=scale, outline=outline,
                                outline_color=OUTLINE)
    except Exception as exc:
        log.warning("halloween decor: could not load %s (%s)", name, exc)
        return None


def decor_active(settings=None) -> bool:
    """Season on, professional off, AND the halloween theme is the one showing."""
    try:
        from techdeck.core.constants import halloween_active
        if not halloween_active(settings=settings):
            return False
        if settings is None:
            from techdeck.core.settings import SettingsManager
            settings = SettingsManager()
        return settings.get_theme() == "halloween"
    except Exception:
        return False


class _Overlay(QWidget):
    """Click-through, background-less child of the host window."""

    def __init__(self, host):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


# ── cobwebs ──────────────────────────────────────────────────────────────
class CornerWeb(_Overlay):
    def __init__(self, host, pixmap: QPixmap, corner: str):
        super().__init__(host)
        self._host = host
        self._pix = pixmap
        self.corner = corner
        self.setFixedSize(pixmap.size())
        host.installEventFilter(self)
        self.place()

    def place(self):
        host = self._host
        x = host.width() - self.width() if self.corner in ("tr", "br") else 0
        y = host.height() - self.height() if self.corner in ("bl", "br") else 0
        self.move(x, y)
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is getattr(self, '_host', None):
            if event.type() == QEvent.Type.Resize:
                self.place()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(WEB_OPACITY)
        painter.drawPixmap(0, 0, self._pix)
        painter.end()


# ── one crawly ───────────────────────────────────────────────────────────
class Critter(_Overlay):
    """One bug making one trip. Deletes itself when it leaves the window."""

    # heading -> quarter turns clockwise from the HEAD-UP art
    _TURNS = {"up": 0, "right": 1, "down": 2, "left": 3}

    # A SIGNAL, not a stored callback: a bound method of the decor kept here
    # made decor <-> critter a reference cycle, which only the garbage
    # collector frees - and in the test run it freed these Qt objects after
    # the QApplication was gone (heap corruption, exit 127, every test green).
    gone = Signal(object)

    def __init__(self, host, kind: str, frames: list[QPixmap],
                 rng: random.Random, dangle: bool = False):
        super().__init__(host)
        self._host = host
        self.kind = kind
        self._spec = KINDS[kind]
        self._rng = rng
        self._gone = False
        self.dangle = dangle
        self._frame = 0
        self._frame_ms = 0.0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        if dangle:
            self._plan_dangle(frames)
        else:
            self._plan_run(frames)

    # -- planning ----------------------------------------------------------
    def _turned(self, frames, heading):
        turn = QTransform().rotate(90 * self._TURNS[heading])
        return [f.transformed(turn) for f in frames]

    def _plan_run(self, frames):
        host, rng = self._host, self._rng
        self.heading = rng.choice(("right", "left", "right", "left",
                                   "down", "up"))
        self._frames = self._turned(frames, self.heading)
        w, h = self._frames[0].width(), self._frames[0].height()
        self.setFixedSize(w, h)
        if self.heading in ("right", "left"):
            lane = rng.uniform(0.08, 0.92) * (host.height() - h)
            start = -w if self.heading == "right" else host.width()
            self._pos = QPointF(start, lane)
            self._span = host.width() + w
        else:
            lane = rng.uniform(0.08, 0.92) * (host.width() - w)
            start = -h if self.heading == "down" else host.height()
            self._pos = QPointF(lane, start)
            self._span = host.height() + h
        self._lane = lane
        self._travelled = 0.0
        self._wander_amp = rng.uniform(6.0, 22.0)
        self._wander_len = rng.uniform(260.0, 520.0)
        self._wander_phase = rng.uniform(0.0, math.tau)
        self._moving = True
        self._phase_left = rng.uniform(*self._spec["burst"])

    def _plan_dangle(self, frames):
        host, rng = self._host, self._rng
        self.heading = "down"
        self._down = self._turned(frames, "down")
        self._up = self._turned(frames, "up")
        self._frames = self._down
        self._bw, self._bh = self._down[0].width(), self._down[0].height()
        x = rng.uniform(0.12, 0.88) * (host.width() - self._bw)
        self._pos = QPointF(x, -self._bh)
        self._drop_to = rng.uniform(0.30, 0.62) * host.height()
        self._stage = "drop"
        self._hang_left = rng.uniform(1.2, 2.4)
        self._moving = True

    # -- life --------------------------------------------------------------
    def start(self):
        self._apply()
        self.show()
        self.raise_()
        self._clock.start()
        self._timer.start()

    def leave(self):
        """Gone now (the trip ended, /clear, or the season switched off)."""
        if self._gone:
            return
        self._gone = True
        self._timer.stop()
        self.hide()
        self.deleteLater()
        self.gone.emit(self)

    def _tick(self):
        dt = min(0.05, self._clock.restart() / 1000.0)   # a stall never teleports
        self.advance(dt)

    def advance(self, dt: float):
        """One step of `dt` seconds (also the test seam)."""
        if self._gone:
            return
        if self.dangle:
            self._advance_dangle(dt)
        else:
            self._advance_run(dt)
        if self._moving:
            self._frame_ms += dt * 1000.0
            if self._frame_ms >= self._spec["step_ms"]:
                self._frame_ms = 0.0
                self._frame = (self._frame + 1) % len(self._frames)
                self.update()
        if not self._gone:
            self._apply()

    def _advance_run(self, dt):
        spec, rng = self._spec, self._rng
        self._phase_left -= dt
        if self._phase_left <= 0.0:
            # scurry, freeze, scurry: what makes it read as alive
            self._moving = not self._moving or spec["rest"][1] <= 0.0
            self._phase_left = rng.uniform(
                *(spec["burst"] if self._moving else spec["rest"]))
        if not self._moving:
            return
        self._travelled += spec["speed"] * dt
        if self._travelled >= self._span:
            self.leave()
            return
        drift = self._wander_amp * math.sin(
            self._wander_phase + math.tau * self._travelled / self._wander_len)
        sign = 1 if self.heading in ("right", "down") else -1
        if self.heading in ("right", "left"):
            start = -self.width() if sign > 0 else self._host.width()
            self._pos = QPointF(start + sign * self._travelled,
                                self._lane + drift)
        else:
            start = -self.height() if sign > 0 else self._host.height()
            self._pos = QPointF(self._lane + drift,
                                start + sign * self._travelled)

    def _advance_dangle(self, dt):
        speed = self._spec["speed"] * 0.55
        if self._stage == "drop":
            self._moving = True
            self._pos.setY(self._pos.y() + speed * dt)
            if self._pos.y() >= self._drop_to:
                self._stage = "hang"
        elif self._stage == "hang":
            self._moving = False
            self._hang_left -= dt
            if self._hang_left <= 0.0:
                self._stage = "climb"
                self._frames = self._up
                self.update()
        else:
            self._moving = True
            self._pos.setY(self._pos.y() - speed * 1.5 * dt)
            if self._pos.y() <= -self._bh:
                self.leave()

    def _apply(self):
        if self.dangle:
            # the widget runs from the top edge down to the spider, so the
            # thread it hangs from can be painted in the same widget
            bottom = max(1, int(self._pos.y()) + self._bh)
            self.setGeometry(int(self._pos.x()), 0, self._bw, bottom)
        else:
            self.move(int(self._pos.x()), int(self._pos.y()))

    def paintEvent(self, event):
        painter = QPainter(self)
        pix = self._frames[self._frame % len(self._frames)]
        if self.dangle:
            painter.setPen(QPen(THREAD, 1))
            mid = self.width() // 2
            painter.drawLine(mid, 0, mid, max(0, self.height() - self._bh))
            painter.drawPixmap(0, self.height() - self._bh, pix)
        else:
            painter.drawPixmap(0, 0, pix)
        painter.end()


# ── the whole dressing ───────────────────────────────────────────────────
class HalloweenDecor(QObject):
    """Owns the cobwebs and the spawn clock. One per main window."""

    def __init__(self, host, settings=None, rng: random.Random | None = None):
        super().__init__(host)
        self._host = host
        self._settings = settings
        self._rng = rng or random.Random()
        self._webs: list[CornerWeb] = []
        self._critter: Critter | None = None
        self._last_kind = None
        self._frames: dict[str, list[QPixmap]] = {}
        self._clock = QTimer(self)
        self._clock.setSingleShot(True)
        self._clock.timeout.connect(self._on_clock)
        self._first = True

    # -- public ------------------------------------------------------------
    def is_active(self) -> bool:
        return decor_active(self._settings)

    def refresh(self):
        """Match the app to the gate: call at startup and on theme change."""
        if self.is_active():
            self._ensure_webs()
            if not self._clock.isActive() and self._critter is None:
                self._arm()
        else:
            self.clear()
            self._clock.stop()
            for web in self._webs:
                web.hide()
                web.deleteLater()
            self._webs = []

    def clear(self):
        """Send the current crawly away (/clear). Cobwebs stay."""
        if self._critter is not None:
            self._critter.leave()

    def current(self) -> Critter | None:
        return self._critter

    def spawn(self, kind: str | None = None, dangle: bool | None = None):
        """Send one out NOW. Returns it, or None if one is already out, the
        kind is unknown, or its art is missing. `/crawl` and the clock both
        come through here, so 'one at a time' lives in exactly one place."""
        if self._critter is not None:
            return None
        if kind is None:
            choices = [k for k in KINDS if k != self._last_kind] or list(KINDS)
            kind = self._rng.choice(choices)
        if kind not in KINDS:
            return None
        frames = self._frames_for(kind)
        if not frames:
            return None
        if dangle is None:
            dangle = kind == "spider" and self._rng.random() < DANGLE_CHANCE
        self._last_kind = kind
        self._critter = Critter(self._host, kind, frames, self._rng,
                                dangle=bool(dangle) and kind == "spider")
        self._critter.gone.connect(self._on_gone)
        self._critter.start()
        return self._critter

    # -- internals ---------------------------------------------------------
    def _frames_for(self, kind):
        if kind not in self._frames:
            loaded = [_load(f"{kind}_{i}", CELL, True)
                      for i in range(KINDS[kind]["frames"])]
            self._frames[kind] = [p for p in loaded if p is not None]
        return self._frames[kind]

    def _ensure_webs(self):
        if self._webs:
            for web in self._webs:
                web.place()
            return
        for name, corner in WEBS.items():
            pix = _load(name, WEB_CELL, False)
            if pix is None:
                continue
            web = CornerWeb(self._host, pix, corner)
            web.show()
            self._webs.append(web)

    def _arm(self):
        lo, hi = FIRST_MS if self._first else EVERY_MS
        self._first = False
        self._clock.start(self._rng.randint(lo, hi))

    def _on_clock(self):
        if not self.is_active():
            self.refresh()          # the season ended while we were open
            return
        host = self._host
        # nobody is looking: skip this visit rather than queue it
        if host.isVisible() and not host.isMinimized():
            self.spawn()
        if self._critter is None:
            self._arm()

    def _on_gone(self, critter):
        if critter is self._critter:
            self._critter = None
            if self.is_active():
                self._arm()
