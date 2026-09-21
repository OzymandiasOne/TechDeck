"""Halloween dressing on top of the app: corner cobwebs + one darting crawly.

Two cobwebs sit in the top-right (small) and bottom-left (large) corners of the
main window, and at unpredictable moments ONE creepy crawly bolts across it,
never two at once. A spider sometimes drops from the top on a thread instead.

REALISTIC, not pixel art (his call, 2026-09-18; the pixel first draft is commit
20c0b4e1).
  * The bugs are real 3D, rendered in Blender by tools/blender_art/critters.py
    into assets/critters/ as top-down RGBA frame loops (fur, jointed legs, a
    baked contact shadow). This module only plays them: a flipbook advanced by
    DISTANCE travelled - one loop is exactly `loop_travel_px` of ground, so no
    foot skates - turned smoothly to face any heading.
  * The webs are hairline silk drawn once with an antialiased QPainter -
    sagging rings, snapped strands, dust at the joints.

FAST AND SPORADIC (also his call): it is meant to catch you off guard. A bug
moves in short violent darts at varying speed, snaps to a new heading for each
one, freezes for anything from a blink to a couple of seconds, and now and then
darts the wrong way. Visits are RARE - at least ten minutes apart, never two
bugs at once - so nobody is ever expecting one.

Everything is a click-through child overlay of the main window (the seance
Disturbance contract): no stylesheet swap, no layout participation, so removing
it leaves the app exactly as it was and nothing can ever eat a click.

Gate: the season (constants.halloween_active) AND the halloween theme being the
active theme. Switching to any other theme is the off switch - someone who has
opted out of the look has opted out of bugs on their screen too. Re-checked at
USE time (every spawn, every theme change), never cached, so a session left
open across Nov 2 quietly goes back to normal.
"""
from __future__ import annotations

import json
import logging
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer, QEvent, QObject, QPointF, QRectF, QTimer, Qt, Signal)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

# ── knobs ────────────────────────────────────────────────────────────────
SCALE = 1.0                     # size of EVERY bug at once (each kind has its own `px`)
WEB_SMALL_PX = 150              # top-right
WEB_LARGE_PX = 250              # bottom-left
WEB_SEED = 13                   # same webs every launch
WEB_OPACITY = 0.70              # whole-web see-through (1.0 = as drawn)
# RARE on purpose (his call): a long quiet gap is what makes it a shock. Never
# less than ten minutes between two visits; the spread on top keeps anyone
# from learning the rhythm.
FIRST_MS = (240_000, 480_000)   # first visitor: 4-8 minutes after launch
EVERY_MS = (600_000, 840_000)   # then 10-14 minutes after the last one LEFT
DANGLE_CHANCE = 0.35            # a spider's odds of coming down on a thread
BORED_S = 14.0                  # after this it stops fooling around and leaves
MAX_TRIP_S = 30.0               # nothing stays forever, whatever happens
# The legs cannot usefully cycle faster than this at 60 fps: past it a walk
# loop strobes instead of blurring. Feet skate a little at full sprint, which
# nobody can see at that speed; below it they are planted exactly.
MAX_GAIT_FRAMES_PER_S = 120.0

_SILK = QColor(233, 230, 242)


@dataclass(frozen=True)
class Kind:
    px: float                       # sprite box on screen. Size only: shrinking
                                    # a bug must never slow it down.
    speed: float                    # px/s, before per-dart variety
    dart: tuple[float, float]       # seconds per dart
    swerve: tuple[float, float]     # radians off its line, per dart
    wild: float                     # chance a dart goes badly the wrong way


# A kind only ever appears if its frames exist in assets/critters/.
KINDS = {
    "spider": Kind(96.0, 560.0, (0.12, 0.55), (0.25, 1.10), 0.18),   # 128 -25%
    "roach": Kind(96.0, 680.0, (0.10, 0.45), (0.30, 1.25), 0.22),
    "centipede": Kind(128.0, 300.0, (0.40, 1.10), (0.20, 0.70), 0.08),
}


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


# ── the rendered clips ───────────────────────────────────────────────────
def _critter_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(getattr(sys, "_MEIPASS")) / "assets"
    else:
        base = Path(__file__).resolve().parents[3] / "assets"
    return base / "critters"


@dataclass
class Clip:
    frames: list
    size: int                       # px the frames were rendered at
    loop_travel_px: float           # ground covered by one loop, at `size`


_CLIPS: dict[tuple[str, str], Clip | None] = {}


def load_clip(kind: str, name: str) -> Clip | None:
    """Frames for one clip, or None (logged once) if it is not in the build.
    Loaded on first use, never at startup - startup feel is protected."""
    key = (kind, name)
    if key not in _CLIPS:
        clip = None
        try:
            folder = _critter_dir()
            meta = json.loads((folder / f"{kind}_{name}.json").read_text(
                encoding="utf-8"))
            frames = []
            for i in range(int(meta["frames"])):
                pix = QPixmap(str(folder / f"{kind}_{name}_{i:02d}.png"))
                if pix.isNull():
                    raise OSError(f"frame {i} missing")
                frames.append(pix)
            clip = Clip(frames, int(meta["size"]), float(meta["loop_travel_px"]))
        except Exception as exc:
            log.warning("halloween decor: no %s/%s clip (%s)", kind, name, exc)
        _CLIPS[key] = clip
    return _CLIPS[key]


def available_kinds() -> list[str]:
    return [k for k in KINDS if load_clip(k, "walk") is not None]


# ── overlays ─────────────────────────────────────────────────────────────
class _Overlay(QWidget):
    """Click-through, background-less child of the host window."""

    def __init__(self, host):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def render_web(size: int, corner: str, seed: int = WEB_SEED,
               quarter: bool = False) -> QPixmap:
    """One corner cobweb, drawn once. Built in 'web space' (u, v measured out
    of the corner along the two walls) and mapped into the pixmap per corner,
    so that GRAVITY - the droop of a snapped strand, the hang of a stray
    thread - always points down the screen whichever corner it is in.

    `quarter=True` draws a true 90-degree fan: spokes from wall to wall, all
    the same length, so the outline is a quarter circle of radius ~`size`.
    Otherwise the middle spokes are shorter and the web sags into a kite."""
    rng = random.Random(seed * 7919 + size)
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    flip_x, flip_y = corner in ("tr", "br"), corner in ("bl", "br")

    def px(u, v):
        return QPointF(size - u if flip_x else u, size - v if flip_y else v)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # dusty haze packed into the corner
    haze = QRadialGradient(px(0, 0), size * 0.55)
    haze.setColorAt(0.0, QColor(233, 230, 242, 30))
    haze.setColorAt(1.0, QColor(233, 230, 242, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(haze)
    p.drawRect(0, 0, size, size)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def strand(path: QPainterPath, alpha: float, width: float = 1.0):
        glow = QColor(_SILK)
        glow.setAlphaF(min(1.0, alpha * 0.16))
        p.setPen(QPen(glow, width + 2.4))
        p.drawPath(path)
        core = QColor(_SILK)
        core.setAlphaF(min(1.0, alpha))
        p.setPen(QPen(core, width))
        p.drawPath(path)

    n = 8 if size < 200 else 10
    if quarter:
        # wall to wall: the end spokes lie ALONG the two walls (half a degree
        # in, so the hairline is not clipped by the pixmap edge)
        angles = [math.radians(0.5 + 89 * i / (n - 1)
                               + (rng.uniform(-2.0, 2.0) if 0 < i < n - 1 else 0))
                  for i in range(n)]
        reach = [size * 0.97 for _ in range(n)]
    else:
        angles = [math.radians(3 + 84 * i / (n - 1) + rng.uniform(-2.5, 2.5))
                  for i in range(n)]
        reach = []
        for i in range(n):
            mid = 1 - abs(i - (n - 1) / 2) / ((n - 1) / 2)   # 0 at the walls
            reach.append(size * (0.97 - 0.20 * mid) * rng.uniform(0.9, 1.0))

    def at(i, r):
        r = min(r, reach[i])
        return (r * math.cos(angles[i]), r * math.sin(angles[i]))

    # spokes: taut, but never ruler-straight
    for i in range(n):
        u, v = at(i, reach[i])
        bow = rng.uniform(-0.03, 0.03) * reach[i]
        path = QPainterPath(px(0, 0))
        path.quadTo(px(u * 0.5 - math.sin(angles[i]) * bow,
                       v * 0.5 + math.cos(angles[i]) * bow), px(u, v))
        strand(path, rng.uniform(0.55, 0.85))

    rings = 7 if size < 200 else 10
    joints = []
    for kk in range(1, rings + 1):
        r = size * (0.10 + 0.84 * (kk / rings) ** 1.12) * rng.uniform(0.96, 1.04)
        for i in range(n - 1):
            roll = rng.random()
            if roll < 0.09:
                continue                                     # a gap
            (u0, v0), (u1, v1) = at(i, r), at(i + 1, r)
            am = (angles[i] + angles[i + 1]) / 2
            sag = rng.uniform(0.80, 0.91)
            a, b = px(u0, v0), px(u1, v1)
            if roll < 0.16:
                # snapped at one end: it hangs from the other, straight down
                end = QPointF(a.x() + rng.uniform(-3, 3),
                              a.y() + r * rng.uniform(0.10, 0.22))
                path = QPainterPath(a)
                path.quadTo(QPointF((a.x() + end.x()) / 2 + rng.uniform(-4, 4),
                                    (a.y() + end.y()) / 2), end)
                strand(path, rng.uniform(0.30, 0.5), 0.9)
                continue
            path = QPainterPath(a)
            path.quadTo(px(r * sag * math.cos(am), r * sag * math.sin(am)), b)
            strand(path, rng.uniform(0.35, 0.8))
            joints.append(a)
    # the messy tangle right in the corner
    for _ in range(16):
        r0, r1 = rng.uniform(0.02, 0.2) * size, rng.uniform(0.02, 0.2) * size
        a0, a1 = rng.uniform(0, math.pi / 2), rng.uniform(0, math.pi / 2)
        path = QPainterPath(px(r0 * math.cos(a0), r0 * math.sin(a0)))
        path.lineTo(px(r1 * math.cos(a1), r1 * math.sin(a1)))
        strand(path, rng.uniform(0.18, 0.4), 0.8)
    # stray threads hanging off the outer edge
    for _ in range(5 if size < 200 else 8):
        i = rng.randrange(1, n - 1)
        u, v = at(i, reach[i] * rng.uniform(0.7, 1.0))
        a = px(u, v)
        end = QPointF(a.x() + rng.uniform(-8, 8),
                      a.y() + size * rng.uniform(0.08, 0.2))
        path = QPainterPath(a)
        path.quadTo(QPointF(a.x() + rng.uniform(-10, 10),
                            (a.y() + end.y()) / 2), end)
        strand(path, rng.uniform(0.2, 0.38), 0.8)
    # dust caught where threads cross
    p.setPen(Qt.PenStyle.NoPen)
    for j in joints:
        if rng.random() < 0.22:
            c = QColor(_SILK)
            c.setAlphaF(rng.uniform(0.45, 0.8))
            p.setBrush(c)
            r = rng.uniform(0.7, 1.5)
            p.drawEllipse(j, r, r)
    p.end()
    return pix


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


def _turn_toward(current: float, target: float, max_step: float) -> float:
    delta = (target - current + math.pi) % math.tau - math.pi
    if abs(delta) <= max_step:
        return target
    return current + math.copysign(max_step, delta)


class Critter(_Overlay):
    """One bug making one trip. Deletes itself when it leaves the window."""

    # A SIGNAL, not a stored callback: a bound method of the decor kept here
    # made decor <-> critter a reference cycle, which only the garbage
    # collector frees - and in the test run it freed these Qt objects after
    # the QApplication was gone (heap corruption, exit 127, every test green).
    gone = Signal(object)

    TURN_RATE = 22.0                # rad/s: it snaps round, it does not steer

    def __init__(self, host, kind: str, walk: Clip, rng: random.Random,
                 hang: Clip | None = None):
        super().__init__(host)
        self._host = host
        self.kind = kind
        self._spec = KINDS[kind]
        self._rng = rng
        self._gone = False
        self.dangle = hang is not None
        self._clip = hang if hang is not None else walk
        self._px = self._spec.px * SCALE                 # sprite box on screen
        self._loop_px = self._clip.loop_travel_px * self._px / self._clip.size
        self._gait = 0.0                                 # fractional frame
        self._age = 0.0
        self._speed = 0.0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        if self.dangle:
            self._plan_dangle()
        else:
            self._plan_run()
        self._apply()

    # -- planning ----------------------------------------------------------
    def _plan_run(self):
        host, rng, m = self._host, self._rng, self._px * 0.75
        w, h = host.width(), host.height()
        edge = rng.choice(("left", "right", "left", "right", "top", "bottom"))
        if edge in ("left", "right"):
            self._x = -m if edge == "left" else w + m
            self._y = rng.uniform(0.1, 0.9) * h
            self._exit = ((w + m if edge == "left" else -m),
                          rng.uniform(0.1, 0.9) * h)
        else:
            self._y = -m if edge == "top" else h + m
            self._x = rng.uniform(0.1, 0.9) * w
            self._exit = (rng.uniform(0.1, 0.9) * w,
                          (h + m if edge == "top" else -m))
        self.heading = self._line()
        self._aim = self.heading
        self._travelled = 0.0
        self._entered = False
        # the first dart is a long straight one: it has to get on screen
        self._moving = True
        self._want = self._spec.speed
        self._phase_left = rng.uniform(0.35, 0.6)

    def _line(self) -> float:
        return math.atan2(self._exit[1] - self._y, self._exit[0] - self._x)

    def _plan_dangle(self):
        host, rng = self._host, self._rng
        self._anchor_x = rng.uniform(0.15, 0.85) * host.width()
        self._x, self._y = self._anchor_x, -self._px
        self.heading = math.pi / 2                       # head down
        self._drop_to = rng.uniform(0.30, 0.62) * host.height()
        # it comes down in jerks: fall, snatch, fall
        self._halts = sorted(rng.uniform(0.2, 0.85) * self._drop_to
                             for _ in range(rng.choice((1, 2, 2, 3))))
        self._stage = "drop"
        self._hold = 0.0
        self._hang_left = rng.uniform(0.9, 2.4)
        self._moving = True

    # -- life --------------------------------------------------------------
    def start(self):
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
        self._age += dt
        if self._age > MAX_TRIP_S:
            self.leave()
            return
        if self.dangle:
            self._advance_dangle(dt)
        else:
            self._advance_run(dt)
        if not self._gone:
            self._apply()
            self.update()

    def _next_phase(self):
        spec, rng = self._spec, self._rng
        bored = self._age > BORED_S
        if self._moving and not bored:
            # freeze: mostly a blink, sometimes long enough to make them look
            self._moving = False
            roll = rng.random()
            self._phase_left = (rng.uniform(0.08, 0.40) if roll < 0.70 else
                                rng.uniform(0.50, 1.20) if roll < 0.95 else
                                rng.uniform(1.50, 2.60))
            return
        self._moving = True
        self._want = spec.speed * (1.5 if bored else rng.uniform(0.75, 1.5))
        line = self._line()
        if bored:
            self._aim, self._phase_left = line, 5.0
        elif self._travelled > 250.0 and rng.random() < spec.wild:
            # the wrong way, hard, and not for long
            self._aim = line + rng.choice((-1, 1)) * rng.uniform(1.6, 2.6)
            self._phase_left = rng.uniform(0.10, 0.22)
        else:
            self._aim = line + rng.choice((-1, 1)) * rng.uniform(*spec.swerve)
            self._phase_left = rng.uniform(*spec.dart)

    def _advance_run(self, dt):
        self._phase_left -= dt
        if self._phase_left <= 0.0:
            self._next_phase()
        want = self._want if self._moving else 0.0
        self._speed += (want - self._speed) * min(1.0, dt * 30.0)   # it BOLTS
        self.heading = _turn_toward(self.heading, self._aim, self.TURN_RATE * dt)
        dist = self._speed * dt
        self._travelled += dist
        self._x += math.cos(self.heading) * dist
        self._y += math.sin(self.heading) * dist
        self._step_gait(dist, dt)
        inside = self._box().intersects(QRectF(self._host.rect()))
        if inside:
            self._entered = True
        elif self._entered:
            self.leave()

    def _step_gait(self, dist, dt):
        n = len(self._clip.frames)
        frames = dist / self._loop_px * n
        self._gait = (self._gait + min(frames, MAX_GAIT_FRAMES_PER_S * dt)) % n

    def _advance_dangle(self, dt):
        fall = self._spec.speed * 0.8
        depth = max(0.0, self._y)
        self._x = self._anchor_x + math.sin(self._age * 1.5) * 7.0 * min(
            1.0, depth / 300.0)
        n = len(self._clip.frames)
        self._gait = (self._gait + dt * 14.0) % n        # the legs never rest
        if self._stage == "drop":
            if self._hold > 0.0:
                self._hold -= dt
                return
            self._y += fall * dt
            if self._halts and self._y >= self._halts[0]:
                self._halts.pop(0)
                self._hold = self._rng.uniform(0.12, 0.5)
            if self._y >= self._drop_to:
                self._stage = "hang"
        elif self._stage == "hang":
            self._hang_left -= dt
            if self._hang_left <= 0.0:
                self._stage, self._turn = "turn", 0.0
        elif self._stage == "turn":
            self._turn = min(1.0, self._turn + dt / 0.22)
            self.heading = math.pi / 2 + math.pi * self._turn
            if self._turn >= 1.0:
                self._stage = "climb"
        else:
            self._y -= fall * 1.5 * dt                   # and it is GONE
            if self._y <= -self._px:
                self.leave()

    # -- geometry + paint --------------------------------------------------
    def _box(self) -> QRectF:
        r = self._px * 0.75                              # room to turn in
        box = QRectF(self._x - r, self._y - r, 2 * r, 2 * r)
        if self.dangle:
            box.setTop(0.0)
            box = box.united(QRectF(self._anchor_x - 2, 0, 4, 1))
        return box

    def _apply(self):
        self.setGeometry(self._box().toAlignedRect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(-self.x(), -self.y())          # window coordinates
        if self.dangle:
            back = self._px * 0.30                       # the spinnerets
            silk = QColor(_SILK)
            silk.setAlpha(175)
            painter.setPen(QPen(silk, 1.0))
            painter.drawLine(
                QPointF(self._anchor_x, 0),
                QPointF(self._x - math.cos(self.heading) * back,
                        self._y - math.sin(self.heading) * back))
        frames = self._clip.frames
        pix = frames[int(self._gait) % len(frames)]
        painter.translate(self._x, self._y)
        painter.rotate(math.degrees(self.heading))       # the art faces +x
        half = self._px / 2
        painter.drawPixmap(QRectF(-half, -half, self._px, self._px), pix,
                           QRectF(pix.rect()))
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
        """Send one out NOW. Returns it, or None if one is already out, or the
        kind is unknown / not rendered yet. `/crawl` and the clock both come
        through here, so 'one at a time' lives in exactly one place."""
        if self._critter is not None:
            return None
        ready = available_kinds()
        if kind is None:
            choices = [k for k in ready if k != self._last_kind] or ready
            if not choices:
                return None
            kind = self._rng.choice(choices)
        if kind not in ready:
            return None
        walk = load_clip(kind, "walk")
        hang = load_clip(kind, "hang") if kind == "spider" else None
        if dangle is None:
            dangle = hang is not None and self._rng.random() < DANGLE_CHANCE
        self._last_kind = kind
        self._critter = Critter(self._host, kind, walk, self._rng,
                                hang=hang if dangle else None)
        self._critter.gone.connect(self._on_gone)
        self._critter.start()
        return self._critter

    # -- internals ---------------------------------------------------------
    def _ensure_webs(self):
        if self._webs:
            for web in self._webs:
                web.place()
            return
        # top-right: a clean 90-degree quarter circle (his call); bottom-left
        # keeps the saggy kite
        for size, corner, quarter in ((WEB_SMALL_PX, "tr", True),
                                      (WEB_LARGE_PX, "bl", False)):
            try:
                pix = render_web(size, corner, quarter=quarter)
            except Exception:
                # decor that cannot draw simply does not appear
                log.exception("halloween decor: could not draw the %s web", corner)
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
