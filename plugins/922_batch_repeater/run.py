"""
Batch Repeater Plugin for TechDeck v2.5.0
Copies repeat orders from previous batches into new batch REPEAT BATCHES folder.

v2.5.0: after the copy, every folder in REPEAT BATCHES is AUDITED for the
shop-print tube files - a 'CAD-AND-SHOP-PRINTS' folder, and `.lst` files in
the `7000` folders beneath it - using the same scan the 922 LST Organizer
pulls with (`sdk.scan_shop_print_lsts`). Nothing is pulled or organized here;
this only LOOKS. The point is timing: a repeat's CAD folder is distributed
into this batch's brand-new order folders, so if the SOURCE never had its
.lst files the new folders start life without them and nobody finds out until
the LST Organizer reports the tubes missing at the END of the batch. Only
tube parts have a 7000 folder, so "no 7000 folder" is information, not a
finding; a missing CAD folder and an empty 7000 folder are, and they end the
run in a blocking sdk.show_warning.

v2.4.0: the repeater now MAINTAINS the 922 MPL workbook instead of only
reading it. Before the repeat search, in one open/save of 922 MPL.xlsx:
  1) writes the batch's 'PO {n}' column into the PO 321+ matrix sheet,
     filled from the batch root's ORDER FOLDER NAMES ('{WO}-{PPN}', skipping
     Documentation/REPEAT BATCHES) - so a missing column fills itself and
     the old "PO isn't in the spreadsheet" dead end is gone; an existing
     column only gets blanks appended, and
  2) parses the batch's own 'PO {n} QF-QU-09 REV C' workbook (Documentation
     folder, order-folder copies as fallback) and folds every order into the
     MASTER PARTS catalog sheet via the shared master_parts.py merge engine
     - new parts appended, repeats updated (times made, batch history,
     alternate suffixes, latest WO/qty). Runs without the other half if the
     workbook (or the folders) aren't there yet.
Toggles: Settings 'update_mpl_matrix' / 'update_master_parts' and
stage_options keys 'mpl_matrix' / 'master_parts' (all default ON);
Settings 'dry_run' previews the MPL changes without saving. A locked
workbook (open in Excel) skips the MPL stage with a warning - repeat
pulling still runs.

v2.1.0: after the CAD/binder distribution, POSTs the repeats' card titles to
the 'TechDeck 922 Repeat Tagger' Power Automate flow, which adds the REPEAT
label and moves each card to the batch's MODEL CHECK bucket (see
docs/TEAMS_CARDS.md). Blank webhook URL or Dry run -> payload preview only.

v2.2.0: honors params['stage_options'] = {"distribute": bool, "tag": bool}
(both default True) so the consolidated 922 Setup's master toggle window can
switch the CAD/binder distribution and the card tagging off individually.
Standalone runs never pass the key, so behavior there is unchanged.

v2.3.0: order->folder matching is now EXACT (folder PPN or whole name equals
the MPL order), not a substring - so a '-H1' order no longer pulls a '-H11' /
'-H14' folder (11 such prefix-collision pairs exist across the real batches).
Same fix applied to the 'already pulled' check. Also removed the dead
get_console_input helper and stopped hardcoding the MPL sheet name + header
row (both are now scanned).
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# master_parts.py lives beside this file; load it by path so it resolves under
# every plugin-loader import style (dev repo AND %LOCALAPPDATA% installs).
import importlib.util as _ilu
_MP_SPEC = _ilu.spec_from_file_location(
    "techdeck_922_master_parts",
    Path(__file__).resolve().parent / "master_parts.py")
assert _MP_SPEC is not None and _MP_SPEC.loader is not None
mp = _ilu.module_from_spec(_MP_SPEC)
_MP_SPEC.loader.exec_module(mp)

# Hardcoded constants
SHEET_NAME = "PO 321+"
COMPLETED_FOLDER_NAME = "1 - Completed"

# The 'TechDeck 922 Repeat Tagger' Power Automate flow. Baked in so a fresh
# install labels cards out of the box (v0.8.6.8 shipped with a blank default
# and silently dry-ran the tagging on every machine but the author's). The
# Settings field stays as an OVERRIDE; dry_run previews without posting.
DEFAULT_REPEAT_WEBHOOK_URL = (
    "https://REDACTED-ENVIRONMENT.api"
    ".powerplatform.com:443/powerautomate/automations/direct/cu/01/workflows/"
    "REDACTED-WORKFLOW-ID/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=REDACTED"
)


_PO_HDR_RE = re.compile(r"^\s*PO\s*\d+\s*$", re.IGNORECASE)


def find_batch_root(source_po: int, base_path: Path, completed_root: Path,
                    cancel_event=None) -> Optional[Path]:
    """Locate the folder named 'Batch {source_po}'."""
    target = f"Batch {source_po}"

    # 1) Active root
    candidate1 = base_path / target
    if candidate1.exists():
        return candidate1

    # 2) Direct child of completed
    candidate2 = completed_root / target
    if candidate2.exists():
        return candidate2

    # 3) Nested child (recursive search). Poll cancel_event while walking the
    # '1 - Completed' archive — it can be a very large OneDrive tree, and without
    # the check a Cancel click can't interrupt this walk.
    if completed_root.exists():
        target_lower = target.lower()
        for i, (root, dirs, _) in enumerate(os.walk(completed_root)):
            if cancel_event is not None and i % 64 == 0 and cancel_event.is_set():
                break
            for d in dirs:
                if d.lower() == target_lower:
                    return Path(root) / d

    return None


def _audit_repeat_shop_prints(repeat_root: Path, log, cancel_event
                              ) -> Tuple[int, int, list]:
    """Check every folder in REPEAT BATCHES for the shop-print tube files the
    922 LST Organizer will later look for.

    A repeat is pulled so its CAD data can be distributed into this batch's
    brand-new order folders — so if the SOURCE folder never had its
    `CAD-AND-SHOP-PRINTS\\...\\7000\\*.lst` files, the new order folder starts
    life without them and nobody finds out until the LST Organizer reports the
    tubes missing at the end of the batch. Same scan the organizer uses
    (`sdk.scan_shop_print_lsts`) — this one only LOOKS; nothing is pulled or
    organized here.

    Only TUBE parts have a 7000 folder, so "no 7000 folder" is normal and is
    reported as information. The two actionable findings are a repeat with no
    CAD-AND-SHOP-PRINTS folder at all, and a 7000 folder holding no .lst.

    A repeat that carries its OWN nested `REPEAT\\` copy (the batch before
    last) is not counted twice: the scan treats that copy as a fallback and
    only reads it when the folder's own tree has nothing.

    Returns (folders checked, .lst files seen, [(folder name, problem), ...]).
    """
    problems: list = []
    checked = total_lsts = 0
    try:
        folders = sorted((d for d in repeat_root.iterdir() if d.is_dir()),
                         key=lambda d: d.name.lower())
    except (FileNotFoundError, PermissionError) as e:
        log(f"WARNING: could not read REPEAT BATCHES: {e}")
        return 0, 0, problems

    for folder in folders:
        sdk.raise_if_cancelled(cancel_event)
        scan = sdk.scan_shop_print_lsts(folder, cancel_event)
        checked += 1
        total_lsts += len(scan.lsts)
        if not scan.has_cad:
            problems.append((folder.name, "no CAD-AND-SHOP-PRINTS folder"))
            log(f"  ! {folder.name}: no CAD-AND-SHOP-PRINTS folder")
            continue
        if not scan.seven_k:
            log(f"    {folder.name}: CAD prints present, no 7000 folder "
                f"(no tube parts)")
            continue
        if scan.empty_7000:
            where = ", ".join(p.parent.name for p in scan.empty_7000)
            problems.append((folder.name,
                             f"{len(scan.empty_7000)} 7000 folder(s) with no "
                             f".lst file ({where})"))
            log(f"  ! {folder.name}: {len(scan.lsts)} .lst, but "
                f"{len(scan.empty_7000)} empty 7000 folder(s) - {where}")
            continue
        log(f"  ok {folder.name}: {len(scan.lsts)} .lst in "
            f"{len(scan.seven_k)} 7000 folder(s)"
            + ("  (from its own nested REPEAT copy)" if scan.from_nested else ""))
    return checked, total_lsts, problems


def _load_922_setup_template(log) -> dict:
    """Read the sibling 922 Setup plugin's card_template.json (label_map,
    title format, plan name). Both plugins live side by side in the plugins
    dir - repo AND %LOCALAPPDATA% installs - so the Planner card contract
    stays defined in one file. Returns {} (caller falls back to defaults)
    if it can't be read."""
    import json
    tpl = Path(__file__).resolve().parents[1] / "922_setup" / "card_template.json"
    try:
        with open(tpl, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"WARNING: could not read 922 Setup's card_template.json ({exc}) - "
            f"using built-in defaults.")
        return {}


def dypn_of(folder_name: str) -> Optional[str]:
    """DYPN = the order-folder name after the FIRST dash.

    e.g. 'BK531539-R7211361-H3' -> 'r7211361-h3'. This is the same key used to
    decide a folder is a repeat (the part number before the first dash changes
    between batches; the DYPN suffix is what's shared). None if there's no dash.
    Returned lower-cased for case-insensitive matching.
    """
    if "-" in folder_name:
        return folder_name.split("-", 1)[1].strip().lower()
    return None


def _order_matches_folder(order: str, folder_name: str) -> bool:
    """EXACT match between an MPL order value (a PPN like 'H7921467-H1') and an
    order folder ('X7443992-H7921467-H1'): the folder's PPN (name after the
    first dash) OR the whole folder name must equal the order. NEVER a substring,
    so a '-H1' order can't grab a '-H11' / '-H14' folder (the old bug: order
    'H7921467-H1' substring-matched 11 real '-H1x' folders across the batches)."""
    key = order.strip().lower()
    return dypn_of(folder_name) == key or folder_name.strip().lower() == key


def _resolve_po_sheet(xls, preferred: str, log) -> str:
    """Pick the MPL sheet: the preferred name if present, else the sheet whose
    first rows hold the most 'PO ###' headers (so a rename doesn't break us)."""
    for s in xls.sheet_names:
        if s.strip().casefold() == preferred.strip().casefold():
            return s
    best, best_n = None, 0
    for s in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=s, header=None, nrows=8)
        n = max((sum(1 for v in row if isinstance(v, str) and _PO_HDR_RE.match(v))
                 for _, row in raw.iterrows()), default=0)
        if n > best_n:
            best, best_n = s, n
    if best:
        log(f"WARNING: sheet '{preferred}' not found; using '{best}' ({best_n} PO columns).")
    return best or preferred


def _find_po_header_row(raw) -> int:
    """0-based index of the row with the most 'PO ###' cells (Hard Rule 2 - scan,
    don't hardcode). Falls back to the legacy row index 2."""
    best_i, best_n = 2, 0
    for i in range(min(8, len(raw))):
        n = sum(1 for v in raw.iloc[i] if isinstance(v, str) and _PO_HDR_RE.match(v))
        if n > best_n:
            best_i, best_n = i, n
    return best_i if best_n >= 3 else 2


def _read_mpl_po_columns(path: Path, preferred_sheet: str, log) -> Tuple[Any, Dict[int, str]]:
    """(dataframe, {po_num: column_name}) from the MPL PO sheet, with the sheet
    and header row resolved rather than hardcoded."""
    xls = sdk.open_excel_resilient(path, log=log)  # placeholder hydrate + locked-open message
    sheet = _resolve_po_sheet(xls, preferred_sheet, log)
    raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=8)
    hdr = _find_po_header_row(raw)
    df = pd.read_excel(xls, sheet_name=sheet, header=hdr)
    log(f"Sheet '{sheet}', header row {hdr + 1}")
    po_columns: Dict[int, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.strip().lower().startswith("po"):
            m = re.search(r"(\d+)", col)
            if m:
                po_columns[int(m.group(1))] = col
    return df, po_columns


def _write_po_matrix_column(wb, new_po_num: int, ppn_list, log) -> bool:
    """Write the batch's 'PO {n}' column into the PO 321+ matrix sheet of an
    open MPL workbook. The sheet + header row are found by scanning for
    'PO ###' header cells (Hard Rule 2). A missing column is created after the
    last PO column (header look copied from its neighbor); an existing column
    only gets PPNs it doesn't already contain appended below its last value -
    a hand-edited cell is never overwritten. Returns True if anything changed."""
    import copy as _copy
    best_ws, best_row, best_cols = None, None, {}
    for ws in wb.worksheets:
        for r_i in range(1, min(8, ws.max_row or 1) + 1):
            cols = {}
            for c_i in range(1, (ws.max_column or 1) + 1):
                v = ws.cell(r_i, c_i).value
                if isinstance(v, str) and _PO_HDR_RE.match(v):
                    m = re.search(r"(\d+)", v)
                    if m:
                        cols[int(m.group(1))] = c_i
            if len(cols) > len(best_cols):
                best_ws, best_row, best_cols = ws, r_i, cols
    if best_ws is None or len(best_cols) < 3:
        log("WARNING: couldn't find the PO matrix sheet - PO column not written.")
        return False

    changed = False
    if new_po_num in best_cols:
        col = best_cols[new_po_num]
    else:
        col = max(best_cols.values()) + 1
        hdr = best_ws.cell(best_row, col)
        hdr.value = f"PO {new_po_num}"
        left = best_ws.cell(best_row, col - 1)
        try:
            hdr.font = _copy.copy(left.font)
            hdr.fill = _copy.copy(left.fill)
            hdr.border = _copy.copy(left.border)
            hdr.alignment = _copy.copy(left.alignment)
        except Exception:
            pass
        log(f"Added column 'PO {new_po_num}' to '{best_ws.title}'")
        changed = True

    existing = []
    for r_i in range(best_row + 1, (best_ws.max_row or best_row) + 1):
        v = best_ws.cell(r_i, col).value
        if v is not None and str(v).strip():
            existing.append(str(v).strip().lower())
    next_row = best_row + 1 + len(existing)
    have = set(existing)
    added = 0
    for ppn in ppn_list:
        if ppn.strip().lower() in have:
            continue
        best_ws.cell(next_row, col, ppn)
        next_row += 1
        added += 1
    if added:
        log(f"PO {new_po_num} column: {added} order(s) written"
            + (f" (kept {len(existing)} already there)" if existing else ""))
        changed = True
    elif existing:
        log(f"PO {new_po_num} column already lists all "
            f"{len(existing)} order(s) - unchanged.")
    return changed


def _update_master_parts_sheet(wb, new_po_num: int, po_rows, quote_path,
                               log) -> bool:
    """Fold the batch's PO rows into the MASTER PARTS catalog sheet of an open
    MPL workbook via the shared merge engine. Orders whose PPN already records
    this batch are skipped (idempotent re-runs). Returns True if the sheet was
    rewritten."""
    import datetime as _dt
    if mp.MASTER_SHEET_NAME not in wb.sheetnames:
        log(f"WARNING: no '{mp.MASTER_SHEET_NAME}' sheet in the MPL - run the "
            "initial build (tools/mpl_build_master.py) first; skipped.")
        return False
    cat = mp.read_master_sheet(wb[mp.MASTER_SHEET_NAME])
    today = _dt.date.today().isoformat()

    occ: Dict[Tuple[str, str], list] = {}
    for r in po_rows:
        occ.setdefault((r["order"], r["ppn"]), []).append(r)
    merged = skipped = 0
    for (wo, ppn), rows in occ.items():
        if cat.has_batch(ppn, new_po_num):
            skipped += 1
            continue
        cat.merge_occurrence(ppn, new_po_num, wo, rows, today)
        merged += 1
    if merged == 0:
        log(f"MASTER PARTS already records batch {new_po_num} for all "
            f"{skipped} order(s) - nothing to add.")
        return False
    cat.finalize_times_made()
    try:
        pricing = mp.load_pricing_map(quote_path, log=log)
        cat.apply_part_types(pricing)
    except Exception as exc:
        log(f"WARNING: couldn't read the Quote MATERIAL PRICING sheet ({exc})"
            " - existing part types kept, new parts typed from tube serials "
            "only.")
        cat.apply_part_types({}, only_untyped=True)
    for w in cat.warnings:
        log(f"  note: {w}")
    mp.write_master_sheet(wb, cat.sorted_rows())
    if mp.ANALYSIS_SHEET_NAME not in wb.sheetnames:
        mp.write_analysis_sheet(wb)
        log("ANALYSIS sheet was missing - recreated it.")
    log(f"MASTER PARTS updated: {merged} order(s) folded in"
        + (f", {skipped} already recorded" if skipped else "")
        + f" - {len(cat.rows)} catalog rows total.")
    return True


def _batch_folder_ppns(batch_folder: Path, log) -> list:
    """PPNs read off the batch root's ORDER FOLDER NAMES ('{WO}-{PPN}' - the
    text after the first dash), skipping the Documentation folder and REPEAT
    BATCHES. These fill the PO 321+ column (user-specified source: the
    folders, not the PO workbook - so the column fills even when the workbook
    is missing or blank)."""
    ppns: list = []
    seen = set()
    try:
        for entry in sorted(os.listdir(batch_folder)):
            p = batch_folder / entry
            n = entry.lower()
            if not p.is_dir() or "documentation" in n or "repeat" in n:
                continue
            if "-" not in entry:
                continue
            ppn = entry.split("-", 1)[1].strip()
            if ppn and ppn.lower() not in seen:
                seen.add(ppn.lower())
                ppns.append(ppn)
    except OSError as e:
        log(f"WARNING: could not scan the batch folder for order folders: {e}")
    return ppns


def _update_mpl_sheets(spreadsheet_path: Path, quote_path: Path,
                       new_po_num: int, batch_folder: Path, do_matrix: bool,
                       do_master: bool, dry_run: bool, log) -> int:
    """v2.4.0 stage: maintain the MPL in ONE open/save. The PO 321+ column is
    filled from the batch's ORDER FOLDER NAMES; the MASTER PARTS catalog from
    the batch's own PO workbook (which has the DYPN/material/qty detail the
    folder names don't). Either half can proceed without the other. Returns
    the error count (0 or 1) - a locked/unreadable MPL is a warning, never a
    run-killer, so repeat pulling still happens."""
    ppn_list = _batch_folder_ppns(batch_folder, log) if do_matrix else []
    if do_matrix and not ppn_list:
        log("WARNING: no order folders in the batch root yet - the PO column "
            "can't be filled from them this run.")

    po_rows = []
    if do_master:
        res = mp.extract_batch(batch_folder, new_po_num, log=log)
        if res["status"] != "ok":
            reasons = {
                "old_rev": "the batch's PO workbook isn't REV C",
                "no_po_workbook": f"no 'PO {new_po_num} QF-QU-09 REV C' "
                                  "workbook in the batch's Documentation or "
                                  "order folders",
            }
            log(f"WARNING: MASTER PARTS update skipped - "
                f"{reasons.get(res['status'], res.get('error', res['status']))}.")
        else:
            for w in res["warnings"]:
                log(f"  note: {w}")
            log(f"Parsed {len(res['rows'])} PO rows from '{res['path'].name}'")
            po_rows = res["rows"]

    if not ppn_list and not po_rows:
        return 0

    try:
        wb = sdk.load_workbook_resilient(spreadsheet_path, log=log)
    except sdk.UserFacingError as exc:
        log(f"WARNING: {exc.problem} MPL update skipped - repeat pulling "
            "continues.")
        return 1
    try:
        changed = False
        if do_matrix and ppn_list:
            changed |= _write_po_matrix_column(wb, new_po_num, ppn_list, log)
        if do_master and po_rows:
            changed |= _update_master_parts_sheet(
                wb, new_po_num, po_rows, quote_path, log)
        if not changed:
            return 0
        if dry_run:
            log("Dry run enabled in Settings -> MPL changes NOT saved.")
            return 0
        wb.save(spreadsheet_path)
        log("MPL saved.")
        return 0
    except PermissionError:
        log(f"WARNING: '{spreadsheet_path.name}' is open in another program "
            "(usually Excel) - MPL changes NOT saved. Close it and re-run to "
            "record this batch; repeat pulling continues.")
        return 1
    finally:
        wb.close()


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    """
    Main plugin execution function.
    
    Args:
        params: Dictionary containing 'settings', 'console', and 'log'
        progress_callback: Function to call with progress (0-100)
        cancel_event: threading.Event to check for cancellation
    """
    settings = params.get('settings', {})
    log = params.get('log', print)  # Get log callback

    # Stage toggles from the consolidated 922 Setup's master window (absent on
    # standalone runs -> everything on).
    stage_options = params.get('stage_options') or {}
    do_distribute = bool(stage_options.get('distribute', True))
    do_tag = bool(stage_options.get('tag', True))
    do_mpl_matrix = (bool(settings.get('update_mpl_matrix', True))
                     and bool(stage_options.get('mpl_matrix', True)))
    do_master_parts = (bool(settings.get('update_master_parts', True))
                       and bool(stage_options.get('master_parts', True)))

    log("Starting 922 Batch Repeater v2.5.0...")
    progress_callback(0)
    
    # Base directory is an optional override; auto-discover by default so the
    # user never has to configure a path everyone already shares.
    base_directory = settings.get('base_directory', '')
    spreadsheet_filename = (settings.get('spreadsheet_filename', '') or '').strip() or '922 MPL.xlsx'

    base_path = sdk.resolve_922_root(base_directory)
    if base_path is None or not base_path.exists():
        raise sdk.UserFacingError(
            "Couldn't find the '922 QTDR Production Packages' folder.",
            "Make sure OneDrive is synced, or set the Base Directory in this "
            "plugin's Settings, then run again.")

    spreadsheet_path = base_path / spreadsheet_filename
    if not spreadsheet_path.exists():
        raise sdk.UserFacingError(
            f"Couldn't find the spreadsheet '{spreadsheet_filename}'.",
            "Make sure OneDrive is synced and the file name matches this "
            "plugin's Settings, then run again.")

    completed_root = base_path / COMPLETED_FOLDER_NAME
    
    log("")
    log(f"Base directory: {base_path}")
    log(f"Spreadsheet: {spreadsheet_path.name}")
    log(f"Sheet: {SHEET_NAME}")
    log("")
    
    progress_callback(5)
    
    # === ASK FOR BATCH FOLDER NAME ===
    log("Input required from user...")
    batch_name_input = sdk.request_batch_number(
        params,
        "Enter batch number or full folder name (e.g., '429' or 'Batch 429')"
    )

    raw_input = batch_name_input.strip()
    if not raw_input:
        raise sdk.UserFacingError(
            "No batch number was entered.",
            "Run it again and type the batch number (e.g. '429').")

    # Extract a number from whatever the user typed
    num_match = re.search(r'\d+', raw_input)
    if num_match:
        extracted_num = num_match.group()
        # Search base_path for any folder whose name contains that exact number
        # (not preceded or followed by another digit, so "467" won't match "14670")
        number_pattern = re.compile(r'(?<!\d)' + re.escape(extracted_num) + r'(?!\d)')
        matched_folder = None
        try:
            for entry in os.listdir(base_path):
                if (base_path / entry).is_dir() and number_pattern.search(entry):
                    matched_folder = entry
                    break
        except (FileNotFoundError, PermissionError) as e:
            log(f"WARNING: Could not scan base directory: {e}")

        if matched_folder:
            actual_batch_name = matched_folder
            log(f"Matched existing folder: {actual_batch_name}")
        else:
            actual_batch_name = f"Batch {extracted_num}"
            log(f"No existing folder found - will create: {actual_batch_name}")
    else:
        # No number in input - use raw input as folder name (will create new)
        actual_batch_name = raw_input
        log(f"Using batch name: {actual_batch_name}")
    
    # === EXTRACT PO NUMBER FROM BATCH NAME ===
    # Look for numbers in the batch name
    po_match = re.search(r'\d+', actual_batch_name)
    if not po_match:
        raise sdk.UserFacingError(
            f"There's no number in what you entered ('{actual_batch_name}').",
            "Run it again and include the batch number (e.g. 'Batch 429').")
    
    new_po_num = int(po_match.group())
    log(f"Extracted PO: {new_po_num}")
    
    log("")
    log(f"PO Number: {new_po_num}")
    log(f"Batch folder: {actual_batch_name}")
    log("")
    
    progress_callback(10)
    
    # Check for cancellation
    if cancel_event.is_set():
        log("Operation cancelled")
        return

    # === v2.4.0: MAINTAIN THE MPL (PO column + MASTER PARTS catalog) ========
    # The batch folder is needed first - the batch's own PO workbook lives in
    # its Documentation/order folders.
    new_po_folder = base_path / actual_batch_name
    new_po_folder.mkdir(exist_ok=True)
    log(f"Batch folder: {new_po_folder.name}")

    mpl_errors = 0
    if do_mpl_matrix or do_master_parts:
        log("")
        log("Updating the MPL from the batch's PO workbook...")
        quote_path = base_path / "2 - Planning" / "EB 922 H# Quote.xlsx"
        mpl_errors = _update_mpl_sheets(
            spreadsheet_path, quote_path, new_po_num, new_po_folder,
            do_mpl_matrix, do_master_parts,
            bool(settings.get('dry_run', False)), log)
        log("")
    else:
        log("MPL updates switched OFF.")

    # Read the MPL and identify PO columns (sheet + header row auto-resolved,
    # not hardcoded - Hard Rule 2).
    log("Reading Excel spreadsheet...")
    try:
        sdk.ensure_local(spreadsheet_path, log)  # OneDrive placeholder -> download first (Hard Rule 13)
        df, po_columns = _read_mpl_po_columns(spreadsheet_path, SHEET_NAME, log)
    except Exception as e:
        log(f"ERROR: Error reading spreadsheet: {e}")
        raise RuntimeError(f"Error reading spreadsheet: {e}")

    progress_callback(15)

    if not po_columns:
        raise sdk.UserFacingError(
            "No PO columns were found in the spreadsheet.",
            "Check that the MPL has its usual 'PO ###' header row, then run again.")

    log(f"Found {len(po_columns)} PO columns")
    progress_callback(20)
    
    # Check if new PO exists. Normally the MPL stage above just wrote it from
    # the batch's PO workbook; landing here means that stage was off, dry-run,
    # skipped (no REV C workbook), or the save was blocked.
    if new_po_num not in po_columns:
        available_pos = sorted(po_columns.keys())
        raise sdk.UserFacingError(
            f"PO {new_po_num} isn't in the spreadsheet.",
            "TechDeck adds it automatically from the batch's 'PO {n} QF-QU-09 "
            "REV C' workbook - make sure that workbook is in the batch's "
            "Documentation folder, the MPL isn't open in Excel, and the "
            "'Update MPL' settings are on. Otherwise add the column by hand. "
            f"POs currently there: {available_pos}.")
    
    new_po_col = po_columns[new_po_num]
    log(f"Using column '{new_po_col}'")
    
    # REPEAT BATCHES is created later, only after the user has chosen which
    # repeats to pull (so a cancelled run leaves no folder). new_po_folder
    # itself was already created before the MPL stage above.
    repeat_batch_folder = new_po_folder / "REPEAT BATCHES"

    progress_callback(25)
    
    # Get unique orders
    log("Analyzing orders...")
    new_po_orders = {
        str(order).strip()
        for order in df[new_po_col]
        if pd.notna(order) and str(order).strip()
    }
    log(f"Found {len(new_po_orders)} unique orders")
    
    progress_callback(30)
    
    # Find source PO for each order
    log("Searching for repeat orders...")
    orders_to_copy: Dict[str, int] = {}
    
    for order in new_po_orders:
        source_po_num = None
        for po_num, col in po_columns.items():
            if po_num >= new_po_num:
                continue
            
            column_values = df[col].dropna().astype(str).str.strip()
            if order in column_values.values:
                if source_po_num is None or po_num > source_po_num:
                    source_po_num = po_num
        
        if source_po_num is not None:
            orders_to_copy[order] = source_po_num
    
    log(f"Found {len(orders_to_copy)} repeat orders")
    progress_callback(35)
    
    if not orders_to_copy:
        log("No repeat orders! All new!")
        progress_callback(100)
        return

    # ------------------------------------------------------------------ #
    # Let the user choose which repeats to pull (911-Setup-style dialog).
    # Orders whose folder already sits in REPEAT BATCHES are flagged
    # "already pulled" so a re-run reads differently from a fresh run;
    # re-running overwrites them. Selection happens up front -- nothing
    # below copies until the user submits the dialog.
    # ------------------------------------------------------------------ #
    existing_repeat_dirs = []
    if repeat_batch_folder.exists():
        existing_repeat_dirs = [d.name for d in repeat_batch_folder.iterdir() if d.is_dir()]
    done_orders = {
        order for order in orders_to_copy
        if any(_order_matches_folder(order, name) for name in existing_repeat_dirs)
    }
    if done_orders:
        log(f"{len(done_orders)} repeat(s) already pulled in a prior run")

    console = params.get("console")
    if console is not None and hasattr(console, "request_selection"):
        ordered_orders = sorted(orders_to_copy.keys(), key=str.lower)
        selection = sdk.request_selection(
            params,
            ordered_orders,
            done_orders,
            window_title=f"922 Batch Repeater - {actual_batch_name}",
            header="Select Repeats to Pull",
            root_label=f"{actual_batch_name}  (all repeats)",
            noun="repeat order",
            done_label="already pulled",
            subhead_prefix=f"{actual_batch_name} - ",
            prompt_note="Check the repeats you want to pull.",
        )
        if selection is None:
            log("Repeat selection cancelled -- nothing was pulled.")
            return   # sdk.request_selection already flagged the cancel
        chosen = set(selection)
        orders_to_copy = {o: s for o, s in orders_to_copy.items() if o in chosen}
        if not orders_to_copy:
            log("No repeats selected -- nothing to do.")
            cancel_event.set()
            return
        log(f"Pulling {len(orders_to_copy)} repeat(s)")

    # Create the destination only now that we know there's something to pull.
    repeat_batch_folder.mkdir(exist_ok=True)
    log("Created: REPEAT BATCHES")
    log("")
    log("Copying order folders...")
    
    # Copy folders with progress
    copied_count = 0
    not_found_count = 0
    error_count = mpl_errors  # a skipped MPL save counts as a warning-level error
    copied_repeats: list = []  # destination folders inside REPEAT BATCHES (for DYPN distribution below)
    
    total_orders = len(orders_to_copy)
    base_progress = 35
    progress_range = 60
    
    for idx, (order, source_po) in enumerate(orders_to_copy.items()):
        if cancel_event.is_set():
            log("")
            log("WARNING: Cancelled by user")
            log(f"Copied {copied_count} of {total_orders}")
            return
        
        progress = base_progress + int((idx / total_orders) * progress_range)
        progress_callback(progress)

        # Locating a batch may walk the whole '1 - Completed' archive (slow on a
        # large OneDrive tree); announce it first so the walk doesn't look frozen.
        log(f"[{idx + 1}/{total_orders}] Locating Batch {source_po} for {order}...")
        batch_root = find_batch_root(source_po, base_path, completed_root, cancel_event)
        
        if not batch_root:
            log(f"WARNING: Batch {source_po} not found for {order}")
            not_found_count += 1
            continue
        
        found_folder = None
        try:
            for entry in os.listdir(batch_root):
                entry_path = batch_root / entry
                if entry_path.is_dir() and _order_matches_folder(order, entry):
                    found_folder = entry_path
                    break
        except (FileNotFoundError, PermissionError) as e:
            log(f"ERROR: Error accessing Batch {source_po}: {e}")
            error_count += 1
            continue
        
        if not found_folder:
            log(f"WARNING: '{order}' not found in Batch {source_po}")
            not_found_count += 1
            continue
        
        destination_folder = repeat_batch_folder / found_folder.name
        try:
            shutil.copytree(found_folder, destination_folder, dirs_exist_ok=True)
            log(f"Copied {order} from Batch {source_po}")
            copied_count += 1
            copied_repeats.append(destination_folder)
        except Exception as e:
            log(f"ERROR: Failed to copy {order}: {e}")
            error_count += 1
    
    progress_callback(88)

    # === Audit the repeats' shop prints (look only - nothing is pulled) =====
    # Everything sitting in REPEAT BATCHES, not just what this run copied: a
    # repeat pulled last week is still feeding this batch. See
    # _audit_repeat_shop_prints for why "no 7000 folder" isn't a finding.
    lst_problems: list = []
    if repeat_batch_folder.exists() and not cancel_event.is_set():
        log("")
        log("Checking repeat folders for CAD-AND-SHOP-PRINTS / 7000 .lst files...")
        checked, total_lsts, lst_problems = _audit_repeat_shop_prints(
            repeat_batch_folder, log, cancel_event)
        log(f"Shop prints: {total_lsts} .lst file(s) across {checked} repeat "
            f"folder(s); {len(lst_problems)} need attention.")

    progress_callback(90)

    # === Distribute CAD prints + binders into matching root order folders ===
    # Each repeat shares a DYPN (folder name after the first dash) with one or
    # more brand-new order folders sitting at the batch root. Copy the repeat's
    # CAD-AND-SHOP-PRINTS folder and Binder*.pdf into EVERY root folder that
    # shares its DYPN (e.g. repeat 'BK531539-R7211361-H3' feeds root folder
    # 'BL416682-R7211361-H3').
    distributed_count = 0
    repeat_roots: set = set()  # root order folders that ARE repeats (for card tagging)
    if copied_repeats and not cancel_event.is_set():
        log("")
        if do_distribute:
            log("Distributing CAD prints + binders to matching root folders...")
        else:
            # The DYPN matching still runs (card tagging needs repeat_roots);
            # only the copies are skipped.
            log("CAD/binder distribution switched OFF - matching repeats to "
                "root folders for card tagging only.")

        # Map DYPN -> [root order folders] (direct children of the batch root,
        # excluding REPEAT BATCHES and the batch Documentation folder).
        root_by_dypn: Dict[str, list] = {}
        try:
            for entry in os.listdir(new_po_folder):
                entry_path = new_po_folder / entry
                if not entry_path.is_dir():
                    continue
                if entry == "REPEAT BATCHES" or "documentation" in entry.lower():
                    continue
                dypn = dypn_of(entry)
                if dypn:
                    root_by_dypn.setdefault(dypn, []).append(entry_path)
        except (FileNotFoundError, PermissionError) as e:
            log(f"WARNING: Could not scan batch root for matches: {e}")

        for i, repeat_folder in enumerate(copied_repeats):
            if cancel_event.is_set():
                log("WARNING: Cancelled by user")
                break

            dypn = dypn_of(repeat_folder.name)
            matches = root_by_dypn.get(dypn, []) if dypn else []
            if not matches:
                log(f"  {repeat_folder.name}: no matching root order folder - "
                    f"its card will NOT be tagged as a repeat")
                continue
            repeat_roots.update(m.name for m in matches)
            if not do_distribute:
                continue

            # Locate the CAD folder and binder PDF inside the copied repeat.
            cad_src = None
            binder_src = None
            try:
                for child in repeat_folder.iterdir():
                    if child.is_dir() and "cad" in child.name.lower():
                        cad_src = child
                    elif (child.is_file()
                          and child.name.lower().startswith("binder")
                          and child.suffix.lower() == ".pdf"):
                        binder_src = child
            except (FileNotFoundError, PermissionError) as e:
                log(f"ERROR: Could not read {repeat_folder.name}: {e}")
                error_count += 1
                continue

            if not cad_src and not binder_src:
                continue

            for dest_root in matches:
                try:
                    if cad_src:
                        shutil.copytree(cad_src, dest_root / cad_src.name, dirs_exist_ok=True)
                    if binder_src:
                        sdk.ensure_local(binder_src, log)  # Hard Rule 13
                        shutil.copy2(binder_src, dest_root / binder_src.name)
                    log(f"  {repeat_folder.name} -> {dest_root.name}")
                    distributed_count += 1
                except Exception as e:
                    log(f"ERROR: Failed {repeat_folder.name} -> {dest_root.name}: {e}")
                    error_count += 1

    # === Tag the repeats' cards in Planner (REPEAT label + MODEL CHECK) =====
    # Every root order folder that DYPN-matched a pulled repeat IS a repeat
    # order: its Planner card (created by 922 Setup) gets the REPEAT label and
    # moves to the batch's MODEL CHECK bucket, via the 'TechDeck 922 Repeat
    # Tagger' Power Automate flow (recipe in docs/TEAMS_CARDS.md). The label
    # slot + title format come from 922 Setup's card_template.json so the
    # Planner contract lives in exactly one place.
    if repeat_roots and not do_tag:
        log("")
        log("Card labeling switched OFF - repeat cards were NOT labeled in Teams.")
    if do_tag and repeat_roots and not cancel_event.is_set():
        log("")
        log("Labeling repeat cards in Teams (REPEAT label + MODEL CHECK bucket)...")
        template = _load_922_setup_template(log)
        repeat_slot = (template.get("label_map") or {}).get("REPEAT")
        if not repeat_slot:
            repeat_slot = "category19"
            log("WARNING: no REPEAT entry in 922 Setup's label_map - "
                "assuming category19 (Teal).")
        title_fmt = template.get("title_format", "BATCH {batch}: {folder}")
        payload = {
            "plan": template.get("plan", "D922 PIPELINE"),
            "batch": str(new_po_num),
            "bucket": f"BATCH {new_po_num}: MODEL CHECK",
            "label": repeat_slot,
            "titles": [title_fmt.format(batch=new_po_num, folder=name)
                       for name in sorted(repeat_roots, key=str.lower)],
        }
        log(f"{len(payload['titles'])} card(s) to tag:")
        for t in payload["titles"]:
            log(f"  - {t}")

        url = ((settings.get('repeat_webhook_url', '') or '').strip()
               or DEFAULT_REPEAT_WEBHOOK_URL)
        dry_run = bool(settings.get('dry_run', False))
        if dry_run:
            log("Dry run enabled in Settings -> not posting.")
            sdk.write_payload_preview(payload, "last_922_repeat_tag_payload.json", log)
        else:
            if sdk.post_webhook(url, payload, log):
                log(f"Repeat cards should now sit in 'BATCH {new_po_num}: MODEL CHECK' "
                    "with the REPEAT label - check the D922 PIPELINE board "
                    "in Teams.")
            else:
                error_count += 1

    progress_callback(95)

    # Summary
    log("")
    log("=" * 50)
    log("COPY SUMMARY")
    log("=" * 50)
    log(f"Successfully copied: {copied_count}")
    log(f"CAD/binder distributed to root folders: {distributed_count}")

    if not_found_count > 0:
        log(f"Not found: {not_found_count}")

    if error_count > 0:
        log(f"Errors: {error_count}")

    if lst_problems:
        log(f"Repeats missing shop-print .lst files: {len(lst_problems)}")

    log("=" * 50)

    # The .lst gap is what bites at the END of the batch (the LST Organizer
    # reports the tubes missing), so raise it now rather than let it scroll by
    # inside a 4-stage 922 Setup run.
    if lst_problems:
        sdk.show_warning(
            params, "922 Batch Repeater - repeat shop prints",
            "These repeat folders are missing the tube .lst files the 922 LST "
            "Organizer will look for. Their CAD prints get distributed into "
            "this batch's order folders as-is, so the tubes will read as "
            "missing at the end of the batch unless the source is fixed:\n\n"
            + "\n".join(f"  - {name}: {why}" for name, why in lst_problems))

    progress_callback(100)
    
    if error_count > 0 or not_found_count > 0:
        log("WARNING: Completed with warnings")
    else:
        log("All done successfully!")


if __name__ == "__main__":
    # Standalone testing
    import threading
    
    test_settings = {
        'base_directory': input("Base directory path: ").strip(),
        'spreadsheet_filename': input("Spreadsheet filename [922 MPL.xlsx]: ").strip() or "922 MPL.xlsx"
    }
    
    cancel_event = threading.Event()
    
    def progress(p):
        print(f"Progress: {p}%")
    
    try:
        run(
            params={'settings': test_settings, 'console': None},
            progress_callback=progress,
            cancel_event=cancel_event
        )
        print("\nDone!")
    except Exception as e:
        print(f"\nERROR: Failed: {e}")
