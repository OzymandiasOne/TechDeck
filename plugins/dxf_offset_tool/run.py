"""DXF Offset Tool - grow holes / shrink the plate outline in ASCII DXF files.

Coating/fit allowance prep: every hole's diameter is increased by a set
amount (default 1/16"), the outer plate profile is offset inward per side
(default 1/16"), and hole geometry is moved to its own layer (default
HOLES). The source file is patched surgically - only the affected numeric
values and layer codes are rewritten, the same technique as Customer DXF
Quoting's export - so everything else in the file survives byte-for-byte.
Output is written next to the source as "<name> OFFSET.dxf".

Geometry support: CIRCLE holes, and outlines made of LINE/ARC entities or
closed LWPOLYLINEs (bulge arcs included). Round plates (a CIRCLE that IS
the outer profile) shrink instead of grow. ASCII DXF only.
"""

import math
from pathlib import Path

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

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

def _decode_dxf(path):
    data = Path(path).read_bytes()
    if data.startswith(b"AutoCAD Binary DXF"):
        raise ValueError("Binary DXF - re-export as ASCII DXF.")
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
    pairs, lines, newline, enc = _read_pairs(path)
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
# Per-file processing
# ---------------------------------------------------------------------------

def process_dxf(src, dest, hole_increase, edge_offset, holes_layer, log):
    """Offset one DXF; writes dest. Returns a stats dict."""
    parsed = _parse(src)

    # Units: offsets are specified in inches; scale for metric files.
    unit_scale = 1.0
    if parsed["insunits"] == 4:
        unit_scale = 25.4
        log("  Metric file (INSUNITS=mm) - offsets converted to mm.")
    elif parsed["insunits"] not in (None, 0, 1):
        log(f"  NOTE: unusual $INSUNITS={parsed['insunits']} - "
            "treating drawing units as inches.")
    grow = (hole_increase / 2.0) * unit_scale   # radial growth per hole
    shrink = edge_offset * unit_scale           # per-side profile offset

    ents = parsed["entities"]
    circles = [e for e in ents if e["etype"] == "CIRCLE"]
    free = [e for e in ents if e["etype"] in ("LINE", "ARC")]
    polys = [e for e in ents if e["etype"] == "LWPOLYLINE"]

    loops = []          # (segments, source_desc)
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

    # --- classify regions: outer profiles vs interior cutouts/holes -------
    loop_info = []
    for segs in loops:
        pts = _loop_samples(segs)
        loop_info.append({"segs": segs, "pts": pts, "bbox": _bbox(pts),
                          "area": _signed_area(pts)})

    # Containment only counts STRICTLY LARGER regions, so concentric circles
    # (a washer) classify correctly: the big OD ring is the profile even
    # though its center point sits inside the small ID circle.
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

    stats = {"holes": 0, "cutouts": 0, "profiles": 0, "warnings": warnings}
    replace = {}

    # Circles: inside another region = hole (grow); standalone = round plate.
    for c in circles:
        c_area = math.pi * c["r"] ** 2
        if (_inside_any_loop(c["c"], c_area)
                or _inside_any_circle(c["c"], c_area, exclude=c)):
            new_r = c["r"] + grow
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

    # Loops: contained in another loop = cutout (grow); else outer (shrink).
    for li in loop_info:
        probe = li["pts"][0]
        interior_left = li["area"] > 0
        is_cutout = (_inside_any_loop(probe, abs(li["area"]), exclude=li)
                     or _inside_any_circle(probe, abs(li["area"])))
        if is_cutout:
            s = -grow if interior_left else grow      # expand the opening
        else:
            s = shrink if interior_left else -shrink  # pull edges inward
        new_segs = _offset_loop(li["segs"], s)
        _patch_segments(new_segs, replace)
        if is_cutout:
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


# ---------------------------------------------------------------------------
# Plugin entry
# ---------------------------------------------------------------------------

def _num(settings, key, default):
    v = settings.get(key)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def run(params: dict, progress_callback, cancel_event):
    log = params.get("log", print)
    settings = params.get("settings", {})

    hole_increase = _num(settings, "hole_increase", DEFAULT_HOLE_INCREASE)
    edge_offset = _num(settings, "edge_offset", DEFAULT_EDGE_OFFSET)
    holes_layer = (settings.get("holes_layer") or DEFAULT_HOLES_LAYER).strip()

    single = (settings.get("dxf_file") or "").strip().strip('"')
    if single:
        src = Path(single)
        if not src.is_file():
            raise sdk.UserFacingError(
                f"The DXF file set in Settings does not exist: {src}",
                "Fix or clear the 'Single DXF file' setting in Settings > Apps.")
        files = [src]
    else:
        # Popup first: one file or a whole folder? (Older TechDeck without
        # request_choice/request_file falls back to the folder-only flow.)
        mode = "Whole folder"
        if hasattr(sdk, "request_choice") and hasattr(sdk, "request_file"):
            mode = sdk.request_choice(
                params, "DXF Offset Tool",
                "Offset a single DXF file, or every DXF in a folder?",
                ["Single file", "Whole folder"])
            if mode is None:
                if hasattr(cancel_event, "set"):
                    cancel_event.set()
                return
        if mode == "Single file":
            picked = sdk.request_file(params, "Select the DXF file",
                                      name_filter="DXF files (*.dxf)")
            if not picked:
                if hasattr(cancel_event, "set"):
                    cancel_event.set()
                return
            files = [Path(picked)]
        else:
            folder = sdk.request_directory(
                params, "Select the folder of DXF files")
            if not folder:
                if hasattr(cancel_event, "set"):
                    cancel_event.set()
                return
            root = Path(folder)
            files = sorted(p for p in root.iterdir()
                           if p.suffix.lower() == ".dxf"
                           and not p.stem.upper().endswith(" OFFSET"))
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
        progress_callback(int((i + 1) / len(files) * 100))

    if failed and hasattr(sdk, "set_run_outcome"):
        sdk.set_run_outcome(
            params, sdk.RUN_OUTCOME_PARTIAL,
            f"{failed} of {len(files)} file(s) skipped - see notes above.")
    if done == 0:
        raise sdk.UserFacingError(
            "No DXF could be processed - every file was skipped.",
            "Check the notes above; the files may use unsupported geometry.")
    log(f"Done: {done} file(s) written.")
