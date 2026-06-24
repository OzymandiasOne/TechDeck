"""
922 Setup
=========
Creates one Microsoft Planner card per order folder in a 922 batch.

Flow:
  1. Prompt for the batch number (family-shared via the SDK).
  2. Resolve the '922 QTDR Production Packages' root and locate 'Batch {n}'
     (same logic as every other 922 plugin).
  3. List the order folders directly under the batch folder, dropping the
     'Batch {n} - Documentation' and 'REPEAT BATCHES' folders (and any
     temp/hidden entries).
  4. Build one card per folder from card_template.json:
       title    = "BATCH {batch}: {folder}"
       bucket   = "BATCH {batch}"
       priority = Medium, status = Not started
       checklist= TL Print / Saw Print / Inspection Sheet / Program /
                  Processing Completed
  5. POST the cards as JSON to a Power Automate webhook, which creates the
     tasks in the D922 PIPELINE plan. With no webhook URL (or dry_run on) it
     just previews the payload and writes it to disk for inspection.

The card layout lives in card_template.json so it can be edited without
touching this code. Power Automate flow setup is documented in
docs/TEAMS_CARDS.md.
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

VERSION = "1.0.0"

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


def _is_order_folder(entry: Path) -> bool:
    if not entry.is_dir():
        return False
    name = entry.name
    if name.startswith(("~", ".", "$")):
        return False
    if _ignored_reason(name):
        return False
    return True


def _build_cards(template: dict, batch: str, folders: list[str]) -> list[dict]:
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
        })
    return cards


def _post_cards(url: str, payload: dict, log, cancel_event):
    """POST the payload to the Power Automate webhook. Returns True on success."""
    import requests  # bundled (the updater uses it); respects corporate proxies

    try:
        resp = requests.post(url, json=payload, timeout=60)
    except requests.exceptions.RequestException as exc:
        log(f"ERROR: could not reach the webhook: {exc}")
        log("Check the URL in Settings, your network/VPN, and that the flow is on.")
        return False

    if 200 <= resp.status_code < 300:
        log(f"Webhook accepted the request (HTTP {resp.status_code}).")
        body = (resp.text or "").strip()
        if body:
            log(f"Response: {body[:500]}")
        return True

    log(f"ERROR: webhook returned HTTP {resp.status_code}.")
    log(f"Response: {(resp.text or '')[:500]}")
    return False


def _write_preview(payload: dict, log) -> None:
    """Save the built payload next to TechDeck's data for inspection."""
    import os
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    out = Path(base) / "TechDeck" / "last_922_setup_payload.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        log(f"Preview written to: {out}")
    except OSError as exc:
        log(f"(Could not write preview file: {exc})")


def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("=" * 60)
    log(f"922 Setup v{VERSION}")
    log("=" * 60)

    # --- Batch number (family-shared) --------------------------------------
    raw = sdk.request_batch_number(params, "Enter the 922 batch number:")
    if cancel_event.is_set():
        return
    batch = sdk.parse_922_batch(raw)
    if not batch:
        log(f"ERROR: '{raw}' is not a valid batch number.")
        return
    log(f"Batch: {batch}")

    # --- Locate the batch folder (same logic as other 922 apps) ------------
    root = sdk.resolve_922_root(settings.get("base_path", ""))
    if root is None or not root.exists():
        log("ERROR: could not find the '922 QTDR Production Packages' root.")
        log("Set it in Settings, or right-click the folder in OneDrive -> "
            "'Always keep on this device'.")
        return
    batch_path = sdk.find_922_batch_path(root, batch)
    if batch_path is None:
        log(f"ERROR: Batch {batch} not found under {root}.")
        return
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

    # --- Build the cards from the template ---------------------------------
    try:
        template = _load_template()
    except (OSError, json.JSONDecodeError) as exc:
        log(f"ERROR: could not read card_template.json: {exc}")
        return
    cards = _build_cards(template, batch, folders)
    payload = {
        "plan": template.get("plan", "D922 PIPELINE"),
        "batch": batch,
        "tasks": cards,
    }

    log(f"\nWill create {len(cards)} card(s) in plan '{payload['plan']}', "
        f"bucket 'BATCH {batch}':")
    for card in cards:
        log(f"  - {card['title']}")
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
    ok = _post_cards(url, payload, log, cancel_event)
    progress_callback(100)
    if ok:
        log(f"\nDONE. Requested {len(cards)} card(s) for Batch {batch}.")
        log("Check the D922 PIPELINE plan in Teams to confirm.")
    else:
        log("\nFAILED — see the errors above. The payload was not created.")


if __name__ == "__main__":
    # Headless smoke test: python plugins/922_setup/run.py
    import threading
    import builtins
    builtins.input = lambda *_: "483"
    run({"log": print, "settings": {}, "console": None, "plugin_family": "922"},
        lambda p: print(f"[{p}%]"), threading.Event())
