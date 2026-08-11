# TechDeck v0.8.6.13 - 911 Teams Cards

[![Tests](https://github.com/OzymandiasOne/TechDeck/actions/workflows/tests.yml/badge.svg)](https://github.com/OzymandiasOne/TechDeck/actions/workflows/tests.yml)

**TechDeck** is a standalone Windows desktop application that delivers automation tools
for Electric Boat ASA manufacturing workflows
to colleagues who can't run Python directly. No installs, no PATH changes - just run
the `.exe`.

---

## What's New in v0.8.6.13

**911 Teams Cards is now its own app.** Card generation has moved out of 911 Setup into a
separate tool, so you can post cards without running a setup and run a setup without
posting cards. It needs no batch number - the EB 922 Schedule's queue is the work list -
and it reads whichever batches happen to be waiting. 911 Setup still offers the stage as
an optional first step if you want both in one pass, but it now starts switched off.

**Pick exactly which nests get a card.** The new app opens a tick-list of every nest
waiting on the schedule, showing each one's difficulty, its saw-cut or tube-laser routing,
and its due date. Everything is ticked to begin with, so carding the whole queue is still
one click. Anything you untick stays queued and is offered again next time.

**The schedule keeps itself up to date.** As work completes, TechDeck now advances the
STATUS column for you instead of leaving it to be retyped: a nest moves off the card queue
once its card is posted, and off the setup queue once its batch is set up. Only nests that
genuinely reached the next stage move, and if someone else has the schedule open the cards
still go out - the console just lists the rows to change by hand.

**911 Setup remembers your action checklist.** The window that asks which steps to run now
reopens with whatever you picked last time, saved between sessions and across updates. A
site that always skips a step sets it up once instead of unticking it on every run.

**Cancelling a run now reports as cancelled.** Closing an app's first window used to play
the success sound and award tickets for work that never happened. Backing out of any
folder picker, file picker, or checklist window is now recorded as a cancelled run.

**Difficulty labels are working again.** The rating column on the EB 922 Schedule was
renamed, and TechDeck was still looking for the old name - so it quietly stopped finding
any ratings at all. Packets stamped no difficulty label and Teams cards carried none.
Column lookups now tolerate a heading that has had words added to it.

**Smaller fixes.** A run-completion message could come out with two lines run together.

### Feedback Fixes

*"Could the Teams card generation be separate from 911 Setup? I don't want to make Teams
cards every time I run the setup - sometimes I re-run the setup because something changed
and I just want an updated version."*
911 Teams Cards is now a standalone app, and the stage inside 911 Setup defaults to off.

*"Sometimes I only want to make a couple of Teams cards. Ideally I'd be able to select
which of the orders in the schedule I want, and only make those."*
The new app opens a tick-list of the waiting nests; untick any you don't want yet.

*"Could the schedule's status column be updated automatically as cards are made?"*
It is - nests move to NEED SETUP when their card posts, and to NEED MODEL once their batch
is set up.

*"911 Setup feels less streamlined now - we have to keep toggling off the Teams card
generation and the difficulty label before we can enter our batch number. Could there be
default toggle sets?"*
The checklist window now remembers your selection between sessions, so those toggles stay
where you leave them.

---

## What's New in v0.8.6.12

**922 Setup creates Teams cards again.** On v0.8.6.11 the card post was accepted but the
flow behind it failed before creating anything, so a run could report DONE with no cards
appearing on the D922 PIPELINE board. The posted payload had lost its bucket list in the
v0.8.6.11 reordering change; it's restored, and the payload is now covered by tests so a
required field can't silently disappear again. If your batch got no cards, just re-run
the Generate Teams Cards stage - nothing was half-created, and existing cards are never
duplicated.

**FORMED tags land on the plate, not the rod.** Some parts carry a formed plate AND a rod
under one part number, on two PO lines with different source materials. When the PO had
no BEND note, FormingFinder recorded whichever line came first - often the rod - and
Kitting then stamped FORMED on the rod's kit row while the actual plate went unmarked
(Batch 485 had roughly thirty of these coin-flip parts). FormingFinder now reads the
source-material descriptions and records the plate (THK) line; a BEND note still wins
outright, and a part it can't disambiguate gets a warning naming it instead of a silent
guess. For an affected batch, re-run FormingFinder and then Kitting to reprint correctly.

**LST reports stop counting one tube twice.** A tube can be spelled `-4` on the PO and
`-4A` on the shop file (or the reverse) - the same physical piece renamed between
systems. The 922 LST Organizer treated those as two problems: a "missing" tube AND a
"needs review" file. Both directions now match as one piece, the pairing is printed in
the summary and marked on the report, and a genuinely different piece number still goes
to Needs Review. The 911 LST Organizer gets the same matching for parts on the 1D
diagram, logged and marked `OK as` on its report.

**Batch Repeater checks repeat shop prints up front.** After pulling repeats it now
verifies each repeat folder has its CAD-AND-SHOP-PRINTS folder and the tube cut files in
the 7000 folders beneath it - looking only, nothing is moved. A repeat missing them used
to surface weeks later as "missing tubes" on the end-of-batch LST report; now it's a
warning at pull time, while the source batch is still easy to fix. Orders with no tube
parts are noted as normal, never flagged.

---

## What's New in v0.8.6.11

**911 Setup now creates your modeling cards in Teams.** A new first stage reads the
`EB 922 Schedule` and posts one card into the **MODELING** bucket of SOPO D911 PIPELINE
for every current-pipeline row marked DEPT. 911 with a status of NEED TEAMS/SETUP. Each
card carries the job's difficulty and whether it's a saw-cut or tube-laser job, and the
`Program` field is left off for anything that isn't tube stock. The stage runs before the
batch prompt and doesn't need a batch number, so you can tick it on its own and TechDeck
won't ask for one. Re-running is safe - cards already posted are skipped rather than
duplicated, and nests with no specified work are passed over.

**911 Setup marks how hard each job is.** Every cover sheet now carries a colour-coded
SIMPLE / MEDIUM / DIFFICULT label read straight from the schedule's rating column, and
the setup run finishes with an action checklist so nothing gets missed on handoff. The
label can be switched off if you don't want it.

**922 Setup stamps pallets before it pulls repeats.** The two stages ran in the wrong
order, so repeat orders - and the repeat binders distributed into the root order folders
- could pick up a pallet stamp meant for the current batch. Stamping now finishes first,
and repeats are left clean.

**902 DXF Prep reads the right sheet, and recognises more part numbers.** It could latch
onto a hidden FORMING or PRICING staging sheet instead of the real PO sheet - those
hidden sheets carry the same headers - and silently produce a three-row QTY output. It
now only ever scans visible sheets. The part-number pattern has also been widened to
match the schemes actually appearing on real POs.

**Customer DXF Analysis applies customer guideline offsets for you.** Switch on
**Automated offsets** and enter plate thicknesses once for the whole batch; each file
then opens with guideline offsets already applied to a working copy - holes and cutouts
grown by the thickness band, capped at twice thickness, with a warning under half
thickness, and the outer profile untouched. Save overwrites the original, Export writes a
copy, and either advances the review queue. Enter now drives the whole review flow, and
circles are reported by diameter rather than cut length.

**Apps you remove from a kit stay removed.** Taking an app out of a kit could leave it
still queued to run - the tile was gone from the screen but the selection behind it
wasn't cleared. Removing an app now actually removes it from the run.

**A freeze now explains itself.** If TechDeck stops responding or closes unexpectedly,
it captures what it was doing at the time, so a debug report sent after a restart still
explains the original problem instead of arriving empty.

**At Woogy's Emporium.** The Sentry Drone kill-cam picker is now a gadget you can buy and
arm per app, rather than something that just happens - My Stuff's SET UP window controls
which apps use it. Beyblades join the fidget spinner collection, built from swappable
tops, bottoms and centres, and the spinner art no longer clips or renders oversized on
the store tiles.

**Also:** a new `/moredetails` console command opens a per-app reference covering setup,
how each app works and what it outputs; long item names no longer clip on store tiles;
plugin logs now flush before the completion banner so the banner prints last; and DXF
exports no longer pick up a byte-order mark that made some machines reject the file.

### Feedback Fixes

*"The text boxes on the 911 cover sheets don't look right."* The cover stamp now matches
the requested layout - two left-aligned lines with labels (`BATCH: S036`, `NEST: 503884`)
instead of one centred line - matched to the supplied sample within about a point.

*"The Which Feature list on the feedback form is out of date."* That dropdown is now
built from the app library at runtime, so new apps appear automatically, and retired ones
are marked as retired before dropping off entirely.

*"The 922 Teams cards come out in reverse alphabetical order."* Cards are now posted in
the order that makes the bucket read A-Z top to bottom.

---

## What's New in v0.8.6.10

**911 Batch Repeater v3 - rebuilt around the Master Parts List.** Repeats are no longer
found by scanning old batch folders: the Repeater now looks up every part in each nest
against the 911 Master Parts List (compiled from all completed nests) and copies each
repeat part's CAD files - SolidWorks model, drawing, and PDF - from its completed source
nest into a **REPEAT** folder inside the target nest, organized per part. A new
nest-selection window lets you expand any nest and toggle exactly what it grabs (models,
PDFs, overwrite existing). And when a nest turns up no repeats, the report now tells you
why: its parts are genuinely new to the catalog, or their source folder couldn't be
found. (The old NC-file and inspection-library grabbing is retired.)

**Cancel works everywhere, and the run banner tells the truth.** Every app now checks
for cancellation inside its long loops, so Cancel stops a run promptly - mid-scan,
mid-batch, mid-PDF - instead of waiting for the current sweep to finish. An app that
finishes with skipped stages or a failed step now ends with a visible WARNING instead of
a green checkmark, and the end-of-run banner reflects the real mix of outcomes. Closing
TechDeck while an app is running now asks first, then gives the run a moment to stop at
a safe point instead of cutting it off mid-write.

**Settings saves fixed.** A race between two parts of the app could silently revert
just-saved settings; saving is now atomic and race-free. (The same bug had frozen
several achievements - see Feedback Fixes.) TechDeck also gained its first automated
test suite, guarding this and the rest of the core run logic on every build.

**Safer updates.** The auto-updater now verifies the downloaded installer's SHA-256
fingerprint before running it, so a corrupted or tampered download can never launch.

**911 SSPO Award Review v2.8** - Two new columns close out the output table: **EB
Machine** and **EB Fuel**, read from each nest packet's front-page header table (the
Machine/Gantry and Fuel cells) and repeated on that nest's rows - verified across all
142 packets of Awards 8, 9, and 10.

**Sentry Drone targeting.** Batch picking got an upgrade: 922 Setup's batch pick, and
the 911 Batch Repeater's batch + nest pick, now run through a Sentry Drone overlay -
lock onto the batch folder, zoom inside, lock as many nests as you want, then execute
the strike (locked nests run with the default grabs). Full sound design included. It's
on by default and toggleable in Settings ("Sentry Drone mode"); the Professional theme -
or any hiccup in the effect - falls back to the standard Windows picker automatically.

**UI polish** - On/off options in app Settings render as proper toggle switches; ticking
a stage's checkbox in 922 Setup's master window no longer pops the stage open; the 911
LST Organizer got its own theme-aware folder icon.

### Feedback Fixes

Changes in this release that came directly from submitted feedback - thank you, and
keep it coming.

- *"The Move Ticket Omit cover page doesn't identify its batch and nest, and the
  Material Type is left blank once the move tickets are removed."* - The cover is now
  stamped with the batch and nest in bold red beneath the Quality Requirements block,
  and the blank Material Type cell is filled in automatically (in black, matching the
  form) from the removed move tickets. Applies to 911 Remove Ticket and the 911 Setup
  print-packet step that uses it.

- *"Inspection sheets should include a QF-QU-09 slot for every piece, with the hull
  code shown under each part number."* - 911 Setup now generates one inspection slot
  per piece with the hull code under each part number, and the blank template tab is
  hidden in the finished workbook.

- *"Please put the scribe-verification Word doc in a folder like PRODUCTION
  PAPERWORK."* - 911 Setup now files the QF-QU-15 scribe-verification doc into a
  **PRODUCTION PAPERWORK** subfolder of each nest folder instead of dropping it loose
  (re-running on an existing batch moves the old loose copy in, too).

- *"There should be an easier way to submit suggestions."* - A **Submit Feedback**
  button now sits at the bottom of the left sidebar, one click away from anywhere in
  the app.

- *"The Batch Repeater should only pull orders whose numbers match exactly."* - Repeat
  matching is now exact end-to-end, so an order can no longer partially match a
  similarly-numbered one (e.g. -H1 picking up -H11) - only true repeats are pulled.

- *"The first four achievements never make any progress, while the rest keep
  climbing."* - Root cause found: the settings bug above was reverting the app's
  total-run counter on every run, freezing exactly the achievements that read it. It's
  fixed, and the lost progress heals automatically the first time this version starts.

- *"The ASA game's doesn't have enough ways to influence A-Frame demand when tube surplus piles up."* 
  - The sleeping animation was redrawn, and new gameplay levers let you influence A-Frame demand 
  directly. Plus, a few more things...

- *"Solar panels in the ASA game should have more uses beyond powering the server."* -
  Solar fields now anchor the reworked power economy: the trading AI and the drone
  fleet both draw real power that solar has to supply, and the late game builds on it
  from there.

- *"The Help & Feedback text is hard to read in some themes."* - Secondary text
  everywhere now takes its color from the active theme instead of a fixed gray, and
  updates immediately on theme change.

---

## What's New in v0.8.6.9

**Sharper tile icons across the board.** Ten of the app's hand-drawn tile icons were
redrawn for a cleaner, more consistent look - calculator, copy, lamp, magnifier, ruler,
stamp, toolbox, QR, scissors, plus the ASA game's cartridge. They recolor correctly in
every theme. Purely visual; nothing about how the tools work changed.

**Runtime estimate reworked (SSPO Award Review).** The primary plate-cut estimate is now
derived from actual production throughput (pieces per hour) rather than the older
feed-rate model, with the thickness break tuned per shop feedback and a matching
Analysis sheet.

**922 Setup gains a Batch Folder Setup stage** at the front of the run, and awards
tickets per stage completed (5 each). Multi-PPN orders now get their work-packet PDF
placed in every relevant folder.

**New app: Sheet Metal Calculators** - A library of shop calculators behind a simple
picker. Pick a calculator on the left, fill in the fields, get the result live. Three
to start - **Flat Length** (bend-allowance flat length from K-factor, thickness, inside
radius/ID/OD, and bend angle), **Bend Deduction** (OSSB / bend allowance / bend
deduction), and **Material Weight** (by sheet size or area) - with more being added one
at a time.

**922 LST Organizer v3** - Rewritten matching end to end: aggressive filename
normalization with order-PO and suffix fallbacks, EXTRA files (on disk but not on the
batch PO) called out, and one color-coded PDF report reconciling the PO's tube count
(total / oversized / target-standard) against what was actually pulled. Anything it
can't confidently place lands in a Needs Review folder instead of being guessed at.

**922 Batch Repeater v2.4** - Now keeps the 922 Master Parts List up to date on every
run: writes the batch's PO column and folds each order into the MASTER PARTS catalog
(how many times every part has been made, in which batches, and under what alternate
names), and the MPL gained a formula-driven ANALYSIS sheet of stats and charts.

**922 Pallet Stamper v1.2** - Stamps that fail on the first pass are retried after the
main run, and anything that still can't be stamped is listed in a manual-stamp report
instead of being silently skipped.

**Errors in plain English** - Common user-fixable failures across every app now end
with a clear problem-plus-fix message instead of a technical traceback - including a
workbook you have open in Excel, which now names the file to close and re-run. Failures
that can't be self-diagnosed point to the retry / debug-report path.

**General family** - Apps that belong to no production family (QR Code Generator, Batch
Auditor, Customer DXF Quoting, Sheet Metal Calculators) now wear a visible General
badge instead of sitting in an unlabeled bucket. Also fixed: 911 LST Organizer reads
multi-nest 1D cutting diagrams with spaced nest prefixes correctly.

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
|---|---|
| 902 DXF Prep | Batch DXF cleanup and prep for Boost 902 part files - IGES CONVERT folder + QTY sheet, renames/sorts exported DXFs for AutoCAD review, then recombines and reconciles against the PO spreadsheet |
| 911 Setup | Full 911 QTDR batch setup - nest folders, templates, forecast data, PDFs, inspection sheets and Move Ticket Omit stamping - behind a checklist of what to run that remembers your selection between sessions |
| 911 Teams Cards | Posts one Teams modeling card per 911 nest the EB 922 Schedule marks NEED TEAMS/SETUP, into the MODELING bucket of the SOPO D911 PIPELINE plan with its difficulty, its saw-cut or tube-laser machine and its scheduled due date, then moves each nest's status along the schedule as its card goes out. Pick which nests you want cards for - all ticked by default - and the rest stay queued for next time. Needs no batch number |
| 911 Batch Repeater | Finds repeat parts for a 911 batch via the 911 Master Parts List (compiled from completed nests) and copies each repeat's CAD files (SolidWorks model, drawing, and PDF) from its completed source nest into a REPEAT folder inside the target nest. If you own the Sentry Drone and have switched it on for this app, the two-phase drone picker locks the batch folder, zooms inside, then lets you lock multiple nests before striking them - those nests run with the default grabs. Otherwise: a folder dialog plus a nest-selection window where any nest expands to toggle exactly what it grabs (models, PDFs, overwrite existing) |
| 911 Remove Ticket | Removes Move Ticket pages from nest package PDFs (keeps MIL-SPEC and HULL pages); stamps the cover with the batch + nest in red and fills in the Material Type from the removed move tickets |
| 911 PO PDF Extractor | Extracts PO data from PDFs into Excel |
| 911 Sketch Extractor | Extracts part sketch data with 17-column output and weight consolidation |
| 911 SSPO Award Review | (Formerly 911 Runtime Estimator.) Runs off an award package (folder of order folders); estimates plate cutting time from actual D911 throughput (a pieces-per-hour table by thickness band derived from 18.5 months of closed actuals - includes setup/handling) plus stock/material from each nest's packet PDF - the old exact-linear-inch times (each work order's DXF geometry / a thickness-driven feed rate) still computed as far-right reference columns - and writes one workbook with Plates and Non-Plates sheets (data table + real Excel PivotTable each), a Shape Ft Req sheet totalling each shape nest's stock feet (Summary-of-Batches lengths / 12, rounded up per length) for receiving, and a Working Forecast Input sheet (per-nest Source Material / Pieces / Orders from the nest packet, shape Total Ft Req, blank REM columns) that copy-pastes straight into the Working Forecast List |
| 911 SSPO Invoicing Prep | Splits an SSPO pricing sheet into one workbook per Batch + Nest (each in its own "BATCH NEST Invoicing Docs" folder), each with the split rows + price total on tab 1 and a generated ASA Invoice Supplement on tab 2 (PO / PO Line auto-filled from the Working Forecast List), plus a top-level "D911 Workorder Close Outs" sheet (Scheduling Group set to Closed) |
| 911 Baked Beans Wild Ride | Consolidates a folder of filled NC-calc pricing sheets into one review list (DYPN, Batch, Nest, Total Bevels, Total Complex Bevels, Total Cut Lin per part + totals row, sorted by batch/nest/part), saved into that same folder and named from the batch + nest the sheets themselves declare |
| 911 LST Organizer | Pulls the .lst files for the parts on a nest's 1D cutting diagram into the nest's PRODUCTION PAPERWORK\LST folder - cross-batch parts are resolved to their source batch automatically |
| 922 Setup | Full 922 batch prep behind a master toggle window: builds the batch's order folders from the PO REV C workbook (one per ORDER-PPN, with a per-order copy of the PO workbook and each order's work packet PDF filed in from the Work Packets folder), creates the batch's ordered pipeline buckets + one pallet-labelled Teams card per order ("BATCH X: folder") via a Power Automate webhook, then optionally runs the Batch Repeater and Pallet Stamper with the same batch number |
| 922 Pallet Stamper | Stamps work-packet PDFs with batch and pallet info |
| 922 FormingFinder | Discovers formed plate PDFs via filename, PO NOTES, and PDF spatial analysis; copies, merges, and populates the Bent Plates sheet |
| 922 Kitting | Formats and prints kitting paperwork for an entire 922 batch; detects formed plates, merges all kit pages into a single PDF |
| 922 Batch Repeater | Copies repeat orders from prior 922 batches, distributes CAD prints + binders to matching orders, labels each repeat's Teams card REPEAT and moves it to MODEL CHECK - and keeps the 922 MPL up to date (writes the new batch's PO column and updates the MASTER PARTS catalog: how many times each part has been made, in which batches, and its alternate part names) |
| 922 LST Organizer | Gathers a batch's tube .lst files into per-material folders and writes one color-coded PDF that reconciles the PO's tube count against what was actually pulled; files it can't confidently place go to a Needs Review folder |
| 922 Runtime Genie | Scans CNC machine time PDFs, matches LST reference, outputs estimate with 40% buffer |
| QA Gemba Analyzer | GUI plugin (QA family) - logs QA rework events to one shared workbook and charts YTD / last-week performance (pie/column/stacked, best-fit line, %-threshold) with a one-click printable Gemba Pack PDF |
| Batch Auditor | Read-only readiness check for a 911/922 batch: verifies orders/prints, LST files, run time, forming, pallets, and kitting, then renders a dashboard (KPI cards + charts) and a text summary - nothing is modified |
| Customer DXF Analysis | Interactive DXF viewer for quoting - layer-colored flat pattern, per-line measurements, layer reassignment for selected lines, and total linear inches of cut - plus automated customer-guideline offsets: enter the plate thickness and every hole/cutout is increased per the customer's thickness band table (features already twice the plate thickness are left alone; below-minimum features get flagged), review the result, then Save over the original or Export a copy. Batch mode queues a whole folder and steps through it one file at a time; manual amounts stay available via Adjust Dimensions |
| Sheet Metal Calculators | GUI plugin - a library of shop calculators behind a picker, each defined by a simple field-list + formula so new ones drop in easily. Calculators: Flat Length (bend-allowance flat length from K-factor, thickness, inside radius/ID/OD, and bend angle), Bend Deduction (OSSB / bend allowance / bend deduction), and Material Weight (by sheet size or area) |
| QR Code Generator | GUI plugin - dual-tab QR library and generator |

---

## Development & Testing

TechDeck is a Python 3.13 / PySide6 app, frozen to a standalone exe with PyInstaller +
Inno Setup for a locked-down corporate environment (users cannot install Python).

```powershell
# install dev dependencies (runtime pins + test toolchain)
python -m pip install -r requirements-dev.txt

# run the app in dev mode (no build required)
python -m techdeck

# run the test suite
python -m pytest

# with coverage
python -m pytest --cov=techdeck --cov=tools --cov-report=term
```

The suite (`tests/`) runs Qt headless (`QT_QPA_PLATFORM=offscreen`, set in
`conftest.py`) and covers the plugin executor, the plugin SDK, settings persistence,
the auto-updater (including SHA-256 installer verification), and widget behavior for
the main UI surfaces.

**Quality gates.** Every push runs the suite on a Windows runner via GitHub Actions
([tests.yml](.github/workflows/tests.yml)), along with `tools/check_ship_readiness.py`
- a custom static gate that walks every plugin's import graph and verifies each import
exists in the frozen bundle's `hiddenimports`, validates plugin manifests, and loads
every plugin through the real `PluginLoader`. The same two gates run locally in
`build.ps1`, so a build that would fail in the field never produces an installer.

Releases are built locally (`.\build.ps1`), published as GitHub Releases, and
distributed by an in-app auto-updater driven by a version manifest on GitHub Pages.