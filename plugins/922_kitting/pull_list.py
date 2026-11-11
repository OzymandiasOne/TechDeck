"""The material pull list - the cover sheet of the kitting paperwork.

Written from Carrie's own outline ("How to make a pull list for EB batches",
2026-11-10): open `QF-PR-10 - Material Pull List - Electric Boat`, open the
batch's `Material QTY` tab, carry the quantities across, check the batch
number, print. TechDeck does the carrying, so nothing is mistyped on the way -
her own filled 511 copy carries a 14 where the tab says 24.

The template is HER live file in `Notes\\Pull list`. It is an ISO-controlled
form (QF-PR-10 rev B), so a frozen copy shipped with the plugin would go stale
the day the form revs: it is read fresh every run and NEVER written - the fill
happens on a staged copy, in Excel COM, because the form carries drawn shapes
that an openpyxl round trip silently drops.

Two pull sheets, split by what the id looks like. A bare numeric serial
(218019941, 211031592) is warehouse stock - the `Tube Pull List`; anything
else (262028653-12) is a mount-kit item - the `Plate-Rod Pull List`. Checked
against her filled 511 copy: same split, row for row. Sizes come from the
template's own lookup sheets where the id is known there, and from the
organizer itself where it is not (`PO Info Drop` Base Material for a serial,
`Source Material Info` SCRIBE DESCRIPTION for a mount id); an id neither
knows is named in the console so she can write the size in by hand - the row
still lands, with its quantity.

Everything here is read-only except the staged copy of the template.
"""
from pathlib import Path

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:                       # standalone / CLI testing
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

MATERIAL_QTY_SHEET = "Material QTY"
TUBE_SHEET = "Tube Pull List"
PLATE_SHEET = "Plate-Rod Pull List"
TUBE_LOOKUP = "Tube Material List"
PLATE_LOOKUP = "Plate-Rod Material List"
SOURCE_INFO_SHEET = "Source Material Info"

# the SIZE / DESCRIPTION cell of a row whose id the template's lookup sheet
# knows - the same formulas Carrie's own filled copies use
TUBE_SIZE_FORMULA = "=VLOOKUP(B{r},'{lk}'!A:D,4,FALSE)"
# The template's own MW ITEM # formula looks the id up in a lookup column
# that holds only the text "N/A", so it prints #N/A on every row - Carrie's
# filled copies carry that error code. The cell is left BLANK instead; if
# the lookup sheet ever gains real MW numbers, revisit.
PLATE_DESC_FORMULA = "=VLOOKUP(B{r},'{lk}'!B:C,2,FALSE)"


def find_template(root_922):
    """Carrie's live QF-PR-10 workbook, or None. The `Mount` variant is a
    different form and is deliberately not matched."""
    if root_922 is None:
        return None
    folder = Path(root_922) / "Notes" / "Pull list"
    hits = [p for p in folder.glob("*Material Pull List*Electric Boat*.xlsx")
            if not p.name.startswith("~$") and "MOUNT" not in p.name.upper()]
    return hits[0] if hits else None


def read_material_qty(workbook_path, log):
    """[(id text, qty)] off the organizer's Material QTY tab, in sheet order.

    The tab is a pivot: `Source Material` / `Sum of QTY`, ending on a
    `Grand Total` row that is the pivot's own arithmetic, not a material.
    """
    wb = sdk.load_workbook_resilient(workbook_path, read_only=True,
                                     data_only=True, log=log)
    try:
        sheet = next((n for n in sdk.visible_sheetnames(wb)
                      if n.strip().upper() == MATERIAL_QTY_SHEET.upper()),
                     None)
        if sheet is None:
            return None                           # the caller says so
        ws = wb[sheet]
        header_row, cols = sdk.find_header_row(
            ws, ["Source Material", "Sum of QTY"])
        if header_row is None:
            return None
        c_id, c_qty = cols["SOURCE MATERIAL"], cols["SUM OF QTY"]
        out = []
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
            def _v(c):
                v = r[c - 1] if c - 1 < len(r) else None
                return "" if v is None else str(v).strip()
            mid = _v(c_id).split(".")[0] if _v(c_id).replace(".", "", 1) \
                .isdigit() else _v(c_id)
            if not mid:
                continue
            if mid.upper().startswith("GRAND TOTAL"):
                break
            try:
                qty = int(float(_v(c_qty) or 0))
            except ValueError:
                qty = 0
            out.append((mid, qty))
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


def split_materials(rows):
    """(tubes, plates): a bare numeric id is pulled by size off the Tube Pull
    List; anything else is a mount-kit item for the Plate-Rod one."""
    tubes = [(m, q) for m, q in rows if str(m).isdigit()]
    plates = [(m, q) for m, q in rows if not str(m).isdigit()]
    return tubes, plates


def plan_rows(entries, known, fallback, slots):
    """-> (plan, overflow, hand_sizes) for one pull sheet.

    plan rows are (id, qty, desc): desc None = the template's own VLOOKUP
    does the work; text = written literally (the organizer's wording);
    "" = nobody knows the size - the row still lands, named for a hand fill.
    """
    plan, overflow, hand = [], [], []
    for mid, qty in entries:
        if len(plan) >= slots:
            overflow.append(mid)
            continue
        if str(mid) in known:
            plan.append((mid, qty, None))
            continue
        desc = str(fallback.get(str(mid), "") or "").strip()
        if not desc:
            hand.append(mid)
        plan.append((mid, qty, desc))
    return plan, overflow, hand


def _anchors(ws):
    """Where one pull sheet keeps things, found by TEXT (Hard Rule 2): the
    ISO form revs, so no row number is trusted.

    -> {"batch": "I6", "row0": 9, "row1": 27, "cols": {header: letter}}
    """
    from openpyxl.utils import get_column_letter
    batch, header_row, end_row, cols = None, None, None, {}
    for row in ws.iter_rows():
        for c in row:
            text = str(c.value or "").strip().upper()
            if not text:
                continue
            if text.startswith("BATCH #") and batch is None:
                batch = f"{get_column_letter(c.column + 1)}{c.row}"
            if text.startswith("SOURCE MATERIAL") and header_row is None:
                header_row = c.row
            if text.startswith("SECTION 2") and end_row is None:
                end_row = c.row - 1
        if batch and header_row and end_row:
            break
    if not (batch and header_row and end_row):
        return None
    for c in ws[header_row]:
        text = str(c.value or "").strip().upper().rstrip(" #")
        if text:
            cols.setdefault(text, get_column_letter(c.column))
    return {"batch": batch, "row0": header_row + 1, "row1": end_row,
            "cols": cols}


def read_template(template_path, log):
    """One read of Carrie's template: both sheets' anchors + the ids their
    lookup sheets know. None (with a log line) when the form has moved so far
    the anchors are gone - the caller skips the cover rather than guessing."""
    wb = sdk.load_workbook_resilient(template_path, read_only=False,
                                     data_only=False, log=log)
    try:
        out = {}
        for sheet, lookup, id_col in ((TUBE_SHEET, TUBE_LOOKUP, "A"),
                                      (PLATE_SHEET, PLATE_LOOKUP, "B")):
            if sheet not in wb.sheetnames or lookup not in wb.sheetnames:
                log(f"WARNING: {template_path.name} has no '{sheet}' or "
                    f"'{lookup}' sheet - no pull list cover")
                return None
            anchors = _anchors(wb[sheet])
            if anchors is None:
                log(f"WARNING: could not find the BATCH #, SOURCE MATERIAL "
                    f"and Section 2 anchors on '{sheet}' - no pull list cover")
                return None
            # an id counts as known ONLY when the lookup cell holds it
            # clean: '262028653-37' is in the list with a trailing TAB, so
            # Excel's exact-match VLOOKUP misses it and prints #N/A - the
            # wall Carrie's own filled copies hit. A polluted id falls back
            # to the organizer's wording, written as plain text.
            known = set()
            col = 1 if id_col == "A" else 2
            for row in wb[lookup].iter_rows(min_row=2, min_col=col,
                                            max_col=col, values_only=True):
                raw = "" if row[0] is None else str(row[0])
                if raw and raw == raw.strip():
                    known.add(raw.split(".")[0])
            out[sheet] = {"anchors": anchors, "known": known,
                          "lookup": lookup}
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


def desc_maps(organizer_path, log):
    """(tube serial -> Base Material, mount id -> SCRIBE DESCRIPTION) off the
    batch's own organizer, for ids the template's lookup sheets do not know."""
    tubes, plates = {}, {}
    wb = sdk.load_workbook_resilient(organizer_path, read_only=True,
                                     data_only=True, log=log)
    try:
        if "PO Info Drop" in wb.sheetnames:
            ws = wb["PO Info Drop"]
            header_row, cols = sdk.find_header_row(
                ws, ["SOURCE MATERIAL", "Base Material"])
            if header_row is not None:
                c_src, c_base = cols["SOURCE MATERIAL"], cols["BASE MATERIAL"]
                for r in ws.iter_rows(min_row=header_row + 1,
                                      values_only=True):
                    src = r[c_src - 1] if c_src - 1 < len(r) else None
                    base = r[c_base - 1] if c_base - 1 < len(r) else None
                    if src and base:
                        tubes.setdefault(
                            str(src).strip().split(".")[0],
                            " ".join(str(base).split()))
        sheet = next((n for n in wb.sheetnames
                      if n.strip().upper() == SOURCE_INFO_SHEET.upper()), None)
        if sheet is not None:
            ws = wb[sheet]
            header_row, cols = sdk.find_header_row(
                ws, ["Material", "SCRIBE DESCRIPTION"])
            if header_row is not None:
                c_id, c_desc = cols["MATERIAL"], cols["SCRIBE DESCRIPTION"]
                for r in ws.iter_rows(min_row=header_row + 1,
                                      values_only=True):
                    mid = r[c_id - 1] if c_id - 1 < len(r) else None
                    desc = r[c_desc - 1] if c_desc - 1 < len(r) else None
                    if mid and desc:
                        plates.setdefault(str(mid).strip(),
                                          " ".join(str(desc).split()))
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return tubes, plates


def _fill_sheet(ws, anchors, plan, batch_no, lookup, is_tube):
    """Write one pull sheet of the STAGED COPY through COM: the batch cell,
    then a clean data window - every leftover row of whichever batch Carrie
    filled last is cleared, broken `#REF!` formulas included."""
    cols = anchors["cols"]
    r0, r1 = anchors["row0"], anchors["row1"]
    id_col = cols.get("SOURCE MATERIAL", "B")
    qty_col = cols.get("QTY", "D" if is_tube else "H")
    desc_col = cols.get("SIZE" if is_tube else "DESCRIPTION",
                        "E" if is_tube else "D")

    ws.Range(anchors["batch"]).Value = f"{batch_no} KIT"
    # ONE rectangle over the whole data window: the form merges cells inside
    # it (B:C, E:G, I:J), and clearing a single column that cuts through a
    # merge is an Excel error. A rectangle that CONTAINS the merges is fine -
    # one column past the rightmost header catches its merge partner.
    from openpyxl.utils import column_index_from_string, get_column_letter
    last = max(column_index_from_string(c) for c in cols.values())
    ws.Range(f"A{r0}:{get_column_letter(last + 1)}{r1}").ClearContents()

    for i, (mid, qty, desc) in enumerate(plan):
        r = r0 + i
        ws.Range(f"{id_col}{r}").Value = (int(mid) if str(mid).isdigit()
                                          else str(mid))
        ws.Range(f"{qty_col}{r}").Value = int(qty)
        if desc is None:
            formula = (TUBE_SIZE_FORMULA if is_tube
                       else PLATE_DESC_FORMULA).format(r=r, lk=lookup)
            ws.Range(f"{desc_col}{r}").Formula = formula
        elif desc:
            ws.Range(f"{desc_col}{r}").Value = desc


def build_cover(excel, template_path, template_info, stage_dir, batch_no,
                qty_rows, tube_desc, plate_desc, log):
    """Fill a staged copy of the template and export the cover PDF.

    -> (cover_pdf, filled_xlsx, hand_sizes) - hand_sizes names the ids whose
    size nobody knew, which the caller reports. Raises on a COM failure; the
    caller treats any raise as "no cover", because the kitting paperwork must
    still print.
    """
    import fitz

    tubes, plates = split_materials(qty_rows)
    staged = Path(stage_dir) / template_path.name
    sdk.copy_resilient(template_path, staged, log)

    plans, hand_all, overflow_all = {}, [], []
    for sheet, entries, fallback in ((TUBE_SHEET, tubes, tube_desc),
                                     (PLATE_SHEET, plates, plate_desc)):
        info = template_info[sheet]
        slots = info["anchors"]["row1"] - info["anchors"]["row0"] + 1
        plan, overflow, hand = plan_rows(entries, info["known"], fallback,
                                         slots)
        plans[sheet] = plan
        hand_all += hand
        overflow_all += overflow
    if overflow_all:
        log(f"WARNING: {len(overflow_all)} material(s) do not fit on the "
            f"pull list form and are NOT on it - add them by hand: "
            f"{', '.join(str(m) for m in overflow_all)}")

    wb = excel.Workbooks.Open(str(staged))
    pdfs = []
    try:
        for sheet in (TUBE_SHEET, PLATE_SHEET):
            if not plans[sheet]:
                log(f"  {sheet}: nothing on this batch - page skipped")
                continue
            info = template_info[sheet]
            ws = wb.Worksheets(sheet)
            _fill_sheet(ws, info["anchors"], plans[sheet], batch_no,
                        info["lookup"], is_tube=(sheet == TUBE_SHEET))
            pdf = Path(stage_dir) / f"pull_{sheet}.pdf"
            ws.ExportAsFixedFormat(0, str(pdf))
            pdfs.append(pdf)
            log(f"  {sheet}: {len(plans[sheet])} material(s)")
        wb.Save()
    finally:
        try:
            wb.Close(False)
        except Exception:
            pass

    if not pdfs:
        return None, None, hand_all
    cover = Path(stage_dir) / "pull_list_cover.pdf"
    merged = fitz.open()
    try:
        for p in pdfs:
            sdk.ensure_local(p)
            src = fitz.open(str(p))
            try:
                merged.insert_pdf(src)
            finally:
                src.close()
        merged.save(str(cover))
    finally:
        merged.close()
    return cover, staged, hand_all
