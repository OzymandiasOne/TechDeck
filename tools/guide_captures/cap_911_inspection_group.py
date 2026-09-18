r"""User Guide captures: 911 Inspection Dimensions (full treatment) plus the
four simple apps around it (1-2 shots each).

Run from the repo root, ONE app per process (each gets a fresh sandbox and its
own safety timer):

    PYTHONUTF8=1 python -u tools/guide_captures/cap_911_inspection_group.py inspection
    PYTHONUTF8=1 python -u tools/guide_captures/cap_911_inspection_group.py bakedbeans
    PYTHONUTF8=1 python -u tools/guide_captures/cap_911_inspection_group.py invoicing
    PYTHONUTF8=1 python -u tools/guide_captures/cap_911_inspection_group.py award
    PYTHONUTF8=1 python -u tools/guide_captures/cap_911_inspection_group.py lst

Shots produced (docs/user_guide/images/):
  911_inspection_dimensions_select_nests.png - "Select Nests to Read" window
  911_inspection_dimensions_report.png       - the fill-in report window
  911_inspection_dimensions_console.png      - console after the run
  911_baked_beans_wild_ride_board.png        - the "Board the Ride" picker
  911_sspo_invoicing_prep_dates.png          - the close-out date range window
  911_sspo_invoicing_prep_done.png           - the end-of-run summary popup
  911_sspo_award_review_done.png             - console DONE block
  911_lst_organizer_summary.png              - console pull summary
  911_lst_organizer_attention.png            - the "attention needed" popup

All data is FAKE (practice batches under C:\Temp\TechDeck Practice - never a
real batch, person, or production path). The apps' first interaction is a
native Explorer dialog, which cannot be photographed or driven - so that one
pick is skipped by handing sdk.request_directory / sdk.pick_file_gui the
practice folder, and everything after it is the real app running. Event-driven
throughout (QTimer + generator, probe()'s pattern): a modal dialog's nested
event loop would freeze straight-line code.

The inspection run really exercises the OCR reader, kept to ONE nest with a
ONE-page fabricated PART SKETCH (three clean dimension callouts) so the read
stays seconds, not minutes.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, r"C:\Dev\TechDeck\tools")
import capture_guide_screens as cam  # noqa: E402  (sandboxes LOCALAPPDATA on import)

# ── Fake practice data ───────────────────────────────────────────────────────
FIX_ROOT = Path(r"C:\Temp\TechDeck Practice")
QTDR = FIX_ROOT / "911 QTDR"
BATCH = "V060"

SAFETY_MS = 120_000


def _reset_fixtures() -> None:
    if FIX_ROOT.exists():
        shutil.rmtree(FIX_ROOT, ignore_errors=True)
    FIX_ROOT.mkdir(parents=True, exist_ok=True)


# ── Fixture builders ─────────────────────────────────────────────────────────

def _sketch_pdf(path: Path, part: str, callouts) -> None:
    """A one-page PART SKETCH: real title-block text + the drawing as an
    embedded raster (that is what the real packets are - the reader OCRs the
    picture). `callouts` = [(text, (x, y))] drawn onto the raster."""
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1400, 800), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 56)
    for text, xy in callouts:
        draw.text(xy, text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 40
    for line, size in [("1 OF 1", 9), ("AB123456", 9), ("PART SKETCH", 14),
                       (f"PART: {part}", 10), ("REV/SEQ: A", 10),
                       ("QTY: 4", 10), ("NOUN: BRACKET", 10), ("SIZE:", 10),
                       (".50 X 4.00 X 12.50", 10), ("FAB DIM: 12.50", 10)]:
        page.insert_text((36, y), line, fontsize=size)
        y += size + 6
    # 520 x 297 pt placement keeps the 1400x800 raster's aspect ratio.
    page.insert_image(fitz.Rect(46, 250, 566, 547), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def _qf_workbook(path: Path, tab: str, part: str) -> None:
    """A minimal QF-QU-09-shaped nest workbook: the per-part tab with the part
    number in A16 and live "=..." MIN formulas beside every nominal group, so
    the writer treats the tolerances as intact."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = tab
    ws["A16"] = part
    for row in range(16, 36, 2):
        for col in ("N", "U", "AB", "AI", "AP"):
            ws[f"{col}{row}"] = f"=L{row}-0.1"
    wb.save(path)


def build_inspection_fixtures() -> Path:
    """Order folder V060 with three nests: one that gets read for real (tiny
    PART SKETCH + workbook), one with a workbook, one without (so the window
    shows its report-only label). Returns the order folder."""
    order = QTDR / BATCH
    for nest, workbook in (("503991", True), ("503992", True), ("503993", False)):
        nd = order / nest
        nd.mkdir(parents=True)
        if nest == "503991":
            _sketch_pdf(nd / f"{nest} MOVE TICKET OMIT.pdf", "BK1144-3",
                        [("12.50", (620, 90)), ("4.00", (1020, 360)),
                         ("R.25", (240, 560))])
        else:
            # never opened - only the ticked nest's packet is read
            (nd / f"{nest} MOVE TICKET OMIT.pdf").write_bytes(b"%PDF-1.4\n")
        if workbook:
            _qf_workbook(nd / f"911 BATCH {BATCH} {nest}.xlsx", "-3", "BK1144-3")
    return order


def build_invoicing_fixtures():
    """The SSPO pricing workbook + a Working Forecast List with both sheets.
    Returns (pricing_path, forecast_dir)."""
    from openpyxl import Workbook

    pricing = FIX_ROOT / "SSPO Pricing Back Up.xlsx"
    wb = Workbook()
    ws = wb.active
    headers = ["Batch", "Work Order", "DYPN", "Material", "DYPN QTY",
               "Nest Pkg Nbr", "Scheduling Group", "Firm VPD", "Machine",
               "Total price per WO"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    # Firm VPD = yesterday, inside the date dialog's default last-7-days range,
    # so the capture run flows straight through with every real row kept.
    from datetime import date, timedelta
    vpd = date.today() - timedelta(days=1)
    rows = [
        ("V060", "AB123456", "BK1144-3", "EB218099999A", 4, "503991", "Open", vpd, "NON", 1480.00),
        ("V060", "AB123457", "BK1144-7", "EB218099999A", 2, "503991", "Open", vpd, "NON", 926.50),
        ("V060", "AB123458", "BK1152-12", "EB218099998A", 6, "503992", "Open", vpd, "XX5", 2210.75),
        ("TOTALS", "", "", "", "", "", "", "", "", 4617.25),   # footer row - skipped
    ]
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v if v != "" else None)
    for r in range(2, 5):
        ws.cell(r, 8).number_format = "mm-dd-yy"
        ws.cell(r, 10).number_format = '"$"#,##0.00'
    wb.save(pricing)

    fdir = FIX_ROOT / "Forecast and Inventory Reports"
    fdir.mkdir(parents=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "911 Forecast"
    # v2.3.0+: the app also reads Ship Date + PS/Inv (the invoice number), so
    # the popup shows the clean path (invoice filled, PDF printed).
    for c, h in enumerate(["PO", "Line", "Batch /DR", "Nest", "Ship Date", "PS/Inv"], 1):
        ws.cell(1, c, h)
    for r, (po, line, batch, nest, ship, inv) in enumerate(
            [(4500123456, "SSPO", "V060", "503991", vpd, "55501"),
             (4500123456, "SSPO", "V060", "503992", vpd, "55502")], 2):
        ws.cell(r, 1, po)
        ws.cell(r, 2, line)
        ws.cell(r, 3, batch)
        ws.cell(r, 4, nest)
        ws.cell(r, 5, ship).number_format = "mm-dd-yy"
        ws.cell(r, 6, inv)
    ws2 = wb.create_sheet("Complete 911 QTDR")
    for c, h in enumerate(["PO", "Line", "Batch /DR", "Nest", "Ship Date", "PS/Inv"], 1):
        ws2.cell(1, c, h)
    wb.save(fdir / "Working Forecast List.xlsx")

    # v2.4.0: a practice 911 QTDR tree so the pricing calcs are found - one
    # shape nest (calc-sheet folder) and one plate nest (LINEAR INCH CALC book).
    qtdr = FIX_ROOT / "911 QTDR"
    shape = qtdr / "V060" / "503991" / "Linear Inch Calcs"
    shape.mkdir(parents=True)
    for name in ("BK1144-3.xlsm", "BK1144-7.xlsm", "V060 503991 NC Baked Beans.xlsx"):
        (shape / name).write_bytes(b"practice")
    plate = qtdr / "V060" / "503992"
    plate.mkdir(parents=True)
    (plate / "503992 KINETIC LINEAR INCH CALC.xlsx").write_bytes(b"practice")
    return pricing, fdir, qtdr


def _award_packet_pdf(path: Path, orders: int, pieces: int, thickness: float,
                      length: float, width: float) -> None:
    """A nest packet page 1 with the Orders/Pieces/Thickness/Length/Width
    block laid out the way the parser reads it (label block, then values)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 60
    for line in ["NEST PACKAGE", "Orders", "Pieces", "Thickness", "Length",
                 "Width", str(orders), str(pieces), f"{thickness:.3f}",
                 f"{length:.2f}", f"{width:.2f}"]:
        page.insert_text((60, y), line, fontsize=10)
        y += 16
    doc.save(str(path))
    doc.close()


def build_award_fixtures() -> Path:
    """An award package ROOT: one order folder with its CUI folder, batch list
    and NEST PACKAGES packets. Returns the ROOT."""
    from openpyxl import Workbook

    root = FIX_ROOT / "SSPO AWARD 12"
    cui = root / "V102" / "CUI- TECH DATA READ ME"
    pkg = cui / "NEST PACKAGES"
    pkg.mkdir(parents=True)

    wb = Workbook()
    ws = wb.active
    for c, h in enumerate(["Work Order", "DYPN", "Description", "Material",
                           "Nest Pkg Nbr", "PPN Quantity"], 1):
        ws.cell(1, c, h)
    rows = [
        ("AB223401", "BK1201-1", "PLATE ; STL ; 0.500 THK #96 X 240 ; SF",
         "EB218099999A", "503811", 4),
        ("AB223402", "BK1201-5", "PLATE ; STL ; 0.500 THK #96 X 240 ; SF",
         "EB218099999A", "503811", 2),
        ("AB223403", "BK1210-2", "PLATE ; STL ; 1.000 THK #90 X 360 ; SF",
         "EB218099998A", "503812", 3),
        ("AB223404", "BK1220-4", "ANGLE, 3.00 X 3.00 X 0.250 THK, STL",
         "EB218099997A", "503812", 8),
    ]
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
    wb.save(cui / "V102 BATCH LIST.xlsx")

    _award_packet_pdf(pkg / "503811 NEST PACKAGE.pdf", 2, 6, 0.500, 96, 240)
    _award_packet_pdf(pkg / "503812 NEST PACKAGE.pdf", 2, 11, 1.000, 90, 360)
    return root


def _1d_pdf(path: Path, parts) -> None:
    """A 1D cutting diagram: the Parts Id. table is all the organizer reads."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    y = 60
    for line in ["1D CUTTING PATTERN", "Parts Id."] + list(parts) + ["Total Bars"]:
        page.insert_text((60, y), line, fontsize=10)
        y += 16
    doc.save(str(path))
    doc.close()


def build_lst_fixtures():
    """Two nests under the practice 911 QTDR tree. 503991's diagram resolves
    cleanly (incl. one part borrowed from another batch); 503992's has a nest
    that exists nowhere and a part with no .lst, for the attention popup.
    Returns (pp_clean, pp_problem) - the two PRODUCTION PAPERWORK folders."""
    # clean run: own parts + one borrowed from nest 503887 (batch V061)
    nest1 = QTDR / BATCH / "503991"
    pp1 = nest1 / "PRODUCTION PAPERWORK"
    pp1.mkdir(parents=True)
    _1d_pdf(pp1 / f"{BATCH} 503991 1D.pdf",
            ["BK1144-3", "BK1144-7", "503887 / BK1152-12"])
    dstv1 = nest1 / "DSTV FILES"
    dstv1.mkdir()
    for stem in ("BK1144-3", "BK1144-7"):
        (dstv1 / f"{stem}.lst").write_text("ST\n  practice lst\nEN\n")
    foreign = QTDR / "V061" / "503887" / "DSTV FILES"
    foreign.mkdir(parents=True)
    (foreign / "BK1152-12.lst").write_text("ST\n  practice lst\nEN\n")

    # attention run: a nest found nowhere on disk + a part with no .lst
    nest2 = QTDR / BATCH / "503992"
    pp2 = nest2 / "PRODUCTION PAPERWORK"
    pp2.mkdir(parents=True)
    _1d_pdf(pp2 / f"{BATCH} 503992 1D.pdf",
            ["BK1160-1", "BK1190-2", "607777 / BK1170-3"])
    dstv2 = nest2 / "DSTV FILES"
    dstv2.mkdir()
    (dstv2 / "BK1160-1.lst").write_text("ST\n  practice lst\nEN\n")
    return pp1, pp2


# ── Event-driven state machine (probe()'s pattern) ───────────────────────────
# The flow is a generator; each `yield (condition, timeout_s, label)` suspends
# it until the QTimer tick sees the condition come true - so a modal dialog's
# nested event loop can't freeze us.

_app = None
_window = None
_settings = None
_gen = None
_cond = None
_deadline = 0.0
_label = ""


def _die(msg: str) -> None:
    print(f"CAPTURE FAILED: {msg}", flush=True)
    try:
        print("-- console tail:", flush=True)
        print(cam.console_tail(_window, 25), flush=True)
    except Exception:
        pass
    sys.stdout.flush()
    os._exit(1)


def _advance(value=None) -> None:
    global _cond, _deadline, _label
    try:
        step = _gen.send(value)
    except StopIteration:
        print("All captures done.", flush=True)
        sys.stdout.flush()
        os._exit(0)
    except Exception:
        traceback.print_exc()
        _die("script step raised")
    _cond, timeout_s, _label = step
    _deadline = time.time() + timeout_s


def _tick() -> None:
    global _cond
    if _cond is None:
        return
    try:
        result = _cond()
    except Exception:
        traceback.print_exc()
        _die(f"condition raised in step: {_label}")
        return
    if result:
        _cond = None
        _advance(result)
    elif time.time() > _deadline:
        _die(f"timed out waiting for: {_label}")


def _start(plugin_id: str) -> None:
    # cam.start_app minus the trailing pump: a pump here can get trapped in a
    # dialog's nested event loop before the generator reaches its next yield.
    _window.home_page.selected_tiles = {plugin_id}
    _window.home_page._run.run_selected_plugins()


def _find_window(type_name: str, title_contains: str = ""):
    from PySide6.QtWidgets import QApplication

    def cond():
        for w in QApplication.topLevelWidgets():
            if w is _window or not w.isVisible():
                continue
            if type(w).__name__ != type_name:
                continue
            if title_contains.lower() in (w.windowTitle() or "").lower():
                return w
        return None
    return cond


def _find_report():
    def cond():
        dlg = getattr(_window.console, "_open_report", None)
        return dlg if (dlg is not None and dlg.isVisible()) else None
    return cond


def _ticks(n: int):
    box = {"left": n}

    def cond():
        box["left"] -= 1
        return box["left"] <= 0
    return cond


def _running():
    return lambda: _window.home_page._run.session.is_running


def _not_running():
    return lambda: not _window.home_page._run.session.is_running


def _click_ok(box) -> None:
    from PySide6.QtWidgets import QMessageBox, QPushButton

    btn = box.button(QMessageBox.StandardButton.Ok)
    if btn is None:
        buttons = box.findChildren(QPushButton)
        btn = buttons[0] if buttons else None
    if btn is not None:
        btn.click()


def _console_shot(name: str):
    """Generator fragment: tall console, settle, grab, hand the name back."""
    _window.home_splitter.setSizes([220, 580])

    def then():
        cam.save(_window.console, name)
    return then


# ── Per-app flows ────────────────────────────────────────────────────────────

def flow_inspection():
    from PySide6.QtCore import Qt
    from techdeck.core import plugin_sdk as sdk

    order = build_inspection_fixtures()
    # The folder pick is a native Explorer dialog (unphotographable); skip just
    # that pick - everything after it is the real app running, OCR included.
    sdk.request_directory = (
        lambda params, title="", start_dir="", style=None: str(order))

    _start("911_inspection_dimensions")
    dlg = yield (_find_window("SelectionDialog", "911 Inspection Dimensions"),
                 40, "Select Nests to Read window")
    dlg.root.child(0).setCheckState(0, Qt.CheckState.Checked)   # 503991
    yield (_ticks(3), 10, "tick-list settle")
    cam.save(dlg, "911_inspection_dimensions_select_nests")
    dlg.run_btn.click()

    # The real read: one nest, one PART SKETCH page through the OCR ensemble,
    # then the workbook fill and the report window.
    rep = yield (_find_report(), 110, "fill-in report window")
    yield (_ticks(3), 10, "report settle")
    cam.save(rep, "911_inspection_dimensions_report")
    rep.accept()
    yield (_not_running(), 20, "run end")

    shot = _console_shot("911_inspection_dimensions_console")
    yield (_ticks(3), 10, "console relayout")
    shot()


def flow_bakedbeans():
    _start("911_baked_beans_wild_ride")
    dlg = yield (_find_window("SelectionDialog", "911 Baked Beans Wild Ride"),
                 40, "Board the Ride picker")
    dlg.resize(560, 460)      # room for the greyed row's "- coming soon" tag
    yield (_ticks(3), 10, "picker settle")
    cam.save(dlg, "911_baked_beans_wild_ride_board")
    dlg.reject()
    yield (_not_running(), 20, "ride cancelled")


def flow_invoicing():
    from techdeck.core import plugin_sdk as sdk

    pricing, fdir, qtdr = build_invoicing_fixtures()
    _settings.set_plugin_setting("911_sspo_invoicing_prep", "forecast_dir",
                                 str(fdir))
    _settings.set_plugin_setting("911_sspo_invoicing_prep", "qtdr_root",
                                 str(qtdr))
    # The file pick is a native Explorer dialog (unphotographable); skip just
    # that pick. Explorer must not really open over the capture run either.
    sdk.pick_file_gui = (
        lambda params, title="", start_dir="", name_filter="", parent=None:
        str(pricing))
    os.startfile = lambda *a, **k: None

    _start("911_sspo_invoicing_prep")
    dlg = yield (_find_window("QDialog", "Close-out date range"),
                 40, "date range window")
    yield (_ticks(3), 10, "date dialog settle")
    cam.save(dlg, "911_sspo_invoicing_prep_dates")
    dlg.accept()
    box = yield (_find_window("QMessageBox", "911 SSPO Invoicing Prep"),
                 40, "invoicing summary popup")
    yield (_ticks(3), 10, "popup settle")
    cam.save(box, "911_sspo_invoicing_prep_done")
    _click_ok(box)
    yield (_not_running(), 20, "invoicing run end")


def flow_award():
    from techdeck.core import plugin_sdk as sdk

    root = build_award_fixtures()
    sdk.request_directory = (
        lambda params, title="", start_dir="", style=None: str(root))

    _start("911_sspo_award_review")
    yield (_running(), 15, "award run start")
    # Includes the real Excel COM pivot pass, so give it room.
    yield (_not_running(), 100, "award run + Excel pivots")
    shot = _console_shot("911_sspo_award_review_done")
    yield (_ticks(3), 10, "console relayout")
    shot()


def flow_lst():
    from techdeck.core import plugin_sdk as sdk

    pp1, pp2 = build_lst_fixtures()
    picks = [str(pp1), str(pp2)]
    sdk.request_directory = (
        lambda params, title="", start_dir="", style=None: picks.pop(0))

    # Run 1: everything resolves - the console pull summary.
    _start("911_lst_organizer")
    yield (_running(), 15, "lst run 1 start")
    yield (_not_running(), 40, "lst run 1 end")
    shot = _console_shot("911_lst_organizer_summary")
    yield (_ticks(3), 10, "console relayout")
    shot()

    # Run 2: a nest that exists nowhere + a part with no .lst - the popup.
    _window.console.clear_btn.click()
    yield (_ticks(2), 10, "console cleared")
    _start("911_lst_organizer")
    box = yield (_find_window("QMessageBox", "attention needed"),
                 40, "attention popup")
    yield (_ticks(3), 10, "popup settle")
    cam.save(box, "911_lst_organizer_attention")
    _click_ok(box)
    yield (_not_running(), 20, "lst run 2 end")


FLOWS = {
    "inspection": flow_inspection,
    "bakedbeans": flow_bakedbeans,
    "invoicing": flow_invoicing,
    "award": flow_award,
    "lst": flow_lst,
}


def main() -> None:
    global _app, _window, _settings, _gen

    if len(sys.argv) != 2 or sys.argv[1] not in FLOWS:
        sys.exit(f"usage: cap_911_inspection_group.py {{{'|'.join(FLOWS)}}}")
    flow = FLOWS[sys.argv[1]]

    _reset_fixtures()
    _app, _window, _settings = cam.boot()

    # No chimes out of the real speakers during capture.
    from techdeck.core.audio_manager import get_audio_manager
    get_audio_manager().set_enabled(False)
    _settings.set_audio_settings(False, 0)

    # No random talkback / tech-tip lines under the success banner - a flavor
    # line about some unrelated file reads as a mystery in a manual picture.
    import random as _random
    _random.random = lambda: 0.99

    # The queue only runs tiles that are in the Home kit.
    _settings.set_profile_tiles([
        "911_inspection_dimensions", "911_baked_beans_wild_ride",
        "911_sspo_invoicing_prep", "911_sspo_award_review", "911_lst_organizer",
    ])

    from PySide6.QtCore import QTimer

    # Global safety: nothing (a native dialog, a hung COM call) may hang the
    # terminal - print and hard-exit instead.
    safety = QTimer()
    safety.setSingleShot(True)
    safety.timeout.connect(lambda: _die(f"global {SAFETY_MS // 1000}s safety timer"))
    safety.start(SAFETY_MS)

    ticker = QTimer()
    ticker.timeout.connect(_tick)
    ticker.start(350)

    _gen = flow()
    _advance()          # run to the first yield
    _app.exec()
    os._exit(1)         # unreachable: the generator exits the process


if __name__ == "__main__":
    main()
