"""
922 Difficulty Stamper Plugin for TechDeck

DriveWorks prints a "DIFFICULT" label on a part drawing when the part has a
compound cut (see the Difficulty layer in the TUBE and CLEVIS projects). The
floor never sees the part drawings up front, though - they see the work packet.

This app closes that gap: it reads every part drawing under an order's
CAD-AND-SHOP-PRINTS folder, and if any of them carry the label it stamps
DIFFICULT on the first page of that order's work packet, the same way the
Pallet Stamper stamps the batch and pallet.
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk


# --- The label we look for on part drawings -----------------------------------
#
# DriveWorks writes it as its own text span, 18pt CenturyGothic-Bold. Matching a
# SUBSTRING would be wrong: a part number like "CLEVISDIFFICULTY-4" contains the
# same letters, so a substring match flags every part of a job that merely
# happens to be named that way. Match the whole span, nothing less.
DIFFICULT_LABEL = "DIFFICULT"

# Our stamp on the work packet is red; fitz packs RGB(1,0,0) as 0xFF0000.
# Colour is what separates our stamp from a black DIFFICULT that would appear if
# a drawing page were ever bound into the packet - only ours is ever redacted.
_RED_COLOR_INT = 0xFF0000

# Where the modeled parts live inside an order folder.
_CAD_FOLDER = "CAD-AND-SHOP-PRINTS"

# Batch folders that aren't orders.
_NON_ORDER_SUFFIX = "- Documentation"
_NON_ORDER_NAMES = {"repeat batches"}

# Office lock files (~$…) and stray Python temp files (tmpab12cd34.pdf) are not
# real PDFs of ours. A leftover temp PDF in an order folder would otherwise be
# picked up as that order's work packet by "the first PDF in the folder".
_NOT_A_REAL_PDF_RE = re.compile(r'^(~\$|tmp[a-z0-9_]{6,}$)', re.IGNORECASE)


def _is_real_pdf(path: Path) -> bool:
    return not _NOT_A_REAL_PDF_RE.match(path.stem)


def parse_batch_number(raw: str) -> Optional[str]:
    """Extract a numeric batch number from user input.

    Accepts "401", "Batch 401", "PO 401", "PO#401", ... Returns the digit
    string, or None if there are no digits.
    """
    match = re.search(r'\d+', raw or "")
    return match.group(0) if match else None


def _is_label_span(text: str) -> bool:
    """True when a span IS the DIFFICULT label (not merely contains it)."""
    return (text or "").strip().upper() == DIFFICULT_LABEL


def drawing_has_label(pdf_path: Path, log) -> Optional[bool]:
    """Does this part drawing carry the DIFFICULT label?

    Returns True/False, or None if the PDF could not be read (the caller
    reports unreadable drawings rather than silently treating them as clean -
    a drawing we couldn't open might well be a difficult one).
    """
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download (Hard Rule 13)
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        log(f"WARNING: Could not read {pdf_path.name}: {e}")
        return None

    try:
        for page in doc:
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if _is_label_span(span.get("text", "")):
                            return True
        return False
    except Exception as e:
        log(f"WARNING: Could not read {pdf_path.name}: {e}")
        return None
    finally:
        doc.close()


def find_part_drawings(order_dir: Path) -> List[Path]:
    """Every part-drawing PDF under an order's CAD-AND-SHOP-PRINTS folder.

    Resolved case-insensitively by scan rather than by a hardcoded join, since
    real folders vary (Hard Rule / defensive folder resolution).
    """
    cad = None
    for child in order_dir.iterdir():
        if child.is_dir() and child.name.strip().casefold() == _CAD_FOLDER.casefold():
            cad = child
            break
    if cad is None:
        return []
    return sorted(p for p in cad.rglob("*.pdf") if p.is_file() and _is_real_pdf(p))


def find_work_packet(order_dir: Path) -> Optional[Path]:
    """The order's work-packet PDF.

    Prefer a PDF whose name starts with the order number (the folder is
    "{ORDER}-{PPN}"), otherwise fall back to the first PDF in the folder -
    the same file the Pallet Stamper picks.
    """
    pdfs = sorted(p for p in order_dir.iterdir()
                  if p.is_file() and p.suffix.lower() == ".pdf" and _is_real_pdf(p))
    if not pdfs:
        return None
    order_no = order_dir.name.split('-', 1)[0].strip().upper()
    for p in pdfs:
        if p.stem.strip().upper().startswith(order_no):
            return p
    return pdfs[0]


def anchor_xy(page, h_offset_in: float, v_offset_in: float) -> Tuple[float, float]:
    """Stamp anchor in page coordinates, honouring page rotation.

    Same geometry as the Pallet Stamper so the two stamps line up.
    """
    ppi = 72.0
    off_x = h_offset_in * ppi
    off_y = v_offset_in * ppi
    w, h = page.rect.width, page.rect.height
    rot = page.rotation % 360

    if rot == 90:
        return off_y, h - off_x
    if rot == 180:
        return off_x, off_y
    if rot == 270:
        return w - off_y, off_x
    return w - off_x, h - off_y


def _find_stamp_rects(page) -> List[fitz.Rect]:
    """Rects of any DIFFICULT stamp this app previously put on the page."""
    rects = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("color", 0) != _RED_COLOR_INT:
                    continue
                if _is_label_span(span.get("text", "")):
                    b = span["bbox"]
                    rects.append(fitz.Rect(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2))
    return rects


def apply_stamp(pdf_path: Path, want_stamp: bool, font_size: int,
                h_offset_in: float, v_offset_in: float, log) -> Optional[str]:
    """Put the stamp on the work packet, or take it off.

    Returns "stamped", "removed", or "unchanged"; None if the PDF errored.
    A packet that needs no change is never rewritten.
    """
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download (Hard Rule 13)
        doc = fitz.open(str(pdf_path))
        saved = False
        try:
            page = doc[0]
            existing = _find_stamp_rects(page)

            if not want_stamp and not existing:
                return "unchanged"

            # Always clear an old stamp first, so a changed font size or offset
            # moves the stamp instead of printing a second one next to it.
            if existing:
                for r in existing:
                    page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions()

            if want_stamp:
                x, y = anchor_xy(page, h_offset_in, v_offset_in)
                page.insert_text(
                    fitz.Point(x, y),
                    DIFFICULT_LABEL,
                    fontsize=font_size,
                    fontname="helv",
                    fill=(1, 0, 0),
                    rotate=(-page.rotation) % 180,
                )

            sdk.save_pdf_atomic(doc, pdf_path)  # closes doc - don't close again
            saved = True
        finally:
            if not saved:
                try:
                    doc.close()
                except Exception:
                    pass

        return "stamped" if want_stamp else "removed"

    except Exception as e:
        log(f"ERROR: PDF error for {pdf_path.name}: {e}")
        return None


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    settings = params.get('settings', {})
    log = params.get('log', print)

    log("Starting 922 Difficulty Stamper...")
    progress_callback(0)

    base_path = settings.get('base_path', '')
    font_size = int(settings.get('font_size', 18) or 18)
    h_offset = float(settings.get('h_offset_inches', 4.0) or 4.0)
    v_offset = float(settings.get('v_offset_inches', 6.5) or 6.5)

    root = sdk.resolve_922_root(base_path)
    if root is None or not root.exists():
        raise sdk.UserFacingError(
            "Couldn't find the '922 QTDR Production Packages' folder.",
            "Make sure OneDrive is synced, or set the Base Directory in this "
            "plugin's Settings, then run again.")

    raw = sdk.request_batch_number(
        params, 'Enter batch number (e.g. "488", "Batch 488", "PO 488"):')
    batch_no = parse_batch_number((raw or "").strip())
    if not batch_no:
        raise sdk.UserFacingError(
            "That isn't a batch number I can read.",
            'Run it again and enter the batch number (e.g. "488" or "Batch 488").')

    batch_path = sdk.find_922_batch_path(root, batch_no)
    if batch_path is None:
        raise sdk.UserFacingError(
            f"Couldn't find Batch {batch_no} (checked the live folder and "
            f"'1 - Completed').",
            "Double-check the batch number and that OneDrive is synced, then "
            "run again.")

    log(f"Batch folder: {batch_path.name}")

    order_dirs = [
        d for d in sorted(batch_path.iterdir())
        if d.is_dir()
        and not d.name.endswith(_NON_ORDER_SUFFIX)
        and d.name.strip().casefold() not in _NON_ORDER_NAMES
    ]
    total = len(order_dirs)
    log(f"Scanning {total} order folders for the DIFFICULT label...")
    log("")
    progress_callback(5)

    difficult: List[Tuple[str, List[str]]] = []   # (order, [part drawing names])
    stamped: List[str] = []
    removed: List[str] = []
    not_modeled: List[str] = []
    no_packet: List[str] = []
    unreadable: List[str] = []
    failures: List[Tuple[str, Path]] = []         # (order, work packet)

    for idx, order_dir in enumerate(order_dirs):
        sdk.raise_if_cancelled(cancel_event)
        progress_callback(5 + int((idx / max(total, 1)) * 85))

        order_no = order_dir.name.split('-', 1)[0].strip().upper()

        drawings = find_part_drawings(order_dir)
        if not drawings:
            not_modeled.append(order_dir.name)
            continue

        hits: List[str] = []
        for i, pdf in enumerate(drawings):
            if i % 16 == 0:
                sdk.raise_if_cancelled(cancel_event)
            found = drawing_has_label(pdf, log)
            if found is None:
                unreadable.append(f"{order_no}: {pdf.name}")
            elif found:
                hits.append(pdf.name)

        packet = find_work_packet(order_dir)
        if packet is None:
            if hits:
                no_packet.append(f"{order_no} ({len(hits)} difficult part(s))")
            else:
                no_packet.append(order_no)
            continue

        if hits:
            difficult.append((order_no, hits))

        result = apply_stamp(packet, bool(hits), font_size, h_offset, v_offset, log)
        if result is None:
            failures.append((order_no, packet))
        elif result == "stamped":
            stamped.append(order_no)
            log(f"Stamped {order_no} - {len(hits)} difficult part(s)")
        elif result == "removed":
            removed.append(order_no)
            log(f"Removed old stamp from {order_no} (no difficult parts any more)")

    # --- Retry pass -----------------------------------------------------------
    # A OneDrive hiccup on one packet shouldn't cost a hand-stamp if the file
    # hydrates fine a minute later. Go back once, then report what's left.
    if failures:
        sdk.raise_if_cancelled(cancel_event)
        log("")
        log(f"Retrying {len(failures)} failed stamp(s)...")
        still_failed: List[Tuple[str, Path]] = []
        for order_no, packet in failures:
            sdk.raise_if_cancelled(cancel_event)
            want = any(o == order_no for o, _ in difficult)
            if apply_stamp(packet, want, font_size, h_offset, v_offset, log) is None:
                still_failed.append((order_no, packet))
            else:
                log(f"Stamped on retry: {order_no}")
                stamped.append(order_no)
        failures = still_failed

    progress_callback(95)

    log("")
    log("=" * 50)
    log(f"DIFFICULTY SUMMARY - BATCH {batch_no}")
    log("=" * 50)
    log(f"Orders scanned:        {total}")
    log(f"Difficult orders:      {len(difficult)}")
    log(f"Packets stamped:       {len(stamped)}")
    if removed:
        log(f"Stamps removed:        {len(removed)}")
    if not_modeled:
        log(f"Not modeled yet:       {len(not_modeled)}")
    if no_packet:
        log(f"No work packet found:  {len(no_packet)}")
    if unreadable:
        log(f"Drawings unreadable:   {len(unreadable)}")
    if failures:
        log(f"NOT stamped:           {len(failures)}")

    if difficult:
        log("")
        log("Difficult orders and the parts that made them difficult:")
        for order_no, hits in difficult:
            log(f"  {order_no}")
            for name in hits:
                log(f"      {name}")

    if not_modeled:
        log("")
        log("No CAD-AND-SHOP-PRINTS folder (not modeled yet) - skipped:")
        for name in not_modeled:
            log(f"  {name}")

    if no_packet:
        log("")
        log("No work-packet PDF in the order folder:")
        for name in no_packet:
            log(f"  {name}")

    if unreadable:
        log("")
        log("Part drawings that could not be read (check these by hand):")
        for name in unreadable:
            log(f"  {name}")

    log("=" * 50)
    progress_callback(100)

    # Anything the user has to act on gets a popup - a console line scrolls past.
    problems = []
    if failures:
        problems.append(
            "These work packets could not be stamped (even after a retry). "
            "Stamp them by hand:\n" +
            "\n".join(f"  {o}\n      {p}" for o, p in failures))
    if unreadable:
        problems.append(
            "These part drawings could not be read, so they were not checked "
            "for the DIFFICULT label:\n" +
            "\n".join(f"  {n}" for n in unreadable))
    if no_packet:
        problems.append(
            "These orders have no work-packet PDF to stamp:\n" +
            "\n".join(f"  {n}" for n in no_packet))

    if problems:
        sdk.show_warning(params, "Difficulty Stamper - needs a look",
                         "\n\n".join(problems))
        if hasattr(sdk, "set_run_outcome"):
            sdk.set_run_outcome(
                params, sdk.RUN_OUTCOME_WARNING,
                f"{len(failures)} unstamped, {len(unreadable)} unreadable drawing(s), "
                f"{len(no_packet)} order(s) with no packet")
        log("WARNING: Completed, but some items need a look")
    else:
        log("All done successfully!")


if __name__ == "__main__":
    import threading

    def progress(p):
        print(f"Progress: {p}%")

    run(params={'settings': {}, 'log': print},
        progress_callback=progress,
        cancel_event=threading.Event())
    print("\nDone!")
