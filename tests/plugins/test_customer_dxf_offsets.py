"""Customer DXF Analysis — the offset engine's polyline + guideline behavior.

Pinned by user feedback (2026-08-19): holes/slots drawn as POLYLINEs got no
offset because the patch-oriented parser only read LWPOLYLINE — old-style
heavy POLYLINE (the only polyline flavor an R12 export can contain) was
skipped entirely. And real exports often write a "closed" shape as an OPEN
polyline whose last vertex repeats the first; that must count as a loop, and
the duplicate vertex must be re-patched alongside vertex 0 or the offset
outline kinks. The guideline band amounts are also pinned: the customer's
table is +1/32" dia under 1/2" plate, +1/16" to 1.25", +3/32" from 1.25"
to 3" (the .094 the feedback asked about), nothing at 3" and up.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def dxa():
    spec = importlib.util.spec_from_file_location(
        "dxa_run", PLUGINS / "customer_dxf_analysis" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- DXF builders -------------------------------------------------------------

def _dxf(entity_lines):
    """Minimal ASCII DXF: a LAYER table (the exporter clones its record when
    it adds the HOLES layer) + the given ENTITIES section lines."""
    head = ["0", "SECTION", "2", "TABLES",
            "0", "TABLE", "2", "LAYER",
            "0", "LAYER", "2", "0", "70", "0", "62", "7", "6", "CONTINUOUS",
            "0", "ENDTAB", "0", "ENDSEC",
            "0", "SECTION", "2", "ENTITIES"]
    tail = ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(head + entity_lines + tail) + "\n"


def _line(x1, y1, x2, y2):
    return ["0", "LINE", "8", "0",
            "10", str(x1), "20", str(y1), "11", str(x2), "21", str(y2)]


def _square_lines(x0, y0, size):
    pts = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]
    out = []
    for i in range(4):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        out += _line(x1, y1, x2, y2)
    return out


def _heavy_polyline(verts, closed):
    out = ["0", "POLYLINE", "8", "0", "66", "1", "70", "1" if closed else "0"]
    for x, y in verts:
        out += ["0", "VERTEX", "8", "0", "10", str(x), "20", str(y)]
    out += ["0", "SEQEND"]
    return out


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# --- guideline band table -----------------------------------------------------

@pytest.mark.parametrize("thickness,expected", [
    (0.10, None),
    (0.25, ("Grande", 0.015625)),
    (0.375, ("Grande", 0.015625)),   # customer ruling: exactly-0.375 is Grande
    (0.50, ("Medium", 0.03125)),
    (1.00, ("Medium", 0.03125)),
    (1.25, ("Venti", 0.046875)),     # feedback: 1.25-3 must give +3/32" dia
    (2.00, ("Venti", 0.046875)),
    (3.00, None),                    # customer ruling: "3 and UP" no offset
])
def test_guideline_band(dxa, thickness, expected):
    assert dxa.guideline_band(thickness) == expected


def test_venti_diameter_increase_is_094(dxa):
    band = dxa.guideline_band(2.0)
    assert round(2.0 * band[1], 3) == 0.094


# --- heavy POLYLINE holes get offsets -----------------------------------------

def _poly_bbox(parsed):
    polys = [e for e in parsed["entities"] if e["etype"] == "POLYLINE"]
    assert polys, "heavy POLYLINE missing from the parse"
    xs = [v[0] for v in polys[0]["verts"]]
    ys = [v[1] for v in polys[0]["verts"]]
    return polys[0], (min(xs), min(ys), max(xs), max(ys))


def test_closed_heavy_polyline_cutout_is_offset(dxa, tmp_path):
    # 10x10 profile of loose LINEs, 2x2 heavy-POLYLINE cutout in the middle.
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _heavy_polyline([(4, 4), (6, 4), (6, 6), (4, 6)], closed=True)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), 0.0, 0.0, "HOLES",
                            lambda *_: None, thickness=1.5)
    assert stats["cutouts"] == 1 and stats["profiles"] == 1
    assert "Venti" in stats["band"]

    ent, bbox = _poly_bbox(dxa._parse(str(dest)))
    d = 0.046875  # Venti per-side
    assert bbox == pytest.approx((4 - d, 4 - d, 6 + d, 6 + d), abs=1e-6)
    assert ent["layer"] == "HOLES"


def test_open_polyline_with_repeated_end_vertex_counts_as_closed(dxa, tmp_path):
    # Same cutout but written the way R12 exports often do: open flag,
    # last vertex repeating the first.
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _heavy_polyline([(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)],
                          closed=False)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), 0.0, 0.0, "HOLES",
                            lambda *_: None, thickness=1.5)
    assert stats["cutouts"] == 1

    ent, bbox = _poly_bbox(dxa._parse(str(dest)))
    d = 0.046875
    assert bbox == pytest.approx((4 - d, 4 - d, 6 + d, 6 + d), abs=1e-6)
    # The duplicate closing vertex must be co-patched onto vertex 0 —
    # unpatched it would keep its OLD coordinates and kink the outline.
    verts = ent["verts"]
    assert (verts[-1][0], verts[-1][1]) == (verts[0][0], verts[0][1])


def test_genuinely_open_polyline_warns_and_stays(dxa, tmp_path):
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _heavy_polyline([(4, 4), (6, 4), (6, 6)], closed=False)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), 0.0, 0.0, "HOLES",
                            lambda *_: None, thickness=1.5)
    assert stats["cutouts"] == 0
    assert any("don't close into a loop" in w for w in stats["warnings"])


def test_measure_dxf_sees_polyline_cutouts(dxa, tmp_path):
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _heavy_polyline([(4, 4), (6, 4), (6, 6), (4, 6)], closed=True)))
    info = dxa.measure_dxf(str(src))
    assert info["cutouts"] == 1
    assert info["profiles"] == 1


def _circle(x, y, r):
    return ["0", "CIRCLE", "8", "0",
            "10", str(x), "20", str(y), "40", str(r)]


# --- per-feature failures (2026-08-19: "is this for all offsets or just
# that line?" - failures must be per FEATURE, with the rest still offset) ---

def test_one_bad_feature_does_not_fail_the_file(dxa, tmp_path):
    # Manual mode, shrinking hole diameters by 1": the 0.5" hole inverts
    # (fails), the 4" hole shrinks fine - file written, failure recorded.
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _circle(2, 2, 0.25) + _circle(6, 5, 2.0)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), -1.0, 0.0, "HOLES",
                            lambda *_: None)
    assert stats["holes"] == 1
    assert len(stats["failed"]) == 1
    assert "invert" in stats["failed"][0]
    assert dest.exists()
    parsed = dxa._parse(str(dest))
    radii = sorted(e["r"] for e in parsed["entities"]
                   if e["etype"] == "CIRCLE")
    assert radii == pytest.approx([0.25, 1.5])  # failed one untouched


def test_all_features_failing_raises_with_the_reasons(dxa, tmp_path):
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10) + _circle(2, 2, 0.25)))
    dest = tmp_path / "part OFFSET.dxf"
    with pytest.raises(dxa.LoopOffsetError, match="No offsets could be applied"):
        dxa.process_dxf(str(src), str(dest), -1.0, 0.0, "HOLES",
                        lambda *_: None)


def test_all_capped_file_still_defines_the_holes_layer(dxa, tmp_path):
    # Every feature >=2x thickness: nothing grows, but the features are
    # still moved to HOLES - the layer record must be added or strict CAD
    # readers reject the output over an undefined layer.
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10) + _circle(5, 5, 2.0)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), 0.0, 0.0, "HOLES",
                            lambda *_: None, thickness=0.5)
    assert stats["holes"] == 0 and stats["unchanged"] == 1
    parsed = dxa._parse(str(dest))
    assert "HOLES" in parsed["layer_names"]


def test_two_x_thickness_cap_still_applies_to_polylines(dxa, tmp_path):
    # 2" opening on 0.5" plate measures past 2x thickness -> left unchanged.
    src = _write(tmp_path, "part.dxf", _dxf(
        _square_lines(0, 0, 10)
        + _heavy_polyline([(4, 4), (6, 4), (6, 6), (4, 6)], closed=True)))
    dest = tmp_path / "part OFFSET.dxf"
    stats = dxa.process_dxf(str(src), str(dest), 0.0, 0.0, "HOLES",
                            lambda *_: None, thickness=0.5)
    assert stats["cutouts"] == 0 and stats["unchanged"] == 1
    _ent, bbox = _poly_bbox(dxa._parse(str(dest)))
    assert bbox == pytest.approx((4, 4, 6, 6), abs=1e-9)
