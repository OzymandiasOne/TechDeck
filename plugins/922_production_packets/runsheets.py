"""Step 2 of the production packet procedure: the production run binders.

Step 1 (`run.py`) builds the cutting list and binds each source material's
drawings. Then it STOPS, because the next thing that has to happen is not
something TechDeck can do: Carrie takes the cutting list into the 1D nesting
software and produces one cutting-pattern PDF per source material by hand.

Step 2 picks up from those 1Ds. It is everything she used to do with a PDF
editor and Word, written down from her own worked example for batch 508
(`TechDeck Packets\\ANTHONY REF`, 2026-11-02), which carries the four stages
side by side:

    1.GENERATED 1Ds   what the nesting software gives her
    2.FIXED 1Ds       the same sheets with her notes and highlights
    3.COVER SHEET     a Word procedure page per pallet, plus their PDFs
    4.BINDER          cover + 1Ds, bound one file per pallet

What this module reproduces, in her words: "i go in and add some notes and
highlights to the pdfs ... All needed information for the pdf editing is found
in the EB 922 Material Use Tracker excel doc (the notes column will say if
it's an estimated drop length, which should be confirmed with a '~' next to
the length in the 1D). I'll then make cover sheets for each pallet using the
two word docs ... They're all bound together in the end."

Two things are deliberately NOT symmetric, both confirmed by Carrie
2026-11-02:

  * only the SAW binder carries tube drawings. "the tube laser parts don't
    need drawings because they'll be programmed", so PALLET 1/2/3 are cover +
    1Ds and nothing else;
  * only a SAW 1D gets the `pre-cut bar length` blank.

Nothing here writes outside the folder it is handed, and it only ever creates
files - no 1D, no drawing and no tracker row is modified in place.
"""
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import fitz

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:                       # standalone / CLI testing
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

SAW_PALLET = "SAW"

# Her own ink, sampled out of 2.FIXED 1Ds rather than guessed at.
NOTE_BLUE = (0.075, 0.451, 0.910)
NOTE_YELLOW = (0.988, 0.957, 0.522)
NOTE_SIZE = 11
NOTE_FONT = "helv"

# The two Word procedure pages, shipped with the plugin. Carrie keeps her own
# copies in the batch folder; these are the ones TechDeck fills, so a batch
# can never inherit the pallet block of whichever batch she edited last.
TEMPLATE_LASER = "Production Run Procedure (7000).docx"
TEMPLATE_SAW = "Production Run Procedure (SAW).docx"


# ──────────────────────────────────────────────────────── the tracker read

def _rows(ws):
    """The STICK rows of one tracker sheet, in sheet order.

    The sheet's lower half holds PLATE USAGE and ROD USAGE blocks whose first
    column is a tag, not a pallet, so the walk stops at whichever comes first.
    A blank row inside the table is skipped, not treated as the end - batch
    507 has one, and stopping there hides every SAW row below it.
    """
    header_row, cols = sdk.find_header_row(ws, ["PALLET", "ITEM"])
    if header_row is None:
        return []
    c_item, c_pallet = cols["ITEM"], cols.get("PALLET")
    c_len, c_after = cols.get("LENGTH"), cols.get("ESTIMATED AFTER RUN")
    out = []
    for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
        def _v(c):
            v = r[c - 1] if c and c - 1 < len(r) else None
            return "" if v is None else str(v).strip()

        head = _v(c_pallet).upper()
        if head.startswith("PLATE") or head.startswith("ROD"):
            break
        serial = _v(c_item).split(".")[0]       # 218012959.0 on some rows
        if not serial.isdigit():
            continue
        after = r[c_after - 1] if c_after and c_after - 1 < len(r) else None
        try:
            after = float(after)
        except (TypeError, ValueError):
            after = 0.0
        out.append({"pallet": head.replace("PALLET", "").strip() or SAW_PALLET,
                    "serial": serial, "length": _v(c_len), "after": after})
    return out


def _tracker_sheets(root, log):
    """(workbook, {batch_number: sheet_name}) for the Material Use Tracker."""
    folder = Path(root) / "2 - Planning"
    hits = [p for p in folder.glob("*Material Use Tracker*.xlsx")
            if not p.name.startswith("~$")]
    if not hits:
        raise sdk.UserFacingError(
            "There is no Material Use Tracker in '2 - Planning'.",
            "Step 2 reads the bar lengths off it. Check the file is there "
            "and run this again.")
    wb = sdk.load_workbook_resilient(hits[0], read_only=True, data_only=True,
                                     log=log)
    by_batch = {}
    for name in sdk.visible_sheetnames(wb):
        text = str(name).strip()
        if text.isdigit():
            by_batch[int(text)] = name
    return wb, by_batch, hits[0].name


def read_tracker(root_922, batch_no, log):
    """-> {(pallet, serial): {"length", "estimated", "from_batch"}}.

    `estimated` is the `~` the tracker's LENGTH column carries - that is what
    marks a bar as a leftover drop rather than a fresh 240" stick, and it is
    the only thing that puts a "DROP FROM BATCH n" note on a 1D.

    `from_batch` is WHERE that drop came from: the most recent EARLIER batch
    that used the same item and left something over (`ESTIMATED AFTER RUN`
    above zero). Checked against Carrie's own batch 508 markup, which this
    reproduces 7 times out of 7 - including the two she had to look past a
    nearer batch for, because 507 used the material and left nothing
    (`1.2` -> 505, `2.1` -> 506).
    """
    wb, by_batch, fname = _tracker_sheets(root_922, log)
    try:
        batch_no = int(str(batch_no).strip())
        if batch_no not in by_batch:
            raise sdk.UserFacingError(
                f"{fname} has no sheet for batch {batch_no} yet.",
                "Step 2 reads the bar lengths off that sheet. Add it and run "
                "this again.")
        mine = _rows(wb[by_batch[batch_no]])
        earlier = sorted((b for b in by_batch if b < batch_no), reverse=True)

        def source_of(serial):
            for b in earlier:
                for row in _rows(wb[by_batch[b]]):
                    if row["serial"] == serial and row["after"] > 0:
                        return str(b)
            return None

        out, sources = {}, {}
        for row in mine:
            estimated = row["length"].startswith("~")
            from_batch = None
            if estimated:
                if row["serial"] not in sources:
                    sources[row["serial"]] = source_of(row["serial"])
                from_batch = sources[row["serial"]]
            out[(row["pallet"], row["serial"])] = {
                "length": row["length"], "estimated": estimated,
                "from_batch": from_batch}
        drops = sum(1 for v in out.values() if v["estimated"])
        log(f"{fname} sheet {batch_no}: {len(out)} bar(s), {drops} of them a "
            f"leftover drop")
        for (pallet, serial), v in out.items():
            if v["estimated"] and v["from_batch"] is None:
                log(f"WARNING: pallet {pallet} {serial} is marked estimated "
                    f"({v['length']}) but no earlier batch left a drop of it "
                    f"- its 1D gets the highlight and the blanks, but no "
                    f"'DROP FROM BATCH' note. Check the tracker.")
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────── marking up a 1D

def _find(page, needle):
    """The first box on the page holding `needle`, or None."""
    hits = page.search_for(needle)
    return hits[0] if hits else None


def _material_of(page):
    """The `HSS ...` material line a 1D prints under its title."""
    for line in page.get_text().split("\n"):
        text = line.strip()
        if text.upper().startswith("HSS "):
            return text
    return None


def annotate(src: Path, dest: Path, info, saw, log):
    """Write `src` to `dest` with Carrie's notes and highlights on it.

    `info` is one `read_tracker` entry, or None when the tracker has no row
    for this material - the sheet still gets the highlight and the blanks,
    because those go on every 1D; only the drop note needs the tracker.

    Returns a short list of what was put on the page, so the run can say.
    """
    sdk.ensure_local(src)
    doc = fitz.open(sdk.long_path(str(src)))
    added, saved = [], False
    try:
        page = doc[0]
        rect = page.rect

        # 1 - the material line, highlighted yellow. On every sheet.
        material = _material_of(page)
        box = _find(page, material) if material else None
        if box is not None:
            hl = page.add_highlight_annot(box)
            hl.set_colors(stroke=NOTE_YELLOW)
            hl.update()
            added.append("highlight")

        # 2 - the drop note: an arrow pointing back at the bar length, and
        # which batch the drop came off. ONLY when the tracker says estimated.
        if info and info.get("estimated") and info.get("from_batch"):
            label = _find(page, "Bar Length")
            if label is not None:
                mid = (label.y0 + label.y1) / 2
                # the arrow starts clear of the length VALUE, which prints to
                # the right of the label; the value is the next word along
                value_end = label.x1
                for w in page.get_text("words"):
                    if (abs((w[1] + w[3]) / 2 - mid) < 4 and w[0] >= label.x1
                            and w[2] > value_end and w[0] < label.x1 + 90):
                        value_end = w[2]
                tip, tail = value_end + 5, value_end + 62
                arrow = page.add_line_annot((tail, mid), (tip, mid))
                arrow.set_border(width=1)
                arrow.set_colors(stroke=NOTE_BLUE)
                arrow.set_line_ends(fitz.PDF_ANNOT_LE_NONE,
                                    fitz.PDF_ANNOT_LE_OPEN_ARROW)
                arrow.update()
                page.insert_text((tail + 7, mid + 4),
                                 f"DROP FROM BATCH {info['from_batch']} "
                                 f"(ESTIMATED)", fontsize=NOTE_SIZE,
                                 fontname=NOTE_FONT, color=NOTE_BLUE)
                added.append(f"drop from {info['from_batch']}")

        # 3 - the blanks the operator writes in, under the Total Bars box.
        # A saw bar is cut from stock of an unknown length, so it gets a
        # second blank; a laser bar comes off the 7000 and does not.
        totals = _find(page, "Total Bars")
        base = totals.y1 if totals is not None else rect.height * 0.60
        if saw:
            page.insert_text((414, base - 1), "pre-cut bar length:" + "_" * 15,
                             fontsize=NOTE_SIZE, fontname=NOTE_FONT,
                             color=NOTE_BLUE)
            page.insert_text((390, base + 16), "drop :" + "_" * 17,
                             fontsize=NOTE_SIZE, fontname=NOTE_FONT,
                             color=NOTE_BLUE)
            added.append("pre-cut + drop blanks")
        else:
            page.insert_text((410, base + 9), "drop:" + "_" * 14,
                             fontsize=NOTE_SIZE, fontname=NOTE_FONT,
                             color=NOTE_BLUE)
            added.append("drop blank")

        sdk.ensure_dir(dest.parent)
        # `dest` is a different file from `src`, but this still goes through
        # the SDK helper (Hard Rule 5): it owns the temp-then-replace and the
        # long-path wrap, and it CLOSES the doc, which is why the finally
        # below only closes on the error path.
        sdk.save_pdf_atomic(doc, dest)
        saved = True
    finally:
        if not saved:
            try:
                doc.close()
            except Exception:
                pass
    return added


# ─────────────────────────────────────────────────────────── the cover page

# The cover's shading, read out of Carrie's own template rather than guessed.
# All three are derivable, so TechDeck can colour a cover it has never seen:
FILL_TITLE = "C6E0B4"     # the PALLET n / MATERIAL REQUIRED heading rows
FILL_SAW_ORDER = "FFFF00" # an ORDER whose material is saw cut - yellow
FILL_SAW_MAT = "D9D9D9"   # that material's row in MATERIAL REQUIRED - grey
FILL_BAND = "E2EFDA"      # every other material GROUP, so the groups read apart

# the saw page's sign-off line, one per saw material, copied from Carrie's own
USED_LINE = ("USED: {material} - TAG: " + "_" * 14
             + " DROP LENGTH: " + "_" * 14)

CELL_RE = re.compile(r"<w:tc>.*?</w:tc>", re.S)
ROW_RE = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
TEXT_RE = re.compile(r"(<w:t(?: [^>]*)?>)([^<]*)(</w:t>)")
SHD_RE = re.compile(r"<w:shd [^/]*?/>")


def _xml_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _set_cell(cell, text=None, fill=None):
    """One table cell's text and shading, leaving its formatting alone."""
    if text is not None:
        def once(m, done=[]):
            if done:
                return m.group(1) + m.group(3)       # drop extra runs
            done.append(True)
            return (m.group(1).replace("<w:t>", '<w:t xml:space="preserve">')
                    + _xml_escape(text) + m.group(3))
        cell = TEXT_RE.sub(once, cell)
    if fill:
        if SHD_RE.search(cell):
            cell = SHD_RE.sub(
                f'<w:shd w:val="clear" w:color="000000" w:fill="{fill}"/>',
                cell, count=1)
        else:
            cell = cell.replace(
                "</w:tcPr>",
                f'<w:shd w:val="clear" w:color="000000" w:fill="{fill}"/>'
                "</w:tcPr>", 1)
    else:
        cell = SHD_RE.sub("", cell)
    return cell


def _set_row(row, values):
    """`values` is [(text, fill), ...] for the row's cells, left to right."""
    cells = CELL_RE.findall(row)
    out, pos = [], 0
    for i, cell in enumerate(cells):
        start = row.index(cell, pos)
        out.append(row[pos:start])
        if i < len(values):
            text, fill = values[i]
            out.append(_set_cell(cell, text, fill))
        else:
            out.append(_set_cell(cell, None, None))
        pos = start + len(cell)
    out.append(row[pos:])
    return "".join(out)


def fill_docx(template: Path, dest: Path, batch_no, title, listing,
              materials, saw_materials):
    """Write `template` out as `dest` with this batch's cover data in it.

    The table is rebuilt in the document XML rather than through Word's COM
    table API, because Carrie's table has VERTICALLY MERGED cells and Word
    refuses row-by-row access on one of those outright ("Cannot access
    individual rows in this collection because the table has vertically merged
    cells"). Cloning her own row XML also keeps every font, border and width
    exactly as she set them - nothing is re-styled from scratch.

    Three shadings are reproduced, all of them derivable:
      * an ORDER is yellow when the material it uses is saw cut;
      * that material's MATERIAL REQUIRED row is grey for the same reason;
      * the material column bands every other material GROUP, so a reader can
        see where one material's orders end and the next start.
    """
    src = zipfile.ZipFile(sdk.long_path(str(template)))
    try:
        items = {n: src.read(n) for n in src.namelist()}
    finally:
        src.close()
    xml = items["word/document.xml"].decode("utf-8")

    table = re.search(r"<w:tbl>.*?</w:tbl>", xml, re.S)
    if table is None:
        raise sdk.UserFacingError(
            f"The cover template {template.name} has no table in it.",
            "It should hold the pallet listing table. Restore it from a "
            "known-good copy and run this again.")
    rows = ROW_RE.findall(table.group(0))
    if len(rows) < 17:
        raise sdk.UserFacingError(
            f"The cover template {template.name} is not the expected shape.",
            "Its table should hold the PALLET heading, the order listing and "
            "the MATERIAL REQUIRED block. Restore a known-good copy.")
    t_title, t_blank, t_body = rows[0], rows[1], rows[3]
    t_mat_head, t_mat = rows[15], rows[16]

    # which MATERIAL REQUIRED entry each order's material is, so the banding
    # and the yellow both key off the same list the page already prints
    index, saw = {}, set()
    for i, text in enumerate(materials, start=1):
        key = _norm(text)
        index.setdefault(key, i)
        if "SAW CUT" in text.upper():
            saw.add(key)

    built = [_set_row(t_title, [(title, FILL_TITLE)]), t_blank]
    for order, material in listing:
        key = _norm(material)
        n = index.get(key)
        built.append(_set_row(t_body, [
            (order, FILL_SAW_ORDER if key in saw else None),
            (material, FILL_BAND if n and n % 2 == 0 else None)]))
    built += [rows[13], rows[14],
              _set_row(t_mat_head,
                       [(f"MATERIAL REQUIRED: {len(materials)}", FILL_TITLE)])]
    for i, text in enumerate(materials, start=1):
        shade = FILL_SAW_MAT if "SAW CUT" in text.upper() else None
        built.append(_set_row(t_mat, [(str(i), shade), (text, shade)]))

    head, tail = table.group(0).split(rows[0], 1)
    rebuilt = head + "".join(built) + tail.split(rows[-1], 1)[1]
    xml = xml[:table.start()] + rebuilt + xml[table.end():]

    # the heading is the only place the batch number appears
    xml = re.sub(r"(BATCH\s*)\d+", lambda m: f"{m.group(1)}{batch_no}", xml)

    # the saw page ends with a line per saw material for the operator to
    # write the tag and the leftover length on. Built here, not by the caller,
    # so the wording cannot drift between the two pages.
    if saw_materials:
        block = "".join(
            '<w:p><w:r><w:t xml:space="preserve">'
            f'{_xml_escape(USED_LINE.format(material=m))}</w:t></w:r></w:p>'
            for m in saw_materials)
        xml = xml.replace("<w:sectPr", block + "<w:sectPr", 1)

    items["word/document.xml"] = xml.encode("utf-8")
    sdk.ensure_dir(dest.parent)
    out = zipfile.ZipFile(sdk.long_path(str(dest)), "w", zipfile.ZIP_DEFLATED)
    try:
        for name, data in items.items():
            out.writestr(name, data)
    finally:
        out.close()
    return dest


def _norm(text):
    """A material as a comparable key - the organizer writes the same size
    with and without the `HSS` prefix and the `(SAW CUT)` tag."""
    t = re.sub(r"\(.*?\)", " ", str(text or "").upper())
    t = re.sub(r"\bHSS\b|\bNOM\b|\bTHK\b|,", " ", t)
    return " ".join(t.split())


def cover_pdf(template: Path, dest: Path, batch_no, title, listing, materials,
              saw_materials, log):
    """Fill one procedure page and export it to PDF.

    The filling is `fill_docx` (pure XML, no Word). Word is used only for the
    last step, turning the finished .docx into the PDF that goes in the
    binder - the same COM export `922_kitting` and `911_sspo_invoicing_prep`
    already use for Excel.
    """
    import pythoncom
    import win32com.client as win32

    work = Path(tempfile.mkdtemp(prefix="td922cover_")) / template.name
    fill_docx(template, work, batch_no, title, listing, materials,
              saw_materials)

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32.gencache.EnsureDispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        doc = word.Documents.Open(str(work), ReadOnly=True)
        try:
            sdk.ensure_dir(dest.parent)
            doc.ExportAsFixedFormat(str(dest), 17)   # 17 = wdExportFormatPDF
        finally:
            doc.Close(SaveChanges=0)
    except Exception as exc:
        raise sdk.UserFacingError(
            f"Word could not turn the {title} cover page into a PDF ({exc}).",
            "Close any open Word documents and run this again. If Word is "
            "mid-update or not installed on this machine, the cover pages "
            "cannot be built here.")
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        shutil.rmtree(sdk.long_path(str(work.parent)), ignore_errors=True)
    log(f"  {dest.name}")
    return dest


# ──────────────────────────────────────────────────────────── the binders

def bind(dest: Path, pages, log):
    """Append every (path, from_page, to_page) in order into one PDF."""
    out = fitz.open()
    try:
        for item in pages:
            path = item if isinstance(item, (str, Path)) else item[0]
            sdk.ensure_local(path)
            src = fitz.open(sdk.long_path(str(path)))
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        if not out.page_count:
            return None
        sdk.ensure_dir(dest.parent)
        out.save(sdk.long_path(str(dest)), garbage=3, deflate=True)
        log(f"  {dest.name}  ({out.page_count} pages)")
        return dest, out.page_count
    finally:
        out.close()


def match_1ds(folder: Path, packets, log):
    """{packet name: 1D pdf} for the sheets Carrie made.

    Matched on the file NAME first, because she names them after the packet
    (`1.1.pdf`, `SAW.2.pdf`) - that is the contract the cutting list sets up.
    A sheet whose name does not match is matched on the material line printed
    inside it instead, so a renamed file still lands rather than vanishing.
    """
    by_name, leftovers = {}, []
    for p in sorted(Path(folder).glob("*.pdf")):
        stem = p.stem.strip().upper()
        if stem in packets:
            by_name[stem] = p
        else:
            leftovers.append(p)

    missing = [k for k in packets if k not in by_name]
    if leftovers and missing:
        wanted = {packets[k]["material"].upper(): k for k in missing}
        for p in list(leftovers):
            try:
                sdk.ensure_local(p)
                doc = fitz.open(sdk.long_path(str(p)))
                material = (_material_of(doc[0]) or "").upper()
                doc.close()
            except Exception:
                continue
            if material in wanted and wanted[material] not in by_name:
                by_name[wanted[material]] = p
                leftovers.remove(p)
                log(f"  {p.name} matched to packet {wanted[material]} by its "
                    f"material line, not its name")

    for p in leftovers:
        log(f"WARNING: {p.name} does not match any of this batch's packets - "
            f"it is not in a binder")
    for k in packets:
        if k not in by_name:
            log(f"WARNING: no 1D for packet {k} "
                f"({packets[k]['material']}) - that material is missing from "
                f"its binder")
    return by_name


SAFE = re.compile(r'[<>:"/\\|?*]')


def safe_name(name):
    return SAFE.sub("-", str(name)).strip()


# ───────────────────────────────────────────────────── the whole of step 2

RUN_FOLDER = "Production Run"
PACKET_RE = re.compile(r"^(SAW\.\d+|\d+\.\d+)_(.+)$")


def read_cutting_list(path: Path, log):
    """{packet: {"serial", "material", "pallet"}} off step 1's own workbook.

    Step 2 does not re-read the drawings or re-derive the groups: step 1
    already wrote one sheet per packet, named after that packet, with the
    source material number in A1 and the organizer's wording in A2. That is
    everything step 2 needs to tie a 1D to a tracker row.
    """
    if not sdk.is_file(path):
        raise sdk.UserFacingError(
            f"There is no {path.name} in the Production Packets folder.",
            "Step 2 builds on step 1's cutting list. Run the app with this "
            "option switched OFF first, make the 1Ds, then run it again.")
    wb = sdk.load_workbook_resilient(path, read_only=True, data_only=True,
                                     log=log)
    try:
        out = {}
        for name in sdk.visible_sheetnames(wb):
            ws = wb[name]
            packet = str(name).strip().upper()
            out[packet] = {
                "serial": str(ws["A1"].value or "").split(".")[0].strip(),
                "material": str(ws["A2"].value or "").strip(),
                "pallet": (SAW_PALLET if packet.startswith(SAW_PALLET)
                           else packet.split(".")[0])}
        log(f"{path.name}: {len(out)} packet(s) - {', '.join(sorted(out))}")
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


def packet_drawings(folder: Path):
    """{packet: the bound drawing PDF step 1 wrote for it}."""
    out = {}
    for p in sorted(Path(folder).glob("*.pdf")):
        m = PACKET_RE.match(p.stem)
        if m:
            out.setdefault(m.group(1).upper(), p)
    return out
