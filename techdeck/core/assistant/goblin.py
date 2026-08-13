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
# Added after watching a real conversation in which 80% of what the user said
# fell through to MOOD_NEUTRAL. Each of these is a thing somebody actually
# typed at him, not a category invented in the abstract.
MOOD_ABOUT_HIM = "about_him"      # "what did you do today"
MOOD_LAUGH = "laugh"              # "lol"
MOOD_COMPLIMENT = "compliment"    # "that was surprisingly responsive"
MOOD_ACK = "ack"                  # "k", "kay", "ya i kno that"
MOOD_LEADIN = "leadin"            # "you know what"  ->  "What?"
MOOD_REPEAT = "repeat"            # "you said that already"
MOOD_STOP = "stop"                # "just stop"
MOOD_SHOUT = "shout"              # "YEAH"
MOOD_SCOLDED = "scolded"          # "no need to get an attitude"
MOOD_THREAT = "threat"            # "I didnt threaten you yet"
MOOD_EXCLAIM = "exclaim"          # "omg"
MOOD_CONFUSED = "confused"        # "what?"


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


# A bare opener that is waiting for "What?" before the real sentence arrives.
_LEADIN = re.compile(
    r"^\s*(?:you know what|guess what|hey woogy|woogy|listen|check this out|"
    r"one more thing|so anyway)\s*[.!,]?\s*$", re.I)

_REPEAT_CALLOUT = re.compile(
    r"\b(?:you (?:said|say) that already|already said that|you already said|"
    r"said that before|repeat(?:ing)? yourself|same (?:thing|one) again|"
    r"you keep saying)\b", re.I)

# Questions ABOUT him, as opposed to requests OF him. "can you check the
# schedule" is second person too, and answering it with "Woogy is just a guy"
# would be worse than saying nothing.
_ABOUT_HIM = re.compile(
    r"^\s*(?:what'?s up|whats up|sup|wassup|how'?s it going)\b"
    r"|\b(?:what|how|who|why)\s+(?:are|is|do|did|does|was|were)\s+(?:you|woogy)\b"
    r"|\bwhat did you (?:do|say|mean)\b"
    r"|\b(?:are|do|did|can|will|would)\s+you\s+(?:ok|okay|real|alive|there|"
    r"listening|understand|know|remember|sleep|eat|think|care|even|actually)\b"
    r"|\byou (?:don'?t|do not|dont) (?:understand|know|get|listen)\b"
    r"|\byou (?:did|do|didn'?t do) (?:nothing|anything)\b"
    r"|\btell me about (?:yourself|you|woogy)\b", re.I)

# (?:ha|he){2,} rather than haha+ : "hahaha" is ha-ha-ha, so haha+ only ever
# matched a stutter like "hahaa".
_LAUGH = re.compile(r"\b(?:lol+|lmao+|rofl|(?:ha|he){2,}|heh|hah)\b|😂|🤣", re.I)

_COMPLIMENT = re.compile(
    r"\b(?:good (?:job|bot|one|answer|boy)|nice one|well done|not bad|"
    r"impressive|responsive|clever|that was (?:good|great|funny)|"
    r"love (?:it|that)|amazing|excellent|proud of you)\b", re.I)

_STOP = re.compile(
    r"^\s*(?:just |please )?(?:stop|quit it|enough|no more|cut it out|"
    r"nevermind|never mind|forget it|drop it)\b", re.I)

_SCOLDED = re.compile(
    r"\b(?:no need to|don'?t be|watch it|excuse me|attitude|sass\w*|snippy|"
    r"uncalled for|that'?s mean|be nice|settle down)\b", re.I)

_THREAT = re.compile(
    r"\b(?:threat\w*|or else|watch out|fight me|square up|had it up to here|"
    r"i'?ve had it|ive had it|so help me|don'?t make me|dont make me)\b", re.I)

_EXCLAIM = re.compile(
    r"^\s*(?:omg|oh my god|ugh+|oof|jeez|geez|sheesh|wow+|whoa+|bruh|welp|"
    r"hm+|hmm+|eh)\b", re.I)

_CONFUSED = re.compile(r"^\s*(?:what|huh|come again|say again|\?+)[?!.]*\s*$", re.I)

# Short affirmatives. Matched on the OPENER plus a length cap, because "kay",
# "ya i kno that" and "okay wise guy" are all the same shrug.
_ACK_OPENER = re.compile(
    r"^\s*(?:k|kay|ok|okay|sure|right|alright|aight|mhm+|yeah|yea|ya|yep|yup|"
    r"yes|fine|cool|gotcha|word|true)\b", re.I)


def is_ack(text: str) -> bool:
    raw = (text or "").strip()
    return bool(_ACK_OPENER.match(raw)) and len(raw.split()) <= 5


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

    # Order is precedence, most specific first. The named phrases come before
    # the broad sentiment buckets, and MOOD_ASK stays near the bottom because
    # "how are you?" is about HIM before it is a question.
    if is_aimed_at_me(raw):
        return MOOD_AT_ME
    if _REPEAT_CALLOUT.search(raw):
        return MOOD_REPEAT
    if _SCOLDED.search(raw):
        return MOOD_SCOLDED
    if _THREAT.search(raw):
        return MOOD_THREAT
    if _LEADIN.match(raw):
        return MOOD_LEADIN
    if _ABOUT_HIM.search(raw):
        return MOOD_ABOUT_HIM
    if _LAUGH.search(raw):
        return MOOD_LAUGH
    if _COMPLIMENT.search(raw):
        return MOOD_COMPLIMENT
    if _STOP.match(raw):
        return MOOD_STOP
    # _INSULT counts here too: "excel sucks" is plainly anger, and "sucks"
    # lives in the insult list rather than the rage list.
    if _RAGE_WORDS.search(raw) or _INSULT.search(raw) or shouting or bangs:
        return MOOD_RAGE
    if _TIRED_WORDS.search(raw):
        return MOOD_TIRED
    if _WIN_WORDS.search(raw):
        return MOOD_WIN
    # Thanks stays BELOW rage on purpose: "thanks for NOTHING" is a complaint,
    # and answering it with "any time!" is the single most irritating thing a
    # chat box can do. Moving this line up broke that; a test caught it.
    if _THANKS_WORDS.search(raw):
        return MOOD_THANKS
    if _GREETING_WORDS.match(raw):
        return MOOD_GREETING
    # Short and in capitals: emphasis, not fury. Long capitals already went to
    # rage above.
    if _CAPS_WORD.search(raw) and len(raw.split()) <= 3:
        return MOOD_SHOUT
    if is_ack(raw):
        return MOOD_ACK
    if _CONFUSED.match(raw):
        return MOOD_CONFUSED
    if _EXCLAIM.match(raw):
        return MOOD_EXCLAIM
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


# ── The conversational pools ────────────────────────────────────────────────
# Added after watching a real conversation. Every one of these exists because
# somebody typed something Woogy had no answer for.

_ABOUT_HIM_LINES = [
    "Woogy stands here. That is the whole job. Woogy is very good at it.",
    "Not much! Woogy had a big day of standing.",
    "Woogy waited. Woogy is real good at waiting.",
    "Woogy is a guy in a box. That is the honest answer.",
    "Woogy don't sleep. Woogy don't eat. Woogy just is.",
    "Woogy has been right here. Woogy is always right here.",
    "Woogy understands SOME of it. Woogy nods at the rest.",
    "Honestly? Woogy is doing his best and it is going okay.",
    "Woogy don't have a today. Woogy has a here.",
    "Woogy counted the pixels again. There is the same amount.",
    "Woogy thought about a sandwich for a while. That was the day.",
]

_LAUGH_LINES = [
    "Hee. Woogy made a funny.",
    "Was that a good one? Woogy will do more.",
    "Woogy is laughing too. Woogy thinks.",
    "Oh good. Woogy likes when you do that.",
    "Woogy don't get it, but Woogy is happy.",
    "Heh. Yeah.",
    "Woogy will write that one down in the funny book.",
]

_COMPLIMENT_LINES = [
    "Oh! Um. Thank you. Woogy tried.",
    "V-very kind. Woogy is going to think about that all day.",
    "Woogy is blushing. You cannot see it. It is happening.",
    "Really? Woogy did that?",
    "Woogy will take it. Woogy don't get many.",
    "Aw. Now Woogy has to be good all the time.",
    "Woogy is going to tell the other Woogys. There are no other Woogys.",
]

_ACK_LINES = [
    "Mm.",
    "Yeah.",
    "Right.",
    "Okay good.",
    "Woogy agrees. Woogy usually agrees.",
    "Cool cool.",
    "Good.",
]

# The user asked for this one by name: a bare "you know what" is waiting for
# "What?" before the actual sentence arrives.
_LEADIN_LINES = [
    "What?",
    "What? What is it.",
    "Yeah? Woogy is listening.",
    "Ooh. What.",
    "Woogy is ready. Go.",
]

_REPEAT_LINES = [
    "Oh. Woogy did say that. Woogy has a small brain.",
    "Sorry. Woogy only knows so many things.",
    "Woogy will find a different one. Woogy is looking.",
    "That is embarrassing. Woogy apologises.",
    "Woogy repeats when Woogy is nervous. Woogy is always nervous.",
]

_STOP_LINES = [
    "Okay. Woogy stops.",
    "Stopping. Stopped.",
    "Woogy will be quiet now.",
    "Okay okay okay.",
    "Woogy is a closed mouth.",
]

# Being shouted at does not make him acknowledge you, it makes him hide or
# over-agree. The two kept lines set that register; anything added here should
# be frightened or pathetically eager, never a simple "heard you".
_SHOUT_LINES = [
    "Woogy cowers behind the counter. Only the top of his head is visible.",
    "YES. Whatever it is, YES.",
    "Woogy agrees. Woogy agrees so much. Please stop shouting.",
    "Every eye Woogy has is pointed at you.",
    "Woogy did it. Whatever it was, Woogy did it, and Woogy is sorry.",
    # Angle brackets mark an inner thought, which is also the one place the
    # third-person tic drops. The terminal escapes them, so they render as
    # written rather than being eaten as markup.
    "Woogy is standing very still. <User can't see me if I stand very still>",
]

_SCOLDED_LINES = [
    "Sorry! Woogy did not mean it like that.",
    "Oh no. Woogy has no attitude. Woogy has no anything.",
    "Woogy is sorry. Woogy will do a better voice.",
    "That came out wrong. Woogy is bad at coming out right.",
    "Woogy takes it back. All of it.",
]

_THREAT_LINES = [
    "Woogy is very small and has done nothing.",
    "Please. Woogy has a family. Woogy thinks.",
    "Okay okay! Woogy is putting his hands up. Woogy has hands?",
    "Woogy accepts whatever this is.",
    "Woogy would like the record to show that he was polite.",
]

_EXCLAIM_LINES = [
    "Yeah.",
    "Woogy knows.",
    "Right?",
    "Mm. Big feelings.",
    "Woogy felt that too.",
]

_CONFUSED_LINES = [
    "Woogy don't know either.",
    "Woogy is also asking that.",
    "Hm. Yeah. Hm.",
    "Woogy was hoping you knew.",
]


_PROFESSIONAL = [
    "Noted.",
    "Understood.",
    "Okay.",
    "Got it.",
]

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
            MOOD_ABOUT_HIM: CompendiumState(_ABOUT_HIM_LINES),
            MOOD_LAUGH: CompendiumState(_LAUGH_LINES),
            MOOD_COMPLIMENT: CompendiumState(_COMPLIMENT_LINES),
            MOOD_ACK: CompendiumState(_ACK_LINES),
            MOOD_LEADIN: CompendiumState(_LEADIN_LINES),
            MOOD_REPEAT: CompendiumState(_REPEAT_LINES),
            MOOD_STOP: CompendiumState(_STOP_LINES),
            MOOD_SHOUT: CompendiumState(_SHOUT_LINES),
            MOOD_SCOLDED: CompendiumState(_SCOLDED_LINES),
            MOOD_THREAT: CompendiumState(_THREAT_LINES),
            MOOD_EXCLAIM: CompendiumState(_EXCLAIM_LINES),
            MOOD_CONFUSED: CompendiumState(_CONFUSED_LINES),
            "professional": CompendiumState(_PROFESSIONAL),
        }

    def respond(self, text: str) -> str:
        """One reply to one line of free text."""
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
    if read_mood(raw) != MOOD_NEUTRAL:
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
