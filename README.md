# TechDeck v0.8.3.2

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows (911 and 922 QTDR production packages)
to colleagues who can't run Python directly. No installs, no PATH changes — just run
the `.exe`.

---

## What's New Since v0.8.1

### New Plugin: 911 Remove Ticket

A dedicated tool for stripping **PART SKETCH** pages out of nest package PDFs before
routing move tickets.

- Scans a configured directory and lists all PDFs by number
- Select individual files or process the entire batch at once
- Output saved alongside the originals as `{original name} Move Ticket Omit.pdf`
  inside a `Move Ticket Omit/` subfolder — originals are never touched

---

### Plugin Personality System

TechDeck now has opinions about the tools it runs.

- **Nicknames** — after a plugin has been run 10+ times it earns a nickname that
  appears in the console start message (e.g. "911 Setup, a.k.a. The Beast, is warming up...")
- **TechDeck Talks Back** — after a successful run there's roughly a 1-in-5 chance
  of a dry one-liner appearing in the console. Lines cycle through a pool of 30 before
  repeating and will never print back-to-back.
- **Problem Child** — a plugin that fails 3+ times in a row gets a temporary label
  noting its track record.

---

### Processing Spinner

When a plugin is running, a **Claude Code-style spinner** now appears between the
console output area and the input bar.

- One glowing color, smooth braille animation running at a fixed 100 ms tick —
  completely independent of how fast the plugin logs output
- Flavor text changes every ~4 seconds with whimsical readouts like
  *"Discombobulating..."*, *"Kerfuffling the data..."*, *"Grinched through..."*
- Intermittent movie quote interruptions appear roughly every 20–28 seconds and
  hold for ~5 seconds before returning to flavor text
- **Phase-aware**: the spinner stays locked on its initial text while a plugin is
  waiting for your input. The moment you hit Enter, it immediately jumps to a new
  flavor text to signal that work has actually started
- When all plugins finish, the spinner shows a summary for 4 seconds
  (*"Cogitated for 2m 14s."*) before disappearing — no redundant line in the console

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

Added easter eggs. Recommend looking out for new terminal commands in the console.

---

### Theme: Salmon

The salmon theme has been re-tuned:

- Background is now the deeper salmon so the page has visual weight
- Plugin cards sit lighter on top, making the card grid easier to read
- Checkboxes are now clearly visible against the tile surface

---

### Bug Fixes & Performance

- **Spinner lag fixed** — plugin log messages are now buffered in a Python queue
  and drained in batches every 50 ms. This keeps the Qt event queue lean so the
  spinner animation stays smooth even when a plugin is printing hundreds of lines
- **Salmon/light theme checkboxes** — checkbox indicators were previously invisible
  against the near-white tile background; resolved
- **batch_repeater folder matching** — now matches batch folders by number rather
  than exact name, handling naming variations that previously caused the plugin to
  find nothing
- **Plugin card thread safety** — status updates from background threads are now
  delivered to the main thread via a signal rather than touching Qt widgets directly
- **Removed ForgeAI** — removed unused API key infrastructure and dead constants
  left over from the ForgeAI integration

---

## Installed Plugins

| Plugin | Description |
|---|---|
| 911 Setup | Full 911 QTDR batch setup — nest folders, templates, forecast data, PDFs |
| 911 Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches |
| 911 Remove Ticket | Removes PART SKETCH pages from nest package PDFs |
| 922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info |
| Batch Repeater | Copies repeat orders from prior 922 batches |
| LST Organizer | Organizes .lst files by material type |
| PO Packet Extractor | Extracts PO data from PDFs into Excel |
| Part Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation |
| QR Code Generator | GUI plugin — dual-tab QR library and generator |

---

## Installation

Download `TechDeck-0.8.3.2-Setup.exe` from the [Releases](https://github.com/OzymandiasOne/TechDeck/releases) page and run it.
No Python, no admin rights, no PATH changes required.

TechDeck will notify you automatically when a new version is available.
