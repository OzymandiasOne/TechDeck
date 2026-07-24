"""Chopper-gunner folder picker — 922 Setup's batch-folder prompt.

A non-native QFileDialog (Directory mode, so it themes with TechDeck) plus a
full-screen, click-through, always-on-top overlay that plays the MW2
chopper-gunner fantasy around it:

* crosshair cursor + AC-130 HUD dressing (compass strip, corner brackets,
  status callouts) while the dialog is open
* clicking a folder row locks on — designator brackets converge onto the row
* accepting the dialog FIRES: recoil shake, ~1 s of shell flight, then a
  slow-motion debris burst (840 tumbling fragments w/ smoke trails + dust
  haze) centred on the locked row, followed by a full-feed "transmission
  knocked out" static flicker — and only then does the dialog close and the
  picked path return
* any key skips the sequence; Cancel/Esc never triggers it

Everything is drawn on the overlay — the real dialog is only moved a few px
(shake/jitter) and has its window opacity flickered; no UI is repainted or
distorted. All effect timings run through DT (slow-motion factor) exactly as
locked in the approved HTML mockup (see docs/PLUGINS.md, 922 Setup).

Entry point: :func:`pick_folder_chopper` (GUI thread only). Reached via
``sdk.request_directory(..., style="chopper_gunner")`` →
``console.request_directory`` → ``console._directory_gui``, which gates on
the professional theme (native dialog instead) and falls back to the native
dialog on ANY failure here — the toy must never block a 922 run.
"""

import math
import random

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QListView, QWidget
from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap,
    QRadialGradient,
)

# Slow-motion factor locked in the mockup: same trajectories, ~55% speed,
# lifetimes stretched by 1/DT so total travel is unchanged.
DT = 0.55

_HUD = QColor(232, 237, 232)
_RANGE = QColor(227, 216, 74)        # rangefinder yellow
_TARGET = QColor(224, 72, 60)        # designator red
_TICK_MS = 16                        # ~60 fps during the fire sequence
_AIM_TICK_MS = 33                    # lighter cadence while just aiming

# Fire-sequence beat timings (ms). Flight is real time; the burst plays in
# slow motion (1/DT). The transmission glitch fires WITH the detonation and
# lasts _KNOCKOUT_TICKS frames, overlapping the front of the debris burst.
_FLIGHT_MS = 1000
_KNOCKOUT_TICKS = 45
_SHAKE_MS = 350
_AAR_MS = 1500         # "TARGET NEUTRALIZED" after-action hold before the close
_CRT_MS = 480          # CRT power-off collapse when the picker closes


class _SkipFilter(QObject):
    """App-level filter active only while the kill-cam runs: any key skips
    (the dialog itself is disabled then, so it can't receive keys), and
    stray clicks are swallowed so nothing lands mid-sequence."""

    def __init__(self, overlay):
        super().__init__()
        self._overlay = overlay

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.KeyPress:
            self._overlay.skip()
            return True
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return True
        return False


def _crosshair_cursor() -> QCursor:
    """The MW2-style reticle cursor: cross with a centre gap + tiny x,
    white with a 1px dark halo so it reads on light rows too."""
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    c = size // 2
    for color, w in ((QColor(10, 12, 10, 200), 3), (_HUD, 1.5)):
        pen = QPen(color)
        pen.setWidthF(w)
        p.setPen(pen)
        gap = 4
        p.drawLine(c, 2, c, c - gap)
        p.drawLine(c, c + gap, c, size - 3)
        p.drawLine(2, c, c - gap, c)
        p.drawLine(c + gap, c, size - 3, c)
    p.end()
    return QCursor(pm, c, c)


def _grain_tiles(count: int = 8, w: int = 640, h: int = 360) -> list:
    """Pre-render a handful of grey-noise tiles once; the paint loop cycles
    them scaled to full screen for the always-on 'thermal feed' film grain
    (the persistent grey static veil from the mockup). Cheap: one scaled
    blit per frame instead of per-pixel noise every frame."""
    import os
    tiles = []
    for _ in range(count):
        buf = os.urandom(w * h)     # w*h random grey bytes
        img = QImage(bytes(buf), w, h, w,
                     QImage.Format.Format_Grayscale8).copy()  # detach from buf
        tiles.append(QPixmap.fromImage(img))
    return tiles


def _smoke_sprite() -> QPixmap:
    """One pre-rendered soft blob, stamped for every smoke-trail dot."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    g = QRadialGradient(16, 16, 16)
    g.setColorAt(0.0, QColor(188, 195, 188, 128))
    g.setColorAt(1.0, QColor(188, 195, 188, 0))
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRect(0, 0, 32, 32)
    p.end()
    return pm


class GunnerOverlay(QWidget):
    """Full-screen, input-transparent overlay: HUD + lock-on + kill-cam FX.

    States: 'aim' (HUD + lock brackets tracking the dialog selection) →
    'flight' (recoil fired, shell in the air) → 'burst' (debris/smoke/dust
    physics; knockout scheduled) → 'knockout' (static flicker) → done
    callback. All coordinates are overlay-local (map global rects with
    :meth:`map_rect`).
    """

    def __init__(self, dialog: QDialog, screen_geo: QRect):
        # Parent to the dialog: an OWNED tool window stays above its owner in
        # z-order automatically, so the HUD/FX composite ABOVE the modal
        # QFileDialog (a sibling top-level would render BEHIND it — the bug
        # that made the effect invisible in the real modal-exec path).
        super().__init__(dialog)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setGeometry(screen_geo)

        self._dialog = dialog
        self._dialog_home = None       # original pos, restored after shakes
        self._state = "aim"
        self._on_done = None
        self._elapsed = 0.0            # ms in current state
        self._callout = "DESIGNATE TARGET FOLDER"
        self._callout_alert = False

        # Lock-on box (overlay-local QRectF or None) + convergence animation.
        self._lock_rect = None
        self._lock_from = None
        self._lock_anim = 1.0          # 0→1 convergence progress
        self._lock_solid = False
        self._confirm_ticks = 0        # brief lock flicker when a folder is clicked

        # FX particle state (ported 1:1 from the approved mockup).
        self._parts: list = []
        self._smoke: list = []
        self._puffs: list = []
        self._impact = QPointF()
        self._flash = 0.0              # white flash alpha
        self._knock_ticks = 0
        self._knock_pending = False
        self._smoke_pm = _smoke_sprite()
        self._grain = _grain_tiles()   # always-on grey film-grain veil
        self._mono = QFont("Consolas", 10)
        self._ambient = None           # (player, audio_out) for the looping bed
        self._lock_sfx_done = False    # lock-on sound fires once per acquisition
        self._crt_cb = None            # callback to run when the CRT close ends
        self._aar_path = ""            # picked path, shown on the TARGET NEUTRALIZED screen
        self._t0 = 0.0                 # ms since burst began (for puffs)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_AIM_TICK_MS)

    # ── audio (never allowed to break the picker) ────────────────────────

    def _sfx(self, sound_id: str):
        """Fire a one-shot picker sound; silent no-op on any failure."""
        try:
            from techdeck.core.audio_manager import get_audio_manager
            get_audio_manager().play(sound_id)
        except Exception:
            pass

    def start_ambient(self):
        """Begin the looping gunship-interior bed at half volume (the user's
        '50% quieter' ask). Called from pick_folder_chopper, not __init__, so
        headless sequence tests never spin up the mp3 loop."""
        try:
            from techdeck.core.audio_manager import (
                get_audio_manager, SOUND_CHOPPER_AMBIENT,
            )
            self._ambient = get_audio_manager().play_loop_effect(
                SOUND_CHOPPER_AMBIENT, volume_scale=0.5)
        except Exception:
            self._ambient = None

    def stop_ambient(self):
        """Stop the ambient bed (idempotent; safe to call more than once)."""
        amb, self._ambient = self._ambient, None
        if amb is not None:
            try:
                amb.stop()
            except Exception:
                pass

    # ── public API (driven by the dialog) ────────────────────────────────

    def map_rect(self, global_rect: QRect) -> QRectF:
        o = self.geometry().topLeft()
        return QRectF(global_rect.translated(-o.x(), -o.y()))

    def set_lock(self, rect: QRectF, name: str):
        """A folder row was designated: converge the lock brackets onto it."""
        if self._state != "aim":
            return
        self._lock_from = rect.adjusted(-80, -60, 80, 60)
        self._lock_rect = rect.adjusted(-8, -6, 8, 6)
        self._lock_anim = 0.0
        self._lock_solid = False
        self._lock_sfx_done = False
        self._callout, self._callout_alert = "ACQUIRING…", True
        self._lock_name = name

    def clear_lock(self):
        self._lock_rect = None
        if self._state == "aim":
            self._callout, self._callout_alert = "DESIGNATE TARGET FOLDER", False

    def confirm_lock(self):
        """Explicit click committed this folder — flicker the lock brackets and
        upgrade the callout to TARGET CONFIRMED (a transient flash over the
        existing lock, not a change to its steady look)."""
        if self._lock_rect is None:
            return
        self._lock_anim = 1.0
        self._lock_solid = True
        self._confirm_ticks = 12       # ~0.4s of blink at the aim cadence
        self._callout = f"TARGET CONFIRMED — {getattr(self, '_lock_name', '')}"
        self._callout_alert = False

    def fire(self, on_done):
        """Accept pressed with a lock: recoil now, impact after the flight."""
        self._on_done = on_done
        self._state = "flight"
        self._elapsed = 0.0
        self._callout, self._callout_alert = "FIRING SOLUTION LOCKED", True
        self._dialog_home = self._dialog.pos()
        self._skip_filter = _SkipFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._skip_filter)
        self._shake(self._dialog, 7)   # recoil
        from techdeck.core.audio_manager import SOUND_CHOPPER_FIRE
        self._sfx(SOUND_CHOPPER_FIRE)  # railgun shot
        self._timer.start(_TICK_MS)

    def skip(self):
        """Any key mid-sequence: jump straight to the end, restore, finish."""
        if self._state in ("flight", "burst"):
            self._parts, self._smoke, self._puffs = [], [], []
            self._knock_ticks, self._flash = 0, 0.0
            self._finish(aar=False)   # skipped: go straight to the CRT close

    # ── state machine ────────────────────────────────────────────────────

    def _tick(self):
        # Keep the overlay above the modal dialog every frame — parent
        # ownership alone doesn't reliably win z-order on Windows once the
        # dialog is interacted with, and raise_() on an already-top window
        # is cheap (no visible flicker since the frame recomposites anyway).
        self.raise_()
        dt_ms = self._timer.interval()
        self._elapsed += dt_ms
        if self._confirm_ticks > 0:
            self._confirm_ticks -= 1

        if self._state == "flight":
            if self._elapsed >= 350 and self._callout != "ROUND AWAY":
                self._callout = "ROUND AWAY"
            if self._elapsed >= _FLIGHT_MS:
                self._begin_burst()
        elif self._state == "burst":
            self._step_particles()
            if self._flash > 0:
                self._flash = max(0.0, self._flash - dt_ms / 220.0 * 0.8)
            # Transmission glitch runs concurrently with the detonation, then
            # the feed restores and the debris keeps settling underneath.
            if self._knock_ticks > 0:
                self._knock_tick()
            # As soon as the glitch ends, go to the after-action screen — the
            # static's last frames mask the debris, so no dead pause waiting
            # for every fragment to settle.
            if self._knock_ticks <= 0:
                self._finish()
        elif self._state == "aar":
            if self._elapsed >= _AAR_MS:
                self._state = "crt"      # after-action hold done → CRT power-off
                self._elapsed = 0.0
        elif self._state == "crt":
            if self._elapsed >= _CRT_MS:
                self._end_crt()
        self.update()

    def _begin_burst(self):
        self._state = "burst"
        self._elapsed = 0.0
        self._t0 = 0.0
        self._flash = 0.8
        self._knock_ticks = _KNOCKOUT_TICKS   # glitch fires WITH the impact
        from techdeck.core.audio_manager import SOUND_CHOPPER_IMPACT
        self._sfx(SOUND_CHOPPER_IMPACT)  # detonation on the folder
        self._callout, self._callout_alert = "IMPACT CONFIRMED", True
        x, y = self._impact.x(), self._impact.y()
        # ~840 fine tumbling fragments (1–2 px) flung far enough to cross the
        # window; a vertical z-axis pop scales them toward the camera.
        for _ in range(840):
            a = random.random() * math.tau
            life = int((40 + random.random() * 40) / DT)
            w = 1 + random.random()
            self._parts.append({
                "cx": x, "cy": y, "ang": a,
                "r": 4 + random.random() * 10, "vr": 9 + random.random() * 22,
                "z": 0.0, "vz": 3 + random.random() * 9,
                "w": w, "h": w * (0.45 + random.random() * 0.8),
                "rot": random.random() * 180.0,
                "vrot": (random.random() - 0.5) * 28.6,   # deg/tick ≈ mockup rad
                "life": life, "max": life,
                "warm": random.random() < 0.3,
            })
        # Dirt/dust haze under the fragments.
        for i in range(8):
            a = random.random() * math.tau
            d = random.random() * 55
            self._puffs.append({
                "x": x + math.cos(a) * d, "y": y + math.sin(a) * d * 0.5,
                "r0": 14.0, "r1": 70 + random.random() * 90,
                "a0": 0.10 + random.random() * 0.07,
                "start": i * 70 / DT, "dur": (850 + random.random() * 550) / DT,
            })
        self._shake(self._dialog, 7)

    def _step_particles(self):
        self._t0 += self._timer.interval()
        drag = 0.96 ** DT
        alive = []
        for pt in self._parts:
            pt["life"] -= 1
            if pt["life"] <= 0:
                continue
            pt["vr"] *= drag
            pt["r"] += pt["vr"] * DT
            pt["vz"] -= 0.35 * DT
            pt["z"] += pt["vz"] * DT
            if pt["z"] < 0:            # hits the deck, skids
                pt["z"] = 0.0
                pt["vz"] *= -0.35
                pt["vr"] *= 0.7
            pt["rot"] += pt["vrot"] * DT
            t = pt["life"] / pt["max"]
            # Shed a smoke dot behind this fragment while it's hot.
            if t > 0.3 and len(self._smoke) < 5200 and random.random() < 0.08:
                sc = min(2.6, 1 + pt["z"] * 0.012)
                sx = pt["cx"] + math.cos(pt["ang"]) * pt["r"]
                sy = pt["cy"] + math.sin(pt["ang"]) * pt["r"] * 0.6 - pt["z"]
                self._smoke.append({
                    "x": sx, "y": sy,
                    "s": (3.5 + random.random() * 5) * sc,
                    "a": 0.22 + random.random() * 0.12,
                })
            alive.append(pt)
        self._parts = alive
        # Smoke: swell, drift up, thin out slowly (long linger).
        kept = []
        for sm in self._smoke:
            sm["s"] += 0.3 * DT
            sm["a"] -= 0.006 * DT
            sm["y"] -= 0.15 * DT
            if sm["a"] > 0:
                kept.append(sm)
        self._smoke = kept

    def _knock_tick(self):
        self._knock_ticks -= 1
        dlg = self._dialog
        if random.random() < 0.24:     # hard dropout frame
            dlg.setWindowOpacity(0.0)
        else:
            dlg.setWindowOpacity(0.0 if random.random() < 0.45
                                 else 0.25 + random.random() * 0.75)
        if self._dialog_home is not None:
            jx = int(random.random() * 28 - 14)
            dlg.move(self._dialog_home.x() + jx, self._dialog_home.y())

    def _shake(self, dlg, amp: int):
        """Brief window shake around the dialog's home position."""
        home = self._dialog_home or dlg.pos()
        steps = [(-amp, amp // 2), (amp - 1, -amp + 2), (-amp // 2, -amp // 2),
                 (amp // 2, amp // 2), (-amp // 3, amp // 3), (0, 0)]
        for i, (dx, dy) in enumerate(steps):
            QTimer.singleShot(int(i * _SHAKE_MS / len(steps)),
                              lambda dx=dx, dy=dy: dlg.move(home.x() + dx,
                                                            home.y() + dy))

    def _finish(self, aar: bool = True):
        if self._on_done is None:
            return
        cb, self._on_done = self._on_done, None
        self.stop_ambient()
        flt = getattr(self, "_skip_filter", None)
        if flt is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(flt)
            self._skip_filter = None
        self._crt_cb = cb
        self._elapsed = 0.0
        self._parts, self._smoke, self._puffs = [], [], []   # burst is over
        # Dialog dissolves into the static feed; the sequence then holds on the
        # "TARGET NEUTRALIZED" after-action screen (unless skipped) before the
        # CRT power-off collapses it and the path returns.
        self._dialog.setWindowOpacity(0.0)
        if aar:
            self._callout, self._callout_alert = "TRANSMISSION RESTORED", False
            self._state = "aar"
        else:
            self._state = "crt"
        self.update()

    def _end_crt(self):
        """CRT collapse finished — hand the picked path back (closes dialog)."""
        cb, self._crt_cb = getattr(self, "_crt_cb", None), None
        self._state = "done"
        if cb is not None:
            cb()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        if self._state == "aar":
            self._paint_aar(p, w, h)
            p.end()
            return
        if self._state == "crt":
            self._paint_crt(p, w, h)
            p.end()
            return

        if self._state != "done":
            self._paint_hud(p, w, h)
        if self._state == "aim" and self._lock_rect is not None:
            self._paint_lock(p)
        if self._state in ("flight", "burst") and self._lock_rect is not None:
            self._paint_lock(p, frozen=True)
        if self._state == "burst":
            self._paint_fx(p)
        if self._state != "done":
            # Persistent grey film grain over the whole feed (incl. the dialog),
            # a fresh random tile each frame so it crawls like real static.
            p.setOpacity(0.10)
            p.drawPixmap(self.rect(), random.choice(self._grain))
            p.setOpacity(1.0)
        if self._knock_ticks > 0:
            self._paint_static(p, w, h)
        if self._flash > 0:
            p.fillRect(self.rect(), QColor(255, 255, 255,
                                           int(self._flash * 255)))
        p.end()

    def _paint_hud(self, p: QPainter, w: int, h: int):
        p.setFont(self._mono)
        hud_pen = QPen(_HUD)
        hud_pen.setWidthF(2)
        p.setPen(hud_pen)
        # Corner brackets
        s, m = 46, 56
        for (cx, cy, sx, sy) in ((m, m, 1, 1), (w - m, m, -1, 1),
                                 (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(cx, cy, cx + s * sx, cy)
            p.drawLine(cx, cy, cx, cy + s * sy)
        # Compass tick strip (subtle sway while aiming)
        sway = math.sin(self._elapsed / 1400.0) * 10 if self._state == "aim" else 0
        cx0 = w / 2 - 260 + sway
        thin = QPen(_HUD)
        thin.setWidthF(1)
        p.setPen(thin)
        for i in range(44):
            x = cx0 + i * 12
            tall = 14 if i % 5 == 0 else 8
            p.drawLine(int(x), 18, int(x), 18 + tall)
        # Status callout
        p.setPen(_TARGET if self._callout_alert else _RANGE)
        f = QFont(self._mono)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        p.setFont(f)
        p.drawText(QRectF(0, 52, w, 24), Qt.AlignmentFlag.AlignHCenter,
                   self._callout)
        # Bottom-right ammo block
        p.setPen(_HUD)
        p.setFont(self._mono)
        p.drawText(QRectF(0, h - 74, w - 40, 40),
                   Qt.AlignmentFlag.AlignRight,
                   "RAILGUN CHARGED\nROUNDS ∞")

    def _paint_lock(self, p: QPainter, frozen: bool = False):
        # Converge from the wide box to the tight one with a hint of overshoot.
        if not frozen and self._lock_anim < 1.0:
            self._lock_anim = min(1.0, self._lock_anim + 0.09)
            if self._lock_anim >= 1.0 and not self._lock_solid:
                self._lock_solid = True
                self._callout = f"TARGET LOCKED — {self._lock_name}"
                self._callout_alert = False
                if not self._lock_sfx_done:
                    self._lock_sfx_done = True
                    from techdeck.core.audio_manager import SOUND_CHOPPER_LOCK
                    self._sfx(SOUND_CHOPPER_LOCK)
        a, b = self._lock_from, self._lock_rect
        if a is None or b is None:
            return
        t = self._lock_anim
        ease = 1 - (1 - t) ** 3
        r = QRectF(a.x() + (b.x() - a.x()) * ease,
                   a.y() + (b.y() - a.y()) * ease,
                   a.width() + (b.width() - a.width()) * ease,
                   a.height() + (b.height() - a.height()) * ease)
        # Commit flicker: on the "on" phase of the blink, flash the brackets
        # bright white and thicker; between phases they read as the normal lock.
        flashing = self._confirm_ticks > 0 and (self._confirm_ticks // 2) % 2 == 1
        if flashing:
            pen = QPen(QColor(255, 255, 255))
            pen.setWidthF(4.0)
        else:
            pen = QPen(_RANGE if self._lock_solid else _TARGET)
            pen.setWidthF(2.5)
        p.setPen(pen)
        s = 18 if flashing else 15
        for (cx, cy, sx, sy) in (
                (r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(QPointF(cx, cy), QPointF(cx + s * sx, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + s * sy))
        p.setFont(self._mono)
        p.drawText(QPointF(r.left(), r.top() - 6),
                   "CONFIRMED" if self._confirm_ticks > 0 else "LOCK")

    def _paint_fx(self, p: QPainter):
        # Dust puffs (under everything)
        for pf in self._puffs:
            t = (self._t0 - pf["start"]) / pf["dur"]
            if t <= 0 or t >= 1:
                continue
            rad = pf["r0"] + (pf["r1"] - pf["r0"]) * math.sqrt(t)
            g = QRadialGradient(pf["x"], pf["y"], rad)
            col = QColor(198, 205, 197, int((1 - t) * pf["a0"] * 255))
            g.setColorAt(0.15, col)
            g.setColorAt(1.0, QColor(198, 205, 197, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(pf["x"], pf["y"]), rad, rad * 0.55)
        self._puffs = [pf for pf in self._puffs
                       if (self._t0 - pf["start"]) < pf["dur"]]
        # Smoke trail dots
        for sm in self._smoke:
            p.setOpacity(sm["a"])
            s = sm["s"]
            p.drawPixmap(QRectF(sm["x"] - s / 2, sm["y"] - s / 2, s, s),
                         self._smoke_pm, QRectF(0, 0, 32, 32))
        p.setOpacity(1.0)
        # Debris fragments (over the smoke)
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._parts:
            t = pt["life"] / pt["max"]
            alpha = min(1.0, t * 1.6)
            sc = min(2.6, 1 + pt["z"] * 0.012)
            sx = pt["cx"] + math.cos(pt["ang"]) * pt["r"]
            sy = pt["cy"] + math.sin(pt["ang"]) * pt["r"] * 0.6 - pt["z"]
            if t > 0.7:
                col = QColor(255, 255, 255)
            elif t > 0.4:
                col = QColor(227, 216, 74) if pt["warm"] \
                    else QColor(225, 231, 224)
            else:
                col = QColor(165, 172, 165)
            col.setAlphaF(alpha)
            p.save()
            p.translate(sx, sy)
            p.rotate(pt["rot"])
            p.fillRect(QRectF(-pt["w"] * sc / 2, -pt["h"] * sc / 2,
                              pt["w"] * sc, pt["h"] * sc), col)
            p.restore()

    def _paint_static(self, p: QPainter, w: int, h: int):
        if random.random() < 0.24:     # hard dropout: black frame + SIGNAL LOST
            p.fillRect(self.rect(), QColor(0, 0, 0, 240))
            if random.random() < 0.65:
                f = QFont(self._mono)
                f.setPointSize(14)
                f.setBold(True)
                f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
                p.setFont(f)
                p.setPen(_HUD)
                p.drawText(QRectF(0, h / 2 - 20, w, 40),
                           Qt.AlignmentFlag.AlignCenter, "SIGNAL LOST")
                pen = QPen(QColor(232, 237, 232, 128))
                pen.setWidthF(1)
                p.setPen(pen)
                p.drawRect(QRectF(w / 2 - 170, h / 2 - 26, 340, 52))
            return
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(11):            # full-feed noise bands
            bh = 6 + random.random() * 44
            by = random.random() * h
            g = int(140 + random.random() * 115)
            p.fillRect(QRectF(0, by, w, bh),
                       QColor(g, 255, g, int((0.12 + random.random() * 0.34) * 255)))
        for _ in range(3):             # horizontal tears
            ty = random.random() * h
            th = 4 + random.random() * 18
            p.fillRect(QRectF(0, ty, w, th), QColor(0, 0, 0, 217))
            p.fillRect(QRectF(random.random() * 120 - 60, ty, w, 1.5),
                       QColor(255, 255, 255, 140))

    def _paint_aar(self, p: QPainter, w: int, h: int):
        """After-action screen: the dialog has dissolved into a dark static
        feed; show the HUD dressing + 'TARGET NEUTRALIZED' and the picked
        path, mirroring the mockup, before the CRT power-off."""
        p.fillRect(self.rect(), QColor(6, 8, 6))            # dark feed
        p.setOpacity(0.16)                                  # grainy static bed
        p.drawPixmap(self.rect(), random.choice(self._grain))
        p.setOpacity(1.0)
        self._paint_hud(p, w, h)
        cy = h / 2.0
        a = min(1.0, self._elapsed / 220.0)                 # fade the readout in
        big = QFont(self._mono)
        big.setPointSize(22)
        big.setBold(True)
        big.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 9.0)
        p.setFont(big)
        col = QColor(_RANGE)
        col.setAlphaF(a)
        p.setPen(col)
        p.drawText(QRectF(0, cy - 46, w, 44),
                   Qt.AlignmentFlag.AlignHCenter, "TARGET NEUTRALIZED")
        sub = QFont(self._mono)
        sub.setPointSize(11)
        sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        p.setFont(sub)
        col2 = QColor(_HUD)
        col2.setAlphaF(a * 0.85)
        p.setPen(col2)
        raw = (self._aar_path or "").replace("/", "\\")
        parts = [x for x in raw.split("\\") if x]
        disp = ("...\\" + "\\".join(parts[-3:])) if len(parts) > 3 else raw
        p.drawText(QRectF(0, cy + 6, w, 24),
                   Qt.AlignmentFlag.AlignHCenter, f"PATH ACQUIRED    {disp}")

    def _paint_crt(self, p: QPainter, w: int, h: int):
        """Old-CRT power-off: the feed snaps to a bright horizontal line, that
        line collapses to a central dot, and the dot flashes out to black."""
        p.fillRect(self.rect(), QColor(0, 0, 0))
        t = min(1.0, self._elapsed / _CRT_MS)
        cx, cy = w / 2.0, h / 2.0
        white = QColor(236, 246, 255)
        if t < 0.42:                       # vertical collapse → a thin line
            a = t / 0.42
            bar_h = max(3.0, (1.0 - a) ** 1.5 * h)
            glow = QLinearGradient(0, cy - bar_h, 0, cy + bar_h)
            glow.setColorAt(0.0, QColor(236, 246, 255, 0))
            glow.setColorAt(0.5, QColor(236, 246, 255, 90))
            glow.setColorAt(1.0, QColor(236, 246, 255, 0))
            p.fillRect(QRectF(0, cy - bar_h, w, bar_h * 2), glow)
            p.fillRect(QRectF(0, cy - bar_h / 2, w, bar_h), white)
        elif t < 0.85:                     # horizontal collapse → a dot
            a = (t - 0.42) / 0.43
            bar_w = max(4.0, (1.0 - a) ** 1.7 * w)
            p.fillRect(QRectF(cx - bar_w / 2, cy - 1.5, bar_w, 3.0), white)
        else:                              # dot flash, then black
            a = (t - 0.85) / 0.15
            r = 3.0 * (1.0 - a) + 1.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(255 * (1.0 - a))))
            p.drawEllipse(QPointF(cx, cy), r, r)


class _ChopperDialog(QFileDialog):
    """Non-native directory picker that fires the kill-cam before accepting."""

    def __init__(self, parent, title: str, start_dir: str):
        super().__init__(parent, title, start_dir or "")
        self.setFileMode(QFileDialog.FileMode.Directory)
        self.setOptions(QFileDialog.Option.DontUseNativeDialog
                        | QFileDialog.Option.ShowDirsOnly)
        self.setViewMode(QFileDialog.ViewMode.List)
        self.setLabelText(QFileDialog.DialogLabel.Accept, "Execute")
        self.setCursor(_crosshair_cursor())
        self._overlay = None
        self._sequence_done = False
        self._firing = False
        self._committed = False   # True once a folder is clicked: hover stops moving the lock

    def attach_overlay(self, overlay: GunnerOverlay):
        self._overlay = overlay
        view = self.findChild(QListView, "listView")
        if view is not None:
            # Auto-target on hover: sweeping the crosshair over a folder row
            # selects it (which drives the lock-on), so you designate by
            # pointing, not just clicking. Needs mouse tracking for `entered`.
            view.setMouseTracking(True)
            view.viewport().setMouseTracking(True)
            view.entered.connect(self._on_hover)
            view.clicked.connect(self._on_click)   # a click pins the lock
            sel = view.selectionModel()
            if sel is not None:
                sel.selectionChanged.connect(lambda *_: self._on_pick(view))
        # Navigating to a different folder re-opens hover targeting.
        self.directoryEntered.connect(self._on_dir_changed)

    def _on_hover(self, index):
        # Sweep-to-target — but only until the user commits with a click.
        if self._firing or self._committed or not index.isValid():
            return
        view = self.findChild(QListView, "listView")
        if view is not None:
            view.setCurrentIndex(index)   # → selectionChanged → _on_pick lock-on

    def _on_click(self, index):
        # Explicit click: pin the lock to this row; hover no longer moves it.
        if self._firing or not index.isValid():
            return
        self._committed = True
        view = self.findChild(QListView, "listView")
        if view is not None:
            view.setCurrentIndex(index)
        if self._overlay is not None:
            self._overlay.confirm_lock()   # flicker to confirm the selection

    def _on_dir_changed(self, _path):
        self._committed = False
        if self._overlay is not None:
            self._overlay.clear_lock()

    def _on_pick(self, view):
        idxs = view.selectionModel().selectedIndexes()
        if not idxs or self._overlay is None:
            if self._overlay is not None:
                self._overlay.clear_lock()
            return
        idx = idxs[0]
        vr = view.visualRect(idx)
        top_left = view.viewport().mapToGlobal(vr.topLeft())
        self._overlay.set_lock(
            self._overlay.map_rect(QRect(top_left, vr.size())),
            idx.data() or "")
        self._overlay._impact = self._overlay.map_rect(
            QRect(top_left, vr.size())).center()

    def keyPressEvent(self, event):
        # Any key skips a running sequence (matches the mockup contract).
        if self._firing and self._overlay is not None:
            self._overlay.skip()
            return
        super().keyPressEvent(event)

    def done(self, result):
        if (result == QDialog.DialogCode.Accepted and self._overlay is not None
                and not self._sequence_done):
            if self._firing:
                return
            self._firing = True
            # Re-resolve the locked row NOW — scrolling or dragging the
            # dialog since the click leaves the cached rect stale.
            view = self.findChild(QListView, "listView")
            if view is not None and view.selectionModel() is not None \
                    and view.selectionModel().selectedIndexes():
                self._on_pick(view)
            # No row rect (typed path / no selection): impact at dialog centre.
            if self._overlay._lock_rect is None:
                centre = self._overlay.map_rect(self.geometry()).center()
                self._overlay._impact = centre
            sel = self.selectedFiles()
            self._overlay._aar_path = sel[0] if sel else ""
            self.setEnabled(False)     # freeze the UI for the kill-cam
            self._overlay.fire(self._complete)
            return
        super().done(result)

    def _complete(self):
        self._sequence_done = True
        self._firing = False
        super().done(QDialog.DialogCode.Accepted)


def pick_folder_chopper(parent, title: str, start_dir: str = ""):
    """GUI-thread entry: run the chopper-gunner picker, return the chosen
    path string or None on cancel. Raises on construction failure — the
    console catches anything and falls back to the native dialog."""
    dlg = _ChopperDialog(parent, title, start_dir)
    screen = (parent.screen() if parent is not None
              else QApplication.primaryScreen())
    overlay = GunnerOverlay(dlg, screen.geometry())
    dlg.attach_overlay(overlay)
    overlay.show()
    overlay.start_ambient()            # looping gunship bed while the picker is up
    try:
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        files = dlg.selectedFiles()
    finally:
        overlay.stop_ambient()         # covers the cancel path (no _finish)
        overlay._timer.stop()
        overlay.close()
        overlay.deleteLater()
        dlg.deleteLater()
    if accepted and files:
        return files[0]
    return None
