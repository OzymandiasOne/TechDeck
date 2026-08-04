"""
Generate a demo DXF set for showing off the Customer DXF Analysis plugin.

Builds a folder that exercises every branch of the plugin worth showing:

    <out>/
        Batch 4471 - Weldment Brackets/     <- "Whole folder" mode (6 parts)
        Customer Sample - Lift Bracket.dxf  <- "Single file" mode, mis-layered
        Customer Sample - Round Flange.dxf  <- "Single file" mode, all circles
        README - Demo Run Sheet.txt         <- thickness to type + what to expect

Every part is written in the DXF flavor the plugin's PATCH parser requires:

  * ASCII, strict two-line group pairs (pairs[i] <-> lines[2i], lines[2i+1]),
  * a LAYER table with at least one full record (process_dxf clones it to add
    the HOLES layer, and raises without one),
  * explicit 50/51 angles on every ARC (_patch_segments refuses an arc that
    has none),
  * a 42 bulge code on EVERY LWPOLYLINE vertex (a bulge vertex with no 42 to
    patch raises LoopOffsetError),
  * closed loops wound CCW, chained-entity loops whose endpoints meet well
    inside CHAIN_TOL (5e-4),
  * free lines (bend/weld) only in files whose profile is a single closed
    LWPOLYLINE, so a stray endpoint can never be chained into the outline.

Run it with --verify (the default) and it re-reads everything it wrote through
the plugin's own parse_dxf / measure_dxf / process_dxf / export_with_layers and
asserts the offsets land where the customer guideline table says they should.

    python tools/make_demo_dxfs.py                 # generate + verify
    python tools/make_demo_dxfs.py --out <dir>
    python tools/make_demo_dxfs.py --verify-only
"""

import argparse
import importlib.util
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path.home() / "OneDrive - American Steel & Alum" / "Desktop" / "Customer DXF Demo"
BATCH_DIR = "Batch 4471 - Weldment Brackets"

# ACI color indexes (mirror the plugin's DEFAULT_LAYER_COLORS)
ACI = {"CUT": 1, "BEND_UP": 4, "BEND_DOWN": 6, "WELD": 5, "BOUNDING_BOX": 9,
       "Layer1": 7, "0": 7}

BULGE_90 = math.tan(math.pi / 8)    # quarter-circle CCW
BULGE_180 = 1.0                     # half-circle CCW


# ---------------------------------------------------------------------------
# DXF writer
# ---------------------------------------------------------------------------

def num(v):
    """Plain decimal, no exponent, no trailing zero noise."""
    txt = f"{float(v):.10f}".rstrip("0").rstrip(".")
    return txt if txt not in ("", "-0") else "0"


class Dxf:
    """Minimal AC1015 ASCII DXF builder (HEADER / TABLES / ENTITIES / EOF)."""

    def __init__(self, title=""):
        self.title = title
        self.layers = {}      # name -> aci
        self.entities = []    # (etype, layer, [(code, value_or_number), ...])
        self.pts = []         # every point that matters, for $EXTMIN/$EXTMAX

    # -- layers ------------------------------------------------------------
    def use_layer(self, name):
        if name not in self.layers:
            self.layers[name] = ACI.get(name, 7)
        return name

    # -- entities ----------------------------------------------------------
    def line(self, layer, p1, p2):
        self.use_layer(layer)
        self.pts += [p1, p2]
        self.entities.append(("LINE", layer, [
            (100, "AcDbEntity"), (8, layer), (100, "AcDbLine"),
            (10, num(p1[0])), (20, num(p1[1])), (30, "0"),
            (11, num(p2[0])), (21, num(p2[1])), (31, "0"),
        ]))

    def circle(self, layer, c, r):
        self.use_layer(layer)
        self.pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        self.entities.append(("CIRCLE", layer, [
            (100, "AcDbEntity"), (8, layer), (100, "AcDbCircle"),
            (10, num(c[0])), (20, num(c[1])), (30, "0"), (40, num(r)),
        ]))

    def arc(self, layer, c, r, a0_deg, a1_deg):
        """DXF arcs always run CCW from a0 to a1."""
        self.use_layer(layer)
        self.pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
        self.entities.append(("ARC", layer, [
            (100, "AcDbEntity"), (8, layer), (100, "AcDbCircle"),
            (10, num(c[0])), (20, num(c[1])), (30, "0"), (40, num(r)),
            (100, "AcDbArc"), (50, num(a0_deg)), (51, num(a1_deg)),
        ]))

    def lwpolyline(self, layer, verts, closed=True):
        """verts = [(x, y, bulge)]. A 42 code is written for EVERY vertex."""
        self.use_layer(layer)
        self.pts += [(v[0], v[1]) for v in verts]
        groups = [(100, "AcDbEntity"), (8, layer), (100, "AcDbPolyline"),
                  (90, str(len(verts))), (70, "1" if closed else "0")]
        for x, y, b in verts:
            groups += [(10, num(x)), (20, num(y)), (42, num(b))]
        self.entities.append(("LWPOLYLINE", layer, groups))

    # -- output ------------------------------------------------------------
    def _pairs(self):
        handle = 0x100
        layer_records = []
        for name, aci in self.layers.items():
            layer_records.append([
                (0, "LAYER"), (5, format(handle, "X")),
                (100, "AcDbSymbolTableRecord"), (100, "AcDbLayerTableRecord"),
                (2, name), (70, "0"), (62, str(aci)), (6, "CONTINUOUS"),
            ])
            handle += 1
        table_handle = format(handle, "X")
        handle += 1

        ent_pairs = []
        for etype, _lyr, groups in self.entities:
            ent_pairs.append((0, etype))
            ent_pairs.append((5, format(handle, "X")))
            handle += 1
            ent_pairs.extend(groups)

        xs = [p[0] for p in self.pts] or [0.0]
        ys = [p[1] for p in self.pts] or [0.0]

        pairs = [
            (0, "SECTION"), (2, "HEADER"),
            (9, "$ACADVER"), (1, "AC1015"),
            (9, "$INSUNITS"), (70, "1"),                 # 1 = inches
            (9, "$EXTMIN"), (10, num(min(xs))), (20, num(min(ys))), (30, "0"),
            (9, "$EXTMAX"), (10, num(max(xs))), (20, num(max(ys))), (30, "0"),
            (9, "$HANDSEED"), (5, format(handle + 16, "X")),
            (0, "ENDSEC"),
            (0, "SECTION"), (2, "TABLES"),
            (0, "TABLE"), (2, "LAYER"), (5, table_handle),
            (100, "AcDbSymbolTable"), (70, str(len(layer_records))),
        ]
        for rec in layer_records:
            pairs.extend(rec)
        pairs += [(0, "ENDTAB"), (0, "ENDSEC"),
                  (0, "SECTION"), (2, "ENTITIES")]
        pairs.extend(ent_pairs)
        pairs += [(0, "ENDSEC"), (0, "EOF")]
        return pairs

    def write(self, path):
        lines = []
        for code, value in self._pairs():
            lines.append(f"{code:3d}")
            lines.append(str(value))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # CRLF like every CAD package; no BOM (a BOM-prefixed DXF is rejected).
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("\r\n".join(lines) + "\r\n")
        return path


# ---------------------------------------------------------------------------
# Geometry helpers - every loop comes back wound CCW
# ---------------------------------------------------------------------------

def rect_verts(x, y, w, h):
    return [(x, y, 0.0), (x + w, y, 0.0), (x + w, y + h, 0.0), (x, y + h, 0.0)]


def rounded_rect_verts(x, y, w, h, r):
    b = BULGE_90
    return [
        (x + r, y, 0.0), (x + w - r, y, b),
        (x + w, y + r, 0.0), (x + w, y + h - r, b),
        (x + w - r, y + h, 0.0), (x + r, y + h, b),
        (x, y + h - r, 0.0), (x, y + r, b),
    ]


def slot_verts(cx, cy, length, width, vertical=False):
    """Obround slot: two straights + two 180 degree caps."""
    r = width / 2.0
    run = (length - width) / 2.0
    if run <= 0:
        raise ValueError("slot length must exceed its width")
    if vertical:
        return [(cx + r, cy - run, 0.0), (cx + r, cy + run, BULGE_180),
                (cx - r, cy + run, 0.0), (cx - r, cy - run, BULGE_180)]
    return [(cx - run, cy - r, 0.0), (cx + run, cy - r, BULGE_180),
            (cx + run, cy + r, 0.0), (cx - run, cy + r, BULGE_180)]


# ---------------------------------------------------------------------------
# The parts
# ---------------------------------------------------------------------------

def base_plate():
    """12 x 8 plate: 4 grown holes, 1 over the 2x cap, 1 under the minimum."""
    d = Dxf()
    d.lwpolyline("CUT", rect_verts(0, 0, 12, 8))
    for cx, cy in [(0.875, 0.875), (11.125, 0.875), (11.125, 7.125), (0.875, 7.125)]:
        d.circle("CUT", (cx, cy), 0.5625 / 2)
    d.circle("CUT", (6.0, 4.0), 1.5 / 2)         # >= 2t at 1/2" -> untouched
    d.circle("CUT", (3.0, 6.5), 0.1875 / 2)      # < 1/2 t       -> flagged
    return d


def slotted_rail():
    """Slots (bulged polylines) + holes + a bend line that never chains."""
    d = Dxf()
    d.lwpolyline("CUT", rect_verts(0, 0, 14, 3))
    for cx in (3.0, 7.0, 11.0):
        d.lwpolyline("CUT", slot_verts(cx, 1.5, 1.5, 0.375))
    d.circle("CUT", (0.75, 1.5), 0.3125 / 2)
    d.circle("CUT", (13.25, 1.5), 0.3125 / 2)
    d.line("BEND_UP", (5.0, 0.05), (5.0, 2.95))   # inset: cannot join the outline
    return d


def tube_cap():
    """Round plate: the profile IS a circle; concentric bore + bolt circle."""
    d = Dxf()
    d.circle("CUT", (0.0, 0.0), 10.0 / 2)        # profile
    d.circle("CUT", (0.0, 0.0), 2.0 / 2)         # >= 2t at 3/8" -> untouched
    for i in range(6):
        a = math.radians(i * 60.0)
        d.circle("CUT", (3.75 * math.cos(a), 3.75 * math.sin(a)), 0.4062 / 2)
    return d


def access_cover():
    """Rounded profile + a rectangular cutout + a hole under the minimum."""
    d = Dxf()
    d.lwpolyline("CUT", rounded_rect_verts(0, 0, 10, 7, 0.75))
    d.lwpolyline("CUT", rect_verts(3.75, 3.0625, 2.5, 0.875))   # cutout
    for cx, cy in [(1.25, 1.25), (8.75, 1.25), (8.75, 5.75), (1.25, 5.75)]:
        d.circle("CUT", (cx, cy), 0.5 / 2)
    d.circle("CUT", (5.0, 1.0), 0.25 / 2)        # < 1/2 t at 5/8" -> flagged
    return d


def heavy_pad():
    """Venti band: thick plate, a bore over the cap, a vent under the minimum."""
    d = Dxf()
    d.lwpolyline("CUT", rect_verts(0, 0, 9, 9))
    for cx, cy in [(1.25, 1.25), (7.75, 1.25), (7.75, 7.75), (1.25, 7.75)]:
        d.circle("CUT", (cx, cy), 1.0625 / 2)
    d.circle("CUT", (4.5, 4.5), 3.5 / 2)         # >= 2t at 1-1/2" -> untouched
    d.circle("CUT", (4.5, 8.25), 0.5 / 2)        # < 1/2 t         -> flagged
    return d


def lift_bracket():
    """The mis-layered customer file: profile on 'Layer1', bends, a weld seam."""
    d = Dxf()
    d.lwpolyline("Layer1", rounded_rect_verts(0, 0, 9, 5, 0.5))   # reassign me
    d.circle("CUT", (1.25, 2.5), 0.6875 / 2)
    d.circle("CUT", (7.75, 2.5), 0.6875 / 2)
    d.lwpolyline("CUT", slot_verts(4.5, 2.5, 2.0, 0.5))
    d.line("BEND_UP", (3.0, 0.08), (3.0, 4.92))
    d.line("BEND_DOWN", (6.0, 0.08), (6.0, 4.92))
    d.line("WELD", (0.35, 4.4), (8.65, 4.4))
    return d


def round_flange():
    """All circles: profile, bore over the cap, bolt circle, tiny tap holes."""
    d = Dxf()
    d.circle("CUT", (0.0, 0.0), 8.0 / 2)         # profile
    d.circle("CUT", (0.0, 0.0), 3.0 / 2)         # >= 2t at 1/4" -> untouched
    for i in range(8):
        a = math.radians(22.5 + i * 45.0)
        d.circle("CUT", (2.875 * math.cos(a), 2.875 * math.sin(a)), 0.4375 / 2)
    for i in range(4):
        a = math.radians(i * 90.0)
        d.circle("CUT", (1.0 * math.cos(a), 1.0 * math.sin(a)), 0.1015 / 2)
    return d


# (relative path, builder, demo thickness, expected process_dxf stats)
PARTS = [
    (f"{BATCH_DIR}/BRKT-4471-01 Base Plate.dxf", base_plate, 0.500,
     dict(band="Medium", holes=5, cutouts=0, unchanged=1, profiles=1, below_min=1)),
    (f"{BATCH_DIR}/BRKT-4471-02 Slotted Rail.dxf", slotted_rail, 0.250,
     dict(band="Grande", holes=2, cutouts=3, unchanged=0, profiles=1, below_min=0)),
    (f"{BATCH_DIR}/BRKT-4471-03 Tube Cap.dxf", tube_cap, 0.375,
     dict(band="Grande", holes=6, cutouts=0, unchanged=1, profiles=1, below_min=0)),
    (f"{BATCH_DIR}/BRKT-4471-04 Access Cover.dxf", access_cover, 0.625,
     dict(band="Medium", holes=5, cutouts=1, unchanged=0, profiles=1, below_min=1)),
    (f"{BATCH_DIR}/BRKT-4471-05 Heavy Pad.dxf", heavy_pad, 1.500,
     dict(band="Venti", holes=5, cutouts=0, unchanged=1, profiles=1, below_min=1)),
    ("Customer Sample - Lift Bracket.dxf", lift_bracket, 0.500,
     dict(band="Medium", holes=2, cutouts=1, unchanged=0, profiles=1, below_min=0)),
    ("Customer Sample - Round Flange.dxf", round_flange, 0.250,
     dict(band="Grande", holes=12, cutouts=0, unchanged=1, profiles=1, below_min=4)),
]


# ---------------------------------------------------------------------------
# Verification - drive the plugin's own engine over what we just wrote
# ---------------------------------------------------------------------------

def load_plugin():
    """Import the plugin's run.py as a module (offscreen - it pulls in Qt)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(
        "cdxf_demo_engine", REPO / "plugins" / "customer_dxf_analysis" / "run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scratch_dxf(prefix):
    """A closed temp path - mkstemp leaves the handle OPEN, and Windows then
    refuses to unlink it."""
    fd, path = tempfile.mkstemp(suffix=".dxf", prefix=prefix)
    os.close(fd)
    return Path(path)


def verify(out_dir, quiet=False):
    eng = load_plugin()
    failures = []

    def say(msg=""):
        if not quiet:
            print(msg)

    for rel, _builder, thickness, want in PARTS:
        src = Path(out_dir) / rel
        name = Path(rel).name
        say(f"\n{'=' * 78}\n{rel}   (demo thickness {thickness}\")")
        try:
            # --- 1. the viewer parser ------------------------------------
            ents, colors, skipped, insunits = eng.parse_dxf(src)
            if skipped:
                failures.append(f"{name}: viewer skipped {skipped}")
            if insunits != 1:
                failures.append(f"{name}: $INSUNITS={insunits}, expected 1")
            per_layer = {}
            for e in ents:
                per_layer[e["layer"]] = per_layer.get(e["layer"], 0.0) + e["length"]
            total = sum(v for k, v in per_layer.items()
                        if k.upper() not in eng.NEVER_COUNT)
            say(f"  parse_dxf   : {len(ents)} entities, 0 skipped, "
                f"units=inches, {total:.3f} linear in")
            say(f"                layers " + ", ".join(
                f"{k} ({v:.2f}\")" for k, v in sorted(per_layer.items())))
            for lyr in per_layer:
                if lyr not in colors:
                    failures.append(f"{name}: layer {lyr} missing from LAYER table")

            # --- 2. Adjust Dimensions' read-only measure ------------------
            m = eng.measure_dxf(src)
            say(f"  measure_dxf : {len(m['holes'])} holes "
                f"{[round(h, 4) for h in m['holes']]}, {m['cutouts']} cutouts, "
                f"profile {m['profile_size']}")
            for w in m["warnings"]:
                say(f"                note: {w}")

            # --- 3. guideline offsets at the demo thickness ---------------
            band = eng.guideline_band(thickness)
            tmp = scratch_dxf("demo_chk_")
            stats = eng.process_dxf(src, tmp, 0.0, 0.0, "HOLES",
                                    lambda *_a, **_k: None, thickness=thickness)
            got = dict(band=stats["band"], holes=stats["holes"],
                       cutouts=stats["cutouts"], unchanged=stats["unchanged"],
                       profiles=stats["profiles"], below_min=len(stats["below_min"]))
            say(f"  process_dxf : band {stats['band']} (+{band[1] * 2:.4f}\" dia), "
                f"{stats['holes']} grown, {stats['cutouts']} cutouts grown, "
                f"{stats['unchanged']} left alone, "
                f"{len(stats['below_min'])} under the 1/2-t minimum")
            if got != want:
                failures.append(f"{name}: stats {got} != expected {want}")

            # --- 4. the OUTPUT is still a valid DXF, grown by exactly 2x band
            oents, _oc, oskipped, _ou = eng.parse_dxf(tmp)
            if oskipped:
                failures.append(f"{name}: offset output skipped {oskipped}")
            if len(oents) != len(ents):
                failures.append(f"{name}: offset output lost entities")
            before = sorted(e["dia"] for e in ents if e["type"] == "CIRCLE")
            after = sorted(e["dia"] for e in oents if e["type"] == "CIRCLE")
            grown = [round(b, 4) for b, a in zip(before, after)
                     if abs((a - b) - 2 * band[1]) < 1e-6]
            same = [round(b, 4) for b, a in zip(before, after) if abs(a - b) < 1e-9]
            if len(grown) + len(same) != len(before):
                failures.append(f"{name}: a circle moved by an unexpected amount")
            if len(grown) != stats["holes"]:
                failures.append(
                    f"{name}: {len(grown)} circles grew but stats say {stats['holes']}")
            say(f"  re-read     : {len(oents)} entities, 0 skipped; "
                f"grew {sorted(set(grown))} -> +{2 * band[1]:.4f}\" dia; "
                f"untouched {sorted(set(same))}")
            hole_layers = {e["layer"] for e in oents if e["layer"] == "HOLES"}
            if (stats["holes"] or stats["cutouts"]) and not hole_layers:
                failures.append(f"{name}: HOLES layer never made it into the output")

            # --- 5. Save / Export DXF path (layer reassignment) -----------
            for e in ents:
                if e["layer"] != "CUT":
                    e["layer"] = "CUT"
            text, enc = eng.export_with_layers(src, ents)
            rt = scratch_dxf("demo_exp_")
            with open(rt, "w", encoding=enc, newline="") as fh:
                fh.write(text)
            rents, _rc, rskipped, _ru = eng.parse_dxf(rt)
            if rskipped or len(rents) != len(ents):
                failures.append(f"{name}: export round-trip changed the file")
            if any(e["layer"] != "CUT" for e in rents):
                failures.append(f"{name}: export did not rewrite every layer")
            say(f"  export      : reassign-all-to-CUT round-trip OK "
                f"({len(rents)} entities)")

            # --- 6. manual Adjust Dimensions defaults ---------------------
            mt = scratch_dxf("demo_man_")
            mstats = eng.process_dxf(src, mt, eng.DEFAULT_HOLE_INCREASE
                                     if hasattr(eng, "DEFAULT_HOLE_INCREASE")
                                     else 0.0625,
                                     eng.DEFAULT_EDGE_OFFSET, "HOLES",
                                     lambda *_a, **_k: None)
            ments, _mc, mskipped, _mu = eng.parse_dxf(mt)
            if mskipped:
                failures.append(f"{name}: manual-mode output skipped {mskipped}")
            say(f"  manual mode : +1/16\" dia / -1/16\" per side OK "
                f"({mstats['holes']} holes, {mstats['cutouts']} cutouts, "
                f"profile shrunk)")
            for p in (tmp, rt, mt):
                p.unlink(missing_ok=True)
        except Exception as exc:                     # noqa: BLE001 - report all
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            say(f"  !! {type(exc).__name__}: {exc}")

    say(f"\n{'=' * 78}")
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"All {len(PARTS)} demo files verified: parse, measure, guideline "
          f"offsets, re-read, export round-trip, manual mode.")
    return 0


# ---------------------------------------------------------------------------

RUN_SHEET = """\
CUSTOMER DXF ANALYSIS - DEMO RUN SHEET
======================================
Generated by tools/make_demo_dxfs.py. Every file here is a synthetic part
built to show one behaviour of the app; none of them are customer data.

Open TechDeck -> Customer DXF Analysis.


DEMO 1 - THE BATCH (folder mode, automated offsets ON)
------------------------------------------------------
Pick "Whole folder" with the "Automated offsets" box CHECKED, and choose:

    {batch}

Five files queue up and the thickness page lists all five at once. Type these
top to bottom, pressing Enter after each - Enter jumps to the next box, and
the last Enter submits. Then Enter, Enter, ... walks the review queue.

    BRKT-4471-01 Base Plate       0.500   (or 1/2)
    BRKT-4471-02 Slotted Rail     0.250   (or 1/4)
    BRKT-4471-03 Tube Cap         0.375   (or 3/8)
    BRKT-4471-04 Access Cover     0.625   (or 5/8)
    BRKT-4471-05 Heavy Pad        1.500   (or 1 1/2)

What each one is there to show:

  01 Base Plate    MEDIUM band (+1/16" dia). Four 9/16" holes grow; the 1-1/2"
                   access hole is left alone (it already measures 2x the plate
                   thickness); the 3/16" pilot hole trips the red
                   "1 below 1/2-t minimum" warning.
  02 Slotted Rail  GRANDE band (+1/32"). Three obround slots grow by WIDTH, not
                   length. The bend line sits on BEND_UP, which is unchecked by
                   default, so it is not counted in the linear-inch total - tick
                   it on to show the total move.
  03 Tube Cap      The profile IS a circle (round plate). The concentric 2"
                   bore is over the cap and stays put while the six bolt holes
                   grow - shows containment handles concentric geometry.
  04 Access Cover  MEDIUM band. Rounded corners, plus a rectangular CUTOUT that
                   grows on all four sides. The 1/4" vent hole is under the
                   1/2-thickness minimum.
  05 Heavy Pad     VENTI band (+3/32"). The 3-1/2" bore is past the 2x cap; the
                   1/2" drain hole is under the minimum.

Point out the toolbar verdict on each file: green "Offsets applied", the band
name, how many grew, and the red under-minimum count where it applies.


DEMO 2 - THE MIS-LAYERED CUSTOMER FILE (single file, offsets OFF)
-----------------------------------------------------------------
Pick "Single file" with "Automated offsets" UNCHECKED:

    Customer Sample - Lift Bracket.dxf

The verdict reads amber "No offsets applied" - this is the quoting side.
  * The outer profile came in on "Layer1" (the classic bad export). Click it
    in the view or the table, pick CUT in the layer box - it recolors and the
    subtotals update the moment you pick, no Apply button.
  * BEND_UP / BEND_DOWN / WELD are their own layers. Bends start unchecked, so
    the headline total is cut-only; tick WELD to show its inches separately.
  * Click any line to see its length, or the slot's cap arcs. Circles read as
    a diameter, not a cut length.
  * "Export DXF..." writes a copy with the reassignments; the original is
    untouched.


DEMO 3 - ONE PART, START TO FINISH (single file, offsets ON)
-------------------------------------------------------------
Pick "Single file" with "Automated offsets" CHECKED:

    Customer Sample - Round Flange.dxf     thickness 0.250

Everything on this one is a circle. The 3" bore is past the 2x cap and stays,
the eight 7/16" bolt holes grow by 1/32" diameter, and the four tiny 0.1015"
tap holes are flagged under the minimum. Hit Save to write the offsets back
over the original (the warning has a don't-ask-again box), or Export DXF to
write a copy instead.


NOTES
-----
* Re-run tools/make_demo_dxfs.py any time to reset these files to their
  original dimensions - Save overwrites them in place.
* Files whose name ends in " OFFSET" are skipped when a folder is queued, so
  the manual Adjust Dimensions output never gets re-offset.
* Don't add a BOUNDING_BOX rectangle to a file you run offsets on: it encloses
  the part, so the engine reads the box as the profile and the real profile as
  an interior feature.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help=f"output folder (default: {DEFAULT_OUT})")
    ap.add_argument("--verify-only", action="store_true",
                    help="check files that already exist instead of rewriting them")
    ap.add_argument("--no-verify", action="store_true",
                    help="write the files without running the checks")
    ap.add_argument("--clean", action="store_true",
                    help="delete the output folder first")
    args = ap.parse_args()

    out = Path(args.out)
    if not args.verify_only:
        if args.clean and out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)
        for rel, builder, _t, _w in PARTS:
            path = builder().write(out / rel)
            print(f"  wrote {path.relative_to(out)}  ({path.stat().st_size:,} bytes)")
        (out / "README - Demo Run Sheet.txt").write_text(
            RUN_SHEET.format(batch=out / BATCH_DIR), encoding="utf-8")
        print(f"  wrote README - Demo Run Sheet.txt")
        print(f"\n{len(PARTS)} DXFs written to {out}")
        if args.no_verify:
            return 0
    return verify(out)


if __name__ == "__main__":
    sys.exit(main())
