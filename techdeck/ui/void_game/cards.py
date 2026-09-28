"""Card and sigil definitions - pure data, no Qt.

A quarter of the depth of the game that inspired this, on purpose: eight sigils,
a dozen cards. Every sigil NAME and icon should show the METAPHOR, not the maths
(Mullins's rule): a winged thing flies over, a gorgon's gaze weakens.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── sigils ───────────────────────────────────────────────────────────────
WINGED = "winged"            # strikes past the card in front of it, straight at him
WARDEN = "warden"            # stands in the way of winged things
VENOM = "venom"              # whatever it wounds, dies
THREE_MOUTHS = "three_mouths"  # bites the lane in front AND the lanes either side
UNDYING = "undying"          # when it dies it returns to your hand, stronger
WORTHY = "worthy"            # counts as three offerings when sacrificed
GROWS = "grows"              # survives a turn on the board and becomes something else
GAZE = "gaze"                # the card facing it loses 1 power

SIGILS = {
    WINGED: ("WINGED", "It strikes past whatever stands in front of it."),
    WARDEN: ("WARDEN", "Winged things cannot pass it."),
    VENOM: ("VENOM", "Whatever it wounds, dies."),
    THREE_MOUTHS: ("THREE MOUTHS", "It bites the lane ahead and the lanes either side."),
    UNDYING: ("UNDYING", "When it dies it returns to your hand, stronger."),
    WORTHY: ("WORTHY", "Offered up, it counts as three."),
    GROWS: ("GROWS", "Left alone for a turn, it becomes something else."),
    GAZE: ("GAZE", "The thing facing it loses 1 power."),
}

OFFER = "offer"              # pay by sacrificing your own cards
REMNANT = "remnant"          # pay with what your dead leave behind


@dataclass(frozen=True)
class CardDef:
    id: str
    name: str
    power: int
    health: int
    cost: int = 0
    cost_kind: str = OFFER
    sigils: tuple[str, ...] = ()
    grows_into: str = ""
    note: str = ""             # one line of flavour, for the inspect panel


_ALL = [
    CardDef("votary", "VOTARY", 0, 1, note="It came willingly. They always do."),
    CardDef("scarab", "SCARAB", 1, 2, 1, note="It rolls the sun. It does not ask why."),
    CardDef("hound", "HOUND", 2, 2, 2, note="It has your scent now."),
    CardDef("huginn", "HUGINN", 1, 1, 1, sigils=(WINGED,), note="Thought, on black wings."),
    CardDef("weigher", "THE WEIGHER", 1, 1, 2, sigils=(VENOM,),
            note="He weighs the heart. It is always too heavy."),
    CardDef("gorgon", "GORGON", 1, 2, 2, sigils=(GAZE,), note="Do not look. You are looking."),
    CardDef("ouroboros", "OUROBOROS", 1, 1, 2, sigils=(UNDYING,),
            note="The end of it is the beginning of it."),
    CardDef("cerberus", "CERBERUS", 2, 3, 3, sigils=(THREE_MOUTHS,),
            note="Three mouths. One hunger."),
    CardDef("sleeper", "THE SLEEPER", 4, 6, 3, note="It is not dead. It is waiting for the stars."),
    CardDef("monolith", "MONOLITH", 0, 5, 3, REMNANT, sigils=(WARDEN,),
            note="It was here before the ground was."),
    CardDef("dead_star", "DEAD STAR", 0, 2, 1, sigils=(GROWS,), grows_into="nova",
            note="The light you see left it long ago."),
    CardDef("nova", "NOVA", 4, 1, 1, note="Oh. There it is."),
]
CARDS: dict[str, CardDef] = {c.id: c for c in _ALL}

# What you sit down with. Ten cards: a curve from cheap to vast.
STARTER_DECK = ["scarab", "scarab", "hound", "hound", "huginn", "weigher",
                "gorgon", "ouroboros", "cerberus", "sleeper", "monolith", "dead_star"]
VOTARY_PILE = 10

# His first game. Each turn: the cards he slides into his INCOMING row. A lane of
# None means "wherever there is room". After the script runs out he improvises.
FIRST_GAME_PLAN = [
    [("votary", 1)],
    [("scarab", 2)],
    [],
    [("huginn", 3)],
    [("hound", 0)],
    [],
    [("gorgon", None), ("votary", None)],
    [("weigher", None)],
    [("hound", None)],
    [("cerberus", None)],
    [("dead_star", None)],
    [("sleeper", None)],
]
HIS_POOL = ["scarab", "hound", "huginn", "gorgon", "weigher", "dead_star"]
