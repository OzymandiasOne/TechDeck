"""911 SSPO Invoicing Prep v2.3.0 - invoice number + ship date on the supplement,
and the supplement-to-PDF step (invoicing's ask 2026-09-04, answers 2026-09-16).

Pins:
  - the forecast lookup carries PS/Inv + Ship Date, found by header NAME on both
    sheets ('911 Forecast' first, 'Complete 911 QTDR' fallback);
  - the Invoice Supplement gets G2 = PS/Inv and G3 = Ship Date; blank stays blank;
  - the PDF is printed ONLY for a nest with an invoice number, named
    'ASA Invoice No. {inv} Supplement.pdf' beside its back-up workbook;
  - a nest without PS/Inv lands in missing_invoice (no PDF), one with no forecast
    row at all stays in missing_po;
  - an exporter that can't run leaves pdf_error set and still writes every workbook.
"""
import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_sspo_invoicing_prep" / "run.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("sp_911_sspo_invoicing_prep", PLUGIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PRICING_HEADERS = ["Batch", "Work Order", "DYPN", "Material", "DYPN QTY",
                   "Nest Pkg Nbr", "TOTAL PRICE PER WO", "Firm VPD", "Machine",
                   "Scheduling Group", "Program", "SCOPE OF WORK", "SubGroup",
                   "Division", "Notes", "Material Status"]


def _pricing_workbook(path: Path, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(PRICING_HEADERS)
    for batch, nest, wo, total in rows:
        ws.append([batch, wo, f"H{wo}", "HSS", 2, nest, total,
                   datetime(2026, 9, 4), "V807", "Open", "911", "CUT", "A",
                   "SOPO", "", "OK"])
    wb.save(path)


def _forecast_workbook(path: Path, active_rows, complete_rows, with_inv=True):
    """Both 911 sheets with the REAL column positions that matter: PO/Line/Batch/
    Nest up front, Ship Date at AT (col 46) and PS/Inv at BD (col 56) - the
    lookup must find them by name, so the test also proves it isn't reading a
    fixed letter."""
    wb = Workbook()
    ws = wb.active
    ws.title = "911 Forecast"
    wb.create_sheet("Complete 911 QTDR")

    def fill(sheet, batch_header, rows):
        hdr = [""] * 56
        hdr[0], hdr[1], hdr[2], hdr[6] = "PO", "Line", batch_header, "Nest"
        hdr[45] = "Ship Date"
        if with_inv:
            hdr[55] = "PS/Inv"
        sheet.append(hdr)
        for po, line, batch, nest, ship, inv in rows:
            r = [None] * 56
            r[0], r[1], r[2], r[6] = po, line, batch, nest
            r[45], r[55] = ship, inv
            sheet.append(r)

    fill(wb["911 Forecast"], "Batch /DR", active_rows)
    fill(wb["Complete 911 QTDR"], "Batch/Order", complete_rows)
    wb.save(path)


class FakeExporter:
    """Stands in for Excel: records every export and writes an empty PDF."""

    def __init__(self, fail=False, error=None):
        self.calls = []
        self.fail = fail
        self.error = error
        self.closed = False

    def export(self, xlsx_path, pdf_path):
        self.calls.append((Path(xlsx_path), Path(pdf_path)))
        if self.fail:
            return False
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")
        return True

    def close(self):
        self.closed = True


@pytest.fixture
def qtdr(tmp_path):
    """A stand-in 911 QTDR tree. ALWAYS passed to the plugin so a test never
    walks the real OneDrive tree looking for S038\\P08348."""
    root = tmp_path / "911 QTDR"
    root.mkdir()
    return root


@pytest.fixture
def run_split(mod, tmp_path, qtdr):
    def _run(active_rows, complete_rows, pricing_rows, exporter=None, with_inv=True,
             qtdr_root=None):
        fdir = tmp_path / "forecast"
        fdir.mkdir(exist_ok=True)
        _forecast_workbook(fdir / "Working Forecast List.xlsx",
                           active_rows, complete_rows, with_inv=with_inv)
        src = tmp_path / "SSPO PRICING.xlsx"
        _pricing_workbook(src, pricing_rows)
        out = tmp_path / "out"
        exporter = exporter if exporter is not None else FakeExporter()
        logs = []
        result = mod.split_workbook(
            src, out,
            {"forecast_dir": str(fdir),
             "qtdr_root": str(qtdr if qtdr_root is None else qtdr_root)},
            logs.append,
            date_range=(date(2026, 9, 1), date(2026, 9, 7)),
            pdf_exporter=exporter)
        return result, out, exporter, logs
    return _run


ROW = ("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), "55501")


def _supplement(out: Path, batch, nest, mod):
    wb = load_workbook(out / f"{batch} {nest} Invoicing Docs"
                       / f"{batch} {nest} Pricing Back Up.xlsx")
    return wb[mod.INV_SHEET]


# ---------------------------------------------------------------------------------
# Forecast lookup
# ---------------------------------------------------------------------------------
def test_lookup_carries_invoice_and_ship_date_from_both_sheets(mod, tmp_path):
    p = tmp_path / "wf.xlsx"
    _forecast_workbook(
        p,
        active_rows=[("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), "55501")],
        complete_rows=[("1000129724", 11, "V094", "503891", datetime(2026, 8, 20), "55420"),
                       ("1000129724", 14, "S038", "P08348", datetime(2025, 1, 1), "OLD")])
    m = mod._read_po_map(p, lambda *_: None, None)
    # v2.5.0: every line is kept, active sheet first - the picker chooses.
    assert m[("S038", "P08348")] == [
        mod.ForecastRow("1000129724", 14, "55501", datetime(2026, 9, 3)),
        mod.ForecastRow("1000129724", 14, "OLD", datetime(2025, 1, 1))]
    assert m[("V094", "503891")][0].invoice == "55420"
    assert m[("V094", "503891")][0].ship_date == datetime(2026, 8, 20)


def test_lookup_without_the_column_warns_once_and_leaves_blank(mod, tmp_path):
    p = tmp_path / "wf.xlsx"
    _forecast_workbook(
        p, [("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), None)], [],
        with_inv=False)
    logs = []
    m = mod._read_po_map(p, logs.append, None)
    row = m[("S038", "P08348")][0]
    assert row.invoice == "" and row.po == "1000129724"
    assert sum(mod.INV_HEADER in l for l in logs) == 2    # one warning per sheet


# ---------------------------------------------------------------------------------
# Partial shipments (v2.5.0, A.T. 2026-09-25): one forecast line per shipment.
# The first line used to win, so later shipments got the FIRST invoice number.
# ---------------------------------------------------------------------------------
RANGE = (date(2026, 9, 1), date(2026, 9, 7))       # run_split's close-out range
FIRST = ("1000129724", 14, "S038", "P08348", datetime(2026, 8, 21), "55400")
SECOND = ("1000129724", 14, "S038", "P08348", datetime(2026, 9, 4), "55501")


def test_partial_shipment_takes_the_line_shipping_in_range(mod, run_split):
    result, out, exporter, _ = run_split(
        active_rows=[FIRST, SECOND], complete_rows=[],
        pricing_rows=[("S038", "P08348", 26308, 10)])
    ws = _supplement(out, "S038", "P08348", mod)
    assert ws["G2"].value == "55501"                      # not the first line's 55400
    assert ws["G3"].value == datetime(2026, 9, 4)
    assert [c[1].name for c in exporter.calls] == ["ASA Invoice No. 55501 Supplement.pdf"]
    assert result.ambiguous_invoice == []


def test_late_shipment_after_the_week_is_still_found(mod, run_split):
    # Nests do ship after their Firm VPD (confirmed 2026-09-28): the closest
    # shipment AFTER the close-out week wins, and last month's never does.
    late = ("1000129724", 14, "S038", "P08348", datetime(2026, 9, 9), "55600")
    later = ("1000129724", 14, "S038", "P08348", datetime(2026, 9, 25), "55700")
    result, out, exporter, _ = run_split(
        active_rows=[FIRST, later, late], complete_rows=[],
        pricing_rows=[("S038", "P08348", 26308, 10)])
    ws = _supplement(out, "S038", "P08348", mod)
    assert ws["G2"].value == "55600" and ws["G3"].value == datetime(2026, 9, 9)
    assert result.ambiguous_invoice == []


def test_an_earlier_weeks_shipment_is_never_reused(mod, run_split):
    # This week's shipment has no Ship Date on the forecast yet. Taking the
    # earlier line would reuse its invoice number - the original bug.
    not_yet = ("1000129724", 14, "S038", "P08348", None, None)
    result, out, exporter, logs = run_split(
        active_rows=[FIRST, not_yet], complete_rows=[],
        pricing_rows=[("S038", "P08348", 26308, 10)])
    ws = _supplement(out, "S038", "P08348", mod)
    assert ws["G2"].value is None and ws["G3"].value is None     # never a guess
    assert ws["A" + str(mod.INV_DATA_START)].value == "1000129724"  # PO still filled
    assert exporter.calls == []
    assert result.ambiguous_invoice == [
        "S038 P08348 (2 shipments on the forecast and no Ship Date during or "
        "after this range)"]
    assert result.missing_invoice == []                  # listed once, not twice


def test_two_invoices_on_the_closest_date_is_a_tie(mod):
    a = mod.ForecastRow("PO", 1, "1", date(2026, 9, 2))
    b = mod.ForecastRow("PO", 1, "2", date(2026, 9, 5))   # both inside the week
    row, why = mod._pick_forecast_row([a, b], RANGE)
    assert why and row.invoice == "" and row.po == "PO"


def test_repeated_identical_lines_are_not_ambiguous(mod):
    a = mod.ForecastRow("PO", 1, "55501", datetime(2026, 9, 4))
    row, why = mod._pick_forecast_row([a, a._replace()], RANGE)
    assert why is None and row.invoice == "55501"


def test_single_line_is_used_whatever_its_ship_date(mod):
    # One forecast line = the nest's only shipment: nothing to choose between.
    a = mod.ForecastRow("PO", 1, "55501", datetime(2026, 12, 1))
    assert mod._pick_forecast_row([a], RANGE) == (a, None)


def test_typed_ship_date_text_is_understood(mod):
    a = mod.ForecastRow("PO", 1, "1", "8/21/2026")
    b = mod.ForecastRow("PO", 1, "2", "09/04/2026")
    row, why = mod._pick_forecast_row([a, b], RANGE)
    assert why is None and row.invoice == "2"


# ---------------------------------------------------------------------------------
# Supplement + PDF
# ---------------------------------------------------------------------------------
def test_supplement_gets_invoice_and_ship_date_and_a_pdf(mod, run_split):
    result, out, exporter, _ = run_split(
        active_rows=[("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), "55501")],
        complete_rows=[],
        pricing_rows=[("S038", "P08348", 26308, 1234.5), ("S038", "P08348", 26309, 10)])
    ws = _supplement(out, "S038", "P08348", mod)
    assert ws["F2"].value == "Invoice #" and ws["G2"].value == "55501"
    assert ws["F3"].value == "Invoice Date:" and ws["G3"].value == datetime(2026, 9, 3)
    assert ws["G3"].number_format == "mm-dd-yy"

    docs = out / "S038 P08348 Invoicing Docs"
    assert exporter.calls == [(docs / "S038 P08348 Pricing Back Up.xlsx",
                               docs / "ASA Invoice No. 55501 Supplement.pdf")]
    assert (docs / "ASA Invoice No. 55501 Supplement.pdf").exists()
    assert result.pdfs == ["S038 P08348 Invoicing Docs\\ASA Invoice No. 55501 Supplement.pdf"]
    assert result.missing_invoice == [] and result.missing_po == []
    assert result.pdf_error is None and exporter.closed


def test_nest_without_invoice_number_gets_no_pdf_and_is_named(mod, run_split):
    result, out, exporter, logs = run_split(
        active_rows=[("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), None),
                     ("1000129724", 15, "S038", "P08356", datetime(2026, 9, 3), "55502")],
        complete_rows=[],
        pricing_rows=[("S038", "P08348", 1, 5), ("S038", "P08356", 2, 6),
                      ("V999", "504999", 3, 7)])      # V999: not on the forecast
    blank = _supplement(out, "S038", "P08348", mod)
    assert blank["G2"].value is None and blank["G3"].value == datetime(2026, 9, 3)
    assert blank["A" + str(mod.INV_DATA_START)].value == "1000129724"   # PO still filled

    assert [c[1].name for c in exporter.calls] == ["ASA Invoice No. 55502 Supplement.pdf"]
    assert result.missing_invoice == ["S038 P08348"]
    assert result.missing_po == ["V999 504999"]         # no forecast row -> not "missing invoice"
    assert any("P08348 has no PS/Inv" in l for l in logs)
    # Every workbook is still written regardless.
    assert len(result.written) == 3


def test_excel_unavailable_still_writes_workbooks(mod, run_split):
    exporter = FakeExporter(fail=True, error="Excel automation (pywin32) is not available")
    result, out, exporter, _ = run_split(
        active_rows=[("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), "55501")],
        complete_rows=[], pricing_rows=[("S038", "P08348", 1, 5)], exporter=exporter)
    assert result.written and result.pdfs == []
    assert result.pdf_error == "Excel automation (pywin32) is not available"
    assert _supplement(out, "S038", "P08348", mod)["G2"].value == "55501"


def test_logo_stays_above_the_header_band(mod, run_split):
    """2026-09-17: the printed PDF had the logo box overlapping the blue header
    band. The six title rows are pinned and the picture sized inside them."""
    _, out, _, _ = run_split(
        active_rows=[("1000129724", 14, "S038", "P08348", datetime(2026, 9, 3), "55501")],
        complete_rows=[], pricing_rows=[("S038", "P08348", 1, 5)])
    ws = _supplement(out, "S038", "P08348", mod)
    title_pt = sum(ws.row_dimensions[r].height for r in range(1, mod.INV_HEADER_ROW))
    assert title_pt == 6 * mod.TITLE_ROW_HEIGHT_PT
    assert mod.LOGO_PRINT_SIZE[1] <= title_pt * 96 / 72 - mod.LOGO_SEAM_PX
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.fitToWidth == 1
    # A reloaded image reports its natural pixel size; the placed size is the
    # anchor extent, in EMU (9525 per px).
    anchor = ws._images[0].anchor
    assert (anchor.ext.width, anchor.ext.height) == tuple(px * 9525 for px in mod.LOGO_PRINT_SIZE)
    # Nudged 1 pt right and 1 pt down from A1 (Anthony's pick, 2026-09-17).
    assert (anchor._from.col, anchor._from.row) == (0, 0)
    assert (anchor._from.colOff, anchor._from.rowOff) == (12700, 12700)


# ---------------------------------------------------------------------------------
# Pricing calcs (v2.4.0)
# ---------------------------------------------------------------------------------
def _shape_nest(qtdr, batch, nest, folder="Linear Inch Calcs"):
    d = qtdr / batch / nest / folder
    d.mkdir(parents=True)
    (d / "H4533328-22.xlsm").write_bytes(b"calc")
    (d / "H4533328-23.xlsm").write_bytes(b"calc")
    (d / "H4533328-22.NC").write_bytes(b"nc")
    (d / f"{batch} {nest} NC Baked Beans.xlsx").write_bytes(b"beans")
    (d / "~$H4533328-22.xlsm").write_bytes(b"lock")          # Excel lock: skipped
    (d / "DSTVs").mkdir()
    (d / "DSTVs" / "part.nc1").write_bytes(b"dstv")
    # Siblings that must NOT be mistaken for the calc folder.
    (qtdr / batch / nest / "PRODUCTION PAPERWORK").mkdir()
    (qtdr / batch / nest / "PRODUCTION PAPERWORK" / "scribe.docx").write_bytes(b"x")
    return d


def test_shape_nest_calc_folder_is_zipped_whatever_its_name(mod, run_split, qtdr):
    import zipfile
    _shape_nest(qtdr, "S038", "P08348", folder="PRICING")     # one of the odd spellings
    result, out, _, logs = run_split([ROW], [], [("S038", "P08348", 1, 5)])
    z = out / "S038 P08348 Invoicing Docs" / "S038 P08348 Linear Inch Calcs.zip"
    assert z.exists()
    names = sorted(zipfile.ZipFile(z).namelist())
    assert names == ["DSTVs/part.nc1", "H4533328-22.NC", "H4533328-22.xlsm",
                     "H4533328-23.xlsm", "S038 P08348 NC Baked Beans.xlsx"]
    assert result.calcs == ["S038 P08348 Invoicing Docs\\S038 P08348 Linear Inch Calcs.zip"]
    assert result.missing_calcs == [] and result.calc_error is None
    assert any("from 'PRICING'" in l for l in logs)


def test_plate_nest_linear_inch_workbook_is_copied(mod, run_split, qtdr):
    nest = qtdr / "L019" / "5CDBBC"
    nest.mkdir(parents=True)
    (nest / "5CDBBC KINETIC LINEAR INCH CALC.xlsx").write_bytes(b"plate")
    (nest / "5CDBBC ASA Calc and Datasheet - 6.5.26 AT Mod.xlsx").write_bytes(b"no")
    (nest / "~$5CDBBC KINETIC LINEAR INCH CALC.xlsx").write_bytes(b"lock")
    (nest / "Machine Files").mkdir()
    (nest / "Machine Files" / "a.nc").write_bytes(b"nc")       # no calc sheets: ignored
    row = ("1000129724", 3, "L019", "5CDBBC", datetime(2026, 9, 3), "55510")
    result, out, _, _ = run_split([row], [], [("L019", "5CDBBC", 1, 5)])
    docs = out / "L019 5CDBBC Invoicing Docs"
    assert (docs / "5CDBBC KINETIC LINEAR INCH CALC.xlsx").read_bytes() == b"plate"
    assert not (docs / "5CDBBC ASA Calc and Datasheet - 6.5.26 AT Mod.xlsx").exists()
    assert not (docs / "L019 5CDBBC Linear Inch Calcs.zip").exists()
    assert result.calcs == ["L019 5CDBBC Invoicing Docs\\5CDBBC KINETIC LINEAR INCH CALC.xlsx"]
    assert result.missing_calcs == []


def test_nest_without_calcs_is_flagged_and_run_carries_on(mod, run_split, qtdr):
    (qtdr / "S038" / "P08348" / "PRODUCTION PAPERWORK").mkdir(parents=True)  # nest, no calcs
    # V999 504999: no nest folder at all
    rows = [ROW, ("1000129724", 9, "V999", "504999", datetime(2026, 9, 3), "55520")]
    result, out, _, _ = run_split(rows, [], [("S038", "P08348", 1, 5), ("V999", "504999", 2, 6)])
    assert len(result.written) == 2 and len(result.pdfs) == 2      # everything else done
    assert result.calcs == []
    assert result.missing_calcs == [
        "S038 P08348 (no calc folder or LINEAR INCH CALC workbook in the nest folder)",
        "V999 504999 (no V999\\504999 folder under 911 QTDR)"]


def test_missing_qtdr_root_skips_calcs_with_one_warning(mod, run_split, tmp_path):
    result, _, _, logs = run_split([ROW], [], [("S038", "P08348", 1, 5)],
                                   qtdr_root=tmp_path / "nowhere")
    assert result.written and result.pdfs
    assert "911 QTDR folder was not found" in result.calc_error
    assert result.missing_calcs == [] and result.calcs == []
    assert sum("no pricing calcs will be collected" in l for l in logs) == 1


def test_calc_folder_is_picked_by_contents_not_name(mod, tmp_path):
    nest = tmp_path / "S001" / "503001"
    (nest / "CAD-AND-SHOP-PRINTS").mkdir(parents=True)
    (nest / "CAD-AND-SHOP-PRINTS" / "print.pdf").write_bytes(b"x")
    (nest / "Linear Inch Calcs").mkdir()
    (nest / "Linear Inch Calcs" / "readme.txt").write_bytes(b"x")   # right name, no calcs
    (nest / "CALCULATIONS").mkdir()
    (nest / "CALCULATIONS" / "H1.xlsm").write_bytes(b"x")
    assert mod._find_shape_calc_folder(nest) == nest / "CALCULATIONS"
    assert mod._find_shape_calc_folder(nest / "CAD-AND-SHOP-PRINTS") is None


def test_pdf_name_is_invoicings_own_and_filename_safe(mod):
    assert mod._supplement_pdf_name(" 55501 ") == "ASA Invoice No. 55501 Supplement.pdf"
    assert "/" not in mod._supplement_pdf_name("PS/55501")


def test_real_exporter_reports_missing_excel_without_raising(mod, monkeypatch, tmp_path):
    """The COM path degrades to a recorded error, never an exception, when
    pywin32 can't be imported - the workbooks must still be written."""
    import builtins
    real_import = builtins.__import__

    def no_win32(name, *a, **k):
        if name in ("pythoncom", "win32com.client", "win32com"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_win32)
    logs = []
    ex = mod._SupplementPdfExporter(logs.append)
    assert ex.export(tmp_path / "a.xlsx", tmp_path / "a.pdf") is False
    assert ex.export(tmp_path / "b.xlsx", tmp_path / "b.pdf") is False
    assert "pywin32" in ex.error
    assert sum("no supplement PDFs" in l for l in logs) == 1      # warned once
    ex.close()


# ── Workorder Close Outs: the columns are chosen BY NAME ────────────────────
# v2.4.1 (invoicing, 2026-09-22). The sheet used to be "every column from A
# through the one headed Machine" - a positional range wearing a header name.
# That produced the right 20 columns only while the input was a sheet already
# trimmed to them. Since v2.2.0 the input is a copy of the WHOLE pricing
# master, where Machine is column 76 and the wanted columns are scattered, so
# the close-out sheet came out with all 76 columns and the master's #DIV/0!
# cells in it. The positions below are the real ones from her 9-18 sheet.

_REAL_POSITIONS = {  # header -> its column in the real pricing master
    "Program": 1, "Batch": 2, "Work Order": 3, "DYPN": 4, "Material": 7,
    "DYPN QTY": 10, "Nest Pkg Nbr": 11, "SCOPE OF WORK ": 33, "PO": 38,
    "Line": 39, "SubGroup": 40, "Division": 41, "Scheduling Group": 42,
    "Firm VPD": 45, "Notes": 46, "ASA SALES REP": 71, "QUOTE DATE": 72,
    "Shape_Plate": 74, "MATERIAL_TYPE": 75, "Machine": 76,
    "Total Price per WO": 95,        # column CQ, well past Machine
}


def _master(drop=None):
    """A pricing master shaped like the real one: 76 columns, the wanted ones
    scattered, junk and a formula error in between."""
    wb = Workbook()
    ws = wb.active
    for j in range(1, 101):
        ws.cell(row=1, column=j, value=f"Filler {j}")
    for name, col in _REAL_POSITIONS.items():
        if name != drop:
            ws.cell(row=1, column=col, value=name)
    for r in (2, 3):
        for j in range(1, 101):
            ws.cell(row=r, column=j, value=f"v{r}c{j}")
        ws.cell(row=r, column=42, value="Open")          # Scheduling Group
        ws.cell(row=r, column=65, value="#DIV/0!")       # junk the sheet must not carry
    return ws


def _hmap(ws):
    return {str(c.value).strip().upper(): c.column for c in ws[1] if c.value}


def _run_closeouts(mod, ws, tmp_path, log=None):
    name = mod._write_closeouts(
        ws, 1, _hmap(ws), [tuple(r) for r in ws.iter_rows(min_row=2)],
        tmp_path, date(2026, 9, 18), log or (lambda *_: None))
    return load_workbook(tmp_path / name).active, name


def test_close_outs_take_only_the_named_columns_from_a_full_master(mod, tmp_path):
    ws, name = _run_closeouts(mod, _master(), tmp_path)
    # the header text is copied from the source cell, so it carries the
    # master's own casing - the list entries are lookup keys, not display text
    headers = [str(c.value).strip().upper() for c in ws[1] if c.value is not None]
    assert headers == [h.strip().upper() for h, _ in mod.CLOSEOUT_COLUMNS]
    assert ws.max_column == 21, "the whole master was copied again"
    assert not any(isinstance(c.value, str) and c.value.startswith("#")
                   for row in ws.iter_rows() for c in row)
    assert name == "D911 Workorder Close Outs 9-18-2026.xlsx"


def test_close_outs_pull_each_column_from_its_real_position(mod, tmp_path):
    ws, _ = _run_closeouts(mod, _master(), tmp_path)
    # DYPN QTY lives at master column 10, Machine at 76 - the values must follow
    out = {str(ws.cell(1, j).value).strip().upper(): ws.cell(2, j).value
           for j in range(1, ws.max_column + 1)}
    assert out["DYPN QTY"] == "v2c10"
    assert out["SCOPE OF WORK"] == "v2c33"
    assert out["MACHINE"] == "v2c76"
    assert out["PROGRAM"] == "v2c1"
    # invoicing's 2026-09-22 ask: master column CQ, as close-out column U
    assert out["TOTAL PRICE PER WO"] == "v2c95"


def test_total_price_per_wo_is_column_U(mod, tmp_path):
    """Invoicing asked for master column CQ at close-out column U (the 21st)."""
    from openpyxl.utils import get_column_letter
    ws, _ = _run_closeouts(mod, _master(), tmp_path)
    j = next(j for j in range(1, ws.max_column + 1)
             if str(ws.cell(1, j).value).strip().upper() == "TOTAL PRICE PER WO")
    assert get_column_letter(j) == "U"
    assert ws.cell(2, j).value == "v2c95"


def test_close_outs_force_scheduling_group_to_closed(mod, tmp_path):
    ws, _ = _run_closeouts(mod, _master(), tmp_path)
    col = next(j for j in range(1, ws.max_column + 1)
               if str(ws.cell(1, j).value).strip().upper() == "SCHEDULING GROUP")
    assert [ws.cell(r, col).value for r in (2, 3)] == ["Closed", "Closed"]


def test_a_missing_column_warns_and_blanks_it_without_shifting_the_rest(mod, tmp_path):
    logged = []
    ws, _ = _run_closeouts(mod, _master(drop="Notes"), tmp_path, logged.append)
    headers = [str(c.value).strip().upper() for c in ws[1] if c.value is not None]
    assert headers == [h.strip().upper() for h, _ in mod.CLOSEOUT_COLUMNS]  # still 21, in order
    col = headers.index("NOTES") + 1
    assert ws.cell(2, col).value is None
    assert any("Notes" in ln for ln in logged)
    # the column after it is still the right one, not shifted left
    assert str(ws.cell(1, col + 1).value).strip().upper() == "ASA SALES REP"
