"""The 922 test sandbox: a safe copy of a real batch to run 922 apps against.

    python -m tools.devkit.sandbox_922 status          # what is there right now
    python -m tools.devkit.sandbox_922 reset ready     # put Batch 900 back (set-up state)
    python -m tools.devkit.sandbox_922 reset raw       # ...or the fresh-drop state
    python -m tools.devkit.sandbox_922 launch          # run TechDeck (dev) inside the sandbox
    python -m tools.devkit.sandbox_922 build           # one-time: rebuild _Pristine from real batches

WHERE: `922 QTDR Production Packages\\Automation Test Environment` (the "sandbox").
It is laid out like a miniature 922 root, because that is what the apps need:

    Batch 900\\                      the test batch (live - the apps change it)
    922 MPL.xlsx                    copy of the real MPL, minus the PO 498 column
    1 - Completed\\Batch 413 ...     the source orders the 4 repeats are pulled from
    2 - Planning\\Batch Setup\\Quote\\EB 922 H# Quote.xlsx   (the master quote)
    _Pristine\\                      the untouched originals `reset` copies back

WHY A WHOLE MINI ROOT: several 922 apps re-find a batch by NUMBER under the 922
root, and the MPL stage / Batch Repeater write `<root>\\922 MPL.xlsx`. Launched
with `launch`, the env var `sdk.SANDBOX_922_ENV` makes the sandbox the root for
EVERY app (dev runs only), and `sdk.post_webhook` refuses to send - nothing can
reach a real batch, the real MPL, or the live Teams board.

THE BATCH (number 900 - no real batch will reach it for years): nine real orders
chosen to cover the cases that have bitten us - see ORDERS below. The
Documentation workbooks are real copies trimmed to those nine orders THROUGH
EXCEL (formatting, the EB header art and the organizer's spill formulas survive;
openpyxl would drop them), batch number set to 900, and the organizer's Manual
Adjustments spread the nine orders 3 / 3 / 3 over PALLET 1-3. Old red pallet and
DIFFICULT stamps are stripped from every packet so a stamper run starts clean.

Two states:
  raw    Documentation + a `Work Packets` folder of unstamped packets - what the
         office has before 922 Setup's Batch Folder Setup stage.
  ready  the nine order folders with their CAD, prints and .lst files (as the
         real batch had them after the Repeater and modelling) + REPEAT BATCHES.

The data is real (CUI / NNPI - the READ ME marking is kept in the Documentation
folder). It stays on the same SharePoint site; never copy it anywhere else.
Dev-only (tools/devkit never ships).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from techdeck.core import plugin_sdk as sdk

BATCH = "900"
SANDBOX_NAME = "Automation Test Environment"
PRISTINE = "_Pristine"
REPO = Path(__file__).resolve().parents[2]

# (source batch, order folder, what it is there to exercise)
ORDERS = [
    ("498", "BK597871-R6513461-H20", "plain new order, no CAD"),
    ("498", "BL416594-R7212587-H9", "packet named '<order> NOFORN.pdf'"),
    ("498", "BM330293-R7923661-H19", "repeat (src 413); forming 'PLT F' drawing; .lst"),
    ("498", "X4652239-H7918262-H2", "repeat (src 444); two forming drawings; .lst"),
    ("498", "FK372138-H5223261-H77", "repeat (src 427); '<order> PRINT.pdf' beside the packet"),
    ("498", "X7453481-H7921467-H48", "repeat (src 476); four .lst files"),
    ("498", "X7442975-H6431566-H6", "same PPN as X6505358: two orders, one part"),
    ("498", "X6505358-H6431566-H6", "same PPN as X7442975"),
    ("496", "BM356522-R8672862-H36G", "DIFFICULT drawing; repeat (src 496)"),
]
# Where the Batch Repeater pulls each repeat from: (source batch, folder, copy-from
# relative to the real root). 498's REPEAT BATCHES holds faithful copies.
REPEAT_SOURCES = [
    ("413", "BL342666-R7923661-H19", "Batch 498/REPEAT BATCHES"),
    ("444", "X3645116-H7918262-H2", "Batch 498/REPEAT BATCHES"),
    ("427", "X8379102-H5223261-H77", "Batch 498/REPEAT BATCHES"),
    ("476", "X6483199-H7921467-H48", "Batch 498/REPEAT BATCHES"),
    ("496", "BM356522-R8672862-H36G", "Batch 496"),
]
MASTER_QUOTE = Path("2 - Planning") / "Batch Setup" / "Quote" / "EB 922 H# Quote.xlsx"
MPL_DROP_FROM = 498        # sandbox MPL keeps PO columns < this (900 follows 497)
PALLET_SPLIT = [1, 1, 1, 2, 2, 2, 3, 3, 3]   # Manual Adjustments, rows 45+
LIVE_ITEMS = ["Batch " + BATCH, "922 MPL.xlsx", "1 - Completed", "2 - Planning"]

_XL_UP = -4162


# ── paths ──────────────────────────────────────────────────────────────────

def real_root() -> Path:
    """The REAL 922 root, ignoring any active sandbox env var."""
    root = sdk._resolve_root("", "922 QTDR Production Packages")
    if root is None or not sdk.is_dir(root):
        sys.exit("Couldn't find '922 QTDR Production Packages' - is OneDrive synced?")
    return root


def sandbox_root() -> Path:
    box = real_root() / SANDBOX_NAME
    if not sdk.is_dir(box):
        sys.exit(f"The sandbox folder doesn't exist: {box}")
    return box


def _inside_sandbox(path: Path, box: Path) -> Path:
    """Refuse to touch anything outside the sandbox folder (the one guard that
    stands between `reset` and a real batch)."""
    path, box = Path(path).resolve(), Path(box).resolve()
    if box.name != SANDBOX_NAME or box not in path.parents:
        raise RuntimeError(f"Refusing to touch {path}: not inside {box}")
    return path


def _rmtree(path: Path, box: Path) -> None:
    path = _inside_sandbox(path, box)
    if sdk.is_dir(path):
        shutil.rmtree(sdk.long_path(path))
    elif sdk.exists(path):
        os.remove(sdk.long_path(path))


def _copytree(src: Path, dest: Path) -> int:
    """Copy a tree through the SDK (long paths, cloud-only files hydrated)."""
    n = 0
    base = sdk.long_path(src)
    for dirpath, _dirs, files in os.walk(base):
        rel = Path(os.path.relpath(dirpath, base))
        sdk.ensure_dir(dest / rel)
        for f in files:
            if f.lower() == "desktop.ini" or f.startswith("~$"):
                continue
            sdk.copy_resilient(Path(src) / rel / f, dest / rel / f)
            n += 1
    return n


# ── reset / status / launch ────────────────────────────────────────────────

def reset(state: str) -> None:
    box = sandbox_root()
    src = box / PRISTINE
    if not sdk.is_dir(src / state):
        sys.exit(f"No pristine '{state}' copy in {src} - run `build` first.")
    for item in LIVE_ITEMS:
        _rmtree(box / item, box)
    n = _copytree(src / "common", box)
    n += _copytree(src / state, box)
    print(f"Sandbox reset to '{state}' ({n} files) in {box}")


def status() -> None:
    box = sandbox_root()
    print(f"Sandbox: {box}")
    for item in LIVE_ITEMS + [PRISTINE]:
        print(f"  {'OK ' if sdk.exists(box / item) else '-- '} {item}")
    batch = box / ("Batch " + BATCH)
    if sdk.is_dir(batch):
        kids = sorted(p.name for p in batch.iterdir())
        state = "raw" if "Work Packets" in kids else "ready (or already run)"
        print(f"  Batch {BATCH}: {len(kids)} entries - looks {state}")


def launch(state: str | None) -> None:
    box = sandbox_root()
    if state:
        reset(state)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env[sdk.SANDBOX_922_ENV] = str(box)
    print(f"Launching TechDeck with the 922 sandbox ON ({box}).")
    print("Every 922 app sees the sandbox as its root; webhooks are previewed, never sent.")
    subprocess.call([sys.executable, "-m", "techdeck"], cwd=str(REPO), env=env)


# ── build (one-time, from the real batches) ────────────────────────────────

def _load_plugin(plugin_id: str):
    import importlib.util
    path = REPO / "plugins" / plugin_id / "run.py"
    spec = importlib.util.spec_from_file_location(f"sbx_{plugin_id}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip_stamps(pdf: Path, pallet_mod, diff_mod) -> bool:
    """Remove our red 'Batch N Pallet P' and 'DIFFICULT' stamps from page 1."""
    import fitz
    doc = fitz.open(sdk.long_path(pdf))
    page = doc[0]
    rects = pallet_mod._find_all_stamp_rects(page) + diff_mod._find_stamp_rects(page)
    if not rects:
        doc.close()
        return False
    for r in rects:
        page.add_redact_annot(r, fill=(1, 1, 1))
    page.apply_redactions()
    sdk.save_pdf_atomic(doc, pdf)            # closes doc
    return True


def _header(ws, want: str = "ORDER"):
    """(row, {HEADER: col}) of the first row (1-10) holding `want`."""
    for r in range(1, 11):
        vals = {}
        for c in range(1, 41):
            v = ws.Cells(r, c).Value
            if v is not None and str(v).strip():
                vals[str(v).strip().upper()] = c
        if want in vals:
            return r, vals
    raise RuntimeError(f"No '{want}' header on sheet {ws.Name}")


def _trim_sheet(ws, keep: set, extra_rows: list[dict]) -> int:
    """Delete every data row whose ORDER isn't in `keep`, then append
    `extra_rows` ({HEADER: value}) below the last kept row. Returns rows kept."""
    hdr, cols = _header(ws)
    oc = cols["ORDER"]
    last = ws.Cells(ws.Rows.Count, oc).End(_XL_UP).Row
    r = last
    while r > hdr:                        # bottom-up, contiguous runs at a time
        v = ws.Cells(r, oc).Value
        if v is not None and str(v).strip().upper() in keep:
            r -= 1
            continue
        top = r
        while top - 1 > hdr:
            u = ws.Cells(top - 1, oc).Value
            if u is not None and str(u).strip().upper() in keep:
                break
            top -= 1
        ws.Range(ws.Rows(top), ws.Rows(r)).Delete()
        r = top - 1
    nxt = ws.Cells(ws.Rows.Count, oc).End(_XL_UP).Row + 1
    kept = nxt - hdr - 1
    for row in extra_rows:
        for name, c in cols.items():
            if name in row and row[name] is not None:
                ws.Cells(nxt, c).Value = row[name]
        nxt += 1
    return kept + len(extra_rows)


def _read_rows(xlsx: Path, sheet: str, order: str) -> list[dict]:
    """{HEADER: value} for each row of `order` on `sheet` (openpyxl, read-only)."""
    wb = sdk.load_workbook_resilient(xlsx, data_only=True, read_only=True)
    try:
        ws = wb[sheet]
        rows = list(ws.iter_rows(min_row=1, max_row=400, max_col=40, values_only=True))
    finally:
        wb.close()
    for i, row in enumerate(rows[:10]):
        names = [str(v).strip().upper() if v is not None else "" for v in row]
        if "ORDER" in names:
            oc = names.index("ORDER")
            return [{n: v for n, v in zip(names, r) if n}
                    for r in rows[i + 1:]
                    if r[oc] is not None and str(r[oc]).strip().upper() == order]
    return []


def _excel():
    import win32com.client as win32
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    return xl


def build() -> None:
    root, box = real_root(), sandbox_root()
    keep = {folder.split("-", 1)[0].upper() for _b, folder, _w in ORDERS}
    extra_batch, extra_folder = next((b, f) for b, f, _w in ORDERS if b != "498")
    extra_order = extra_folder.split("-", 1)[0].upper()
    src_doc = root / "Batch 498" / "Batch 498 - Documentation"
    extra_rows = _read_rows(
        root / f"Batch {extra_batch}" / f"Batch {extra_batch} - Documentation"
        / f"PO H{extra_batch} QF-QU-09 REV C.xlsx", "PO", extra_order)
    print(f"{extra_order}: {len(extra_rows)} PO row(s) from Batch {extra_batch}")
    pallet_mod = _load_plugin("922_pallet_stamper")
    diff_mod = _load_plugin("922_difficulty_stamper")

    stage = Path(tempfile.mkdtemp(prefix="sandbox922_"))
    doc = stage / "doc" / f"Batch {BATCH} - Documentation"
    common, raw, ready = stage / "common", stage / "raw", stage / "ready"
    try:
        # ---- Documentation workbooks, trimmed through Excel --------------
        rev_c = doc / f"PO H{BATCH} QF-QU-09 REV C.xlsx"
        organizer = doc / f"PO H{BATCH} Pallet & Rod Organizer.xlsx"
        quote = doc / "Quote" / f"EB 922 H{BATCH} Quote.xlsx"
        sdk.copy_resilient(src_doc / "PO H498 QF-QU-09 REV C.xlsx", rev_c)
        sdk.copy_resilient(src_doc / "PO H498 Pallet & Rod Organizer.xlsx", organizer)
        sdk.copy_resilient(src_doc / "Quote" / "EB 922 H498 Quote.xlsx", quote)
        mpl = common / "922 MPL.xlsx"
        sdk.copy_resilient(root / "922 MPL.xlsx", mpl)
        xl = _excel()
        try:
            for path, sheet in ((rev_c, "PO"), (organizer, "PO Info Drop"),
                                (quote, "PO DROP")):
                wb = xl.Workbooks.Open(str(path))
                ws = wb.Worksheets(sheet)
                n = _trim_sheet(ws, keep, extra_rows)
                ws.Range("G1").Value = int(BATCH)
                if sheet == "PO Info Drop":
                    blc = wb.Worksheets("Bin Label & Checklist")
                    for i, pallet in enumerate(PALLET_SPLIT):
                        blc.Cells(45 + i, 7).Value = pallet
                xl.CalculateFull()
                wb.Save()
                wb.Close()
                print(f"  {path.name} [{sheet}]: {n} row(s) kept, G1 = {BATCH}")
            wb = xl.Workbooks.Open(str(mpl))
            ws = wb.Worksheets("PO 321+")
            dropped = []
            for r in range(1, 9):
                for c in range(ws.UsedRange.Columns.Count + ws.UsedRange.Column, 0, -1):
                    v = ws.Cells(r, c).Value
                    s = str(v).strip().upper() if v is not None else ""
                    if s.startswith("PO ") and s[3:].strip().isdigit() \
                            and int(s[3:]) >= MPL_DROP_FROM:
                        ws.Columns(c).Delete()
                        dropped.append(s)
            wb.Save()
            wb.Close()
            print(f"  922 MPL.xlsx: dropped {dropped or 'nothing'}")
        finally:
            xl.Quit()

        readme = src_doc / "H498 ALL" / "CUI -NNPI- READ ME.pdf"
        if sdk.exists(readme):
            sdk.copy_resilient(readme, doc / f"H{BATCH} ALL" / readme.name)
        for sub in ("Production Packets", "QA"):
            sdk.ensure_dir(doc / sub)
        (doc / "README - TEST BATCH.txt").write_text(_readme_text(), encoding="utf-8")

        # ---- common: 1 - Completed sources + the master quote -------------
        for src_batch, folder, where in REPEAT_SOURCES:
            _copytree(root / where / folder,
                      common / "1 - Completed" / f"Batch {src_batch}" / folder)
        # Mirrors the REAL layout (Batch Setup\Quote - master_parts.quote_path).
        sdk.copy_resilient(root / MASTER_QUOTE, common / MASTER_QUOTE)

        # ---- raw: Documentation + Work Packets ----------------------------
        for state_dir in (raw, ready):
            _copytree(doc.parent, state_dir / f"Batch {BATCH}")
        packets = raw / f"Batch {BATCH}" / "Work Packets"
        for src_batch, folder, _w in ORDERS:
            pkt = sdk.find_work_packet(root / f"Batch {src_batch}" / folder)
            if pkt is None:
                print(f"  WARNING: no work packet found in {folder}")
                continue
            dest = sdk.copy_resilient(pkt, packets / pkt.name)
            _strip_stamps(dest, pallet_mod, diff_mod)

        # ---- ready: the order folders (+ REPEAT BATCHES) ------------------
        for src_batch, folder, _w in ORDERS:
            dest = ready / f"Batch {BATCH}" / folder
            _copytree(root / f"Batch {src_batch}" / folder, dest)
            pkt = sdk.find_work_packet(dest)
            if pkt is not None:
                _strip_stamps(pkt, pallet_mod, diff_mod)
        for src_batch, folder, where in REPEAT_SOURCES:
            if where.endswith("REPEAT BATCHES"):
                _copytree(root / where / folder,
                          ready / f"Batch {BATCH}" / "REPEAT BATCHES" / folder)

        # ---- publish into _Pristine ---------------------------------------
        pristine = box / PRISTINE
        _rmtree(pristine, box)
        for name in ("common", "raw", "ready"):
            n = _copytree(stage / name, pristine / name)
            print(f"  _Pristine\\{name}: {n} files")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print("Built. Run `reset ready` (or `reset raw`) to lay the batch out.")


def _readme_text() -> str:
    lines = [
        f"TEST BATCH {BATCH} - NOT A REAL BATCH",
        "",
        "Built by TechDeck's tools/devkit/sandbox_922.py from real orders, for testing",
        "922 apps. Reset it any time:  python -m tools.devkit.sandbox_922 reset ready",
        "Run TechDeck against it:      python -m tools.devkit.sandbox_922 launch",
        "",
        "The data is real (CUI / NNPI). Keep it on this SharePoint site.",
        "",
        "Orders (source batch - folder - why it is here):",
    ]
    lines += [f"  {b} - {f} - {w}" for b, f, w in ORDERS]
    lines += ["", f"PALLET split (Manual Adjustments): {PALLET_SPLIT}",
              f"922 MPL copy has every PO column >= {MPL_DROP_FROM} removed.",
              "Workbooks trimmed to these orders; the Material Info form and the",
              "printed quote / pallet organizer PDFs were not copied."]
    return "\r\n".join(lines) + "\r\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("build")
    p = sub.add_parser("reset")
    p.add_argument("state", choices=["raw", "ready"])
    p = sub.add_parser("launch")
    p.add_argument("state", nargs="?", choices=["raw", "ready"],
                   help="reset to this state first (default: run as-is)")
    args = ap.parse_args(argv)
    {"status": status, "build": build}.get(args.cmd, lambda: None)()
    if args.cmd == "reset":
        reset(args.state)
    elif args.cmd == "launch":
        launch(args.state)


if __name__ == "__main__":
    main()
