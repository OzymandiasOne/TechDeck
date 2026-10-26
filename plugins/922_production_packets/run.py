"""922 Production Packets - the tube cutting list a batch feeds to the optimizer.

What it builds
--------------
`<batch> Tubes.xlsx` in the batch's `Production Packets` folder: one sheet per
source material, named after its packet (`SAW.4`, `2.5`), carrying the material
number, the batch and the pallet across the top and then part name, saw cut
length and quantity - Carrie's formatting, lifted from the two sheets she
marked up. A row worth a second look gets an arrow in the Problem? column,
which brings up the X at the top of the sheet.
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

_PK_SPEC = _ilu.spec_from_file_location(
    'techdeck_922_packets',
    Path(__file__).resolve().parent / 'packets.py')
assert _PK_SPEC is not None and _PK_SPEC.loader is not None
pk = _ilu.module_from_spec(_PK_SPEC)
_PK_SPEC.loader.exec_module(pk)

VERSION = "1.3.0"

PACKETS_FOLDER = "Production Packets"
PACKETS_SUBFOLDER = "TechDeck Packets"   # our own folder; nothing to overwrite
ORGANIZER_GLOB = "*Pallet & Rod Organizer*.xlsx"
TRACKER_FOLDER = "2 - Planning"
TRACKER_GLOB = "*Material Use Tracker*.xlsx"
INFO_SHEET = "PO Info Drop"
SAW_PALLET = "SAW"
SWAMP_GREEN = "#4FD468"

# Carrie's sheet formatting, lifted cell for cell from the sheets she marked up
# ("GET THE FORMATTING FROM SHEETS SAW.4 AND 2.5", 2026-10-26). Her file uses
# theme colours; these are the same shades written out, so a theme change on
# somebody's machine cannot move them.
SAW_TOP, SAW_BAND = "CCC1DA", "B3A2C7"        # accent4, tint .6 / .4 - purple
LASER_TOP, LASER_BAND = "B7DEE8", "93CDDD"    # accent5, tint .6 / .4 - blue
PROBLEM_FONT = "4F6228"                       # accent3 tint -.5 - dark olive
X_FONT = "C00000"                             # the dark red of the X
ARROW = chr(0x2192)                           # the arrow that marks a bad row
# One X per sheet, not per row: the arrow says WHICH row, the X says this sheet
# has something in it. It is a plain formula, not conditional formatting - the
# only CF rule in Carrie's file is a broken one whose formula is the text
# "IF(A5-A100=\"\")", which can never fire, so it is not reproduced.
X_FORMULA = '=IF(COUNTA(A5:A100)>0,"X","")'
COL_WIDTHS = {"A": 12.43, "B": 20.71, "C": 10.86, "D": 13.14, "E": 10.71}
ROW_H, ROW_H_TALL = 20.1, 24.95


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


def _size_triple(text):
    """A tube size as (side, side, wall) so two documents can be compared.

    The tracker writes a square tube as `3.0 SQ X .25` and the organizer writes
    the same one as `3.0 X 3.0 X 0.25 NOM`, so neither string matches the other
    and the numbers are the only common ground. `SQ` with two numbers means the
    side is repeated. Returns None when it cannot read three numbers out.
    """
    import re
    t = str(text or "").upper()
    nums = [float(n) for n in re.findall(r"\d*\.?\d+", t)]
    if "SQ" in t and len(nums) == 2:
        nums = [nums[0], nums[0], nums[1]]
    if len(nums) < 3:
        return None
    return (round(nums[0], 3), round(nums[1], 3), round(nums[2], 3))


def _tracker_order(root, batch_no, log):
    """{serial: position} in the order the Material Use Tracker lists them.

    The tracker carries one sheet per batch, named by the batch number, and its
    rows are already grouped the way the floor reads them - pallet 1, then 2,
    then 3, then SAW on its own. The cutting list's sheets come out in that
    same order so the two documents can be read side by side (Anthony,
    2026-10-26).

    A missing tracker, a batch with no sheet yet, or a file somebody has open
    is a NOTE and nothing more: the order falls back to TechDeck's own.
    Read-only throughout - this is somebody's live planning workbook.
    """
    if root is None:
        return {}
    hits = [p for p in (Path(root) / TRACKER_FOLDER).glob(TRACKER_GLOB)
            if not p.name.startswith("~$")]
    if not hits:
        log(f"No Material Use Tracker in '{TRACKER_FOLDER}' - sheets go in "
            f"TechDeck's own order")
        return {}
    try:
        wb = sdk.load_workbook_resilient(hits[0], read_only=True,
                                         data_only=True, log=log)
    except Exception as exc:
        log(f"Could not read {hits[0].name} ({exc}) - sheets go in TechDeck's "
            f"own order")
        return {}
    try:
        sheet = next((n for n in sdk.visible_sheetnames(wb)
                      if str(n).strip() == str(batch_no)), None)
        if sheet is None:
            log(f"{hits[0].name} has no sheet for batch {batch_no} yet - "
                f"sheets go in TechDeck's own order")
            return {}
        ws = wb[sheet]
        header_row, cols = sdk.find_header_row(ws, ["PALLET", "ITEM"])
        if header_row is None:
            log(f"No PALLET / ITEM header row on {hits[0].name} sheet "
                f"'{sheet}' - sheets go in TechDeck's own order")
            return {}
        c_item = cols["ITEM"]
        c_size = cols.get("SIZE")
        order, n = {}, 0
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
            def _v(c):
                v = r[c - 1] if c and c - 1 < len(r) else None
                return "" if v is None else str(v).strip()
            # the serial comes back as a float on some rows (218012959.0), and
            # the lower half of the sheet holds plate/rod tags, not serials
            serial = _v(c_item).split(".")[0]
            if not serial.isdigit() or serial in order:
                continue
            order[serial] = n
            # the SIZE is the fallback: batch 505's tracker stocks 3.0 X 3.0 X
            # 0.25 under item 218136140 while the PO calls it 218003095, and
            # without this that material drops out of its pallet group
            triple = _size_triple(_v(c_size))
            if triple is not None:
                order.setdefault(triple, n)
            n += 1
    finally:
        wb.close()
    log(f"Sheet order from {hits[0].name} sheet '{batch_no}' "
        f"({len(order)} materials)")
    return order


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
        out, order = {}, 0
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
                text = str(desc).strip()
                key = _norm_material(desc)
                if key in out:
                    continue
                # the organizer's own item number is kept for the record, but it
                # is NOT the packet number - see _packet_names
                out[key] = {"pallet": pallet,
                            "idx": str(ws.cell(r, c0).value or "").strip(),
                            "order": order,
                            "text": text,
                            "saw": "SAW CUT" in text.upper()}
                order += 1
        log(f"Pallet map: {len(out)} materials across "
            f"{len({e['pallet'] for e in out.values()})} pallets")
        return out
    finally:
        wb.close()


def _pallet_of(serial, desc, pallet_map):
    """Which packet group a source material belongs to.

    The organizer decides: it writes "(SAW CUT)" after the materials that go to
    the saw, and SAW counts as its own packet group for this process even though
    those materials ride on pallet 1. Everything else takes the pallet number the
    organizer gave it. `sdk.tube_class` is only the fallback for a material the
    organizer does not list at all; anything neither knows is reported, never
    guessed at.
    """
    hit = pallet_map.get(_norm_material(desc))
    if hit:
        return SAW_PALLET if hit["saw"] else hit["pallet"]
    if sdk.tube_class(serial) == "oversized":
        return SAW_PALLET
    return "UNKNOWN"


def _packet_names(pallet_map):
    """{normalised material: packet name} - `SAW.1`, `1.1`, `2.3`.

    Numbered FRESH per group, walking the organizer's MATERIAL REQUIRED list in
    its own order: the saw cut materials become SAW.1, SAW.2 ... and the rest are
    numbered within their own pallet.

    The organizer's own item number is NOT the packet number, which cost a
    wrong file name. Batch 505's pallet 1 lists seven materials - six saw cut,
    and one laser one sitting at position 5 - and the hand-built packet for that
    laser material is `1.1`, not `1.5`. Pallet 2 hid the bug, because every one
    of its materials is laser so its item numbers and its packet numbers agree.
    """
    counters, out = {}, {}
    for key, e in sorted(pallet_map.items(), key=lambda kv: kv[1]["order"]):
        group = SAW_PALLET if e["saw"] else e["pallet"]
        counters[group] = counters.get(group, 0) + 1
        out[key] = f"{group}.{counters[group]}"
    return out


def _group_materials(tubes, pallet_map, root_922, batch_no, log):
    """-> [(serial, [tube, ...])], one entry per source material.

    Two separate decisions, in this order, and the order matters:

      1. The packet NAME (`2.3`, `SAW.1`) is worked out over TechDeck's own
         ordering - SAW first, biggest tube first - because that is what matched
         the hand-built `SAW.1`-`SAW.6` packets on batch 505. A name has to land
         the same whoever builds it, so nothing downstream may rename a file.
      2. The materials are THEN put in the Material Use Tracker's order, which
         is how the floor reads them: pallet 1, then 2, then 3, then SAW. That
         is the order the workbook's sheets and the report's groups come out in.
    """
    by_serial = {}
    for t in tubes:
        by_serial.setdefault(t["serial"], []).append(t)
    materials = sorted(
        by_serial.items(),
        key=lambda kv: (kv[1][0]["pallet"] != SAW_PALLET,
                        _size_key(kv[1][0]["desc"])))

    names = _packet_names(pallet_map)
    taken = set(names.values())
    counters = {}
    for _serial, entries in materials:
        entries.sort(key=lambda e: -(e["length"] or 0))
        pallet = entries[0]["pallet"]
        key = _norm_material(entries[0]["desc"])
        packet = names.get(key)
        while packet is None:                  # not on the organizer at all
            counters[pallet] = counters.get(pallet, 0) + 1
            candidate = f"{pallet}.{counters[pallet]}"
            if candidate not in taken:
                packet = candidate
                taken.add(packet)
        org = pallet_map.get(key)
        for e in entries:
            e["packet"] = packet
            # rows 1 and 2 of the sheet are the organizer's own words
            e["mat_text"] = org["text"] if org else f"HSS {e['desc']}"
            e["org_pallet"] = org["pallet"] if org else pallet

    tracker = _tracker_order(root_922, batch_no, log)
    if tracker:
        LAST = 10 ** 6

        def _pos(serial, desc):
            if serial in tracker:
                return tracker[serial]
            triple = _size_triple(desc)
            return tracker.get(triple, LAST) if triple else LAST

        materials.sort(key=lambda kv: _pos(kv[0], kv[1][0]["desc"]))
        by_size, strays = [], []
        for serial, entries in materials:
            if serial in tracker:
                continue
            (strays if _pos(serial, entries[0]["desc"]) == LAST
             else by_size).append(f"{serial} ({entries[0]['desc']})")
        for s in by_size:
            log(f"{s} is not on the tracker by item number - placed by its "
                f"size instead")
        if strays:
            log(f"{len(strays)} source material(s) are not on the tracker "
                f"sheet at all, so they come last: {', '.join(strays)}")
    return materials


# ───────────────────────────────────────────────────────────── the workbook

def _guard_output(dest: Path):
    """Refuse to write anything but our OWN two files.

    The Production Packets folder holds the hand-built cutting list and the
    finished SAW.n / n.n packet PDFs. This app only ever adds two files, both
    carrying "(TechDeck)" in the name, and it never merges, renames or deletes
    anything that is already in there.
    """
    if "(TechDeck)" not in dest.name and PACKETS_SUBFOLDER not in dest.parts:
        raise RuntimeError(
            f"refusing to write {dest.name} - this app only writes its own "
            f"'(TechDeck)' files into the Production Packets folder")
    return dest


def _safe_sheet(name, used):
    """A sheet name Excel will take, unique within the workbook."""
    bad = set("[]:*?/" + chr(92))
    title = "".join(ch for ch in str(name) if ch not in bad)[:31] or "Sheet"
    base, n = title, 2
    while title in used:
        title = f"{base[:27]} ({n})"
        n += 1
    used.add(title)
    return title


def _write_workbook(dest: Path, batch_no, materials, log):
    """One sheet per source material, formatted the way Carrie asked for.

    The sheet is named after its PACKET (`SAW.4`, `2.5`) and the source material
    number sits in A1, which is how she renamed the two sheets she marked up.
    Rows 1 and 2 are the Pallet Organizer's own words - the material line is
    copied from its MATERIAL REQUIRED entry, "(SAW CUT)" and all.

    A row the reader was unsure about gets an ARROW in the Problem? column
    instead of the yellow highlight we used before. The X in E1 then appears by
    formula, so a sheet with anything to look at says so at the top.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(style="thin")
    center = Alignment(horizontal="center", vertical="center")

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    flagged = 0
    for serial, entries in materials:
        saw = entries[0]["pallet"] == SAW_PALLET
        top, band = ((SAW_TOP, SAW_BAND) if saw else (LASER_TOP, LASER_BAND))
        ws = wb.create_sheet(_safe_sheet(entries[0]["packet"], used))
        for col, width in COL_WIDTHS.items():
            ws.column_dimensions[col].width = width

        # row 1 - the material number, the batch, and the problem flag
        ws.merge_cells("C1:D1")
        ws["A1"] = int(serial) if str(serial).isdigit() else serial
        ws["B1"] = "Electric Boat"
        ws["C1"] = f"Batch {batch_no}: Pallet {entries[0]['org_pallet']}"
        ws["E1"] = X_FORMULA
        for c in "ABCDE":
            cell = ws[f"{c}1"]
            cell.fill = PatternFill("solid", fgColor=top)
            cell.alignment = center
            cell.font = Font(name="Calibri", size=12, color="000000")
            cell.border = Border(top=thin, bottom=thin, right=thin,
                                 left=None if c == "D" else thin)
        ws["E1"].font = Font(name="Aharoni", size=18, bold=True, color=X_FONT)
        ws.row_dimensions[1].height = ROW_H

        # row 2 - the material exactly as the organizer writes it
        ws.merge_cells("A2:E2")
        ws["A2"] = entries[0]["mat_text"]
        for c in "ABCDE":
            cell = ws[f"{c}2"]
            cell.fill = PatternFill("solid", fgColor=band)
            cell.alignment = center
            cell.font = Font(name="Calibri", size=14, bold=True,
                             color="000000")
            cell.border = Border(top=thin, bottom=thin,
                                 left=thin if c == "A" else None,
                                 right=thin if c == "E" else None)
        ws.row_dimensions[2].height = ROW_H_TALL
        ws.row_dimensions[3].height = ROW_H

        # row 4 - the headers. The table is open on its left and right edges,
        # the way hers is, so only the inner lines are drawn.
        for c, text, size, color in (("A", "Problem?", 11, PROBLEM_FONT),
                                     ("B", "Parts Id.", 14, None),
                                     ("C", "Length", 14, None),
                                     ("D", "Quantity", 14, None)):
            cell = ws[f"{c}4"]
            cell.value = text
            cell.font = Font(name="Calibri", size=size, bold=True,
                             color=color or "000000")
            cell.alignment = center
            cell.border = Border(bottom=thin,
                                 left=thin if c in "BCD" else None,
                                 right=thin if c in "ABC" else None)
        ws.row_dimensions[4].height = ROW_H_TALL

        # the parts
        for i, e in enumerate(entries):
            r = 5 + i
            flag = bool(e["review"]) or e["length"] is None
            flagged += int(flag)
            cell = ws.cell(r, 1, ARROW if flag else None)
            cell.font = Font(name="Calibri", size=14, bold=True)
            cell.alignment = center
            cell.border = Border(top=thin, right=thin, bottom=thin)
            for col, value in ((2, e["part"]), (3, e["length"]), (4, e["qty"])):
                cell = ws.cell(r, col, value)
                cell.font = Font(name="Calibri", size=12, color="000000")
                cell.alignment = center
                cell.border = Border(top=thin, bottom=thin, left=thin,
                                     right=thin if col < 4 else None)
            ws.row_dimensions[r].height = ROW_H

    sdk.save_workbook(wb, _guard_output(dest), log=log)
    if flagged:
        log(f"{flagged} row(s) marked with an arrow in the Problem? column")
    return dest


# ──────────────────────────────────────────────────────────────── the report

def _write_report(dest: Path, batch_no, materials, no_sheet, log):
    """The colour-coded PDF, same shape as the LST Organizer's."""
    C = sdk.REPORT_COLORS
    flat = [e for _s, entries in materials for e in entries]
    review = [e for e in flat if e["review"] and e["length"] is not None]
    missing = [e for e in flat if e["length"] is None]
    unknown = [e for e in flat if e["pallet"] == "UNKNOWN"]
    # a tube with no drawing at all is already listed under "no drawing found";
    # these are the ones whose length IS good (read off an assembly sheet) but
    # that have no single-tube page for a binder
    _missing_parts = {e["part"] for e in missing}
    no_print = sorted((e for e in no_sheet
                       if e["part"] not in _missing_parts),
                      key=lambda e: e["part"])

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
        ("No print of their own to bind", len(no_print),
         C["extra_bg"] if no_print else C["ok_bg"],
         C["extra_tx"] if no_print else C["ok_tx"]),
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

    if no_print:
        d.text("No print of their own - not in a drawing binder", size=11,
               bold=True, color=C["extra_tx"])
        for line in ("The batch draws these tubes on an assembly sheet only, "
                     "so the length is good",
                     "but there is no single-tube page to bind. Their "
                     "assembly sheet is in the saw cut",
                     "packet; the laser binders are short by these parts."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Length", "Material", "Pallet", "Read from"], w5)
        for e in no_print:
            d.row([e["part"], "-" if e["length"] is None else str(e["length"]),
                   e["desc"], e["packet"], e["source"]], w5,
                  fill=C["extra_bg"], tcolor=C["extra_tx"])
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

    root_922 = sdk.resolve_922_root(settings.get("base_path", ""))
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

    materials = _group_materials(tubes, pallet_map, root_922, batch_no, log)
    progress_callback(80)

    out_dir = batch_path / f"Batch {batch_no} - Documentation" / PACKETS_FOLDER
    sdk.ensure_dir(out_dir)
    # a separate file from the hand-built "<batch> Tubes.xlsx", so the two can
    # be compared side by side and a human sheet is never written over
    book = _write_workbook(
        out_dir / f"{batch_no} Tubes (TechDeck).xlsx", batch_no, materials, log)
    progress_callback(85)

    log("Binding the packet drawings...")
    tube_parts = {t["part"] for t in tubes}
    drawings = pk.survey(batch_path, tube_parts, log=log,
                         cancel_event=cancel_event)
    packets, no_sheet = pk.build(out_dir / PACKETS_SUBFOLDER, batch_no,
                                 materials, drawings, log)
    log(f"{len(packets)} packet PDF(s), "
        f"{sum(n for _p, n in packets)} pages in total")
    progress_callback(95)

    # the report is written LAST on purpose: which tubes have no print of their
    # own is only known once the binders have been built, and the report is
    # where the reader goes looking for it
    report = _write_report(
        out_dir / f"Production Packets Report (TechDeck) - Batch {batch_no}.pdf",
        batch_no, materials, no_sheet, log)
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
