"""The abuse goblin, the thing that lives in the Assistant's terminal.

**Why this exists.** The first build treated every unmatched line as a task to
capture. That is wrong, and it is wrong in an annoying way: someone who types
"this PO sheet is a nightmare" wanted to *say* that, not add a chore called
"this PO sheet is a nightmare". People need somewhere to vent at 6:40am when
OneDrive has eaten a file, and a tool that answers a complaint with a to-do item
is a tool you stop talking to.

So: **free text is conversation. Nothing is filed unless you ask.** Capture
happens on the Add a task button, the Tasks tab, `/task`, or an explicit
"remind me to…". Everything else reaches the goblin.

**The rules the goblin obeys.**

1. It never insults the user. Ever. The abuse flows *in*, and whatever comes
   back out is aimed at the situation (Excel, OneDrive, the printer, the
   schedule) and never at the person typing.
2. It doesn't fix, advise, or reframe unless asked. "That sounds hard, have you
   tried…" is exactly the wrong answer to a vent.
3. He is a dumb sweetheart, not a wit. Third person, small words, tries
   hard, slightly out of his depth. The comedy is earnestness, not snark,
   and it keeps the screen safe for a colleague walking past.
4. It shuts up in the professional theme. Client demos get a plain,
   neutral acknowledgement and nothing else.

No Qt, no I/O, no state on disk. Pure text in, text out.
"""

from __future__ import annotations

import random
import re
from typing import Dict, List, Optional

from techdeck.core.flavor import CompendiumState

# ── Moods ────────────────────────────────────────────────────────────────────

MOOD_RAGE = "rage"
MOOD_AT_ME = "at_me"
MOOD_TIRED = "tired"
MOOD_WIN = "win"
MOOD_GREETING = "greeting"
MOOD_THANKS = "thanks"
MOOD_ASK = "ask"
MOOD_NEUTRAL = "neutral"


_RAGE_WORDS = re.compile(
    # "tired OF something" is a complaint about that thing, not exhaustion.
    # It belongs here, and rage is tested first so it wins.
    r"\b(hate|hates|hating|sick of|tired of|fed up|furious|livid|raging|screaming|"
    r"stupid|idiotic|moronic|garbage|trash|useless|worthless|broken|busted|"
    r"nightmare|disaster|ridiculous|absurd|insane|unbelievable|infuriating|"
    r"killing me|driving me|had it|over this|done with|why (?:the|does|won'?t|"
    r"is|can'?t)|again|AGAIN|seriously|for the love of|come on|what the|"
    r"piece of|damn|damned|dammit|hell|crap|bs|bullshit|screwed|jesus|"
    r"christ|god)\b", re.I)

_TIRED_WORDS = re.compile(
    r"\b(exhausted|tired|knackered|wiped|drained|burnt out|burned out|"
    r"fried|spent|running on|no energy|long day|long week|rough day|"
    r"rough week|can'?t anymore|over it|checked out|need a break|"
    r"need coffee|monday)\b", re.I)

_WIN_WORDS = re.compile(
    r"\b(finally|got it|nailed it|nailed|smashed|crushed|shipped|"
    r"figured it out|fixed it|it works|working now|sorted|sorted it|"
    r"done and dusted|yes+|woo+|let'?s go|beautiful|perfect|love it|"
    r"good news|clean run|no errors)\b", re.I)

_GREETING_WORDS = re.compile(
    r"^\s*(hi|hey+|hello|yo+|sup|morning|good morning|afternoon|"
    r"good afternoon|evening|howdy|oi)\b", re.I)

_THANKS_WORDS = re.compile(
    r"\b(thanks|thank you|thx|ty|cheers|appreciate it|appreciated|"
    r"you'?re the best|good bot|nice one)\b", re.I)

# Things worth naming back at the user. The goblin is far funnier when it knows
# what you're actually angry at.
_TARGETS: Dict[str, str] = {
    "excel": "Excel", "spreadsheet": "that spreadsheet", "xlsx": "Excel",
    "onedrive": "OneDrive", "sharepoint": "SharePoint", "sync": "the sync",
    "teams": "Teams", "outlook": "Outlook", "email": "email",
    "printer": "the printer", "print": "the printer",
    "pdf": "that PDF", "acrobat": "Acrobat",
    "autocad": "AutoCAD", "solidworks": "SolidWorks",
    "driveworks": "DriveWorks", "cad": "the CAD",
    "vpn": "the VPN", "network": "the network", "server": "the server",
    "it ": "IT", "helpdesk": "the helpdesk",
    "schedule": "the schedule", "forecast": "the forecast",
    "po ": "the PO", "po.": "the PO", "rev c": "the REV C",
    "batch": "that batch", "nest": "that nest", "packet": "the packet",
    "drawing": "the drawings", "drawings": "the drawings",
    "meeting": "that meeting", "windows": "Windows",
    "techdeck": "TechDeck",
}

_CAPS_WORD = re.compile(r"\b[A-Z]{3,}\b")
_WORD = re.compile(r"\b[A-Za-z]{3,}\b")

# Is the complaint pointed at WOOGY, rather than at Excel or the printer?
# Second person, his name, or the app itself. Answering "i hate you" with a
# line about some imaginary third party is the one thing an abuse goblin
# really cannot get wrong.
_AT_ME = re.compile(
    r"\b(?:you|you'?re|youre|your|yours|yourself|u|ur|woogy|techdeck)\b"
    r"|\bthis (?:app|thing|program|terminal|assistant|bot|goblin)\b", re.I)

# Aimed language only counts as abuse when it is actually unkind. "can you
# check the schedule" is second person too.
_INSULT = re.compile(
    r"\b(hate|suck|sucks|sucked|stupid|dumb|idiot|moron|useless|worthless|"
    r"pointless|annoying|irritating|garbage|trash|rubbish|terrible|awful|"
    r"lame|cringe|unfunny|not funny|worst|shut up|shutup|shut it|be quiet|"
    r"go away|leave me alone|nonsense|creepy|weird)\b", re.I)


def is_aimed_at_me(text: str) -> bool:
    """True when the user is having a go at Woogy himself.

    Two ways in. The obvious one is second person ("i hate you", "shut up
    woogy"). The other is a **bare verdict**: "not funny", "lame", "boring".
    Those name no subject at all, and in a two-party chat the only thing they
    can be about is the last thing said, which was his. The guard is that
    there must be no recognised external culprit in the line, so "excel sucks"
    still gets the Excel treatment.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if not _INSULT.search(raw):
        return False
    if _AT_ME.search(raw):
        return True
    return len(raw.split()) <= 4 and read_target(raw) is None


def read_mood(text: str) -> str:
    """Classify one line of free text.

    Rage is checked before everything else on purpose: "thanks for NOTHING" and
    "finally, after the fourth crash" are complaints, not gratitude and not
    wins, and reading them the cheerful way is the single most irritating thing
    a chat box can do.
    """
    raw = (text or "").strip()
    if not raw:
        return MOOD_NEUTRAL

    shouting = bool(_CAPS_WORD.search(raw)) and len(raw) > 6
    bangs = raw.count("!") >= 2 or "?!" in raw

    # Before general rage: if it's pointed at him, he takes it rather than
    # commiserating about a culprit that doesn't exist.
    if is_aimed_at_me(raw):
        return MOOD_AT_ME
    # _INSULT counts here too: "excel sucks" is plainly anger, and "sucks"
    # lives in the insult list rather than the rage list.
    if _RAGE_WORDS.search(raw) or _INSULT.search(raw) or shouting or bangs:
        return MOOD_RAGE
    if _TIRED_WORDS.search(raw):
        return MOOD_TIRED
    if _WIN_WORDS.search(raw):
        return MOOD_WIN
    if _THANKS_WORDS.search(raw):
        return MOOD_THANKS
    if _GREETING_WORDS.match(raw):
        return MOOD_GREETING
    if raw.rstrip().endswith("?"):
        return MOOD_ASK
    return MOOD_NEUTRAL


def read_target(text: str) -> Optional[str]:
    """The thing being complained about, if the goblin recognises it."""
    lowered = f" {(text or '').lower()} "
    for needle, label in _TARGETS.items():
        if needle in lowered:
            return label
    return None


# ── What it says ─────────────────────────────────────────────────────────────

_RAGE = [
    "Woogy don't like that. Woogy don't like that at all.",
    "That is a bad one. Woogy is sorry.",
    "Ohhh. Ohhh, that is rotten.",
    "Woogy would fight it for you. Woogy would lose. But Woogy would go.",
    "You keep going. Woogy is listening real good.",
    "That should not happen to a nice person.",
    "Woogy is making an angry face. You cannot see it. It is very angry.",
    "Hrrmph. No. Bad.",
    "Woogy wrote it in the bad book. Woogy keeps a bad book.",
    "You have been SO patient about this. Woogy noticed.",
    "Say more. Woogy has all day. Woogy has nothing but day.",
    "That is not fair and Woogy will say so to anybody who asks.",
    "Oh no. Oh no no no.",
    "Woogy don't understand it, but Woogy is mad about it too.",
    "V-very bad. Maybe the worst one today.",
    "Woogy is on your side. Woogy is always on your side.",
]

# Aimed at him. He takes it, cheerfully, and stays. No sulking, no arguing
# back, no wounded bit, all three would make the user manage HIS feelings,
# which is backwards.
_AT_ME_LINES = [
    "Okay. Woogy can take it.",
    "That is fair. Woogy is not very good.",
    "Woogy don't mind. Woogy is still here.",
    "Yeah. Woogy gets that a lot.",
    "Better Woogy than the printer, maybe.",
    "Go on. Woogy has thick skin. Woogy has like four skins.",
    "Okay! ...okay.",
    "Woogy will be right here when you are done.",
    "You are allowed. Woogy don't have feelings, only opinions.",
    "Hrmph. Fine. Woogy still likes you.",
    "Woogy has been yelled at by better software.",
    "That one got Woogy a little. Woogy is okay.",
    "Alright, alright. Woogy will just be over here.",
    "Woogy is not offended. Woogy is barely a guy.",
]

_RAGE_TARGETED = [
    "{target} did that on purpose. Woogy has always said so.",
    "Woogy does not trust {target}. Never has.",
    "{target} again! {target} is always doing this.",
    "Woogy is putting {target} in the bad book.",
    "Ohhh, {target}. Woogy knows all about {target}.",
    "If Woogy sees {target}, Woogy will say something. Probably. Maybe.",
    "{target} is a menace and nobody listens to Woogy about it.",
    "Woogy warned everybody about {target}. Nobody wrote it down.",
    "Not {target} again. Woogy is tired of {target}.",
]

_TIRED = [
    "You should sit down. Woogy will watch the list.",
    "Long one, huh. Woogy is tired too and Woogy don't even do anything.",
    "That is a lot of day for one person.",
    "Woogy says you are allowed to be tired. Woogy is in charge of that.",
    "Go get a coffee. Woogy will not move.",
    "Nothing on the list is running away. Woogy checked.",
    "You did plenty already. Woogy saw.",
    "Rest your eyes. Woogy has three and it don't help.",
]

_WIN = [
    "HEY! Woogy saw that!",
    "V-very good! Woogy approves.",
    "Look at you go. Woogy is telling everybody.",
    "Woogy knew you would. Woogy did not doubt one second.",
    "That is the good stuff. Woogy is happy.",
    "Woogy is writing this one in the GOOD book.",
    "Wooo! ...that was Woogy. Woogy did that.",
    "Good! Good good good.",
]

_GREETING = [
    "Hi! Woogy is here. What'll it be.",
    "Oh! You came back. Woogy waited.",
    "Hello hello. Who are we mad at today.",
    "Woogy is up. Woogy has been up. Woogy don't sleep.",
    "Hey. Tell Woogy things.",
    "There you are. Woogy was just standing here.",
]

_THANKS = [
    "Aw. Woogy did nothing. Woogy just sat here.",
    "Ohh. Um. You are welcome.",
    "Woogy likes when you say that.",
    "That is Woogy's job. Woogy has one job.",
    "Don't. Woogy will get shy.",
    "Any time. Woogy means it.",
]

# ASK catches ANY question, including the self-doubting kind ("am i crazy?").
# So no line here may open with a bare affirmative: "Probably!" is a shrug
# about the world, but sitting under that question it reads as agreeing the
# user is crazy. Every line stays pointed at the situation or at Woogy.
_ASK = [
    "Woogy don't know. Woogy is just a guy.",
    "You are not crazy. Woogy thinks it is bad too.",
    "Woogy has opinions and no power. It is a bad combination.",
    "Hmm. Woogy is thinking. ...Woogy is done thinking. Woogy don't know.",
    "If you want Woogy to DO something, /help has the list. Woogy can read.",
    "Woogy would bet it is not you. It is usually not you.",
    "Woogy is rarely sure about anything, but Woogy is sure that is annoying.",
]

_NEUTRAL = [
    "Woogy is listening.",
    "Mm-hm.",
    "Okay.",
    "Woogy hears you.",
    "Woogy is listening. A bead of cold sweat rolls down his forehead. "
    "At any moment, he might have a panic attack.",
    "Yeah?",
    "Woogy is still here.",
    "Right, right.",
]

_PROFESSIONAL = [
    "Noted.",
    "Understood.",
    "Okay.",
    "Got it.",
]

# Dropped in every so often, never twice close together, the whole point of
# the rewrite is that people can trust this box not to file things behind
# their back, and trust needs saying out loud once in a while.
NUDGE = ("(Woogy don't write any of this down. Press “Add a task” or type "
         "/task if you want it kept)")
NUDGE_EVERY = 7


class Goblin:
    """One goblin per Assistant page. Holds only the shuffled pools and a
    counter, so it can be constructed anywhere and thrown away."""

    def __init__(self, professional: bool = False):
        self.professional = professional
        self._pools = {
            MOOD_RAGE: CompendiumState(_RAGE),
            MOOD_AT_ME: CompendiumState(_AT_ME_LINES),
            "rage_targeted": CompendiumState(_RAGE_TARGETED),
            MOOD_TIRED: CompendiumState(_TIRED),
            MOOD_WIN: CompendiumState(_WIN),
            MOOD_GREETING: CompendiumState(_GREETING),
            MOOD_THANKS: CompendiumState(_THANKS),
            MOOD_ASK: CompendiumState(_ASK),
            MOOD_NEUTRAL: CompendiumState(_NEUTRAL),
            "professional": CompendiumState(_PROFESSIONAL),
        }
        self._spoken = 0

    def respond(self, text: str) -> str:
        """One reply to one line of free text."""
        self._spoken += 1
        if self.professional:
            return self._pools["professional"].get_line()

        mood = read_mood(text)
        if mood == MOOD_RAGE:
            target = read_target(text)
            # Namedrop when we know the culprit, but not every single time.
            # A goblin that always says the magic word stops being funny.
            if target and random.random() < 0.65:
                return self._pools["rage_targeted"].get_line().format(target=target)
        return self._pools[mood].get_line()

    def wants_nudge(self) -> bool:
        """True on the first reply and every Nth after it, the reminder that
        nothing here is being filed."""
        return self._spoken == 1 or (self._spoken % NUDGE_EVERY == 0)


def looks_actionable(text: str) -> bool:
    """Could this line plausibly be a task, if the user decided it was?

    Used only to decide whether to OFFER a one-click "make that a task", never
    to file anything. It deliberately says no to venting: a complaint contains
    plenty of verbs, and offering to add "this printer is garbage" to someone's
    to-do list is the joke the goblin exists to prevent.
    """
    raw = (text or "").strip()
    if len(raw) < 6 or len(raw.split()) > 20:
        return False
    if read_mood(raw) in (MOOD_RAGE, MOOD_AT_ME, MOOD_TIRED, MOOD_WIN,
                          MOOD_GREETING, MOOD_THANKS):
        return False
    if raw.rstrip().endswith("?"):
        return False
    words = _WORD.findall(raw.lower())
    if not words:
        return False
    return bool(_ACTION_VERBS.search(raw))


_ACTION_VERBS = re.compile(
    r"\b(call|email|send|order|check|review|fix|update|finish|start|make|"
    r"build|write|print|pull|cut|run|book|schedule|ask|confirm|chase|"
    r"file|submit|clean|sort|count|measure|weld|stamp|scan|log|draft|"
    r"quote|invoice|ship|deliver|pick up|drop off|follow up|look at|"
    r"talk to|get)\b", re.I)
