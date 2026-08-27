"""
922 Difficulty Stamper Plugin for TechDeck

DriveWorks prints a "DIFFICULT" label on a part drawing when the part has a
compound cut (see the Difficulty layer in the TUBE and CLEVIS projects). The
floor never sees the part drawings up front, though - they see the work packet.

This app closes that gap: it reads every part drawing under an order's
CAD-AND-SHOP-PRINTS folder, and if any of them carry the label it stamps
DIFFICULT on the first page of that order's work packet, the same way the
Pallet Stamper stamps the batch and pallet.

Once the packet is stamped, the (blue) label has done its job on the drawing,
so it is redacted OFF the part drawing. A metadata marker is left behind in
the drawing so a re-run still knows the order is difficult - without it, the
stripped drawing would read as clean and the packet stamp would be wrongly
removed. DriveWorks regenerating the drawing writes a fresh file (no marker),
so a re-modeled part always speaks for itself.
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

# After the packet is stamped, the label is stripped off the part drawing and
# this marker is written into the drawing's PDF metadata Keywords. It is the
# ONLY record that the drawing was difficult, so a re-run keeps the packet
# stamped instead of reading the stripped drawing as clean.
_STRIP_MARKER = "TechDeck-DIFFICULT-stripped"

# Where the modeled parts live inside an order folder.
_CAD_FOLDER = "CAD-AND-SHOP-PRINTS"

# Batch folders that aren't orders.
_NON_ORDER_SUFFIX = "- Documentation"
_NON_ORDER_NAMES = {"repeat batches"}

# Office lock files (~$…) and stray Python temp files (tmpab12cd34.pdf) are not
# real PDFs of ours. Single home is the SDK, which the work-packet finder uses
# too - this used to be a second copy of the same regex.
_is_real_pdf = sdk.is_real_pdf


def _is_label_span(text: str) -> bool:
    """True when a span IS the DIFFICULT label (not merely contains it)."""
    return (text or "").strip().upper() == DIFFICULT_LABEL


def _label_rects(page, color: Optional[int] = None) -> List[fitz.Rect]:
    """Rects of whole-span DIFFICULT labels on a page (padded 2pt for a clean
    redaction). Pass a colour int to match only that colour's spans."""
    rects = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if color is not None and span.get("color", 0) != color:
                    continue
                if _is_label_span(span.get("text", "")):
                    b = span["bbox"]
                    rects.append(fitz.Rect(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2))
    return rects


def _has_strip_marker(doc) -> bool:
    return _STRIP_MARKER in ((doc.metadata or {}).get("keywords") or "")


def inspect_drawing(pdf_path: Path, log) -> Optional[Tuple[bool, bool]]:
    """(has_visible_label, was_stripped_before) for a part drawing.

    has_visible_label: the drawing still carries DriveWorks' DIFFICULT label.
    was_stripped_before: this app already moved the label to the packet and
    redacted it off (metadata marker). Returns None if the PDF could not be
    read - the caller reports unreadable drawings rather than silently
    treating them as clean; a drawing we couldn't open might well be a
    difficult one.
    """
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download (Hard Rule 13)
        doc = fitz.open(sdk.long_path(pdf_path))
    except Exception as e:
        log(f"WARNING: Could not read {pdf_path.name}: {e}")
        return None

    try:
        marker = _has_strip_marker(doc)
        visible = any(_label_rects(page) for page in doc)
        return visible, marker
    except Exception as e:
        log(f"WARNING: Could not read {pdf_path.name}: {e}")
        return None
    finally:
        doc.close()


def strip_label(pdf_path: Path, log) -> Optional[int]:
    """Redact every DIFFICULT label off a part drawing, once the packet holds
    the stamp, and leave the strip marker in the PDF metadata.

    Returns the number of labels removed (0 = nothing visible, file left
    untouched), or None if the PDF errored - the caller reports those; the
    drawing keeps its label and the next run simply tries again.
    """
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download (Hard Rule 13)
        doc = fitz.open(sdk.long_path(pdf_path))
        saved = False
        try:
            count = 0
            for page in doc:
                rects = _label_rects(page)
                if not rects:
                    continue
                for r in rects:
                    page.add_redact_annot(r, fill=(1, 1, 1))
                page.apply_redactions()
                count += len(rects)

            if not count:
                return 0  # already stripped - never rewrite the file

            md = doc.metadata or {}
            keywords = (md.get("keywords") or "").strip()
            if _STRIP_MARKER not in keywords:
                md["keywords"] = f"{keywords} {_STRIP_MARKER}".strip()
                doc.set_metadata(md)

            sdk.save_pdf_atomic(doc, pdf_path)  # closes doc - don't close again
            saved = True
            return count
        finally:
            if not saved:
                try:
                    doc.close()
                except Exception:
                    pass

    except Exception as e:
        log(f"WARNING: could not remove the label from {pdf_path.name}: {e}")
        return None


def find_part_drawings(order_dir: Path) -> List[Path]:
    """Every part-drawing PDF under an order's CAD-AND-SHOP-PRINTS folder.

    Resolved case-insensitively by scan rather than by a hardcoded join, since
    real folders vary (Hard Rule / defensive folder resolution).
    """
    cad = None
    for child in order_dir.iterdir():
        if sdk.is_dir(child) and child.name.strip().casefold() == _CAD_FOLDER.casefold():
            cad = child
            break
    if cad is None:
        return []
    return sorted(p for p in cad.rglob("*.pdf") if sdk.is_file(p) and _is_real_pdf(p))


def find_work_packet(order_dir: Path, log=None) -> Optional[Path]:
    """The order's work-packet PDF - the same file the Pallet Stamper picks.

    Single home is `sdk.find_work_packet`: it ranks by name and then CONFIRMS
    by reading the page-1 title block, so a drawing binder sitting in the order
    folder is never mistaken for the packet. The name-only version this used to
    be still fell through to "the first PDF in the folder" when nothing was
    named for the order, which is exactly how the Pallet Stamper stamped
    binders (reported 2026-08-20).
    """
    return sdk.find_work_packet(order_dir, log=log)


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
    """Rects of any DIFFICULT stamp this app previously put on the page.
    Red-only: a packet stamp is always ours; a drawing's label never is."""
    return _label_rects(page, color=_RED_COLOR_INT)


def apply_stamp(pdf_path: Path, want_stamp: bool, font_size: int,
                h_offset_in: float, v_offset_in: float, log) -> Optional[str]:
    """Put the stamp on the work packet, or take it off.

    Returns "stamped", "removed", or "unchanged"; None if the PDF errored.
    A packet that needs no change is never rewritten.
    """
    try:
        sdk.ensure_local(pdf_path)  # OneDrive placeholder -> download (Hard Rule 13)
        doc = fitz.open(sdk.long_path(pdf_path))
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


def _strip_order_drawings(order_no: str, labeled: List[Path],
                          strip_failed: List[str], log) -> int:
    """Strip the label off an order's drawings AFTER its packet is stamped.
    Returns how many labels came off; failures are collected for the report
    (the drawing keeps its label, so the next run just tries again)."""
    count = 0
    for pdf in labeled:
        result = strip_label(pdf, log)
        if result is None:
            strip_failed.append(f"{order_no}: {pdf.name}")
        elif result:
            count += result
            log(f"  Removed the label from {pdf.name}")
    return count


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    settings = params.get('settings', {})
    log = params.get('log', print)

    log("Starting 922 Difficulty Stamper...")
    progress_callback(0)

    base_path = settings.get('base_path', '')
    font_size = int(settings.get('font_size', 18) or 18)
    h_offset = float(settings.get('h_offset_inches', 4.0) or 4.0)
    v_offset = float(settings.get('v_offset_inches', 6.5) or 6.5)

    # Batch input = pick the 'Batch NNN' folder (Sentry Drone capable,
    # family-cache aware — inside 922 Setup this never prompts; a queued 922
    # run prompts at most once).
    picked = sdk.request_922_batch_folder(params, base_path)
    if picked is None or cancel_event.is_set():
        return  # user cancelled — the helper already flagged the run
    batch_no, batch_path = picked

    order_dirs = [
        d for d in sorted(batch_path.iterdir())
        if sdk.is_dir(d)
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
    to_strip: Dict[str, List[Path]] = {}          # stamp failed; strip after retry
    strip_failed: List[str] = []
    labels_stripped = 0

    for idx, order_dir in enumerate(order_dirs):
        sdk.raise_if_cancelled(cancel_event)
        progress_callback(5 + int((idx / max(total, 1)) * 85))

        order_no = order_dir.name.split('-', 1)[0].strip().upper()

        drawings = find_part_drawings(order_dir)
        if not drawings:
            not_modeled.append(order_dir.name)
            continue

        labeled: List[Path] = []          # still carrying the blue label
        stripped_before: List[str] = []   # label already moved to the packet
        for i, pdf in enumerate(drawings):
            if i % 16 == 0:
                sdk.raise_if_cancelled(cancel_event)
            res = inspect_drawing(pdf, log)
            if res is None:
                unreadable.append(f"{order_no}: {pdf.name}")
                continue
            visible, was_stripped = res
            if visible:
                labeled.append(pdf)
            elif was_stripped:
                stripped_before.append(pdf.name)

        hits = ([p.name for p in labeled] +
                [f"{n} (label already on the packet)" for n in stripped_before])

        packet = find_work_packet(order_dir, log=log)
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
            if labeled:
                # Packet first, drawings second: the label stays on the
                # drawing until the packet actually carries the stamp.
                to_strip[order_no] = labeled
        elif result == "stamped":
            stamped.append(order_no)
            log(f"Stamped {order_no} - {len(hits)} difficult part(s)")
            labels_stripped += _strip_order_drawings(
                order_no, labeled, strip_failed, log)
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
                if want and order_no in to_strip:
                    labels_stripped += _strip_order_drawings(
                        order_no, to_strip.pop(order_no), strip_failed, log)
        failures = still_failed

    progress_callback(95)

    log("")
    log("=" * 50)
    log(f"DIFFICULTY SUMMARY - BATCH {batch_no}")
    log("=" * 50)
    log(f"Orders scanned:        {total}")
    log(f"Difficult orders:      {len(difficult)}")
    log(f"Packets stamped:       {len(stamped)}")
    if labels_stripped:
        log(f"Drawing labels removed:{labels_stripped:>4}")
    if strip_failed:
        log(f"Labels NOT removed:    {len(strip_failed)}")
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
    if strip_failed:
        problems.append(
            "The DIFFICULT label could not be removed from these drawings "
            "(their packet IS stamped; the drawing just still shows the "
            "label - the next run will try again):\n" +
            "\n".join(f"  {n}" for n in strip_failed))
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
                f"{len(failures)} unstamped, {len(strip_failed)} label(s) not "
                f"removed, {len(unreadable)} unreadable drawing(s), "
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
