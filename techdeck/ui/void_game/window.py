"""The playable table: one dark window, the whole game as objects in a void.

No UI. The bell lights when you may ring it, the piles light when you must
draw, lanes light where a card may go. His captions burn into the tube
between his face and the board. The rules engine already knows what
happened; this window replays its EVENTS as animation, one act at a time,
and only listens to the mouse when no act is running.
"""
from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import art, render3d as r3
from .art import BONE, BRIGHT, DIM, EMBER, MID, PEAK, VOID
from .cards import CARDS, HIS_PET, OFFER, REMNANT, SIGILS
from .scenes import RoadScenes
from .dialogue import MOODS, Dialogue, Mood
from .rules import HIM, LANES, SCALE_TO_WIN, YOU, Card, Game, IllegalMove
from .render3d import H, W, Vec, add, dot, ease, lerp, mul, norm

FPS = 30
TICK_MS = 1000 // FPS
Pose = tuple[Vec, Vec, Vec]               # centre, half-width vector, half-height vector

DEAL_S, PLAY_S, MOVE_S, HAND_S = 0.45, 0.55, 0.45, 0.16
LUNGE_S, FADE_S, GROW_S = 0.22, 0.42, 0.5
IDLE_LINE_S = 40.0
CHARS_PER_S = 25.5                    # he types his lines, as in the console (a quarter slower than first cut)
GLANCE_WAIT_S = 1.0                   # a beat after a key before the camera glances at the scale or the bell
PICK_RISE_S = 0.32                    # a chosen card rises this long before the camera goes to the board
HAND_DIP_S = 0.5                      # the empty holding hand dips off the screen in this long
BLINK_S = 0.16
FLAVOR_HOLD_S = 6.0                   # a passing remark lingers this long after it is typed
MUST_READ = {"welcome", "welcome_again", "rules_lanes", "rules_blood",
             "first_hit", "win", "first_win", "lose", "teeth", "candle_out", "boss_welcome",
             "boss_phase", "run_won", "dead", "deathcard_first_time", "deathcard", "deathcard_cost_first_time",
             "deathcard_cost", "deathcard_power_first_time", "deathcard_power", "deathcard_sigil_first_time",
             "deathcard_sigil_first_time_double", "deathcard_sigil", "deathcard_before_named_first_time", "deathcard_before_named",
             "deathcard_post_named", "digitize", "first_sacrifice", "famine", "scene_road_first", "scene_road",
             "scene_fight", "scene_choice", "scene_rare", "scene_fire", "scene_altar", "scene_boss",
             "fire_again", "fire_leave", "fire_buffed", "fire_eaten", "altar_done", "card_taken"}   # these wait for you
NAG_HOLD_S = 3.0                      # a rule slip ("Draw first.") lingers this long
def plural(word: str, n: int) -> str:
    """'point' / 'points' for a {n} in his lines."""
    return word if n == 1 else word + "s"


PROMPT_KEYS = {"first_turn", "second_turn", "first_draw", "deck_empty"}   # instructions: they never eat a key
PROMPT_HOLD_S = 25.0                  # ...and linger until you do the thing, or this long
GLOW_TAGS = ("lanes_you", "lanes_him", "scale", "bell", "piles", "remnants", "costs", "cost_icon")
HINT_AFTER_S = 3.5                    # a waiting line shows its SPACE key only after this long
WIPE_S = 0.55                         # the end of a match: the board is swept off to the side...
GROW_S = 0.7                          # ...and the next scene grows up out of the floor
SHAKE_PART = 0.25                     # the camera trembles for this much of a displeased mood's hold
LESSON_DELAY_S = 0.98                 # the board lesson starts this long after the camera sets off for the board (1.3 s after Space: 0.32 rise + this)

KEYS_TEXT = [
    ("CLICK A CARD", "pick it up; the board lights a lane"),
    ("SPACE ON A CARD", "the same, from the keyboard"),
    ("A / D", "along your hand (the card comes forward); with one raised, its lane"),
    ("S / W", "raise the hand to eye level / rest it low. W from the low hand: the board"),
    ("RIGHT / LEFT", "straight to the piles (while a draw is owed), and back"),
    ("SPACE", "play into the lit lane; draw the lit pile; move him along"),
    ("W from the piles", "the board; W again pitches up to his back row; S comes back down"),
    ("A / D on the board", "along the slots; past the leftmost, a glance at the scale; past the rightmost, the bell and your candles"),
    ("S", "put the raised card down"),
    ("TAB", "ring the bell"),
    ("E / R", "draw from your deck / from the votaries"),
    ("S from the raised hand", "the book of marks"),
    ("Q", "the book, at the raised card's mark"),
    ("ESC", "this menu"),
]
MENU_MAIN = ["RESUME", "KEYS", "DISPLAY", "SOUND", "QUIT"]
DEFAULT_SETTINGS = {"scanlines": True, "volume": 70}


def settings_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "TechDeck", "void_game.json")


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            got = json.load(f)
        kept = {k: got[k] for k in DEFAULT_SETTINGS if k in got}
        if isinstance(got.get("memory"), dict):
            kept["memory"] = got["memory"]                 # what survives a run
        if isinstance(got.get("run"), dict):
            kept["run"] = got["run"]                       # the run you quit, at its last doors
        return {**DEFAULT_SETTINGS, **kept}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(s: dict):
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f)
    except OSError:
        pass
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


class VoidTable(RoadScenes, QWidget):
    """The window. Create it with `open_table()` so something owns it."""

    def __init__(self, seed: int | None = None, parent=None, dialogue: Dialogue | None = None,
                 memory: dict | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("The Puppet Master")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setMinimumSize(640, 360)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.game: Game | None = None     # the current fight's engine; set by begin_fight
        self.dlg = dialogue or Dialogue(seed=seed)
        self.t = 0.0
        self.vcards: dict[int, VCard] = {}
        self.acts: deque[Act] = deque()
        self.act_end = -1.0
        self.selected: int | None = None
        self.sacrifices: list[int] = []
        self.hover = None                 # ("card", uid) | ("slot", lane) | ("bell",) | ("deck",) | ("votary",)
        self.hand_empty_since: float | None = None   # the holding hand dips away once the last card is gone
        self.hits: list[tuple[tuple, QPolygonF]] = []
        self.menu: str | None = None      # None | main | keys | display | sound
        self.menu_index = 0
        self.settings = load_settings()
        self._apply_settings()
        self.captions: deque[tuple[str, str, str, str]] = deque()   # text, emotion, key, glow
        self.caption_key = ""
        self.glow = ""                    # what on the table glows while this page shows
        self.glance_at: float | None = None   # a pending turn of the camera, a beat after a key
        self.caption_auto = False         # this page lets go by itself
        self.typed_at = -1.0              # when the page finished typing
        self.lesson_at: float | None = None   # the board lesson, pending
        self.board_at: float | None = None    # a chosen card has risen; the camera follows a beat later
        self.opening_done = False             # the opening deal is over; draws from here are yours
        self.caption: str = ""
        self.caption_shown = 0
        self.type_t0 = 0.0
        self.caption_until = -1.0
        self.next_blink = 3.0
        self.blink_until = -1.0
        self.gaze = (2, 1)
        self.hand_cursor: int | None = None   # the hand card A / D are on
        self.pending_pick: int | None = None  # a raised card, laid flat while you look at the piles
        self.view = "hand_low"
        self.view_prev = "hand_low"
        self.view_t0 = -9.0
        self.cursor: int | None = None    # a lane (board view) or a pile (deck view)
        self.mood: Mood = MOODS["calm"]
        self.mood_t0 = -9.0
        self.scale_shown = 0.0
        self.scale_target = 0.0
        self.scale_glow = 0.0
        self.remnants_shown = 0
        self.bell_t0 = -9.0
        self.bell_told = False            # the tutorial: he has spoken of the bell (until then, hands off)
        self.over = False
        self.last_input_t = 0.0
        self.idle_said_turn = 0
        self.said_this_phase: set[str] = set()
        self.played_lines: set[str] = set()
        self.frame = None
        self._init_run(seed, memory if memory is not None else self.settings.get("memory"))
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self._begin()

    # ── lifecycle ────────────────────────────────────────────────────────
    def _begin(self):
        self.road_show()                 # the first door is the table, and it opens itself
        self.timer.start()

    def closeEvent(self, event):
        self.timer.stop()
        save_settings(self.settings)
        super().closeEvent(event)

    def event(self, ev):
        if ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key.Key_Tab:
            self.keyPressEvent(ev)
            return True
        return super().event(ev)

    # ── his voice ────────────────────────────────────────────────────────
    def say(self, key: str, once_per_phase: bool = False, part: str = "all", **holes):
        """Queue a line. `part` = "all", "head" (every page but the last) or
        "tail" (only the last page) - the forge asks its question with the
        head and recaps your choice with the tail."""
        if once_per_phase:
            if key in self.said_this_phase:
                return
            self.said_this_phase.add(key)
        got = self.dlg.line(key, **holes)
        if not got:
            return
        text, emotion = got
        if (self._must_read(key) and self.caption and self.caption_until != float("inf")
                and self.caption_shown >= len(self.caption)):
            self.caption_until = self.t            # a passing remark makes way at once for one that waits
        pages = [p.strip() for p in text.split("//")]
        if part == "head":
            pages = pages[:-1]
        elif part == "tail":
            pages = pages[-1:]
        for page in pages:
            glow, auto = "", False
            if page.startswith("[") and "]" in page:
                tags, page = page[1:].split("]", 1)
                for tag in (t.strip() for t in tags.split(",")):
                    if tag in GLOW_TAGS:
                        glow = tag
                    elif tag == "auto":
                        auto = True
                page = page.strip()
            if page:
                self.captions.append((page, emotion, key, glow + ("|auto" if auto else "")))

    def nag(self, text: str):
        """A rule slip, in his voice: 'Draw first.' After whatever he is saying."""
        if self.caption == text or any(c[0] == text for c in self.captions):
            return
        self.captions.append((text, "amused", "nag", ""))
        if text == "Draw first." and self.run.fights == 0 and self.run.memory["runs"] == 1:
            self.show_draw_arrow = True            # the tutorial: point the way to the piles

    def _apply_settings(self):
        pass                                        # nothing live to apply yet (scanlines are read each frame)

    def _speech_tick(self):
        if self.caption and self.t < self.caption_until:
            if self.glance_at is not None and self.t >= self.glance_at:
                self.glance_at = None
                self._glance_for(self.glow)
            self.caption_shown = max(0, min(len(self.caption), int((self.t - self.type_t0) * CHARS_PER_S)))
            return
        self.caption = ""
        ended = self.caption_key if self.caption_key else ""
        self.glow = ""
        if self.captions:
            text, emotion, key, glow = self.captions.popleft()
            glow, _, auto = glow.partition("|")
            self.caption, self.caption_key, self.glow = text, key, glow
            self.caption_auto = auto == "auto"
            if glow == "bell":
                self.bell_told = True
            self.caption_shown = 0
            self.type_t0 = self.t
            self.typed_at = -1.0
            self.mood = MOODS.get(emotion, MOODS["calm"])
            self.mood_t0 = self.t
            if self._needs_glance(glow):
                # a beat of silence, then the camera turns, then he speaks
                self.glance_at = self.t + GLANCE_WAIT_S
                self.type_t0 = self.glance_at + r3.VIEW_S
            else:
                self.glance_at = None
                self._glance_for(glow)
            if key in ("first_turn", "second_turn") and self._drawing() and self.view != "deck":
                self.set_view("deck")              # the piles open as he offers the choice
                self.type_t0 = max(self.type_t0, self.t + r3.VIEW_S)
            typed = len(text) / CHARS_PER_S + max(0.0, self.type_t0 - self.t)
            # Rules and greetings wait for a key; a passing remark lingers; an [auto] page lets go.
            hold = NAG_HOLD_S if key == "nag" else (PROMPT_HOLD_S if key in PROMPT_KEYS else FLAVOR_HOLD_S)
            waits = self._must_read(key) and not self.caption_auto
            self.caption_until = float("inf") if waits else self.t + typed + hold
            if key != ended and ended:
                self._blurb_ended(ended)
        elif ended:
            self.caption_key = ""
            self._blurb_ended(ended)

    @staticmethod
    def _must_read(key: str) -> bool:
        """A line that waits for a key: the rules, the greetings, the scenes -
        and every remark on a card you played or offered."""
        return key in MUST_READ or key.startswith(("play_", "sacrifice"))

    def _needs_glance(self, glow: str) -> bool:
        """A page about the scale or the bell, from the board, when the camera
        is not already looking that way."""
        if self.view not in r3.BOARD_VIEWS or self.scene != "fight":
            return False
        return (glow == "scale" and self.view != "board_left") or (glow == "bell" and self.view != "board_right")

    def _glance_for(self, glow: str):
        """While he speaks of the scale or the bell from the board, the camera
        glances that way by itself; any other page brings it back to the board."""
        if self.view not in r3.BOARD_VIEWS or self.scene != "fight":
            return
        if glow == "scale":
            self.set_view("board_left")
        elif glow == "bell":
            self.set_view("board_right")
        elif self.view in ("board_left", "board_right"):
            self.set_view("board")

    def active_glow(self) -> str:
        """The page's glow, but only from halfway through the line."""
        if not self.glow or not self.caption:
            return ""
        return self.glow if self.caption_shown * 2 >= len(self.caption) else ""

    def _blurb_ended(self, key: str):
        """The last page of a blurb has gone. The board lesson leaves you on the
        board, your lane still lit, your card still waiting."""
        if key == "rules_lanes" and self.view in r3.BOARD_VIEWS:
            self.set_view("board")

    def advance_dialogue(self) -> bool:
        """Space or a click while he is talking: finish the line if it is still
        typing, else move on. Returns True when the input was spent on him."""
        if not self.caption:
            return False
        if self._talking():
            self.caption_shown = len(self.caption)
            self.type_t0 = self.t - len(self.caption) / CHARS_PER_S
            if self.caption_until != float("inf"):
                self.caption_until = self.t + FLAVOR_HOLD_S
        else:
            self.caption_until = self.t
        return True

    def _talking(self) -> bool:
        talking = bool(self.caption) and self.caption_shown < len(self.caption)
        if self.caption and not talking and self.typed_at < 0:
            self.typed_at = self.t
        return talking

    def _draw_glows(self):
        return self.active_glow()

    def waiting_for_key(self) -> bool:
        """A line that will not go on until you press something."""
        return bool(self.caption) and self.caption_until == float("inf")

    def _mouth(self) -> int:
        """The console's own rhythm: the jaw alternates every three characters."""
        return 1 + (self.caption_shown // 3) % 2 if self._talking() else 0

    def _blink_tick(self):
        if self.t >= self.next_blink:
            self.blink_until = self.t + BLINK_S
            self.next_blink = self.t + 2.5 + (self.t * 7.3) % 4.0

    def _mood_strength(self, part: float = 1.0) -> float:
        """How strongly the mood shows, fading out over its hold (`part` of it)."""
        k = self.t - self.mood_t0
        hold = self.mood.hold_ms / 1000.0 * part
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
            elif k == "sacrifice":
                sac_count += 1
                if e["card"].defn.id != "votary" and not self.first_sacrifice_said:
                    self.first_sacrifice_said = True
                    self._act(0, lambda: self.say("first_sacrifice"))
                self._act(FADE_S, lambda c=e["card"]: self._kill(c, ember=True))
            elif k == "endless":
                self._act(0.3, lambda c=e["card"]: self._endless(c))
            elif k == "spawn":
                self._act(DEAL_S, lambda c=e["card"]: self._spawn(c))
            elif k == "thorns":
                self._act(0.3, lambda ev=e: self._thorns(ev))
            elif k == "repelled":
                self._act(LUNGE_S, lambda ev=e: self._repelled(ev))
            elif k == "guard":
                self._act(MOVE_S, lambda c=e["card"], f=e["from_lane"], l=e["lane"]: self._guard(c, f, l))
            elif k == "unmade":
                self._act(0.35, lambda was=e["was"], c=e["card"], l=e["lane"]: self._unmade(was, c, l))
            elif k == "boss_phase":
                self._act(1.2, self._boss_phase)
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
            elif k == "famine":
                self._act(MOVE_S + 0.3, lambda c=e["card"], l=e["lane"], n=e["count"]: self._famine(c, l, n))
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
        self.show_draw_arrow = False
        self._prompt_done("first_turn", "second_turn", "deck_empty")
        if self._tutorial() and self.opening_done and "first_draw" not in self.played_lines and any(
                c.defn.id == "votary" for c in self.game.hand):        # your first real draw, not the opening deal
            self.played_lines.add("first_draw")
            self.say("first_draw")                 # he points at the votary; you play it yourself
        if self.view in ("deck", "hand_high"):
            self.set_view("hand_low")              # the draw is made: the hand rests, on its own
        self.pending_pick = None                   # the new card takes the cursor, not the old pick
        hand = self._hand_cards()
        self.hand_cursor = next((i for i, v in enumerate(hand) if v.uid == card.uid), self.hand_cursor)
        self._layout_hand(force=True)

    def _play(self, card: Card, lane: int, sacrificed: int):
        vc = self.vcards[card.uid]
        vc.where, vc.lane = "you", lane
        vc.go(self._slot_pose(r3.ROW_YOU, lane), self.t, PLAY_S, arc=1.4)
        self.selected, self.sacrifices = None, []
        self.set_view("hand_low")                  # the card is down: the hand rests
        if sacrificed and not self.sacrifice_remark_said:
            from .scenes import SACRIFICE_REMARK_CHANCE
            if self.run.rng.random() < SACRIFICE_REMARK_CHANCE:
                self.sacrifice_remark_said = True          # that was the match's one
                self.say("sacrifice_many" if sacrificed >= 2 else "sacrifice")
        cid = card.defn.id
        key = "play_" + cid
        ever = self.run.memory["cards_played"]     # across runs and sessions
        played_before = cid in ever
        if not played_before:
            ever.append(cid)
            self._save_memory()
        seen_tonight = cid in self.seen_this_fight
        self.seen_this_fight.add(cid)
        if self.card_remark_said:
            pass                                   # one remark on a card per match
        elif self.dlg.has(key) and not played_before:
            self.card_remark_said = True
            self.say(key, name=card.name)          # the card's own line: its first play, ever
        elif not self.generic_remark_ok:
            pass                                   # the generic remarks: one match in five
        elif played_before and cid != "votary":
            self.card_remark_said = True
            self.say("play_repeat", name=card.name)
        elif card.defn.cost >= 3:
            self.card_remark_said = True
            self.say("play_big", name=card.name)
        elif not seen_tonight and cid != "votary":
            self.card_remark_said = True
            self.say("play_new", name=card.name)   # new tonight: the one remark that is per match
        self._layout_hand()

    def _endless(self, card: Card):
        vc = self.vcards.get(card.uid)
        if vc is not None:
            vc.flash_until = self.t + 0.5
        self.say("endless", once_per_phase=True)

    def _spawn(self, card: Card):
        start = (add(r3.slot_center(r3.ROW_YOU, 1), (0, 1.0, 0)), r3.FLAT_U, r3.FLAT_V)
        vc = VCard(card, start, start, card.power, card.health, where="hand", opacity=0.0)
        vc.fade(1.0, DEAL_S)
        self.vcards[card.uid] = vc
        self._layout_hand(force=True)
        self.say("spawn", once_per_phase=True)

    def _thorns(self, e):
        striker = self.vcards.get(e["striker"].uid)
        if striker is not None:
            striker.shown_health = e["hp_after"]
            striker.shake_until = self.t + 0.3
        self.say("thorns", once_per_phase=True)

    def _repelled(self, e):
        attacker = self.vcards.get(e["card"].uid)
        if attacker is not None:
            toward = -1.0 if e["card"].owner == YOU else 1.0
            attacker.lunge = (0.0, 0.1, toward * 0.4)
            attacker.lunge_t0 = self.t
        self.say("repelled", once_per_phase=True)

    def _guard(self, card: Card, from_lane: int, lane: int):
        vc = self.vcards.get(card.uid)
        if vc is not None:
            vc.lane = lane
            vc.go(self._slot_pose(r3.ROW_YOU, lane), self.t, MOVE_S, arc=0.4)
        self.say("guard", once_per_phase=True)

    def _unmade(self, was: Card, card: Card, lane: int):
        old = self.vcards.pop(was.uid, None)
        pose = old.pose if old else self._slot_pose(r3.ROW_YOU, lane)
        vc = VCard(card, pose, pose, card.power, card.health, where="you", lane=lane)
        vc.flash_until = self.t + 0.6
        self.vcards[card.uid] = vc

    def _boss_phase(self):
        for vc in self.vcards.values():
            if vc.where in ("him", "next"):
                vc.where = "gone"; vc.fade(0.0, 0.6)
        self.scale_target = 0.0
        self.say("boss_phase")

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
        if (not e["direct"] and e["card"].owner == HIM and self._tutorial()
                and not self._retired("first_hit")):
            self._retire("first_hit")              # the first time one of his wounds one of yours: narrated once, ever
            self.say("first_hit", yours=e["defender"].name.title(), his=e["card"].name.title(), n=e["power"],
                     points=plural("point", e["power"]))
        attacker = self.vcards.get(e["card"].uid)
        if attacker is None:
            return
        toward = -1.0 if e["card"].owner == YOU else 1.0
        dx = (r3.LANES[e["target_lane"]] - r3.LANES[e["lane"]]) * 0.5
        attacker.lunge = (dx, 0.35 if e.get("flew") else 0.15, toward * 1.1)
        attacker.lunge_t0 = self.t
        if e["direct"]:
            self.scale_glow = 1.0
            self.say("hit_him" if e["card"].owner == YOU else "hit_you", once_per_phase=True, n=e["power"],
                     weights=plural("weight", e["power"]))
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
        elif card.owner == HIM and card.defn.id == HIS_PET:
            self.say("pet_dies")
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
            self.say(key, name=card.name, n=self._reach(card, lane))

    def _reach(self, card: Card, lane: int) -> int:
        """How many of your cards a card of his could strike from that lane."""
        from .cards import THREE_MOUTHS, TWO_MOUTHS
        if card.has(THREE_MOUTHS):
            lanes = (lane - 1, lane, lane + 1)
        elif card.has(TWO_MOUTHS):
            lanes = (lane - 1, lane + 1)
        else:
            lanes = (lane,)
        return sum(1 for l in lanes if 0 <= l < LANES and self.game.rows[YOU][l] is not None)

    def _famine(self, card: Card, lane: int, count: int):
        """Hunger lands on his row, straight down out of the dark."""
        start = (r3.add(r3.slot_center(r3.ROW_HIM, lane), (0, 3.0, 0)), r3.FLAT_U, r3.FLAT_V)
        vc = VCard(card, start, start, card.power, card.health, where="him", lane=lane, opacity=0.0)
        vc.fade(1.0, MOVE_S)
        vc.go(self._slot_pose(r3.ROW_HIM, lane), self.t, MOVE_S + 0.2)
        vc.flash_until = self.t + 0.5
        self.vcards[card.uid] = vc
        self.say("famine" if count == 1 else "famine_again", n=count)

    def _your_turn(self, turn: int):
        self.opening_done = True
        self.said_this_phase.clear()
        self.idle_said_turn = 0
        self.last_input_t = self.t
        if self._drawing():
            if not self._offers_draw(turn):
                self.set_view("deck")              # the turn opens at the piles
            if not self.game.deck and self.game.votaries > 0 and "deck_empty" not in self.played_lines:
                self.played_lines.add("deck_empty")
                self.say("deck_empty")
        if self._tutorial() and self._drawing():
            if turn == 1:
                self.say("first_turn")
            elif turn == 2:
                self.say("second_turn")

    def _offers_draw(self, turn: int) -> bool:
        """The tutorial's first two turns: he offers the draw in words, and the
        camera does not look at the piles until that line begins."""
        return self._tutorial() and turn in (1, 2)

    def _bell_allowed(self) -> bool:
        """The tutorial keeps the bell out of reach until he has spoken of it."""
        if self._tutorial() and not self.bell_told:
            self.say("bell_early")
            return False
        return True

    def _drawing(self) -> bool:
        """A draw is owed: the piles are open, and the hand does not rest low."""
        g = self.game
        return g is not None and g.phase == "draw" and not self.over

    def _game_over(self, winner: str):
        self.over = True
        self.fight_ended(winner)

    # ── layout ───────────────────────────────────────────────────────────
    def _slot_pose(self, row: float, lane: int) -> Pose:
        return r3.slot_center(row, lane), r3.FLAT_U, r3.FLAT_V

    def _hand_cards(self) -> list[VCard]:
        order = {c.uid: i for i, c in enumerate(self.game.hand)}
        return sorted((v for v in self.vcards.values() if v.where == "hand"),
                      key=lambda v: order.get(v.uid, 99))

    def _layout_hand(self, force: bool = False):
        if self.game is None:
            return
        hand = self._hand_cards()
        n = len(hand)
        if self.hand_cursor is not None and self.hand_cursor >= n:
            self.hand_cursor = n - 1 if n else None        # the card under the cursor was played
        for i, vc in enumerate(hand):
            k = i - (n - 1) / 2
            lift, front = 0.0, 0.0
            if self.selected == vc.uid:
                lift = 1.0                              # high above the hand
            elif self.hand_cursor == i and not self.busy() and self.view in ("hand_high", "hand_low"):
                front = 0.75 if self.view == "hand_high" else 0.5   # up, clear of the others (a smaller lift when low)
            tucked = self.view in r3.BOARD_VIEWS or self.book is not None
            if tucked and self.selected == vc.uid:
                pose = r3.held_pose(self.view)          # the chosen card stays in view, bottom left
            else:
                high = 1.0 if self.view == "hand_high" and not tucked else 0.0
                ducked = self.selected is not None and self.selected != vc.uid   # the rest drop while one is raised
                tuck = 1.0 if tucked else (0.35 if ducked else 0.0)
                pose = r3.hand_pose(k * min(1.0, 5.0 / max(n, 1)), lift, tuck, front, high)
            if force or pose != vc.dst:
                vc.go(pose, self.t, HAND_S if not force else DEAL_S, 0.0)

    # ── the clock ────────────────────────────────────────────────────────
    def _tick(self):
        dt = TICK_MS / 1000.0
        self.t += dt
        self._acts_tick()
        if self.board_at is not None and self.t >= self.board_at:
            self.board_at = None
            still_held = self.selected is not None and any(c.uid == self.selected for c in self.game.hand)
            if still_held and self.view in ("hand_low", "hand_high"):
                self.set_view("board")             # the card has risen: on to the lanes
        if self.lesson_at is not None and self.t >= self.lesson_at:
            self.lesson_at = None
            if self.view in r3.BOARD_VIEWS:
                self.say("rules_lanes")
            else:
                self.played_lines.discard("rules_lanes")     # they looked away; next time
        self._speech_tick()
        self._blink_tick()
        self._layout_hand()
        for vc in list(self.vcards.values()):
            vc.advance(self.t, dt)
            if vc.where == "gone" and vc.opacity <= 0.0:
                del self.vcards[vc.uid]
        self.scale_shown += (self.scale_target - self.scale_shown) * min(1.0, dt * 6)
        self.scale_glow = max(0.0, self.scale_glow - dt * 1.5)
        g = self.game
        if (self.scene == "fight" and g is not None and not self.over and not self.busy()
                and g.phase in ("play", "draw") and self.t - self.last_input_t > IDLE_LINE_S
                and self.idle_said_turn != g.turn):
            self.idle_said_turn = g.turn
            self.say("idle")
        self.frame = self._render() if self.scene == "fight" else self.render_scene()
        self.update()

    # ── drawing ──────────────────────────────────────────────────────────
    def _render(self):
        g = self.game
        strength = self._mood_strength()
        k = min(1.0, (self.t - self.view_t0) / r3.VIEW_S)
        shake = self.mood.shake * self._mood_strength(SHAKE_PART)   # a short tremble, not the whole mood
        cam = r3.camera_between(self.view_prev, self.view, k, self.t, shake)
        fr = r3.Frame(cam)
        self.hits = []
        r3.draw_void(fr, self.t)
        halo = tuple(int(a + (b - a) * strength) for a, b in zip(MOODS["calm"].halo, self.mood.halo))
        r3.draw_him(fr, self.t, self.mood.flicker * strength, int(self.t * 8), halo,
                    mouth=self._mouth(), blink=self.t < self.blink_until, iris=self.gaze)
        warp = self._warp()
        if warp:
            fr.cam = r3.Warped(cam, warp)          # the wipe / the grow: every board object
        highlight = set()
        if self.selected is not None and not self.busy():
            for lane in range(LANES):
                if not g.why_not(self.selected, lane, self.sacrifices):
                    highlight.add(("you", lane))
        if self.cursor is not None and (self.view in r3.BOARD_VIEWS or self.selected is not None):
            highlight.add(("you", self.cursor))
        pulse = 0.5 + 0.5 * math.sin(self.t * 5)          # everything he speaks of breathes
        glow = self.active_glow()                          # from halfway through the line
        pulsing = set()
        if glow == "lanes_you":
            pulsing = {("you", l) for l in range(LANES)}
        elif glow == "lanes_him":
            pulsing = {("him", l) for l in range(LANES)} | {("next", l) for l in range(LANES)}
        r3.draw_slots(fr, highlight - pulsing, pulsing, pulse)
        if ("you", self.cursor) in highlight and self.cursor is not None:
            poly = r3.slot_polygon(fr, r3.ROW_YOU, self.cursor)   # the lane the card will land in: a soft fill
            if poly:
                fill = QColor(PEAK); fill.setAlpha(int(40 + 40 * pulse))
                fr.p.setPen(Qt.PenStyle.NoPen); fr.p.setBrush(fill); fr.p.drawPolygon(poly)
        r3.draw_scale(fr, self.scale_shown, max(self.scale_glow, pulse if glow == "scale" else 0.0))
        self._draw_progress(fr)
        self._draw_candles(fr)
        can_act = not self.busy() and not self.over
        ringing = self.t - self.bell_t0
        bell = r3.draw_bell(fr, (can_act and g.phase == "play") or (glow == "bell" and pulse > 0.5),
                            ringing if 0 <= ringing < 1 else 0.0)
        if bell:
            self.hits.append((("bell",), bell))
        must_draw = can_act and g.phase == "draw"
        in_deck = self.view == "deck"
        vot = r3.draw_pile(fr, r3.VOTARIES, g.votaries, art.card_face(CARDS["votary"]),
                           (must_draw and g.votaries > 0) or (in_deck and self.cursor == 1) or (glow == "piles" and pulse > 0.5))
        if vot:
            self.hits.append((("votary",), vot))
        deck = r3.draw_pile(fr, r3.DECK, len(g.deck), art.card_back(),
                            (must_draw and bool(g.deck)) or (in_deck and self.cursor == 0) or (glow == "piles" and pulse > 0.5))
        if deck:
            self.hits.append((("deck",), deck))
        r3.draw_remnants(fr, self.remnants_shown)
        if glow == "remnants":
            fr.polyline3(fr.ring(r3.REMNANTS, 0.7, 12), r3._mix(DIM, PEAK, pulse), 1.0 + 1.6 * pulse)
        # slots you may play into are also click targets
        if self.selected is not None or self.view == "board":
            for lane in range(LANES):
                poly = r3.slot_polygon(fr, r3.ROW_YOU, lane)
                if poly:
                    self.hits.append((("slot", lane), poly))
        tucked_all = self.book is not None
        if self.view == "hand_high" and not tucked_all and self.selected is None:
            self._draw_holding_fingers(fr)
        # cards, far to near - except the hand, which is a fan: left to right, the right card
        # on top, whatever a card's centre does; held up, the current card comes to the front
        # of the fan (layer 2 to layer 1) - low, it only slides up; a raised card tops them all
        hand = self._hand_cards()
        rank = {vc.uid: i for i, vc in enumerate(hand)}
        if self.view == "hand_high" and self.hand_cursor is not None and self.hand_cursor < len(hand):
            rank[hand[self.hand_cursor].uid] = len(hand)
        if self.selected in rank:
            rank[self.selected] = len(hand) + 1
        order = sorted(self.vcards.values(),
                       key=lambda v: (v.uid in rank, rank[v.uid] if v.uid in rank else -cam.depth(v.pose[0])))
        for vc in order:
            c, u, v = vc.drawn_pose(self.t)
            edge = vc.edge
            if vc.lane in self.sacrifices and vc.where == "you":
                edge = EMBER
                c = add(c, (0, 0.15, 0))
            elif self.selected == vc.uid or self.t < vc.flash_until:
                edge = PEAK
            elif vc.where == "hand" and self.hand_cursor is not None and self._hand_cards()[self.hand_cursor:self.hand_cursor + 1] == [vc]:
                edge = PEAK                             # the current card, marked but not moved
            face = art.card_face(vc.card.defn, vc.shown_power, vc.shown_health, vc.card.sigils)
            poly = fr.draw_card(c, u, v, face, art.card_back(), vc.opacity, edge)
            if poly and vc.where != "gone":
                self.hits.append((("card", vc.uid), poly))
            if vc.where == "hand" and vc.card.defn.cost > 0 and (
                    (glow == "cost_icon" and self.selected == vc.uid) or glow == "costs"):
                # a pulsing ring around the price: every priced card, or just the raised one
                at = add(add(c, mul(u, 0.55)), mul(v, 0.55))
                q = cam.project(at)
                if q:
                    kk = max(0.6, min(1.2, 7.0 / q[2]))
                    col = QColor(EMBER); col.setAlphaF(0.5 + 0.5 * pulse)
                    fr.p.setPen(QPen(col, 2.0)); fr.p.setBrush(Qt.BrushStyle.NoBrush)
                    fr.p.drawEllipse(QPointF(q[0], q[1]), 16 * kk, 12 * kk)
            if self.selected == vc.uid and vc.card.sigils and self.book is None:
                # the book's key, floating under the raised card
                at = add(c, mul(v, -1.22))
                q = cam.project(at)
                if q:
                    kk = max(0.7, min(1.1, 7.0 / q[2]))
                    fr.page_icon(q[0] - 14 * kk, q[1], "right", kk)
                    fr.keycap(q[0] + 14 * kk, q[1], "Q", kk)
        fr.cam = cam
        self._draw_caption(fr)
        # small key hints where the eye is: E / R under the piles in the deck
        # view, Z under the bell from the hand
        draw_on = can_act and g.phase == "draw"
        if draw_on and self.view in ("deck", "hand_low", "hand_high"):   # only while a draw can be made
            fr.label3(r3.add(r3.DECK, (0, 0, 1.25)), "E", BRIGHT)
            fr.label3(r3.add(r3.VOTARIES, (0, 0, 1.25)), "R", BRIGHT)
        if self.view != "board_left" and not self.over and not self.busy() and g.phase == "play":
            at = r3.add(r3.BELL, (0, 0.05, 0.55))
            q = fr.cam.project(at)
            if q and not self._under_a_hand_card(q[0], q[1]):
                fr.label3(at, "TAB")                       # wherever the bell is in view, and not behind a card
        if self.view == "hand_high" and not tucked_all and self.selected is None:
            self._draw_holding_hand(fr)
        if self.show_draw_arrow and self.view in ("hand_low", "hand_high") and g.phase == "draw":
            self._draw_arrow_to_deck(fr)
        self._draw_inspect(fr)
        if self.book is not None:
            self._draw_book(fr)
        if self.menu:
            self._draw_menu(fr)
        img = fr.end()
        return r3.finish(img, max(self.mood.dim * strength, 0.55 if self.menu else 0.0),
                         self.settings["scanlines"])

    def _draw_arrow_to_deck(self, fr: r3.Frame):
        """The tutorial's one pointer: an arrow at the right edge toward the
        piles, with the key that looks that way. Pulses until you draw."""
        pulse = 0.5 + 0.5 * math.sin(self.t * 4)
        col = QColor(PEAK); col.setAlphaF(0.55 + 0.45 * pulse)
        x, y = W - 92 + 6 * pulse, H * 0.62
        p = fr.p
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(x, y - 12), QPointF(x + 22, y), QPointF(x, y + 12),
                                 QPointF(x + 6, y), ]))
        p.drawRect(QRectF(x - 26, y - 4, 30, 8))
        fr.keycap(x - 52, y, "D", 1.1)

    def _under_a_hand_card(self, x: float, y: float, reach: float = 16.0) -> bool:
        """Is a screen point (or its near neighbours) covered by a card in the hand?"""
        hand = {vc.uid for vc in self._hand_cards()}
        pts = [QPointF(x, y), QPointF(x - reach, y), QPointF(x + reach, y), QPointF(x, y - reach), QPointF(x, y + reach)]
        for kind, poly in self.hits:
            if kind[0] == "card" and kind[1] in hand and any(poly.containsPoint(p, Qt.FillRule.OddEvenFill) for p in pts):
                return True
        return False

    def _fan_points(self, fr: r3.Frame):
        """The screen point at the bottom middle of the held fan (it moves only
        with the fan, never with the card you are on), and a scale. With no
        card left to hold, the hand dips off the bottom of the screen (None once
        it has gone)."""
        c, u, v = r3.hand_pose(0.0, 0.0, 0.0, 0.0, 1.0)
        bottom = fr.cam.project(add(c, mul(v, -1.0)))
        if not bottom:
            return None
        k = max(0.6, min(1.6, 6.0 / bottom[2]))
        if self._hand_cards():
            self.hand_empty_since = None
            return bottom, k
        if self.hand_empty_since is None:
            self.hand_empty_since = self.t
        dip = min(1.0, (self.t - self.hand_empty_since) / HAND_DIP_S)
        if dip >= 1.0:
            return None
        dip = dip * dip * (3 - 2 * dip)                      # eased
        return (bottom[0], bottom[1] + 340 * k * dip, bottom[2]), k

    def _draw_holding_fingers(self, fr: r3.Frame):
        """The palm and curled fingers BEHIND the cards, at the fan's lower
        left: a dark mass the cards mostly hide, as in a real hand."""
        pts = self._fan_points(fr)
        if not pts:
            return
        (bx, by, _), k = pts
        p = fr.p
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(DIM), 1.2)); p.setBrush(QColor(2, 12, 6))
        # BEHIND the cards: the wrist and the gathered fingers of a pinching hand
        # (mano a borsa) rising from the bottom edge at the fan's centre
        wrist = QPainterPath()
        wrist.moveTo(bx - 70 * k, by + 240 * k)
        wrist.cubicTo(bx - 90 * k, by + 120 * k, bx - 60 * k, by + 20 * k, bx + 10 * k, by - 10 * k)
        wrist.cubicTo(bx + 70 * k, by + 20 * k, bx + 100 * k, by + 120 * k, bx + 80 * k, by + 240 * k)
        wrist.closeSubpath()
        p.drawPath(wrist)

    def _draw_holding_hand(self, fr: r3.Frame):
        """The thumb, in front of the cards at the fan's lower left, on the
        heel of the hand that rises from the bottom of the screen. Drawn as
        smooth silhouettes with a soft rim, so it reads as a hand, not a shape."""
        pts = self._fan_points(fr)
        if not pts:
            return
        (bx, by, _), k = pts
        p = fr.p
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        skin = QColor(3, 18, 9)
        rim = QColor(MID)
        # IN FRONT: the thumb, rising from the bottom edge to the pinch at the fan's
        # centre, leaning in from the left; its pad rests on the cards' bottom edge
        thumb = QPainterPath()
        thumb.moveTo(bx - 60 * k, by + 240 * k)
        thumb.cubicTo(bx - 80 * k, by + 130 * k, bx - 70 * k, by + 30 * k, bx - 30 * k, by - 14 * k)
        thumb.cubicTo(bx - 16 * k, by - 32 * k, bx + 14 * k, by - 30 * k, bx + 20 * k, by - 6 * k)
        thumb.cubicTo(bx + 28 * k, by + 40 * k, bx + 26 * k, by + 140 * k, bx + 30 * k, by + 240 * k)
        thumb.closeSubpath()
        p.setPen(QPen(rim, 1.3)); p.setBrush(skin); p.drawPath(thumb)
        p.setPen(QPen(QColor(DIM), 1.0)); p.setBrush(Qt.BrushStyle.NoBrush)
        crease = QPainterPath(); crease.moveTo(bx - 52 * k, by + 60 * k)
        crease.cubicTo(bx - 34 * k, by + 46 * k, bx - 4 * k, by + 46 * k, bx + 16 * k, by + 62 * k)
        p.drawPath(crease)                                   # the knuckle
        nail = QPainterPath(); nail.moveTo(bx - 22 * k, by - 12 * k)
        nail.cubicTo(bx - 14 * k, by - 28 * k, bx + 10 * k, by - 26 * k, bx + 14 * k, by - 8 * k)
        p.drawPath(nail)

    def _draw_caption(self, fr: r3.Frame):
        """His line, burned into the tube between his face and the board. The
        narrator's lines are set differently: not shouted, a quieter green."""
        if not self.caption:
            return
        x, y, w, h = self._caption_rect()
        shown = self.caption[:self.caption_shown]
        if self.scene == "fight" and self.view in r3.BOARD_VIEWS:
            # looking down, the rows run to the top edge: a dark band keeps the words legible
            fr.p.setPen(Qt.PenStyle.NoPen); fr.p.setBrush(QColor(1, 6, 3, 205))
            fr.p.drawRoundedRect(QRectF(x - 12, y - 6, w + 24, h + 12 + (16 if self.waiting_for_key() else 0)), 6, 6)
        if self.mood.narrator:
            fr.text(x, y, w, h, shown, BRIGHT, 12, False, spacing=1)
        else:
            fr.text(x, y, w, h, shown.upper(), PEAK, 13)
        if not self._talking() and self.caption_until == float("inf") and self.t - self.typed_at > HINT_AFTER_S:
            fr.keycap(x + w / 2, y + h + 14, "SPACE", 0.8, MID, 9)

    def _caption_rect(self):
        """Where his line sits: centred in the gap between his face and the far
        row, as tall as the wrapped text needs (it used to clip at three lines)."""
        narr = self.mood.narrator
        f = QFont(art.MONO, 12 if narr else 13); f.setBold(not narr)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1 if narr else 2)
        w = W - 220
        h = QFontMetrics(f).boundingRect(QRect(0, 0, w, 400), int(Qt.TextFlag.TextWordWrap),
                                         self.caption if narr else self.caption.upper()).height() + 6
        if self.scene == "fight" and self.view in r3.BOARD_VIEWS:
            y = 14                                           # looking down: his line at the top, off the rows
        else:
            centre = 246 if self.scene == "fight" else 172   # on the road the doors sit lower
            y = max(120, int(centre - h / 2))
        return 110, y, w, h

    # ── the menu (Esc) ──────────────────────────────────────────────────
    def _menu_items(self) -> list[tuple[str, str]]:
        """(label, value) rows for the open menu page."""
        s = self.settings
        if self.menu == "main":
            return [(m, "") for m in MENU_MAIN]
        if self.menu == "keys":
            return KEYS_TEXT + [("BACK", "")]
        if self.menu == "display":
            return [("SCANLINES", "ON" if s["scanlines"] else "OFF"), ("BACK", "")]
        if self.menu == "sound":
            return [("VOLUME", f"{s['volume']}  (no sound yet)"), ("BACK", "")]
        return []

    def open_menu(self, page: str = "main"):
        self.menu, self.menu_index = page, 0

    def close_menu(self):
        self.menu = None
        save_settings(self.settings)

    def _menu_adjust(self, step: int):
        """A / D on a setting row."""
        label = self._menu_items()[self.menu_index][0]
        if label == "SCANLINES":
            self.settings["scanlines"] = not self.settings["scanlines"]
        elif label == "VOLUME":
            self.settings["volume"] = max(0, min(100, self.settings["volume"] + 10 * step))

    def _menu_pick(self):
        label = self._menu_items()[self.menu_index][0]
        if self.menu == "main":
            if label == "RESUME":
                self.close_menu()
            elif label == "QUIT":
                self.close()
            else:
                self.open_menu(label.lower())
        elif label == "BACK":
            self.open_menu("main")
        else:
            self._menu_adjust(1)

    def _menu_key(self, key):
        if key == Qt.Key.Key_Escape:
            self.open_menu("main") if self.menu != "main" else self.close_menu()
        elif key in (Qt.Key.Key_W, Qt.Key.Key_Up):
            self.menu_index = (self.menu_index - 1) % len(self._menu_items())
        elif key in (Qt.Key.Key_S, Qt.Key.Key_Down):
            self.menu_index = (self.menu_index + 1) % len(self._menu_items())
        elif key in (Qt.Key.Key_A, Qt.Key.Key_Left):
            self._menu_adjust(-1)
        elif key in (Qt.Key.Key_D, Qt.Key.Key_Right):
            self._menu_adjust(1)
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._menu_pick()

    def _draw_menu(self, fr: r3.Frame):
        items = self._menu_items()
        title = {"main": "THE TABLE", "keys": "KEYS", "display": "DISPLAY", "sound": "SOUND"}[self.menu]
        row_h = 26 if self.menu != "keys" else 22
        h = 70 + row_h * len(items)
        w = 620 if self.menu == "keys" else 340
        x, y = (W - w) // 2, (H - h) // 2
        p = fr.p
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(1, 6, 3, 235)); p.drawRect(QRectF(x, y, w, h))
        p.setPen(QColor(BRIGHT)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(QRectF(x, y, w, h))
        fr.text(x, y + 14, w, 24, title, PEAK, 14)
        cy = y + 52
        for i, (label, value) in enumerate(items):
            on = i == self.menu_index
            col, size = (PEAK if on else MID), (11 if self.menu != "keys" else 9)
            if self.menu == "keys" and label != "BACK":
                fr.text(x + 22, cy, 200, row_h, label, col, size, True,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 1)
                fr.text(x + 230, cy, w - 244, row_h, value, col, size, False,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 0)
            else:
                text = f"{'> ' if on else ''}{label}{'   ' + value if value else ''}"
                fr.text(x, cy, w, row_h, text, col, size)
            poly = QPolygonF([QPointF(x, cy), QPointF(x + w, cy), QPointF(x + w, cy + row_h), QPointF(x, cy + row_h)])
            self.hits.append((("menu", i), poly))
            cy += row_h

    # ── views and the cursor ────────────────────────────────────────────
    def set_view(self, view: str):
        if view == self.view:
            return
        self.view_prev, self.view, self.view_t0 = self.view, view, self.t
        if view in r3.BOARD_VIEWS:
            if self.cursor is None or self.view_prev not in r3.BOARD_VIEWS:
                self.cursor = self._first_lane()
            if view == "board" and self._tutorial() and "rules_lanes" not in self.played_lines:
                self.played_lines.add("rules_lanes")
                self.lesson_at = self.t + LESSON_DELAY_S     # give them a second to look
        elif view == "deck":
            self.cursor = 0 if self.game.deck else 1
        else:
            self.cursor = self._first_lane() if self.selected is not None else None

    def _first_lane(self) -> int:
        g = self.game
        if self.selected is not None and any(c.uid == self.selected for c in g.hand):
            for lane in range(LANES):
                if not g.why_not(self.selected, lane, self.sacrifices):
                    return lane
        return 0

    def _lesson_holds(self) -> bool:
        """The tutorial's board lesson is about to start, or is running: no
        card is played until it is over."""
        if self.lesson_at is not None:
            return True
        return self.caption_key == "rules_lanes" or any(c[2] == "rules_lanes" for c in self.captions)

    def _warp(self):
        """The scene's warp this frame: the wipe at a match's end, else the
        grow for the first moments of any scene, else none."""
        if self.wipe_t0 >= 0:
            return r3.warp_wipe((self.t - self.wipe_t0) / WIPE_S)
        k = (self.t - self.scene_t0) / GROW_S
        return r3.warp_grow(k) if k < 1.0 else None

    def _retired(self, key: str) -> bool:
        """A line he says once, ever (kept with the memory, across runs and sessions)."""
        return key in self.run.memory["retired"]

    def _retire(self, key: str):
        if key not in self.run.memory["retired"]:
            self.run.memory["retired"].append(key)
            self._save_memory()

    def _tutorial(self) -> bool:
        return self.run.fights == 0 and self.run.memory["runs"] == 1

    def _prompt_done(self, *keys: str):
        """An instruction he gave has been followed: let it go."""
        if self.caption_key in keys and self.caption_until != float("inf"):
            self.caption_until = self.t

    def pick_up(self, uid: int):
        """Choose a card from the hand: it rises first; a beat later the camera
        moves on to the board with a lane lit and the card waiting at the left.
        One fluid step, in two parts. S puts it down / comes back to the hand."""
        self._prompt_done("first_draw")
        self.selected, self.sacrifices = uid, []
        self.cursor = self._first_lane()
        if self.view in ("hand_low", "hand_high"):
            self.board_at = self.t + PICK_RISE_S

    def put_down(self):
        self.board_at = None
        self.selected, self.sacrifices = None, []
        if self.view == "board":
            self.cursor = self._first_lane()

    def _act_on_lane(self, lane: int):
        """Space or a click on a lane of yours: offer the card standing there,
        or play the chosen card into it. A second Space on a marked lane plays
        if the offering is now enough, else takes the mark back."""
        g = self.game
        if self.selected is None:
            raise IllegalMove("Choose a card from your hand first.")
        if self._lesson_holds():
            return                                 # the board lesson first: the card waits
        d = g._hand_card(self.selected).defn
        standing = g.rows[YOU][lane]
        legal = not g.why_not(self.selected, lane, self.sacrifices)
        if legal:
            self.enqueue(g.play(self.selected, lane, self.sacrifices))
        elif lane in self.sacrifices:
            self.sacrifices.remove(lane)
        elif standing is not None and d.cost_kind == OFFER and d.cost:
            self.sacrifices.append(lane)
        else:
            raise IllegalMove(g.why_not(self.selected, lane, self.sacrifices))

    def _draw_inspect(self, fr: r3.Frame):
        if not self.hover or self.hover[0] != "card":
            return
        vc = self.vcards.get(self.hover[1])
        if vc is None:
            return
        d = vc.card.defn
        p = fr.p
        x, y, w = 14, H - 150, 380
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
        pt = self._to_frame(event.position())
        self.hover = self._hit(pt)
        if self.hover and self.hover[0] == "card":
            hand = [v.uid for v in self._hand_cards()]
            if self.hover[1] in hand:
                self.hand_cursor = hand.index(self.hover[1])   # the mouse moves the cursor too
        self.gaze = (max(0, min(4, int(pt.x() / W * 5))), max(0, min(2, int(pt.y() / H * 3))))

    def leaveEvent(self, event):
        self.hover = None

    def mousePressEvent(self, event):
        self.last_input_t = self.t
        if self.menu:
            hit = self._hit(self._to_frame(event.position()))
            if hit and hit[0] == "menu":
                self.menu_index = hit[1]
                self._menu_pick()
            return
        if event.button() == Qt.MouseButton.RightButton:
            return
        if self.book is not None:
            self.book = None; self.peek = False
            return
        if self.advance_dialogue():
            return
        if self.over:
            if not self.captions:
                self.after_fight_go()
            return
        hit = self._hit(self._to_frame(event.position()))
        if self.scene != "fight":
            if self.scene == "digitize":
                if self.t - self.digitize_t0 > 4.5:
                    self.close()
                return
            self.scene_click(hit)
            return
        if self.busy() or hit is None:
            return
        try:
            self._click(hit)
        except IllegalMove as why:
            self.nag(str(why))

    def _click(self, hit):
        g = self.game
        kind = hit[0]
        if kind == "bell":
            if self._bell_allowed():
                self.enqueue(g.ring_bell())
        elif kind in ("deck", "votary"):
            if self.view != "deck":
                self.set_view("deck")              # look over first; the next click draws
                self.cursor = 0 if kind == "deck" else 1
            else:
                self.enqueue(g.draw(kind))
        elif kind == "slot":
            if self.view == "board":
                self.cursor = hit[1]
            if self.selected is not None:
                self._act_on_lane(hit[1])
        elif kind == "card":
            vc = self.vcards.get(hit[1])
            if vc is None:
                return
            if vc.where == "hand":
                if self.selected == vc.uid:
                    return                                  # only Tab / S put it down
                elif g.phase == "draw":
                    raise IllegalMove("Draw first.")
                elif not g.can_afford(vc.uid):
                    d = vc.card.defn
                    if self._tutorial() and "rules_blood" not in self.played_lines and d.cost_kind == OFFER:
                        self.played_lines.add("rules_blood")
                        self.selected = vc.uid          # raised, so its price can be pointed at
                        self.say("rules_blood")         # the first card you could not pay for: blood
                        return
                    if d.cost_kind == REMNANT:
                        raise IllegalMove(f"It demands {d.cost} remnants. You cannot pay.")
                    raise IllegalMove(f"{d.name.title()} requires {d.cost} sacrifice{'s' if d.cost > 1 else ''}. "
                                      f"You do not have enough.")
                else:
                    self.pick_up(vc.uid)
            elif vc.where == "you" and self.selected is not None:
                d = g._hand_card(self.selected).defn
                if d.cost_kind != OFFER or not d.cost:
                    raise IllegalMove("It asks for no offering.")
                if self.view == "board":
                    self.cursor = vc.lane
                if vc.lane in self.sacrifices:
                    self.sacrifices.remove(vc.lane)
                else:
                    self.sacrifices.append(vc.lane)

    def _walk_hand(self, step: int):
        """A / D along the hand. A raised card comes with the cursor; D past
        the rightmost card looks at the piles."""
        hand = self._hand_cards()
        if not hand:
            if step > 0:
                self._look_at_piles()
            return
        cur = self.hand_cursor
        if cur is None:
            cur = 0 if step > 0 else len(hand) - 1
        else:
            cur += step
        if cur >= len(hand):
            self._look_at_piles()
            return
        cur = max(0, cur)
        self.hand_cursor = cur
        if self.hover and self.hover[0] == "card":
            self.hover = None                       # the keys have the cursor now, not the mouse
        if self.selected is not None and self.selected != hand[cur].uid:
            self._raise(hand[cur].uid)

    def _raise(self, uid: int):
        """Lift a card in the hand; the camera follows to the board a beat later."""
        self.pick_up(uid)

    def _look_at_piles(self):
        """To the piles - only while a draw is owed. A raised card lies flat
        meanwhile and is remembered."""
        if not self._drawing():
            return
        self.pending_pick = self.selected
        self.selected, self.sacrifices = None, []
        self.set_view("deck")

    def _back_to_hand(self):
        """Back from the piles to the hand, held up, on the rightmost card; the
        remembered card rises again."""
        self.set_view("hand_high")
        hand = self._hand_cards()
        self.hand_cursor = len(hand) - 1 if hand else None
        if self.pending_pick is not None and any(v.uid == self.pending_pick for v in hand):
            self._raise(self.pending_pick)
            self.hand_cursor = [v.uid for v in hand].index(self.pending_pick)
        self.pending_pick = None

    def keyPressEvent(self, event):
        """Esc cancels/leaves. Space advances his dialogue, else picks (a lane in
        the board view, a pile in the deck view). W looks
        down at the board, D leans to the deck (or moves the cursor right), A
        moves it left (and from the deck's first pile returns to the hand), S
        comes back to the hand. Z rings the bell. The mouse only ever clicks."""
        self.last_input_t = self.t
        key = event.key()
        if self.menu:
            self._menu_key(key)
            return
        if self.scene == "forge" and self.forge_step == 3 and key not in (Qt.Key.Key_Escape,):
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Backspace):
                self.scene_key(key)
            else:
                self.forge_type(event.text())
            return
        if self.book_key(key):
            return
        if key == Qt.Key.Key_Escape:
            self.open_menu()
            return
        if self.waiting_for_key() or (self.caption_key in MUST_READ and self._talking()):
            self.advance_dialogue()                 # everything else is frozen: any key moves him on
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.advance_dialogue():
            return
        if self.over:
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.captions:
                self.after_fight_go()
            return
        if self.scene != "fight":
            self.scene_key(key)
            return
        try:
            if key == Qt.Key.Key_Tab:
                if not self.busy() and not self.over and self._bell_allowed():
                    self.enqueue(self.game.ring_bell())     # the bell
            elif key == Qt.Key.Key_Q:
                if self.selected is not None:
                    d = self.game._hand_card(self.selected).defn
                    self.open_book_at(d.sigils[0] if d.sigils else None)
                else:
                    self.open_book_at(None)
            elif key == Qt.Key.Key_Space:
                if self.busy():
                    return
                if self.view in r3.BOARD_VIEWS and self.cursor is not None:
                    self._act_on_lane(self.cursor)
                elif self.view == "deck" and self.cursor is not None:
                    self.enqueue(self.game.draw("deck" if self.cursor == 0 else "votary"))
                elif self.view in ("hand_low", "hand_high"):
                    if self.selected is not None and self.cursor is not None:
                        self._act_on_lane(self.cursor)     # play it into the lit lane, from here
                    else:
                        hand = self._hand_cards()
                        if self.hover and self.hover[0] == "card":
                            self._click(self.hover)         # the card under the mouse...
                        elif self.hand_cursor is not None and 0 <= self.hand_cursor < len(hand):
                            self._click(("card", hand[self.hand_cursor].uid))   # ...else the cursor's
            elif key == Qt.Key.Key_Right and self.view in ("hand_low", "hand_high"):
                self._look_at_piles()
            elif key == Qt.Key.Key_Left and self.view == "deck":
                self._back_to_hand()
            elif key in (Qt.Key.Key_E, Qt.Key.Key_R):
                if not self.busy() and not self.over:
                    self.enqueue(self.game.draw("deck" if key == Qt.Key.Key_E else "votary"))
            elif key in (Qt.Key.Key_W, Qt.Key.Key_Up):
                v = self.view
                if self.selected is not None and v in ("hand_low", "hand_high"):
                    self.set_view("board")                  # a raised card: see the lanes
                elif v == "hand_low":
                    if self._drawing():
                        self._look_at_piles()               # a draw is owed: up is the piles
                    else:
                        self.set_view("board")              # up from the resting hand: the board
                elif v == "hand_high":
                    if self._drawing():
                        self._look_at_piles()               # low is not open while a draw is owed
                    else:
                        self.set_view("hand_low")           # the hand goes back down
                elif v == "deck":
                    self.set_view("board")
                elif v == "board":
                    self.set_view("board_far")
                elif v in ("board_left", "board_right"):
                    self.set_view("board")
            elif key in (Qt.Key.Key_S, Qt.Key.Key_Down):
                v = self.view
                if self.selected is not None and v in ("hand_low", "hand_high"):
                    self.put_down()                         # S with a raised card: it goes back in line
                elif v == "hand_low":
                    self.set_view("hand_high")              # down: the hand rises to eye level
                elif v == "hand_high":
                    self.open_book_at(None)                 # further down: the book
                elif v == "deck":
                    self.set_view("hand_high")
                elif v == "board":
                    self.put_down()
                    self.set_view("deck" if self._drawing() else "hand_low")
                elif v in ("board_far", "board_left", "board_right"):
                    self.set_view("board")
            elif key == Qt.Key.Key_D:
                v = self.view
                if v in ("board", "board_far"):
                    if self.cursor is None:
                        self.cursor = self._first_lane()
                    elif self.cursor >= LANES - 1:
                        self.set_view("board_right")       # past the rightmost slot: the bell and your candles
                    else:
                        self.cursor += 1                   # along the slots
                elif v == "board_left":
                    self.set_view("board")                 # back from the scale (card raised or not)
                elif v == "board_right":
                    pass                                   # already looking right
                elif self.selected is not None and self.cursor is not None:
                    self.cursor = (self.cursor + 1) % LANES  # a card raised, from the hand: choose its lane
                elif v in ("hand_low", "hand_high"):
                    self._walk_hand(+1)                    # ...and past the last card, the piles (while a draw is owed)
                elif v == "deck":
                    self.cursor = 1
            elif key == Qt.Key.Key_A:
                v = self.view
                if v in ("board", "board_far"):
                    if self.cursor is None:
                        self.cursor = self._first_lane()
                    elif self.cursor <= 0:
                        self.set_view("board_left")        # past the leftmost slot: the scale
                    else:
                        self.cursor -= 1
                elif v == "board_right":
                    self.set_view("board")                 # back from the bell (card raised or not)
                elif v == "board_left":
                    pass                                   # already looking left
                elif self.selected is not None and self.cursor is not None:
                    self.cursor = (self.cursor - 1) % LANES
                elif v in ("hand_low", "hand_high"):
                    self._walk_hand(-1)
                elif v == "deck":
                    self._back_to_hand()
            else:
                super().keyPressEvent(event)
        except IllegalMove as why:
            self.nag(str(why))


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
