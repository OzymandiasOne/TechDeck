"""
902 Batch Validator - v1.0.0
===========================
Answers one question about a 902 batch before anybody starts on it: **did EB
send everything needed for every part on the list - a usable DXF, a sound IGES,
and a print?**

(Built the same day as '902 Part Validator'; renamed when the prints check made
it a check of the whole BATCH. "missing prints" is 26 of the 35 notes the 902
crew has logged on the Working Forecast List - more than everything else put
together - so the prints are not an extra, they are most of the job.)

Why it exists (2026-09-21): EB told 902 not to ship a batch with parts missing,
and 3000+ parts sat on hold waiting on a handful of DXFs - because when a batch
arrives nobody can tell at a glance

  1. which PO parts have NO file at all,
  2. which DXFs are there but EMPTY (open fine, contain no geometry), and
  3. which IGES files are CORRUPT (cut off in transfer, or damaged), and
  4. which parts have NO PRINT in the WPDD folder.

This app checks all four and writes one color-coded PDF (the LST organizers'
report look, `sdk.ReportPdf`) that can go straight back to EB as the chase list.

It is READ-ONLY: nothing in the batch is moved, renamed or edited. The only
thing written is the report, into the batch folder (the PO workbook's folder -
the same place 902 DXF Prep puts its outputs).

How the pieces are judged
-------------------------
- The part list is the PO sheet, read by 902 DXF Prep's own reader (sibling
  import) so both apps agree on what a part number is and which tab is the PO.
- A file belongs to a part when its name reduces to that DYPN with DXF Prep's
  `clean_stem` (drops `(18x) `, `_A`, `_2`, `_FLAT-PATTERN#1`).
- The folder is searched with its subfolders, so numbered review folders,
  `IGES CONVERT` and `EXTRA` are all seen. A second copy of the same file does
  no harm - a part is covered when ANY of its files is good.
- DXF: a text DXF is walked group-by-group. "Geometry" is anything that cuts -
  LINE / ARC / CIRCLE / polylines / SPLINE / ELLIPSE / solids - plus an INSERT
  of a block that itself holds geometry. Text, dimensions, points and viewports
  do NOT count, so a drawing of only a title note is still EMPTY.
- IGES: the file's last line (the Terminate record) states how many lines each
  section has. A file cut off in transfer cannot match its own count, which is
  the check. Then the Directory section must list at least one real geometry
  entity - a curve/surface/solid flagged as geometry. Reference planes, points
  and annotation linework do not count: batch 3921 had two IGES files holding
  only those, and both converted to an empty DXF.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

# SDK bootstrap - works both in-process (TechDeck/frozen exe) and for standalone
# CLI testing (python plugins/902_batch_validator/run.py).
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

VERSION = "1.0.0"   # unreleased: prints check added before first ship

DXF_EXTS = {".dxf"}
IGES_EXTS = {".igs", ".iges"}

# File verdicts.
GOOD, EMPTY, BAD, REVIEW = "good", "empty", "bad", "review"


class FileCheck(NamedTuple):
    path: Path
    kind: str        # 'DXF' | 'IGES'
    verdict: str     # GOOD | EMPTY | BAD | REVIEW
    detail: str      # plain-English reason (or a short "N entities" note)


# ── DXF ─────────────────────────────────────────────────────────────────────

# Entities that are actual cut/shape geometry. VERTEX/SEQEND ride along with
# their POLYLINE; text, dimensions, points, viewports and attributes are not
# geometry - a DXF holding only those is what the floor calls "empty".
_DXF_GEOMETRY = {
    "LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE",
    "SOLID", "TRACE", "3DFACE", "3DSOLID", "REGION", "BODY", "SURFACE",
    "MESH", "HATCH", "MLINE", "HELIX", "XLINE", "RAY",
}
_BINARY_DXF_SENTINEL = b"AutoCAD Binary DXF"


def _dxf_pairs(text: str):
    """(group code, value) pairs of a text DXF. Tolerant: a non-numeric code
    line ends the walk (the caller then reports the file as damaged)."""
    lines = text.splitlines()
    for i in range(0, len(lines) - 1, 2):
        code = lines[i].strip()
        if not code.lstrip("-").isdigit():
            yield None, lines[i]
            return
        yield int(code), lines[i + 1].strip()


def check_dxf(path: Path, log=None) -> FileCheck:
    """Is there geometry in this DXF?"""
    sdk.ensure_local(path, log=log)
    with open(sdk.long_path(path), "rb") as fh:
        data = fh.read()
    if not data.strip():
        return FileCheck(path, "DXF", EMPTY, "the file is blank (0 bytes of drawing)")
    if data[:22].startswith(_BINARY_DXF_SENTINEL):
        return FileCheck(path, "DXF", REVIEW,
                         "binary DXF - cannot be read here, open it to check")
    if b"\x00" in data[:4096]:
        return FileCheck(path, "DXF", BAD, "not a DXF (the file holds binary junk)")

    text = data.decode("latin-1")          # never fails; DXF tags are ASCII
    section = None                         # current SECTION name
    expect_section_name = False
    saw_entities = saw_eof = damaged = False
    block_name: Optional[str] = None
    expect_block_name = False
    block_geometry: Dict[str, int] = defaultdict(int)     # block -> geometry count
    block_inserts: Dict[str, List[str]] = defaultdict(list)  # block -> inserted blocks
    top_geometry = 0
    top_inserts: List[str] = []
    other_entities = 0
    pending_insert_owner: Optional[str] = None   # '' = model space, else block name
    in_insert = False

    for code, value in _dxf_pairs(text):
        if code is None:
            damaged = True
            break
        if code == 0:
            in_insert = False
            up = value.upper()
            if up == "SECTION":
                expect_section_name = True
                continue
            if up == "ENDSEC":
                section = None
                continue
            if up == "EOF":
                saw_eof = True
                break
            if section == "BLOCKS":
                if up == "BLOCK":
                    expect_block_name = True
                    block_name = None
                elif up == "ENDBLK":
                    block_name = None
                elif block_name is not None:
                    if up in _DXF_GEOMETRY:
                        block_geometry[block_name] += 1
                    elif up == "INSERT":
                        in_insert, pending_insert_owner = True, block_name
            elif section == "ENTITIES":
                if up in _DXF_GEOMETRY:
                    top_geometry += 1
                elif up == "INSERT":
                    in_insert, pending_insert_owner = True, ""
                elif up not in ("VERTEX", "SEQEND"):
                    other_entities += 1
        elif code == 2:
            if expect_section_name:
                section = value.upper()
                expect_section_name = False
                if section == "ENTITIES":
                    saw_entities = True
            elif expect_block_name:
                block_name = value
                expect_block_name = False
            elif in_insert:
                if pending_insert_owner == "":
                    top_inserts.append(value)
                elif pending_insert_owner is not None:
                    block_inserts[pending_insert_owner].append(value)
                in_insert = False

    # A block "has geometry" if it draws any itself or inserts one that does.
    def _block_has_geometry(name: str, seen: set) -> bool:
        if name in seen:
            return False
        seen.add(name)
        if block_geometry.get(name):
            return True
        return any(_block_has_geometry(b, seen) for b in block_inserts.get(name, ()))

    geometry = top_geometry + sum(
        1 for b in top_inserts if _block_has_geometry(b, set()))

    if geometry:
        if damaged or not saw_eof:
            return FileCheck(path, "DXF", BAD,
                             "the file is cut off part way through (no end-of-file "
                             "marker) - AutoCAD will reject it")
        return FileCheck(path, "DXF", GOOD, f"{geometry} shape(s)")
    if damaged or not saw_entities:
        return FileCheck(path, "DXF", BAD,
                         "damaged - the drawing section could not be read")
    if other_entities:
        return FileCheck(path, "DXF", EMPTY,
                         f"no geometry - only {other_entities} text/dimension "
                         "item(s), nothing to cut")
    return FileCheck(path, "DXF", EMPTY, "no geometry - the drawing is empty")


# ── IGES ────────────────────────────────────────────────────────────────────

# What counts as PART geometry in an IGES directory entry. Two tests, both
# learned from real EB files in batch 3921 whose converted DXFs came out empty:
#  - the entity TYPE must be a curve, surface or solid. Reference planes (108),
#    points (116) and transformation matrices (124) are scaffolding, 2xx is
#    annotation, 3xx/4xx is structure. H4533302-168 held ONLY 108/116/124.
#  - its ENTITY-USE flag (status digits 5-6) must be 00 = geometry. H6980110-68
#    had four LINE entities, all flagged 01 = annotation (dimension linework):
#    no outline, empty DXF.
_IGES_SCAFFOLD_TYPES = {108, 116, 124}


def _iges_is_geometry(entity_type: int, status: str) -> bool:
    if entity_type in _IGES_SCAFFOLD_TYPES:
        return False
    if not (100 <= entity_type < 200 or 500 <= entity_type < 600):
        return False
    use_flag = status.replace(" ", "0").rjust(8, "0")[4:6]
    return use_flag == "00"


_IGES_TERMINATE_RE = re.compile(
    r"^S\s*(\d+)G\s*(\d+)D\s*(\d+)P\s*(\d+)")


def check_iges(path: Path, log=None) -> FileCheck:
    """Is this IGES whole, and does it hold geometry?"""
    sdk.ensure_local(path, log=log)
    with open(sdk.long_path(path), "rb") as fh:
        data = fh.read()
    if not data.strip():
        return FileCheck(path, "IGES", BAD, "the file is blank (0 bytes)")
    if b"\x00" in data:
        return FileCheck(path, "IGES", BAD,
                         "corrupt - the file holds binary junk, not IGES text")

    lines = [ln for ln in data.decode("latin-1").splitlines() if ln.strip()]
    counts = {"S": 0, "G": 0, "D": 0, "P": 0, "T": 0}
    stray = 0
    d_lines: List[str] = []
    for ln in lines:
        # Fixed 80-column records: section letter in column 73, then a sequence
        # number. (A 'C' flag record marks compressed IGES - not seen from EB.)
        letter = ln[72:73] if len(ln) >= 73 else ""
        if letter in counts and ln[73:80].strip().isdigit():
            counts[letter] += 1
            if letter == "D":
                d_lines.append(ln)
        else:
            stray += 1

    if not counts["S"] and not counts["G"] and not counts["D"]:
        return FileCheck(path, "IGES", BAD,
                         "corrupt - this is not an IGES file (none of its "
                         "sections are there)")
    last = lines[-1]
    if counts["T"] != 1 or last[72:73] != "T":
        return FileCheck(path, "IGES", BAD,
                         "corrupt - the file is cut off (its closing line is "
                         "missing)")
    m = _IGES_TERMINATE_RE.match(last)
    if not m:
        return FileCheck(path, "IGES", BAD,
                         "corrupt - the closing line cannot be read")
    said = dict(zip("SGDP", (int(x) for x in m.groups())))
    for letter, name in (("D", "directory"), ("P", "geometry data"),
                         ("G", "header"), ("S", "start")):
        if said[letter] != counts[letter]:
            return FileCheck(
                path, "IGES", BAD,
                f"corrupt - lines lost: says {said[letter]} {name} lines, "
                f"has {counts[letter]}")
    if stray:
        return FileCheck(path, "IGES", BAD,
                         f"corrupt - {stray} line(s) are damaged")
    if counts["D"] % 2:
        return FileCheck(path, "IGES", BAD,
                         "corrupt - the directory section is incomplete")

    geometry = 0
    for ln in d_lines[0::2]:               # each entity = 2 directory lines
        try:
            if _iges_is_geometry(int(ln[0:8]), ln[64:72]):
                geometry += 1
        except ValueError:
            return FileCheck(path, "IGES", BAD,
                             "corrupt - the directory section cannot be read")
    if not geometry:
        return FileCheck(path, "IGES", EMPTY,
                         "no part geometry - the model holds only notes, points "
                         "or reference planes, no outline to cut")
    return FileCheck(path, "IGES", GOOD, f"{geometry} shape(s)")


# ── prints ──────────────────────────────────────────────────────────────────
# "missing prints" is 26 of the 35 notes the 902 crew has logged on the
# Working Forecast List - three times everything else put together. The prints
# live in the batch's 'WPDD Files...' folder in two forms, and both count:
#   * one PDF, a page per VIEW (so pages != parts: FLAT-PATTERN, FORMED VIEW -
#     FRONT, ...). The part number is DRAWN on the page in a CAD stroke font -
#     there is no text layer on any of the 11 example PDFs - so it is read with
#     the on-device drawing reader (RapidOCR, the one 911 Inspection Dimensions
#     ships). It appears as 'R6432701-F107-1WJ_A' in a title box, or as
#     '001AV - R5730036-131 FLAT-PATTERN' under the view.
#   * loose images named ORDER_DYPN_n.jpg - the name is the part, no reading.

PRINT_PDF_EXTS = {".pdf"}
PRINT_IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# What a stroke font gets misread as. BOTH sides are folded, so a legitimate
# letter folds the same way on the part list and on the print.
_OCR_FOLD = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
                           "J": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})


def _print_key(text: str, fold: bool = True, dashed: bool = True) -> str:
    """A part number / OCR line reduced for comparison: upper-cased, every run
    of punctuation or spaces one dash ('R5730036- 131' reads fine), leading
    zeros off all-digit segments ('H5391611-010' IS 'H5391611-10', batch 4420),
    and optionally the misread fold and the dashes themselves removed."""
    s = str(text or "").upper()
    if fold:
        s = s.translate(_OCR_FOLD)
    segs = [g for g in re.split(r"[^A-Z0-9]+", s) if g]
    segs = [(g.lstrip("0") or "0") if g.isdigit() else g for g in segs]
    return ("-" if dashed else "").join(segs)


def _holds(line: str, part: str) -> bool:
    """`part` sits inside `line` and does not run on into more digits
    ('...-F8-1' must not match a print of '...-F8-10')."""
    i = line.find(part)
    while i != -1:
        if not line[i + len(part): i + len(part) + 1].isdigit():
            return True
        i = line.find(part, i + 1)
    return False


def _one_misread(line: str, part: str, head_len: int) -> bool:
    """`part` appears in `line` with exactly ONE character read wrong - and that
    character is in the DRAWING number (the first `head_len` characters), never
    in the piece number. Neighbouring parts differ by exactly one digit of the
    piece number ('-6' / '-8'): batch 4363 p43 is a clean print of H5742601-6,
    a part NOT on the list, and a looser rule credited it to H5742601-8."""
    n = len(part)
    for i in range(len(line) - n + 1):
        win = line[i:i + n]
        diff = [j for j in range(n) if win[j] != part[j]]
        if (len(diff) == 1 and diff[0] < head_len
                and not line[i + n: i + n + 1].isdigit()):
            return True
    return False


def _head(part: str) -> str:
    """The drawing number: everything before the first dash."""
    return part.split("-", 1)[0]


def match_print(lines: List[str], parts: List[str]) -> Tuple[Optional[str], str]:
    """Which part is this print for? (part, how) or (None, '').

    Tiers, strictest first; a tier answers only when it is UNAMBIGUOUS (the
    longest candidate, and only one of that length), else the next is tried:
      exact    the part number as written
      folded   after the stroke-font misread fold (O/0, I/1, ...)
      letter   the list says '-47M', the print says '-47' (every real batch
               that spells a part with a trailing M does this)
      misread  one character of the DRAWING number off (never the piece number)
      drawing  the page names a drawing number only ONE part on the list has
               ('SEE R524-7924 SHEET 13' - the part number itself is etched in
               a heavy marking font the reader garbles, batch 4363 p1)
    'letter', 'misread' and 'drawing' are guesses: the report says when one
    was used, and none of them fires unless it is unambiguous."""
    def longest(cands: List[str]) -> Optional[str]:
        if not cands:
            return None
        top = max(len(c) for c in cands)
        best = [c for c in cands if len(c) == top]
        return best[0] if len(best) == 1 else None

    for how, fold, dashed in (("exact", False, True), ("folded", True, True),
                              ("folded", True, False)):
        keyed = [_print_key(ln, fold, dashed) for ln in lines]
        hit = longest([p for p in parts
                       if any(_holds(k, _print_key(p, fold, dashed)) for k in keyed)])
        if hit:
            return hit, how
    keyed = [_print_key(ln) for ln in lines]
    lettered = [p for p in parts if re.search(r"\d[A-Z]$", p)
                and any(_holds(k, _print_key(p[:-1])) for k in keyed)]
    if len(lettered) == 1:
        return lettered[0], "letter"
    flat = [_print_key(ln, dashed=False) for ln in lines]
    near = [p for p in parts if len(_print_key(_head(p), dashed=False)) >= 7
            and any(_one_misread(k, _print_key(p, dashed=False),
                                 len(_print_key(_head(p), dashed=False))) for k in flat)]
    if len(near) == 1:
        return near[0], "misread"
    heads: Dict[str, List[str]] = defaultdict(list)
    for p in parts:
        heads[_squash(_head(p))].append(p)
    named = [ps[0] for h, ps in heads.items()
             if len(ps) == 1 and len(h) >= 7
             and any(_names_drawing_only(ln, h) for ln in lines)
             # ...and NO other line on the page pins it to a specific piece
             and not any(_names_a_piece(ln, h) for ln in lines)]
    if len(named) == 1:
        return named[0], "drawing"
    return None, ""


def _squash(text: str, fold: bool = True) -> str:
    """Letters and digits only. Folding is 1:1, so the folded and unfolded
    forms of one line stay the same length - position i is the same character."""
    s = re.sub(r"[^A-Z0-9]", "", str(text or "").upper())
    return s.translate(_OCR_FOLD) if fold else s


def _after_head(line: str, head: str):
    """For each place drawing `head` appears in `line`: the chunk of text that
    follows it, up to the next space or punctuation. Read off the UNFOLDED line
    (an 'S' is still an 'S', not a 5); the head is found in the folded one."""
    plain, breaks = [], set()
    for ch in str(line or "").upper():
        if ch.isalnum() and ch.isascii():
            plain.append(ch)
        else:
            breaks.add(len(plain))           # a separator sits before this index
    plain = "".join(plain)
    folded = plain.translate(_OCR_FOLD)
    i = folded.find(head)
    while i != -1:
        end = i + len(head)
        stop = min((b for b in breaks if b > end), default=len(plain))
        yield plain[end:stop]
        i = folded.find(head, i + 1)


def _names_a_piece(line: str, head: str) -> bool:
    """The line carries drawing `head` followed by a piece number - any chunk
    with a digit in it: '-72', '-F8-10' (a piece number can open with a
    letter), 'A34'."""
    return any(re.search(r"\d", chunk) for chunk in _after_head(line, head))


def _names_drawing_only(line: str, head: str) -> bool:
    """The line names drawing `head` and does NOT go on to a piece number.
    'SEE R524-7924 SHEET 13' qualifies; 'H5735152-72' does not - that is a
    clean print of one SPECIFIC piece, and if that piece is not on the list the
    print belongs to nobody (batch 4419 p5 is exactly this)."""
    chunks = list(_after_head(line, head))
    return bool(chunks) and not any(re.search(r"\d", c) for c in chunks)


class PrintPage(NamedTuple):
    source: str               # 'file.pdf p7' or 'ORDER_PART_1.jpg'
    part: Optional[str]       # the PO part it is a print of, or None
    how: str                  # match tier ('' when unmatched)
    read: str                 # what was read off it (for the unmatched list)


# The reader is sensitive to scale, and not in one direction: batch 4423 p7 reads
# at 1000 px and comes back EMPTY at 1700; batch 4406 p8 misreads '-11' as '-1I'
# only at 2600. So a page is tried at each scale, cheapest first, until one
# pass names a part. (pixel width to render at, detector side length)
_OCR_PASSES = ((1000, 960), (1700, 960), (2600, 2400))
_ocr_engines: Dict[int, object] = {}


def _ocr_engine(side: int):
    if side not in _ocr_engines:
        # Import AND construction guarded: RapidOCR loads its engines by name
        # out of its own config, so a build that did not bundle them raises at
        # construction, not import (Hard Rule 10's sibling class, gate E15).
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engines[side] = RapidOCR(
            det_model_path=None, det_limit_side_len=side, det_box_thresh=0.3,
            cls_model_path=None, rec_model_path=None, text_score=0.3)
    return _ocr_engines[side]


def _ocr_lines(page, width_px: int, side: int) -> List[str]:
    import fitz
    import numpy as np
    zoom = width_px / max(1.0, page.rect.width)
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width)
    result, _elapsed = _ocr_engine(side)(img)
    return [str(text) for _box, text, _score in (result or [])]


def find_print_folders(batch_root: Path) -> List[Path]:
    """The batch's prints folder(s): any folder directly under the batch folder
    with WPDD in its name ('WPDD Files-complete', 'WPDD Files COMPLETE',
    'WPDD Files-partial', 'WPDD Files' - EB never spells it the same twice)."""
    return sorted(d for d in batch_root.iterdir()
                  if sdk.is_dir(d) and "WPDD" in d.name.upper())


def read_prints(folders: List[Path], parts: List[str], log, cancel_event,
                progress=None) -> Tuple[List[PrintPage], str]:
    """Every print page / image in the WPDD folder(s), matched to a part.
    Returns (pages, problem): `problem` is '' or why pages could not be READ
    (the drawing reader would not start) - then unmatched PDF pages mean
    'not checked', never 'missing'."""
    import fitz
    pdfs: List[Path] = []
    images: List[Path] = []
    for folder in folders:
        for i, p in enumerate(folder.rglob("*")):
            if i % 64 == 0:
                sdk.raise_if_cancelled(cancel_event)
            if p.name.startswith("~$") or not sdk.is_file(p):
                continue
            if p.suffix.lower() in PRINT_PDF_EXTS:
                pdfs.append(p)
            elif p.suffix.lower() in PRINT_IMG_EXTS:
                images.append(p)

    out: List[PrintPage] = []
    for img in sorted(images):
        # ORDER_DYPN_n.jpg - each underscore piece on its own, or the trailing
        # '_1' reads as the part number running on into another digit.
        part, how = match_print([t for t in img.stem.split("_") if t], parts)
        out.append(PrintPage(img.name, part, how, img.stem))

    problem = ""
    docs = []
    for pdf in sorted(pdfs):
        try:
            sdk.ensure_local(pdf, log=log)
            docs.append((pdf, fitz.open(sdk.long_path(pdf))))
        except sdk.UserFacingError:
            raise
        except Exception as e:
            out.append(PrintPage(pdf.name, None, "", f"could not be opened ({e})"))
    total = sum(doc.page_count for _p, doc in docs) or 1
    done = 0
    try:
        for pdf, doc in docs:
            for n in range(doc.page_count):
                sdk.raise_if_cancelled(cancel_event)
                page = doc[n]
                source = f"{pdf.name} p{n + 1}"
                typed = [ln for ln in page.get_text().splitlines() if ln.strip()]
                part, how = match_print(typed, parts) if typed else (None, "")
                read = typed
                if not part and not problem:
                    for width_px, side in _OCR_PASSES:
                        try:
                            read = _ocr_lines(page, width_px, side)
                        except Exception as e:      # reader will not start
                            problem = str(e) or e.__class__.__name__
                            log(f"  WARNING: the drawing reader could not start "
                                f"({problem}) - print pages cannot be read.")
                            break
                        part, how = match_print(read, parts)
                        if part:
                            break
                partish = [ln for ln in read if re.search(r"\d{4,}", ln)]
                out.append(PrintPage(source, part, how, "; ".join(partish[:3])))
                done += 1
                if progress:
                    progress(done / total)
    finally:
        for _p, doc in docs:
            doc.close()
    return out, problem


# ── batch context ───────────────────────────────────────────────────────────

_prep_module = None


def _prep():
    """902 DXF Prep's run.py - the ONE home of the 902 PO reader, the DYPN
    shape and the filename -> DYPN rule. Both apps must agree on all three."""
    global _prep_module
    if _prep_module is None:
        _prep_module = sdk.load_sibling("902_dxf_prep", anchor=__file__)
    return _prep_module


def _find_po(work_folder: Path, log) -> Optional[Path]:
    """The PO/pricing workbook: in the picked folder, else up to two folders
    above it (the part files often sit a level or two under the batch folder)."""
    prep = _prep()
    folder = work_folder
    for _ in range(3):
        hit = prep._find_pricing_workbook(folder, log)
        if hit is not None:
            return hit
        if folder.parent == folder:
            break
        folder = folder.parent
    return None


def _scan_files(work_folder: Path, cancel_event) -> List[Path]:
    """Every DXF/IGES under the picked folder, subfolders included."""
    out: List[Path] = []
    for i, p in enumerate(work_folder.rglob("*")):
        if i % 64 == 0:
            sdk.raise_if_cancelled(cancel_event)
        if p.suffix.lower() in DXF_EXTS | IGES_EXTS and sdk.is_file(p) \
                and not p.name.startswith("~$"):
            out.append(p)
    return sorted(out, key=lambda p: str(p).upper())


class PartResult(NamedTuple):
    """One PO part and every file that belongs to it.

    EB sends each part as a DXF + IGES PAIR (209 of 209 across 13 example
    batches), and the DXF is the file 902 cuts from - so each kind is judged
    on its own and a part has an ISSUE when either one is wrong:

      missing   no DXF was sent (with or without an IGES)
      unusable  a DXF was sent, but it is empty or damaged
      corrupt   an IGES was sent, but it is corrupt or holds no part
      no_print  no print was FOUND (no WPDD page or image names the part).
                Not the same as "EB sent none" - a print we could not read
                is a print we did not find, so the wording says found.
      look      a file could not be checked here (binary DXF)

    A kind is fine as soon as ONE of its files is good, so a second copy of a
    file (IGES CONVERT, a numbered review folder) never causes an issue."""
    dypn: str
    qty: float
    files: List[FileCheck]
    matched_as: str = ""      # the file's spelling, when it differs from the PO's
    prints: Optional[List[PrintPage]] = None   # None = prints were not checked

    def _of(self, kind: str) -> List[FileCheck]:
        return [f for f in self.files if f.kind == kind]

    def _state(self, kind: str) -> str:
        """'none' | 'good' | 'review' | 'bad' for this part's DXF or IGES."""
        files = self._of(kind)
        if not files:
            return "none"
        if any(f.verdict == GOOD for f in files):
            return "good"
        if any(f.verdict == REVIEW for f in files):
            return "review"
        return "bad"

    @property
    def missing(self) -> bool:
        return self._state("DXF") == "none"

    @property
    def unusable(self) -> bool:
        return self._state("DXF") == "bad"

    @property
    def corrupt(self) -> bool:
        return self._state("IGES") == "bad"

    @property
    def look(self) -> bool:
        return "review" in (self._state("DXF"), self._state("IGES"))

    @property
    def no_print(self) -> bool:
        return self.prints is not None and not self.prints

    @property
    def issue(self) -> bool:
        return (self.missing or self.unusable or self.corrupt or self.no_print
                or self.look)

    def _first_bad(self, kind: str) -> FileCheck:
        return next(f for f in self._of(kind) if f.verdict != GOOD)

    @property
    def wrong(self) -> str:
        """The 'What is wrong' cell: every problem, in plain words. On a part
        with no issue it is blank, or a short note worth knowing."""
        bits: List[str] = []
        iges = self._state("IGES")
        if self.missing:
            bits.append("No file was sent" if iges == "none"
                        else "No DXF was sent (IGES only)")
        elif self.unusable:
            bits.append(f"DXF: {self._first_bad('DXF').detail}")
        elif self._state("DXF") == "review":
            bits.append(f"DXF: {self._first_bad('DXF').detail}")
        if self.corrupt:
            bits.append(f"IGES: {self._first_bad('IGES').detail}")
        if self.no_print:
            bits.append("No print found, please review PDF for print if available")
        if not self.issue and iges == "none":
            bits.append("Note: DXF only, no IGES was sent")
        # A guess is only worth a note when it is ALL the part has to go on.
        sure = [pg for pg in (self.prints or []) if pg.how in ("exact", "folded")]
        guess = [pg for pg in (self.prints or []) if pg.how in ("misread", "drawing")]
        if guess and not sure:
            bits.append("Note: print matched "
                        + ("on a near read" if guess[0].how == "misread"
                           else "by drawing number only")
                        + f" ({guess[0].source}) - check it")
        if self.matched_as:
            bits.append(f"Note: the files are named {self.matched_as}")
        return ";  ".join(bits)


def reconcile(po_rows, checks: List[FileCheck]
              ) -> Tuple[List[PartResult], List[Tuple[FileCheck, str]]]:
    """(one PartResult per distinct PO DYPN in PO order, extras). An extra is
    (file check, why): its name is not a part number, or is not on this PO."""
    prep = _prep()
    qty: Dict[str, float] = {}
    for dypn, q in po_rows:
        qty[dypn] = qty.get(dypn, 0) + q

    by_name: Dict[str, List[FileCheck]] = defaultdict(list)
    for fc in checks:
        by_name[prep.clean_stem(fc.path.stem).upper()].append(fc)

    by_part: Dict[str, List[FileCheck]] = defaultdict(list)
    matched_as: Dict[str, str] = {}
    leftover: Dict[str, List[FileCheck]] = {}
    for name, files in by_name.items():
        if name in qty:
            by_part[name] += files
        else:
            leftover[name] = files

    # The PO and the file do not always spell a piece the same way: real EB
    # batches list 'R4142704-145M' while the files are 'R4142704-145' (4423,
    # 4426, 4457). A trailing letter is the same piece (sdk.match_dypn_variant,
    # the LST organizers' rule): only an UNAMBIGUOUS match against a part that
    # has no files of its own counts, and the report says so - never silent.
    for name in sorted(leftover):
        if not prep._PART_RE.match(name):
            continue
        open_parts = [d for d in qty if d not in by_part]
        hit = sdk.match_dypn_variant(name, open_parts)
        if hit:
            by_part[hit] += leftover.pop(name)
            matched_as[hit] = name

    extras: List[Tuple[FileCheck, str]] = []
    for name, files in leftover.items():
        why = ("not on this PO" if prep._PART_RE.match(name)
               else "file name is not a part number")
        extras += [(f, why) for f in files]
    parts = [PartResult(d, q, by_part.get(d, []), matched_as.get(d, ""))
             for d, q in qty.items()]
    return parts, extras


# ── report ──────────────────────────────────────────────────────────────────

def _where(fc: FileCheck, work_folder: Path) -> str:
    """The file's folder, relative to the picked folder."""
    try:
        rel = fc.path.parent.relative_to(work_folder)
    except ValueError:
        return str(fc.path.parent)
    return str(rel) if str(rel) != "." else "(picked folder)"


def _fmt_qty(q: float) -> str:
    return str(int(q)) if float(q).is_integer() else f"{q:g}"


def write_report(path: Path, label: str, po_name: str, work_folder: Path,
                 parts: List[PartResult], extras, checks: List[FileCheck],
                 prints: Optional[List[PrintPage]] = None,
                 prints_note: str = "") -> None:
    """Page 1: the counts, then EVERY part with Issue Y/N + what is wrong.
    Next page on: the breakdown by kind of problem (layout asked for by the
    902 lead 2026-09-21 - the full list first, because that is the page that
    gets read; the breakdown is the reference behind it)."""
    C = sdk.REPORT_COLORS
    missing = [p for p in parts if p.missing]
    unusable = [p for p in parts if p.unusable]
    corrupt = [p for p in parts if p.corrupt]
    look = [p for p in parts if p.look]
    no_print = [p for p in parts if p.no_print]
    issues = [p for p in parts if p.issue]
    prints_checked = prints is not None
    stray_prints = [pg for pg in (prints or []) if not pg.part]
    bad_dxf = [f for f in checks if f.kind == "DXF" and f.verdict in (EMPTY, BAD)]
    bad_iges = [f for f in checks if f.kind == "IGES" and f.verdict in (EMPTY, BAD)]

    d = sdk.ReportPdf()
    d.text(f"902 Batch Validator  -  {label}", size=17, bold=True, color=C["band"])
    d.text(f"Generated {time.strftime('%Y-%m-%d %H:%M')}   |   Part list: {po_name}"
           f"   |   {len(checks)} part file(s)"
           + (f" + {len(prints)} print page(s)" if prints_checked else "")
           + " checked", size=8.5, color=C["grey"])
    d.row([f"Folder: {work_folder}"], [528], size=7.5, h=11, tcolor=C["grey"],
          wrap=True)
    d.gap(8)

    summary = [
        ("TARGET PARTS  -  on the part list", len(parts), C["target_bg"]),
        ("MISSING  -  no DXF was sent", len(missing), C["miss_bg"]),
        ("UNUSABLE  -  the DXF is empty or damaged", len(unusable), C["miss_bg"]),
        ("CORRUPT  -  the IGES is corrupt or empty", len(corrupt), C["miss_bg"]),
        ("NO PRINT  -  no print found, review the PDF",
         len(no_print) if prints_checked else "not checked", C["miss_bg"]),
        ("NEEDS A LOOK  -  could not be checked here", len(look), C["rev_bg"]),
    ]
    for i, (lab, val, fill) in enumerate(summary):
        if val == "not checked":
            bg = C["rev_bg"]
        else:
            bg = fill if (i == 0 or val) else C["ok_bg"]
        d.row([lab, str(val)], [400, 90], size=9.5, h=18, bold=True, fill=bg)
    d.gap(4)
    if prints_note:
        d.row([prints_note], [528], size=8.5, h=13, bold=True, tcolor=C["rev_tx"],
              wrap=True)
    if issues:
        d.text(f"NOT READY  -  {len(issues)} of {len(parts)} part(s) have an issue.",
               size=10, bold=True, color=C["miss_tx"])
    else:
        d.text(f"READY  -  all {len(parts)} part(s) have a good file"
               + (" and a print." if prints_checked else "."), size=10,
               bold=True, color=C["ok_tx"])
    d.gap(10)

    d.text("EVERY PART", size=11, bold=True, color=C["band"])
    widths = [140, 35, 40, 305]
    d.header_row(["Part", "Qty", "Issue", "What is wrong"], widths)
    for i, p in enumerate(sorted(parts, key=lambda p: p.dypn)):
        if p.issue:
            only_look = p.look and not (p.missing or p.unusable or p.corrupt)
            fill, tcolor = ((C["rev_bg"], C["rev_tx"]) if only_look
                            else (C["miss_bg"], C["miss_tx"]))
        else:
            fill, tcolor = (C["zebra"] if i % 2 else C["white"]), C["ink"]
        d.row([p.dypn, _fmt_qty(p.qty), "Y" if p.issue else "N", p.wrong],
              widths, size=8, h=13, bold=p.issue, fill=fill, tcolor=tcolor,
              wrap=True)

    # ── the breakdown starts on its own page ──
    d.new_page()
    d.text(f"BREAKDOWN  -  {label}", size=14, bold=True, color=C["band"])
    d.gap(8)

    def _part_section(title, note, rows, kind):
        d.text(title, size=11, bold=True, color=C["miss_tx"])
        if note:
            d.text(note, size=8, color=C["grey"])
        if not rows:
            d.text("None.", size=9, color=C["ok_tx"])
            d.gap(10)
            return
        w = [110, 30, 160, 220]
        d.header_row(["Part", "Qty", "File", "What is wrong"], w)
        for p in rows:
            # one row per distinct bad file - a second copy is the same file
            shown = list({(f.path.name, f.detail): f for f in p._of(kind)
                          if f.verdict != GOOD}.values())
            for j, f in enumerate(shown):
                d.row([p.dypn if j == 0 else "", _fmt_qty(p.qty) if j == 0 else "",
                       f.path.name, f.detail], w, size=8, h=14,
                      fill=C["miss_bg"], tcolor=C["miss_tx"], wrap=True)
        d.gap(10)

    d.text("MISSING  -  NO DXF WAS SENT FOR THESE PARTS", size=11, bold=True,
           color=C["miss_tx"])
    if missing:
        d.header_row(["Part", "Qty", "What was sent"], [200, 40, 280])
        for p in missing:
            sent = ("nothing" if p._state("IGES") == "none"
                    else "an IGES only: " + ", ".join(sorted({f.path.name for f in p._of("IGES")})))
            d.row([p.dypn, _fmt_qty(p.qty), sent], [200, 40, 280], size=8, h=14,
                  fill=C["miss_bg"], tcolor=C["miss_tx"], wrap=True)
    else:
        d.text("None.", size=9, color=C["ok_tx"])
    d.gap(10)

    _part_section("UNUSABLE  -  THE DXF IS EMPTY OR DAMAGED",
                  "Parts on the list whose DXF cannot be cut from.", unusable, "DXF")

    def _file_section(title, note, files):
        d.text(title, size=11, bold=True, color=C["rev_tx"])
        if note:
            d.text(note, size=8, color=C["grey"])
        if not files:
            d.text("None.", size=9, color=C["ok_tx"])
            d.gap(10)
            return
        w = [190, 110, 220]
        d.header_row(["File", "In folder", "What is wrong"], w)
        for f in files:
            d.row([f.path.name, _where(f, work_folder), f.detail], w, size=8,
                  h=14, fill=C["rev_bg"], tcolor=C["rev_tx"], wrap=True)
        d.gap(10)

    _file_section("EMPTY OR DAMAGED DXF FILES",
                  "Every bad DXF file in the folder, copies and files not on the "
                  "list included.", bad_dxf)
    _file_section("CORRUPT OR EMPTY IGES FILES",
                  "Every bad IGES file in the folder, copies and files not on the "
                  "list included.", bad_iges)

    if prints_checked:
        d.text("NO PRINT  -  NO PRINT FOUND FOR THESE PARTS", size=11, bold=True,
               color=C["miss_tx"])
        d.text("No page of the WPDD PDF and no WPDD image names the part.",
               size=8, color=C["grey"])
        if no_print:
            d.header_row(["Part", "Qty"], [400, 120])
            for p in no_print:
                d.row([p.dypn, _fmt_qty(p.qty)], [400, 120], size=8, h=14,
                      fill=C["miss_bg"], tcolor=C["miss_tx"])
        else:
            d.text("None.", size=9, color=C["ok_tx"])
        d.gap(10)

        d.text("PRINTS THAT MATCH NO PART  -  check these by eye", size=11,
               bold=True, color=C["rev_tx"])
        d.row(["A print of a part that is not on the list, a page with no part "
               "number on it, or one the reader could not make out. If a part above "
               "has no print, its print may be one of these."], [528], size=8, h=12,
              tcolor=C["grey"], wrap=True)
        if stray_prints:
            w = [230, 290]
            d.header_row(["Print", "What was read off it"], w)
            for pg in stray_prints:
                d.row([pg.source, pg.read or "(nothing that looks like a part number)"],
                      w, size=8, h=14, fill=C["rev_bg"], tcolor=C["rev_tx"], wrap=True)
        else:
            d.text("None.", size=9, color=C["ok_tx"])
        d.gap(10)

    d.text("NOT ON THE PO  -  files that match no part on the list", size=11,
           bold=True, color=C["extra_tx"])
    if extras:
        w = [230, 120, 170]
        d.header_row(["File", "In folder", "Why"], w)
        for f, why in extras:
            d.row([f.path.name, _where(f, work_folder), why], w, size=8, h=14,
                  fill=C["extra_bg"], tcolor=C["extra_tx"], wrap=True)
    else:
        d.text("None.", size=9, color=C["ok_tx"])

    d.save(path)


# ── entry point ─────────────────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event) -> None:
    log = params.get("log", print)
    log(f"Starting 902 Batch Validator (v{VERSION})...")
    progress_callback(0)

    start_dir = ""
    try:
        roots = sdk.pilot_program_roots()
        if roots:
            start_dir = str(roots[0])
    except Exception:
        pass
    raw = sdk.request_directory(
        params, "Select the batch folder, or the folder with its part files "
                "(DXF / IGES)", start_dir)
    if cancel_event.is_set():
        return
    if not raw:
        log("Folder selection cancelled - nothing was run.")
        cancel_event.set()   # user cancel: not a successful (ticket-earning) run
        return
    work_folder = Path(raw.strip().strip('"'))
    if not sdk.is_dir(work_folder):
        raise sdk.UserFacingError(
            f"That folder could not be found: {work_folder}",
            "Pick the batch folder, or the folder that holds its DXF / IGES files.")
    log(f"Picked folder: {work_folder}")

    # ── the part list = the parts that must have a file ──
    po = _find_po(work_folder, log)
    if po is None:
        raise sdk.UserFacingError(
            "No part list was found in that folder or the two folders above it - "
            "neither the pricing workbook nor EB's 'B#### 902 OFFLOAD TO ASA' "
            "workbook.",
            "Put one of them in the batch folder, then run again.")
    log(f"Part list: {po.name}")
    batch, po_rows = _prep()._load_po_rows(po, log)
    if not po_rows:
        raise sdk.UserFacingError(
            f"No parts could be read from {po.name} - no visible sheet has a "
            "DYPN column with a quantity column beside it.",
            "Check that it is the batch's part list and that its PO / BATCH tab "
            "is not hidden.")
    batch_root = po.parent
    if not batch:
        m = (re.search(r"\b(\d{3,5})\b", batch_root.name)
             or re.search(r"\b(\d{3,5})\b", work_folder.name))
        batch = m.group(1) if m else None
    label = f"Batch {batch}" if batch else work_folder.name
    progress_callback(10)

    # ── find + check every part file ──
    log("Looking for DXF / IGES files (subfolders included)...")
    files = _scan_files(work_folder, cancel_event)
    n_dxf = sum(1 for p in files if p.suffix.lower() in DXF_EXTS)
    log(f"  {n_dxf} DXF + {len(files) - n_dxf} IGES file(s).")
    sdk.prefetch_paths(files, cancel_event=cancel_event)

    checks: List[FileCheck] = []
    for i, p in enumerate(files, 1):
        sdk.raise_if_cancelled(cancel_event)
        try:
            fc = (check_dxf if p.suffix.lower() in DXF_EXTS else check_iges)(p, log)
        except sdk.UserFacingError:
            raise
        except Exception as e:             # unreadable on disk = a bad file
            kind = "DXF" if p.suffix.lower() in DXF_EXTS else "IGES"
            fc = FileCheck(p, kind, BAD, f"could not be opened ({e})")
        checks.append(fc)
        if fc.verdict != GOOD:
            log(f"  {fc.verdict.upper():6} {p.name}: {fc.detail}")
        if i % 10 == 0 or i == len(files):
            progress_callback(10 + int(75 * i / len(files)))

    # ── prints (the WPDD folder) ──
    parts, extras = reconcile(po_rows, checks)
    prints: Optional[List[PrintPage]] = None
    prints_note = ""
    folders = find_print_folders(batch_root)
    if not folders:
        prints = []
        prints_note = ("No 'WPDD' prints folder was found in the batch folder, so "
                       "every part is listed as having no print.")
        log(f"  WARNING: {prints_note}")
    else:
        log(f"Reading the prints in {', '.join(f.name for f in folders)} "
            "(a scanned page takes a second or two)...")
        prints, problem = read_prints(
            folders, [p.dypn for p in parts], log, cancel_event,
            progress=lambda f: progress_callback(85 + int(9 * f)))
        if problem:
            # Pages that could not be READ are not evidence of a missing print.
            prints = None
            prints_note = ("The prints were NOT checked: the drawing reader could "
                           f"not start ({problem}). Update TechDeck, and if it still "
                           "fails send a Debug Report to a TechDeck admin.")
    if prints is not None:
        by_part: Dict[str, List[PrintPage]] = defaultdict(list)
        for pg in prints:
            if pg.part:
                by_part[pg.part].append(pg)
        parts = [p._replace(prints=by_part.get(p.dypn, [])) for p in parts]
        guessed = [pg for pg in prints if pg.how in ("letter", "misread", "drawing")]
        log(f"  {len(prints)} print page(s) / image(s): "
            f"{sum(1 for pg in prints if pg.part)} matched to a part, "
            f"{sum(1 for pg in prints if not pg.part)} not.")
        for pg in guessed:
            log(f"  NOTE: {pg.source} matched to {pg.part} "
                + {"letter": "(the print leaves off the trailing letter)",
                   "misread": f"on a near read ({pg.read})",
                   "drawing": f"by drawing number only ({pg.read})"}[pg.how])

    # ── report ──
    missing = [p for p in parts if p.missing]
    unusable = [p for p in parts if p.unusable]
    corrupt = [p for p in parts if p.corrupt]
    look = [p for p in parts if p.look]
    no_print = [p for p in parts if p.no_print]
    issues = [p for p in parts if p.issue]
    for p in parts:
        if p.matched_as:
            log(f"  NOTE: {p.dypn} matched to files named {p.matched_as} "
                "(same piece, different trailing letter)")

    report = batch_root / f"{batch or work_folder.name} - BATCH VALIDATION REPORT.pdf"
    try:
        write_report(report, label, po.name, work_folder, parts, extras, checks,
                     prints, prints_note)
    except PermissionError:
        raise sdk.UserFacingError(
            f"The report could not be saved - '{report.name}' is open.",
            "Close the PDF and run again.")
    progress_callback(95)

    log("=" * 60)
    log(f"902 Batch Validator - {label}")
    log(f"  Target parts:                 {len(parts)}")
    log(f"  Missing (no DXF sent):        {len(missing)}")
    log(f"  Unusable (DXF empty/damaged): {len(unusable)}")
    log(f"  Corrupt (IGES corrupt/empty): {len(corrupt)}")
    log(f"  No print found:               "
        f"{len(no_print) if prints is not None else 'NOT CHECKED'}")
    log(f"  Needs a look:                 {len(look)}")
    log(f"  Files not on the PO:          {len(extras)}")
    log("=" * 60)
    if issues:
        log("Parts with an issue (copy this list to send to EB):")
        for p in sorted(issues, key=lambda p: p.dypn):
            log(f"  {p.dypn}  -  {p.wrong}")
        lines = [f"{len(issues)} of {len(parts)} part(s) have an issue:", ""]
        lines += [f"  - {p.dypn}: {p.wrong}"
                  for p in sorted(issues, key=lambda p: p.dypn)[:15]]
        if len(issues) > 15:
            lines.append(f"  ...and {len(issues) - 15} more (see the report)")
        sdk.show_warning(params, f"902 Batch Validator - {label}", "\n".join(lines))
    else:
        log(f"READY - all {len(parts)} part(s) have a good file"
            + (" and a print." if prints is not None else "."))
    if prints is None and hasattr(sdk, "set_run_outcome"):
        # The run finished, but one of its checks did not happen - say so.
        sdk.set_run_outcome(params, sdk.RUN_OUTCOME_PARTIAL,
                            "the prints were not checked (the drawing reader "
                            "could not start)")

    sdk.link_output(params, f"Open the batch validation report for {label}",
                    report, prefix="[REPORT]")
    progress_callback(100)


if __name__ == "__main__":
    import threading
    run(params={"log": print, "settings": {}},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=threading.Event())
