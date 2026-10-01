"""The road, drawn: everything between fights, plus the book.

A mixin for VoidTable. The table (window.py) owns the fight; this owns the
scenes around it - three doors, a choice of cards, the fire, the altar, the
forge where the dead make their card, the moment he keeps it - and the
rule book you look down at from your hand. All of it is objects in the
same void, drawn with the same renderer; the run itself is run.py.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPolygonF

from . import art, render3d as r3
from .art import BRIGHT, DIM, EMBER, MID, PEAK
from .cards import CARDS, OFFER, REMNANT, SIGILS
from .render3d import H, W, add, mul, norm
from .run import CANDLES, ROAD_LENGTH, Run

DOOR_X = (-3.4, 0.0, 3.4)
DOOR_Z = 0.4
DOOR_LABEL = {"fight": "THE TABLE", "choice": "THREE CARDS", "rare": "SOMETHING OLD", "fire": "A FIRE",
              "altar": "THE STONE", "boss": "HIM"}
PICK_X = (-1.7, 0.0, 1.7)
FAN_Z, FAN_Y = 4.6, 0.9
LAMP_X = -6.6
BOOK_PER_PAGE = 4
DIGITIZE_S = 4.5
FIRE_AGAIN_DEATHS = 5                 # a second rest at the same fire is only offered after this many deaths


class RoadScenes:
    # ── state ────────────────────────────────────────────────────────────
    def _init_run(self, seed, memory):
        self.run = Run(seed, memory)
        self.scene = "road"               # road | fight | pick | fire | altar | forge | digitize
        self.pick = 0
        self.after_fight = ""
        self.forge_step = 0               # 0 cost, 1 numbers, 2 marks, 3 name
        self.forge_from = [None, None, None]
        self.forge_name = ""
        self.forge_first = False
        self.digitize_t0 = -9.0
        self.peek = False                 # the hand pulled down, nothing else
        self.book: int | None = None      # page of the rule book, or None
        self.seen_this_fight: set[str] = set()
        self.card_remark_said = False         # he remarks on one played card per match
        self.first_sacrifice_said = False
        self.road_opened = False              # the road's first doors have been narrated
        self.warmed: str = ""                 # the last card warmed at this fire, for leaving
        self.show_draw_arrow = False        # the tutorial's pointer to the piles
        self.scene_t0 = 0.0

    def _save_memory(self):
        self.settings["memory"] = self.run.memory
        from .window import save_settings
        save_settings(self.settings)

    # ── moving along the road ────────────────────────────────────────────
    def road_show(self):
        """The doors ahead. One door (the first table, or him) opens itself."""
        offers = self.run.offer()
        self.scene, self.pick, self.scene_t0 = "road", 0, self.t
        if len(offers) == 1:
            if offers[0].kind == "boss":
                self.say("scene_boss")
            self.road_pick()
            return
        if self.run.step == 1 and not self.road_opened:
            self.road_opened = True
            self.say("scene_road_first")           # once per run: he recalls your story
        else:
            self.say("scene_road")

    def road_pick(self):
        stop = self.run.choose(self.pick)
        k = stop.kind
        if k in ("fight", "boss"):
            self.begin_fight()
        elif k in ("choice", "rare"):
            self.scene, self.pick, self.scene_t0 = "pick", 1, self.t
            self.say("scene_rare" if k == "rare" else "scene_choice")
        elif k == "fire":
            self.scene, self.pick, self.scene_t0 = "fire", 0, self.t
            self.say("scene_fire", what=stop.fire)
        elif k == "altar":
            self.scene, self.pick, self.scene_t0 = "altar", 0, self.t
            self.forge_from = [None, None, None]
            self.say("scene_altar")

    def begin_fight(self):
        run = self.run
        self.game = run.game
        self.scene, self.scene_t0 = "fight", self.t
        self.vcards.clear(); self.acts.clear(); self.act_end = -1.0
        self.selected, self.sacrifices, self.cursor = None, [], None
        self.view = self.view_prev = "hand_low"; self.peek = False; self.book = None
        self.over = False; self.after_fight = ""; self.opening_done = False
        self.scale_shown = self.scale_target = 0.0; self.remnants_shown = 0
        self.seen_this_fight = set(); self.said_this_phase = set(); self.card_remark_said = False
        if run.stop and run.stop.kind == "boss":
            self.say("boss_welcome")
        elif run.fights == 0:
            self.say("welcome")                      # the rules come when you reach for things
        else:
            self.say("welcome_again")
        self.enqueue(self.game.start())

    def fight_ended(self, winner: str):
        """The table's game is over: settle it with the run and let him speak."""
        result = self.run.settle_fight()
        self.after_fight = result
        self._save_memory()
        if result in ("won", "run_won"):
            first_ever = self.run.memory["wins"] == 0 and self.run.fights == 1 and self.run.memory["runs"] == 1
            if result == "run_won":
                self.say("run_won")
            elif first_ever:
                self.say("first_win")
            else:
                self.say("win")
            over = max(0, self.game.scale - 5)
            if over and result != "run_won":
                self.say("teeth", n=over)
        elif result == "lost":
            self.say("lose"); self.say("candle_out")
        else:
            self.say("lose"); self.say("dead")

    def after_fight_go(self):
        """Space or a click once his last word is out."""
        r = self.after_fight
        self.over = False
        if r in ("won", "lost"):
            self.road_show()
        elif r == "dead":
            self.scene, self.pick, self.scene_t0 = "forge", 0, self.t
            self.forge_step, self.forge_from, self.forge_name = 0, [None, None, None], ""
            self.forge_first = self.run.memory["deaths"] <= 1        # the first death of all
            if self.forge_first:
                self.say("deathcard_first_time")
                self.say("deathcard_cost_first_time", part="head")
            else:
                self.say("deathcard")
                self.say("deathcard_cost")
        else:
            self.close()

    # ── the other stops ──────────────────────────────────────────────────
    def pick_go(self):
        card = self.run.take_card(self.pick)
        self.say("card_taken")
        self.road_show()
        return card

    def fire_go(self):
        if not self.run.deck:
            return
        card = self.run.deck[self.pick]
        times = self.run.stop.rests.get(self.pick, 0) if self.run.stop else 0
        if times >= 1:
            if self.run.memory["deaths"] < FIRE_AGAIN_DEATHS:
                return                          # not yet: the survivors keep their manners
            self.say("fire_again")
        out = self.run.rest(self.pick)
        self.warmed = card.defn.name.title() if out == "buffed" else ""
        self.say("fire_buffed" if out == "buffed" else "fire_eaten", name=card.defn.name.title(),
                 what=self.run.stop.fire if self.run.stop else "power")
        if out == "eaten" or not self.run.deck:
            self.pick = 0
            self.road_show()
        self.pick = min(self.pick, max(0, len(self.run.deck) - 1))

    def altar_go(self):
        if len(self.run.deck) < 2:
            self.road_show(); return
        if self.forge_from[0] is None:
            self.forge_from[0] = self.pick
            return
        if self.pick == self.forge_from[0]:
            return
        self.run.altar(self.forge_from[0], self.pick)
        self.forge_from = [None, None, None]
        self.say("altar_done")
        self.road_show()

    def leave_stop(self):
        if self.scene == "fire" and self.warmed:
            self.say("fire_leave", name=self.warmed)
            self.warmed = ""
        if self.scene in ("fire", "altar"):
            self.road_show()

    # ── the forge and what follows ───────────────────────────────────────
    def forge_go(self):
        if self.forge_step >= 3:
            self.forge_finish()
            return
        dc = self.run.deck[self.pick]
        d = dc.defn
        self.forge_from[self.forge_step] = self.pick
        step = self.forge_step
        self.forge_step += 1
        first = self.forge_first
        if step == 0:                                          # the cost is chosen
            if first:
                self.say("deathcard_cost_first_time", part="tail", cost=d.cost, card=d.name.title())
                self.say("deathcard_power_first_time", part="head")
            else:
                self.say("deathcard_power")
        elif step == 1:                                        # the numbers are chosen
            if first:
                self.say("deathcard_power_first_time", part="tail", power=d.power + dc.power,
                         health=d.health + dc.health, card=d.name.title())
                self.say("deathcard_sigil_first_time", part="head")
            else:
                self.say("deathcard_sigil")
        else:                                                  # the marks are chosen
            sigils = tuple(dict.fromkeys(d.sigils + dc.sigils))
            names = [SIGILS[s][0].title() for s in sigils]
            if first and len(names) >= 2:
                self.say("deathcard_sigil_first_time_double", part="tail", sigil=names[0], sigil2=names[1],
                         card=d.name.title())
            elif first and names:
                self.say("deathcard_sigil_first_time", part="tail", sigil=names[0], card=d.name.title())
            self.say("deathcard_before_named_first_time" if first else "deathcard_before_named")

    def forge_finish(self):
        d = self.run.forge_deathcard(self.forge_name, *self.forge_from)
        self._save_memory()
        self.say("deathcard_post_named", name=d.name)
        self.say("digitize")
        self.scene, self.digitize_t0 = "digitize", self.t

    def forge_type(self, text: str):
        if self.forge_step == 3 and len(self.forge_name) < 14:
            for ch in text:
                if ch.isalnum() or ch in " '-":
                    self.forge_name += ch.upper()

    def forge_backspace(self):
        self.forge_name = self.forge_name[:-1]

    # ── input for the scenes ─────────────────────────────────────────────
    def scene_count(self) -> int:
        if self.scene == "road":
            return len(self.run.offers)
        if self.scene == "pick":
            return len(self.run.stop.cards) if self.run.stop else 0
        return len(self.run.deck)

    def scene_key(self, key) -> bool:
        """Keys outside the fight. True when the key was used."""
        s = self.scene
        if s == "forge" and self.forge_step == 3:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.forge_name.strip():
                    self.forge_finish()
            elif key == Qt.Key.Key_Backspace:
                self.forge_backspace()
            return True                                   # letters arrive through forge_type
        if s == "digitize":
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Return) and self.t - self.digitize_t0 > DIGITIZE_S:
                self.close()
            return True
        if s not in ("road", "pick", "fire", "altar", "forge"):
            return False
        n = max(1, self.scene_count())
        if key in (Qt.Key.Key_A, Qt.Key.Key_Left):
            self.pick = (self.pick - 1) % n
        elif key in (Qt.Key.Key_D, Qt.Key.Key_Right):
            self.pick = (self.pick + 1) % n
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.scene_go()
        elif key == Qt.Key.Key_Tab:
            self.leave_stop()
        return True

    def scene_go(self):
        {"road": self.road_pick, "pick": self.pick_go, "fire": self.fire_go,
         "altar": self.altar_go, "forge": self.forge_go}[self.scene]()

    def scene_click(self, hit) -> bool:
        if hit and hit[0] in ("door", "pick", "deckcard"):
            self.pick = hit[1]
            self.scene_go()
            return True
        if hit and hit[0] == "leave":
            self.leave_stop()
            return True
        return False

    # ── the book ─────────────────────────────────────────────────────────
    def book_pages(self) -> int:
        return (len(SIGILS) + BOOK_PER_PAGE * 2 - 1) // (BOOK_PER_PAGE * 2)

    def open_book_at(self, sigil: str | None = None):
        keys = list(SIGILS)
        page = 0
        if sigil in keys:
            page = keys.index(sigil) // (BOOK_PER_PAGE * 2)
        self.book = page
        self.peek = True

    def book_key(self, key) -> bool:
        if self.book is None:
            return False
        if key in (Qt.Key.Key_D, Qt.Key.Key_Right):
            self.book = min(self.book_pages() - 1, self.book + 1)
        elif key in (Qt.Key.Key_A, Qt.Key.Key_Left):
            self.book = max(0, self.book - 1)
        elif key in (Qt.Key.Key_W, Qt.Key.Key_Escape, Qt.Key.Key_Q, Qt.Key.Key_Up):
            self.book = None; self.peek = False
            self.set_view("hand_low")                       # up from the book: the hand at rest
        return True

    def _draw_book(self, fr: r3.Frame):
        keys = list(SIGILS)
        p = fr.p
        x, y, w, h = 90, 40, W - 180, H - 100
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(1, 6, 3, 236)); p.drawRect(QRectF(x, y, w, h))
        p.setPen(QColor(BRIGHT)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(QRectF(x, y, w, h))
        p.setPen(QColor(MID)); p.drawLine(QPointF(x + w / 2, y + 12), QPointF(x + w / 2, y + h - 12))
        fr.text(x, y + 8, w, 20, "THE BOOK OF MARKS", PEAK, 12)
        start = (self.book or 0) * BOOK_PER_PAGE * 2
        for i in range(BOOK_PER_PAGE * 2):
            k = start + i
            if k >= len(keys):
                break
            col = 0 if i < BOOK_PER_PAGE else 1
            row = i % BOOK_PER_PAGE
            cx = x + 24 + col * (w / 2)
            cy = y + 44 + row * 96
            icon = art.sigil_icon(keys[k], 2)
            p.drawImage(int(cx), int(cy + 6), icon)
            name, rule = SIGILS[keys[k]]
            fr.text(cx + 56, cy, w / 2 - 90, 20, name, PEAK, 11, True,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 1)
            fr.text(cx + 56, cy + 22, w / 2 - 90, 56, rule, MID, 9, False,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, 0)
        # each page numbered in its own bottom corner; the turn keys in the top corners
        left_no = (self.book or 0) * 2 + 1
        fr.text(x + 16, y + h - 26, 60, 18, str(left_no), DIM, 9, False, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 1)
        fr.text(x + w - 76, y + h - 26, 60, 18, str(left_no + 1), DIM, 9, False, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 1)
        if (self.book or 0) > 0:
            fr.page_icon(x + 22, y + 20, "left", 0.9, MID); fr.keycap(x + 44, y + 20, "A", 0.9, MID)
        if (self.book or 0) < self.book_pages() - 1:
            fr.keycap(x + w - 44, y + 20, "D", 0.9, MID); fr.page_icon(x + w - 22, y + 20, "right", 0.9, MID)

    # ── drawing the road ─────────────────────────────────────────────────
    def _draw_progress(self, fr: r3.Frame):
        """Lamps along the left edge, one per stop, lit as you pass them; his
        eye at the far end. The way to tell how close he is."""
        run = self.run
        n = ROAD_LENGTH
        for i in range(n + 1):
            z = 3.6 - i * (10.8 / n)
            c = (LAMP_X, 0.0, z)
            lit = i < run.step
            last = i == n
            if last:
                col = EMBER if lit else QColor(120, 60, 40)
                fr.polyline3(fr.ring(c, 0.5, 12), col, 1.4)
                q = fr.cam.project(add(c, (0, 0.15, 0)))
                if q:
                    fr.p.setPen(Qt.PenStyle.NoPen); fr.p.setBrush(EMBER if lit else QColor(140, 70, 50))
                    fr.p.drawEllipse(QPointF(q[0], q[1]), 3.5, 3.5)
            else:
                fr.polyline3(fr.ring(c, 0.28, 10), PEAK if lit else DIM, 1.4 if lit else 0.9)
                if lit:
                    q = fr.cam.project(add(c, (0, 0.12, 0)))
                    if q:
                        fr.p.setPen(Qt.PenStyle.NoPen); fr.p.setBrush(PEAK)
                        fr.p.drawEllipse(QPointF(q[0], q[1]), 2.5, 2.5)
            if i < n:
                fr.line3(add(c, (0, 0, -0.35)), (LAMP_X, 0.0, z - 10.8 / n + 0.35), DIM, 0.8)

    def _draw_candles(self, fr: r3.Frame):
        """Your lives: two small flames at your right hand."""
        t = self.t
        for i, (cx, cz) in enumerate(((5.3, -1.4), (6.0, -1.9))):
            b = (cx, 0, cz)                                  # behind the bell, off the piles, on stands
            fr.line3(b, add(b, (0, 0.9, 0)), DIM, 1.0)
            fr.polyline3(fr.ring(b, 0.3, 8), DIM)
            b = add(b, (0, 0.9, 0))
            fr.polyline3(fr.ring(b, 0.14, 8), MID); fr.polyline3(fr.ring(add(b, (0, 0.7, 0)), 0.14, 8), MID)
            for a in range(0, 360, 90):
                d = (0.14 * math.cos(math.radians(a)), 0, 0.14 * math.sin(math.radians(a)))
                fr.line3(add(b, d), add(add(b, (0, 0.7, 0)), d), MID, 1.0)
            if i < self.run.candles:
                fl = 0.26 + 0.05 * math.sin(t * 9 + i * 2)
                tip = fr.cam.project(add(b, (0.03 * math.sin(t * 7 + i), 0.7 + fl, 0)))
                base = fr.cam.project(add(b, (0, 0.72, 0)))
                if tip and base:
                    p = fr.p
                    p.setPen(Qt.PenStyle.NoPen); p.setBrush(EMBER)
                    p.drawPolygon(QPolygonF([QPointF(tip[0], tip[1]), QPointF(base[0] + 4, base[1]), QPointF(base[0] - 4, base[1])]))

    def _draw_arch(self, fr: r3.Frame, x: float, label: str, lit: bool):
        base = (x, 0.0, DOOR_Z)
        col = PEAK if lit else MID
        hw, hh = 1.0, 2.2
        for sx in (-hw, hw):
            fr.line3(add(base, (sx, 0, 0)), add(base, (sx, hh, 0)), col, 1.6 if lit else 1.1)
        pts = [add(base, (hw * math.cos(math.pi - a * math.pi / 8), hh + hw * math.sin(a * math.pi / 8), 0)) for a in range(9)]
        fr.polyline3(pts, col, 1.6 if lit else 1.1)
        fr.polyline3(fr.ring(base, 1.2, 12), DIM, 0.9)
        q = fr.cam.project(add(base, (0, 1.1, 0)))
        if q:
            fr.text(q[0] - 90, q[1] - 10, 180, 20, label, col, 10, True, spacing=2)
        pr = fr.quad3(add(base, (0, hh / 2 + 0.3, 0)), (hw + 0.2, 0, 0), (0, hh / 2 + 0.6, 0))
        return QPolygonF([QPointF(a[0], a[1]) for a in pr]) if pr else None

    def _upright_pose(self, x: float, y: float, z: float, scale: float = 1.0):
        return (x, y, z), (r3.CW2 * scale, 0, 0), (0, r3.CH2 * scale, 0)

    def _fan_pose(self, i: int, n: int, lift: float = 0.0):
        k = i - (n - 1) / 2
        spread = min(0.95, 5.2 / max(n, 1))
        ang = -k * 0.08
        hs = 0.62 if n <= 7 else 0.5
        u = (r3.CW2 * hs * math.cos(ang), r3.CW2 * hs * math.sin(ang), 0)
        v = mul(norm((-math.sin(ang) * 0.9, math.cos(ang) * 0.86, -0.5)), r3.CH2 * hs)
        return (k * spread, FAN_Y + lift, FAN_Z - abs(k) * 0.05), u, v

    def _draw_deck_fan(self, fr: r3.Frame, marks: dict[int, str] | None = None):
        deck = self.run.deck
        n = len(deck)
        order = sorted(range(n), key=lambda i: -abs(i - (n - 1) / 2))
        for i in order:
            dc = deck[i]
            lift = 0.35 if i == self.pick else 0.0
            c, u, v = self._fan_pose(i, n, lift)
            d = dc.defn
            face = art.card_face(d, d.power + dc.power, d.health + dc.health, d.sigils + dc.sigils)
            edge = PEAK if i == self.pick else BRIGHT
            if marks and i in marks:
                edge = EMBER
            poly = fr.draw_card(c, u, v, face, art.card_back(), 1.0, edge)
            if poly:
                self.hits.append((("deckcard", i), poly))
            if marks and i in marks:
                q = fr.cam.project(add(c, (0, r3.CH2 * 0.62 + 0.25, 0)))
                if q:
                    fr.text(q[0] - 60, q[1] - 9, 120, 18, marks[i], EMBER, 9, True, spacing=2)

    def _draw_leave(self, fr: r3.Frame):
        poly = self._draw_arch(fr, 5.2, "BACK TO THE ROAD", False)
        fr.label3((5.2, 0.35, DOOR_Z + 0.9), "TAB")
        if poly:
            self.hits.append((("leave",), poly))

    def _draw_fire(self, fr: r3.Frame):
        b = (0.0, 0.0, 0.6)
        fr.polyline3(fr.ring(b, 0.9, 12), MID, 1.0)
        for a in range(0, 360, 60):
            r = math.radians(a)
            fr.line3(add(b, (0.8 * math.cos(r), 0, 0.8 * math.sin(r))), add(b, (0.15 * math.cos(r + 1.2), 0.6, 0.15 * math.sin(r + 1.2))), BRIGHT, 1.2)
        t = self.t
        for k in range(3):
            fl = 1.1 + 0.25 * math.sin(t * (7 + k) + k)
            tip = fr.cam.project(add(b, (0.15 * math.sin(t * 5 + k * 2), 0.5 + fl, 0.1 * k - 0.1)))
            base = fr.cam.project(add(b, (0, 0.5, 0)))
            if tip and base:
                p = fr.p; p.setPen(Qt.PenStyle.NoPen)
                c = QColor(EMBER); c.setAlpha(160 - k * 40); p.setBrush(c)
                p.drawPolygon(QPolygonF([QPointF(tip[0], tip[1]), QPointF(base[0] + 14 - k * 3, base[1]), QPointF(base[0] - 14 + k * 3, base[1])]))
        stop = self.run.stop
        what = "+1 POWER" if stop and stop.fire == "power" else "+2 HEALTH"
        q = fr.cam.project(add(b, (0, 2.6, 0)))
        if q:
            fr.text(q[0] - 100, q[1] - 10, 200, 20, what, EMBER, 11, True, spacing=2)
        fr.label3((0.0, 0.0, 2.2), "SPACE")

    def _draw_altar(self, fr: r3.Frame):
        b = (0.0, 0.0, 0.4)
        top = add(b, (0, 0.8, 0))
        for dz in (-0.6, 0.6):
            for dx in (-1.4, 1.4):
                fr.line3(add(b, (dx, 0, dz)), add(top, (dx, 0, dz)), MID, 1.1)
        for y in (0.0, 0.8):
            pts = [add(b, (-1.4, y, -0.6)), add(b, (1.4, y, -0.6)), add(b, (1.4, y, 0.6)), add(b, (-1.4, y, 0.6))]
            fr.polyline3(pts + [pts[0]], BRIGHT if y else DIM, 1.2)
        step = "GIVER" if self.forge_from[0] is None else "TAKER"
        q = fr.cam.project(add(top, (0, 1.4, 0)))
        if q:
            fr.text(q[0] - 120, q[1] - 10, 240, 20, f"CHOOSE THE {step}", PEAK, 11, True, spacing=2)
        fr.label3((0.0, 0.0, 2.2), "SPACE")

    def _draw_forge(self, fr: r3.Frame):
        titles = ("WHOSE COST", "WHOSE NUMBERS", "WHOSE MARKS", "ITS NAME")
        step = self.forge_step
        q = fr.cam.project((0.0, 3.2, 0.4))
        if q:
            fr.text(q[0] - 200, q[1] - 12, 400, 24, titles[step], EMBER, 13, True, spacing=3)
        deck = self.run.deck
        if step == 3:
            # the card so far, and its name being typed
            c, s, g = (deck[i] for i in self.forge_from)
            d = art.C.CardDef("deathcard", self.forge_name or "?", s.defn.power + s.power, s.defn.health + s.health,
                              c.defn.cost, c.defn.cost_kind, tuple(dict.fromkeys(g.defn.sigils + g.sigils)), deathcard=True)
            face = art.card_face(d, sigils=d.sigils)
            fr.draw_card(*self._upright_pose(0.0, 1.5, 1.2, 1.1), face, art.card_back(), 1.0, EMBER)
            cursor = "_" if int(self.t * 2) % 2 == 0 else " "
            q = fr.cam.project((0.0, 3.55, 0.4))
            if q:
                fr.text(q[0] - 200, q[1] + 20, 400, 22, (self.forge_name + cursor), PEAK, 13, True, spacing=3)
                fr.text(q[0] - 200, q[1] + 44, 400, 16, "TYPE IT. ENTER.", DIM, 8, False, spacing=2)
        else:
            marks = {}
            for i, label in zip(self.forge_from, ("COST", "NUMBERS", "MARKS")):
                if i is not None:
                    marks[i] = label
            self._draw_deck_fan(fr, marks)
            fr.label3((0.0, 0.0, 2.2), "SPACE")

    def _draw_digitize(self, fr: r3.Frame):
        k = min(1.0, (self.t - self.digitize_t0) / DIGITIZE_S)
        e = r3.ease(k)
        d = self.run.deathcard
        if d is None:
            return
        start = self._upright_pose(0.0, 1.5, 1.2, 1.1)
        end = ((0.0, r3.FACE_CENTER[1] - 0.6, r3.FACE_CENTER[2] + 1.5), (r3.CW2 * 0.2, 0, 0), (0, r3.CH2 * 0.2, 0))
        c = r3.lerp(start[0], end[0], e)
        u = r3.lerp(start[1], end[1], e); v = r3.lerp(start[2], end[2], e)
        face = art.card_face(d, sigils=d.sigils)
        fr.draw_card(c, u, v, face, art.card_back(), 1.0 - 0.6 * e, EMBER)
        if k >= 1.0 and not self._talking() and not self.captions:
            fr.keycap(W / 2, H - 52, "SPACE", 0.8, MID, 9)

    # ── the frame for a scene ────────────────────────────────────────────
    def render_scene(self):
        strength = self._mood_strength()
        cam = r3.camera_between("hand", "hand", 1.0, self.t, 0.0)
        fr = r3.Frame(cam)
        self.hits = []
        r3.draw_void(fr, self.t)
        from .dialogue import MOODS
        halo = tuple(int(a + (b - a) * strength) for a, b in zip(MOODS["calm"].halo, self.mood.halo))
        flick = self.mood.flicker * strength
        if self.scene == "digitize":
            flick = max(flick, 0.12 * min(1.0, (self.t - self.digitize_t0) / DIGITIZE_S))
        r3.draw_him(fr, self.t, flick, int(self.t * 8), halo,
                    mouth=self._mouth(), blink=self.t < self.blink_until, iris=self.gaze)
        self._draw_progress(fr)
        self._draw_candles(fr)
        s = self.scene
        if s == "road":
            for i, stop in enumerate(self.run.offers):
                poly = self._draw_arch(fr, DOOR_X[i] if len(self.run.offers) == 3 else 0.0,
                                       DOOR_LABEL.get(stop.kind, stop.kind.upper()), i == self.pick)
                if poly:
                    self.hits.append((("door", i), poly))
            fr.label3((DOOR_X[self.pick] if len(self.run.offers) == 3 else 0.0, 0.0, DOOR_Z + 1.7), "SPACE")
        elif s == "pick":
            for i, cid in enumerate(self.run.stop.cards):
                d = CARDS[cid]
                lift = 0.3 if i == self.pick else 0.0
                poly = fr.draw_card(*self._upright_pose(PICK_X[i], 1.5 + lift, 1.0, 1.0),
                                    art.card_face(d), art.card_back(), 1.0, PEAK if i == self.pick else BRIGHT)
                if poly:
                    self.hits.append((("pick", i), poly))
            fr.label3((PICK_X[self.pick], 0.0, 2.4), "SPACE")
        elif s == "fire":
            self._draw_fire(fr); self._draw_deck_fan(fr); self._draw_leave(fr)
        elif s == "altar":
            self._draw_altar(fr)
            marks = {self.forge_from[0]: "GIVER"} if self.forge_from[0] is not None else None
            self._draw_deck_fan(fr, marks); self._draw_leave(fr)
        elif s == "forge":
            self._draw_forge(fr)
        elif s == "digitize":
            self._draw_digitize(fr)
        self._draw_caption(fr)
        if self.menu:
            self._draw_menu(fr)
        img = fr.end()
        return r3.finish(img, max(self.mood.dim * strength, 0.55 if self.menu else 0.0),
                         self.settings["scanlines"])
