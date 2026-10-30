"""Bind a batch's shop drawings into the production packet PDFs.

Three sets:

  1. `SAW.<n>_<size>.pdf`   - one per SAW CUT source material. Per contributing
                              order: the assembly sheet (when its tubes belong
                              to one) then each tube's own sheet, every page
                              stamped with its order number and the saw cut
                              dimension highlighted. Matches the hand-built
                              packets in "THIS IS WHAT I WANT DRIVEWORKS TO
                              MAKE" page for page.
  2. `<n.n>_<size>.pdf`     - one per LASER source material. Individual tube
                              sheets only, no assembly sheets, unstamped.
  3. `_Problem Drawings.pdf`- every drawing behind a flagged or blank length,
                              assembly sheets included.

A fourth, `_Everything Else.pdf`, held every sheet that was not an individual
tube page - plate, rod, and the tube assembly sheets. It was dropped in v1.7.0
(Anthony, 2026-10-30): on batch 506 it was 206 pages and 28MB that nobody
opened. It was also the only page-level accounting, so `build` now LOGS how
many tube sheets it bound against how many the batch holds, and `no_sheet`
still names every tube that reached no binder.

Nothing here ever writes outside the folder it is handed, and it only ever
creates files - no drawing in the batch is modified in place.
"""
import re
from pathlib import Path

import fitz

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:                       # standalone / CLI testing
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

PART_RE = re.compile(r'^[A-Z]{1,2}\d{6,7}-[A-Z0-9]+-\d+[A-Z]?$')
SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)')
STAMP_COLOR = (0.0, 0.42, 0.80)      # the blue the hand-stamped drawings use
HIGHLIGHT = (1.0, 0.93, 0.30)        # the yellow over the saw cut dimension


def _size_name(desc):
    """A source material as Carrie names a packet file: `4.0 SQ X 0.25`.

    Her packets spell a square tube `4.0 SQ X 0.25` and a rectangular one
    `6.0 X 4.0 X 0.50`, and drop the `NOM`. The number tokens are reused exactly
    as the organizer prints them (`0.50`, never `0.5`), which is what lands the
    name on hers character for character.
    """
    m = SIZE_RE.search(str(desc or "").upper())
    if m is None:
        return str(desc or "").strip()
    a, b, wall = m.groups()
    return f"{a} SQ X {wall}" if a == b else f"{a} X {b} X {wall}"


def _open(path):
    """fitz.open with the OneDrive + long-path guardrails (Hard Rules 6, 7)."""
    sdk.ensure_local(path)
    return fitz.open(sdk.long_path(path))


# ────────────────────────────────────────────────── what a drawing sheet IS

def classify(path, tube_parts):
    """-> [(page_index, kind, parts)] for EVERY sheet in one drawing PDF.

    kind is 'assembly' (the sheet names two or more parts), 'tube' (names
    exactly one, and it is on the batch's tube roster) or 'other' (a plate, a
    rod, anything else).

    Page-level on purpose: an assembly PDF carries its own assembly sheet on
    page 1 and each member tube's sheet after it, so a first-page-only pass
    found 47 of the batch's 60 tubes and left the rest out of their binder.
    """
    try:
        doc = _open(path)
    except Exception:
        return []
    out = []
    try:
        for i in range(doc.page_count):
            names = []
            for w in doc[i].get_text("words"):
                t = w[4].strip().rstrip(",").upper()
                if PART_RE.match(t) and t not in names:
                    names.append(t)
            if len(names) >= 2:
                out.append((i, "assembly", names))
            elif len(names) == 1 and names[0] in tube_parts:
                out.append((i, "tube", names))
            else:
                out.append((i, "other", names))
    finally:
        doc.close()
    return out


def survey(batch_path, tube_parts, log=None, cancel_event=None):
    """Classify every SHEET of every shop drawing in the batch, once.

    Returns [(path, page_index, kind, parts)] in path order. One pass, because
    each sheet is wanted by more than one packet and re-reading the tree per
    packet is the slow part.
    """
    out = []
    seen_stems = set()
    for i, p in enumerate(sorted(Path(batch_path).rglob("*.pdf"))):
        if i % 32 == 0 and cancel_event is not None:
            sdk.raise_if_cancelled(cancel_event)
        if "CAD-AND-SHOP-PRINTS" not in str(p).upper():
            continue
        # a repeat order carries the same sheet under REPEAT BATCHES; one copy
        # of each drawing is enough
        if p.stem.upper() in seen_stems:
            continue
        seen_stems.add(p.stem.upper())
        for page_i, kind, parts in classify(p, tube_parts):
            out.append((p, page_i, kind, parts))
    if log:
        kinds = {}
        for _p, _i, kind, _n in out:
            kinds[kind] = kinds.get(kind, 0) + 1
        log(f"Sheets surveyed: {kinds}")
    return out


# ───────────────────────────────────────────────────────────── the stamping

def _stamp_page(page, order):
    """Put `ORDER: <n>` on the sheet and highlight its saw cut dimension.

    The order number goes in the clear space above the title block - the same
    place it is written by hand. The saw cut dimension is found by its own
    "(SAW CUT)" label, so a sheet without one is simply left unhighlighted.
    """
    words = page.get_text("words")
    rect = page.rect
    if order:
        page.insert_text((rect.width * 0.58, rect.height * 0.17),
                         f"ORDER: {order}", fontsize=13, fontname="hebo",
                         color=STAMP_COLOR)
    for i, w in enumerate(words):
        if w[4].strip().upper().lstrip("(") != "SAW":
            continue
        # "MUST GRIND BEVELS ON TUBE AFTER SAW OP." is note 2 on every sheet -
        # the notes band is the bottom of the page and is never a dimension
        if w[1] > rect.height * 0.86:
            continue
        box = fitz.Rect(w[:4])
        for nxt in words[i:i + 2]:                 # "(SAW" + "CUT)"
            if nxt[4].strip().upper().rstrip(")") in ("SAW", "CUT"):
                box |= fitz.Rect(nxt[:4])
        # the number this label belongs to sits just above or beside it
        best = None
        for v in words:
            if not re.match(r'^\(?\d+\.\d{2}\)?$', v[4].strip()):
                continue
            d = abs((v[0] + v[2]) / 2 - (w[0] + w[2]) / 2) + \
                abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2)
            if d <= 70 and (best is None or d < best[0]):
                best = (d, fitz.Rect(v[:4]))
        if best is None:
            continue        # a "SAW" with no dimension beside it is prose
        box |= best[1]
        page.draw_rect(box + (-2, -2, 2, 2), color=None, fill=HIGHLIGHT,
                       overlay=False)


# ───────────────────────────────────────────────────────────── the binders

def _append(out_doc, sheet, order=None, stamp=False):
    """Append ONE sheet - (path, page_index) - optionally stamped."""
    path, page_i = sheet
    src = _open(path)
    try:
        start = out_doc.page_count
        out_doc.insert_pdf(src, from_page=page_i, to_page=page_i)
    finally:
        src.close()
    if stamp:
        _stamp_page(out_doc[start], order)
    return 1


def build(out_dir: Path, batch_no, materials, drawings, log):
    """Write the packet sets.

    Returns (written, no_sheet) - [(path, pages)] and the tubes that have no
    individual drawing anywhere in the batch, so a short binder is reported
    rather than silently short.
    """
    out_dir = Path(out_dir)
    sdk.ensure_dir(out_dir)
    written, no_sheet = [], []
    # every tube sheet that made it into a binder, so the count at the end can
    # be checked against what the batch holds
    all_bound = set()

    by_part = {}
    for _serial, entries in materials:
        for e in entries:
            by_part[e["part"]] = e
    tube_sheet, assembly_of = {}, {}
    for path, page_i, kind, parts in drawings:
        if kind == "tube" and parts:
            tube_sheet.setdefault(parts[0], (path, page_i))
        elif kind == "assembly":
            for name in parts:
                assembly_of.setdefault(name, (path, page_i))

    # 1 + 2 - one binder per source material
    for serial, entries in materials:
        saw = entries[0]["pallet"] == "SAW"
        doc = fitz.open()
        used_assemblies = set()
        pages = 0
        try:
            # grouped by order, the way the hand-built packets read
            for e in sorted(entries, key=lambda e: (e["order"], e["part"])):
                if saw:
                    asm = assembly_of.get(e["part"])
                    if asm is not None and asm not in used_assemblies:
                        used_assemblies.add(asm)
                        pages += _append(doc, asm, e["order"], stamp=True)
                sheet = tube_sheet.get(e["part"])
                if sheet is None:
                    no_sheet.append(e)
                    continue
                pages += _append(doc, sheet, e["order"], stamp=saw)
                all_bound.add(sheet)
            if not pages:
                continue
            # every packet is named the way Carrie's hand-built set is,
            # saw and laser alike: `SAW.4_4.0 SQ X 0.375.pdf`, `2.1_4.0 SQ X
            # 0.25.pdf` (Anthony, 2026-10-27)
            name = (f"{entries[0]['packet']}_"
                    f"{_size_name(entries[0]['desc'])}.pdf")
            dest = out_dir / _safe(name)
            doc.save(sdk.long_path(dest), garbage=3, deflate=True)
            written.append((dest, pages))
            log(f"  {dest.name}  ({pages} pages)")
        finally:
            doc.close()

    # 3 - the drawings behind a flagged or blank length
    problems = [e for e in by_part.values()
                if e["review"] or e["length"] is None]
    if problems:
        doc = fitz.open()
        seen, pages = set(), 0
        try:
            for e in sorted(problems, key=lambda e: e["part"]):
                for src in (assembly_of.get(e["part"]),
                            tube_sheet.get(e["part"])):
                    if src is not None and src not in seen:
                        seen.add(src)
                        pages += _append(doc, src)
            if pages:
                dest = out_dir / "_Problem Drawings.pdf"
                doc.save(sdk.long_path(dest), garbage=3, deflate=True)
                written.append((dest, pages))
                log(f"  {dest.name}  ({pages} pages)")
        finally:
            doc.close()

    # `_Everything Else.pdf` lived here until v1.7.0 - a binder of every sheet
    # that was not an individual tube page, which on batch 506 was 206 pages
    # and 28MB nobody opened (Anthony, 2026-10-30). It was also the only
    # page-level net, so the accounting it did is now done by numbers instead:
    # `build` reports how many tube sheets it bound against how many the batch
    # has, and `no_sheet` names every tube that reached no binder.
    bound = len({(p, i) for p, i in all_bound})
    tube_sheets = len({(p, i) for p, i, kind, _n in drawings if kind == "tube"})
    log(f"Tube sheets bound: {bound} of the {tube_sheets} in the batch")

    if no_sheet:
        log(f"{len(no_sheet)} tube(s) have no individual drawing, so they are "
            f"not in a binder:")
        for e in no_sheet:
            log(f"    {e['part']}  ({e['desc']})")
    return written, no_sheet


def _safe(name):
    """A file name Windows will accept."""
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()
