# TechDeck v0.8.5.1 - 911 Setup Upgrades

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows
to colleagues who can't run Python directly. No installs, no PATH changes — just run
the `.exe`.

---

## What's New in v0.8.5.1

### 911 Setup

**Pick which nests to run** - After entering the batch number, 911 Setup now shows a
checklist of every nest in the batch. Check the whole batch or just the nests you need;
nests that already have a folder are flagged "already set up." Nothing runs until you
submit.

**Nests listed in Windows order** - The nest checklist (and the order they're processed)
now matches the ascending order Windows Explorer shows your files.

**Correct MIL spec and material** - MIL spec and material type are now read from each
nest's own work-packet move ticket, so every nest gets its own correct values instead
of inheriting another nest's spec. Non-MIL specs (QQ-, ASTM-, AISI-) are captured too.

**Every part row filled** - MIL spec and material now appear on every part's row across
the NEST and SCRIBE VERIFICATION sheets, not just the first row.

**Scribe verification form included** - The scribe-verification document is copied into
every generated nest folder automatically.

---

## What's New in v0.8.5

### New Plugins

**922 FormSeeker** - Discovers formed plate PDFs in a 922 batch via filename, PO NOTES,
and PDF spatial analysis. Copies and merges them, then populates the Bent Plates sheet
in the Pallet & Rod Organizer.

**922 Kitting** - Formats and prints kitting paperwork for an entire 922 batch.
Applies batch color formatting, detects formed plates from the Bent Plates sheet,
and merges all kit pages into a single PDF.

### Surface Redesign

- Live theme switching - themes now apply instantly, no restart required.
- Settings reorganized into Personalization, Apps, and Help & Feedback tabs.
- Report Feedback moved into Settings → Help & Feedback.
- Plugin settings now render in a redesigned dynamic form widget.
- Splash screen now plays in a dedicated subprocess (smooth animation regardless of
  startup load) and matches the active theme. Rounded corners + heavier caption shadow
  for visual polish.

### Other

- `/info` command describes selected tile(s).
- Audio system polish: pre-loaded sounds, click and error chimes, distinct sidebar nav sound.

---

## What's New in v0.8.4.2

### Bug Fixes

**911 Setup - inspection sheet formatting restored** - Inspection sheets generated
by 911 Setup now preserve every detail of the template: conditional formatting
(the grey-to-white field-fill logic), data validation, merged cells, and theme
references. Previously the underlying sheet-copy mechanism silently dropped all
350 conditional formatting rules, leaving every cell white and breaking the
template's interactive field design. The plugin now drives Excel directly for
the sheet-duplication step, preserving everything natively. Sheet naming
(suffix + duplicate disambiguation) and the part-number write into the A16:C17
merged box are unchanged.

**Report Feedback icon - Light and Salmon themes** - The Report Feedback button
now displays the correct icon under the Light and Salmon themes. Previously
those themes fell back to the account icon because the dark-icon folder was
missing a `feedback.svg`.

**TechDeck icon in title bar and taskbar** - The TechDeck icon now appears in
the application's title bar and Windows taskbar, replacing the generic default
icon. The packaged `.exe` file itself now also shows the TechDeck icon in
Explorer and on pinned shortcuts.

---

## Installed Plugins

| Plugin | Description |

911 Setup | Full 911 QTDR batch setup - nest folders, templates, forecast data, PDFs 
911 Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches 
911 Remove Ticket | Removes Move Ticket pages from nest package PDFs; keeps MIL-SPEC and HULL pages 
922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info 
922 FormSeeker | Discovers formed plate PDFs via filename, PO NOTES, and PDF spatial analysis; copies, merges, and populates the Bent Plates sheet 
922 Kitting | Formats and prints kitting paperwork for an entire 922 batch; detects formed plates, merges all kit pages into a single PDF 
Batch Repeater | Copies repeat orders from prior 922 batches 
922 LST Organizer | Organizes .lst files by material type; outputs per-batch overview 
911 PO PDF Extractor | Extracts PO data from PDFs into Excel 
911 Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation 
QR Code Generator | GUI plugin - dual-tab QR library and generator 
922 Runtime Genie | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer 