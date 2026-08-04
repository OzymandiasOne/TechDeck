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

# ---- AUTOMATION TOOLS :: renames applied BEFORE the upsert -----------------
TOOL_RENAMES = {
    "Customer DXF Quoting": "Customer DXF Analysis",
}

# ---- AUTOMATION TOOLS  (name, what, key automation, status, since) ----------
AUTOMATION_TOOLS = [
    ("Sheet Metal Calculators",
     "A library of shop calculators -- flat length, bend deduction, material "
     "weight -- behind one picker.",
     "Driven by a declarative registry: each calculator is a field list plus a "
     "formula, so adding one is a single data entry with no interface work. "
     "Native forms with per-input validation.",
     "Active", "0.8.6.9"),
    ("Customer DXF Analysis",
     "Interactive DXF viewer for quoting customer-supplied parts, with "
     "automated guideline offsets applied per plate thickness.",
     "Layer-coloured geometry with per-line measurements and total linear "
     "inches; thickness-banded hole and cutout offsets with cap and minimum "
     "warnings; saves over the original or exports a copy.",
     "Active", "0.8.6"),
]

# ---- VERSION HISTORY  (version, date, type, deliverables, tools) ------------
VERSION_ROWS = [
    ("In Development", "Aug 2026", "Feature",
     "Engagement and personalisation layer expanded: the rewards catalog gains "
     "a desktop widget line built on a new composable three-layer asset "
     "system, with an in-app builder for operators to assemble their own "
     "combinations. Several long-standing interface defects fixed alongside "
     "it, including truncated catalog names and clipped widget display.",
     "Desktop Widgets (new line), Widget Builder (new), Sheet Metal "
     "Calculators, interface text fitting, widget display and sizing fixes"),
]

# ---- Wording fixes in EXISTING Version Controller prose --------------------
# Rows written before the tone rule that still use the in-house currency name.
# (Left alone: "911 Remove Ticket", "move ticket PDFs" and "IT tickets" -- those
# are real tool names and manufacturing documents, not the reward currency.)
PROSE_FIXES = [
    ("VERSION HISTORY",
     "credits recognition tickets for each stage completed",
     "awards activity credits for each stage completed"),
]

# ---- ROADMAP  (priority, item, description, workflow, phase) ---------------
ROADMAP = [
    ("Medium", "Operator Presence & Nudges",
     "Show which colleagues are in the platform and allow a lightweight nudge, "
     "so a batch hand-off does not need a separate message.",
     "Platform", "Research"),
    ("Low", "Code Signing Certificate",
     "Sign the executable and installer so Windows Smart App Control stops "
     "blocking first run on clean machines.",
     "Platform", "Planned"),
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
    ("CONTINUOUS INTEGRATION", "COMPLETE",
     "FULL TEST SUITE RUNS AUTOMATICALLY ON EVERY CODE CHANGE, NOT ONLY BEFORE "
     "A RELEASE; SUITE GROWN FROM 69 TO 405 TESTS"),
]
