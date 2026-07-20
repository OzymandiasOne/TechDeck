"""Phase-1 extraction CLI for the 922 MASTER PARTS build.

Enumerate mode: find every leaf 'Batch NNN' folder under '1 - Completed' plus
the active top-level batches, dedupe by batch number, and write a
'num<TAB>path' list.

Extract mode: for each listed batch, locate its OWN 'PO {n} QF-QU-09 REV C'
workbook (Documentation folder first, order-folder copies as fallback; never
the batch root or REPEAT BATCHES - those hold OTHER batches' POs), parse the
PO sheet, and emit one batch_{n}.json per batch. Old-rev-only batches are
recorded as skipped (user rule: pre-REV-C data is too outdated to reuse).

Usage:
  python tools/mpl_extract_batches.py --list-out <file> [--root <922 root>]
  python tools/mpl_extract_batches.py --batch-list <file> --out <dir>
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "plugins" / "922_batch_repeater"))

import master_parts as mp  # noqa: E402  (repo-path import)
from techdeck.core import plugin_sdk as sdk  # noqa: E402

COMPLETED = "1 - Completed"
ACTIVE_BATCHES = list(range(478, 485))  # 478-484; 485 in progress, 999 empty
_BATCH_DIR_RE = re.compile(r"^Batch\s+(\d+)$", re.IGNORECASE)


def resolve_root(override: str = "") -> Path:
    root = sdk.resolve_922_root(override)
    if not root:
        raise SystemExit("could not resolve the 922 QTDR Production Packages root")
    return Path(root)


def enumerate_batches(root: Path):
    """{batch_num: [candidate paths]} - leaf Batch N dirs under 1 - Completed
    (skipping anything inside REPEAT BATCHES) + the active top-level batches."""
    import os
    found = {}
    completed = root / COMPLETED
    for walk_root, dirs, _ in os.walk(completed):
        if "repeat" in Path(walk_root).name.lower():
            dirs[:] = []
            continue
        for d in list(dirs):
            m = _BATCH_DIR_RE.match(d)
            if m:
                found.setdefault(int(m.group(1)), []).append(Path(walk_root) / d)
                dirs.remove(d)  # a batch folder never nests another batch
    for n in ACTIVE_BATCHES:
        p = root / f"Batch {n}"
        if p.is_dir():
            found.setdefault(n, []).insert(0, p)
    return found


def pick_candidate(n: int, paths):
    """When a batch number appears in more than one place, prefer the path
    that actually yields a REV C PO workbook."""
    if len(paths) == 1:
        return paths[0], mp.find_batch_po_workbook(paths[0], n)
    best = None
    for p in paths:
        res = mp.find_batch_po_workbook(p, n)
        if res["status"] == "ok":
            return p, res
        if best is None or (res["status"] == "old_rev"
                            and best[1]["status"] == "no_po_workbook"):
            best = (p, res)
    return best


def cmd_list(args):
    root = resolve_root(args.root)
    found = enumerate_batches(root)
    lines = []
    for n in sorted(found):
        path, _ = pick_candidate(n, found[n])
        lines.append(f"{n}\t{path}")
    Path(args.list_out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} batch folders -> {args.list_out}")


def extract_one(n: int, batch_dir: Path, out_dir: Path):
    try:
        res = mp.extract_batch(batch_dir, n)
    except Exception as exc:  # never abort the chunk on one bad workbook
        res = {"status": "error", "path": None, "location": None, "rows": [],
               "warnings": [], "error": f"{type(exc).__name__}: {exc}"}
    payload = {"batch": n, "batch_dir": str(batch_dir), "status": res["status"],
               "workbook": str(res["path"]) if res.get("path") else None,
               "source_location": res.get("location"), "rows": res["rows"],
               "warnings": res["warnings"]}
    if "error" in res:
        payload["error"] = res["error"]
    out = out_dir / f"batch_{n}.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload["status"]


def cmd_extract(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tallies = {}
    errors = []
    for line in Path(args.batch_list).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        num_s, path_s = line.split("\t", 1)
        status = extract_one(int(num_s), Path(path_s), out_dir)
        tallies[status] = tallies.get(status, 0) + 1
        if status == "error":
            errors.append(num_s)
        print(f"batch {num_s}: {status}", flush=True)
    print("SUMMARY " + json.dumps(tallies)
          + (f" errors={','.join(errors)}" if errors else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="", help="922 root override")
    ap.add_argument("--list-out", help="enumerate mode: write num<TAB>path list")
    ap.add_argument("--batch-list", help="extract mode: list file to process")
    ap.add_argument("--out", help="extract mode: output dir for batch JSONs")
    args = ap.parse_args()
    if args.list_out:
        cmd_list(args)
    elif args.batch_list and args.out:
        cmd_extract(args)
    else:
        ap.error("use --list-out OR (--batch-list + --out)")


if __name__ == "__main__":
    main()
