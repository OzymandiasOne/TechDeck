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

PRIMARY_CELLS = ["C2", "R2", "C20", "R20"]
SECONDARY_CELLS = ["C3", "R3", "C21", "R21"]

PART_ROWS = range(22, 32)
LEFT_DYPN_COL = "F"
LEFT_RAWMAT_COL = "G"
LEFT_MATDESC_COL = "H"
RIGHT_DYPN_COL = "U"
RIGHT_RAWMAT_COL = "V"
RIGHT_MATDESC_COL = "W"

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

def _apply_color_formatting(ws, batch_no: str, log) -> None:
    legend_addr = _legend_cell_for_batch(batch_no)
    legend_color = int(ws.Range(legend_addr).Interior.Color)
    rgb = _bgr_to_rgb(legend_color)
    log(f"  Legend {legend_addr}: RGB{rgb}")

    primary_text = (255, 255, 255) if _luminance(rgb) < LUMINANCE_DARK_CUTOFF else (0, 0, 0)
    light_rgb = _lighten(rgb)
    secondary_text = (255, 255, 255) if _luminance(light_rgb) < LUMINANCE_DARK_CUTOFF else (0, 0, 0)

    primary_bgr = _rgb_to_bgr(rgb)
    primary_text_bgr = _rgb_to_bgr(primary_text)
    secondary_bgr = _rgb_to_bgr(light_rgb)
    secondary_text_bgr = _rgb_to_bgr(secondary_text)

    for addr in PRIMARY_CELLS:
        cell = ws.Range(addr)
        cell.Interior.Color = primary_bgr
        cell.Font.Color = primary_text_bgr

    for addr in SECONDARY_CELLS:
        cell = ws.Range(addr)
        cell.Interior.Color = secondary_bgr
        cell.Font.Color = secondary_text_bgr

    log(f"  Primary fill RGB{rgb}, text {'white' if primary_text == (255, 255, 255) else 'black'}")
    log(f"  Secondary fill RGB{light_rgb}, text {'white' if secondary_text == (255, 255, 255) else 'black'}")


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

def _apply_formed_edits(ws, bent_plates: dict[str, set[str]], log) -> list[tuple[str, str]]:
    if not bent_plates:
        return []

    edits: list[tuple[str, str]] = []
    for r in PART_ROWS:
        for dypn_col, rawmat_col, desc_col in (
            (LEFT_DYPN_COL, LEFT_RAWMAT_COL, LEFT_MATDESC_COL),
            (RIGHT_DYPN_COL, RIGHT_RAWMAT_COL, RIGHT_MATDESC_COL),
        ):
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
    kitting_dir.mkdir(parents=True, exist_ok=True)
    final_pdf = kitting_dir / f"Kitting {batch_no}.pdf"
    labels_pdf = kitting_dir / f"Bin Labels {batch_no}.pdf"
    progress_callback(5)

    # Stage workbook locally - Excel COM is unreliable directly against OneDrive paths
    stage_dir = Path(tempfile.mkdtemp(prefix=f"techdeck_kitting_{batch_no}_"))
    log(f"Staging dir: {stage_dir}")
    staged_workbook = stage_dir / organizer_path.name
    pdf_dir = stage_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

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
        _apply_color_formatting(ws_kit, batch_no, log)
        progress_callback(10)
        if cancel_event.is_set():
            log("Cancelled.")
            return

        bent_plates = _collect_bent_plates(wb, log)
        log(f"Bent Plates DYPNs indexed: {len(bent_plates)}")
        progress_callback(15)

        # Pre-check: find every kit line missing its source material BEFORE
        # any paperwork is generated, and halt unless the user says otherwise.
        # Nothing is saved yet, so a halt here leaves the workbook untouched.
        log("Pre-check: scanning all kit pages for missing source material...")
        missing = _scan_missing_source_material(
            excel, ws_kit, cancel_event, progress_callback, 15, 25)
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
                if not label_pdf.exists():
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

                if not out_pdf.exists():
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

        # Merge full-kit PDFs
        log(f"Merging {len(pdf_paths)} full PDF(s) into {final_pdf.name}...")
        merged = fitz.open()
        try:
            for p in pdf_paths:
                sdk.ensure_local(p)  # OneDrive placeholder -> download first (Hard Rule 13)
                src = fitz.open(p)
                try:
                    merged.insert_pdf(src)
                finally:
                    src.close()
            merged.save(str(final_pdf))
        finally:
            merged.close()
        progress_callback(94)

        # Merge labels-only PDFs
        log(f"Merging {len(label_pdf_paths)} labels PDF(s) into {labels_pdf.name}...")
        merged_labels = fitz.open()
        try:
            for p in label_pdf_paths:
                sdk.ensure_local(p)  # OneDrive placeholder -> download first (Hard Rule 13)
                src = fitz.open(p)
                try:
                    merged_labels.insert_pdf(src)
                finally:
                    src.close()
            merged_labels.save(str(labels_pdf))
        finally:
            merged_labels.close()
        progress_callback(96)

        # Copy staged workbook back over the OneDrive original
        log("Copying workbook back to OneDrive...")
        shutil.copy2(staged_workbook, organizer_path)
        progress_callback(100)

        log("=" * 50)
        log(f"922 Kitting -- Batch {batch_no}")
        log(f"  Orders printed   : 36")
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
            shutil.rmtree(stage_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    cancel = threading.Event()
    run(
        params={'log': print, 'settings': {}, 'console': None},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=cancel,
    )
