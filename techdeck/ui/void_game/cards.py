"""Card and sigil definitions - pure data, no Qt.

About half the depth of the game that inspired this: fifteen sigils, two dozen
cards. Every sigil NAME and icon should show the METAPHOR, not the maths
(Mullins's rule): a winged thing flies over, a gorgon's gaze weakens.

Deathcards (the ones a beaten player forges) are registered at runtime with
`register_deathcard`; they live in CARDS like any other card.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── sigils ───────────────────────────────────────────────────────────────
WINGED = "winged"            # strikes past the card in front of it, straight at him
WARDEN = "warden"            # stands in the way of winged things
VENOM = "venom"              # whatever it wounds, dies
THREE_MOUTHS = "three_mouths"  # bites the lane in front AND the lanes either side
TWO_MOUTHS = "two_mouths"    # bites the lanes either side, NOT the one in front
UNDYING = "undying"          # when it dies it returns to your hand, stronger
WORTHY = "worthy"            # counts as three offerings when sacrificed
GROWS = "grows"              # survives a turn on the board and becomes something else
GAZE = "gaze"                # the card facing it loses 1 power
THORNS = "thorns"            # whatever strikes it is wounded for 1
SENTINEL = "sentinel"        # moves to face a card of his that arrives opposite an empty lane
ENDLESS = "endless"          # offered up, it does not die
SPAWN = "spawn"              # when played, another of it enters your hand
HERALD = "herald"            # the cards beside it strike for 1 more
ABHORRED = "abhorred"        # nothing will strike it

SIGILS = {
    WINGED: ("WINGED", "It strikes past whatever stands in front of it."),
    WARDEN: ("WARDEN", "Winged things cannot pass it."),
    VENOM: ("VENOM", "Whatever it wounds, dies."),
    THREE_MOUTHS: ("THREE MOUTHS", "It bites the lane ahead and the lanes either side."),
    TWO_MOUTHS: ("TWO MOUTHS", "It bites the lanes either side, never the one ahead."),
    UNDYING: ("UNDYING", "When it dies it returns to your hand, stronger."),
    WORTHY: ("WORTHY", "Offered up, it counts as three."),
    GROWS: ("GROWS", "Left alone for a turn, it becomes something else."),
    GAZE: ("GAZE", "The thing facing it loses 1 power."),
    THORNS: ("THORNS", "Whatever strikes it is wounded for 1."),
    SENTINEL: ("SENTINEL", "When one of his arrives facing an empty lane, it moves to meet it."),
    ENDLESS: ("ENDLESS", "Offered up, it does not die."),
    SPAWN: ("SPAWN", "When it is played, another of it enters your hand."),
    HERALD: ("HERALD", "The cards beside it strike for 1 more."),
    ABHORRED: ("ABHORRED", "Nothing will strike it."),
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
    rare: bool = False         # offered only at the rarer stops; he plays them late
    deathcard: bool = False    # forged by a beaten player


_ALL = [
    CardDef("votary", "VOTARY", 0, 1, note="It came willingly. They always do."),
    CardDef("mote", "MOTE", 1, 1, sigils=(WINGED,), note="A spark that got away."),
    CardDef("scarab", "SCARAB", 1, 2, 1, note="It rolls the sun. It does not ask why."),
    CardDef("hound", "HOUND", 2, 2, 2, note="It has your scent now."),
    CardDef("huginn", "HUGINN", 1, 1, 1, sigils=(WINGED,), note="Thought, on black wings."),
    CardDef("weigher", "THE WEIGHER", 1, 1, 2, sigils=(VENOM,),
            note="He weighs the heart. It is always too heavy."),
    CardDef("gorgon", "GORGON", 1, 2, 2, sigils=(GAZE,), note="Do not look. You are looking."),
    CardDef("ouroboros", "OUROBOROS", 1, 1, 2, sigils=(UNDYING,),
            note="The end of it is the beginning of it."),
    CardDef("hydra", "HYDRA", 1, 2, 1, sigils=(TWO_MOUTHS,), note="Cut one. Count again."),
    CardDef("thornback", "THORNBACK", 1, 2, 1, sigils=(THORNS,), note="Touch it and learn."),
    CardDef("watcher", "WATCHER", 2, 3, 2, sigils=(SENTINEL,), note="It goes where the gap is."),
    CardDef("martyr", "MARTYR", 0, 1, 1, sigils=(ENDLESS,), note="It dies for you. Then it does it again."),
    CardDef("locust", "LOCUST", 2, 2, 2, sigils=(SPAWN,), note="Where there was one."),
    CardDef("wraith", "WRAITH", 3, 1, 2, REMNANT, note="It has no weight. It has an edge."),
    CardDef("cerberus", "CERBERUS", 2, 3, 3, sigils=(THREE_MOUTHS,),
            note="Three mouths. One hunger."),
    CardDef("sleeper", "THE SLEEPER", 4, 6, 3, note="It is not dead. It is waiting for the stars."),
    CardDef("monolith", "MONOLITH", 0, 5, 3, REMNANT, sigils=(WARDEN,),
            note="It was here before the ground was."),
    CardDef("dead_star", "DEAD STAR", 0, 2, 1, sigils=(GROWS,), grows_into="nova",
            note="The light you see left it long ago."),
    CardDef("nova", "NOVA", 4, 1, 1, note="Oh. There it is."),
    CardDef("crowned", "THE CROWNED", 1, 2, 4, REMNANT, sigils=(HERALD,),
            note="Those beside it stand taller."),
    # rare: seen at the rarer stops, and in his hand near the end
    CardDef("seraph", "SERAPH", 6, 3, 1, sigils=(WINGED,), rare=True,
            note="Six wings. It is not here to comfort you."),
    CardDef("leviathan", "LEVIATHAN", 7, 7, 4, rare=True, note="The sea was made to hold it."),
    # Not in any deck. It comes for you when you have nothing left to draw.
    CardDef("famine", "FAMINE", 1, 1, sigils=(ABHORRED,), note="What is left when nothing is left."),
]
CARDS: dict[str, CardDef] = {c.id: c for c in _ALL}

# What can be offered at a stop on the road. Not the votary, not the famine,
# not what only grows out of something else.
_NEVER_OFFERED = {"votary", "famine", "nova"}
CHOICE_POOL = [c.id for c in _ALL if c.id not in _NEVER_OFFERED and not c.rare]
RARE_POOL = [c.id for c in _ALL if c.rare]

# What you sit down with: six cards, a curve from cheap to vast (the game that
# inspired this starts you with four). The votaries are the rest.
STARTER_DECK = ["hound", "scarab", "huginn", "thornback", "weigher", "dead_star"]
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

# What he draws from as the road goes on. Each tier adds to the last.
HIS_TIERS = [
    ["votary", "scarab", "huginn", "hound", "mote"],
    ["gorgon", "weigher", "hydra", "thornback", "watcher", "locust", "dead_star"],
    ["cerberus", "sleeper", "wraith", "martyr"],
    ["leviathan", "seraph", "crowned"],
]
HIS_PET = "hound"            # the one he minds losing


def register_deathcard(name: str, power: int, health: int, cost: int, cost_kind: str,
                       sigils: tuple[str, ...], note: str = "") -> CardDef:
    """A beaten player's card. The id is stable for the name, so a saved run
    and a saved deck agree on it."""
    slug = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_") or "nameless"
    cid = "death_" + slug
    n = 2
    while cid in CARDS and CARDS[cid].name != name.upper():
        cid = f"death_{slug}_{n}"; n += 1
    d = CardDef(cid, name.upper(), power, health, cost, cost_kind, tuple(sigils),
                note=note or "It was someone, once.", deathcard=True)
    CARDS[cid] = d
    return d
