# TechDeck v0.8.4.2

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows (911 and 922 QTDR production packages)
to colleagues who can't run Python directly. No installs, no PATH changes — just run
the `.exe`.

---

## What's New in v0.8.4.2

### Bug Fixes

**911 Setup — inspection sheet formatting restored** — Inspection sheets generated
by 911 Setup now preserve every detail of the template: conditional formatting
(the grey-to-white field-fill logic), data validation, merged cells, and theme
references. Previously the underlying sheet-copy mechanism silently dropped all
350 conditional formatting rules, leaving every cell white and breaking the
template's interactive field design. The plugin now drives Excel directly for
the sheet-duplication step, preserving everything natively. Sheet naming
(suffix + duplicate disambiguation) and the part-number write into the A16:C17
merged box are unchanged.

**Report Feedback icon — Light and Salmon themes** — The Report Feedback button
now displays the correct icon under the Light and Salmon themes. Previously
those themes fell back to the account icon because the dark-icon folder was
missing a `feedback.svg`.

**TechDeck icon in title bar and taskbar** — The TechDeck icon now appears in
the application's title bar and Windows taskbar, replacing the generic default
icon. The packaged `.exe` file itself now also shows the TechDeck icon in
Explorer and on pinned shortcuts.

---

## What's New Since v0.8.1

### New Plugin: Run Time Estimator

Automates CNC machine time estimation for a batch — a calculation that previously
required manually digging through dozens of PDF folders.

- Prompts for a batch number at runtime (accepts "Batch 403", "PO #403", "403", "#403")
- Discovers all 7000 machining folders under the batch root automatically
- Matches each PDF against a known LST stem list — unrecognized files are skipped cleanly
- Extracts machine time (in minutes) from each matched PDF via regex
- Outputs `Run Time Estimate - Batch {N}.txt` to the LST folder with part count,
  total raw hours, and total hours with 40% buffer applied

---

### New Plugin: 911 Remove Ticket

A dedicated tool for stripping **Move Ticket** pages out of nest package PDFs before
routing move tickets.

- Scans a configured directory and lists all PDFs by number
- Select individual files or process the entire batch at once
- MIL-SPEC and HULL pages are always preserved
- Output saved alongside the originals as `{original name} Move Ticket Omit.pdf`
  inside a `Move Ticket Omit/` subfolder — originals are never touched

---

### Sound Design

TechDeck now has a full audio layer. Every interaction has a sound cue, tuned to
feel like a polished piece of software rather than a utility.

| Event | Sound |
|---|---|
| Plugin completes successfully | Chime |
| Plugin errors | Error tone |
| Plugin card or library tile selected | Click |
| Sidebar page navigation | Nav tone |
| Console cleared | Clear sweep |
| Blackjack card dealt | Card dealing sound |
| /rave activated | Daft Punk Alive 2007 |
| Moth summoned | One of 11 shuffled voice clips |

All sounds are loaded at startup and played via Qt's multimedia layer. The audio
system is fully thread-safe — worker threads marshal sound requests to the main thread
via Qt signals so playback never races with plugin execution.

---

### New Themes: Cyberpunk and Matrix

Two new dark-background themes join Dark, Light, Salmon, and Blue.

**Cyberpunk** — High-contrast neon green on near-black. Forces a monospace font
throughout the UI, making every panel feel like a terminal. Accent color bleeds
into card borders and button highlights.

**Matrix** — Green-on-black with its own CSS overrides. Tuned independently from
Cyberpunk for a distinct character.

Both themes route icons from the `light/` folder (white SVGs read correctly against
dark backgrounds) and can be activated with `/theme cyberpunk` or `/theme matrix`
from the console.

---

### Theme Builder

Settings → Personalization now includes a full custom theme editor.

- Pick any accent, background, surface, text, and border color via color picker
- Optionally override the font family (good for monospace looks)
- Name and save themes — they persist as JSON files in
  `%LOCALAPPDATA%\TechDeck\themes\` and survive updates
- Custom themes load automatically at startup and appear in the theme switcher
  alongside the six built-in themes

---

### Rogue Mode Audio Player

Type `/roguemode` in the console to open the Rogue Mode floating audio player.

- Upload audio files and organize them into playlists from Settings → Personalization
- Three loop modes: Loop All, Loop One, Play Once
- Stays on top and out of the way while you run plugins
- Playlists are persisted in settings and survive restarts

---

### LST Organizer v2.0.0

The LST Organizer was rebuilt from scratch as a fully self-contained plugin.

- All logic lives in `run.py` — no external script, no subprocess
- Always prompts for the batch number at runtime via the console
- Output filenames include the actual batch number (e.g. `LST_Overview_Batch_403.txt`)
- Skips `REPEAT BATCHES` folder during gather to avoid pulling in repeat copies
- Post-gather case-insensitive duplicate removal
- Tracks standard vs. oversized tubes separately throughout

---

### Run/Cancel Button Toggle

The "Run Selected" button now converts to a **Cancel** button while plugins are
executing. Click it mid-run to stop all active plugins immediately. The button
reverts to "Run Selected" once execution completes or is cancelled.

---

### Plugin Personality System

TechDeck now has opinions about the tools it runs.

After 10 successful runs, a plugin earns a nickname shown in console start messages.
After 3 consecutive errors, it gets temporarily tagged "The Problem Child" until it
cleans up its act.

| Plugin | Nickname |
|---|---|
| 911 Setup | The Beast |
| 922 Pallet Stamper | Old Reliable |
| 911 Repeater | The Surgeon |
| LST Organizer | The Librarian |
| Batch Repeater | The Courier |
| PO Packet Extractor | The Accountant |
| Part Sketch Extractor | The Architect |
| QR Code Generator | The Printer |
| Run Time Estimator | The Timekeeper |

After a successful run, there's roughly a 1-in-5 chance TechDeck prints a dry
one-liner in purple flavor text. Lines cycle through a pool of 30 before repeating
and never print back-to-back.

---

### Processing Spinner

When a plugin is running, a spinner appears between the console output and input bar.
It cycles through whimsical phase messages during execution and prints a short
elapsed-time flavor summary on completion. Long runs can be interrupted mid-message
by a movie quote — then the phase text resumes.

---

### UI Animations

The home page and plugin cards received a full animation pass:

- **Staggered card entrance** — cards fade in sequentially when the page loads
- **Hover lift** — cards cast a stronger shadow on hover with a smooth 150 ms ease
- **Running pulse** — a card's shadow breathes in and out while its plugin is active
- **Success flash** — cards flash green then fade back to normal on completion
- **Run button glow** — the Run Selected button pulses with a soft accent glow when
  plugins are selected
- **Startup fade-in** — the application window fades in on launch

---

### Plugin Card Status Indicators

Plugin cards now reflect execution state visually:

| State | Appearance |
|---|---|
| Running | Accent-colored border + pulsing shadow |
| Success | Green flash, returns to idle |
| Error | Red border (persists until next run) |
| Cancelled | Yellow/orange border |
| Timeout | Red border |

---

### Serial Plugin Execution

When multiple plugins are selected, they now run **one at a time in sequence** rather
than all simultaneously. This prevents resource conflicts and makes console output
readable. Each plugin starts as soon as the previous one finishes.

---

### Easter Eggs

Type any of these into the console:

| Command | What It Does |
|---|---|
| `/fidget` | Opens a chrome fidget spinner window. Click to add spin. Double-click to close. Drag to move. |
| `/rave` | Pulses accent colors through a saturated rainbow for 10 seconds, spawns 5 ASCII dancing crabs, and plays Daft Punk Alive 2007. |
| `/jack` | Starts a blackjack game in the console. Dealer: Sal. Fixed $25 bet. Bankroll persists across sessions. |
| `/haiku` | Generates a manufacturing-themed haiku. |
| `/moth` | A moth appears from a random screen edge and flies toward the Run button. Type again to redirect it to a different UI element. Double-click to dismiss. |
| `/steelbeams` | Opens the Steel Tube Operation game. |
| `/roguemode` | Opens the Rogue Mode focus music player. |

---

### Theme: Salmon (Tuned)

The salmon theme was re-tuned:

- Background is now the deeper salmon so the page has visual weight
- Plugin cards sit lighter on top, making the card grid easier to read
- Checkboxes are now clearly visible against the tile surface

---

### Bug Fixes & Performance (v0.8.x)

- **Spinner lag fixed** — plugin log messages are buffered in a Python queue and
  drained in batches every 50 ms, keeping the Qt event queue lean so the spinner
  stays smooth even when a plugin is printing hundreds of lines
- **Run/Cancel race condition fixed** — button state transitions are now safe
  under rapid click sequences
- **Salmon/light theme checkboxes** — checkbox indicators were previously invisible
  against the near-white tile background; resolved
- **batch_repeater folder matching** — now matches batch folders by number rather
  than exact name, handling naming variations that previously caused the plugin to
  find nothing
- **Plugin card thread safety** — status updates from background threads are now
  delivered to the main thread via a signal rather than touching Qt widgets directly
- **Update checker stale cache** — update checker no longer serves stale version
  data after the first check
- **Removed ForgeAI** — removed unused API key infrastructure and dead constants
  left over from the ForgeAI integration

---

## Installed Plugins

| Plugin | Description |
|---|---|
| 911 Setup | Full 911 QTDR batch setup — nest folders, templates, forecast data, PDFs |
| 911 Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches |
| 911 Remove Ticket | Removes Move Ticket pages from nest package PDFs; keeps MIL-SPEC and HULL pages |
| 922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info |
| Batch Repeater | Copies repeat orders from prior 922 batches |
| LST Organizer | Organizes .lst files by material type; outputs per-batch overview |
| PO Packet Extractor | Extracts PO data from PDFs into Excel |
| Part Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation |
| QR Code Generator | GUI plugin — dual-tab QR library and generator |
| Run Time Estimator | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer |

---

## Installation

Download `TechDeck-0.8.4.2-Setup.exe` from the [Releases](https://github.com/OzymandiasOne/TechDeck/releases) page and run it.
No Python, no admin rights, no PATH changes required.

TechDeck will notify you automatically when a new version is available.
