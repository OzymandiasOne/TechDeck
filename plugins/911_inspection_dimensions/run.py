"""911 Inspection Dimensions.

Reads the PART SKETCH pages out of a folder of 911 nest-package PDFs and logs every
dimension printed on each drawing - plus the weld preps (the KB codes) - so they can
be dropped onto an inspection sheet instead of being typed off the paper by hand.

The drawings are RASTER images inside the PDF (there is no selectable text on them),
so the dimensions come out of an on-device OCR pass (RapidOCR / ONNX Runtime - no
network, no external exe). Everything above the drawing frame is real PDF text and is
read directly, which is where the part number / work order / FAB DIM come from.

Two things the reader deliberately does NOT count as inspection dimensions:
  * anything labelled REF (reference only) - listed separately,
  * numbers that live inside a drawing NOTE ("0.375 THK MECHANICAL SQUARE STEEL TUBE").
"""

import os
import re
import glob
import datetime

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:  # standalone CLI testing
    import sys
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk


VERSION = "0.2.0"

# The detector is run twice at different working resolutions and the two results are
# merged: the small pass reliably picks up crowded dimension stacks, the large pass
# picks up small isolated callouts (an R .25 hanging off a corner). Either one alone
# misses roughly one dimension in ten on these drawings.
_DET_SIDES = (736, 2000)
_PAD_PX = 60          # white margin so text flush with the image edge still detects
_RENDER_DPI = 300


# --------------------------------------------------------------------------- OCR
_ENGINES = None


def _engines(log):
    """Lazily build the OCR engines (model load is ~1s and only needed on a real run)."""
    global _ENGINES
    if _ENGINES is not None:
        return _ENGINES
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - dependency guard
        raise sdk.UserFacingError(
            "The drawing reader could not start up (%s)." % exc,
            "This app needs the built-in drawing reader. Update TechDeck to the latest "
            "version, and if it still fails send a Debug Report to a TechDeck admin.",
        )
    log("Starting the drawing reader...")
    _ENGINES = [
        RapidOCR(
            det_model_path=None,
            det_limit_side_len=side,
            det_box_thresh=0.3,
            cls_model_path=None,
            rec_model_path=None,
            text_score=0.3,
        )
        for side in _DET_SIDES
    ]
    return _ENGINES


# --------------------------------------------------------------- text normalisation
# The recogniser is a general-purpose model, so a stroke-font period sometimes comes
# back as a CJK full stop and a hyphen as a CJK dash. Fold those back before parsing.
_TRANSLATE = {
    ord("。"): ".", ord("．"): ".", ord("·"): ".",
    ord("，"): ",", ord("、"): ",",
    ord("一"): "-", ord("－"): "-", ord("–"): "-", ord("—"): "-",
    ord("Ｘ"): "X", ord("×"): "X",
}
for _i, _ch in enumerate("０１２３４５６７８９"):
    _TRANSLATE[ord(_ch)] = str(_i)

_EDGE_JUNK = re.compile(r"^[\s\-_=~|,'`\"]+|[\s\-_=~|,'`\"]+$")


def _norm(text):
    """Fold OCR quirks and strip the arrowhead dashes that glue onto a dimension."""
    t = (text or "").translate(_TRANSLATE)
    t = t.replace("　", " ").strip().upper()
    return _EDGE_JUNK.sub("", t)


# ----------------------------------------------------------------- classification
# Words that may sit next to a number without making it prose.
MODIFIER_WORDS = {
    "TYP", "REF", "THK", "MIN", "MAX", "NOM", "DIA", "RAD", "R", "X",
    "SNIPE", "CUT", "NEAT", "PL", "PLCS", "PLC", "EA", "DEG", "BOTH", "SIDES",
    "NS", "FS", "AND", "OR", "TO", "OF",
}

# --- weld preps -------------------------------------------------------------
# A weld prep is called out as a code starting "KB" on a leader line, usually with
# the side it applies to on the line underneath ("KB114" / "NS & FS" = near side and
# far side). Codes come back from OCR with the leader dash glued on ("-KB114") and
# sometimes with the digits spaced out ("KB 1 1 4"), so match on the space-stripped
# text after trimming leading punctuation.
WELD_PREP_RE = re.compile(r"^KB[A-Z0-9]{1,6}$")
SIDE_RE = re.compile(r"^(?:[NFB]S(?:&[NFB]S)?|BOTHSIDES?|NEARSIDE|FARSIDE)$")
# Modifiers that ride along on the dimension itself.
TRAILING_MODS = ("TYP", "REF", "THK", "MIN", "MAX", "NOM", "SNIPE")

_NUM = r"\d*\.?\d+"
NUM_RE = re.compile(r"^%s$" % _NUM)
COMPOUND_RE = re.compile(r"^(%s)(?:X(%s))+$" % (_NUM, _NUM))
COUNT_PREFIX_RE = re.compile(r"^\(?(\d{1,2})\)?X(.+)$")
ANGLE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:°|DEG)$")
FRACTION_RE = re.compile(r"^(\d+)-(\d+)/(\d+)$")
# a chamfer callout: 1.00 X 45 deg
CHAMFER_RE = re.compile(r"^(%s)X(\d+(?:\.\d+)?)(?:°|DEG)$" % _NUM)


def classify(raw):
    """Turn one OCR token into (kind, value, mods), or None if it isn't a dimension."""
    t = _norm(raw).replace(" ", "")
    if not t:
        return None
    mods = []
    kind = "linear"

    cham = CHAMFER_RE.match(t)
    if cham:
        return "chamfer", "%s X %s deg" % (cham.group(1), cham.group(2)), mods

    ang = ANGLE_RE.match(t)
    if ang:
        return "angle", ang.group(1), mods

    if t.startswith("DIA"):
        kind, t = "diameter", t[3:]
    elif t and t[0] in "Ø⌀" and len(t) > 1:
        kind, t = "diameter", t[1:]
    elif t.startswith("R") and len(t) > 1 and (t[1].isdigit() or t[1] == "."):
        kind, t = "radius", t[1:]

    # a leading count multiplier: 2X .50, (4)X .50
    m = COUNT_PREFIX_RE.match(t)
    if m and not m.group(2).startswith("."):
        pass  # 1.00X1.00 style compound, not a count - fall through
    elif m:
        mods.append("%sX" % m.group(1))
        t = m.group(2)

    for word in TRAILING_MODS:
        if t.endswith(word) and len(t) > len(word):
            mods.append(word)
            t = t[: -len(word)]
        if t.startswith(word) and len(t) > len(word):
            mods.append(word)
            t = t[len(word):]
    t = _EDGE_JUNK.sub("", t)

    if COMPOUND_RE.match(t):
        return kind, " X ".join(t.split("X")), mods
    if FRACTION_RE.match(t):
        return kind, t, mods
    if not NUM_RE.match(t):
        return None
    # A bare integer with no decimal point is almost never a dimension on these
    # drawings (they are all printed to two places) - it is a view tag or a stray.
    if "." not in t:
        return None
    return kind, t, mods


# ------------------------------------------------------------------------ geometry
def _bbox(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def _near_label(item, items, label):
    """True when a standalone `label` box sits against this one on any side."""
    x0, y0, x1, y1 = item["bb"]
    h = max(1.0, y1 - y0)
    w = max(1.0, x1 - x0)
    for other in items:
        if other is item or other["word"] != label:
            continue
        ox0, oy0, ox1, oy1 = other["bb"]
        xover = min(x1, ox1) - max(x0, ox0)
        yover = min(y1, oy1) - max(y0, oy0)
        if xover > 0.3 * min(w, ox1 - ox0):
            gap = max(oy0 - y1, y0 - oy1)          # above or below
            if -0.2 * h <= gap <= 1.4 * h:
                return True
        if yover > 0.4 * min(h, oy1 - oy0):
            gap = max(ox0 - x1, x0 - ox1)          # left or right
            if -0.2 * w <= gap <= 2.5 * h:
                return True
    return False


def _weld_code(word):
    """Normalise one OCR token to a weld-prep code, or None."""
    t = re.sub(r"^[^A-Z0-9]+", "", word).replace(" ", "")
    if not t.startswith("KB"):
        return None
    # trim a side note that OCR glued onto the code ("KB114NS&FS")
    m = re.match(r"^(KB[A-Z0-9]{1,6}?)((?:[NFB]S(?:&[NFB]S)?)?)$", t)
    if not m:
        return None
    code = m.group(1)
    if not WELD_PREP_RE.match(code) or not any(c.isdigit() for c in code):
        return None
    return code, _fmt_side(m.group(2))


def _fmt_side(side):
    """Put the spaces back into a side note the glue-strip ran together."""
    return re.sub(r"\s+", " ", (side or "").replace("&", " & ")).strip()


def weld_preps(items):
    """Find the KB weld-prep callouts and the side each applies to.

    Run over the RAW box list, independent of the note/dimension passes - a weld
    prep is neither, and must not be lost to either one.
    """
    found = []
    for it in items:
        parsed = _weld_code(it["word"])
        if not parsed:
            continue
        code, glued_side = parsed
        side = glued_side
        if not side:
            side = _side_note(it, items)
        found.append({"code": code, "side": side, "score": it["score"], "bb": it["bb"]})

    # one callout can be detected twice (both OCR passes, slightly different boxes)
    unique = []
    for w in sorted(found, key=lambda d: (-len(d["side"]), -d["score"])):
        cx, cy = (w["bb"][0] + w["bb"][2]) / 2.0, (w["bb"][1] + w["bb"][3]) / 2.0
        h = max(1.0, w["bb"][3] - w["bb"][1])
        if any(u["code"] == w["code"]
               and abs(cx - (u["bb"][0] + u["bb"][2]) / 2.0) < 3 * h
               and abs(cy - (u["bb"][1] + u["bb"][3]) / 2.0) < 3 * h
               for u in unique):
            continue
        unique.append(w)
    unique.sort(key=lambda d: (round(d["bb"][1] / 60.0), d["bb"][0]))
    return unique


def _side_note(item, items):
    """The NS / FS / NS & FS label sitting under (or beside) a weld-prep code."""
    x0, y0, x1, y1 = item["bb"]
    h = max(1.0, y1 - y0)
    best = ""
    for other in items:
        if other is item:
            continue
        flat = other["word"].replace(" ", "")
        if not SIDE_RE.match(flat):
            continue
        ox0, oy0, ox1, oy1 = other["bb"]
        xover = min(x1, ox1) - max(x0, ox0)
        yover = min(y1, oy1) - max(y0, oy0)
        close = (xover > 0.3 * min(x1 - x0, ox1 - ox0)
                 and -0.2 * h <= max(oy0 - y1, y0 - oy1) <= 1.6 * h)
        beside = (yover > 0.4 * min(h, oy1 - oy0)
                  and -0.2 * h <= max(ox0 - x1, x0 - ox1) <= 2.5 * h)
        if (close or beside) and len(other["word"]) > len(best):
            best = other["word"]
    return _fmt_side(best)


def _note_lines(items):
    """Group boxes into text lines and return the ones that read as prose notes.

    A note is a line (or a stacked paragraph of lines) carrying two or more ordinary
    words - "0.375 THK MECHANICAL SQUARE STEEL TUBE", "CUT FROM / 3.00X3.00X.188 /
    ANGLE IRON". Numbers inside one are stock/material callouts, not dimensions.
    """
    lines = []
    for it in sorted(items, key=lambda d: d["bb"][1]):
        placed = False
        for line in lines:
            ly0, ly1 = line["y0"], line["y1"]
            h = min(it["bb"][3] - it["bb"][1], ly1 - ly0)
            if min(it["bb"][3], ly1) - max(it["bb"][1], ly0) > 0.5 * max(1.0, h):
                line["items"].append(it)
                line["y0"] = min(ly0, it["bb"][1])
                line["y1"] = max(ly1, it["bb"][3])
                placed = True
                break
        if not placed:
            lines.append({"items": [it], "y0": it["bb"][1], "y1": it["bb"][3]})

    # stack lines into paragraphs (tight vertical spacing + overlapping x range)
    paras = []
    for line in sorted(lines, key=lambda l: l["y0"]):
        lx0 = min(i["bb"][0] for i in line["items"])
        lx1 = max(i["bb"][2] for i in line["items"])
        h = line["y1"] - line["y0"]
        for para in paras:
            if (0 <= line["y0"] - para["y1"] <= 0.9 * h
                    and min(lx1, para["x1"]) - max(lx0, para["x0"]) > 0):
                para["lines"].append(line)
                para["y1"] = line["y1"]
                para["x0"] = min(para["x0"], lx0)
                para["x1"] = max(para["x1"], lx1)
                break
        else:
            paras.append({"lines": [line], "y0": line["y0"], "y1": line["y1"],
                          "x0": lx0, "x1": lx1})

    notes = []
    for para in paras:
        members = [i for line in para["lines"] for i in line["items"]]
        words = []
        for it in members:
            for chunk in re.split(r"[^A-Z]+", it["word"]):
                if len(chunk) >= 3 and chunk not in MODIFIER_WORDS:
                    words.append(chunk)
        if len(words) >= 2:
            text = " ".join(
                i["word"] for i in sorted(members, key=lambda d: (round(d["bb"][1] / 20), d["bb"][0]))
            )
            notes.append({"text": text, "members": members})
    return notes


# ---------------------------------------------------------------------- page work
def drawing_clip(page):
    """Rect of the biggest embedded raster on the page - the drawing frame."""
    best, best_px = None, 0
    for img in page.get_images(full=True):
        px = img[2] * img[3]
        if px < 400 * 400:
            continue
        for rect in page.get_image_rects(img[0]):
            if px > best_px:
                best_px, best = px, rect
    return best


def _read_boxes(page, clip, log):
    """Render the drawing and run both OCR passes over it, merged and de-duplicated."""
    import fitz
    import numpy as np

    scale = _RENDER_DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = arr[:, :, :3]
    elif pix.n == 1:
        arr = np.repeat(arr, 3, axis=2)
    arr = np.ascontiguousarray(arr[:, :, ::-1])           # RGB -> BGR for the model
    padded = np.full((arr.shape[0] + 2 * _PAD_PX, arr.shape[1] + 2 * _PAD_PX, 3), 255, np.uint8)
    padded[_PAD_PX:_PAD_PX + arr.shape[0], _PAD_PX:_PAD_PX + arr.shape[1]] = arr

    items = []
    for engine in _engines(log):
        result, _ = engine(padded)
        for box, txt, score in (result or []):
            word = _norm(txt)
            if not word:
                continue
            items.append({"raw": txt, "word": word, "bb": _bbox(box), "score": float(score)})

    # Merge the two passes. The same text can come back as one wide box from one pass
    # and two narrower boxes from the other, so drop anything whose box mostly sits
    # inside a longer reading, then collapse near-identical centres.
    items.sort(key=lambda d: (-(d["bb"][2] - d["bb"][0]) * (d["bb"][3] - d["bb"][1]), -d["score"]))
    merged = []
    for it in items:
        x0, y0, x1, y1 = it["bb"]
        area = max(1.0, (x1 - x0) * (y1 - y0))
        h = max(1.0, y1 - y0)
        keep = True
        for seen in merged:
            sx0, sy0, sx1, sy1 = seen["bb"]
            overlap = (max(0.0, min(x1, sx1) - max(x0, sx0))
                       * max(0.0, min(y1, sy1) - max(y0, sy0)))
            if overlap > 0.7 * area:
                keep = False
                break
            if (abs((x0 + x1) - (sx0 + sx1)) / 2.0 < h
                    and abs((y0 + y1) - (sy0 + sy1)) / 2.0 < h):
                keep = False
                break
        if keep:
            merged.append(it)
    return merged


def read_drawing(page, clip, log):
    """Return (dimensions, notes, weld preps) for one drawing page."""
    items = _read_boxes(page, clip, log)
    welds = weld_preps(items)
    notes = _note_lines(items)
    in_note = {id(m) for n in notes for m in n["members"]}

    dims = []
    for it in items:
        if id(it) in in_note:
            continue
        parsed = classify(it["raw"])
        if not parsed:
            continue
        kind, value, mods = parsed
        ref = "REF" in mods or _near_label(it, items, "REF")
        if _near_label(it, items, "TYP") and "TYP" not in mods:
            mods.append("TYP")
        if _near_label(it, items, "SNIPE") and "SNIPE" not in mods:
            mods.append("SNIPE")
        dims.append({
            "kind": kind,
            "value": value,
            "mods": [m for m in mods if m != "REF"],
            "ref": ref,
            "raw": it["raw"],
            "score": it["score"],
            "bb": it["bb"],
        })
    dims.sort(key=lambda d: (round(d["bb"][1] / 60.0), d["bb"][0]))
    return dims, [n["text"] for n in notes], welds


_FIELD_RE = {
    "part": re.compile(r"PART:\s*([A-Z0-9][A-Z0-9\-\.]*)"),
    "rev": re.compile(r"REV/SEQ:\s*([A-Z0-9/]+)"),
    "qty": re.compile(r"QTY:\s*(\d+)"),
    "noun": re.compile(r"NOUN:\s*([A-Z][A-Z ]*?)\s*\n"),
    "size": re.compile(r"SIZE:\s*\n?\s*([^\n]+)"),
    "fab_dim": re.compile(r"FAB DIM:\s*\n?\s*([0-9.]+)"),
    "srce": re.compile(r"SRCE:\s*([A-Z0-9]+)"),
}


# A blank title-block cell makes the next label bleed into the capture ("REV/SEQ: SRCE").
_LABELS = {"SRCE", "QTY", "NOUN", "MATL", "LVL", "FER", "SIZE", "DESC", "PART",
           "REV", "SEQ", "MFG", "NUC", "NON", "PRT", "WT", "FAB", "DIM", "SHIP", "DUE", "DTE"}


def title_block(page):
    """Pull the real-text header fields off a PART SKETCH page."""
    txt = page.get_text()
    out = {}
    for key, rx in _FIELD_RE.items():
        m = rx.search(txt)
        value = m.group(1).strip() if m else ""
        if value.rstrip(":").upper() in _LABELS:
            value = ""
        out[key] = value
    # the first line after the page counter is the work-order barcode label
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    out["work_order"] = ""
    for line in lines[1:4]:
        if re.fullmatch(r"[A-Z]{1,2}\d{5,}", line):
            out["work_order"] = line
            break
    return out


# ------------------------------------------------------------------------- report
def _fmt_dim(d):
    label = {"linear": "", "radius": "R ", "diameter": "DIA ",
             "angle": "", "chamfer": ""}.get(d["kind"], "")
    suffix = " deg" if d["kind"] == "angle" else ""
    mods = (" " + " ".join(dict.fromkeys(d["mods"]))) if d["mods"] else ""
    flag = "   <-- CHECK (low confidence)" if d["score"] < 0.55 else ""
    return "%s%s%s%s%s" % (label, d["value"], suffix, mods, flag)


def process_pdf(pdf_path, log, cancel_event, progress=None):
    """Read one nest package. Returns a list of part records."""
    import fitz

    sdk.ensure_local(pdf_path, log=log)
    doc = fitz.open(pdf_path)
    parts = []
    try:
        for index, page in enumerate(doc):
            sdk.raise_if_cancelled(cancel_event)
            text = page.get_text()
            clip = drawing_clip(page)
            is_sketch = "PART SKETCH" in text

            if is_sketch:
                info = title_block(page)
                record = dict(info)
                record.update({"page": index + 1, "dims": [], "notes": [],
                               "welds": [], "views": 0, "problem": ""})
                parts.append(record)
                if clip is None:
                    record["problem"] = (
                        "no drawing on the page - the PDF says the drawing image could "
                        "not be loaded when the packet was printed"
                        if "not reachable" in text else "no drawing image on the page"
                    )
                    log("   page %d  %s - %s" % (index + 1, info.get("part", "?"), record["problem"]))
                    continue
            elif clip is not None and parts:
                record = parts[-1]           # a continuation view of the part above
                record["views"] += 1
            else:
                continue

            dims, notes, welds = read_drawing(page, clip, log)
            record["dims"].extend(dims)
            for note in notes:
                if note not in record["notes"]:
                    record["notes"].append(note)
            for weld in welds:
                if not any(w["code"] == weld["code"] and w["side"] == weld["side"]
                           for w in record["welds"]):
                    record["welds"].append(weld)
            if progress:
                progress()
            keep = len([d for d in dims if not d["ref"]])
            log("   page %d  %-18s %d dimension(s)%s%s"
                % (index + 1, record.get("part", "?"), keep,
                   ", %d REF" % (len(dims) - keep) if len(dims) - keep else "",
                   ", weld prep %s" % "/".join(w["code"] for w in welds) if welds else ""))
    finally:
        doc.close()
    return parts


def build_report(folder, results, elapsed):
    """Render the whole run as the text file the user gets."""
    now = datetime.datetime.now()
    out = []
    add = out.append
    add("911 INSPECTION DIMENSIONS")
    add("=" * 78)
    add("Folder : %s" % folder)
    add("Run    : %s" % now.strftime("%Y-%m-%d %H:%M"))
    add("Reader : TechDeck 911 Inspection Dimensions v%s" % VERSION)
    add("")
    add("Dimensions and weld preps are read off the drawing picture, so CHECK them")
    add("against the paperwork before they go on an inspection sheet. Anything the")
    add("reader was unsure about is marked CHECK. Dimensions marked REF on the")
    add("drawing are listed under 'Reference only' and are NOT inspection")
    add("dimensions. Weld preps are the KB codes called out on the drawing, with")
    add("the side each one applies to (NS = near side, FS = far side).")
    add("")

    total_parts = total_dims = total_ref = total_welds = 0
    problems = []
    low_conf = []

    for pdf_name, parts in results:
        add("=" * 78)
        add("PDF: %s" % pdf_name)
        add("=" * 78)
        if not parts:
            add("  (no PART SKETCH pages found)")
            add("")
            continue
        for rec in parts:
            total_parts += 1
            add("")
            add("  PART %s" % (rec.get("part") or "(part number not readable)"))
            meta = []
            if rec.get("work_order"):
                meta.append("Work order %s" % rec["work_order"])
            if rec.get("rev"):
                meta.append("Rev/Seq %s" % rec["rev"])
            if rec.get("qty"):
                meta.append("Qty %s" % rec["qty"])
            if rec.get("noun"):
                meta.append(rec["noun"].title())
            add("    %s" % ("  |  ".join(meta) if meta else "-"))
            if rec.get("size"):
                add("    Size     : %s" % rec["size"])
            if rec.get("fab_dim"):
                add("    FAB DIM  : %s" % rec["fab_dim"])
            add("    Sketch page %d%s"
                % (rec["page"], " (+%d extra view page(s))" % rec["views"] if rec["views"] else ""))

            if rec["problem"]:
                add("    ** %s" % rec["problem"])
                problems.append("%s - %s: %s" % (pdf_name, rec.get("part", "?"), rec["problem"]))
                continue

            keep = [d for d in rec["dims"] if not d["ref"]]
            refs = [d for d in rec["dims"] if d["ref"]]
            total_dims += len(keep)
            total_ref += len(refs)
            add("")
            if keep:
                add("    DIMENSIONS (%d)" % len(keep))
                for d in keep:
                    add("      - %s" % _fmt_dim(d))
                    if d["score"] < 0.55:
                        low_conf.append("%s - %s: %s" % (pdf_name, rec.get("part", "?"), d["value"]))
            else:
                add("    DIMENSIONS (0)   ** nothing readable - check this drawing by hand **")
                problems.append("%s - %s: no dimensions read" % (pdf_name, rec.get("part", "?")))
            if rec["welds"]:
                total_welds += len(rec["welds"])
                add("    WELD PREPS (%d)" % len(rec["welds"]))
                for weld in rec["welds"]:
                    side = ("  %s" % weld["side"]) if weld["side"] else "  (no side marked)"
                    flag = "   <-- CHECK (low confidence)" if weld["score"] < 0.55 else ""
                    add("      - %s%s%s" % (weld["code"], side, flag))
                    if weld["score"] < 0.55:
                        low_conf.append("%s - %s: weld prep %s"
                                        % (pdf_name, rec.get("part", "?"), weld["code"]))
            if refs:
                add("    Reference only (not inspected): %s"
                    % ", ".join(_fmt_dim(d).replace("   <-- CHECK (low confidence)", "") for d in refs))
            if rec["notes"]:
                add("    Drawing notes:")
                for note in rec["notes"]:
                    add("      %s" % note)
        add("")

    add("=" * 78)
    add("SUMMARY")
    add("=" * 78)
    add("PDFs read           : %d" % len(results))
    add("Parts found         : %d" % total_parts)
    add("Dimensions logged   : %d" % total_dims)
    add("Reference (skipped) : %d" % total_ref)
    add("Weld preps logged   : %d" % total_welds)
    add("Time                : %.0f seconds" % elapsed)
    if problems:
        add("")
        add("NEEDS A HUMAN LOOK (%d)" % len(problems))
        for p in problems:
            add("  - %s" % p)
    if low_conf:
        add("")
        add("LOW CONFIDENCE READINGS (%d) - verify these against the drawing" % len(low_conf))
        for p in low_conf:
            add("  - %s" % p)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------- run
def run(params, progress_callback, cancel_event):
    import time

    log = params.get("log", print)
    settings = params.get("settings", {})
    console = params.get("console")

    folder = sdk.request_directory(
        params,
        "Select the folder of nest PDFs to read",
        start_dir=settings.get("base_path", "") or "",
    )
    if not folder or cancel_event.is_set():
        cancel_event.set()
        return

    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    pdfs = [p for p in pdfs if not os.path.basename(p).startswith("~$")]
    if not pdfs:
        raise sdk.UserFacingError(
            "There are no PDF files in that folder.",
            "Pick the folder that holds the nest package PDFs and run it again.",
        )

    log("Reading %d PDF(s) from %s" % (len(pdfs), folder))
    log("")

    # rough page budget so the bar moves sensibly across the whole run
    import fitz

    total_pages = 0
    for path in pdfs:
        sdk.raise_if_cancelled(cancel_event)
        try:
            sdk.ensure_local(path, log=log)
            with fitz.open(path) as doc:
                total_pages += sum(1 for pg in doc if drawing_clip(pg) is not None)
        except Exception:
            total_pages += 1
    done = [0]

    def tick():
        done[0] += 1
        progress_callback(min(97, int(5 + 92.0 * done[0] / max(1, total_pages))))

    started = time.time()
    results = []
    failed = []
    for path in pdfs:
        sdk.raise_if_cancelled(cancel_event)
        name = os.path.basename(path)
        log("%s" % name)
        try:
            results.append((name, process_pdf(path, log, cancel_event, tick)))
        except sdk.PluginCancelled:
            raise
        except sdk.UserFacingError:
            raise
        except Exception as exc:
            log("   ! could not read this PDF: %s" % exc)
            failed.append("%s (%s)" % (name, exc))
            results.append((name, []))
    elapsed = time.time() - started

    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    out_name = "911 Inspection Dimensions - %s - %s.txt" % (os.path.basename(folder.rstrip("\\/")), stamp)
    out_path = os.path.join(folder, out_name)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(build_report(folder, results, elapsed))

    parts = sum(len(p) for _, p in results)
    dims = sum(len([d for d in rec["dims"] if not d["ref"]]) for _, p in results for rec in p)
    log("")
    log("Read %d part(s), logged %d dimension(s) in %.0f seconds." % (parts, dims, elapsed))
    log("Saved: %s" % out_path)

    if console is not None and hasattr(console, "append_link"):
        try:
            console.append_link(out_name, out_path, prefix="REPORT", at_run_end=True)
        except TypeError:
            console.append_link(out_name, out_path)

    if failed and hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_WARNING,
            "%d PDF(s) could not be read: %s" % (len(failed), "; ".join(failed)),
        )
    progress_callback(100)


if __name__ == "__main__":  # headless harness
    import sys
    import threading

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    sdk.request_directory = lambda *a, **k: target
    run({"log": print, "settings": {}, "console": None}, lambda p: None, threading.Event())
