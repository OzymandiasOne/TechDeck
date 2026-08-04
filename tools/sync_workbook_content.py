"""Content for the tracking workbooks — the words, kept apart from the writer.

TONE RULE. Everything the platform does gets logged, INCLUDING the engagement
features, but the Version Controller is read outside the team, so it never uses
in-house or playful names. Nothing here is invented or overstated; the same
feature is simply described by what it DOES:

    activity credits / rewards catalog ... Recognition & Rewards Economy
    fidget spinners, collectible items ... Desktop Widgets
    personal room / garden .............. Workspace Personalization
    achievements ....................... Milestone Recognition
    client-demo theme .................. Presentation Mode
    targeting-overlay folder picker .... Guided File Selection
    in-app games and easter eggs ....... Engagement Features
"""

# ---- Version Controller :: SYSTEM FEATURES  (name, what, value, status) -----
SYSTEM_FEATURES = [
    ("Recognition & Rewards Economy",
     "Activity credits accrue as operators run automation tools and submit "
     "feedback, and are redeemed in an in-app rewards catalog.",
     "Gives day-to-day tool use visible payback, increasing adoption of new "
     "automation and the volume of feedback reaching the development team.",
     "Active"),
    ("Milestone Recognition",
     "Tracks usage milestones per operator (tools run, batches completed, "
     "feedback submitted) and awards credits when one is reached.",
     "Surfaces how much manual work the platform has absorbed, and recognises "
     "the operators who rely on it most.",
     "Active"),
    ("Desktop Widgets",
     "Optional always-on-top desk widgets earned through use. Each is "
     "assembled from three independently swappable art layers, so operators "
     "can build their own combinations.",
     "A low-cost personalisation reward that gives the credit economy "
     "something to spend on without touching production workflows.",
     "Active"),
    ("Workspace Personalization",
     "A personal space each operator furnishes with items earned through use, "
     "plus selectable backdrops and companions.",
     "Long-run engagement that keeps the platform in daily use rather than "
     "opened only when a batch is due.",
     "Active"),
    ("Presentation Mode",
     "A dedicated light theme that hides every engagement feature -- credits, "
     "rewards, widgets and personalisation -- leaving only automation tools.",
     "The application can be shown to customers, auditors or management with "
     "no informal content visible.",
     "Active"),
    ("Guided File Selection",
     "An optional targeting overlay replaces the plain Windows folder dialog "
     "for tools that ask for a batch folder, enabled per tool.",
     "Makes the most error-prone step in several workflows -- choosing the "
     "right batch folder -- deliberate and hard to get wrong.",
     "Active"),
    ("Command Console",
     "A built-in console accepting slash-commands for diagnostics, session "
     "control and platform utilities.",
     "Support and power users can drive the platform and gather diagnostics "
     "without a rebuild or a developer present.",
     "Active"),
    ("Audio Feedback",
     "Sound cues on run start, completion, failure and input prompts.",
     "An operator can start a long batch job and step away, and still know "
     "when it finishes or needs an answer.",
     "Active"),
    ("Multi-Tool Run Control",
     "Several tools can be queued in one run, reordered by drag, and paused, "
     "resumed or shelved mid-sequence. Same-family tools share prompt answers, "
     "so a batch number is entered once.",
     "A full batch package is prepared in a single pass instead of running "
     "each tool by hand and re-entering the same details.",
     "Active"),
    ("Per-Run Output Log",
     "Every run's complete output is persisted and reviewable afterwards.",
     "A run can be audited or diagnosed days later without reproducing it.",
     "Active"),
    ("Usage Telemetry & Feedback Delivery",
     "Anonymous usage counts and in-app feedback are spooled locally and "
     "delivered automatically to the development team.",
     "Development effort is aimed at the tools operators actually use, and "
     "problems are heard without anyone filing a ticket.",
     "Active"),
    ("Coordination Card Delivery",
     "Tools post batch coordination cards straight into the team's planning "
     "boards, sorted into the correct pipeline stage with labels for "
     "difficulty, machine routing and pallet, and re-tag repeat orders.",
     "Batch coordination is set up from the batch data itself rather than "
     "typed in one card at a time, and it cannot drift out of step with the "
     "folders the operators actually work from.",
     "Active"),
    ("Historical Parts Catalogs",
     "Compiled parts catalogs covering every past 911 and 922 batch, "
     "maintained automatically as new batches run.",
     "Repeat work is found automatically and its existing engineering reused, "
     "which is the single largest source of avoided effort on the platform.",
     "Active"),
    ("Diagnostic Snapshot",
     "One click captures a full diagnostic report -- versions, settings, "
     "environment, recent errors -- for support.",
     "Reduces a problem report from a back-and-forth to a single attachment.",
     "Active"),
]

# ---- ENGINEERING & RELIABILITY  (date, initiative, cat, what, value, scope) --
ENGINEERING = [
    ("Jun 2026", "Pre-Ship Verification Gate", "Quality",
     "Added an automated readiness check that runs before any build and "
     "refuses to package if a tool would ship broken -- missing dependencies, "
     "unregistered modules or malformed configuration.",
     "A tool that would fail on an operator machine cannot be released.",
     "Enforced on every build; covers every deployed tool."),
    ("Jul 2026", "Continuous Integration", "Testing",
     "The full test suite now runs automatically on every code change, not "
     "only ahead of a release.",
     "Regressions surface within minutes of being introduced rather than "
     "during a release.",
     "Platform-wide; automated on every push."),
    ("Jul 2026", "Visual Asset Standards", "Tooling",
     "Documented a measured house style for the platform custom artwork and "
     "built an automated checker that enforces it.",
     "Interface artwork stays visually consistent as it grows, without "
     "reviewing every asset by eye.",
     "Applied across the full icon and sprite set."),
    ("Jun 2026", "Shared Prompt Memory", "Usability",
     "Tools belonging to the same workflow now share their prompt answers "
     "within a run, so a batch number entered for the first tool is reused by "
     "every tool after it, and the ship-readiness gate fails any tool that "
     "asks for a batch number outside that shared path.",
     "A full batch package is prepared without re-entering the same details at "
     "each stage, and the class of bug that caused the re-prompting cannot "
     "return.",
     "All 911 and 922 tools; enforced by the pre-ship gate."),
    ("Jul 2026", "Historical Data Compilation", "Data",
     "Compiled per-piece parts catalogs from the full history of completed "
     "batches -- 166 historical 922 revision packages and the equivalent 911 "
     "batch record -- and wired their upkeep into the tools that run each "
     "batch, so the catalogs stay current without a maintenance step.",
     "Repeat parts are identified against the real production record rather "
     "than recollection, which is what makes reusing prior engineering "
     "dependable enough to rely on.",
     "19,676 catalogued part rows across the 911 and 922 workflows."),
    ("Jul 2026", "Measured Estimating Baseline", "Data",
     "Derived cutting throughput by material thickness from 18.5 months of "
     "closed work orders and replaced the theoretical feed-rate model with it, "
     "keeping the geometric calculation alongside as a reference column.",
     "Award estimates are based on what the shop actually produces, including "
     "setup and handling, instead of an idealised cutting rate.",
     "911 award review; both models retained for comparison."),
    ("Jul 2026", "Private-by-Default Publishing", "Security",
     "Split the codebase's development history from what is published: the "
     "public copy is rebuilt through a filter that strips internal notes, "
     "working documents and development tooling, and replaces colleagues' "
     "names and personal file paths with initials across every commit rather "
     "than only the latest.",
     "The platform's source can be shared or open-sourced without exposing "
     "internal documentation or naming any colleague who did not choose to be "
     "named.",
     "Whole published history; enforced before every publish."),
    ("Aug 2026", "Publishing Scrub Verification", "Security",
     "Replaced the hand-maintained scrub list with an automated gate. The list "
     "could only redact names someone had already thought of; scanning the "
     "filtered history instead found a colleague's home directory in a code "
     "comment that would otherwise have been published. The gate now scans "
     "every commit's content, message and author identity across all branches "
     "and blocks the publish on anything not explicitly allowed. Integration "
     "endpoint URLs and their signature tokens are scrubbed by the same pass.",
     "Personal data and working credentials cannot reach a public repository "
     "through an old commit, which is the failure a review of the current "
     "files would never catch.",
     "All commits, all branches; blocking gate on the publish step."),
    ("Aug 2026", "Record-Keeping Automation", "Process",
     "Turned maintenance of the platform's tracking workbooks into a scripted, "
     "idempotent step with the content held in version control, after the "
     "manual end-of-session update proved to be the step that got skipped.",
     "The published record of the platform stays current and consistent "
     "without depending on anyone remembering to update it.",
     "Both tracking workbooks; roster verified against the live tool set."),
    ("Aug 2026", "Composable Asset System", "Tooling",
     "Rebuilt widget artwork so each item is three independent layers composed "
     "at display time rather than one flattened image, with automated checks "
     "on the properties that keep the layers interchangeable.",
     "Operators can mix parts into their own combinations, and one authored "
     "part is reused across many items instead of redrawing each whole.",
     "Widget asset pipeline; 21 layer files across 7 items."),
    ("Aug 2026", "Interface Text Fitting", "Quality",
     "Fixed a long-standing defect where any catalog name longer than about "
     "eight characters was silently clipped at both ends, and added a "
     "regression test asserting every name fits its label.",
     "Thirteen items had been displaying truncated names to operators.",
     "Shared text renderer; all catalog surfaces."),
]

# AUTOMATION TOOLS and ROADMAP are NOT upserted from here -- they are rebuilt
# wholesale from `sync_workbook_tools.py`. Upserting them was the reason both
# drifted: an upsert can add a row, but it cannot move one out of the wrong
# workflow section, rename one in place, or move a shipped item off "Planned".

# ---- VERSION HISTORY :: re-key on release (old key -> new key) --------------
# A row logged while its work was unreleased is keyed "In Development"; cutting
# the release turns that key into the version number. Applied BEFORE the upsert
# so the row is updated in place rather than duplicated.
VERSION_RENAMES = {
    "In Development": "0.8.6.11",
}

# ---- VERSION HISTORY  (version, date, type, deliverables, tools) ------------
VERSION_ROWS = [
    ("0.8.6.11", "Aug 2026", "Feature",
     "Task-card creation for the 911 pipeline is now automated: setup reads the "
     "master schedule and raises one card per job awaiting modeling, carrying "
     "the job's difficulty rating and machine routing, which removes a manual "
     "card-entry step from every batch and keeps the board consistent with the "
     "schedule. Difficulty is also recorded on the printed cover sheets, and "
     "each setup run closes with a handoff checklist. Batch preparation "
     "ordering was corrected so repeat orders are no longer stamped for the "
     "wrong batch; quoting gained automatic application of customer geometry "
     "guidelines; and a source-data defect that could silently truncate "
     "quantity output was fixed. Diagnostic capture added for unexpected "
     "stoppages, so a report sent after a restart still explains the original "
     "fault. Engagement and personalisation layer expanded: the rewards "
     "catalog gains a desktop widget line built on a new composable "
     "three-layer asset system, with an in-app builder for operators to "
     "assemble their own combinations. Several long-standing interface "
     "defects fixed alongside it, including truncated catalog names and "
     "clipped widget display.",
     "911 Setup, 922 Setup, 902 DXF Prep, Customer DXF Analysis, Desktop "
     "Widgets (new line), Widget Builder (new), Sheet Metal Calculators, "
     "interface text fitting, widget display and sizing fixes"),
]

# ---- Wording fixes in EXISTING Version Controller prose --------------------
# Rows written before the tone rule that still use the in-house currency name.
# (Left alone: "911 Remove Ticket", "move ticket PDFs" and "IT tickets" -- those
# are real tool names and manufacturing documents, not the reward currency.)
#
# The second group is the tool renames. VERSION HISTORY is a HISTORICAL record,
# so the name a tool shipped under stays -- but a reader comparing it against
# AUTOMATION TOOLS cannot tell that "922 FormSeeker" and "922 FormingFinder"
# are one tool, so the current name is appended once where the old one appears.
PROSE_FIXES = [
    ("VERSION HISTORY",
     "credits recognition tickets for each stage completed",
     "awards activity credits for each stage completed"),
    ("VERSION HISTORY", "922 FormSeeker (NEW)",
     "922 FormSeeker (NEW; now 922 FormingFinder)"),
    ("VERSION HISTORY", "LST Organizer, PO Packet Extractor, Part Sketch "
     "Extractor, QR Code Generator",
     "LST Organizer (now 922 LST Organizer), PO Packet Extractor (now 911 PO "
     "PDF Extractor), Part Sketch Extractor (now 911 Sketch Extractor), QR "
     "Code Generator"),
    ("VERSION HISTORY", "Run Time Estimator, LST Organizer v2.0",
     "Run Time Estimator (now 922 Runtime Genie), LST Organizer v2.0 (now 922 "
     "LST Organizer)"),
    ("VERSION HISTORY", "Customer DXF Quoting (weld measurement",
     "Customer DXF Quoting (now Customer DXF Analysis; weld measurement"),
]

# ---- Process Improvement log :: entries to RENAME (old -> new, desc) --------
# The internal log keeps every entry, but the in-house names are replaced so
# the two workbooks describe the same platform in the same language.
PI_RENAMES = {
    "TICKET ECONOMY + WOOGYS EMPORIUM": (
        "RECOGNITION & REWARDS ECONOMY",
        "ACTIVITY CREDITS EARNED PER TOOL RUN AND PER FEEDBACK SUBMISSION, "
        "REDEEMED IN AN IN-APP REWARDS CATALOG WITH PURCHASE AND EQUIP FLOW"),
    "MY HOUSE / GARDEN TAB": (
        "WORKSPACE PERSONALIZATION",
        "A PERSONAL SPACE EACH OPERATOR FURNISHES WITH ITEMS EARNED THROUGH "
        "USE; SELECTABLE BACKDROPS, PLACED FURNISHINGS AND COMPANIONS"),
    "ACHIEVEMENTS PAGE": (
        "MILESTONE RECOGNITION",
        "USAGE MILESTONES PER OPERATOR (TOOLS RUN, BATCHES COMPLETED, "
        "FEEDBACK GIVEN) WITH CREDIT AWARDS ON COMPLETION"),
    "PIXEL-ART FIDGET SPINNER": (
        "DESKTOP WIDGET FRAMEWORK",
        "ALWAYS-ON-TOP DESK WIDGET RENDERED FROM HAND-EDITABLE ART WITH "
        "ROTATIONAL PHYSICS; THE BASIS FOR THE EARNABLE WIDGET LINE"),
    "STEEL BEAMS GAME": (
        "ENGAGEMENT MODULE",
        "OPTIONAL IN-APP ENGAGEMENT MODULE UNLOCKED THROUGH THE REWARDS "
        "CATALOG; HIDDEN ENTIRELY IN PRESENTATION MODE"),
    "ASA GAME EVENT SYSTEM": (
        "ENGAGEMENT MODULE CONTENT SYSTEM",
        "EVENT AND PROGRESSION SYSTEM FOR THE ENGAGEMENT MODULE: 112 EVENTS "
        "ACROSS ALL STAGES, FIVE OUTCOME PATHS, FULL SCENE ART SET"),
    "CHOPPER GUNNER FOLDER PICKER": (
        "GUIDED FILE SELECTION",
        "TARGETING-OVERLAY REPLACEMENT FOR THE PLAIN WINDOWS FOLDER DIALOG ON "
        "BATCH-FOLDER PROMPTS; FALLS BACK TO THE NATIVE DIALOG ON ANY FAILURE"),
    "SENTRY DRONE GADGET": (
        "GUIDED FILE SELECTION - PER-TOOL OPT-IN",
        "GUIDED FILE SELECTION TURNED INTO A CATALOG ITEM WITH A SETUP SCREEN "
        "CHOOSING WHICH TOOLS USE IT FOR THEIR FILE AND FOLDER PROMPTS"),
    "MUSASHI MOTH MUSINGS": (
        "IN-APP COMPANION MESSAGING",
        "ROTATING FIRST-PERSON COMPANION MESSAGES SHOWN ALONGSIDE LONG RUNS"),
    "ROGUE MODE PLAYER": (
        "FLOATING AUDIO PLAYER",
        "DETACHED ALWAYS-ON-TOP AUDIO PLAYER LAUNCHED FROM THE COMMAND CONSOLE"),
    "UI PERSONALITY SYSTEM": (
        "CONTEXTUAL STATUS MESSAGING",
        "PER-TOOL DISPLAY NAMES AND CONTEXTUAL PROGRESS COMMENTARY DURING RUNS"),
}

# ---- Process Improvement log :: NEW entries (task, state, description) ------
PI_NEW = [
    ("DESKTOP WIDGET LINE", "COMPLETE",
     "SEVEN EARNABLE DESK WIDGETS ADDED TO THE REWARDS CATALOG, EACH BUILT "
     "FROM THREE INDEPENDENTLY SWAPPABLE ART LAYERS"),
    ("COMPOSABLE ASSET SYSTEM", "COMPLETE",
     "WIDGET ART REBUILT AS THREE SEPARATE LAYERS COMPOSED AT DISPLAY TIME "
     "INSTEAD OF ONE FLATTENED IMAGE; PALETTE MERGING RESOLVES COLLISIONS SO "
     "LAYERS FROM DIFFERENT ITEMS COMBINE WITHOUT RECOLOURING EACH OTHER"),
    ("WIDGET BUILDER", "COMPLETE",
     "IN-APP SCREEN TO ASSEMBLE A WIDGET FROM OWNED PARTS WITH A LIVE PREVIEW; "
     "OFFERS ONLY OWNED DESIGNS AND SNAPS AN UNOWNED SAVED COMBINATION BACK TO "
     "SOMETHING THE OPERATOR HAS"),
    ("PIXEL EDITOR LAYER SYSTEM", "COMPLETE",
     "LAYER STACK ADDED TO THE ART EDITOR AND STUDIO: OVERLAPPING EDIT ON ONE "
     "CANVAS, PER-LAYER VISIBILITY, OPACITY, DRAG REORDER, AND SAVE-ALL "
     "WRITING EACH LAYER BACK TO ITS OWN FILE"),
    ("INTERFACE TEXT FITTING", "COMPLETE",
     "FIXED CATALOG NAMES LONGER THAN ~8 CHARACTERS BEING CLIPPED AT BOTH "
     "ENDS (13 ITEMS AFFECTED); TEXT NOW WRAPS OR SCALES TO FIT AND A "
     "REGRESSION TEST ASSERTS EVERY NAME FITS"),
    ("WIDGET DISPLAY FIXES", "COMPLETE",
     "WIDGET WINDOW NOW SIZED FROM THE ART REACH RATHER THAN ITS BOUNDING BOX "
     "SO ROTATION NO LONGER CLIPS THE CORNERS; DISPLAY SIZE REDUCED; TOP SPEED "
     "DERIVED FROM EACH DESIGN ROTATIONAL SYMMETRY TO AVOID STROBING"),
    ("SHEET METAL CALCULATORS", "COMPLETE",
     "GUI PLUGIN HOSTING A LIBRARY OF SHOP CALCULATORS BEHIND ONE PICKER, "
     "DRIVEN BY A DECLARATIVE REGISTRY"),
    # {tests} is filled from a live pytest collection, not remembered -- see
    # test_count() in the writer. Any row here may use it.
    ("CONTINUOUS INTEGRATION", "COMPLETE",
     "FULL TEST SUITE RUNS AUTOMATICALLY ON EVERY CODE CHANGE, NOT ONLY BEFORE "
     "A RELEASE; SUITE GROWN FROM 69 TO {tests} TESTS"),
    ("TRACKING WORKBOOK AUDIT", "COMPLETE",
     "FULL AUDIT OF THE PRESENTED RECORD AGAINST THE LIVE TOOL SET: FIVE TOOLS "
     "WERE FILED UNDER THE WRONG WORKFLOW SECTION, FOUR WERE LISTED UNDER NAMES "
     "THEY HAD BEEN RENAMED AWAY FROM, AND SHIPPED ROADMAP ITEMS WERE STILL "
     "MARKED PLANNED; TOOL AND ROADMAP SHEETS NOW REBUILT FROM VERSION CONTROL"),
    ("ROADMAP 911 COVERAGE", "COMPLETE",
     "THE ROADMAP SHEET HELD ONLY 922 AND PLATFORM ITEMS, LEAVING THE ENTIRE "
     "911 PROGRAMME INVISIBLE; NOW COVERS ALL FIVE WORKFLOWS WITH DELIVERED "
     "ITEMS RETAINED AND PHASED RATHER THAN DROPPED"),
    ("RECORD ROSTER GUARD", "COMPLETE",
     "AUTOMATED TEST CROSS-CHECKS THE PRESENTED TOOL ROSTER AGAINST THE ACTUAL "
     "PLUGIN SET -- FAILS ON A MISSING, INVENTED, RENAMED OR MISFILED TOOL, AND "
     "ON ANY IN-HOUSE TERM REACHING THE EXTERNALLY-READ WORKBOOK"),
    ("WORKBOOK FORMATTING PASS", "COMPLETE",
     "ONE VISUAL VOCABULARY APPLIED ACROSS ALL SIX SHEETS -- TITLE, SECTION, "
     "HEADER AND BANDED DATA STYLES, COLUMN WIDTHS SIZED TO THE PROSE, AND "
     "FROZEN HEADER PANES"),

    # ---- source control and publishing process -----------------------------
    ("SOURCE CONTROL - PUBLISHING SPLIT", "COMPLETE",
     "DEVELOPMENT HISTORY KEPT PRIVATE; THE PUBLIC REPOSITORY RECEIVES A "
     "FILTERED COPY REBUILT FROM IT. INTERNAL NOTES, WORKING DOCS, DEVELOPMENT "
     "TOOLING AND ONE-OFF APPS ARE STRIPPED FROM EVERY COMMIT, NOT JUST THE "
     "LATEST -- A FIX AT THE TIP DOES NOTHING FOR WHAT A MIRROR PUBLISHES"),
    ("PUBLISHING - PERSONAL DATA SCRUB", "COMPLETE",
     "COWORKER NAMES AND PERSONAL FILE PATHS ARE REPLACED WITH INITIALS ACROSS "
     "THE WHOLE PUBLISHED HISTORY BEFORE ANYTHING LEAVES THE BUILDING; NOBODY "
     "IS NAMED IN THE PUBLIC REPOSITORY WITHOUT CHOOSING TO BE"),
    ("PUBLISHING - AUTOMATED SCRUB GATE", "COMPLETE",
     "THE SCRUB LIST WAS A HAND-MAINTAINED SET OF NAMES SOMEONE HAD THOUGHT "
     "OF, SO IT COULD ONLY CATCH WHAT WAS ALREADY KNOWN. AN ACTUAL SCAN OF THE "
     "FILTERED HISTORY FOUND A COWORKER HOME DIRECTORY IN A CODE COMMENT THAT "
     "WOULD OTHERWISE HAVE SHIPPED. TOOLS/CHECK_PUBLISH_SCRUB.PY NOW SCANS "
     "EVERY COMMIT'S CONTENT, MESSAGE AND AUTHOR IDENTITY ACROSS ALL BRANCHES "
     "AND BLOCKS THE PUBLISH ON ANYTHING NOT EXPLICITLY ALLOWED"),
    ("PUBLISHING - CREDENTIAL SCRUB", "COMPLETE",
     "INTEGRATION ENDPOINT URLS AND THEIR SIGNATURE TOKENS ARE STRIPPED FROM "
     "THE PUBLISHED HISTORY, SO A WORKING SECRET CANNOT REACH A PUBLIC "
     "REPOSITORY BY WAY OF AN OLD COMMIT"),
    ("PUBLISHING - TAG SCOPE CONTROL", "COMPLETE",
     "RELEASE TAGS ARE NO LONGER PUSHED WHOLESALE: MOST POINT AT COMMITS "
     "OUTSIDE THE PUBLISHED BRANCH, AND PUSHING THEM WOULD HAVE DRAGGED "
     "UNPUBLISHED HISTORY INTO THE PUBLIC REPOSITORY BEHIND THE FILTER"),
    ("CONTINUOUS INTEGRATION - HOSTED RUNNERS", "COMPLETE",
     "TEST SUITE AND PRE-SHIP READINESS CHECK RUN ON HOSTED WINDOWS RUNNERS "
     "FOR EVERY PUSH, SO A REGRESSION IS CAUGHT ON A CLEAN MACHINE RATHER THAN "
     "ONLY ON THE DEVELOPER'S"),
    ("RELEASE DISTRIBUTION PIPELINE", "COMPLETE",
     "RELEASES ARE PUBLISHED AS VERSIONED DOWNLOADS WITH THE INSTALLER "
     "ATTACHED, AND THE IN-APP UPDATER READS A SEPARATE PUBLISHED MANIFEST; "
     "UPDATING THE MANIFEST IS THE DELIBERATE GO-LIVE STEP, SO A BUILD CAN BE "
     "PUBLISHED AND VERIFIED BEFORE ANY OPERATOR IS OFFERED IT"),
]
