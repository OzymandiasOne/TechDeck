"""
911 Setup Plugin
================
Automates the full 911 QTDR batch setup workflow:

  1. Prompt for batch number → locate batch folder
  2. Read BATCH LIST → extract unique nest numbers from "Nest Pkg Nbr" header column
  3. Create a subfolder per nest inside the batch folder
  4. Copy "911 BATCH _.xlsx" template into each nest folder, rename it
  5. Copy Working Forecast List → extract rows for each nest → paste into
     NEST sheet cols A-C starting row 4
  6. Parse NEST PACKAGES PDFs → extract MIL-S spec (→ D4) and MATL (→ E4)
  7. Read BATCH LIST → filter rows by nest number → paste into NEST cols F-K
     starting row 4
  8. Read DYPN values from NEST col G → copy INSPECTION SHEET tab for each
     part, write full DYPN into A16 (merged A16:C17). Nothing else on the
     copied sheet is modified -- the template's formulas/CF drive the rest
     off A16. Sheet name = suffix (e.g. "-80"); on collisions, both
     colliding sheets are renamed using the last 2 chars of the preceding
     segment (e.g. H4533321-80 -> "21-80", H4533322-80 -> "22-80").
  9. Save every nest excel, repeat for all nests in the batch
 10. Build MOVE TICKET OMIT PDF for each nest (removes MOVE TICKET pages, keeps MIL-SPEC/HULL)

v1.2.0 changes
  - Filesystem roots are configurable via plugin settings:
      * qtdr_base_path     -> 911 QTDR root
      * forecast_dir       -> Forecast and Inventory Reports root
      * template_subdir    -> subpath under QTDR for the 911 BATCH template
      * forecast_filename  -> name of the working forecast workbook
    Blank/missing values fall back to the original Path.home() defaults,
    so existing installs keep working without any setup.

  - Nest number regex updated to ^[PS]?\\d{3,}$ (case-insensitive).
    Accepts:
      * P07866, S013      (existing P/S-prefixed format)
      * 503682            (new digits-only format)
    Rejects stray small numbers (< 3 digits) that could appear in totals
    or footer rows.

  - QTDR root existence is validated before trying to find the batch
    folder, with an error message that points the user at the relevant
    setting.

  - FIXED: forecast row matching used a raw `==` between the batch-list
    nest (str) and the forecast cell value. Digits-only nests like
    "503627" failed silently because the forecast stores them as int.
    Match now normalizes both sides to stripped, upper-cased strings.
"""

import re
import shutil
import threading
from pathlib import Path

import openpyxl
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfWriter, PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Nest number pattern
#
# Accepts an optional P or S prefix (case-insensitive), then 3 or more digits.
# The 3-digit minimum filters out stray small numbers that could appear in
# totals/footers without rejecting any real nest number we've seen.
# ---------------------------------------------------------------------------
_NEST_RE = re.compile(r'^[PS]?\d{3,}$', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Path helpers
#
# Each helper takes an optional override string. If the override is non-empty
# it wins; otherwise the helper falls back to the default Path.home() path
# that the plugin has always used. This means the new settings are purely
# additive - blank settings preserve the previous behavior exactly.
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE_SUBDIR = "03 - Processing Forms & Templates\\00 - SACO"
_DEFAULT_FORECAST_FILENAME = "Working Forecast List.xlsx"


def _default_qtdr() -> Path:
    """Default 911 QTDR root, used when no override is configured."""
    return (
        Path.home()
        / "American Steel & Alum"
        / "Communication site - Electric Boat ASA Docs"
        / "Pilot Program"
        / "911 QTDR"
    )


def _default_forecast_dir() -> Path:
    """Default Forecast and Inventory Reports root."""
    return (
        Path.home()
        / "American Steel & Alum"
        / "Communication site - Electric Boat ASA Docs"
        / "Pilot Program"
        / "Forecast and Inventory Reports"
    )


def _base_qtdr(override: str = "") -> Path:
    """911 QTDR root. Uses the configured override if non-empty."""
    if override:
        return Path(override).expanduser()
    return _default_qtdr()


def _forecast_dir(override: str = "") -> Path:
    """Forecast and Inventory Reports root. Uses the configured override if non-empty."""
    if override:
        return Path(override).expanduser()
    return _default_forecast_dir()


def _template_dir(qtdr_override: str = "",
                  template_subdir: str = _DEFAULT_TEMPLATE_SUBDIR) -> Path:
    """Template directory, relative to the 911 QTDR root."""
    return _base_qtdr(qtdr_override) / template_subdir


# ---------------------------------------------------------------------------
# BATCH LIST helpers
# ---------------------------------------------------------------------------

def _find_batch_list(batch_folder: Path, batch_number: str) -> Path:
    """
    Locate the BATCH LIST excel inside the batch folder.
    Expected name: "<batch_number> BATCH LIST.xlsx" (case-insensitive).
    Falls back to any .xlsx containing 'BATCH LIST' if exact name not found.
    """
    exact = batch_folder / f"{batch_number} BATCH LIST.xlsx"
    if exact.exists():
        return exact

    for f in batch_folder.iterdir():
        if (f.is_file()
                and f.suffix.lower() == ".xlsx"
                and "BATCH LIST" in f.name.upper()
                and not f.name.startswith("~")):
            return f

    raise FileNotFoundError(
        f"No BATCH LIST file found in {batch_folder}. "
        f"Expected '{batch_number} BATCH LIST.xlsx'."
    )


def _find_header_col(ws, header_name: str, header_row: int):
    """
    Scan a specific row for a column whose value matches header_name
    (case-insensitive, stripped). Returns the 1-based column index or None.
    """
    for col in range(1, ws.max_column + 1):
        val = ws.cell(header_row, col).value
        if val is not None and str(val).strip().upper() == header_name.upper():
            return col
    return None


def _get_unique_nests_from_batch_list(batch_list_path: Path) -> list:
    """
    Read the BATCH LIST 'BATCH' sheet.
    Headers in row 3, data from row 4.
    Locates 'Nest Pkg Nbr' column by header name (case-insensitive).
    Returns ordered list of unique nest numbers matching [PS]\\d+ pattern.
    """
    wb = load_workbook(batch_list_path, data_only=True)
    ws = wb["BATCH"] if "BATCH" in wb.sheetnames else wb.active

    nest_col = _find_header_col(ws, "Nest Pkg Nbr", header_row=3)
    if nest_col is None:
        wb.close()
        raise ValueError(
            f"Could not find 'Nest Pkg Nbr' column header in row 3 of {batch_list_path.name}."
        )

    seen = []
    seen_set = set()
    for row in range(4, ws.max_row + 1):
        val = ws.cell(row, nest_col).value
        if val is not None:
            val = str(val).strip()
            if val and _NEST_RE.match(val) and val not in seen_set:
                seen_set.add(val)
                seen.append(val)

    wb.close()
    return seen


def _get_batch_rows_for_nest(batch_list_path: Path, nest_number: str) -> list:
    """
    Read the BATCH LIST 'BATCH' sheet and return rows matching nest_number
    in the 'Nest Pkg Nbr' column.

    Headers in row 3, data from row 4.
    Pulls these columns by header name (case-insensitive):
      Work Order, DYPN, Material, DYPN QTY, Nest Pkg Nbr, SCOPE OF WORK

    Returns list of 6-tuples in that order.
    """
    wb = load_workbook(batch_list_path, data_only=True)
    ws = wb["BATCH"] if "BATCH" in wb.sheetnames else wb.active

    HEADER_ROW = 3

    col_work_order = _find_header_col(ws, "Work Order",    HEADER_ROW)
    col_dypn       = _find_header_col(ws, "DYPN",          HEADER_ROW)
    col_material   = _find_header_col(ws, "Material",      HEADER_ROW)
    col_dypn_qty   = _find_header_col(ws, "DYPN QTY",      HEADER_ROW)
    col_nest       = _find_header_col(ws, "Nest Pkg Nbr",  HEADER_ROW)
    col_scope      = _find_header_col(ws, "SCOPE OF WORK", HEADER_ROW)

    missing = [name for name, col in [
        ("Work Order",    col_work_order),
        ("DYPN",          col_dypn),
        ("Material",      col_material),
        ("DYPN QTY",      col_dypn_qty),
        ("Nest Pkg Nbr",  col_nest),
        ("SCOPE OF WORK", col_scope),
    ] if col is None]

    if missing:
        wb.close()
        raise ValueError(
            f"Could not find these column headers in row 3 of {batch_list_path.name}: "
            + ", ".join(missing)
        )

    rows = []
    for row in range(4, ws.max_row + 1):
        nest_val = ws.cell(row, col_nest).value
        if nest_val is not None and str(nest_val).strip().upper() == nest_number.upper():
            rows.append((
                ws.cell(row, col_work_order).value,
                ws.cell(row, col_dypn).value,
                ws.cell(row, col_material).value,
                ws.cell(row, col_dypn_qty).value,
                ws.cell(row, col_nest).value,
                ws.cell(row, col_scope).value,
            ))

    wb.close()
    return rows


def _paste_batch_rows_into_nest(nest_ws, batch_rows: list):
    """
    Paste batch_rows into NEST sheet cols F-K (6-11) starting at row 4.
    Each item is a 6-tuple:
      (Work Order, DYPN, Material, DYPN QTY, Nest Pkg Nbr, SCOPE OF WORK)
    """
    for i, row_data in enumerate(batch_rows):
        dest_row = 4 + i
        for j, val in enumerate(row_data):
            nest_ws.cell(dest_row, 6 + j).value = val  # F=6 through K=11


# ---------------------------------------------------------------------------
# Step 5: Working Forecast List -> NEST cols A-C
# ---------------------------------------------------------------------------

def _copy_forecast_rows(forecast_wb, nest_number: str) -> list:
    """
    In the '911 Forecast' sheet, find all rows where column G == nest_number.
    Return list of (A, B, C) tuples for those rows.

    Note: column G stores some nests as int (e.g. 503627) and some as str
    (e.g. "9FANDR"), while nest_number is always a str coming from the
    BATCH LIST reader. Normalize both sides before comparing so int-stored
    nests match correctly.
    """
    ws = forecast_wb["911 Forecast"]
    target = str(nest_number).strip().upper()
    rows = []
    for row in range(2, ws.max_row + 1):
        g_val = ws.cell(row, 7).value
        if g_val is None:
            continue
        if str(g_val).strip().upper() == target:
            rows.append((
                ws.cell(row, 1).value,
                ws.cell(row, 2).value,
                ws.cell(row, 3).value,
            ))
    return rows


def _paste_forecast_into_nest(nest_ws, forecast_rows: list):
    """
    Paste forecast_rows into NEST sheet cols A, B, C starting at row 4.
    """
    for i, (a, b, c) in enumerate(forecast_rows):
        dest_row = 4 + i
        nest_ws.cell(dest_row, 1).value = a
        nest_ws.cell(dest_row, 2).value = b
        nest_ws.cell(dest_row, 3).value = c


# ---------------------------------------------------------------------------
# Step 6: PDF -> MIL-S spec + MATL
# ---------------------------------------------------------------------------

def _extract_pdf_data(pdf_path: Path) -> tuple:
    """
    Parse a PDF and return (mil_spec, matl_type).
    Returns (None, None) if not found.
    """
    if not PYMUPDF_AVAILABLE:
        raise ImportError(
            "PyMuPDF is required for PDF parsing. "
            "Install it with: pip install pymupdf"
        )

    doc = fitz.open(str(pdf_path))
    mil_spec = None
    matl_type = None

    for page in doc:
        text = page.get_text()

        if mil_spec is None:
            m = re.search(r'MIL-S-\d+', text)
            if m:
                mil_spec = m.group(0)

        if matl_type is None:
            m = re.search(r'MATL:\s*(\S+)', text)
            if m:
                matl_type = m.group(1)

        if mil_spec and matl_type:
            break

    doc.close()
    return mil_spec, matl_type


def _get_pdf_data_for_nest(nest_packages_folder: Path, log) -> tuple:
    """
    Search all PDFs in NEST PACKAGES folder.
    Return (mil_spec, matl_type) aggregated across PDFs.
    """
    if not nest_packages_folder.exists():
        log(f"  WARNING: NEST PACKAGES folder not found: {nest_packages_folder}")
        return None, None

    pdfs = [f for f in nest_packages_folder.iterdir()
            if f.is_file() and f.suffix.lower() == ".pdf"]

    if not pdfs:
        log(f"  WARNING: No PDFs found in {nest_packages_folder}")
        return None, None

    mil_spec = None
    matl_type = None

    for pdf in pdfs:
        log(f"  Parsing PDF: {pdf.name}")
        try:
            ms, mt = _extract_pdf_data(pdf)
            if ms and mil_spec is None:
                mil_spec = ms
            if mt and matl_type is None:
                matl_type = mt
        except Exception as e:
            log(f"  WARNING: Could not parse {pdf.name}: {e}")

        if mil_spec and matl_type:
            break

    return mil_spec, matl_type


# ---------------------------------------------------------------------------
# Step 7b: Part Sketch extraction -> MOVE TICKET OMIT PDF
# ---------------------------------------------------------------------------


def _extract_nest_drawings(nest_packages_folder: Path, nest_number: str,
                            dest_path: Path, log) -> bool:
    """
    Build the MOVE TICKET OMIT PDF for a nest.

    Starts with every page in the nest's source PDF and removes pages that
    contain "MOVE TICKET" text.  Pages that contain "MIL-SPEC" or "HULL"
    are always kept, even if they also contain "MOVE TICKET".

    Returns True if the output PDF was written successfully.
    """
    if not PYPDF_AVAILABLE:
        log("  WARNING: pypdf not available -- cannot extract drawings PDF.")
        return False

    if not nest_packages_folder.exists():
        log("  WARNING: NEST PACKAGES folder not found -- skipping drawings.")
        return False

    nest_upper = nest_number.upper()
    matching_pdf = None
    for f in nest_packages_folder.iterdir():
        if f.is_file() and f.suffix.lower() == ".pdf":
            if nest_upper in f.stem.upper():
                matching_pdf = f
                break

    if matching_pdf is None:
        log(f"  WARNING: No PDF containing '{nest_number}' found in NEST PACKAGES.")
        return False

    log(f"  Found nest PDF: {matching_pdf.name}")

    try:
        doc = fitz.open(str(matching_pdf))
        total_pages = len(doc)

        keep_indices = []
        removed = 0
        for i in range(total_pages):
            text = (doc[i].get_text("text") or "").upper()
            if "MOVE TICKET" in text and "MIL-SPEC" not in text and "HULL" not in text:
                removed += 1
            else:
                keep_indices.append(i)
        doc.close()

        if not keep_indices:
            log(f"  WARNING: All {total_pages} pages are MOVE TICKET pages — nothing to write for {nest_number}.")
            return False

        reader = PdfReader(str(matching_pdf))
        writer = PdfWriter()
        for idx in keep_indices:
            writer.add_page(reader.pages[idx])

        with open(dest_path, "wb") as f:
            writer.write(f)

        log(f"  Drawings PDF: {dest_path.name} ({len(keep_indices)} page(s), removed {removed} MOVE TICKET page(s))")
        return True

    except Exception as e:
        log(f"  WARNING: Could not write drawings PDF: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 8: Inspection sheet naming helpers
# ---------------------------------------------------------------------------

def _basic_suffix(dypn: str) -> str:
    """Sheet name = part after the last '-' (e.g. 'H4533321-80' -> '-80')."""
    parts = dypn.rsplit('-', 1)
    return f"-{parts[-1]}" if len(parts) == 2 else dypn


def _disambiguated_name(dypn: str) -> str:
    """
    Used when two DYPNs share a suffix.
    H4533321-80 -> '21-80', H4533322-80 -> '22-80'
    (last 2 chars of the head + '-' + suffix tail)
    """
    segments = dypn.rsplit('-', 1)
    if len(segments) == 2:
        head, tail = segments
        return f"{head[-2:]}-{tail}"
    return dypn


def _plan_sheet_names(dypns: list, existing_sheet_names: set = None) -> list:
    """
    Build the list of (full_dypn, sheet_name) pairs for the inspection
    sheet copy step. If two DYPNs share a suffix, *both* get the
    disambiguated name. Falls back to '<name> (n)' for any remaining
    collision (e.g. identical DYPNs).
    """
    if existing_sheet_names is None:
        existing_sheet_names = set()

    suffix_counts = {}
    for dypn in dypns:
        s = _basic_suffix(dypn)
        suffix_counts[s] = suffix_counts.get(s, 0) + 1

    used = set()
    plan = []
    for full_dypn in dypns:
        suffix = _basic_suffix(full_dypn)
        name = _disambiguated_name(full_dypn) if suffix_counts.get(suffix, 0) > 1 else suffix
        name = name[:31]

        base = name
        counter = 2
        while name in used or name in existing_sheet_names:
            name = f"{base} ({counter})"[:31]
            counter += 1
        used.add(name)
        plan.append((full_dypn, name))
    return plan


def _get_dypn_rows(nest_ws) -> list:
    """
    Read NEST col G (col 7, DYPN) from row 4 downward.
    Return list of full DYPN strings for every non-empty cell.
    """
    result = []
    for row in range(4, nest_ws.max_row + 1):
        val = nest_ws.cell(row, 7).value  # Column G = DYPN
        if val and str(val).strip():
            result.append(str(val).strip())
    return result


# ---------------------------------------------------------------------------
# Inspection sheet copy step uses Excel COM, not openpyxl.
#
# openpyxl's copy_worksheet does not propagate conditional formatting rules
# to the new sheet (verified empirically: 350 CF rules on the template ->
# 0 CF rules on every copy). The template's grey->white field-fill logic
# is driven entirely by those CF rules, so the copies look "completely
# white". Excel's native Sheet.Copy preserves the CF perfectly.
#
# openpyxl is still used for the NEST data writes -- those don't go through
# copy_worksheet, and the CF on the source INSPECTION SHEET tab survives
# the openpyxl load/save round-trip intact.
# ---------------------------------------------------------------------------

def _build_inspection_sheets_via_excel(workbook_path: Path, dypns: list, log):
    """
    Copy the INSPECTION SHEET tab once per DYPN, writing the full DYPN
    into A16 on each copy. Excel COM is used so conditional formatting
    on the copies is preserved (openpyxl's copy_worksheet drops it).

    Implementation note: Excel SaveAs writing back to a OneDrive-synced
    path fails with "Cannot access" because OneDrive is tracking the
    file. So we do all COM work on a local temp copy outside OneDrive,
    then atomically replace the original via os.replace.

    Nothing else on copies is modified -- template formulas/CF drive
    the rest off A16. The original INSPECTION SHEET tab stays visible.

    Sheet name = suffix after the last '-' (e.g. '-80'). When two DYPNs
    share a suffix, both names are disambiguated (e.g. H4533321-80 ->
    '21-80', H4533322-80 -> '22-80').
    """
    try:
        import win32com.client
        import pythoncom
    except ImportError:
        raise RuntimeError(
            "Excel COM bindings (pywin32) are required by 911 Setup."
        )

    import os
    import tempfile

    plan = _plan_sheet_names(dypns)

    xlCalculationManual = -4135
    xlCalculationAutomatic = -4105
    msoAutomationSecurityForceDisable = 3

    def _silence(app):
        """Disable every dialog category Excel can throw at us."""
        app.Visible = False
        app.DisplayAlerts = False
        app.ScreenUpdating = False
        app.EnableEvents = False
        app.AskToUpdateLinks = False
        for prop, val in (
            ("AlertBeforeOverwriting", False),
            ("FeatureInstall", 0),
            ("AutomationSecurity", msoAutomationSecurityForceDisable),
            ("Calculation", xlCalculationManual),
        ):
            try:
                setattr(app, prop, val)
            except Exception:
                pass

    pythoncom.CoInitialize()
    excel = None
    wb = None
    tmp_dir = None
    try:
        # Stage the file outside OneDrive so Excel never sees a synced path
        tmp_dir = tempfile.mkdtemp(prefix="techdeck_911_")
        local_copy = Path(tmp_dir) / workbook_path.name
        shutil.copy2(workbook_path, local_copy)
        log(f"  Staging via local temp: {local_copy}")

        excel = win32com.client.DispatchEx("Excel.Application")
        _silence(excel)

        wb = excel.Workbooks.Open(
            Filename=str(local_copy),
            UpdateLinks=0,
            ReadOnly=False,
            IgnoreReadOnlyRecommended=True,
            Notify=False,
            AddToMru=False,
        )
        try:
            wb.CheckCompatibility = False
        except Exception:
            pass

        template = wb.Sheets("INSPECTION SHEET")

        for full_dypn, sheet_name in plan:
            count_before = wb.Sheets.Count
            last_sheet = wb.Sheets(count_before)

            # Excel COM signature is Worksheet.Copy(Before, After).
            # Passing After= as a kwarg via pywin32 late binding has been
            # observed to silently fall through to Copy() with no args
            # (which spawns a new orphan workbook). Use positional args.
            template.Copy(None, last_sheet)

            try:
                excel.CutCopyMode = False
            except Exception:
                pass

            count_after = wb.Sheets.Count
            if count_after != count_before + 1:
                # Fallback: Copy()-with-no-args creates a new workbook;
                # move that sheet back into our workbook.
                log(f"  WARNING: in-place Copy did not grow sheet count "
                    f"({count_before} -> {count_after}); trying Copy()+Move fallback")
                try:
                    template.Copy()
                    new_wb = excel.ActiveWorkbook
                    if new_wb is not None and new_wb.Name != wb.Name:
                        new_wb.Sheets(1).Move(None, wb.Sheets(wb.Sheets.Count))
                        try:
                            new_wb.Close(SaveChanges=False)
                        except Exception:
                            pass
                except Exception as e:
                    raise RuntimeError(
                        f"Copy+Move fallback failed for {full_dypn}: {e}"
                    )
                if wb.Sheets.Count != count_before + 1:
                    raise RuntimeError(
                        f"Sheet.Copy did not create a new sheet for {full_dypn}. "
                        f"Workbook still has {wb.Sheets.Count} sheets."
                    )

            # After Copy/Move the new sheet is the active sheet. Don't
            # index by position -- the new copy isn't necessarily at the
            # end of the tab order, so wb.Sheets(wb.Sheets.Count) can
            # return the wrong sheet and we'd rename SOURCE MATERIAL INFO
            # 22 times instead of the actual copies.
            new_sheet = excel.ActiveSheet
            new_sheet.Name = sheet_name
            new_sheet.Range("A16").Value = full_dypn
            log(f"  Creating inspection sheet '{sheet_name}' for {full_dypn}")

        try:
            excel.Calculation = xlCalculationAutomatic
        except Exception:
            pass

        wb.Save()
        wb.Close(SaveChanges=False)
        wb = None

        # Tear Excel down before moving the file back -- ensures all
        # handles are released so os.replace can overwrite cleanly.
        try:
            excel.Quit()
        except Exception:
            pass
        excel = None

        # Atomic replace back into OneDrive. os.replace is atomic on
        # Windows when source and target are on the same volume.
        os.replace(str(local_copy), str(workbook_path))
        log(f"  Wrote final workbook -> {workbook_path}")
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.EnableEvents = True
                excel.DisplayAlerts = True
                excel.ScreenUpdating = True
            except Exception:
                pass
            try:
                excel.Quit()
            except Exception:
                pass
        excel = None
        if tmp_dir is not None:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------------------
# Template finder
# ---------------------------------------------------------------------------

def _find_template_911(template_dir: Path) -> Path:
    """
    Find '911 BATCH _.xlsx' in the template directory.
    Matches any .xlsx whose name starts with '911 BATCH' (case-insensitive).
    """
    for f in template_dir.iterdir():
        if (f.is_file()
                and f.suffix.lower() == ".xlsx"
                and f.stem.upper().startswith("911 BATCH")
                and not f.name.startswith("~")):
            return f

    raise FileNotFoundError(
        f"Could not find a '911 BATCH _.xlsx' template in {template_dir}"
    )


# ---------------------------------------------------------------------------
# Main run() function -- TechDeck plugin interface
# ---------------------------------------------------------------------------

def run(params: dict, progress_callback, cancel_event: threading.Event):
    """
    TechDeck plugin entry point.

    params keys:
      - 'settings': dict of plugin settings from plugin.json (optional overrides)
      - 'console':  TechDeck console (used for batch number prompt)
      - 'log':      callable injected by executor
      - 'batch_number': str (used when running without a console, e.g. CLI test)
    """
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    # ------------------------------------------------------------------ #
    # Read configurable paths from settings.
    # Blank/missing values fall back to the original Path.home() defaults.
    # ------------------------------------------------------------------ #
    qtdr_override     = (settings.get("qtdr_base_path") or "").strip()
    forecast_override = (settings.get("forecast_dir") or "").strip()
    template_subdir   = (settings.get("template_subdir") or "").strip() or _DEFAULT_TEMPLATE_SUBDIR
    forecast_filename = (settings.get("forecast_filename") or "").strip() or _DEFAULT_FORECAST_FILENAME

    # ------------------------------------------------------------------ #
    # Step 1 -- Prompt user for batch number, then resolve batch folder
    # ------------------------------------------------------------------ #
    console = params.get("console")
    if console and hasattr(console, "request_input"):
        raw = console.request_input("Enter Batch Number (e.g. V060, V086):")
    else:
        raw = params.get("batch_number", "")

    batch_number = raw.strip().upper()
    if not batch_number:
        raise ValueError("No batch number provided. Please enter a batch number.")

    qtdr_root = _base_qtdr(qtdr_override)
    batch_folder = qtdr_root / batch_number

    log(f"Batch number : {batch_number}")
    log(f"QTDR root    : {qtdr_root}")
    log(f"Batch folder : {batch_folder}")

    if not qtdr_root.exists():
        raise FileNotFoundError(
            f"911 QTDR root not found: {qtdr_root}\n"
            f"Check the '911 QTDR Base Directory' setting for this plugin, or "
            f"verify your OneDrive sync."
        )

    if not batch_folder.exists():
        raise FileNotFoundError(
            f"Batch folder not found: {batch_folder}\n"
            f"Verify the batch number '{batch_number}' is correct and the folder exists."
        )

    progress_callback(5)
    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------ #
    # Step 2 -- Find BATCH LIST and extract unique nest numbers
    # ------------------------------------------------------------------ #
    log("Locating BATCH LIST...")
    try:
        batch_list_path = _find_batch_list(batch_folder, batch_number)
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e))

    log(f"BATCH LIST    : {batch_list_path.name}")

    try:
        nest_numbers = _get_unique_nests_from_batch_list(batch_list_path)
    except ValueError as e:
        raise ValueError(str(e))

    if not nest_numbers:
        raise ValueError(
            f"No nest numbers found in the 'Nest Pkg Nbr' column of {batch_list_path.name}. "
            "Check that the BATCH LIST has data starting from row 4."
        )

    log(f"Nests found   : {', '.join(nest_numbers)}")
    progress_callback(10)

    # ------------------------------------------------------------------ #
    # Step 3 -- Create nest subfolders
    # ------------------------------------------------------------------ #
    log("Creating nest folders...")
    for nest in nest_numbers:
        nest_dir = batch_folder / nest
        nest_dir.mkdir(exist_ok=True)
        log(f"  Folder: {nest_dir.name}")

    progress_callback(15)
    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------ #
    # Step 4 -- Copy & rename 911 BATCH template into each nest folder
    # ------------------------------------------------------------------ #
    log("Copying 911 BATCH template...")
    template_dir = _template_dir(qtdr_override, template_subdir)

    if not template_dir.exists():
        raise FileNotFoundError(
            f"Template directory not found: {template_dir}\n"
            f"Check the 'Template Subfolder' setting for this plugin."
        )

    template_path = _find_template_911(template_dir)
    log(f"Template      : {template_path.name}")

    nest_excel_paths = {}
    for nest in nest_numbers:
        dest_name = f"911 BATCH {batch_number} {nest}.xlsx"
        dest_path = batch_folder / nest / dest_name
        shutil.copy2(template_path, dest_path)
        nest_excel_paths[nest] = dest_path
        log(f"  Copied -> {dest_name}")

    progress_callback(20)
    if cancel_event.is_set():
        return

    # ------------------------------------------------------------------ #
    # Step 5 -- Copy Working Forecast List into batch folder, load it
    # ------------------------------------------------------------------ #
    log("Copying Working Forecast List...")
    forecast_src = _forecast_dir(forecast_override) / forecast_filename
    if not forecast_src.exists():
        raise FileNotFoundError(
            f"Working Forecast List not found at:\n{forecast_src}\n"
            "Check the 'Forecast and Inventory Reports Directory' and "
            "'Working Forecast Filename' settings, and that the folder is synced."
        )

    forecast_copy = batch_folder / forecast_filename
    shutil.copy2(forecast_src, forecast_copy)
    log(f"Forecast copy : {forecast_copy}")

    log("Loading 911 Forecast sheet...")
    forecast_wb = load_workbook(forecast_copy, data_only=True)

    progress_callback(25)
    if cancel_event.is_set():
        forecast_wb.close()
        return

    # ------------------------------------------------------------------ #
    # Determine NEST PACKAGES folder path
    # ------------------------------------------------------------------ #
    nest_packages_folder = batch_folder / "NEST PACKAGES"

    progress_callback(30)

    # ------------------------------------------------------------------ #
    # Per-nest processing loop
    # ------------------------------------------------------------------ #
    total_nests = len(nest_numbers)
    for nest_idx, nest in enumerate(nest_numbers):
        if cancel_event.is_set():
            break

        log(f"\n{'='*50}")
        log(f"Processing nest {nest_idx+1}/{total_nests}: {nest}")
        log(f"{'='*50}")

        nest_excel = nest_excel_paths[nest]
        wb = load_workbook(nest_excel)
        nest_ws = wb["NEST"]

        # -- Step 5: Forecast data -> NEST cols A-C, starting row 4 ------
        log(f"  [Step 5] Extracting forecast rows for {nest}...")
        forecast_rows = _copy_forecast_rows(forecast_wb, nest)
        if not forecast_rows:
            log(f"  WARNING: No forecast rows found for nest {nest} in column G.")
        else:
            log(f"  Found {len(forecast_rows)} forecast rows.")
            _paste_forecast_into_nest(nest_ws, forecast_rows)

        # -- Step 6: PDF -> MIL-S spec (D4) + MATL (E4) ------------------
        log(f"  [Step 6] Parsing PDFs in NEST PACKAGES...")
        mil_spec, matl_type = _get_pdf_data_for_nest(nest_packages_folder, log)

        if mil_spec:
            nest_ws.cell(4, 4).value = mil_spec   # D4
            log(f"  MIL Spec -> D4: {mil_spec}")
        else:
            log(f"  WARNING: MIL-S spec not found in any PDF.")

        if matl_type:
            nest_ws.cell(4, 5).value = matl_type  # E4
            log(f"  MATL Type -> E4: {matl_type}")
        else:
            log(f"  WARNING: MATL type not found in any PDF.")

        # -- Step 7: BATCH LIST -> NEST cols F-K, starting row 4 ---------
        log(f"  [Step 7] Extracting batch rows for {nest}...")
        try:
            batch_rows = _get_batch_rows_for_nest(batch_list_path, nest)
        except ValueError as e:
            log(f"  WARNING: {e} -- skipping batch data for {nest}")
            batch_rows = []

        if not batch_rows:
            log(f"  WARNING: No batch rows found for nest {nest}.")
        else:
            log(f"  Found {len(batch_rows)} batch rows.")
            _paste_batch_rows_into_nest(nest_ws, batch_rows)

        # -- Step 8a: Collect DYPN values from NEST col G ----------------
        log(f"  [Step 8] Reading DYPN values from NEST col G...")
        dypns = _get_dypn_rows(nest_ws)
        if not dypns:
            log(f"  WARNING: No DYPN values found in NEST col G.")
        else:
            log(f"  Found {len(dypns)} DYPN rows.")

        # -- Save and close openpyxl workbook before Excel COM opens it --
        log(f"  Saving {nest_excel.name}...")
        wb.save(nest_excel)
        wb.close()

        # -- Step 8b: Copy inspection sheets via Excel COM ---------------
        # openpyxl's copy_worksheet drops conditional formatting rules
        # on copy (verified: 350 CF rules on template -> 0 on copy).
        # Excel's native Sheet.Copy preserves them.
        if dypns:
            log(f"  Building {len(dypns)} inspection sheet(s) via Excel...")
            try:
                _build_inspection_sheets_via_excel(nest_excel, dypns, log)
            except Exception as e:
                log(f"  ERROR: Excel COM inspection sheet build failed: {e}")
                raise

        log(f"  Done: {nest_excel.name}")

        # -- Step 9: Build MOVE TICKET OMIT PDF (remove MOVE TICKET pages, keep MIL-SPEC/HULL) --
        log(f"  [Step 9] Extracting drawings for {nest}...")
        drawings_dest = batch_folder / nest / f"{nest} MOVE TICKET OMIT.pdf"
        _extract_nest_drawings(nest_packages_folder, nest, drawings_dest, log)

        pct = 30 + int(65 * (nest_idx + 1) / total_nests)
        progress_callback(pct)

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #
    forecast_wb.close()

    progress_callback(100)
    log(f"\n{'='*50}")
    log(f"911 Setup complete for batch {batch_number}.")
    log(f"Processed {total_nests} nest(s): {', '.join(nest_numbers)}")
    log(f"{'='*50}")


# ---------------------------------------------------------------------------
# CLI entry point for local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    batch = input("Enter batch number: ").strip()
    if not batch:
        print("No batch number entered.")
        sys.exit(1)

    ev = threading.Event()

    def _prog(v):
        print(f"  [Progress] {v}%")

    run({"batch_number": batch, "log": print, "settings": {}}, _prog, ev)
