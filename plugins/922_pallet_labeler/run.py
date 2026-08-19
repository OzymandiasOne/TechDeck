"""
922 Pallet Labeler
==================
Applies each order's PALLET 1/2/3 label to the order's EXISTING Teams card on
the D922 PIPELINE board. It never creates a card - it is the second pass for
the (routine) case where the cards were generated before anyone filled in the
batch's Pallet & Rod Organizer.

Why this exists (batch 489, 2026-08-18)
---------------------------------------
922 Setup's "Generate Teams Cards" stage reads the Pallet Organizer at card-
creation time. Batch 489's cards were posted at 11:17 AM, before the pallet
assignments were entered, so all 37 cards went up with an EMPTY ``labels``
array (confirmed in the flow's run history). Batch 490, set up the same
afternoon with a filled organizer, labelled fine. The cards can't be re-posted
without duplicating them - hence a tool that labels what is already there.

Flow:
  1. Pick the 'Batch NNN' folder (sdk.request_922_batch_folder - family cache,
     Sentry Drone capable). No typed batch number, ever.
  2. Load the sibling 922_setup plugin and reuse ITS organizer reader, label
     resolver and card_template.json. The pallet->slot contract stays defined
     in exactly one place; this plugin never forks it.
  3. List the batch's order folders (same ignore rules as 922 Setup).
  4. Resolve each folder to its pallet label slot ('category2' = PALLET 1 etc).
  5. POST {plan, batch, cards:[{title, labels}]} to the 'TechDeck 922 Pallet
     Labeler' Power Automate flow, which finds each card by exact title and
     writes ONLY the three pallet slots - so a card's REPEAT/material labels
     survive untouched (recipe in docs/TEAMS_CARDS.md, flow #4).

Fails loud, on purpose: if the organizer is missing/unreadable, or not one
order on it matches a folder, this raises a UserFacingError instead of posting
a no-op payload. Posting nothing quietly is exactly how batch 489 went
unnoticed.
"""

from pathlib import Path

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

VERSION = "1.0.0"

# The 'TechDeck 922 Pallet Labeler' Power Automate flow. Baked in so a fresh
# install labels out of the box - a blank default silently dry-runs on every
# machine but the author's (v0.8.6.8 shipped that way for both 922 webhooks).
# The Settings field stays as an OVERRIDE.
# TODO(flow): paste the flow's HTTP POST URL here once the flow is built, and
# ship an app update. Until then the plugin previews and reports a warning
# outcome rather than pretending it posted.
DEFAULT_LABELER_WEBHOOK_URL = ""

SETUP_PLUGIN_ID = "922_setup"


def _load_setup(log):
    """Import the sibling 922 Setup plugin - the single home of the organizer
    reader, the label resolver and the card template."""
    try:
        module = sdk.load_sibling(SETUP_PLUGIN_ID, __file__)
    except Exception as exc:
        module = None
        log(f"ERROR: could not load '{SETUP_PLUGIN_ID}': {exc}")
    if module is None or not callable(getattr(module, "_read_pallet_organizer", None)):
        raise sdk.UserFacingError(
            "The 922 Setup app is missing, so the pallet labels can't be worked out.",
            "Reinstall/update TechDeck so 922 Setup is installed alongside this app.",
        )
    return module


def _order_folders(batch_path: Path, setup, cancel_event, log) -> list:
    """The batch's order folders, using 922 Setup's own ignore rules."""
    folders: list[str] = []
    skipped: list[str] = []
    for i, entry in enumerate(sorted(batch_path.iterdir())):
        if i % 64 == 0:
            sdk.raise_if_cancelled(cancel_event)
        if not entry.is_dir():
            continue
        reason = setup._ignored_reason(entry.name)
        if reason:
            skipped.append(f"{entry.name} ({reason})")
        elif setup._is_order_folder(entry):
            folders.append(entry.name)
    if skipped:
        log(f"Skipped: {', '.join(skipped)}")
    return folders


def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("=" * 60)
    log(f"922 Pallet Labeler v{VERSION}")
    log("=" * 60)
    log("Adds the PALLET 1/2/3 label to cards that already exist.")
    log("It never creates a card - run 922 Setup for that.")
    log("")

    # --- Batch folder ------------------------------------------------------
    picked = sdk.request_922_batch_folder(params, settings.get("base_path", ""))
    if picked is None or cancel_event.is_set():
        return
    batch, batch_path = picked
    log(f"Batch: {batch}")
    log(f"Batch folder: {batch_path}")
    progress_callback(10)

    setup = _load_setup(log)

    # --- Order folders -----------------------------------------------------
    folders = _order_folders(batch_path, setup, cancel_event, log)
    if not folders:
        raise sdk.UserFacingError(
            f"Batch {batch} has no order folders in it.",
            "Pick the 'Batch NNN' folder that holds the order folders, or run "
            "922 Setup first to build them.",
        )
    log(f"Found {len(folders)} order folder(s).")
    progress_callback(30)

    # --- Pallet assignments ------------------------------------------------
    organizer, warnings = setup._read_pallet_organizer(batch_path, batch, log)
    if organizer is None:
        # The reader already explained why in `warnings` - surface it as the
        # fix text instead of posting a payload with no labels in it.
        raise sdk.UserFacingError(
            f"Couldn't read the pallet assignments for Batch {batch}, so there "
            f"are no labels to apply.",
            " ".join(warnings) or
            f"Open 'PO H{batch} Pallet & Rod Organizer.xlsx' in the batch's "
            f"Documentation folder and check the Pallet Organizer sheet.",
        )
    log(f"Pallet Organizer: {len(organizer)} order-to-pallet assignment(s).")
    progress_callback(45)

    # --- Resolve each folder's label slot ----------------------------------
    template = setup._load_template()
    label_map = {setup._norm_label(name): slot
                 for name, slot in (template.get("label_map") or {}).items()}
    title_fmt = template.get("title_format", "BATCH {batch}: {folder}")

    unmatched: set = set()
    cards: list[dict] = []
    unlabelled: list[str] = []
    for folder in folders:
        sdk.raise_if_cancelled(cancel_event)
        # apply_materials=False: this app is the PALLET pass. Material labels
        # stay 922 Setup's card-creation-time option.
        slots, names = setup._labels_for_folder(
            folder, organizer, label_map, False, warnings, unmatched)
        if not slots:
            unlabelled.append(folder)
            continue
        cards.append({
            "title": title_fmt.format(batch=batch, folder=folder),
            "labels": slots,
            "_names": names,          # log only; stripped before posting
        })
    if unmatched:
        warnings.append("No matching Teams label for: "
                        + ", ".join(sorted(unmatched)))
    progress_callback(60)

    if not cards:
        raise sdk.UserFacingError(
            f"Not one of Batch {batch}'s {len(folders)} orders is listed under "
            f"PALLET 1/2/3 on the Pallet Organizer sheet.",
            f"Fill in the pallet assignments in 'PO H{batch} Pallet & Rod "
            f"Organizer.xlsx' (Documentation folder), then run this again.",
        )

    log("")
    log(f"{len(cards)} card(s) to label:")
    for card in cards:
        log(f"  - {card['title']}   [{', '.join(card['_names'])}]")
    if unlabelled:
        log("")
        log(f"{len(unlabelled)} order(s) are not on the Pallet Organizer sheet "
            f"- their cards are left alone:")
        for name in unlabelled:
            log(f"  - {name}")

    if warnings:
        log("")
        log("Warnings:")
        for w in warnings:
            log(f"  ! {w}")

    payload = {
        "plan": template.get("plan", "D922 PIPELINE"),
        "batch": str(batch),
        "cards": [{"title": c["title"], "labels": c["labels"]} for c in cards],
    }
    progress_callback(75)

    if cancel_event.is_set():
        return

    # --- Post (or preview) -------------------------------------------------
    url = (settings.get("webhook_url", "") or "").strip() or DEFAULT_LABELER_WEBHOOK_URL
    dry_run = bool(settings.get("dry_run", False))

    if not url:
        log("")
        log("No Pallet Labeler webhook is configured - previewing only, "
            "NOTHING was sent to Teams.")
        sdk.write_payload_preview(payload, "last_922_pallet_label_payload.json", log)
        progress_callback(100)
        _warn(params, f"No webhook configured - Batch {batch}'s cards were NOT "
                      f"labeled (payload previewed only).")
        return

    if dry_run:
        log("")
        log("Dry run enabled in Settings -> not posting.")
        sdk.write_payload_preview(payload, "last_922_pallet_label_payload.json", log)
        progress_callback(100)
        log("DONE (dry run).")
        return

    log("")
    log("Posting the labels to the webhook...")
    ok = sdk.post_webhook(url, payload, log)
    progress_callback(100)
    if not ok:
        _warn(params, f"The pallet-label post failed - Batch {batch}'s cards "
                      f"were not labeled. See the errors above.")
        return

    log("")
    log(f"DONE. Requested labels for {len(cards)} card(s) in Batch {batch}.")
    log("Check the D922 PIPELINE board in Teams to confirm.")
    if unlabelled:
        _warn(params, f"{len(unlabelled)} order(s) are not on the Pallet "
                      f"Organizer sheet - their cards were left unlabeled.")


def _warn(params: dict, message: str) -> None:
    """Report a finished-but-not-clean run (guarded for older TechDecks)."""
    if hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(params, sdk.RUN_OUTCOME_WARNING, message)
    else:
        params.get("log", print)(f"WARNING: {message}")
