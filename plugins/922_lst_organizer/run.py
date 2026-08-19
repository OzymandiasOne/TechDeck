"""
922 LST Organizer - v3.2.0
==========================
Gathers the tube-cutting `.lst` files for a 922 batch, files each one into its
source-material folder, and writes ONE color-coded Excel report that reconciles
the batch PO's tube count against what was actually pulled.

Why the rewrite (replaces the v15 lineage):
- The old join was `filename stem -> DYPN -> PO` and broke on real filename
  suffixes (mainly SigmaNest's `_P_TubeN` export tag, plus `-STEP` and the odd
  duplicated `-4A_4A`). A file that failed the join dropped to "Uncategorized"
  AND made its PO part show up as a "missing standard tube" - the exact bug of
  categorized-yet-missing files. Robust normalization + an order-folder-PO
  fallback + a conservative suffix match now resolve all but genuinely
  ambiguous files (a foreign part, or a real letter conflict), which are moved
  to a `Needs Review` folder and listed on the report.
- Output is now a single color-coded `.pdf` (reconciliation + attention + pull
  list), not the old `LST_Overview.txt` + `Tube_Parts_Batch.txt` + `.jsonl`.

v3.1.0 - a trailing REVISION LETTER is the same piece in either direction. The
PO can read `R6455461-H51-4` while the file on disk reads `R6455461-H51-4A-STEP`
(Batch 485), or the reverse; v3.0 only forgave the second case, so the first
reported one physical tube twice - "needs review" AND "missing". The match now
runs through `sdk.match_dypn_variant`, still single-candidate-only, with the
order number breaking a tie when the PO has more than one open variant.

v3.2.0 - batch input is now a FOLDER PICK (`sdk.request_directory` -> the
'Batch NNN' folder, Sentry Drone capable), not a typed batch number; a cache
hit from an earlier 922 plugin in a multi-run skips the pick, and a fresh pick
seeds that same family cache (Hard Rule 10). The report's missing-tubes table
shows each tube's SOURCE MATERIAL description instead of the where-to-look
path hint (the material is what you take to the floor).

Oversized tubes (>0.375" NOM) never have `.lst` files - they're only counted on
the report so the target (standard tubes) reconciles cleanly.
"""
from __future__ import annotations

import re
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

import fitz  # PyMuPDF - the report is drawn as a color-coded PDF

VERSION = "3.3.0"

NEEDS_REVIEW_FOLDER = "Needs Review"

# Filename/DYPN normalization and the revision-letter variant match live in the
# SDK (sdk.normalize_dypn / split_dypn / match_dypn_variant) so every plugin
# that joins a part number to a file inherits the same rules.
_normalize_part = sdk.normalize_dypn
_split_dypn = sdk.split_dypn


# ── LST discovery ───────────────────────────────────────────────────────────

def _order_dirs(batch_path: Path, batch_no: str) -> List[Path]:
    """Top-level order folders, excluding the batch's own system dirs."""
    doc = f"batch {batch_no} - documentation"
    out = []
    for d in sorted(p for p in batch_path.iterdir() if p.is_dir()):
        low = d.name.strip().lower()
        if low == doc or low == "repeat batches":
            continue
        out.append(d)
    return out


def _find_lsts_for_order(order_dir: Path, cancel_event=None) -> List[Path]:
    """`.lst` files under any `CAD-AND-SHOP-PRINTS/*/7000/` subtree. Non-repeat
    paths win; repeat paths are a fallback. The walk (and its Hard Rule 11
    cancel polling) lives in `sdk.scan_shop_print_lsts`, shared with the 922
    Batch Repeater's repeat audit."""
    return sdk.scan_shop_print_lsts(order_dir, cancel_event).lsts


# ── PO reading ──────────────────────────────────────────────────────────────

def _cell(row: tuple, idx: Optional[int]) -> Optional[str]:
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    if v in (None, ""):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _scan_headers(ws, required: List[str], max_rows: int = 25) -> Tuple[int, Dict[str, int]]:
    """Find the row (1-based) holding all `required` header names and return
    {UPPER HEADER: 0-based col}. Streaming, so it works on read-only sheets.
    Looks up by NAME, never a fixed index (Hard Rules 1-2)."""
    want = {h.strip().upper() for h in required}
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_rows, values_only=True), 1):
        found: Dict[str, int] = {}
        for c, val in enumerate(row):
            if val not in (None, ""):
                found[str(val).strip().upper()] = c
        if want.issubset(found):
            return r, found
    raise ValueError(f"headers {sorted(want)} not found in first {max_rows} rows")


def _read_po(xlsx: Path, log=None) -> Tuple[Dict[str, Tuple[Optional[str], Optional[str]]],
                                            Dict[str, str]]:
    """(dypn_map, serial_desc) from a QF-QU-09 workbook.
       dypn_map:   normalized DYPN -> (order, source-material serial)
       serial_desc: serial -> material description."""
    wb = sdk.load_workbook_resilient(xlsx, read_only=True, data_only=True)
    try:
        smap = {s.strip().casefold(): s for s in wb.sheetnames}
        if "po" not in smap:
            raise ValueError("workbook has no 'PO' sheet")
        po_ws = wb[smap["po"]]
        hdr, cols = _scan_headers(po_ws, ["ORDER", "DYPN", "SOURCE MATERIAL"])
        dypn_map: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for row in po_ws.iter_rows(min_row=hdr + 1, values_only=True):
            dypn = _cell(row, cols["DYPN"])
            if not dypn:
                continue
            dypn_map[_normalize_part(dypn)] = (
                _cell(row, cols["ORDER"]), _cell(row, cols["SOURCE MATERIAL"]))

        serial_desc: Dict[str, str] = {}
        if "source material" in smap:
            src = wb[smap["source material"]]
            try:
                shr, scols = _scan_headers(src, ["SOURCE MATERIAL", "PART DESCRIPTION"])
                desc_col = scols["PART DESCRIPTION"]
            except ValueError:
                shr, scols = _scan_headers(src, ["SOURCE MATERIAL", "SCRIBE DESCRIPTION"])
                desc_col = scols["SCRIBE DESCRIPTION"]
            ser_col = scols["SOURCE MATERIAL"]
            for row in src.iter_rows(min_row=shr + 1, values_only=True):
                s, d = _cell(row, ser_col), _cell(row, desc_col)
                if s and d:
                    serial_desc.setdefault(s, d)
        return dypn_map, serial_desc
    finally:
        wb.close()


def _has_po_sheet(p: Path) -> bool:
    try:
        wb = sdk.load_workbook_resilient(p, read_only=True)
        ok = "po" in {s.strip().casefold() for s in wb.sheetnames}
        wb.close()
        return ok
    except Exception:
        return False


def _find_master_po(batch_path: Path, batch_no: str) -> Optional[Path]:
    """The batch's QF-QU-09 PO workbook in the Documentation folder. Prefers the
    QF-QU file (the pallet/organizer workbook shares the `PO H{batch}` prefix but
    has no PO sheet), and validates the PO sheet before returning."""
    doc = batch_path / f"Batch {batch_no} - Documentation"
    searches = []
    if doc.exists():
        searches += [doc.glob(f"*H{batch_no}*QF*QU*.xlsx"), doc.glob("*QF*QU*.xlsx"),
                     doc.glob(f"PO H{batch_no}*.xlsx"), doc.glob("*.xlsx")]
    searches.append(batch_path.rglob("*QF*QU*.xlsx"))
    seen: set = set()
    for it in searches:
        for p in sorted(it):
            low = p.name.lower()
            if p in seen or low.startswith("~$") or "pallet" in low or "organizer" in low:
                continue
            seen.add(p)
            if _has_po_sheet(p):
                return p
    return None


def _find_order_po(order_dir: Path) -> Optional[Path]:
    """An order folder's own QF-QU workbook (e.g. `R6513463-H9DR.xlsx`)."""
    hits = sorted(p for p in order_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    return hits[0] if hits else None


# ── resolution ──────────────────────────────────────────────────────────────

class Pulled:
    """One gathered .lst file resolved to a material (or flagged for review)."""
    __slots__ = ("src", "order", "part", "serial", "desc", "tube", "how", "reason")

    def __init__(self, src, order, part, serial=None, desc=None, tube=None,
                 how=None, reason=None):
        self.src = src            # source Path
        self.order = order        # order folder name
        self.part = part          # normalized DYPN
        self.serial = serial      # source-material serial
        self.desc = desc          # material description
        self.tube = tube          # 'standard' | 'oversized' | None
        self.how = how            # 'exact' | 'order-po' | 'suffix' | None(review)
        self.reason = reason      # why it needs review, when how is None

    @property
    def resolved(self) -> bool:
        return self.how is not None

    @property
    def folder(self) -> str:
        if not self.resolved:
            return NEEDS_REVIEW_FOLDER
        return _sanitize(f"{self.desc} ({self.serial})") if (self.desc and self.serial) \
            else NEEDS_REVIEW_FOLDER


def _sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()


def _order_num(name: str) -> str:
    """Order number = the folder name before the first dash
    ('FK357980-H5222070-H3' -> 'FK357980'). Bare PO order values pass through."""
    return (name or "").split("-", 1)[0]


def _material_label(serial: Optional[str], serial_desc: Dict[str, str]) -> str:
    """'{description} ({serial})' when the SOURCE MATERIAL sheet knows the
    serial, else the bare serial - what a missing tube reads as on the floor."""
    if not serial:
        return ""
    desc = serial_desc.get(serial)
    return f"{desc} ({serial})" if desc else serial


def _resolve(files: List[Tuple[str, Path]], master_map, serial_desc,
             batch_path: Path, log) -> Tuple[List[Pulled], Dict[str, Tuple], Dict[str, str]]:
    """Resolve every gathered file to a material. Returns (pulled, expected_tubes,
    serial_desc) where expected_tubes maps PO DYPN -> (order, serial, class) for
    every tube in the master PO (the target list)."""
    order_cache: Dict[str, Dict] = {}

    def _lookup(part, mapping):
        hit = mapping.get(part)
        if not hit:
            return None
        order, serial = hit
        serial = str(serial).strip() if serial else None
        return order, serial

    results: List[Pulled] = []
    deferred: List[Pulled] = []
    for order_name, src in files:
        part = _normalize_part(src.stem)
        hit = _lookup(part, master_map)
        how = "exact"
        if not hit:
            # order-folder PO fallback (the master PO can be an incomplete snapshot)
            if order_name not in order_cache:
                po = _find_order_po(batch_path / order_name)
                omap, odesc = ({}, {})
                if po:
                    try:
                        omap, odesc = _read_po(po, log)
                    except Exception as e:
                        log(f"  WARNING: could not read order PO {po.name}: {e}")
                order_cache[order_name] = omap
                for k, v in odesc.items():
                    serial_desc.setdefault(k, v)
            hit = _lookup(part, order_cache[order_name])
            how = "order-po"
        if hit:
            order, serial = hit
            serial = serial or None
            desc = serial_desc.get(serial) if serial else None
            results.append(Pulled(src, order_name, part, serial, desc,
                                  sdk.tube_class(serial), how))
        else:
            deferred.append(Pulled(src, order_name, part))

    # Expected tubes = every tube DYPN in the master PO (the target).
    expected: Dict[str, Tuple] = {}
    for dypn, (order, serial) in master_map.items():
        serial = str(serial).strip() if serial else None
        cls = sdk.tube_class(serial)
        if cls:
            expected[dypn] = (order, serial, cls)

    covered = {p.part for p in results}
    missing = {d: v for d, v in expected.items()
               if v[2] == "standard" and d not in covered}

    # Conservative revision-letter match: a still-unresolved file maps to a
    # MISSING standard tube when the PPN + piece number agree and the trailing
    # letter is the only difference, IN EITHER DIRECTION (PO '-4' vs file '-4A'
    # and the reverse - EB renames the piece between the PO and the SigmaNest
    # export). Still single-candidate-only; the order number breaks a tie when
    # the PO left more than one variant of that piece open.
    for pf in deferred:
        onum = _order_num(pf.order)
        d = sdk.match_dypn_variant(
            pf.part, list(missing),
            prefer=lambda cand: _order_num(missing[cand][0] or "") == onum)
        if d:
            order, serial, _cls = missing.pop(d)
            pf.part, pf.order = d, order or pf.order
            pf.serial, pf.desc = serial, serial_desc.get(serial)
            pf.tube, pf.how = sdk.tube_class(serial), "suffix"
            pf.reason = None
        else:
            ppn, num, _letter = _split_dypn(pf.part)
            variants = sorted(d for d in missing
                              if _split_dypn(d)[:2] == (ppn, num))
            same_ppn = sorted(d for d in expected if _split_dypn(d)[0] == ppn)
            if len(variants) > 1:
                pf.reason = ("ambiguous - could be any of "
                             f"{', '.join(variants)}")
            elif not same_ppn:
                pf.reason = "part not found in this batch's PO (foreign / repeat?)"
            else:
                pf.reason = ("no matching tube for this piece number (PO has "
                             f"{', '.join(same_ppn)})")
        results.append(pf)   # keep review items in the result set

    return results, expected, serial_desc


# ── report ──────────────────────────────────────────────────────────────────

# colors (RGB 0-1)
_C_BAND = (0.12, 0.31, 0.37)     # dark teal header band
_C_WHITE = (1, 1, 1)
_C_GREY = (0.46, 0.46, 0.46)
_C_INK = (0.10, 0.10, 0.12)
_C_MISS_BG, _C_MISS_TX = (0.97, 0.85, 0.85), (0.60, 0.00, 0.00)
_C_REV_BG, _C_REV_TX = (0.99, 0.91, 0.82), (0.70, 0.37, 0.02)
_C_OK_BG, _C_OK_TX = (0.85, 0.93, 0.82), (0.15, 0.31, 0.07)
_C_EXTRA_BG, _C_EXTRA_TX = (0.82, 0.90, 0.96), (0.10, 0.32, 0.55)
_C_TGT_BG = (1.0, 0.95, 0.74)
_C_GRP_BG = (0.86, 0.89, 0.96)
_C_ZEBRA = (0.96, 0.96, 0.97)

_PW, _PH, _M = 612, 792, 42


class _Pdf:
    """Tiny top-down PDF layout helper over PyMuPDF with auto page breaks."""

    def __init__(self):
        self.doc = fitz.open()
        self._page()

    def _page(self):
        self.p = self.doc.new_page(width=_PW, height=_PH)
        self.y = _M

    def _fits(self, h):
        if self.y + h > _PH - _M:
            self._page()

    @staticmethod
    def _font(bold):
        return "hebo" if bold else "helv"

    def _clip(self, s, w, size, bold=False):
        s = "" if s is None else str(s)
        fn = self._font(bold)
        if fitz.get_text_length(s, fontname=fn, fontsize=size) <= w - 6:
            return s
        while s and fitz.get_text_length(s + "..", fontname=fn, fontsize=size) > w - 6:
            s = s[:-1]
        return s + ".."

    def gap(self, h):
        self.y += h

    def text(self, s, size: float = 9, bold=False, color=_C_INK, dx=0):
        self._fits(size + 4)
        self.y += size
        self.p.insert_text((_M + dx, self.y), s, fontsize=size,
                           fontname=self._font(bold), color=color)
        self.y += 4

    def row(self, cells, widths, size=8.5, h=15, bold=False,
            fill=None, tcolor=_C_INK):
        self._fits(h)
        x0 = _M
        if fill is not None:
            self.p.draw_rect(fitz.Rect(x0, self.y, x0 + sum(widths), self.y + h),
                             fill=fill, width=0)
        x, base = x0, self.y + h - 4.5
        for c, w in zip(cells, widths):
            self.p.insert_text((x + 3, base), self._clip(c, w, size, bold),
                               fontsize=size, fontname=self._font(bold), color=tcolor)
            x += w
        self.y += h

    def save(self, path):
        self.doc.save(str(path), garbage=3, deflate=True)
        self.doc.close()


def _write_report(path: Path, batch_no: str, master_po: Optional[Path],
                  orders: List[str], pulled: List[Pulled], expected: Dict[str, Tuple],
                  files_found: int, serial_desc: Dict[str, str]) -> None:
    std_total = sum(1 for v in expected.values() if v[2] == "standard")
    over_total = sum(1 for v in expected.values() if v[2] == "oversized")
    resolved = [p for p in pulled if p.resolved]
    review = [p for p in pulled if not p.resolved]
    std_covered = len({p.part for p in resolved
                       if p.tube == "standard" and p.part in expected})
    covered = {p.part for p in resolved}
    missing = sorted((d, v) for d, v in expected.items()
                     if v[2] == "standard" and d not in covered)
    # "Extra" = a filed tube whose DYPN is NOT in the batch master PO (found via
    # the order-folder workbook, so the batch PO is missing that line).
    extra = [p for p in resolved if p.tube and p.part not in expected]

    d = _Pdf()
    d.text(f"922 LST Organizer  -  Batch {batch_no}", size=17, bold=True, color=_C_BAND)
    d.text(f"Generated {time.strftime('%Y-%m-%d %H:%M')}   |   "
           f"PO: {master_po.name if master_po else '(not found)'}   |   "
           f"{len(orders)} order folders", size=8.5, color=_C_GREY)
    d.gap(8)

    # reconciliation
    d.text("TUBE RECONCILIATION", size=11, bold=True, color=_C_BAND)
    recon = [
        ("Total tubes in PO", std_total + over_total, None),
        ("Oversized (no .lst expected)", over_total, None),
        ("TARGET  -  standard tubes to pull", std_total, _C_TGT_BG),
        (".lst files found & filed", len(resolved), None),
        (f"Standard tubes accounted for", f"{std_covered} / {std_total}",
         _C_OK_BG if std_covered >= std_total else None),
        ("EXTRA (filed, not in batch PO)", len(extra), _C_EXTRA_BG if extra else _C_OK_BG),
        ("MISSING standard tubes", len(missing), _C_MISS_BG if missing else _C_OK_BG),
        ("Needs review", len(review), _C_REV_BG if review else _C_OK_BG),
    ]
    for i, (label, val, fill) in enumerate(recon):
        bold = label.startswith("TARGET") or label.startswith("MISSING")
        bg = fill if fill is not None else (_C_ZEBRA if i % 2 else _C_WHITE)
        d.row([label, str(val)], [300, 90], size=9.5, h=18, bold=bold, fill=bg)
    d.gap(4)
    flags = []
    if missing:
        flags.append(f"{len(missing)} missing")
    if review:
        flags.append(f"{len(review)} need review")
    if extra:
        flags.append(f"{len(extra)} extra (not in batch PO)")
    if not flags:
        d.text("All target tubes accounted for.", size=10, bold=True, color=_C_OK_TX)
    else:
        d.text("  -  ".join(flags) + ".", size=10, bold=True, color=_C_MISS_TX)
    d.gap(10)

    # missing - the SOURCE MATERIAL description is what the floor pulls
    # against, so it replaced the old where-to-look path hint (2026-08-05).
    if missing:
        d.text("MISSING STANDARD TUBES", size=11, bold=True, color=_C_MISS_TX)
        d.row(["Order", "Part", "Serial", "Source Material"],
              [90, 130, 70, 240], size=8.5, h=16, bold=True, fill=_C_BAND, tcolor=_C_WHITE)
        for dd, (order, serial, _c) in missing:
            desc = (serial_desc.get(serial) or "") if serial else ""
            d.row([_order_num(order), dd, serial, desc], [90, 130, 70, 240],
                  h=14, fill=_C_MISS_BG, tcolor=_C_MISS_TX)
        d.gap(10)

    # needs review
    if review:
        d.text("NEEDS REVIEW  (moved to 'Needs Review' folder)", size=11, bold=True, color=_C_REV_TX)
        d.row(["File", "Order", "Part", "Reason"],
              [124, 80, 96, 228], size=8.5, h=16, bold=True, fill=_C_BAND, tcolor=_C_WHITE)
        for p in review:
            d.row([p.src.name, _order_num(p.order), p.part, p.reason], [124, 80, 96, 228],
                  size=8, h=14, fill=_C_REV_BG, tcolor=_C_REV_TX)
        d.gap(10)

    # extra (filed, not in the batch PO)
    if extra:
        d.text("EXTRA - FILED BUT NOT IN THIS BATCH'S PO", size=11, bold=True, color=_C_EXTRA_TX)
        d.text("Found via the order folder's own workbook. Verify the batch PO isn't "
               "missing these lines.", size=8, color=_C_GREY)
        d.row(["File", "Order", "Part", "Material"],
              [140, 84, 110, 194], size=8.5, h=16, bold=True, fill=_C_BAND, tcolor=_C_WHITE)
        for p in extra:
            mat = f"{p.desc} ({p.serial})" if p.desc else (p.serial or "")
            d.row([p.src.name, _order_num(p.order), p.part, mat], [140, 84, 110, 194],
                  size=8, h=14, fill=_C_EXTRA_BG, tcolor=_C_EXTRA_TX)
        d.gap(10)

    # pull list by material
    d.text("PULL LIST BY MATERIAL", size=11, bold=True, color=_C_BAND)
    d.text("via:  exact = the PO DYPN matched the filename   |   order-po = matched via "
           "the order folder's own workbook   |   suffix = same piece, different "
           "revision letter", size=7.5, color=_C_GREY)
    groups: Dict[Tuple[str, str], List[Pulled]] = defaultdict(list)
    for p in resolved:
        groups[(p.desc or "(unknown)", p.serial or "")].append(p)
    if not groups:
        d.text("No files were filed.", size=9, color=_C_GREY)
    for (desc, serial) in sorted(groups, key=lambda k: str(k[0]).lower()):
        items = sorted(groups[(desc, serial)], key=lambda p: p.part)
        d.row([f"{desc}  ({serial})", f"{len(items)} pc"], [430, 90],
              size=9.5, h=17, bold=True, fill=_C_GRP_BG)
        d.row(["Order", "Part", "File", "via"], [90, 150, 230, 50],
              size=8, h=13, bold=True, tcolor=_C_GREY)
        for i, p in enumerate(items):
            d.row([_order_num(p.order), p.part, p.src.name, p.how], [90, 150, 230, 50],
                  h=13, fill=_C_ZEBRA if i % 2 else _C_WHITE)
        d.gap(6)

    d.save(path)


# ── file operations ─────────────────────────────────────────────────────────

def _retry(fn, *a, tries=5, delay=0.2, **kw):
    import errno
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM, errno.EBUSY):
                time.sleep(delay * (i + 1))
                continue
            raise


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    k = 2
    while True:
        cand = dest.with_name(f"{dest.stem}({k}){dest.suffix}")
        if not cand.exists():
            return cand
        k += 1


# ── entry point ─────────────────────────────────────────────────────────────

def run(params: dict, progress_callback, cancel_event) -> None:
    settings = params.get("settings", {})
    log = params.get("log", print)

    log(f"Starting 922 LST Organizer (v{VERSION})...")
    progress_callback(0)

    dry_run = bool(settings.get("dry_run", False))
    do_organize = bool(settings.get("organize_by_material", True))

    # Batch input = pick the 'Batch NNN' folder itself, via the shared SDK
    # helper this plugin's v3.2 flow was promoted into (Sentry Drone capable,
    # family-cache aware: a cache hit from an earlier 922 plugin skips the
    # pick; a fresh pick seeds that cache so later 922 stages never re-prompt
    # — Hard Rule 10 preserved without a typed prompt).
    picked = sdk.request_922_batch_folder(params, settings.get("base_path") or "")
    if picked is None or cancel_event.is_set():
        return  # user cancelled — the helper already flagged the run
    batch_no, batch_path = picked
    if dry_run:
        log("DRY RUN - no files will be copied or moved.")

    lst_dir = batch_path / f"Batch {batch_no} - Documentation" / "LST"
    lst_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: gather ──
    log("Scanning order folders for .lst files...")
    order_dirs = _order_dirs(batch_path, batch_no)
    gathered: List[Tuple[str, Path]] = []   # (order_name, dest_path) for the report
    seen: set = set()
    for idx, od in enumerate(order_dirs, 1):
        if cancel_event.is_set():
            log("Cancelled."); return
        log(f"  [{idx}/{len(order_dirs)}] {od.name}")
        for f in _find_lsts_for_order(od, cancel_event):
            key = f.name.lower()
            if key in seen:
                continue
            seen.add(key)
            if dry_run:
                gathered.append((od.name, f))
            else:
                sdk.ensure_local(f)
                dest = _unique(lst_dir / f.name)
                _retry(shutil.copy2, f, dest)
                gathered.append((od.name, dest))
    log(f"Gathered {len(gathered)} .lst file(s) from {len(order_dirs)} order folder(s).")
    progress_callback(35)

    if cancel_event.is_set():
        log("Cancelled."); return

    # ── Phase 2: PO ──
    master_po = _find_master_po(batch_path, batch_no)
    if not master_po:
        raise RuntimeError(
            "Master PO workbook (PO H{batch} QF-QU-09) not found in the batch's "
            "Documentation folder.".replace("{batch}", batch_no))
    log(f"Reading PO: {master_po.name}...")
    master_map, serial_desc = _read_po(master_po, log)
    log(f"  {len(master_map)} DYPN rows, {len(serial_desc)} material descriptions.")
    progress_callback(55)

    # ── Phase 3: resolve ──
    log("Matching files to materials...")
    pulled, expected, serial_desc = _resolve(
        gathered, master_map, serial_desc, batch_path, log)
    resolved = [p for p in pulled if p.resolved]
    review = [p for p in pulled if not p.resolved]
    progress_callback(75)

    # ── Phase 4: organize ──
    if do_organize and not dry_run:
        log("Filing files into material folders...")
        for p in pulled:
            sdk.raise_if_cancelled(cancel_event)
            target_dir = lst_dir / p.folder
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                _retry(shutil.move, str(p.src), str(_unique(target_dir / p.src.name)))
            except Exception as e:
                log(f"  WARNING: could not file {p.src.name}: {e}")
    progress_callback(88)

    # ── Phase 5: report ──
    report = lst_dir / f"LST Report - Batch {batch_no}.pdf"
    try:
        _write_report(report, batch_no, master_po,
                      [d.name for d in order_dirs], pulled, expected, len(gathered),
                      serial_desc)
        log(f"Report: {report}")
    except Exception as e:
        log(f"WARNING: could not write report: {e}")
    progress_callback(95)

    # ── console summary ──
    std_total = sum(1 for v in expected.values() if v[2] == "standard")
    over_total = sum(1 for v in expected.values() if v[2] == "oversized")
    covered = {p.part for p in resolved}
    missing = [d for d, v in expected.items()
               if v[2] == "standard" and d not in covered]
    extra = [p for p in resolved if p.tube and p.part not in expected]
    by_letter = [p for p in resolved if p.how == "suffix"]
    log("=" * 60)
    log(f"922 LST Organizer - Batch {batch_no}")
    log(f"  Total tubes in PO:            {std_total + over_total}")
    log(f"  Oversized (no .lst):          {over_total}")
    log(f"  Target (standard tubes):      {std_total}")
    log(f"  Files found & filed:          {len(resolved)}")
    log(f"  Extra (not in batch PO):      {len(extra)}")
    log(f"  Missing standard tubes:       {len(missing)}")
    log(f"  Needs review:                 {len(review)}")
    log("=" * 60)
    if by_letter:
        # Surfaced, not silent: the PO and the file spell the same piece
        # differently, so show the user exactly what was paired.
        log(f"Matched by revision letter ({len(by_letter)}) - same piece, "
            "PO and file spell the suffix differently:")
        for p in by_letter:
            log(f"  - PO {p.part}  <-  {p.src.name}")

    if missing or review or extra:
        lines = []
        if missing:
            lines.append(f"{len(missing)} standard tube(s) missing:")
            lines += [f"  - {d}  -  {_material_label(expected[d][1], serial_desc)}"
                      for d in sorted(missing)[:12]]
            if len(missing) > 12:
                lines.append(f"  ...and {len(missing) - 12} more")
        if review:
            lines.append(f"\n{len(review)} file(s) need review (moved to '{NEEDS_REVIEW_FOLDER}'):")
            lines += [f"  - {p.src.name}: {p.reason}" for p in review[:12]]
        if extra:
            lines.append(f"\n{len(extra)} extra file(s) filed but NOT in the batch PO "
                         "(verify the PO isn't missing a line):")
            lines += [f"  - {p.src.name}  [{_order_num(p.order)}]  = {p.part}" for p in extra[:12]]
        sdk.show_warning(params, f"922 LST - Batch {batch_no}", "\n".join(lines))

    progress_callback(100)


if __name__ == "__main__":
    import threading
    run(
        params={"log": print,
                "settings": {"base_path": "", "dry_run": True, "organize_by_material": True}},
        progress_callback=lambda p: print(f"[{p}%]"),
        cancel_event=threading.Event(),
    )
