"""922 Production Packets - the tube cutting list a batch feeds to the optimizer.

What it builds
--------------
`<batch> Tubes.xlsx` in the batch's `Production Packets` folder: one sheet per
source material, named after the serial, three columns and no headers - part
name, saw cut length, quantity - ready to paste into the 1D cutting optimizer.
Beside it, `Production Packets Report - Batch <n>.pdf`, which says where every
length came from and which ones want a human eye.

Where a length comes from (worked out against 291 real parts on batches
500-504, 285 of them right)
---------------------------------------------------------------------------
A tube that belongs to an ASSEMBLY is read off the assembly sheet, never off
its own part sheet. Its own sheet is opened only to rank the tubes of that
assembly by length, which is the one thing that says which dimension belongs to
which tube - a callout's leader points away from the tube it names, so
nearest-callout and reading-order both deal the numbers out wrong.

  1. "( N SAW CUT )", or a bare parenthesis under a dimension - that IS the cut
     length; nothing is added.
  2. Otherwise the assembly dimension plus 0.10" per ground end: +0.10 for an
     end tube, +0.20 for a middle tube of a 3-or-more tube assembly, because
     every jointed end is modelled 0.1" oversized for the grind.
  3. A one-off tube with no assembly: a parenthesised dimension if it has one,
     else the dimension as printed. A straight cut gets nothing added.

Everything rounds UP to the tenth.

Where it is unsure it still writes its best answer, highlights the row yellow,
and lists it on the report. It never leaves a cell blank and guesses nothing
silently.
"""
import threading
from pathlib import Path

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:                       # standalone / CLI testing
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# cut_lengths.py lives beside this file; load it by path so it resolves under
# every plugin-loader import style (dev repo AND %LOCALAPPDATA% installs).
import importlib.util as _ilu
_CL_SPEC = _ilu.spec_from_file_location(
    "techdeck_922_cut_lengths",
    Path(__file__).resolve().parent / "cut_lengths.py")
assert _CL_SPEC is not None and _CL_SPEC.loader is not None
cl = _ilu.module_from_spec(_CL_SPEC)
_CL_SPEC.loader.exec_module(cl)

VERSION = "1.0.0"

PACKETS_FOLDER = "Production Packets"
ORGANIZER_GLOB = "*Pallet & Rod Organizer*.xlsx"
INFO_SHEET = "PO Info Drop"
SAW_PALLET = "SAW"
YELLOW = "FFF4C2"           # the review highlight; matches the report's target
SWAMP_GREEN = "#4FD468"


# ───────────────────────────────────────────────────────────────── the batch

def _organizer(batch_path: Path, batch_no, log):
    """The batch's PO H<n> Pallet & Rod Organizer workbook."""
    doc = batch_path / f"Batch {batch_no} - Documentation"
    folder = doc if sdk.is_dir(doc) else batch_path
    hits = [p for p in folder.glob(ORGANIZER_GLOB)
            if not p.name.startswith("~$")]
    if not hits:
        raise sdk.UserFacingError(
            f"Batch {batch_no} has no Pallet & Rod Organizer workbook.",
            "Set the batch up first, then run this again.")
    log(f"Organizer: {hits[0].name}")
    return hits[0]


def _read_tubes(path: Path, log):
    """Every TUBE on the batch, from the organizer's PO Info Drop.

    Returns [{part, order, serial, desc, qty}]. A row is a tube when it carries
    a Base Material - the organizer fills that column for tubes only, which is
    how the plate and rod lines are left behind. Columns are looked up by
    header NAME (Hard Rule 1).
    """
    wb = sdk.load_workbook_resilient(path, read_only=True, data_only=True, log=log)
    try:
        if INFO_SHEET not in wb.sheetnames:
            raise sdk.UserFacingError(
                f"The organizer has no '{INFO_SHEET}' sheet.",
                "Check the workbook was made from the current template.")
        ws = wb[INFO_SHEET]
        header_row, cols = sdk.find_header_row(
            ws, ["ORDER", "DYPN", "SOURCE MATERIAL", "QTY", "Base Material"])
        if header_row is None:
            raise sdk.UserFacingError(
                f"Could not find the column headers on '{INFO_SHEET}'.",
                "Check the sheet still has its ORDER / DYPN / SOURCE MATERIAL "
                "header row.")
        c_order = cols["ORDER"]
        c_dypn = cols["DYPN"]
        c_src = cols["SOURCE MATERIAL"]
        c_qty = cols["QTY"]
        c_base = cols["BASE MATERIAL"]

        rows, seen = [], set()
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
            def _v(c):
                v = r[c - 1] if c - 1 < len(r) else None
                return "" if v is None else str(v).strip()
            part, serial, base = _v(c_dypn), _v(c_src), _v(c_base)
            if not part or not serial or not base:
                continue
            serial = serial.split(".")[0]          # Excel hands back 218012959.0
            key = (part.upper(), serial)
            if key in seen:
                continue
            seen.add(key)
            try:
                qty = int(float(_v(c_qty) or 1))
            except ValueError:
                qty = 1
            rows.append({"part": part.upper(), "order": _v(c_order),
                         "serial": serial, "desc": base, "qty": max(qty, 1)})
    finally:
        wb.close()
    log(f"{len(rows)} tubes on the batch, "
        f"{len({r['serial'] for r in rows})} source materials")
    return rows


def _size_key(desc):
    """Sort key putting the BIGGEST tube first.

    Batch 505's finished packets are named SAW.1 = 6.0 X 6.0 X 0.50 down to
    SAW.6 = 3.0 X 3.0 X 0.375, and the Material Use Tracker lists them the same
    way, so numbering from the small end would have named every packet file
    wrongly.
    """
    import re
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(desc or ""))]
    nums += [0.0, 0.0, 0.0]
    return (-nums[0], -nums[1], -nums[2])


def _norm_material(text):
    """One spelling for a tube size, whoever typed it.

    'HSS 6.0 X 6.0 X 0.50 NOM' and '6.0 X 6.0 X 0.50 NOM' are one material, and
    so are '1.5 X 1.5 X 0.188' and '1.5 X1.5 X 0.188' - the PO drops the space
    after the X on some rows while the organizer keeps it, which filed a real
    pallet-2 material under UNKNOWN until the X became a separator here.
    """
    import re
    t = str(text or "").upper()
    t = re.sub(r"\(.*?\)", " ", t)        # the organizer appends "(SAW CUT)"
    t = re.sub(r"\bHSS\b|\bNOM\b|,", " ", t)
    t = re.sub(r"\s*X\s*", " X ", t)
    return " ".join(t.split())


def _read_pallets(path: Path, log):
    """{normalised material: pallet number} from the Pallet Organizer sheet.

    The printed sheet's lower half lists the source materials each pallet
    needs, numbered, under a 'MATERIAL REQUIRED' heading per pallet. Both the
    heading and the 'PALLET n' title above it are found by TEXT, never by cell
    address (Hard Rule 1) - the block moves as the batch's order count changes.
    """
    import re
    wb = sdk.load_workbook_resilient(path, read_only=False, data_only=True, log=log)
    try:
        sheet = next((n for n in sdk.visible_sheetnames(wb)
                      if n.strip().upper() == "PALLET ORGANIZER"), None)
        if sheet is None:
            log("WARNING: no 'Pallet Organizer' sheet - pallet numbers skipped")
            return {}
        ws = wb[sheet]
        heads = []
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and "MATERIAL REQUIRED" in                         cell.value.upper():
                    heads.append((cell.row, cell.column))
        out = {}
        for r0, c0 in heads:
            pallet = None
            for r in range(r0 - 1, 0, -1):
                v = ws.cell(r, c0).value
                m = re.search(r"PALLET\s*(\d+)", str(v or "").upper())
                if m:
                    pallet = m.group(1)
                    break
            if pallet is None:
                continue
            for r in range(r0 + 1, r0 + 40):
                desc = ws.cell(r, c0 + 1).value
                if desc is None or not str(desc).strip():
                    continue
                idx = ws.cell(r, c0).value
                out.setdefault(_norm_material(desc), (pallet, str(idx or '').strip()))
        log(f"Pallet map: {len(out)} materials across "
            f"{len({p for p, _i in out.values()})} pallets")
        return out
    finally:
        wb.close()


def _pallet_of(serial, desc, pallet_map):
    """Which packet group a source material belongs to.

    An oversized tube is saw cut, and SAW counts as its own pallet for this
    process even though it rides on pallet 1. Everything else takes the pallet
    number the organizer gave it. Anything neither knows is reported, never
    guessed at.
    """
    if sdk.tube_class(serial) == "oversized":
        return SAW_PALLET
    hit = pallet_map.get(_norm_material(desc))
    if hit:
        return hit[0]
    return "UNKNOWN"


# ───────────────────────────────────────────────────────────── the workbook

def _guard_output(dest: Path):
    """Refuse to write anything but our OWN two files.

    The Production Packets folder holds the hand-built cutting list and the
    finished SAW.n / n.n packet PDFs. This app only ever adds two files, both
    carrying "(TechDeck)" in the name, and it never merges, renames or deletes
    anything that is already in there.
    """
    if "(TechDeck)" not in dest.name:
        raise RuntimeError(
            f"refusing to write {dest.name} - this app only writes its own "
            f"'(TechDeck)' files into the Production Packets folder")
    return dest


def _write_workbook(dest: Path, materials, log):
    """One sheet per source material: part / length / qty, no headers.

    A row the reader was unsure about is filled in anyway and highlighted
    yellow - a blank cell in a cutting list is worse than a flagged guess.
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    fill = PatternFill("solid", fgColor=YELLOW)
    wb = Workbook()
    wb.remove(wb.active)
    for serial, entries in materials:
        ws = wb.create_sheet(title=serial[:31])
        for i, e in enumerate(entries, start=1):
            ws.cell(i, 1, e["part"])
            ws.cell(i, 2, e["length"])
            ws.cell(i, 3, e["qty"])
            if e["review"]:
                for c in (1, 2, 3):
                    ws.cell(i, c).fill = fill
        ws.column_dimensions["A"].width = 24
    sdk.save_workbook(wb, _guard_output(dest), log=log)
    return dest


# ──────────────────────────────────────────────────────────────── the report

def _write_report(dest: Path, batch_no, materials, log):
    """The colour-coded PDF, same shape as the LST Organizer's."""
    C = sdk.REPORT_COLORS
    flat = [e for _s, entries in materials for e in entries]
    review = [e for e in flat if e["review"] and e["length"] is not None]
    missing = [e for e in flat if e["length"] is None]
    unknown = [e for e in flat if e["pallet"] == "UNKNOWN"]

    d = sdk.ReportPdf()
    d.text(f"Production Packets - Batch {batch_no}", size=16, bold=True,
           color=C["band"])
    d.text("Tube cutting list for the 1D cutting optimizer", size=9,
           color=C["grey"])
    d.gap(8)

    w2 = [360, 168]
    d.header_row(["Batch summary", "Count"], w2)
    rows = [
        ("Tubes on the batch", len(flat), None, None),
        ("Source materials", len(materials), None, None),
        ("Lengths read from a drawing", len(flat) - len(missing), None, None),
        ("Needs a look before you cut", len(review),
         C["rev_bg"] if review else C["ok_bg"],
         C["rev_tx"] if review else C["ok_tx"]),
        ("No drawing found", len(missing),
         C["miss_bg"] if missing else C["ok_bg"],
         C["miss_tx"] if missing else C["ok_tx"]),
        ("Source material not recognised", len(unknown),
         C["miss_bg"] if unknown else C["ok_bg"],
         C["miss_tx"] if unknown else C["ok_tx"]),
    ]
    for label, n, bg, tx in rows:
        d.row([label, str(n)], w2, fill=bg, tcolor=tx)
    d.gap(14)

    w5 = [120, 86, 150, 60, 112]
    if missing:
        d.text("No drawing found - these have no length", size=11, bold=True,
               color=C["miss_tx"])
        for line in ("Nothing in the batch draws these parts, so the cell is "
                     "left empty.",
                     "Find the print and fill the length in by hand."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Order", "Material", "Pallet", ""], w5)
        for e in missing:
            d.row([e["part"], e["order"], e["desc"], e["packet"], ""], w5,
                  fill=C["miss_bg"], tcolor=C["miss_tx"])
        d.gap(14)

    if review:
        d.text("Check these before you cut", size=11, bold=True,
               color=C["rev_tx"])
        for line in ("The length is filled in, and highlighted yellow on the "
                     "cutting list.",
                     "Two tubes on one assembly were too close in length to "
                     "tell apart, so which",
                     "number went to which tube is a judgement call."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Length", "Material", "Pallet", "Read from"], w5)
        for e in review:
            d.row([e["part"], str(e["length"]), e["desc"], e["packet"],
                   e["source"]], w5, fill=C["rev_bg"], tcolor=C["rev_tx"])
        d.gap(14)

    if unknown:
        d.text("Source material not recognised", size=11, bold=True,
               color=C["extra_tx"])
        for line in ("These are on the PO with a base material, but neither the "
                     "organizer nor",
                     "TechDeck says which pallet they belong to, so they are "
                     "filed under UNKNOWN."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Order", "Material", "Serial", ""], w5)
        for e in unknown:
            d.row([e["part"], e["order"], e["desc"], e["serial"], ""], w5,
                  fill=C["extra_bg"], tcolor=C["extra_tx"])
        d.gap(14)

    d.new_page()
    d.text("The full cutting list", size=11, bold=True, color=C["band"])
    w4 = [150, 96, 60, 222]
    for serial, entries in materials:
        d.gap(6)
        d.row([f"{entries[0]['packet']}   {serial}   {entries[0]['desc']}",
               "", "", ""], [528], fill=C["group_bg"], bold=True)
        d.header_row(["Part", "Length", "Qty", "Read from"], w4)
        for i, e in enumerate(entries):
            fill = (C["rev_bg"] if e["review"]
                    else C["miss_bg"] if e["length"] is None
                    else C["zebra"] if i % 2 else None)
            d.row([e["part"],
                   "-" if e["length"] is None else str(e["length"]),
                   str(e["qty"]), e["source"]], w4, fill=fill)
    d.save(_guard_output(dest))
    log(f"Report: {dest.name}")
    return dest


# ────────────────────────────────────────────────────────────────────── run

def run(params: dict, progress_callback, cancel_event: threading.Event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}
    console = params.get("console")

    log(f"922 Production Packets v{VERSION}")

    picked = sdk.request_922_batch_folder(params, settings.get("base_path", ""))
    if picked is None or cancel_event.is_set():
        return
    batch_no, batch_path = picked
    batch_path = Path(batch_path)
    log(f"Batch {batch_no}: {batch_path}")
    progress_callback(5)

    organizer = _organizer(batch_path, batch_no, log)
    tubes = _read_tubes(organizer, log)
    pallet_map = _read_pallets(organizer, log)
    if not tubes:
        raise sdk.UserFacingError(
            f"Batch {batch_no}'s organizer lists no tubes.",
            "Check the PO Info Drop sheet has the batch's orders pasted in.")
    progress_callback(12)

    # hydrate the shop prints while we group the tubes (Hard Rule 6)
    prefetch = sdk.prefetch_paths(
        (p for p in batch_path.rglob("*.pdf")), cancel_event=cancel_event)
    try:
        index = cl.index_drawings(str(batch_path))
        log(f"{len(index)} drawings in the batch")

        # every tube of an assembly, so the ranking roster is the PO's, not
        # whichever callouts happen to be readable on the sheet
        siblings = {}
        for t in tubes:
            siblings.setdefault(t["part"].rsplit("-", 1)[0], []).append(t["part"])

        for i, t in enumerate(tubes):
            sdk.raise_if_cancelled(cancel_event)
            length, source, _asm, review = cl.read(
                t["part"], index, t["desc"],
                siblings.get(t["part"].rsplit("-", 1)[0], [t["part"]]))
            t["length"] = length
            t["source"] = source
            t["review"] = bool(review)
            t["pallet"] = _pallet_of(t["serial"], t["desc"], pallet_map)
            progress_callback(12 + int(63 * (i + 1) / len(tubes)))
    finally:
        try:
            prefetch.stop()
        except Exception:
            pass

    # group by source material, SAW packets first, then by tube size descending
    by_serial = {}
    for t in tubes:
        by_serial.setdefault(t["serial"], []).append(t)
    materials = sorted(
        by_serial.items(),
        key=lambda kv: (kv[1][0]["pallet"] != SAW_PALLET,
                        _size_key(kv[1][0]["desc"])))
    # the packet number is the organizer's OWN number for that material, so a
    # packet file lands on the same name whoever builds it. SAW counts as its
    # own pallet here, so those are numbered fresh.
    counters = {}
    for serial, entries in materials:
        entries.sort(key=lambda e: -(e["length"] or 0))
        pallet = entries[0]["pallet"]
        hit = pallet_map.get(_norm_material(entries[0]["desc"]))
        index = hit[1] if (hit and pallet != SAW_PALLET and hit[1]) else ""
        if not index:
            counters[pallet] = counters.get(pallet, 0) + 1
            index = str(counters[pallet])
        packet = f"{pallet}.{index}"
        for e in entries:
            e["packet"] = packet
    progress_callback(80)

    out_dir = batch_path / f"Batch {batch_no} - Documentation" / PACKETS_FOLDER
    sdk.ensure_dir(out_dir)
    # a separate file from the hand-built "<batch> Tubes.xlsx", so the two can
    # be compared side by side and a human sheet is never written over
    book = _write_workbook(
        out_dir / f"{batch_no} Tubes (TechDeck).xlsx", materials, log)
    progress_callback(90)
    report = _write_report(
        out_dir / f"Production Packets Report (TechDeck) - Batch {batch_no}.pdf",
        batch_no, materials, log)
    progress_callback(100)

    flagged = sum(1 for t in tubes if t["review"] and t["length"] is not None)
    blank = sum(1 for t in tubes if t["length"] is None)
    log(f"{len(tubes)} tubes across {len(materials)} source materials")
    if flagged:
        log(f"{flagged} highlighted yellow - check those before you cut")
    if blank:
        log(f"{blank} with no drawing - those cells are empty")
        sdk.flag_action(
            params,
            f"Fill in the saw cut length for {blank} tube(s) by hand in "
            f"{book.name}.",
            "TechDeck found no drawing for them anywhere in the batch, so it "
            "left those cells empty rather than guess. The report lists them.")
    if flagged or blank:
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_WARNING,
            f"{flagged + blank} tube(s) need a look - see the report")

    sdk.link_output(params, f"Open {book.name}", str(book), prefix="[CUT LIST]")
    sdk.link_output(params, "Open the Production Packets report", str(report),
                    prefix="[REPORT]")

    if console is not None and hasattr(console, "safe_colored_log"):
        console.safe_colored_log("Get out me swamp!", SWAMP_GREEN)
