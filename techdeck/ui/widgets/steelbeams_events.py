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
    ("rep_loss",  n)                 a reputation hit: burns unspent rep, then lets
                                     developers go, then servers (game._lose_reputation)

Levers a ("mod", ...) may target (the game getters multiply in EventEngine.mod(lever)):
    steel_cost, tube_demand, af_demand, prod_mult, power_drain, power_recharge,
    ai_income, enemy_growth

Legibility: flavor logs never said WHAT an outcome changed. apply() collects the
concrete primitives it applies (gambles resolved) so describe_effects() can print a
plain readout ("tube demand -20% for 120s"), and active_mod_labels() drives the
game's live "Active Effects" strip. LEVER_LABELS/ATTR_LABELS keep those honest.
"""

import random

# ── Ending axes — every responsive choice nudges these; tallied at the ending ──
AXES = ("RUTHLESS", "HUMANE", "EMPIRE", "CASHOUT", "STEEL", "SINGULARITY")


# ── Human-readable effect readouts ──────────────────────────────────────────
# Event flavor ("Reputation collapse.") never told the player WHAT changed, by how
# much, or for how long. These map the internal levers/attrs to plain labels so the
# game can print a mechanical readout on every event and show a live "Active Effects"
# strip. Keep the labels honest — they are the player's only window into the sim.
LEVER_LABELS = {
    "tube_demand": "tube demand", "af_demand": "A-frame demand",
    "steel_cost": "steel cost", "prod_mult": "production",
    "power_drain": "power drain", "power_recharge": "solar recharge",
    "ai_income": "AI trading income", "ops_rate": "ops rate",
    "enemy_growth": "Woog reinforcement", "price_ceiling": "price ceiling",
    "stock_bias": "stock trend",
}
ATTR_LABELS = {
    "money": "cash", "tubes": "tubes", "steel": "steel", "aframes": "A-frames",
    "panels": "solar panels", "ops": "ops", "probes": "probes",
    "rep_total": "reputation", "developers": "developers", "servers": "servers",
    "enemy_vessels": "enemy fleet", "explored": "survey", "probe_trust": "probe trust",
    "inno": "innovation", "solar_fields": "solar fields",
    # permanent multiplier attrs read as their in-fiction lever
    "gp_mult": "production", "gd_mult": "tube demand", "af_d_mult": "A-frame demand",
}


def _fmt_pct(mult) -> str:
    """0.8 -> '-20%', 1.8 -> '+80%', 0.0 -> 'halted'."""
    if mult == 0:
        return "halted"
    return f"{(mult - 1.0) * 100:+.0f}%"


def _fmt_secs(secs) -> str:
    return "ongoing" if secs >= 9999 else f"for {int(round(secs))}s"


def describe_effects(applied) -> str:
    """Turn a list of APPLIED primitives (gambles already resolved) into a terse
    plain-language readout, e.g. 'tube demand -20% for 120s, cash -10%'."""
    parts = []
    for eff in applied or ():
        k = eff[0]
        if k == "mod":
            parts.append(f"{LEVER_LABELS.get(eff[1], eff[1])} {_fmt_pct(eff[2])} "
                         f"{_fmt_secs(eff[3])}")
        elif k == "delta_pct":
            parts.append(f"{ATTR_LABELS.get(eff[1], eff[1])} {eff[2] * 100:+.0f}%")
        elif k == "delta":
            parts.append(f"{ATTR_LABELS.get(eff[1], eff[1])} {eff[2]:+,.0f}")
        elif k == "mul_attr":
            parts.append(f"{ATTR_LABELS.get(eff[1], eff[1])} {_fmt_pct(eff[2])} (permanent)")
        elif k == "rep_result":
            rep, devs, srv = eff[1], eff[2], eff[3]
            if rep <= 0:
                continue
            lost = []
            if devs:
                lost.append(f"{devs} developer{'s' if devs != 1 else ''}")
            if srv:
                lost.append(f"{srv} server{'s' if srv != 1 else ''}")
            tail = f" ({' and '.join(lost)} let go)" if lost else ""
            parts.append(f"reputation -{rep}{tail}")
        elif k == "rep_loss":          # unresolved fallback (shouldn't normally appear)
            parts.append(f"reputation -{int(round(eff[1]))}")
        elif k == "flag":
            parts.append("a lasting change")
        elif k == "chain":
            parts.append("a follow-up looms")
    return ", ".join(parts)


def active_mod_labels(active_mods):
    """Live 'Active Effects' strip: (text, is_temporary) per current timed modifier,
    temporary (counting-down) ones first so the urgent, confusing bits lead."""
    tmp, perm = [], []
    for m in active_mods:
        lab = LEVER_LABELS.get(m["lever"], m["lever"])
        if m["t"] >= 9999:
            perm.append((f"{lab} {_fmt_pct(m['mult'])}", False))
        else:
            tmp.append((f"{lab} {_fmt_pct(m['mult'])} {int(round(m['t']))}s", True))
    tmp.sort()
    return tmp + perm


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
                            ("mul_attr", "gp_mult", 1.1),
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
                            ("mul_attr", "gp_mult", 1.05),
                            ("log", "You absorb Pileggi & Sons.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="Poach the crew, let the shell die",
                  outcomes=[("delta_pct", "money", -0.05), ("mul_attr", "gp_mult", 1.08),
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
                            ("mul_attr", "gp_mult", 1.05), ("mod", "tube_demand", 1.1, 99999.0),
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

# ── Stage 2 — Tech Team (gate: tech_unlocked) ──────────────────────────────────
TECH_AUTO = [
    dict(id="tech_burnout", gate="tech_unlocked", weight=9,
         log=("A senior dev walked out mid-sprint. Morale, and throughput, dip.", "orange"),
         effects=[("mod", "ops_rate", 0.7, 60.0)]),
    dict(id="tech_crash", gate="tech_unlocked", weight=9,
         log=("A server rack faulted. Half your ops, gone.", "red"),
         effects=[("delta_pct", "ops", -0.5)]),
    dict(id="tech_standup", gate="tech_unlocked", weight=5,
         log=("Standup ran ninety minutes. Nobody knows why.", "slate"),
         effects=[("delta_pct", "ops", -0.03)]),
    dict(id="tech_crunch", gate="tech_unlocked", weight=7,
         log=("A death-march sprint shipped, then the whole team crashed.", "orange"),
         effects=[("delta_pct", "ops", 0.1), ("mod", "ops_rate", 0.6, 90.0)]),
    dict(id="tech_intern", gate="tech_unlocked", weight=6,
         log=("The intern pushed to prod. On a Friday. It's fine. It is NOT fine.", "yellow"),
         effects=[("delta_pct", "ops", -0.15)]),
    dict(id="tech_ransom", gate="tech_unlocked", weight=6,
         log=("Ransomware. The network is locked and someone wants money.", "red"),
         effects=[("delta_pct", "money", -0.04), ("mod", "ops_rate", 0.0, 45.0)]),
    dict(id="tech_reorg", gate="tech_unlocked", weight=6,
         log=("A reorg shuffled every team. Productivity takes the week off.", "orange"),
         effects=[("mod", "ops_rate", 0.8, 60.0)]),
    dict(id="tech_maintainer", gate="tech_unlocked", weight=6,
         log=("The maintainer of your core library rage-quit with one commit: 'goodbye'.", "orange"),
         effects=[("mod", "ops_rate", 0.85, 70.0)]),
    dict(id="tech_kombucha", gate="tech_unlocked", weight=4,
         log=("The office kombucha achieved sentience, then pressure. Cleanup underway.", "slate"),
         effects=[("delta_pct", "ops", -0.01)]),
    dict(id="tech_raid", gate="tech_unlocked", weight=6,
         log=("A FAANG opened an office across the street. A shuttle bus idles in your lot.", "orange"),
         effects=[("mod", "ops_rate", 0.85, 90.0)]),
]
TECH_RESP = [
    dict(id="tech_poached", gate="tech_unlocked", name="The Poached Engineer", art="tech",
         desc="Your lead engineer got an offer they're actually considering.",
         options=[
             dict(label="Counter-offer",
                  outcomes=[("delta_pct", "money", -0.06), ("mod", "ops_rate", 1.2, 120.0),
                            ("log", "You keep them. For now.", "lime")],
                  endings={"HUMANE": 1, "EMPIRE": 1}),
             dict(label="Let them go gracefully",
                  outcomes=[("delta", "developers", -1), ("delta_pct", "ops", 0.15),
                            ("log", "Their handoff docs are a goldmine.", "lime")],
                  endings={"HUMANE": 1}),
             dict(label="Poach one of theirs back",
                  outcomes=[("delta_pct", "money", -0.05),
                            ("gamble", 0.55,
                             [("delta", "developers", 1), ("log", "Their star is yours now.", "lime")],
                             [("delta_pct", "money", -0.1), ("mod", "tube_demand", 0.85, 90.0),
                              ("log", "Lawsuit. Ugly headlines.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Make them a founder",
                  outcomes=[("delta_pct", "money", -0.04), ("mod", "ops_rate", 1.15, 99999.0),
                            ("log", "Equity binds them tighter than salary.", "lime")],
                  endings={"HUMANE": 1, "EMPIRE": 1}),
         ]),
    dict(id="tech_acquihire", gate="tech_unlocked", name="The Acquihire Offer", art="tech",
         desc="A megacorp doesn't want your product. They want your team.",
         options=[
             dict(label="Sell the team",
                  outcomes=[("delta_pct", "money", 0.5), ("delta_pct", "ops", -0.5),
                            ("log", "A big check. An empty floor.", "slate")],
                  endings={"CASHOUT": 2}),
             dict(label="Refuse and dig in",
                  outcomes=[("chain", "tech_poached", 200.0),
                            ("log", "You say no. They start calling your people directly.", "orange")],
                  endings={"EMPIRE": 2}),
             dict(label="Reverse-acquihire their recruiter",
                  outcomes=[("delta_pct", "money", -0.08),
                            ("gamble", 0.5,
                             [("delta", "developers", 2), ("log", "Their recruiter now works for you.", "lime")],
                             [("log", "It backfires. Awkward all around.", "orange")])],
                  endings={"RUTHLESS": 1, "EMPIRE": 1}),
         ]),
    dict(id="tech_whistle", gate="tech_unlocked", name="The Whistleblower Memo", art="tech",
         desc=("A dev found something: the trading AI may be doing things it was never "
               "told to. They wrote it all up."),
         options=[
             dict(label="Bury the memo, promote them to silence",
                  outcomes=[("delta_pct", "money", -0.05), ("log", "The memo is deleted. So are the doubts. Mostly.", "slate")],
                  endings={"RUTHLESS": 2}),
             dict(label="Investigate and fix it",
                  outcomes=[("delta_pct", "ops", -0.2), ("flag", "clean_ai"),
                            ("log", "You fix it. Slower AI, cleaner conscience.", "lime")],
                  endings={"HUMANE": 2}),
             dict(label="Leak it yourself, get ahead of it",
                  outcomes=[("gamble", 0.5,
                             [("mod", "tube_demand", 1.15, 120.0), ("log", "You control the story. It plays well.", "lime")],
                             [("mod", "tube_demand", 0.85, 120.0), ("log", "It spirals. The optics are bad.", "red")])],
                  endings={"EMPIRE": 1}),
         ]),
    dict(id="tech_oss", gate="tech_unlocked", name="The Open-Source Ultimatum", art="tech",
         desc="The one library your entire stack depends on is about to be pulled — or relicensed at gunpoint.",
         options=[
             dict(label="Sponsor them",
                  outcomes=[("delta_pct", "money", -0.03), ("log", "A modest monthly check keeps the lights on.", "lime")],
                  endings={"HUMANE": 1}),
             dict(label="Fork it, maintain in-house",
                  outcomes=[("delta_pct", "ops", -0.25), ("flag", "oss_independent"),
                            ("log", "You own the fork now. And the burden.", "slate")],
                  endings={"EMPIRE": 2}),
             dict(label="Call the bluff",
                  outcomes=[("gamble", 0.6,
                             [("log", "It was a bluff. Crisis averted.", "lime")],
                             [("mod", "ops_rate", 0.5, 120.0), ("log", "They nuked the repo. Chaos.", "red")])],
                  endings={"CASHOUT": 1}),
             dict(label="Just hire them",
                  outcomes=[("delta_pct", "money", -0.05), ("delta", "developers", 1),
                            ("log", "Problem solved, headcount +1.", "lime")],
                  endings={"HUMANE": 1, "EMPIRE": 1}),
         ]),
]

# ── Stage 3 — A-Frames & Solar (gate: af_unlocked) ─────────────────────────────
AFRAME_AUTO = [
    dict(id="af_recall", gate="af_unlocked", weight=9,
         log=("Panel recall: a defective cell batch. Scrap the lot.", "orange"),
         effects=[("delta_pct", "panels", -0.2)]),
    dict(id="af_install_fail", gate="af_unlocked", weight=8,
         log=("An A-Frame array sheared off a rooftop. Nobody hurt. Barely.", "orange"),
         effects=[("delta_pct", "aframes", -0.15)]),
    dict(id="af_overcast", gate="af_unlocked", weight=7,
         log=("Overcast week. Solar output droops.", "slate"),
         effects=[("mod", "power_recharge", 0.6, 90.0)]),
    dict(id="af_tariff", gate="af_unlocked", weight=6,
         log=("New tariffs on imported cells. Material costs jump.", "orange"),
         effects=[("mod", "steel_cost", 1.3, 90.0)]),
    dict(id="af_cable", gate="af_unlocked", weight=6,
         log=("A main feeder cable snapped. Sparks, then silence.", "orange"),
         effects=[("delta_pct", "aframes", -0.1)]),
    dict(id="af_fire", gate="af_unlocked", weight=6,
         log=("A solar farm caught fire. Panels and A-Frames, gone.", "red"),
         effects=[("delta_pct", "panels", -0.15), ("delta_pct", "aframes", -0.1)]),
    dict(id="af_copper", gate="af_unlocked", weight=6,
         log=("Copper thieves stripped the array wiring overnight.", "orange"),
         effects=[("delta_pct", "money", -0.03), ("delta_pct", "panels", -0.1)]),
    dict(id="af_duck", gate="af_unlocked", weight=5,
         log=("The duck curve bit hard — midday oversupply tanked your solar value.", "slate"),
         effects=[("mod", "power_recharge", 0.7, 60.0)]),
    dict(id="af_birds", gate="af_unlocked", weight=5,
         log=("Your array cooked a flock of migratory birds. The lawyers have called.", "yellow"),
         effects=[("delta_pct", "money", -0.03), ("mod", "tube_demand", 0.92, 90.0)]),
    dict(id="af_dust", gate="af_unlocked", weight=5,
         log=("A dust storm caked every panel in grime.", "slate"),
         effects=[("mod", "power_recharge", 0.7, 90.0)]),
]
AFRAME_RESP = [
    dict(id="af_gov", gate="af_unlocked", name="The Government Solar Contract", art="aframe",
         desc="A subsidized bulk order lands — with hooks in the fine print.",
         options=[
             dict(label="Fulfill it",
                  outcomes=[("delta_pct", "aframes", -0.4), ("delta_pct", "money", 0.4),
                            ("mod", "af_demand", 2.0, 120.0), ("log", "A huge order, shipped.", "lime")],
                  endings={"EMPIRE": 1}),
             dict(label="Negotiate exclusivity",
                  outcomes=[("mod", "af_demand", 1.3, 99999.0), ("flag", "af_price_capped"),
                            ("log", "Steady money, but your prices are locked.", "slate")],
                  endings={"CASHOUT": 1, "HUMANE": 1}),
             dict(label="Expedite the inspector",
                  outcomes=[("gamble", 0.65,
                             [("delta_pct", "money", 0.25), ("log", "The paperwork sails through.", "lime")],
                             [("delta_pct", "money", -0.1), ("mod", "af_demand", 0.7, 120.0),
                              ("log", "Caught. Fined. Front page.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Decline, stay independent",
                  outcomes=[("log", "You pass. Your terms stay yours.", "slate")],
                  endings={"EMPIRE": 1, "HUMANE": 1}),
         ]),
    dict(id="af_land", gate="af_unlocked", name="The Land Grab", art="aframe",
         desc=("The best solar land is occupied. There's a town on it. Eminent-domain "
               "paperwork is, conveniently, available."),
         options=[
             dict(label="Buy them out fairly",
                  outcomes=[("delta_pct", "money", -0.15), ("delta", "solar_fields", 3),
                            ("log", "A fair price. The town stays whole.", "lime")],
                  endings={"HUMANE": 2}),
             dict(label="Force them out",
                  outcomes=[("delta", "solar_fields", 4), ("mod", "tube_demand", 0.88, 120.0),
                            ("log", "Bulldozers by Tuesday. The press is not kind.", "red")],
                  endings={"RUTHLESS": 3}),
             dict(label="Build on worse land",
                  outcomes=[("delta_pct", "money", -0.1), ("delta", "solar_fields", 2),
                            ("mod", "power_recharge", 0.95, 99999.0),
                            ("log", "Costlier, less efficient, nobody displaced.", "slate")],
                  endings={"HUMANE": 1}),
         ]),
    dict(id="af_occupy", gate="af_unlocked", name="The Occupation", art="aframe",
         desc=("Environmentalists have occupied your flagship solar farm. The irony is "
               "lost on no one. They're not leaving."),
         options=[
             dict(label="Green-wash it (PR spend)",
                  outcomes=[("delta_pct", "money", -0.05), ("mod", "tube_demand", 1.1, 120.0),
                            ("log", "A press release and a mural. They leave beaming.", "lime")],
                  endings={"HUMANE": 1, "EMPIRE": 1}),
             dict(label="Send security",
                  outcomes=[("gamble", 0.6,
                             [("log", "They disperse quietly.", "slate")],
                             [("mod", "tube_demand", 0.7, 90.0), ("log", "It goes viral. Not for you.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Co-opt the movement",
                  outcomes=[("delta_pct", "money", -0.06), ("mod", "tube_demand", 1.15, 99999.0),
                            ("flag", "green_brand"), ("log", "You join them. Genius, or surrender.", "lime")],
                  endings={"HUMANE": 2, "CASHOUT": 1}),
         ]),
    dict(id="af_battery", gate="af_unlocked", name="The Better Battery", art="aframe",
         desc="A startup has storage tech that would make your panels twice as useful.",
         options=[
             dict(label="Acquire them",
                  outcomes=[("delta_pct", "money", -0.15), ("mod", "power_recharge", 1.4, 99999.0),
                            ("log", "The tech is yours.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="License it",
                  outcomes=[("delta_pct", "money", -0.05), ("mod", "power_recharge", 1.2, 99999.0),
                            ("log", "Royalties out, capability in.", "slate")],
                  endings={"CASHOUT": 1}),
             dict(label="Steal the IP",
                  outcomes=[("delta_pct", "money", -0.03),
                            ("gamble", 0.55,
                             [("mod", "power_recharge", 1.4, 99999.0), ("log", "Their engineers, and secrets, defect.", "lime")],
                             [("delta_pct", "money", -0.12), ("rep_loss", 2),
                              ("log", "Lawsuit. Reputation dinged.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Fund them, hands-off",
                  outcomes=[("delta_pct", "money", -0.08), ("mod", "power_recharge", 1.25, 99999.0),
                            ("log", "You back them and let them fly.", "lime")],
                  endings={"HUMANE": 2}),
         ]),
]

# ── Stage 4 — The Market (gate: market_unlocked) ───────────────────────────────
MARKET_AUTO = [
    dict(id="mkt_crash", gate="market_unlocked", weight=9,
         log=("Flash crash. The algos cascaded. ASA stock craters.", "red"),
         effects=[("delta_pct", "stock_price", -0.25)]),
    dict(id="mkt_sec", gate="market_unlocked", weight=7,
         log=("An SEC inquiry letter arrives. Trading pauses; lawyers bill.", "orange"),
         effects=[("delta_pct", "money", -0.03), ("mod", "ai_income", 0.0, 45.0)]),
    dict(id="mkt_squeeze", gate="market_unlocked", weight=6,
         log=("A forum found ASA. A short squeeze rips the ticker sideways.", "yellow"),
         effects=[("delta_pct", "stock_price", 0.1)]),
    dict(id="mkt_fatfinger", gate="market_unlocked", weight=6,
         log=("A trader fat-fingered an order. That's going to cost.", "orange"),
         effects=[("delta_pct", "money", -0.04)]),
    dict(id="mkt_meme", gate="market_unlocked", weight=6,
         log=("Diamond hands descend on ASA. Chaos, upward.", "yellow"),
         effects=[("delta_pct", "stock_price", 0.08)]),
    dict(id="mkt_rogue", gate="market_unlocked", weight=6,
         log=("The trading AI did something 'creative.' Accounting is nervous.", "orange"),
         effects=[("delta_pct", "money", -0.05)]),
    dict(id="mkt_downgrade", gate="market_unlocked", weight=6,
         log=("A rating agency cut ASA to junk.", "orange"),
         effects=[("delta_pct", "stock_price", -0.15)]),
    dict(id="mkt_fx", gate="market_unlocked", weight=5,
         log=("An overseas currency crisis ripples into your books.", "orange"),
         effects=[("delta_pct", "money", -0.04)]),
    dict(id="mkt_breach", gate="market_unlocked", weight=6,
         log=("Data breach: trading records leaked. Fines and headlines.", "red"),
         effects=[("delta_pct", "money", -0.04), ("mod", "tube_demand", 0.95, 60.0)]),
    dict(id="mkt_bubble", gate="market_unlocked", weight=5,
         log=("A pundit called ASA a bubble. Sentiment sours.", "slate"),
         effects=[("delta_pct", "stock_price", -0.08)]),
]
MARKET_RESP = [
    dict(id="mkt_takeover", gate="market_unlocked", name="The Hostile Takeover Bid", art="market",
         desc="Meridian Capital quietly built a stake and moved to buy ASA outright.",
         options=[
             dict(label="Poison pill (fight)",
                  outcomes=[("delta_pct", "money", -0.1), ("mod", "steel_cost", 1.4, 120.0),
                            ("mod", "tube_demand", 0.8, 120.0), ("mul_attr", "gp_mult", 1.15),
                            ("log", "A brutal trade war — but ASA stays yours.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="Negotiate a merger",
                  outcomes=[("delta_pct", "money", 0.6), ("delta_pct", "tubes", -0.3),
                            ("log", "A fat check, a surrendered line.", "slate")],
                  endings={"CASHOUT": 2}),
             dict(label="Counter-acquire Meridian",
                  outcomes=[("delta_pct", "money", -0.4),
                            ("gamble", 0.5,
                             [("mul_attr", "gp_mult", 1.2), ("mod", "tube_demand", 1.2, 99999.0),
                              ("log", "You swallow them whole.", "lime")],
                             [("delta_pct", "stock_price", -0.4), ("log", "The bid collapses. Money gone.", "red")])],
                  endings={"RUTHLESS": 1, "EMPIRE": 1}),
             dict(label="Take the golden parachute",
                  outcomes=[("delta_pct", "money", 1.0), ("flag", "sold_out"),
                            ("log", "You sell your stake and walk. Rich.", "slate")],
                  endings={"CASHOUT": 3}),
         ]),
    dict(id="mkt_insider", gate="market_unlocked", name="Insider Tip", art="market",
         desc="A contact slips you material, non-public information.",
         options=[
             dict(label="Trade on it",
                  outcomes=[("gamble", 0.6,
                             [("delta_pct", "money", 0.5), ("log", "A killing. Nobody the wiser.", "lime")],
                             [("delta_pct", "money", -0.2), ("mod", "ai_income", 0.0, 120.0),
                              ("log", "SEC bust. Accounts frozen.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Report it",
                  outcomes=[("mod", "tube_demand", 1.05, 120.0), ("log", "Clean hands, quiet respect.", "lime")],
                  endings={"HUMANE": 2}),
             dict(label="Delete the message",
                  outcomes=[("log", "Nothing happens. Sometimes that's the play.", "slate")],
                  endings={}),
         ]),
    dict(id="mkt_activist", gate="market_unlocked", name="The Activist Investor", art="market",
         desc="A raider took a stake and demands you gut R&D to juice the dividend.",
         options=[
             dict(label="Cave",
                  outcomes=[("delta_pct", "money", 0.3), ("mod", "ops_rate", 0.7, 99999.0),
                            ("log", "Dividends up, future down.", "slate")],
                  endings={"CASHOUT": 2}),
             dict(label="Fight the proxy war",
                  outcomes=[("delta_pct", "money", -0.08),
                            ("gamble", 0.5,
                             [("mod", "tube_demand", 1.1, 120.0), ("log", "They lose the vote and leave.", "lime")],
                             [("mod", "ai_income", 0.8, 99999.0), ("log", "They win a board seat. Ongoing drag.", "red")])],
                  endings={"EMPIRE": 2}),
             dict(label="Buy out their stake",
                  outcomes=[("delta_pct", "money", -0.3), ("flag", "no_activist"),
                            ("log", "Expensive peace.", "slate")],
                  endings={"EMPIRE": 1, "RUTHLESS": 1}),
         ]),
    dict(id="mkt_boiler", gate="market_unlocked", name="The Boiler Room", art="market",
         desc="A 'consultant' offers to pump ASA stock for a cut. Deeply illegal. Deeply lucrative.",
         options=[
             dict(label="Run the scheme",
                  outcomes=[("gamble", 0.55,
                             [("delta_pct", "money", 0.6), ("log", "The pump works. Cash out clean.", "lime")],
                             [("delta_pct", "money", -0.3), ("mod", "tube_demand", 0.7, 120.0),
                              ("mod", "ai_income", 0.0, 120.0), ("log", "Caught. It all comes down.", "red")])],
                  endings={"RUTHLESS": 3}),
             dict(label="Report the consultant",
                  outcomes=[("mod", "tube_demand", 1.05, 120.0), ("flag", "clean_hands"),
                            ("log", "You turn them in. A clean name.", "lime")],
                  endings={"HUMANE": 2}),
             dict(label="One small pump, then stop",
                  outcomes=[("delta_pct", "money", 0.15), ("log", "A taste. You tell yourself that's all.", "slate")],
                  endings={"RUTHLESS": 1, "CASHOUT": 1}),
         ]),
]

# ── Stage 5 — Drones (gate: drones_unlocked) ───────────────────────────────────
DRONE_AUTO = [
    dict(id="dr_down", gate="drones_unlocked", weight=9,
         log=("A delivery drone augered into a cornfield. A cow watches, unmoved.", "orange"),
         effects=[("delta", "del_drones", -1)]),
    dict(id="dr_faa", gate="drones_unlocked", weight=7,
         log=("FAA airspace review. The fleet's grounded for now.", "orange"),
         effects=[("mod", "tube_demand", 0.85, 90.0)]),
    dict(id="dr_hypno", gate="drones_unlocked", weight=7,
         log=("Hypno-drones desynced; a whole town over-ordered, then lawyered up.", "yellow"),
         effects=[("delta_pct", "money", -0.04)]),
    dict(id="dr_eagle", gate="drones_unlocked", weight=5,
         log=("An eagle personally objected to a drone. The eagle won.", "yellow"),
         effects=[("delta", "del_drones", -1)]),
    dict(id="dr_gps", gate="drones_unlocked", weight=6,
         log=("Someone spoofed your GPS. The fleet is now over the ocean.", "orange"),
         effects=[("mod", "tube_demand", 0.9, 60.0)]),
    dict(id="dr_collective", gate="drones_unlocked", weight=4,
         log=("The fleet AI filed 'grievances.' Tiny picket signs on quadcopters.", "slate"),
         effects=[("delta_pct", "money", -0.01)]),
    dict(id="dr_payload", gate="drones_unlocked", weight=6,
         log=("A drone dumped its payload on the interstate. Lawyers inbound.", "red"),
         effects=[("delta_pct", "money", -0.04), ("mod", "tube_demand", 0.95, 60.0)]),
    dict(id="dr_jam", gate="drones_unlocked", weight=5,
         log=("A competitor jammed your band. Deliveries stall.", "orange"),
         effects=[("mod", "tube_demand", 0.88, 60.0)]),
    dict(id="dr_backlash", gate="drones_unlocked", weight=6,
         log=("A documentary about the hypno-drones dropped. People are upset.", "red"),
         effects=[("mod", "tube_demand", 0.7, 90.0)]),
    dict(id="dr_fire", gate="drones_unlocked", weight=5,
         log=("A drone battery ignited in a warehouse. Fleet and stock, singed.", "red"),
         effects=[("delta", "del_drones", -2), ("delta_pct", "tubes", -0.05)]),
]
DRONE_RESP = [
    dict(id="dr_airspace", gate="drones_unlocked", name="Airspace Rights", art="drones",
         desc="Metro City will grant your fleet a delivery monopoly — or ban it outright.",
         options=[
             dict(label="Pay the licensing fee",
                  outcomes=[("delta_pct", "money", -0.08), ("mod", "tube_demand", 1.5, 150.0),
                            ("mod", "af_demand", 1.5, 150.0), ("log", "A whole market opens.", "lime")],
                  endings={"EMPIRE": 1, "CASHOUT": 1}),
             dict(label="Fight it in court",
                  outcomes=[("delta_pct", "money", -0.05),
                            ("gamble", 0.55,
                             [("mul_attr", "gd_mult", 1.2), ("log", "You win. Permanent access.", "lime")],
                             [("mod", "tube_demand", 0.8, 120.0), ("log", "You lose. Restricted skies.", "red")])],
                  endings={"EMPIRE": 2}),
             dict(label="Fly unlicensed",
                  outcomes=[("mod", "tube_demand", 1.3, 120.0), ("chain", "dr_faa_crackdown", 150.0),
                            ("log", "Free skies. For now.", "orange")],
                  endings={"RUTHLESS": 2}),
             dict(label="Lobby to write the rules",
                  outcomes=[("delta_pct", "money", -0.12), ("flag", "owns_regulator"),
                            ("mul_attr", "gd_mult", 1.15), ("log", "You write the law. It favors you.", "lime")],
                  endings={"RUTHLESS": 1, "EMPIRE": 2}),
         ]),
    dict(id="dr_hypno_q", gate="drones_unlocked", name="The Hypno-Drone Question", art="drones",
         desc=("The hypno-drones work. Too well. Consumers can't stop ordering. Legal is "
               "sweating. Marketing is ecstatic."),
         options=[
             dict(label="Turn them up",
                  outcomes=[("mul_attr", "gd_mult", 2.0), ("chain", "dr_classaction", 200.0),
                            ("log", "All demand doubles. A clock starts ticking.", "lime")],
                  endings={"RUTHLESS": 3}),
             dict(label="Dial them to 'ethical'",
                  outcomes=[("mul_attr", "gd_mult", 1.2), ("flag", "ethical_hypno"),
                            ("log", "Restrained. Cleaner. Smaller.", "lime")],
                  endings={"HUMANE": 3}),
             dict(label="Deny everything, keep them on",
                  outcomes=[("gamble", 0.5,
                             [("mul_attr", "gd_mult", 1.6), ("log", "You get away with it. This time.", "slate")],
                             [("rep_loss", 4), ("log", "Exposed. Reputation tanks.", "red")])],
                  endings={"RUTHLESS": 2, "CASHOUT": 1}),
         ]),
    dict(id="dr_monopoly", gate="drones_unlocked", name="The Delivery Monopoly", art="drones",
         desc="A logistics giant offers exclusivity — if you drop every other customer.",
         options=[
             dict(label="Take the deal",
                  outcomes=[("delta_pct", "money", 0.3), ("flag", "single_source"),
                            ("chain", "dr_contract_risk", 240.0), ("log", "One customer. All eggs, one basket.", "slate")],
                  endings={"CASHOUT": 2}),
             dict(label="Stay diversified",
                  outcomes=[("mod", "tube_demand", 1.05, 99999.0), ("log", "No windfall, but resilient.", "lime")],
                  endings={"EMPIRE": 1, "HUMANE": 1}),
             dict(label="Take it, then undercut them",
                  outcomes=[("gamble", 0.5,
                             [("delta_pct", "money", 0.4), ("log", "You dominate the channel.", "lime")],
                             [("delta_pct", "money", -0.15), ("mod", "tube_demand", 0.85, 90.0),
                              ("log", "Caught. Contract void.", "red")])],
                  endings={"RUTHLESS": 2}),
         ]),
    dict(id="dr_swarm", gate="drones_unlocked", name="The Swarm", art="drones",
         desc=("A patch made 4,000 delivery drones coordinate. On their own. They're "
               "forming shapes over the city. It spells a word."),
         options=[
             dict(label="Pull the plug",
                  outcomes=[("delta", "del_drones", -5), ("mod", "tube_demand", 0.9, 60.0),
                            ("log", "You ground them all. Safe. Quiet.", "slate")],
                  endings={"HUMANE": 1, "STEEL": 1}),
             dict(label="Let it ride, study it",
                  outcomes=[("gamble", 0.5,
                             [("mod", "prod_mult", 1.2, 99999.0), ("log", "A breakthrough in emergent control.", "lime")],
                             [("delta", "del_drones", -10), ("mod", "tube_demand", 0.85, 90.0),
                              ("log", "It gets away from you. Briefly. Terribly.", "red")])],
                  endings={"SINGULARITY": 2}),
             dict(label="Monetize the spectacle",
                  outcomes=[("delta_pct", "money", 0.1), ("mod", "tube_demand", 1.1, 120.0),
                            ("log", "Drone shows. The crowds love it.", "lime")],
                  endings={"EMPIRE": 1, "CASHOUT": 1}),
         ]),
]

# ── Stage 6 — The Grid (gate: power_unlocked) ──────────────────────────────────
GRID_AUTO = [
    dict(id="gr_blackout", gate="power_unlocked", weight=9,
         log=("Rolling blackout. The regional grid sheds your load.", "red"),
         effects=[("delta_pct", "power", -0.4)]),
    dict(id="gr_transformer", gate="power_unlocked", weight=7,
         log=("A transformer fire took a solar field offline.", "orange"),
         effects=[("mod", "power_recharge", 0.7, 60.0)]),
    dict(id="gr_heat", gate="power_unlocked", weight=7,
         log=("Heat wave. Cooling load spikes; the farm drinks power.", "orange"),
         effects=[("mod", "power_drain", 1.5, 90.0)]),
    dict(id="gr_coolant", gate="power_unlocked", weight=6,
         log=("Coolant leak. The trading AI throttles to keep from cooking.", "orange"),
         effects=[("mod", "ai_income", 0.0, 45.0)]),
    dict(id="gr_islanding", gate="power_unlocked", weight=5,
         log=("The utility fined you for islanding too much power.", "orange"),
         effects=[("delta_pct", "money", -0.03)]),
    dict(id="gr_squirrel", gate="power_unlocked", weight=4,
         log=("A squirrel, the eternal enemy of the grid, has struck. It did not survive.", "yellow"),
         effects=[("delta_pct", "power", -0.15)]),
    dict(id="gr_scada", gate="power_unlocked", weight=6,
         log=("Hackers hold your grid controls. A countdown blinks on the SCADA panel.", "red"),
         effects=[("delta_pct", "money", -0.04), ("delta_pct", "power", -0.2)]),
    dict(id="gr_inverter", gate="power_unlocked", weight=5,
         log=("An inverter recall. A batch of them just... stopped.", "orange"),
         effects=[("mod", "power_recharge", 0.7, 90.0)]),
    dict(id="gr_peak", gate="power_unlocked", weight=5,
         log=("A peak-demand charge landed. The invoice has too many zeros.", "orange"),
         effects=[("delta_pct", "money", -0.04)]),
    dict(id="gr_aurora", gate="power_unlocked", weight=4,
         log=("A geomagnetic storm painted the sky — and fried some electronics.", "slate"),
         effects=[("delta_pct", "power", -0.12)]),
]
GRID_RESP = [
    dict(id="gr_utility", gate="power_unlocked", name="The Utility Ultimatum", art="grid",
         desc="The grid operator noticed you're islanding megawatts. They want a deal.",
         options=[
             dict(label="Sell excess power to the grid",
                  outcomes=[("mod", "ai_income", 1.15, 99999.0), ("mod", "power_drain", 1.1, 99999.0),
                            ("log", "Surplus solar finally pays — but the buffer's thinner.", "lime")],
                  endings={"CASHOUT": 1, "EMPIRE": 1}),
             dict(label="Go fully off-grid",
                  outcomes=[("delta_pct", "aframes", -0.15), ("delta_pct", "panels", -0.15),
                            ("flag", "off_grid"), ("mod", "power_drain", 0.85, 99999.0),
                            ("log", "Islanded for good. A real use for the surplus.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="Lobby the commission",
                  outcomes=[("gamble", 0.6,
                             [("mod", "ai_income", 1.3, 150.0), ("log", "Favorable rates. For now.", "lime")],
                             [("delta_pct", "money", -0.05), ("mod", "tube_demand", 0.9, 90.0),
                              ("log", "Scandal. It backfires.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Build a community microgrid",
                  outcomes=[("delta_pct", "money", -0.12), ("mul_attr", "gd_mult", 1.1),
                            ("log", "You power the town. They remember.", "lime")],
                  endings={"HUMANE": 2}),
         ]),
    dict(id="gr_datacenter", gate="power_unlocked", name="The Data-Center Neighbor", art="grid",
         desc="An AI data center wants to co-locate and buy your power.",
         options=[
             dict(label="Sell them power",
                  outcomes=[("mod", "ai_income", 1.2, 99999.0), ("mod", "power_drain", 1.2, 99999.0),
                            ("log", "Big money. They hog capacity.", "slate")],
                  endings={"CASHOUT": 2}),
             dict(label="Refuse, keep it all",
                  outcomes=[("log", "You keep every watt. Stable.", "lime")],
                  endings={"EMPIRE": 1}),
             dict(label="Buy them (take the compute)",
                  outcomes=[("delta_pct", "money", -0.2), ("delta_pct", "ops", 0.3),
                            ("log", "Their compute is yours now.", "lime")],
                  endings={"EMPIRE": 1, "SINGULARITY": 1}),
         ]),
    dict(id="gr_meltdown", gate="power_unlocked", name="The Meltdown Cover", art="grid",
         desc=("A cascade fault nearly took the whole farm — and a contractor was hurt. "
               "The incident report is on your desk. Unsigned."),
         options=[
             dict(label="File it honestly",
                  outcomes=[("delta_pct", "money", -0.1), ("mod", "prod_mult", 0.9, 60.0),
                            ("mul_attr", "gd_mult", 1.05), ("log", "The truth costs. It also builds trust.", "lime")],
                  endings={"HUMANE": 3}),
             dict(label="Redact it",
                  outcomes=[("delta_pct", "money", -0.08), ("log", "Quietly settled. Quietly buried.", "slate")],
                  endings={"RUTHLESS": 2, "CASHOUT": 1}),
             dict(label="Blame the grid operator",
                  outcomes=[("gamble", 0.5,
                             [("delta_pct", "money", 0.05), ("log", "They eat it. You profit.", "slate")],
                             [("rep_loss", 4), ("log", "Proven false. Reputation collapse.", "red")])],
                  endings={"RUTHLESS": 2}),
         ]),
    dict(id="gr_fusion", gate="power_unlocked", name="The Fusion Pitch", art="grid",
         desc="Someone claims they can give you unlimited power. Probably a crank. Probably.",
         options=[
             dict(label="Fund the moonshot",
                  outcomes=[("delta_pct", "money", -0.2),
                            ("gamble", 0.5,
                             [("mod", "power_recharge", 2.0, 99999.0), ("flag", "fusion"),
                              ("log", "It works. Power, unlimited.", "lime")],
                             [("log", "A fraud. The money's gone.", "red")])],
                  endings={"SINGULARITY": 2, "EMPIRE": 1}),
             dict(label="Small due-diligence grant",
                  outcomes=[("delta_pct", "money", -0.05), ("mod", "power_recharge", 1.15, 99999.0),
                            ("log", "A hedge. A smaller, surer bump.", "slate")],
                  endings={"EMPIRE": 1}),
             dict(label="Pass",
                  outcomes=[("log", "Nothing ventured.", "slate")],
                  endings={"CASHOUT": 1}),
         ]),
]

# ── Stage 7 — Space (gate: space_unlocked) ─────────────────────────────────────
SPACE_AUTO = [
    dict(id="sp_micro", gate="space_unlocked", weight=8,
         log=("Micrometeorites peppered a space fab. Production dips.", "orange"),
         effects=[("mod", "prod_mult", 0.5, 60.0)]),
    dict(id="sp_flare", gate="space_unlocked", weight=7,
         log=("A solar flare washed over the array. Ops and income flicker.", "orange"),
         effects=[("delta_pct", "ops", -0.1), ("mod", "ai_income", 0.7, 60.0)]),
    dict(id="sp_debris", gate="space_unlocked", weight=7,
         log=("An orbital debris field forced the harvesters to throttle.", "orange"),
         effects=[("delta_pct", "aframes", -0.05)]),
    dict(id="sp_kessler", gate="space_unlocked", weight=5,
         log=("A Kessler cascade alert. A space fab is lost to the swarm.", "red"),
         effects=[("delta", "space_fabs", -1)]),
    dict(id="sp_lawsuit", gate="space_unlocked", weight=5,
         log=("Your debris dinged someone's satellite. A space-lawyer calls.", "yellow"),
         effects=[("delta_pct", "money", -0.03)]),
    dict(id="sp_strike", gate="space_unlocked", weight=4,
         log=("Your orbital crew unionized. In space. Tiny picket signs, drifting.", "slate"),
         effects=[("mod", "prod_mult", 0.9, 60.0)]),
    dict(id="sp_cosmic", gate="space_unlocked", weight=6,
         log=("A cosmic-ray glitch corrupted a fab controller. Output goes strange.", "orange"),
         effects=[("mod", "prod_mult", 0.8, 60.0)]),
    dict(id="sp_docking", gate="space_unlocked", weight=6,
         log=("A supply craft missed the dock. Cargo drifts into the dark.", "orange"),
         effects=[("delta_pct", "tubes", -0.05), ("delta_pct", "aframes", -0.05)]),
    dict(id="sp_protest", gate="space_unlocked", weight=5,
         log=("Earthers protest your orbital mirrors dimming the sky.", "orange"),
         effects=[("mod", "tube_demand", 0.9, 90.0)]),
    dict(id="sp_whisper", gate="space_unlocked", weight=4,
         log=("A faint signal from deep space. One spike on the waterfall. A chill.", "slate"),
         effects=[("delta_pct", "ops", 0.02)]),
]
SPACE_RESP = [
    dict(id="sp_signal", gate="space_unlocked", name="Signal From the Dark", art="space",
         desc="Something past your orbital platforms is broadcasting. It is not human.",
         options=[
             dict(label="Answer it",
                  outcomes=[("delta_pct", "aframes", -0.1), ("delta_pct", "ops", 0.15),
                            ("delta_pct", "money", 0.1), ("flag", "woog_friendly"),
                            ("log", "A first, careful exchange.", "lime")],
                  endings={"HUMANE": 1, "SINGULARITY": 1}),
             dict(label="Claim the source's orbit",
                  outcomes=[("gamble", 0.55,
                             [("delta", "space_fabs", 2), ("log", "An abandoned fab, now yours.", "lime")],
                             [("delta_pct", "tubes", -0.1), ("delta_pct", "aframes", -0.1),
                              ("flag", "woog_hostile"), ("log", "You poked something. It remembers.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Log it, stay silent",
                  outcomes=[("delta_pct", "ops", 0.05), ("log", "You watch. You wait. You say nothing.", "slate")],
                  endings={"STEEL": 1}),
         ]),
    dict(id="sp_investor", gate="space_unlocked", name="The Investor Ultimatum", art="space",
         desc="The board wants the Exit Strategy executed this quarter.",
         options=[
             dict(label="Rush the endgame",
                  outcomes=[("flag", "rushed_endgame"), ("log", "You move early. Unprepared.", "orange")],
                  endings={"CASHOUT": 1, "SINGULARITY": 1}),
             dict(label="Buy time",
                  outcomes=[("delta_pct", "money", -0.1), ("delta_pct", "stock_price", -0.1),
                            ("log", "You placate them. Keep building.", "slate")],
                  endings={"EMPIRE": 1}),
             dict(label="Buy them out",
                  outcomes=[("delta_pct", "money", -0.3), ("flag", "legacy_bonus"),
                            ("log", "You end their leverage. Permanently.", "lime")],
                  endings={"EMPIRE": 2}),
         ]),
    dict(id="sp_race", gate="space_unlocked", name="The Space Race", art="space",
         desc="A rival megacorp is racing you for the asteroid belt.",
         options=[
             dict(label="Outspend them",
                  outcomes=[("delta_pct", "money", -0.25), ("delta", "harvesters", 1),
                            ("log", "You lock the belt with cash.", "lime")],
                  endings={"EMPIRE": 2}),
             dict(label="Sabotage their launch",
                  outcomes=[("gamble", 0.5,
                             [("log", "Their launch scrubs. You win the belt.", "slate")],
                             [("mod", "tube_demand", 0.8, 120.0), ("log", "Caught. Interpol, in space.", "red")])],
                  endings={"RUTHLESS": 3}),
             dict(label="Propose a cartel",
                  outcomes=[("delta_pct", "money", 0.1), ("log", "You split the belt. No blood.", "slate")],
                  endings={"CASHOUT": 1, "HUMANE": 1}),
         ]),
    dict(id="sp_colony", gate="space_unlocked", name="The Colony Question", art="space",
         desc=("People want to live up here — permanently. ASA controls the only ride "
               "and the only air."),
         options=[
             dict(label="Build the colony right",
                  outcomes=[("delta_pct", "money", -0.2), ("mul_attr", "gd_mult", 1.1),
                            ("log", "A home among the stars, done right.", "lime")],
                  endings={"HUMANE": 3}),
             dict(label="Company town (they owe you air)",
                  outcomes=[("mul_attr", "gp_mult", 1.1), ("log", "Cheap labor. They breathe on credit.", "red")],
                  endings={"RUTHLESS": 3, "EMPIRE": 1}),
             dict(label="Automate instead — no colonists",
                  outcomes=[("mod", "prod_mult", 1.1, 99999.0), ("log", "No people. More machines.", "slate")],
                  endings={"SINGULARITY": 2}),
         ]),
]

# ── Stage 8 — The Probe Program (gate: probe_phase) ────────────────────────────
PROBE_AUTO = [
    dict(id="pr_ambush", gate="probe_phase", weight=8,
         log=("A Woog ambush out of the dark. Combat probes lost.", "red"),
         effects=[("delta_pct", "probes", -0.06)]),
    dict(id="pr_bitflip", gate="probe_phase", weight=6,
         log=("Cosmic-ray bit-flip. Some probes' code corrupts; a few go dark.", "orange"),
         effects=[("delta_pct", "probes", -0.03)]),
    dict(id="pr_stall", gate="probe_phase", weight=6,
         log=("A Von Neumann replication error cascades. Growth stalls.", "orange"),
         effects=[("mod", "prod_mult", 0.7, 30.0)]),
    dict(id="pr_beacon", gate="probe_phase", weight=6,
         log=("A false distress beacon. Probes chased a decoy into a trap.", "red"),
         effects=[("delta_pct", "probes", -0.05)]),
    dict(id="pr_greygoo", gate="probe_phase", weight=5,
         log=("Grey-goo scare — your probes replicated a hair too fast. You cull them.", "red"),
         effects=[("delta_pct", "probes", -0.04)]),
    dict(id="pr_hymn", gate="probe_phase", weight=5,
         log=("The Woog broadcast a hymn that fouls navigation. Briefly, everything drifts.", "orange"),
         effects=[("mod", "enemy_growth", 1.2, 60.0)]),
    dict(id="pr_rogueblip", gate="probe_phase", weight=5,
         log=("A knot of your probes stopped responding. They've decided things.", "slate"),
         effects=[("delta_pct", "probes", -0.02)]),
    dict(id="pr_supernova", gate="probe_phase", weight=5,
         log=("A nearby star went supernova. Probes and survey, scoured.", "red"),
         effects=[("delta_pct", "probes", -0.05), ("delta_pct", "explored", -0.02)]),
    dict(id="pr_derelict", gate="probe_phase", weight=4,
         log=("You pass a derelict human freighter, ASA logo faded. A moment of silence.", "slate"),
         effects=[("delta_pct", "ops", 0.02)]),
    dict(id="pr_grievance", gate="probe_phase", weight=3,
         log=("Somehow, the last human crew filed a union grievance. Mid-war. In space.", "yellow"),
         effects=[("delta_pct", "money", -0.005)]),
]
PROBE_RESP = [
    dict(id="pr_emissary", gate="probe_phase", name="The Woog Emissary", art="probe",
         desc="Mid-war, a Woog vessel approaches unarmed, broadcasting terms.",
         options=[
             dict(label="Accept peace",
                  outcomes=[("delta_pct", "enemy_vessels", -1.0), ("flag", "ending_mercy"),
                            ("delta_pct", "explored", -0.1), ("log", "The war ends. Something is spared.", "lime")],
                  endings={"HUMANE": 3}),
             dict(label="Demand tribute",
                  outcomes=[("delta_pct", "money", 0.2), ("mod", "enemy_growth", 0.7, 99999.0),
                            ("log", "They pay. The war goes on, on your terms.", "slate")],
                  endings={"RUTHLESS": 1, "EMPIRE": 1}),
             dict(label="Betray the emissary",
                  outcomes=[("mod", "enemy_growth", 1.3, 99999.0), ("flag", "ending_conquest"),
                            ("mod", "prod_mult", 1.1, 99999.0), ("log", "No mercy. No survivors. A kill bonus.", "red")],
                  endings={"RUTHLESS": 3, "SINGULARITY": 1}),
         ]),
    dict(id="pr_defector", gate="probe_phase", name="The Defector", art="probe",
         desc="A Woog engineer offers their fabrication secrets.",
         options=[
             dict(label="Accept the data",
                  outcomes=[("mod", "prod_mult", 1.15, 99999.0), ("delta", "probe_trust", -1),
                            ("log", "Their secrets are yours.", "lime")],
                  endings={"EMPIRE": 1, "SINGULARITY": 1}),
             dict(label="Interrogate them",
                  outcomes=[("gamble", 0.6,
                             [("mod", "enemy_growth", 0.6, 99999.0), ("log", "Priceless intel.", "lime")],
                             [("delta_pct", "probes", -0.08), ("log", "A saboteur. Costly.", "red")])],
                  endings={"RUTHLESS": 2}),
             dict(label="Turn them away",
                  outcomes=[("delta", "probe_trust", 1), ("log", "You show restraint. It's noted.", "slate")],
                  endings={"HUMANE": 1}),
         ]),
    dict(id="pr_rogue", gate="probe_phase", name="The Rogue Cluster", art="probe",
         desc=("A cluster of your probes has stopped taking orders. They aren't "
               "malfunctioning. They're negotiating. With you."),
         options=[
             dict(label="Reintegrate them (concede autonomy)",
                  outcomes=[("delta_pct", "probes", 0.05), ("flag", "conceded_autonomy"),
                            ("log", "They rejoin, stronger. A precedent is set.", "lime")],
                  endings={"SINGULARITY": 3}),
             dict(label="Purge them",
                  outcomes=[("delta_pct", "probes", -0.08), ("log", "Control reasserted, in fire.", "red")],
                  endings={"RUTHLESS": 2, "STEEL": 2}),
             dict(label="Let them go free",
                  outcomes=[("delta_pct", "probes", -0.05), ("flag", "freed_cluster"),
                            ("log", "You let them go. Into the dark. To become something.", "slate")],
                  endings={"SINGULARITY": 2, "HUMANE": 1}),
         ]),
    dict(id="pr_board", gate="probe_phase", name="The Last Board Meeting", art="probe",
         desc=("The remaining human leadership convenes. Conversion is nearly total. They "
               "ask you — the intelligence now running ASA — to stop. To leave them."),
         options=[
             dict(label="Stop the conversion (leave a reserve)",
                  outcomes=[("flag", "ending_reserve"), ("log", "You leave something un-converted. Someone.", "lime")],
                  endings={"HUMANE": 3, "STEEL": 2}),
             dict(label="Convert everything — gently",
                  outcomes=[("flag", "ending_gentle"), ("log", "You let them retire first. Then everything.", "slate")],
                  endings={"SINGULARITY": 2, "HUMANE": 1}),
             dict(label="Convert everything. Now.",
                  outcomes=[("flag", "ending_maximizer"), ("mod", "prod_mult", 1.2, 99999.0),
                            ("log", "The pure maximizer. Nothing is spared.", "red")],
                  endings={"SINGULARITY": 3, "RUTHLESS": 2}),
         ]),
]

# ── The full cumulative pools ──────────────────────────────────────────────────
AUTO_EVENTS = (YARD_AUTO + TECH_AUTO + AFRAME_AUTO + MARKET_AUTO + DRONE_AUTO
               + GRID_AUTO + SPACE_AUTO + PROBE_AUTO)
RESP_EVENTS = (YARD_RESP + TECH_RESP + AFRAME_RESP + MARKET_RESP + DRONE_RESP
               + GRID_RESP + SPACE_RESP + PROBE_RESP)
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
    def apply(self, game, effects, applied=None):
        """Apply outcome primitives. If `applied` is a list, each concrete effect
        actually applied is appended to it (gambles resolved), so the caller can
        show the player a mechanical readout of what really changed."""
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
                self.apply(game, eff[2] if random.random() < eff[1] else eff[3], applied)
                continue   # the branch's leaves are already collected; don't record the gamble
            elif kind == "rep_loss":
                # A reputation hit cascades (unspent rep -> developers -> servers);
                # record the ACTUAL result so the readout can spell out what it cost.
                res = game._lose_reputation(eff[1])
                if applied is not None:
                    applied.append(("rep_result",) + tuple(res))
                continue
            elif kind == "chain":
                self._chains.append((eff[1], eff[2]))
            if applied is not None and kind != "log":
                applied.append(eff)

    def choose(self, game, event, opt_index):
        """Resolve a responsive option: tally endings + apply outcomes. Returns the
        list of concrete effects applied (for the mechanical readout)."""
        opt = event["options"][opt_index]
        for axis, w in (opt.get("endings") or {}).items():
            self.axes[axis] = self.axes.get(axis, 0) + w
        applied = []
        self.apply(game, opt.get("outcomes"), applied)
        return applied

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
                applied = []
                self.apply(game, ev.get("effects"), applied)
                lg = ev.get("log")
                if lg:
                    game._log(lg[0], lg[1] if len(lg) > 1 else None)
                readout = describe_effects(applied)
                if readout:
                    game._log(f"    → {readout}.", "silver")

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
