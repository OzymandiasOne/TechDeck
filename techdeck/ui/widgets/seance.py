"""The /seance ritual — TechDeck is disturbed, and something climbs out.

THE EFFECT, and why it is built this way
----------------------------------------
The apparition is drawn from ONE grid by ONE painter, into TWO surfaces:

  ConsoleVeil   a child overlay CLIPPED to the console, painting rows [k:]
                — the part still inside.
  Apparition    a frameless top-level at the IDENTICAL screen rect and cell
                size, painting rows [:k] — the part that is out.

The slices are complementary, so their union is always the whole creature:
nothing ever looks erased, which is the point.

The split point is GEOMETRIC, not abstract, and that is the whole trick. The
console's top edge is treated as a SURFACE: rows still below it belong to the
veil (which its own widget bounds clip anyway), rows that have crossed above
it belong to the apparition. The ghost then physically RISES through that
line, so the hand-off is driven by real motion.

(The first version split at an arbitrary row index while the ghost held
still. Being pixel-perfect, that hand-off was literally invisible — the union
never changed, so nothing happened on screen. A perfect crossfade between two
identical renderings is a no-op; the motion through a fixed boundary is what
the eye reads as emergence.)

Because both halves call the same `paint_ghost` with the same cell size at
the same global rect, the seam is aligned by construction rather than by
tuning: there is no second art asset and no second renderer to drift.

The ritual is four beats:
    disturb   the window shudders and the lights fail (nothing answers yet)
    manifest  the ghost fades up low inside the console
    emerge    it hauls itself up through the console's top edge — a glowing
              tear marks where it is breaking through
    linger    free above the app: it says hello, floats gently in place, and
              can be dragged anywhere. It STAYS until dismissed (double-click
              to shoo, or /clear) — a thing you can pick up should not
              evaporate on a timer while you are holding it.

Nothing here may ever break the console: the whole thing is a toy, so every
entry point is guarded and `dismiss()` is idempotent.
"""

from __future__ import annotations

import math
import random

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from techdeck.ui import pixel_art

# ── the apparition ───────────────────────────────────────────────────────
# The art is a .tdart sprite, so it opens in DevKit -> Pixel Studio like any
# other TechDeck sprite: assets/sprites/ghost.tdart. Legend as authored —
#   H lit edge · B body · S shaded edge · E void (eyes and mouth)
# — but nothing here depends on those letters: the palette comes from the
# file, so recolouring or adding tones in the studio just works.
#
# Loaded ONCE at import (the widget sizes below are derived from it), so an
# edit shows up on the next app start rather than the next /seance.
GHOST_SPRITE_NAME = "ghost.tdart"
CELL = 5                     # px per art cell — both halves MUST share this
MARGIN = 1                   # a cell of slack so the outline never clips
GHOST_OUTLINE = "#0A1018"

# Spectral, and deliberately NOT theme-tinted: he has to read as a foreign
# thing on both the near-black console and the bright app. Kept separate from
# the sprite's palette so recolouring the art cannot break his speech bubble.
GHOST_INK = QColor("#101A26")
GHOST_PALE = QColor("#EAF6FF")

# Last-resort silhouette if the sprite is missing from a build — he appears
# as a blank shape rather than not at all.
_FALLBACK = {
    "format": "tdart", "version": 1,
    "palette": {"B": "#BFD8EC"},
    "rows": ["." * 6 + "B" * 12 + "." * 6] * 20,
}


def _sprite_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parents[3] / "assets"
    return base / "sprites" / GHOST_SPRITE_NAME


def _load_sprite():
    try:
        return pixel_art.normalize(pixel_art.load(_sprite_path()))
    except Exception as exc:
        # Loud on purpose: the fallback is a featureless blob, so a silent
        # miss here would ship a blank ghost that still "works".
        logging.getLogger(__name__).warning(
            "seance: could not load %s (%s) — using the blank fallback",
            _sprite_path(), exc)
        return pixel_art.normalize(dict(_FALLBACK))


GHOST_SPRITE = _load_sprite()
GHOST_ROWS = GHOST_SPRITE["rows"]
GRID_W, GRID_H = pixel_art.dimensions(GHOST_SPRITE)
SIZE_W = (GRID_W + 2 * MARGIN) * CELL
SIZE_H = (GRID_H + 2 * MARGIN) * CELL

_PIXMAP = None


def ghost_pixmap():
    """The whole ghost, rendered once at CELL scale with the house outline
    trace. Both halves slice THIS, which is what makes the seam exact: two
    complementary slices of one pixmap are that pixmap."""
    global _PIXMAP
    if _PIXMAP is None:
        _PIXMAP = pixel_art.render(GHOST_SPRITE, scale=CELL, outline=True,
                                   outline_color=GHOST_OUTLINE)
    return _PIXMAP


def paint_ghost(painter: QPainter, row_from: int, row_to: int,
                alpha: float = 1.0, origin: QPoint | None = None):
    """Paint art rows [row_from, row_to) at `origin`, `alpha` 0..1.

    THE seam guarantee: the veil and the apparition both call this with
    complementary row ranges, at the same origin and CELL, against the same
    cached pixmap — so a row belongs to exactly one of them and the union is
    the whole creature. (The outline is baked into the pixmap, so it is
    sliced along with everything else and cannot double up at the join.)
    """
    lo, hi = max(0, row_from), min(GRID_H, row_to)
    if alpha <= 0.0 or hi <= lo:
        return
    origin = origin or QPoint(MARGIN * CELL, MARGIN * CELL)
    pix = ghost_pixmap()
    # the outline lives OUTSIDE the grid, so slice a cell of slack either
    # side and let the neighbouring half own its own edge
    top = lo * CELL
    height = (hi - lo) * CELL
    if alpha < 1.0:
        painter.setOpacity(alpha)
    painter.drawPixmap(origin.x(), origin.y() + top, pix.width(), height,
                       pix, 0, top, pix.width(), height)
    if alpha < 1.0:
        painter.setOpacity(1.0)


class ConsoleVeil(QWidget):
    """The half still inside: a child overlay clipped to the console.

    It is a child of the ConsoleWidget (not of the text area) so it paints
    over the document without touching it — the console's text, the plugin
    output, and the Puppet Master's own bookmarked range are all left
    completely alone by this effect.
    """

    def __init__(self, console):
        super().__init__(console)
        self._console = console
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.rows_from = 0          # rows [rows_from, GRID_H) are still here
        self.alpha = 0.0
        self.ghost_pos = QPoint(0, 0)   # top-left of the art, in veil coords
        self._sync_geometry()

    def _sync_geometry(self):
        """Cover exactly the console's text area, in console coordinates."""
        out = getattr(self._console, "output", None)
        if out is None:
            return
        top_left = out.mapTo(self._console, QPoint(0, 0))
        self.setGeometry(QRect(top_left, out.size()))

    def place_ghost_low(self):
        """Park the ghost low in the console — fully inside, and far enough
        below the surface that hauling itself out is a real journey."""
        self._sync_geometry()
        drop = int((self.height() - GRID_H * CELL) * 0.72)
        self.ghost_pos = QPoint(
            (self.width() - GRID_W * CELL) // 2,
            max(0, drop),
        )

    def surface_global_y(self) -> int:
        """The screen y of the console's top edge — the surface the ghost
        comes through, and the line that decides which half owns which row."""
        return self.mapToGlobal(QPoint(0, 0)).y()

    def set_ghost_global(self, art_pos: QPoint):
        self.ghost_pos = self.mapFromGlobal(art_pos)

    def ghost_global_pos(self) -> QPoint:
        """Where the art's top-left sits in SCREEN coords — the apparition
        aligns to exactly this, which is what makes the seam vanish."""
        return self.mapToGlobal(self.ghost_pos)

    def paintEvent(self, event):
        if self.alpha <= 0.0 or self.rows_from >= GRID_H:
            return
        painter = QPainter(self)
        paint_ghost(painter, self.rows_from, GRID_H, self.alpha,
                    origin=self.ghost_pos)
        painter.end()


class Apparition(QWidget):
    """The half that is out: frameless, translucent, above everything.

    Draws rows [0, rows_to) — the complement of the veil — at the identical
    screen rect until the hand-off completes, after which it owns the whole
    ghost and is free to move.
    """

    def __init__(self, host=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Interactive, unlike the veil: he can be picked up and put down.
        # (That does mean his window swallows clicks meant for whatever is
        # underneath — the same trade the moth and the fidget spinner make.)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedSize(SIZE_W, SIZE_H)
        self.dragging = False
        self.on_shoo = None       # set by the ritual: double-click to banish
        self._drag_pos = None
        self.rows_to = 0
        self.alpha = 1.0
        self.companion = None     # the speech bubble, while one is up
        self._host = host
        self._host_pos = None
        if host is not None:
            self._host_pos = host.frameGeometry().topLeft()
            host.installEventFilter(self)

    def move_art_to(self, global_art_pos: QPoint):
        """Place the window so the ART's top-left lands on the given screen
        point (the window carries a MARGIN of slack around the art)."""
        self.move(global_art_pos - QPoint(MARGIN * CELL, MARGIN * CELL))

    def art_global_pos(self) -> QPoint:
        return self.pos() + QPoint(MARGIN * CELL, MARGIN * CELL)

    # -- follow the window it haunts (same contract as the moth) ----------
    def eventFilter(self, obj, event):
        if obj is getattr(self, '_host', None):
            et = event.type()
            if et == QEvent.Type.Move and self._host_pos is not None:
                new = self._host.frameGeometry().topLeft()
                delta = new - self._host_pos
                self._host_pos = new
                if not delta.isNull():
                    self.move(self.pos() + delta)
                    if self.companion is not None:
                        self.companion.move(self.companion.pos() + delta)
            elif et == QEvent.Type.WindowStateChange:
                self._set_all_visible(not self._host.isMinimized())
            elif et == QEvent.Type.Hide:
                self._set_all_visible(False)
        return super().eventFilter(obj, event)

    def _set_all_visible(self, visible: bool):
        """The bubble is a separate top-level, so it has to be dragged
        through minimise/restore with us or it hangs in empty space."""
        self.setVisible(visible)
        if self.companion is not None:
            try:
                self.companion.setVisible(visible)
            except RuntimeError:
                self.companion = None

    def detach(self):
        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except RuntimeError:
                pass
            self._host = None

    # -- picked up and put down -------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self._drag_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if not (self.dragging and event.buttons() & Qt.MouseButton.LeftButton):
            return
        now = event.globalPosition().toPoint()
        delta = now - self._drag_pos
        self._drag_pos = now
        self.move(self.pos() + delta)
        if self.companion is not None:      # his bubble comes with him
            try:
                self.companion.move(self.companion.pos() + delta)
            except RuntimeError:
                self.companion = None

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self._drag_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        """Shoo him — the moth's contract, so the gesture is already known."""
        if self.on_shoo is not None:
            self.on_shoo()

    def paintEvent(self, event):
        if self.rows_to <= 0:
            return
        painter = QPainter(self)
        paint_ghost(painter, 0, self.rows_to, self.alpha)
        painter.end()


class Disturbance(QWidget):
    """The lights failing: a click-through overlay over the whole window.

    Paints a dim wash plus an occasional bright scan band. Kept as a plain
    overlay rather than a stylesheet swap so it cannot disturb any theme
    state — when it is deleted the app is exactly as it was.
    """

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.dim = 0.0          # 0..1 wash
        self.band_y = -1.0      # normalised scan-band position, <0 = none
        # The tear: a split of cold light along the console's top edge, in
        # THIS widget's coords. It lives here rather than on the apparition
        # because it must be as wide as the console, not as wide as the
        # ghost — a ghost-wide glow reads as a halo, a console-wide slit
        # reads as the box being opened.
        self.tear_y = -1.0
        self.tear_x0 = 0
        self.tear_x1 = 0
        self.tear_strength = 0.0
        self.sync()

    def sync(self):
        self.setGeometry(self._host.rect())

    def paintEvent(self, event):
        if self.dim <= 0.0 and self.band_y < 0 and self.tear_strength <= 0.0:
            return
        painter = QPainter(self)
        if self.dim > 0.0:
            wash = QColor(4, 2, 8)
            wash.setAlphaF(min(0.92, self.dim))
            painter.fillRect(self.rect(), wash)
        if 0.0 <= self.band_y <= 1.0:
            h = max(2, self.height() // 40)
            y = int(self.band_y * self.height())
            glow = QColor(190, 214, 236)
            glow.setAlphaF(0.10)
            painter.fillRect(0, y, self.width(), h, glow)
        if self.tear_strength > 0.0 and self.tear_x1 > self.tear_x0:
            self._paint_tear(painter)
        painter.end()

    def _paint_tear(self, painter: QPainter):
        """The console's top edge, split open. Brightest at the middle of
        the rip and feathered to nothing at its ends, so it reads as a
        wound in that edge rather than a drawn line."""
        strength = self.tear_strength
        reach = int(16 * strength) + 3
        y = int(self.tear_y)
        width = self.tear_x1 - self.tear_x0
        # vertical falloff: glow above and below the split
        band = QRect(self.tear_x0, y - reach, width, reach * 2)
        vert = QLinearGradient(0.0, float(band.top()), 0.0, float(band.bottom()))
        vert.setColorAt(0.0, QColor(214, 236, 255, 0))
        vert.setColorAt(0.5, QColor(214, 236, 255, int(95 * strength)))
        vert.setColorAt(1.0, QColor(214, 236, 255, 0))
        painter.fillRect(band, vert)
        # the split itself, feathered along its length
        core = QLinearGradient(float(self.tear_x0), 0.0,
                               float(self.tear_x1), 0.0)
        core.setColorAt(0.0, QColor(238, 248, 255, 0))
        core.setColorAt(0.5, QColor(238, 248, 255, int(235 * strength)))
        core.setColorAt(1.0, QColor(238, 248, 255, 0))
        painter.fillRect(QRect(self.tear_x0, y - 1, width, 3), core)


class SeanceRitual(QObject):
    """Drives the four beats and owns every widget the ritual creates."""

    # 60fps. At 30 a 5px drift moved in visible 1px steps — the judder was
    # the frame rate, not the curve. Everything here is cheap to repaint (a
    # few hundred fillRects in a 130px window), so the rate is the fix.
    TICK_MS = 16
    SHUDDER_EVERY_MS = 33   # …but the shudder keeps its own slower cadence,
                            # or it stops reading as a shake and just blurs
    DISTURB_MS = 2000
    MANIFEST_MS = 1500
    EMERGE_MS = 2900        # the whole climb, surface crossing included
    GREET_AFTER_MS = 700    # a beat to settle before it says anything
    GREET_READ_MS = 2200    # …and how long it hangs after the last letter
    GREETING = "o hi"
    LINGER_MS = 22000       # it hangs around, then fades of its own accord
    FADE_MS = 1400

    def __init__(self, console, host=None, parent=None):
        super().__init__(parent)
        self._console = console
        self._host = host
        self._veil = None
        self._app = None
        self._disturb = None
        self._elapsed = 0
        self._phase = "disturb"
        self._home_pos = None        # the host's geometry before we shook it
        self._climb_from = None
        self._climb_to = None
        self._anchor = None          # where he floats about, once he is free
        self._shudder_due = 0.0      # ms accumulator for the slower shake
        self.tear_strength = 0.0     # 0 shut, 1 fully torn (drives the glow)
        self._bubble = None
        self._bubble_until = None    # ms mark (into linger) to stop talking
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._seed = random.randrange(1 << 20)

    # ── lifecycle ────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._timer.isActive() or self._app is not None

    def start(self):
        self._veil = ConsoleVeil(self._console)
        self._veil.place_ghost_low()
        self._veil.show()
        self._veil.raise_()
        if self._host is not None:
            self._disturb = Disturbance(self._host)
            self._disturb.show()
            self._disturb.raise_()
            if not (self._host.isMaximized() or self._host.isFullScreen()):
                # Never move a maximized window (see LESSONS_LEARNED) — when
                # we cannot shake the frame the wash and band carry the beat.
                self._home_pos = self._host.pos()
        self._elapsed = 0
        self._phase = "disturb"
        self._timer.start()

    def _drop_bubble(self):
        if self._bubble is not None:
            try:
                self._bubble.hide()
                self._bubble.deleteLater()
            except RuntimeError:
                pass
            self._bubble = None
        if self._app is not None:
            self._app.companion = None

    def dismiss(self):
        """Idempotent teardown — /clear, a second /seance, or the fade end."""
        self._timer.stop()
        self._restore_host()
        self._drop_bubble()
        for w in (self._veil, self._disturb):
            if w is not None:
                try:
                    w.hide()
                    w.deleteLater()
                except RuntimeError:
                    pass
        self._veil = None
        self._disturb = None
        if self._app is not None:
            try:
                self._app.detach()
                self._app.hide()
                self._app.deleteLater()
            except RuntimeError:
                pass
            self._app = None

    def _settle_host(self):
        """Put the window back where it was, but KEEP the anchor — the
        breakthrough still has a jolt to spend."""
        if self._home_pos is not None and self._host is not None:
            try:
                self._host.move(self._home_pos)
            except RuntimeError:
                pass

    def _restore_host(self):
        self._settle_host()
        self._home_pos = None

    # ── the beats ────────────────────────────────────────────────────────
    def _tick(self):
        self._elapsed += self.TICK_MS
        try:
            handler = getattr(self, "_beat_" + self._phase)
            handler()
        except RuntimeError:
            self.dismiss()          # a widget died under us; leave cleanly

    def _advance(self, nxt: str):
        self._phase = nxt
        self._elapsed = 0

    def _beat_disturb(self):
        t = self._elapsed / self.DISTURB_MS
        if self._disturb is not None:
            self._disturb.sync()
            # three failing pulses, deepening — the last one nearly blacks out
            pulse = abs(math.sin(t * math.pi * 3.0)) ** 2
            self._disturb.dim = pulse * (0.25 + 0.60 * t)
            self._disturb.band_y = (t * 2.4) % 1.0 if t > 0.35 else -1.0
            self._disturb.update()
        self._shudder_due -= self.TICK_MS
        if (self._home_pos is not None and self._host is not None
                and self._shudder_due <= 0):
            self._shudder_due = self.SHUDDER_EVERY_MS
            # amplitude grows with the dread
            amp = int(2 + 7 * t)
            self._host.move(self._home_pos
                            + QPoint(random.randint(-amp, amp),
                                     random.randint(-amp, amp)))
        if self._elapsed >= self.DISTURB_MS:
            self._settle_host()
            self._advance("manifest")

    def _beat_manifest(self):
        t = min(1.0, self._elapsed / self.MANIFEST_MS)
        if self._disturb is not None:
            # the dark holds a moment, then lifts as the shape resolves
            self._disturb.dim = 0.55 * (1.0 - t) ** 1.5
            self._disturb.band_y = -1.0
            self._disturb.update()
        if self._veil is not None:
            self._veil.alpha = t ** 1.4
            self._veil.rows_from = 0
            self._veil.update()
        if self._elapsed >= self.MANIFEST_MS:
            self._begin_emerge()

    def _begin_emerge(self):
        """Hand the surface line to a real window and start the climb."""
        if self._veil is None:
            self.dismiss()
            return
        self._app = Apparition(host=self._host)
        self._app.rows_to = 0
        self._app.move_art_to(self._veil.ghost_global_pos())
        self._app.show()
        self._app.raise_()
        self._climb_from = self._veil.ghost_global_pos()
        # far enough that it ends up clear of the console entirely
        surface = self._veil.surface_global_y()
        self._climb_to = QPoint(self._climb_from.x(),
                                surface - GRID_H * CELL - SIZE_H // 2)
        self._advance("emerge")

    def _beat_emerge(self):
        """One continuous haul upward. Which half owns which row is decided
        by the surface line every frame, so the creature is never in two
        places and never in none."""
        t = min(1.0, self._elapsed / self.EMERGE_MS)
        # heaves, then eases out — smoothstep reads as effort
        ease = t * t * (3.0 - 2.0 * t)
        if self._veil is None or self._app is None or not self._climb_from:
            self.dismiss()
            return

        self._veil._sync_geometry()      # a splitter drag must not strand it
        surface = self._veil.surface_global_y()
        sway = math.sin(t * math.pi * 3.0) * (7.0 * (1.0 - t))
        art = QPoint(
            int(self._climb_from.x() + sway),
            int(self._climb_from.y()
                + (self._climb_to.y() - self._climb_from.y()) * ease),
        )
        # rows that have crossed the surface belong to the free half
        crossed = max(0, min(GRID_H,
                             int(math.ceil((surface - art.y()) / CELL))))

        self._veil.set_ghost_global(art)
        self._veil.rows_from = crossed
        self._veil.alpha = 1.0
        self._veil.update()

        self._app.move_art_to(art)
        self._app.rows_to = crossed
        self._app.update()

        # the tear opens as it breaks through and closes once it is clear
        through = crossed / GRID_H
        self.tear_strength = (
            0.0 if crossed in (0, GRID_H) else math.sin(through * math.pi))
        if self._disturb is not None and self._host is not None:
            self._disturb.sync()
            origin = self._host.mapToGlobal(QPoint(0, 0))
            left = self._veil.mapToGlobal(QPoint(0, 0))
            self._disturb.tear_y = surface - origin.y()
            self._disturb.tear_x0 = left.x() - origin.x()
            self._disturb.tear_x1 = self._disturb.tear_x0 + self._veil.width()
            self._disturb.tear_strength = self.tear_strength
            # the room holds its breath while it is halfway through
            self._disturb.dim = 0.34 * self.tear_strength
            self._disturb.band_y = -1.0
            self._disturb.update()
        self._shudder_due -= self.TICK_MS
        if (self._home_pos is not None and self._host is not None
                and self._shudder_due <= 0):
            self._shudder_due = self.SHUDDER_EVERY_MS
            # a flinch, not the full shudder — the frame reacts to being
            # opened, then settles the instant it is through
            jolt = int(4 * self.tear_strength)
            if jolt:
                self._host.move(self._home_pos
                                + QPoint(random.randint(-jolt, jolt),
                                         random.randint(-jolt, jolt)))
            else:
                self._settle_host()

        if self._elapsed >= self.EMERGE_MS:
            self._veil.hide()
            self._veil.deleteLater()
            self._veil = None
            self._app.rows_to = GRID_H
            self._app.update()
            self.tear_strength = 0.0
            self._anchor = self._climb_to
            self._app.on_shoo = self.banish
            self._settle_host()
            if self._disturb is not None:
                self._disturb.dim = 0.0
                self._disturb.tear_strength = 0.0
                self._disturb.update()
            self._advance("linger")

    @staticmethod
    def _float_offset(t: float):
        """A live, non-repeating drift. Two out-of-phase sines per axis so
        the loop never reads as a loop; the fast pair carries the motion and
        the slow pair wanders the centre so he never traces the same path
        twice. Amplitudes stay small — he is breathing, not bobbing.

        The frequencies are picked, not guessed. Window positions are whole
        pixels, so what the eye reads as judder is how long he SITS on one
        pixel, and that is set by speed, not frame rate: the original curve
        was slow enough to freeze for 1.2s at each turnaround. These four
        were searched for the shortest simultaneous stall on both axes
        (~300ms, at ~12 position changes/sec) — when one axis is turning
        around the other is still travelling, so he never quite stops."""
        return (math.sin(t * 2.4) * 6.0 + math.sin(t * 0.7) * 2.5,
                math.sin(t * 1.6) * 5.0 + math.cos(t * 0.43) * 2.5)

    def _beat_linger(self):
        """Free: he says hello, floats in place, and waits to be picked up.
        No timer takes him away — see banish()."""
        if self._app is None or self._anchor is None:
            return
        dx, dy = self._float_offset(self._elapsed / 1000.0)
        if self._app.dragging:
            # He follows the cursor; re-anchor under him so letting go does
            # not snap the float back to where he was summoned.
            here = self._app.art_global_pos()
            self._anchor = QPoint(int(here.x() - dx), int(here.y() - dy))
            art = here
        else:
            art = QPoint(int(self._anchor.x() + dx), int(self._anchor.y() + dy))
            self._app.move_art_to(art)
        if (self._bubble is None and self._bubble_until is None
                and self._elapsed >= self.GREET_AFTER_MS):
            self._greet(art)
        elif self._bubble is not None:
            if self._elapsed >= self._bubble_until:
                self._drop_bubble()         # said his piece
            elif not self._app.dragging:
                self._place_bubble(art)     # glued, so it drifts with him

    def banish(self):
        """Shoo him away (double-click, and what a caller would use to end
        him politely) — he fades rather than blinking out."""
        if self._phase == "linger":
            self._advance("fade")

    def _greet(self, art: QPoint):
        """Say hello, in the house speech bubble — coloured from the GHOST's
        palette rather than the theme's, because he is deliberately not a
        TechDeck-tinted thing and neither is anything he says."""
        try:
            from techdeck.ui.widgets.moth_widget import SpeechBubble
            self._bubble = SpeechBubble(
                self.GREETING,
                fg=QColor(GHOST_INK),
                bg=QColor(GHOST_PALE),
                frame=QColor(GHOST_OUTLINE),
                corner="bl",
            )
        except Exception:
            self._bubble = None         # never let a flourish break the toy
            return
        if self._app is not None:
            self._app.companion = self._bubble
        # gone once it has been typed out and read
        try:
            typing = self._bubble.type_ms()
        except Exception:
            typing = 300
        self._bubble_until = self._elapsed + typing + self.GREET_READ_MS
        self._place_bubble(art)
        self._bubble.show()
        self._bubble.raise_()

    def _place_bubble(self, art: QPoint):
        """Park it above him with the tail pointing down at his head."""
        if self._bubble is None:
            return
        centre_x = art.x() + (GRID_W * CELL) // 2
        corner = "bl"
        try:
            tip_x, tip_y = self._bubble.tip_offset(corner)
        except Exception:
            tip_x, tip_y = 0, self._bubble.height()
        pos = QPoint(centre_x - tip_x, art.y() - 6 - tip_y)
        if self._host is not None:
            # clamp into the window it haunts, never the screen (a maximized
            # window on a second monitor otherwise flings it off-app)
            top_left = self._host.mapToGlobal(QPoint(0, 0))
            left = top_left.x() + 4
            right = top_left.x() + self._host.width() - self._bubble.width() - 4
            top = top_left.y() + 4
            if right > left:
                pos.setX(max(left, min(pos.x(), right)))
            pos.setY(max(top, pos.y()))
        self._bubble.move(pos)

    def _beat_fade(self):
        t = min(1.0, self._elapsed / self.FADE_MS)
        if self._bubble is not None:
            self._drop_bubble()      # he stops talking before he stops being
        if self._app is not None:
            self._app.alpha = 1.0 - t
            self._app.update()
        if self._elapsed >= self.FADE_MS:
            self.dismiss()
