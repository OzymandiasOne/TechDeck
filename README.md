# TechDeck v0.8.6 - DXF Quoting Upgrades & Quality-of-Life Fixes
**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows
to colleagues who can't run Python directly. No installs, no PATH changes - just run
the `.exe`.

---

## What's New in v0.8.6

**Customer DXF Quoting v1.2** - A new app that takes in DXF files, displays the part with dimensions and layers, 
allows for reassigning/assigning layers to said lines, calculates total linear inches of cut, and exports a new dxf file with the updated changes. 

**Report Feedback fixed for everyone** - The feedback workbook now handles file lookup and modification the same
way all apps find their folders, so it works no matter how OneDrive named the synced SharePoint folder on your machine.

**App directory settings** - Every app that works out of a fixed OneDrive folder
(Batch Auditor, 911 Batch Repeater, 922 Kitting, FormingFinder, Runtime Genie) now shows
that folder in Settings > Apps; blank means auto-detect, or set it explicitly.

**Window & layout fixes** - Maximized window no longer clips at the bottom of the screen;
the Run button stays available when the console is collapsed; the console can be dragged
much taller; the Library packs apps tightly at any window size; missing-app tiles can be
removed cleanly and follow theme changes; the post-update notes window opens at the right
size.

**Console polish** - /help shows a "read more" hint, blackjack takes a bet each hand and
auto-plays if the player hits a 21, and a few more surprises.

---

## What's New in v0.8.5.5

**New nest number format supported** - 911 Setup and Batch Auditor now recognize the new
alphanumeric nest package numbers (e.g. `5CDAVW`) introduced with batch GX030, alongside
the existing numeric and P/S-prefixed formats.

**911 Setup verifies quantities against the nest packets** - Some BATCH LISTs arrive with
the `DYPN QTY` and `Material Amount (Total)` column headers swapped (confirmed on
GX029-GX032). 911 Setup now checks both columns against the per-part quantities on the
nest packet PDF's summary page, fills the nest workbooks from whichever column the packets
confirm, and repairs the swapped headers in the BATCH LIST file. Any part whose quantity
still disagrees with the packet keeps the BATCH LIST value but is flagged: its qty cell is
highlighted yellow in the workbook, and an end-of-run QTY VERIFICATION summary lists every
mismatched or unverifiable part so nothing slips through.

---

## What's New in v0.8.5.4

**Minor bug and visual fixes** - Icons updated. Visual feedback refined. Light theme tweaked to warmer values.  

**Console Update** - /moth & /haiku removed; /friend added

---

## What's New in v0.8.5.3

**Cancel actually stops long scans** - When a plugin was scanning a large batch folder,
clicking **Cancel** could appear to do nothing because the scan ran in one uninterruptible
sweep. The 922 LST Organizer, 922 FormSeeker, and 922 Batch Repeater now check for
cancellation while they scan, so Cancel stops them promptly. Cancel also logs a brief
"Cancelling run..." message so you get immediate feedback.

**Cleaner Home tiles** - Removed the status ring that appeared around a tile's icon while
running; a tile's status now reads from its shadow pulse and the green success flash.

---

## What's New in v0.8.5.2

**Plugins load again** - Fixed a packaging bug in v0.8.5.1 where most plugins failed to
start with a "missing dependency: plugin_sdk" error. The shared plugin toolkit is now
bundled into the build, so all plugins run normally.

**Theme-matched tile icons** - The Home and Library tile icons now recolor to match the
active theme using a curated pixel-art palette (dark, light, blue, cyberpunk, matrix, and
cherry blossom each get their own look).

**Cleaner Home family tags** - The 911/922 family tag on Home tiles is now text-only,
colored with the active theme's accent instead of sitting in a filled chip.

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

**922 FormingFinder** - Discovers formed plate PDFs in a 922 batch via filename, PO NOTES,
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
911 Batch Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches 
911 Remove Ticket | Removes Move Ticket pages from nest package PDFs; keeps MIL-SPEC and HULL pages 
922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info 
922 FormingFinder | Discovers formed plate PDFs via filename, PO NOTES, and PDF spatial analysis; copies, merges, and populates the Bent Plates sheet 
922 Kitting | Formats and prints kitting paperwork for an entire 922 batch; detects formed plates, merges all kit pages into a single PDF 
Batch Repeater | Copies repeat orders from prior 922 batches 
922 LST Organizer | Organizes .lst files by material type; outputs per-batch overview 
911 PO PDF Extractor | Extracts PO data from PDFs into Excel 
911 Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation 
QR Code Generator | GUI plugin - dual-tab QR library and generator 
922 Runtime Genie | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer 
911 Runtime Estimator | Reads each nest's packet PDF and batch list across a directory of orders, computes a plate-cutting time estimate, and writes one workbook with Plates and Non-Plates sheets (data table + nest summary each) 
Customer DXF Quoting | Interactive DXF quoting viewer - layer-colored flat pattern, per-line measurements, layer reassignment for selected lines, and total linear inches of cut 