"""
911 LST Organizer Plugin - v2.3.0
Single-file TechDeck plugin.

Pulls the .lst files for exactly the parts a nest's 1D cutting-pattern diagram
calls for (v1 gathered a whole batch like the 922 organizer; reworked to the
real 911 workflow 2026-07-07):

1. The user picks the nest's PRODUCTION PAPERWORK folder (e.g.
   ...\\911 QTDR\\S035\\503874\\PRODUCTION PAPERWORK) via the native dialog.
2. The '1D' PDF inside it (name always contains '1D', e.g. 'S035 503874 1D.pdf')
   is parsed with PyMuPDF: the 'Parts Id.' table lists the parts to pull. A part
   may be prefixed with its nest number; unprefixed parts belong to the current
   nest. The prefix separator has drifted across nesting-software exports -
   '503874-H4143481-3', '503874- H4143481-3', and (since 2026-08, incl. the
   MULTIPLE ORDERS diagrams that cover two batches at once) '503887 / H4112842-34'
   - all are accepted (v2.2.0; the slash form previously parsed as ZERO parts).
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

v2.3.0 (2026-09-21) - caught up with the 922 LST Organizer: the pull report
is now ONE color-coded PDF ('LST Report - {batch} {nest}.pdf', drawn by the
shared sdk.ReportPdf) instead of a tab-separated .txt plus a debug .jsonl; the
source nests' .lst files are prefetched from OneDrive in the background; the
attention popup NAMES the missing parts instead of pointing at the report; and
problems the user can fix (wrong folder, no 1D diagram) read as plain-English
stop messages, not tracebacks.

The batch/nest/root are derived from the picked path itself (the component
after the '911 QTDR' ancestor), so per-machine OneDrive layout differences
('Communication site - Electric Boat ASA Docs' vs 'Communication site - Pilot
Program') don't matter.
"""
from __future__ import annotations

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

VERSION = "2.3.0"

# Hard Rule 3 nest shape (also the shape of a foreign-nest prefix in Parts Id).
NEST_RE = sdk.NEST_ID_RE  # single home in the SDK — never re-type the pattern

# A DYPN / part id: letters + digits, then at least one dashed suffix
# (H4143481-3, H4143408-145, H4130401-22M, R5711906-401, H5532004-19-2).
PART_RE = re.compile(r"^[A-Z]{1,3}\d{4,}(?:-[A-Z0-9]+)+$", re.IGNORECASE)

# '{nest}<sep>{part}': the nest-prefix separator is '-' or '/' with optional
# whitespace around it (both shapes appear in real 1D exports; see
# _classify_token). Groups are validated against NEST_RE / PART_RE after.
PREFIXED_PART_RE = re.compile(r"^([A-Z0-9]+)\s*[-/]\s*(\S+)$", re.IGNORECASE)

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

    'H4143481-3'           -> (current nest, 'H4143481-3')
    '503874-H4143481-3'    -> ('503874', 'H4143481-3')
    '503874- H4143481-3'   -> ('503874', 'H4143481-3')   (multi-nest bar layout)
    '503887 / H4112842-34' -> ('503887', 'H4112842-34')  (2026-08 slash exports)
    """
    token = token.strip().upper()
    if PART_RE.match(token):
        return current_nest, token
    # A nest-prefixed part. The separator drifts between exports: a plain
    # hyphen, a hyphen with whitespace, or (since 2026-08 - every part line on
    # the MULTIPLE ORDERS diagrams AND new single-order ones) ' / '. Splitting
    # on the first hyphen alone cut '503887 / H4112842-34' INSIDE the part
    # number, so those diagrams parsed as zero parts (CDAUGHAN-LT, 2026-08-21).
    m = PREFIXED_PART_RE.match(token)
    if m and NEST_RE.match(m.group(1)) and PART_RE.match(m.group(2)):
        return m.group(1), m.group(2)
    return None


def parse_1d_parts(pdf_path: Path, current_nest: str, log
                   ) -> List[Tuple[str, str]]:
    """The (nest, part) list from the PDF's 'Parts Id.' table(s), in order,
    deduplicated. Falls back to a whole-page part-token scan if no table
    region is found (layout drift)."""
    sdk.ensure_local(pdf_path, log=log)
    doc = fitz.open(sdk.long_path(pdf_path))
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
    if sdk.is_dir(probe):
        result = (current_batch, probe)
    else:
        for scan_root, batch_depth in ((root, 1), (root / ARCHIVE_DIR_NAME, 1)):
            if result or not sdk.is_dir(scan_root):
                continue
            for i, d in enumerate(sorted(scan_root.iterdir(),
                                         key=lambda p: p.name.upper())):
                if i % 32 == 0 and cancel_event.is_set():
                    break
                if not sdk.is_dir(d):
                    continue
                cand = d / nest
                if sdk.is_dir(cand):
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
        if not (sdk.is_file(p) and p.suffix.lower() == ".lst"):
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

def _write_report(pdf_path: Path, info: dict, rows: list,
                  unresolved: Dict[str, List[str]], copied: int,
                  issues: List[str], dry_run: bool = False) -> None:
    """The color-coded pull report (same look as the 922 LST Organizer's).
    rows: (part, nest, batch, [copied names] or None, variant part or None)."""
    C = sdk.REPORT_COLORS
    missing = [r for r in rows if not r[3]]
    pulled = [r for r in rows if r[3]]
    by_letter = [r for r in pulled if r[4]]
    nest_missing = sum(len(v) for v in unresolved.values())
    listed = len(rows) + nest_missing

    d = sdk.ReportPdf()
    d.text(f"911 LST Organizer  -  {info['batch']} {info['nest']}",
           size=17, bold=True, color=C["band"])
    d.text(f"Generated {time.strftime('%Y-%m-%d %H:%M')}   |   "
           f"1D diagram: {info['pdf']}"
           + ("   |   DRY RUN - nothing was copied" if dry_run else ""),
           size=8.5, color=C["grey"])
    d.gap(8)

    d.text("LST RECONCILIATION", size=11, bold=True, color=C["band"])
    recon = [
        ("TARGET  -  parts on the 1D diagram", listed, C["target_bg"]),
        ("Parts with a .lst pulled", f"{len(pulled)} / {listed}",
         C["ok_bg"] if len(pulled) >= listed else None),
        (".lst files copied", copied, None),
        ("Matched by revision letter", len(by_letter),
         C["extra_bg"] if by_letter else None),
        ("MISSING .lst", len(missing), C["miss_bg"] if missing else C["ok_bg"]),
        ("Parts in a nest that was NOT FOUND", nest_missing,
         C["miss_bg"] if nest_missing else C["ok_bg"]),
        ("Copy problems", len(issues), C["rev_bg"] if issues else C["ok_bg"]),
    ]
    for i, (label, val, fill) in enumerate(recon):
        bold = label.startswith("TARGET") or label.startswith("MISSING")
        bg = fill if fill is not None else (C["zebra"] if i % 2 else C["white"])
        d.row([label, str(val)], [300, 90], size=9.5, h=18, bold=bold, fill=bg)
    d.gap(4)
    flags = []
    if missing:
        flags.append(f"{len(missing)} missing")
    if nest_missing:
        flags.append(f"{nest_missing} in a nest that was not found")
    if issues:
        flags.append(f"{len(issues)} copy problem(s)")
    if flags:
        d.text("  -  ".join(flags) + ".", size=10, bold=True, color=C["miss_tx"])
    else:
        d.text("Every part on the diagram has its .lst.", size=10, bold=True,
               color=C["ok_tx"])
    d.gap(10)

    if missing:
        d.text("MISSING  -  NO .LST FOUND FOR THESE PARTS", size=11, bold=True,
               color=C["miss_tx"])
        d.header_row(["Part", "Nest", "Batch"], [220, 150, 150])
        for part, nest, batch, _f, _v in missing:
            d.row([part, nest, batch or ""], [220, 150, 150], h=14,
                  fill=C["miss_bg"], tcolor=C["miss_tx"])
        d.gap(10)

    if unresolved:
        d.text("NEST NOT FOUND  -  no folder for these nests in any batch",
               size=11, bold=True, color=C["miss_tx"])
        d.text("Their parts were NOT pulled. Sync the nest's batch folder, "
               "then run again.", size=8, color=C["grey"])
        d.header_row(["Nest", "Part"], [150, 370])
        for nest in sorted(unresolved):
            for part in unresolved[nest]:
                d.row([nest, part], [150, 370], h=14,
                      fill=C["miss_bg"], tcolor=C["miss_tx"])
        d.gap(10)

    if by_letter:
        d.text("MATCHED BY REVISION LETTER  -  same piece, spelled differently",
               size=11, bold=True, color=C["extra_tx"])
        d.header_row(["Diagram says", "File is named", "Nest"], [200, 200, 120])
        for part, nest, _b, _f, via in by_letter:
            d.row([part, via, nest], [200, 200, 120], h=14,
                  fill=C["extra_bg"], tcolor=C["extra_tx"])
        d.gap(10)

    if issues:
        d.text("COPY PROBLEMS", size=11, bold=True, color=C["rev_tx"])
        for it in issues:
            d.row([it], [520], size=8, h=14, fill=C["rev_bg"],
                  tcolor=C["rev_tx"], wrap=True)
        d.gap(10)

    d.text("PULL LIST BY NEST", size=11, bold=True, color=C["band"])
    groups: Dict[Tuple[str, str], list] = defaultdict(list)
    for r in pulled:
        groups[(r[1], r[2] or "")].append(r)
    if not groups:
        d.text("No files were pulled.", size=9, color=C["grey"])
    for (nest, batch) in sorted(groups):
        items = groups[(nest, batch)]
        own = "   (this nest)" if nest == info["nest"] else ""
        d.row([f"Nest {nest}  -  batch {batch}{own}", f"{len(items)} pc"],
              [430, 90], size=9.5, h=17, bold=True, fill=C["group_bg"])
        d.row(["Part", "File(s)"], [170, 350], size=8, h=13, bold=True,
              tcolor=C["grey"])
        for i, (part, _n, _b, files, _via) in enumerate(items):
            d.row([part, "; ".join(files)], [170, 350], h=13,
                  fill=C["zebra"] if i % 2 else C["white"], wrap=True)
        d.gap(6)

    d.save(pdf_path)

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
    if not sdk.is_dir(picked):
        raise sdk.UserFacingError(
            f"That folder could not be found: {picked}",
            "Pick the nest's PRODUCTION PAPERWORK folder and run again.")

    root, batch, nest = derive_context(picked)
    if root is None:
        raise sdk.UserFacingError(
            f"'{picked.name}' is not inside the '911 QTDR' folder.",
            "Pick the nest's PRODUCTION PAPERWORK folder (for example "
            "911 QTDR > S035 > 503874 > PRODUCTION PAPERWORK).")
    log(f"911 QTDR root : {root}")
    log(f"Batch / nest  : {batch} / {nest}")
    progress_callback(5)

    pdf = find_1d_pdf(picked, batch, nest)
    if pdf is None:
        raise sdk.UserFacingError(
            f"There is no 1D cutting diagram in '{picked.name}' (a PDF with "
            "'1D' in its name; the '1D POST' one does not count).",
            "Save the nest's 1D diagram into that folder, or pick the folder "
            "that holds it, then run again.")
    log(f"1D diagram    : {pdf.name}")

    pairs = parse_1d_parts(pdf, nest, log)
    if not pairs:
        raise sdk.UserFacingError(
            f"No part numbers could be read from {pdf.name}.",
            "Check that it is the nest's 1D cutting diagram. If it is, send a "
            "debug report (Settings > Generate Debug Report) with the PDF.")
    foreign = sorted({n for n, _ in pairs if n != nest})
    log(f"Parts listed  : {len(pairs)}"
        + (f" (nests referenced besides {nest}: {', '.join(foreign)})" if foreign else ""))
    if dry_run:
        log("DRY RUN MODE - no files will be copied.")
    progress_callback(15)

    dest = picked / DEST_FOLDER_NAME
    if not dry_run:
        sdk.ensure_dir(dest)
    report_path = dest / f"LST Report - {batch} {nest}.pdf"

    # Group the wanted parts by nest, resolve each nest to its batch on disk,
    # and index each resolved nest folder's .lst files once.
    by_nest: Dict[str, List[str]] = defaultdict(list)
    for n, part in pairs:
        by_nest[n].append(part)

    nest_cache: Dict[str, Optional[Tuple[str, Path]]] = {
        nest: (batch, root / batch / nest)
    }
    rows: list = []            # (part, nest, batch, [copied names] or None, via)
    unresolved: Dict[str, List[str]] = {}
    issues: List[str] = []
    seen_lower: Set[str] = set()
    copied_count = 0

    total_nests = len(by_nest)
    resolved_nests: Dict[str, Tuple[str, Path]] = {}
    for src_nest, parts in sorted(by_nest.items()):
        sdk.raise_if_cancelled(cancel_event)
        hit = resolve_nest_folder(root, batch, src_nest, nest_cache, cancel_event)
        if hit is None:
            log(f"  WARNING: nest {src_nest} not found in any batch folder "
                f"({len(parts)} part(s) skipped).")
            unresolved[src_nest] = parts
        else:
            resolved_nests[src_nest] = hit

    # Run ahead of the serial per-nest walk below: background workers hydrate
    # every source nest's .lst files, so a cloud-only nest folder stops stalling
    # the copy loop one file at a time (same move as the 922 LST Organizer).
    def _read_set():
        for _b, folder in resolved_nests.values():
            yield from folder.rglob("*.lst")
    if not dry_run:
        sdk.prefetch_paths(_read_set(), cancel_event=cancel_event)

    for ni, (src_nest, (src_batch, nest_folder)) in enumerate(
            sorted(resolved_nests.items()), 1):
        sdk.raise_if_cancelled(cancel_event)
        parts = by_nest[src_nest]
        log(f"  Nest {ni}/{len(resolved_nests)}: {src_nest} -> batch {src_batch}"
            f" ({len(parts)} part(s))")
        index = index_nest_lsts(nest_folder, dest, cancel_event)

        for part in parts:
            sdk.raise_if_cancelled(cancel_event)
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
                    if not dry_run and not sdk.exists(target):
                        sdk.ensure_local(f)  # Hard Rule 6
                        _retry_fileop(shutil.copy2, sdk.long_path(f),
                                      sdk.long_path(target))
                    seen_lower.add(fname_lower)
                    copied_names.append(f.name)
                    copied_count += 1
                except Exception as e:
                    issues.append(f"Failed to copy {f.name}: {e}")
            if not hits:
                log(f"    MISSING: no .lst for {part} under {src_nest}")
            rows.append((part, src_nest, src_batch, copied_names or None, via))
        progress_callback(15 + int(70 * ni / max(1, total_nests)))

    missing = [r for r in rows if not r[3]]
    report_ok = False
    if not dry_run:
        try:
            _write_report(report_path,
                          {"pdf": pdf.name, "batch": batch, "nest": nest},
                          rows, unresolved, copied_count, issues)
            report_ok = True
        except Exception as e:
            log(f"WARNING: could not write the PDF report: {e}")
    progress_callback(90)

    # ── Console summary ────────────────────────────────────────────────────────
    nest_missing = sum(len(v) for v in unresolved.values())
    log("=" * 60)
    log(f"911 LST Organizer - {batch} {nest}")
    log(f"  Parts on the 1D diagram:      {len(pairs)}")
    log(f"  .lst files copied:            {copied_count}"
        + (" (dry run)" if dry_run else ""))
    log(f"  Missing .lst:                 {len(missing)}")
    log(f"  In a nest that was not found: {nest_missing}")
    log(f"  Copy problems:                {len(issues)}")
    log("=" * 60)
    by_letter = [r for r in rows if r[3] and r[4]]
    if by_letter:
        log(f"Matched by revision letter ({len(by_letter)}) - same piece, the "
            "diagram and the .lst spell the suffix differently:")
        for part, _n, _b, _f, via in by_letter:
            log(f"  - {part}  <-  {via}")
    for it in issues:
        log(f"  COPY PROBLEM: {it}")
    if not dry_run:
        log(f"LST folder: {dest}")
    progress_callback(100)

    # Anything short of a clean pull is reported honestly, not as a blank tick.
    if (unresolved or missing or issues) and hasattr(sdk, "set_run_outcome"):
        bits = []
        if missing:
            bits.append(f"{len(missing)} part(s) have no .lst")
        if nest_missing:
            bits.append(f"{nest_missing} part(s) are in a nest that was not found")
        if issues:
            bits.append(f"{len(issues)} file(s) could not be copied")
        sdk.set_run_outcome(params, sdk.RUN_OUTCOME_WARNING, "; ".join(bits))

    # Blocking popup for anything the user must not miss - it NAMES the parts
    # (v2.3.0), so nobody has to open the report to learn what to chase.
    if unresolved or missing:
        lines: List[str] = []
        if missing:
            lines.append(f"{len(missing)} part(s) have no .lst file:")
            lines += [f"  - {part}  (nest {n}, batch {b})"
                      for part, n, b, _f, _v in missing[:12]]
            if len(missing) > 12:
                lines.append(f"  ...and {len(missing) - 12} more (see the report)")
        if unresolved:
            if lines:
                lines.append("")
            lines.append("These nests were not found in any batch folder "
                         "(their parts were NOT pulled):")
            lines += [f"  - {n}: {', '.join(ps)}"
                      for n, ps in sorted(unresolved.items())]
        sdk.show_warning(params, f"911 LST - {batch} {nest}", "\n".join(lines))

    if report_ok:
        sdk.link_output(params, f"Open the LST report for {batch} {nest}",
                        report_path, prefix="[REPORT]")


# ── Standalone test harness ────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading
    run(
        params={'log': print, 'settings': {'base_path': '', 'dry_run': True}},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=threading.Event(),
    )
