r"""
911 Repeater Plugin
===================
v3.0.0 — MPL-driven repeat pull, rebuilt around the modern 911 workflow.

Finds repeat parts for a 911 QTDR batch by looking each nest's DYPNs up in
the 911 MASTER PARTS LIST (compiled from completed nests by
tools/build_911_mpl.py; lives in the REPEATER folder). A repeat part's
CAD-AND-SHOP-PRINTS folder (SolidWorks model + drawing + PDF) is copied from
the completed source nest into a REPEAT folder INSIDE the target nest:

  911 QTDR\{batch}\{nest}\REPEAT\{DYPN}\{DYPN}.pdf / .SLDPRT / .SLDDRW

There is no batch-level repeats folder — repeats land per nest. The legacy
NC / inspection-library grabbing (v1–v2) is gone with the workflow it served.

Workflow:
  1. Prompt for batch number (e.g. V109, S045)
  2. Locate the LIVE batch folder directly under the 911 QTDR root
  3. Load the MASTER PARTS LIST (Settings override, else the REPEATER folder)
     and index DYPN -> source nest folders
  4. For each nest subfolder (nest-number-shaped names only), read DYPNs from
     the nest's 911 BATCH workbook — NEST sheet, DYPN column found by header
  5. Nest-selection window: checkable nest rows (part + repeat counts, a flag
     when REPEAT already has files; all start unchecked); clicking a nest's
     NAME expands its grab options — SolidWorks models / part PDFs /
     overwrite. Cancelling runs nothing. Headless: 'nests' list + 'grab'
     option-override dict; default = all nests, default options.
  6. Per selected nest, copy each repeat DYPN's files (per that nest's
     options) from its source nest into {nest}\REPEAT\{DYPN}\
  7. Report summary (copy errors end the run with a warning outcome)
"""

import re
import shutil
from pathlib import Path

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk


MPL_FILENAME = "911 MASTER PARTS LIST.xlsx"

# Nest-number-shaped folder names (Hard Rule 3) — filters out support folders
# like NEST PACKAGES / DTSV FILES / WPDD SKETCHES in the batch folder.
_NEST_RE = re.compile(r"^(?:[PS]?\d{3,}|(?=[A-Z0-9]*\d)[A-Z0-9]{4,8})$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Master Parts List
# ---------------------------------------------------------------------------

def _default_mpl_path(qtdr_root: Path) -> Path:
    return (qtdr_root / "04 - Notes - Protocols - Tutorials" / "TECH SERVICES"
            / "REPEATER" / MPL_FILENAME)


def _load_mpl_index(mpl_path: Path, log) -> dict[str, list[dict]]:
    """DYPN (upper) -> [{'batch','nest','status','rel'}] from the MPL."""
    wb = sdk.load_workbook_resilient(mpl_path, data_only=True, log=log)
    try:
        ws = wb.active
        header_row, cols = sdk.find_header_row(ws, ["DYPN", "SOURCE FOLDER"])
        if header_row is None:
            raise sdk.UserFacingError(
                f"{mpl_path.name} has no DYPN / SOURCE FOLDER header row.",
                "Rebuild the list with tools/build_911_mpl.py (its layout may "
                "have been edited).")
        c_dypn = cols.get("DYPN")
        c_batch = cols.get("BATCH")
        c_nest = cols.get("NEST")
        c_status = cols.get("STATUS")
        c_rel = cols.get("SOURCE FOLDER")

        index: dict[str, list[dict]] = {}
        for row in range(header_row + 1, ws.max_row + 1):
            dypn = ws.cell(row, c_dypn).value
            rel = ws.cell(row, c_rel).value if c_rel else None
            if not dypn or not rel:
                continue
            index.setdefault(str(dypn).strip().upper(), []).append({
                "batch": str(ws.cell(row, c_batch).value or "").strip() if c_batch else "",
                "nest": str(ws.cell(row, c_nest).value or "").strip() if c_nest else "",
                "status": str(ws.cell(row, c_status).value or "").strip() if c_status else "",
                "rel": str(rel).strip(),
            })
        return index
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# Nest discovery
# ---------------------------------------------------------------------------

def _find_nest_excel(nest_folder: Path, batch_number: str, nest_number: str) -> Path | None:
    expected = nest_folder / f"911 BATCH {batch_number} {nest_number}.xlsx"
    if expected.exists():
        return expected
    candidates = [
        f for f in nest_folder.glob("*.xlsx")
        if "batch" in f.name.lower() and not f.name.startswith("~")
    ]
    return candidates[0] if candidates else None


def _read_dypns(excel_path: Path, log) -> list[str]:
    """DYPNs from the nest workbook's NEST sheet, column found by header name."""
    wb = sdk.load_workbook_resilient(excel_path, data_only=True, log=log)
    try:
        if "NEST" not in wb.sheetnames:
            return []
        ws = wb["NEST"]
        header_row, cols = sdk.find_header_row(ws, ["DYPN"])
        if header_row is None:
            return []
        col = cols.get("DYPN")
        if col is None:
            return []
        dypns = []
        for row in range(header_row + 1, ws.max_row + 1):
            val = ws.cell(row, col).value
            if val is not None:
                stripped = str(val).strip()
                if stripped:
                    dypns.append(stripped)
        return dypns
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# Nest selection window
# ---------------------------------------------------------------------------

# Per-nest grab options shown under each nest row in the selection window.
_GRAB_CHILDREN = [
    {"key": "models",    "label": "Grab SolidWorks models (.SLDPRT + .SLDDRW)", "checked": True},
    {"key": "pdf",       "label": "Grab part PDFs",                             "checked": True},
    {"key": "overwrite", "label": "Overwrite files already in REPEAT",          "checked": False},
]

_DEFAULT_GRAB = {c["key"]: c["checked"] for c in _GRAB_CHILDREN}

# Which file extensions each grab option covers.
_MODEL_EXTS = {".sldprt", ".slddrw"}
_PDF_EXTS = {".pdf"}


def _has_repeat_files(nest_dir: Path) -> bool:
    """True if this nest's REPEAT folder already holds anything."""
    d = nest_dir / "REPEAT"
    try:
        return d.is_dir() and any(d.iterdir())
    except OSError:
        return False


def _select_nests(params, batch_number: str, nest_infos: dict[str, dict]):
    """
    Show the nest/options window (nests as checkable rows, each expanding to
    its grab options). ``nest_infos`` is {nest: {'dypns', 'repeats', 'has_repeat'}}.
    Returns [(nest, options_dict)] in nest order for the checked nests, an
    empty list if nothing was checked, or None on cancel. Headless: 'nests'
    (list) picks a subset and 'grab' (dict) overrides the option defaults.
    """
    console = params.get("console")
    order = list(nest_infos.keys())

    if console is not None and hasattr(console, "request_grouped_toggles"):
        groups = []
        for nest in order:
            info = nest_infos[nest]
            n, r = len(info["dypns"]), info["repeats"]
            label = f"{nest}   ({n} part{'s' if n != 1 else ''}, {r} repeat{'s' if r != 1 else ''})"
            if info["has_repeat"]:
                label += "  - REPEAT folder has files"
            groups.append({
                # Like 911 Setup's nest picker, nests start unchecked.
                "key": nest, "label": label, "checked": False,
                "children": [dict(c) for c in _GRAB_CHILDREN],
            })
        result = sdk.request_grouped_toggles(
            params, groups,
            window_title=f"911 Batch Repeater - Batch {batch_number}",
            header="Select Nests to Run",
            subtext=("Check the nests to process. Click a nest's name to "
                     "choose exactly what the repeater grabs for it."),
            run_button_text="Run Repeater",
        )
        if result is None:
            return None
        return [(nest, result[nest]["options"]) for nest in order
                if result.get(nest, {}).get("enabled")]

    # No console (CLI/test): honor explicit overrides, else all nests.
    override = params.get("nests")
    if override:
        wanted = {str(x).strip().upper() for x in override}
        chosen = [n for n in order if n.upper() in wanted]
    else:
        chosen = order
    opts = dict(_DEFAULT_GRAB)
    opts.update(params.get("grab") or {})
    return [(nest, dict(opts)) for nest in chosen]


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------

def _pick_source(sources: list[dict], qtdr_root: Path,
                 target_batch: str, target_nest: str) -> tuple[dict, Path] | None:
    """First MPL row (skipping the target nest itself) whose folder exists."""
    for src in sources:
        if (src["batch"].upper() == target_batch.upper()
                and src["nest"].upper() == target_nest.upper()):
            continue
        src_dir = qtdr_root / Path(src["rel"])
        if src_dir.is_dir():
            return src, src_dir
    return None


def _copy_part(src_dir: Path, dest_dir: Path, exts: set[str], overwrite: bool,
               log, cancel_event) -> tuple[int, int]:
    """Copy src files whose suffix is in exts into dest_dir. -> (copied, skipped)"""
    copied = skipped = 0
    for f in sorted(src_dir.iterdir()):
        sdk.raise_if_cancelled(cancel_event)
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        dest = dest_dir / f.name
        if dest.exists() and not overwrite:
            skipped += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        sdk.ensure_local(f, log=log)  # OneDrive placeholder -> download (Hard Rule 13)
        shutil.copy2(f, dest)
        copied += 1
    return copied, skipped


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(params, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("911 Repeater starting...")
    progress_callback(0)

    # ------------------------------------------------------------------ #
    # Step 1 - Prompt for batch number
    # ------------------------------------------------------------------ #
    batch_number = sdk.request_batch_number(
        params, "Enter Batch Number (e.g. V109, S045):"
    ).strip().upper()

    if not batch_number:
        log("No batch number entered - aborting.")
        return

    log(f"Batch         : {batch_number}")

    # ------------------------------------------------------------------ #
    # Step 2 - Resolve the QTDR root + live batch folder
    # ------------------------------------------------------------------ #
    qtdr_root = sdk.resolve_911_qtdr_root(settings.get("qtdr_base_path", ""))
    if qtdr_root is None or not qtdr_root.exists():
        raise sdk.UserFacingError(
            "Couldn't find the 911 QTDR folder.",
            "Make sure OneDrive is synced, or set the 911 QTDR root in "
            "Settings → Apps → 911 Batch Repeater, then run again.")
    log(f"911 QTDR root : {qtdr_root}")

    batch_folder = sdk.find_911_batch_folder(qtdr_root, batch_number)
    if batch_folder is None:
        raise sdk.UserFacingError(
            f"Couldn't find batch folder '{batch_number}' under the 911 QTDR "
            f"root.\n  {qtdr_root}",
            "Double-check the batch number and that the folder exists there, "
            "then run again.")
    log(f"Batch folder  : {batch_folder}")
    progress_callback(5)

    # ------------------------------------------------------------------ #
    # Step 3 - Load the Master Parts List
    # ------------------------------------------------------------------ #
    mpl_override = str(settings.get("mpl_path", "") or "").strip()
    mpl_path = Path(mpl_override) if mpl_override else _default_mpl_path(qtdr_root)
    if not mpl_path.exists():
        raise sdk.UserFacingError(
            f"Couldn't find the 911 MASTER PARTS LIST.\n  {mpl_path}",
            "Make sure OneDrive is synced (the list lives in the REPEATER "
            "folder), or point at it in Settings → Apps → 911 Batch Repeater. "
            "A TechDeck admin can rebuild it with tools/build_911_mpl.py.")

    log(f"Parts list    : {mpl_path.name}")
    mpl_index = _load_mpl_index(mpl_path, log)
    log(f"  {sum(len(v) for v in mpl_index.values())} catalogued parts, "
        f"{len(mpl_index)} unique DYPNs")
    progress_callback(10)

    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------ #
    # Step 4 - Collect DYPNs (and repeat counts) per nest
    # ------------------------------------------------------------------ #
    nest_folders = sorted(
        d for d in batch_folder.iterdir()
        if d.is_dir() and _NEST_RE.match(d.name))

    if not nest_folders:
        log(f"No nest subfolders found in {batch_folder.name}. Has 911 Setup been run?")
        return

    log(f"Nest folders  : {len(nest_folders)} found")

    nest_infos: dict[str, dict] = {}

    for nest_dir in nest_folders:
        sdk.raise_if_cancelled(cancel_event)
        nest_name = nest_dir.name
        excel_path = _find_nest_excel(nest_dir, batch_number, nest_name)

        if excel_path is None:
            log(f"  [{nest_name}] WARNING: No 911 BATCH Excel found - skipping")
            continue

        try:
            dypns = _read_dypns(excel_path, log)
        except Exception as exc:
            log(f"  [{nest_name}] WARNING: Could not read Excel ({exc}) - skipping")
            continue

        if not dypns:
            log(f"  [{nest_name}] No DYPNs found in the NEST sheet")
            continue

        repeats = sum(1 for d in dypns if d.strip().upper() in mpl_index)
        log(f"  [{nest_name}] {len(dypns)} DYPNs, {repeats} in the parts list")
        nest_infos[nest_name] = {
            "dypns": dypns,
            "repeats": repeats,
            "has_repeat": _has_repeat_files(nest_dir),
        }

    progress_callback(25)

    if not nest_infos:
        log("No DYPNs found across any nest - nothing to do.")
        return

    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------ #
    # Step 5 - Nest-selection window (which nests + what to grab)
    # ------------------------------------------------------------------ #
    selection = _select_nests(params, batch_number, nest_infos)

    if selection is None:
        log("Nest selection cancelled - nothing was run.")
        cancel_event.set()  # user cancel: don't count as a successful (ticket-earning) run
        return
    if not selection:
        log("No nests selected - nothing to do.")
        cancel_event.set()  # nothing ran: don't count as a successful (ticket-earning) run
        return

    log(f"Running nests : {', '.join(n for n, _ in selection)}")
    progress_callback(30)

    # ------------------------------------------------------------------ #
    # Step 6 - Per nest: look up repeats, copy into {nest}\REPEAT\{DYPN}\
    # ------------------------------------------------------------------ #
    total_parts = 0
    total_files = 0
    total_new = 0
    total_missing_src = 0
    total_errors = 0

    for nest_idx, (nest_name, opts) in enumerate(selection):
        if cancel_event.is_set():
            log("Cancelled by user.")
            return

        want_models = opts.get("models", True)
        want_pdf = opts.get("pdf", True)
        overwrite = opts.get("overwrite", False)

        exts: set[str] = set()
        if want_models:
            exts |= _MODEL_EXTS
        if want_pdf:
            exts |= _PDF_EXTS

        dypns = nest_infos[nest_name]["dypns"]
        grabbing = [name for flag, name in
                    ((want_models, "models"), (want_pdf, "PDFs")) if flag]
        log(f"\n[{nest_name}] Processing {len(dypns)} DYPNs "
            f"(grabbing {' + '.join(grabbing) if grabbing else 'nothing'}"
            f"{', overwrite on' if overwrite else ''})...")

        if not exts:
            log(f"  [{nest_name}] Both grab options are off - nothing to do here.")
            continue

        nest_dir = batch_folder / nest_name
        repeat_root = nest_dir / "REPEAT"

        seen: set[str] = set()
        nest_parts = nest_files = nest_errors = 0

        for dypn in dypns:
            sdk.raise_if_cancelled(cancel_event)
            dypn_key = dypn.strip().upper()
            if dypn_key in seen:
                continue
            seen.add(dypn_key)

            sources = mpl_index.get(dypn_key)
            if not sources:
                total_new += 1
                continue  # new part - not a repeat, nothing to pull

            picked = _pick_source(sources, qtdr_root, batch_number, nest_name)
            if picked is None:
                log(f"  {dypn} - in the parts list but its source folder is "
                    f"missing (was {sources[0]['batch']} {sources[0]['nest']})")
                total_missing_src += 1
                continue

            src, src_dir = picked
            try:
                copied, skipped = _copy_part(
                    src_dir, repeat_root / src_dir.name, exts, overwrite,
                    log, cancel_event)
                if copied:
                    nest_parts += 1
                    nest_files += copied
                    log(f"  {dypn} - {copied} file(s) from {src['batch']} {src['nest']}"
                        f"{f' ({skipped} kept)' if skipped else ''}")
                elif skipped:
                    log(f"  {dypn} - already in REPEAT, skipping")
            except Exception as exc:
                log(f"  {dypn} - ERROR copying: {exc}")
                nest_errors += 1

        log(f"  [{nest_name}] {nest_parts} repeat part(s), {nest_files} file(s) -> REPEAT")
        total_parts += nest_parts
        total_files += nest_files
        total_errors += nest_errors

        progress_callback(30 + int((nest_idx + 1) / len(selection) * 65))

    # ------------------------------------------------------------------ #
    # Step 7 - Summary
    # ------------------------------------------------------------------ #
    progress_callback(100)
    log("\n" + "=" * 50)
    log("REPEATER SUMMARY")
    log("=" * 50)
    log(f"Batch           : {batch_number}")
    log(f"Nests processed : {len(selection)}")
    log(f"Repeat parts    : {total_parts}")
    log(f"Files copied    : {total_files}")
    if total_new:
        log(f"New parts (not in the parts list): {total_new}")
    if total_missing_src:
        log(f"Missing sources : {total_missing_src}")
    if total_errors:
        log(f"Errors          : {total_errors}")
    log("=" * 50)
    log("Done." if total_errors == 0 else f"Done with {total_errors} error(s).")

    if total_errors and hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_WARNING,
            f"{total_errors} file(s) failed to copy - see the log above.")
