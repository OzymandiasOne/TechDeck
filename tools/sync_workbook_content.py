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
    ("Integrated User Manual",
     "A full illustrated manual - every screen and every tool, step by step "
     "with real screenshots - ships inside the application and opens from the "
     "console or the settings page. It is regenerated automatically as part "
     "of every build, with automated checks on wording, pictures, and layout, "
     "so the shipped manual can never fall behind the software.",
     "Operators answer their own how-do-I questions at the desk instead of "
     "interrupting a colleague, and new hires can work through any tool "
     "unassisted from day one.",
     "Active"),
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
     "difficulty, machine routing and pallet, and re-tag repeat orders. The "
     "integration reports back what it actually did - how many cards were "
     "created, how many already existed and which failed - and a card that "
     "failed is offered again on the next run.",
     "Batch coordination is set up from the batch data itself rather than "
     "typed in one card at a time, it cannot drift out of step with the "
     "folders the operators actually work from, and a failed hand-off to the "
     "board is seen when it happens rather than when someone looks.",
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
    # New rows are APPENDED to the sheet in list order, so add below this line
    # in the order the features shipped.
    ("Personal Planning Workspace",
     "Staff capture their workload in plain language and the platform lays "
     "the day out as a worked schedule: dated commitments first, the rest "
     "ordered by value against time, every estimate padded, and anything "
     "that will not fit reported with the reason. Scheduled meetings and "
     "blocked time are planned around; work parked on another person is held "
     "out of the plan but tracked, with a follow-up prompt after a set number "
     "of days; time spent is captured per item and reported by item and by "
     "day with a spreadsheet export; a large piece of work carries its own "
     "dated sub-steps; and the whole list is searchable. The workspace can "
     "be lifted out into a floating panel inside the application - movable, "
     "resizable, docking to any edge - so the plan stays in view while a "
     "tool runs. Plans export to Outlook, and the page can use its own "
     "display scheme.",
     "Turns an over-committed day into a conversation before it becomes a "
     "missed deadline, and answers where the week went from recorded time "
     "rather than recollection.",
     "Active"),
    ("Seasonal Themes & What's-New Markers",
     "A seasonal display theme applies itself for its month, and what's-new "
     "markers across the account pages lead operators to newly added "
     "engagement features.",
     "Keeps the engagement layer discoverable without an announcement having "
     "to be read.",
     "Active"),
    ("Foreground Prompts & Run Notices",
     "A prompt that needs an operator's answer opens in front of whatever "
     "application is in use, and tools end with an explicit on-screen notice "
     "when a run failed or produced output that would mislead the next step, "
     "rather than recording it only in the run log.",
     "Closes a class of stalled runs where a tool waited unseen behind a "
     "spreadsheet, and stops a failed step from being discovered only when "
     "the next tool does the wrong thing.",
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
     "All three tracking workbooks, the project Gantt chart included; "
     "rosters verified against the live tool set."),
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
    ("Oct 2026", "Shared-Routine Call Verification", "Quality",
     "Where two tools do the same job they call one shared routine rather "
     "than keeping a copy each, which is what keeps them agreeing on the "
     "data. The weakness is the handover: because the connection is made "
     "while a tool is running, changing the routine for one caller and not "
     "the other was not detectable before release, and one such change "
     "stopped a 922 batch preparation step for six days before an operator "
     "diagnostic identified it. A new build check now reads every one of "
     "these shared calls and refuses to package if a caller and the routine "
     "it calls disagree.",
     "Removes a class of failure that could only be found by an operator "
     "hitting it in production. Twenty shared calls across five tools are "
     "verified on every build.",
     "Build-time check; covers every tool that shares a routine with "
     "another."),
    # New rows are APPENDED to the sheet in list order, so add below this line
    # in date order. (The two Aug 2026 rows were logged late, 2026-11-11: both
    # were on the Gantt chart and in the process log but never reached here.)
    ("Aug 2026", "Windows Long-Path Reliability", "Reliability",
     "A field report of repeated 'file not found' failures was traced to "
     "Windows' 260-character path limit rather than a missing file: the "
     "customer folder tree runs close to the limit before a tool writes "
     "anything. Treated as a platform defect rather than a one-tool bug - "
     "every file operation in every tool now goes through shared routines "
     "that are safe on long paths, including the existence checks that fail "
     "silently, and a build check prevents reintroduction.",
     "Tools no longer fail with a misleading message wherever the folder "
     "tree runs deep, and a create-if-missing guard can no longer overwrite "
     "real work because a check wrongly answered no.",
     "Around 215 file operations across all 25 tools; enforced on every "
     "build."),
    ("Aug 2026", "Cloud File Prefetch & Run Profiling", "Performance",
     "Analysis of 253 recorded tool runs showed the dominant machine-time "
     "cost was waiting on cloud-synchronised files retrieved one at a time. "
     "Tools now retrieve the files they will need in the background while "
     "the operator is still answering prompts, and the run log itself is "
     "mined as the profiler.",
     "Shortens the runs that spend most of their time waiting on downloads, "
     "and gives performance work a measured basis instead of impressions.",
     "Shared routine; adopted by the tools with the longest cloud waits."),
    ("Sep 2026", "Packaging Check for Runtime-Loaded Components", "Quality",
     "A release shipped with the image-recognition component missing from "
     "its package: the component loads its own parts by name while running, "
     "which the packaging step cannot see, so the inspection tool returned "
     "nothing and reported the drawings as empty. The component was restored "
     "the same day, the build now reads the component's own configuration "
     "and refuses to package if any part it names is absent, and a component "
     "that cannot start is reported as such rather than as empty input.",
     "The omission cannot recur silently, and an operator is pointed at the "
     "tool rather than sent hunting through paperwork that was never the "
     "problem.",
     "Build-time check on every release; corrective release issued the same "
     "day."),
    ("Sep 2026", "Guarded Publishing & Repository Backup", "Security",
     "Publishing the filtered copy of the source was a sequence of "
     "hand-entered commands; run once in the wrong place, the filter rewrote "
     "the working history itself, which was recovered only from a copy an "
     "earlier step happened to leave behind. Publishing is now one scripted "
     "step that first takes a verified full backup outside the repository, "
     "refuses to run anywhere but an isolated copy, and stops before the "
     "push for a deliberate go-ahead.",
     "The development record can no longer be damaged by the act of "
     "publishing it, and a verified restore point exists before any history "
     "operation.",
     "Every publish; the last five backups are retained, each verified by "
     "commit, branch and tag count."),
    ("Sep 2026", "Published-Copy Verification", "Testing",
     "The published copy of the source is a filtered rebuild, so a test "
     "could pass on the development machine and fail only on the published "
     "copy - on three releases the public build failed immediately after "
     "publishing. Two build checks now reproduce the filter's effect before "
     "anything leaves: one applies the name-scrubbing rules to every "
     "published file and compiles the result, the other fails any test that "
     "reads a file the filter removes.",
     "A release no longer discovers on the public side what could have been "
     "known before it left.",
     "All published source and tests; enforced on every build."),
    ("Sep 2026", "Release Content Inventory", "Process",
     "A release shipped a whole new tool without naming it in any "
     "announcement, because the notes were compiled from the feedback log "
     "and the tool had no request behind it. The list of what ships is now "
     "read from the code history - every new or changed tool since the "
     "previous release - and the build fails if a new tool is not named in "
     "the release record.",
     "Operators are told about every tool they receive, and an announcement "
     "can no longer drift from what was actually built.",
     "Every release; checked in the build and against each announcement "
     "text."),
    ("Oct 2026", "Sleep vs Freeze Detection", "Quality",
     "The diagnostic record was logging a computer going to sleep with the "
     "application open as an application freeze, burying genuine freezes "
     "among false entries. The two are now distinguished.",
     "A genuine freeze is visible in a diagnostic report rather than lost "
     "among false alarms.",
     "Platform-wide; hang monitoring and the one-click debug report."),
    ("Oct 2026", "Verified Integration Results", "Reliability",
     "Creating a batch's coordination cards reported success as soon as the "
     "request was accepted, not when the cards existed - on one batch all 35 "
     "cards failed to be created and the run still reported complete. The "
     "integration now returns what it actually did and the application "
     "reports it: cards created, cards already present, and cards that "
     "failed, with a failed card offered again on the next run.",
     "A failed hand-off to the production board is seen at the moment it "
     "happens instead of when someone looks at the board. First capability "
     "built on the upgraded integration licence.",
     "911 card creation first; the remaining four card integrations can be "
     "upgraded individually without a new release."),
    ("Oct 2026", "Part-Number Recognition Rebuild", "Data",
     "Part-number recognition was rebuilt from the part numbers on all 105 "
     "live batch lists (5,415 values) and moved to a single shared "
     "definition, after pricing consolidation rows were found falling back "
     "to a file name and sorting to the wrong place.",
     "Every tool recognises the same set of part-number shapes, so a new "
     "shape is corrected once rather than tool by tool.",
     "Shared definition; every tool that reads part numbers."),
    ("Nov 2026", "Optical Reading of Text-Less Work Packets", "Reliability",
     "Work packets re-printed through a generic PDF printer lose their "
     "machine-readable text, which stopped the packet-marking step on 13 "
     "orders across five batches with a false 'no work packet found'. The "
     "affected tools now read such a page as an image when it carries no "
     "usable text.",
     "Packet marking no longer depends on how a document happened to be "
     "printed, and the operator is not sent looking for a packet that is "
     "already in the folder.",
     "Central fix in the shared toolkit; three 922 tools."),
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
    # move to this comment): "In Development" -> "Beta 0.8.6.11",
    # "In Development" -> "Beta 0.8.7.1", "In Development" -> "Beta 0.8.7.6".
    "In Development": "Beta 0.8.8",
    "0.8.6.11": "Beta 0.8.6.11",
}

# ---- VERSION HISTORY  (version, date, type, deliverables, tools) ------------
VERSION_ROWS = [
    ("In Development", "Nov 23, 2026", "Feature",
     "A floor-feedback release, built from requests sent in by planning and "
     "invoicing staff. 922 Production Packets now opens with the platform's "
     "standard step-selection window: the operator chooses which stages run "
     "- the cutting list, the packet drawings, the production run binders - "
     "and, within the last, whether the marked-up nest sheets and cover "
     "pages are rebuilt and which pallet binders are bound, so one binder "
     "can be re-made after a hand correction without rewriting the rest. "
     "Each cutting-list sheet now totals the tube length it calls for, as a "
     "live figure that updates when a length is filled in by hand, and the "
     "sheets are ordered by packet number. The cover pages' note heading "
     "takes each pallet's own colour. 911 batch setup: a template edit made "
     "in October had removed the formulas that fill the Part Description on "
     "the inspection sheets, so every sheet built since carried that field "
     "blank unless it was typed in by hand; both templates are repaired, "
     "and the tool now fills the field itself whenever a template's formula "
     "is missing and closes the run with a notice that the template needs "
     "attention. Invoice supplements: the invoice date showed as ###### in "
     "the saved workbook - the earlier correction had reached the printed "
     "copy only - and now displays in both, with an automated check that "
     "every column the tool writes has a set width. The personal planning "
     "workspace can be lifted out into a floating panel inside the "
     "application and kept in view beside whichever tool is running; it "
     "moves, resizes and docks to any edge. The shared step-selection "
     "window, used by four tools, was also corrected: a skipped stage's "
     "options were drawn as selected and could not be cleared.",
     "922 Production Packets, 911 Setup, 911 SSPO Invoicing Prep, Personal "
     "Planning Workspace, 922 Setup, 911 Batch Repeater"),
    ("Beta 0.8.10", "Nov 11, 2026", "Feature",
     "A floor-feedback release for the 922 line. Kit paperwork now opens "
     "with the batch's filled material pull list: the standard pull-list "
     "form is filled from the batch's material plan and bound in as each "
     "kit's cover pages, with the filled workbook kept alongside for hand "
     "additions - work previously done by hand for every batch. Production "
     "packet accuracy: a batch making the same tube on more than one order "
     "was counted once, so the cutting list ran one tube short and the "
     "packet carried a single print; every part made now gets its own "
     "cutting-list line and stamped print, grouped behind each order's own "
     "assembly sheet. The per-pallet cover pages now carry the correct "
     "batch number (a template fault printed one fixed number on every "
     "batch), per-pallet color coding, and a mixed-material order is "
     "highlighted whenever any of its material is saw cut.",
     "922 Kitting, 922 Production Packets"),
    ("Beta 0.8.9", "Nov 3, 2026", "Feature",
     "A production-paperwork release. New tool: 922 Production Packets "
     "prepares a batch's tube cutting paperwork end to end - it works out "
     "the saw cut length for every tube on the batch, writes the cutting "
     "list the 1D optimizer consumes, and assembles the shop prints into "
     "one binder per source material; the cut-length rules were graded "
     "against 291 real parts across five live batches before release. A "
     "second stage, run after the operator's own nesting, marks up each "
     "nest sheet, builds a per-pallet cover page from the standard "
     "procedure documents, and binds the production run. Reliability: work "
     "packets that had been re-printed through a generic PDF printer lose "
     "their machine-readable text, which stopped the pallet stamping step "
     "on 13 orders across five batches with a false 'no work packet "
     "found'; the three affected tools now read such pages optically and "
     "continue. Invoice supplements no longer print a date or amount as "
     "###### when its column is too narrow - the column is widened for the "
     "print only, and the operator's own workbook layout is preserved.",
     "922 Production Packets, 922 Pallet Stamper, 922 Difficulty Stamper, "
     "922 Setup, 911 SSPO Invoicing Prep"),
    ("Beta 0.8.8", "Oct 21, 2026", "Feature",
     "A floor-feedback release. 911 batch setup now collects each nest's "
     "machine program files into a single folder per nest, instead of the "
     "operator opening one work-order folder at a time across a batch; a "
     "survey of every live batch found that one file name in six collides "
     "with another, so the collection keeps both files rather than "
     "overwriting, which the manual method could not guarantee. The same "
     "tool no longer reports a complete run when a nest is absent from the "
     "shared forecast: the three affected columns are highlighted and "
     "annotated in the workbook itself with the nest, the date and the one "
     "step to re-run, and the run closes as a warning - two batches had "
     "reached the floor with silently blank columns and a clean result. "
     "Packet preparation drops the near-empty continuation pages operators "
     "were deleting by hand; the rule was graded against 394 real packets "
     "first, where four of every five pages carrying that text turned out to "
     "be genuine drawings that must be kept. Part-number recognition was "
     "rebuilt from the part numbers on all 105 live batch lists (5,415 "
     "values) and moved to a single shared definition, correcting pricing "
     "consolidation rows that were falling back to a file name and sorting "
     "to the wrong place. Reliability: 922 batch preparation could not "
     "complete its parts-list and repeat-detection step, reported by an "
     "operator diagnostic six days after the previous release; the cause was "
     "a shared routine two tools call, changed for one caller only, and a "
     "new build check now verifies every such shared call so the class "
     "cannot recur. The same diagnostic also showed that a computer going to "
     "sleep with the application open was being recorded as an application "
     "freeze; it is now distinguished from one, so a genuine freeze is "
     "visible in a report rather than buried among false entries. "
     "Production-board accuracy: creating a batch's cards on the shared "
     "production board reported success as soon as the request was accepted, "
     "not when the cards existed - on one batch all 35 cards failed to be "
     "created and the run still reported complete, which was found only when "
     "the board was looked at. The integration now returns what it actually "
     "did, and the application reports it: how many cards were created, how "
     "many already existed, and which ones failed. A card that failed is no "
     "longer recorded as done, so it is offered again on the next run rather "
     "than being lost. This is the first capability built on the upgraded "
     "integration licence, which allows the service to answer rather than "
     "only receive; the remaining four card integrations can be upgraded "
     "individually without a new release.",
     "911 Setup, 911 Remove Ticket, 911 Baked Beans Wild Ride, 922 Setup, "
     "911 Teams Cards, 922 Batch Repeater"),
    ("Beta 0.8.7.9", "Oct 14, 2026", "Feature",
     "A planning and time-visibility release, built entirely from user "
     "requests. The personal work planner gains four capabilities operators "
     "asked for: scheduled commitments (meetings and other blocked time) that "
     "the day plan is built around rather than over; a blocked status for work "
     "parked on another person or department, which is held out of the plan "
     "but reported with the name of whoever holds it and raises a follow-up "
     "prompt after a configurable number of days; elapsed-time capture per "
     "item, with a reporting view that totals time by item and by day over a "
     "chosen range and exports to spreadsheet, answering where the week "
     "actually went; and sub-items under one piece of work, each with its own "
     "estimate and date, so a multi-week project is tracked as one item with "
     "internal milestones instead of several look-alike entries. Free-text "
     "search across the whole work list is included, and the page can be set "
     "to its own display scheme where sustained reading made the shared one "
     "hard to use. Reliability: prompts that need an operator answer now open "
     "in front of whatever application is in use, closing a class of stalled "
     "runs where a tool waited behind a spreadsheet with no visible signal. "
     "Six tools now end with an explicit notice when a run failed or produced "
     "output that would mislead the next step, rather than recording it only "
     "in the run log. The 922 forming tool resolves a formed part whose "
     "purchase-order number disagrees with its drawing number by deriving the "
     "part number and reading source material from the order's own purchase "
     "order, closing a gap that let a formed part reach kitting paperwork "
     "untagged; an operator-entered material value now survives a re-run.",
     "Personal Work Planner, 922 FormingFinder, 922 Kitting, 922 Runtime "
     "Genie, 922 Batch Repeater, 902 DXF Prep, 911 PO PDF Extractor"),
    ("Beta 0.8.7.8", "Oct 5, 2026", "Feature",
     "A seasonal engagement release: a seasonal theme applies itself for the "
     "month and a discovery trail (what's-new markers across the account pages) "
     "leads people to the new engagement features, including a new in-app game. "
     "On the production side: 922 batch setup now applies source-material labels "
     "to Teams cards that already exist, so a re-run completes a partly labelled "
     "board instead of skipping it, and no longer blocks on a repeat-tag warning "
     "the operator chose to skip. 911 SSPO invoicing prep gives each partial "
     "shipment of a nest its own invoice number and ship date, matched by "
     "sub-group and close-out week, and leaves a nest it cannot resolve blank "
     "and named rather than guessing; its close-out sheet is back to the "
     "intended twenty columns with a total price per work order. The 922 "
     "forming, kitting and nest-file tools now reconcile a PO part number that "
     "disagrees with its drawing number, closing a gap that produced unlabelled "
     "formed parts, wrongly stamped rod lines and false missing-tube reports. "
     "The two 922 packet stampers stamp only a proven work packet and clean "
     "stray stamps off sketches and prints (six of 252 orders across four "
     "batches had been mis-stamped). Six apps that asked for a typed path or "
     "batch number now open a folder picker, removing a class of typo failures. "
     "MieTrak hardware codes gain a reference and a reader. A retired theme is "
     "migrated automatically.",
     "922 Setup, 911 SSPO Invoicing Prep, 922 FormingFinder, 922 Kitting, "
     "922 LST Organizer, 922 Pallet Stamper, 922 Difficulty Stamper, "
     "922 Batch Repeater, MieTrak Tools, Sheet Metal Calculators, 911 PO PDF "
     "Extractor, 911 Sketch Extractor, 911 Remove Ticket, 911 Setup, "
     "Batch Auditor, Puppet Master (new)"),
    ("Beta 0.8.7.7", "Sep 21, 2026", "Feature",
     "A new incoming-batch validation tool answers, on the day a 902 batch "
     "arrives, which parts are not yet ready to work: parts with no drawing "
     "file, drawing files that open but hold no geometry, damaged model files, "
     "and parts with no print. It reads the customer's own part list, so it "
     "runs before internal pricing paperwork exists, and reads the part number "
     "off each scanned print page to match prints to parts. Read-only: no file "
     "in the batch is moved or altered. The result is one report listing every "
     "part with issue yes/no and the reason in plain words, which goes back to "
     "the customer as a single request instead of a part at a time; over three "
     "thousand parts were on hold waiting on a handful of files when this was "
     "commissioned. Validated against fourteen received batches and the "
     "program's own delay log. The 911 nest-file gathering tool now issues the "
     "same color-coded reconciliation report as its 922 counterpart. In 911 "
     "batch setup the scribe verification sheet now matches the nest's part "
     "count (it was fixed at twenty-four rows, silently omitting parts beyond "
     "that on larger nests), lists parts in nest-package order for final "
     "inspection, takes quantities from the nest package where it disagrees "
     "with the batch list, and fills the material specification per part from "
     "the part print for non-ferrous plate. A quantity verification that had "
     "never run on plate work is fixed.",
     "902 Batch Validator (new), 911 Setup, 911 LST Organizer, 902 DXF Prep, "
     "922 LST Organizer"),
    ("Beta 0.8.7.6", "Sep 17, 2026", "Feature",
     "A new MieTrak Tools window collects small MieTrak helpers behind one "
     "picker. Its first tool, the Hardware Code Generator, builds a hardware "
     "part number from dropdown picks (material, type, thread, length or "
     "screw size) and copies it to the clipboard, replacing a standalone "
     "program left behind by a departed colleague; its code tables were kept "
     "verbatim and are now covered by automated tests so the numbers keep "
     "matching. Invoicing preparation now fills the invoice number and ship "
     "date on the supplement from the working forecast, prints the supplement "
     "to PDF beside the invoice, and gathers each nest's pricing calculations "
     "into its invoicing folder. Part sketch pages that lost their drawing on "
     "the report server are filled back in from the batch's own sketch "
     "library, and the material designation is written on every part sketch "
     "so the shop can scribe from the print. The 922 batch setup tool starts "
     "with the label options on and files the batch progress checklist card in "
     "the hold stage. The tube file organizer now matches purchase-order part "
     "numbers written without the sheet hyphen.",
     "MieTrak Tools (new), 911 SSPO Invoicing Prep, 911 Setup, 911 Remove Ticket, "
     "922 Setup, 922 LST Organizer"),
    ("Beta 0.8.7.5", "Sep 11, 2026", "Feature",
     "The 922 batch setup tool now records the batch in the master parts "
     "list and identifies repeat orders at the start of the run, so each "
     "repeat's tracking card is created already labelled and already in the "
     "model-check stage of the pipeline board; previously the cards were "
     "created plain and re-tagged in a later pass. The tool also creates the "
     "batch's fourteen-step progress checklist card, which was made by hand "
     "on every batch until now. "
     "The invoicing preparation tool now takes a copy of the entire pricing "
     "master and a close-out date range, instead of a sheet trimmed down to "
     "the week by hand. Rows whose promise date falls inside the range become "
     "the week's invoicing packages, and both weekly reports - the work order "
     "close out sheet and the material status listing - are produced "
     "automatically in the same invoicing folder, replacing two documents "
     "previously rebuilt by hand every week. A complete illustrated user "
     "manual now ships inside the application, opened from the console or "
     "the settings page, and is regenerated by every build so it always "
     "matches the software it describes.",
     "922 Setup, 911 SSPO Invoicing Prep, Integrated User Manual (new)"),
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
     "911 Inspection Dimensions"),
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
    ("902 INCOMING PART FILE VALIDATION", "COMPLETE",
     "THE CUSTOMER DIRECTED THAT NO 902 BATCH SHIP WITH PARTS MISSING, AND "
     "OVER 3,000 PARTS WERE ON HOLD WAITING ON A HANDFUL OF DRAWING FILES, "
     "BECAUSE ON RECEIPT NOBODY COULD TELL WHICH PARTS HAD NO FILE, WHICH DXF "
     "FILES WERE EMPTY, WHICH IGES FILES WERE CORRUPT, OR WHICH PARTS HAD NO "
     "PRINT (THE MOST COMMON PROBLEM LOGGED); A NEW TOOL CHECKS EVERY FILE AND "
     "EVERY SCANNED PRINT IN A RECEIVED BATCH AGAINST THE CUSTOMER'S OWN PART LIST AND "
     "PRODUCES ONE REPORT LISTING EVERY PART WITH ISSUE YES/NO AND THE REASON "
     "IN PLAIN WORDS, SO THE FULL REQUEST GOES BACK TO THE CUSTOMER ON DAY ONE; "
     "VALIDATED READ-ONLY AGAINST 14 REAL BATCHES (440 PART FILES), WHERE ITS "
     "VERDICT ON EVERY IGES FILE MATCHED WHAT THE CONVERTED DRAWING SHOWED, AND "
     "ITS MISSING-PRINT FINDINGS MATCHED THE PROGRAM'S OWN DELAY LOG"),
    ("IN-APP USER MANUAL", "COMPLETE",
     "A COMPLETE ILLUSTRATED USER MANUAL FOR THE PLATFORM AND ALL 26 "
     "PRODUCTION TOOLS, WRITTEN IN PLAIN SHOP LANGUAGE WITH NUMBERED "
     "SECTIONS AND STEP-BY-STEP SCREENSHOTS TAKEN FROM THE REAL "
     "APPLICATION RUNNING ON PRACTICE DATA; SHIPS INSIDE THE APP (CONSOLE "
     "COMMAND OR SETTINGS BUTTON) AND IS REGENERATED BY EVERY BUILD WITH "
     "AUTOMATED CHECKS ON WORDING, PICTURES, PAGE LAYOUT, AND DROPPED "
     "TEXT, SO IT CANNOT GO STALE"),
    ("WEEKLY INVOICING REPORTS AUTOMATION", "COMPLETE",
     "THE INVOICING PREPARATION TOOL NOW TAKES A COPY OF THE ENTIRE PRICING "
     "MASTER PLUS A CLOSE-OUT DATE RANGE INSTEAD OF A SHEET TRIMMED TO THE "
     "WEEK BY HAND; THE WEEK'S ROWS ARE SELECTED BY THEIR PROMISE DATE, AND "
     "BOTH WEEKLY REPORTS - THE WORK ORDER CLOSE OUTS AND THE MATERIAL STATUS "
     "LISTING - ARE PRODUCED ALONGSIDE THE PER-NEST INVOICING PACKAGES IN THE "
     "SAME FOLDER, REPLACING TWO SHEETS PREVIOUSLY REBUILT BY HAND EVERY "
     "WEEK; OUTPUT VERIFIED CELL-IDENTICAL AGAINST THE HAND-MADE ORIGINALS"),
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
    ("DRAWING DIMENSION READER", "COMPLETE",
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
    ("MIETRAK TOOLS", "COMPLETE",
     "GUI PLUGIN HOSTING SMALL MIETRAK HELPERS BEHIND ONE PICKER; FIRST TOOL "
     "IS THE HARDWARE CODE GENERATOR, A NATIVE PORT OF A DEPARTED COLLEAGUE'S "
     "STANDALONE EXE (TABLES AND ASSEMBLY RULE KEPT VERBATIM, PYTEST-PINNED)"),
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

    # ---- September to November 2026 (logged 2026-11-11) ---------------------
    # New rows are APPENDED to the sheet in list order: keep this block in the
    # order the work shipped, and add below it.
    ("INSPECTION READER CORRECTIVE RELEASE", "COMPLETE",
     "THE IMAGE RECOGNITION COMPONENT WAS MISSING FROM THE 0.8.7.2 PACKAGE, SO "
     "THE DRAWING DIMENSION READER RETURNED NOTHING AND REPORTED THE DRAWINGS "
     "AS EMPTY; RESTORED THE SAME DAY WITH A BUILD CHECK THAT READS THE "
     "COMPONENT'S OWN CONFIGURATION. ANGULAR DIMENSIONS NOW CARRY THE CORRECT "
     "TOLERANCE AND IMPLAUSIBLE READINGS ARE WITHHELD FOR REVIEW INSTEAD OF "
     "ENTERED; RE-VALIDATED ON THE REPORTING PACKET (122 DIMENSIONS, 24 PARTS, "
     "19 INSPECTION SHEETS)"),
    ("PUBLISHING - VERIFIED BACKUP + GUARDED SCRIPT", "COMPLETE",
     "PUBLISHING WAS A CHAIN OF HAND-ENTERED COMMANDS; RUN ONCE IN THE WRONG "
     "PLACE, THE HISTORY FILTER REWROTE THE WORKING REPOSITORY ITSELF AND WAS "
     "RECOVERED ONLY FROM A COPY AN EARLIER STEP HAD LEFT BEHIND. PUBLISHING IS "
     "NOW ONE SCRIPT THAT TAKES A VERIFIED FULL BACKUP OUTSIDE THE REPOSITORY "
     "FIRST, REFUSES TO RUN ANYWHERE BUT AN ISOLATED COPY, AND STOPS BEFORE "
     "THE PUSH"),
    ("911 SCRIPTING PREP", "COMPLETE",
     "NEW TOOL: BUILDS THE TWO-SHEET SSPO ERP SCRIPTING WORKBOOK FROM A "
     "FINISHED AWARD REVIEW AND THE WORKING FORECAST LIST INSTEAD OF TYPING IT "
     "LINE BY LINE; LINES IT CANNOT RESOLVE ARE LISTED INSIDE THE SAME FILE "
     "WITH THE REASON. VALUES SHARED ACROSS AN ORDER LINE (PO, LINE, REVISION, "
     "CLAUSES, SHIP-TO, PROMISE DATE) ARE ENTERED ONCE AND PROPAGATE TO EVERY "
     "LINE. THE PO PDF EXTRACTOR, WITHDRAWN IN ERROR AS SUPERSEDED, WAS "
     "REINSTATED - THE TWO SERVE OPPOSITE DIRECTIONS"),
    ("911 PLATE BATCH SETUP", "COMPLETE",
     "911 SETUP NOW PREPARES PLATE WORK AS WELL AS STRUCTURAL SHAPES: THE "
     "PLATE WORKBOOK AND PLATE VERIFICATION FORM, MATERIAL SPEC RECORDED AS "
     "NOT APPLICABLE ON CARBON PLATE - DECIDED BY THE PAPERWORK'S OWN FERROUS "
     "FLAG, NEVER INFERRED FROM THE MATERIAL NAME - AND THE TRACEABILITY NUMBER "
     "CARRIED FROM THE FORECAST. THE PLATE SELECTION DELIBERATELY DOES NOT "
     "PERSIST BETWEEN RUNS"),
    ("PUBLISHED-COPY TEST GATES", "COMPLETE",
     "ON THREE RELEASES THE PUBLIC BUILD FAILED RIGHT AFTER PUBLISHING, EACH "
     "TIME ON SOMETHING THAT PASSED LOCALLY: THE PUBLISHING FILTER REWRITES "
     "NAMES AND REMOVES PRIVATE FILES. TWO BUILD CHECKS NOW REPRODUCE THAT "
     "LOCALLY - ONE COMPILES EVERY PUBLISHED FILE AFTER THE NAME SCRUB, ONE "
     "FAILS ANY TEST THAT READS A FILE THE FILTER REMOVES"),
    ("922 REPEAT IDENTIFICATION AT SETUP", "COMPLETE",
     "922 SETUP NOW RECORDS THE BATCH IN THE MASTER PARTS LIST AND FINDS "
     "REPEAT ORDERS AT THE START OF THE RUN, SO REPEAT CARDS ARE CREATED "
     "ALREADY LABELLED AND ALREADY IN THE MODEL-CHECK STAGE; IT ALSO CREATES "
     "THE BATCH'S FOURTEEN-STEP PROGRESS CHECKLIST CARD THAT WAS MADE BY HAND "
     "ON EVERY BATCH"),
    ("INVOICE SUPPLEMENT AUTOMATION", "COMPLETE",
     "INVOICING PREP FILLS THE INVOICE NUMBER AND SHIP DATE ON THE SUPPLEMENT "
     "FROM THE WORKING FORECAST, PRINTS THE SUPPLEMENT TO PDF BESIDE THE "
     "INVOICE, AND GATHERS EACH NEST'S PRICING CALCULATIONS INTO ITS INVOICING "
     "FOLDER; A NEST WITH NO INVOICE NUMBER IS LEFT BLANK AND NAMED"),
    ("PART SKETCH REPAIR + MATERIAL DESIGNATION", "COMPLETE",
     "PART SKETCH PAGES THAT LOST THEIR DRAWING ON THE REPORT SERVER ARE "
     "FILLED BACK IN FROM THE BATCH'S OWN SKETCH LIBRARY, AND THE MATERIAL "
     "DESIGNATION IS WRITTEN ON EVERY PART SKETCH SO THE SHOP CAN SCRIBE FROM "
     "THE PRINT"),
    ("RELEASE CONTENT INVENTORY", "COMPLETE",
     "A RELEASE SHIPPED A WHOLE NEW TOOL AND NAMED IT IN NO ANNOUNCEMENT, "
     "BECAUSE THE NOTES WERE BUILT FROM THE FEEDBACK LOG AND THE TOOL HAD NO "
     "REQUEST BEHIND IT; THE SHIPPING LIST IS NOW READ FROM THE CODE HISTORY "
     "AND THE BUILD FAILS IF A NEW TOOL IS NOT NAMED IN THE RELEASE RECORD"),
    ("SCRIBE VERIFICATION SHEET CORRECTIONS", "COMPLETE",
     "THE SCRIBE VERIFICATION TABLE WAS FIXED AT 24 ROWS, SILENTLY OMITTING "
     "PARTS BEYOND THAT ON LARGER NESTS; IT NOW MATCHES THE NEST'S PART COUNT, "
     "LISTS PARTS IN NEST-PACKAGE ORDER, TAKES QUANTITIES FROM THE NEST "
     "PACKAGE ON A MISMATCH, AND FILLS THE MATERIAL SPEC PER PART FOR "
     "NON-FERROUS PLATE; A QUANTITY CHECK THAT HAD NEVER RUN ON PLATE WORK IS "
     "FIXED. THE 911 NEST-FILE GATHERING TOOL ALSO GAINS THE SAME COLOUR-CODED "
     "RECONCILIATION REPORT AS ITS 922 COUNTERPART"),
    ("SEASONAL THEME + WHAT'S-NEW MARKERS", "COMPLETE",
     "A SEASONAL DISPLAY THEME APPLIES ITSELF FOR ITS MONTH AND WHAT'S-NEW "
     "MARKERS ACROSS THE ACCOUNT PAGES LEAD TO NEW ENGAGEMENT FEATURES; A "
     "THIRD OPTIONAL ENGAGEMENT MODULE WAS ADDED, AND A RETIRED THEME IS "
     "MIGRATED AUTOMATICALLY"),
    ("SOURCE MATERIAL LABELS ON EXISTING CARDS", "COMPLETE",
     "922 SETUP APPLIES SOURCE-MATERIAL LABELS TO COORDINATION CARDS THAT "
     "ALREADY EXIST, SO A RE-RUN COMPLETES A PARTLY LABELLED BOARD INSTEAD OF "
     "SKIPPING IT, AND NO LONGER BLOCKS ON A REPEAT-TAG WARNING THE OPERATOR "
     "CHOSE TO SKIP"),
    ("PARTIAL-SHIPMENT INVOICING", "COMPLETE",
     "EACH PARTIAL SHIPMENT OF A NEST GETS ITS OWN INVOICE NUMBER AND SHIP "
     "DATE, MATCHED BY SUB-GROUP AND CLOSE-OUT WEEK; A NEST THAT CANNOT BE "
     "RESOLVED IS LEFT BLANK AND NAMED RATHER THAN GUESSED"),
    ("PO VS DRAWING NUMBER RECONCILIATION", "COMPLETE",
     "THE 922 FORMING, KITTING AND NEST-FILE TOOLS RECONCILE A PO PART NUMBER "
     "THAT DISAGREES WITH ITS DRAWING NUMBER, CLOSING A GAP THAT PRODUCED "
     "UNLABELLED FORMED PARTS, WRONGLY STAMPED ROD LINES AND FALSE "
     "MISSING-TUBE REPORTS; AN OPERATOR-ENTERED MATERIAL VALUE NOW SURVIVES A "
     "RE-RUN"),
    ("PROVEN-PACKET STAMPING", "COMPLETE",
     "THE TWO 922 PACKET STAMPERS STAMP ONLY A PROVEN WORK PACKET AND CLEAN "
     "STRAY STAMPS OFF SKETCHES AND PRINTS; 6 OF 252 ORDERS ACROSS FOUR "
     "BATCHES HAD BEEN MIS-STAMPED"),
    ("FOLDER PICKERS REPLACE TYPED PATHS", "COMPLETE",
     "SIX MORE TOOLS THAT ASKED FOR A TYPED PATH OR BATCH NUMBER NOW OPEN A "
     "FOLDER PICKER, REMOVING A CLASS OF TYPO FAILURES; A BUILD CHECK KEEPS "
     "NEW TOOLS ON THE PICKER"),
    ("PLANNER - MEETINGS, WAITING, TIME CAPTURE, STEPS", "COMPLETE",
     "THE PERSONAL WORK PLANNER GAINS FOUR USER-REQUESTED CAPABILITIES: "
     "SCHEDULED COMMITMENTS THE DAY IS PLANNED AROUND; A WAITING STATUS THAT "
     "HOLDS WORK OUT OF THE PLAN, NAMES WHO HOLDS IT AND PROMPTS A FOLLOW-UP; "
     "ELAPSED-TIME CAPTURE WITH TOTALS BY ITEM AND BY DAY PLUS A SPREADSHEET "
     "EXPORT; AND DATED SUB-STEPS UNDER ONE PIECE OF WORK. ALSO FREE-TEXT "
     "SEARCH AND A PER-PAGE DISPLAY SCHEME"),
    ("FOREGROUND PROMPTS + RUN NOTICES", "COMPLETE",
     "A PROMPT THAT NEEDS AN ANSWER NOW OPENS IN FRONT OF WHATEVER APPLICATION "
     "IS IN USE INSTEAD OF BEHIND IT, AND SIX TOOLS END WITH AN EXPLICIT "
     "NOTICE WHEN A RUN FAILED OR PRODUCED OUTPUT THAT WOULD MISLEAD THE NEXT "
     "STEP"),
    ("SHARED-ROUTINE CALL VERIFICATION", "COMPLETE",
     "A ROUTINE SHARED BY TWO TOOLS WAS CHANGED FOR ONE CALLER ONLY, WHICH "
     "STOPPED A 922 BATCH PREPARATION STEP FOR SIX DAYS BEFORE AN OPERATOR "
     "DIAGNOSTIC NAMED IT; FIXED THE SAME DAY, AND A BUILD CHECK NOW VERIFIES "
     "EVERY SUCH SHARED CALL (20 ACROSS FIVE TOOLS)"),
    ("911 NEST PROGRAM FILE COLLECTION", "COMPLETE",
     "911 SETUP COLLECTS EACH NEST'S MACHINE PROGRAM FILES INTO ONE FOLDER PER "
     "NEST INSTEAD OF THE OPERATOR OPENING ONE WORK-ORDER FOLDER AT A TIME; "
     "ONE FILE NAME IN SIX COLLIDES WITH ANOTHER ACROSS THE LIVE BATCHES, SO "
     "BOTH FILES ARE KEPT RATHER THAN OVERWRITTEN"),
    ("FORECAST-MISSING NEST WARNING", "COMPLETE",
     "A NEST ABSENT FROM THE SHARED FORECAST NO LONGER PRODUCES A CLEAN RUN "
     "WITH SILENTLY BLANK COLUMNS: THE THREE COLUMNS ARE HIGHLIGHTED AND "
     "ANNOTATED WITH THE NEST, THE DATE AND THE ONE STEP TO RE-RUN, AND THE "
     "RUN ENDS ON A WARNING. TWO BATCHES HAD REACHED THE FLOOR THAT WAY"),
    ("CONTINUATION PAGE REMOVAL", "COMPLETE",
     "PACKET PREPARATION DROPS THE NEAR-EMPTY CONTINUATION PAGES OPERATORS "
     "WERE DELETING BY HAND; THE RULE WAS GRADED AGAINST 394 REAL PACKETS "
     "FIRST, WHERE FOUR OF EVERY FIVE PAGES CARRYING THAT TEXT WERE GENUINE "
     "DRAWINGS THAT MUST BE KEPT"),
    ("PART-NUMBER RECOGNITION REBUILD", "COMPLETE",
     "PART-NUMBER RECOGNITION REBUILT FROM THE PART NUMBERS ON ALL 105 LIVE "
     "BATCH LISTS (5,415 VALUES) AND MOVED TO ONE SHARED DEFINITION, "
     "CORRECTING PRICING CONSOLIDATION ROWS THAT FELL BACK TO A FILE NAME AND "
     "SORTED TO THE WRONG PLACE"),
    ("SLEEP VS FREEZE DETECTION", "COMPLETE",
     "A COMPUTER GOING TO SLEEP WITH THE APPLICATION OPEN WAS RECORDED AS AN "
     "APPLICATION FREEZE; THE TWO ARE NOW DISTINGUISHED, SO A GENUINE FREEZE "
     "IS VISIBLE IN A REPORT RATHER THAN BURIED AMONG FALSE ENTRIES"),
    ("VERIFIED CARD CREATION (TWO-WAY INTEGRATION)", "COMPLETE",
     "CARD CREATION REPORTED SUCCESS WHEN THE REQUEST WAS ACCEPTED, NOT WHEN "
     "THE CARDS EXISTED - ON ONE BATCH ALL 35 CARDS FAILED AND THE RUN STILL "
     "REPORTED COMPLETE. THE INTEGRATION NOW RETURNS WHAT IT ACTUALLY DID "
     "(CREATED, ALREADY PRESENT, FAILED) AND A FAILED CARD IS OFFERED AGAIN ON "
     "THE NEXT RUN; FIRST CAPABILITY BUILT ON THE UPGRADED INTEGRATION "
     "LICENCE"),
    ("922 PRODUCTION PACKETS", "COMPLETE",
     "NEW TOOL: WORKS OUT THE SAW CUT LENGTH FOR EVERY TUBE ON A BATCH, WRITES "
     "THE CUTTING LIST THE 1D OPTIMIZER CONSUMES, AND BINDS THE SHOP PRINTS "
     "INTO ONE BINDER PER SOURCE MATERIAL; CUT-LENGTH RULES GRADED AGAINST 291 "
     "REAL PARTS ACROSS FIVE LIVE BATCHES BEFORE RELEASE. A LENGTH IT IS "
     "UNSURE OF IS FLAGGED, NEVER QUIETLY GUESSED"),
    ("PRODUCTION RUN BINDERS", "COMPLETE",
     "SECOND STAGE OF 922 PRODUCTION PACKETS, RUN AFTER THE OPERATOR'S OWN "
     "NESTING: MARKS UP EACH NEST SHEET, BUILDS A COVER PAGE PER PALLET FROM "
     "THE STANDARD PROCEDURE DOCUMENTS, AND BINDS THE PRODUCTION RUN; "
     "REPRODUCED A HAND-BUILT REFERENCE SET PAGE FOR PAGE"),
    ("TEXT-LESS WORK PACKET READ", "COMPLETE",
     "WORK PACKETS RE-PRINTED THROUGH A GENERIC PDF PRINTER LOSE THEIR "
     "MACHINE-READABLE TEXT, WHICH STOPPED PACKET MARKING ON 13 ORDERS ACROSS "
     "FIVE BATCHES; THE THREE AFFECTED TOOLS NOW READ SUCH A PAGE AS AN IMAGE. "
     "ALSO: INVOICE SUPPLEMENTS NO LONGER PRINT A NARROW DATE OR AMOUNT AS "
     "######"),
    ("KITTING PULL LIST COVER", "COMPLETE",
     "KIT PAPERWORK NOW OPENS WITH THE BATCH'S FILLED MATERIAL PULL LIST: THE "
     "STANDARD FORM IS FILLED FROM THE BATCH'S MATERIAL PLAN AND BOUND IN AS "
     "EACH KIT'S COVER PAGES, WITH THE FILLED WORKBOOK KEPT ALONGSIDE FOR HAND "
     "ADDITIONS; PREVIOUSLY BUILT BY HAND FOR EVERY BATCH"),
    ("A PRINT FOR EVERY PART MADE", "COMPLETE",
     "A BATCH MAKING THE SAME TUBE ON MORE THAN ONE ORDER WAS COUNTED ONCE, SO "
     "THE CUTTING LIST RAN A TUBE SHORT AND THE PACKET HELD ONE PRINT; EVERY "
     "PART MADE NOW GETS ITS OWN CUTTING-LIST LINE AND STAMPED PRINT. THE "
     "PALLET COVER PAGES NOW CARRY THE RIGHT BATCH NUMBER, PER-PALLET COLOURS "
     "AND SAW-CUT HIGHLIGHTING FOR MIXED-MATERIAL ORDERS"),
    ("PLATFORM 1.0 - TOOL LIBRARY + PER-TOOL DELIVERY", "PENDING",
     "NEXT PLATFORM GENERATION, CAPABILITY SIDE: EACH TOOL DELIVERED AND "
     "UPDATED ON ITS OWN FROM A LIBRARY INSIDE THE APPLICATION, SO A FIX TO "
     "ONE TOOL NO LONGER NEEDS A FULL RELEASE AND THE INSTALLER CARRIES THE "
     "PLATFORM ONLY. DIRECTION AGREED NOV 10; ONE TOOL SET PER OPERATOR IS IN "
     "PLACE AND THE DELIVERY DESIGN IS SETTLED (PER-TOOL DOWNLOAD, INTEGRITY "
     "CHECK, SWAP WITHOUT A REINSTALL); THE DELIVERY ITSELF IS NOT BUILT YET"),
    ("TRACKING RECORD CATCH-UP", "COMPLETE",
     "AUDIT OF THE THREE TRACKING WORKBOOKS FOUND THE RECORD HAD STOPPED IN "
     "SEPTEMBER WHEREVER NO SCRIPT OWNED A SHEET: THE GANTT CHART'S TASK AND "
     "PROGRESS-NOTE SHEETS, THIS LOG, AND TWO SHEETS OF THE VERSION "
     "CONTROLLER. ALL BROUGHT CURRENT, AND THE TWO UNOWNED GANTT SHEETS ARE "
     "NOW WRITTEN BY THE SYNC SCRIPT FROM VERSION CONTROL"),
    ("CUTTING LIST TOTALS AND SHEET ORDER", "COMPLETE",
     "THREE FLOOR REQUESTS ON 922 PRODUCTION PACKETS: EACH CUTTING-LIST SHEET "
     "NOW TOTALS THE TUBE LENGTH IT CALLS FOR, AS A LIVE FIGURE THAT UPDATES "
     "WHEN A LENGTH IS FILLED IN BY HAND; THE SHEETS ARE ORDERED BY PACKET "
     "NUMBER; AND THE COVER PAGES' NOTE HEADING TAKES EACH PALLET'S OWN "
     "COLOUR. EACH CHECKED READ-ONLY AGAINST A LIVE BATCH'S PLANNING FILES"),
    ("INVOICE DATE IN THE SAVED WORKBOOK", "COMPLETE",
     "THE INVOICE DATE SHOWED AS ###### IN THE SAVED INVOICE WORKBOOK; THE "
     "EARLIER CORRECTION HAD WIDENED THE COLUMN FOR THE PRINTED COPY ONLY. "
     "THE COLUMN NOW CARRIES A SET WIDTH IN THE WORKBOOK ITSELF, AND AN "
     "AUTOMATED CHECK REQUIRES A SET WIDTH ON EVERY COLUMN THE TOOL WRITES"),
    ("INSPECTION SHEET PART DESCRIPTION SAFEGUARD", "COMPLETE",
     "A TEMPLATE EDIT IN OCTOBER REMOVED THE FORMULAS THAT FILL THE PART "
     "DESCRIPTION ON THE 911 INSPECTION SHEETS, SO EVERY SHEET BUILT SINCE "
     "CARRIED THE FIELD BLANK UNLESS IT WAS TYPED IN BY HAND. BOTH TEMPLATES "
     "REPAIRED (FOUR CELLS, NOTHING ELSE). THE TOOL NOW FILLS THE FIELD "
     "ITSELF WHENEVER A TEMPLATE'S FORMULA IS MISSING AND CLOSES THE RUN "
     "WITH A NOTICE THAT THE TEMPLATE NEEDS ATTENTION"),
    ("PLANNING WORKSPACE FLOATING PANEL", "COMPLETE",
     "THE PERSONAL PLANNING WORKSPACE CAN BE LIFTED OUT INTO A FLOATING PANEL "
     "INSIDE THE APPLICATION, KEPT IN VIEW BESIDE WHICHEVER TOOL IS RUNNING; "
     "IT MOVES, RESIZES, DOCKS TO ANY EDGE AND REMEMBERS ITS PLACE. A USER "
     "REQUEST FROM OCTOBER"),
    ("PRODUCTION PACKETS STEP SELECTION", "COMPLETE",
     "922 PRODUCTION PACKETS NOW OPENS WITH THE PLATFORM'S STANDARD "
     "STEP-SELECTION WINDOW: THE OPERATOR CHOOSES WHICH STAGES RUN, WHETHER "
     "THE MARKED-UP NEST SHEETS AND COVER PAGES ARE REBUILT, AND WHICH PALLET "
     "BINDERS ARE BOUND, SO ONE BINDER CAN BE RE-MADE AFTER A HAND CORRECTION "
     "WITHOUT REWRITING THE REST. THE SHARED WINDOW (FOUR TOOLS) WAS "
     "CORRECTED ON THE WAY: A SKIPPED STAGE'S OPTIONS WERE DRAWN AS SELECTED "
     "AND COULD NOT BE CLEARED"),
]

# ---- Automation Projects Gantt Chart :: project rows ------------------------
# Full mirror of the chart's project rows ('Gantt Chart' sheet, columns A-E).
# A ("SECTION", title) entry marks one of the chart's section header rows; a
# project row is (name, status, fraction complete, start "YYYY-MM",
# end "YYYY-MM"). Duration (column F) is derived from the dates, never stored.
#
# This workbook is the one the writer must NOT round-trip through openpyxl:
# it carries VBA and conditional-formatting extension parts an openpyxl save
# strips (the calendar bars are that formatting), so the writer diffs against
# a read-only load and applies cell edits through Excel itself. See
# sync_gantt() in sync_tracking_workbooks.py.
GANTT_DONE = "Complete/ Continued Support (100% complete)"
GANTT_DEV = "Project Development"
GANTT_PLAN = "Planning (0% complete)"
GANTT_DEFERRED = "Deferred"

# Chart rows re-keyed in place (old name -> new name), applied before the
# row match so the row updates instead of duplicating. The test-count rename
# exists because a number embedded in a row NAME goes stale silently; the
# count now lives with the claim in the Version Controller, where it is read
# from a live pytest run.
GANTT_RENAMES = {
    "Automated Testing & Continuous Integration (1,312 Tests)":
        "Automated Testing & Continuous Integration",
    "Crane Inspection Tracker":
        "Crane Inspection Tracker (Cancelled by Management)",
}

# Chart rows taken OFF the chart, by exact name. The writer deletes the row.
# A row is removed only on his word, and the reason is recorded here - leaving
# a name out of GANTT_ROWS does nothing by itself, because rows the content
# does not name are never touched.
GANTT_REMOVED = [
    # The same work as the fellowship row, listed twice (2026-11-11).
    "ShipOS Implementation Lead (Navy Maritime Industrial Base)",
]

GANTT_ROWS = [
    ("SECTION", "TECHDECK — PLATFORM & INFRASTRUCTURE"),
    ("TechDeck Platform (Maintenance)", GANTT_DONE, 1, "2026-02", "2027-01"),
    ("Platform Core Rebuild (v0.8.0 Modular Architecture)",
     GANTT_DONE, 1, "2026-02", "2026-02"),
    ("UI Redesign & Live Theme Engine (v0.8.5)",
     GANTT_DONE, 1, "2026-02", "2026-05"),
    ("Theme Engine & Custom Theme Builder", GANTT_DONE, 1, "2026-02", "2026-05"),
    ("User Feedback System", GANTT_DONE, 1, "2026-03", "2026-04"),
    ("Audio Feedback System", GANTT_DONE, 1, "2026-02", "2026-05"),
    ("Plugin Card Status & Stability Program",
     GANTT_DONE, 1, "2026-03", "2026-05"),
    ("Auto-Update & Release Distribution Pipeline",
     GANTT_DONE, 1, "2026-02", "2027-01"),
    ("Command Console & Diagnostics Suite", GANTT_DONE, 1, "2026-02", "2026-08"),
    ("Presentation Mode (Client Demo Theme)",
     GANTT_DONE, 1, "2026-07", "2026-07"),
    ("Guided File Selection Overlay", GANTT_DONE, 1, "2026-07", "2026-08"),
    ("Multi-Tool Run Control & Run Engine", GANTT_DONE, 1, "2026-02", "2026-08"),
    ("Usage Telemetry & Feedback Delivery", GANTT_DONE, 1, "2026-07", "2026-08"),
    ("Recognition & Rewards System", GANTT_DONE, 1, "2026-06", "2026-08"),
    ("Desktop Widget Line & Widget Builder",
     GANTT_DONE, 1, "2026-07", "2026-08"),
    ("922 Dashboard Widget (TechDeck)", GANTT_DONE, 1, "2026-02", "2026-06"),
    ("911 Dashboard Widget (TechDeck)", GANTT_DONE, 1, "2026-02", "2026-06"),
    # Meetings, waiting, time capture and steps shipped 0.8.7.9 (Oct 14).
    # The floating panel was built Nov 20 (rides 0.8.11).
    ("Personal Planning Workspace (Assistant)",
     GANTT_DONE, 1, "2026-07", "2026-11"),
    # The CAPABILITY side of 1.0, not the look: tools delivered and updated one
    # at a time. His call 2026-11-11 - "focus on the capability aspects of it,
    # not so much the UI". 0.15 = the design is settled and the one-tool-set
    # groundwork is in; delivery itself is unbuilt. Finish month is a
    # placeholder until he sets one.
    ("TechDeck 1.0 Platform (Tool Library & Per-Tool Updates)",
     GANTT_DEV, 0.15, "2026-09", "2027-03"),
    ("SECTION", "ENGINEERING & RELIABILITY PROGRAMS"),
    ("Reliability Hardening (OneDrive, Cancellation, Settings, Errors)",
     GANTT_DONE, 1, "2026-06", "2026-09"),
    # Suite grew 1,312 -> 2,765 between Sep 1 and the 0.8.10 release.
    ("Automated Testing & Continuous Integration",
     GANTT_DONE, 1, "2026-07", "2026-11"),
    # Guarded publish script + verified backup + published-copy gates (Sep).
    ("Security & Publishing Controls", GANTT_DONE, 1, "2026-07", "2026-09"),
    # Runtime-component, release-inventory (Sep) and shared-call (Oct) gates.
    ("Build & Ship Quality Gates", GANTT_DONE, 1, "2026-06", "2026-10"),
    # Sleep-vs-freeze detection shipped 0.8.8 (Oct 21).
    ("Diagnostics & Supportability", GANTT_DONE, 1, "2026-06", "2026-10"),
    # Six more folder pickers (0.8.7.8), foreground prompts (0.8.7.9) - Oct.
    ("Usability Standardization (Shared Prompts, Folder-Pick Entry)",
     GANTT_DONE, 1, "2026-06", "2026-10"),
    ("Long-Path (MAX_PATH) Platform-Wide Fix",
     GANTT_DONE, 1, "2026-08", "2026-09"),
    ("Performance Profiling & Cloud Prefetch",
     GANTT_DONE, 1, "2026-08", "2026-09"),
    ("SECTION", "911 QTDR WORKFLOW AUTOMATION"),
    # Plate batches (0.8.7.4), verification sheet (0.8.7.7), program-file
    # collection and the forecast warning (0.8.8, Oct 21).
    # v2.6.0 (Part Description safeguard) was built Nov 19, rides 0.8.11.
    ("911 Setup", GANTT_DONE, 1, "2026-02", "2026-11"),
    # Verified card creation (two-way integration) shipped 0.8.8.
    ("911 Teams Cards", GANTT_DONE, 1, "2026-07", "2026-10"),
    ("911 Batch Repeater", GANTT_DONE, 1, "2026-03", "2026-07"),
    # Sketch repair + material designation (0.8.7.6), continuation pages
    # (0.8.8).
    ("911 Remove Ticket", GANTT_DONE, 1, "2026-03", "2026-10"),
    ("911 PO PDF Extractor (Support)", GANTT_DONE, 1, "2026-02", "2027-01"),
    ("911 Sketch Extractor (Support)", GANTT_DONE, 1, "2026-02", "2027-01"),
    ("911 LST Organizer", GANTT_DONE, 1, "2026-06", "2026-09"),
    ("911 Baked Beans Wild Ride (NC Pricing Consolidation)",
     GANTT_DONE, 1, "2026-07", "2026-07"),
    # Partial shipments (0.8.7.8), narrow-date print fix (0.8.9, Nov 3).
    ("911 SSPO Invoicing Prep", GANTT_DONE, 1, "2026-06", "2026-11"),
    ("911 SSPO Award Review", GANTT_DONE, 1, "2026-06", "2026-07"),
    ("911 Data Extraction", GANTT_DONE, 1, "2026-02", "2026-04"),
    ("911 Data Organizer", GANTT_DONE, 1, "2026-02", "2026-07"),
    # Shipped 0.8.7.1, corrected and validated through 0.8.7.2.1; only field
    # confirmations remain, which is support, not development.
    ("911 Inspection Dimensions (Drawing Dimension OCR)",
     GANTT_DONE, 1, "2026-08", "2026-09"),
    # New app, shipped 0.8.7.3 (Sep 2, 2026).
    ("911 Scripting Prep", GANTT_DONE, 1, "2026-09", "2026-09"),
    ("SECTION", "922 QTDR WORKFLOW AUTOMATION"),
    # Repeat identification (0.8.7.5), labels on existing cards (0.8.7.8),
    # text-less packet read (0.8.9, Nov 3).
    ("922 Setup (Folder Build, Teams Cards, Stage Orchestration)",
     GANTT_DONE, 1, "2026-03", "2026-11"),
    ("922 Batch Repeater (Support + Catalog Rebuild)",
     GANTT_DONE, 1, "2026-02", "2027-01"),
    ("922 Pallet Stamper (Support)", GANTT_DONE, 1, "2026-02", "2027-01"),
    ("922 LST Organizer (Support + v3 Rebuild)",
     GANTT_DONE, 1, "2026-02", "2027-01"),
    ("922 FormingFinder", GANTT_DONE, 1, "2026-04", "2026-10"),
    # Material pull list cover shipped 0.8.10 (Nov 11).
    ("922 Kitting", GANTT_DONE, 1, "2026-04", "2026-11"),
    ("922 Difficulty Stamper", GANTT_DONE, 1, "2026-08", "2026-11"),
    ("922 Runtime Genie", GANTT_DONE, 1, "2026-04", "2026-05"),
    ("922 Master Parts Catalog", GANTT_DONE, 1, "2026-07", "2026-07"),
    # First commit 2026-10-26; shipped 0.8.9 (Nov 3), extended 0.8.10.
    ("922 Production Packets", GANTT_DONE, 1, "2026-10", "2026-11"),
    ("Flat Bar Forming Support", GANTT_DONE, 1, "2026-08", "2026-09"),
    ("SECTION", "902 QTDR WORKFLOW"),
    ("902 DXF Prep", GANTT_DONE, 1, "2026-06", "2026-07"),
    ("902 Batch Validator", GANTT_DONE, 1, "2026-09", "2026-09"),
    ("902 Documentation & Paperwork Rebuild (Automation Prep)",
     GANTT_DEV, 0.6, "2026-08", "2026-10"),
    ("902 Setup App Suite (Mirrors 911/922 Toolchains)",
     GANTT_PLAN, 0, "2026-08", "2026-10"),
    ("SECTION", "QUALITY, ESTIMATING & SHOP TOOLS"),
    # Closed as complete by him, 2026-11-11.
    ("Customer DXF Analysis (Quoting + Automated Offsets)",
     GANTT_DONE, 1, "2026-02", "2026-09"),
    ("Sheet Metal Calculators", GANTT_DONE, 1, "2026-07", "2026-07"),
    ("MieTrak Tools (Hardware Code Generator)", GANTT_DONE, 1, "2026-09", "2026-09"),
    ("Batch Auditor", GANTT_DONE, 1, "2026-05", "2026-06"),
    ("QA Gemba Analyzer", GANTT_DONE, 1, "2026-06", "2026-07"),
    ("QR Code Generator (Support)", GANTT_DONE, 1, "2026-02", "2027-01"),
    # Cancelled by management (his word, 2026-11-11). It stays on the chart
    # as a record, at the completion it had reached when it stopped.
    ("Crane Inspection Tracker (Cancelled by Management)",
     GANTT_DEFERRED, 0.75, "2026-02", "2026-10"),
    ("SECTION", "DRIVEWORKS & DESIGN AUTOMATION"),
    ("DriveWorks Automation (Support)", GANTT_DONE, 1, "2026-02", "2027-01"),
    ("DriveWorks Difficulty Layer (Compound-Cut Flagging, TUBE + CLEVIS)",
     GANTT_DONE, 1, "2026-08", "2026-08"),
    ("DriveWorks Flat-Bar Forming Rules (Formed-Part File Naming)",
     GANTT_DONE, 1, "2026-08", "2026-08"),
    ("DriveWorks Plate Project Overhaul", GANTT_DONE, 1, "2026-08", "2026-08"),
    ("DriveWorks Data Export & Inspection Sheet Automation",
     GANTT_DEV, 0.05, "2026-08", "2026-09"),
    ("DriveWorks Project Rule Audit & Documentation (11 Projects)",
     GANTT_DEV, 0.5, "2026-08", "2026-09"),
    ("SECTION", "CAD / NC / DXF RESEARCH & DATA"),
    ("NC-1 G Code Automation", GANTT_DEFERRED, 0, "2026-02", "2027-02"),
    ("NC-to-SolidWorks Conversion Feasibility Study",
     GANTT_DONE, 1, "2026-02", "2026-03"),
    # Both closed as complete by him, 2026-11-11.
    ("DXF Linear-Inch Measurement Engine",
     GANTT_DONE, 1, "2026-02", "2026-07"),
    ("DSTV / NC File Format Study (SolidWorks Integration)",
     GANTT_DONE, 1, "2026-02", "2026-09"),
    ("911 Master Parts List", GANTT_DONE, 1, "2026-02", "2026-07"),
    ("Throughput-Based Cut Estimating", GANTT_DONE, 1, "2026-07", "2026-07"),
    ("EB Bevel Book Transcription (947 Reference Prints)",
     GANTT_DONE, 1, "2026-08", "2026-09"),
    ("SECTION", "SHIPOS / PALANTIR FOUNDRY"),
    # "ShipOS Implementation Lead" was the same work as the fellowship row
    # below; he kept this one (2026-11-11). See GANTT_REMOVED.
    # All six courses finished 2026-11-04, which is the training half of the
    # program; the capstone half runs to the final presentation, week of
    # 2027-01-18 (Cohort 7 Capstone Guide). 0.5 = coursework done, capstone
    # not yet built - HIS number to move, like every completion on this chart.
    ("American Tech Fellowship (Palantir Foundry, 12-Week Program)",
     GANTT_DEV, 0.5, "2026-10", "2027-01"),
    # Scoped and proposed; nothing built yet. 0.1 is the scoping share.
    ("Fellowship Capstone (Foundry Workflow on ASA Production Data)",
     GANTT_DEV, 0.1, "2026-10", "2027-01"),
    ("SECTION", "PLANNED / UPCOMING"),
    # The illustrated User Guide IS this project. It shipped in 0.8.7.5 and
    # is rebuilt and updated with every release, so it is complete and its bar
    # runs to the latest release (his call, 2026-11-11: "yes and ongoing").
    ("922/911 Quick Reference Library (TechDeck)",
     GANTT_DONE, 1, "2026-09", "2026-11"),
    ("Engineering Change (ECR/ECO/ECN) Generator",
     GANTT_PLAN, 0, "2027-03", "2027-05"),
    # Not before 2027 (his word, 2026-11-11); same length, moved out.
    ("922 PO Builder", GANTT_PLAN, 0, "2027-01", "2027-04"),
    ("922 Quote Builder", GANTT_PLAN, 0, "2026-10", "2027-01"),
    ("Automated 922 Rod Tags", GANTT_PLAN, 0, "2027-01", "2027-03"),
    ("Code Signing Certificate", GANTT_PLAN, 0, "2026-09", "2026-10"),
    ("EB Quoting Automation", GANTT_PLAN, 0, "2026-12", "2027-08"),
    ("EB Batch Setup Full Automation", GANTT_PLAN, 0, "2027-02", "2027-11"),
]


# ---- Automation Projects Gantt Chart :: 'Engineering Tasks' sheet -----------
# The chart's task list (table ToDoList23, columns B-K). It is the three
# Version Controller sheets merged and date-sorted, plus the work that is not
# TechDeck (DriveWorks, 902 paperwork, the fellowship). Until 2026-11-11 no
# script owned it, so it stopped on Sep 1 while ten releases went by - the same
# drift the chart's project rows had before GANTT_ROWS existed.
#
# A row is (task, priority, status, start, due, fraction complete, done,
# notes, production update, subject). Dates are "YYYY-MM-DD"; `due`, the
# fraction, `done` and the subject may be None, which leaves that cell EMPTY -
# an unknown is left blank, never estimated. Rows are matched on the task
# name, so a row already on the sheet is updated in place and only new ones
# are appended, in list order: keep the list in date order, add at the bottom.
#
# Only rows named here are touched. Everything logged by hand before
# 2026-09-02 stays exactly as it was written.
TASK_DONE, TASK_OPEN, TASK_TODO = "Complete", "In Progress", "Not Started"
SUBJECT_TOOLS = "Automation Tools"
SUBJECT_FEATURES = "System Features"
SUBJECT_ENGINEERING = "Engineering & Reliability"


def _eng_task(initiative, start, due, priority="High"):
    """A task row built from the ENGINEERING entry of that name, so the two
    workbooks cannot describe one initiative two different ways."""
    for _date, name, category, what, value, _scope in ENGINEERING:
        if name == initiative:
            return (name, priority, TASK_DONE, start, due, 1, 1,
                    f"[{category}] {what}", value, SUBJECT_ENGINEERING)
    raise KeyError(f"no ENGINEERING entry named {initiative!r}")


def _feature_task(feature, start, due, priority="Normal"):
    """Same, from a SYSTEM_FEATURES entry."""
    for name, what, value, _status in SYSTEM_FEATURES:
        if name == feature:
            return (name, priority, TASK_DONE, start, due, 1, 1,
                    what, value, SUBJECT_FEATURES)
    raise KeyError(f"no SYSTEM_FEATURES entry named {feature!r}")


GANTT_TASKS = [
    _eng_task("Packaging Check for Runtime-Loaded Components",
              "2026-09-01", "2026-09-01"),
    _eng_task("Guarded Publishing & Repository Backup",
              "2026-09-01", "2026-09-01"),
    _eng_task("Published-Copy Verification", "2026-09-01", "2026-09-30"),
    ("911 Scripting Prep", "High", TASK_DONE, "2026-09-02", "2026-09-04", 1, 1,
     "New tool. Builds the two-sheet SSPO ERP scripting workbook from a "
     "finished award review and the Working Forecast List, instead of typing "
     "it out line by line.",
     "Lines the tool cannot resolve are listed inside the same file with the "
     "reason. Values shared across an order line are entered once and "
     "propagate to every line (added Sep 4).",
     SUBJECT_TOOLS),
    ("911 Setup - Plate Batch Preparation", "High", TASK_DONE,
     "2026-09-03", "2026-09-04", 1, 1,
     "911 batch setup now prepares plate work as well as structural shapes: "
     "the plate workbook and plate verification form, with the material "
     "specification recorded as not applicable on carbon plate - decided by "
     "the ferrous flag the shop paperwork itself carries - and the "
     "traceability number carried from the forecast.",
     "Plate batches were previously prepared by hand around the tool. The "
     "plate selection deliberately does not persist, so a prior plate run can "
     "never apply plate paperwork to a shape batch.",
     SUBJECT_TOOLS),
    _feature_task("Integrated User Manual", "2026-09-04", "2026-09-11"),
    ("TechDeck 1.0 - Tool Library & Per-Tool Updates", "High", TASK_OPEN,
     "2026-09-09", None, 0.15, None,
     "The next platform generation, on the capability side: each automation "
     "tool becomes content delivered and updated on its own from a library "
     "inside the application, instead of every tool shipping inside one "
     "installer. A fix to one tool no longer needs a full release, and the "
     "installer carries the platform only.",
     "Direction agreed Nov 10, 2026. Groundwork in place: one tool set per "
     "operator replaces the older grouped sets, and the delivery design is "
     "settled (per-tool download, integrity check, swap without a reinstall). "
     "The delivery itself is not built yet.",
     SUBJECT_FEATURES),
    ("922 Setup - Repeat Identification & Progress Checklist", "High",
     TASK_DONE, "2026-09-11", "2026-09-11", 1, 1,
     "922 batch setup records the batch in the master parts list and "
     "identifies repeat orders at the start of the run, so each repeat's "
     "coordination card is created already labelled and already in the "
     "model-check stage.",
     "Cards were previously created plain and re-tagged in a later pass. The "
     "tool also creates the batch's fourteen-step progress checklist card, "
     "which was made by hand on every batch.",
     SUBJECT_TOOLS),
    ("Weekly Invoicing Reports Automation", "High", TASK_DONE,
     "2026-09-11", "2026-09-11", 1, 1,
     "Invoicing preparation takes a copy of the entire pricing master and a "
     "close-out date range instead of a sheet trimmed to the week by hand, "
     "and produces both weekly reports - the work order close outs and the "
     "material status listing - alongside the invoicing packages.",
     "Replaces two documents previously rebuilt by hand every week.",
     SUBJECT_TOOLS),
    ("911 Invoice Supplement Automation", "High", TASK_DONE,
     "2026-09-16", "2026-09-17", 1, 1,
     "Invoicing preparation fills the invoice number and ship date on the "
     "supplement from the working forecast, prints the supplement to PDF "
     "beside the invoice, and gathers each nest's pricing calculations into "
     "its invoicing folder.",
     "A nest with no invoice number is left blank and named rather than "
     "printed - nothing ships without an invoice number.",
     SUBJECT_TOOLS),
    ("MieTrak Tools", "High", TASK_DONE, "2026-09-17", "2026-09-17", 1, 1,
     "New tool. A picker window of small MieTrak helpers; the first, the "
     "Hardware Code Generator, builds a hardware part number from dropdown "
     "picks and copies it to the clipboard.",
     "Replaces a standalone program left behind by a departed colleague. Its "
     "code tables were kept verbatim and are covered by automated tests, so "
     "the numbers keep matching.",
     SUBJECT_TOOLS),
    ("911 Part Sketch Repair & Material Designation", "High", TASK_DONE,
     "2026-09-17", "2026-09-17", 1, 1,
     "Part sketch pages that lost their drawing on the report server are "
     "filled back in from the batch's own sketch library, and the material "
     "designation is written on every part sketch.",
     "The shop can scribe from the print, and a blank sketch page no longer "
     "has to be patched by hand.",
     SUBJECT_TOOLS),
    _eng_task("Release Content Inventory", "2026-09-18", "2026-09-18",
              priority="Normal"),
    ("902 Batch Validator", "High", TASK_DONE, "2026-09-21", "2026-09-21", 1, 1,
     "New tool. On the day a 902 batch arrives it reports which parts are not "
     "ready to work: no drawing file, a drawing file that holds no geometry, "
     "a damaged model file, or no print. Read-only - no file in the batch is "
     "moved or altered.",
     "One report goes back to the customer as a single request instead of a "
     "part at a time; over three thousand parts were on hold waiting on a "
     "handful of files when this was commissioned. Validated against "
     "fourteen received batches.",
     SUBJECT_TOOLS),
    ("911 Scribe Verification Sheet Corrections", "High", TASK_DONE,
     "2026-09-21", "2026-09-21", 1, 1,
     "The scribe verification table was fixed at twenty-four rows and "
     "silently omitted parts beyond that on larger nests. It now matches the "
     "nest's part count, lists parts in nest-package order, takes quantities "
     "from the nest package where it disagrees with the batch list, and fills "
     "the material specification per part for non-ferrous plate.",
     "No part is left off the verification sheet, and a quantity check that "
     "had never run on plate work is fixed.",
     SUBJECT_TOOLS),
    ("922 Setup - Material Labels on Existing Cards", "High", TASK_DONE,
     "2026-09-25", "2026-10-05", 1, 1,
     "Batch setup applies source-material labels to coordination cards that "
     "already exist, so a re-run completes a partly labelled board instead of "
     "skipping it.",
     "Reported by an operator whose cards already existed and so never "
     "received their material labels.",
     SUBJECT_TOOLS),
    ("911 Partial-Shipment Invoicing", "High", TASK_DONE,
     "2026-09-28", "2026-10-05", 1, 1,
     "Each partial shipment of a nest gets its own invoice number and ship "
     "date, matched by sub-group and close-out week. Previously every "
     "shipment of a split nest received the first shipment's values.",
     "A nest the tool cannot resolve is left blank and named rather than "
     "guessed.",
     SUBJECT_TOOLS),
    ("922 Part-Number Reconciliation (PO vs Drawing)", "High", TASK_DONE,
     "2026-10-05", "2026-10-14", 1, 1,
     "The 922 forming, kitting and nest-file tools reconcile a purchase-order "
     "part number that disagrees with its drawing number.",
     "Closes a gap that produced unlabelled formed parts, wrongly stamped rod "
     "lines and false missing-tube reports.",
     SUBJECT_TOOLS),
    ("922 Proven Work-Packet Stamping", "High", TASK_DONE,
     "2026-10-05", "2026-10-05", 1, 1,
     "The two packet-marking tools stamp only a document proven to be the "
     "work packet, and clean stray stamps off sketches and prints.",
     "Six of 252 orders across four batches had been mis-stamped.",
     SUBJECT_TOOLS),
    _feature_task("Seasonal Themes & What's-New Markers",
                  "2026-10-05", "2026-10-05"),
    ("Personal Planning Workspace - Meetings, Waiting, Time Capture, Steps",
     "Normal", TASK_DONE, "2026-10-09", "2026-10-14", 1, 1,
     "The personal work planner gains scheduled commitments the day is "
     "planned around, a waiting status that holds work out of the plan and "
     "prompts a follow-up, elapsed-time capture with totals by item and by "
     "day, dated sub-steps under one piece of work, and free-text search.",
     "Built entirely from user requests. Answers where the week went from "
     "recorded time rather than recollection.",
     SUBJECT_FEATURES),
    _feature_task("Foreground Prompts & Run Notices",
                  "2026-10-14", "2026-10-14"),
    ("American Tech Fellowship - Coursework (6 Courses)", "High", TASK_DONE,
     "2026-10-16", "2026-11-04", 1, 1,
     "All six courses of the Palantir Foundry fellowship completed: platform "
     "overview, data transformation (without code and in Python), ontology "
     "development, application building, the checkpoint exercises, and AI "
     "and automation. The final course's issue-to-work-order automation ran "
     "end to end and was verified live.",
     "Completes the training half of the program. The capstone - a real "
     "workflow built on company data - is the second half.",
     None),
    ("American Tech Fellowship - Capstone Project", "High", TASK_OPEN,
     "2026-10-19", "2027-01-18", 0.1, None,
     "A production workflow built in the company's own Foundry environment "
     "on real work data. Requirements gathered with production management, "
     "the target system scoped end to end (Nov 4), and the written proposal "
     "prepared for the Nov 9 submission deadline.",
     "Program milestones: midpoint check-in the week of Dec 1, program break "
     "Dec 15 to Jan 6, demo dry run the week of Jan 11, final presentation to "
     "Palantir engineers and company leadership the week of Jan 18, 2027.",
     None),
    _eng_task("Shared-Routine Call Verification", "2026-10-20", "2026-10-20"),
    ("911 Nest Program File Collection", "High", TASK_DONE,
     "2026-10-20", "2026-10-21", 1, 1,
     "911 batch setup collects each nest's machine program files into a "
     "single folder per nest, instead of the operator opening one work-order "
     "folder at a time across a batch.",
     "A survey of every live batch found one file name in six collides with "
     "another, so the collection keeps both files rather than overwriting - "
     "which the manual method could not guarantee.",
     SUBJECT_TOOLS),
    ("911 Forecast-Missing Nest Warning", "High", TASK_DONE,
     "2026-10-20", "2026-10-21", 1, 1,
     "A nest absent from the shared forecast no longer produces a clean run: "
     "the three affected columns are highlighted and annotated in the "
     "workbook with the nest, the date and the one step to re-run, and the "
     "run closes as a warning.",
     "Two batches had reached the floor with silently blank columns and a "
     "clean result. The columns stay blank - nothing is guessed.",
     SUBJECT_TOOLS),
    ("911 Continuation Page Removal", "High", TASK_DONE,
     "2026-10-20", "2026-10-21", 1, 1,
     "Packet preparation drops the near-empty continuation pages operators "
     "were deleting by hand.",
     "The rule was graded against 394 real packets first, where four of "
     "every five pages carrying that text turned out to be genuine drawings "
     "that must be kept.",
     SUBJECT_TOOLS),
    _eng_task("Part-Number Recognition Rebuild", "2026-10-20", "2026-10-21"),
    _eng_task("Sleep vs Freeze Detection", "2026-10-20", "2026-10-21"),
    _eng_task("Verified Integration Results", "2026-10-21", "2026-10-21"),
    ("922 Production Packets", "High", TASK_DONE,
     "2026-10-26", "2026-11-03", 1, 1,
     "New tool. Works out the saw cut length for every tube on a batch, "
     "writes the cutting list the 1D optimizer consumes, and binds the shop "
     "prints into one binder per source material.",
     "Cut-length rules were graded against 291 real parts across five live "
     "batches before release. A length the tool is unsure of is flagged for "
     "a decision, never quietly guessed.",
     SUBJECT_TOOLS),
    ("922 Production Packets - Production Run Binders", "High", TASK_DONE,
     "2026-11-02", "2026-11-03", 1, 1,
     "A second stage, run after the operator's own nesting: marks up each "
     "nest sheet, builds a cover page per pallet from the standard procedure "
     "documents, and binds the production run.",
     "Reproduced a hand-built reference set of binders page for page.",
     SUBJECT_TOOLS),
    _eng_task("Optical Reading of Text-Less Work Packets",
              "2026-11-02", "2026-11-03"),
    ("American Tech Fellowship - AI Implementation Homework (Levels 0-4)",
     "Normal", TASK_OPEN, "2026-11-04", None, 0, None,
     "Five practice assignments on the fellowship's AI maturity ladder: data "
     "processing, search and visualization, decision guidance, feedback "
     "loops, and AI-driven automation.",
     "Worked alongside the capstone as hands-on practice in building from a "
     "blank page.",
     None),
    ("922 Kitting - Material Pull List Cover", "High", TASK_DONE,
     "2026-11-09", "2026-11-11", 1, 1,
     "Kit paperwork now opens with the batch's filled material pull list: "
     "the standard form is filled from the batch's material plan and bound "
     "in as each kit's cover pages, with the filled workbook kept alongside "
     "for hand additions.",
     "The pull list was previously built by hand for every batch.",
     SUBJECT_TOOLS),
    ("922 Production Packets - A Print for Every Part Made", "High",
     TASK_DONE, "2026-11-09", "2026-11-11", 1, 1,
     "A batch making the same tube on more than one order was counted once, "
     "so the cutting list ran one tube short and the packet carried a single "
     "print. Every part made now gets its own cutting-list line and stamped "
     "print, grouped behind each order's own assembly sheet.",
     "The per-pallet cover pages now also carry the correct batch number, "
     "per-pallet colour coding, and saw-cut highlighting for mixed-material "
     "orders.",
     SUBJECT_TOOLS),
    ("922 Production Packets - Cutting List Totals, Sheet Order, Cover Colours",
     "Normal", TASK_DONE, "2026-11-16", "2026-11-18", 1, 1,
     "Each cutting-list sheet totals the tube length it calls for, as a live "
     "figure that updates when a length is filled in by hand. The sheets are "
     "ordered by packet number, and the cover pages' note heading takes each "
     "pallet's own colour.",
     "Three requests from the floor. Each was checked against a live batch's "
     "own planning files, read-only, before it was called done. Rides the "
     "next release.",
     SUBJECT_TOOLS),
    ("911 SSPO Invoicing Prep - Invoice Date in the Saved Workbook", "High",
     TASK_DONE, "2026-11-18", "2026-11-18", 1, 1,
     "The invoice date showed as ###### in the saved workbook. The earlier "
     "correction widened the column for the printed copy only; the column "
     "now carries a set width in the workbook itself.",
     "An automated check now requires a set width on every column the tool "
     "writes, so the same fault cannot return on another column. Rides the "
     "next release.",
     SUBJECT_TOOLS),
    ("911 Setup - Inspection Sheet Part Description Safeguard", "High",
     TASK_DONE, "2026-11-19", "2026-11-19", 1, 1,
     "The Part Description on the inspection sheets was filled by formulas "
     "in the template, and a template edit in October had removed them. The "
     "tool now fills the field itself whenever a template's formula is "
     "missing, and closes the run with a notice that the template needs "
     "attention.",
     "Both templates were repaired the same day, changing only the four "
     "affected cells. The template stays in charge; the tool's own write is "
     "the backup. Rides the next release.",
     SUBJECT_TOOLS),
    ("Personal Planning Workspace - Floating Panel", "Normal", TASK_DONE,
     "2026-11-20", "2026-11-20", 1, 1,
     "The personal work planner can be lifted out into a floating panel "
     "inside the application, kept in view beside whichever tool is running. "
     "It moves, resizes, docks to any edge and remembers its place.",
     "A user request from October: keep the plan visible while running "
     "tools. Rides the next release.",
     SUBJECT_FEATURES),
    ("922 Production Packets - Step Selection Window", "Normal", TASK_DONE,
     "2026-11-23", "2026-11-23", 1, 1,
     "The tool opens with the platform's standard step-selection window. "
     "The operator chooses which stages run, whether the marked-up nest "
     "sheets and cover pages are rebuilt, and which pallet binders are "
     "bound.",
     "One binder can be re-made after a hand correction without rewriting "
     "the rest. The shared window was corrected on the way: a skipped "
     "stage's options were drawn as selected and could not be cleared. "
     "Rides the next release.",
     SUBJECT_TOOLS),
]


# Hand-written task rows whose STATUS has moved. These rows were logged by
# hand and their text is not in version control, so only the cells named here
# change: (task name, status, fraction complete, done). None leaves that cell
# exactly as it is on the sheet. A name here must not also be in GANTT_TASKS.
TASK_CANCELLED = "Cancelled"
GANTT_TASK_STATUS = [
    # Cancelled by management (his word, 2026-11-11); stopped at 75%.
    ("Crane Inspection Tracker", TASK_CANCELLED, None, None),
    # Closed as complete by him, 2026-11-11.
    ("Customer DXF System Improvements (Round 2)", TASK_DONE, 1, 1),
]


# ---- Automation Projects Gantt Chart :: 'Progress Notes' sheet --------------
# The narrative build log: the good, the bad and the ugly, one row per event.
# A row is (date "YYYY-MM-DD", subject, type, what happened, resolution /
# outcome); type is one of NOTE_TYPES. Rows are matched on subject AND date,
# updated in place if already there and otherwise appended in list order -
# keep the list in date order. A new row is INSERTED where its date belongs,
# so a note logged late still reads in order. Like the task list, this sheet
# had no script behind it until 2026-11-11 and stopped on Sep 1.
NOTE_TYPES = ("Milestone", "Problem", "Decision", "Unresolved")

GANTT_NOTES = [
    ("2026-09-01", "Inspection Reader Missing From the Build", "Problem",
     "The 0.8.7.2 release shipped without the image-recognition component "
     "the inspection-data tool depends on: the component loads its own parts "
     "by name while running, which the packaging step cannot see. In the "
     "field the tool returned nothing and reported the drawings as "
     "containing no sketch pages.",
     "Corrective release 0.8.7.2.1 issued the same day and re-validated on "
     "the reporting packet (122 dimensions, 24 parts, 19 inspection sheets). "
     "A build check now reads the component's own configuration, and a "
     "component that cannot start is reported as such."),
    ("2026-09-01", "Publishing Rewrote the Working History", "Problem",
     "While publishing a release, the history filter was run in the working "
     "repository instead of an isolated copy. It rewrote the development "
     "history in place and removed the internal documentation from it.",
     "Fully recovered from a copy an earlier step had left behind. "
     "Publishing is now a single script that takes a verified backup first "
     "and refuses to run anywhere but an isolated copy."),
    ("2026-09-02", "TechDeck v0.8.7.3 Release", "Milestone",
     "Release cut and pushed live: the new 911 Scripting Prep tool builds "
     "the SSPO ERP scripting workbook from a finished award review, and the "
     "purchase-order extraction tool was reinstated after being withdrawn in "
     "error - the two serve opposite directions.",
     "Live to the team. The scripting sheet arrives filled in rather than "
     "transcribed, with unresolved lines listed in the same file."),
    ("2026-09-04", "TechDeck v0.8.7.4 Release", "Milestone",
     "Release cut and pushed live: 911 batch setup prepares plate work as "
     "well as shapes, the scripting tool takes shared order-line values "
     "once, and the difficulty marker is preserved on part drawings.",
     "Live to the team. Plate batches are no longer prepared by hand around "
     "the tool."),
    ("2026-09-04", "Public Build Failed After Publishing", "Problem",
     "For the third time, a release's public build failed immediately after "
     "publishing on something that passed locally. The published copy is a "
     "filtered rebuild - names are rewritten and private files removed - so "
     "its code and tests can differ from the development copy.",
     "Two build checks now reproduce the filter locally: one compiles every "
     "published file after the name scrub, one fails any test that reads a "
     "file the filter removes. The failure is found before anything leaves."),
    ("2026-09-11", "TechDeck v0.8.7.5 Release", "Milestone",
     "Release cut and pushed live: 922 batch setup identifies repeat orders "
     "at the start of the run and creates the batch's progress checklist "
     "card; invoicing preparation produces both weekly reports from the "
     "pricing master; a complete illustrated user manual ships inside the "
     "application.",
     "Live to the team. The manual is regenerated by every build, so it "
     "cannot fall behind the software."),
    ("2026-09-17", "TechDeck v0.8.7.6 Release", "Milestone",
     "Release cut and pushed live: the new MieTrak Tools window (Hardware "
     "Code Generator); invoice number, ship date and a supplement PDF on the "
     "invoicing packages; part sketch pages repaired from the batch's sketch "
     "library, with the material designation written on each.",
     "Live to the team."),
    ("2026-09-18", "New Tool Left Out of the Announcement", "Problem",
     "The 0.8.7.6 announcement named a whole new tool nowhere: the notes had "
     "been built from the feedback log, and the tool had no request behind "
     "it.",
     "A follow-up announcement went out. The shipping list is now read from "
     "the code history, and the build fails if a new tool is not named in "
     "the release record."),
    ("2026-09-21", "TechDeck v0.8.7.7 Release", "Milestone",
     "Release cut and pushed live: the new 902 Batch Validator reports, on "
     "the day a batch arrives, which parts are not ready to work; the 911 "
     "scribe verification sheet now fits the nest's part count.",
     "Live to the team. Validated against fourteen received 902 batches and "
     "the program's own delay log."),
    ("2026-09-21", "Verification Sheet Dropped Parts Past 24", "Problem",
     "Reported from the floor: the scribe verification table ran out of "
     "lines on larger batches. The table was fixed at twenty-four rows in "
     "both templates, so part 25 onward was silently omitted.",
     "The table now matches the nest's part count in both directions. The "
     "same review found a quantity check that had never run on plate work, "
     "also fixed."),
    ("2026-10-05", "TechDeck v0.8.7.8 Release", "Milestone",
     "Release cut and pushed live: material labels applied to existing "
     "coordination cards; an invoice number and ship date per partial "
     "shipment; part-number reconciliation across the 922 forming, kitting "
     "and nest-file tools; packet marking restricted to a proven work "
     "packet; six more tools take a folder pick instead of a typed path; a "
     "seasonal display theme.",
     "Live to the team."),
    ("2026-10-05", "Release Verified in Parts, Failed Whole", "Problem",
     "The test suite passed folder by folder but crashed when run as one "
     "process, which is how the build gate and the public check run it. The "
     "cause was a test fixture, not the product, and it surfaced after the "
     "release had been published.",
     "A release now starts by proving the whole suite green in a single "
     "process before anything else is done."),
    ("2026-10-14", "TechDeck v0.8.7.9 Release", "Milestone",
     "Release cut and pushed live: the personal work planner gains meetings, "
     "a waiting status, time capture and reporting, sub-steps and search; "
     "prompts open in front of whatever application is in use; six tools end "
     "with an explicit notice when a run needs attention.",
     "Live to the team. Built entirely from user requests."),
    ("2026-10-20", "922 Setup Stage Broken for Six Days", "Problem",
     "An operator diagnostic showed 922 batch preparation could not complete "
     "its parts-list and repeat-detection step. A routine two tools share "
     "had been changed for one caller only, and because the connection is "
     "made while a tool runs, no build check could see it.",
     "Fixed the same day. A new build check verifies every shared call - "
     "twenty across five tools - so the class cannot recur."),
    ("2026-10-20", "Blank Forecast Columns Reported as a Clean Run", "Problem",
     "Two 911 batches reached the floor with three columns silently blank: "
     "the nests were not yet in the shared forecast when they were set up, "
     "and the tool warned only in a log while reporting a clean run.",
     "The columns are now highlighted and annotated in the workbook with the "
     "nest, the date and the one step to re-run, and the run ends on a "
     "warning. The columns stay blank - nothing is guessed."),
    ("2026-10-20", "American Tech Fellowship - Courses 1 to 3 Complete",
     "Milestone",
     "First three courses of the Palantir Foundry fellowship finished: "
     "platform overview, data transformation (pipelines without code and "
     "Python transforms), and ontology development (object, link and action "
     "types).",
     "Capstone requirements gathering with production management began the "
     "same week."),
    ("2026-10-21", "TechDeck v0.8.8 Release", "Milestone",
     "Release cut and pushed live: 911 setup collects each nest's machine "
     "program files into one folder; continuation pages are dropped from "
     "packets; part-number recognition rebuilt from all live batch lists; "
     "the 922 setup stage restored.",
     "Live to the team."),
    ("2026-10-21", "Card Creation Reported Success Without Creating Cards",
     "Problem",
     "Creating a batch's coordination cards reported success as soon as the "
     "request was accepted. On one batch all 35 cards failed to be created "
     "and the run still reported complete; it was found only when the board "
     "was looked at.",
     "The integration now returns what it actually did - created, already "
     "present, failed - and a failed card is offered again on the next run. "
     "First capability built on the upgraded integration licence."),
    ("2026-11-03", "TechDeck v0.8.9 Release", "Milestone",
     "Release cut and pushed live: the new 922 Production Packets tool works "
     "out every tube's saw cut length, writes the cutting list and binds the "
     "shop prints, with a second stage that binds the production run after "
     "nesting.",
     "Live to the team. Cut-length rules graded against 291 real parts "
     "across five live batches before release."),
    ("2026-11-03", "Re-Printed Work Packets Lost Their Text", "Problem",
     "Packet marking stopped on 13 orders across five batches with 'no work "
     "packet found' on packets that looked normal. They had been re-printed "
     "through a generic PDF printer, which replaces the text with a picture "
     "of it.",
     "The three affected tools now read such a page as an image. The "
     "upstream cause - packets being re-printed that way - is still to be "
     "traced."),
    ("2026-11-04", "American Tech Fellowship - Coursework Complete",
     "Milestone",
     "All six fellowship courses finished. The final course's AI and "
     "automation exercise ran end to end and was verified live.",
     "The program moves to the capstone: proposal due Nov 9, midpoint "
     "check-in the week of Dec 1, final presentation to Palantir engineers "
     "and company leadership the week of Jan 18, 2027."),
    ("2026-11-04", "Fellowship Capstone Scoped", "Decision",
     "The capstone's target system was scoped end to end. Maintenance and "
     "safety were taken out of scope by management decision, leaving the "
     "path a customer order travels through production.",
     "The first deliverable is one thin end-to-end slice; nothing widens "
     "until it runs."),
    ("2026-11-10", "TechDeck 1.0 Direction Set", "Decision",
     "The end state for the next platform generation was agreed. The "
     "capability that matters is delivery: each tool is installed and "
     "updated on its own from a library inside the application, so a fix to "
     "one tool reaches operators without a full release, and the installer "
     "carries the platform only.",
     "The current look is kept; the work goes into delivery rather than a "
     "redesign. How it is built is still open, and the delivery piece does "
     "not depend on that choice."),
    ("2026-11-11", "TechDeck v0.8.10 Release", "Milestone",
     "Release cut and pushed live: kit paperwork opens with the batch's "
     "filled material pull list; production packets carry a print for every "
     "part made; the pallet cover pages are corrected.",
     "Live to the team. 2,765 automated tests green; the pre-ship gate "
     "stopped the build once on a real defect in the new code, fixed before "
     "release."),
    ("2026-11-11", "Tracking Record Audit (Sep to Nov)", "Problem",
     "An audit of the tracking workbooks found the record had stopped on "
     "Sep 1 wherever no script owned a sheet: this log, the task list beside "
     "it, and parts of the other two workbooks. The Version Controller had "
     "also missed its 0.8.9 row.",
     "All three workbooks brought current. The task list and this log are "
     "now written by the sync script from version control, so they can no "
     "longer fall behind by being forgotten."),
    ("2026-11-11", "Project Status Review", "Decision",
     "Open rows on the chart were reviewed one by one. Customer DXF "
     "Analysis, the DXF linear-inch measurement engine and the DSTV / NC "
     "file format study are closed as complete. The crane inspection "
     "tracker was cancelled by management at about three quarters built. "
     "922 PO Builder and Automated 922 Rod Tags will not start before 2027. "
     "The in-application manual is complete and is updated with every "
     "release.",
     "The chart now matches. The separate ShipOS implementation-lead row "
     "was removed because it described the same work as the fellowship row, "
     "which stays. TechDeck 1.0 was added as its own row, tracked on its "
     "capability - delivering and updating tools individually."),
    ("2026-11-18", "Invoice Date Fix Reached the Print but Not the Workbook",
     "Problem",
     "The earlier correction for dates printing as ###### widened the "
     "columns at print time only. The printed supplement was right, and the "
     "workbook the invoicing staff open still showed ######. It was reported "
     "again after the release.",
     "The date column now carries a set width in the workbook itself, "
     "checked in Excel on a real invoice workbook. An automated check "
     "requires a set width on every column the tool writes. Rides the next "
     "release."),
    ("2026-11-19", "Inspection Templates Lost Their Part Description",
     "Problem",
     "Planning reported the Part Description on the 911 inspection sheets "
     "was not being filled in. The tool had never written it: two formulas "
     "in the template did, and both inspection templates had been re-saved "
     "on Oct 23 with those formulas gone. Every sheet built since carried "
     "the field blank unless it was typed in by hand.",
     "Both templates repaired the same day, changing only the four affected "
     "cells. The October save was not rolled back, because it had also "
     "corrected fifty tolerance formulas."),
    ("2026-11-19", "Templates Stay in Charge of the Inspection Sheet",
     "Decision",
     "After the template fault, the first fix had the tool write the Part "
     "Description itself every time. That was changed the same day: the "
     "template's own formula stays in charge, and the tool fills the field "
     "only when the formula is missing.",
     "A run that had to fall back closes with a notice that the template "
     "has been modified and needs to be fixed, so a damaged template is "
     "seen on the first batch instead of a month later."),
]
