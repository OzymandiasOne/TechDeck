"""
Customer DXF Analysis plugin for TechDeck.

Two tools in one (merged from Customer DXF Quoting + the DXF Offset Tool,
2026-07-29). A popup asks single file or whole folder:

- Single file: the interactive quoting viewer - geometry rendered with layer
  colors, a table of every entity's length, per-layer subtotals, and a grand
  total of linear inches for quoting. Lines can be reassigned to a different
  layer (CUT / BEND_UP / BEND_DOWN / WELD / BOUNDING_BOX) when the customer's
  file is mis-layered; BOUNDING_BOX and IGNORE never count toward the total.
  The Adjust Dimensions dialog additionally grows/shrinks every hole diameter
  and offsets the outer profile per side, writing "<name> OFFSET.dxf".

- Whole folder: every DXF in the picked folder gets the hole/profile offsets
  from Settings applied (defaults 1/16"), written alongside as
  "<name> OFFSET.dxf" - the batch flow of the old DXF Offset Tool.

Both paths patch the ORIGINAL file surgically - only the affected numeric
values and layer codes are rewritten, everything else survives byte-for-byte.
The DXF parsers are self-contained (stdlib only) so the frozen build needs no
new hiddenimports. ASCII DXF only.
"""

import math
from collections import Counter
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView,
    QGraphicsScene, QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsItem,
    QSplitter, QFileDialog, QMessageBox, QGroupBox, QAbstractItemView,
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit
)
from PySide6.QtCore import Qt, QRect, QRectF, QTimer, QItemSelectionModel
from PySide6.QtGui import (QPen, QBrush, QColor, QPainter, QPainterPath,
                           QPixmap, QIcon, QTransform)

from techdeck.core.plugin_window import PluginWindow

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# Module-level reference prevents the window from being garbage collected when run() returns
_window = None

SUPPORTED_TYPES = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}

# AutoCAD Color Index -> hex, for the indexes that show up in practice.
# (Full 255-entry ACI table is overkill; unknown indexes fall back to light gray.)
ACI_COLORS = {
    1: "#FF4444", 2: "#FFFF55", 3: "#55FF55", 4: "#55FFFF", 5: "#5577FF",
    6: "#FF55FF", 7: "#F0F0F0", 8: "#9A9A9A", 9: "#C8C8C8",
    250: "#3C3C3C", 251: "#5B5B5B", 252: "#848484", 253: "#ADADAD",
    254: "#D6D6D6", 255: "#FFFFFF",
}

# Layers offered for (re)assignment, and their colors when the file doesn't define them
STANDARD_LAYERS = ["CUT", "BEND_UP", "BEND_DOWN", "WELD", "BOUNDING_BOX"]
DEFAULT_LAYER_COLORS = {
    "CUT": ACI_COLORS[1], "BEND_UP": ACI_COLORS[4], "BEND_DOWN": ACI_COLORS[6],
    "BOUNDING_BOX": ACI_COLORS[9], "ETCH": ACI_COLORS[2], "FORM": ACI_COLORS[3],
    "IGNORE": ACI_COLORS[8], "WELD": ACI_COLORS[5],
}

# ACI color index written into the LAYER table for layers we ADD on export
# (hex isn't valid there; these mirror DEFAULT_LAYER_COLORS).
_LAYER_ACI = {
    "CUT": 1, "BEND_UP": 4, "BEND_DOWN": 6, "BOUNDING_BOX": 9,
    "ETCH": 2, "FORM": 3, "IGNORE": 8, "WELD": 5,
}

# Layers that are reference-only: never included in the linear-inch total
NEVER_COUNT = {"BOUNDING_BOX", "BOUNDING BOX", "IGNORE"}


def aci_to_hex(index):
    return ACI_COLORS.get(index, "#DDDDDD")


# ---------------------------------------------------------------------------
# DXF parsing
# ---------------------------------------------------------------------------

def _decode_dxf(path):
    """Read + decode an ASCII DXF. Returns (text, encoding)."""
    data = Path(path).read_bytes()
    if data.startswith(b"AutoCAD Binary DXF"):
        raise ValueError("Binary DXF files are not supported - re-export as ASCII DXF.")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            # Never hand "utf-8-sig" back as the WRITE encoding: on write it
            # always emits a BOM, and a DXF must start with a bare group code
            # (AutoCAD/SolidWorks reject a BOM-prefixed file as incomplete).
            return data.decode(enc), ("utf-8" if enc == "utf-8-sig" else enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode file - is this a DXF?")


def _read_pairs(path):
    """Read an ASCII DXF into a list of (group_code, value) pairs."""
    text, _enc = _decode_dxf(path)
    lines = text.splitlines()
    pairs = []
    it = iter(lines)
    for code_line in it:
        try:
            value = next(it)
        except StopIteration:
            break
        try:
            code = int(code_line.strip())
        except ValueError:
            raise ValueError("Malformed DXF (expected a numeric group code, "
                             f"got {code_line.strip()!r}).")
        pairs.append((code, value.strip()))
    if not pairs:
        raise ValueError("File is empty.")
    return pairs


def _arc_points(cx, cy, r, a0, sweep, n=None):
    """Sample an arc into a polyline for display."""
    if n is None:
        n = max(8, int(abs(sweep) / math.tau * 64) + 1)
    return [(cx + r * math.cos(a0 + sweep * t / n),
             cy + r * math.sin(a0 + sweep * t / n)) for t in range(n + 1)]


def _bulge_segment(p1, p2, bulge):
    """Polyline segment with DXF bulge -> (display points, true arc length)."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    if abs(bulge) < 1e-12 or chord < 1e-12:
        return [p1, p2], chord
    theta = 4.0 * math.atan(bulge)              # signed included angle (CCW positive)
    radius = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
    # Signed distance from chord midpoint to arc center, along the left normal
    h = chord * (1.0 - bulge * bulge) / (4.0 * bulge)
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    nx, ny = -dy / chord, dx / chord
    cx, cy = mx + nx * h, my + ny * h
    a0 = math.atan2(y1 - cy, x1 - cx)
    return _arc_points(cx, cy, radius, a0, theta), radius * abs(theta)


def _collect_until_next_entity(pairs, j):
    """Gather (code, value) groups from j until the next 0 group."""
    groups = []
    n = len(pairs)
    while j < n and pairs[j][0] != 0:
        groups.append(pairs[j])
        j += 1
    return groups, j


def _build_line(groups):
    g = dict()
    for code, val in groups:
        if code in (8, 10, 20, 11, 21):
            g[code] = val
    try:
        p1 = (float(g[10]), float(g[20]))
        p2 = (float(g[11]), float(g[21]))
    except KeyError:
        return None
    return {"type": "LINE", "layer": g.get(8, "0"),
            "points": [p1, p2], "length": math.dist(p1, p2)}


def _build_arc(groups, full_circle=False):
    g = {}
    for code, val in groups:
        if code in (8, 10, 20, 40, 50, 51):
            g[code] = val
    try:
        cx, cy, r = float(g[10]), float(g[20]), float(g[40])
    except KeyError:
        return None
    if full_circle:
        a0, sweep = 0.0, math.tau
        etype = "CIRCLE"
    else:
        a0 = math.radians(float(g.get(50, 0.0)))
        a1 = math.radians(float(g.get(51, 360.0)))
        sweep = (a1 - a0) % math.tau or math.tau
        etype = "ARC"
    ent = {"type": etype, "layer": g.get(8, "0"),
           "points": _arc_points(cx, cy, r, a0, sweep), "length": r * sweep}
    if full_circle:
        # Holes read as a diameter on the floor, so CIRCLEs DISPLAY as one
        # (label/tooltip/table); length stays the circumference - that is
        # what the linear-inch cut totals must keep counting.
        ent["dia"] = 2.0 * r
    return ent


def _build_lwpolyline(groups):
    layer, flags = "0", 0
    verts = []  # each: [x, y, bulge]
    for code, val in groups:
        if code == 8:
            layer = val
        elif code == 70:
            flags = int(val)
        elif code == 10:
            verts.append([float(val), None, 0.0])
        elif code == 20 and verts:
            verts[-1][1] = float(val)
        elif code == 42 and verts:
            verts[-1][2] = float(val)
    return _polyline_entity("LWPOLYLINE", layer, verts, closed=bool(flags & 1))


def _build_polyline(pairs, j):
    """Heavy POLYLINE: consume VERTEX entities through SEQEND. Returns (entity, next_j)."""
    groups, j = _collect_until_next_entity(pairs, j)
    layer, flags = "0", 0
    for code, val in groups:
        if code == 8:
            layer = val
        elif code == 70:
            flags = int(val)
    verts = []
    n = len(pairs)
    while j < n:
        code, val = pairs[j]
        if code == 0 and val == "VERTEX":
            vgroups, j = _collect_until_next_entity(pairs, j + 1)
            v = [None, None, 0.0]
            vflags = 0
            for c, vv in vgroups:
                if c == 10:
                    v[0] = float(vv)
                elif c == 20:
                    v[1] = float(vv)
                elif c == 42:
                    v[2] = float(vv)
                elif c == 70:
                    vflags = int(vv)
            # Skip spline frame control points (flag bit 16)
            if v[0] is not None and v[1] is not None and not (vflags & 16):
                verts.append(v)
        elif code == 0 and val == "SEQEND":
            _, j = _collect_until_next_entity(pairs, j + 1)
            break
        else:
            j += 1
    return _polyline_entity("POLYLINE", layer, verts, closed=bool(flags & 1)), j


def _polyline_entity(etype, layer, verts, closed):
    verts = [v for v in verts if v[1] is not None]
    if len(verts) < 2:
        return None
    points, total = [], 0.0
    seg_pairs = list(zip(verts, verts[1:]))
    if closed:
        seg_pairs.append((verts[-1], verts[0]))
    for v1, v2 in seg_pairs:
        seg_pts, seg_len = _bulge_segment((v1[0], v1[1]), (v2[0], v2[1]), v1[2])
        points.extend(seg_pts if not points else seg_pts[1:])
        total += seg_len
    return {"type": etype, "layer": layer, "points": points, "length": total}


def parse_dxf(path):
    """
    Parse an ASCII DXF.

    Returns (entities, layer_colors, skipped, insunits):
      entities     - list of {type, layer, points [(x,y)...], length,
                     orig_layer, span}. `span` is the inclusive (start, end)
                     range of this entity's (code, value) pairs in the file
                     (POLYLINE spans include its VERTEXes + SEQEND) and
                     `orig_layer` the layer as loaded — both used by
                     export_with_layers to write reassignments back.
      layer_colors - {layer_name: hex_color}
      skipped      - {entity_type: count} of unsupported entity types
      insunits     - $INSUNITS header value or None
    """
    pairs = _read_pairs(path)
    n = len(pairs)
    entities, layer_colors, skipped = [], {}, {}
    insunits = None
    section = None
    i = 0
    while i < n:
        code, val = pairs[i]
        if code == 0 and val == "SECTION" and i + 1 < n and pairs[i + 1][0] == 2:
            section = pairs[i + 1][1]
            i += 2
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            i += 1
            continue

        if section == "HEADER" and code == 9 and val == "$INSUNITS":
            if i + 1 < n and pairs[i + 1][0] == 70:
                insunits = int(pairs[i + 1][1])
            i += 1
            continue

        if section == "TABLES" and code == 0 and val == "LAYER":
            groups, i = _collect_until_next_entity(pairs, i + 1)
            name, color = None, 7
            for c, v in groups:
                if c == 2:
                    name = v
                elif c == 62:
                    color = abs(int(v))  # negative = layer off; color is abs value
            if name is not None:
                layer_colors[name] = aci_to_hex(color)
            continue

        if section == "ENTITIES" and code == 0:
            start = i
            if val == "LINE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_line(groups)
            elif val == "ARC":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_arc(groups)
            elif val == "CIRCLE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_arc(groups, full_circle=True)
            elif val == "LWPOLYLINE":
                groups, i = _collect_until_next_entity(pairs, i + 1)
                ent = _build_lwpolyline(groups)
            elif val == "POLYLINE":
                ent, i = _build_polyline(pairs, i + 1)
            else:
                skipped[val] = skipped.get(val, 0) + 1
                i += 1
                continue
            if ent is not None:
                ent["span"] = (start, i - 1)
                ent["orig_layer"] = ent["layer"]
                entities.append(ent)
            continue

        i += 1

    return entities, layer_colors, skipped, insunits


# ---------------------------------------------------------------------------
# Export — write layer reassignments back into the ORIGINAL file text
# ---------------------------------------------------------------------------

def export_with_layers(src_path, entities):
    """Return (text, encoding) for a DXF with the current layer assignments.

    The original file is patched surgically, never regenerated: only each
    entity's layer codes (8) are rewritten, per-entity color overrides
    (62/420) are dropped from REASSIGNED entities so they render BYLAYER,
    and any now-used layer missing from the LAYER table is added by cloning
    an existing record (so strict readers like AutoCAD don't reject the
    file over an undefined layer). All geometry stays byte-identical.
    """
    text, enc = _decode_dxf(src_path)
    lines = text.splitlines()
    newline = "\r\n" if "\r\n" in text else "\n"

    # pairs[i] <-> lines[2i] (code) + lines[2i+1] (value)
    pairs = []
    for k in range(0, len(lines) - 1, 2):
        try:
            pairs.append((int(lines[k].strip()), lines[k + 1].strip()))
        except ValueError:
            raise ValueError("Malformed DXF (expected a numeric group code, "
                             f"got {lines[k].strip()!r}).")

    # --- entity layer rewrites -------------------------------------------
    replace = {}        # value-line index -> new text
    drop_pairs = set()  # pair indices to delete entirely (stale 62/420)
    for e in entities:
        span = e.get("span")
        if not span:
            continue
        s, t = span
        if s >= len(pairs) or pairs[s][0] != 0:
            raise ValueError("The DXF on disk no longer matches what was "
                             "loaded - reopen the file and retry the export.")
        changed = e["layer"] != e.get("orig_layer", e["layer"])
        for idx in range(s, min(t, len(pairs) - 1) + 1):
            c = pairs[idx][0]
            if c == 8:
                replace[2 * idx + 1] = e["layer"]
            elif changed and c in (62, 420):
                drop_pairs.add(idx)

    # --- LAYER table: find definitions, a template record, the insert spot
    table_names = set()
    template_span = None      # (start, end) pairs of the first LAYER record
    endtab_idx = None         # pair index of the LAYER table's ENDTAB
    section = None
    in_layer_table = False
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if code == 0 and val == "SECTION" and i + 1 < len(pairs) and pairs[i + 1][0] == 2:
            section = pairs[i + 1][1]
            i += 2
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            i += 1
            continue
        if section == "TABLES":
            if code == 0 and val == "TABLE":
                in_layer_table = (i + 1 < len(pairs) and pairs[i + 1] == (2, "LAYER"))
            elif in_layer_table and code == 0 and val == "LAYER":
                start = i
                j = i + 1
                while j < len(pairs) and pairs[j][0] != 0:
                    if pairs[j][0] == 2:
                        table_names.add(pairs[j][1])
                    j += 1
                if template_span is None:
                    template_span = (start, j - 1)
                i = j
                continue
            elif in_layer_table and code == 0 and val == "ENDTAB":
                endtab_idx = i
                in_layer_table = False
        i += 1

    used = {e["layer"] for e in entities}
    missing = sorted(l for l in used if l not in table_names)

    insert_lines = []
    handseed_replace = None
    if missing:
        if endtab_idx is None:
            raise ValueError("No LAYER table found in this DXF - cannot add "
                             f"layer definitions for: {', '.join(missing)}")
        # Allocate handles above every handle in the file (codes 5/105).
        max_handle = 0
        handseed_pair = None
        for idx, (c, v) in enumerate(pairs):
            if c == 9 and v == "$HANDSEED":
                handseed_pair = idx + 1
            if c in (5, 105):
                try:
                    max_handle = max(max_handle, int(v, 16))
                except ValueError:
                    pass
        next_handle = max_handle + 1
        for name in missing:
            aci = _LAYER_ACI.get(name.upper(), 7)
            if template_span is not None:
                # Clone an existing record so the new one carries whatever
                # extras this file's flavor of DXF expects (330 owner,
                # 370/390 plot data, ...). Swap name/handle/color.
                s, t = template_span
                record, seen_62 = [], False
                for c, v in pairs[s:t + 1]:
                    if c == 2:
                        v = name
                    elif c == 5:
                        v = format(next_handle, "X")
                    elif c == 62:
                        v, seen_62 = str(aci), True
                    elif c == 420:
                        continue  # don't inherit a true-color override
                    record.append((c, v))
                if not seen_62:
                    record.append((62, str(aci)))
            else:
                record = [(0, "LAYER"), (5, format(next_handle, "X")),
                          (100, "AcDbSymbolTableRecord"),
                          (100, "AcDbLayerTableRecord"),
                          (2, name), (70, "0"), (62, str(aci)),
                          (6, "Continuous")]
            next_handle += 1
            for c, v in record:
                insert_lines.append(f"{c:3d}")
                insert_lines.append(v)
        if handseed_pair is not None and handseed_pair < len(pairs):
            handseed_replace = (2 * handseed_pair + 1, format(next_handle, "X"))

    # --- stitch the output -------------------------------------------------
    drop_lines = set()
    for idx in drop_pairs:
        drop_lines.add(2 * idx)
        drop_lines.add(2 * idx + 1)
    if handseed_replace is not None:
        replace[handseed_replace[0]] = handseed_replace[1]
    insert_at = 2 * endtab_idx if (missing and endtab_idx is not None) else -1

    out = []
    for ln_idx, ln in enumerate(lines):
        if ln_idx == insert_at:
            out.extend(insert_lines)
        if ln_idx in drop_lines:
            continue
        out.append(replace.get(ln_idx, ln))
    return newline.join(out) + newline, enc


TAU = math.tau
CHAIN_TOL = 5e-4      # endpoint-matching tolerance when chaining loops
DEFAULT_HOLE_INCREASE = 0.0625   # diameter, inches
DEFAULT_EDGE_OFFSET = 0.0625     # per side, inches
DEFAULT_HOLES_LAYER = "HOLES"
HOLES_LAYER_ACI = 1              # red


class LoopOffsetError(Exception):
    """A loop couldn't be offset safely - the file is skipped, not mangled."""


# ---------------------------------------------------------------------------
# DXF reading (patch-oriented: every entity remembers WHERE its values live)
# ---------------------------------------------------------------------------

def _read_pairs_patch(path):
    """(pairs, lines, newline, encoding); pairs[i] <-> lines[2i], lines[2i+1]."""
    text, enc = _decode_dxf(path)
    lines = text.splitlines()
    newline = "\r\n" if "\r\n" in text else "\n"
    pairs = []
    for k in range(0, len(lines) - 1, 2):
        try:
            pairs.append((int(lines[k].strip()), lines[k + 1].strip()))
        except ValueError:
            raise ValueError("Malformed DXF (expected a numeric group code, "
                             f"got {lines[k].strip()!r}).")
    if not pairs:
        raise ValueError("File is empty.")
    return pairs, lines, newline, enc


def _collect(pairs, j):
    """Groups + their pair indices from j until the next 0 code."""
    groups, idxs = [], []
    n = len(pairs)
    while j < n and pairs[j][0] != 0:
        groups.append(pairs[j])
        idxs.append(j)
        j += 1
    return groups, idxs, j


def _parse(path):
    """Parse the DXF into patchable entities + LAYER-table info.

    Returns a dict with: pairs, lines, newline, enc, insunits, entities
    (list of dicts with etype/layer/idx8/geometry/value pair indices),
    skipped ({etype: count}), layer_names, layer_template_span, endtab_idx.
    """
    pairs, lines, newline, enc = _read_pairs_patch(path)
    entities, skipped = [], {}
    insunits = None
    layer_names = set()
    layer_template_span = None
    endtab_idx = None
    section, in_layer_table = None, False

    i, n = 0, len(pairs)
    while i < n:
        code, val = pairs[i]
        if code == 0 and val == "SECTION" and i + 1 < n and pairs[i + 1][0] == 2:
            section = pairs[i + 1][1]
            i += 2
            continue
        if code == 0 and val == "ENDSEC":
            section = None
            i += 1
            continue

        if section == "HEADER" and code == 9 and val == "$INSUNITS":
            if i + 1 < n and pairs[i + 1][0] == 70:
                insunits = int(pairs[i + 1][1])
            i += 1
            continue

        if section == "TABLES":
            if code == 0 and val == "TABLE":
                in_layer_table = (i + 1 < n and pairs[i + 1] == (2, "LAYER"))
            elif in_layer_table and code == 0 and val == "LAYER":
                start = i
                _g, _idxs, j = _collect(pairs, i + 1)
                for c, v in _g:
                    if c == 2:
                        layer_names.add(v)
                if layer_template_span is None:
                    layer_template_span = (start, j - 1)
                i = j
                continue
            elif in_layer_table and code == 0 and val == "ENDTAB":
                endtab_idx = i
                in_layer_table = False
            i += 1
            continue

        if section == "ENTITIES" and code == 0:
            if val in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE"):
                groups, idxs, i = _collect(pairs, i + 1)
                ent = _build_entity(val, groups, idxs)
                if ent is not None:
                    entities.append(ent)
            else:
                if val not in ("SEQEND", "VERTEX"):
                    skipped[val] = skipped.get(val, 0) + 1
                i += 1
            continue

        i += 1

    return {"pairs": pairs, "lines": lines, "newline": newline, "enc": enc,
            "insunits": insunits, "entities": entities, "skipped": skipped,
            "layer_names": layer_names,
            "layer_template_span": layer_template_span,
            "endtab_idx": endtab_idx}


def _build_entity(etype, groups, idxs):
    g, gi = {}, {}
    verts = []  # LWPOLYLINE: [x, y, bulge, idx10, idx20, idx42]
    flags = 0
    for (code, val), idx in zip(groups, idxs):
        if etype == "LWPOLYLINE":
            if code == 8:
                g[8], gi[8] = val, idx
            elif code == 70:
                flags = int(val)
            elif code == 10:
                verts.append([float(val), None, 0.0, idx, None, None])
            elif code == 20 and verts:
                verts[-1][1] = float(val)
                verts[-1][4] = idx
            elif code == 42 and verts:
                verts[-1][2] = float(val)
                verts[-1][5] = idx
        elif code in (8, 10, 20, 11, 21, 40, 50, 51):
            g[code], gi[code] = val, idx

    ent = {"etype": etype, "layer": g.get(8, "0"), "idx8": gi.get(8)}
    try:
        if etype == "LINE":
            ent["p1"] = (float(g[10]), float(g[20]))
            ent["p2"] = (float(g[11]), float(g[21]))
            ent["gi"] = gi
        elif etype == "CIRCLE":
            ent["c"] = (float(g[10]), float(g[20]))
            ent["r"] = float(g[40])
            ent["gi"] = gi
        elif etype == "ARC":
            ent["c"] = (float(g[10]), float(g[20]))
            ent["r"] = float(g[40])
            ent["a0"] = math.radians(float(g.get(50, 0.0)))
            ent["a1"] = math.radians(float(g.get(51, 360.0)))
            ent["gi"] = gi
        elif etype == "LWPOLYLINE":
            vs = [v for v in verts if v[1] is not None]
            if len(vs) < 2:
                return None
            ent["verts"] = vs
            ent["closed"] = bool(flags & 1)
    except KeyError:
        return None
    return ent


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _pt_on(c, r, a):
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _seg_start(s):
    return s["p1"] if s["k"] == "l" else _pt_on(s["c"], s["r"], s["sa"])


def _seg_end(s):
    return s["p2"] if s["k"] == "l" else _pt_on(s["c"], s["r"], s["ea"])


def _sweep(s):
    return (s["ea"] - s["sa"]) % TAU if s["ccw"] else (s["sa"] - s["ea"]) % TAU


def _sample_seg(s, n=16):
    if s["k"] == "l":
        return [s["p1"], s["p2"]]
    sw = _sweep(s) or TAU
    sgn = 1.0 if s["ccw"] else -1.0
    return [_pt_on(s["c"], s["r"], s["sa"] + sgn * sw * t / n)
            for t in range(n + 1)]


def _loop_samples(segs):
    pts = []
    for s in segs:
        sp = _sample_seg(s)
        pts.extend(sp if not pts else sp[1:])
    return pts


def _signed_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xin > x:
                inside = not inside
    return inside


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Loop building
# ---------------------------------------------------------------------------

def _ent_to_seg(ent, rev):
    """LINE/ARC entity -> traversal segment. DXF arcs always run CCW a0->a1."""
    if ent["etype"] == "LINE":
        p1, p2 = (ent["p2"], ent["p1"]) if rev else (ent["p1"], ent["p2"])
        return {"k": "l", "p1": p1, "p2": p2, "src": ("ent", ent, rev)}
    if rev:
        return {"k": "a", "c": ent["c"], "r": ent["r"], "sa": ent["a1"],
                "ea": ent["a0"], "ccw": False, "src": ("ent", ent, rev)}
    return {"k": "a", "c": ent["c"], "r": ent["r"], "sa": ent["a0"],
            "ea": ent["a1"], "ccw": True, "src": ("ent", ent, rev)}


def _ent_endpoints(ent):
    if ent["etype"] == "LINE":
        return ent["p1"], ent["p2"]
    return (_pt_on(ent["c"], ent["r"], ent["a0"]),
            _pt_on(ent["c"], ent["r"], ent["a1"]))


def _chain_loops(free_ents):
    """Chain loose LINE/ARC entities into closed loops by endpoint matching.

    Returns (loops, leftover_count). Each loop is a list of segments in
    traversal order. Entities that don't close into a loop are left alone.
    """
    unused = list(range(len(free_ents)))
    loops, leftover = [], 0
    while unused:
        start_i = unused.pop(0)
        ent = free_ents[start_i]
        seg = _ent_to_seg(ent, rev=False)
        chain = [seg]
        loop_start = _seg_start(seg)
        cur = _seg_end(seg)
        closed = False
        while True:
            if _dist(cur, loop_start) < CHAIN_TOL and len(chain) > 1:
                closed = True
                break
            found = None
            for u in unused:
                a, b = _ent_endpoints(free_ents[u])
                if _dist(a, cur) < CHAIN_TOL:
                    found = (u, False)
                    break
                if _dist(b, cur) < CHAIN_TOL:
                    found = (u, True)
                    break
            if found is None:
                break
            u, rev = found
            unused.remove(u)
            seg = _ent_to_seg(free_ents[u], rev)
            chain.append(seg)
            cur = _seg_end(seg)
        if closed:
            loops.append(chain)
        else:
            leftover += len(chain)
    return loops, leftover


def _poly_to_segs(ent):
    """Closed LWPOLYLINE -> traversal segments (bulge -> true arc)."""
    vs = ent["verts"]
    segs = []
    for i in range(len(vs)):
        x1, y1, bulge = vs[i][0], vs[i][1], vs[i][2]
        j = (i + 1) % len(vs)
        x2, y2 = vs[j][0], vs[j][1]
        p1, p2 = (x1, y1), (x2, y2)
        if abs(bulge) < 1e-12:
            if _dist(p1, p2) < 1e-12:
                continue
            segs.append({"k": "l", "p1": p1, "p2": p2, "src": ("pv", ent, i)})
            continue
        chord = _dist(p1, p2)
        theta = 4.0 * math.atan(bulge)          # signed sweep, CCW positive
        r = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
        h = chord * (1.0 - bulge * bulge) / (4.0 * bulge)
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        nx, ny = -(y2 - y1) / chord, (x2 - x1) / chord
        c = (mx + nx * h, my + ny * h)
        sa = math.atan2(y1 - c[1], x1 - c[0])
        ea = math.atan2(y2 - c[1], x2 - c[0])
        segs.append({"k": "a", "c": c, "r": r, "sa": sa, "ea": ea,
                     "ccw": theta > 0, "src": ("pv", ent, i)})
    if len(segs) < 2:
        raise LoopOffsetError("Outline polyline has too few usable segments.")
    return segs


# ---------------------------------------------------------------------------
# Offsetting
# ---------------------------------------------------------------------------

def _offset_segments(segs, s):
    """Shift every segment LEFT of travel by s (negative = right). In place-ish:
    returns new segment list; arcs keep center, radius changes."""
    out = []
    for seg in segs:
        if seg["k"] == "l":
            dx = seg["p2"][0] - seg["p1"][0]
            dy = seg["p2"][1] - seg["p1"][1]
            length = math.hypot(dx, dy)
            if length < 1e-12:
                raise LoopOffsetError("Zero-length outline segment.")
            nx, ny = -dy / length, dx / length
            out.append({**seg,
                        "p1": (seg["p1"][0] + s * nx, seg["p1"][1] + s * ny),
                        "p2": (seg["p2"][0] + s * nx, seg["p2"][1] + s * ny),
                        "od": (dx, dy)})
        else:
            new_r = seg["r"] - s if seg["ccw"] else seg["r"] + s
            if new_r <= 1e-9:
                raise LoopOffsetError(
                    "Offset would collapse an arc (radius "
                    f"{seg['r']:.4f} too small for the offset).")
            out.append({**seg, "r": new_r, "osw": _sweep(seg)})
    return out


def _fix_junction(a, b):
    """Make a.end and b.start meet: intersect the offset segments and pull
    both endpoints to the intersection nearest the current (open) joint."""
    pa, pb = _seg_end(a), _seg_start(b)
    ref = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
    if a["k"] == "l" and b["k"] == "l":
        p = _isect_lines(a["p1"], a["p2"], b["p1"], b["p2"]) or ref
    elif a["k"] == "l":
        p = _isect_line_circle(a["p1"], a["p2"], b["c"], b["r"], ref)
    elif b["k"] == "l":
        p = _isect_line_circle(b["p1"], b["p2"], a["c"], a["r"], ref)
    else:
        p = _isect_circles(a["c"], a["r"], b["c"], b["r"], ref)
    _set_end(a, p)
    _set_start(b, p)


def _isect_lines(a1, a2, b1, b2):
    d1 = (a2[0] - a1[0], a2[1] - a1[1])
    d2 = (b2[0] - b1[0], b2[1] - b1[1])
    denom = d1[0] * d2[1] - d1[1] * d2[0]
    scale = max(abs(d1[0]), abs(d1[1]), abs(d2[0]), abs(d2[1]), 1.0)
    if abs(denom) < 1e-10 * scale * scale:
        return None  # parallel/collinear - caller snaps to the midpoint
    t = ((b1[0] - a1[0]) * d2[1] - (b1[1] - a1[1]) * d2[0]) / denom
    return (a1[0] + t * d1[0], a1[1] + t * d1[1])


def _isect_line_circle(l1, l2, c, r, ref):
    dx, dy = l2[0] - l1[0], l2[1] - l1[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    fx, fy = l1[0] - c[0], l1[1] - c[1]
    b = fx * ux + fy * uy
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        # No true intersection - snap to the circle point nearest the joint.
        return _project_to_circle(ref, c, r)
    root = math.sqrt(disc)
    cands = [(l1[0] + (-b + root) * ux, l1[1] + (-b + root) * uy),
             (l1[0] + (-b - root) * ux, l1[1] + (-b - root) * uy)]
    return min(cands, key=lambda p: _dist(p, ref))


def _isect_circles(c1, r1, c2, r2, ref):
    d = _dist(c1, c2)
    if d < 1e-12:
        return _project_to_circle(ref, c1, r1)
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    ux, uy = (c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d
    mx, my = c1[0] + a * ux, c1[1] + a * uy
    if h2 < 0:
        return _project_to_circle(ref, c1, r1)
    h = math.sqrt(h2)
    cands = [(mx - h * uy, my + h * ux), (mx + h * uy, my - h * ux)]
    return min(cands, key=lambda p: _dist(p, ref))


def _project_to_circle(p, c, r):
    d = _dist(p, c)
    if d < 1e-12:
        return (c[0] + r, c[1])
    return (c[0] + (p[0] - c[0]) * r / d, c[1] + (p[1] - c[1]) * r / d)


def _set_start(seg, p):
    if seg["k"] == "l":
        seg["p1"] = p
    else:
        seg["sa"] = math.atan2(p[1] - seg["c"][1], p[0] - seg["c"][0])


def _set_end(seg, p):
    if seg["k"] == "l":
        seg["p2"] = p
    else:
        seg["ea"] = math.atan2(p[1] - seg["c"][1], p[0] - seg["c"][0])


def _offset_loop(segs, s):
    """Offset a closed loop left-of-travel by s and re-join the corners.
    Raises LoopOffsetError if the result is degenerate."""
    out = _offset_segments(segs, s)
    for i in range(len(out)):
        _fix_junction(out[i], out[(i + 1) % len(out)])
    for seg in out:
        if seg["k"] == "l":
            dx = seg["p2"][0] - seg["p1"][0]
            dy = seg["p2"][1] - seg["p1"][1]
            if math.hypot(dx, dy) < 1e-9 or dx * seg["od"][0] + dy * seg["od"][1] <= 0:
                raise LoopOffsetError(
                    "Offset is larger than a feature of this outline "
                    "(an edge inverted). Reduce the offset.")
        else:
            if _sweep(seg) > seg["osw"] + math.pi:
                raise LoopOffsetError(
                    "Offset produced an invalid arc on this outline.")
    return out


# ---------------------------------------------------------------------------
# Regions (loops + circles), classification, patching
# ---------------------------------------------------------------------------

def _fmt(v):
    """DXF float format: plain decimal, no exponent surprises."""
    txt = f"{v:.10f}".rstrip("0").rstrip(".")
    return txt if txt not in ("", "-0") else "0"


def _patch_segments(segs, replace):
    """Write offset segments back into their source entities via `replace`
    ({value-line index: new text}). A polyline vertex's new position is the
    start point of its segment."""
    for seg in segs:
        kind, ent = seg["src"][0], seg["src"][1]
        if kind == "ent":
            gi = ent["gi"]
            rev = seg["src"][2]
            if ent["etype"] == "LINE":
                p_start, p_end = _seg_start(seg), _seg_end(seg)
                ep1, ep2 = (p_end, p_start) if rev else (p_start, p_end)
                replace[2 * gi[10] + 1] = _fmt(ep1[0])
                replace[2 * gi[20] + 1] = _fmt(ep1[1])
                replace[2 * gi[11] + 1] = _fmt(ep2[0])
                replace[2 * gi[21] + 1] = _fmt(ep2[1])
            else:  # ARC - center stays, radius/angles patched (DXF is CCW)
                if 50 not in gi or 51 not in gi:
                    raise LoopOffsetError(
                        "An outline ARC has no explicit start/end angles - "
                        "unsupported file flavor.")
                a_ccw0 = seg["ea"] if rev else seg["sa"]
                a_ccw1 = seg["sa"] if rev else seg["ea"]
                replace[2 * gi[40] + 1] = _fmt(seg["r"])
                replace[2 * gi[50] + 1] = _fmt(math.degrees(a_ccw0) % 360.0)
                replace[2 * gi[51] + 1] = _fmt(math.degrees(a_ccw1) % 360.0)
        else:  # ("pv", ent, vertex_index)
            vi = seg["src"][2]
            vert = ent["verts"][vi]
            p = _seg_start(seg)
            replace[2 * vert[3] + 1] = _fmt(p[0])
            replace[2 * vert[4] + 1] = _fmt(p[1])
            if seg["k"] == "a":
                new_bulge = math.tan(_sweep(seg) / 4.0)
                if not seg["ccw"]:
                    new_bulge = -new_bulge
                if vert[5] is None:
                    raise LoopOffsetError(
                        "A polyline arc vertex has no bulge code to patch.")
                replace[2 * vert[5] + 1] = _fmt(new_bulge)


def _relayer(ent, layer, replace, warnings):
    if ent.get("idx8") is not None:
        replace[2 * ent["idx8"] + 1] = layer
    else:
        warnings.append(f"Could not move a {ent['etype']} to layer {layer} "
                        "(no layer code in the file).")


def _layer_insert(parsed, layer_name):
    """Build (insert_lines, insert_at_line, handseed_patch) adding layer_name
    to the LAYER table by cloning the first record (same approach as the
    Customer DXF Quoting exporter). Returns (None, -1, None) if present."""
    if layer_name in parsed["layer_names"]:
        return None, -1, None
    if parsed["endtab_idx"] is None:
        raise ValueError("No LAYER table in this DXF - cannot add the "
                         f"{layer_name} layer.")
    pairs = parsed["pairs"]
    max_handle = 0
    handseed_pair = None
    for idx, (c, v) in enumerate(pairs):
        if c == 9 and v == "$HANDSEED":
            handseed_pair = idx + 1
        if c in (5, 105):
            try:
                max_handle = max(max_handle, int(v, 16))
            except ValueError:
                pass
    next_handle = max_handle + 1
    span = parsed["layer_template_span"]
    if span is not None:
        record, seen_62 = [], False
        for c, v in pairs[span[0]:span[1] + 1]:
            if c == 2:
                v = layer_name
            elif c == 5:
                v = format(next_handle, "X")
            elif c == 62:
                v, seen_62 = str(HOLES_LAYER_ACI), True
            elif c == 420:
                continue
            record.append((c, v))
        if not seen_62:
            record.append((62, str(HOLES_LAYER_ACI)))
    else:
        record = [(0, "LAYER"), (5, format(next_handle, "X")),
                  (100, "AcDbSymbolTableRecord"), (100, "AcDbLayerTableRecord"),
                  (2, layer_name), (70, "0"), (62, str(HOLES_LAYER_ACI)),
                  (6, "Continuous")]
    insert_lines = []
    for c, v in record:
        insert_lines.append(f"{c:3d}")
        insert_lines.append(v)
    handseed_patch = None
    if handseed_pair is not None and handseed_pair < len(pairs):
        handseed_patch = (2 * handseed_pair + 1, format(next_handle + 1, "X"))
    return insert_lines, 2 * parsed["endtab_idx"], handseed_patch



# ---------------------------------------------------------------------------
# Region classification + per-file offset processing
# ---------------------------------------------------------------------------

def _classify(parsed):
    """Chain outlines into loops and classify every region.

    Each CIRCLE entity gains ``is_hole`` (contained in a larger region);
    loops become info dicts with segs/pts/bbox/area + ``is_cutout``.
    Returns (circles, loop_info, warnings). Containment only counts STRICTLY
    LARGER regions, so concentric circles (a washer) classify correctly: the
    big OD ring is the profile even though its center point sits inside the
    small ID circle.
    """
    ents = parsed["entities"]
    circles = [e for e in ents if e["etype"] == "CIRCLE"]
    free = [e for e in ents if e["etype"] in ("LINE", "ARC")]
    polys = [e for e in ents if e["etype"] == "LWPOLYLINE"]

    loops = []
    for ent in polys:
        if ent["closed"]:
            loops.append(_poly_to_segs(ent))
    chained, leftover = _chain_loops(free)
    loops.extend(chained)

    warnings = []
    if leftover:
        warnings.append(f"{leftover} line/arc entities don't form a closed "
                        "outline - left unchanged.")
    for etype, count in sorted(parsed["skipped"].items()):
        if etype not in ("POINT",):
            warnings.append(f"{count}x {etype} not supported - left unchanged.")

    loop_info = []
    for segs in loops:
        pts = _loop_samples(segs)
        loop_info.append({"segs": segs, "pts": pts, "bbox": _bbox(pts),
                          "area": _signed_area(pts)})

    def _inside_any_loop(pt, min_area, exclude=None):
        for li in loop_info:
            if li is exclude or abs(li["area"]) <= min_area:
                continue
            b = li["bbox"]
            if not (b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]):
                continue
            if _point_in_poly(pt, li["pts"]):
                return True
        return False

    def _inside_any_circle(pt, min_area, exclude=None):
        for c in circles:
            if c is exclude or math.pi * c["r"] ** 2 <= min_area:
                continue
            if _dist(pt, c["c"]) < c["r"]:
                return True
        return False

    for c in circles:
        c_area = math.pi * c["r"] ** 2
        c["is_hole"] = (_inside_any_loop(c["c"], c_area)
                        or _inside_any_circle(c["c"], c_area, exclude=c))
    for li in loop_info:
        probe = li["pts"][0]
        li["is_cutout"] = (_inside_any_loop(probe, abs(li["area"]), exclude=li)
                           or _inside_any_circle(probe, abs(li["area"])))
    return circles, loop_info, warnings


def _unit_scale(insunits, log):
    """Offsets are specified in inches; scale them for metric files."""
    if insunits == 4:
        log("  Metric file (INSUNITS=mm) - offsets converted to mm.")
        return 25.4
    if insunits not in (None, 0, 1):
        log(f"  NOTE: unusual $INSUNITS={insunits} - "
            "treating drawing units as inches.")
    return 1.0


def measure_dxf(src):
    """Read-only analysis for the Adjust Dimensions dialog.

    Returns {holes: [diameter...], cutouts, profiles, profile_size (w, h)
    or None, insunits, warnings} in drawing units - nothing is written.
    """
    parsed = _parse(src)
    circles, loop_info, warnings = _classify(parsed)
    holes = sorted(2.0 * c["r"] for c in circles if c["is_hole"])
    cutouts = sum(1 for li in loop_info if li["is_cutout"])
    profiles = (sum(1 for li in loop_info if not li["is_cutout"])
                + sum(1 for c in circles if not c["is_hole"]))
    profile_size = None
    for li in loop_info:
        if not li["is_cutout"]:
            b = li["bbox"]
            profile_size = (b[2] - b[0], b[3] - b[1])
    if profile_size is None:
        # A standalone CIRCLE profile is a round plate - its size is the dia.
        for c in circles:
            if not c["is_hole"]:
                profile_size = (2.0 * c["r"], 2.0 * c["r"])
    return {"holes": holes, "cutouts": cutouts, "profiles": profiles,
            "profile_size": profile_size, "insunits": parsed["insunits"],
            "warnings": warnings}


def process_dxf(src, dest, hole_increase, edge_offset, holes_layer, log):
    """Offset one DXF; writes dest. Returns a stats dict."""
    parsed = _parse(src)
    scale = _unit_scale(parsed["insunits"], log)
    grow = (hole_increase / 2.0) * scale    # radial growth per hole
    shrink = edge_offset * scale            # per-side profile offset

    circles, loop_info, warnings = _classify(parsed)
    stats = {"holes": 0, "cutouts": 0, "profiles": 0, "warnings": warnings}
    replace = {}

    # Circles: holes grow; a standalone circle IS a round plate - it shrinks.
    for c in circles:
        if c["is_hole"]:
            new_r = c["r"] + grow
            if new_r <= 0:
                raise LoopOffsetError(
                    f"Shrinking hole R{c['r']:.4f} by {-grow:.4f} would "
                    "invert it.")
            replace[2 * c["gi"][40] + 1] = _fmt(new_r)
            _relayer(c, holes_layer, replace, warnings)
            stats["holes"] += 1
        else:
            new_r = c["r"] - shrink
            if new_r <= 0:
                raise LoopOffsetError(
                    f"Shrinking circle R{c['r']:.4f} by {shrink:.4f} would "
                    "invert it.")
            replace[2 * c["gi"][40] + 1] = _fmt(new_r)
            stats["profiles"] += 1

    # Loops: cutouts expand their opening; outer profiles pull inward.
    for li in loop_info:
        interior_left = li["area"] > 0
        if li["is_cutout"]:
            s = -grow if interior_left else grow      # expand the opening
        else:
            s = shrink if interior_left else -shrink  # pull edges inward
        new_segs = _offset_loop(li["segs"], s)
        _patch_segments(new_segs, replace)
        if li["is_cutout"]:
            for ent in {id(seg["src"][1]): seg["src"][1] for seg in new_segs}.values():
                _relayer(ent, holes_layer, replace, warnings)
            stats["cutouts"] += 1
        else:
            b = li["bbox"]
            stats["profiles"] += 1
            stats["profile_size"] = (b[2] - b[0], b[3] - b[1])

    if not stats["holes"] and not stats["cutouts"] and not stats["profiles"]:
        raise ValueError("No supported geometry (circles or closed outlines) "
                         "found in this file.")

    # --- add the HOLES layer if any hole geometry moved to it -------------
    insert_lines, insert_at, handseed_patch = (None, -1, None)
    if stats["holes"] or stats["cutouts"]:
        insert_lines, insert_at, handseed_patch = _layer_insert(parsed, holes_layer)
    if handseed_patch is not None:
        replace[handseed_patch[0]] = handseed_patch[1]

    out = []
    for ln_idx, ln in enumerate(parsed["lines"]):
        if ln_idx == insert_at and insert_lines:
            out.extend(insert_lines)
        out.append(replace.get(ln_idx, ln))
    text = parsed["newline"].join(out) + parsed["newline"]
    with open(dest, "w", encoding=parsed["enc"], newline="") as fh:
        fh.write(text)
    return stats


def _log_offset_stats(log, src, dest, stats, edge_offset):
    """One console line per processed file + its per-file notes."""
    bits = []
    if stats["holes"]:
        bits.append(f"{stats['holes']} hole(s) grown")
    if stats["cutouts"]:
        bits.append(f"{stats['cutouts']} cutout(s) grown")
    if stats["profiles"]:
        size = stats.get("profile_size")
        bits.append("profile shrunk"
                    + (f" ({size[0]:.4g} x {size[1]:.4g} -> "
                       f"{size[0] - 2 * edge_offset:.4g} x "
                       f"{size[1] - 2 * edge_offset:.4g})" if size else ""))
    log(f"  {src.name} -> {dest.name}: " + ", ".join(bits))
    for w in stats["warnings"]:
        log(f"    NOTE: {w}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class DxfView(QGraphicsView):
    """Graphics view with wheel zoom, middle/right-drag pan, left-click select
    (Ctrl+click adds to / removes from the selection)."""

    def __init__(self, on_pick, on_zoom=None, parent=None):
        super().__init__(parent)
        self._on_pick = on_pick
        self._on_zoom = on_zoom
        self._pan_origin = None
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#14141c"))
        self.setDragMode(QGraphicsView.NoDrag)
        # No visible scrollbars: pan is drag-based (the hidden bars still hold
        # the scroll range, so the drag-pan handlers keep working) and edge
        # dimension labels no longer butt up against a scrollbar.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
        if self._on_zoom is not None:
            self._on_zoom()  # re-spread length labels at the new zoom

    def mousePressEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            # 9x9 px pick box so hairline geometry is clickable
            picked = self.items(QRect(pos.x() - 4, pos.y() - 4, 9, 9))
            for item in picked:
                if isinstance(item, QGraphicsPathItem) and item.data(0) is not None:
                    self._on_pick(item.data(0), event.modifiers())
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None:
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_origin is not None and event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_origin = None
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(event)


class AnalysisWindow(PluginWindow):

    HIDDEN_BY_DEFAULT = {"BOUNDING_BOX", "BOUNDING BOX", "IGNORE"}

    @classmethod
    def _hidden_by_default(cls, layer):
        # Default total = cut geometry only: bends and welds start unchecked
        # (their per-layer subtotals still show on the checkboxes).
        name = layer.upper()
        return (name in cls.HIDDEN_BY_DEFAULT or name.startswith("BEND")
                or name.startswith("WELD"))

    def __init__(self, log=print, on_success=None, settings=None):
        super().__init__("customer_dxf_analysis", "Customer DXF Analysis")
        self.resize(1320, 840)
        self._log = log
        self._on_success = on_success  # success chime; fired on a successful DXF export
        self._settings = settings or {}  # Adjust Dimensions dialog defaults
        self.entities = []
        self.layer_colors = {}
        self.items = []        # QGraphicsPathItem per entity
        self.labels = []       # QGraphicsSimpleTextItem per entity
        self.layer_checks = {}
        self._geom_rect = QRectF()
        self._source_path = None
        self._build_ui()

    # ----- UI construction -------------------------------------------------

    def _build_ui(self):
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        self.btn_open = QPushButton("Open DXF...")
        self.btn_open.clicked.connect(self.open_file_dialog)
        self.btn_fit = QPushButton("Fit View")
        self.btn_fit.clicked.connect(self.fit_view)
        self.btn_export = QPushButton("Export DXF...")
        self.btn_export.setToolTip(
            "Save a copy of the DXF with the current layer assignments")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_dxf)
        self.btn_adjust = QPushButton("Adjust Dimensions...")
        self.btn_adjust.setToolTip(
            "Grow/shrink the hole diameters and offset the outer profile, "
            "writing '<name> OFFSET.dxf'")
        self.btn_adjust.setEnabled(False)
        self.btn_adjust.clicked.connect(self.open_adjust_dialog)
        self.chk_labels = QCheckBox("Show length labels")
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self._update_label_visibility)
        self.lbl_file = QLabel("No file loaded")
        toolbar.addWidget(self.btn_open)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.btn_export)
        toolbar.addWidget(self.btn_adjust)
        toolbar.addSpacing(12)
        toolbar.addWidget(self.chk_labels)
        toolbar.addStretch(1)
        toolbar.addWidget(self.lbl_file)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        self.scene = QGraphicsScene()
        self.view = DxfView(on_pick=self._on_view_pick,
                            on_zoom=self._resolve_label_overlaps)
        self.view.setScene(self.scene)
        splitter.addWidget(self.view)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.layers_group = QGroupBox("Layers (checked = shown + counted)")
        self.layers_layout = QVBoxLayout(self.layers_group)
        self.layers_layout.setSpacing(2)
        right_layout.addWidget(self.layers_group)

        assign_row = QHBoxLayout()
        assign_row.addWidget(QLabel("Assign selected lines to:"))
        self.cmb_assign = QComboBox()
        self.cmb_assign.addItems(STANDARD_LAYERS)
        # Auto-apply: picking a layer assigns the selected lines immediately —
        # no Apply click. `activated` only fires on USER interaction (including
        # re-picking the same entry), never on programmatic combo refreshes.
        self.cmb_assign.activated.connect(self._assign_selected)
        assign_row.addWidget(self.cmb_assign, 1)
        right_layout.addLayout(assign_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["#", "Layer", "Type", "Length / Ø (in)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._sync_highlights)
        self.table.cellClicked.connect(self._center_on_row)
        right_layout.addWidget(self.table, 1)

        totals = QGroupBox("Totals")
        totals_layout = QVBoxLayout(totals)
        self.lbl_total = QLabel("Total linear inches: -")
        self.lbl_total.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.lbl_skipped = QLabel("")
        totals_layout.addWidget(self.lbl_total)
        totals_layout.addWidget(self.lbl_skipped)
        right_layout.addWidget(totals)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([800, 500])
        root.addWidget(splitter, 1)

        self.set_content(container)

    # ----- file loading -----------------------------------------------------

    def open_file_dialog(self):
        start_dir = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DXF", start_dir, "DXF files (*.dxf);;All files (*.*)")
        if path:
            self.load_dxf(path)

    def load_dxf(self, path):
        try:
            sdk.ensure_local(path, log=self._log)
            entities, layer_colors, skipped, insunits = parse_dxf(path)
        except Exception as e:
            QMessageBox.critical(self, "Customer DXF Analysis", f"Could not read DXF:\n{e}")
            self._log(f"Failed to read {path}: {e}")
            return
        if not entities:
            QMessageBox.warning(self, "Customer DXF Analysis",
                                "No measurable geometry (LINE/ARC/CIRCLE/POLYLINE) found.")
            return

        self.entities = entities
        self.layer_colors = layer_colors
        self._source_path = path
        self.btn_export.setEnabled(True)
        self.btn_adjust.setEnabled(True)

        self.lbl_file.setText(Path(path).name)
        self._populate_scene()
        self._populate_layer_checks()
        self._refresh_assign_combo()
        self._populate_table()
        self._apply_layer_visibility()
        self.refresh_totals()
        # Defer the fit until the splitter/layout has settled at its real size,
        # otherwise the drawing lands off-center in a half-laid-out view
        QTimer.singleShot(0, self.fit_view)

        if skipped:
            detail = ", ".join(f"{t} x{c}" for t, c in sorted(skipped.items()))
            self.lbl_skipped.setText(f"Skipped (unsupported): {detail}")
            self._log(f"Skipped unsupported entities: {detail}")
        else:
            self.lbl_skipped.setText("")
        if insunits not in (None, 0, 1):
            self._log(f"NOTE: DXF $INSUNITS={insunits} (not inches) - "
                      "totals are in drawing units.")
        self._log_summary(path)

    def _log_summary(self, path):
        self._log(f"Loaded {Path(path).name}: {len(self.entities)} entities")
        for layer in self._layers_in_order():
            ents = [e for e in self.entities if e["layer"] == layer]
            total = sum(e["length"] for e in ents)
            suffix = "  [not counted]" if layer.upper() in NEVER_COUNT else ""
            self._log(f"  {layer}: {total:.4f} in ({len(ents)} entities){suffix}")

    # ----- scene / table / layer panel construction -------------------------

    def _layers_in_order(self):
        seen = []
        for e in self.entities:
            if e["layer"] not in seen:
                seen.append(e["layer"])
        return seen

    def _layer_color(self, layer):
        return self.layer_colors.get(layer) or DEFAULT_LAYER_COLORS.get(layer.upper(), "#DDDDDD")

    def _entity_tooltip(self, idx):
        e = self.entities[idx]
        if "dia" in e:
            return (f"#{idx + 1}  {e['type']} on {e['layer']}\n"
                    f"Diameter: {e['dia']:.4f} in\n"
                    f"(cut length: {e['length']:.4f} in)")
        return (f"#{idx + 1}  {e['type']} on {e['layer']}\n"
                f"Length: {e['length']:.4f} in")

    def _populate_scene(self):
        self.scene.clear()
        self.items = []
        self.labels = []
        xs, ys = [], []
        for idx, e in enumerate(self.entities):
            color = QColor(self._layer_color(e["layer"]))
            path = QPainterPath()
            pts = e["points"]
            # Negate Y: DXF is y-up, Qt scenes are y-down
            path.moveTo(pts[0][0], -pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, -y)
            xs.extend(p[0] for p in pts)
            ys.extend(-p[1] for p in pts)
            item = QGraphicsPathItem(path)
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidthF(1.4)
            item.setPen(pen)
            item.setData(0, idx)
            item.setToolTip(self._entity_tooltip(idx))
            self.scene.addItem(item)
            self.items.append(item)

            mid = pts[len(pts) // 2]
            label = QGraphicsSimpleTextItem(
                f"Ø{e['dia']:.3f}\"" if "dia" in e
                else f"{e['length']:.3f}\"")
            label.setBrush(QBrush(color))
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            label.setPos(mid[0], -mid[1])
            label.setZValue(10)
            self.scene.addItem(label)
            self.labels.append(label)

        # Fit on the geometry only - the fixed-size text labels report inflated
        # scene bounds (ItemIgnoresTransformations), which skewed fitInView
        self._geom_rect = QRectF()
        if xs:
            self._geom_rect = QRectF(min(xs), min(ys),
                                     (max(xs) - min(xs)) or 1.0,
                                     (max(ys) - min(ys)) or 1.0)
            # Pin the scene rect symmetrically around the part. Without this
            # the label items inflate sceneRect asymmetrically (down/right),
            # so fitInView's centering scroll could not reach center and the
            # part sat high in the viewport. The 1x padding each side leaves
            # room to drag-pan when zoomed in.
            pad_x = max(self._geom_rect.width(), 1.0)
            pad_y = max(self._geom_rect.height(), 1.0)
            self.scene.setSceneRect(
                self._geom_rect.adjusted(-pad_x, -pad_y, pad_x, pad_y))

    def _populate_layer_checks(self, preserve=None):
        preserve = preserve or {}
        while self.layers_layout.count():
            item = self.layers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.layer_checks = {}
        for layer in self._layers_in_order():
            ents = [e for e in self.entities if e["layer"] == layer]
            total = sum(e["length"] for e in ents)
            text = f"{layer}   -   {total:.4f} in   ({len(ents)})"
            if layer.upper() in NEVER_COUNT:
                text += "   [never counted]"
            chk = QCheckBox(text)
            chip = QPixmap(12, 12)
            chip.fill(QColor(self._layer_color(layer)))
            chk.setIcon(QIcon(chip))
            chk.setChecked(preserve.get(layer, not self._hidden_by_default(layer)))
            chk.toggled.connect(self._on_layer_toggled)
            self.layers_layout.addWidget(chk)
            self.layer_checks[layer] = chk

    def _refresh_assign_combo(self):
        current = self.cmb_assign.currentText()
        layers = list(STANDARD_LAYERS)
        layers += [l for l in self._layers_in_order() if l not in layers]
        self.cmb_assign.blockSignals(True)
        self.cmb_assign.clear()
        self.cmb_assign.addItems(layers)
        if current in layers:
            self.cmb_assign.setCurrentText(current)
        self.cmb_assign.blockSignals(False)

    def _populate_table(self):
        self.table.clearSelection()
        self.table.setRowCount(len(self.entities))
        for idx, e in enumerate(self.entities):
            cells = [str(idx + 1), e["layer"], e["type"],
                     f"Ø{e['dia']:.4f}" if "dia" in e
                     else f"{e['length']:.4f}"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(idx, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    # ----- interactivity ----------------------------------------------------

    def _selected_rows(self):
        return {ix.row() for ix in self.table.selectionModel().selectedRows()}

    def _on_view_pick(self, idx, modifiers):
        if modifiers & Qt.ControlModifier:
            model_index = self.table.model().index(idx, 0)
            self.table.selectionModel().select(
                model_index, QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
        else:
            self.table.selectRow(idx)
        self.table.scrollToItem(self.table.item(idx, 0))

    def _center_on_row(self, row, _col=0):
        if 0 <= row < len(self.items):
            self.view.centerOn(self.items[row])

    def _sync_highlights(self):
        selected = self._selected_rows()
        for idx, item in enumerate(self.items):
            pen = item.pen()
            if idx in selected:
                pen.setColor(QColor("#FFFFFF"))
                pen.setWidthF(3.5)
            else:
                pen.setColor(QColor(self._layer_color(self.entities[idx]["layer"])))
                pen.setWidthF(1.4)
            item.setPen(pen)

    def _assign_selected(self, _index=None):
        rows = sorted(self._selected_rows())
        if not rows:
            # Combo navigation with nothing selected is a no-op (auto-apply
            # fires on every pick) — a modal here would nag, so just log a hint.
            self._log("No lines selected — click a line in the view or table, "
                      "then pick a layer to reassign it.")
            return
        layer = self.cmb_assign.currentText()
        if layer not in self.layer_colors:
            self.layer_colors[layer] = DEFAULT_LAYER_COLORS.get(layer.upper(), "#DDDDDD")
        color = QColor(self._layer_color(layer))
        states = {l: c.isChecked() for l, c in self.layer_checks.items()}
        states.setdefault(layer, True)  # make a newly used layer visible so the change shows
        for r in rows:
            self.entities[r]["layer"] = layer
            self.labels[r].setBrush(QBrush(color))
            self.items[r].setToolTip(self._entity_tooltip(r))
            self.table.item(r, 1).setText(layer)
        self._populate_layer_checks(preserve=states)
        self._refresh_assign_combo()
        self._apply_layer_visibility()
        self._sync_highlights()
        self.refresh_totals()
        self._log(f"Assigned {len(rows)} line(s) to {layer}")

    def _included_layers(self):
        return {layer for layer, chk in self.layer_checks.items()
                if chk.isChecked() and layer.upper() not in NEVER_COUNT}

    def _on_layer_toggled(self, _checked):
        self._apply_layer_visibility()
        self.refresh_totals()

    def _apply_layer_visibility(self):
        labels_on = self.chk_labels.isChecked()
        dim = QBrush(QColor("#777777"))
        for idx, e in enumerate(self.entities):
            chk = self.layer_checks.get(e["layer"])
            visible = chk.isChecked() if chk else True
            counted = visible and e["layer"].upper() not in NEVER_COUNT
            self.items[idx].setVisible(visible)
            self.labels[idx].setVisible(visible and labels_on)
            for col in range(self.table.columnCount()):
                cell = self.table.item(idx, col)
                if cell:
                    cell.setData(Qt.ForegroundRole, None if counted else dim)
        self._resolve_label_overlaps()

    def _resolve_label_overlaps(self):
        """Spread length labels apart in SCREEN space.

        Entities can share a midpoint (a bounding-box edge over a cut edge,
        adjacent short segments), which stacked their labels into unreadable
        soup. Labels are ItemIgnoresTransformations, so their OWN transform
        applies in device pixels — a translate is a fixed on-screen nudge
        that survives panning. Recomputed on fit, zoom, and visibility
        changes (pan never changes relative label positions).
        """
        placed = []
        for label in self.labels:
            if not label.isVisible():
                continue
            anchor = self.view.mapFromScene(label.pos())
            br = label.boundingRect()  # device px (ignores transformations)
            rect = QRectF(anchor.x(), anchor.y(), br.width(), br.height())
            moved = True
            while moved:
                moved = False
                for other in placed:
                    if rect.intersects(other):
                        # Drop just below the label it collides with.
                        rect.moveTop(other.bottom() + 2)
                        moved = True
            label.setTransform(
                QTransform.fromTranslate(0, rect.top() - anchor.y()))
            placed.append(rect)

    def _update_label_visibility(self, _checked=None):
        self._apply_layer_visibility()

    def refresh_totals(self):
        included = self._included_layers()
        ents = [e for e in self.entities if e["layer"] in included]
        total = sum(e["length"] for e in ents)
        self.lbl_total.setText(f"Total linear inches: {total:.4f} in"
                               f"   ({len(ents)} entities)")

    def export_dxf(self):
        """Save a copy of the loaded DXF with the current layer assignments."""
        if not self._source_path or not self.entities:
            return
        src = Path(self._source_path)
        default = str(src.with_name(f"{src.stem} - Reassigned.dxf"))
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", default, "DXF files (*.dxf)")
        if not dest:
            return
        try:
            text, enc = export_with_layers(self._source_path, self.entities)
            Path(dest).write_text(text, encoding=enc, newline="")
        except Exception as e:
            QMessageBox.critical(self, "Customer DXF Analysis",
                                 f"Export failed:\n{e}")
            self._log(f"Export failed: {e}")
            return
        changed = sum(1 for ent in self.entities
                      if ent["layer"] != ent.get("orig_layer", ent["layer"]))
        self._log(f"Exported {Path(dest).name} "
                  f"({changed} reassigned line(s) written back)")
        if callable(self._on_success):
            self._on_success()

    def open_adjust_dialog(self):
        """Adjust the hole/profile dimensions of the loaded file and write
        its OFFSET copy (the single-file offset flow)."""
        if not self._source_path:
            return
        try:
            sdk.ensure_local(self._source_path, log=self._log)
            info = measure_dxf(self._source_path)
        except Exception as e:
            QMessageBox.critical(self, "Customer DXF Analysis",
                                 f"Could not analyze this DXF:\n{e}")
            self._log(f"Adjust Dimensions failed to analyze: {e}")
            return
        dlg = AdjustDimensionsDialog(self, self._source_path, info,
                                     self._settings, self._log,
                                     self._on_success)
        dlg.exec()
        if dlg.written_path and dlg.chk_open.isChecked():
            self.load_dxf(str(dlg.written_path))

    def fit_view(self):
        if not self._geom_rect.isNull():
            # 12% breathing room so edge dimension labels (fixed-size text
            # hanging outside the geometry) stay clear of the view edges.
            margin_x = self._geom_rect.width() * 0.12
            margin_y = self._geom_rect.height() * 0.12
            self.view.fitInView(self._geom_rect.adjusted(-margin_x, -margin_y,
                                                         margin_x, margin_y),
                                Qt.KeepAspectRatio)
            self._resolve_label_overlaps()



# ---------------------------------------------------------------------------
# Adjust Dimensions dialog (single-file offset flow)
# ---------------------------------------------------------------------------

class AdjustDimensionsDialog(QDialog):
    """Grow/shrink every hole diameter and offset the outer profile per side
    on the loaded DXF, writing "<name> OFFSET.dxf" next to the source (the
    old DXF Offset Tool, scoped to one file). Stays open when an offset
    fails so the values can be backed off; ``written_path`` holds the output
    path after a successful write."""

    def __init__(self, parent, src_path, info, settings, log, on_success):
        super().__init__(parent)
        self.setWindowTitle("Adjust Dimensions")
        self._src = Path(src_path)
        self._info = info
        self._log = log
        self._on_success = on_success
        self.written_path = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(f"<b>{self._src.name}</b>"))
        summary = QLabel("Detected: " + self._detected_text())
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if info["insunits"] == 4:
            layout.addWidget(QLabel("Metric file (mm) - the inch values "
                                    "below are converted automatically."))

        form = QFormLayout()
        self.ed_hole = QLineEdit(_fmt(_num(settings, "hole_increase",
                                           DEFAULT_HOLE_INCREASE)))
        self.ed_edge = QLineEdit(_fmt(_num(settings, "edge_offset",
                                           DEFAULT_EDGE_OFFSET)))
        self.ed_layer = QLineEdit((settings.get("holes_layer")
                                   or DEFAULT_HOLES_LAYER).strip())
        form.addRow("Increase hole diameters by (in):", self.ed_hole)
        form.addRow("Offset outer profile per side by (in):", self.ed_edge)
        form.addRow("Move hole geometry to layer:", self.ed_layer)
        layout.addLayout(form)

        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        layout.addWidget(self.lbl_result)

        self.chk_open = QCheckBox("Open the OFFSET file in the viewer when done")
        self.chk_open.setChecked(True)
        layout.addWidget(self.chk_open)

        buttons = QDialogButtonBox()
        self.btn_write = buttons.addButton("Write OFFSET DXF",
                                           QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._write)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.ed_hole.textChanged.connect(self._refresh_result)
        self.ed_edge.textChanged.connect(self._refresh_result)
        self._refresh_result()

    @staticmethod
    def _group_diameters(diameters, delta=0.0):
        """'2 x 1.0000", 1 x 0.5000"' - hole diameters grouped by size."""
        groups = Counter(round(d + delta, 4) for d in diameters)
        return ", ".join(f'{n} x {d:.4f}"' for d, n in sorted(groups.items()))

    def _detected_text(self):
        info = self._info
        bits = []
        if info["holes"]:
            bits.append(f"holes {self._group_diameters(info['holes'])}")
        if info["cutouts"]:
            bits.append(f"{info['cutouts']} cutout(s)/slot(s)")
        if info["profile_size"]:
            w, h = info["profile_size"]
            bits.append(f'outer profile {w:.4f} x {h:.4f}')
        if not bits:
            bits.append("no supported geometry")
        return "; ".join(bits)

    def _values(self):
        try:
            return float(self.ed_hole.text()), float(self.ed_edge.text())
        except (TypeError, ValueError):
            return None

    def _refresh_result(self):
        vals = self._values()
        if vals is None:
            self.lbl_result.setText("Enter numeric offset values.")
            self.btn_write.setEnabled(False)
            return
        hole, edge = vals
        info = self._info
        bits = []
        if info["holes"]:
            bits.append(f"holes {self._group_diameters(info['holes'], hole)}")
        if info["cutouts"]:
            bits.append(f"{info['cutouts']} cutout(s) grown the same amount")
        if info["profile_size"]:
            w, h = info["profile_size"]
            bits.append(f"outer profile {w - 2 * edge:.4f} x {h - 2 * edge:.4f}")
        self.lbl_result.setText(("Result: " + "; ".join(bits)) if bits else "")
        self.btn_write.setEnabled(True)

    def _write(self):
        vals = self._values()
        if vals is None:
            return
        hole, edge = vals
        layer = self.ed_layer.text().strip() or DEFAULT_HOLES_LAYER
        dest = self._src.with_name(f"{self._src.stem} OFFSET.dxf")
        try:
            stats = process_dxf(str(self._src), str(dest), hole, edge,
                                layer, self._log)
        except (LoopOffsetError, ValueError) as e:
            QMessageBox.warning(self, "Adjust Dimensions",
                                f"Could not offset this DXF:\n{e}")
            return  # dialog stays open so the values can be adjusted
        self.written_path = dest
        _log_offset_stats(self._log, self._src, dest, stats, edge)
        if callable(self._on_success):
            self._on_success()
        self.accept()


# ---------------------------------------------------------------------------
# Plugin entrypoint
# ---------------------------------------------------------------------------

def _num(settings, key, default):
    v = settings.get(key)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _ask_mode():
    """Single-vs-folder popup. run() executes on the MAIN Qt thread
    (requires_main_thread), where the console's request_choice - a
    worker-thread marshal - raises; a direct QMessageBox is the same UX.
    Returns "Single file" / "Whole folder", or None on cancel."""
    box = QMessageBox()
    box.setWindowTitle("Customer DXF Analysis")
    box.setText("Analyze a single DXF file, or offset every DXF in a folder?")
    box.setIcon(QMessageBox.Icon.Question)
    options = ["Single file", "Whole folder"]
    buttons = [box.addButton(o, QMessageBox.ButtonRole.AcceptRole)
               for o in options]
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(buttons[0])
    box.exec()
    clicked = box.clickedButton()
    for opt, btn in zip(options, buttons):
        if btn is clicked:
            return opt
    return None


def _run_batch(folder, settings, log, progress_callback, cancel_event, params):
    """Offset every DXF directly in `folder` (the old DXF Offset Tool batch
    flow) using the Settings > Apps offsets. Inputs already ending " OFFSET"
    (or "_OFFSET" - hand-renamed outputs exist in the wild) are skipped, so
    reruns are idempotent."""
    hole_increase = _num(settings, "hole_increase", DEFAULT_HOLE_INCREASE)
    edge_offset = _num(settings, "edge_offset", DEFAULT_EDGE_OFFSET)
    holes_layer = (settings.get("holes_layer") or DEFAULT_HOLES_LAYER).strip()

    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() == ".dxf"
                   and not p.stem.upper().endswith((" OFFSET", "_OFFSET")))
    if not files:
        raise sdk.UserFacingError(
            "The folder has no DXF files in it.",
            "Pick the folder that holds the part DXFs.")

    log(f"Offsetting {len(files)} DXF file(s): holes +{hole_increase:.4f}\" dia, "
        f"profile -{edge_offset:.4f}\" per side, holes -> layer {holes_layer}.")

    done, failed = 0, 0
    for i, src in enumerate(files):
        sdk.raise_if_cancelled(cancel_event)
        dest = src.with_name(f"{src.stem} OFFSET.dxf")
        try:
            sdk.ensure_local(src, log=log)
            stats = process_dxf(str(src), str(dest), hole_increase,
                                edge_offset, holes_layer, log)
        except (LoopOffsetError, ValueError) as exc:
            failed += 1
            log(f"  SKIPPED {src.name}: {exc}")
            continue
        done += 1
        _log_offset_stats(log, src, dest, stats, edge_offset)
        progress_callback(int((i + 1) / len(files) * 100))

    if failed and hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_PARTIAL,
            f"{failed} of {len(files)} file(s) skipped - see notes above.")
    if done == 0:
        raise sdk.UserFacingError(
            "No DXF could be processed - every file was skipped.",
            "Check the notes above; the files may use unsupported geometry.")
    on_success = params.get("on_success")
    if callable(on_success):
        # GUI-thread plugin: the shell suppresses its auto chime, so the
        # batch path must fire the success chime itself (plugin Hard Rule).
        on_success()


def run(params: dict, progress_callback, cancel_event):
    global _window
    log = params.get("log", print)
    settings = params.get("settings", {})

    progress_callback(5)
    mode = _ask_mode()
    if mode is None:
        if hasattr(cancel_event, "set"):
            cancel_event.set()
        return

    if mode == "Whole folder":
        folder = QFileDialog.getExistingDirectory(
            None, "Select the folder of DXF files",
            str(Path.home() / "Downloads"))
        if not folder:
            if hasattr(cancel_event, "set"):
                cancel_event.set()
            return
        _run_batch(Path(folder), settings, log, progress_callback,
                   cancel_event, params)
        return

    log("Opening Customer DXF Analysis...")
    progress_callback(10)
    _window = AnalysisWindow(log=log, on_success=params.get("on_success"),
                             settings=settings)
    _window.show()

    default = (settings.get("default_dxf") or "").strip()
    if default and Path(default).is_file():
        _window.load_dxf(default)
    else:
        _window.open_file_dialog()

    progress_callback(100)
    log("Customer DXF Analysis window opened.")
