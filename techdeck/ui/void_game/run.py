"""The run: the road between fights. Pure Python - no Qt, no clock.

A run is a road of ROAD_LENGTH stops and then him. At every stop you are shown
three doors and pick one: a fight, a choice of cards, a fire, an altar, a rarer
choice. Two candles: lose a fight and one goes out; lose both and you are
dead - and a dead player forges a DEATHCARD from their deck, which turns up in
later runs, in your hand or, rarely, in his.

What survives a run (the `memory` dict the window saves):
    deathcards, the undying bonus (an Ouroboros remembers dying), run counts,
    and every card you have ever played (he remarks on a card's first play once,
    across runs and sessions).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import (CARDS, CHOICE_POOL, FIRST_GAME_PLAN, HIS_TIERS, OFFER, RARE_POOL,
                    STARTER_DECK, CardDef, register_deathcard)
from .rules import HIM, YOU, Game, SCALE_TO_WIN

ROAD_LENGTH = 7                 # stops before him
CANDLES = 2
STOP_WEIGHTS = {"fight": 5, "choice": 4, "fire": 2, "altar": 2, "rare": 1}
DEATHCARD_CHANCE = 0.08         # per card he improvises, when any exist
DEATHCARD_DECK_CHANCE = 0.35    # a saved deathcard joining your starting deck
FIRE_RISK = (0.0, 0.34, 0.5, 0.7)   # chance the fire eats the card: 1st rest free, then rising


@dataclass
class DeckCard:
    """A card in YOUR deck, with what the road did to it."""
    id: str
    power: int = 0                       # bonus from fires
    health: int = 0
    sigils: tuple[str, ...] = ()         # gained at an altar

    @property
    def defn(self) -> CardDef:
        return CARDS[self.id]

    def as_entry(self) -> dict:
        return {"id": self.id, "power": self.power, "health": self.health, "sigils": list(self.sigils)}

    def to_dict(self) -> dict:
        return self.as_entry()

    @staticmethod
    def from_dict(d: dict) -> "DeckCard":
        return DeckCard(d["id"], d.get("power", 0), d.get("health", 0), tuple(d.get("sigils", ())))


@dataclass
class Stop:
    kind: str                            # fight | choice | fire | altar | rare | boss
    cards: list[str] = field(default_factory=list)   # choice/rare: what is on offer
    fire: str = ""                       # fire: "power" or "health"
    rests: dict = field(default_factory=dict)        # fire: deck index -> times rested here


def empty_memory() -> dict:
    return {"deathcards": [], "undying_bonus": {}, "runs": 0, "wins": 0, "deaths": 0, "best": 0,
            "cards_played": []}


class Run:
    def __init__(self, seed: int | None = None, memory: dict | None = None):
        self.rng = random.Random(seed)
        self.memory = {**empty_memory(), **(memory or {})}
        self.memory["runs"] += 1
        for d in self.memory["deathcards"]:
            register_deathcard(d["name"], d["power"], d["health"], d["cost"], d["cost_kind"],
                               tuple(d["sigils"]), d.get("note", ""))
        self.deck: list[DeckCard] = [DeckCard(c) for c in STARTER_DECK]
        if self.memory["deathcards"] and self.rng.random() < DEATHCARD_DECK_CHANCE:
            d = self.rng.choice(self.memory["deathcards"])
            self.deck.append(DeckCard(_death_id(d)))
        self.candles = CANDLES
        self.step = 0                    # stops taken
        self.teeth = 0                   # overkill, kept as a score for now
        self.fights = 0
        self.offers: list[Stop] = []
        self.stop: Stop | None = None
        self.game: Game | None = None
        self.over = False
        self.won = False
        self.dead = False
        self.deathcard: CardDef | None = None

    # ── the road ─────────────────────────────────────────────────────────
    def offer(self) -> list[Stop]:
        """The three doors ahead (one, at the end: him)."""
        if self.step >= ROAD_LENGTH:
            self.offers = [Stop("boss")]
        elif self.step == 0:
            self.offers = [Stop("fight")]           # the first thing on the road is the table
        else:
            kinds = list(STOP_WEIGHTS)
            picked: list[str] = []
            while len(picked) < 3:
                k = self.rng.choices(kinds, [STOP_WEIGHTS[k] for k in kinds])[0]
                if k not in picked:
                    picked.append(k)
            self.offers = [self._stop(k) for k in picked]
        return self.offers

    def _stop(self, kind: str) -> Stop:
        if kind == "choice":
            return Stop(kind, cards=self.rng.sample(CHOICE_POOL, 3))
        if kind == "rare":
            return Stop(kind, cards=self.rng.sample(RARE_POOL, min(2, len(RARE_POOL))) + [self.rng.choice(CHOICE_POOL)])
        if kind == "fire":
            return Stop(kind, fire=self.rng.choice(["power", "health"]))
        return Stop(kind)

    def choose(self, index: int) -> Stop:
        if self.over:
            raise ValueError("The run is over.")
        self.stop = self.offers[index]
        self.step += 1
        if self.stop.kind in ("fight", "boss"):
            self.game = self.new_game(boss=self.stop.kind == "boss")
        return self.stop

    def tier(self) -> int:
        """0..3: how deep into the road the current stop is."""
        return min(3, (self.step - 1) * 4 // (ROAD_LENGTH + 1))

    def new_game(self, boss: bool = False) -> Game:
        deck = [c.as_entry() for c in self.deck]
        if self.fights == 0 and not boss:
            plan, pool = FIRST_GAME_PLAN, HIS_TIERS[0] + HIS_TIERS[1]
        else:
            plan, pool = self._plan(boss)
        return Game(seed=self.rng.randrange(1 << 30), deck=deck, plan=plan, pool=pool,
                    undying_bonus=self.memory["undying_bonus"], boss=boss)

    def _plan(self, boss: bool):
        tier = 3 if boss else self.tier()
        pool = [c for t in HIS_TIERS[:tier + 1] for c in t]
        late = HIS_TIERS[min(3, tier)] + (HIS_TIERS[tier - 1] if tier > 0 else [])
        deaths = [_death_id(d) for d in self.memory["deathcards"]]
        plan = []
        for turn in range(12):
            n = 1 + (1 if (turn >= 4 and self.rng.random() < 0.25 + 0.15 * tier) else 0)
            row = []
            for _ in range(n):
                if deaths and self.rng.random() < DEATHCARD_CHANCE:
                    row.append((self.rng.choice(deaths), None))
                else:
                    src = late if turn >= 3 and self.rng.random() < 0.4 + 0.15 * tier else pool
                    row.append((self.rng.choice(src), None))
            if turn == 2 and not boss:
                row = []                                # a breath, like his first game
            plan.append(row)
        if boss:
            plan[0] = [("sleeper", 1)]
        return plan, pool

    # ── after a fight ────────────────────────────────────────────────────
    def settle_fight(self) -> str:
        """Called when the table's game is over. 'won' | 'lost' | 'dead' | 'run_won'."""
        g = self.game
        assert g is not None and g.phase == "over"
        self.memory["undying_bonus"] = dict(g.undying_bonus)
        self.fights += 1
        if g.winner == YOU:
            self.teeth += max(0, g.scale - SCALE_TO_WIN)
            self.memory["best"] = max(self.memory["best"], self.step)
            if self.stop and self.stop.kind == "boss":
                self.won = self.over = True
                self.memory["wins"] += 1
                return "run_won"
            return "won"
        self.candles -= 1
        if self.candles <= 0:
            self.dead = self.over = True
            self.memory["deaths"] += 1
            return "dead"
        return "lost"

    # ── the other stops ──────────────────────────────────────────────────
    def take_card(self, index: int) -> DeckCard:
        assert self.stop and self.stop.kind in ("choice", "rare")
        card = DeckCard(self.stop.cards[index])
        self.deck.append(card)
        return card

    def rest(self, deck_index: int) -> str:
        """The fire: +1 power or +2 health. The first rest is safe; resting the
        same card again at the same fire risks it being eaten. 'buffed' | 'eaten'."""
        assert self.stop and self.stop.kind == "fire"
        card = self.deck[deck_index]
        times = self.stop.rests.get(deck_index, 0)
        risk = FIRE_RISK[min(times, len(FIRE_RISK) - 1)]
        self.stop.rests[deck_index] = times + 1
        if self.rng.random() < risk:
            self.deck.pop(deck_index)
            return "eaten"
        if self.stop.fire == "power":
            card.power += 1
        else:
            card.health += 2
        return "buffed"

    def altar(self, giver_index: int, taker_index: int) -> DeckCard:
        """One card is given up; its sigils pass to another."""
        assert self.stop and self.stop.kind == "altar" and giver_index != taker_index
        giver = self.deck[giver_index]
        taker = self.deck[taker_index]
        gained = tuple(s for s in giver.defn.sigils + giver.sigils
                       if s not in taker.defn.sigils and s not in taker.sigils)
        taker.sigils = taker.sigils + gained
        self.deck.pop(giver_index)
        return taker

    # ── dying ────────────────────────────────────────────────────────────
    def forge_deathcard(self, name: str, cost_from: int, stats_from: int, sigils_from: int) -> CardDef:
        """The three choices the beaten make: whose cost, whose numbers, whose
        marks. Registered now; remembered for every run after."""
        assert self.dead
        c, s, g = self.deck[cost_from], self.deck[stats_from], self.deck[sigils_from]
        power, health = s.defn.power + s.power, s.defn.health + s.health
        sigils = tuple(dict.fromkeys(g.defn.sigils + g.sigils))
        name = (name.strip() or "NAMELESS")[:14]
        d = register_deathcard(name, power, health, c.defn.cost, c.defn.cost_kind, sigils)
        self.memory["deathcards"].append({"name": d.name, "power": power, "health": health,
                                          "cost": c.defn.cost, "cost_kind": c.defn.cost_kind,
                                          "sigils": list(sigils), "note": d.note})
        self.deathcard = d
        return d


def _death_id(d: dict) -> str:
    return register_deathcard(d["name"], d["power"], d["health"], d["cost"], d["cost_kind"],
                              tuple(d["sigils"]), d.get("note", "")).id
