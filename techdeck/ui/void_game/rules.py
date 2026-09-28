"""The game itself. Pure Python - no Qt, no clock, no drawing.

Every action returns a list of EVENTS describing what just happened, in order.
The state is already final when the list comes back; the window replays the
events as animation. That split is what lets the rules be tested to death
without a screen, and lets the screen be rewritten without touching the rules.

The table:
    4 lanes. Your row, his row, and his INCOMING row behind it - cards he has
    committed that move up next turn, so you can always see what is coming.

A turn:
    draw one (your deck OR the pile of votaries) -> play what you can pay for
    -> ring the bell -> your cards strike -> his incoming cards move up -> he
    commits new ones -> his cards strike -> your turn.

Winning:
    A strike with nothing in its way lands as WEIGHT on the scale. Tip it
    SCALE_TO_WIN in your favour and he loses; the other way and you do.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import (CARDS, FIRST_GAME_PLAN, GAZE, GROWS, HIS_POOL, OFFER, REMNANT,
                    STARTER_DECK, THREE_MOUTHS, UNDYING, VENOM, VOTARY_PILE, WARDEN,
                    WINGED, WORTHY, CardDef)

LANES = 4
SCALE_TO_WIN = 5
OPENING_HAND = 3            # from your deck, plus one votary
YOU, HIM = "you", "him"


class IllegalMove(Exception):
    """The move breaks a rule. The message is written for the player."""


@dataclass
class Card:
    uid: int
    defn: CardDef
    owner: str
    power: int
    health: int
    turns_on_board: int = 0
    sigils: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.defn.name

    def has(self, sigil: str) -> bool:
        return sigil in self.sigils


@dataclass
class Event:
    kind: str
    data: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)


def ev(kind: str, **data) -> Event:
    return Event(kind, data)


class Game:
    def __init__(self, seed: int | None = None, deck=None, plan=None, pool=None):
        self.rng = random.Random(seed)
        self._uid = 0
        self.deck: list[str] = list(deck if deck is not None else STARTER_DECK)
        self.rng.shuffle(self.deck)
        self.votaries = VOTARY_PILE
        self.hand: list[Card] = []
        self.rows: dict[str, list[Card | None]] = {YOU: [None] * LANES, HIM: [None] * LANES}
        self.incoming: list[Card | None] = [None] * LANES
        self.remnants = 0
        self.scale = 0                  # + is weight against HIM, - is weight against YOU
        self.turn = 0
        self.phase = "new"              # new -> play -> draw -> play -> ... -> over
        self.winner: str | None = None
        self.plan = [list(t) for t in (plan if plan is not None else FIRST_GAME_PLAN)]
        self.pool = list(pool if pool is not None else HIS_POOL)
        self.undying_bonus: dict[str, int] = {}     # card id -> times it has come back

    # ── making cards ─────────────────────────────────────────────────────
    def _make(self, card_id: str, owner: str) -> Card:
        d = CARDS[card_id]
        self._uid += 1
        bonus = self.undying_bonus.get(card_id, 0) if owner == YOU else 0
        return Card(self._uid, d, owner, d.power + bonus, d.health + bonus, sigils=d.sigils)

    # ── the opening ──────────────────────────────────────────────────────
    def start(self) -> list[Event]:
        if self.phase != "new":
            raise IllegalMove("The game has already begun.")
        events = [ev("start")]
        for _ in range(OPENING_HAND):
            events += self._draw_from("deck")
        events += self._draw_from("votary")
        events += self._his_commit()            # you see his first move before yours
        self.turn = 1
        self.phase = "play"                     # no draw on the very first turn
        events.append(ev("your_turn", turn=self.turn, draw=False))
        return events

    # ── drawing ──────────────────────────────────────────────────────────
    def can_draw(self, source: str) -> bool:
        if self.phase != "draw":
            return False
        return bool(self.deck) if source == "deck" else self.votaries > 0

    def draw(self, source: str) -> list[Event]:
        if self.phase != "draw":
            raise IllegalMove("You have already drawn.")
        if source not in ("deck", "votary"):
            raise IllegalMove("Draw from your deck or from the votaries.")
        if not self.can_draw(source):
            raise IllegalMove("That pile is empty.")
        events = self._draw_from(source)
        self.phase = "play"
        return events

    def _draw_from(self, source: str) -> list[Event]:
        if source == "deck":
            if not self.deck:
                return []
            card = self._make(self.deck.pop(), YOU)
        else:
            if self.votaries <= 0:
                return []
            self.votaries -= 1
            card = self._make("votary", YOU)
        self.hand.append(card)
        return [ev("draw", card=card, source=source)]

    # ── playing a card ───────────────────────────────────────────────────
    def _hand_card(self, uid: int) -> Card:
        for c in self.hand:
            if c.uid == uid:
                return c
        raise IllegalMove("That card is not in your hand.")

    @staticmethod
    def offering_worth(card: Card) -> int:
        return 3 if card.has(WORTHY) else 1

    def why_not(self, uid: int, lane: int, sacrifices=()) -> str:
        """Why this play is illegal, in the player's words - or '' if it is fine."""
        if self.phase == "draw":
            return "Draw first."
        if self.phase != "play":
            return "It is not your turn."
        card = self._hand_card(uid)
        if not 0 <= lane < LANES:
            return "There is no such lane."
        sac_lanes = list(sacrifices)
        if len(set(sac_lanes)) != len(sac_lanes):
            return "You cannot offer the same one twice."
        for s in sac_lanes:
            if not 0 <= s < LANES or self.rows[YOU][s] is None:
                return "There is nothing there to offer."
        d = card.defn
        if d.cost_kind == OFFER and d.cost > 0:
            worth = sum(self.offering_worth(self.rows[YOU][s]) for s in sac_lanes)
            if worth < d.cost:
                return f"It demands {d.cost}. You have offered {worth}."
        elif sac_lanes:
            return "It asks for no offering."
        if d.cost_kind == REMNANT and self.remnants < d.cost:
            return f"It costs {d.cost} remnants. You have {self.remnants}."
        if self.rows[YOU][lane] is not None and lane not in sac_lanes:
            return "That lane is taken."
        return ""

    def can_afford(self, uid: int) -> bool:
        """Could this card be paid for at all right now (ignoring which lane)?"""
        d = self._hand_card(uid).defn
        if d.cost_kind == REMNANT:
            return self.remnants >= d.cost
        on_board = sum(self.offering_worth(c) for c in self.rows[YOU] if c is not None)
        if d.cost == 0:
            return any(c is None for c in self.rows[YOU])
        return on_board >= d.cost

    def play(self, uid: int, lane: int, sacrifices=()) -> list[Event]:
        problem = self.why_not(uid, lane, sacrifices)
        if problem:
            raise IllegalMove(problem)
        card = self._hand_card(uid)
        events: list[Event] = []
        for s in sacrifices:
            victim = self.rows[YOU][s]
            events.append(ev("sacrifice", card=victim, lane=s))
            events += self._die(victim, s, cause="sacrifice")
        if card.defn.cost_kind == REMNANT and card.defn.cost:
            self.remnants -= card.defn.cost
            events.append(ev("remnants", total=self.remnants, delta=-card.defn.cost))
        self.hand.remove(card)
        self.rows[YOU][lane] = card
        card.turns_on_board = 0
        events.append(ev("play", card=card, lane=lane))
        return events

    # ── the bell ─────────────────────────────────────────────────────────
    def ring_bell(self) -> list[Event]:
        if self.phase == "draw" and (self.deck or self.votaries > 0):
            raise IllegalMove("Draw first.")
        if self.phase not in ("play", "draw"):
            raise IllegalMove("It is not your turn.")
        events = [ev("bell")]
        events += self._combat(YOU)
        if self.winner:
            return events
        events.append(ev("his_turn"))
        events += self._grow(HIM)
        events += self._his_advance()
        events += self._his_commit()
        events += self._combat(HIM)
        if self.winner:
            return events
        for side in (YOU, HIM):
            for c in self.rows[side]:
                if c is not None:
                    c.turns_on_board += 1
        self.turn += 1
        events += self._grow(YOU)
        can_draw = bool(self.deck) or self.votaries > 0
        self.phase = "draw" if can_draw else "play"
        events.append(ev("your_turn", turn=self.turn, draw=can_draw))
        return events

    # ── combat ───────────────────────────────────────────────────────────
    def _strike_power(self, attacker: Card, lane: int) -> int:
        facing = self.rows[HIM if attacker.owner == YOU else YOU][lane]
        penalty = 1 if (facing is not None and facing.has(GAZE)) else 0
        return max(0, attacker.power - penalty)

    def _combat(self, side: str) -> list[Event]:
        other = HIM if side == YOU else YOU
        events: list[Event] = []
        for lane in range(LANES):
            attacker = self.rows[side][lane]
            if attacker is None:
                continue
            power = self._strike_power(attacker, lane)
            if power <= 0:
                continue
            targets = [lane - 1, lane, lane + 1] if attacker.has(THREE_MOUTHS) else [lane]
            for t in (t for t in targets if 0 <= t < LANES):
                if self.rows[side][lane] is not attacker:
                    break                       # it died mid-flurry
                defender = self.rows[other][t]
                flies = attacker.has(WINGED) and not (defender is not None and defender.has(WARDEN))
                if defender is None or flies:
                    self.scale += power if side == YOU else -power
                    events.append(ev("strike", card=attacker, lane=lane, target_lane=t,
                                     direct=True, power=power, flew=bool(flies and defender)))
                    events.append(ev("scale", value=self.scale, delta=power if side == YOU else -power))
                    if abs(self.scale) >= SCALE_TO_WIN:
                        self.winner = YOU if self.scale > 0 else HIM
                        self.phase = "over"
                        events.append(ev("game_over", winner=self.winner))
                        return events
                    continue
                defender.health -= power
                events.append(ev("strike", card=attacker, lane=lane, target_lane=t, direct=False,
                                 power=power, defender=defender, flew=False,
                                 hp_after=defender.health))
                if defender.health <= 0 or attacker.has(VENOM):
                    events += self._die(defender, t, cause="venom" if attacker.has(VENOM)
                                        and defender.health > 0 else "strike")
        return events

    def _die(self, card: Card, lane: int, cause: str) -> list[Event]:
        row = self.rows[card.owner]
        if row[lane] is card:
            row[lane] = None
        events = [ev("die", card=card, lane=lane, cause=cause)]
        if card.owner == YOU:
            self.remnants += 1
            events.append(ev("remnants", total=self.remnants, delta=1))
            if card.has(UNDYING):
                self.undying_bonus[card.defn.id] = self.undying_bonus.get(card.defn.id, 0) + 1
                back = self._make(card.defn.id, YOU)
                self.hand.append(back)
                events.append(ev("return", card=back, was=card))
        return events

    def _grow(self, side: str) -> list[Event]:
        events = []
        for lane, c in enumerate(self.rows[side]):
            if c is not None and c.has(GROWS) and c.turns_on_board >= 1 and c.defn.grows_into:
                grown = self._make(c.defn.grows_into, side)
                grown.turns_on_board = c.turns_on_board
                self.rows[side][lane] = grown
                events.append(ev("grow", card=grown, was=c, lane=lane))
        return events

    # ── him ──────────────────────────────────────────────────────────────
    def _his_advance(self) -> list[Event]:
        events = []
        for lane in range(LANES):
            if self.incoming[lane] is not None and self.rows[HIM][lane] is None:
                card = self.incoming[lane]
                self.incoming[lane] = None
                self.rows[HIM][lane] = card
                card.turns_on_board = 0
                events.append(ev("advance", card=card, lane=lane))
        return events

    def _his_commit(self) -> list[Event]:
        """He slides new cards into his incoming row: the script first, then
        whatever he feels like - one a turn - so a long game never stalls."""
        if self.plan:
            wanted = self.plan.pop(0)
        else:
            wanted = [(self.rng.choice(self.pool), None)] if self.pool else []
        events = []
        for card_id, lane in wanted:
            free = [i for i in range(LANES) if self.incoming[i] is None]
            if not free:
                break
            if lane is None or lane not in free:
                # he prefers a lane he is not already standing in
                open_lanes = [i for i in free if self.rows[HIM][i] is None]
                lane = self.rng.choice(open_lanes or free)
            card = self._make(card_id, HIM)
            self.incoming[lane] = card
            events.append(ev("commit", card=card, lane=lane))
        return events
