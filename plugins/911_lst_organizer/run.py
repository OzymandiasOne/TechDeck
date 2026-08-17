"""
911 LST Organizer Plugin - v2.1.0
Single-file TechDeck plugin.

Pulls the .lst files for exactly the parts a nest's 1D cutting-pattern diagram
calls for (v1 gathered a whole batch like the 922 organizer; reworked to the
real 911 workflow 2026-07-07):

1. The user picks the nest's PRODUCTION PAPERWORK folder (e.g.
   ...\\911 QTDR\\S035\\503874\\PRODUCTION PAPERWORK) via the native dialog.
2. The '1D' PDF inside it (name always contains '1D', e.g. 'S035 503874 1D.pdf')
   is parsed with PyMuPDF: the 'Parts Id.' table lists the parts to pull. A part
   from ANOTHER nest is prefixed with its nest number ('503874-H4143481-3');
   unprefixed parts belong to the current nest.
3. Each foreign nest is resolved to its batch by FILESYSTEM lookup - a nest
   folder sits directly under its batch folder, so we scan '911 QTDR\\*\\{nest}'
   (current batch first, then every top-level batch, then the
   '02 - Complete Packages' archive). The PDF header ('S035 503874 S036 ...')
   is NOT parsed for this: with many batches its text renders clustered/broken,
   but the folder tree is always readable.
4. Each part's .lst is found under its nest folder (stem's first
   space/underscore token == part id; template/ARCHIVE paths excluded) and
   copied flat into PRODUCTION PAPERWORK\\LST. v2.1.0: if nothing matches the
   part id exactly, an unambiguous TRAILING-REVISION-LETTER variant counts
   ('H4143481-3' <-> 'H4143481-3A' - the same piece, spelled differently by the
   1D diagram and the .lst export); the substitution is logged and marked
   'OK as <part>' on the report rather than applied silently.
5. Nests that exist nowhere on disk, and parts with no .lst, are reported in
   the console + report AND raised as a blocking popup (sdk.show_warning) so
   they can't scroll past unseen.

The batch/nest/root are derived from the picked path itself (the component
after the '911 QTDR' ancestor), so per-machine OneDrive layout differences
('Communication site - Electric Boat ASA Docs' vs 'Communication site - Pilot
Program') don't matter.
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

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

VERSION = "2.1.0"

# Hard Rule 3 nest shape (also the shape of a foreign-nest prefix in Parts Id).
NEST_RE = sdk.NEST_ID_RE  # single home in the SDK — never re-type the pattern

# A DYPN / part id: letters + digits, then at least one dashed suffix
# (H4143481-3, H4143408-145, H4130401-22M, R5711906-401, H5532004-19-2).
PART_RE = re.compile(r"^[A-Z]{1,3}\d{4,}(?:-[A-Z0-9]+)+$", re.IGNORECASE)

DEST_FOLDER_NAME = "LST"
ARCHIVE_DIR_NAME = "02 - Complete Packages"

# ── 1D PDF parsing ─────────────────────────────────────────────────────────────

def find_1d_pdf(folder: Path, batch: str, nest: str) -> Optional[Path]:
    """The 1D cutting diagram in `folder`: any *.pdf whose name contains '1D'
    as a token-ish substring — but never the '1D POST' variant (a post-cut
    revision of the diagram, not the pull list). Several matches -> prefer one
    naming the current batch AND nest, else the newest."""
    cands = [p for p in folder.glob("*.pdf")
             if re.search(r"\b1D\b", p.stem, re.IGNORECASE)
             and not re.search(r"\bPOST\b", p.stem, re.IGNORECASE)
             and not p.name.startswith("~$")]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    def _score(p: Path):
        up = p.stem.upper()
        return ((batch.upper() in up) + (nest.upper() in up),
                p.stat().st_mtime)
    return max(cands, key=_score)


def _classify_token(token: str, current_nest: str) -> Optional[Tuple[str, str]]:
    """A Parts Id token -> (nest, part), or None if it isn't a part line.

    'H4143481-3'        -> (current nest, 'H4143481-3')
    '503874-H4143481-3' -> ('503874', 'H4143481-3')
    '503874- H4143481-3'-> ('503874', 'H4143481-3')   (multi-nest bar-nest layout)
    """
    token = token.strip().upper()
    if PART_RE.match(token):
        return current_nest, token
    # Multi-nest bar diagrams render the prefix as '{nest}- {part}' (or
    # '{nest} - {part}') with whitespace around the separating hyphen, so
    # strip both sides before matching (a leading space would sink PART_RE).
    head, sep, tail = token.partition("-")
    head, tail = head.strip(), tail.strip()
    if sep and NEST_RE.match(head) and PART_RE.match(tail):
        return head, tail
    return None


def parse_1d_parts(pdf_path: Path, current_nest: str, log
                   ) -> List[Tuple[str, str]]:
    """The (nest, part) list from the PDF's 'Parts Id.' table(s), in order,
    deduplicated. Falls back to a whole-page part-token scan if no table
    region is found (layout drift)."""
    sdk.ensure_local(pdf_path, log=log)
    doc = fitz.open(str(pdf_path))
    try:
        lines: List[str] = []
        for page in doc:
            lines.extend(page.get_text().splitlines())
    finally:
        doc.close()

    pairs: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    def _take(token: str):
        hit = _classify_token(token, current_nest)
        if hit and hit not in seen:
            seen.add(hit)
            pairs.append(hit)

    in_table = False
    found_table = False
    for raw in lines:
        line = raw.strip()
        up = line.upper()
        if up.startswith("PARTS ID"):
            in_table = True
            found_table = True
            continue
        if in_table and up.startswith("TOTAL BARS"):
            in_table = False
            continue
        if in_table and line:
            _take(line)

    if not found_table:
        log("  NOTE: no 'Parts Id.' table found - scanning the whole page "
            "for part ids instead.")
        for raw in lines:
            _take(raw.strip())
    return pairs

# ── Batch / nest resolution ────────────────────────────────────────────────────

def derive_context(picked: Path) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """(qtdr_root, batch, nest) from the picked PRODUCTION PAPERWORK path -
    the components right after the '911 QTDR' ancestor. Works on every
    machine's OneDrive layout because it never reconstructs the tenant part."""
    parts = picked.resolve().parts
    for i, seg in enumerate(parts):
        if seg.strip().upper() == "911 QTDR" and i + 2 < len(parts):
            root = Path(*parts[: i + 1])
            return root, parts[i + 1], parts[i + 2]
    return None, None, None


def resolve_nest_folder(root: Path, current_batch: str, nest: str,
                        cache: Dict[str, Optional[Tuple[str, Path]]],
                        cancel_event) -> Optional[Tuple[str, Path]]:
    """Find (batch, nest_folder) for a nest number by filesystem lookup:
    the current batch first, then every top-level batch folder, then the
    '02 - Complete Packages' archive. Returns None if the nest folder exists
    nowhere we can see (the caller warns)."""
    if nest in cache:
        return cache[nest]

    result: Optional[Tuple[str, Path]] = None
    probe = root / current_batch / nest
    if probe.is_dir():
        result = (current_batch, probe)
    else:
        for scan_root, batch_depth in ((root, 1), (root / ARCHIVE_DIR_NAME, 1)):
            if result or not scan_root.is_dir():
                continue
            for i, d in enumerate(sorted(scan_root.iterdir(),
                                         key=lambda p: p.name.upper())):
                if i % 32 == 0 and cancel_event.is_set():
                    break
                if not d.is_dir():
                    continue
                cand = d / nest
                if cand.is_dir():
                    result = (d.name, cand)
                    break

    cache[nest] = result
    return result

# ── LST discovery within a nest folder ─────────────────────────────────────────

def _is_excluded(path: Path, dest_dir: Path) -> bool:
    """Skip our own destination folder, ANY nest's prior pull output
    (a 'PRODUCTION PAPERWORK\\LST' pair - plain 'LST' folders are legit
    sources elsewhere, e.g. 'Templates\\LST'), template junk, and ARCHIVE
    dupes."""
    try:
        path.relative_to(dest_dir)
        return True
    except ValueError:
        pass
    parts_up = [seg.upper() for seg in path.parts]
    for i, seg in enumerate(parts_up[:-1]):
        if seg == "PRODUCTION PAPERWORK" and parts_up[i + 1] == DEST_FOLDER_NAME:
            return True
    for seg in parts_up:
        if "TEMPLATE" in seg or seg == "ARCHIVE":
            return True
    return False


def index_nest_lsts(nest_folder: Path, dest_dir: Path, cancel_event
                    ) -> Dict[str, List[Path]]:
    """{normalized first stem token -> [.lst paths]} for a nest folder. One
    cancel-polled recursive walk per nest (Hard Rule 11)."""
    index: Dict[str, List[Path]] = defaultdict(list)
    for i, p in enumerate(nest_folder.rglob("*")):
        if i % 64 == 0 and cancel_event.is_set():
            break
        if not (p.is_file() and p.suffix.lower() == ".lst"):
            continue
        if _is_excluded(p, dest_dir):
            continue
        tokens = [t for t in re.split(r"[ _]+", p.stem.strip()) if t]
        if tokens:
            index[sdk.normalize_dypn(tokens[0])].append(p)
    return dict(index)

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

# ── Report ─────────────────────────────────────────────────────────────────────

def _write_report(txt_path: Path, info: dict, rows: list,
                  unresolved: Dict[str, List[str]], copied: int,
                  issues: List[str]) -> None:
    """rows: (part, nest, batch, [copied names] or None, variant part or None)."""
    with open(txt_path, "w", encoding="utf-8", newline="") as f:
        f.write("# 911 LST pull report (generated)\n")
        f.write("# " + "=" * 76 + "\n")
        for k, v in info.items():
            f.write(f"# {k}: {v}\n")
        missing = [r for r in rows if not r[3]]
        f.write(f"# parts_listed: {len(rows) + sum(len(v) for v in unresolved.values())}\n")
        f.write(f"# files_copied: {copied}\n")
        f.write(f"# parts_missing_lst: {len(missing)}\n")
        f.write(f"# unresolved_nests: {len(unresolved)}\n")

        if unresolved:
            f.write("#\n# UNRESOLVED NESTS - no batch folder found on disk\n")
            f.write("# " + "=" * 76 + "\n")
            for nest in sorted(unresolved):
                f.write(f"#   Nest {nest}: {', '.join(unresolved[nest])}\n")
            f.write("# " + "=" * 76 + "\n")

        f.write("\npart\tnest\tbatch\tstatus\tfiles\n")
        for part, nest, batch, files, via in rows:
            # 'OK as <part>' = the .lst spells the piece with a different
            # trailing revision letter than the 1D diagram does.
            status = ("OK" if not via else f"OK as {via}") if files else "MISSING"
            f.write(f"{part}\t{nest}\t{batch or ''}\t{status}"
                    f"\t{'; '.join(files or [])}\n")
        for nest in sorted(unresolved):
            for part in unresolved[nest]:
                f.write(f"{part}\t{nest}\t\tNEST NOT FOUND\t\n")

        if issues:
            f.write("\n# Issues\n")
            for it in issues:
                f.write(f"# {it}\n")

# ── TechDeck plugin entry point ────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event) -> None:
    settings = params.get('settings', {})
    log = params.get('log', print)

    log(f"Starting 911 LST Organizer v{VERSION}...")
    progress_callback(0)

    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF (fitz) is not available; cannot read the 1D diagram.")

    dry_run = settings.get('dry_run', False)

    start_dir = ""
    try:
        r = sdk.resolve_911_qtdr_root(settings.get('base_path', '').strip())
        if r:
            start_dir = str(r)
    except Exception:
        pass
    raw = sdk.request_directory(
        params,
        "Select the nest's PRODUCTION PAPERWORK folder (holds the 1D cutting diagram)",
        start_dir,
    )
    if cancel_event.is_set():
        return
    if not raw:
        log("Folder selection cancelled - nothing was run.")
        cancel_event.set()
        return
    picked = Path(raw.strip().strip('"'))
    if not picked.is_dir():
        raise ValueError(f"Folder not found: {picked}")

    root, batch, nest = derive_context(picked)
    if root is None:
        raise RuntimeError(
            f"'{picked}' is not inside a '911 QTDR' tree - pick the nest's "
            f"PRODUCTION PAPERWORK folder (e.g. ...\\911 QTDR\\S035\\503874\\"
            f"PRODUCTION PAPERWORK)."
        )
    log(f"911 QTDR root : {root}")
    log(f"Batch / nest  : {batch} / {nest}")
    progress_callback(5)

    pdf = find_1d_pdf(picked, batch, nest)
    if pdf is None:
        raise RuntimeError(
            f"No 1D cutting diagram (*1D*.pdf) found in {picked}."
        )
    log(f"1D diagram    : {pdf.name}")

    pairs = parse_1d_parts(pdf, nest, log)
    if not pairs:
        raise RuntimeError(
            f"No part ids found in {pdf.name} - is this the 1D cutting diagram?"
        )
    foreign = sorted({n for n, _ in pairs if n != nest})
    log(f"Parts listed  : {len(pairs)}"
        + (f" (nests referenced besides {nest}: {', '.join(foreign)})" if foreign else ""))
    if dry_run:
        log("DRY RUN MODE - no files will be copied.")
    progress_callback(15)

    dest = picked / DEST_FOLDER_NAME
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    debug_path = dest / f"debug_pull_lsts_{ts}.jsonl"
    txt_path = dest / f"LST_Pull_{batch}_{nest}.txt"

    # Group the wanted parts by nest, resolve each nest to its batch on disk,
    # and index each resolved nest folder's .lst files once.
    by_nest: Dict[str, List[str]] = defaultdict(list)
    for n, part in pairs:
        by_nest[n].append(part)

    nest_cache: Dict[str, Optional[Tuple[str, Path]]] = {
        nest: (batch, root / batch / nest)
    }
    rows: list = []            # (part, nest, batch, [copied names] or None)
    unresolved: Dict[str, List[str]] = {}
    issues: List[str] = []
    seen_lower: Set[str] = set()
    copied_count = 0

    debug_fp = open(debug_path, "a", encoding="utf-8") if not dry_run else None
    try:
        if debug_fp:
            debug_fp.write(json.dumps({
                "event": "start", "ts": ts, "pdf": str(pdf), "batch": batch,
                "nest": nest, "parts": len(pairs),
            }) + "\n")

        total_nests = len(by_nest)
        for ni, (src_nest, parts) in enumerate(sorted(by_nest.items()), 1):
            if cancel_event.is_set():
                log("Cancelled."); return
            hit = resolve_nest_folder(root, batch, src_nest, nest_cache, cancel_event)
            if hit is None:
                log(f"  WARNING: nest {src_nest} not found in any batch folder "
                    f"({len(parts)} part(s) skipped).")
                unresolved[src_nest] = parts
                if debug_fp:
                    debug_fp.write(json.dumps({"event": "nest_unresolved",
                                               "nest": src_nest, "parts": parts}) + "\n")
                continue
            src_batch, nest_folder = hit
            log(f"  Nest {ni}/{total_nests}: {src_nest} -> batch {src_batch}"
                f" ({len(parts)} part(s))")
            index = index_nest_lsts(nest_folder, dest, cancel_event)

            for part in parts:
                if cancel_event.is_set():
                    log("Cancelled."); return
                hits = index.get(sdk.normalize_dypn(part), [])
                via = None
                if not hits:
                    # A trailing revision letter is the same piece ('-3' vs
                    # '-3A'): the 1D diagram and the .lst export don't always
                    # agree on it, and calling a file that IS there "missing"
                    # sends someone hunting for nothing. Conservative - only an
                    # unambiguous single variant counts (sdk.match_dypn_variant).
                    via = sdk.match_dypn_variant(part, index)
                    if via:
                        hits = index.get(via, [])
                        log(f"    NOTE: no .lst named {part}; pulled {via} "
                            "instead (same piece, different revision letter)")
                copied_names: List[str] = []
                for f in hits:
                    fname_lower = f.name.lower()
                    if fname_lower in seen_lower:
                        if f.name not in copied_names:
                            copied_names.append(f.name)
                        continue
                    target = dest / f.name
                    try:
                        if not dry_run:
                            if not target.exists():
                                sdk.ensure_local(f)  # Hard Rule 13
                                _retry_fileop(shutil.copy2, f, target)
                            if debug_fp:
                                debug_fp.write(json.dumps({"event": "copied",
                                                           "src": str(f)}) + "\n")
                        seen_lower.add(fname_lower)
                        copied_names.append(f.name)
                        copied_count += 1
                    except Exception as e:
                        issues.append(f"Failed to copy {f.name}: {e}")
                if not hits:
                    log(f"    MISSING: no .lst for {part} under {src_nest}")
                rows.append((part, src_nest, src_batch, copied_names or None, via))
            progress_callback(15 + int(70 * ni / total_nests))

        if debug_fp:
            debug_fp.write(json.dumps({"event": "done", "copied": copied_count}) + "\n")
    finally:
        if debug_fp:
            debug_fp.close()

    missing = [r for r in rows if not r[3]]
    if not dry_run:
        _write_report(
            txt_path,
            {"pdf": pdf.name, "batch": batch, "nest": nest, "root": str(root),
             "dest": str(dest)},
            rows, unresolved, copied_count, issues,
        )
    progress_callback(90)

    # ── Console summary ────────────────────────────────────────────────────────
    log("=" * 60)
    log(f"911 LST Organizer - {batch} {nest} Complete")
    log("=" * 60)
    log(f"Parts on the 1D diagram: {len(pairs)}")
    log(f"LST files copied:        {copied_count}" + (" (dry run)" if dry_run else ""))
    by_letter = [r for r in rows if r[3] and r[4]]
    if by_letter:
        log(f"\nMatched by revision letter ({len(by_letter)}) - same piece, the "
            "diagram and the .lst spell the suffix differently:")
        for part, _n, _b, _f, via in by_letter:
            log(f"  - {part}  <-  {via}")
    if missing:
        log(f"\nWARNING: no .lst found for {len(missing)} part(s):")
        for part, src_nest, src_batch, _f, _v in missing[:8]:
            log(f"  - {part} (nest {src_nest}, batch {src_batch})")
        if len(missing) > 8:
            log(f"  ... and {len(missing) - 8} more. See report.")
    if issues:
        log(f"\n{len(issues)} copy issue(s) - see report.")
    if not dry_run:
        log(f"\nLST folder: {dest}")
        log(f"Report:     {txt_path}")
    log("=" * 60)
    progress_callback(100)

    # Blocking popup for anything the user must not miss.
    if unresolved or missing:
        parts_bits = []
        if unresolved:
            parts_bits.append(
                "These nests were not found in any batch folder (their parts "
                "were NOT pulled):\n  "
                + "\n  ".join(f"{n}: {', '.join(ps)}" for n, ps in sorted(unresolved.items()))
            )
        if missing:
            parts_bits.append(
                f"No .lst file was found for {len(missing)} part(s) - "
                "see the report in the LST folder."
            )
        sdk.show_warning(params, "911 LST Organizer - attention needed",
                         "\n\n".join(parts_bits))


# ── Standalone test harness ────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading
    run(
        params={'log': print, 'settings': {'base_path': '', 'dry_run': True}},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=threading.Event(),
    )
