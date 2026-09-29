"""Our own small software 3D renderer, on QPainter.

A camera, perspective, painter's depth sort, card faces mapped onto tilted
quads with QTransform.quadToQuad, glowing wireframe props. No GPU, no OpenGL,
no new dependencies: it runs anywhere TechDeck runs, including locked-down
virtual desktops.

The look recipe (from the talk that inspired this): render SMALL (960x540),
blow it up with hard pixels, let darkness do the work, ONE bloom pass for the
glow (a fat translucent stroke per line cost 42 ms a frame; shrinking the
whole frame and adding it back costs 2), then scanlines and dark corners.
"""
from __future__ import annotations

import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap,
                           QPolygonF, QRadialGradient, QTransform)

from . import art
from .art import BRIGHT, DIM, EMBER, MID, MONO, PEAK, VOID

W, H = 960, 540

Vec = tuple[float, float, float]


# ── maths ────────────────────────────────────────────────────────────────
def add(a: Vec, b: Vec) -> Vec: return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a: Vec, b: Vec) -> Vec: return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a: Vec, k: float) -> Vec: return (a[0] * k, a[1] * k, a[2] * k)
def dot(a: Vec, b: Vec) -> float: return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a: Vec) -> Vec:
    l = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)
def lerp(a: Vec, b: Vec, t: float) -> Vec: return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Camera:
    def __init__(self, pos: Vec, look: Vec, fov: float = 50.0):
        self.f = (H / 2) / math.tan(math.radians(fov) / 2)
        self.set(pos, look)

    def set(self, pos: Vec, look: Vec):
        self.pos = pos
        self.fwd = norm(sub(look, pos))
        self.right = norm(cross(self.fwd, (0, 1, 0)))
        self.up = cross(self.right, self.fwd)

    def project(self, p: Vec):
        """Screen (x, y, depth) or None when it is behind the lens."""
        d = sub(p, self.pos)
        z = dot(d, self.fwd)
        if z < 0.15:
            return None
        return (W / 2 + self.f * dot(d, self.right) / z, H / 2 - self.f * dot(d, self.up) / z, z)

    def depth(self, p: Vec) -> float:
        return dot(sub(p, self.pos), self.fwd)


# ── the table's geometry (world units) ───────────────────────────────────
LANES = [-2.4, -0.8, 0.8, 2.4]
ROW_YOU, ROW_HIM, ROW_NEXT = 2.55, 0.25, -2.05
CW2, CH2 = 0.68, 1.02                 # half width / half height of a card on the table
FLAT_U: Vec = (CW2, 0, 0)
FLAT_V: Vec = (0, 0, -CH2)
SCALE_BASE: Vec = (-5.0, 0, 1.2)
BELL: Vec = (4.9, 0, 0.2)
DECK: Vec = (4.5, 0, 2.6)
VOTARIES: Vec = (5.7, 0, 2.6)
REMNANTS: Vec = (-4.9, 0, 3.4)
FACE_CENTER: Vec = (0.0, 4.45, -9.5)
HAND_Z = 6.3
HAND_SCALE = 0.62


def slot_center(row: float, lane: int, lift: float = 0.03) -> Vec:
    return (LANES[lane], lift, row)


def hand_pose(k: float, lift: float = 0.0, tuck: float = 0.0):
    """Where the k-th card of a fanned hand sits (k is centred: -1.5 .. 1.5).
    `tuck` (0..1) drops the hand out of the way until only the tops show."""
    ang = -k * 0.13
    hs = HAND_SCALE
    u = (CW2 * hs * math.cos(ang), CW2 * hs * math.sin(ang), 0)
    v = mul(norm((-math.sin(ang) * 0.9, math.cos(ang) * 0.80, -0.60)), CH2 * hs)
    c = (k * 0.82, 2.75 - abs(k) * 0.07 + lift - 1.15 * tuck, HAND_Z - lift * 0.6 + 0.35 * tuck)
    return c, u, v


# The three places the camera can be. HAND is the resting view (with the slow
# sway); DECK leans right toward the piles; BOARD is the top-down view where
# every lane is clear. Moves between them glide (camera_between).
VIEWS = {
    "hand": ((0.0, 5.6, 9.6), (0.0, 0.95, -1.4), 50.0),
    "deck": ((3.4, 5.0, 8.6), (4.9, 0.3, 2.0), 46.0),
    "board": ((0.0, 11.4, 3.1), (0.0, 0.0, 0.35), 50.0),
}
VIEW_S = 0.45                         # a camera move, in seconds


def camera_between(view_from: str, view_to: str, k: float, t: float, shake: float = 0.0) -> Camera:
    """The camera part-way (k = 0..1) from one view to another."""
    sw = CAMERA_SWAY
    sway = (0.50 * sw * math.sin(t * 0.55) + shake * math.sin(t * 61) * 0.08,
            0.10 * sw * math.sin(t * 0.8) + shake * math.cos(t * 53) * 0.06, 0.0)
    look_sway = (0.10 * sw * math.sin(t * 0.4), 0.0, 0.0)
    e = ease(k)
    (pa, la, fa), (pb, lb, fb) = VIEWS[view_from], VIEWS[view_to]
    wa = 1.0 if view_from == "hand" else 0.0
    wb = 1.0 if view_to == "hand" else 0.0
    ws = wa + (wb - wa) * e
    pos = add(lerp(pa, pb, e), mul(sway, ws))
    look = add(lerp(la, lb, e), mul(look_sway, ws))
    return Camera(pos, look, fov=fa + (fb - fa) * e)


# The slow camera sway. TECHDECK_TABLE_STILL=1 freezes it (playtesting by
# screenshot: a card must be where the picture said it was).
CAMERA_SWAY = 0.0 if os.environ.get("TECHDECK_TABLE_STILL") else 1.0


def default_camera(t: float, shake: float = 0.0) -> Camera:
    sw = CAMERA_SWAY
    sx = 0.50 * sw * math.sin(t * 0.55) + shake * math.sin(t * 61) * 0.08
    sy = 5.6 + 0.10 * sw * math.sin(t * 0.8) + shake * math.cos(t * 53) * 0.06
    return Camera((sx, sy, 9.6), (0.10 * sw * math.sin(t * 0.4), 0.95, -1.4), fov=50.0)


# ── drawing in 3D ────────────────────────────────────────────────────────
_PENS: dict[tuple, QPen] = {}


def _pen(color, width: float, alpha: float) -> QPen:
    """Pens cached by colour, width and 1/24th of alpha: hundreds of lines a
    frame, a handful of distinct pens."""
    key = (color.rgb(), round(width, 1), int(alpha * 24))
    pen = _PENS.get(key)
    if pen is None:
        c = QColor(color); c.setAlphaF(key[2] / 24)
        pen = _PENS[key] = QPen(c, width)
    return pen


class Frame:
    """One frame being drawn: the image, its painter and the camera."""

    def __init__(self, cam: Camera):
        self.cam = cam
        self.img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        self.img.fill(VOID)
        self.p = QPainter(self.img)
        self.p.setRenderHint(QPainter.RenderHint.Antialiasing)

    def glow_line(self, a, b, color, width=1.4, depth=6.0):
        """ONE thin stroke, dimmer with distance. The glow comes from finish()."""
        k = max(0.15, min(1.0, 7.0 / depth))
        self.p.setPen(_pen(color, width, min(1.0, 0.95 * k + 0.05)))
        self.p.drawLine(QPointF(*a), QPointF(*b))

    def line3(self, a: Vec, b: Vec, color, width=1.4):
        pa, pb = self.cam.project(a), self.cam.project(b)
        if pa and pb:
            self.glow_line(pa[:2], pb[:2], color, width, (pa[2] + pb[2]) / 2)

    def polyline3(self, pts, color, width=1.2):
        for a, b in zip(pts, pts[1:]):
            self.line3(a, b, color, width)

    def quad3(self, center: Vec, u: Vec, v: Vec):
        """Corners TL, TR, BR, BL projected, or None if any is behind the lens."""
        pts = [add(center, add(mul(u, -1), v)), add(center, add(u, v)),
               add(center, add(u, mul(v, -1))), add(center, add(mul(u, -1), mul(v, -1)))]
        pr = [self.cam.project(q) for q in pts]
        return None if any(q is None for q in pr) else pr

    def draw_textured(self, pr, pm: QPixmap, opacity: float = 1.0):
        dst = QPolygonF([QPointF(q[0], q[1]) for q in pr])
        src = QPolygonF([QPointF(0, 0), QPointF(pm.width(), 0), QPointF(pm.width(), pm.height()), QPointF(0, pm.height())])
        t = QTransform()
        if not QTransform.quadToQuad(src, dst, t):
            return
        p = self.p
        p.save(); p.setTransform(t, True); p.setOpacity(opacity)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(0, 0, pm); p.restore()

    def draw_card(self, center: Vec, u: Vec, v: Vec, front: QPixmap, back: QPixmap,
                  opacity: float = 1.0, edge=BRIGHT):
        """A card: a textured quad with a glowing edge. Returns its screen polygon
        (for picking) or None."""
        pr = self.quad3(center, u, v)
        if not pr:
            return None
        normal = cross(u, v)
        facing = dot(normal, sub(self.cam.pos, center)) > 0
        pm = front if facing else back
        self.draw_textured(pr if facing else [pr[1], pr[0], pr[3], pr[2]], pm, opacity)
        depth = sum(q[2] for q in pr) / 4
        for i in range(4):
            self.glow_line(pr[i][:2], pr[(i + 1) % 4][:2], edge, 1.2, depth)
        return QPolygonF([QPointF(q[0], q[1]) for q in pr])

    def ring(self, center: Vec, r: float, n: int = 10):
        return [add(center, (r * math.cos(math.tau * i / n), 0, r * math.sin(math.tau * i / n)))
                for i in range(n + 1)]

    def keycap(self, cx: float, cy: float, s: str, k: float = 1.0, color=BRIGHT, size: int = 11):
        """A key, drawn flat at a screen point: one letter is square, a word is a
        bar (the space bar is wide). `k` scales with distance."""
        w = max(22, 12 + 9 * len(s)) * k
        h = 22 * k
        x, y = cx - w / 2, cy - h / 2
        p = self.p
        p.setPen(QPen(QColor(color), 1.2)); p.setBrush(QColor(1, 8, 4, 210))
        p.drawRoundedRect(QRectF(x, y, w, h), 4 * k, 4 * k)
        p.setPen(QPen(QColor(color), 1.0)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(x + 4 * k, y + h - 3 * k), QPointF(x + w - 4 * k, y + h - 3 * k))   # the cap's lip
        self.text(x, y - 1, w, h - 2, s, color, int(size * k), True, spacing=0)
        return w, h

    def page_icon(self, cx: float, cy: float, side: str = "right", k: float = 1.0, color=BRIGHT):
        """A page with its corner turning: `side` is the corner that curls."""
        w, h = 14 * k, 18 * k
        x, y = cx - w / 2, cy - h / 2
        p = self.p
        p.setPen(QPen(QColor(color), 1.2)); p.setBrush(QColor(1, 8, 4, 210))
        f = 6 * k
        if side == "right":
            pts = [QPointF(x, y), QPointF(x + w - f, y), QPointF(x + w, y + f), QPointF(x + w, y + h), QPointF(x, y + h)]
            fold = [QPointF(x + w - f, y), QPointF(x + w - f, y + f), QPointF(x + w, y + f)]
        else:
            pts = [QPointF(x + f, y), QPointF(x + w, y), QPointF(x + w, y + h), QPointF(x, y + h), QPointF(x, y + f)]
            fold = [QPointF(x + f, y), QPointF(x + f, y + f), QPointF(x, y + f)]
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(QColor(color)); p.drawPolygon(QPolygonF(fold))
        p.setPen(QPen(QColor(color), 0.9))
        for i in (1, 2):
            yy = y + h * (0.45 + 0.18 * i)
            p.drawLine(QPointF(x + 3 * k, yy), QPointF(x + w - 3 * k, yy))

    def label3(self, at: Vec, s: str, color=BRIGHT, size: int = 11):
        """A key hint floating at a point in the world."""
        q = self.cam.project(at)
        if not q:
            return
        k = max(0.6, min(1.0, 7.0 / q[2]))
        self.keycap(q[0], q[1], s, k, color, size)

    def text(self, x, y, w, h, s, color=PEAK, size=13, bold=True, align=Qt.AlignmentFlag.AlignCenter, spacing=2):
        f = QFont(MONO, size); f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        self.p.setFont(f); self.p.setPen(color)
        self.p.drawText(QRectF(x, y, w, h), int(align) | int(Qt.TextFlag.TextWordWrap), s)

    def end(self) -> QImage:
        self.p.end()
        return self.img


# ── the void and its furniture ───────────────────────────────────────────
_rain_rng = random.Random(3)
RAIN = [(_rain_rng.uniform(-16, 16), _rain_rng.uniform(-24, -9), _rain_rng.uniform(0, 9), _rain_rng.uniform(0.6, 1.6))
        for _ in range(30)]
_GLYPHS = "01ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜ"


def draw_void(fr: Frame, t: float):
    """Horizon glow, code rain far off, the grid running into the dark."""
    p, cam = fr.p, fr.cam
    hz = cam.project((0, 0, -60))
    if hz:
        g = QLinearGradient(0, hz[1] - 70, 0, hz[1] + 60)
        g.setColorAt(0, QColor(0, 0, 0, 0)); g.setColorAt(0.55, QColor(20, 110, 50, 70)); g.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, hz[1] - 70, W, 130), g)
    p.setFont(QFont(MONO, 9))
    for (x, z, off, sp) in RAIN:
        for k in range(7):
            y = 9.0 - ((t * sp * 2.2 + off + k * 0.55) % 9.5)
            q = cam.project((x, y, z))
            if q:
                c = QColor(PEAK if k == 0 else MID)
                c.setAlphaF(max(0.0, (0.75 if k == 0 else 0.42 - k * 0.04)) * min(1, 9 / q[2]))
                p.setPen(c)
                p.drawText(QPointF(q[0], q[1]), _GLYPHS[int(x * 97 + k + int(t * sp * 4)) % len(_GLYPHS)])
    for i in range(-14, 15):
        fr.line3((i * 1.6, 0, 6.5), (i * 1.6, 0, -34), DIM, 0.9)
    for k in range(0, 26):
        z = 6.5 - k * 1.6
        fr.line3((-22.4, 0, z), (22.4, 0, z), DIM, 0.9)


def draw_him(fr: Frame, t: float, flicker: float = 0.0, seed: int = 0, halo=(40, 200, 90, 46), bob: float = 1.0,
             mouth: int = 0, blink: bool = False, iris=(2, 1)):
    """HIM, vast, far back, looking down at the board. The mouth moves while
    he talks, the eyes blink and follow the mouse - the console face's own frames."""
    ftex = art.face_texture(mouth, blink, iris, flicker, seed)
    fc = (FACE_CENTER[0], FACE_CENTER[1] + 0.08 * bob * math.sin(t * 0.9), FACE_CENTER[2])
    fu = (6.4, 0, 0)
    fv = mul(norm((0, 1, 0.30)), 6.4 * ftex.height() / ftex.width())
    pr = fr.quad3(fc, fu, fv)
    if not pr:
        return
    cx, cy = (pr[0][0] + pr[2][0]) / 2, (pr[0][1] + pr[2][1]) / 2
    g = QRadialGradient(QPointF(cx, cy), 330)
    g.setColorAt(0, QColor(*halo)); g.setColorAt(1, QColor(0, 0, 0, 0))
    fr.p.fillRect(0, 0, W, H, g)
    fr.draw_textured(pr, ftex)


def draw_slots(fr: Frame, highlight: set[tuple[str, int]] = frozenset()):
    """Card slots etched into the grid, each with a watching eye. `highlight`
    holds (row_name, lane) pairs to light up (legal targets)."""
    for name, z, tone in (("next", ROW_NEXT, DIM), ("him", ROW_HIM, MID), ("you", ROW_YOU, MID)):
        for lane, x in enumerate(LANES):
            c = (x, 0.01, z)
            col, wd = (PEAK, 1.8) if (name, lane) in highlight else (tone, 1.0)
            pts = [add(c, (-CW2 - .07, 0, -CH2 - .07)), add(c, (CW2 + .07, 0, -CH2 - .07)),
                   add(c, (CW2 + .07, 0, CH2 + .07)), add(c, (-CW2 - .07, 0, CH2 + .07))]
            fr.polyline3(pts + [pts[0]], col, wd)
            fr.polyline3(fr.ring(c, 0.22, 8), col, 0.9)


def slot_polygon(fr: Frame, row: float, lane: int) -> QPolygonF | None:
    pr = fr.quad3(slot_center(row, lane), FLAT_U, FLAT_V)
    return QPolygonF([QPointF(q[0], q[1]) for q in pr]) if pr else None


def draw_scale(fr: Frame, value: float, glow: float = 0.0):
    """The scale, left. `value` is the game's scale: + tips toward him (your
    weights on his pan), - tips toward you. Weight, not numbers."""
    base = SCALE_BASE
    tilt = -0.16 * max(-1.0, min(1.0, value / 5.0))
    fr.polyline3(fr.ring(base, 0.55), MID)
    top = add(base, (0, 1.9, 0))
    fr.line3(base, top, BRIGHT, 1.6)
    la = add(top, (-1.25 * math.cos(tilt), -1.25 * math.sin(tilt), 0))
    ra = add(top, (1.25 * math.cos(tilt), 1.25 * math.sin(tilt), 0))
    fr.line3(la, ra, BRIGHT, 1.6)
    yours = max(0, int(round(value)))       # weights YOU have landed sit on the right pan
    his = max(0, int(round(-value)))
    for arm, n_w in ((la, his), (ra, yours)):
        pan = add(arm, (0, -0.75, 0))
        for a in (0, 2.1, 4.2):
            fr.line3(arm, add(pan, (0.42 * math.cos(a), 0, 0.42 * math.sin(a))), MID, 1.0)
        fr.polyline3(fr.ring(pan, 0.42), BRIGHT)
        for i in range(n_w):
            wq = fr.cam.project(add(pan, (-0.2 + 0.2 * (i % 3), 0.10 + 0.17 * (i // 3), 0)))
            if wq:
                p = fr.p
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(EMBER); c.setAlpha(int(70 + 120 * glow)); p.setBrush(c)
                p.drawEllipse(QPointF(wq[0], wq[1]), 9, 9)
                p.setBrush(EMBER); p.drawEllipse(QPointF(wq[0], wq[1]), 3.6, 3.6)


def draw_bell(fr: Frame, lit: bool = False, ringing: float = 0.0) -> QPolygonF | None:
    """The bell, right. Returns a screen polygon for picking."""
    bb = BELL
    col = PEAK if lit else BRIGHT
    wob = 0.08 * math.sin(ringing * 40) * (1 - ringing) if ringing else 0.0
    fr.polyline3(fr.ring(bb, 0.5), col)
    fr.polyline3(fr.ring(add(bb, (wob, 0.35, 0)), 0.36), MID)
    fr.polyline3(fr.ring(add(bb, (wob * 1.6, 0.6, 0)), 0.14), MID)
    for a in range(0, 360, 60):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        fr.polyline3([add(bb, (0.5 * ca, 0, 0.5 * sa)), add(bb, (0.36 * ca + wob, 0.35, 0.36 * sa)),
                      add(bb, (0.14 * ca + wob * 1.6, 0.6, 0.14 * sa))], MID, 0.9)
    return _box_polygon(fr, bb, 0.6, 0.75)


def _box_polygon(fr: Frame, base: Vec, r: float, height: float) -> QPolygonF | None:
    pts = [add(base, (-r, 0, r)), add(base, (r, 0, r)), add(base, (r, height, -r)), add(base, (-r, height, -r))]
    pr = [fr.cam.project(q) for q in pts]
    if any(q is None for q in pr):
        return None
    return QPolygonF([QPointF(q[0], q[1]) for q in pr])


def draw_pile(fr: Frame, base: Vec, count: int, top: QPixmap, lit: bool = False) -> QPolygonF | None:
    """A stack of cards, face down (or `top` face up). Returns a screen polygon."""
    if count <= 0:
        pts = [add(base, (-CW2 * .8, 0.01, CH2 * .8)), add(base, (CW2 * .8, 0.01, CH2 * .8)),
               add(base, (CW2 * .8, 0.01, -CH2 * .8)), add(base, (-CW2 * .8, 0.01, -CH2 * .8))]
        fr.polyline3(pts + [pts[0]], DIM, 1.0)
        return _box_polygon(fr, base, CW2 * .8, 0.05)
    layers = min(count, 8)
    poly = None
    for i in range(layers):
        c = add(base, (0, 0.02 + i * 0.045, 0))
        pm = top if i == layers - 1 else art.card_back()
        poly = fr.draw_card(c, mul(FLAT_U, .8), mul(FLAT_V, .8), pm, art.card_back(), 1.0,
                            PEAK if (lit and i == layers - 1) else MID)
    return poly


def draw_remnants(fr: Frame, count: int):
    """What your dead left behind: a small heap of bone diamonds."""
    for i in range(count):
        q = fr.cam.project(add(REMNANTS, (-0.3 + 0.3 * (i % 3), 0.05 + 0.22 * (i // 3), 0.1 * ((i // 3) % 2))))
        if q:
            s = 7 * min(1.0, 7.0 / q[2])
            fr.p.setPen(Qt.PenStyle.NoPen); fr.p.setBrush(art.BONE)
            fr.p.drawPolygon(QPolygonF([QPointF(q[0], q[1] - s), QPointF(q[0] + s * .7, q[1]),
                                        QPointF(q[0], q[1] + s), QPointF(q[0] - s * .7, q[1])]))
    fr.polyline3(fr.ring(REMNANTS, 0.5, 12), DIM, 0.9)


# ── the tube ─────────────────────────────────────────────────────────────
_OVERLAYS: dict[bool, QImage] = {}


def _tube_overlay(scanlines: bool = True) -> QImage:
    """Scanlines + dark corners, drawn ONCE and reused every frame."""
    o = _OVERLAYS.get(scanlines)
    if o is None:
        o = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        o.fill(Qt.GlobalColor.transparent)
        p = QPainter(o)
        if scanlines:
            p.setPen(QPen(QColor(0, 0, 0, 58), 1))
            for y in range(0, H, 3):
                p.drawLine(0, y, W, y)
        v = QRadialGradient(QPointF(W / 2, H / 2), W * 0.72)
        v.setColorAt(0.55, QColor(0, 0, 0, 0)); v.setColorAt(1.0, QColor(0, 0, 0, 215))
        p.fillRect(0, 0, W, H, v); p.end()
        _OVERLAYS[scanlines] = o
    return o


def finish(img: QImage, dim: float = 0.0, scanlines: bool = True) -> QImage:
    """Bloom = shrink the frame, blow it back up soft, ADD it on top: one glow
    for everything on screen. Then scanlines and dark corners. `dim` darkens
    the whole tube (his displeasure)."""
    small = img.scaled(W // 6, H // 6, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    soft = small.scaled(W, H, Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus); p.setOpacity(0.85)
    p.drawImage(0, 0, soft)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver); p.setOpacity(1.0)
    p.drawImage(0, 0, _tube_overlay(scanlines))
    if dim > 0:
        p.fillRect(0, 0, W, H, QColor(0, 0, 0, int(200 * min(1.0, dim))))
    p.end()
    return img
