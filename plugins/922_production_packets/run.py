"""922 Production Packets - the tube cutting list a batch feeds to the optimizer.

What it builds
--------------
`<batch> Tubes.xlsx` in the batch's `Production Packets` folder: one sheet per
source material PER PALLET, named after its packet (`SAW.4`, `2.5`), carrying
the material number, the batch and the pallet across the top and then part
name, saw cut length, quantity and the order it came in on - Carrie's
formatting, lifted from the two sheets she marked up. A row worth a second look
gets an arrow in the Problem? column, which brings up the X at the top of the
sheet.

A material whose parts fill one pallet and spill onto the next is listed twice
(or three times) by the Pallet Organizer, and each listing gets its own sheet
and its own binder - `1.3`, `2.3`, `3.1` for one size on batch 506. Which
pallet a given tube sits on comes from its ORDER, which the organizer's top
half files under exactly one pallet.
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

_RS_SPEC = _ilu.spec_from_file_location(
    'techdeck_922_runsheets',
    Path(__file__).resolve().parent / 'runsheets.py')
assert _RS_SPEC is not None and _RS_SPEC.loader is not None
rs = _ilu.module_from_spec(_RS_SPEC)
_RS_SPEC.loader.exec_module(rs)

VERSION = "1.12.0"

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
# E is the Order column, added after Quantity so Carrie's Parts Id. / Length /
# Quantity stay in the columns she put them in (Anthony, 2026-10-30). The X
# moves along to F, keeping it at the end of the table.
COL_WIDTHS = {"A": 12.43, "B": 20.71, "C": 10.86, "D": 13.14, "E": 13.14,
              "F": 10.71}
X_CELL = "F1"
LAST_COL = "F"
DATA_COLS = "ABCDE"
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
    # a ROUND tube is `1.66 OD X 0.166` - diameter and wall, two numbers and no
    # second side. Batch 486 carries one (211031252). Giving it a 0 middle
    # keeps it a distinct key from any square tube rather than no key at all,
    # which is what dropped it out of its pallet group.
    if "OD" in t and len(nums) == 2:
        nums = [nums[0], 0.0, nums[1]]
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
        c_pallet = cols.get("PALLET")
        order, n = {}, 0
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
            def _v(c):
                v = r[c - 1] if c and c - 1 < len(r) else None
                return "" if v is None else str(v).strip()
            # the serial comes back as a float on some rows (218012959.0), and
            # the lower half of the sheet holds plate/rod tags, not serials
            serial = _v(c_item).split(".")[0]
            if not serial.isdigit():
                continue
            # the tracker lists a material once per PALLET it lands on, so the
            # pallet is part of the key - otherwise a material split across
            # pallets 2 and 3 gives both its sheets pallet 2's position
            pallet = _v(c_pallet).upper().replace("PALLET", "").strip()
            triple = _size_triple(_v(c_size))
            for key in ((pallet, serial), serial,
                        (pallet, triple) if triple else None,
                        # the SIZE is the fallback: batch 505's tracker stocks
                        # 3.0 X 3.0 X 0.25 under item 218136140 while the PO
                        # calls it 218003095, and without this that material
                        # drops out of its pallet group
                        triple):
                if key is not None:
                    order.setdefault(key, n)
            n += 1
    finally:
        wb.close()
    log(f"Sheet order from {hits[0].name} sheet '{batch_no}' "
        f"({len(order)} materials)")
    return order


def _read_tubes(path: Path, log):
    """Every TUBE on the batch, from the organizer's PO Info Drop.

    Returns `(rows, skipped, all_parts)` - `[{part, order, serial, desc,
    qty}]`, the rows left behind although their SOURCE MATERIAL is a serial
    `sdk.tube_class` knows as a tube, and every part number on the sheet
    whatever it is made of (`_diagnose_no_sheet` needs the plate and rod
    numbers too).

    A row is a tube when it carries a Base Material - the organizer fills that
    column for tubes only, which is how the plate and rod lines are left
    behind. Columns are looked up by header NAME (Hard Rule 1).

    **That one column is the only thing marking a row as a tube**, so a row it
    was not filled on vanishes. Checked against all 19 batches on the drive on
    2026-10-30: no batch drops SOME of its tubes, and batch 503 (where the
    column is empty on all 61 tube rows) reads zero tubes and fails loudly. But
    nothing was WATCHING for it, so `skipped` now is, and the report names them.
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

        rows, skipped, seen, all_parts = [], [], set(), set()
        for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
            def _v(c):
                v = r[c - 1] if c - 1 < len(r) else None
                return "" if v is None else str(v).strip()
            part, serial, base = _v(c_dypn), _v(c_src), _v(c_base)
            if part:
                # every part on the PO, plate and rod included - a part number
                # the PO already uses is not a candidate for "this tube is
                # probably mis-numbered" (see _diagnose_no_sheet)
                all_parts.add(part.upper())
            if not part or not serial or not base:
                # a row with a part number and a serial TechDeck knows as a
                # tube, but no Base Material, is a tube that would vanish
                if (part and serial
                        and sdk.tube_class(serial.split(".")[0]) is not None):
                    skipped.append({"part": part.upper(), "order": _v(c_order),
                                    "serial": serial.split(".")[0],
                                    "desc": "", "qty": 1})
                continue
            serial = serial.split(".")[0]          # Excel hands back 218012959.0
            # the ORDER is part of the key: the same part on TWO orders is two
            # physical tubes, and keying on (part, serial) alone dropped the
            # second - batch 511 carried H7652061-H12-4A on FK409785 AND
            # X8385397, the cutting list said one tube, and the binder held
            # one print (Carrie, 2026-11-09). Only a literal repeat of the
            # same row is a duplicate.
            key = (part.upper(), serial, _v(c_order).upper())
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
    repeats = {}
    for row in rows:
        repeats.setdefault((row["part"], row["serial"]), []).append(row["order"])
    for (part, _s), orders in sorted(repeats.items()):
        if len(orders) > 1:
            log(f"{part} is on {len(orders)} orders ({', '.join(orders)}) - "
                f"one tube to cut and one print to bind for each")
    if skipped:
        log(f"WARNING: {len(skipped)} row(s) on '{INFO_SHEET}' carry a tube "
            f"source material but no Base Material, so they are NOT on the "
            f"cutting list - fill that column in and run again:")
        for e in skipped:
            log(f"    {e['part']}  (material {e['serial']})")
    return rows, skipped, all_parts


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
    # THK is the same noise word as NOM: batch 391's PO writes
    # `3.0 X 3.0 X 0.50 THK` where the organizer writes `... NOM`, and keeping
    # it meant the two never matched and the material fell to UNKNOWN
    # (found in the 380-502 sweep, 2026-10-30)
    t = re.sub(r"\bHSS\b|\bNOM\b|\bTHK\b|,", " ", t)
    t = re.sub(r"\s*X\s*", " X ", t)
    return " ".join(t.split())


def _read_pallets(path: Path, log):
    """Read both halves of the Pallet Organizer sheet.

    Returns `(pallet_map, order_pallets)`:

      * `pallet_map` - `{normalised material: [entry, ...]}`, one entry per
        pallet the material is listed under, in the organizer's own order.
      * `order_pallets` - `{order number: pallet}` from the sheet's TOP half,
        which is how a single tube is tied to a single pallet.

    The lower half lists the source materials each pallet needs, numbered,
    under a 'MATERIAL REQUIRED' heading per pallet; the upper half lists that
    pallet's orders and the materials each one uses. The heading and the
    'PALLET n' title above it are found by TEXT, never by cell address (Hard
    Rule 1) - both blocks move as the batch's order count changes.

    **A material is listed under every pallet that needs it.** When its parts
    fill one pallet and spill onto the next, the organizer writes it out again
    (Anthony, 2026-10-29) - 11 of the 19 batches on the drive do this, and
    `2.0 X 2.0 X 0.188` is the usual one. Keeping only the first listing threw
    whole pallets away: batch 506 reported "2 pallets" with three on the sheet.
    So every listing is kept and each one becomes its own packet.
    """
    import re
    wb = sdk.load_workbook_resilient(path, read_only=False, data_only=True, log=log)
    try:
        sheet = next((n for n in sdk.visible_sheetnames(wb)
                      if n.strip().upper() == "PALLET ORGANIZER"), None)
        if sheet is None:
            log("WARNING: no 'Pallet Organizer' sheet - pallet numbers skipped")
            return {}, {}
        ws = wb[sheet]
        heads = []
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and "MATERIAL REQUIRED" in                         cell.value.upper():
                    heads.append((cell.row, cell.column))
        out, order_pallets, order = {}, {}, 0
        for r0, c0 in heads:
            pallet, title_row = None, None
            for r in range(r0 - 1, 0, -1):
                v = ws.cell(r, c0).value
                m = re.search(r"PALLET\s*(\d+)", str(v or "").upper())
                if m:
                    pallet = m.group(1)
                    title_row = r
                    break
            if pallet is None or title_row is None:
                continue
            # the TOP half: this pallet's order numbers, in the same column as
            # its title, between the title and the MATERIAL REQUIRED heading
            for r in range(title_row + 1, r0):
                v = ws.cell(r, c0).value
                num = str(v or "").strip()
                if num and not num.replace(".", "", 1).isdigit():
                    order_pallets.setdefault(num.upper(), pallet)
            for r in range(r0 + 1, r0 + 40):
                desc = ws.cell(r, c0 + 1).value
                if desc is None or not str(desc).strip():
                    continue
                text = str(desc).strip()
                key = _norm_material(desc)
                seen = out.setdefault(key, [])
                if any(e["pallet"] == pallet for e in seen):
                    continue              # the same material twice on one pallet
                # the organizer's own item number is kept for the record, but it
                # is NOT the packet number - see _packet_names
                seen.append({"pallet": pallet,
                             "idx": str(ws.cell(r, c0).value or "").strip(),
                             "order": order,
                             "text": text,
                             "saw": "SAW CUT" in text.upper()})
                order += 1
        pallets = {e["pallet"] for v in out.values() for e in v}
        log(f"Pallet map: {len(out)} materials across {len(pallets)} pallets, "
            f"{len(order_pallets)} orders")
        for key, entries in sorted(out.items(),
                                   key=lambda kv: kv[1][0]["order"]):
            if len(entries) > 1:
                log(f"{key} fills more than one pallet "
                    f"({', '.join(e['pallet'] for e in entries)}) - it gets a "
                    f"sheet and a packet per pallet")
        return out, order_pallets
    finally:
        wb.close()


def read_cover_blocks(path: Path, log):
    """-> {pallet: {"listing": [(order, material)], "materials": [text, ...]}}

    What a production run COVER PAGE says, straight off the Pallet Organizer.
    Carrie builds that page by pasting two things into a Word table: the
    pallet's column of order numbers with the material each one uses, and the
    `MATERIAL REQUIRED` block under it. Both are already on the sheet, so step
    2 reads them rather than asking anybody to paste anything.

    Same TEXT-anchored walk as `_read_pallets` (Hard Rule 1) - the blocks move
    down the sheet as a batch's order count changes, so neither the title nor
    the heading can be a cell address.
    """
    import re
    wb = sdk.load_workbook_resilient(path, read_only=False, data_only=True,
                                     log=log)
    try:
        sheet = next((n for n in sdk.visible_sheetnames(wb)
                      if n.strip().upper() == "PALLET ORGANIZER"), None)
        if sheet is None:
            log("WARNING: no 'Pallet Organizer' sheet - no cover pages")
            return {}
        ws = wb[sheet]
        heads = []
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and                         "MATERIAL REQUIRED" in cell.value.upper():
                    heads.append((cell.row, cell.column))
        out = {}
        for r0, c0 in heads:
            pallet, title_row = None, None
            for r in range(r0 - 1, 0, -1):
                m = re.search(r"PALLET\s*(\d+)",
                              str(ws.cell(r, c0).value or "").upper())
                if m:
                    pallet, title_row = m.group(1), r
                    break
            if pallet is None or title_row is None:
                continue
            listing = []
            for r in range(title_row + 1, r0):
                num = str(ws.cell(r, c0).value or "").strip()
                if not num or num.replace(".", "", 1).isdigit():
                    continue
                listing.append((num, str(ws.cell(r, c0 + 1).value or "").strip()))
            materials = []
            for r in range(r0 + 1, r0 + 40):
                desc = ws.cell(r, c0 + 1).value
                if desc is None or not str(desc).strip():
                    continue
                materials.append(str(desc).strip())
            out[pallet] = {"listing": listing, "materials": materials}
        log(f"Cover blocks: {len(out)} pallet(s) - "
            + ", ".join(f"{p} ({len(v['listing'])} orders, "
                        f"{len(v['materials'])} materials)"
                        for p, v in sorted(out.items())))
        return out
    finally:
        wb.close()


def _pallet_of(serial, desc, pallet_map, order_pallets=None, order=""):
    """Which packet group ONE TUBE belongs to.

    The organizer decides: it writes "(SAW CUT)" after the materials that go to
    the saw, and SAW counts as its own packet group for this process even though
    those materials ride on pallet 1. A saw material is therefore never split,
    however many pallets it is listed under.

    Everything else takes the pallet number the organizer gave it. Where the
    material is listed under SEVERAL pallets its parts are split between them,
    and the tube's own ORDER says which one it is on: the sheet's top half
    files every order under exactly one pallet. On batch 506 all 36 orders
    matched, so this is the organizer's own answer, not a guess.

    `sdk.tube_class` is only the fallback for a material the organizer does not
    list at all; anything neither knows is reported, never guessed at.
    """
    hits = pallet_map.get(_norm_material(desc)) or []
    if hits:
        if any(e["saw"] for e in hits):
            return SAW_PALLET
        pallets = [e["pallet"] for e in hits]
        if len(pallets) > 1:
            mine = (order_pallets or {}).get(str(order or "").strip().upper())
            if mine in pallets:
                return mine
        return pallets[0]
    if sdk.tube_class(serial) == "oversized":
        return SAW_PALLET
    return "UNKNOWN"


def _packet_names(pallet_map):
    """{(normalised material, group): packet name} - `SAW.1`, `1.1`, `2.3`.

    Numbered FRESH per group, walking the organizer's MATERIAL REQUIRED list in
    its own order: the saw cut materials become SAW.1, SAW.2 ... and the rest are
    numbered within their own pallet.

    The organizer's own item number is NOT the packet number, which cost a
    wrong file name. Batch 505's pallet 1 lists seven materials - six saw cut,
    and one laser one sitting at position 5 - and the hand-built packet for that
    laser material is `1.1`, not `1.5`. Pallet 2 hid the bug, because every one
    of its materials is laser so its item numbers and its packet numbers agree.

    A material listed under several pallets earns a name on EACH of them, which
    is why the key carries the group: batch 506's `2.0 X 2.0 X 0.188` is `1.3`,
    `2.3` and `3.1`. A SAW material is one group however many pallets list it,
    so it is numbered once.
    """
    flat = [(key, e) for key, entries in pallet_map.items() for e in entries]
    counters, out = {}, {}
    for key, e in sorted(flat, key=lambda kv: kv[1]["order"]):
        group = SAW_PALLET if e["saw"] else e["pallet"]
        if (key, group) in out:
            continue
        counters[group] = counters.get(group, 0) + 1
        out[(key, group)] = f"{group}.{counters[group]}"
    return out


def _diagnose_no_sheet(batch_path: Path, no_sheet, all_parts, log):
    """Say WHY a tube reached no binder - and name the part it probably is.

    Two very different things were both reported as "no individual drawing":

      * **the PO's part number is wrong.** Batch 507's PO Info Drop has the
        tube suffixes of two assemblies swapped: it says `H7421762-H55` needs
        -5 and -8 while the batch carries sheets for -4, -6 and -10, and says
        `H7421762-H54` needs -4 and -10 while that one has -6 and -8. Carrie
        corrected exactly that by hand (`-5`->`-4`, `-8`->`-6`, plus `-10`), so
        the drawings are right and the paperwork is wrong. Detectable: the
        assembly HAS sheets, just for suffixes no tube on the PO claims.
      * **the prints are genuinely missing.** `H7212562-H780-12/13/14` and
        `R6511964-H7-3A` have no sheet for their assembly at all, so there is
        nothing to suggest and somebody has to go and find the print.

    Annotates each entry with `why` and `suggest`, read-only, file NAMES only -
    no PDF is opened.
    """
    import re
    suf = re.compile(r"^(.+)-(\d+[A-Z]?)$")

    sheets, claimed = {}, {}
    for p in Path(batch_path).rglob("*.pdf"):
        if "CAD-AND-SHOP-PRINTS" not in str(p).upper():
            continue
        m = suf.match(p.stem.upper())
        if m:
            sheets.setdefault(m.group(1), set()).add(m.group(2))
    # EVERY part on the PO, plate and rod included: batch 507's
    # `H7421762-H55-2` is a plate, so it is not a candidate tube number even
    # though a sheet for it exists
    for part in all_parts:
        m = suf.match(str(part).upper())
        if m:
            claimed.setdefault(m.group(1), set()).add(m.group(2))

    wrong, absent = [], []
    for e in no_sheet:
        m = suf.match(e["part"].upper())
        stem = m.group(1) if m else e["part"].upper()
        spare = sorted((sheets.get(stem) or set())
                       - (claimed.get(stem) or set()),
                       key=lambda s: (int(re.sub(r"\D", "", s) or 0), s))
        if spare:
            e["why"] = "part number looks wrong"
            e["suggest"] = ", ".join(f"{stem}-{s}" for s in spare)
            wrong.append(e)
        else:
            e["why"] = ("no print for this assembly at all"
                        if not sheets.get(stem) else "no sheet for this part")
            e["suggest"] = ""
            absent.append(e)

    if wrong:
        log(f"{len(wrong)} tube(s) have no drawing, but their assembly DOES - "
            f"the PO's part number is probably wrong:")
        for e in wrong:
            log(f"    {e['part']} -> the batch has {e['suggest']}")
    if absent:
        log(f"{len(absent)} tube(s) have no print anywhere in the batch - "
            f"somebody has to find those:")
        for e in absent:
            log(f"    {e['part']}  ({e['desc']})")
    return no_sheet


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
    # One group per (SIZE, pallet). A material whose parts spill onto the next
    # pallet is listed again by the organizer and gets its own sheet and its
    # own binder for each (Anthony, 2026-10-29).
    #
    # The key is the SIZE, not the serial, because one physical size can carry
    # two serials: 218003095 was retired in favour of 218136140 for
    # 3.0 X 3.0 X 0.25, and an old repeat's print still says the old number
    # (Carrie, 2026-10-30). Keying on the serial made two groups claim ONE
    # packet name, and the second binder overwrote the first on disk -
    # batches 426, 474, 491, 496 and 497 all did this. The size is also what
    # `_packet_names` keys on, so a collision is now impossible by
    # construction. The floor merges them by hand too (474, 497).
    by_group = {}
    for t in tubes:
        by_group.setdefault((_norm_material(t["desc"]), t["pallet"]),
                            []).append(t)
    groups = sorted(
        by_group.values(),
        key=lambda v: (v[0]["pallet"] != SAW_PALLET,
                       _size_key(v[0]["desc"]), v[0]["pallet"]))

    materials = []
    for v in groups:
        serials = sorted({sdk.canonical_tube_material(e["serial"])
                          for e in v})
        raw = sorted({e["serial"] for e in v})
        for e in v:
            e["serials"] = raw
        materials.append((serials[0] if len(serials) == 1
                          else " / ".join(serials), v))

    names = _packet_names(pallet_map)
    taken = set(names.values())
    counters = {}
    for _serial, entries in materials:
        entries.sort(key=lambda e: -(e["length"] or 0))
        pallet = entries[0]["pallet"]
        key = _norm_material(entries[0]["desc"])
        packet = names.get((key, pallet))
        while packet is None:                  # not on the organizer at all
            counters[pallet] = counters.get(pallet, 0) + 1
            candidate = f"{pallet}.{counters[pallet]}"
            if candidate not in taken:
                packet = candidate
                taken.add(packet)
        hits = pallet_map.get(key) or []
        org = next((e for e in hits
                    if (SAW_PALLET if e["saw"] else e["pallet"]) == pallet),
                   hits[0] if hits else None)
        for e in entries:
            e["packet"] = packet
            # rows 1 and 2 of the sheet are the organizer's own words
            e["mat_text"] = org["text"] if org else f"HSS {e['desc']}"
            e["org_pallet"] = org["pallet"] if org else pallet
            # two safeguards against a NEW or unknown tube material slipping
            # through quietly (Anthony, 2026-10-30):
            #   off_organizer - the Pallet Organizer does not list this
            #     material at all, so its pallet came from TechDeck's own
            #     sdk.tube_class list, not from the paperwork
            #   new_material  - neither SDK list has this serial. Batch 495
            #     carries 211002778 (6.0 X 8.0 X 0.50), one digit off the
            #     218002778 that IS listed, and nothing said a word
            e["off_organizer"] = org is None
            e["new_material"] = sdk.tube_class(e["serial"]) is None

    # Two sheets sharing a packet name means two binders sharing a FILE name,
    # and the second silently overwrote the first (batches 426, 474, 491, 496,
    # 497 before the group key became the size). Keyed on the size this cannot
    # happen, so if it ever does the run says so instead of losing a file.
    _seen = {}
    for serial, entries in materials:
        p = entries[0]["packet"]
        if p in _seen:
            log(f"WARNING: packet {p} is claimed by both {_seen[p]} and "
                f"{serial} - their binders would overwrite each other. "
                f"Treat this batch's packets as incomplete and report it")
        _seen[p] = serial

    # a merged group carries a retired serial AND the current one. Carrie's
    # standing job is to restamp those old repeat prints, so name them.
    for serial, entries in materials:
        raw = entries[0].get("serials") or []
        if len(raw) > 1:
            old = [s for s in raw if s in sdk.TUBE_MATERIAL_ALIASES]
            log(f"{entries[0]['desc']} on pallet {entries[0]['pallet']} comes "
                f"in under {len(raw)} serials ({', '.join(raw)}) - one sheet "
                f"and one packet, filed as {serial}"
                + (f". The print(s) still saying {', '.join(old)} want "
                   f"restamping" if old else ""))

    off = sorted({(e["serial"], e["desc"]) for _s, en in materials
                  for e in en if e["off_organizer"]})
    for serial, desc in off:
        log(f"WARNING: {serial} ({desc}) is not on the Pallet Organizer's "
            f"MATERIAL REQUIRED list - TechDeck filed it from its own tube "
            f"list instead. Add it to the organizer so the paperwork agrees")
    new = sorted({(e["serial"], e["desc"]) for _s, en in materials
                  for e in en if e["new_material"]})
    for serial, desc in new:
        log(f"WARNING: {serial} ({desc}) is a tube material TechDeck has "
            f"never seen - add it to the SDK's tube material lists")

    tracker = _tracker_order(root_922, batch_no, log)
    if tracker:
        LAST = 10 ** 6

        def _pos(entries):
            """The group's spot on the tracker, by any serial it carries.

            A merged group holds both the retired serial and the current one,
            and the tracker may list either, so every one is tried before the
            size fallback.
            """
            e0 = entries[0]
            pallet, desc = e0["pallet"], e0["desc"]
            serials = list(e0.get("serials") or [])
            serials += [sdk.canonical_tube_material(s) for s in serials]
            keys = [(pallet, s) for s in serials] + serials
            triple = _size_triple(desc)
            if triple is not None:
                keys += [(pallet, triple), triple]
            for key in keys:
                if key in tracker:
                    return tracker[key]
            return LAST

        materials.sort(key=lambda kv: _pos(kv[1]))
        by_size, by_serial, strays = [], [], []
        for serial, entries in materials:
            pallet = entries[0]["pallet"]
            serials = list(entries[0].get("serials") or [])
            if any((pallet, s) in tracker for s in serials):
                continue
            label = f"{serial} ({entries[0]['desc']}) on pallet {pallet}"
            if any(s in tracker for s in serials):
                by_serial.append(label)
            elif _pos(entries) == LAST:
                strays.append(label)
            else:
                by_size.append(label)
        for s in by_serial:
            log(f"{s} is not a row on the tracker - the organizer says that "
                f"pallet needs it, so its sheet follows the material's other "
                f"tracker row")
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


def _tidy(text):
    """A cell's text with no padding: outer whitespace gone, inner runs to one.

    Covers the non-breaking space and the newline too, which a pasted
    organizer cell carries and which are just as invisible as a plain space.
    """
    return " ".join(str(text or "").split())


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
    """One sheet per source material per pallet, formatted the way Carrie asked.

    The sheet is named after its PACKET (`SAW.4`, `2.5`) and the source material
    number sits in A1, which is how she renamed the two sheets she marked up.
    Rows 1 and 2 are the Pallet Organizer's own words - the material line is
    copied from its MATERIAL REQUIRED entry, "(SAW CUT)" and all.

    Columns are Problem?, Parts Id., Length, Quantity, Order - the order number
    each part came in on (Anthony, 2026-10-30), added after Quantity so the
    three columns Carrie laid out stay where she put them.

    A row the reader was unsure about gets an ARROW in the Problem? column
    instead of the yellow highlight we used before. The X in F1 then appears by
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
        ws["A1"] = (int(serial) if str(serial).isdigit()
                    else _tidy(serial))
        ws["B1"] = "Electric Boat"
        ws["C1"] = f"Batch {batch_no}: Pallet {entries[0]['org_pallet']}"
        ws[X_CELL] = X_FORMULA
        for c in COL_WIDTHS:
            cell = ws[f"{c}1"]
            cell.fill = PatternFill("solid", fgColor=top)
            cell.alignment = center
            cell.font = Font(name="Calibri", size=12, color="000000")
            cell.border = Border(top=thin, bottom=thin, right=thin,
                                 left=None if c == "D" else thin)
        ws[X_CELL].font = Font(name="Aharoni", size=18, bold=True,
                               color=X_FONT)
        ws.row_dimensions[1].height = ROW_H

        # row 2 - the material exactly as the organizer writes it, minus any
        # padding. Carrie, 2026-10-30: "in cell A2 of each of the excel sheets
        # ... there's a bunch of spaces in the cell after the last word."
        # Row 2 is centred in a merged band, so padding shows up as text that
        # sits left of centre. Her own hand-built 505 sheet `2.5` carries
        # `HSS 2.5 X 2.5 X 0.25 NOM ` with the trailing space, so the wording
        # really does arrive padded sometimes - `_tidy` makes it impossible to
        # reach the sheet whatever the organizer holds.
        ws.merge_cells(f"A2:{LAST_COL}2")
        ws["A2"] = _tidy(entries[0]["mat_text"])
        for c in COL_WIDTHS:
            cell = ws[f"{c}2"]
            cell.fill = PatternFill("solid", fgColor=band)
            cell.alignment = center
            cell.font = Font(name="Calibri", size=14, bold=True,
                             color="000000")
            cell.border = Border(top=thin, bottom=thin,
                                 left=thin if c == "A" else None,
                                 right=thin if c == LAST_COL else None)
        ws.row_dimensions[2].height = ROW_H_TALL
        ws.row_dimensions[3].height = ROW_H

        # row 4 - the headers. The table is open on its left and right edges,
        # the way hers is, so only the inner lines are drawn.
        for c, text, size, color in (("A", "Problem?", 11, PROBLEM_FONT),
                                     ("B", "Parts Id.", 14, None),
                                     ("C", "Length", 14, None),
                                     ("D", "Quantity", 14, None),
                                     ("E", "Order", 14, None)):
            cell = ws[f"{c}4"]
            cell.value = text
            cell.font = Font(name="Calibri", size=size, bold=True,
                             color=color or "000000")
            cell.alignment = center
            cell.border = Border(bottom=thin,
                                 left=thin if c != DATA_COLS[0] else None,
                                 right=thin if c != DATA_COLS[-1] else None)
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
            for col, value in ((2, e["part"]), (3, e["length"]),
                               (4, e["qty"]), (5, e["order"])):
                cell = ws.cell(r, col, value)
                cell.font = Font(name="Calibri", size=12, color="000000")
                cell.alignment = center
                cell.border = Border(top=thin, bottom=thin, left=thin,
                                     right=thin if col < len(DATA_COLS)
                                     else None)
            ws.row_dimensions[r].height = ROW_H

    sdk.save_workbook(wb, _guard_output(dest), log=log)
    if flagged:
        log(f"{flagged} row(s) marked with an arrow in the Problem? column")
    return dest


# ──────────────────────────────────────────────────────────────── the report

def _write_report(dest: Path, batch_no, materials, no_sheet, skipped_rows,
                  log):
    """The colour-coded PDF, same shape as the LST Organizer's."""
    C = sdk.REPORT_COLORS
    flat = [e for _s, entries in materials for e in entries]
    review = [e for e in flat if e["review"] and e["length"] is not None]
    missing = [e for e in flat if e["length"] is None]
    unknown = [e for e in flat if e["pallet"] == "UNKNOWN"]
    # one row per MATERIAL for the two new-material checks, not per tube
    off_org = sorted({(e["serial"], e["desc"], e["packet"]) for e in flat
                      if e.get("off_organizer")})
    new_mat = sorted({(e["serial"], e["desc"], e["packet"]) for e in flat
                      if e.get("new_material")})
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
        ("Source materials", len({e["serial"] for e in flat}), None, None),
        # a material whose parts spill onto the next pallet is cut and bound
        # per pallet, so there are more sheets than materials
        ("Cutting list sheets", len(materials), None, None),
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
        ("Materials TechDeck has never seen", len(new_mat),
         C["miss_bg"] if new_mat else C["ok_bg"],
         C["miss_tx"] if new_mat else C["ok_tx"]),
        ("Materials not on the Pallet Organizer", len(off_org),
         C["rev_bg"] if off_org else C["ok_bg"],
         C["rev_tx"] if off_org else C["ok_tx"]),
        ("PO rows left off the cutting list", len(skipped_rows),
         C["miss_bg"] if skipped_rows else C["ok_bg"],
         C["miss_tx"] if skipped_rows else C["ok_tx"]),
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
                     "but there is no single-tube page to bind. Where the "
                     "assembly HAS sheets for part",
                     "numbers the PO does not list, the PO's number is "
                     "probably the wrong one."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Length", "Why", "The batch has", ""], w5)
        for e in no_print:
            d.row([e["part"], "-" if e["length"] is None else str(e["length"]),
                   e.get("why", ""), e.get("suggest", "") or "-", ""], w5,
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

    if new_mat:
        d.text("Tube material TechDeck has never seen", size=11, bold=True,
               color=C["miss_tx"])
        for line in ("This serial is on neither of TechDeck's tube material "
                     "lists. The Pallet Organizer",
                     "placed it, so the cutting list is right - but check the "
                     "serial is not a typo of a",
                     "material we already stock, and have it added to "
                     "TechDeck so the next batch knows it."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Serial", "Material", "Packet", "", ""], w5)
        for serial, desc, packet in new_mat:
            d.row([serial, desc, packet, "", ""], w5,
                  fill=C["miss_bg"], tcolor=C["miss_tx"])
        d.gap(14)

    if off_org:
        d.text("Material not on the Pallet Organizer", size=11, bold=True,
               color=C["rev_tx"])
        for line in ("The organizer's MATERIAL REQUIRED list does not carry "
                     "this material, so TechDeck",
                     "filed it from its own tube list instead of from the "
                     "paperwork. Add it to the",
                     "organizer so the two documents agree."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Serial", "Material", "Packet", "", ""], w5)
        for serial, desc, packet in off_org:
            d.row([serial, desc, packet, "", ""], w5,
                  fill=C["rev_bg"], tcolor=C["rev_tx"])
        d.gap(14)

    if skipped_rows:
        d.text("PO rows left off the cutting list", size=11, bold=True,
               color=C["miss_tx"])
        for line in ("These rows carry a tube source material but no Base "
                     "Material, and that column is",
                     "the only thing marking a row as a tube - so they are "
                     "NOT on any sheet and NOT in any",
                     "binder. Fill the Base Material in on the PO Info Drop "
                     "and run this again."):
            d.text(line, size=8, color=C["grey"])
        d.header_row(["Part", "Order", "Serial", "", ""], w5)
        for e in skipped_rows:
            d.row([e["part"], e["order"], e["serial"], "", ""], w5,
                  fill=C["miss_bg"], tcolor=C["miss_tx"])
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

def _step_two(params, settings, log, batch_no, batch_path, root_922,
              progress_callback, cancel_event):
    r"""Step 2: mark up the 1Ds, build the covers, bind the production run.

    Carrie's own four-stage reference for batch 508 is what this follows
    (`TechDeck Packets\ANTHONY REF`, 2026-11-02). Step 1 has to have run and
    she has to have made the 1Ds in between - the nesting is hers, not ours.
    """
    out_dir = batch_path / f"Batch {batch_no} - Documentation" / PACKETS_FOLDER
    packets_dir = out_dir / PACKETS_SUBFOLDER
    run_dir = packets_dir / rs.RUN_FOLDER

    packets = rs.read_cutting_list(
        out_dir / f"{batch_no} Tubes (TechDeck).xlsx", log)
    if not packets:
        raise sdk.UserFacingError(
            f"Step 1's cutting list for batch {batch_no} has no sheets in it.",
            "Run the app with this option switched OFF first.")

    one_d = sdk.request_directory(
        params, f"Pick the folder holding batch {batch_no}'s 1D PDFs",
        str(packets_dir))
    if one_d is None or cancel_event.is_set():
        return None
    log(f"1Ds: {one_d}")
    progress_callback(20)

    bars = rs.read_tracker(root_922, batch_no, log)
    blocks = read_cover_blocks(_organizer(batch_path, batch_no, log), log)
    sheets = rs.match_1ds(Path(one_d), packets, log)
    progress_callback(35)

    # 1 - every 1D gets her notes and highlights
    log("Marking up the 1Ds...")
    marked = {}
    for n, (packet, src) in enumerate(sorted(sheets.items())):
        sdk.raise_if_cancelled(cancel_event)
        info = packets[packet]
        saw = info["pallet"] == SAW_PALLET
        dest = run_dir / "1Ds (marked up)" / f"{rs.safe_name(packet)}.pdf"
        added = rs.annotate(src, dest, bars.get((info["pallet"],
                                                 info["serial"])), saw, log)
        marked[packet] = dest
        log(f"  {packet:6s} {', '.join(added)}")
        progress_callback(35 + int(25 * (n + 1) / max(len(sheets), 1)))

    # 2 - a cover page per pallet, plus the saw one. The saw cover carries
    # the pallet block of whichever pallet the saw materials are listed under
    # (pallet 1 on batch 508), because that is the paperwork the saw operator
    # is handed alongside it.
    log("Building the cover pages...")
    templates = Path(__file__).resolve().parent / "templates"
    covers = {}
    for pallet in sorted(blocks):
        sdk.raise_if_cancelled(cancel_event)
        block = blocks[pallet]
        covers[pallet] = rs.cover_pdf(
            templates / rs.TEMPLATE_LASER,
            run_dir / "Cover Sheets" / f"_{pallet}.pdf", batch_no,
            f"PALLET {pallet}", block["listing"], block["materials"], [], log)
    saw_pallet = next((p for p in sorted(blocks)
                       if any("SAW CUT" in t.upper()
                              for t in blocks[p]["materials"])), None)
    if saw_pallet is not None:
        block = blocks[saw_pallet]
        covers[SAW_PALLET] = rs.cover_pdf(
            templates / rs.TEMPLATE_SAW,
            run_dir / "Cover Sheets" / "_SAW.pdf", batch_no,
            f"PALLET {saw_pallet}", block["listing"], block["materials"],
            [t.replace(" (SAW CUT)", "").strip()
             for t in block["materials"] if "SAW CUT" in t.upper()], log)
    progress_callback(80)

    # 3 - bind. A pallet binder is the cover and its 1Ds; the SAW binder
    # also carries each material's drawings, because only the saw operator
    # cuts from a print. Carrie, 2026-11-02: "I don't want the tube drawings
    # for pallet 1,2,3 ... the tube laser parts don't need drawings because
    # they'll be programmed."
    log("Binding the production run...")
    drawings = rs.packet_drawings(packets_dir)
    by_pallet = {}
    for packet, info in packets.items():
        by_pallet.setdefault(info["pallet"], []).append(packet)
    written = []
    for pallet in sorted(by_pallet, key=lambda p: (p == SAW_PALLET, p)):
        sdk.raise_if_cancelled(cancel_event)
        cover = covers.get(pallet)
        if cover is None:
            log(f"WARNING: no cover page for pallet {pallet} - its binder "
                f"starts at the first 1D")
        pages = [cover] if cover else []
        for packet in sorted(by_pallet[pallet], key=_packet_sort):
            sheet = marked.get(packet)
            if sheet is None:
                continue                      # match_1ds already said so
            pages.append(sheet)
            if pallet == SAW_PALLET and packet in drawings:
                pages.append(drawings[packet])
        name = ("SAW TUBES.pdf" if pallet == SAW_PALLET
                else f"PALLET {pallet}.pdf")
        made = rs.bind(run_dir / name, pages, log)
        if made is not None:
            written.append(made)
    progress_callback(100)
    return run_dir, written, len(sheets), len(packets)


def _packet_sort(packet):
    """`2.10` after `2.9`, and SAW last - a packet name is not a number."""
    head, _, tail = str(packet).partition(".")
    return (head == SAW_PALLET, head, int(tail) if tail.isdigit() else 0)


def run(params: dict, progress_callback, cancel_event: threading.Event):
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}
    console = params.get("console")

    log(f"922 Production Packets v{VERSION}")

    # Step 2 is off unless somebody turns it on in Settings > Apps. It cannot
    # run in the same pass as step 1: the 1Ds it works from are nested by
    # hand, in software TechDeck does not drive, between the two runs.
    step_two = bool(settings.get("production_run_binders"))

    root_922 = sdk.resolve_922_root(settings.get("base_path", ""))
    picked = sdk.request_922_batch_folder(params, settings.get("base_path", ""))
    if picked is None or cancel_event.is_set():
        return
    batch_no, batch_path = picked
    batch_path = Path(batch_path)
    log(f"Batch {batch_no}: {batch_path}")
    progress_callback(5)

    if step_two:
        log("Step 2: the production run binders")
        done = _step_two(params, settings, log, batch_no, batch_path,
                         root_922, progress_callback, cancel_event)
        if done is None or cancel_event.is_set():
            return
        run_dir, written, marked, total = done
        log(f"{marked} of {total} packet(s) had a 1D, "
            f"{len(written)} binder(s) built")
        if marked < total:
            sdk.flag_action(
                params,
                f"{total - marked} source material(s) have no 1D, so they are "
                f"missing from their binder.",
                "The console names each one. Nest them, put the PDFs in the "
                "same folder named after their packet (1.1.pdf, SAW.2.pdf) "
                "and run this again.")
            sdk.set_run_outcome(
                params, sdk.RUN_OUTCOME_PARTIAL,
                f"{total - marked} material(s) have no 1D - see the console")
        for dest, pages in written:
            sdk.link_output(params, f"Open {dest.name}", str(dest),
                            prefix="[BINDER]")
        return

    organizer = _organizer(batch_path, batch_no, log)
    tubes, skipped_rows, all_parts = _read_tubes(organizer, log)
    pallet_map, order_pallets = _read_pallets(organizer, log)
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
            t["pallet"] = _pallet_of(t["serial"], t["desc"], pallet_map,
                                     order_pallets, t["order"])
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
    if no_sheet:
        _diagnose_no_sheet(batch_path, no_sheet, all_parts, log)
    progress_callback(95)

    # the report is written LAST on purpose: which tubes have no print of their
    # own is only known once the binders have been built, and the report is
    # where the reader goes looking for it
    report = _write_report(
        out_dir / f"Production Packets Report (TechDeck) - Batch {batch_no}.pdf",
        batch_no, materials, no_sheet, skipped_rows, log)
    progress_callback(100)

    flagged = sum(1 for t in tubes if t["review"] and t["length"] is not None)
    blank = sum(1 for t in tubes if t["length"] is None)
    log(f"{len(tubes)} tubes across "
        f"{len({t['serial'] for t in tubes})} source materials, "
        f"{len(materials)} sheet(s)")
    if flagged:
        log(f"{flagged} highlighted yellow - check those before you cut")
    if blank:
        log(f"{blank} with no drawing - those cells are empty")
        sdk.flag_action(
            params,
            f"Fill in the saw cut length for {blank} tube(s) by hand in "
            f"{book.name}.",
            "TechDeck found no drawing it could match to those part numbers, "
            "so it left the cells empty rather than guess. The report says "
            "which of them look MIS-NUMBERED - the assembly has sheets under "
            "part numbers the PO does not list - and which have no print in "
            "the batch at all.")
    # A new material does NOT get a popup: the organizer placed it, so the
    # cutting list is right and nothing downstream acts on it wrongly - it is
    # the app working correctly, which is the wrong class for a dialog
    # (tests/tools/test_action_items_popup.py). The console WARNING, the report
    # section and the warning outcome carry it.
    new_mats = sorted({t["serial"] for t in tubes if t.get("new_material")})
    # A skipped row DOES: those parts are on no sheet, so the 1D optimizer
    # nests nothing for them and the batch gets cut short.
    if skipped_rows:
        sdk.flag_action(
            params,
            f"{len(skipped_rows)} part(s) on the PO Info Drop have no Base "
            f"Material, so they are NOT on the cutting list.",
            "That column is the only thing marking a row as a tube. Fill it "
            "in and run this again. The report names every one.")

    if flagged or blank or new_mats or skipped_rows:
        reasons = []
        if flagged or blank:
            reasons.append(f"{flagged + blank} tube(s) need a look")
        if new_mats:
            reasons.append(f"{len(new_mats)} unknown material(s)")
        if skipped_rows:
            reasons.append(f"{len(skipped_rows)} row(s) left off")
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_WARNING,
            f"{', '.join(reasons)} - see the report")

    sdk.link_output(params, f"Open {book.name}", str(book), prefix="[CUT LIST]")
    sdk.link_output(params, "Open the Production Packets report", str(report),
                    prefix="[REPORT]")

    # step 1 ends by saying what has to happen before step 2 can run - the
    # nesting in between is hers, and nothing here can do it for her
    log("")
    log("NEXT: nest these materials into 1Ds, save one PDF per packet named "
        "after it (1.1.pdf, SAW.2.pdf), then switch on 'Build the production "
        "run binders' in Settings > Apps and run this again.")

    if console is not None and hasattr(console, "safe_colored_log"):
        console.safe_colored_log("Get out me swamp!", SWAMP_GREEN)
