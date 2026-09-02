"""Authoritative AUTOMATION TOOLS + ROADMAP content for the Version Controller.

These two sheets are REBUILT from this file rather than upserted, because the
problems in them were not missing rows -- they were wrong ones. Five tools sat
under the wrong workflow heading (the two 911 extractors and the QR generator
were filed under 922; the 922 runtime tool was filed under 911), which is why
the 911 section looked thin, and four names had gone stale after renames. An
upsert cannot fix a row that is in the wrong section under an old name; it just
adds a second copy.

Sections and names here are checked against `plugins/*/plugin.json` by
`test_workbook_roster.py`, so a tool added or renamed in the app fails the test
until this file matches.
"""

# (section, [(tool, what it does, key automation, status, since version), ...])
TOOL_SECTIONS = [
 ("911 QTDR PRODUCTION PACKAGE WORKFLOW", [
  ("911 Setup",
   "Performs the full 911 QTDR batch setup: nest folders, templates, forecast "
   "data and production PDFs.",
   "Reads nest numbers from the batch list, builds each nest folder from the "
   "template set, files the production PDFs, and populates forecast data. "
   "Which steps run is chosen from a checklist that remembers each operator's "
   "selection between sessions, so a site that skips a step configures it "
   "once rather than every run.",
   "Active", "0.8.0"),
  ("911 Teams Cards",
   "Creates the coordination cards for every 911 order waiting to be modelled, "
   "and keeps the planning board's status column current.",
   "Reads the shared planning schedule for orders awaiting setup and posts one "
   "coordination card each, with difficulty and machine routing already set "
   "and the scheduled due date attached, then advances each order's status on "
   "the schedule as its card goes out. Needs no batch number and skips orders "
   "already carded, so it can be run at any time.",
   "Active", "0.8.7"),
  ("911 Batch Repeater",
   "Finds every repeat part in a 911 batch and copies its existing CAD work "
   "forward instead of remodelling it.",
   "Looks each nest's part numbers up in the 911 Master Parts List and copies "
   "the model, drawing and PDF from the completed source nest into the new "
   "one. Batch and nests are chosen through a guided multi-select picker.",
   "Active", "0.8.3"),
  ("911 Remove Ticket",
   "Removes part-sketch pages from nest PDFs and produces a clean set for the "
   "floor.",
   "Strips the sketch pages, writes a separate omitted-page set, and stamps "
   "the cover with the batch and nest plus the material type recovered from "
   "the removed pages.",
   "Active", "0.8.3"),
  ("911 PO PDF Extractor",
   "Extracts purchase-order data from 911 PDFs into a structured spreadsheet.",
   "Scans PDF text for the PO fields and builds a spreadsheet rather than "
   "requiring them to be read off and typed in.",
   "Active", "0.7.4"),
  ("911 Scripting Prep",
   "Builds the two-sheet SSPO ERP scripting workbook from a finished award "
   "review and the Working Forecast List.",
   "Reuses the award data a reviewer has already checked instead of "
   "re-reading the PO PDFs, and looks each source material's designation and "
   "size up in the forecast, so the scripting sheet is filled in rather than "
   "typed out line by line.",
   "Active", "0.8.7.3"),
  ("911 Sketch Extractor",
   "Extracts part-sketch data from 911 batch nests into a 17-column sheet.",
   "Scans the nest files, extracts the sketch data, and consolidates part "
   "weights across the batch.",
   "Active", "0.7.4"),
  ("911 LST Organizer",
   "Pulls the material listing files for exactly the parts a nest's cutting "
   "diagram calls for.",
   "Reads the part list off the nest's cutting-pattern diagram, resolves parts "
   "belonging to other nests back to their own batch by filesystem lookup, and "
   "raises a blocking warning for anything it cannot place.",
   "Active", "0.8.6.6"),
  ("911 Inspection Dimensions",
   "Reads the dimensions off each part drawing in a batch and fills them "
   "onto that part's inspection sheet.",
   "Reads the drawings themselves on the machine -- no outside service -- and "
   "types each part's dimensions into its inspection sheet, leaving out "
   "reference-only figures and stock notes, never overwriting a sheet already "
   "filled in by hand, and flagging any drawing it could not read.",
   "Pilot", "0.8.8"),
  ("911 Baked Beans Wild Ride",
   "Consolidates a folder of completed per-part pricing calculations into one "
   "review list.",
   "Reads each calculation sheet by field label rather than cell position, "
   "flags any sheet left uncalculated, and sorts the result by batch, nest and "
   "part with live totals.",
   "Active", "0.8.6.5"),
  ("911 SSPO Invoicing Prep",
   "Prepares invoicing back-up workbooks from an SSPO pricing sheet.",
   "Splits pricing rows into one workbook per batch and nest, each with a "
   "totalled invoice supplement built from scratch, PO details matched from "
   "the working forecast, and live-linked extended prices. Also writes the "
   "work-order close-out sheet.",
   "Active", "0.8.6.4"),
  ("911 SSPO Award Review",
   "Estimates plate-cutting hours for an award package before the batch is "
   "released.",
   "Bases the estimate on measured production throughput by material "
   "thickness rather than a theoretical feed rate, reads stock and thickness "
   "from the packet PDFs, and outputs a costing workbook with a pivot summary, "
   "a receiving length requirement sheet and a forecast input sheet.",
   "Active", "0.8.6"),
 ]),
 ("922 QTDR PALLET PACKAGE WORKFLOW", [
  ("922 Setup",
   "Runs the full 922 batch preparation sequence from one screen.",
   "Builds an order folder per order line with its revision sheet and work "
   "packet, generates the batch's coordination cards into ordered pipeline "
   "stages with pallet labelling, then runs stamping and repeat collection in "
   "the correct order. Stages are chosen up front and the batch folder is "
   "picked once.",
   "Active", "0.8.6.4"),
  ("922 Batch Repeater",
   "Copies repeat orders forward from prior 922 batches and maintains the "
   "parts catalog.",
   "Gathers each repeat order's existing work, tags and moves its coordination "
   "card automatically, and folds every order into a master parts catalog "
   "covering 166 historical batches.",
   "Active", "0.7.4"),
  ("922 Pallet Stamper",
   "Stamps PO and pallet label information onto every work packet in a batch.",
   "Iterates the work-order PDFs and overlays the PO and pallet detail so the "
   "floor paperwork is labelled without manual editing.",
   "Active", "0.7.4"),
  ("922 Difficulty Stamper",
   "Marks the work packets of orders containing a part that is difficult to "
   "produce.",
   "Reads every part drawing in a batch, identifies the parts the design "
   "automation system marked as requiring a compound cut, and stamps that "
   "marking onto the front page of the corresponding work packet so the "
   "difficulty is visible on the paperwork the floor works from rather than "
   "only on the individual part prints. Re-running after a part is revised "
   "corrects the packet in either direction, and the run reports which parts "
   "made each order difficult, which orders are not yet modelled, and any "
   "drawing it could not read.",
   "Active", "0.8.6.13"),
  ("922 FormingFinder",
   "Discovers and merges the formed-plate PDFs for a 922 batch.",
   "Identifies formed plates three ways -- filename, PO notes, and spatial "
   "analysis of the PDF itself -- then merges them and populates the bent "
   "plates sheet in the pallet organizer.",
   "Active", "0.8.5"),
  ("922 Kitting",
   "Formats and prints the kitting paperwork for a 922 batch.",
   "Applies the batch colour formatting, detects formed plates from the bent "
   "plates sheet, and merges every kit page into a single PDF for printing.",
   "Active", "0.8.5"),
  ("922 LST Organizer",
   "Collects and organizes the tube material listing files for a batch.",
   "Sorts the files into per-material folders and writes a colour-coded PDF "
   "reconciling the PO tube count against what was actually pulled, with "
   "unresolvable files routed to a review folder.",
   "Active", "0.8.4"),
  ("922 Runtime Genie",
   "Estimates total CNC machine run time for a 922 batch.",
   "Scans the machining folders for machine-time PDFs, matches them to the "
   "material listing files, and sums the result with a buffer applied.",
   "Active", "0.8.4"),
 ]),
 ("902 QTDR PRODUCTION PACKAGE WORKFLOW", [
  ("902 DXF Prep",
   "Prepares and verifies a 902 batch of DXF part files for production.",
   "Builds the conversion working folder and quantity sheet, renames and "
   "sorts the exported files for review, then recombines and reconciles them "
   "against the PO spreadsheet -- extras separated, missing parts listed, "
   "quantities prefixed.",
   "Active", "0.8.6.4"),
 ]),
 ("QUALITY, ESTIMATING & SHOP TOOLS", [
  ("QA Gemba Analyzer",
   "Logs rework events to a shared workbook and charts them for Gemba review.",
   "One-form event capture including a missing-material flag, appending to a "
   "shared workbook with lock-aware retry, plus a charted dashboard with "
   "time-window and grouping controls and a one-click review pack.",
   "Active", "0.8.6.4"),
  ("Batch Auditor",
   "Read-only readiness check for a 911 or 922 batch before it is released.",
   "Verifies orders, prints, material listings, run time, forming, pallets and "
   "kitting, then renders a dashboard and written summary. Changes nothing.",
   "Active", "0.8.5.5"),
  ("Customer DXF Analysis",
   "Interactive DXF viewer for quoting customer-supplied parts, with "
   "automated guideline offsets applied per plate thickness.",
   "Layer-coloured geometry with per-line measurements and total linear "
   "inches; thickness-banded hole and cutout offsets with cap and minimum "
   "warnings; saves over the original or exports a copy.",
   "Active", "0.8.6"),
  ("Sheet Metal Calculators",
   "A library of shop calculators -- flat length, bend deduction, material "
   "weight -- behind one picker.",
   "Driven by a declarative registry: each calculator is a field list plus a "
   "formula, so adding one is a single data entry with no interface work. "
   "Native forms with per-input validation.",
   "Active", "0.8.6.9"),
  ("QR Code Generator",
   "Generates QR codes that embed links or images for shop-floor labelling.",
   "Dual-tab interface -- a saved code library alongside the generator.",
   "Active", "0.7.4"),
 ]),
]

# ---- ROADMAP, audited against what actually shipped ------------------------
# Two problems this fixes. First, "Automated 922 Coordination Cards" sat at
# Planned months after it shipped, because nothing moved a roadmap row when the
# work landed. Second, the sheet only ever held 922 and platform items, so the
# entire 911 programme -- the larger half of the work -- was invisible on the
# one sheet a reader turns to for direction.
#
# Delivered items STAY on the sheet with their phase moved rather than being
# deleted. A roadmap that shows only what is outstanding hides the fact that it
# is being worked through, which is most of what a reader wants from it.
ROADMAP_ROWS = [
    # ---- 911 ---------------------------------------------------------------
    ("High", "911 Batch Setup Automation",
     "Build an entire 911 QTDR batch package in one run -- nest folders, "
     "templates, forecast data and production PDFs -- from the batch list.",
     "911", "Delivered"),
    ("High", "911 Master Parts List",
     "A compiled parts list across historical 911 batches so repeat parts are "
     "identified automatically and their existing CAD work is reused instead "
     "of being modelled a second time.",
     "911", "Delivered"),
    ("High", "Throughput-Based Cut Estimating",
     "Replace theoretical feed-rate estimating with measured production "
     "throughput by material thickness, derived from 18 months of closed work "
     "orders, so award pricing reflects what the shop actually achieves.",
     "911", "Delivered"),
    ("High", "911 Award Review Package",
     "Turn an award package into a single costed workbook -- estimated cut "
     "hours, a summary by nest, receiving length requirements, and a sheet "
     "that pastes straight into the working forecast.",
     "911", "Delivered"),
    ("Medium", "911 Invoicing Back-Up Automation",
     "Split an SSPO pricing sheet into per-batch, per-nest invoicing back-up "
     "workbooks with the invoice supplement and work-order close-outs built.",
     "911", "Delivered"),
    ("Medium", "Automated 911 Coordination Cards",
     "Create the 911 modelling-stage cards straight from the production "
     "schedule, with difficulty and machine routing applied automatically.",
     "911", "Delivered"),
    ("Medium", "911 Material Listing Reconciliation",
     "Pull exactly the material listing files a nest's cutting diagram calls "
     "for, including parts belonging to other nests, and flag what is missing.",
     "911", "Delivered"),
    ("Medium", "911 Pricing Consolidation",
     "Merge a batch's per-part pricing calculations into one review list, "
     "flagging any sheet left uncalculated.",
     "911", "Delivered"),
    # ---- 922 ---------------------------------------------------------------
    ("High", "922 Batch Preparation Consolidation",
     "Run the whole 922 preparation sequence -- folder build, coordination "
     "cards, pallet stamping, repeat collection -- as one guided pass with a "
     "single batch selection.",
     "922", "Delivered"),
    ("High", "922 Master Parts Catalog",
     "Per-piece catalog built from 166 historical batches and maintained "
     "automatically on every repeater run, covering repeat counts, batch "
     "history and alternate part numbers.",
     "922", "Delivered"),
    ("Medium", "Automated 922 Coordination Cards",
     "Create and populate the batch coordination cards for a 922 batch, "
     "sorted into ordered pipeline stages with pallet labelling, and re-tag "
     "repeat orders automatically.",
     "922", "Delivered"),
    ("Medium", "Formed-Plate Discovery",
     "Identify formed plates three independent ways and merge their prints, "
     "instead of finding them by eye during kitting.",
     "922", "Delivered"),
    ("Medium", "Automated Kitting Paperwork",
     "Format, colour-code and merge an entire batch's kitting paperwork into "
     "one print-ready document.",
     "922", "Delivered"),
    ("High", "922 PO Builder",
     "Automate full 922 PO structure creation from the source order data.",
     "922", "Planned"),
    ("Medium", "Automated 922 Rod Tags",
     "Fill the rod tag sheet and generate the printable PDF.",
     "922", "Planned"),
    ("Medium", "922 Quote Builder",
     "Autofill the 922 quote sheet from batch data.",
     "922", "Planned"),
    # ---- 902 and cross-workflow -------------------------------------------
    ("Medium", "902 Workflow Coverage",
     "Bring the 902 production package onto the platform, starting with DXF "
     "preparation and PO reconciliation.",
     "902", "Delivered"),
    ("Medium", "Quality Rework Tracking",
     "Capture rework events at the point they happen and chart them for Gemba "
     "review, replacing after-the-fact recollection.",
     "Quality", "Delivered"),
    ("Medium", "Pre-Release Batch Readiness Check",
     "A read-only check that verifies a batch is complete -- orders, prints, "
     "material, run time, forming, pallets, kitting -- before it is released.",
     "Quality", "Delivered"),
    ("Medium", "Customer Quoting Offsets",
     "Apply customer guideline offsets to quoted DXF geometry automatically "
     "by plate thickness, with cap and minimum warnings.",
     "Quality", "Delivered"),
    # ---- Platform ----------------------------------------------------------
    ("High", "Colour Palette Options",
     "User-selectable and custom-built colour themes.",
     "Platform", "Delivered"),
    ("Medium", "Automated Regression Testing",
     "An automated test suite run on every change, so defects are caught "
     "before they reach an operator.",
     "Platform", "Delivered"),
    ("Medium", "Usage Telemetry & Feedback Delivery",
     "Deliver anonymous usage counts and in-app feedback to the development "
     "team automatically, so effort is aimed at the tools actually in use.",
     "Platform", "Delivered"),
    ("Medium", "Live SharePoint Data (Graph API)",
     "Read forecast and batch data directly from SharePoint rather than the "
     "locally synced copy, removing the dependency on a machine's sync state.",
     "Platform", "Research"),
    ("Medium", "Operator Presence & Nudges",
     "Show which colleagues are in the platform and allow a lightweight nudge, "
     "so a batch hand-off does not need a separate message.",
     "Platform", "Research"),
    ("Low", "Code Signing Certificate",
     "Sign the executable and installer so Windows Smart App Control stops "
     "blocking first run on clean machines.",
     "Platform", "Planned"),
    ("Low", "OneDrive File Exchange",
     "Explore OneDrive API access for direct file exchange.",
     "Platform", "Research"),
    ("Low", "Email Access Tool",
     "Tool to access and manage work email from inside the platform.",
     "Platform", "Backlog"),
]
