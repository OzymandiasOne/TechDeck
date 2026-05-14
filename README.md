# TechDeck v0.8.4.1

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows (911 and 922 QTDR production packages)
to colleagues who can't run Python directly. No installs, no PATH changes — just run
the `.exe`.

---

## What's New in v0.8.4.1

### Bug Fixes

**Kit save** — Adding a new app to a kit no longer wipes the apps that were already
in it. Previously, opening the Library page, checking a new app, and clicking Save
would replace the entire kit with just that one app. Fixed.

**Input prompt ordering** — When a plugin asks for user input (e.g. batch number,
directory), the prompt is now always the last line visible before the input bar
becomes active. Previously, buffered log messages could appear after the prompt,
making it unclear what you were responding to.

**Missing app — Remove from Kit** — Plugin cards marked `(Missing)` on the Home
page now have a **Remove from Kit** button. Previously, clearing a missing app
required switching to the Library page and saving. You can now do it directly.

**911 Remove Ticket — wrong pages removed** — The plugin was removing pages
containing `"PART SKETCH"` text instead of `"MOVE TICKET"` text. It now correctly
removes Move Ticket pages while keeping everything else — and pages containing
`"MIL-SPEC"` or `"HULL"` are always kept even if they also contain Move Ticket text.

**911 Setup — same page logic** — The Move Ticket Omit PDF produced during batch
setup now uses the same rule: remove Move Ticket pages, always keep MIL-SPEC and
HULL pages.

**Update checker** — The manifest fetch now bypasses CDN caching (cache-busting
query parameter + no-cache headers). Previously, a stale cached manifest could tell
TechDeck about an older intermediate release instead of the current latest version,
requiring two update cycles to fully catch up.

**Spinner flavor text** — Running-phase flavor text now holds for **8 seconds** per
phrase (previously 4 seconds). A secondary fix ensures that after a movie-quote
interruption ends, the next phrase always gets a full 8-second window rather than
resuming mid-cycle.

**Console /help** — Removed stale commands (`/profiles`, `/profile`, `/tiles`,
`/guides`, `/guide`) from the help output. The commands still work; they were just
cluttering the list.

**Rave crabs** — Crabs from `/rave` now spawn on whichever monitor TechDeck is
currently displayed on instead of always targeting the primary monitor.

---

## What's New Since v0.8.1

### New Plugin: 911 Remove Ticket

A dedicated tool for stripping **Move Ticket** pages out of nest package PDFs before
routing move tickets.

- Scans a configured directory and lists all PDFs by number
- Select individual files or process the entire batch at once
- MIL-SPEC and HULL pages are always preserved
- Output saved alongside the originals as `{original name} Move Ticket Omit.pdf`
  inside a `Move Ticket Omit/` subfolder — originals are never touched

---

### Plugin Personality System

TechDeck now has opinions about the tools it runs.

### Processing Spinner

When a plugin is running, a spinning icon now appears between the
console output area and the input bar.

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

### Bug Fixes & Performance (v0.8.x)

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
| 911 Remove Ticket | Removes Move Ticket pages from nest package PDFs; keeps MIL-SPEC and HULL pages |
| 922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info |
| Batch Repeater | Copies repeat orders from prior 922 batches |
| LST Organizer | Organizes .lst files by material type |
| PO Packet Extractor | Extracts PO data from PDFs into Excel |
| Part Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation |
| QR Code Generator | GUI plugin — dual-tab QR library and generator |

---

## Installation

Download `TechDeck-0.8.4.1-Setup.exe` from the [Releases](https://github.com/OzymandiasOne/TechDeck/releases) page and run it.
No Python, no admin rights, no PATH changes required.

TechDeck will notify you automatically when a new version is available.
