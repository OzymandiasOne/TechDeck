# TechDeck v0.8.5

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows (911 and 922 QTDR production packages)
to colleagues who can't run Python directly. No installs, no PATH changes — just run
the `.exe`.

---

## What's New in v0.8.5

### New Plugins

**922 FormSeeker** — Discovers formed plate PDFs in a 922 batch via filename, PO NOTES,
and PDF spatial analysis. Copies and merges them, then populates the Bent Plates sheet
in the Pallet & Rod Organizer.

**922 Kitting** — Formats and prints kitting paperwork for an entire 922 batch.
Applies batch color formatting, detects formed plates from the Bent Plates sheet,
and merges all kit pages into a single PDF.

### Surface Redesign

- Live theme switching — themes now apply instantly, no restart required.
- Settings reorganized into Personalization, Apps, and Help & Feedback tabs.
- Report Feedback moved into Settings → Help & Feedback.
- Plugin settings now render in a redesigned dynamic form widget.
- Splash screen now plays in a dedicated subprocess (smooth animation regardless of
  startup load) and matches the active theme. Rounded corners + heavier caption shadow
  for visual polish.

### Other

- New Steel Tube Operation easter-egg game (`/steelbeams`).
- `/info` command describes selected tile(s).
- Audio system polish: pre-loaded sounds, click and error chimes, distinct sidebar nav sound.
- Removed plugin nickname system, retired `/compliment` and `/roast`, removed console timestamps.

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

## Installed Plugins

| Plugin | Description |
|---|---|
| 911 Setup | Full 911 QTDR batch setup — nest folders, templates, forecast data, PDFs |
| 911 Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches |
| 911 Remove Ticket | Removes Move Ticket pages from nest package PDFs; keeps MIL-SPEC and HULL pages |
| 922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info |
| 922 FormSeeker | Discovers formed plate PDFs via filename, PO NOTES, and PDF spatial analysis; copies, merges, and populates the Bent Plates sheet |
| 922 Kitting | Formats and prints kitting paperwork for an entire 922 batch; detects formed plates, merges all kit pages into a single PDF |
| Batch Repeater | Copies repeat orders from prior 922 batches |
| LST Organizer | Organizes .lst files by material type; outputs per-batch overview |
| PO Packet Extractor | Extracts PO data from PDFs into Excel |
| Part Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation |
| QR Code Generator | GUI plugin — dual-tab QR library and generator |
| Run Time Estimator | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer |

---

## Installation

Download `TechDeck-0.8.5-Setup.exe` from the [Releases](https://github.com/OzymandiasOne/TechDeck/releases) page and run it.
No Python, no admin rights, no PATH changes required.

TechDeck will notify you automatically when a new version is available.
