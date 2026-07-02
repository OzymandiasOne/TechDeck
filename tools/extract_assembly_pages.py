"""
extract_assembly_pages.py -- Isolate the ASSEMBLY drawing page(s) from each EB
Desktop Work Package, the real ML-corpus target.

Document structure (user-confirmed, always in this order):
    [front matter] -> [Engineering Parts List, 1+ pp] -> [ASSEMBLY, 1+ pp]
                   -> [Move Ticket(s), barcodes] -> end
The assembly is ALWAYS the block between the EPL and the Move Ticket.

Detection uses only pixels + image metadata (no OCR/Tesseract -- not available in
the locked-down env; deps are fitz + numpy, both present):
  * big sheet page   : has one large embedded image (>800px on a side)
  * EPL page         : a big sheet whose render has many full-width horizontal
                       rules (dense ruled table). Calibrated: EPL ~14 rules,
                       every other sheet 0-2 -> threshold 8 is safe.
  * Move Ticket page : no big image + >=3 small images (barcodes/label strips)
  assembly = big-sheet pages after the LAST EPL page and before the Move Ticket.

Reuses the order-folder model from drawing_corpus_scan.py: dedup by the folder
name after the first '-'; one representative <ORDER>.pdf per distinct drawing.

Usage:
  python tools/extract_assembly_pages.py --root "<...\\1 - Completed>" [--local-only]
         [--limit N] [--export <dir>] [--dpi 200] [--out manifest.csv]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import fitz
import numpy as np

ORDER_NUM_RE = re.compile(r"^[A-Za-z]{1,3}\d{4,}")
BIG_IMG_PX = 800        # an image this big on a side => a full sheet
OCR_DPI = 130           # render DPI for the title-strip OCR
TITLE_TOP = 0.0         # OCR the top band (banner + section title); a tighter crop
TITLE_BOT = 0.30        # clips the title and the detector misses it
MAX_BACK_OCR = 10       # cap big-sheet OCR walking back from the Move Ticket

FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
_CLOUD_ONLY_MASK = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS


def is_cloud_only(path: Path) -> bool:
    try:
        return bool(getattr(os.stat(path), "st_file_attributes", 0) & _CLOUD_ONLY_MASK)
    except OSError:
        return False


def page_image_counts(pg) -> tuple[int, int]:
    """(#big images, #small images) on the page."""
    big = small = 0
    for i in pg.get_image_info():
        if max(i.get("width", 0), i.get("height", 0)) > BIG_IMG_PX:
            big += 1
        else:
            small += 1
    return big, small


_OCR_ENGINE = None


def _match_title(nows: str) -> str | None:
    """Whitespace-stripped, upper-cased title -> EPL / MT / None."""
    if "ENGINEERINGPARTSLIST" in nows:
        return "EPL"
    if "MOVETICKET" in nows:
        return "MT"
    return None


# Sheet titles that are never a drawing. A keyword inside an "APPLICABLE ... ON
# SHEET N" callout is a cross-reference printed ON a real drawing, not a title --
# so it must NOT trigger a drop (that bug dropped real drawings, e.g. X4495101).
NON_DRAWING_TITLES = ["ENGINEERINGPARTSLIST", "GENERALNOTES", "WELDNOTES",
                      "INSTALLATIONNOTES", "REFERENCES", "COVERSHEET",
                      "WORKINSTRUCTION", "MOVETICKET", "FABRICATIONNOTES",
                      "PAINTNOTES", "MATERIALNOTES"]


def _is_notes_sheet(nows: str) -> str:
    """Return the matched non-drawing keyword, or '' if the page is a drawing."""
    for kw in NON_DRAWING_TITLES:
        if kw in nows and not ((kw + "ONSHEET") in nows or ("APPLICABLE" + kw) in nows):
            return kw
    return ""


def _ocr_title(pg) -> str:
    """OCR the section-title band of a page; return whitespace-stripped upper text."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    pix = pg.get_pixmap(dpi=OCR_DPI)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    y0, y1 = int(pix.height * TITLE_TOP), int(pix.height * TITLE_BOT)
    res, _ = _OCR_ENGINE(a[y0:y1, :, :3])
    return "".join(re.sub(r"\s+", "", t).upper() for _b, t, _s in (res or []))


def _digital_title(pg) -> str | None:
    """EPL/MT from the digital text layer; None if no usable text (raster page)."""
    u = (pg.get_text("text") or "").upper()
    if len(u.strip()) <= 30:
        return None
    return _match_title(re.sub(r"\s+", "", u))


def _trailing_barcode_start(big_small) -> int | None:
    """Start index of the TRAILING run of barcode-style pages (the Move Tickets)."""
    bc = [i for i, (b, s) in enumerate(big_small) if b == 0 and s >= 3]
    if not bc:
        return None
    run, seen = bc[-1], set(bc)
    while run - 1 in seen:
        run -= 1
    return run


def segment(doc, use_ocr: bool = True) -> dict:
    """Locate EPL, Move Ticket, and the assembly block. OCR is used sparingly:
    Move Ticket needs none (digital title or trailing barcode run); EPL is OCR'd
    only when there's no digital EPL title, walking big sheets BACKWARD from the
    Move Ticket so OCR touches only the assembly pages + one EPL page."""
    n = doc.page_count
    big_small = [page_image_counts(pg) for pg in doc]
    dig = [_digital_title(pg) for pg in doc]

    # --- Move Ticket: digital title, else trailing barcode run, else OCR last pages.
    mt_digital = [i for i, d in enumerate(dig) if d == "MT"]
    mt_start = min(mt_digital) if mt_digital else _trailing_barcode_start(big_small)
    if mt_start is None and use_ocr:
        for i in range(n - 1, max(n - 4, -1), -1):
            if _match_title(_ocr_title(doc[i])) == "MT":
                mt_start = i
                break
    end = mt_start if mt_start is not None else n

    # --- EPL end: digital EPL if present, else OCR big sheets backward from the MT.
    dig_epl = [i for i in range(end) if dig[i] == "EPL"]
    big_sheets = [i for i in range(end) if big_small[i][0] >= 1]
    if dig_epl:
        epl_end, mode = max(dig_epl), "text"
    else:
        epl_end, mode = None, "ocr"
        searched = 0
        for i in reversed(big_sheets):
            if not use_ocr or searched >= MAX_BACK_OCR:
                break
            searched += 1
            if _match_title(_ocr_title(doc[i])) == "EPL":
                epl_end = i
                break

    if epl_end is None:
        return {"status": "no_epl", "mode": mode, "epl": [], "assembly": [],
                "mt_start": (mt_start + 1) if mt_start is not None else None, "pages": n}

    assembly = [i for i in range(epl_end + 1, end) if big_small[i][0] >= 1]
    if use_ocr:                        # drop notes/reference/EPL sheets left in the bracket
        assembly = [i for i in assembly if not _is_notes_sheet(_ocr_title(doc[i]))]
    status = "ok" if assembly else "no_assembly"
    if status == "ok" and mt_start is None:
        status = "needs_review"            # found EPL but no end bound -> verify
    return {
        "status": status,
        "mode": mode,
        "epl": [epl_end + 1],
        "assembly": [i + 1 for i in assembly],
        "mt_start": (mt_start + 1) if mt_start is not None else None,
        "pages": n,
    }


def walk_representatives(roots, local_only):
    """Yield (dedup_key, order, pdf_path) -- one representative per distinct drawing."""
    groups: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            name = os.path.basename(dirpath)
            if "-" not in name:
                continue
            order, key = (s.strip() for s in name.split("-", 1))
            want = f"{order}.pdf".casefold()
            pdf = next((Path(dirpath) / f for f in files if f.casefold() == want), None)
            if pdf is None and not ORDER_NUM_RE.match(order):
                continue
            dirs[:] = []
            if pdf is not None:
                groups[key.casefold()].append((order, pdf))
    for key, members in groups.items():
        rep = next((m for m in members if not is_cloud_only(m[1])), members[0])
        if local_only and is_cloud_only(rep[1]):
            continue
        yield key, rep[0], rep[1]


class ReviewPdf:
    """Bind candidate drawing pages into PDF(s) for human pruning. Each page is a
    compressed JPEG render of the source page plus a small machine-readable label,
    so survivors can be mapped back after the user deletes the non-drawings."""

    def __init__(self, base_path: str, dpi: int, split: int):
        self.base = Path(base_path)
        self.dpi = dpi
        self.split = split
        self.doc = fitz.open()
        self.part = 0
        self.total = 0
        self.in_part = 0

    def add(self, src_page, label: str) -> None:
        pix = src_page.get_pixmap(dpi=self.dpi)
        jpg = pix.tobytes("jpg", jpg_quality=70)
        w_pt, h_pt = pix.width * 72.0 / self.dpi, pix.height * 72.0 / self.dpi
        page = self.doc.new_page(width=w_pt, height=h_pt)
        page.insert_image(page.rect, stream=jpg)
        page.draw_rect(fitz.Rect(0, 0, 230, 13), color=(1, 1, 1), fill=(1, 1, 1))
        page.insert_text((3, 10), label, fontsize=7, color=(0.85, 0, 0))  # readable back via get_text
        self.total += 1
        self.in_part += 1
        if self.split and self.in_part >= self.split:
            self._flush()

    def _flush(self) -> None:
        if self.doc.page_count == 0:
            return
        path = self.base if not self.split else self.base.with_name(
            f"{self.base.stem}_{self.part:03d}{self.base.suffix}")
        self.doc.save(path, deflate=True)
        self.doc.close()
        self.doc = fitz.open()
        self.part += 1
        self.in_part = 0

    def close(self) -> None:
        self._flush()


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract the assembly drawing page(s) from each work package.")
    ap.add_argument("--root", action="append", required=True)
    ap.add_argument("--local-only", action="store_true", help="Skip cloud-only reps (no downloads).")
    ap.add_argument("--limit", type=int, default=0, help="Cap packages processed (sample); 0 = all.")
    ap.add_argument("--export", default="", help="Dir to write assembly-page PNGs into.")
    ap.add_argument("--review-pdf", default="", help="Bind candidate assembly pages into one PDF for human pruning.")
    ap.add_argument("--review-dpi", type=int, default=110, help="Render DPI for the review PDF.")
    ap.add_argument("--split", type=int, default=0, help="Pages per review-PDF file (0 = single file).")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-ocr", action="store_true", help="Disable title-strip OCR (digital-text titles only).")
    ap.add_argument("--resume", action="store_true", help="Append to --out, skipping orders already in it (survives kills).")
    ap.add_argument("--out", default="assembly_manifest.csv")
    args = ap.parse_args()

    roots = [Path(r) for r in args.root]
    for r in roots:
        if not r.exists():
            print(f"ERROR: root does not exist: {r}", file=sys.stderr)
            return 2
    export_dir = Path(args.export) if args.export else None
    if export_dir:
        export_dir.mkdir(parents=True, exist_ok=True)
    review = ReviewPdf(args.review_pdf, args.review_dpi, args.split) if args.review_pdf else None

    fields = ["dedup_key", "order", "status", "mode", "pages", "epl_pages",
              "assembly_pages", "mt_start", "exported"]
    out = Path(args.out)

    done_keys: set[str] = set()
    resuming = args.resume and out.exists()
    if resuming:
        with out.open(encoding="utf-8") as fh:
            done_keys = {r["dedup_key"] for r in csv.DictReader(fh)}
        print(f"Resuming: {len(done_keys)} orders already done, skipping them.")

    tally: dict[str, int] = defaultdict(int)
    done = 0
    with out.open("a" if resuming else "w", newline="", encoding="utf-8") as fh:  # incremental
        w = csv.DictWriter(fh, fieldnames=fields)
        if not resuming:
            w.writeheader()
        for key, order, pdf in walk_representatives(roots, args.local_only):
            if key in done_keys:
                continue
            row = {k: "" for k in fields}
            row.update(dedup_key=key, order=order)
            try:
                doc = fitz.open(pdf)
            except Exception as exc:
                row["status"] = f"open_failed:{str(exc)[:60]}"
                tally["open_failed"] += 1
                w.writerow(row); fh.flush()
                continue
            try:
                seg = segment(doc, use_ocr=not args.no_ocr)
                exported = []
                for pno in seg["assembly"]:                      # ok + needs_review have pages
                    if export_dir and seg["status"] == "ok":
                        png = export_dir / f"{key}__{order}__p{pno}.png"
                        doc[pno - 1].get_pixmap(dpi=args.dpi).save(png)
                        exported.append(png.name)
                    if review:
                        review.add(doc[pno - 1], f"{order}|p{pno}|{key}")
                row.update(status=seg["status"], mode=seg["mode"], pages=seg["pages"],
                           epl_pages=";".join(map(str, seg["epl"])),
                           assembly_pages=";".join(map(str, seg["assembly"])),
                           mt_start=seg["mt_start"] if seg["mt_start"] else "",
                           exported=";".join(exported))
                tally[seg["status"]] += 1
            finally:
                doc.close()
            w.writerow(row); fh.flush()
            done += 1
            if done % 5 == 0:
                print(f"  ...{done} packages", flush=True)
            if args.limit and done >= args.limit:
                break

    if review:
        review.close()
        print(f"Review PDF: {review.total} candidate pages -> {Path(args.review_pdf).resolve()}"
              + (f" (split every {args.split})" if args.split else ""))

    print(f"\nProcessed {done} packages -> {out.resolve()}")
    for status, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {status:14s}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
