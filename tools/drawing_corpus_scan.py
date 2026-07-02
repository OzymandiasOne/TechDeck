"""
drawing_corpus_scan.py -- Build an ML-corpus manifest of EB assembly drawings
from the 922 QTDR order-folder library.

Unit of the corpus is the EB assembly DRAWING (one per order), not the part.
Repeat orders carry the SAME EB drawing + same parts, so they are exact
duplicates and collapse to one. Self-contained: no MPL, no plugin imports.

Folder/name model (guaranteed by the library convention):
    <root>/.../<ORDER>-<DYPNNAME>-<SUFFIX>/<ORDER>.pdf
    e.g.  FJ331595-H5222366-H19 / FJ331595.pdf

  ORDER     = folder name before the FIRST  '-'   (e.g. FJ331595)  -> names the PDF
  DEDUP KEY = folder name after  the FIRST  '-'   (e.g. H5222366-H19)
              identical across repeat orders => the EB-drawing identity

An order folder is recognised by: it contains "<ORDER>.pdf" (the convention the
library guarantees). Folders matching the dashed pattern but MISSING that PDF are
reported as anomalies rather than silently skipped.

Two-pass design so we never download the whole OneDrive archive:
  Pass 1 (inventory, DEFAULT) -- os.walk + os.stat only. ZERO file opens, ZERO
         downloads. Groups order folders by dedup key; detects cloud-only
         placeholders via the Windows offline attribute. Reports scope.
  Pass 2 (classify)           -- opens ONE representative <ORDER>.pdf per distinct
         EB drawing and labels it vector / raster / text-only / mixed. Hydrates
         only the deduped survivors, preferring an already-local copy.

Usage:
  python tools/drawing_corpus_scan.py --root "<...\\1 - Completed>"
  python tools/drawing_corpus_scan.py --root "<...>" --mode classify
  (optional)  --root again for more status folders   --out manifest.csv
              --limit N (cap classify for a dry run)
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# An order number = 1-3 leading letters then >=4 digits (FJ331595, BM309373,
# X4442763, XY391516). Used to tell a real order folder from a dashed non-order
# folder (CAD-AND-SHOP-PRINTS, SAMPLE-DRAWING) when the <ORDER>.pdf is absent.
ORDER_NUM_RE = re.compile(r"^[A-Za-z]{1,3}\d{4,}")

# OneDrive Files-On-Demand placeholder attributes (Windows). Reading these via
# os.stat does NOT trigger a download; opening the file content would.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
_CLOUD_ONLY_MASK = (
    FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_RECALL_ON_OPEN
    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)

# Vector/raster thresholds (re-tunable from the raw signals in the manifest).
PATH_THRESHOLD = 20      # >= this many vector paths => real linework => vector
LOW_PATHS = 5            # "essentially no" vector paths
BIG_IMAGE_FRAC = 0.60    # one image covering >= this fraction of a page = scan
TEXT_MIN = 50            # meaningful text-layer length


def find_order_pdf(dirpath: str, files: list[str], order: str) -> Path | None:
    want = f"{order}.pdf".casefold()
    for f in files:
        if f.casefold() == want:
            return Path(dirpath) / f
    return None


def is_cloud_only(path: Path) -> bool:
    """True if a OneDrive placeholder (no local content). Does not download."""
    try:
        attrs = getattr(os.stat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & _CLOUD_ONLY_MASK)


def pick_representative(pdfs: list[Path]) -> Path:
    """Prefer an already-local copy so classify doesn't force a download."""
    for p in pdfs:
        if not is_cloud_only(p):
            return p
    return pdfs[0]


def classify_pdf(path: Path) -> dict:
    """Open + classify a drawing PDF. Survives cloud-only read failures (Rule 13)."""
    import fitz  # PyMuPDF -- lazy import so inventory mode needs no dependency

    try:
        doc = fitz.open(path)
    except Exception as exc:  # Errno 22 = cloud-only that wouldn't hydrate
        return {"readable": False, "error": str(exc)[:120], "label": "unreadable"}

    try:
        total_paths = total_text = 0
        any_big_image = False
        page_count = doc.page_count
        for page in doc:
            total_text += len((page.get_text("text") or "").strip())
            total_paths += len(page.get_drawings())
            page_area = (page.rect.width * page.rect.height) or 1.0
            for info in page.get_image_info():
                bbox = info.get("bbox")
                if not bbox:
                    continue
                if ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / page_area >= BIG_IMAGE_FRAC:
                    any_big_image = True
                    break

        if total_paths >= PATH_THRESHOLD:
            label = "vector"                       # real linework present
        elif any_big_image and total_paths < LOW_PATHS:
            label = "raster"                       # scan, OCR text layer or not
        elif total_text > TEXT_MIN and total_paths < LOW_PATHS and not any_big_image:
            label = "text-only"                    # notes/PO-style PDF, not a drawing
        else:
            label = "mixed"

        return {
            "readable": True, "error": "", "label": label,
            "page_count": page_count, "vector_paths": total_paths,
            "text_len": total_text, "big_image": int(any_big_image),
        }
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Order-folder dedup + vector/raster scan for the EB-drawing ML corpus.")
    ap.add_argument("--root", action="append", required=True, help="Status/library root (repeatable), e.g. '...\\1 - Completed'.")
    ap.add_argument("--mode", choices=["inventory", "classify"], default="inventory")
    ap.add_argument("--out", default="drawing_corpus_manifest.csv")
    ap.add_argument("--limit", type=int, default=0, help="Cap classified drawings (dry run); 0 = all.")
    ap.add_argument("--local-only", action="store_true", help="Classify only already-local reps; skip cloud-only (no downloads).")
    args = ap.parse_args()

    roots = [Path(r) for r in args.root]
    for r in roots:
        if not r.exists():
            print(f"ERROR: root does not exist: {r}", file=sys.stderr)
            return 2

    # Pass 1 -- walk + dedup by folder name. No file opens, no downloads.
    groups: dict[str, list[dict]] = defaultdict(list)  # dedup_key -> [{order, pdf}]
    missing_pdf: list[str] = []
    order_folders = 0
    print("Walking roots (no downloads)...")
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            name = os.path.basename(dirpath)
            if "-" not in name:
                continue  # batch / status dir -- keep descending
            order, dedup_key = (s.strip() for s in name.split("-", 1))
            pdf = find_order_pdf(dirpath, files, order)
            if pdf is None and not ORDER_NUM_RE.match(order):
                continue  # dashed non-order folder (e.g. CAD-AND-SHOP-PRINTS) -- descend
            dirs[:] = []   # order folder location: never nests, don't walk prints subdirs
            if pdf is None:
                missing_pdf.append(dirpath)  # order-numbered but no <ORDER>.pdf -> real anomaly
                continue
            order_folders += 1
            groups[dedup_key.casefold()].append({"order": order, "pdf": pdf})
            if order_folders % 500 == 0:
                print(f"  ...{order_folders} order folders, {len(groups)} distinct drawings so far")

    distinct = len(groups)
    repeats = order_folders - distinct
    cloud_reps = 0

    rows: list[dict] = []
    classified = 0
    do_classify = args.mode == "classify"
    if do_classify:
        print("\nClassifying one representative per distinct drawing (this hydrates cloud-only files)...")

    for dedup_key, members in groups.items():
        pdfs = [m["pdf"] for m in members]
        rep = pick_representative(pdfs)
        rep_cloud = is_cloud_only(rep)
        cloud_reps += int(rep_cloud)
        row = {
            "dedup_key": dedup_key,
            "order_count": len(members),
            "orders": ";".join(sorted(m["order"] for m in members)),
            "representative_order": next(m["order"] for m in members if m["pdf"] == rep),
            "representative_pdf": str(rep),
            "rep_cloud_only": int(rep_cloud),
            "label": "", "page_count": "", "vector_paths": "",
            "text_len": "", "big_image": "", "readable": "", "error": "",
        }
        if do_classify and (args.limit == 0 or classified < args.limit):
            if args.local_only and rep_cloud:
                row["label"] = "skipped-cloud"
            else:
                row.update(classify_pdf(rep))
                classified += 1
                if classified % 100 == 0:
                    print(f"  ...classified {classified}")
        rows.append(row)

    print("\n=== Inventory ===")
    print(f"  Order folders found     : {order_folders}")
    print(f"  Distinct EB drawings    : {distinct}")
    print(f"  Repeats collapsed       : {repeats}")
    print(f"  Cloud-only reps         : {cloud_reps}  (would download on classify)")
    print(f"  Order-shaped, no <ORDER>.pdf : {len(missing_pdf)}  (anomalies -- review)")
    for m in missing_pdf[:10]:
        print(f"      ! {m}")

    out = Path(args.out)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nManifest written: {out.resolve()}  ({len(rows)} distinct drawings)")

    if do_classify:
        tally: dict[str, int] = defaultdict(int)
        for r in rows:
            if r["label"]:
                tally[r["label"]] += 1
        print("=== Classification (deduped survivors) ===")
        for label, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"  {label:12s}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
