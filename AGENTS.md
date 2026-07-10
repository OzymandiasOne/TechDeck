# TechDeck — Codex Project Guide

This file is the **always-on router**: a lean index of the must-know facts plus pointers to
deeper docs you load on demand. Keep it under the budget in **Doc Governance** (bottom).
Detail belongs in `docs/`, the skills, or `LESSONS_LEARNED.md` — not here.

## What Is TechDeck

TechDeck is a Python/PySide6 desktop app that distributes automation plugins to
colleagues at American Steel & Alum working on Electric Boat ASA manufacturing workflows
(911 and 922 QTDR production packages). Core constraint: a locked-down corporate IT
environment — users can't install Python, modify PATH, or run scripts directly. TechDeck
is packaged as a standalone Windows exe via PyInstaller + Inno Setup and distributed
through GitHub Releases with an auto-updater.

Current version: **0.8.6.4**
GitHub: `https://github.com/OzymandiasOne/TechDeck`
Updates manifest: `https://ozymandiasone.github.io/TechDeck-updates/manifest.json`

---

## Reference Docs Map

The deep detail lives in focused docs that load **on demand** — read the one whose trigger
matches your task instead of reconstructing from scratch. Each is signposted here so you
always know it exists.

| Doc | Read it when… |
|---|---|
| `docs/ARCHITECTURE.md` | Working on the shell/UI, theming, splash, tile grid, plugin execution/pause/resume/shelve, console, or dashboard — plus the full project-structure file map. |
| `docs/PLUGINS.md` | Modifying/debugging a specific plugin's internals (the deep notes behind the roster table below). |
| `docs/CONSOLE_AND_EGGS.md` | Adding/changing a console `/command`, the talkback system, or an easter egg. |
| `docs/TEAMS_CARDS.md` | Working on the `922_setup` plugin or the Power Automate flow that turns its payload into D922 PIPELINE Planner cards (the webhook contract + flow recipe). |
| `docs/USAGE_TELEMETRY.md` | Working on usage telemetry or feedback delivery — the local-spool + Power Automate webhook design, payload schema, flow recipe, and go-live steps. |
| `docs/DOC_PROTOCOL.md` | A change adds/removes/renames a plugin, ships a feature, or bumps the version — the full doc-sync procedure + the two Excel workbooks. |
| `docs/PLUGIN_SHIP_REQUIREMENTS.md` | Adding a plugin or an import to one, or prepping a release — the "works out of the box" checklist + the `tools/check_ship_readiness.py` gate that build.ps1 enforces. |
| `LESSONS_LEARNED.md` | Chasing a weird runtime symptom, or before touching theming/splash/console/tile UI — the "what bit us" war stories. |
| `.Codex/skills/techdeck-plugin` | Authoring/modifying/debugging a plugin: plugin.json schema, `run()`, the SDK, GUI plugins, dev-testing, plugin Hard Rules + failure modes. Ships a scaffold. |
| `.Codex/skills/techdeck-release` | Version bump + PyInstaller/Inno build + test + local commit/tag + draft the manifest description. **LOCAL only — Codex never touches GitHub**; the user pushes, cuts the Release, and updates the manifest. |

**Skills load themselves** when a task matches their description; **docs you Read** when the
trigger above fires. Prefer both over re-deriving procedure.

---

## How To Run and Build

`python -m techdeck` from the project root — dev mode, no build required, the primary way
to test changes. Building the installer, version bumps, and the full release sequence →
the **`techdeck-release`** skill.

---

## Plugin System

A plugin is `plugins/<id>/` with `plugin.json` + `run.py`; entry is
`run(params, progress_callback, cancel_event)`; loads at runtime from
`%LOCALAPPDATA%\TechDeck\plugins\<id>\`; `family` is `902/911/922/QA/Games/other`; GUI plugins
need `requires_main_thread: true`. **Naming convention (2026-07, gate check E9):** the
folder/id = snake_case slug of the Library display name, family-prefixed — 902/911/922/QA
names start with their family ("911 Setup"→`911_setup`, "QA Gemba Analyzer"→
`qa_gemba_analyzer`), Games ids get a `game_` prefix, family-less ("other") plugins are
just the slug. Home AND Library tiles strip the family prefix from the name and show the
family badge instead; renaming an id needs a `_PLUGIN_ID_RENAMES` entry (settings.py) + an
installer `[InstallDelete]` line so user installs migrate. Everything else — schema, the
SDK helpers, console prompts, GUI plugins, dev-testing — is in the **`techdeck-plugin`**
skill.

---

## Hard Rules — Never Break These

Always-on guardrails. Code examples + rationale live in the `techdeck-plugin` /
`techdeck-release` skills.

1. **Look up Excel columns by header NAME, never a fixed index** (positions shift between
   files/batches). Use `sdk.find_header_col` / `sdk.header_map`.
2. **Scan for the header row; never hardcode its number.** Use `sdk.find_header_row`.
3. **Nest number regex `^(?:[PS]?\d{3,}|(?=[A-Z0-9]*\d)[A-Z0-9]{4,8})$`** (case-insensitive)
   to drop footer/total/junk rows. Covers legacy numeric nests AND alphanumeric IDs like
   `5CDAVW` (first seen GX030); the must-contain-a-digit rule is what rejects junk text.
4. **GUI plugins run on the main Qt thread** — `requires_main_thread: true`; never create
   QWidgets from a worker thread (crashes / `QBasicTimer` errors). Store the window in a
   module-level var or Qt GCs it.
5. **PyMuPDF (fitz) cannot save in place** — write a temp file then replace; use
   `sdk.save_pdf_atomic(doc, dest)`.
6. **`build.ps1` is ASCII only** — Unicode symbols break the PowerShell parser on some machines.
7. **Declare every asset dir in `TechDeck.spec` `datas`** or it's missing from the build.
8. **Anything only imported dynamically by plugins must be in `TechDeck.spec`
   `hiddenimports`** or the frozen exe ImportErrors despite working in dev. PyInstaller's
   static analysis can't see plugin imports (plugins load at runtime from `%LOCALAPPDATA%`),
   so this covers both third-party libs (openpyxl, pandas, fitz, pypdf, qrcode+submodules,
   PIL+submodules, `PySide6.QtCharts`) AND first-party modules the main app never imports —
   notably **`techdeck.core.plugin_sdk`** (only plugins import it; omitting it gives "cannot
   import name 'plugin_sdk' from 'techdeck.core'" and breaks every SDK-using plugin) and
   **`techdeck.core.plugin_window`** (only GUI plugins import it; omitting it broke
   Customer DXF Quoting in the v0.8.6 frozen build with "No module named
   'techdeck.core.plugin_window'"). Enforced automatically: `build.ps1` runs
   `tools/check_ship_readiness.py` and refuses to build on a miss
   (see `docs/PLUGIN_SHIP_REQUIREMENTS.md`).
9. **Subprocess env: set `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`** to avoid encoding crashes.
10. **Batch-number prompts MUST use `sdk.request_batch_number`; everything else uses
    `sdk.request_text`.** `request_batch_number` reads/writes the family-shared cache so
    same-family plugins in a multi-run reuse one answer — prompting for a batch via raw
    `console.request_input`/`input` silently skips the cache and the next plugin re-prompts
    (bit FormingFinder→Kitting, fixed v0.8.6.3). Conversely, using it for a non-batch prompt
    poisons that cache (bit `batch_auditor`). Enforced by `check_ship_readiness.py` E8.
11. **Poll `cancel_event` *inside* long file-system walks, not only between phases.**
    Cancellation is cooperative (the executor just sets the flag); a single `rglob`/`os.walk`
    over a OneDrive tree runs uninterruptibly, so a Cancel mid-walk is ignored until the
    walk ends — and the run never completes, so the spinner spins forever. Check every ~64
    iterations and bail (bit LST Organizer, FormSeeker, Batch Repeater; fixed v0.8.5.3).
12. **After editing a plugin, copy it to BOTH locations.** The running app — even in dev
    (`python -m techdeck`) — loads plugins from `%LOCALAPPDATA%\TechDeck\plugins\<id>\`,
    never from the repo `plugins/` tree (`PluginLoader()` always defaults there, no dev
    override). A repo-only edit silently runs the stale installed copy. So after editing
    `plugins/<id>/run.py` (or `plugin.json`), also `Copy-Item` it over
    `%LOCALAPPDATA%\TechDeck\plugins\<id>\` and delete that dir's `__pycache__` before
    testing — otherwise the fix "doesn't work" because it never ran (bit 922 Kitting).
13. **Reads of OneDrive-tree files must survive cloud-only placeholders.** On a
    Files-On-Demand sync a file can exist (globs/`.exists()` pass) while its CONTENT is
    cloud-only; if OneDrive can't download on demand, reads die — openpyxl/zipfile raise
    `OSError [Errno 22] Invalid argument` on a file that's plainly there (bit
    FormingFinder, Batch 481 PO, NRAPINI-LT) — **or the same failure disguised as
    `zipfile.BadZipFile: File is not a zip file`** (zipfile eats the OSError while
    seeking the central directory; bit 911 Setup, v0.8.6.5). Use `sdk.load_workbook_resilient` for
    workbooks and `sdk.ensure_local(path)` immediately before any other content read
    (fitz/PdfReader/pd.read_excel/shutil.copy source) — both hydrate + retry, or fail
    with user instructions. Applied across all apps in the post-0.8.6.1 sweep.

---

## Fix Protocol — Eradicate, Don't Patch

A diagnosed bug is a defect CLASS until proven otherwise. Before calling any fix done:
**(1)** grep the pattern across `plugins/`, `techdeck/`, and the SDK and fix every
occurrence — the reported site is rarely the only one (FormingFinder's OneDrive-placeholder
crash had ~25 siblings across 12 apps); **(2)** prefer centralizing the fix in
`plugin_sdk` so future call sites inherit it; **(3)** where mechanically checkable, encode
the class into `tools/check_ship_readiness.py` so it can never ship again; **(4)** record
it (Hard Rule / skill / `LESSONS_LEARNED.md`). Do this by default, without being asked.

---

## Installed Plugins

Roster only — deep per-plugin internals are in `docs/PLUGINS.md`.

| Plugin ID | Name | Family | Key Function |
|---|---|---|---|
| `902_dxf_prep` | 902 DXF Prep | 902 | Batch DXF cleanup/prep for Boost 902 part files (**first plugin in the new `902` family** — cyan badge/monogram): builds the IGES CONVERT folder + QTY sheet, renames/sorts exported DXFs for AutoCAD review, then recombines + reconciles against the PO spreadsheet (extras → EXTRA folder, missing parts listed, `(Nx)` qty prefixes) |
| `911_setup` | 911 Setup | 911 | Full 911 QTDR batch setup — nest folders, templates, forecast data, PDFs |
| `911_batch_repeater` | 911 Batch Repeater | 911 | Finds/copies repeat parts (NC + inspection PDFs) |
| `911_remove_ticket` | 911 Remove Ticket | 911 | Removes PART SKETCH pages from nest PDFs; saves "{stem} Move Ticket Omit.pdf" in a Move Ticket Omit subfolder |
| `911_po_pdf_extractor` | 911 PO PDF Extractor | 911 | Extracts PO data from PDFs to Excel |
| `911_sketch_extractor` | 911 Sketch Extractor | 911 | Extracts part sketch data, 17-column output, weight consolidation |
| `911_baked_beans_wild_ride` | 911 Baked Beans Wild Ride | 911 | Consolidates a folder of filled "NC style baked beans" calc workbooks (per-part DSTV/linear-inch pricing sheets from Vacam NC files) into one review list — DYPN, Batch, Nest, Total Bevels, Total Complex Bevels, Total Cut Lin (labels found by text, cached values only; uncalculated sheets flagged), sorted batch→nest→DYPN + live totals row — saved into that same folder as "{batch} {nest} NC Baked Beans.xlsx" (batch/nest read from each sheet's Batch/Nest cell; the folder is the only prompt). Process picker shows "Run NC Style Baked Beans spreadsheet" greyed out (future); RCT rider-thought console flavor; clickable "The ride never ends!" finale opens the bundled Mr Bones saga jpg |
| `911_sspo_invoicing_prep` | 911 SSPO Invoicing Prep | 911 | Splits an SSPO pricing sheet into one workbook per Batch+Nest ("BATCH NEST Pricing Back Up.xlsx"), built from scratch: split rows + Total-price-per-WO sum on tab 1, ASA Invoice Supplement (bundled `asa_logo.png`) on tab 2 — PO/PO Line from the Working Forecast List ('911 Forecast' → 'Complete 911 QTDR', matched on Batch+Nest, read via a temp copy that's deleted after; NEVER the live file), Price/Ea `=J/G`, Ext. Price live-links tab 1, dynamic Grand Total. Promoted from `one_off_apps/` |
| `911_runtime_estimator` | 911 Runtime Estimator | 911 | Prompts for a ROOT of order folders; reads each nest's NEST PACKAGES packet PDF + batch list, computes a thickness-band plate-cutting estimate, writes ONE workbook (Plates + Non-Plates sheets, each a data table + a **real** Excel PivotTable via COM: nest → Sum of Est Cut Hours + grand total) |
| `922_setup` | 922 Setup | 922 | Reads a batch's order folders (drops the Documentation + REPEAT BATCHES folders) and creates one Planner card per order ("BATCH X: {folder}") in the D922 PIPELINE plan via a Power Automate webhook; card layout in `card_template.json`, flow recipe in `docs/TEAMS_CARDS.md` |
| `922_pallet_stamper` | 922 Pallet Stamper | 922 | Stamps work-packet PDFs with batch/pallet info |
| `922_formingfinder` | 922 FormingFinder | 922 | Discovers formed plate PDFs (filename, PO NOTES, PDF spatial analysis); copies/merges them, populates the Bent Plates sheet in the Pallet & Rod Organizer |
| `922_kitting` | 922 Kitting | 922 | Formats/prints kitting paperwork for a 922 batch; color formatting, detects formed plates from Bent Plates sheet, merges all kit pages into one PDF |
| `922_lst_organizer` | 922 LST Organizer | 922 | Organizes .lst files by material type |
| `911_lst_organizer` | 911 LST Organizer | 911 | Pulls the .lst files for exactly the parts a nest's 1D cutting-pattern diagram lists (user picks the nest's PRODUCTION PAPERWORK folder; parts under "Parts Id.", foreign parts prefixed `{nest}-{part}`) into `PRODUCTION PAPERWORK\LST`; foreign nests resolved to their batch by filesystem lookup (never the PDF's cluster-prone header); unresolved nests / missing LSTs raise a blocking `sdk.show_warning` popup |
| `922_runtime_genie` | 922 Runtime Genie | 922 | Scans 7000 folders for CNC machine time PDFs, matches LST reference files, sums + outputs run time estimate with 40% buffer |
| `922_batch_repeater` | 922 Batch Repeater | 922 | Copies repeat orders from prior 922 batches |
| `qr_code_generator` | QR Code Generator | other | GUI plugin — dual-tab QR library + generator |
| `batch_auditor` | Batch Auditor | other | Read-only readiness check for a 911/922 batch (user picks line). Verifies orders/prints, LST, run time, forming, pallets, kitting; renders a dashboard (KPI cards + charts) + text summary. Uses the SDK. |
| `customer_dxf_quoting` | Customer DXF Quoting | other | GUI plugin — interactive DXF flat-pattern viewer for quoting: layer-colored geometry, per-line lengths, auto-apply layer reassignment (CUT/BEND_UP/BEND_DOWN/WELD/BOUNDING_BOX), total linear inches, DXF export of reassignments; BOUNDING_BOX/IGNORE never counted |
| `qa_gemba_analyzer` | QA Gemba Analyzer | QA | GUI plugin — QA rework logging + Gemba dashboard (**first plugin in the new `QA` family**; `magnifier` tile icon). Single charts window with "Log Rework" (modal entry form, closes on submit) + "Open Rework Log" (opens the xlsx in Excel) buttons. Appends one rework event per row to a single shared workbook (default = the Gemba folder in the ASA Quality Management System lib, discovered via `sdk.library_roots`; auto-created EMPTY — no seed data; lock-aware header-name-mapped append-retry; 8s mtime auto-refresh). Tracks MISSING MATERIAL? (Y/N) per event (feeds a future missing-materials email template). Renders QtCharts pie/column/stacked with toggles (time window, group-by category/detailed-mode/material/recut/missing-material, %-threshold, best-fit line, per-graph include/hide missing-material; controls grey out when N/A to the chart type) + a one-click "Gemba Pack" PDF. Stacked segments are name-labelled on the bar (no legend) via a `LabeledChartView.drawForeground` overlay. FAILURE MODE stays one "Category - Subcategory" cell, split on first " - ". QtCharts + QPdfWriter only (no matplotlib) |
| `game_asa_the_video_game` | ASA: The Video Game | Games | GUI incremental-strategy game (formerly id `steeltube_game`), v2: 16-bit Sweetie-16 pixel visuals + animated pixel banner, full Universal-Paperclips arc (Yard→Tech Team→A-Frames→Market→Drones→Space→Probes→universe converted; ending offers rest or a new universe at +25% legacy/run). **Purchasable** — `plugin.json` `"locked": true` hides it in the Library until `is_unlocked(id)`, bought with tickets at Woogy's Emporium. "Games" family (excluded from batch-number sharing). `.tdart` cartridge icon. Game widget in `widgets/steelbeams_game.py` (details in `docs/PLUGINS.md`) |

---

## Corporate Environment Notes

**File paths** — OneDrive-synced SharePoint, locally cached under:
`C:\Users\ASiebenmorgen\American Steel & Alum\Communication site - Electric Boat ASA Docs\Pilot Program\`
(base name varies per machine — `sdk.pilot_program_roots()` discovers all layouts; never hardcode it)

**IT restrictions** — no admin rights, no PATH modifications, can't install Python
system-wide. That's why TechDeck bundles its own Python via PyInstaller.

**Plugin distribution** — installed to `%LOCALAPPDATA%\TechDeck\plugins\` by the Inno
Setup installer. Users never touch Python files directly.

---

## Doc Governance — Keep This File Lean

AGENTS.md is loaded into context on **every** session, so its size is a permanent tax.
Detail that's only relevant to one subsystem doesn't belong here — it belongs in a doc that
loads on demand. This section is the system that keeps AGENTS.md from bloating back to 40k.

**Budget:** target **≤ ~250 lines / ~14k chars**. When an edit pushes past that, don't
trim words — **extract the heaviest topic section into the right `docs/` file and leave a
one-line pointer** in the Reference Docs Map.

**Where new info goes (route it, don't dump it here):**

| New info is… | Put it in… | AGENTS.md gets… |
|---|---|---|
| An always-on guardrail (must never be broken, applies broadly) | **Hard Rules** (here) | the rule itself |
| A plugin added/removed/renamed | roster table (here) + `docs/PLUGINS.md` | a table row |
| A plugin's internal behaviour detail | `docs/PLUGINS.md` | nothing |
| Shell/UI/theme/splash/tile/execution/console/dashboard design | `docs/ARCHITECTURE.md` | nothing (map already points there) |
| A console command or easter egg | `docs/CONSOLE_AND_EGGS.md` | nothing |
| A cross-cutting gotcha / "this bit us" fix | `LESSONS_LEARNED.md` | nothing |
| A plugin-authoring or build/release procedure | the matching **skill** | nothing |
| A whole new topic area worth its own doc | a new `docs/*.md` | a Reference Docs Map row |

**Maintain everything as living docs — automatically, without being asked.** When work
changes a workflow a skill covers, update that SKILL.md (and scaffold) the same session.
When it changes architecture/plugin/command detail, update the matching `docs/` file. The
full cross-doc sync procedure (README, the two Excel workbooks, etc.) is in
`docs/DOC_PROTOCOL.md`. Commit doc updates immediately (see Git Workflow).

---

## Git Workflow

Commit after every meaningful change — one logical change per commit, clear message (e.g.
"Fix 911 Setup nest regex to accept digits-only format"); don't batch unrelated changes,
so any point stays rollback-able. Commit AGENTS.md / docs updates immediately as
"Update docs - [brief description]".
