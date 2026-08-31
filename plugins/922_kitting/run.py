"""
922 Kitting
===========
Formats and prints kitting paperwork for an entire 922 batch.

Phase 1: applies the batch color (read from legend AD3..AD12) to the Bin Label
& Checklist sheet header/footer cells, with luminance-based text color and a
lightened secondary shade.

Phase 2: first a PRE-CHECK pass over every kit page - a line with a part but
no source material would print a blank bin label, so all such lines are
flagged up front and the run halts (with the option to proceed anyway).
Then loops the driver cell D21 over 1, 3, ..., 35 (18 iterations / 36
orders), detects FORMED parts against the Bent Plates sheet by appending
&" FORMED" to the Material Desc formula (the sheet's DYPNs cover formed
plates AND formed flat bars - whatever FormingFinder recorded), exports each
iteration as a 2-page PDF, reverts the FORMED edits, then merges all
per-iteration PDFs into Kitting {batch}.pdf.

Phase 3 handles OVERSIZE orders. The Bin Label & Checklist checklist has only
10 part rows, so an order with more parts silently loses the rest (Batch 490:
FK328102 has 11 and printed 10). Those orders are re-rendered off the hidden
'Larger Bin Label' sheet - same D21 driver, same colors, same FORMED edits,
15 part rows - and their page is SUBSTITUTED into Kitting {batch}.pdf in place
of the truncated one.

Requires Excel COM (pywin32). The workbook is staged locally before any COM
work - OneDrive can interfere with Excel COM saves.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional

import fitz

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

try:
    import pythoncom
    import win32com.client as win32
    _COM_AVAILABLE = True
except ImportError:
    _COM_AVAILABLE = False


# Constants -------------------------------------------------------------------

_XL_CALC_AUTOMATIC = -4105
_XL_TYPE_PDF = 0

SHEET_NAME = "Bin Label & Checklist"
BENT_PLATES_SHEET = "Bent Plates"
LARGER_SHEET_NAME = "Larger Bin Label"
PO_INFO_SHEET = "PO Info Drop"

# The window the sheet's own array formulas read for the part list. Kept
# identical to them so a part count here can never disagree with what prints.
PO_INFO_ORDER_RANGE = "D6:D910"

PRIMARY_CELLS = ["C2", "R2", "C20", "R20"]
SECONDARY_CELLS = ["C3", "R3", "C21", "R21"]

PART_ROWS = range(22, 32)
LEFT_DYPN_COL = "F"
LEFT_RAWMAT_COL = "G"
LEFT_MATDESC_COL = "H"
RIGHT_DYPN_COL = "U"
RIGHT_RAWMAT_COL = "V"
RIGHT_MATDESC_COL = "W"

# Column triples (DYPN, Raw Material, Material Desc) a kit page reads parts
# from. The standard sheet prints two orders side by side; the larger sheet
# prints one.
STANDARD_COLS = (
    (LEFT_DYPN_COL, LEFT_RAWMAT_COL, LEFT_MATDESC_COL),
    (RIGHT_DYPN_COL, RIGHT_RAWMAT_COL, RIGHT_MATDESC_COL),
)

# 'Larger Bin Label': one order per page, part rows 22-36, and the same
# single-order color cells as the standard sheet's left half.
LARGER_PART_ROWS = range(22, 37)
LARGER_COLS = ((LEFT_DYPN_COL, LEFT_RAWMAT_COL, LEFT_MATDESC_COL),)
LARGER_PRIMARY_CELLS = ["C2", "C20"]
LARGER_SECONDARY_CELLS = ["C3", "C21"]
LARGER_DRIVER_CELL = "D21"

STANDARD_CAPACITY = len(PART_ROWS)      # 10 - beyond this an order truncates
LARGER_CAPACITY = len(LARGER_PART_ROWS)  # 15 - beyond this even the big page does

_XL_SHEET_VISIBLE = -1

LUMINANCE_DARK_CUTOFF = 140.0
LIGHTEN_FACTOR = 0.40

# Labels-only export: top portion of the sheet (no material list)
LABELS_END_ROW = 17
LABELS_FALLBACK_PRINT_AREA = "$A$1:$AC$17"

# Missing-source-material gate
_CHOICE_STOP = "Stop - fix the PO first"
_CHOICE_PROCEED = "Proceed anyway"

# Matches a single cell range like $A$1:$Q$35 (with or without sheet prefix outside)
_RANGE_RE = re.compile(r"(\$?[A-Z]+)\$?(\d+):(\$?[A-Z]+)\$?(\d+)")


def _find_organizer_workbook(doc_folder: Path, batch_no: str) -> Optional[Path]:
    matches = [
        p for p in doc_folder.glob(f"PO H{batch_no} Pallet & Rod Organizer*.xlsx")
        if not p.name.startswith("~")
    ]
    return sorted(matches)[0] if matches else None


# Color helpers ---------------------------------------------------------------

def _bgr_to_rgb(bgr: int) -> tuple[int, int, int]:
    r = bgr & 0xFF
    g = (bgr >> 8) & 0xFF
    b = (bgr >> 16) & 0xFF
    return (r, g, b)


def _rgb_to_bgr(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _lighten(rgb: tuple[int, int, int], factor: float = LIGHTEN_FACTOR) -> tuple[int, int, int]:
    r, g, b = rgb
    return (
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )


def _legend_cell_for_batch(batch_no: str) -> str:
    # Last digit 1->AD3, 2->AD4, ..., 9->AD11, 0->AD12
    digit = int(batch_no[-1])
    if digit == 0:
        return "AD12"
    return f"AD{2 + digit}"


def _derive_labels_print_area(original: str) -> str:
    """Rewrite a PrintArea string so each region keeps its column boundaries but
    spans rows 1..LABELS_END_ROW. Returns LABELS_FALLBACK_PRINT_AREA if the
    original is empty or unparseable."""
    if not original:
        return LABELS_FALLBACK_PRINT_AREA

    def _replace(m: re.Match) -> str:
        col_start = m.group(1).replace("$", "")
        col_end = m.group(3).replace("$", "")
        return f"${col_start}$1:${col_end}${LABELS_END_ROW}"

    rewritten = _RANGE_RE.sub(_replace, original)
    if not rewritten or "$" not in rewritten:
        return LABELS_FALLBACK_PRINT_AREA
    return rewritten


# Phase 1: color formatting ---------------------------------------------------

def _batch_color_scheme(ws_legend, batch_no: str, log) -> dict:
    """The batch's four fill/text colors, read off the legend. The legend only
    exists on the standard sheet (column AD), so the larger sheet is colored
    from this same scheme rather than looking for its own legend."""
    legend_addr = _legend_cell_for_batch(batch_no)
    legend_color = int(ws_legend.Range(legend_addr).Interior.Color)
    rgb = _bgr_to_rgb(legend_color)
    log(f"  Legend {legend_addr}: RGB{rgb}")

    primary_text = (255, 255, 255) if _luminance(rgb) < LUMINANCE_DARK_CUTOFF else (0, 0, 0)
    light_rgb = _lighten(rgb)
    secondary_text = (255, 255, 255) if _luminance(light_rgb) < LUMINANCE_DARK_CUTOFF else (0, 0, 0)

    log(f"  Primary fill RGB{rgb}, text {'white' if primary_text == (255, 255, 255) else 'black'}")
    log(f"  Secondary fill RGB{light_rgb}, text {'white' if secondary_text == (255, 255, 255) else 'black'}")
    return {
        'primary': _rgb_to_bgr(rgb),
        'primary_text': _rgb_to_bgr(primary_text),
        'secondary': _rgb_to_bgr(light_rgb),
        'secondary_text': _rgb_to_bgr(secondary_text),
    }


def _apply_color_scheme(ws, scheme: dict, primary_cells, secondary_cells) -> None:
    for addr in primary_cells:
        cell = ws.Range(addr)
        cell.Interior.Color = scheme['primary']
        cell.Font.Color = scheme['primary_text']
    for addr in secondary_cells:
        cell = ws.Range(addr)
        cell.Interior.Color = scheme['secondary']
        cell.Font.Color = scheme['secondary_text']


# Bent Plates collection ------------------------------------------------------

def _norm(v) -> str:
    """Normalise a cell value for matching. COM returns numeric material codes
    as float (e.g. 218012959.0), so coerce integer-valued floats to int before
    stringifying."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip().casefold()


def _collect_bent_plates(wb, log) -> dict[str, set[str]]:
    """Map each formed-plate DYPN to the set of SOURCE MATERIAL codes recorded
    for it on the Bent Plates sheet. The source material is what distinguishes
    the formed plate from a rod that shares the same DYPN."""
    try:
        ws = wb.Worksheets(BENT_PLATES_SHEET)
    except Exception:
        log(f"  WARNING: '{BENT_PLATES_SHEET}' sheet not found; no FORMED detection")
        return {}

    header_row = 2
    dypn_col = None
    src_col = None
    last_col = max(int(ws.UsedRange.Columns.Count), 8)
    for c in range(1, last_col + 1):
        val = ws.Cells(header_row, c).Value
        if not isinstance(val, str):
            continue
        name = val.strip().upper()
        if name == "DYPN":
            dypn_col = c
        elif name == "SOURCE MATERIAL":
            src_col = c
    if dypn_col is None:
        log("  WARNING: DYPN column not found in Bent Plates header; no FORMED detection")
        return {}
    if src_col is None:
        log("  WARNING: SOURCE MATERIAL column not found in Bent Plates header; "
            "falling back to DYPN-only FORMED matching")

    bent: dict[str, set[str]] = {}
    last_row = max(int(ws.UsedRange.Rows.Count), 3)
    for r in range(3, last_row + 1):
        key = _norm(ws.Cells(r, dypn_col).Value)
        if not key:
            continue
        src = _norm(ws.Cells(r, src_col).Value) if src_col is not None else ""
        sources = bent.setdefault(key, set())
        if src:
            sources.add(src)
    return bent


# FORMED edits ----------------------------------------------------------------

def _apply_formed_edits(ws, bent_plates: dict[str, set[str]], log,
                        part_rows=PART_ROWS,
                        col_triples=STANDARD_COLS) -> list[tuple[str, str]]:
    if not bent_plates:
        return []

    edits: list[tuple[str, str]] = []
    for r in part_rows:
        for dypn_col, rawmat_col, desc_col in col_triples:
            dypn_val = ws.Range(f"{dypn_col}{r}").Value
            if dypn_val is None or dypn_val == "":
                continue
            key = _norm(dypn_val)
            if key not in bent_plates:
                continue
            # A plate and a rod can share the same DYPN; only the plate's row
            # carries the formed-plate source material, so require the row's
            # Raw Material to match. (When no source material was recorded for
            # this DYPN we fall back to a DYPN-only match.)
            sources = bent_plates[key]
            if sources:
                raw_mat = _norm(ws.Range(f"{rawmat_col}{r}").Value)
                if raw_mat not in sources:
                    log(f"    Skip {dypn_val} at {desc_col}{r}: Raw Material "
                        f"{raw_mat!r} not a formed source {sorted(sources)}")
                    continue
            desc_addr = f"{desc_col}{r}"
            try:
                desc_cell = ws.Range(desc_addr)
                original = desc_cell.Formula
                if original is None or original == "":
                    continue
                if isinstance(original, str) and original.startswith("="):
                    new_formula = f'{original}&" FORMED"'
                else:
                    new_formula = f'{original} FORMED'
                desc_cell.Formula = new_formula
                edits.append((desc_addr, original))
                log(f"    FORMED match: {dypn_val} at {desc_addr}")
            except Exception as exc:
                log(f"    WARNING: could not modify {desc_addr} for {dypn_val}: {exc}")
    return edits


def _revert_edits(ws, edits: list[tuple[str, str]], log) -> None:
    for addr, original in edits:
        try:
            ws.Range(addr).Formula = original
        except Exception as exc:
            log(f"    WARNING: could not revert {addr}: {exc}")


# Oversize orders -------------------------------------------------------------

def _part_counts_by_order(wb, log) -> dict[str, int]:
    """{normalised order number: how many parts the PO lists for it}. Read in
    ONE COM call from the same 'PO Info Drop' window the kit page's own array
    formulas index into, so a count here can never disagree with what prints."""
    try:
        ws = wb.Worksheets(PO_INFO_SHEET)
    except Exception:
        log(f"  WARNING: '{PO_INFO_SHEET}' sheet not found; cannot detect orders "
            f"that overflow the {STANDARD_CAPACITY}-row checklist")
        return {}
    try:
        vals = ws.Range(PO_INFO_ORDER_RANGE).Value
    except Exception as exc:
        log(f"  WARNING: could not read {PO_INFO_SHEET}!{PO_INFO_ORDER_RANGE}: {exc}")
        return {}
    counts: dict[str, int] = {}
    for row in (vals or ()):
        key = _norm(row[0] if isinstance(row, tuple) else row)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _order_index_map(ws, log) -> dict[int, str]:
    """{D21 driver value: order number}, read from the index table the kit
    page's own C21 VLOOKUP uses - index in column B, order in column C, under
    the 'Order Numbers on PO' heading. The heading's row differs between the
    standard and larger sheets, so it is scanned for rather than hardcoded."""
    try:
        col_c = ws.Range("C1:C120").Value
    except Exception as exc:
        log(f"  WARNING: could not read the order index table: {exc}")
        return {}
    header_row = None
    for i, row in enumerate(col_c or (), start=1):
        v = row[0] if isinstance(row, tuple) else row
        if isinstance(v, str) and "order numbers on po" in v.strip().casefold():
            header_row = i
            break
    if header_row is None:
        log("  WARNING: order index table not found; cannot detect orders that "
            f"overflow the {STANDARD_CAPACITY}-row checklist")
        return {}
    try:
        vals = ws.Range(f"B{header_row + 1}:C{header_row + 200}").Value
    except Exception as exc:
        log(f"  WARNING: could not read the order index table: {exc}")
        return {}
    out: dict[int, str] = {}
    for row in (vals or ()):
        idx, order = row[0], row[1]
        if idx in (None, "") or order in (None, ""):
            continue
        try:
            out[int(float(idx))] = str(order).strip()
        except (TypeError, ValueError):
            continue
    return out


def _find_oversize_orders(wb, ws_kit, log) -> dict[int, tuple[str, int]]:
    """{driver value: (order number, part count)} for every order with more
    parts than the standard checklist has rows to show them in."""
    counts = _part_counts_by_order(wb, log)
    if not counts:
        return {}
    index_map = _order_index_map(ws_kit, log)
    oversize: dict[int, tuple[str, int]] = {}
    for idx, order in index_map.items():
        count = counts.get(_norm(order), 0)
        if count > STANDARD_CAPACITY:
            oversize[idx] = (order, count)
    return oversize


def _force_single_page(ws, log) -> dict:
    """Make the sheet export as exactly ONE page; returns the PageSetup values
    to put back afterwards.

    The larger bin label carries stale manual page breaks inside its print
    area, so a plain export comes out as a 2x2 grid - the real page plus three
    blanks. Fit-to-1-page-wide-by-1-tall overrides them, and Excel never scales
    ABOVE 100%, so a page that already fit is not enlarged."""
    ps = ws.PageSetup
    saved: dict = {}
    for attr in ("Zoom", "FitToPagesWide", "FitToPagesTall"):
        try:
            saved[attr] = getattr(ps, attr)
        except Exception as exc:
            log(f"  WARNING: could not read PageSetup.{attr}: {exc}")
    try:
        ps.Zoom = False
        ps.FitToPagesWide = 1
        ps.FitToPagesTall = 1
    except Exception as exc:
        log(f"  WARNING: could not force a single page: {exc}")
    return saved


def _restore_page_setup(ws, saved: dict, log) -> None:
    """Zoom goes back LAST - setting FitToPages* is ignored while Zoom holds a
    number, and writing Zoom is what turns fit-to-page back off."""
    ps = ws.PageSetup
    for attr in ("FitToPagesWide", "FitToPagesTall", "Zoom"):
        if attr not in saved:
            continue
        try:
            setattr(ps, attr, saved[attr])
        except Exception as exc:
            log(f"  WARNING: could not restore PageSetup.{attr}: {exc}")


def _render_oversize_pages(excel, ws_big, oversize, bent_plates, pdf_dir,
                           cancel_event, log) -> dict[int, Path]:
    """One 'Larger Bin Label' page per oversize order, colored and FORMED-
    tagged exactly like the standard page. Returns {driver value: pdf}."""
    d21 = ws_big.Range(LARGER_DRIVER_CELL)
    out: dict[int, Path] = {}
    saved_setup = _force_single_page(ws_big, log)
    try:
        for idx, (order, count) in sorted(oversize.items()):
            sdk.raise_if_cancelled(cancel_event)
            d21.Value = idx
            excel.CalculateFull()
            edits = _apply_formed_edits(
                ws_big, bent_plates, log, LARGER_PART_ROWS, LARGER_COLS)
            try:
                if edits:
                    excel.CalculateFull()
                page = pdf_dir / f"big{idx:02d}.pdf"
                ws_big.ExportAsFixedFormat(_XL_TYPE_PDF, str(page))
                if not sdk.exists(page):
                    raise RuntimeError(
                        f"Larger bin label PDF was not written: {page}")
                out[idx] = page
                log(f"  Order {idx} ({order}, {count} parts) -> "
                    "larger bin label page")
            finally:
                _revert_edits(ws_big, edits, log)
            excel.CalculateFull()
    finally:
        d21.Value = 1
        excel.CalculateFull()
        _restore_page_setup(ws_big, saved_setup, log)
    return out


def _merge_kit_pages(pdf_paths: list[Path], iterations: list[int],
                     larger_pages: dict[int, Path], dest: Path, log) -> None:
    """Merge the per-iteration 2-page exports into the final kitting PDF,
    SUBSTITUTING the larger bin label page for any order that overflowed - the
    order keeps its place in the print order, it just prints all its parts."""
    merged = fitz.open()
    try:
        for i, n in enumerate(iterations):
            src_path = pdf_paths[i]
            sdk.ensure_local(src_path)  # OneDrive placeholder -> download first
            src = fitz.open(sdk.long_path(src_path))
            try:
                for side, order_index in enumerate((n, n + 1)):
                    big = larger_pages.get(order_index)
                    if big is not None:
                        page = fitz.open(sdk.long_path(big))
                        try:
                            merged.insert_pdf(page)
                        finally:
                            page.close()
                    elif side < src.page_count:
                        merged.insert_pdf(src, from_page=side, to_page=side)
                    else:
                        log(f"  WARNING: {src_path.name} has {src.page_count} "
                            f"page(s); order {order_index} has no page to merge")
            finally:
                src.close()
        merged.save(sdk.long_path(dest))
    finally:
        merged.close()


# Missing source-material pre-check -------------------------------------------

def _cell_text(ws, addr: str) -> str:
    """A cell's DISPLAYED text. .Text (not .Value) so a lookup error shows as
    its '#N/A'-style string instead of a COM error integer."""
    try:
        txt = ws.Range(addr).Text
    except Exception:
        return ""
    return str(txt or "").strip()


def _is_blank_value(txt: str) -> bool:
    """'' is blank; '0' is what a lookup of an empty source cell renders
    (real material codes are never a bare 0); '#...' is a broken lookup."""
    return txt == "" or txt == "0" or txt.startswith("#")


def _scan_missing_source_material(
    excel, ws, cancel_event, progress_callback, p_start: int, p_end: int,
) -> list[tuple[int, int, str]]:
    """One pass over every kit page BEFORE anything prints: a line with a
    part (DYPN) but no Raw Material means the PO has no source material for
    it, and that field would go out blank. Returns [(order_no, row, dypn)].
    Leaves D21 back at 1."""
    d21 = ws.Range("D21")
    iterations = list(range(1, 36, 2))
    missing: list[tuple[int, int, str]] = []
    for idx, n in enumerate(iterations):
        sdk.raise_if_cancelled(cancel_event)
        d21.Value = n
        excel.CalculateFull()
        for r in PART_ROWS:
            for order_no, dypn_col, rawmat_col in (
                (n, LEFT_DYPN_COL, LEFT_RAWMAT_COL),
                (n + 1, RIGHT_DYPN_COL, RIGHT_RAWMAT_COL),
            ):
                dypn_txt = _cell_text(ws, f"{dypn_col}{r}")
                if _is_blank_value(dypn_txt):
                    continue
                if _is_blank_value(_cell_text(ws, f"{rawmat_col}{r}")):
                    missing.append((order_no, r, dypn_txt))
        progress_callback(
            p_start + int((idx + 1) / len(iterations) * (p_end - p_start)))
    d21.Value = 1
    excel.CalculateFull()
    return missing


def _scan_missing_overflow(excel, ws_big, oversize, cancel_event, log
                           ) -> list[tuple[int, int, str]]:
    """The standard pre-check can only see an order's first rows. For orders
    that overflow onto the larger sheet, check the rows ONLY that sheet shows,
    so a part with no source material there is caught too."""
    d21 = ws_big.Range(LARGER_DRIVER_CELL)
    extra_rows = [r for r in LARGER_PART_ROWS
                  if r >= min(LARGER_PART_ROWS) + STANDARD_CAPACITY]
    missing: list[tuple[int, int, str]] = []
    for idx, _meta in sorted(oversize.items()):
        sdk.raise_if_cancelled(cancel_event)
        d21.Value = idx
        excel.CalculateFull()
        for r in extra_rows:
            dypn_txt = _cell_text(ws_big, f"{LEFT_DYPN_COL}{r}")
            if _is_blank_value(dypn_txt):
                continue
            if _is_blank_value(_cell_text(ws_big, f"{LEFT_RAWMAT_COL}{r}")):
                missing.append((idx, r, dypn_txt))
    d21.Value = 1
    excel.CalculateFull()
    return missing


def _resolve_missing_source_material(
    params: dict, console, missing: list[tuple[int, int, str]], log,
) -> None:
    """Halt on missing source material unless the user chooses to proceed.
    Raises UserFacingError to stop; returns normally to proceed anyway."""
    log(f"WARNING: {len(missing)} kit line(s) have a part but NO source material:")
    for o, r, d in missing:
        log(f"  Order {o}, row {r}: {d}")

    lines = "\n".join(f"  Order {o}, row {r}: {d}" for o, r, d in missing)
    choice = None
    if hasattr(sdk, "request_choice"):
        choice = sdk.request_choice(
            params, "922 Kitting - missing source material",
            "These kit lines have a part but no source material, so the "
            f"field would print blank:\n\n{lines}\n\n"
            "Stop and fix the PO / organizer first, or generate the kitting "
            "paperwork anyway?",
            [_CHOICE_STOP, _CHOICE_PROCEED])
    elif console is not None and hasattr(console, "request_input"):
        ans = console.request_input(
            f"{len(missing)} kit line(s) are missing their source material "
            "(listed above). Proceed anyway? Y/N")
        if (ans or "").strip().lower() in {"y", "yes"}:
            choice = _CHOICE_PROCEED
    else:
        ans = input(f"{len(missing)} kit line(s) missing source material. "
                    "Proceed anyway? Y/N: ")
        if (ans or "").strip().lower() in {"y", "yes"}:
            choice = _CHOICE_PROCEED

    if choice != _CHOICE_PROCEED:
        raise sdk.UserFacingError(
            f"{len(missing)} kit line(s) have a part with no source material "
            "(listed in the console).",
            "Fill in the SOURCE MATERIAL for those parts on the PO / Pallet & "
            "Rod Organizer, then run 922 Kitting again - or choose 'Proceed "
            "anyway' when it asks.")

    log("Proceeding anyway - those fields will print blank.")
    if hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_WARNING,
            f"{len(missing)} kit line(s) missing source material - "
            "proceeded anyway")


# Main entry ------------------------------------------------------------------

def run(params: dict, progress_callback, cancel_event: threading.Event) -> None:
    log = params.get('log', print)
    console = params.get('console')
    settings = params.get('settings', {}) or {}

    log("Starting 922 Kitting...")
    progress_callback(0)

    if not _COM_AVAILABLE:
        raise RuntimeError(
            "pywin32 (win32com.client) is not available. Excel COM is required."
        )

    # Batch input = pick the 'Batch NNN' folder (Sentry Drone capable,
    # family-cache aware — a queued 922 run prompts at most once).
    picked = sdk.request_922_batch_folder(params, settings.get('base_path', ''))
    if picked is None or cancel_event.is_set():
        return  # user cancelled — the helper already flagged the run
    batch_no, batch_path = picked
    doc_folder = batch_path / f"Batch {batch_no} - Documentation"
    organizer_path = _find_organizer_workbook(doc_folder, batch_no)
    if not organizer_path:
        raise RuntimeError(
            f"Pallet & Rod Organizer workbook not found in {doc_folder}"
        )
    log(f"Workbook: {organizer_path.name}")

    kitting_dir = doc_folder / "Kitting"
    sdk.ensure_dir(kitting_dir)
    final_pdf = kitting_dir / f"Kitting {batch_no}.pdf"
    labels_pdf = kitting_dir / f"Bin Labels {batch_no}.pdf"
    progress_callback(5)

    # Stage workbook locally - Excel COM is unreliable directly against OneDrive paths
    stage_dir = Path(tempfile.mkdtemp(prefix=f"techdeck_kitting_{batch_no}_"))
    log(f"Staging dir: {stage_dir}")
    staged_workbook = stage_dir / organizer_path.name
    pdf_dir = stage_dir / "pdfs"
    sdk.ensure_dir(pdf_dir)

    sdk.copy_resilient(organizer_path, staged_workbook, log)  # hydrate + locked-open message

    excel = None
    wb = None
    ws_kit = None
    in_progress_edits: list[tuple[str, str]] = []

    pythoncom.CoInitialize()
    try:
        try:
            excel = win32.DispatchEx("Excel.Application")
        except Exception as exc:
            raise RuntimeError(f"Failed to launch Excel via COM: {exc}")

        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False

        wb = excel.Workbooks.Open(str(staged_workbook))

        # Calculation property is only settable once a workbook is open
        try:
            excel.Calculation = _XL_CALC_AUTOMATIC
        except Exception as exc:
            log(f"  WARNING: could not set Calculation=Automatic ({exc}); continuing")

        try:
            ws_kit = wb.Worksheets(SHEET_NAME)
        except Exception:
            raise RuntimeError(f"'{SHEET_NAME}' sheet not found in workbook")

        # Phase 1
        log("Phase 1: applying batch color formatting...")
        scheme = _batch_color_scheme(ws_kit, batch_no, log)
        _apply_color_scheme(ws_kit, scheme, PRIMARY_CELLS, SECONDARY_CELLS)

        # The larger bin label is a hidden sheet, so it is easy to forget - it
        # gets the SAME batch colors whether or not this batch needs it.
        ws_big = None
        try:
            ws_big = wb.Worksheets(LARGER_SHEET_NAME)
        except Exception:
            log(f"  WARNING: '{LARGER_SHEET_NAME}' sheet not found - an order "
                f"with more than {STANDARD_CAPACITY} parts would print "
                "truncated")
        if ws_big is not None:
            _apply_color_scheme(ws_big, scheme,
                                LARGER_PRIMARY_CELLS, LARGER_SECONDARY_CELLS)
            log(f"  '{LARGER_SHEET_NAME}' recolored to match")
        progress_callback(10)
        if cancel_event.is_set():
            log("Cancelled.")
            return

        bent_plates = _collect_bent_plates(wb, log)
        log(f"Bent Plates DYPNs indexed: {len(bent_plates)}")

        # Which orders have more parts than the standard checklist can print?
        oversize: dict[int, tuple[str, int]] = {}
        if ws_big is not None:
            oversize = _find_oversize_orders(wb, ws_kit, log)
            if oversize:
                for idx, (order, count) in sorted(oversize.items()):
                    log(f"  Order {idx} ({order}) has {count} parts - more than "
                        f"the {STANDARD_CAPACITY}-row checklist; will print on "
                        f"'{LARGER_SHEET_NAME}'")
                    if count > LARGER_CAPACITY:
                        log(f"    WARNING: '{LARGER_SHEET_NAME}' only shows "
                            f"{LARGER_CAPACITY} parts - {count - LARGER_CAPACITY} "
                            "would still be cut off")
                        if hasattr(sdk, "set_run_outcome"):
                            sdk.set_run_outcome(
                                params, sdk.RUN_OUTCOME_WARNING,
                                f"Order {order} has {count} parts - too many "
                                f"for even '{LARGER_SHEET_NAME}'")
            else:
                log(f"  No order exceeds the {STANDARD_CAPACITY}-row checklist.")
        progress_callback(15)

        # Pre-check: find every kit line missing its source material BEFORE
        # any paperwork is generated, and halt unless the user says otherwise.
        # Nothing is saved yet, so a halt here leaves the workbook untouched.
        log("Pre-check: scanning all kit pages for missing source material...")
        missing = _scan_missing_source_material(
            excel, ws_kit, cancel_event, progress_callback, 15, 25)
        if ws_big is not None and oversize:
            # Rows past the standard checklist only exist on the larger sheet.
            missing.extend(_scan_missing_overflow(
                excel, ws_big, oversize, cancel_event, log))
            missing.sort()
        if missing:
            _resolve_missing_source_material(params, console, missing, log)
        else:
            log("  All kit lines have a source material.")
        progress_callback(25)

        # Phase 2: print loop
        d21 = ws_kit.Range("D21")
        try:
            current_val = int(float(d21.Value))
        except (TypeError, ValueError):
            current_val = None
        if current_val != 1:
            log(f"  D21 was {d21.Value!r}; resetting to 1")
            d21.Value = 1
            excel.CalculateFull()

        # Capture original PrintArea and derive the labels-only variant
        original_print_area = ws_kit.PageSetup.PrintArea or ""
        labels_print_area = _derive_labels_print_area(original_print_area)
        log(f"  Full print area  : {original_print_area or '(empty)'}")
        log(f"  Labels print area: {labels_print_area}")

        iterations = list(range(1, 36, 2))
        total_iters = len(iterations)
        pdf_paths: list[Path] = []
        label_pdf_paths: list[Path] = []

        for idx, n in enumerate(iterations):
            if cancel_event.is_set():
                log("Cancelled.")
                return

            log(f"Printing orders {n} & {n + 1}...")
            d21.Value = n
            excel.CalculateFull()

            # Labels-only export (no FORMED edits - rows 22-31 not in this print area)
            label_pdf = pdf_dir / f"L{idx:02d}.pdf"
            try:
                ws_kit.PageSetup.PrintArea = labels_print_area
                ws_kit.ExportAsFixedFormat(_XL_TYPE_PDF, str(label_pdf))
                if not sdk.exists(label_pdf):
                    raise RuntimeError(f"Labels PDF was not written: {label_pdf}")
                label_pdf_paths.append(label_pdf)
            finally:
                ws_kit.PageSetup.PrintArea = original_print_area

            # Full kit export (with FORMED detection)
            in_progress_edits = _apply_formed_edits(ws_kit, bent_plates, log)
            try:
                if in_progress_edits:
                    excel.CalculateFull()

                out_pdf = pdf_dir / f"p{idx:02d}.pdf"
                ws_kit.ExportAsFixedFormat(_XL_TYPE_PDF, str(out_pdf))

                if not sdk.exists(out_pdf):
                    raise RuntimeError(f"PDF was not written: {out_pdf}")

                pdf_paths.append(out_pdf)
            finally:
                _revert_edits(ws_kit, in_progress_edits, log)
                in_progress_edits = []

            excel.CalculateFull()
            progress_callback(25 + int((idx + 1) / total_iters * 60))

        # Reset driver
        d21.Value = 1
        excel.CalculateFull()

        # Phase 3: re-print the oversize orders off the larger sheet. Excel
        # will not export a hidden worksheet, so unhide it for the export and
        # put its visibility back before the workbook is saved.
        larger_pages: dict[int, Path] = {}
        if ws_big is not None and oversize:
            log(f"Phase 3: re-printing {len(oversize)} oversize order(s) on "
                f"'{LARGER_SHEET_NAME}'...")
            original_visible = ws_big.Visible
            try:
                if original_visible != _XL_SHEET_VISIBLE:
                    ws_big.Visible = _XL_SHEET_VISIBLE
                larger_pages = _render_oversize_pages(
                    excel, ws_big, oversize, bent_plates, pdf_dir,
                    cancel_event, log)
            finally:
                try:
                    ws_big.Visible = original_visible
                except Exception as exc:
                    log(f"  WARNING: could not restore '{LARGER_SHEET_NAME}' "
                        f"visibility: {exc}")
        progress_callback(88)

        # Save and close
        log("Saving workbook...")
        wb.Save()
        wb.Close(False)
        wb = None
        ws_kit = None
        excel.Quit()
        excel = None
        progress_callback(92)

        # Merge full-kit PDFs, swapping in the larger page for oversize orders
        log(f"Merging {len(pdf_paths)} full PDF(s) into {final_pdf.name}"
            + (f" ({len(larger_pages)} order(s) on the larger bin label)"
               if larger_pages else "") + "...")
        _merge_kit_pages(pdf_paths, iterations, larger_pages, final_pdf, log)
        progress_callback(94)

        # Merge labels-only PDFs
        log(f"Merging {len(label_pdf_paths)} labels PDF(s) into {labels_pdf.name}...")
        merged_labels = fitz.open()
        try:
            for p in label_pdf_paths:
                sdk.ensure_local(p)  # OneDrive placeholder -> download first (Hard Rule 13)
                src = fitz.open(sdk.long_path(p))
                try:
                    merged_labels.insert_pdf(src)
                finally:
                    src.close()
            merged_labels.save(sdk.long_path(labels_pdf))
        finally:
            merged_labels.close()
        progress_callback(96)

        # Copy staged workbook back over the OneDrive original
        log("Copying workbook back to OneDrive...")
        shutil.copy2(sdk.long_path(staged_workbook), sdk.long_path(organizer_path))
        progress_callback(100)

        log("=" * 50)
        log(f"922 Kitting -- Batch {batch_no}")
        log(f"  Orders printed   : 36")
        if larger_pages:
            log(f"  Larger bin labels: {len(larger_pages)} "
                f"({', '.join(oversize[i][0] for i in sorted(larger_pages))})")
        log(f"  Full output PDF  : {final_pdf}")
        log(f"  Labels output PDF: {labels_pdf}")
        log("=" * 50)

    finally:
        if ws_kit is not None and in_progress_edits:
            try:
                _revert_edits(ws_kit, in_progress_edits, log)
            except Exception:
                pass

        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            shutil.rmtree(sdk.long_path(stage_dir), ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    cancel = threading.Event()
    run(
        params={'log': print, 'settings': {}, 'console': None},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=cancel,
    )
