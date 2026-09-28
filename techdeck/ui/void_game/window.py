"""The playable table: one dark window, the whole game as objects in a void.

No UI. The bell lights when you may ring it, the piles light when you must
draw, lanes light where a card may go. His captions burn into the tube
between his face and the board. The rules engine already knows what
happened; this window replays its EVENTS as animation, one act at a time,
and only listens to the mouse when no act is running.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from . import art, render3d as r3
from .art import BONE, BRIGHT, DIM, EMBER, MID, PEAK, VOID
from .cards import CARDS, OFFER, REMNANT, SIGILS
from .dialogue import MOODS, Dialogue, Mood
from .rules import HIM, LANES, SCALE_TO_WIN, YOU, Card, Game, IllegalMove
from .render3d import H, W, Vec, add, dot, ease, lerp, mul, norm

FPS = 30
TICK_MS = 1000 // FPS
Pose = tuple[Vec, Vec, Vec]               # centre, half-width vector, half-height vector

DEAL_S, PLAY_S, MOVE_S, HAND_S = 0.45, 0.55, 0.45, 0.16
LUNGE_S, FADE_S, GROW_S = 0.22, 0.42, 0.5
IDLE_LINE_S = 40.0
FAR_AWAY: Vec = (0.0, 3.5, -7.0)         # where his cards come from


def _vlen(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def lerp_pose(a: Pose, b: Pose, e: float, arc: float = 0.0) -> Pose:
    c = lerp(a[0], b[0], e)
    c = (c[0], c[1] + arc * math.sin(math.pi * e), c[2])
    u, v = lerp(a[1], b[1], e), lerp(a[2], b[2], e)
    lu = _vlen(a[1]) + (_vlen(b[1]) - _vlen(a[1])) * e
    lv = _vlen(a[2]) + (_vlen(b[2]) - _vlen(a[2])) * e
    return c, mul(norm(u), lu), mul(norm(v), lv)


@dataclass
class VCard:
    """A card as the screen knows it: where it is, where it is going."""
    card: Card
    pose: Pose
    dst: Pose
    shown_power: int
    shown_health: int
    where: str = "hand"                   # hand | you | him | next | gone
    lane: int = -1
    opacity: float = 1.0
    fade_to: float = 1.0
    fade_rate: float = 0.0
    anim_from: Pose | None = None
    anim_t0: float = 0.0
    anim_dur: float = 0.0
    anim_arc: float = 0.0
    lunge: Vec = (0.0, 0.0, 0.0)
    lunge_t0: float = -9.0
    shake_until: float = -1.0
    flash_until: float = -1.0
    edge: QColor = field(default_factory=lambda: QColor(BRIGHT))

    @property
    def uid(self) -> int:
        return self.card.uid

    def go(self, dst: Pose, t: float, dur: float, arc: float = 0.0):
        if dst == self.dst and self.anim_from is not None:
            return
        self.anim_from, self.dst = self.pose, dst
        self.anim_t0, self.anim_dur, self.anim_arc = t, dur, arc

    def advance(self, t: float, dt: float):
        if self.anim_from is not None:
            e = 1.0 if self.anim_dur <= 0 else (t - self.anim_t0) / self.anim_dur
            if e >= 1.0:
                self.pose, self.anim_from = self.dst, None
            else:
                self.pose = lerp_pose(self.anim_from, self.dst, ease(e), self.anim_arc)
        if self.opacity != self.fade_to:
            step = self.fade_rate * dt
            self.opacity = (min(self.fade_to, self.opacity + step) if self.fade_to > self.opacity
                            else max(self.fade_to, self.opacity - step))

    def fade(self, to: float, seconds: float):
        self.fade_to, self.fade_rate = to, abs(to - self.opacity) / max(0.05, seconds)

    def drawn_pose(self, t: float) -> Pose:
        c, u, v = self.pose
        k = t - self.lunge_t0
        if 0 <= k < LUNGE_S * 2:
            c = add(c, mul(self.lunge, math.sin(math.pi * k / (LUNGE_S * 2))))
        if t < self.shake_until:
            c = add(c, (0.06 * math.sin(t * 90), 0, 0.04 * math.cos(t * 70)))
        return c, u, v


@dataclass
class Act:
    dur: float
    start: object = None                  # callable(), run when the act begins


class VoidTable(QWidget):
    """The window. Create it with `open_table()` so something owns it."""

    def __init__(self, seed: int | None = None, parent=None, dialogue: Dialogue | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("The Puppet Master")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setMinimumSize(640, 360)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.game = Game(seed)
        self.dlg = dialogue or Dialogue(seed=seed)
        self.t = 0.0
        self.vcards: dict[int, VCard] = {}
        self.acts: deque[Act] = deque()
        self.act_end = -1.0
        self.selected: int | None = None
        self.sacrifices: list[int] = []
        self.hover = None                 # ("card", uid) | ("slot", lane) | ("bell",) | ("deck",) | ("votary",)
        self.hits: list[tuple[tuple, QPolygonF]] = []
        self.hint = ""
        self.captions: deque[tuple[str, str]] = deque()
        self.caption: str = ""
        self.caption_until = -1.0
        self.mood: Mood = MOODS["calm"]
        self.mood_t0 = -9.0
        self.scale_shown = 0.0
        self.scale_target = 0.0
        self.scale_glow = 0.0
        self.remnants_shown = 0
        self.bell_t0 = -9.0
        self.over = False
        self.last_input_t = 0.0
        self.idle_said_turn = 0
        self.said_this_phase: set[str] = set()
        self.played_lines: set[str] = set()
        self.frame = None
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self._begin()

    # ── lifecycle ────────────────────────────────────────────────────────
    def _begin(self):
        self.say("welcome")
        self.say("rules")
        self.say("rules")
        self.enqueue(self.game.start())
        self.timer.start()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    # ── his voice ────────────────────────────────────────────────────────
    def say(self, key: str, once_per_phase: bool = False, **holes):
        if once_per_phase:
            if key in self.said_this_phase:
                return
            self.said_this_phase.add(key)
        got = self.dlg.line(key, **holes)
        if got and len(self.captions) < 3:
            self.captions.append(got)

    def _speech_tick(self):
        if self.caption and self.t < self.caption_until:
            return
        self.caption = ""
        if self.captions:
            text, emotion = self.captions.popleft()
            self.caption = text
            self.mood = MOODS.get(emotion, MOODS["calm"])
            self.mood_t0 = self.t
            self.caption_until = self.t + self.mood.hold_ms / 1000.0 + 0.3

    def _mood_strength(self) -> float:
        k = self.t - self.mood_t0
        hold = self.mood.hold_ms / 1000.0
        if k < 0 or k > hold:
            return 0.0
        return 1.0 if k < hold * 0.6 else 1.0 - (k - hold * 0.6) / (hold * 0.4)

    # ── acts: the event queue as animation ───────────────────────────────
    def busy(self) -> bool:
        return bool(self.acts) or self.t < self.act_end

    def _act(self, dur: float, start=None):
        self.acts.append(Act(dur, start))

    def _acts_tick(self):
        while self.t >= self.act_end and self.acts:
            act = self.acts.popleft()
            if act.start:
                act.start()
            self.act_end = self.t + act.dur

    def enqueue(self, events):
        g = self.game
        sac_count = 0
        for e in events:
            k = e.kind
            if k == "draw":
                card, source = e["card"], e["source"]
                self._act(DEAL_S, lambda c=card, s=source: self._deal(c, s))
                self._act(0, lambda s=source: self.say("draw_" + s))
            elif k == "sacrifice":
                sac_count += 1
                self._act(FADE_S, lambda c=e["card"]: self._kill(c, ember=True))
            elif k == "play":
                card, lane = e["card"], e["lane"]
                self._act(PLAY_S, lambda c=card, l=lane, n=sac_count: self._play(c, l, n))
                sac_count = 0
            elif k == "remnants":
                self._act(0, lambda n=e["total"]: setattr(self, "remnants_shown", n))
            elif k == "bell":
                self._act(0.5, self._ring)
            elif k == "strike":
                self._act(LUNGE_S * 2, lambda ev=e: self._strike(ev))
            elif k == "scale":
                self._act(0.35, lambda v=e["value"]: self._scale(v))
            elif k == "die":
                card, cause = e["card"], e["cause"]
                self._act(FADE_S, lambda c=card, why=cause: self._die(c, why))
            elif k == "return":
                self._act(DEAL_S, lambda c=e["card"]: self._return(c))
            elif k == "grow":
                self._act(GROW_S, lambda c=e["card"], was=e["was"]: self._grow(c, was))
            elif k == "his_turn":
                self._act(0.3, lambda: self.said_this_phase.clear())
            elif k == "advance":
                self._act(MOVE_S, lambda c=e["card"], l=e["lane"]: self._advance(c, l))
            elif k == "commit":
                self._act(MOVE_S, lambda c=e["card"], l=e["lane"]: self._commit(c, l))
            elif k == "your_turn":
                self._act(0.1, lambda turn=e["turn"]: self._your_turn(turn))
            elif k == "game_over":
                self._act(0.6, lambda w=e["winner"]: self._game_over(w))

    # act starts
    def _deal(self, card: Card, source: str):
        base = r3.DECK if source == "deck" else r3.VOTARIES
        start = (add(base, (0, 0.4, 0)), mul(r3.FLAT_U, 0.8), mul(r3.FLAT_V, 0.8))
        vc = VCard(card, start, start, card.power, card.health, where="hand")
        self.vcards[card.uid] = vc
        self._layout_hand(force=True)

    def _play(self, card: Card, lane: int, sacrificed: int):
        vc = self.vcards[card.uid]
        vc.where, vc.lane = "you", lane
        vc.go(self._slot_pose(r3.ROW_YOU, lane), self.t, PLAY_S, arc=1.4)
        self.selected, self.sacrifices = None, []
        if sacrificed >= 2:
            self.say("sacrifice_many")
        elif sacrificed == 1:
            self.say("sacrifice")
        key = "play_" + card.defn.id
        if self.dlg.has(key) and key not in self.played_lines:
            self.played_lines.add(key)
            self.say(key, name=card.name)
        elif card.defn.cost >= 3:
            self.say("play_big", name=card.name)
        elif sacrificed == 0 and card.defn.cost == 0 and card.defn.id != "votary":
            self.say("play_small", name=card.name)
        self._layout_hand()

    def _kill(self, card: Card, ember: bool = False):
        vc = self.vcards.get(card.uid)
        if vc is None:
            return
        vc.where = "gone"
        vc.flash_until = self.t + 0.25
        if ember:
            vc.edge = QColor(EMBER)
        vc.fade(0.0, FADE_S)
        vc.go((add(vc.pose[0], (0, 0.5, 0)), vc.pose[1], vc.pose[2]), self.t, FADE_S)

    def _ring(self):
        self.bell_t0 = self.t
        self.selected, self.sacrifices = None, []
        self.said_this_phase.clear()

    def _strike(self, e):
        attacker = self.vcards.get(e["card"].uid)
        if attacker is None:
            return
        toward = -1.0 if e["card"].owner == YOU else 1.0
        dx = (r3.LANES[e["target_lane"]] - r3.LANES[e["lane"]]) * 0.5
        attacker.lunge = (dx, 0.35 if e.get("flew") else 0.15, toward * 1.1)
        attacker.lunge_t0 = self.t
        if e["direct"]:
            self.scale_glow = 1.0
            self.say("hit_him" if e["card"].owner == YOU else "hit_you", once_per_phase=True)
        else:
            d = self.vcards.get(e["defender"].uid)
            if d is not None:
                QTimer.singleShot(int(LUNGE_S * 1000), lambda d=d, hp=e["hp_after"]: self._wound(d, hp))

    def _wound(self, vc: VCard, hp: int):
        vc.shown_health = hp
        vc.shake_until = self.t + 0.3

    def _scale(self, value: int):
        self.scale_target = value
        if not self.over:
            if value >= SCALE_TO_WIN - 1:
                self.say("close_you", once_per_phase=True)
            elif value <= -(SCALE_TO_WIN - 1):
                self.say("close_him", once_per_phase=True)

    def _die(self, card: Card, cause: str):
        self._kill(card)
        if cause == "venom":
            self.say("venom", once_per_phase=True)
        elif card.owner == HIM:
            self.say("kill_his", once_per_phase=True)
        else:
            self.say("kill_yours", once_per_phase=True)

    def _return(self, card: Card):
        start = (add(r3.slot_center(r3.ROW_YOU, 0), (0, 1.2, 0)), r3.FLAT_U, r3.FLAT_V)
        vc = VCard(card, start, start, card.power, card.health, where="hand", opacity=0.0)
        vc.fade(1.0, DEAL_S)
        self.vcards[card.uid] = vc
        self._layout_hand(force=True)
        self.say("undying")

    def _grow(self, card: Card, was: Card):
        old = self.vcards.pop(was.uid, None)
        pose = old.pose if old else self._slot_pose(r3.ROW_YOU if card.owner == YOU else r3.ROW_HIM, 0)
        vc = VCard(card, pose, pose, card.power, card.health, where="you" if card.owner == YOU else "him",
                   lane=old.lane if old else 0)
        vc.flash_until = self.t + GROW_S
        self.vcards[card.uid] = vc
        self.say("grow")

    def _advance(self, card: Card, lane: int):
        vc = self.vcards.get(card.uid)
        if vc is None:
            return
        vc.where, vc.lane = "him", lane
        vc.fade(1.0, MOVE_S)
        vc.go(self._slot_pose(r3.ROW_HIM, lane), self.t, MOVE_S, arc=0.3)

    def _commit(self, card: Card, lane: int):
        start = ((r3.LANES[lane] * 0.6, FAR_AWAY[1], FAR_AWAY[2]), r3.FLAT_U, r3.FLAT_V)
        vc = VCard(card, start, start, card.power, card.health, where="next", lane=lane, opacity=0.0)
        vc.fade(0.7, MOVE_S)
        vc.go(self._slot_pose(r3.ROW_NEXT, lane), self.t, MOVE_S)
        self.vcards[card.uid] = vc
        key = "commit_" + card.defn.id
        if key not in self.played_lines:
            self.played_lines.add(key)
            self.say(key, name=card.name)

    def _your_turn(self, turn: int):
        self.said_this_phase.clear()
        self.idle_said_turn = 0
        self.last_input_t = self.t
        if turn == 1:
            self.say("first_turn")

    def _game_over(self, winner: str):
        self.over = True
        self.captions.clear()
        self.caption = ""
        self.say("win" if winner == YOU else "lose")

    # ── layout ───────────────────────────────────────────────────────────
    def _slot_pose(self, row: float, lane: int) -> Pose:
        return r3.slot_center(row, lane), r3.FLAT_U, r3.FLAT_V

    def _hand_cards(self) -> list[VCard]:
        order = {c.uid: i for i, c in enumerate(self.game.hand)}
        return sorted((v for v in self.vcards.values() if v.where == "hand"),
                      key=lambda v: order.get(v.uid, 99))

    def _layout_hand(self, force: bool = False):
        hand = self._hand_cards()
        n = len(hand)
        for i, vc in enumerate(hand):
            k = i - (n - 1) / 2
            lift = 0.0
            if self.selected == vc.uid:
                lift = 0.55
            elif self.hover == ("card", vc.uid) and not self.busy():
                lift = 0.28
            pose = r3.hand_pose(k * min(1.0, 4.0 / max(n, 1)), lift)
            if force or pose != vc.dst:
                vc.go(pose, self.t, HAND_S if not force else DEAL_S, 0.0)

    # ── the clock ────────────────────────────────────────────────────────
    def _tick(self):
        dt = TICK_MS / 1000.0
        self.t += dt
        self._acts_tick()
        self._speech_tick()
        self._layout_hand()
        for vc in list(self.vcards.values()):
            vc.advance(self.t, dt)
            if vc.where == "gone" and vc.opacity <= 0.0:
                del self.vcards[vc.uid]
        self.scale_shown += (self.scale_target - self.scale_shown) * min(1.0, dt * 6)
        self.scale_glow = max(0.0, self.scale_glow - dt * 1.5)
        if (not self.over and not self.busy() and self.game.phase in ("play", "draw")
                and self.t - self.last_input_t > IDLE_LINE_S and self.idle_said_turn != self.game.turn):
            self.idle_said_turn = self.game.turn
            self.say("idle")
        self.frame = self._render()
        self.update()

    # ── drawing ──────────────────────────────────────────────────────────
    def _render(self):
        g = self.game
        strength = self._mood_strength()
        cam = r3.default_camera(self.t, self.mood.shake * strength)
        fr = r3.Frame(cam)
        self.hits = []
        r3.draw_void(fr, self.t)
        halo = tuple(int(a + (b - a) * strength) for a, b in zip(MOODS["calm"].halo, self.mood.halo))
        r3.draw_him(fr, self.t, self.mood.flicker * strength, int(self.t * 8), halo)
        highlight = set()
        if self.selected is not None and not self.busy():
            for lane in range(LANES):
                if not g.why_not(self.selected, lane, self.sacrifices):
                    highlight.add(("you", lane))
        r3.draw_slots(fr, highlight)
        r3.draw_scale(fr, self.scale_shown, self.scale_glow)
        can_act = not self.busy() and not self.over
        ringing = self.t - self.bell_t0
        bell = r3.draw_bell(fr, can_act and g.phase == "play", ringing if 0 <= ringing < 1 else 0.0)
        if bell:
            self.hits.append((("bell",), bell))
        must_draw = can_act and g.phase == "draw"
        deck = r3.draw_pile(fr, r3.DECK, len(g.deck), art.card_back(), must_draw and bool(g.deck))
        if deck:
            self.hits.append((("deck",), deck))
        vot = r3.draw_pile(fr, r3.VOTARIES, g.votaries, art.card_face(CARDS["votary"]), must_draw and g.votaries > 0)
        if vot:
            self.hits.append((("votary",), vot))
        r3.draw_remnants(fr, self.remnants_shown)
        # slots you may play into are also click targets
        if self.selected is not None:
            for lane in range(LANES):
                poly = r3.slot_polygon(fr, r3.ROW_YOU, lane)
                if poly:
                    self.hits.append((("slot", lane), poly))
        # cards, far to near
        order = sorted(self.vcards.values(), key=lambda v: -cam.depth(v.pose[0]))
        for vc in order:
            c, u, v = vc.drawn_pose(self.t)
            edge = vc.edge
            if vc.lane in self.sacrifices and vc.where == "you":
                edge = EMBER
                c = add(c, (0, 0.15, 0))
            elif self.selected == vc.uid or self.t < vc.flash_until:
                edge = PEAK
            face = art.card_face(vc.card.defn, vc.shown_power, vc.shown_health)
            poly = fr.draw_card(c, u, v, face, art.card_back(), vc.opacity, edge)
            if poly and vc.where != "gone":
                self.hits.append((("card", vc.uid), poly))
        # his caption, burned into the tube between his face and the board
        if self.caption:
            fr.text(130, 226, W - 260, 44, self.caption.upper(), PEAK, 13)
        # a quiet hint for the hands
        hint = self.hint or self._standing_hint()
        if hint:
            fr.text(W - 470, H - 24, 450, 18, hint, MID, 9, bold=False,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, spacing=1)
        self._draw_inspect(fr)
        img = fr.end()
        return r3.finish(img, self.mood.dim * strength)

    def _standing_hint(self) -> str:
        g = self.game
        if self.over:
            return "CLICK TO LEAVE THE TABLE"
        if self.busy():
            return ""
        if g.phase == "draw":
            return "DRAW: YOUR DECK, OR A VOTARY"
        if self.selected is not None:
            card = g._hand_card(self.selected)
            d = card.defn
            if d.cost_kind == OFFER and d.cost:
                worth = sum(g.offering_worth(g.rows[YOU][s]) for s in self.sacrifices)
                return f"OFFER {d.cost}: CLICK YOUR CARDS TO OFFER THEM ({worth} OF {d.cost}), THEN A LIT LANE"
            return "CLICK A LIT LANE"
        return "PLAY WHAT YOU CAN. THEN RING THE BELL."

    def _draw_inspect(self, fr: r3.Frame):
        if not self.hover or self.hover[0] != "card":
            return
        vc = self.vcards.get(self.hover[1])
        if vc is None:
            return
        d = vc.card.defn
        p = fr.p
        x, y, w = 14, H - 150, 300
        lines = [(d.name, PEAK, 12, True)]
        cost = ("FREE" if not d.cost else
                f"COST: {d.cost} {'REMNANT' if d.cost_kind == REMNANT else 'OFFERING'}{'S' if d.cost > 1 else ''}")
        lines.append((f"{vc.shown_power} POWER   {vc.shown_health} HEALTH   {cost}", BRIGHT, 9, False))
        for s in d.sigils:
            name, rule = SIGILS[s]
            lines.append((f"{name}: {rule}", BRIGHT, 9, False))
        if d.note:
            lines.append((d.note, MID, 9, False))
        rows = [(22 if ln[2] > 10 else (30 if len(ln[0]) > 46 else 16)) for ln in lines]
        h = 16 + sum(rows)
        y = 14
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(1, 6, 3, 200)); p.drawRect(QRectF(x, y, w, h))
        p.setPen(QColor(MID)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(QRectF(x, y, w, h))
        cy = y + 8
        for (text, color, size, bold), hh in zip(lines, rows):
            fr.text(x + 10, cy, w - 20, hh, text, color, size, bold,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 1 if bold else 0)
            cy += hh

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), VOID)
        if self.frame is None:
            return
        rw, rh = self.width(), self.height()
        k = min(rw / W, rh / H)
        dw, dh = int(W * k), int(H * k)
        ox, oy = (rw - dw) // 2, (rh - dh) // 2
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(QRectF(ox, oy, dw, dh), self.frame)
        self._view = (ox, oy, k)

    # ── input ────────────────────────────────────────────────────────────
    def _to_frame(self, pos) -> QPointF:
        ox, oy, k = getattr(self, "_view", (0, 0, 1.0))
        return QPointF((pos.x() - ox) / k, (pos.y() - oy) / k)

    def _hit(self, pt: QPointF):
        for key, poly in reversed(self.hits):          # drawn last = nearest
            if poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
                return key
        return None

    def mouseMoveEvent(self, event):
        self.hover = self._hit(self._to_frame(event.position()))

    def leaveEvent(self, event):
        self.hover = None

    def mousePressEvent(self, event):
        self.last_input_t = self.t
        self.hint = ""
        if self.over:
            if not self.captions and self.t > self.caption_until - 1.0:
                self.close()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.selected, self.sacrifices = None, []
            return
        if self.busy():
            return
        hit = self._hit(self._to_frame(event.position()))
        if hit is None:
            return
        try:
            self._click(hit)
        except IllegalMove as why:
            self.hint = str(why).upper()

    def _click(self, hit):
        g = self.game
        kind = hit[0]
        if kind == "bell":
            self.enqueue(g.ring_bell())
        elif kind in ("deck", "votary"):
            self.enqueue(g.draw(kind))
        elif kind == "slot":
            if self.selected is not None:
                self.enqueue(g.play(self.selected, hit[1], self.sacrifices))
        elif kind == "card":
            vc = self.vcards.get(hit[1])
            if vc is None:
                return
            if vc.where == "hand":
                if self.selected == vc.uid:
                    self.selected, self.sacrifices = None, []
                elif g.phase == "draw":
                    raise IllegalMove("Draw first.")
                else:
                    self.selected, self.sacrifices = vc.uid, []
                    if not g.can_afford(vc.uid):
                        self.selected = None
                        d = vc.card.defn
                        raise IllegalMove(f"It demands {d.cost} {'remnants' if d.cost_kind == REMNANT else 'offerings'}. "
                                          f"You cannot pay.")
            elif vc.where == "you" and self.selected is not None:
                d = g._hand_card(self.selected).defn
                if d.cost_kind != OFFER or not d.cost:
                    raise IllegalMove("It asks for no offering.")
                if vc.lane in self.sacrifices:
                    self.sacrifices.remove(vc.lane)
                else:
                    self.sacrifices.append(vc.lane)

    def keyPressEvent(self, event):
        self.last_input_t = self.t
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.over or self.selected is None:
                self.close()
            else:
                self.selected, self.sacrifices = None, []
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.busy() and not self.over:
            try:
                self.enqueue(self.game.ring_bell())
            except IllegalMove as why:
                self.hint = str(why).upper()
        else:
            super().keyPressEvent(event)


_TABLE: VoidTable | None = None


def open_table(seed: int | None = None, parent=None) -> VoidTable:
    """Open (or raise) the table. Module-level ownership so Qt cannot collect it."""
    global _TABLE
    if _TABLE is not None and _TABLE.isVisible():
        _TABLE.raise_(); _TABLE.activateWindow()
        return _TABLE
    _TABLE = VoidTable(seed, parent)
    _TABLE.resize(1280, 720)
    _TABLE.showMaximized()
    return _TABLE
