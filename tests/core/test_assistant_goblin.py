"""The abuse goblin.

Two things are being protected here and only one of them is the jokes:

1. **Nothing gets filed on a guess.** `looks_actionable` decides whether to
   *offer* a one-click capture, and it must say no to venting, a complaint is
   full of verbs, and "this printer is garbage" is not a to-do item.
2. **The abuse only ever flows one way.** The goblin absorbs it and aims
   whatever comes back at the situation, never at the person typing.
"""

import pytest

from techdeck.core.assistant import goblin
from techdeck.core.assistant.goblin import Goblin


# ── mood ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "this PO sheet is a nightmare",
    "I hate this spreadsheet",
    "onedrive ate the file AGAIN",
    "WHY WON'T IT SYNC",
    "are you kidding me?!",
    "this printer is garbage",
    "seriously??",
    "sick of this",
])
def test_rage_is_recognised(text):
    assert goblin.read_mood(text) == goblin.MOOD_RAGE


def test_tired_of_something_is_rage_not_exhaustion():
    """"Tired OF X" is a complaint about X. Answering it with "sit down and
    rest" misses the point entirely."""
    assert goblin.read_mood("i am so tired of excel") == goblin.MOOD_RAGE
    assert goblin.read_mood("i am so tired today") == goblin.MOOD_TIRED


@pytest.mark.parametrize("text,mood", [
    ("absolutely exhausted", goblin.MOOD_TIRED),
    ("long week", goblin.MOOD_TIRED),
    ("finally got it working", goblin.MOOD_WIN),
    ("nailed it", goblin.MOOD_WIN),
    ("morning", goblin.MOOD_GREETING),
    ("hey", goblin.MOOD_GREETING),
    ("thanks", goblin.MOOD_THANKS),
    ("is that normal?", goblin.MOOD_ASK),
    ("just thinking out loud", goblin.MOOD_NEUTRAL),
])
def test_other_moods(text, mood):
    assert goblin.read_mood(text) == mood


def test_sarcastic_thanks_reads_as_rage_not_gratitude():
    """"thanks for NOTHING" answered with "any time!" is the single most
    irritating thing a chat box can do."""
    assert goblin.read_mood("thanks for NOTHING") == goblin.MOOD_RAGE


def test_empty_input_is_neutral():
    assert goblin.read_mood("") == goblin.MOOD_NEUTRAL


# ── targets ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,label", [
    ("excel did it again", "Excel"),
    ("onedrive is broken", "OneDrive"),
    ("the printer hates me", "the printer"),
    ("this rev c is wrong", "the REV C"),
])
def test_targets_are_recognised(text, label):
    assert goblin.read_target(text) == label


def test_an_unknown_target_is_fine():
    assert goblin.read_target("everything is bad") is None


# ── responses ────────────────────────────────────────────────────────────────

def test_it_always_says_something():
    g = Goblin()
    for text in ("this is broken", "hey", "thanks", "tired", "finally", "hm"):
        assert g.respond(text).strip()


def test_a_targeted_rage_line_never_leaves_its_placeholder_showing():
    """Every {target} template must actually be formatted."""
    g = Goblin()
    for _ in range(60):
        assert "{target}" not in g.respond("excel is broken AGAIN")


def test_it_never_turns_on_the_user():
    """The one rule that isn't negotiable: abuse goes IN, and what comes back
    is aimed at the situation. ("you're allowed to be tired" is fine, this is
    about blame and dismissal, not the word "you".)"""
    banned = ("your fault", "that's on you", "user error", "skill issue",
              "stupid of you", "you should have", "you should've",
              "you messed", "you broke", "you're wrong", "you're being",
              "calm down", "relax", "get over it", "it's not that bad")
    g = Goblin()
    for _ in range(400):
        for text in ("this is broken and I hate it", "WHY", "I'm exhausted",
                     "thanks", "hey", "is this normal?", "hm"):
            said = g.respond(text).lower()
            for phrase in banned:
                assert phrase not in said, said


def test_professional_mode_gets_a_plain_acknowledgement():
    g = Goblin(professional=True)
    for _ in range(20):
        assert g.respond("this is a nightmare AGAIN") in goblin._PROFESSIONAL


def test_the_nudge_fires_first_then_rarely():
    g = Goblin()
    fired = []
    for _ in range(goblin.NUDGE_EVERY * 3):
        g.respond("hm")
        fired.append(g.wants_nudge())
    assert fired[0] is True
    assert fired[1] is False
    assert sum(fired) <= 4          # occasional reassurance, not nagging


# ── looks_actionable ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "call Dan about the rev C",
    "order the 4130 tube",
    "check the pallet count",
    "email the drawings to QA",
])
def test_a_plain_job_can_be_offered(text):
    assert goblin.looks_actionable(text) is True


@pytest.mark.parametrize("text", [
    "this printer is garbage",
    "I hate this spreadsheet",
    "WHY WON'T IT SYNC",
    "absolutely exhausted",
    "finally got it working",
    "thanks",
    "morning",
    "should I check the pallet count?",
    "hm",
    "well this is a very long ramble about nothing in particular that goes on "
    "and on and is clearly not a task anybody would want on a list",
])
def test_venting_rambling_and_questions_are_never_offered(text):
    assert goblin.looks_actionable(text) is False
