"""
922 Setup
=========
Creates the batch's Planner buckets and one Microsoft Planner card per order
folder in a 922 batch, labelled with the order's pallet assignment.

Flow:
  1. Prompt the user to pick the batch folder (native folder dialog, opened
     at the '922 QTDR Production Packages' root when it can be found).
  2. Derive the batch number from the picked folder's name ('Batch 483' ->
     '483') for the card titles/buckets.
  3. List the order folders directly under the batch folder, dropping the
     'Batch {n} - Documentation' and 'REPEAT BATCHES' folders (and any
     temp/hidden entries).
  4. Read the batch's 'PO H{batch} Pallet & Rod Organizer.xlsx' (Pallet
     Organizer sheet) to map each order number (folder name before the first
     dash) to its PALLET 1/2/3 assignment - and, when the deferred
     'apply_material_labels' setting exists and is on, its tube source
     materials. Labels are sent as Planner slot keys ('category2') resolved
     through card_template.json's label_map (label NAME -> slot); anything
     with no matching label warns and is skipped.
  5. Build one card per folder from card_template.json:
       title    = "BATCH {batch}: {folder}"
       bucket   = "BATCH {batch}"
       priority = Medium, status = Not started
       checklist= TL Print / Saw Print / Inspection Sheet / Program /
                  Processing Completed
       labels   = pallet (+ materials when enabled) slot keys
  6. POST one JSON payload to a Power Automate webhook, which find-or-creates
     the ordered bucket list (HOLD / BATCH {n} / MODEL CHECK / 7000 / SHOP
     READY, left to right) and creates the tasks in the D922 PIPELINE plan.
     Cards are POSTED in reverse folder order (_order_for_planner) so Planner,
     which top-inserts each new task, shows the bucket A-Z top-to-bottom.
     With no webhook URL (or dry_run on) it just previews the payload and
     writes it to disk for inspection.

The card layout, bucket order, and label map live in card_template.json so
they can be edited without touching this code. Power Automate flow setup is
documented in docs/TEAMS_CARDS.md.

v2.1.0: consolidated 922 Setup. run() now opens a master toggle window
(GroupedToggleDialog via sdk.request_grouped_toggles) listing the whole 922
batch-prep sequence - "Generate Teams Cards" (the card creation above),
"Batch Repeater" (with "Distribute CAD prints + binders" / "Tag REPEAT cards
in Planner" options), and "Pallet Stamper" - and runs the checked stages top
to bottom. Sibling stages import the INSTALLED sibling plugins' run.py
in-process with their own saved settings; the batch number derived from the
picked folder seeds the family-shared cache so later stages never re-prompt
for it.

v2.1.1: pallet labels (PALLET 1/2/3) always apply - the Generate Teams Cards
child toggle is "Apply source material labels" (default OFF), which is now
the live enablement path for the previously deferred material-label branch.

v2.2.0: tickets scale with the stages run - each completed stage counts as a
full system run (sdk.set_ticket_units), so Setup alone pays 5 tickets,
Setup + Stamper 10, Setup + Repeater + Stamper 15.

v2.3.0: new FIRST stage "Batch Folder Setup" - builds the batch's order
folders from the PO sheet of the Documentation folder's 'PO H{n} QF-QU-09
REV C.xlsx' (one folder per unique ORDER-PPN pair, named '{ORDER}-{PPN}'),
copies the REV C workbook into each as '{PPN}.xlsx' (never overwriting an
existing copy - those get filled in per order later), then moves each order's
work-packet PDF (filename contains the ORDER number) out of the batch's
'Work Packets' folder - falling back to PDFs loose in the batch root, the
pre-convention drop spot - into its order folder. Idempotent: existing
folders/copies/moved PDFs are skipped, so re-runs are safe. The batch-folder
pick now happens ONCE up front (orchestrator level) and feeds every stage.

v2.3.1: an order spanning several PPNs (several folders) gets its work
packet PDF placed in EVERY one of its folders, not just the first.

v2.3.3: Teams cards now read A-Z top-to-bottom in the bucket. Planner
top-inserts each new task, so posting folders A-Z made the bucket read Z-A
(user report); cards are now posted in reverse (_order_for_planner) so the
alphabetically-first card lands on top.

v2.4.1: restore the payload's `buckets` key. The v2.3.3 edit rewrote the
payload dict inline to flip the post order and dropped `"buckets"` with it -
flow #1's For_each_bucket does a foreach over that array, and a foreach over
Null is a hard flow failure. TechDeck still logged DONE (HTTP 202 = accepted,
not succeeded), so every 0.8.6.11 card run silently created nothing (bit
Batch 488, 2026-08-05). The payload is now built by _build_payload - one
place, contract-tested (tests/core/test_922_setup_cards.py) so a flow
contract key can't silently vanish again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# SDK bootstrap — works in-process (TechDeck/frozen exe) and standalone.
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

VERSION = "2.5.0"

# The 'TechDeck 922 Setup - Create Production Cards' Power Automate flow.
# Baked in so a fresh install posts out of the box (same pattern as the
# telemetry webhook in constants.py) — v0.8.6.8 shipped with a blank default
# and silently dry-ran on every machine but the author's. The Settings field
# stays as an OVERRIDE (e.g. pointing at a rebuilt flow without an app
# update); the dry_run toggle is how you preview without posting.
DEFAULT_WEBHOOK_URL = (
    "https://REDACTED-ENVIRONMENT.api"
    ".powerplatform.com:443/powerautomate/automations/direct/cu/04/workflows/"
    "REDACTED-WORKFLOW-ID/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=REDACTED"
)

# The 'TechDeck 922 Pallet Labeler' Power Automate flow (#4) — the SECOND
# PASS that labels cards which already exist. Separate flow, separate URL: #1
# creates cards and would duplicate the board if re-posted, #4 only updates.
# Baked in so a fresh install labels out of the box (a blank default silently
# dry-runs on every machine but the author's — v0.8.6.8 shipped that way for
# both 922 webhooks). The Settings field stays as an OVERRIDE.
# Built + verified live 2026-08-19 against Batches 490 and 489.
DEFAULT_LABELER_WEBHOOK_URL = (
    "https://REDACTED-ENVIRONMENT.api"
    ".powerplatform.com:443/powerautomate/automations/direct/cu/13/workflows/"
    "aeeef154166f49e996df9b22d3c0775e/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=REDACTED"
)

# Folders that are never orders, so they never become cards:
#   - "Batch {n} - Documentation" (matched loosely on "documentation")
#   - "REPEAT BATCHES"
# Both are matched case-insensitively.
_DOC_RE = re.compile(r"documentation", re.IGNORECASE)
_REPEAT_RE = re.compile(r"^\s*repeat\s+batches\s*$", re.IGNORECASE)


def _ignored_reason(name: str) -> str | None:
    """Why this folder is not an order, or None if it is one."""
    if _DOC_RE.search(name):
        return "documentation"
    if _REPEAT_RE.match(name):
        return "repeat batches"
    return None


def _load_template() -> dict:
    """Load card_template.json sitting next to this file."""
    tpl_path = Path(__file__).with_name("card_template.json")
    with open(tpl_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# Pallet group headers on the Pallet Organizer sheet ("PALLET 1" .. "PALLET 3").
_PALLET_HDR_RE = re.compile(r"^PALLET\s*\d+$")
# The orders section ends where the per-pallet "MATERIAL REQUIRED: n" block starts.
_MATERIAL_REQ_RE = re.compile(r"^MATERIAL\s+REQUIRED", re.IGNORECASE)


def _norm_label(text: str) -> str:
    """Canonical form for matching organizer values against label_map names:
    uppercase, whitespace collapsed, trailing ' NOM' dropped (the organizer
    writes '4.0 X 4.0 X 0.50 NOM'; the Planner label is '4.0 X 4.0 X 0.50')."""
    norm = re.sub(r"\s+", " ", str(text)).strip().upper()
    if norm.endswith(" NOM"):
        norm = norm[:-4].rstrip()
    return norm


def _read_pallet_organizer(batch_path: Path, batch: str, log):
    """Parse the batch's Pallet & Rod Organizer -> order-number map.

    Returns (mapping, warnings) where mapping is
        {ORDER: {"pallet": "PALLET 1", "materials": ["4.0 X 4.0 X 0.50 NOM", ...]}}
    or None when the workbook/sheet can't be read (warnings say why). The
    sheet is a fixed template: the pallet headers sit on one row (found by
    scanning, not hardcoded), orders in the header's column below it, that
    order's comma-separated source materials one column to the right.
    """
    warnings: list[str] = []
    xl_path = (batch_path / f"Batch {batch} - Documentation"
               / f"PO H{batch} Pallet & Rod Organizer.xlsx")
    if not sdk.is_file(xl_path):
        warnings.append(f"Pallet & Rod Organizer not found "
                        f"({xl_path.name}) - cards will have NO labels.")
        return None, warnings
    try:
        wb = sdk.load_workbook_resilient(xl_path, log=log, data_only=True,
                                         read_only=True)
    except Exception as exc:
        warnings.append(f"Could not read {xl_path.name}: {exc} - "
                        f"cards will have NO labels.")
        return None, warnings
    try:
        if "Pallet Organizer" not in wb.sheetnames:
            warnings.append(f"No 'Pallet Organizer' sheet in {xl_path.name} - "
                            f"cards will have NO labels.")
            return None, warnings
        ws = wb["Pallet Organizer"]
        # Small fixed-template sheet: snapshot the region once (read-only
        # worksheets make random cell access slow).
        grid = [[cell.value for cell in row]
                for row in ws.iter_rows(min_row=1, max_row=60, max_col=12)]
    finally:
        wb.close()

    # Locate the pallet header row + the (order col, pallet name) groups.
    groups: list[tuple[int, str]] = []   # (0-based col index, "PALLET N")
    header_row = None
    for r, row in enumerate(grid[:10]):
        found = [(c, _norm_label(v)) for c, v in enumerate(row)
                 if v is not None and _PALLET_HDR_RE.match(_norm_label(v))]
        if found:
            header_row, groups = r, found
            break
    if not groups:
        warnings.append(f"No 'PALLET n' headers found on the Pallet Organizer "
                        f"sheet of {xl_path.name} - cards will have NO labels.")
        return None, warnings
    if len(groups) != 3:
        warnings.append(f"Expected 3 pallet groups on the Pallet Organizer "
                        f"sheet, found {len(groups)} - proceeding with those.")

    mapping: dict[str, dict] = {}
    for r in range(header_row + 1, len(grid)):
        row = grid[r]
        # Stop at the "MATERIAL REQUIRED" block under the order lists.
        if any(isinstance(row[c], str) and _MATERIAL_REQ_RE.match(row[c].strip())
               for c, _ in groups if c < len(row)):
            break
        for c, pallet in groups:
            order = row[c] if c < len(row) else None
            if order is None or not str(order).strip():
                continue
            materials_cell = row[c + 1] if c + 1 < len(row) else None
            materials = [m.strip() for m in str(materials_cell or "").split(",")
                         if m.strip()]
            mapping[str(order).strip().upper()] = {
                "pallet": pallet,
                "materials": materials,
            }
    if not mapping:
        warnings.append(f"No orders found under the pallet headers in "
                        f"{xl_path.name} - cards will have NO labels.")
        return None, warnings
    return mapping, warnings


def _labels_for_folder(folder: str, organizer: dict | None, label_map: dict,
                       apply_materials: bool, warnings: list,
                       unmatched_materials: set):
    """Resolve one order folder to (slot_keys, display_names).

    label_map is pre-normalized ({_norm_label(name): "categoryN"}). Pallet
    label always applies; material labels only when apply_materials (the
    deferred default-off feature). Unmatched names warn and are skipped -
    the card is still created with whatever did match.
    """
    slots: list[str] = []
    names: list[str] = []
    if organizer is None:
        return slots, names
    order = folder.split("-", 1)[0].strip().upper()
    entry = organizer.get(order)
    if entry is None:
        warnings.append(f"Order {order} ({folder}) is not on the Pallet "
                        f"Organizer sheet - card created with no labels.")
        return slots, names

    wanted = [entry["pallet"]]
    if apply_materials:
        wanted.extend(entry["materials"])
    for name in wanted:
        norm = _norm_label(name)
        slot = label_map.get(norm)
        if slot is None:
            unmatched_materials.add(norm)
        elif slot not in slots:
            slots.append(slot)
            names.append(norm)
    return slots, names


def _is_order_folder(entry: Path) -> bool:
    if not sdk.is_dir(entry):
        return False
    name = entry.name
    if name.startswith(("~", ".", "$")):
        return False
    if _ignored_reason(name):
        return False
    return True


def _build_cards(template: dict, batch: str, folders: list[str],
                 folder_labels: dict[str, list[str]]) -> list[dict]:
    title_fmt = template.get("title_format", "BATCH {batch}: {folder}")
    bucket_fmt = template.get("bucket_format", "BATCH {batch}")
    priority = template.get("priority", "Medium")
    status = template.get("status", "Not started")
    checklist = list(template.get("checklist", []))
    cards = []
    for folder in folders:
        cards.append({
            "title": title_fmt.format(batch=batch, folder=folder),
            "bucket": bucket_fmt.format(batch=batch),
            "priority": priority,
            "status": status,
            "checklist": checklist,
            "labels": list(folder_labels.get(folder, [])),
        })
    return cards


def _order_for_planner(cards: list[dict]) -> list[dict]:
    """Order the cards for POSTING so the bucket reads A-Z top-to-bottom.

    Planner's "Create a task" inserts each new card at the TOP of its bucket, so
    posting the folders in natural A-Z order makes the bucket read Z-A (reported
    by C.D. 2026-07-27, "THEY'RE Z-A ... AND THATS MESSED UP"). Posting in
    reverse means the alphabetically-FIRST folder is created LAST and lands on
    top -> the bucket reads A-Z. Cards are built A-Z (labels/logs/preview stay
    natural); only the post order is flipped.
    """
    return list(reversed(cards))


def _build_payload(template: dict, batch: str, cards: list[dict]
                   ) -> tuple[dict, list[str]]:
    """The flow #1 webhook payload — the REMOTE CONTRACT with the 'TechDeck 922
    Setup - Create Production Cards' Power Automate flow.

    Every key here is load-bearing on the flow side: `plan`, `batch`, `tasks`,
    and `buckets` (the ordered left-to-right bucket set the flow find-or-creates
    — its For_each_bucket loop does a foreach over `buckets`, and a foreach over
    Null is a hard fail, not a skip). The v2.3.3 post-order edit rewrote this
    dict inline and dropped `buckets` with it: every 0.8.6.11 run then died in
    the flow at 858ms while TechDeck logged DONE (bit C.D., Batch 488,
    2026-08-05). Built in one place and contract-tested so a key can't silently
    vanish again. Returns (payload, buckets) — the buckets list is also logged.
    """
    buckets = [b.format(batch=batch) for b in template.get("buckets", [])] \
        or [template.get("bucket_format", "BATCH {batch}").format(batch=batch)]
    payload = {
        "plan": template.get("plan", "D922 PIPELINE"),
        "batch": batch,
        "buckets": buckets,
        # Posted in reverse so Planner (which top-inserts each new card) shows
        # the bucket A-Z top-to-bottom instead of Z-A. See _order_for_planner.
        "tasks": _order_for_planner(cards),
    }
    return payload, buckets


def _write_preview(payload: dict, log) -> None:
    """Save the built payload next to TechDeck's data for inspection."""
    sdk.write_payload_preview(payload, "last_922_setup_payload.json", log)


def _run_pallet_labels(params: dict, progress_callback, cancel_event,
                       batch_path, batch: str) -> bool:
    """Stage: put each order's PALLET 1/2/3 label on the card that ALREADY
    exists on the D922 PIPELINE board. Default OFF.

    Why this stage exists (Batch 489, 2026-08-18)
    ---------------------------------------------
    The Generate Teams Cards stage resolves labels at card-CREATION time. A
    batch carded before the Pallet & Rod Organizer is filled in therefore gets
    cards with an EMPTY label list - and flow #1's dedupe SKIPS exact-title
    matches rather than updating them, so re-running Setup would duplicate the
    board, not fix it. Batch 489's 37 cards went up at 11:17 AM with
    ``"labels": []``; Batch 490, set up that same afternoon off a filled
    organizer, went out with category2/3/4 throughout (both read from the
    flow's own run history). Same version, same machine, three hours apart -
    the only variable was whether anyone had assigned the pallets yet.

    So this is the second pass: tick it on its own once the organizer is
    filled in, and the cards already on the board get labelled. It NEVER
    creates a card. Flow #4 writes only the three pallet slots, so a card's
    REPEAT and material labels survive; re-running changes nothing.

    Returns True when the stage completed (it counts for a ticket unit).
    Problems warn loudly - a blocking popup + a warning run outcome - instead
    of raising, so the other stages in the run still finish; silence is
    exactly what let 489 through.
    """
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("Puts the PALLET 1/2/3 label on cards that already exist.")
    log("It never creates a card - that is the Generate Teams Cards stage.")
    progress_callback(10)

    # --- Order folders (same ignore rules as the card stage) ---------------
    folders: list[str] = []
    for i, entry in enumerate(sorted(batch_path.iterdir())):
        if i % 64 == 0:
            sdk.raise_if_cancelled(cancel_event)
        if (sdk.is_dir(entry) and not _ignored_reason(entry.name)
                and _is_order_folder(entry)):
            folders.append(entry.name)
    if not folders:
        _label_stage_problem(
            params,
            f"Batch {batch} has no order folders, so there is nothing to "
            f"label.")
        return False
    log(f"Found {len(folders)} order folder(s).")
    progress_callback(30)

    # --- Pallet assignments -------------------------------------------------
    organizer, warnings = _read_pallet_organizer(batch_path, batch, log)
    if organizer is None:
        _label_stage_problem(
            params,
            f"Couldn't read the pallet assignments for Batch {batch}, so no "
            f"labels were applied.\n\n" + "\n\n".join(warnings))
        return False
    log(f"Pallet Organizer: {len(organizer)} order-to-pallet assignment(s).")
    progress_callback(45)

    # --- Resolve each folder's pallet slot ----------------------------------
    template = _load_template()
    label_map = {_norm_label(name): slot
                 for name, slot in (template.get("label_map") or {}).items()}
    title_fmt = template.get("title_format", "BATCH {batch}: {folder}")

    unmatched: set = set()
    cards: list[dict] = []
    names_by_title: dict[str, list] = {}
    unlabelled: list[str] = []
    for folder in folders:
        sdk.raise_if_cancelled(cancel_event)
        # apply_materials=False: this is the PALLET pass. Source-material
        # labels stay the card-creation stage's option.
        slots, names = _labels_for_folder(folder, organizer, label_map,
                                          False, warnings, unmatched)
        if not slots:
            unlabelled.append(folder)
            continue
        title = title_fmt.format(batch=batch, folder=folder)
        cards.append({"title": title, "labels": slots})
        names_by_title[title] = names
    if unmatched:
        warnings.append("No matching Teams label for: "
                        + ", ".join(sorted(unmatched)))
    progress_callback(60)

    if not cards:
        _label_stage_problem(
            params,
            f"Not one of Batch {batch}'s {len(folders)} orders is listed under "
            f"PALLET 1/2/3 on the Pallet Organizer sheet, so no labels were "
            f"applied.\n\nFill in the pallet assignments in 'PO H{batch} "
            f"Pallet & Rod Organizer.xlsx' (Documentation folder), then run "
            f"this stage again.")
        return False

    log("")
    log(f"{len(cards)} card(s) to label:")
    for card in cards:
        log(f"  - {card['title']}   "
            f"[{', '.join(names_by_title[card['title']])}]")
    if unlabelled:
        log("")
        log(f"{len(unlabelled)} order(s) are not on the Pallet Organizer "
            f"sheet - their cards are left alone:")
        for name in unlabelled:
            log(f"  - {name}")
    if warnings:
        log("")
        log("Label warnings:")
        for w in warnings:
            log(f"  ! {w}")

    payload = {
        "plan": template.get("plan", "D922 PIPELINE"),
        "batch": str(batch),
        "cards": cards,
    }
    progress_callback(75)
    if cancel_event.is_set():
        return False

    # --- Post (or preview) --------------------------------------------------
    url = ((settings.get("labeler_webhook_url", "") or "").strip()
           or DEFAULT_LABELER_WEBHOOK_URL)
    dry_run = bool(settings.get("dry_run", False))

    if not url:
        log("")
        log("No Pallet Labeler webhook is configured - previewing only, "
            "NOTHING was sent to Teams.")
        _write_label_preview(payload, log)
        progress_callback(100)
        _label_stage_problem(
            params,
            f"No pallet-label webhook is configured, so Batch {batch}'s cards "
            f"were NOT labeled (the payload was previewed only).",
            popup=False)
        return False

    if dry_run:
        log("")
        log("Dry run enabled in Settings -> not posting.")
        _write_label_preview(payload, log)
        progress_callback(100)
        log("DONE (dry run).")
        return True

    log("")
    log("Posting the pallet labels to the webhook...")
    ok = sdk.post_webhook(url, payload, log)
    progress_callback(100)
    if not ok:
        _label_stage_problem(
            params,
            f"The pallet-label post failed - Batch {batch}'s cards were not "
            f"labeled. See the errors above.",
            popup=False)
        return False

    log("")
    log(f"DONE. Requested labels for {len(cards)} card(s) in Batch {batch}.")
    log("Check the D922 PIPELINE board in Teams to confirm.")
    if unlabelled:
        _label_stage_problem(
            params,
            f"{len(unlabelled)} order(s) are not on the Pallet Organizer "
            f"sheet - their cards were left unlabeled.",
            popup=False)
    return True


def _write_label_preview(payload: dict, log) -> None:
    sdk.write_payload_preview(payload, "last_922_pallet_label_payload.json", log)


def _label_stage_problem(params: dict, message: str, popup: bool = True) -> None:
    """Surface a pallet-label problem without killing the rest of the run.

    A blocking popup for the causes the user can fix right now (no organizer,
    nothing assigned), and a warning run outcome always - so the run never
    ends on a bare green tick when no card was actually labelled.
    """
    log = params.get("log", print)
    log("")
    log(f"WARNING: {message}")
    if popup:
        sdk.show_warning(params, "922 Setup - pallet labels", message)
    if hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(params, sdk.RUN_OUTCOME_WARNING, message)


def _pick_batch_folder(params: dict, cancel_event):
    """Prompt for the 'Batch NNN' folder (native dialog, opened at the 922
    QTDR root when it can be found) and derive the batch number from its
    name. Returns (batch_path, batch) or (None, None) on cancel/bad pick —
    a user cancel also sets cancel_event so the run counts as cancelled."""
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}
    start_dir = ""
    try:
        root = sdk.resolve_922_root(settings.get("base_path", ""))
        if root is not None and sdk.exists(root):
            start_dir = str(root)
    except Exception:
        pass
    # Sentry Drone mode is applied by the SDK: the targeting-drone picker
    # (crosshair, lock-on, railgun) when the drone is OWNED and switched on for
    # this app, otherwise a normal folder dialog. Professional theme / older
    # TechDeck / any effect failure also fall back.
    raw = sdk.request_directory(params, "Select the 922 batch folder", start_dir)
    if cancel_event.is_set():
        return None, None
    if not raw:
        log("Folder selection cancelled - nothing was run.")
        cancel_event.set()  # user cancel: not a successful (ticket-earning) run
        return None, None
    batch_path = Path(raw)
    if not sdk.is_dir(batch_path):
        log(f"ERROR: '{batch_path}' is not a folder.")
        return None, None
    # 'Batch 483' -> '483' (needed for card titles/buckets + file discovery).
    batch = sdk.parse_922_batch(batch_path.name)
    if not batch:
        log(f"ERROR: could not read a batch number from the folder name "
            f"'{batch_path.name}'. Pick the 'Batch NNN' folder itself.")
        return None, None
    log(f"Batch: {batch}")
    log(f"Batch folder: {batch_path}")
    return batch_path, batch


def _run_teams_setup(params: dict, progress_callback, cancel_event,
                     batch_path: Path, batch: str,
                     apply_materials_opt: bool = False):
    """The original 922 Setup stage: build the cards for the already-picked
    batch folder, POST (or dry-run) the webhook payload. Pallet labels
    (PALLET 1/2/3) ALWAYS apply; ``apply_materials_opt`` (the master window's
    "Apply source material labels" toggle, default off) turns the
    source-material labels on for this run. Returns the batch number string
    on success, or None when cancelled / errored (the log says which)."""
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}
    progress_callback(15)

    # --- List order folders (drop the Documentation folder) ----------------
    folders: list[str] = []
    skipped: list[str] = []
    for i, entry in enumerate(sorted(batch_path.iterdir())):
        if cancel_event is not None and i % 64 == 0 and cancel_event.is_set():
            log("Cancelled.")
            return
        if not sdk.is_dir(entry):
            continue
        reason = _ignored_reason(entry.name)
        if reason:
            skipped.append(f"{entry.name} ({reason})")
        elif _is_order_folder(entry):
            folders.append(entry.name)

    if skipped:
        log(f"Skipped: {', '.join(skipped)}")
    if not folders:
        log("ERROR: no order folders found in this batch.")
        return
    log(f"Found {len(folders)} order folder(s).")
    progress_callback(40)

    # --- Read the pallet assignments from the Pallet & Rod Organizer -------
    # Pallet labels always apply. Source-material labels are on only when the
    # master window's toggle was checked (or the still-undeclared
    # 'apply_material_labels' plugin.json setting exists and is true).
    apply_materials = (apply_materials_opt
                       or bool(settings.get("apply_material_labels", False)))
    if apply_materials:
        log("Source material labels: ON for this run.")
    organizer, warnings = _read_pallet_organizer(batch_path, batch, log)
    if organizer is not None:
        log(f"Pallet Organizer: {len(organizer)} order-to-pallet assignment(s).")
    progress_callback(50)

    # --- Build the cards from the template ---------------------------------
    try:
        template = _load_template()
    except (OSError, json.JSONDecodeError) as exc:
        log(f"ERROR: could not read card_template.json: {exc}")
        return

    label_map = {_norm_label(name): slot
                 for name, slot in (template.get("label_map") or {}).items()}
    unmatched: set = set()
    folder_labels: dict[str, list[str]] = {}
    folder_label_names: dict[str, list[str]] = {}
    for folder in folders:
        slots, names = _labels_for_folder(folder, organizer, label_map,
                                          apply_materials, warnings, unmatched)
        folder_labels[folder] = slots
        folder_label_names[folder] = names
    if unmatched:
        warnings.append("No matching Teams label for: "
                        + ", ".join(sorted(unmatched))
                        + " - skipped (cards still created; add/rename the "
                        "label in Teams AND card_template.json to cover it).")

    cards = _build_cards(template, batch, folders, folder_labels)
    payload, buckets = _build_payload(template, batch, cards)

    log(f"\nBuckets (left to right): {', '.join(buckets)}")
    log(f"\nWill create {len(cards)} card(s) in plan '{payload['plan']}', "
        f"bucket 'BATCH {batch}':")
    for folder, card in zip(folders, cards):
        names = folder_label_names.get(folder, [])
        suffix = f"   [{', '.join(names)}]" if names else ""
        log(f"  - {card['title']}{suffix}")

    if warnings:
        log("\nLabel warnings:")
        for w in warnings:
            log(f"  ! {w}")
        sdk.show_warning(params, "922 Setup - label warnings",
                         "\n\n".join(warnings))
    progress_callback(60)

    if cancel_event.is_set():
        return

    # --- Post (or dry-run) -------------------------------------------------
    url = (settings.get("webhook_url", "") or "").strip() or DEFAULT_WEBHOOK_URL
    dry_run = bool(settings.get("dry_run", False))

    if dry_run:
        log("\nDry run enabled in Settings -> not posting.")
        _write_preview(payload, log)
        progress_callback(100)
        log("\nDONE (dry run).")
        return batch

    log("\nPosting cards to the webhook...")
    ok = sdk.post_webhook(url, payload, log)
    progress_callback(100)
    if ok:
        log(f"\nDONE. Requested {len(cards)} card(s) for Batch {batch}.")
        log("Check the D922 PIPELINE plan in Teams to confirm.")
        return batch
    log("\nFAILED — see the errors above. The payload was not created.")
    return batch  # the batch is still known — later stages can proceed


# ─────────────────────────────────────────────────────────────────────────────
# Stage 0 — Batch Folder Setup (v2.3.0)
# ─────────────────────────────────────────────────────────────────────────────
# Builds the batch's order folders from the REV C PO sheet, drops a renamed
# copy of the REV C workbook in each, and files each order's work-packet PDF
# into its folder. Idempotent — everything that already exists is skipped.

# The new drop-spot convention for incoming work-packet PDFs.
_WORK_PACKETS_RE = re.compile(r"^\s*work\s*packets?\s*$", re.IGNORECASE)


def _find_rev_c_workbook(batch_path: Path, batch: str) -> Path:
    """The batch's own 'PO H{n} QF-QU-09 REV C.xlsx' in the Documentation
    folder (both matched loosely — layouts vary). Raises UserFacingError
    when the folder or workbook is missing."""
    doc_dir = next((e for e in sorted(batch_path.iterdir())
                    if sdk.is_dir(e) and _DOC_RE.search(e.name)), None)
    if doc_dir is None:
        raise sdk.UserFacingError(
            f"No 'Batch {batch} - Documentation' folder inside "
            f"'{batch_path.name}'.",
            "Create the Documentation folder with the batch's 'PO QF-QU-09 "
            "REV C' workbook in it, then run 922 Setup again.")
    candidates = [p for p in sorted(doc_dir.glob("*.xlsx"))
                  if not p.name.startswith("~$")
                  and re.search(r"QF[\s.-]*QU[\s.-]*09", p.name, re.IGNORECASE)
                  and re.search(r"REV\s*C", p.name, re.IGNORECASE)]
    if not candidates:
        raise sdk.UserFacingError(
            f"No 'QF-QU-09 REV C' workbook found in '{doc_dir.name}'.",
            "Put the batch's 'PO H{batch} QF-QU-09 REV C.xlsx' in the "
            "Documentation folder, then run 922 Setup again.")
    return candidates[0]


def _read_po_order_ppns(rev_c: Path, log) -> list[tuple[str, str]]:
    """Ordered unique (ORDER, PPN) pairs from the REV C workbook's PO sheet.
    Columns are found by header NAME (never position); ORDER is
    forward-filled since it repeats per line item on some copies."""
    wb = sdk.load_workbook_resilient(rev_c, log=log, data_only=True)
    try:
        ws = wb["PO"] if "PO" in wb.sheetnames else wb.active
        header_row, cols = sdk.find_header_row(ws, ["ORDER", "PPN"])
        if header_row is None:
            raise sdk.UserFacingError(
                f"Could not find the ORDER / PPN header row on the PO sheet "
                f"of '{rev_c.name}'.",
                "Check that the workbook's PO sheet still has ORDER and PPN "
                "columns, then run 922 Setup again.")
        pairs: list[tuple[str, str]] = []
        seen: set = set()
        last_order = None
        for r in range(header_row + 1, ws.max_row + 1):
            def _v(c):
                v = ws.cell(r, c).value
                return str(v).strip() if v not in (None, "") else None
            order, ppn = _v(cols["ORDER"]), _v(cols["PPN"])
            if order:
                last_order = order
            else:
                order = last_order
            if not order or not ppn:
                continue
            key = (order.upper(), ppn.upper())
            if key not in seen:
                seen.add(key)
                pairs.append((order, ppn))
        return pairs
    finally:
        wb.close()


def _order_pdf_sources(batch_path: Path, log) -> list[Path]:
    """The work-packet PDFs to file into order folders. The convention is a
    'Work Packets' folder inside the batch folder; batches from before the
    convention have the PDFs loose in the batch root, so fall back there."""
    wp_dir = next((e for e in sorted(batch_path.iterdir())
                   if sdk.is_dir(e) and _WORK_PACKETS_RE.match(e.name)), None)
    if wp_dir is not None:
        pdfs = [p for p in sorted(wp_dir.iterdir())
                if sdk.is_file(p) and p.suffix.lower() == ".pdf"]
        log(f"Work Packets folder: {len(pdfs)} PDF(s).")
        return pdfs
    pdfs = [p for p in sorted(batch_path.iterdir())
            if sdk.is_file(p) and p.suffix.lower() == ".pdf"]
    if pdfs:
        log(f"No 'Work Packets' folder - using {len(pdfs)} PDF(s) loose in "
            f"the batch folder.")
    else:
        log("No 'Work Packets' folder and no loose PDFs in the batch folder.")
    return pdfs


def _run_folder_setup(params: dict, progress_callback, cancel_event,
                      batch_path: Path, batch: str) -> bool:
    """Stage 0: order folders + per-order REV C copy + work-packet filing.

    For every unique ORDER-PPN pair on the REV C PO sheet: create
    '{ORDER}-{PPN}', copy the REV C workbook in as '{PPN}.xlsx' (existing
    copies are NEVER overwritten - they get filled in per order later), then
    move each PDF whose filename contains the ORDER number out of the Work
    Packets folder (or the batch root) into EVERY folder belonging to that
    order (a multi-PPN order has several). Returns True when the stage
    completed."""
    import shutil

    log = params.get("log", print)
    warnings: list[str] = []

    rev_c = _find_rev_c_workbook(batch_path, batch)
    log(f"PO workbook: {rev_c.name}")
    pairs = _read_po_order_ppns(rev_c, log)
    if not pairs:
        raise sdk.UserFacingError(
            f"The PO sheet of '{rev_c.name}' has no ORDER/PPN rows.",
            "Check the workbook's PO sheet, then run 922 Setup again.")
    log(f"PO sheet: {len(pairs)} unique ORDER-PPN pair(s).")
    progress_callback(20)
    if cancel_event.is_set():
        return False

    # --- Order folders + the per-order REV C copy --------------------------
    # An order that spans several PPNs gets several folders - and its work
    # packet PDF is placed in EVERY one of them below.
    order_to_folders: dict[str, list] = {}
    made_folders = made_copies = 0
    for i, (order, ppn) in enumerate(pairs):
        if i % 16 == 0 and cancel_event.is_set():
            return False
        folder = batch_path / f"{order}-{ppn}"
        if not sdk.exists(folder):
            sdk.ensure_dir(folder)
            made_folders += 1
        order_to_folders.setdefault(order.upper(), []).append(folder)
        dest = folder / f"{ppn}.xlsx"
        if not sdk.exists(dest):
            sdk.copy_resilient(rev_c, dest, log)
            made_copies += 1
        progress_callback(20 + 50 * (i + 1) // len(pairs))
    log(f"Order folders: {made_folders} created "
        f"({len(pairs) - made_folders} already existed); "
        f"{made_copies} PO workbook cop(ies) placed.")
    if cancel_event.is_set():
        return False

    # --- File the work-packet PDFs into their order folders ----------------
    # The ORDER number appears in the PDF filename ('BK573423.pdf',
    # 'X6401069 NOFORN.pdf'); match it as a whole token so one order number
    # can never match inside a longer one.
    pdfs = _order_pdf_sources(batch_path, log)
    moved = 0
    matched_orders: set = set()
    for i, pdf in enumerate(pdfs):
        if i % 16 == 0 and cancel_event.is_set():
            return False
        stem = pdf.stem
        hit = next((key for key in order_to_folders
                    if re.search(rf"(?<![A-Za-z0-9]){re.escape(key)}"
                                 rf"(?![A-Za-z0-9])", stem, re.IGNORECASE)),
                   None)
        if hit is None:
            warnings.append(f"'{pdf.name}' matches no ORDER on the PO sheet - "
                            f"left where it is.")
            continue
        # The PDF goes in EVERY folder for its order (a multi-PPN order has
        # several): copy to each folder that doesn't have it yet, then remove
        # the source once all of them do.
        dests = [f / pdf.name for f in order_to_folders[hit]]
        missing = [d for d in dests if not sdk.exists(d)]
        if not missing:
            warnings.append(f"'{pdf.name}' already exists in its order "
                            f"folder(s) - left where it is.")
            continue
        for d in missing:
            shutil.copy2(sdk.long_path(pdf), sdk.long_path(d))
        pdf.unlink()
        moved += 1
        matched_orders.add(hit)
        if moved <= 40:
            names = " + ".join(d.parent.name for d in dests)
            log(f"  {pdf.name} -> {names}")
    log(f"Work packets: {moved} PDF(s) filed into order folders.")

    # Orders with a folder that still has no work-packet PDF (nothing placed
    # this run AND none already inside) are worth a heads-up.
    # "Has a PDF" is not the same as "has a work packet": a drawing binder
    # (Binder1.pdf ...) lands in the same folder, so counting any PDF hid the
    # orders that genuinely have no packet. sdk.find_work_packet reads the
    # page-1 title block and returns None when every PDF there is a drawing.
    no_pdf = [o for o, folders in order_to_folders.items()
              if o not in matched_orders
              and any(sdk.find_work_packet(f, log=None) is None for f in folders)]
    if no_pdf:
        warnings.append("No work-packet PDF found for: "
                        + ", ".join(sorted(no_pdf))
                        + " - drop them in the batch's 'Work Packets' folder "
                        "and run again.")

    if warnings:
        log("\nFolder setup warnings:")
        for w in warnings:
            log(f"  ! {w}")
        sdk.show_warning(params, "922 Setup - folder setup warnings",
                         "\n\n".join(warnings))
    progress_callback(100)
    log(f"Batch Folder Setup DONE - {len(pairs)} order folder(s) ready.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration — the consolidated 922 Setup
# ─────────────────────────────────────────────────────────────────────────────
# One tile runs the whole 922 batch-prep sequence behind a master toggle
# window: Batch Folder Setup -> Generate Teams Cards -> 922 Pallet Stamper ->
# 922 Batch Repeater. Stamping runs BEFORE the Repeater so repeat orders (and
# the repeat binders the Repeater distributes into the root order folders) are
# never stamped. The sibling plugins' code is NOT duplicated — their
# installed run.py files are imported at run time from the plugins dir this
# file lives in, and each runs with its OWN saved settings
# (sdk.plugin_settings). The standalone Repeater/Stamper tiles keep working
# unchanged; if one is missing (partial install) its stage errors cleanly.

# Progress-bar slice per stage (proportionally re-normalized over the enabled
# stages, so any combination still sweeps 0..100).
_STAGE_WEIGHTS = {"folder_setup": 15, "teams_setup": 30,
                  "pallet_labels": 10, "batch_repeater": 40,
                  "pallet_stamper": 15}


def _dialog_groups() -> list:
    """The master window's plain-data spec (sdk.request_grouped_toggles).

    Pallet labels (PALLET 1/2/3) always apply — the only label toggle is the
    source-MATERIAL labels, default OFF (the deferred-by-teammate-input
    feature; the flow already handles the slots, so checking it is the whole
    enablement for a run).
    """
    return [
        {"key": "folder_setup",
         "label": "Batch Folder Setup",
         "checked": True,
         "children": []},
        {"key": "teams_setup",
         "label": "Generate Teams Cards",
         "checked": True,
         "children": [
             {"key": "materials", "label": "Apply source material labels",
              "checked": False},
         ]},
        {"key": "pallet_labels",
         "label": "Apply pallet labels to existing cards",
         "checked": False,
         "children": []},
        {"key": "pallet_stamper",
         "label": "Pallet Stamper",
         "checked": True,
         "children": []},
        {"key": "batch_repeater",
         "label": "Batch Repeater",
         "checked": True,
         "children": [
             {"key": "distribute", "label": "Distribute CAD prints + binders",
              "checked": True},
             {"key": "tag", "label": "Label REPEAT cards in Teams",
              "checked": True},
         ]},
    ]


def _load_sibling(plugin_id: str, log):
    """Import the installed sibling plugin's run.py (sdk.load_sibling — one
    home for the sibling-resolution dance). Returns the module, or None
    (logged) when it isn't installed / fails to import."""
    try:
        return sdk.load_sibling(plugin_id, __file__)
    except Exception as exc:
        log(f"ERROR: could not load sibling plugin '{plugin_id}': {exc}")
        return None


def _scaled(progress_callback, lo: int, hi: int):
    """Map a stage's 0..100 progress onto the [lo, hi] slice of the run bar."""
    def cb(p):
        try:
            p = max(0, min(100, int(p)))
        except (TypeError, ValueError):
            return
        progress_callback(lo + (hi - lo) * p // 100)
    return cb


def _run_sibling_stage(plugin_id: str, stage_label: str, params: dict,
                       shared_state: dict, progress_cb, cancel_event,
                       stage_options: dict | None = None) -> None:
    """Run a sibling plugin in-process with its own settings. shared_state is
    passed through so sdk.request_batch_number reuses the batch the Teams
    Setup stage derived (no re-prompt). Exceptions propagate — a stage
    failure fails the run, exactly like the standalone tile would."""
    log = params.get("log", print)
    module = _load_sibling(plugin_id, log)
    if module is None or not callable(getattr(module, "run", None)):
        raise RuntimeError(f"{stage_label} stage could not be loaded - "
                           f"is '{plugin_id}' installed?")
    sub_params = dict(params)
    sub_params["plugin_id"] = plugin_id
    sub_params["plugin_family"] = "922"
    sub_params["settings"] = sdk.plugin_settings(plugin_id)
    sub_params["shared_state"] = shared_state
    if stage_options is not None:
        sub_params["stage_options"] = stage_options
    log("")
    log("=" * 60)
    log(f"Stage: {stage_label}")
    log("=" * 60)
    module.run(sub_params, progress_cb, cancel_event)


def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)

    log("=" * 60)
    log(f"922 Setup v{VERSION}")
    log("=" * 60)

    # --- Master toggle window ----------------------------------------------
    choices = sdk.request_grouped_toggles(
        params, _dialog_groups(),
        window_title="922 Setup",
        header="922 Setup - Select Stages",
        subtext=("Stages run top to bottom. Click a stage's name to show its "
                 "options; uncheck a stage to skip it."),
        run_button_text="Run Selected",
    )
    if choices is None:
        log("Stage selection cancelled - nothing was run.")
        cancel_event.set()  # user cancel: not a successful (ticket-earning) run
        return

    order = ["folder_setup", "teams_setup", "pallet_labels",
             "pallet_stamper", "batch_repeater"]
    enabled = [k for k in order if choices.get(k, {}).get("enabled")]
    if not enabled:
        log("No stages selected - nothing was run.")
        cancel_event.set()
        return
    log("Stages: " + " -> ".join(enabled))

    # Proportional progress slices over the enabled stages.
    total = sum(_STAGE_WEIGHTS[k] for k in enabled)
    slices: dict[str, tuple[int, int]] = {}
    acc = 0
    for k in enabled:
        lo = acc * 100 // total
        acc += _STAGE_WEIGHTS[k]
        slices[k] = (lo, acc * 100 // total)

    # The family-shared state travels through every stage so one batch answer
    # serves all of them (the executor injects it on GUI runs; create one for
    # headless runs so the stages still share between themselves).
    shared_state = params.get("shared_state")
    if shared_state is None:
        shared_state = {"911": {}, "922": {}, "General": {}}

    # Each completed stage counts as a full system run for the ticket award
    # (5 per system: all four stages = 20).
    stages_done = 0

    # --- One batch-folder pick feeds every stage that needs it -------------
    batch_path = batch = None
    if ("folder_setup" in enabled or "teams_setup" in enabled
            or "pallet_labels" in enabled):
        batch_path, batch = _pick_batch_folder(params, cancel_event)
        if cancel_event.is_set():
            return
        if batch_path is None:
            raise sdk.UserFacingError(
                "The picked folder is not a 'Batch NNN' batch folder.",
                "Run 922 Setup again and pick the batch's own folder (the "
                "one named like 'Batch 483').")
        # Seed the family batch cache immediately: the folder the user just
        # picked IS this run's batch, so NO later stage ever re-prompts.
        shared_state.setdefault("922", {})["batch_number"] = batch

    # --- Stage 0: Batch Folder Setup ----------------------------------------
    if "folder_setup" in enabled:
        assert batch_path is not None and batch is not None
        lo, hi = slices["folder_setup"]
        if _run_folder_setup(params, _scaled(progress_callback, lo, hi),
                             cancel_event, batch_path, batch):
            stages_done += 1
        if cancel_event.is_set():
            return
        progress_callback(hi)

    # --- Stage 1: Generate Teams Cards (this plugin's original job) ---------
    if "teams_setup" in enabled and not cancel_event.is_set():
        assert batch_path is not None and batch is not None
        lo, hi = slices["teams_setup"]
        apply_materials = choices["teams_setup"]["options"].get("materials", False)
        done = _run_teams_setup(params, _scaled(progress_callback, lo, hi),
                                cancel_event, batch_path, batch,
                                apply_materials_opt=apply_materials)
        if cancel_event.is_set():
            return
        if done:
            stages_done += 1
        elif len(enabled) > 1:
            log("\nWARNING: Generate Teams Cards did not complete (see above). "
                "Continuing with the remaining stages.")
        progress_callback(hi)

    # --- Stage 1b: Apply pallet labels to existing cards --------------------
    # Default OFF. The second pass for a batch whose cards were created before
    # the Pallet & Rod Organizer was filled in (Batch 489) - see
    # _run_pallet_labels. Ticked alongside Generate Teams Cards it is simply a
    # no-op re-assertion of the labels that stage just applied.
    if "pallet_labels" in enabled and not cancel_event.is_set():
        assert batch_path is not None and batch is not None
        lo, hi = slices["pallet_labels"]
        log("")
        log("=" * 60)
        log("Stage: Apply pallet labels to existing cards")
        log("=" * 60)
        if _run_pallet_labels(params, _scaled(progress_callback, lo, hi),
                              cancel_event, batch_path, batch):
            stages_done += 1
        if cancel_event.is_set():
            return
        progress_callback(hi)

    # --- Stage 2: Pallet Stamper --------------------------------------------
    # Runs BEFORE the Batch Repeater on purpose. At this point every order
    # folder holds exactly its own work-packet PDF, and neither the REPEAT
    # BATCHES folder nor the repeat binders the Repeater distributes into the
    # root order folders exist yet -- so the stamp always lands on the right PDF
    # and repeat content is never stamped. (Reversing these two stages was the
    # fix for repeats getting stamped.)
    if "pallet_stamper" in enabled and not cancel_event.is_set():
        lo, hi = slices["pallet_stamper"]
        _run_sibling_stage(
            "922_pallet_stamper", "Pallet Stamper", params, shared_state,
            _scaled(progress_callback, lo, hi), cancel_event,
        )
        if cancel_event.is_set():
            return
        stages_done += 1
        progress_callback(hi)

    # --- Stage 3: Batch Repeater --------------------------------------------
    if "batch_repeater" in enabled and not cancel_event.is_set():
        lo, hi = slices["batch_repeater"]
        opts = choices["batch_repeater"]["options"]
        _run_sibling_stage(
            "922_batch_repeater", "Batch Repeater", params, shared_state,
            _scaled(progress_callback, lo, hi), cancel_event,
            stage_options={"distribute": opts.get("distribute", True),
                           "tag": opts.get("tag", True)},
        )
        if cancel_event.is_set():
            return
        stages_done += 1
        progress_callback(hi)

    # Each completed stage earns a full system's tickets (older SDKs lack the
    # helper — a plain single-run award is the graceful fallback).
    if hasattr(sdk, "set_ticket_units"):
        sdk.set_ticket_units(params, stages_done)

    progress_callback(100)
    log("")
    log("=" * 60)
    log(f"922 Setup finished ({len(enabled)} stage(s)).")
    log("=" * 60)


if __name__ == "__main__":
    # Headless smoke test: python plugins/922_setup/run.py
    # The master window falls back to an all-defaults submit when headless;
    # request_directory falls back to a pasted-path prompt, so point this at
    # a real 'Batch NNN' folder to exercise the full flow.
    import threading
    import builtins
    builtins.input = lambda *_: r"C:\path\to\Batch 483"
    run({"log": print, "settings": {}, "console": None, "plugin_family": "922"},
        lambda p: print(f"[{p}%]"), threading.Event())
