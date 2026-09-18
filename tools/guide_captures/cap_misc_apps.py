"""User Guide screenshots: Customer DXF Analysis + six simpler apps.

Dev tool, run from the repo root, ONE app per process (fresh sandbox each run):

    PYTHONUTF8=1 python -u tools/guide_captures/cap_misc_apps.py --app customer_dxf
    ... --app 902 | batch_auditor | qr | sheet_metal | qa_gemba | game

Uses the camera library (tools/capture_guide_screens.py). Everything modal is
driven by a recurring QTimer "step machine" (probe()'s pattern): a modal
dialog's nested event loop keeps dispatching timers, so each step's predicate
polls for the next window/prompt and its action clicks/fills, even while an
earlier step's action is still blocked inside dlg.exec(). A 120 s hard
watchdog (plain threading.Timer) ends any stuck run with os._exit(1).

All data in the pictures is fake: DXFs from tools/make_demo_dxfs.py, invented
batch/nest/part numbers, and a synthetic QA rework log.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import capture_guide_screens as cam  # noqa: E402  (sandboxes BEFORE Qt import)

# Fixture root: session scratch space, NEVER shown inside any picture.
FX_ROOT = Path(os.environ.get("GUIDE_FX_ROOT")
               or Path(os.environ.get("TEMP", ".")) / "techdeck_guide_fx")

STEP_TIMEOUT_S = 30       # per-step patience
WATCHDOG_S = 120          # whole-process hard cap


def hard_exit(code, msg):
    print(f"[cap] {msg}", flush=True)
    if code != 0:
        import faulthandler
        faulthandler.dump_traceback()   # where every thread is stuck
    sys.stdout.flush()
    os._exit(code)


# ---------------------------------------------------------------------------
# Step machine (QTimer-driven; safe around nested modal event loops)
# ---------------------------------------------------------------------------

_ACTIVE_STEPS = None   # keeps the machine (and its QTimer) alive past the
                       # flow function's return - Qt only borrows the ref.


class Steps:
    def __init__(self, app, window):
        from PySide6.QtCore import QTimer

        self.app = app
        self.window = window
        self.steps = []            # (name, ready() -> payload|None, action(payload))
        self.idx = 0
        self._entered_at = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    def add(self, name, ready, action):
        self.steps.append((name, ready, action))

    def start(self):
        global _ACTIVE_STEPS
        _ACTIVE_STEPS = self
        self._entered_at = time.time()
        self.timer.start(300)

    def _tick(self):
        if self.idx >= len(self.steps):
            return
        name, ready, action = self.steps[self.idx]
        try:
            payload = ready()
        except Exception:
            traceback.print_exc()
            hard_exit(1, f"step '{name}': ready() raised")
        if not payload:
            if time.time() - self._entered_at > STEP_TIMEOUT_S:
                print(cam.console_tail(self.window), flush=True)
                hard_exit(1, f"step '{name}': timed out waiting")
            return
        print(f"[cap] step: {name}", flush=True)
        # Advance first, then run the action from a fresh singleShot: an
        # action may block for a long time inside a modal exec(), and Qt never
        # re-enters a timer's own handler - if the action ran INSIDE this
        # tick, the machine would freeze until the modal closed. Off this
        # stack frame, the recurring timer keeps ticking in the nested loop
        # and later steps drive the modal.
        self.idx += 1
        self._entered_at = time.time()

        from PySide6.QtCore import QTimer

        def _run(name=name, action=action, payload=payload):
            try:
                action(payload)
            except Exception:
                traceback.print_exc()
                hard_exit(1, f"step '{name}': action raised")

        QTimer.singleShot(0, _run)


# ---------------------------------------------------------------------------
# Small find/drive helpers
# ---------------------------------------------------------------------------

def toplevel(cls_name=None, title_sub=None, exclude=()):
    """A visible top-level widget matched by class name and/or title."""
    from PySide6.QtWidgets import QApplication

    for w in QApplication.topLevelWidgets():
        if not w.isVisible() or w in exclude:
            continue
        if cls_name and type(w).__name__ != cls_name:
            continue
        if title_sub and title_sub.lower() not in (w.windowTitle() or "").lower():
            continue
        return w
    return None


def button(root, text):
    """A QPushButton under `root` whose text matches (& and space tolerant)."""
    from PySide6.QtWidgets import QPushButton

    want = text.replace("&", "").strip().lower()
    for b in root.findChildren(QPushButton):
        if b.text().replace("&", "").strip().lower() == want:
            return b
    return None


def button_contains(root, sub):
    from PySide6.QtWidgets import QPushButton

    sub = sub.lower()
    for b in root.findChildren(QPushButton):
        if sub in b.text().replace("&", "").strip().lower():
            return b
    return None


def click_soon(widget):
    """Click on the NEXT event-loop turn so a modal it opens can't block the
    current step frame."""
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, widget.click)


def shot(app, widget, name, settle_ms=500):
    cam.pump(app, settle_ms)
    cam.save(widget, name)


def ensure_in_kit(settings, plugin_id):
    """The run queue = profile tiles ∩ selected tiles, so an app must be in
    the sandbox profile's kit before start_app can run it."""
    tiles = settings.get_profile_tiles()
    if plugin_id not in tiles:
        settings.set_profile_tiles(tiles + [plugin_id])


# ---------------------------------------------------------------------------
# Fixtures (plain files; built BEFORE Qt boots)
# ---------------------------------------------------------------------------

def fx_dxf_demo():
    """The make_demo_dxfs set (fake customer parts). Rebuilt fresh so a prior
    captured Save/offset pass can't leave stamped files behind."""
    out = FX_ROOT / "dxf_demo"
    if out.exists():
        shutil.rmtree(out)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, "-u", str(TOOLS / "make_demo_dxfs.py"),
                    "--out", str(out), "--no-verify"],
                   check=True, cwd=str(REPO), env=env,
                   stdout=subprocess.DEVNULL)
    return out


def fx_902():
    """A fake 902 batch: PO pricing workbook + an exported-DXF folder."""
    import openpyxl

    batch = FX_ROOT / "902" / "Batch 4472"
    dxf = batch / "4472 - DXF"
    if batch.exists():
        shutil.rmtree(batch)
    dxf.mkdir(parents=True)

    parts = [("H4472810-11", 1), ("H4472810-12", 2), ("H4472815-3", 1),
             ("R4472301-7", 4), ("263500220-5001", 1), ("LTG-4472AE", 1)]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PO-4472"
    ws.append(["HULL", "ORDER#", "DYPN", "SOURCE MATERIAL", "QTY ORDERED"])
    for dypn, qty in parts:
        ws.append(["BJ", "BJA04472", dypn, "EB218004472", qty])
    wb.save(batch / "4472 PRICING.xlsx")

    for dypn, _qty in parts:
        (dxf / f"{dypn}_FLAT-PATTERN#1.dxf").write_text(
            "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", encoding="ascii")
    return dxf


def fx_batch_auditor():
    """A fake 911 batch V041: BATCH LIST + nest folders (one ticket missing)."""
    import openpyxl

    root = FX_ROOT / "auditor" / "911 QTDR"
    if root.exists():
        shutil.rmtree(root)
    batch = root / "V041"
    batch.mkdir(parents=True)

    nests = ["P4101", "P4102", "P4103", "P4104", "P4105"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BATCH"
    ws.cell(1, 1, "911 BATCH LIST")
    ws.cell(3, 1, "Nest Pkg Nbr")
    ws.cell(3, 2, "Material")
    for i, nest in enumerate(nests):
        ws.cell(4 + i, 1, nest)
        ws.cell(4 + i, 2, "EB218004101")
    wb.save(batch / "V041 BATCH LIST.xlsx")

    for i, nest in enumerate(nests):
        nd = batch / nest
        nd.mkdir()
        nwb = openpyxl.Workbook()
        nwb.active.append(["placeholder"])
        nwb.save(nd / f"911 BATCH V041 {nest}.xlsx")
        if i != len(nests) - 1:   # last nest: MOVE TICKET still missing
            (nd / f"{nest} MOVE TICKET OMIT.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    return root


def fx_qa_gemba():
    """A synthetic shared QA rework log with enough spread for every chart."""
    import datetime
    import openpyxl

    folder = FX_ROOT / "gemba"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    headers = ["BATCH (PO)", "DATE", "ITEM NUMBER (DYPN)", "SOURCE MATERIAL",
               "RECUT? (Y/N)", "MISSING MATERIAL? (Y/N)", "FAILURE MODE",
               "COMMENTS"]
    today = datetime.date.today()

    def d(days_ago):
        day = today - datetime.timedelta(days=days_ago)
        return datetime.datetime(day.year, day.month, day.day)

    modes = ["Laser - Length", "Laser - Angle", "Laser - Blowout",
             "Form - Angle", "Form - Location", "Saw - Length",
             "Grind - Surface Finish", "Scribe - Illegible", "Other"]
    mats = ["PLATE", "TUBE", "ROD", "LUG", "CLEVIS", "MISC."]
    rows = []
    # Year-to-date spread (fake batches/parts throughout).
    for i in range(26):
        rows.append([f"41{10 + i % 9}", d(15 + i * 8), f"H41{10 + i % 9}810-{11 + i}",
                     mats[i % len(mats)], "YES" if i % 5 == 0 else "NO",
                     "YES" if i % 7 == 0 else "NO", modes[i % len(modes)], ""])
    # Last business week + this week, so the short windows chart too.
    this_monday = today - datetime.timedelta(days=today.weekday())
    for j, (mode, mat) in enumerate([
            ("Laser - Length", "TUBE"), ("Laser - Angle", "TUBE"),
            ("Form - Angle", "PLATE"), ("Saw - Length", "ROD"),
            ("Grind - Surface Finish", "PLATE"), ("Laser - Blowout", "TUBE")]):
        day = this_monday - datetime.timedelta(days=7) + datetime.timedelta(days=j % 5)
        rows.append([f"413{j}", datetime.datetime(day.year, day.month, day.day),
                     f"H413{j}810-{20 + j}", mat, "NO", "NO", mode, ""])
    for k in range(4):
        rows.append([f"414{k}", d(k), f"H414{k}810-{31 + k}",
                     mats[k % len(mats)], "NO", "NO", modes[k % 4], ""])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master Rework Log"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(folder / "QA Rework Log.xlsx")
    return folder


# ---------------------------------------------------------------------------
# Per-app capture flows
# ---------------------------------------------------------------------------

def run_customer_dxf(app, window, settings):
    ensure_in_kit(settings, "customer_dxf_analysis")
    demo = fx_dxf_demo()
    batch_dir = demo / "Batch 4471 - Weldment Brackets"
    flange = demo / "Customer Sample - Round Flange.dxf"
    thickness = {
        "BRKT-4471-01 Base Plate.dxf": "0.500",
        "BRKT-4471-02 Slotted Rail.dxf": "0.250",
        "BRKT-4471-03 Tube Cap.dxf": "0.375",
        "BRKT-4471-04 Access Cover.dxf": "0.625",
        "BRKT-4471-05 Heavy Pad.dxf": "1.500",
    }

    # No flow may reach a native file dialog: the folder/file picks are
    # pre-staged by patching the SDK pickers before the app starts.
    from techdeck.core import plugin_sdk as sdk_mod
    sdk_mod.pick_directory_gui = lambda *a, **k: str(batch_dir)
    sdk_mod.pick_file_gui = lambda *a, **k: str(flange)

    state = {}
    steps = Steps(app, window)

    def find_popup():
        w = toplevel(cls_name="QMessageBox", title_sub="Customer DXF Analysis")
        return w if w and button(w, "Whole folder") else None

    def find_win():
        return toplevel(cls_name="AnalysisWindow")

    # --- Run A: whole folder, automated offsets ON -------------------------
    steps.add("start app (run A)",
              lambda: True,
              lambda _: cam.start_app(app, window, "customer_dxf_analysis"))

    def shoot_popup(box):
        box.checkBox().setChecked(True)
        shot(app, box, "customer_dxf_analysis_choose")
        state["popup_a"] = box
        click_soon(button(box, "Whole folder"))
    steps.add("entry popup", find_popup, shoot_popup)

    def thickness_ready():
        w = find_win()
        if w and w.stack.currentIndex() == 0 and len(w._thick_edits) == 5:
            return w
        return None

    def shoot_thickness(w):
        state["win_a"] = w
        for path, edit in w._thick_edits.items():
            edit.setText(thickness[Path(path).name])
        shot(app, w, "customer_dxf_analysis_thickness")
        click_soon(w.btn_thick_continue)
    steps.add("thickness page", thickness_ready, shoot_thickness)

    def viewer_ready():
        w = state.get("win_a")
        if (w and w.stack.currentIndex() == 1
                and "Offsets applied" in w.lbl_offsets.text()):
            return w
        return None

    def shoot_viewer(w):
        w.resize(1680, 900)   # room for the full toolbar verdict text
        cam.pump(app, 400)
        w.btn_fit.click()
        shot(app, w, "customer_dxf_analysis_viewer", settle_ms=1200)
        w.close()
        cam.pump(app, 400)
        state["run_a_done"] = True
    steps.add("viewer verdict", viewer_ready, shoot_viewer)

    # --- Run B: single file (default DXF), offsets OFF -> Adjust Dimensions
    def start_b(_):
        settings.set_plugin_setting("customer_dxf_analysis", "default_dxf",
                                    str(flange))
        cam.start_app(app, window, "customer_dxf_analysis")
    steps.add("start app (run B)",
              lambda: (state.get("run_a_done")
                       and not window.home_page._run.session.is_running),
              start_b)

    def popup_b_ready():
        w = find_popup()
        return w if w and w is not state.get("popup_a") else None

    def drive_popup_b(box):
        box.checkBox().setChecked(False)
        click_soon(button(box, "Single file"))
    steps.add("entry popup (run B)", popup_b_ready, drive_popup_b)

    def viewer_b_ready():
        w = find_win()
        if (w and w is not state.get("win_a") and w.stack.currentIndex() == 1
                and "No offsets" in w.lbl_offsets.text()):
            return w
        return None

    def open_adjust(w):
        state["win_b"] = w
        cam.pump(app, 600)
        click_soon(w.btn_adjust)
    steps.add("viewer (run B)", viewer_b_ready, open_adjust)

    def shoot_adjust(dlg):
        dlg.ed_thickness.setText("0.250")
        shot(app, dlg, "customer_dxf_analysis_adjust")
        dlg.reject()
        cam.pump(app, 300)
        state["win_b"].close()
        hard_exit(0, "customer_dxf done")
    steps.add("adjust dialog",
              lambda: toplevel(cls_name="AdjustDimensionsDialog"),
              shoot_adjust)

    steps.start()


def run_902(app, window, settings):
    ensure_in_kit(settings, "902_dxf_prep")
    dxf_folder = fx_902()

    # The first prompt is a native folder dialog - answer it before it opens.
    window.console.request_directory = lambda *a, **k: str(dxf_folder)

    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "902_dxf_prep"))

    def shoot_picker(dlg):
        dlg.resize(680, dlg.height())   # untruncate the step labels
        shot(app, dlg, "902_dxf_prep_picker", settle_ms=600)
        click_soon(button(dlg, "Cancel"))

    steps.add("process picker",
              lambda: toplevel(cls_name="SelectionDialog", title_sub="902 DXF Prep"),
              shoot_picker)
    steps.add("run ends",
              lambda: not window.home_page._run.session.is_running,
              lambda _: hard_exit(0, "902 done"))
    steps.start()


def run_batch_auditor(app, window, settings):
    ensure_in_kit(settings, "batch_auditor")
    root = fx_batch_auditor()
    settings.set_plugin_setting("batch_auditor", "qtdr_911_root", str(root))

    con = window.console
    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "batch_auditor"))

    def prompt_ready(contains):
        def check():
            if con.waiting_for_input:
                prompt = getattr(con, "input_prompt", "") or ""
                if contains in prompt.lower():
                    return True
            return None
        return check

    def shoot_prompt(_):
        shot(app, con, "batch_auditor_prompt", settle_ms=600)
        cam.answer_console(app, window, "911")
    steps.add("line prompt", prompt_ready("which line"), shoot_prompt)

    steps.add("batch prompt", prompt_ready("batch number"),
              lambda _: cam.answer_console(app, window, "V041"))

    def audit_done():
        text = con.output.toPlainText()
        return ("need attention" in text or "Batch looks ready." in text) or None

    def shoot_dashboard(_):
        shot(app, con, "batch_auditor_dashboard", settle_ms=1200)
        hard_exit(0, "batch_auditor done")
    steps.add("dashboard", audit_done, shoot_dashboard)
    steps.start()


def run_qr(app, window, settings):
    ensure_in_kit(settings, "qr_code_generator")
    out_dir = Path(r"C:\Users\Public\Documents\QR Codes")  # neutral, no username
    fx = FX_ROOT / "qr"
    if fx.exists():
        shutil.rmtree(fx)   # a stale library file would duplicate the entry
    fx.mkdir(parents=True)

    state = {}
    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "qr_code_generator"))

    def setup(win):
        from PySide6.QtWidgets import QTabWidget

        state["win"] = win
        win.data_file = fx / "entrypoints.json"   # never touch the real library
        win.entrypoints = []
        win.populate_library_table()
        win.resize(1000, 750)
        state["tabs"] = win.findChildren(QTabWidget)[0]
        state["tabs"].setCurrentIndex(1)
        cam.pump(app, 300)
        win.url_edit.setText("https://example.com/work-instructions")
        win.url_name_edit.setText("Work Instructions")
        win.output_folder_edit.setText(str(out_dir))
        win.filename_edit.setText("work_instructions_qr")
        for edit in (win.url_edit, win.url_name_edit,
                     win.output_folder_edit, win.filename_edit):
            edit.setCursorPosition(0)   # show the text from its start
        cam.pump(app, 200)
        click_soon(win.generate_btn)
    steps.add("window", lambda: toplevel(cls_name="QRGeneratorWindow"), setup)

    def dismiss_success(box):
        for b in box.buttons():
            click_soon(b)
            break
    steps.add("success popup", lambda: toplevel(cls_name="QMessageBox"),
              dismiss_success)

    def shoot_generator(_):
        shot(app, state["win"], "qr_code_generator_generate", settle_ms=700)
        state["tabs"].setCurrentIndex(0)
        state["gen_shot"] = True   # gates the next step - never `lambda: True`
    steps.add("generator shot",
              lambda: not toplevel(cls_name="QMessageBox"), shoot_generator)

    def shoot_library(_):
        shot(app, state["win"], "qr_code_generator_library", settle_ms=500)
        try:
            shutil.rmtree(out_dir)   # leave no trace outside the sandbox
        except OSError:
            pass
        hard_exit(0, "qr done")
    steps.add("library shot", lambda: state.get("gen_shot"), shoot_library)
    steps.start()


def run_sheet_metal(app, window, settings):
    ensure_in_kit(settings, "sheet_metal_calculators")
    state = {}
    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "sheet_metal_calculators"))

    def flat_length(win):
        state["win"] = win
        win._list.setCurrentRow(0)   # Flat Length Calculator
        cam.pump(app, 300)
        _spec, thick = win._fields["thickness"]
        thick.setText("0.250")
        _spec, dim = win._fields["dimValue"]
        dim.setText("6")
        _spec, angle = win._fields["angle"]
        angle.setText("360")
        cam.pump(app, 200)
        button(win, "Calculate").click()
        shot(app, win, "sheet_metal_calculators_flat_length", settle_ms=500)
        state["flat_shot"] = True   # gates the next step
    steps.add("window", lambda: toplevel(cls_name="SheetMetalCalculators"),
              flat_length)

    def weight(_):
        from PySide6.QtCore import QCoreApplication, QEvent

        win = state["win"]
        win._list.setCurrentRow(2)   # Material Weight Calculator
        # Purge the old form's deleteLater'd widgets: processEvents never runs
        # DeferredDelete, so without this they still paint (ghosted labels).
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        cam.pump(app, 300)
        _spec, thick = win._fields["thickness"]
        thick.setText("0.190")
        cam.pump(app, 200)
        button(win, "Calculate").click()
        shot(app, win, "sheet_metal_calculators_weight", settle_ms=500)
        hard_exit(0, "sheet_metal done")
    steps.add("weight calc", lambda: state.get("flat_shot"), weight)
    steps.start()


def run_mietrak(app, window, settings):
    ensure_in_kit(settings, "mietrak_tools")
    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "mietrak_tools"))

    def hardware_code(win):
        win._list.setCurrentRow(0)   # Hardware Code Generator
        cam.pump(app, 300)
        tool = win._active

        def pick(combo, label):
            combo.setCurrentIndex(combo.findText(label))
        pick(tool.material, "ZINC PLATED, GRADE 5")
        pick(tool.hardware, "CAP SCREW, HEX HEAD")
        pick(tool.thread_size, "1/2-13")
        pick(tool.length, "2")
        cam.pump(app, 300)
        shot(app, win, "mietrak_tools_hardware_code", settle_ms=500)
        hard_exit(0, "mietrak done")
    steps.add("window", lambda: toplevel(cls_name="MieTrakTools"), hardware_code)
    steps.start()


def run_qa_gemba(app, window, settings):
    ensure_in_kit(settings, "qa_gemba_analyzer")
    folder = fx_qa_gemba()
    settings.set_plugin_setting("qa_gemba_analyzer", "data_dir", str(folder))

    state = {}
    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "qa_gemba_analyzer"))

    def dashboard(win):
        state["win"] = win
        shot(app, win, "qa_gemba_analyzer_dashboard", settle_ms=1500)
        click_soon(button_contains(win, "Log Rework"))
    steps.add("dashboard",
              lambda: toplevel(cls_name="PluginWindow", title_sub="Gemba Analyzer"),
              dashboard)

    def shoot_form(dlg):
        dlg.in_batch.setText("4136")
        dlg.in_item.setText("H4136810-27")
        dlg.in_material.setCurrentText("TUBE")
        dlg.in_category.setCurrentText("Laser")
        cam.pump(app, 200)
        dlg.in_subcategory.setCurrentIndex(2)   # Length
        shot(app, dlg, "qa_gemba_analyzer_log_form")
        dlg.reject()
        hard_exit(0, "qa_gemba done")
    steps.add("log form", lambda: toplevel(cls_name="LogReworkDialog"),
              shoot_form)
    steps.start()


def run_game(app, window, settings):
    ensure_in_kit(settings, "game_asa_the_video_game")
    settings.unlock_item("game_asa_the_video_game")   # sandbox-only purchase

    steps = Steps(app, window)
    steps.add("start app", lambda: True,
              lambda _: cam.start_app(app, window, "game_asa_the_video_game"))

    def shoot(win):
        shot(app, win, "game_asa_the_video_game_start", settle_ms=2000)
        hard_exit(0, "game done")
    steps.add("game window",
              lambda: toplevel(cls_name="SteelBeamsGame"), shoot)
    steps.start()


FLOWS = {
    "customer_dxf": run_customer_dxf,
    "902": run_902,
    "batch_auditor": run_batch_auditor,
    "qr": run_qr,
    "sheet_metal": run_sheet_metal,
    "mietrak": run_mietrak,
    "qa_gemba": run_qa_gemba,
    "game": run_game,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, choices=sorted(FLOWS))
    args = ap.parse_args()

    FX_ROOT.mkdir(parents=True, exist_ok=True)
    threading.Timer(WATCHDOG_S, lambda: hard_exit(1, "WATCHDOG: 120s cap hit")
                    ).start()

    app, window, settings = cam.boot()
    FLOWS[args.app](app, window, settings)
    app.exec()
    hard_exit(0, "event loop ended")


if __name__ == "__main__":
    main()
