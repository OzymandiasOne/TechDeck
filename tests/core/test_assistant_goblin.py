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


# ── aimed at him, versus aimed at the world ──────────────────────────────────

@pytest.mark.parametrize("text", [
    "i hate you",
    "you suck",
    "shut up woogy",
    "youre useless",
    "you are so annoying",
    "this app is garbage",
    "this thing is pointless",
    "not funny",
    "lame",
])
def test_abuse_pointed_at_woogy_is_recognised(text):
    """Answering "i hate you" with a line about some imaginary third party is
    the one thing an abuse goblin really cannot get wrong."""
    assert goblin.read_mood(text) == goblin.MOOD_AT_ME


@pytest.mark.parametrize("text", [
    "excel sucks",
    "onedrive is garbage",
    "this printer is useless",
    "the schedule is garbage",
    "this rev c is stupid",
])
def test_abuse_pointed_at_the_world_still_gets_the_world_treatment(text):
    """A bare verdict only reads as aimed at him when nothing else in the line
    could be the subject."""
    assert goblin.read_mood(text) == goblin.MOOD_RAGE


@pytest.mark.parametrize("text", [
    "can you check the schedule",
    "what do you think",
    "how are you",
    "your plan looks right",
])
def test_second_person_alone_is_not_an_insult(text):
    assert goblin.read_mood(text) != goblin.MOOD_AT_ME


def test_he_takes_it_rather_than_arguing_back():
    """No sulking, no arguing, no wounded bit. All three would make the user
    manage HIS feelings, which is backwards."""
    g = Goblin()
    banned = ("rude", "that's not nice", "sorry you feel", "i tried",
              "how dare", "wow.", "no need for that")
    for _ in range(200):
        said = g.respond("i hate you").lower()
        for phrase in banned:
            assert phrase not in said, said


def test_venting_at_him_is_never_offered_as_a_task():
    assert goblin.looks_actionable("i hate you") is False
    assert goblin.looks_actionable("shut up woogy") is False


def test_no_answer_to_a_question_reads_as_a_verdict_on_the_user():
    """ASK catches any question, including "am i crazy?". A line that opens
    with a bare affirmative agrees with it."""
    for line in goblin._ASK:
        opener = line.split()[0].strip(".,!").lower()
        assert opener not in ("yes", "probably", "maybe", "definitely",
                              "certainly", "sure", "yep", "yeah"), line


def test_woogy_talks_like_woogy():
    """Third person, his own name, the Emporium voice. If most of the pool
    stops sounding like him the character has drifted."""
    pools = (goblin._RAGE + goblin._AT_ME_LINES + goblin._TIRED
             + goblin._WIN + goblin._GREETING + goblin._THANKS
             + goblin._ASK + goblin._NEUTRAL)
    named = [line for line in pools if "Woogy" in line]
    assert len(named) > len(pools) * 0.6


# ── conversational range ─────────────────────────────────────────────────────
# Every case below is a line somebody actually typed at him in a real session
# where 80% of the conversation fell through to the generic pool.

@pytest.mark.parametrize("text,mood", [
    # questions about him, not requests of him
    ("whats up", goblin.MOOD_ABOUT_HIM),
    ("what did you do today", goblin.MOOD_ABOUT_HIM),
    ("so basically you did nothing", goblin.MOOD_ABOUT_HIM),
    ("you dont understand anything that I'm saying, do you?", goblin.MOOD_ABOUT_HIM),
    ("are you real", goblin.MOOD_ABOUT_HIM),
    ("lol okay woogy", goblin.MOOD_LAUGH),
    ("lol", goblin.MOOD_LAUGH),
    ("hahaha", goblin.MOOD_LAUGH),
    ("Wow that was surpisingly responsive", goblin.MOOD_COMPLIMENT),
    ("good bot", goblin.MOOD_COMPLIMENT),
    ("no need to get an attitude", goblin.MOOD_SCOLDED),
    ("ya i kno that", goblin.MOOD_ACK),
    ("kay", goblin.MOOD_ACK),
    ("k", goblin.MOOD_ACK),
    ("okay wise guy", goblin.MOOD_ACK),
    ("YEAH", goblin.MOOD_SHOUT),
    ("you said that already", goblin.MOOD_REPEAT),
    ("omg", goblin.MOOD_EXCLAIM),
    ("just stop", goblin.MOOD_STOP),
    ("you know what", goblin.MOOD_LEADIN),
    ("I didnt threaten you yet", goblin.MOOD_THREAT),
    ("IVE HAD IT UP TO HERE WITH YOU", goblin.MOOD_THREAT),
    ("huh?", goblin.MOOD_CONFUSED),
])
def test_he_has_an_answer_for_the_things_people_actually_type(text, mood):
    assert goblin.read_mood(text) == mood


def test_a_lead_in_gets_what():
    """Asked for by name: a bare "you know what" is waiting for "What?" before
    the real sentence arrives."""
    g = Goblin()
    replies = {g.respond("you know what") for _ in range(30)}
    assert any(r.lower().startswith("what") for r in replies)


def test_a_request_of_him_is_not_a_question_about_him():
    """"can you check the schedule" is second person too. Answering it with
    "Woogy is just a guy" would be worse than saying nothing."""
    assert goblin.read_mood("can you check the schedule") != goblin.MOOD_ABOUT_HIM
    assert goblin.read_mood("would you look at the PO") != goblin.MOOD_ABOUT_HIM


def test_every_mood_has_a_pool_behind_it():
    """A mood with no pool raises a KeyError the moment somebody types the
    phrase that triggers it, which is the worst place to find out."""
    g = Goblin()
    for name in dir(goblin):
        if not name.startswith("MOOD_"):
            continue
        assert getattr(goblin, name) in g._pools, name


def test_the_real_conversation_no_longer_falls_through(qapp=None):
    """The session this whole batch came from: 17 of 21 lines hit the generic
    pool. None should now."""
    said = [
        "hello", "whats up", "what did you do today", "so basically you did nothing",
        "lol okay woogy", "you dont understand anything that I'm saying, do you?",
        "Wow that was surpisingly responsive", "no need to get an attitude",
        "ya i kno that", "YEAH", "okay wise guy", "you said that already",
        "omg", "just stop", "lol", "you know what", "I didnt threaten you yet",
        "kay", "k", "lame",
    ]
    generic = [t for t in said if goblin.read_mood(t) == goblin.MOOD_NEUTRAL]
    assert generic == []
