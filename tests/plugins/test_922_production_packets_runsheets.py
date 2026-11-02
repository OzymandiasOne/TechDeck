"""Step 2: the production run binders.

Written against Carrie's own worked example for batch 508 (`TechDeck Packets\\
ANTHONY REF`, 2026-11-02), which carries the four stages side by side - the
1Ds her nesting software made, the same sheets after she marked them up, the
Word cover pages, and the bound binders. Step 2 reproduces all four binders
page for page, so the numbers below are hers, not invented.
"""
import importlib.util
import pathlib
import re
import zipfile

import fitz
import pytest

PDIR = (pathlib.Path(__file__).resolve().parents[2]
        / "plugins" / "922_production_packets")


@pytest.fixture(scope="module")
def rs():
    spec = importlib.util.spec_from_file_location("rs_test",
                                                  PDIR / "runsheets.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ───────────────────────────────────── where an estimated drop came from

def _tracker(tmp_path, sheets):
    """A stand-in Material Use Tracker: {batch: [(pallet, item, len, after)]}."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for batch, rows in sheets.items():
        ws = wb.create_sheet(str(batch))
        ws.append([f"BATCH {batch}"])
        ws.append(["PALLET ", "ITEM", "QTY", "SIZE", "LENGTH", "PR", "TAG",
                   "ESTIMATED AFTER RUN ", "DROP ", "MEI"])
        for pallet, item, length, after in rows:
            ws.append([pallet, item, 1, "x", length, "", "", after])
        ws.append(["PLATE USAGE ", "", "", "", "", "", "", ""])
        ws.append(["Z1", "262028653-11"])
    folder = tmp_path / "2 - Planning"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "EB 922 Material Use Tracker.xlsx"
    wb.save(dest)
    return tmp_path


def test_the_drop_comes_from_the_last_batch_that_left_one(rs, tmp_path):
    """Carrie's own answers on batch 508. `1.2` is the one that matters: 507
    used 218136140 and left NOTHING, so she looked past it to 505."""
    root = _tracker(tmp_path, {
        505: [("1", 218136140, 240, 75)],
        506: [("2", 218019939, 240, 150)],
        507: [("1", 218002867, 240, 140), ("1", 218136140, 18, 0),
              ("2", 218019939, 31.25, 0)],
        508: [("1", 218002867, "~140", 90), ("1", 218136140, "~70", 40),
              ("2", 218019939, "~145", 100), ("2", 218019941, 240, 145)],
    })
    bars = rs.read_tracker(root, 508, lambda *_a: None)

    assert bars[("1", "218002867")]["from_batch"] == "507"
    assert bars[("1", "218136140")]["from_batch"] == "505", \
        "507 used it and left nothing, so it is not the source"
    assert bars[("2", "218019939")]["from_batch"] == "506"
    # a plain length is a fresh stick - no note at all
    plain = bars[("2", "218019941")]
    assert plain["estimated"] is False and plain["from_batch"] is None


def test_an_estimated_bar_no_earlier_batch_left_is_reported(rs, tmp_path):
    root = _tracker(tmp_path, {
        507: [("1", 218002867, 240, 0)],
        508: [("1", 218002867, "~140", 90)],
    })
    said = []
    bars = rs.read_tracker(root, 508, said.append)
    entry = bars[("1", "218002867")]
    assert entry["estimated"] is True and entry["from_batch"] is None
    assert any("no earlier batch left a drop" in m for m in said), said


def test_a_blank_row_does_not_end_the_sheet(rs, tmp_path):
    """Batch 507's real sheet carries one, and stopping there hid every SAW
    row under it - which is what made the first read of this file wrong."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("508")
    ws.append(["BATCH 508"])
    ws.append(["PALLET ", "ITEM", "QTY", "SIZE", "LENGTH", "PR", "TAG",
               "ESTIMATED AFTER RUN "])
    ws.append(["1", 218002867, 1, "x", 240, "", "", 90])
    ws.append([None, None, None, None, None, None, None, None])
    ws.append(["SAW", 218012959, 1, "x", 240, "", "", 65])
    folder = tmp_path / "2 - Planning"
    folder.mkdir(parents=True)
    wb.save(folder / "EB 922 Material Use Tracker.xlsx")

    bars = rs.read_tracker(tmp_path, 508, lambda *_a: None)
    assert ("SAW", "218012959") in bars, "the row below the gap was dropped"


# ──────────────────────────────────────────────── marking up a 1D sheet

def _one_d(path, material):
    """A stand-in 1D carrying the three things `annotate` anchors on."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((20, 60), material, fontsize=12)
    page.insert_text((20, 120), "Cut From Bars :  218002867 ~", fontsize=10)
    page.insert_text((176, 120), "Bar Length :  140", fontsize=10)
    page.insert_text((36, 315), "Total Bars  (218002867 ~   L=140) :",
                     fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def _added(path):
    doc = fitz.open(str(path))
    try:
        page = doc[0]
        return (page.get_text(),
                [a.type[1] for a in page.annots()])
    finally:
        doc.close()


def test_every_1d_gets_the_highlight_and_the_drop_blank(rs, tmp_path):
    src = _one_d(tmp_path / "in.pdf", "HSS 2.0 X 2.0 X 0.188 NOM")
    dest = tmp_path / "out.pdf"
    added = rs.annotate(src, dest, {"estimated": False, "from_batch": None},
                        False, lambda *_a: None)
    text, annots = _added(dest)
    assert "Highlight" in annots
    assert "drop:" in text
    assert "DROP FROM BATCH" not in text, "a fresh stick gets no drop note"
    assert "pre-cut" not in text, "only a saw sheet gets that blank"
    assert added == ["highlight", "drop blank"]


def test_an_estimated_bar_gets_the_arrow_and_the_batch_it_came_from(rs,
                                                                    tmp_path):
    src = _one_d(tmp_path / "in.pdf", "HSS 3.5 X 3.5 X 0.25 NOM")
    dest = tmp_path / "out.pdf"
    rs.annotate(src, dest, {"estimated": True, "from_batch": "507"}, False,
                lambda *_a: None)
    text, annots = _added(dest)
    assert "DROP FROM BATCH 507 (ESTIMATED)" in text
    assert "Line" in annots, "the arrow back to the bar length"


def test_a_saw_sheet_also_gets_the_pre_cut_blank(rs, tmp_path):
    src = _one_d(tmp_path / "in.pdf", "HSS 6.0 X 6.0 X 0.50 NOM (SAW CUT)")
    dest = tmp_path / "out.pdf"
    rs.annotate(src, dest, {"estimated": True, "from_batch": "507"}, True,
                lambda *_a: None)
    text, _annots = _added(dest)
    assert "pre-cut bar length:" in text
    assert "drop :" in text


def test_nothing_runs_off_the_right_edge(rs, tmp_path):
    """Her saw blanks end at x=546 of 612; ours must stay on the paper too."""
    src = _one_d(tmp_path / "in.pdf", "HSS 6.0 X 6.0 X 0.50 NOM (SAW CUT)")
    dest = tmp_path / "out.pdf"
    rs.annotate(src, dest, {"estimated": True, "from_batch": "507"}, True,
                lambda *_a: None)
    doc = fitz.open(str(dest))
    try:
        right = max(w[2] for w in doc[0].get_text("words"))
    finally:
        doc.close()
    assert right <= 612, f"something is off the page at x={right}"


# ────────────────────────────────────────────────────── the cover page

def _cover_rows(path):
    xml = zipfile.ZipFile(str(path)).read("word/document.xml").decode("utf-8")
    table = re.search(r"<w:tbl>.*?</w:tbl>", xml, re.S).group(0)
    out = []
    for row in re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S):
        cells = []
        for cell in re.findall(r"<w:tc>.*?</w:tc>", row, re.S):
            fill = re.search(r'w:shd [^/]*?w:fill="([0-9A-F]{6})"', cell)
            cells.append((re.sub(r"<[^>]+>", "", cell).strip(),
                          fill.group(1) if fill else None))
        out.append(cells)
    return xml, out


def test_the_cover_table_is_built_from_the_organizer(rs, tmp_path):
    """Pallet 1 of batch 508, exactly as her `_1.pdf` reads."""
    listing = [("BM338238", "6.0 X 6.0 X 0.50 NOM"),
               ("X7454801", "4.0 X 4.0 X 0.375 NOM"),
               ("X8355524", "3.5 X 3.5 X 0.25 NOM"),
               ("BL427270", "3.0 X 3.0 X 0.25 NOM")]
    materials = ["HSS 6.0 X 6.0 X 0.50 NOM (SAW CUT)",
                 "HSS 4.0 X 4.0 X 0.375 NOM (SAW CUT)",
                 "HSS 3.5 X 3.5 X 0.25 NOM",
                 "HSS 3.0 X 3.0 X 0.25 NOM"]
    dest = tmp_path / "cover.docx"
    rs.fill_docx(PDIR / "templates" / rs.TEMPLATE_LASER, dest, 508,
                 "PALLET 1", listing, materials, [])
    xml, rows = _cover_rows(dest)

    assert rows[0][0] == ("PALLET 1", rs.FILL_TITLE)
    body = rows[2:2 + len(listing)]
    assert [c[0][0] for c in body] == [o for o, _m in listing]

    # yellow marks an order whose material is saw cut - and only those
    yellow = [c[0][0] for c in body if c[0][1] == rs.FILL_SAW_ORDER]
    assert yellow == ["BM338238", "X7454801"]

    # the material column bands every other material GROUP
    assert body[1][1][1] == rs.FILL_BAND, "material 2 is a banded group"
    assert body[0][1][1] is None, "material 1 is not"

    head = next(r for r in rows if r[0][0].startswith("MATERIAL REQUIRED"))
    assert head[0] == (f"MATERIAL REQUIRED: {len(materials)}", rs.FILL_TITLE)
    mats = rows[rows.index(head) + 1:]
    assert [c[1][0] for c in mats] == materials
    assert [c[0][1] for c in mats] == [rs.FILL_SAW_MAT, rs.FILL_SAW_MAT,
                                       None, None], "grey = saw cut"
    assert "BATCH 508" in re.sub(r"<[^>]+>", "", xml)


def test_only_the_saw_cover_carries_the_sign_off_lines(rs, tmp_path):
    listing = [("BM338238", "6.0 X 6.0 X 0.50 NOM")]
    materials = ["HSS 6.0 X 6.0 X 0.50 NOM (SAW CUT)"]
    saw = tmp_path / "saw.docx"
    rs.fill_docx(PDIR / "templates" / rs.TEMPLATE_SAW, saw, 508, "PALLET 1",
                 listing, materials, ["HSS 6.0 X 6.0 X 0.50 NOM"])
    text = re.sub(r"<[^>]+>", "",
                  zipfile.ZipFile(str(saw)).read("word/document.xml")
                  .decode("utf-8"))
    assert "USED: HSS 6.0 X 6.0 X 0.50 NOM - TAG: _" in text
    assert "DROP LENGTH: _" in text

    plain = tmp_path / "laser.docx"
    rs.fill_docx(PDIR / "templates" / rs.TEMPLATE_LASER, plain, 508,
                 "PALLET 2", listing, materials, [])
    assert "USED:" not in re.sub(
        r"<[^>]+>", "",
        zipfile.ZipFile(str(plain)).read("word/document.xml").decode("utf-8"))


def test_the_shipped_templates_carry_no_batch_s_data(rs):
    """They are TEMPLATES. A stale `USED:` line in one would print on every
    batch's saw cover on top of the real ones."""
    for name in (rs.TEMPLATE_LASER, rs.TEMPLATE_SAW):
        path = PDIR / "templates" / name
        assert path.is_file(), f"{name} must ship with the plugin"
        text = re.sub(r"<[^>]+>", "",
                      zipfile.ZipFile(str(path)).read("word/document.xml")
                      .decode("utf-8"))
        assert "USED:" not in text


# ──────────────────────────────────────────────── matching and ordering

def test_a_1d_is_matched_by_its_name(rs, tmp_path):
    packets = {"1.1": {"material": "HSS 3.5 X 3.5 X 0.25 NOM"},
               "SAW.2": {"material": "HSS 4.0 X 4.0 X 0.375 NOM"}}
    for stem in ("1.1", "SAW.2"):
        _one_d(tmp_path / f"{stem}.pdf", packets[stem]["material"])
    found = rs.match_1ds(tmp_path, packets, lambda *_a: None)
    assert sorted(found) == ["1.1", "SAW.2"]


def test_a_renamed_1d_is_matched_on_its_material_line(rs, tmp_path):
    packets = {"1.1": {"material": "HSS 3.5 X 3.5 X 0.25 NOM"}}
    _one_d(tmp_path / "nest run final.pdf", "HSS 3.5 X 3.5 X 0.25 NOM")
    said = []
    found = rs.match_1ds(tmp_path, packets, said.append)
    assert found["1.1"].name == "nest run final.pdf"
    assert any("by its material line" in m for m in said), said


def test_a_packet_with_no_1d_is_named(rs, tmp_path):
    packets = {"2.3": {"material": "HSS 2.0 X 2.0 X 0.188 NOM"}}
    said = []
    assert rs.match_1ds(tmp_path, packets, said.append) == {}
    assert any("no 1D for packet 2.3" in m for m in said), said


def test_packets_sort_by_number_not_by_text(rs):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_sort", PDIR / "run.py")
    assert spec is not None and spec.loader is not None
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    order = sorted(["2.10", "2.9", "2.1", "SAW.2", "SAW.10"],
                   key=run._packet_sort)
    assert order == ["2.1", "2.9", "2.10", "SAW.2", "SAW.10"]
