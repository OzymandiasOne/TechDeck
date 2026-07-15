# TechDeck v0.8.6.8 - 922 Setup Expansion
**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows
to colleagues who can't run Python directly. No installs, no PATH changes - just run
the `.exe`.

---

## What's New in v0.8.6.8

**922 Setup is now the whole 922 batch-prep sequence in one run.** Launching it opens a
master window listing the stages - **Generate Teams Cards**, **Batch Repeater**, and
**Pallet Stamper** - each toggleable, run top to bottom. Click a stage's name to reveal
its options. The batch you pick for the Teams cards carries through automatically, so
the later stages never re-ask for it. (The standalone Batch Repeater and Pallet Stamper
tiles still work exactly as before.)

**Generate Teams Cards builds the full pipeline.** One run creates the batch's five
buckets in order - HOLD, BATCH {n}, MODEL CHECK, 7000, SHOP READY - and one card per
order folder, each labelled with its pallet (PALLET 1/2/3) straight from the batch's
Pallet & Rod Organizer. An "Apply source material labels" option (off by default) adds
each order's tube source materials as labels too. Re-running finds the existing buckets
instead of duplicating them.

**Batch Repeater now finishes the job in Teams.** After pulling repeats and
distributing CAD prints + binders, it labels each repeat's card REPEAT and moves it to
the batch's MODEL CHECK bucket automatically. Both steps are toggleable from the master
window, and a dry-run setting previews exactly what would be labelled without posting.

---

## What's New in v0.8.6.7

**911 SSPO Award Review** - The 911 Runtime Estimator has a new name to match what it's
actually for: reviewing an SSPO award package. Two new output sheets ship with it. **Shape
Ft Req** gives receiving the stock feet required per shape nest, computed from the Summary
of Batches lengths (each length rounded up to the foot, then summed, with a grand total).
**Working Forecast Input** lays out one row per nest in the Working Forecast List's own
input-column order - Source Material / Pieces / Orders pulled from each nest packet plus
the shape Total Ft Req - so the whole block copy-pastes straight into the forecast.

**911 SSPO Invoicing Prep** - Each Batch+Nest pricing workbook now lands in its own
"BATCH NEST Invoicing Docs" subfolder, ready to collect the rest of that nest's invoicing
paperwork. The run also writes a top-level "D911 Workorder Close Outs {date}" workbook
(source columns carried over verbatim with styling, Scheduling Group set to "Closed") for
closing out the work orders. The ASA Invoice Supplement logo is sized correctly and stray
wrap-text formatting is gone.

**Updater polish** - Installing an update no longer flashes console windows during the
restart handoff, and release notes in the update dialog no longer clip under the progress
bar.

**Submit Feedback** - The Help & Feedback button is now "Submit Feedback" everywhere it
appears, matching what it does.

**ASA: The Video Game v2.3** - The endgame transition is now a proper two-beat "Exit
Strategy" final project that converts all remaining reputation into compute before the
probe phase begins - no more stranded resources heading into the finale.

---

## What's New in v0.8.6.6

**911 Runtime Estimator v2 - exact linear-inch cut times** - Plate cut times are now
measured, not banded: each work order's DXF geometry is parsed (lines, arcs, circles,
polylines - every cut layer) and the exact linear inches of cut are divided by a
thickness-driven feed rate. Runs off an award package (the folder of order folders,
before batching) so work-scope and machine review can happen up front. The output
workbook gained an **Analysis sheet** (thickness/material/layering/data-quality charts,
DXF-coverage callout listing any parts whose DXF is missing, flagged-deviation list),
an auditable **Equation column** that spells out every row's math, Multi-Layered and
LI-deviation columns with row highlighting, and remnant dimensions. Rows with no DXF
fall back to the old thickness band and are flagged red. (The separate 911 Linear Inch
CutTime app was absorbed into this and removed.)

**New app: 911 LST Organizer** - Pick a nest's PRODUCTION PAPERWORK folder and it pulls
exactly the .lst files that nest's 1D cutting-pattern diagram lists into an LST
subfolder - including parts cut from other batches, which are found automatically and
prefixed with their nest. Missing files or unresolvable nests raise a blocking warning
so nothing is silently skipped.

**Reliability** - Reading a workbook that OneDrive holds cloud-only no longer fails with
a confusing "File is not a zip file" error; the file is hydrated and retried like every
other OneDrive read (this had bitten 911 Setup).

**ASA: The Video Game v2** - Full 16-bit rebuild that now runs the complete arc: the
business act (yard, tech team, trading desk, A-frames, drones, space program with a real
power economy), the probe program that transforms the whole interface, a first-contact
war against the Woogs with an upgrade tree and real attrition combat, and an actual
ending. Plus: Mr Beans' eyes follow your cursor on the Home tile.

---

## What's New in v0.8.6.5

**New app: 911 Baked Beans Wild Ride** - Point it at a folder of filled "NC style baked
beans" calc workbooks and it consolidates every part into one review list (DYPN, Batch,
Nest, Total Bevels, Total Complex Bevels, Total Cut Lin) with live totals, sorted by
batch/nest/part, saved into that same folder and named from the batch + nest the sheets
themselves declare. Sheets that haven't been calculated yet are flagged instead of
silently skipped. The folder is the only question it asks.

**QA Gemba Analyzer** - Now tracks **Missing Material? (Y/N)** on every rework event,
with a matching chart filter and group-by. The demo seed data is gone (the log starts
empty and real), and the shared rework workbook now lives in the QA team's Gemba folder
in the ASA Quality Management System library, found automatically on any machine that
syncs it.

**Library & window polish** - Library tiles now match Home (family badge in the corner,
family prefix dropped from names); admin-only console commands are gated behind
`/admin`; the window's minimum size follows only the page you're looking at, so Home
and Library shrink properly and store pages can't force the window to grow.

---

## What's New in v0.8.6.4

**Four new apps**
- **902 DXF Prep** - first app in the new 902 family: pick the folder holding a batch's
  part files and run any/all of three processes (checkbox picker, all selected by
  default): builds the IGES CONVERT folder + a formatted QTY spreadsheet from the PO,
  cleans DXF filenames and sorts them into AutoCAD-sized folders of 25, then recombines
  and reconciles everything against the PO (missing parts listed in a text report,
  extra files moved to an EXTRA folder, quantity prefixes on multi-qty parts).
- **922 Setup** - reads a batch's order folders and creates one Planner card per order
  in the D922 PIPELINE plan automatically.
- **QA Gemba Analyzer** - first app in the new QA family: log rework events to a shared
  workbook and explore them in a chart dashboard (pie/column/stacked, time windows,
  group-by toggles), with a one-click printable Gemba Pack PDF.
- **911 SSPO Invoicing Prep** - splits an SSPO pricing sheet into one workbook per
  Batch + Nest (each in its own "Invoicing Docs" folder), each with a generated ASA
  Invoice Supplement tab (PO / PO Line filled from the Working Forecast List
  automatically), plus a top-level Workorder Close Outs sheet.

**Tickets & Woogy's Emporium** - Successful runs and feedback submissions now earn
tickets, spendable at Woogy's Emporium (My Account > Ticket Counter): fidget-spinner
skins, furniture and decorations, backgrounds, a Friend, and a purchasable mini-game.
Everyone starts with 75 tickets - enough for a first toy. A new Achievements tab awards
bonus tickets for milestones.

**My House (Garden)** - A new My Account tab: click the house to reveal the interior,
furnish it with Emporium purchases (indoor + yard items), watch your tree grow with app
usage, and meet Buddy - a purchasable pig who wanders the yard and uses your stuff.

**Folder picking, not path pasting** - Apps that need a per-run folder (902 DXF Prep,
911 Runtime Estimator) now open the standard Windows folder dialog instead of asking
you to paste a path into the console.

**Professional theme** - A clean light look that also hides the games and playful extras;
made for running TechDeck in front of clients.

**Fixes & polish** - 911 Runtime Estimator files structural shapes (tube/angle/bar) onto
the Non-Plates sheet correctly; batch numbers asked once and shared across same-family
apps in a multi-run; run-completion sounds for window apps fire at the real finish;
LST Organizer / Pallet Stamper no longer count system folders; stuck run-spinner fixed;
smaller installer (unused components trimmed).

---

## What's New in v0.8.6.3

**Feedback submission works on every OneDrive setup** - Submitting a suggestion
(Settings > Help & Feedback) could fail with "Workbook Not Found" on machines that
synced the QTDR library directly instead of the whole SharePoint site. TechDeck now
locates the shared suggestions workbook across every sync layout, so feedback saves
reliably. The batch apps also auto-detect a directly-synced library now, without a
manual folder setting.

**911 Setup flags missing forecast data** - If a nest isn't found in the Working Forecast
List (most often because the forecast is out of date or not fully synced on that machine),
911 Setup previously left columns A-C blank and still reported success. It now ends with a
clear warning listing those nests and how to fix it, and locates the forecast columns by
header so a reordered sheet can't silently break the lookup.

**Console polish** - The hidden `/friend` companion's musings were rewritten, and the
`/fidget` spinner was remade as a clean, theme-coloured, symmetric pixel-art spinner that
`/clear` puts away.

---

## What's New in v0.8.6.2

**Cloud-only OneDrive files download automatically** - On a freshly synced machine,
files can exist in name only (contents still in the cloud). Apps previously crashed with
a cryptic "Invalid argument" error the moment they read one - now every app asks OneDrive
to download the file and continues, or stops with clear instructions if OneDrive can't
(applies to all 911/922 apps, FormingFinder included). Tip: right-clicking the Pilot
Program folder and choosing "Always keep on this device" makes everything faster.

**Cancel actually cancels** - Cancel now works even while an app is waiting at a console
question, the button immediately shows "Cancelling..." so you know it registered, and a
double-click can no longer accidentally start a brand-new run the instant the old one
stops.

---

## What's New in v0.8.6.1

**911/922 apps find their folders on every machine** - On a fresh install, the batch
apps only looked for the Electric Boat ASA Docs library under two fixed OneDrive folder
names, so machines whose OneDrive named it differently got "Could not locate" errors and
had to set each app's directory by hand. TechDeck now discovers the library wherever
OneDrive put it - tenant-name variants, "Add shortcut to My files" layouts, and relocated
OneDrive folders all resolve automatically. Manually set directories still win - and a
directory set for ONE app now helps every other app (and Report Feedback) find the
library too.

**Report Feedback works on every machine** - The feedback workbook lookup uses the same
folder discovery as the apps, so machines that previously showed "Workbook Not Found"
(even with the SharePoint library synced) now find it - and any manually set app
directory is used as a hint as well.

**Library shows every app again** - On some machines the Library page came up showing
only a single app card until you cycled through kits; all installed apps now lay out
correctly on first open.

**Steel Tube Operation un-frozen** - The /steelbeams game froze permanently the moment
the A-Frame Prototype completed. Fixed, and the game now reports any future fault in
its own log instead of silently freezing.

**New: Generate Debug Report** - Settings > Help & Feedback now has a one-click debug
report. If something misbehaves on your machine, click it and send the file it saves to
your Desktop to the maintainer - it captures TechDeck's version, folder discovery, app
validation results, and logs from your machine (no production documents), which is
usually enough to pinpoint a problem without back-and-forth.

**Customer DXF Quoting launches again** - The v0.8.6 build was missing a component the
DXF viewer needs on a freshly updated machine, so it failed with "missing dependency"
before it could open. The component now ships with the app.

**A failed app launch no longer locks up TechDeck** - When an app couldn't start, the
deck used to stay stuck on a red Cancel button with nothing actually running, and no
other app could be launched until TechDeck was restarted. A failed start now marks the
tile with an error, reports the real reason in the console, and frees the deck
immediately.

**Releases are verified before they ship** - The build now runs an automatic
ship-readiness check on every app (all 15 verified for this release), so an app that
works on the dev machine but not out of the box for everyone else can no longer reach
an installer.

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

902 DXF Prep | Batch DXF cleanup and prep for Boost 902 part files - IGES CONVERT folder + QTY sheet, renames/sorts exported DXFs for AutoCAD review, then recombines and reconciles against the PO spreadsheet 
911 Setup | Full 911 QTDR batch setup - nest folders, templates, forecast data, PDFs 
911 Batch Repeater | Finds and copies repeat parts (NC files + inspection PDFs) for 911 batches 
911 Remove Ticket | Removes Move Ticket pages from nest package PDFs (keeps MIL-SPEC and HULL pages); stamps the cover with the batch + nest in red and fills in the Material Type from the removed move tickets 
922 Setup | Full 922 batch prep behind a master toggle window: creates the batch's ordered pipeline buckets + one pallet-labelled Teams card per order ("BATCH X: folder") via a Power Automate webhook, then optionally runs the Batch Repeater and Pallet Stamper with the same batch number 
922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info 
922 FormingFinder | Discovers formed plate PDFs via filename, PO NOTES, and PDF spatial analysis; copies, merges, and populates the Bent Plates sheet 
922 Kitting | Formats and prints kitting paperwork for an entire 922 batch; detects formed plates, merges all kit pages into a single PDF 
Batch Repeater | Copies repeat orders from prior 922 batches, distributes CAD prints + binders to matching orders, then labels each repeat's Teams card REPEAT and moves it to MODEL CHECK 
922 LST Organizer | Gathers a batch's tube .lst files into per-material folders and writes one color-coded PDF that reconciles the PO's tube count against what was actually pulled; files it can't confidently place go to a Needs Review folder 
911 LST Organizer | Pulls the .lst files for the parts on a nest's 1D cutting diagram into the nest's PRODUCTION PAPERWORK\LST folder - cross-batch parts are resolved to their source batch automatically 

911 PO PDF Extractor | Extracts PO data from PDFs into Excel 
911 Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation 
QR Code Generator | GUI plugin - dual-tab QR library and generator 
922 Runtime Genie | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer 
911 SSPO Award Review | (Formerly 911 Runtime Estimator.) Runs off an award package (folder of order folders); estimates plate cutting time from the EXACT linear inches of cut (each work order's DXF geometry / a thickness-driven feed rate) plus stock/material from each nest's packet PDF, and writes one workbook with Plates and Non-Plates sheets (data table + real Excel PivotTable each), a Shape Ft Req sheet totalling each shape nest's stock feet (Summary-of-Batches lengths / 12, rounded up per length) for receiving, and a Working Forecast Input sheet (per-nest Source Material / Pieces / Orders from the nest packet, shape Total Ft Req, blank REM columns) that copy-pastes straight into the Working Forecast List 
Customer DXF Quoting | Interactive DXF quoting viewer - layer-colored flat pattern, per-line measurements, layer reassignment for selected lines, and total linear inches of cut 
QA Gemba Analyzer | GUI plugin (QA family) - logs QA rework events to one shared workbook and charts YTD / last-week performance (pie/column/stacked, best-fit line, %-threshold) with a one-click printable Gemba Pack PDF 
911 SSPO Invoicing Prep | Splits an SSPO pricing sheet into one workbook per Batch + Nest (each in its own "BATCH NEST Invoicing Docs" folder), each with the split rows + price total on tab 1 and a generated ASA Invoice Supplement on tab 2 (PO / PO Line auto-filled from the Working Forecast List), plus a top-level "D911 Workorder Close Outs" sheet (Scheduling Group set to Closed) 
911 Baked Beans Wild Ride | Consolidates a folder of filled NC-calc pricing sheets into one review list (DYPN, Batch, Nest, Total Bevels, Total Complex Bevels, Total Cut Lin per part + totals row, sorted by batch/nest/part), saved into that same folder and named from the batch + nest the sheets themselves declare 