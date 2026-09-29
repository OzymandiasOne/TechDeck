"""Everything drawn flat: card faces, silhouette portraits, sigil icons, his face.

The rule for all of it: bold phosphor SILHOUETTES. ASCII art turned to mush
once a card was tilted and far away (his call). So every portrait is a solid
bright shape, detail is CUT OUT of it in the card's own dark, and ember is
saved for eyes and fire. Drawn small with antialiasing OFF, then blown up
with hard pixels, so it belongs to the same tube as everything else.

ORIGINAL art only - see the package docstring.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QRadialGradient)

from techdeck.ui.widgets.console_cat import FACE_ART, PHOSPHOR, compose_face

from . import cards as C

DIM, MID, BRIGHT, PEAK = (QColor(PHOSPHOR[k]) for k in ("dim", "mid", "bright", "peak"))
EMBER = QColor("#FF5436")           # offerings, weights, flames, eyes
BONE = QColor("#D8D2A8")            # remnants
CARD_DARK = QColor(2, 12, 6)        # a card's own dark: detail is cut out in it
VOID = QColor("#010302")
MONO = "Consolas"

PW, PH = 76, 62                     # a portrait, in hard pixels
SW = 22                             # a sigil icon, in hard pixels
CARD_PX = (260, 390)                # a card face texture

F, H, M, D, E = BRIGHT, PEAK, MID, CARD_DARK, EMBER


# ── tiny drawing verbs ────────────────────────────────────────────────────
def _poly(p, pts, color):
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(color)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _ell(p, cx, cy, rx, ry, color):
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(color)
    p.drawEllipse(QPointF(cx, cy), rx, ry)


def _line(p, pts, color, w=1.0):
    pen = QPen(color, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


def _wave(x0, y0, x1, y1, amp, waves, n=18, phase=0.0):
    pts = []
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln, dx / ln
    for i in range(n + 1):
        t = i / n
        o = amp * math.sin(phase + t * waves * math.tau) * (0.35 + 0.65 * t)
        pts.append((x0 + dx * t + nx * o, y0 + dy * t + ny * o))
    return pts


# ── portraits (76 x 62) ───────────────────────────────────────────────────
def votary(p):
    path = QPainterPath(QPointF(38, 2))
    path.cubicTo(25, 9, 21, 30, 11, 61); path.lineTo(65, 61); path.cubicTo(55, 30, 51, 9, 38, 2)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(F); p.drawPath(path)
    _ell(p, 38, 25, 8.5, 11, D)                       # the hood is empty
    _poly(p, [(34, 25), (36, 25), (36, 27), (34, 27)], H)
    _poly(p, [(40, 25), (42, 25), (42, 27), (40, 27)], H)
    _line(p, [(30, 44), (38, 50), (46, 44)], D, 1.6)  # folded arms


def _wolf_head(p, cx, cy, s, eye):
    pts = [(cx - 10 * s, cy - 13 * s), (cx - 4 * s, cy - 6 * s), (cx + 4 * s, cy - 6 * s), (cx + 10 * s, cy - 13 * s),
           (cx + 11 * s, cy + 1 * s), (cx + 5 * s, cy + 13 * s), (cx - 5 * s, cy + 13 * s), (cx - 11 * s, cy + 1 * s)]
    _poly(p, [(x + (1.6 if x > cx else -1.6), y + (1.6 if y > cy else -1.6)) for x, y in pts], D)
    _poly(p, pts, F)
    for sgn in (-1, 1):
        _poly(p, [(cx + sgn * 2 * s, cy - 1 * s), (cx + sgn * 8 * s, cy - 4 * s), (cx + sgn * 7 * s, cy + 0.5 * s)], D)
        _ell(p, cx + sgn * 5.4 * s, cy - 1.6 * s, 0.9 * s, 0.9 * s, eye)
    _poly(p, [(cx - 2 * s, cy + 5 * s), (cx + 2 * s, cy + 5 * s), (cx, cy + 7.5 * s)], D)      # nose
    teeth = [(cx - 4.5 * s + i * 1.5 * s, cy + (9.5 if i % 2 == 0 else 11.5) * s) for i in range(7)]
    _line(p, teeth, D, 1.2)


def hound(p):
    _wolf_head(p, 38, 30, 2.1, E)


def cerberus(p):
    _wolf_head(p, 17, 25, 1.0, E)
    _wolf_head(p, 59, 25, 1.0, E)
    _wolf_head(p, 38, 34, 1.45, E)


def ouroboros(p):
    _ell(p, 38, 32, 25, 23, F); _ell(p, 38, 32, 15.5, 13.5, D)
    for k in range(18):                                   # scales, as ticks cut into the ring
        a = math.radians(k * 20 + 8)
        _line(p, [(38 + 17 * math.cos(a), 32 + 15 * math.sin(a)), (38 + 23.5 * math.cos(a), 32 + 21.5 * math.sin(a))], D, 1.0)
    _poly(p, [(35, 3), (45, 6), (44, 16), (35, 17)], D)     # the gap where mouth meets tail
    _poly(p, [(44, 1), (60, 5), (64, 13), (56, 19), (44, 17)], F)   # the head, biting
    _poly(p, [(44, 8), (52, 10), (44, 12)], D)              # the jaw line
    _ell(p, 56, 9, 1.6, 1.6, E)
    _poly(p, [(35, 6), (41, 9), (35, 13)], F)               # the tail tip in its mouth


def weigher(p):
    # the jackal in profile. Tall ears, rounded at the tip (they were spikes).
    head = [(18, 61), (18, 40), (20, 25), (22, 6), (28, 18), (31, 5), (38, 20), (47, 24), (58, 29), (72, 36),
            (72, 41), (60, 44), (47, 45), (42, 50), (40, 61)]
    _poly(p, head, F)
    _ell(p, 22.5, 6.5, 2.6, 3.2, F); _ell(p, 31.5, 5.5, 2.6, 3.2, F)                            # ear tips
    _poly(p, [(23, 10), (26.5, 19), (23, 22)], D); _poly(p, [(31.5, 9), (34.5, 19), (31, 20)], D)   # inner ears
    _poly(p, [(39, 27), (47, 28.5), (50, 31), (41, 31.5)], D)                                   # kohl eye
    _ell(p, 44.5, 29.6, 1.3, 1.3, E)
    _line(p, [(50, 31), (56, 35)], D, 1.0)
    _line(p, [(47, 45), (62, 41), (71, 40)], D, 1.0)                                            # mouth
    _ell(p, 70.5, 37.3, 1.5, 1.2, D)                                                            # nose
    for y in (48, 52, 56):                                                                       # the collar
        _line(p, [(18.5, y), (40.5, y + 1.5)], D, 1.3)


def sleeper(p):
    for i, x in enumerate((17, 27, 38, 49, 59)):
        tip = (x + (x - 38) * 0.45, 61)
        pts = _wave(x, 28, tip[0], tip[1], 3.4, 1.6, phase=i * 1.3)
        for k in range(len(pts) - 1):
            t = k / (len(pts) - 1)
            _line(p, [pts[k], pts[k + 1]], F, max(1.2, 5.2 * (1 - 0.75 * t)))
    _ell(p, 38, 22, 25, 15, F)
    _poly(p, [(13, 22), (38, 10), (63, 22), (38, 34)], D)      # the lid opening
    _ell(p, 38, 22, 9.5, 9.5, F); _ell(p, 38, 22, 6.2, 6.2, D)
    _poly(p, [(38, 14.5), (40.2, 22), (38, 29.5), (35.8, 22)], E)   # the slit


def huginn(p):
    p.save(); p.translate(33, 37); p.rotate(-24); _ell(p, 0, 0, 20, 11.5, F); p.restore()
    _ell(p, 52, 21, 8.5, 8, F)
    _poly(p, [(57, 16), (75, 23), (58, 27)], F)                 # beak
    _line(p, [(59, 22.5), (72, 23.2)], D, 1.0)
    _poly(p, [(19, 40), (1, 52), (4, 57), (11, 55), (24, 49)], F)   # tail
    _poly(p, [(24, 33), (44, 27), (40, 41), (22, 47)], D)       # the folded wing, cut in
    _poly(p, [(26, 35), (42, 30), (39, 39), (25, 44)], M)
    _ell(p, 54, 19.5, 1.7, 1.7, D); _ell(p, 54.5, 19, 0.8, 0.8, H)
    for x in (33, 41):
        _line(p, [(x, 46), (x + 1, 57)], F, 1.6); _line(p, [(x - 3, 59), (x + 1, 57), (x + 5, 59)], F, 1.3)


def monolith(p):
    _poly(p, [(27, 3), (49, 3), (53, 57), (23, 57)], M); _poly(p, [(29, 5), (47, 5), (50.5, 55), (25.5, 55)], D)
    for y in range(9, 54, 4):
        k = (y - 5) / 50
        _line(p, [(29 - 3.5 * k + 1.5, y), (47 + 3.5 * k - 1.5, y)], QColor(30, 110, 55), 1.0)
    _line(p, [(27, 3), (23, 57)], H, 1.4); _line(p, [(27, 3), (49, 3)], H, 1.4)
    _line(p, [(4, 57.5), (72, 57.5)], F, 1.2)                   # the ground
    _ell(p, 63, 51.5, 1.3, 1.3, F); _line(p, [(63, 53), (63, 57)], F, 1.4)   # someone, for scale


def gorgon(p):
    for i, a in enumerate((-158, -135, -112, -90, -68, -45, -22)):
        r = math.radians(a)
        sx, sy = 38 + 11 * math.cos(r), 34 + 13 * math.sin(r)
        ex, ey = 38 + 31 * math.cos(r), 36 + 30 * math.sin(r)
        pts = _wave(sx, sy, ex, max(3, ey), 3.2, 1.5, phase=i * 0.9)
        _line(p, pts, F, 3.0)
        _ell(p, pts[-1][0], pts[-1][1], 2.6, 2.1, F)
    _ell(p, 38, 38, 13.5, 17, F)
    for sgn in (-1, 1):
        _poly(p, [(38 + sgn * 2, 34), (38 + sgn * 10, 31), (38 + sgn * 9, 37)], D)
        _ell(p, 38 + sgn * 6, 34.2, 1.5, 1.5, E)
    _line(p, [(32, 47), (38, 45), (44, 47)], D, 1.4)
    _poly(p, [(34.5, 46.5), (36, 46), (35.4, 50)], D); _poly(p, [(41.5, 46.5), (40, 46), (40.6, 50)], D)   # fangs


def scarab(p):
    for sgn in (-1, 1):
        _line(p, [(38 + sgn * 9, 25), (38 + sgn * 19, 17), (38 + sgn * 15, 9)], F, 2.0)      # holding the sun up
        _line(p, [(38 + sgn * 13, 38), (38 + sgn * 25, 35), (38 + sgn * 30, 42)], F, 2.0)
        _line(p, [(38 + sgn * 12, 48), (38 + sgn * 23, 52), (38 + sgn * 26, 60)], F, 2.0)
    _ell(p, 38, 8, 6.5, 6.5, E); _ell(p, 38, 8, 3.2, 3.2, QColor("#FFB08A"))
    _ell(p, 38, 42, 15, 18.5, F)
    _ell(p, 38, 26, 12, 7, F); _ell(p, 38, 18.5, 5.5, 4.5, F)
    _line(p, [(24, 30.5), (52, 30.5)], D, 1.4)
    _line(p, [(38, 31), (38, 60)], D, 1.4)
    for sgn in (-1, 1):
        _line(p, [(38 + sgn * 5, 35), (38 + sgn * 9, 55)], D, 0.9)


def dead_star(p):
    for k in range(16):
        a = math.radians(k * 22.5)
        r0, r1 = 23, 29 if k % 2 else 26
        _line(p, [(38 + r0 * math.cos(a), 31 + r0 * math.sin(a)), (38 + r1 * math.cos(a), 31 + r1 * math.sin(a))], M, 1.2)
    _ell(p, 38, 31, 19, 19, F); _ell(p, 38, 31, 16.5, 16.5, D)
    _line(p, [(28, 18), (35, 27), (31, 33), (40, 39), (37, 47)], F, 1.4)     # it is cracked through
    _line(p, [(35, 27), (44, 24), (50, 29)], F, 1.1); _line(p, [(40, 39), (49, 41)], F, 1.1)
    for x, y in ((9, 9), (66, 12), (70, 50), (7, 47), (60, 57)):
        _ell(p, x, y, 0.9, 0.9, M)


def nova(p):
    # the same star, a moment later
    for k in range(24):
        a = math.radians(k * 15 + 4)
        r1 = 31 if k % 3 == 0 else (25 if k % 3 == 1 else 21)
        _line(p, [(38 + 12 * math.cos(a), 31 + 12 * math.sin(a)), (38 + r1 * math.cos(a), 31 + r1 * math.sin(a))],
              H if k % 3 == 0 else F, 1.6 if k % 3 == 0 else 1.1)
    _ell(p, 38, 31, 13, 13, H); _ell(p, 38, 31, 9, 9, QColor("#FFB08A")); _ell(p, 38, 31, 5, 5, E)
    for x, y in ((6, 6), (70, 9), (72, 54), (5, 50), (63, 58), (12, 58)):
        _ell(p, x, y, 1.3, 1.3, H)


def famine(p):
    # a hooded thing, all ribs, holding out an empty bowl
    _poly(p, [(38, 3), (20, 22), (18, 61), (58, 61), (56, 22)], F)
    _ell(p, 38, 20, 9, 10, D)                                    # the hollow of the hood
    _ell(p, 34, 19, 2.2, 2.6, F); _ell(p, 42, 19, 2.2, 2.6, F)   # sunken eyes, lit
    _ell(p, 34, 19, 0.9, 0.9, E); _ell(p, 42, 19, 0.9, 0.9, E)
    for y in (33, 38, 43, 48):                                   # ribs cut into the robe
        _line(p, [(24, y), (33, y + 2)], D, 1.5); _line(p, [(52, y), (43, y + 2)], D, 1.5)
    _line(p, [(38, 30), (38, 52)], D, 1.5)
    _ell(p, 38, 55, 12, 4.5, D); _ell(p, 38, 54, 10, 3, F); _ell(p, 38, 54, 7.5, 1.8, D)   # the bowl
    _line(p, [(24, 50), (27, 55)], F, 2.0); _line(p, [(52, 50), (49, 55)], F, 2.0)         # the hands


PORTRAITS = {"votary": votary, "scarab": scarab, "hound": hound, "huginn": huginn, "weigher": weigher,
             "gorgon": gorgon, "ouroboros": ouroboros, "cerberus": cerberus, "sleeper": sleeper,
             "monolith": monolith, "dead_star": dead_star, "nova": nova, "famine": famine}


# ── sigil icons (22 x 22) - the metaphor, not the maths ───────────────────
def _winged(p):
    for sgn in (-1, 1):
        _poly(p, [(11, 14), (11 + sgn * 3, 7), (11 + sgn * 10, 3), (11 + sgn * 10, 9), (11 + sgn * 5, 16)], F)
    _ell(p, 11, 13, 2.2, 4.5, F)


def _warden(p):
    _poly(p, [(4, 3), (18, 3), (18, 11), (11, 20), (4, 11)], F)
    _poly(p, [(7, 6), (15, 6), (15, 10), (11, 15), (7, 10)], D)
    _line(p, [(11, 7), (11, 13)], F, 1.4)


def _venom(p):
    _poly(p, [(6, 2), (16, 2), (12, 13), (10, 13)], F)          # the fang
    _poly(p, [(9, 5), (13, 5), (11, 11)], D)
    _ell(p, 11, 17, 2.6, 3.2, E); _poly(p, [(11, 12), (13.4, 16.5), (8.6, 16.5)], E)   # the drop


def _three_mouths(p):
    for cx in (4.5, 11, 17.5):
        _poly(p, [(cx - 3, 4), (cx + 3, 4), (cx + 3, 18), (cx - 3, 18)], F)
        teeth = [(cx - 2.6 + i * 1.3, 8 if i % 2 else 11) for i in range(5)]
        _line(p, teeth, D, 1.0)
        _line(p, [(cx - 2.6, 14), (cx + 2.6, 14)], D, 1.0)


def _undying(p):
    _ell(p, 11, 11, 8.5, 8.5, F); _ell(p, 11, 11, 5.2, 5.2, D)
    _poly(p, [(11, 0), (16, 3), (11, 8), (8, 3)], D)           # the gap
    _poly(p, [(11, 1), (17, 3.5), (15, 8), (11, 7)], F)         # the head over the tail
    _ell(p, 14.5, 4, 0.8, 0.8, E)


def _worthy(p):
    for cx, cy in ((5.5, 12), (11, 6), (16.5, 12)):
        _poly(p, [(cx, cy - 4.5), (cx + 3.5, cy), (cx, cy + 4.5), (cx - 3.5, cy)], E)
    _poly(p, [(11, 11), (14, 15), (11, 19), (8, 15)], E)


def _grows(p):
    _ell(p, 11, 12, 7.5, 8.5, F); _ell(p, 11, 12, 5.5, 6.5, D)  # the shell
    _line(p, [(7, 8), (10, 12), (8, 15), (12, 18)], F, 1.3)     # the crack
    for a in (-90, -50, -130):
        r = math.radians(a)
        _line(p, [(11 + 8 * math.cos(r), 12 + 9 * math.sin(r)), (11 + 11 * math.cos(r), 12 + 12 * math.sin(r))], H, 1.2)


def _gaze(p):
    _poly(p, [(1, 11), (6, 5), (16, 5), (21, 11), (16, 17), (6, 17)], F)
    _ell(p, 11, 11, 4.2, 4.2, D); _ell(p, 11, 11, 2.4, 2.4, E)


SIGIL_ICONS = {C.WINGED: _winged, C.WARDEN: _warden, C.VENOM: _venom, C.THREE_MOUTHS: _three_mouths,
               C.UNDYING: _undying, C.WORTHY: _worthy, C.GROWS: _grows, C.GAZE: _gaze}


# ── hard-pixel rendering ──────────────────────────────────────────────────
def _hard(w, h, draw, scale):
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)     # hard pixels, on purpose
    draw(p)
    p.end()
    return img.scaled(w * scale, h * scale, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.FastTransformation)


def portrait(card_id: str, scale: int = 3) -> QImage:
    return _hard(PW, PH, PORTRAITS[card_id], scale)


def sigil_icon(sigil: str, scale: int = 3) -> QImage:
    return _hard(SW, SW, SIGIL_ICONS[sigil], scale)


# ── card faces ────────────────────────────────────────────────────────────
_FACES: dict[tuple, QPixmap] = {}


def card_face(defn: C.CardDef, power: int | None = None, health: int | None = None,
              sigils: tuple[str, ...] | None = None) -> QPixmap:
    """The texture for one card. Cached per (card, numbers, sigils): a wounded
    card shows its wound, a grown Ouroboros its new strength, a fifth Famine
    its wings."""
    power = defn.power if power is None else power
    health = defn.health if health is None else health
    sigils = defn.sigils if sigils is None else tuple(sigils)
    key = (defn.id, power, health, sigils)
    if key not in _FACES:
        _FACES[key] = _card_face(defn, power, health, sigils)
    return _FACES[key]


def _card_face(defn: C.CardDef, power: int, health: int, sigils: tuple[str, ...]) -> QPixmap:
    w, h = CARD_PX
    pm = QPixmap(w, h)
    pm.fill(CARD_DARK)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QRadialGradient(w / 2, h * 0.42, w * 0.8)            # a faint lit heart
    g.setColorAt(0, QColor(20, 70, 34, 120)); g.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(0, 0, w, h, g)
    p.setPen(QPen(BRIGHT, 5)); p.drawRect(6, 6, w - 12, h - 12)
    p.setPen(QPen(MID, 2)); p.drawRect(15, 15, w - 30, h - 30)
    p.drawLine(15, 66, w - 15, 66); p.drawLine(15, h - 104, w - 15, h - 104)
    f = QFont(MONO, 19); f.setBold(True); f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
    p.setFont(f); p.setPen(PEAK)
    p.drawText(QRectF(15, 18, w - 30, 46), Qt.AlignmentFlag.AlignCenter, defn.name)
    por = portrait(defn.id, 3)
    p.drawImage(int((w - por.width()) / 2), 84, por)
    if defn.cost:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BONE if defn.cost_kind == C.REMNANT else EMBER)
        for i in range(defn.cost):
            cx = w - 38 - i * 30
            p.drawPolygon(QPolygonF([QPointF(cx, 78), QPointF(cx + 11, 92), QPointF(cx, 106), QPointF(cx - 11, 92)]))
    big = QFont(MONO, 52); big.setBold(True)                # numbers must read from across the board
    p.setFont(big)
    p.setPen(PEAK if power >= defn.power else EMBER)
    p.drawText(QRectF(20, h - 102, 80, 88), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(power))
    p.setPen(PEAK if health >= defn.health else EMBER)
    p.drawText(QRectF(w - 100, h - 102, 80, 88), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(health))
    if sigils:
        icons = [sigil_icon(s, 3) for s in sigils]
        total = sum(i.width() for i in icons) + 10 * (len(icons) - 1)
        x = (w - total) / 2
        for ic in icons:
            p.drawImage(int(x), h - 58 - ic.height() // 2, ic)
            x += ic.width() + 10
    p.end()
    return pm


_BACK: QPixmap | None = None


def card_back() -> QPixmap:
    global _BACK
    if _BACK is None:
        w, h = CARD_PX
        pm = QPixmap(w, h); pm.fill(CARD_DARK)
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(BRIGHT, 5)); p.drawRect(6, 6, w - 12, h - 12)
        p.setPen(QPen(MID, 2))
        for k in range(1, 9):
            p.drawEllipse(QPointF(w / 2, h / 2), k * 14, k * 21)
        p.setPen(QPen(PEAK, 3)); p.drawEllipse(QPointF(w / 2, h / 2), 30, 16)
        p.setBrush(PEAK); p.drawEllipse(QPointF(w / 2, h / 2), 9, 9)
        p.end()
        _BACK = pm
    return _BACK


# ── his face, as a texture ────────────────────────────────────────────────
TIER = {"@": PEAK, "%": BRIGHT, "+": BRIGHT, "=": MID, "o": MID, "x": MID, "~": DIM, "·": DIM}
FACE_ROWS = 14
_FACE_CACHE: dict[int, QPixmap] = {}


def face_texture(mouth: int = 0, blink: bool = False, iris=(2, 1), flicker: float = 0.0,
                 seed: int = 0) -> QPixmap:
    """His face, from the console face's own frames (compose_face): mouth 0 is
    shut, 1/2 the speaking grin; blink drops the lids; iris is the 5x3 gaze.
    Cached per pose: 800 glyphs is too many to redraw per frame. A flickering
    face is cached per seed (a short loop)."""
    key = (mouth, blink, tuple(iris), 0 if flicker < 0.05 else 1 + seed % 6)
    if key not in _FACE_CACHE:
        _FACE_CACHE[key] = _face_texture(mouth, blink, iris, 0.0 if key[3] == 0 else flicker, seed)
    return _FACE_CACHE[key]


def _face_texture(mouth: int, blink: bool, iris, flicker: float, seed: int) -> QPixmap:
    rows = compose_face(iris=tuple(iris), mouth=mouth, blink=blink)
    cw, ch = 15, 28
    pm = QPixmap(55 * cw, len(rows) * ch); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); f = QFont(MONO, 18); f.setBold(True); p.setFont(f)
    rng = random.Random(seed)
    for j, row in enumerate(rows):
        for i, (chh, tier) in enumerate(row):
            if tier is None or chh == " ":
                continue
            col = QColor(PHOSPHOR.get(tier, PHOSPHOR["mid"]))
            if rng.random() < flicker:
                chh = rng.choice("@%#*+=01"); col = QColor(PEAK)
            p.setPen(col); p.drawText(QRectF(i * cw, j * ch, cw, ch), Qt.AlignmentFlag.AlignCenter, chh)
    p.end()
    return pm


def clear_caches():
    _FACES.clear(); _FACE_CACHE.clear()
    global _BACK
    _BACK = None
