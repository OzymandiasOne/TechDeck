"""
TechDeck Flavor Module
All personality data: talkback lines, compliments, roasts, haiku.
"""

import random

# ---------------------------------------------------------------------------
# Plugin start messages
# ---------------------------------------------------------------------------

_PLAIN_VERBS = [
    "Starting", "Launching", "Running", "Fidget Spinning", "Executing",
    "Initializing", "Discombobulating", "Cogitating", "Percolating",
    "Alchemizing", "Transmuting", "Distilling", "Assembling",
]


def get_start_message(plugin_name: str) -> str:
    """Return a flavor start line for the executor."""
    return f"{random.choice(_PLAIN_VERBS)} {plugin_name}..."


# ---------------------------------------------------------------------------
# Talkback lines (post-completion flavor, ~1 in 5 runs)
# ---------------------------------------------------------------------------

TALKBACK_LINES = [
    "Steel is just angry rocks.",
    "[TechDeck has no thoughts at this time.]",
    "Somewhere out there, someone is doing this in Excel. By hand.",
    "A nest with no parts is thinking about what it wants to be when it grows up.",
    "A nest with no parts is, technically, perfect. Nothing in it has gone wrong.",
    "Running. Still Running. Always running.",
    "Still here.",
    "The files were there the whole time.",
    "It went fine.",
    "No one will ever know how close that was.",
    "This is the 4th most interesting thing happening in this building right now.",
    "Technically, all manufacturing is just controlled chaos with good paperwork.",
    "The PDF did not resist.",
    "Some plugins run fast. Some plugins have things to think about first.",
    "Electric Boat has existed since 1899. You have existed for less time than that.",
    "Processing. Judging. Processing.",
    "The spreadsheet contains multitudes.",
    "There are 47 ways this could have gone wrong. You got the good one.",
    "Files moved. Destiny unchanged.",
    "Done. The folder looks the same but it isn't.",
    "A lot of things happened just now. Most of them were fine.",
    "The computer is thinking. Let it.",
    "Somewhere in this company, someone just asked if we can do this in SharePoint instead.",
    "Not every batch needs a hero. But every hero needs a batch.",
    "It is remarkable how much a PDF can be wrong.",
    "TechDeck was not designed for this. It did it anyway.",
    "The nest numbers check out. This time.",
    "Steel does not care what you name the folder. But you should name it correctly anyway.",
    "That file has been waiting in that directory for six months. It is ready.",
    "Nothing failed. Make of that what you will.",
    "I take a chip....and *eat* it.",
    "Here I am, brain the size of a planet, and they ask me to process spreadsheets."
]


class TalkbackState:
    """Shuffled pool of talkback lines — exhausts before cycling, never repeats back-to-back."""

    def __init__(self):
        self._pool: list[int] = []
        self._last: int = -1
        self._refill()

    def _refill(self):
        indices = list(range(len(TALKBACK_LINES)))
        random.shuffle(indices)
        if indices and indices[0] == self._last:
            indices.append(indices.pop(0))
        self._pool = indices

    def get_line(self) -> str:
        if not self._pool:
            self._refill()
        idx = self._pool.pop(0)
        self._last = idx
        return TALKBACK_LINES[idx]


# ---------------------------------------------------------------------------
# Tech Tips (occasionally printed in console after successful plugin runs)
# ---------------------------------------------------------------------------

TECH_TIPS = [
    "Tech Tip: Configure app folder paths in Settings > App Settings.",
    "Tech Tip: Build a custom color theme in Settings > Personalization.",
    "Tech Tip: Type /roguemode to launch the focus music player.",
    "Tech Tip: Try /theme cyberpunk or /theme matrix for a different vibe.",
    "Tech Tip: Type /help to see all available console commands.",
    "Tech Tip: Double-click a track in the Rogue Mode playlist to jump to it.",
]


class TechTipState:
    """Shuffled pool of tech tips — exhausts before cycling."""

    def __init__(self):
        self._pool: list[int] = []
        self._refill()

    def _refill(self):
        indices = list(range(len(TECH_TIPS)))
        random.shuffle(indices)
        self._pool = indices

    def get_line(self) -> str:
        if not self._pool:
            self._refill()
        return TECH_TIPS[self._pool.pop(0)]


# ---------------------------------------------------------------------------
# /compliment  — 50 dry, specific compliments
# ---------------------------------------------------------------------------

COMPLIMENTS = [
    "You have excellent taste in folder naming conventions.",
    "Most people would have just emailed someone. You automated it.",
    "The batch number you entered was correct on the first try. Statistically rare.",
    "You are running TechDeck in a corporate IT environment that technically shouldn't allow this. Respect.",
    "Your spreadsheet discipline is above average.",
    "You know what a nest number is. That puts you ahead of most people.",
    "The way you picked that plugin suggests a degree of operational literacy that is not universal.",
    "You haven't crashed TechDeck today. That says something.",
    "Whoever configured these settings did a solid job. That was probably you.",
    "You're not doing this in SharePoint. Wise.",
    "You checked the console output. Not everyone does.",
    "There's a version of this job where no one automates anything. You are not living that version.",
    "The fact that you installed TechDeck means someone decided to make things better. That person was probably you.",
    "You didn't double-click the plugin twice. Composure.",
    "Your tolerance for ambiguous file paths is commendable.",
    "The spreadsheet you're working with is genuinely complicated. You opened it anyway.",
    "Not everyone in your position would have found this tool. You did.",
    "You have run this plugin enough times to know what a successful output looks like. That is expertise.",
    "Whoever set up these batch folders has a system. You can tell.",
    "You are using a computer well. This is more impressive than it sounds.",
    "The absence of errors in your session so far is not an accident.",
    "You kept the folder names clean. This will matter in six months.",
    "That run completed faster than it had any right to.",
    "You didn't ask IT. You solved it yourself. Classic.",
    "Your threshold for 'good enough' is high. It shows.",
    "The files are exactly where they should be. That didn't happen by itself.",
    "Someone will be grateful for the work you did today. They won't know it was you. You'll know.",
    "You have an excellent instinct for which plugins to run in which order.",
    "Most tools like this get abandoned after a month. You're still here.",
    "Your batch numbers are consistently correct. This is not a given.",
    "You read the output. A lot of people don't.",
    "You caught that error before it became a problem. Good eye.",
    "You exported that to Excel when you could have just printed it. Correct decision.",
    "Your file organization strategy is, objectively, not bad.",
    "You're working in a folder path that would make most people cry. You're fine.",
    "You've automated something that took 45 minutes by hand. Do the math.",
    "You opened the PDF to check it. That's discipline.",
    "The patience required to do this work is not widely distributed. You have it.",
    "You're one of the rare people who treats a file path like it matters. It does.",
    "That plugin ran quietly and correctly because someone did the work to make it that way. Part of that person is you.",
    "You navigated the OneDrive sync delay with grace.",
    "You didn't name the folder 'new folder'. Character.",
    "You're good at this in a way that's hard to explain to someone who's never done it.",
    "You are faster at this than you were three months ago.",
    "You ran the plugin, checked the output, and moved on. Efficient.",
    "Your attention to detail is the reason things are going correctly right now.",
    "You know which file to open without having to look it up. Expertise looks like this.",
    "You could explain what QTDR means without hesitating. That's a compliment.",
    "TechDeck works better when someone who knows what they're doing uses it. That appears to be you.",
    "You kept the console open. That's the move.",
]


# ---------------------------------------------------------------------------
# /roast  — 50 deadpan, observational roasts
# ---------------------------------------------------------------------------

ROASTS = [
    "You ran the same plugin four times today. Growth.",
    "The folder exists. Whether it should is a different question.",
    "That batch number took three attempts. We don't need to talk about it.",
    "You know you can use /clear, right.",
    "The console has hundreds of lines. Some of those are errors. You're aware.",
    "That spreadsheet has been open for 40 minutes and the plugin ran for 12 seconds.",
    "You've been looking at that file path for longer than necessary.",
    "The PDF was already there. It was just in the other folder.",
    "Technically that worked. The technical part is doing a lot of work in that sentence.",
    "You could have pressed Cancel three minutes ago.",
    "That run finished. Not cleanly, but it finished.",
    "The folder name is fine. It's just longer than it needs to be.",
    "You typed the batch number without the leading zero again.",
    "At some point today, a plugin waited for your input for four minutes.",
    "The column header was right there.",
    "You ran the setup plugin twice. The second time was the same as the first time.",
    "That file has not been modified. Running the plugin did not modify it. This is worth considering.",
    "You named it 'final2'.",
    "There's a faster way to do this. You'll discover it eventually.",
    "The error message was, in retrospect, pretty clear.",
    "That PDF opened fine. The second time.",
    "You navigated to that folder by clicking through six levels of Explorer instead of pasting the path.",
    "One of those five files was the right one. You got there.",
    "The plugin finished while you were doing something else. Efficient, in a loose sense.",
    "The spreadsheet was sorted differently than you expected. These things happen.",
    "It is unclear why the same job appears in the batch three times. That's for future you.",
    "The run completed with warnings. You chose not to read them. Bold.",
    "The template was in the same place it always is.",
    "You've restarted TechDeck twice today. Something to think about.",
    "That was a lot of files for a plugin to process. You watched the whole thing.",
    "You accidentally ran the wrong plugin. It ran successfully. On the wrong files.",
    "The folder was named correctly. The files inside were not.",
    "That took 45 seconds when it usually takes 4. We don't know why either.",
    "You checked three times that it was the right batch number. It was. You were right the first time.",
    "The file was there. It always was. Computers are like that.",
    "You exported the report, then re-exported it with the same settings. Some decisions are made twice.",
    "The PDF is 400 pages. You needed page 12.",
    "There are 14 plugins. You use 3 of them. The other 11 wait patiently.",
    "You ran the full setup for a batch that turned out to be a repeat. Thorough.",
    "The cancellation came 1 second before completion. That's timing.",
    "You searched for the file, found it, opened it, closed it, searched for it again.",
    "That's the third time this week you've asked TechDeck something it can't answer.",
    "You have /help mapped to memory but still typed /halp.",
    "That plugin ran faster than expected. You looked suspicious anyway.",
    "The console still shows the previous run's output. You're looking at old data.",
    "You copy-pasted the path from a Teams message instead of navigating. Technically fine.",
    "The batch number and the PO number are not the same number. They were today.",
    "You have excellent folder discipline, except for the folder named 'TEMP STUFF' from March.",
    "That error has a solution. It's in the console. You'll get to it.",
    "TechDeck is glad you're here. TechDeck is also keeping a log.",
]


# ---------------------------------------------------------------------------
# /haiku  — template system (5-7-5), manufacturing theme
# ---------------------------------------------------------------------------

_HAIKU_FIRST = [   # 5 syllables
    "Nest numbers align",
    "The folder is new",
    "Steel on the table",
    "One PDF waits",
    "The batch is complete",
    "Column B is blank",
    "Files moved to their home",
    "No errors today",
    "The template was found",
    "Repeat parts return",
    "The QR code waits",
    "Pallet stamped and sealed",
]

_HAIKU_MIDDLE = [  # 7 syllables
    "The spreadsheet holds the answers",
    "Batch numbers do not explain",
    "A folder waits to be filled",
    "Nothing failed this time around",
    "Steel does not care what you form",
    "The nest has been processed now",
    "Somewhere a spreadsheet grows large",
    "Steel tubes and the standard ones",
    "Electric Boat counts the days",
    "Output written to the drive",
    "Headers found by name not place",
    "The PDF opened cleanly",
]

_HAIKU_LAST = [    # 5 syllables
    "Steel into the dark",
    "Numbers do not lie",
    "The folder holds still",
    "Work continues on",
    "Quietly correct",
    "The file remains there",
    "Nothing was broken",
    "The nest is at rest",
    "The job gets done now",
    "One more batch complete",
    "Folders multiply",
    "The path was correct",
]


class _ShuffledDeck:
    """Draw items in a shuffled order, exhausting all before any repeat, and never
    the same item twice in a row (even across a reshuffle). Feels random but never
    stale."""

    def __init__(self, items):
        self._items = list(items)
        self._pool: list[int] = []
        self._last = -1

    def draw(self):
        if not self._pool:
            self._pool = list(range(len(self._items)))
            random.shuffle(self._pool)
            if len(self._pool) > 1 and self._pool[0] == self._last:
                self._pool.append(self._pool.pop(0))   # don't reopen on a repeat
        idx = self._pool.pop(0)
        self._last = idx
        return self._items[idx]


_recent_haikus: list[str] = []


def generate_haiku() -> str:
    """A haiku from the template pools (each line ends '...'), never repeating a
    recently-shown haiku."""
    for _ in range(20):
        haiku = (
            random.choice(_HAIKU_FIRST) + "...\n"
            + random.choice(_HAIKU_MIDDLE) + "...\n"
            + random.choice(_HAIKU_LAST) + "..."
        )
        if haiku not in _recent_haikus:
            break
    _recent_haikus.append(haiku)
    if len(_recent_haikus) > 12:
        _recent_haikus.pop(0)
    return haiku


# ---------------------------------------------------------------------------
# Moth musings - first-person reflections of someone meeting Miyamoto Musashi's
# ideas for the first time and questioning themselves (Dokkodo / Book of Five
# Rings), shown by /friend in the gaps between haiku. Pre-wrapped (\n only) to
# keep the bubble tidy; no em-dashes by design.
# ---------------------------------------------------------------------------

_MUSINGS = [
    "If I could meet the person I was yesterday,\nwhat would it mean to have surpassed him?\nAnd is that the only contest worth entering,\nthe one where my opponent is already gone?",
    "What if I did only what was useful?\nCould I bear the austerity of that, or do\nI secretly need my wasted motions to feel free?",
    "Why do I keep watching for the prize\nat the end of the road, when everything\nI wanted was supposed to happen\nin the walking? Was the training\nthe means, or the thing itself all along?",
    "Can one thing, truly seen, contain\nten thousand? Or do I flatter myself\nthat a single fact opens onto the whole,\nwhen perhaps the world is simply large\nand I am only hungry for patterns?",
    "What is it the eye cannot see,\nand how would I know I had perceived it?\nIs there a sight beneath sight,\nor only the eye learning to slow down?",
    "If I accepted each thing exactly as it is,\nwould that be wisdom, or surrender?\nWhere is the line between\nacceptance and quietly giving up\nevery wish to make things better?",
    "Why does the thousand-mile road frighten\nme as a whole, when no single step\nin it has ever been beyond me? Is distance\nonly ever the imagination's despair?",
    "What would I have to become\nto regret nothing I had done?\nIs that peace, or the dimming\nof the conscience that regret\nwas meant to keep awake?",
    "Can I think lightly of myself and deeply\nof the world without the first souring\ninto self-contempt? Which weighs more,\nand why have I had the scale upside down?",
    "I have feared endings my whole life.\nBut what if the only thing worth fearing\nwas the wrong turn taken long before the end,\nand the ending itself were neutral, even kind?",
    "If I held no preference in anything,\nwould I be free, or simply absent?\nIs there a way to want nothing\nthat is not also a way to be no one?",
    "What is the blade I keep carrying\nthat I no longer need? And why\nis the weight I refuse to set down\nalways the one I mistake for myself?",
    "Why do I trust the large and famous thing\nmore than the small one in front of me,\nas if size were the same as truth?",
    "What I practice alone, in the quiet,\nis that who I actually am? And when\nthe storm comes, will it reveal me,\nor only what I rehearsed?",
    "Can I depend on no one's hand\nand still honour every god?\nOr is the refusal to lean\nits own kind of arrogance,\ndressed up as strength?",
    "If it came to it, the body or the honour,\nam I sure I know which one I am?\nHave I ever truly been tested, or only\nimagined the answer I would give?",
]


_musing_deck = _ShuffledDeck(_MUSINGS)


def generate_musing() -> str:
    """A musing for the moth (1-2 lines, ending '...'). Drawn from a shuffled deck:
    never repeats until every musing has been shown, and never twice in a row."""
    return _musing_deck.draw().rstrip(" .") + "..."


# ---------------------------------------------------------------------------
# Sal — the blackjack dealer's one-liners (shown on the idle dashboard)
# ---------------------------------------------------------------------------

SAL_LINES = [
    "The house always wins, kid.",
    "Back for more?",
    "Your chips are safe with me. Mostly.",
    "Numbers don't lie. People do.",
    "Don't spend it all on one batch.",
    "Run a tool, then we'll talk.",
    "I've seen worse bankrolls.",
    "Keep your cards close.",
    "Easy come, easy go.",
    "You're up. Don't get cocky.",
]


def get_sal_line() -> str:
    """A random Sal one-liner."""
    return random.choice(SAL_LINES)


# ---------------------------------------------------------------------------
# Generic shuffled pool (used for /compliment and /roast)
# ---------------------------------------------------------------------------

class CompendiumState:
    """Shuffled pool of lines — exhausts before cycling, never repeats back-to-back."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._pool: list[int] = []
        self._last: int = -1
        self._refill()

    def _refill(self):
        indices = list(range(len(self._lines)))
        random.shuffle(indices)
        if indices and indices[0] == self._last:
            indices.append(indices.pop(0))
        self._pool = indices

    def get_line(self) -> str:
        if not self._pool:
            self._refill()
        idx = self._pool.pop(0)
        self._last = idx
        return self._lines[idx]
