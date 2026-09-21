"""902 Part Validator: the three checks the app exists for.

  1. a PO part with no DXF                    -> MISSING
  2. a DXF that opens but holds no geometry   -> UNUSABLE
  3. an IGES that is cut off / damaged        -> CORRUPT

EB sends each part as a DXF + IGES pair, so the two are judged separately and
either one being wrong is an issue on the part (Issue: Y on the report).

The IGES "no part geometry" fixtures mirror two REAL files from batch 3921
whose SigmaNest-converted DXFs came out empty: H4533302-168 held only reference
planes / points / matrices (types 108 / 116 / 124), and H6980110-68 held four
LINE entities all flagged entity-use 01 = annotation (dimension linework). The
validator's verdict matched the converted DXF on 99 of 99 real parts.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def pv():
    spec = importlib.util.spec_from_file_location(
        "pv902_run", PLUGINS / "902_part_validator" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── DXF fixtures ────────────────────────────────────────────────────────────

def _dxf(entities: str, blocks: str = "", eof: bool = True) -> str:
    out = "  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1032\n  0\nENDSEC\n"
    if blocks:
        out += "  0\nSECTION\n  2\nBLOCKS\n" + blocks + "  0\nENDSEC\n"
    out += "  0\nSECTION\n  2\nENTITIES\n" + entities + "  0\nENDSEC\n"
    return out + ("  0\nEOF\n" if eof else "")


LINE = "  0\nLINE\n  8\n0\n 10\n0.0\n 20\n0.0\n 11\n1.0\n 21\n1.0\n"
TEXT = "  0\nTEXT\n  8\n0\n 10\n0.0\n 20\n0.0\n 40\n0.2\n  1\nSEE DRAWING\n"


def _block(name: str, body: str) -> str:
    return f"  0\nBLOCK\n  8\n0\n  2\n{name}\n 70\n0\n{body}  0\nENDBLK\n"


def _insert(name: str) -> str:
    return f"  0\nINSERT\n  8\n0\n  2\n{name}\n 10\n0.0\n 20\n0.0\n"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes(text.encode("latin-1") if isinstance(text, str) else text)
    return p


@pytest.mark.parametrize("name,text,verdict", [
    ("good.dxf", _dxf(LINE * 4), "good"),
    ("empty.dxf", _dxf(""), "empty"),
    ("text_only.dxf", _dxf(TEXT), "empty"),                 # a note is not a part
    ("zero.dxf", b"", "empty"),
    # geometry that lives in a block still counts ...
    ("block_geo.dxf", _dxf(_insert("PART"), _block("PART", LINE)), "good"),
    # ... but an INSERT of an EMPTY block does not (real: H6980110-68.dxf)
    ("block_empty.dxf", _dxf(_insert("LWR_ROD_STOP"), _block("LWR_ROD_STOP", "")), "empty"),
    ("nested.dxf", _dxf(_insert("A"), _block("A", _insert("B")) + _block("B", LINE)), "good"),
    ("cut_off.dxf", _dxf(LINE * 4, eof=False), "bad"),      # AutoCAD rejects it
    ("junk.dxf", b"\x00\x01\x02PK\x03\x04 not a dxf", "bad"),
    ("binary.dxf", b"AutoCAD Binary DXF\r\n\x1a\x00rest", "review"),
])
def test_check_dxf(pv, tmp_path, name, text, verdict):
    assert pv.check_dxf(_write(tmp_path, name, text)).verdict == verdict


# ── IGES fixtures ───────────────────────────────────────────────────────────

def _rec(body: str, letter: str, seq: int) -> str:
    return f"{body:<72}{letter}{seq:>7}"


def _iges(entities, drop_line=None, truncate=False) -> bytes:
    """entities: [(type, status)] -> a structurally valid fixed-format IGES."""
    lines = [_rec("START RECORD", "S", 1), _rec("1H,,1H;,4HTEST;", "G", 1)]
    d, p = [], []
    for i, (etype, status) in enumerate(entities):
        d.append(_rec(f"{etype:>8}{i + 1:>8}{0:>8}{0:>8}{0:>8}{0:>8}{0:>8}{0:>8}{status}",
                      "D", 2 * i + 1))
        d.append(_rec(f"{etype:>8}{0:>8}{0:>8}{1:>8}{0:>8}", "D", 2 * i + 2))
        p.append(_rec(f"{etype},0.,0.,0.,1.,1.,0.;", "P", i + 1))
    lines += d + p
    lines.append(_rec(f"S{1:>7}G{1:>7}D{len(d):>7}P{len(p):>7}", "T", 1))
    if drop_line is not None:
        del lines[drop_line]
    data = "\n".join(lines) + "\n"
    if truncate:
        data = data[: len(data) // 2]
    return data.encode("latin-1")


GEOM, ANNOT, SCAFFOLD = "00020001", "00020101", "00010201"
REAL_PART = [(110, GEOM)] * 4 + [(116, ANNOT)] * 8 + [(108, SCAFFOLD)] * 8


@pytest.mark.parametrize("name,data,verdict", [
    ("good.igs", _iges(REAL_PART), "good"),
    ("zero.igs", b"", "bad"),
    ("truncated.igs", _iges(REAL_PART, truncate=True), "bad"),   # cut off in transfer
    ("line_lost.igs", _iges(REAL_PART, drop_line=5), "bad"),     # count mismatch
    ("junk.igs", b"PK\x03\x04\x00\x00 this is a zip", "bad"),
    ("not_iges.igs", b"hello\nthis is a text file\n", "bad"),
    # real H4533302-168: only planes, points, matrices
    ("scaffold_only.igs", _iges([(108, SCAFFOLD)] * 12 + [(116, ANNOT)] * 8
                                + [(124, SCAFFOLD)] * 31), "empty"),
    # real H6980110-68: four lines, every one flagged annotation
    ("annotation_lines.igs", _iges([(110, ANNOT)] * 4 + [(108, SCAFFOLD)] * 12), "empty"),
])
def test_check_iges(pv, tmp_path, name, data, verdict):
    assert pv.check_iges(_write(tmp_path, name, data)).verdict == verdict


def test_iges_corrupt_reason_is_plain_english(pv, tmp_path):
    r = pv.check_iges(_write(tmp_path, "t.igs", _iges(REAL_PART, truncate=True)))
    assert "cut off" in r.detail


# ── reconcile + report ──────────────────────────────────────────────────────

def _fc(pv, name, kind, verdict, detail="x"):
    return pv.FileCheck(Path("C:/b/files") / name, kind, verdict, detail)


def test_reconcile_judges_dxf_and_iges_separately(pv):
    po = [("H1000000-1", 2.0), ("H1000000-1", 3.0),     # repeated row: qty sums
          ("H1000000-2", 1.0), ("H1000000-3", 1.0), ("H1000000-4", 1.0),
          ("H1000000-5", 1.0), ("H1000000-6", 1.0), ("H1000000-7", 1.0)]
    checks = [
        # -1: a good pair, plus a bad COPY of the DXF - a copy never makes an issue
        _fc(pv, "H1000000-1_A_2.igs", "IGES", pv.GOOD),
        _fc(pv, "(5x) H1000000-1.dxf", "DXF", pv.GOOD),
        _fc(pv, "H1000000-1_A_2.dxf", "DXF", pv.EMPTY),
        # -2: DXF empty, IGES fine -> unusable
        _fc(pv, "H1000000-2.dxf", "DXF", pv.EMPTY, "no geometry - the drawing is empty"),
        _fc(pv, "H1000000-2.igs", "IGES", pv.GOOD),
        # -3: DXF fine, IGES cut off -> corrupt
        _fc(pv, "H1000000-3.dxf", "DXF", pv.GOOD),
        _fc(pv, "H1000000-3_A_FLAT-PATTERN#1.igs", "IGES", pv.BAD, "corrupt - the file is cut off"),
        # -4: nothing at all.  -5: binary DXF.  -6: IGES only.  -7: DXF only.
        _fc(pv, "H1000000-5.dxf", "DXF", pv.REVIEW, "binary DXF"),
        _fc(pv, "H1000000-5.igs", "IGES", pv.GOOD),
        _fc(pv, "H1000000-6.igs", "IGES", pv.GOOD),
        _fc(pv, "H1000000-7.dxf", "DXF", pv.GOOD),
        _fc(pv, "H9999999-1.dxf", "DXF", pv.GOOD),               # real part, wrong PO
        _fc(pv, "notes for anthony.dxf", "DXF", pv.GOOD),
    ]
    parts, extras = pv.reconcile(po, checks)
    by = {p.dypn: p for p in parts}
    assert [p.dypn for p in parts] == [f"H1000000-{n}" for n in range(1, 8)]  # PO order
    assert by["H1000000-1"].qty == 5.0 and not by["H1000000-1"].issue
    assert by["H1000000-1"].wrong == ""
    assert by["H1000000-2"].unusable and "no geometry" in by["H1000000-2"].wrong
    assert by["H1000000-3"].corrupt and "cut off" in by["H1000000-3"].wrong
    assert not by["H1000000-3"].unusable
    assert by["H1000000-4"].missing and by["H1000000-4"].wrong == "No file was sent"
    assert by["H1000000-5"].look and by["H1000000-5"].issue
    assert by["H1000000-6"].missing and "IGES only" in by["H1000000-6"].wrong
    assert not by["H1000000-7"].issue and "DXF only" in by["H1000000-7"].wrong
    assert {(f.path.name, why) for f, why in extras} == {
        ("H9999999-1.dxf", "not on this PO"),
        ("notes for anthony.dxf", "file name is not a part number")}


def test_reconcile_trailing_letter_is_the_same_piece(pv):
    """Real EB batches 4423 / 4426 / 4457: the PO says '-145M', the files say
    '-145'. Matched, and SAID - never silent, and never when it is ambiguous."""
    po = [("R4142704-145M", 1.0), ("H5534001-47M", 1.0), ("H5534001-47", 1.0),
          ("H7000000-1A", 1.0), ("H7000000-1B", 1.0)]
    checks = [
        _fc(pv, "R4142704-145_C_FLAT-PATTERN#1.dxf", "DXF", pv.GOOD),
        _fc(pv, "R4142704-145_C_FLAT-PATTERN#1.igs", "IGES", pv.GOOD),
        _fc(pv, "H5534001-47_A_FLAT-PATTERN#1.dxf", "DXF", pv.GOOD),   # exact hit wins
        _fc(pv, "H7000000-1.dxf", "DXF", pv.GOOD),                     # -1A or -1B? no guess
    ]
    parts, extras = pv.reconcile(po, checks)
    by = {p.dypn: p for p in parts}
    assert not by["R4142704-145M"].issue
    assert by["R4142704-145M"].matched_as == "R4142704-145"
    assert "R4142704-145" in by["R4142704-145M"].wrong
    assert len(by["R4142704-145M"].files) == 2                  # the pair moved together
    assert not by["H5534001-47"].missing and by["H5534001-47M"].missing
    assert by["H7000000-1A"].missing and by["H7000000-1B"].missing
    assert [f.path.name for f, _ in extras] == ["H7000000-1.dxf"]


def test_new_export_suffix_reduces_to_the_part_number(pv):
    # EB batch 4406: tags the suffix list never knew. A DYPN holds no underscore.
    clean = pv._prep().clean_stem
    assert clean("R6432001-F45-1_R_AS_1F01_of_1_FLAT-PATTERN#1") == "R6432001-F45-1"
    assert clean("R6432401-F23-1_R_BS_1F01_FLAT-PATTERN#1") == "R6432401-F23-1"
    assert clean("(18x) H4130810-484_A_2") == "H4130810-484"
    assert clean("notes for anthony") == "notes for anthony"


def test_report_page_one_is_the_five_counts_then_every_part(pv, tmp_path):
    fitz = pytest.importorskip("fitz")
    po = [("H1000000-1", 1.0), ("H1000000-2", 4.0), ("H1000000-3", 1.0)]
    checks = [
        _fc(pv, "H1000000-1.dxf", "DXF", pv.GOOD, "4 shape(s)"),
        _fc(pv, "H1000000-1.igs", "IGES", pv.GOOD, "4 shape(s)"),
        _fc(pv, "H1000000-3.dxf", "DXF", pv.EMPTY, "no geometry - the drawing is empty"),
        _fc(pv, "H1000000-3_A_1.igs", "IGES", pv.BAD, "corrupt - the file is cut off"),
        _fc(pv, "H7777777-9.dxf", "DXF", pv.GOOD),
    ]
    parts, extras = pv.reconcile(po, checks)
    out = tmp_path / "deep" / "3921 - PART VALIDATION REPORT.pdf"
    pv.write_report(out, "Batch 3921", "PO.xlsm", Path("C:/b/files"),
                    parts, extras, checks)
    doc = fitz.open(out)
    pages = [page.get_text() for page in doc]
    doc.close()
    first, rest = pages[0], "\n".join(pages[1:])

    # page 1: the five counts, in the order asked for, then every part
    order = [first.index(k) for k in ("TARGET PARTS", "MISSING", "UNUSABLE",
                                     "CORRUPT", "NEEDS A LOOK", "EVERY PART")]
    assert order == sorted(order)
    assert "NOT READY  -  2 of 3 part(s) have an issue." in first
    for col in ("Part", "Qty", "Issue", "What is wrong"):
        assert col in first
    assert "No file was sent" in first                      # H1000000-2
    assert "BREAKDOWN" not in first                         # it starts on its own page

    # next page on: the breakdown, in the order asked for
    order = [rest.index(k) for k in (
        "BREAKDOWN", "MISSING  -  NO DXF WAS SENT", "UNUSABLE  -  THE DXF IS EMPTY",
        "EMPTY OR DAMAGED DXF FILES", "CORRUPT OR EMPTY IGES FILES", "NOT ON THE PO")]
    assert order == sorted(order)
    assert "H1000000-3_A_1.igs" in rest and "H7777777-9.dxf" in rest


def test_report_ready_when_everything_is_good(pv, tmp_path):
    fitz = pytest.importorskip("fitz")
    checks = [_fc(pv, "H1000000-1.dxf", "DXF", pv.GOOD),
              _fc(pv, "H1000000-1.igs", "IGES", pv.GOOD)]
    parts, extras = pv.reconcile([("H1000000-1", 1.0)], checks)
    out = tmp_path / "ok.pdf"
    pv.write_report(out, "Batch 1", "PO.xlsm", Path("C:/b/files"), parts, extras, checks)
    doc = fitz.open(out)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    assert "READY  -  all 1 part(s) have a good file." in text
    assert "NOT READY" not in text
