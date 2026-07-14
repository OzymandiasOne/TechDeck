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
     With no webhook URL (or dry_run on) it just previews the payload and
     writes it to disk for inspection.

The card layout, bucket order, and label map live in card_template.json so
they can be edited without touching this code. Power Automate flow setup is
documented in docs/TEAMS_CARDS.md.
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

VERSION = "2.0.1"

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
    if not xl_path.is_file():
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
    if not entry.is_dir():
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


def _write_preview(payload: dict, log) -> None:
    """Save the built payload next to TechDeck's data for inspection."""
    sdk.write_payload_preview(payload, "last_922_setup_payload.json", log)


def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("=" * 60)
    log(f"922 Setup v{VERSION}")
    log("=" * 60)

    # --- Pick the batch folder (native folder dialog) ----------------------
    # Open the dialog at the 922 QTDR root when we can find it, so the user is
    # sitting right on the 'Batch NNN' folders.
    start_dir = ""
    try:
        root = sdk.resolve_922_root(settings.get("base_path", ""))
        if root is not None and root.exists():
            start_dir = str(root)
    except Exception:
        pass
    raw = sdk.request_directory(params, "Select the 922 batch folder", start_dir)
    if cancel_event.is_set():
        return
    if not raw:
        log("Folder selection cancelled - nothing was run.")
        cancel_event.set()  # user cancel: not a successful (ticket-earning) run
        return
    batch_path = Path(raw)
    if not batch_path.is_dir():
        log(f"ERROR: '{batch_path}' is not a folder.")
        return

    # The batch number is still needed for the card titles/buckets, so derive
    # it from the picked folder's name ('Batch 483' -> '483').
    batch = sdk.parse_922_batch(batch_path.name)
    if not batch:
        log(f"ERROR: could not read a batch number from the folder name "
            f"'{batch_path.name}'. Pick the 'Batch NNN' folder itself.")
        return
    log(f"Batch: {batch}")
    log(f"Batch folder: {batch_path}")
    progress_callback(15)

    # --- List order folders (drop the Documentation folder) ----------------
    folders: list[str] = []
    skipped: list[str] = []
    for i, entry in enumerate(sorted(batch_path.iterdir())):
        if cancel_event is not None and i % 64 == 0 and cancel_event.is_set():
            log("Cancelled.")
            return
        if not entry.is_dir():
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
    # 'apply_material_labels' is the deferred source-material feature: the
    # code path is complete, but the setting is not declared in plugin.json
    # yet, so it always resolves False. Declaring the boolean field enables it.
    apply_materials = bool(settings.get("apply_material_labels", False))
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
        warnings.append("No matching Planner label for: "
                        + ", ".join(sorted(unmatched))
                        + " - skipped (cards still created; add/rename the "
                        "label in Planner AND card_template.json to cover it).")

    cards = _build_cards(template, batch, folders, folder_labels)
    buckets = [b.format(batch=batch) for b in template.get("buckets", [])] \
        or [template.get("bucket_format", "BATCH {batch}").format(batch=batch)]
    payload = {
        "plan": template.get("plan", "D922 PIPELINE"),
        "batch": batch,
        "buckets": buckets,
        "tasks": cards,
    }

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
    url = (settings.get("webhook_url", "") or "").strip()
    dry_run = bool(settings.get("dry_run", False))

    if not url:
        log("\nNo webhook URL configured -> DRY RUN (nothing posted).")
        log("Set the Planner Webhook URL in Settings to create the cards.")
        _write_preview(payload, log)
        progress_callback(100)
        log("\nDONE (dry run).")
        return
    if dry_run:
        log("\nDry run enabled in Settings -> not posting.")
        _write_preview(payload, log)
        progress_callback(100)
        log("\nDONE (dry run).")
        return

    log("\nPosting cards to the webhook...")
    ok = sdk.post_webhook(url, payload, log)
    progress_callback(100)
    if ok:
        log(f"\nDONE. Requested {len(cards)} card(s) for Batch {batch}.")
        log("Check the D922 PIPELINE plan in Teams to confirm.")
    else:
        log("\nFAILED — see the errors above. The payload was not created.")


if __name__ == "__main__":
    # Headless smoke test: python plugins/922_setup/run.py
    # request_directory falls back to a pasted-path prompt when headless, so
    # point this at a real 'Batch NNN' folder to exercise the full flow.
    import threading
    import builtins
    builtins.input = lambda *_: r"C:\path\to\Batch 483"
    run({"log": print, "settings": {}, "console": None, "plugin_family": "922"},
        lambda p: print(f"[{p}%]"), threading.Event())
