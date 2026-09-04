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
    ("Scheduling Board Status Automation",
     "The shared planning schedule's status column is advanced by the platform "
     "as each job progresses -- off the card queue once its Teams card is "
     "posted, off the setup queue once its batch is set up -- instead of being "
     "retyped by hand.",
     "Removes a manual bookkeeping step that planning previously repeated for "
     "every job, and keeps the board an accurate picture of what is actually "
     "waiting rather than what someone last remembered to update.",
     "Active"),
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
    ("Aug 2026", "Shared PDF Write Reliability", "Quality",
     "Corrected a fault in the shared routine tools use to rewrite a PDF in "
     "place: the file was being swapped while still held open, which failed on "
     "Windows and could leave a partial temporary file next to the original.",
     "Prevents a class of failure where a document is left unwritten and a "
     "stray temporary file could be mistaken for the real paperwork.",
     "Shared component; available to every tool that writes a PDF."),
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
    ("Aug 2026", "Always-On Diagnostics Log", "Quality",
     "Every part of the platform now writes to one rotating diagnostic log, "
     "including the classes of failure that previously vanished without a "
     "trace: update-check problems, tools that fail to load, and unhandled "
     "errors outside a tool run. Startup timings are recorded on every "
     "machine, and an automated check prevents new code from writing "
     "diagnostics anywhere the shipped application cannot capture.",
     "A colleague-reported problem can be diagnosed from their machine's own "
     "log instead of guesswork over a call, and failures that used to be "
     "invisible now leave evidence. After an abnormal shutdown, the next "
     "start offers to create the diagnostic report on the spot, so crashes "
     "get reported without anyone having to find the buried menu option.",
     "Platform-wide; included in the one-click debug report."),
    ("Aug 2026", "Run Engine Consolidation", "Quality",
     "Merged the tool-execution engine's two near-duplicate code paths into "
     "one and brought window-based tools under the same run tracking as "
     "background tools - closing a gap where the application could be closed "
     "mid-run without warning, a cancelled run could be scored as a success, "
     "and a double-click could start the same tool twice.",
     "Reliability fixes now land once and apply to every kind of tool, and "
     "an operator cannot lose work by closing the app during a run.",
     "Platform-wide; execution engine test coverage grown from 3 to 20 tests."),
    ("Aug 2026", "Build Pipeline Hardening", "Quality",
     "The packaging script can no longer report success when part of the "
     "build failed: a failed installer step now stops the pipeline, the "
     "packaging tools' output is captured for diagnosis instead of "
     "discarded, and the release version is cross-checked across every file "
     "that declares it before anything is built.",
     "A broken or mislabeled installer cannot be produced by a build that "
     "claims to have succeeded.",
     "Every build; version agreement also verified continuously by the test "
     "suite."),
    ("Aug 2026", "Point-and-Pick Batch Selection", "Usability",
     "922-series tools now take their batch by picking the batch's folder "
     "instead of typing a batch number: the number is read from the chosen "
     "folder itself, and one pick is shared by every tool queued in the same "
     "run.",
     "Eliminates mistyped batch numbers - the easiest way to point a run at "
     "the wrong batch - and reduces a full multi-tool batch run to a single "
     "pick.",
     "Six 922 tools on the shared routine; the standard for new 922 tools."),
    ("Aug 2026", "Complete Part Coverage on Kit Paperwork", "Quality",
     "Two tools preparing the same batch disagreed on how many parts it "
     "contained, which is how two silent omissions were found. Both are "
     "corrected: the forming tool now identifies a part by its order as well "
     "as its part number, so a part built for two different orders is "
     "recorded and gathered once for each rather than once in total; and the "
     "kitting tool now recognises an order with more parts than its standard "
     "checklist can hold and reprints that order on the larger layout instead "
     "of stopping at ten.",
     "A part could be left off the shop paperwork with no error raised - the "
     "only signal was the two tools disagreeing. Neither omission is possible "
     "now, and an order large enough to outgrow even the larger layout raises "
     "a warning rather than passing quietly.",
     "922 forming and kitting; verified end to end against a live production "
     "batch."),
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
    # Past re-keys (a dict can hold each old key once, so superseded targets
    # move to this comment): "In Development" -> "Beta 0.8.6.11".
    "In Development": "Beta 0.8.7.1",
    "0.8.6.11": "Beta 0.8.6.11",
}

# ---- VERSION HISTORY  (version, date, type, deliverables, tools) ------------
VERSION_ROWS = [
    ("Beta 0.8.7.4", "Sep 4, 2026", "Feature",
     "The 911 batch setup tool now prepares plate work as well as structural "
     "shapes. Until now its output was tailored to shapes, and plate batches "
     "were prepared by hand around it: the operator selects plate for the run "
     "and the tool produces the plate workbook and the plate verification "
     "form, records the material specification as not applicable on carbon "
     "plate - decided by the ferrous designation the shop paperwork itself "
     "carries, never inferred from the material name - and carries each "
     "nest's traceability number from the forecast onto the verification "
     "sheet, a field that previously had to be remembered and typed by hand "
     "on every plate order. The plate selection deliberately does not "
     "persist between runs, so a prior plate run can never silently apply "
     "plate paperwork to a shape batch. "
     "The scripting-preparation tool now takes the values shared across an "
     "order line - purchase order, line, revision, clauses, ship-to and "
     "promise date - once, and propagates them to every line, with any "
     "differing line still editable individually; division naming was "
     "aligned to the exact form the ERP expects, removing a manual "
     "correction. "
     "The difficulty marking applied by the design system is now preserved "
     "on part drawings rather than removed during paperwork preparation - "
     "the shop floor relies on the visible marker - while orders processed "
     "under the previous behaviour continue to be recognised as difficult. "
     "A display fault that made the run control appear to vibrate on scaled "
     "monitors was corrected.",
     "911 Setup, 911 Scripting Prep, 922 Difficulty Stamper"),
    ("Beta 0.8.7.3", "Sep 2, 2026", "Feature",
     "Adds a scripting-preparation tool for the SSPO order line. The ERP "
     "scripting workbook was previously typed out line by line; it is now "
     "built from the award review a reviewer has already checked, with each "
     "material's designation and size looked up in the Working Forecast "
     "List, so the sheet arrives filled in rather than transcribed. Both "
     "sheets are produced in a single file, and any line the tool cannot "
     "resolve is listed inside that same file with the reason it could not - "
     "so the exceptions travel with the data they belong to instead of in a "
     "second document that can be mislaid, and the operator removes the list "
     "once the values are entered. "
     "The purchase-order extraction tool has been reinstated. It was "
     "withdrawn on the assumption that the new scripting tool superseded it; "
     "the two in fact serve opposite directions - one reads the customer's "
     "incoming order paperwork, the other produces the outgoing scripting "
     "sheet - and both are maintained going forward. Operators who lost the "
     "tool from their home screen restore it from the library once. "
     "The order line's quantity and unit price are now operator-configurable "
     "rather than fixed in the build, so an award structured differently is "
     "a setting rather than a development request. A stale home-screen entry "
     "left by the tool's renaming is cleared automatically at next start. "
     "Nest selection in the inspection-data capture tool now starts empty "
     "and is opted into, matching the setup tool. Reading a whole order is "
     "the exception; the previous default obliged the operator to deselect "
     "most of the list on every ordinary run.",
     "911 Scripting Prep (new), 911 PO PDF Extractor (reinstated), "
     "911 Inspection Dimensions"),
    ("Beta 0.8.7.2.1", "Sep 1, 2026", "Patch",
     "Corrective release for the inspection-data capture tool. The image "
     "recognition component it depends on was omitted from the previous "
     "build's package, so the tool returned no results and reported the "
     "drawings as containing no sketch pages - work that had to be entered by "
     "hand. The component is restored and a build-time check now prevents the "
     "omission recurring; the tool was re-validated against the production "
     "packet that reported the fault, recovering 122 dimensions across 24 "
     "parts and completing 19 inspection sheets. The misleading message was "
     "treated as a second defect: a component that cannot start is now "
     "reported as such rather than as an empty drawing set, so the operator "
     "is directed at the tool instead of the paperwork. "
     "Two accuracy defects were also closed. Angular dimensions were written "
     "in a form the inspection sheet read as linear, applying a tolerance an "
     "order of magnitude tighter than the form intends; they now carry the "
     "correct tolerance. And a dimension whose leading decimal point was lost "
     "in recognition was written to a sheet as a value roughly six times the "
     "part - readings that cannot be valid lengths are now withheld and "
     "listed for review rather than entered, with an operator-facing switch "
     "to disable the check if it is ever too strict. "
     "The tool's run report has been rewritten for the inspector who uses it. "
     "It now opens on screen at the end of a run, led by the items needing a "
     "second look, and is saved alongside the work on request rather than "
     "filed automatically into the folder tree. Selecting the top-level "
     "customer folder no longer starts a run across every order in the "
     "programme; the operator is offered the orders and nests to include.",
     "Inspection Data Capture"),
    ("Beta 0.8.7.2", "Sep 1, 2026", "Feature",
     "The inspection-data capture tool now completes the weld-prep entries as "
     "well as the dimensions. Previously it recorded the weld-prep callout "
     "codes it found on each drawing but could not supply the bevel angle, "
     "because that value is not printed on the drawing - it is held in the "
     "customer's bevel reference set. All 947 reference sheets have been "
     "transcribed and are now carried with the tool, so a callout on a drawing "
     "becomes a filled-in nominal on the inspection sheet, one entry per face "
     "the drawing names. Three classes of silent omission were closed in the "
     "process: three of the four callout prefix families were being skipped "
     "entirely (one of them accounts for a fifth of the reference set), a "
     "two-sided callout is now recorded as the two separate entries it "
     "represents, and a callout whose reference sheet carries no angle is "
     "raised for a decision rather than left blank - a prep that produced "
     "nothing previously looked identical to one that was never read. "
     "Withdrawn codes name their replacement instead of writing a value, and "
     "where image recognition returns a damaged code the tool repairs the "
     "unambiguous cases and, for the rest, names the closest valid code for "
     "review without ever substituting a guess onto a quality form. Validated "
     "across 90 production packets covering 684 weld preps. "
     "Reliability work this release removes three defects that each cost "
     "rework in the field. Pallet and batch marking was applied to the first "
     "document found in an order folder, which since the introduction of "
     "drawing binders was usually a drawing rather than the work packet the "
     "shop floor reads - 223 of 252 live order folders were affected. Marking "
     "now identifies the work packet by reading it, and marks left on drawings "
     "by earlier runs are removed. A Windows path-length limit caused file "
     "writes to fail with a misleading 'file not found' message anywhere the "
     "customer folder tree ran deep; the limit has been removed across every "
     "tool, with a build-time check to prevent reintroduction. And where one "
     "batch builds the same part for two different orders, the forming search "
     "recorded only the first - both are now tracked. Kit paperwork prints "
     "orders of more than ten parts in full instead of dropping the overflow, "
     "and the nest-file gathering tool accepts the nesting software's revised "
     "cutting-diagram format, which had been causing repeated run failures. "
     "Tools that read from cloud-synchronised storage now retrieve files "
     "while the operator is still answering prompts, shortening the runs that "
     "spend most of their time waiting on downloads.",
     "911 Inspection Dimensions, 911 LST Organizer, 911 SSPO Award Review, "
     "922 Pallet Stamper, 922 Difficulty Stamper, 922 Setup, "
     "922 FormingFinder, 922 Kitting, plus a platform-wide reliability fix"),
    ("Beta 0.8.7.1", "Aug 20, 2026", "Feature",
     "A new inspection-data capture tool reads every dimension off the part "
     "sketch drawings in a batch's nest packages - the drawings are scanned "
     "images with no machine-readable text, so the tool reads them by "
     "on-device image recognition, with nothing sent off the machine - and "
     "types the values onto each part's inspection sheet, including weld-prep "
     "codes with the side each applies to. Reference dimensions and note text "
     "are excluded and reported separately, and a sheet that already has "
     "values is never overwritten. This removes the slowest manual step in "
     "inspection prep: reading each drawing and keying its dimensions by hand. "
     "Flat bar forming moves in-house: the design automation system now marks "
     "a formed flat bar's files the same way it marks formed plates, the "
     "forming search gathers formed flat bars alongside formed plates by all "
     "three of its methods, and kit paperwork tags those parts automatically - "
     "no separate list-keeping for the new forming work. Kit paperwork "
     "generation also gains an input check: any kit line whose part has no "
     "source material recorded is flagged before anything prints, with the "
     "choice to stop and fix the purchase-order data or knowingly proceed. "
     "And the packet difficulty marking now finishes the job: once a work "
     "packet carries the mark, the original marking is removed from the part "
     "drawings it came from, so the flag lives on the paperwork the floor "
     "works from - re-running still keeps packets honest in both directions. "
     "Batch preparation gains a card-labelling stage that adds pallet labels "
     "to coordination cards raised before pallet assignments existed, closing "
     "a gap where those cards stayed unlabelled. All 922 tools now take their "
     "batch by picking the batch folder rather than typing a number, and a "
     "queued run of several tools asks once. Customer geometry quoting "
     "resolves a set of field-reported defects: thickness entry applies to a "
     "whole batch at once, legacy-format customer files (previously skipped "
     "silently) are fully processed, manual adjustments prefill the correct "
     "customer-guideline amount for the plate, failures are reported per "
     "feature with reasons, and re-processing an already-processed file warns "
     "before compounding. Updates that fail to download can be retried, and "
     "after an unexpected stoppage the next start offers a one-click "
     "diagnostic report.",
     "911 Inspection Dimensions (new), 922 Setup, 922 FormingFinder, "
     "922 Kitting, 922 Difficulty Stamper, 922 LST Organizer, "
     "922 Batch Repeater, 922 Runtime Genie, Customer DXF Analysis"),
    ("Beta 0.8.7", "Aug 13, 2026", "Feature",
     "Adds a personal planning workspace to the platform. Staff can capture "
     "what is on their plate in plain language and have the day laid out as a "
     "worked schedule: commitments with a date are placed first, the remainder "
     "ordered by value returned against time spent, every estimate padded "
     "against optimism, and meetings and breaks worked around. Anything that "
     "will not fit in the available hours is reported with the reason rather "
     "than silently dropped, which turns an over-committed day into a "
     "conversation before it becomes a missed deadline. The finished plan "
     "exports to Outlook, so reminders reach staff on any device, and the "
     "platform also prompts locally before each block begins. A running notes "
     "and task list sits alongside it. "
     "A new packet-marking tool carries the engineering difficulty flag from "
     "the CAD models through to the printed work packet, so a compound-cut "
     "part is visible to the floor at the point of work instead of only in the "
     "model. Re-running is safe in both directions: it will not mark a packet "
     "twice, and a job whose parts are no longer flagged has its previous mark "
     "removed. Parts whose drawings cannot be read are reported rather than "
     "assumed clear. "
     "Also: staff can set a profile picture, and a reliability defect that "
     "could fail a document save when the file was still held open is fixed.",
     "Personal Planning Workspace (new), 922 Difficulty Stamper (new), "
     "profile pictures, document-save reliability fix"),
    ("Beta 0.8.6.13", "Aug 11, 2026", "Feature",
     "Coordination-card creation for the 911 pipeline is now a standalone tool, "
     "so cards can be raised without running a batch setup and a setup can be "
     "re-run without re-raising cards - a change requested directly by the "
     "planning group. Operators can now select which of the waiting jobs to "
     "raise cards for rather than the whole queue. The shared planning "
     "schedule's status column is maintained by the platform as work "
     "progresses, removing a manual bookkeeping step and keeping the board an "
     "accurate picture of what is actually waiting. Setup tools remember each "
     "operator's chosen steps between sessions, so a site that skips a step "
     "configures it once instead of every run. Two reliability defects fixed: "
     "abandoning a tool at its first prompt was being recorded as a completed "
     "run, and a renamed column heading on the planning schedule had silently "
     "stopped difficulty ratings from reaching either the printed packets or "
     "the coordination cards - column lookups now tolerate headings that gain "
     "extra wording.",
     "911 Teams Cards (new), 911 Setup, 922 Setup, scheduling-board status "
     "automation"),
    ("Beta 0.8.6.11", "Aug 5, 2026", "Feature",
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
    ("Beta 0.8.6.12", "Aug 5, 2026", "Fix",
     "Restored automated task-card creation for 922 batches: a regression in "
     "the prior release meant the card post was accepted but no cards were "
     "created on the board; the data contract is repaired and now covered by "
     "automated tests so a required field cannot silently drop out again. "
     "Formed-plate marking on kit paperwork now lands on the plate rather "
     "than the rod for parts that carry both under one part number, "
     "eliminating a class of mislabeled kit sheets. Material pull reports no "
     "longer double-count a piece renamed between the purchase order and the "
     "shop file - one physical part previously showed as both missing and "
     "unresolved - cutting false missing-part alerts. Repeat-order pulls are "
     "now verified for complete shop-print data at pull time, surfacing a "
     "gap weeks earlier than the end-of-batch report that used to catch it.",
     "922 Setup, 922 FormingFinder, 922 Kitting, 922 LST Organizer, 911 LST "
     "Organizer, 922 Batch Repeater"),
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
    ("WELD PREP ANGLE REFERENCE", "COMPLETE",
     "THE CUSTOMER'S COMPLETE BEVEL REFERENCE SET (947 SHEETS) TRANSCRIBED AND "
     "CARRIED WITH THE DRAWING DIMENSION READER, SO A WELD PREP CALLOUT ON A "
     "DRAWING BECOMES A FILLED-IN BEVEL ANGLE ON THE INSPECTION SHEET, ONE "
     "ENTRY PER FACE THE DRAWING NAMES; THREE OF THE FOUR CALLOUT FAMILIES "
     "WERE PREVIOUSLY SKIPPED ENTIRELY, WITHDRAWN CODES NOW NAME THEIR "
     "REPLACEMENT, AND A CALLOUT WITH NO PUBLISHED ANGLE IS RAISED FOR A "
     "DECISION RATHER THAN LEFT BLANK; VALIDATED ON 90 PRODUCTION PACKETS "
     "COVERING 684 WELD PREPS"),
    ("WORK PACKET MARKING CORRECTION", "COMPLETE",
     "PALLET AND DIFFICULTY MARKING WAS BEING APPLIED TO THE FIRST DOCUMENT "
     "FOUND IN AN ORDER FOLDER, WHICH SINCE THE INTRODUCTION OF DRAWING "
     "BINDERS WAS USUALLY A DRAWING RATHER THAN THE WORK PACKET THE SHOP FLOOR "
     "READS -- 223 OF 252 LIVE ORDER FOLDERS AFFECTED; THE WORK PACKET IS NOW "
     "IDENTIFIED BY READING IT, AND MARKS LEFT ON DRAWINGS BY EARLIER RUNS "
     "ARE REMOVED"),
    ("LONG FILE PATH RELIABILITY FIX", "COMPLETE",
     "A WINDOWS PATH-LENGTH LIMIT CAUSED FILE WRITES TO FAIL WITH A MISLEADING "
     "'FILE NOT FOUND' MESSAGE ANYWHERE THE CUSTOMER FOLDER TREE RAN DEEP; "
     "THE LIMIT IS REMOVED ACROSS ALL 25 TOOLS (AROUND 215 FILE OPERATIONS), "
     "WITH A BUILD-TIME CHECK PREVENTING REINTRODUCTION"),
    ("DUPLICATE-ORDER FORMING TRACKING", "COMPLETE",
     "WHERE ONE BATCH BUILDS THE SAME PART FOR TWO DIFFERENT ORDERS, THE "
     "FORMING SEARCH RECORDED ONLY THE FIRST AND DROPPED THE SECOND SILENTLY; "
     "BOTH ORDERS ARE NOW TRACKED AND BOTH REACH THE FORMING BINDER"),
    ("OVERSIZE KIT PAPERWORK", "COMPLETE",
     "AN ORDER OF MORE THAN TEN PARTS PRINTED THE FIRST TEN AND DROPPED THE "
     "REST WITH NO WARNING; SUCH ORDERS NOW PRINT ON THE LARGER CHECKLIST "
     "SHEET AND KEEP THEIR PLACE IN THE KIT PAPERWORK"),
    ("CUTTING DIAGRAM FORMAT UPDATE", "COMPLETE",
     "THE NESTING SOFTWARE CHANGED HOW IT LABELS PARTS ON ITS CUTTING "
     "DIAGRAMS, WHICH CAUSED REPEATED RUN FAILURES IN THE NEST-FILE GATHERING "
     "TOOL; BOTH THE OLD AND NEW FORMATS ARE NOW ACCEPTED"),
    ("CLOUD FILE PREFETCH", "COMPLETE",
     "TOOLS THAT READ FROM CLOUD-SYNCHRONISED STORAGE NOW RETRIEVE FILES IN "
     "THE BACKGROUND WHILE THE OPERATOR IS STILL ANSWERING PROMPTS, INSTEAD OF "
     "ONE AT A TIME MID-RUN; SHORTENS THE RUNS THAT SPEND MOST OF THEIR TIME "
     "WAITING ON DOWNLOADS"),
    ("DRAWING DIMENSION READER", "PILOT",
     "READS THE DIMENSIONS DIRECTLY OFF THE PART DRAWINGS IN A 911 NEST "
     "PACKAGE -- INCLUDING THE WELD PREP CALLOUTS -- AND FILLS THEM ONTO EACH "
     "PART'S INSPECTION SHEET; RUNS ENTIRELY ON THE MACHINE WITH NO OUTSIDE "
     "SERVICE, SKIPS REFERENCE-ONLY FIGURES AND STOCK NOTES, NEVER OVERWRITES "
     "A SHEET ALREADY FILLED IN BY HAND, AND FLAGS ANY DRAWING IT COULD NOT READ"),
    ("922 PALLET LABELER STAGE", "COMPLETE",
     "BATCH PREPARATION GAINS A CARD-LABELLING STAGE THAT ADDS PALLET LABELS "
     "TO COORDINATION CARDS RAISED BEFORE PALLET ASSIGNMENTS EXISTED; "
     "PREVIOUSLY THOSE CARDS STAYED UNLABELLED BECAUSE RE-RUNNING SETUP WOULD "
     "DUPLICATE THE BOARD RATHER THAN LABEL IT"),
    ("CUSTOMER DXF FIELD-REPORTED FIXES", "COMPLETE",
     "FIVE DEFECTS REPORTED BY THE QUOTING CREW RESOLVED: BATCH-WIDE "
     "THICKNESS ENTRY, LEGACY-FORMAT CUSTOMER FILES (PREVIOUSLY SKIPPED "
     "SILENTLY) NOW FULLY PROCESSED, MANUAL ADJUSTMENTS PREFILL THE CORRECT "
     "CUSTOMER-GUIDELINE AMOUNT, FAILURES REPORTED PER FEATURE WITH REASONS, "
     "AND RE-PROCESSING AN ALREADY-PROCESSED FILE WARNS BEFORE COMPOUNDING; "
     "ROOT CAUSES CONFIRMED AGAINST THE REPORTING CREW'S OWN FILES"),
    ("UPDATE DOWNLOAD RETRY", "COMPLETE",
     "A FAILED UPDATE DOWNLOAD NOW OFFERS A RETRY INSTEAD OF A DEAD END, THE "
     "MANUAL UPDATE CHECK REPORTS ITS REAL OUTCOME, AND UPDATES EXIT THE "
     "APPLICATION CLEANLY"),
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
    ("SCHEDULING BOARD - AUTOMATIC STATUS ADVANCE", "COMPLETE",
     "THE PLANNING SCHEDULE'S STATUS COLUMN NOW ADVANCES ITSELF AS WORK "
     "COMPLETES - A JOB MOVES OFF THE CARD QUEUE WHEN ITS TEAMS CARD IS "
     "POSTED AND OFF THE SETUP QUEUE WHEN ITS BATCH IS SET UP; ONLY JOBS THAT "
     "GENUINELY REACHED THE NEXT STAGE MOVE, AND A SCHEDULE OPEN ON ANOTHER "
     "MACHINE LISTS THE ROWS TO CHANGE BY HAND RATHER THAN BLOCKING THE RUN"),
    ("IN-HOUSE FLAT BAR FORMING SUPPORT", "COMPLETE",
     "FORMED FLAT BARS NOW FLOW THROUGH THE SAME AUTOMATED PIPELINE AS FORMED "
     "PLATES: THE DESIGN AUTOMATION SYSTEM APPENDS THE FORMED FILENAME SUFFIX "
     "TO A FLAT BAR WHEN ITS MATERIAL STATE IS SWITCHED TO FORMED, THE "
     "FORMING SEARCH GATHERS THEM BY ALL THREE OF ITS METHODS, AND KIT "
     "PAPERWORK TAGS THEM FORMED AUTOMATICALLY"),
    ("KITTING SOURCE MATERIAL PRE-CHECK", "COMPLETE",
     "EVERY KIT PAGE IS CHECKED BEFORE ANYTHING PRINTS; A LINE WITH A PART "
     "BUT NO SOURCE MATERIAL HALTS THE RUN WITH THE LIST OF OFFENDERS AND "
     "THE CHOICE TO FIX THE PURCHASE ORDER FIRST OR PROCEED ANYWAY"),
    ("DIFFICULTY LABEL MOVES TO THE PACKET", "COMPLETE",
     "ONCE A WORK PACKET IS STAMPED DIFFICULT, THE BLUE LABEL IS REMOVED "
     "FROM THE PART DRAWINGS IT CAME FROM; A METADATA MARKER KEEPS RE-RUNS "
     "HONEST, SO A STRIPPED DRAWING STILL READS AS DIFFICULT UNTIL THE PART "
     "IS REGENERATED"),
    ("PART DIFFICULTY CARRIED ONTO THE WORK PACKET", "COMPLETE",
     "PARTS REQUIRING A COMPOUND CUT ARE MARKED DIFFICULT ON THEIR ENGINEERING "
     "DRAWING BY THE DESIGN AUTOMATION SYSTEM; A NEW TOOL READS EVERY PART "
     "DRAWING IN A BATCH AND STAMPS THAT MARKING ONTO THE FRONT PAGE OF THE "
     "WORK PACKET THE SHOP FLOOR ACTUALLY WORKS FROM, SO DIFFICULTY IS VISIBLE "
     "AT THE START OF THE JOB INSTEAD OF BURIED IN THE PART PRINTS; RE-RUNNING "
     "AFTER A PART CHANGES UPDATES THE PACKET BOTH WAYS, ADDING THE MARKING OR "
     "REMOVING IT"),
    ("UNIFIED DIAGNOSTIC LOG + CRASH CAPTURE", "COMPLETE",
     "ONE ROTATING APPLICATION LOG NOW CAPTURES EVERYTHING OUTSIDE TOOL RUNS "
     "- UPDATER OUTCOMES, TOOLS THAT FAIL TO LOAD, UNHANDLED ERRORS, STARTUP "
     "TIMINGS; 79 DIAGNOSTIC PRINTS THAT WERE SILENT IN THE SHIPPED BUILD "
     "CONVERTED, AND AN AUTOMATED GUARD BLOCKS NEW ONES"),
    ("DEV RUNS LOAD THE REPO TREE", "COMPLETE",
     "THE COPY-EVERY-EDIT-TO-BOTH-LOCATIONS RULE IS RETIRED: A DEV RUN LOADS "
     "TOOLS STRAIGHT FROM THE REPOSITORY, SO THE CODE JUST EDITED IS THE CODE "
     "THAT RUNS; INSTALLED BUILDS ARE UNCHANGED"),
    ("RUN ENGINE CONSOLIDATION", "COMPLETE",
     "THE EXECUTION ENGINE'S TWO NEAR-DUPLICATE CODE PATHS MERGED INTO ONE "
     "AND WINDOW-BASED TOOLS BROUGHT UNDER RUN TRACKING - CLOSE-WITHOUT-"
     "WARNING, CANCELLED-RUN-SCORED-AS-SUCCESS AND DOUBLE-START ALL CLOSED; "
     "ENGINE TEST COVERAGE GROWN FROM 3 TO 20 TESTS"),
    ("BUILD SCRIPT HONESTY", "COMPLETE",
     "A FAILED INSTALLER STEP NOW FAILS THE BUILD INSTEAD OF REPORTING "
     "SUCCESS, PACKAGING TOOL OUTPUT IS CAPTURED FOR DIAGNOSIS INSTEAD OF "
     "DISCARDED, AND THE RELEASE VERSION IS CROSS-CHECKED ACROSS EVERY FILE "
     "THAT DECLARES IT"),
    ("922 FOLDER-PICK BATCH ENTRY", "COMPLETE",
     "FIVE MORE 922 TOOLS TAKE THEIR BATCH BY PICKING THE BATCH FOLDER "
     "INSTEAD OF TYPING A NUMBER - THE NUMBER IS READ FROM THE FOLDER ITSELF "
     "AND ONE PICK IS SHARED ACROSS A QUEUED RUN; ONE SHARED ROUTINE REPLACES "
     "SIX HAND-COPIED PROMPT BLOCKS AND IS THE STANDARD FOR NEW 922 TOOLS"),
]
