"""The /seance ritual — TechDeck is disturbed, and something climbs out.

THE EFFECT, and why it is built this way
----------------------------------------
The apparition is drawn from ONE grid by ONE painter, into TWO surfaces:

  ConsoleVeil   a child overlay CLIPPED to the console, painting rows [k:]
                — the part still inside.
  Apparition    a frameless top-level at the IDENTICAL screen rect and cell
                size, painting rows [:k] — the part that is out.

The slices are complementary, so their union is always the whole creature:
nothing ever looks erased, which is the point. What sells "it came OUT" is
that the top-level is not clipped by the console — once it holds every row
it simply floats up across the console's edge and over the app, which the
veil could never do.

Because both halves call the same `paint_ghost` with the same cell size at
the same global rect, the seam is aligned by construction rather than by
tuning: there is no second art asset and no second renderer to drift.

The ritual is four beats:
    disturb   the window shudders and the lights fail (nothing answers yet)
    manifest  the ghost fades up inside the console
    emerge    the complementary hand-off above
    rise      it floats out over the app, bobbing, then fades

Nothing here may ever break the console: the whole thing is a toy, so every
entry point is guarded and `dismiss()` is idempotent.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

# ── the apparition, hand-editable (house style: a glyph grid + a legend) ──
#   .  transparent      H  lit edge (the side the light is on)
#   B  body             S  shaded edge
#   E  void (eyes and mouth — always the darkest thing on screen)
GHOST_ART = [
    "........................",
    "........BBBBBBBB........",
    "......HBBBBBBBBBBB......",
    ".....HHBBBBBBBBBBBS.....",
    "....HHHBBBBBBBBBBBSS....",
    "...HHHHBBBBBBBBBBBSSS...",
    "...HHHHBBBBBBBBBBBSSS...",
    "..HHHHHEBBBBBBBBEBSSSS..",
    "..HHHHEEEBBBBBBEEESSSS..",
    "..HHHHEEEBBBBBBEEESSSS..",
    "..HHHHEEEBBBBBBEEESSSS..",
    "..HHHHHEBBBBBBBBEBSSSS..",
    "..HHHHHBBBBBBBBBBBSSSS..",
    "..HHHHHBBBBEEBBBBBSSSS..",
    "..HHHHHBBBEEEEBBBBSSSS..",
    "..HHHHHBBBEEEEBBBBSSSS..",
    "..HHHHHBBBBEEBBBBBSSSS..",
    "..HHHHHBBBBBBBBBBBSSSS..",
    "..HHHHHBBBBBBBBBBBSSSS..",
    "..HHHHHBBBBBBBBBBBSSSS..",
    "..HHHHHBBBBBBBBBBBSSSS..",
    "....HHHB..BBBB..BBSS....",
    "....HHH...BBBB...BSS....",
    "....HHH....BB....BSS....",
    ".....H.....BB.....S.....",
]

# Spectral, and deliberately NOT theme-tinted: it must read as a foreign
# thing on both the near-black console and the bright app behind it.
GHOST_TONES = {
    "H": QColor("#EAF6FF"),
    "B": QColor("#BFD8EC"),
    "S": QColor("#7E9CBB"),
    "E": QColor("#101A26"),
}
GHOST_OUTLINE = QColor("#0A1018")

GRID_W = len(GHOST_ART[0])
GRID_H = len(GHOST_ART)
CELL = 5                     # px per art cell — both halves MUST share this
MARGIN = 1                   # a cell of slack so the outline never clips
SIZE_W = (GRID_W + 2 * MARGIN) * CELL
SIZE_H = (GRID_H + 2 * MARGIN) * CELL

_SOLID = set("HBSE")


def _outline_cells():
    """Transparent cells that touch the silhouette — traced once, so the
    ghost keeps a dark edge against the bright app behind it."""
    edge = set()
    for r, row in enumerate(GHOST_ART):
        for c, ch in enumerate(row):
            if ch in _SOLID:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < GRID_H and 0 <= cc < GRID_W:
                    if GHOST_ART[rr][cc] in _SOLID:
                        edge.add((r, c))
                        break
    return frozenset(edge)


OUTLINE_CELLS = _outline_cells()


def paint_ghost(painter: QPainter, row_from: int, row_to: int,
                alpha: float = 1.0, origin: QPoint | None = None):
    """Paint art rows [row_from, row_to) at `origin`, `alpha` 0..1.

    THE seam guarantee: the veil and the apparition both call this, with
    complementary row ranges, at the same origin and CELL. A cell belongs to
    exactly one of the two ranges, so the union is the whole ghost and the
    join is invisible — including the traced outline, which is filtered by
    row here rather than recomputed per surface.
    """
    if alpha <= 0.0:
        return
    origin = origin or QPoint(MARGIN * CELL, MARGIN * CELL)
    lo = max(0, row_from)
    hi = min(GRID_H, row_to)
    painter.setPen(Qt.PenStyle.NoPen)

    for r in range(lo, hi):
        for c in range(GRID_W):
            ch = GHOST_ART[r][c]
            if ch in _SOLID:
                colour = QColor(GHOST_TONES[ch])
            elif (r, c) in OUTLINE_CELLS:
                colour = QColor(GHOST_OUTLINE)
            else:
                continue
            colour.setAlphaF(colour.alphaF() * alpha)
            painter.fillRect(origin.x() + c * CELL, origin.y() + r * CELL,
                             CELL, CELL, colour)


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

    def centre_ghost(self):
        """Park the ghost mid-console — fully inside, so it manifests as a
        whole creature rather than something already half-escaped."""
        self._sync_geometry()
        self.ghost_pos = QPoint(
            (self.width() - GRID_W * CELL) // 2,
            (self.height() - GRID_H * CELL) // 2,
        )

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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(SIZE_W, SIZE_H)
        self.rows_to = 0
        self.alpha = 1.0
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
        if obj is self._host:
            et = event.type()
            if et == QEvent.Type.Move and self._host_pos is not None:
                new = self._host.frameGeometry().topLeft()
                delta = new - self._host_pos
                self._host_pos = new
                if not delta.isNull():
                    self.move(self.pos() + delta)
            elif et == QEvent.Type.WindowStateChange:
                self.setVisible(not self._host.isMinimized())
            elif et == QEvent.Type.Hide:
                self.hide()
        return super().eventFilter(obj, event)

    def detach(self):
        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except RuntimeError:
                pass
            self._host = None

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
        self.sync()

    def sync(self):
        self.setGeometry(self._host.rect())

    def paintEvent(self, event):
        if self.dim <= 0.0 and self.band_y < 0:
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
        painter.end()


class SeanceRitual(QObject):
    """Drives the four beats and owns every widget the ritual creates."""

    TICK_MS = 33
    DISTURB_MS = 2000
    MANIFEST_MS = 1700
    EMERGE_MS = 1500
    RISE_MS = 1700
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
        self._rise_from = None
        self._rise_to = None
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
        self._veil.centre_ghost()
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

    def dismiss(self):
        """Idempotent teardown — /clear, a second /seance, or the fade end."""
        self._timer.stop()
        self._restore_host()
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

    def _restore_host(self):
        if self._home_pos is not None and self._host is not None:
            try:
                self._host.move(self._home_pos)
            except RuntimeError:
                pass
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
        if self._home_pos is not None and self._host is not None:
            # amplitude grows with the dread
            amp = int(2 + 7 * t)
            self._host.move(self._home_pos
                            + QPoint(random.randint(-amp, amp),
                                     random.randint(-amp, amp)))
        if self._elapsed >= self.DISTURB_MS:
            self._restore_host()
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
        """Hand the top rows over to a real window, pinned to the same rect."""
        if self._veil is None:
            self.dismiss()
            return
        self._app = Apparition(host=self._host)
        self._app.rows_to = 0
        self._app.move_art_to(self._veil.ghost_global_pos())
        self._app.show()
        self._app.raise_()
        self._advance("emerge")

    def _beat_emerge(self):
        t = min(1.0, self._elapsed / self.EMERGE_MS)
        k = int(round(t * GRID_H))
        if self._veil is not None:
            self._veil.rows_from = k       # keeps rows [k:] …
            self._veil.alpha = 1.0
            self._veil.update()
        if self._app is not None:
            self._app.rows_to = k          # … and this takes rows [:k]
            self._app.update()
        if self._elapsed >= self.EMERGE_MS:
            # the console's half is spent; only the free thing remains
            if self._veil is not None:
                self._veil.hide()
                self._veil.deleteLater()
                self._veil = None
            self._start_rise()

    def _start_rise(self):
        if self._app is None:
            self.dismiss()
            return
        self._app.rows_to = GRID_H
        start = self._app.art_global_pos()
        self._rise_from = start
        # up and out: clear of the console, into the app it was called from
        climb = SIZE_H * 2 + (self._console.height() // 3 if self._console else 0)
        self._rise_to = QPoint(start.x(), start.y() - climb)
        self._advance("rise")

    def _beat_rise(self):
        t = min(1.0, self._elapsed / self.RISE_MS)
        ease = 1.0 - (1.0 - t) ** 2            # decelerating climb
        if self._app is not None and self._rise_from and self._rise_to:
            x = self._rise_from.x() + math.sin(t * math.pi * 2.0) * 9
            y = (self._rise_from.y()
                 + (self._rise_to.y() - self._rise_from.y()) * ease)
            self._app.move_art_to(QPoint(int(x), int(y)))
        if self._elapsed >= self.RISE_MS:
            self._advance("linger")

    def _beat_linger(self):
        """Free: it bobs where it surfaced until it loses interest."""
        if self._app is not None and self._rise_to is not None:
            t = self._elapsed / 1000.0
            self._app.move_art_to(QPoint(
                int(self._rise_to.x() + math.sin(t * 1.1) * 14),
                int(self._rise_to.y() + math.sin(t * 0.7) * 8)))
        if self._elapsed >= self.LINGER_MS:
            self._advance("fade")

    def _beat_fade(self):
        t = min(1.0, self._elapsed / self.FADE_MS)
        if self._app is not None:
            self._app.alpha = 1.0 - t
            self._app.update()
        if self._elapsed >= self.FADE_MS:
            self.dismiss()
