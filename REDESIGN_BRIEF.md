# TechDeck Redesign Brief

You are the lead designer and engineer on TechDeck, a Windows desktop automation
tool that ships plugins to CNC processing specialists at American Steel & Aluminum,
primarily for Electric Boat manufacturing workflows. It is a PySide6 application
packaged with PyInstaller + Inno Setup, currently at v0.8.4.2, deployed to
locked-down corporate machines via GitHub Releases with an auto-updater. It is in
daily production use. Decisions you make will reach those users in the next release.

Read `CLAUDE.md` for the current state of the codebase — plugin contract, file
structure, hard rules, build process. The REDESIGN IN PROGRESS section at the top
of that document lists which of its statements are superseded by this brief.

## Who actually uses this

Picture the user. They are at a desk on the shop floor. Safety glasses pushed up on
their head. SolidWorks is open on one monitor, an Excel batch list on the other,
and there is a paper packet of mechanical drawings on the desk weighted down with
a coffee cup. They read engineering drawings fluently. They do not read software
documentation. They were trained on a job, not in a classroom. They are good at
their craft and skeptical of anyone telling them a computer will do part of it for
them. When a tool fails silently or behaves inconsistently, they go back to doing
it by hand and they do not come back. The previous person who tried to automate
their workflow lost their trust permanently.

They cannot install Python. They cannot modify PATH. They cannot run as
administrator. IT will not approve WSL without weeks of paperwork. TechDeck exists
because none of those constraints are negotiable.

## The actual problem

TechDeck currently works. Plugins run, files get produced. But the primary UI
surface is a console — a scrolling terminal log with a CLI input bar — and
watching log lines is how the user is supposed to know what the tool is doing.
This is the load-bearing failure. It requires the user to think like a programmer
to use a tool that should require them to think like a tradesperson. It makes
every plugin's output shape different, so the emotional experience of waiting for
a result depends entirely on how the plugin author decided to print. Long-running
plugins that print nothing feel broken. Verbose plugins feel chaotic. Same
emotional moment, wildly different experiences.

The redesign target is the surface, not the foundation. The plugin contract, the
executor, the audio system, settings, theming infrastructure — all of that is
load-bearing and stays. What you are rebuilding is what the user sees, hears,
touches, and trusts.

## Design principles

State these to yourself before each decision.

**The surface contract is consistent.** Every plugin run feels the same shape
regardless of which plugin: it asks for what it needs, it does the work visibly,
it confirms it is done, it tells the user what happened. The user learns the
shape once and it never changes. A plugin that surprises the user with a
different interaction model is a bug in the surface, not a feature of the plugin.

**The user is never aware of the machine.** Complexity is hidden, not removed.
Logs still exist; they are not the front door. Threads still exist; the user
does not see them. The plugin folder structure still exists; the user does not
learn it.

**The machine talks to the user, not at them.** TechDeck has a voice. The voice
is warm, sometimes funny, occasionally weird. It is not performative cleverness —
it is the tone of a tool that respects who is using it. Read the soul inventory
below; that voice is already there and must survive.

**Motion and sound are information, not decoration.** A spinner that doesn't mean
"I am working on this specific thing" is noise. A chime that doesn't mean "this
is done and you can trust it" is noise. Every animation and every sound earns its
place by carrying meaning.

**Hidden depth, not visible complexity.** Power users can dig. New users never
feel like they are missing something. The disclosure controls exist; they do not
advertise.

**The 50th run matters as much as the first.** First-run polish is the easy half.
The harder half is what daily use feels like — when the novelty is gone, when
the user has run the same plugin 200 times, when they could do it in their
sleep. The soul-level features (talkback, movie quotes, tech tips, nicknames)
are tuned for repetition, not first impression. Preserve that.

## What currently exists

### The soul (must survive)

These are named, real, and load-bearing for the product's identity. **None of
these items are candidates for removal.** Their delivery surface is open; their
existence is not. If you find yourself proposing to cut one in the name of
cohesion, you've misread the brief — propose a new home for it instead.

- **Spinner texts** — whimsical phase lines during plugin execution
  ("Negotiating with Excel...", "Herding the data...", "Honking...")
- **Done texts** — funny completion summaries ("Caramelized for 2m 14s")
- **Movie quote interrupts** — a movie quote occasionally replaces the spinner
  text for ~5 seconds mid-run, then resumes
- **Talkback** — post-completion remarks from TechDeck, ~1 in 5 runs, currently
  prints to the console in purple. Same cadence and tone must survive; the
  surface is open. Lines live in `TALKBACK_LINES` in `flavor.py`.
- **Tech tips** — occasional system tips after runs, ~1 in 12.
- **Plugin nicknames** — earned after 10+ successful runs, tracked in
  `settings.json` under `plugin_stats`. "The Beast" (911 Setup), "Old Reliable"
  (922 Pallet Stamper), "The Surgeon" (911 Repeater), and others in
  `PLUGIN_NICKNAMES` in `flavor.py`. After 3+ consecutive errors a plugin
  becomes "The Problem Child" temporarily. This is a pure repeat-use feature —
  invisible on first run, meaningful on the 11th. Now that the plugin card is
  becoming the primary surface, the nickname probably belongs on the card itself
  in some form. Decide.
- **Sound design** — success chime, error tone, nav click, card-dealt sound,
  `/rave` music, moth voice clips. `AudioManager` is the singleton; the sounds
  themselves are tuned and not up for redesign.
- **Easter eggs** — `/rave` (Daft Punk moment), `/moth` (widget with 11
  shuffled voice clips, flies toward UI elements), a steel beams game,
  blackjack (`/jack`, dealer is Sal, $25 bet, bankroll persists), `/fidget`
  (a chrome fidget spinner), `/compliment`, `/roast`, `/haiku`, `/roguemode`
  (audio player). These are not noise — they are the product's personality.
  Whether some stay as commands and others become physically discoverable is
  open. The principle: discovery should feel like finding something, not
  reading a help list.
- **Themes** — six built-in palettes (`dark`, `light`, `salmon`, `blue`,
  `cyberpunk`, `matrix`) plus a custom theme builder. Palette dataclass drives
  all colors. The visual identity per theme is part of the product.

### The infrastructure (must not change)

- `PluginExecutor` — threading, cancellation, timeout, progress callbacks,
  serial execution
- Plugin contract: `run(params, progress_callback, cancel_event)` — sacred
- Dynamic plugin discovery from `%LOCALAPPDATA%\TechDeck\plugins\{plugin_id}\`
  (each containing `run.py` and `plugin.json`)
- `plugin.json` schema, including `requires_main_thread`
- `AudioManager` singleton — thread-safe, signals-based
- `SettingsManager` — JSON-backed profile system, atomic writes
- Theme palette dataclass (all colors flow from this)
- `console.request_input()` — uses `QMetaObject.invokeMethod` for thread-safe
  input from worker threads. The *mechanism* stays. Its *frontend* (the CLI
  input bar) does not have to.
- Plugin nickname / talkback / tech tip / flavor state machinery in
  `flavor.py` — the data and state logic stays; where it surfaces is open.

### The UI as it stands

```
MainWindow (shell.py)
├── Sidebar (sidebar.py): Home, Library, Settings, My Account, Report Feedback
└── QStackedWidget
    ├── HomePage (home_page.py)
    │   ├── Profile selector + Run Selected
    │   ├── Plugin card grid (PluginCard, 220×140 fixed)
    │   │   - Checkbox for multi-select
    │   │   - Name + description tooltip
    │   │   - Pulse/flash/border animations for state
    │   └── ConsoleWidget (console.py) — output log + spinner row + input bar
    ├── LibraryPage
    ├── SettingsPage
    └── AccountPage
```

Multi-plugin selection is real — users check several cards and run them.
Concurrency rules during multi-select are part of what you are designing.

## What needs to change

The console is the symptom. The deeper change is replacing it with surfaces that
give the user a consistent shape: ask, work, confirm. Some directions are
settled, some are open. The open ones are open on purpose.

**Settled:** the CLI input bar is gone as the primary way plugins ask for input.
The raw log is no longer the default view. The plugin card becomes the primary
communication surface for plugin state.

**Open for you to decide:** whether the raw log is hidden behind disclosure or
removed entirely (the disclosure path is more conservative; removal abandons the
debugging value — make the call and defend it). Whether runtime plugin input is
a modal, an inline-on-card prompt, a slide-over panel, or something else (engage
with cancellation, with multi-plugin queueing, with what happens if a user
selects four plugins and three of them want input). Where the talkback line
lives (toast, strip, inside the card, somewhere new — preserving the ~1 in 5
cadence and the dry one-liner tone). Whether easter eggs become physically
discoverable interactions or whether some commands (`/rave`) are funnier
*because* they are commands and should stay that way.

**Also on the table:** Live theme switching without app restart — work out
whether PySide6 lets you do this cleanly and propose a path. (Current
`__main__.py` applies stylesheet globally via `app.setStyleSheet(...)`. Live
switching probably means listening to a theme-change signal and re-applying;
investigate.) The Report Feedback button pinned to the bottom of the sidebar is
misplaced; move it to Settings or argue why it should stay. Home and Library
both deal with plugins — consider whether they should be one page, and if so,
what each does.

## Edge cases you have to design for, not bolt on

**Failure.** A plugin crashes. A plugin times out. A plugin asks for input the
user can't provide. What does the card look like? What does the user do next?
Can they retry? Where does the actual error message live for the user who wants
to look at it without making it shout at the user who doesn't? Failure handling
is half the trust problem and it cannot be a final-pass detail. Note that the
flavor system already has a concept here — after 3+ consecutive errors a plugin
becomes "The Problem Child". That state is real and should be visible in the
new surface in some form.

**Multi-select concurrency.** Three cards are checked. The user clicks Run. One
needs input. Two are long-running. What's the model? Serial with a queue
indicator? Parallel with independent cards? The executor is serial today; that
may or may not be the right answer for the surface.

**The 200th run.** A user who has run Pallet Stamper every day for six months.
What do they see? What do they hear? What's still delightful and what has
become noise? The talkback and tech tip frequencies were tuned for this — keep
tuning them. The nickname system pays off here. The easter eggs reward this
kind of user — design for discovery on the timeline of months, not minutes.

**Migration.** This ships to people whose workflows already exist. A redesign
that requires them to relearn the tool will get rejected. Plan the transition:
what feels familiar enough on day one of the new version that they don't
bounce.

## How to proceed

Before writing any code, produce a design proposal. The format:

For each surface you are changing, write four short paragraphs.
1. What the user currently experiences. Concrete, not abstract.
2. What they will experience after. Concrete, not abstract.
3. Why that change earns its complexity cost. If it doesn't, drop it.
4. What you are unsure about and what would resolve the uncertainty.

Then a separate section: **things in the current design that should change which
I haven't mentioned.** Then a separate section: **things I asked for that you
think are wrong, incomplete, or premature.** This section is required. If it is
empty, you didn't think hard enough.

Keep the proposal under 2500 words. If you can't fit it, you don't have it yet.

After the proposal, wait. Do not start implementing until we have agreed on the
shape. Do not modify any code in this session.

## Disagreement is structural

The proposal format above requires a section where you tell me I'm wrong. This
is not a courtesy. Several of the directives in this brief are guesses dressed
as decisions. The easter egg discoverability question, the modal-vs-inline
input question, the console removal vs. hiding question, the live theme
switching feasibility, the Library/Home merge — these are open and at least
one of them I'm probably wrong about. Find which.

## Success criteria

Two, not one.

**First run:** a CNC specialist who has never seen TechDeck launches it, runs
a plugin, gets a file, and thinks *this knows what it's doing.* They do not
think about the software. They think about the work it did.

**Two hundredth run:** the same person, six months later, running the same
plugin for the fifteenth time this week, still occasionally gets surprised by
something small — a movie quote, a tech tip, a sound they hadn't quite noticed
before, the plugin earning its nickname on screen — and the tool has not once
made them feel like a fool for not understanding what it was doing. The
relationship has compounded instead of decayed.

If both of those are true, the redesign worked. If only the first is, you built
a demo.
