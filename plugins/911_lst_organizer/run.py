"""
911 LST Organizer Plugin - v1.0.0
Single-file TechDeck plugin. The 911 sibling of the 922 LST Organizer.

Gathers every .lst file in a 911 QTDR batch folder into {batch}\\LST, then maps
each file to the batch list for material analysis. Differences from the 922
version, driven by the 911 tree (surveyed 2026-07-07 across S026/S028, 3X010,
V102 and the 02 - Complete Packages archive):

- Batch folders are named like the batch itself (V102, S026, 3X010) directly
  under '911 QTDR', located via sdk.find_911_batch_folder.
- LST files appear in several layouts: '{nest}\\CAD-AND-SHOP-PRINTS\\{part}\\7000\\'
  (like 922), the same without the CAD-AND-SHOP-PRINTS level, and
  '{nest}\\Machine Files\\{nest} 3040.LST' (per-nest machine files). So the scan
  is a full recursive walk of the batch folder rather than a 7000-only probe.
- No Master PO workbook: the material mapping comes from the batch's own
  '(BATCH X) BATCH LIST.xlsx' (DYPN / MATERIAL / DESCRIPTION / NEST PKG NBR
  columns, matched by header name). 911 MATERIAL codes are the same EB serial
  space as 922, so the SDK standard/oversized tube sets apply unchanged.
- File stems name either a DYPN ('H7190602-118.lst', 'H4130401-22M ANGLE.lst',
  'R5711906-401_ANGLE.lst') or a NEST ('5CDARQ 3040.LST'); both are matched.
- Excluded from the gather: the destination LST folder itself, any path segment
  containing 'template' (template/junk LSTs), and 'ARCHIVE' folders (stale
  duplicates). Paths containing 'repeat' are a fallback bucket like the 922
  version's REPEATS handling.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# ── Material sets (canonical definitions live in the SDK) ──────────────────────

STANDARD_TUBE_MATERIALS = sdk.STANDARD_TUBE_MATERIALS
OVERSIZED_TUBE_MATERIALS = sdk.OVERSIZED_TUBE_MATERIALS
ALL_TUBE_MATERIALS = sdk.ALL_TUBE_MATERIALS

# Hard Rule 3: drop footer/total/junk batch-list rows by nest shape.
NEST_RE = re.compile(r"^(?:[PS]?\d{3,}|(?=[A-Z0-9]*\d)[A-Z0-9]{4,8})$", re.IGNORECASE)

DEST_FOLDER_NAME = "LST"

# ── Path helpers ───────────────────────────────────────────────────────────────

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _is_excluded(path: Path, dest_dir: Path) -> bool:
    """True for files the gather must skip: our own destination folder,
    template junk, and stale ARCHIVE copies."""
    try:
        path.relative_to(dest_dir)
        return True
    except ValueError:
        pass
    for seg in path.parts:
        low = seg.lower()
        if "template" in low or low == "archive":
            return True
    return False

# ── LST discovery ──────────────────────────────────────────────────────────────

def _find_lsts_in_folder(folder: Path, dest_dir: Path, cancel_event=None
                         ) -> Tuple[List[Path], List[Path]]:
    """All .lst files under `folder`, split into (primary, repeat-path) lists.

    One recursive walk per top-level batch subfolder; the walk over a OneDrive
    tree can be slow, so cancel_event is polled inside the loop (Hard Rule 11).
    """
    primary: List[Path] = []
    secondary: List[Path] = []
    for i, p in enumerate(folder.rglob("*")):
        if cancel_event is not None and i % 64 == 0 and cancel_event.is_set():
            break
        if not (p.is_file() and p.suffix.lower() == ".lst"):
            continue
        if _is_excluded(p, dest_dir):
            continue
        in_repeat = any("repeat" in seg.lower() for seg in p.parts)
        (secondary if in_repeat else primary).append(p)
    return primary, secondary

# ── Batch-list reading ─────────────────────────────────────────────────────────

def _strip_step(dypn: str) -> str:
    return dypn[:-5] if dypn.upper().endswith("-STEP") else dypn


def _find_batch_list(batch_path: Path) -> Optional[Path]:
    """'*BATCH*LIST*.xlsx' at the batch root first, then one glob level down;
    skips Excel ~$ lock files."""
    def _match(files):
        return [f for f in files
                if "BATCH" in f.name.upper() and "LIST" in f.name.upper()
                and not f.name.startswith("~$")]
    hits = _match(batch_path.glob("*.xlsx"))
    if not hits:
        hits = _match(batch_path.glob("*/*.xlsx"))
    return hits[0] if hits else None


def _read_batch_list(batch_list_path: Path, debug_fp) -> Tuple[Dict, Dict, Dict]:
    """Return (dypn_map, nest_map, serial_desc) from the batch list.

    dypn_map    : DYPN (upper) -> (nest, serial, description)
    nest_map    : NEST (upper) -> set of (serial, description) on that nest
    serial_desc : serial -> description (first seen)
    Junk/footer rows are dropped via the Hard-Rule-3 nest regex.
    """
    wb = sdk.load_workbook_resilient(batch_list_path, read_only=True, data_only=True)
    try:
        target_ws = header_row = cols = None
        for ws in wb.worksheets:
            hr, cmap = sdk.find_header_row(ws, ["DYPN", "Material", "Nest Pkg Nbr"])
            if hr is not None:
                target_ws, header_row, cols = ws, hr, cmap
                break
        if target_ws is None:
            raise ValueError(
                "No sheet with DYPN / Material / Nest Pkg Nbr headers found."
            )
        # Description isn't required to locate the sheet, but map it if present.
        all_cols = sdk.header_map(target_ws, header_row)
        desc_col = all_cols.get("DESCRIPTION")

        dypn_map: Dict = {}
        nest_map: Dict[str, Set] = defaultdict(set)
        serial_desc: Dict = {}
        for row in target_ws.iter_rows(min_row=header_row + 1, values_only=False):
            def _cell(col):
                if not col:
                    return None
                v = row[col - 1].value if len(row) >= col else None
                return str(v).strip() if v not in (None, "") else None
            nest = _cell(cols.get("NEST PKG NBR"))
            if not nest or not NEST_RE.match(nest):
                continue
            dypn = _cell(cols.get("DYPN"))
            serial = _cell(cols.get("MATERIAL"))
            desc = _cell(desc_col)
            nest_u = nest.upper()
            if serial:
                serial_desc.setdefault(serial, desc or "")
                nest_map[nest_u].add((serial, desc or ""))
            if dypn:
                dypn_map[_strip_step(dypn).upper()] = (nest_u, serial, desc)
        debug_fp.write(json.dumps({
            "event": "batch_list_ok", "sheet": target_ws.title,
            "dypn": len(dypn_map), "nests": len(nest_map),
        }) + "\n")
        return dypn_map, dict(nest_map), serial_desc
    finally:
        wb.close()

# ── Row building (map each gathered file to the batch list) ────────────────────

def _stem_tokens(stem: str) -> List[str]:
    """Split a file stem on spaces/underscores (NOT '-': DYPNs contain dashes)."""
    return [t for t in re.split(r"[ _]+", stem.strip()) if t]


def _build_rows(copied_files: List[Path], dypn_map: Dict, nest_map: Dict,
                debug_fp) -> Tuple[list, List[str]]:
    """Rows: (original, dypn, nest, serial, description, match_kind)."""
    rows = []
    problems = []
    for p in copied_files:
        stem_u = p.stem.strip().upper()
        tokens = _stem_tokens(stem_u)
        dypn = nest = serial = desc = None
        kind = "UNMATCHED"

        for cand in ([stem_u] + tokens[:1]):
            cand = _strip_step(cand)
            if cand in dypn_map:
                dypn = cand
                nest, serial, desc = dypn_map[cand]
                kind = "DYPN"
                break
        if kind == "UNMATCHED" and tokens and tokens[0] in nest_map:
            nest = tokens[0]
            kind = "NEST"
            mats = nest_map[nest]
            if len(mats) == 1:
                serial, desc = next(iter(mats))
            else:
                problems.append(
                    f"'{p.name}' matches nest {nest} which carries "
                    f"{len(mats)} materials - not auto-categorized."
                )
        if kind == "UNMATCHED":
            problems.append(f"'{p.name}' matches no DYPN or nest in the batch list.")

        rows.append((p.name, dypn, nest, serial, desc, kind))
        debug_fp.write(json.dumps({
            "event": "row", "orig": p.name, "dypn": dypn, "nest": nest,
            "serial": serial, "desc": desc, "match": kind,
        }) + "\n")
    return rows, problems

# ── Counting ───────────────────────────────────────────────────────────────────

def _compute_counts(rows: list, dypn_map: Dict) -> Tuple:
    """Tube-material analysis from the batch list vs what was gathered."""
    covered_dypns = {r[1] for r in rows if r[1]}
    covered_nests = {r[2] for r in rows if r[2]}

    standard: Dict = {}
    oversized: Dict = {}
    for dypn, (nest, serial, desc) in dypn_map.items():
        s = str(serial).strip() if serial else None
        if s in STANDARD_TUBE_MATERIALS:
            standard[dypn] = (nest, s, desc or "UNKNOWN")
        elif s in OVERSIZED_TUBE_MATERIALS:
            oversized[dypn] = (nest, s, desc or "UNKNOWN")

    # A part counts as covered if its own LST was found OR a per-nest machine
    # file (3X010-style '{nest} 3040.LST') covers its whole nest.
    missing_std = [
        (p, n, s, d) for p, (n, s, d) in standard.items()
        if p not in covered_dypns and n not in covered_nests
    ]
    oversized_list = [(p, n, s, d) for p, (n, s, d) in oversized.items()]
    return (len(standard), len(oversized), len(standard) + len(oversized),
            missing_std, oversized_list)

# ── Output writers ─────────────────────────────────────────────────────────────

def _write_overview_txt(
    txt_path: Path, rows: list, issues: List[str], info: dict,
    std_count: int, over_count: int, total_count: int,
    missing_std: list, oversized: list,
) -> None:
    with open(txt_path, "w", encoding="utf-8", newline="") as f:
        f.write("# LST TXT work file (generated)\n")
        f.write("# " + "=" * 76 + "\n")
        for k, v in info.items():
            f.write(f"# {k}: {v}\n")
        f.write(f"# gathered_files: {len(rows)}\n")
        f.write(f"# standard_tubes_in_batch_list: {std_count}\n")
        f.write(f"# oversized_tubes_in_batch_list: {over_count} (>0.375 NOM)\n")
        f.write(f"# total_tubes_in_batch_list: {total_count}\n")

        if oversized:
            f.write("#\n")
            f.write(f"# OVERSIZED TUBES (>0.375\" NOM) - {len(oversized)} parts\n")
            f.write("# " + "=" * 76 + "\n")
            f.write("# Tracked in the batch list (require special handling).\n#\n")
            by_nest: Dict = defaultdict(list)
            for part, nest, serial, desc in oversized:
                by_nest[nest or "?"].append((part, serial, desc))
            for nest in sorted(by_nest):
                f.write(f"#\n# Nest: {nest}\n")
                for part, serial, desc in by_nest[nest]:
                    f.write(f"#   - {part} (Serial: {serial}, Desc: {desc})\n")
            f.write("# " + "=" * 76 + "\n")

        if missing_std:
            f.write("#\n")
            f.write(f"# MISSING STANDARD TUBE FILES - {len(missing_std)} not found\n")
            f.write("# " + "=" * 76 + "\n")
            f.write("# In the batch list but no .lst was found (directly or per-nest).\n#\n")
            by_nest = defaultdict(list)
            for part, nest, serial, desc in missing_std:
                by_nest[nest or "?"].append((part, serial, desc))
            for nest in sorted(by_nest):
                f.write(f"#\n# Nest: {nest}\n")
                for part, serial, desc in by_nest[nest]:
                    f.write(f"#   - {part} (Serial: {serial}, Desc: {desc})\n")
                    f.write(f"#     Look in: {nest}/**/7000/ or {nest}/Machine Files/\n")
            f.write("# " + "=" * 76 + "\n")

        f.write("\n")
        f.write("original\tdypn\tnest\tserial\tdescription\tmatch\n")
        for (orig, dypn, nest, serial, desc, kind) in rows:
            f.write(
                f"{orig}\t{dypn or ''}\t{nest or ''}\t{serial or ''}"
                f"\t{desc or ''}\t{kind}\n"
            )

        if issues:
            f.write("\n# Issues\n")
            for it in issues:
                f.write(f"# {it}\n")


def _write_grouped_txt(out_path: Path, batch: str, rows: list) -> int:
    items = []
    for (orig, dypn, nest, serial, desc, _) in rows:
        if not serial or not desc:
            continue
        if str(serial).strip() not in STANDARD_TUBE_MATERIALS:
            continue
        items.append((desc, str(serial).strip(), nest or "", dypn or orig))

    items.sort(key=lambda t: (t[0].lower(), t[1], t[2], t[3]))
    groups: Dict = defaultdict(list)
    for desc, s, nest, part in items:
        groups[(desc, s)].append((nest, part))

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(f"Batch {batch}\n")
        f.write(f"Total standard tube parts: {len(items)}\n\n")
        for (desc, s) in sorted(groups, key=lambda k: k[0].lower()):
            f.write(f"{desc} ({s}):\n")
            for nest, part in groups[(desc, s)]:
                f.write(f"{nest}\t{part}\n")
            f.write("\n")
    return len(items)

# ── File operations ────────────────────────────────────────────────────────────

def _retry_fileop(fn, *args, **kwargs):
    import errno
    tries = kwargs.pop("tries", 5)
    delay = kwargs.pop("delay", 0.2)
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM, errno.EBUSY):
                time.sleep(delay * (i + 1))
                continue
            raise


def _gather_and_copy(
    batch_path: Path, dry_run: bool, debug_fp, log, cancel_event,
) -> Tuple[List[Path], List[str], Path]:
    issues: List[str] = []
    copied: List[Path] = []
    dest = batch_path / DEST_FOLDER_NAME
    _ensure_dir(dest)
    seen_lower: Set[str] = set()  # case-insensitive guard during gather

    scan_dirs = sorted(
        (d for d in batch_path.iterdir()
         if d.is_dir() and d.name.upper() != DEST_FOLDER_NAME),
        key=lambda p: p.name.upper(),
    )
    total_dirs = len(scan_dirs)
    for idx, child in enumerate(scan_dirs, 1):
        if cancel_event.is_set():
            break
        log(f"  Scanning folder {idx}/{total_dirs}: {child.name}")
        primary, secondary = _find_lsts_in_folder(child, dest, cancel_event)
        lsts = primary if primary else secondary
        src = "primary" if primary else ("REPEATS*" if secondary else "NONE")
        debug_fp.write(json.dumps({
            "event": "folder_probe", "dir": str(child), "source": src,
            "count": len(lsts),
        }) + "\n")
        for f in lsts:
            if cancel_event.is_set():
                break
            fname_lower = f.name.lower()
            target = dest / f.name
            try:
                if fname_lower in seen_lower:
                    debug_fp.write(json.dumps({"event": "skip_duplicate_gather", "src": str(f)}) + "\n")
                    continue
                if dry_run:
                    copied.append(target)
                    seen_lower.add(fname_lower)
                    debug_fp.write(json.dumps({"event": "dry_run", "src": str(f), "dst": str(target)}) + "\n")
                else:
                    if target.exists():
                        debug_fp.write(json.dumps({"event": "skip_exists", "dst": str(target)}) + "\n")
                        continue
                    sdk.ensure_local(f)  # Hard Rule 13: hydrate before copying
                    _retry_fileop(shutil.copy2, f, target)
                    copied.append(target)
                    seen_lower.add(fname_lower)
                    debug_fp.write(json.dumps({"event": "copied", "src": str(f), "dst": str(target)}) + "\n")
            except Exception as e:
                issues.append(f"Failed to copy {f.name}: {e}")
                debug_fp.write(json.dumps({"event": "copy_error", "src": str(f), "error": str(e)}) + "\n")

    return copied, issues, dest


def _dedup_destination(dest_dir: Path, log, debug_fp) -> int:
    """Case-insensitive duplicate removal on .lst files already in dest_dir."""
    by_lower: Dict[str, List[Path]] = defaultdict(list)
    for p in dest_dir.glob("*.lst"):
        by_lower[p.name.lower()].append(p)

    removed = 0
    for group in by_lower.values():
        if len(group) <= 1:
            continue
        group.sort(key=lambda p: p.name)
        keep = group[0]
        for dupe in group[1:]:
            try:
                dupe.unlink()
                log(f"  Removed duplicate: {dupe.name} (kept {keep.name})")
                debug_fp.write(json.dumps({"event": "dedup_removed", "file": dupe.name, "kept": keep.name}) + "\n")
                removed += 1
            except Exception as e:
                log(f"  Warning: could not remove {dupe.name}: {e}")
                debug_fp.write(json.dumps({"event": "dedup_error", "file": dupe.name, "error": str(e)}) + "\n")
    return removed


def _sanitize_folder_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()


def _organize_by_material(dest_dir: Path, rows: list, debug_fp, cancel_event) -> None:
    by_fname: Dict = {}
    for (orig, _, _, serial, desc, _) in rows:
        if orig and serial and desc:
            by_fname[orig.lower()] = (desc, str(serial).strip())

    moved = 0
    for p in sorted(dest_dir.glob("*.lst")):
        if cancel_event.is_set():
            break
        pair = by_fname.get(p.name.lower())
        folder = _sanitize_folder_name(f"{pair[0]} ({pair[1]})") if pair else "Uncategorized"
        target_dir = dest_dir / folder
        _ensure_dir(target_dir)
        try:
            final = target_dir / p.name
            k = 2
            while final.exists():
                final = target_dir / f"{p.stem}({k}){p.suffix}"
                k += 1
            shutil.move(str(p), str(final))
            moved += 1
            debug_fp.write(json.dumps({"event": "organized", "file": p.name, "folder": folder}) + "\n")
        except Exception as e:
            debug_fp.write(json.dumps({"event": "organize_error", "file": p.name, "error": str(e)}) + "\n")

    debug_fp.write(json.dumps({"event": "organize_done", "moved": moved}) + "\n")

# ── TechDeck plugin entry point ────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event) -> None:
    settings = params.get('settings', {})
    log = params.get('log', print)

    log("Starting 911 LST Organizer...")
    progress_callback(0)

    base_path_str = settings.get('base_path', '').strip()
    dry_run = settings.get('dry_run', False)
    do_organize = settings.get('organize_by_material', True)

    raw = sdk.request_batch_number(
        params, 'Enter 911 batch number (e.g. "V102" or "S026"):'
    )
    batch = sdk.normalize_911_batch(raw or '')
    if not batch:
        raise ValueError(f"Unrecognised batch number input: {raw!r}")

    root = sdk.resolve_911_qtdr_root(base_path_str)
    if not root:
        raise RuntimeError(
            "Could not auto-locate '911 QTDR'. Set Base Directory in plugin settings."
        )
    if not root.is_dir():
        raise ValueError(f"Base directory not found: {root}")
    log(f"Base directory: {root}")

    batch_path = sdk.find_911_batch_folder(root, batch)
    if not batch_path:
        raise RuntimeError(
            f"Batch {batch} not found under {root}. "
            "Verify the batch exists and OneDrive is synced."
        )

    log(f"Batch {batch}: {batch_path}")
    if dry_run:
        log("DRY RUN MODE - no files will be copied or moved.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    lst_dir = batch_path / DEST_FOLDER_NAME
    _ensure_dir(lst_dir)
    debug_path = lst_dir / f"debug_gather_lsts_{ts}.jsonl"
    txt_path = lst_dir / f"LST_Overview_Batch_{batch}.txt"
    group_path = lst_dir / f"Tube_Parts_Batch_{batch}.txt"

    with open(debug_path, "a", encoding="utf-8") as debug_fp:
        debug_fp.write(json.dumps({
            "event": "start", "ts": ts, "batch": batch,
            "root": str(root), "batch_path": str(batch_path),
        }) + "\n")

        if cancel_event.is_set():
            return

        # ── Phase 1: Gather LST files ──────────────────────────────────────────
        log("Scanning the batch folder for .lst files...")
        copied, copy_issues, dest_dir = _gather_and_copy(
            batch_path, dry_run, debug_fp, log, cancel_event
        )
        if cancel_event.is_set():
            log("Cancelled."); return
        log(f"Gathered {len(copied)} file(s).")
        progress_callback(10)

        # ── Phase 2: Deduplicate destination ───────────────────────────────────
        if not dry_run:
            log("Checking for case-insensitive duplicate filenames...")
            removed = _dedup_destination(dest_dir, log, debug_fp)
            if removed:
                log(f"Removed {removed} duplicate file(s).")
                copied = [p for p in copied if p.exists()]
            else:
                log("No duplicates found.")
        progress_callback(20)

        if cancel_event.is_set():
            log("Cancelled."); return

        # ── Phase 3: Locate + read the batch list ──────────────────────────────
        log("Locating the BATCH LIST workbook...")
        batch_list = _find_batch_list(batch_path)
        if not batch_list:
            _write_overview_txt(
                txt_path,
                [(p.name, None, None, None, None, "NO-BATCH-LIST") for p in copied],
                ["BATCH LIST workbook NOT FOUND"],
                {"batch": batch, "note": "gather only - no material mapping"},
                0, 0, 0, [], [],
            )
            raise RuntimeError(
                f"BATCH LIST not found in {batch_path}. Files were gathered to\n"
                f"  {dest_dir}\nbut material analysis needs the batch list - "
                f"seed report written to:\n  {txt_path}"
            )
        log(f"Batch list: {batch_list.name}")
        debug_fp.write(json.dumps({"event": "batch_list", "path": str(batch_list)}) + "\n")
        progress_callback(30)

        log("Reading the batch list...")
        try:
            dypn_map, nest_map, _serial_desc = _read_batch_list(batch_list, debug_fp)
        except Exception as e:
            debug_fp.write(json.dumps({"event": "batch_list_fail", "error": str(e)}) + "\n")
            raise RuntimeError(f"Could not read the batch list: {e}")
        log(f"Loaded {len(dypn_map)} DYPN entries across {len(nest_map)} nest(s).")
        progress_callback(40)

        if cancel_event.is_set():
            log("Cancelled."); return

        # ── Phase 4: Map files to the batch list ───────────────────────────────
        log("Mapping files to batch-list data...")
        rows, problems = _build_rows(copied, dypn_map, nest_map, debug_fp)
        progress_callback(60)

        # ── Phase 5: Tube counts ───────────────────────────────────────────────
        (std_count, over_count, total_count,
         missing_std, oversized_list) = _compute_counts(rows, dypn_map)

        # ── Phase 6: Write output files ────────────────────────────────────────
        log("Writing output files...")
        issues = copy_issues + problems
        _write_overview_txt(
            txt_path, rows, issues,
            {"batch": batch, "root": str(root), "batch_list": str(batch_list),
             "dest_dir": str(dest_dir)},
            std_count, over_count, total_count,
            missing_std, oversized_list,
        )
        _write_grouped_txt(group_path, batch, rows)
        progress_callback(75)

        if cancel_event.is_set():
            log("Cancelled."); return

        # ── Phase 7: Organize by material ──────────────────────────────────────
        if do_organize and not dry_run:
            log("Organizing files by material type...")
            _organize_by_material(dest_dir, rows, debug_fp, cancel_event)
        elif dry_run:
            log("Dry run: skipping file organization.")
        progress_callback(90)

        debug_fp.write(json.dumps({"event": "done"}) + "\n")

    # ── Console summary ────────────────────────────────────────────────────────
    matched = sum(1 for r in rows if r[5] != "UNMATCHED")
    log("=" * 60)
    log(f"911 LST Organizer - Batch {batch} Complete")
    log("=" * 60)
    log(f"Files gathered:  {len(rows)}")
    log(f"Matched to batch list: {matched} ({len(rows) - matched} unmatched)")
    log("")
    log("Tube counts (from the batch list):")
    log(f"  Standard:                 {std_count}")
    log(f"  Oversized (>0.375\" NOM):  {over_count}")
    log(f"  Total:                    {total_count}")

    if oversized_list:
        log(f"\n{len(oversized_list)} oversized tube part(s) tracked in the batch list.")

    if missing_std:
        log(f"\nWARNING: {len(missing_std)} standard tube file(s) not found!")
        for part, nest, *_ in sorted(missing_std)[:5]:
            log(f"  - {part} (Nest: {nest})")
        if len(missing_std) > 5:
            log(f"  ... and {len(missing_std) - 5} more. See report for full list.")
    else:
        log("\nAll expected standard tube files found.")

    if issues:
        log(f"\n{len(issues)} issue(s) logged - see report for details.")

    log("")
    log(f"Main report:   {txt_path}")
    log(f"Grouped tubes: {group_path}")
    log(f"Debug log:     {debug_path}")
    log("=" * 60)
    progress_callback(100)


# ── Standalone test harness ────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading
    run(
        params={
            'log': print,
            'settings': {
                'base_path': '',
                'dry_run': True,
                'organize_by_material': True,
            },
        },
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=threading.Event(),
    )
