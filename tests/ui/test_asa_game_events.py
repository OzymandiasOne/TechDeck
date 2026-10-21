"""ASA: The Video Game — the event engine's outcome primitives.

Headless: the events module is deliberately UI-free and reads the game through
plain attributes, so a stub stands in for the widget.

Reported 2026-10-15 (Matt Overfield, 0.8.7.8): "Random events can cause Space
Fabricator & drone QTY to go negative." He hit two of the six attributes the
"delta" primitive touches; all six had the same hole.
"""

import re
from pathlib import Path

from techdeck.ui.widgets.steelbeams_events import EventEngine, describe_effects

SRC = Path("techdeck/ui/widgets/steelbeams_events.py")

# Every attribute "delta" is used on. All are counts of things you own.
COUNTS = ("developers", "solar_fields", "del_drones",
          "space_fabs", "harvesters", "probe_trust")


class _Game:
    """The handful of attributes the engine touches."""

    def __init__(self, **attrs):
        for name in COUNTS:
            setattr(self, name, 0)
        self.money = 1000.0
        self.tubes = 100.0
        self._flags = set()
        self.logged = []
        for k, v in attrs.items():
            setattr(self, k, v)

    def _log(self, text, color=None):
        self.logged.append((text, color))


def _apply(effects, **attrs):
    g = _Game(**attrs)
    applied = []
    EventEngine().apply(g, effects, applied)
    return g, applied


# ── the floor ──────────────────────────────────────────────────────────────

def test_a_count_cannot_go_negative():
    g, _ = _apply([("delta", "del_drones", -2)], del_drones=1)
    assert g.del_drones == 0


def test_every_count_delta_touches_is_floored():
    """Matt reported two of the six. Pin all of them, or the next event finds
    whichever one was left out."""
    for name in COUNTS:
        g, _ = _apply([("delta", name, -5)], **{name: 1})
        assert getattr(g, name) == 0, name


def test_an_ordinary_loss_is_untouched():
    g, _ = _apply([("delta", "del_drones", -2)], del_drones=5)
    assert g.del_drones == 3


def test_gains_are_untouched():
    g, _ = _apply([("delta", "space_fabs", 3)], space_fabs=2)
    assert g.space_fabs == 5


def test_a_loss_at_zero_stays_at_zero():
    g, _ = _apply([("delta", "harvesters", -1)], harvesters=0)
    assert g.harvesters == 0


# ── the readout tells the truth ────────────────────────────────────────────

def test_the_readout_reports_what_was_actually_lost():
    # Asked for 2, only 1 there to take: the player is told 1.
    _, applied = _apply([("delta", "del_drones", -2)], del_drones=1)
    assert applied == [("delta", "del_drones", -1)]
    assert "-1" in describe_effects(applied)


def test_an_effect_that_changed_nothing_is_not_reported():
    _, applied = _apply([("delta", "harvesters", -3)], harvesters=0)
    assert applied == []


def test_a_normal_effect_still_reports_in_full():
    _, applied = _apply([("delta", "developers", -2)], developers=9)
    assert applied == [("delta", "developers", -2)]


# ── the floor survives a gamble, which recurses into apply ─────────────────

def test_a_gamble_branch_is_floored_too():
    g, applied = _apply([("gamble", 1.0, [("delta", "space_fabs", -4)], [])],
                        space_fabs=1)
    assert g.space_fabs == 0
    assert applied == [("delta", "space_fabs", -1)]


# ── the other primitives cannot cross zero, so they are left alone ─────────

def test_percentage_and_multiplier_effects_stay_positive():
    """delta_pct and mul_attr MULTIPLY, so a positive value stays positive.
    That is why the floor belongs on "delta" alone — pinned here so nobody
    'fixes' the other two by clamping money to an integer zero."""
    g, _ = _apply([("delta_pct", "money", -0.9)], money=100.0)
    assert 0 < g.money < 100

    g, _ = _apply([("mul_attr", "tubes", 0.5)], tubes=100.0)
    assert g.tubes == 50.0


# ── the data has not grown a new count behind the test's back ──────────────

def test_delta_is_only_ever_used_on_the_counts_this_test_knows():
    """If someone adds ("delta", "money", -50) the floor would silently start
    clamping cash, and a player in debt would be handed zero."""
    used = set(re.findall(r'\("delta",\s*"(\w+)"', SRC.read_text(encoding="utf-8")))
    unexpected = used - set(COUNTS)
    assert not unexpected, (
        f"'delta' is now used on {sorted(unexpected)}, which this floor would "
        "clamp at zero. Confirm that is right for those attributes, then add "
        "them to COUNTS.")
