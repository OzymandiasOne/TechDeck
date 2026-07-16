"""
ASA: The Video Game — event system (data + engine).

Design spec: docs/ASA_GAME_EVENTS.md. Adds challenge via events, not by penalizing
surplus. Two kinds:
  * AUTOMATIC "drift hits" — fire on a timer, apply a themed setback, no player input.
  * RESPONSIVE decisions — the game pops a modal (pausing the sim) with 3-4 options;
    the chosen option's outcomes resolve here.

This module is deliberately UI-free and game-agnostic: the engine reads/writes a `game`
object (the SteelBeamsGame widget) through plain attributes + a few helpers, so the pure
logic is unit-testable headlessly. The widget owns the modal window + the tick call.

Outcome primitives (a list per automatic event / per responsive option):
    ("delta",     attr, amount)      game.<attr> += amount
    ("delta_pct", attr, frac)        game.<attr> *= (1 + frac)   # frac<0 loses % of current
    ("mul_attr",  attr, factor)      game.<attr> *= factor       # permanent multiplicative
    ("mod",       lever, mult, secs) timed multiplier on a lever (the "until it resolves" bit)
    ("flag",      name)              game._flags.add(name)
    ("log",       text, color)       game._log(text, color)
    ("gamble",    p, then[], else[]) with prob p apply then[], else else[]
    ("chain",     event_id, delay_s) schedule a follow-up responsive event

Levers a ("mod", ...) may target (the game getters multiply in EventEngine.mod(lever)):
    steel_cost, tube_demand, af_demand, prod_mult, power_drain, power_recharge,
    ai_income, enemy_growth
"""

import random

# ── Ending axes — every responsive choice nudges these; tallied at the ending ──
AXES = ("RUTHLESS", "HUMANE", "EMPIRE", "CASHOUT", "STEEL", "SINGULARITY")


def phase_of(game) -> str:
    """EARLY (on-ramp) → MID → LATE, pinned to existing game flags."""
    if getattr(game, "probe_phase", False):
        return "LATE"
    if getattr(game, "market_unlocked", False):
        return "MID"
    return "EARLY"


# Frequency/severity scaler per phase (gentle EARLY on-ramp). Multiplies the base
# interval (smaller = more often) and severity where an event opts in.
PHASE_FREQ = {"EARLY": 1.6, "MID": 1.0, "LATE": 0.8}

AUTO_MIN_S, AUTO_MAX_S = 120.0, 240.0     # base automatic interval (before phase scale)
RESP_MIN_S, RESP_MAX_S = 300.0, 540.0     # base responsive interval (5–9 min)


# ── Event data ────────────────────────────────────────────────────────────────
# Each event:
#   id     : unique str
#   gate   : name of a truthy game attr required for eligibility, or None (always).
#            This is what makes the pool CUMULATIVE — an event stays eligible for the
#            rest of the run once its stage is unlocked (old events keep firing).
#   name   : title (responsive only)
#   art    : placeholder art key (stage/theme) — real .tdart later
#   weight : draw weight
#   desc   : setup text (responsive only)
#   effects: outcome list (automatic only)
#   options: [dict(label, outcomes=[...], endings={axis:w})] (responsive only)

YARD_AUTO = [
    dict(id="yard_forklift", gate=None, weight=10,
         log=("Forklift incident: a pallet went through the break-room wall. "
              "Doug is fine. Doug is always fine.", "orange"),
         effects=[("delta_pct", "tubes", -0.12)]),
    dict(id="yard_steel_spike", gate=None, weight=10,
         log=("Steel futures spike. Your buyers are furious.", "orange"),
         effects=[("mod", "steel_cost", 1.8, 90.0)]),
    dict(id="yard_rail_delay", gate=None, weight=8,
         log=("Rail delay: the inbound steel car is stuck upstate.", "orange"),
         effects=[("delta_pct", "steel", -0.7)]),
    dict(id="yard_osha", gate=None, weight=8,
         log=("OSHA surprise inspection. Safety stand-down.", "red"),
         effects=[("delta_pct", "money", -0.05), ("mod", "prod_mult", 0.8, 60.0)]),
    dict(id="yard_rats", gate=None, weight=6,
         log=("A rat king in the rafters chewed the mainline. "
              "Seventeen rats. One destiny.", "yellow"),
         effects=[("mod", "prod_mult", 0.5, 30.0)]),
    dict(id="yard_scrap_thieves", gate=None, weight=7,
         log=("Scrap thieves backed a truck up at 3 a.m.", "orange"),
         effects=[("delta_pct", "tubes", -0.1), ("delta_pct", "steel", -0.1)]),
    dict(id="yard_fab_fire", gate=None, weight=6,
         log=("A fabricator cooked itself. The line's down.", "red"),
         effects=[("mod", "prod_mult", 0.6, 60.0)]),
    dict(id="yard_bad_heat", gate=None, weight=7,
         log=("Bad heat: an off-spec steel batch. The tubes are scrap.", "orange"),
         effects=[("delta_pct", "tubes", -0.15)]),
    dict(id="yard_viral", gate=None, weight=6,
         log=("A clip of the mascot 'Rebar Randy' doing something unspeakable "
              "has gone viral.", "yellow"),
         effects=[("mod", "tube_demand", 0.8, 90.0)]),
    dict(id="yard_vending", gate=None, weight=4,
         log=("The break-room vending machine has been reprogrammed to demand "
              "tribute. Negotiations are ongoing.", "slate"),
         effects=[("delta_pct", "money", -0.01)]),
]

YARD_RESP = [
    dict(id="yard_union", gate=None, name="The Union Vote", art="yard",
         desc=("The floor crew is organizing. Tomorrow they vote, and everyone's "
               "watching how you handle it."),
         options=[
             dict(label="Recognize them",
                  outcomes=[("mod", "tube_demand", 1.1, 99999.0),
                            ("log", "You recognize the union. The floor trusts you.", "lime")],
                  endings={"HUMANE": 2, "EMPIRE": 1}),
             dict(label="Hire 'labor consultants'",
                  outcomes=[("delta_pct", "money", -0.08),
                            ("gamble", 0.6,
                             [("mod", "prod_mult", 1.15, 60.0),
                              ("log", "The consultants earn their fee. Vote fails.", "lime")],
                             [("mod", "prod_mult", 0.0, 45.0),
                              ("mod", "tube_demand", 0.8, 90.0),
                              ("log", "Wildcat strike. The yard goes dark.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Ignore it",
                  outcomes=[("chain", "yard_wildcat", 180.0),
                            ("log", "You ignore the vote. For now.", "slate")],
                  endings={"RUTHLESS": 1, "CASHOUT": 1}),
             dict(label="Offer profit-sharing",
                  outcomes=[("delta_pct", "money", -0.05),
                            ("mul_attr", "prod_mult", 1.1),
                            ("mod", "tube_demand", 1.1, 99999.0),
                            ("log", "Profit-sharing. Expensive, and clean.", "lime")],
                  endings={"HUMANE": 1, "EMPIRE": 1}),
         ]),
    dict(id="yard_rival", gate=None, name="The Failing Yard Next Door", art="yard",
         desc=("Pileggi & Sons went under. Their crew, scrap, and contracts are up "
               "for grabs — and so are their debts."),
         options=[
             dict(label="Buy them out",
                  outcomes=[("delta_pct", "money", -0.15), ("delta_pct", "steel", 0.5),
                            ("mul_attr", "prod_mult", 1.05),
                            ("log", "You absorb Pileggi & Sons.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="Poach the crew, let the shell die",
                  outcomes=[("delta_pct", "money", -0.05), ("mul_attr", "prod_mult", 1.08),
                            ("log", "You take their best people. The town remembers.", "orange")],
                  endings={"RUTHLESS": 1, "EMPIRE": 1}),
             dict(label="Undercut and salt the earth",
                  outcomes=[("mod", "tube_demand", 1.15, 90.0),
                            ("chain", "yard_grudge", 200.0),
                            ("log", "You bury them. Someone won't forget.", "orange")],
                  endings={"RUTHLESS": 2}),
             dict(label="Bail them out, keep them independent",
                  outcomes=[("delta_pct", "money", -0.1),
                            ("log", "You save a competitor. Odd. Decent.", "lime")],
                  endings={"HUMANE": 2, "CASHOUT": 1}),
         ]),
    dict(id="yard_inspector", gate=None, name="The Inspector", art="yard",
         desc=("A county inspector found 'irregularities.' He'd hate to file the "
               "paperwork. Be a shame."),
         options=[
             dict(label="Grease the palm",
                  outcomes=[("delta_pct", "money", -0.03),
                            ("gamble", 0.8,
                             [("log", "The file vanishes.", "slate")],
                             [("delta_pct", "money", -0.1),
                              ("mod", "tube_demand", 0.85, 90.0),
                              ("log", "He was wired. This is bad.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Fix it by the book",
                  outcomes=[("delta_pct", "money", -0.08), ("mod", "prod_mult", 0.8, 90.0),
                            ("flag", "yard_compliant"),
                            ("log", "Fixed, filed, clean. No more inspections.", "lime")],
                  endings={"HUMANE": 2}),
             dict(label="Fight it in court",
                  outcomes=[("gamble", 0.55,
                             [("mod", "tube_demand", 1.1, 120.0),
                              ("log", "You win. A 'compliant' badge, and buzz.", "lime")],
                             [("delta_pct", "money", -0.12),
                              ("log", "You lose. Bigger fine.", "red")])],
                  endings={"EMPIRE": 1}),
         ]),
    dict(id="yard_bay4", gate=None, name="The Thing in Bay 4", art="yard_dark",
         desc=("There was an accident on night shift. It's bad. Nobody outside the "
               "yard knows yet. The next ten minutes decide everything."),
         options=[
             dict(label="Report it, take responsibility",
                  outcomes=[("delta_pct", "money", -0.12), ("mod", "prod_mult", 0.7, 60.0),
                            ("mul_attr", "prod_mult", 1.05), ("mod", "tube_demand", 1.1, 99999.0),
                            ("log", "You do the right thing. It costs. It's remembered.", "lime")],
                  endings={"HUMANE": 3}),
             dict(label="Quietly settle it",
                  outcomes=[("delta_pct", "money", -0.2),
                            ("log", "Lawyers, NDAs, a clean disappearance.", "slate")],
                  endings={"RUTHLESS": 1, "CASHOUT": 1}),
             dict(label="Bury it",
                  outcomes=[("gamble", 0.7,
                             [("log", "It stays buried. You don't sleep well.", "slate")],
                             [("chain", "yard_expose", 220.0),
                              ("log", "Something like this never really stays buried.", "red")])],
                  endings={"RUTHLESS": 3}),
         ]),
]

# The full pool. Stages 2-8 (docs/ASA_GAME_EVENTS.md) slot in here as they're encoded.
AUTO_EVENTS = list(YARD_AUTO)
RESP_EVENTS = list(YARD_RESP)
RESP_BY_ID = {e["id"]: e for e in RESP_EVENTS}


class EventEngine:
    """Owns active modifiers, ending tally, and the fire timers. UI-free."""

    def __init__(self):
        self.active_mods = []      # [{lever, mult, t}]
        self.axes = {a: 0 for a in AXES}
        self.seen_once = set()     # responsive ids already shown (story one-shots)
        self._auto_t = random.uniform(AUTO_MIN_S, AUTO_MAX_S)
        self._resp_t = random.uniform(RESP_MIN_S, RESP_MAX_S)
        self._chains = []          # [(event_id, t_remaining)]
        self.enabled = True

    # -- lever modifiers -------------------------------------------------
    def mod(self, lever: str) -> float:
        """Product of all active timed modifiers for a lever (1.0 if none)."""
        m = 1.0
        for a in self.active_mods:
            if a["lever"] == lever:
                m *= a["mult"]
        return m

    def _add_mod(self, lever, mult, secs):
        self.active_mods.append({"lever": lever, "mult": mult, "t": secs})

    # -- outcome resolution ---------------------------------------------
    def apply(self, game, effects):
        for eff in effects or ():
            kind = eff[0]
            if kind == "delta":
                setattr(game, eff[1], getattr(game, eff[1]) + eff[2])
            elif kind == "delta_pct":
                setattr(game, eff[1], getattr(game, eff[1]) * (1.0 + eff[2]))
            elif kind == "mul_attr":
                setattr(game, eff[1], getattr(game, eff[1]) * eff[2])
            elif kind == "mod":
                self._add_mod(eff[1], eff[2], eff[3])
            elif kind == "flag":
                getattr(game, "_flags").add(eff[1])
            elif kind == "log":
                game._log(eff[1], eff[2] if len(eff) > 2 else None)
            elif kind == "gamble":
                self.apply(game, eff[2] if random.random() < eff[1] else eff[3])
            elif kind == "chain":
                self._chains.append((eff[1], eff[2]))

    def choose(self, game, event, opt_index):
        """Resolve a responsive option: tally endings + apply outcomes."""
        opt = event["options"][opt_index]
        for axis, w in (opt.get("endings") or {}).items():
            self.axes[axis] = self.axes.get(axis, 0) + w
        self.apply(game, opt.get("outcomes"))

    # -- eligibility -----------------------------------------------------
    @staticmethod
    def _eligible(game, pool):
        out = []
        for e in pool:
            g = e.get("gate")
            if g is None or getattr(game, g, False):
                out.append(e)
        return out

    def _pick(self, pool):
        if not pool:
            return None
        return random.choices(pool, weights=[e.get("weight", 1) for e in pool])[0]

    # -- the per-tick driver --------------------------------------------
    def tick(self, game, dt):
        """Advance timers/mods. Returns a responsive event dict to SHOW, or None.
        Automatic events are applied inline. The widget shows the returned modal
        (and pauses the sim) itself."""
        # decay active modifiers
        if self.active_mods:
            for a in self.active_mods:
                a["t"] -= dt
            self.active_mods = [a for a in self.active_mods if a["t"] > 0]
        if not self.enabled:
            return None
        ph = phase_of(game)
        scale = PHASE_FREQ.get(ph, 1.0)

        # chained follow-ups
        due = None
        if self._chains:
            nxt = []
            for eid, t in self._chains:
                t -= dt
                if t <= 0 and due is None and eid in RESP_BY_ID:
                    due = RESP_BY_ID[eid]
                else:
                    nxt.append((eid, t))
            self._chains = nxt
            if due is not None:
                self._resp_t = random.uniform(RESP_MIN_S, RESP_MAX_S) * scale
                return due

        # automatic events (applied inline)
        self._auto_t -= dt
        if self._auto_t <= 0:
            self._auto_t = random.uniform(AUTO_MIN_S, AUTO_MAX_S) * scale
            ev = self._pick(self._eligible(game, AUTO_EVENTS))
            if ev is not None:
                self.apply(game, ev.get("effects"))
                lg = ev.get("log")
                if lg:
                    game._log(lg[0], lg[1] if len(lg) > 1 else None)

        # responsive events (returned for the widget to show)
        self._resp_t -= dt
        if self._resp_t <= 0:
            self._resp_t = random.uniform(RESP_MIN_S, RESP_MAX_S) * scale
            pool = [e for e in self._eligible(game, RESP_EVENTS)
                    if e["id"] not in self.seen_once]
            ev = self._pick(pool)
            if ev is not None:
                self.seen_once.add(ev["id"])
                return ev
        return None

    def force(self, event_id):
        """Dev-terminal hook: return a responsive event to show by id."""
        return RESP_BY_ID.get(event_id)
