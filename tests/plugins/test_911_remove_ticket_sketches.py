"""911 Remove Ticket v1.3.0 - PART SKETCH pages whose graphic did not render are
filled from the batch's OWN WPDD SKETCHES folder (invoicing's asks 2026-09-04 +
09-14, her answers 2026-09-17). Single home; 911 Setup calls the same function.

Pins:
  - the batch's sketch folder is found by SKETCH/WPDD in a DIRECT child's name;
    another batch's folder is never consulted, even with the DYPN in it;
  - files are ORDER_DYPN_view.jpg; every view of the part comes in - view 1 onto
    the broken page, views 2+ as inserted pages right after it, captioned;
  - the page's own work-order label narrows same-DYPN files to that order;
  - the .jpgs used are copied into {batch}\\{nest}\\Sketches\\ (only when the
    nest folder exists);
  - a broken page with no sketch on file is reported, not touched; a page whose
    graphic is fine is never touched;
  - the whole thing runs inside _process_pdf (Remove Ticket's own path).
"""
import importlib.util
from pathlib import Path

import fitz
import pytest
from PIL import Image

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_remove_ticket" / "run.py")

MISSING = "The resource of this report item is not reachable."


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("sp_911_remove_ticket", PLUGIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _jpg(path: Path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), color).save(path, "JPEG")
    return path


def _sketch_page(doc, part, order="FK394334", nest="X504050S", broken=True,
                 move_ticket=False):
    page = doc.new_page(width=792, height=612)
    y = 60
    lines = ["MOVE TICKET"] if move_ticket else ["PART SKETCH"]
    lines += [order, f"PART: {part}", "NOUN: CHANNEL", nest, "1"]
    if broken:
        lines.append(MISSING)
    for line in lines:
        page.insert_text((40, y), line, fontsize=10)
        y += 18
    if not broken and not move_ticket:
        # a real drawing: an image on the page
        page.insert_image(fitz.Rect(40, 200, 400, 500), stream=_png_bytes())
    return page


def _png_bytes():
    import io
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "blue").save(buf, "PNG")
    return buf.getvalue()


def _batch(tmp_path, name="V101", sketch_dir="WPDD SKETCHES - COMPLETE"):
    b = tmp_path / name
    (b / "NEST PACKAGES").mkdir(parents=True)
    (b / sketch_dir).mkdir()
    return b


# ---------------------------------------------------------------------------------
def test_folder_lookup_is_the_batch_only(mod, tmp_path):
    b = _batch(tmp_path)
    (b / "DTSV FILES").mkdir()
    assert mod.find_sketch_folder(b) == b / "WPDD SKETCHES - COMPLETE"
    assert mod.find_sketch_folder(b / "NEST PACKAGES") is None
    assert mod.find_sketch_folder(tmp_path / "nope") is None
    # picked folder = NEST PACKAGES -> its parent is the batch; a lone folder -> None
    assert mod.sketch_batch_folder_for(b / "NEST PACKAGES") == b
    assert mod.sketch_batch_folder_for(tmp_path / "loose") is None


def test_index_parses_order_dypn_view_and_skips_strays(mod, tmp_path):
    b = _batch(tmp_path)
    sk = b / "WPDD SKETCHES - COMPLETE"
    _jpg(sk / "FK394334_SQBH5016-1-6_2.jpg", "red")
    _jpg(sk / "FK394334_SQBH5016-1-6_1.jpg", "green")
    _jpg(sk / "FK394399_H6921805-39_1.JPG", "blue")
    (sk / "WJ129- 911 OFFLOAD.pdf").write_bytes(b"%PDF")
    idx = mod.index_sketch_files(sk)
    assert [v for _, v, _ in idx["SQBH5016-1-6"]] == [1, 2]
    assert idx["H6921805-39"][0][0] == "FK394399"
    assert len(idx) == 2


def test_broken_page_gets_every_view_and_the_jpgs_are_copied(mod, tmp_path):
    b = _batch(tmp_path)
    (b / "504050").mkdir()
    sk = b / "WPDD SKETCHES - COMPLETE"
    v1 = _jpg(sk / "FK394334_SQBH5016-1-6_1.jpg", "red")
    v2 = _jpg(sk / "FK394334_SQBH5016-1-6_2.jpg", "green")
    doc = fitz.open()
    _sketch_page(doc, "OTHER-1", broken=False)          # page 1: fine, untouched
    _sketch_page(doc, "SQBH5016-1-6")                   # page 2: broken
    _sketch_page(doc, "OTHER-2", broken=False)          # page 3: fine
    logs = []
    res = mod.restore_missing_sketches(doc, b, "504050", logs.append)

    assert res.restored == ["SQBH5016-1-6 (2 views)"] and res.unmatched == []
    assert res.pages_added == 1 and len(doc) == 4
    # view 1 drawn onto the broken page, view 2 on the page right after it
    assert len(doc[1].get_images()) == 1
    assert "Sketch view 1 of 2 added by TechDeck from WPDD SKETCHES - COMPLETE\\" \
           + v1.name in doc[1].get_text()
    assert "PART SKETCH - PART: SQBH5016-1-6 - view 2 of 2" in doc[2].get_text()
    assert v2.name in doc[2].get_text() and len(doc[2].get_images()) == 1
    # the good pages kept their place and were not touched
    assert "PART: OTHER-1" in doc[0].get_text() and "added by TechDeck" not in doc[0].get_text()
    assert "PART: OTHER-2" in doc[3].get_text()
    # copies for quick reference
    assert sorted(p.name for p in (b / "504050" / "Sketches").iterdir()) == [v1.name, v2.name]
    assert res.copied == 2
    # second run: nothing re-copied
    doc2 = fitz.open(); _sketch_page(doc2, "SQBH5016-1-6")
    assert mod.restore_missing_sketches(doc2, b, "504050", logs.append).copied == 0


def test_only_this_batch_is_searched(mod, tmp_path):
    b = _batch(tmp_path, "V101")
    other = _batch(tmp_path, "V100")
    _jpg(other / "WPDD SKETCHES - COMPLETE" / "FK111111_SQBH5016-1-6_1.jpg", "red")
    doc = fitz.open(); _sketch_page(doc, "SQBH5016-1-6")
    logs = []
    res = mod.restore_missing_sketches(doc, b, "504050", logs.append)
    assert res.restored == [] and res.unmatched == ["SQBH5016-1-6"]
    assert len(doc) == 1 and doc[0].get_images() == []
    assert not (b / "504050" / "Sketches").exists()
    assert any("no SQBH5016-1-6 sketch" in l for l in logs)


def test_no_sketch_folder_reports_every_broken_page(mod, tmp_path):
    b = tmp_path / "V101"; (b / "NEST PACKAGES").mkdir(parents=True)
    doc = fitz.open(); _sketch_page(doc, "A-1"); _sketch_page(doc, "B-2")
    res = mod.restore_missing_sketches(doc, b, "504050", lambda *_: None)
    assert res.unmatched == ["A-1", "B-2"] and res.sketch_folder is None and len(doc) == 2


def test_work_order_label_on_the_page_picks_the_right_file(mod, tmp_path):
    b = _batch(tmp_path)
    sk = b / "WPDD SKETCHES - COMPLETE"
    _jpg(sk / "FK111111_SQBH5016-1-6_1.jpg", "red")      # same DYPN, other order
    right = _jpg(sk / "FK394334_SQBH5016-1-6_1.jpg", "green")
    doc = fitz.open(); _sketch_page(doc, "SQBH5016-1-6", order="FK394334")
    res = mod.restore_missing_sketches(doc, b, "504050", lambda *_: None)
    assert res.restored == ["SQBH5016-1-6 (1 view)"] and len(doc) == 1
    assert right.name in doc[0].get_text() and "FK111111" not in doc[0].get_text()


def test_process_pdf_restores_sketches_and_reports_unmatched(mod, tmp_path):
    b = _batch(tmp_path)
    (b / "504050").mkdir()
    _jpg(b / "WPDD SKETCHES - COMPLETE" / "FK394334_SQBH5016-1-6_1.jpg", "red")
    doc = fitz.open()
    _sketch_page(doc, "-", move_ticket=True)             # removed by the plugin
    _sketch_page(doc, "SQBH5016-1-6")                    # fixed
    _sketch_page(doc, "NOFILE-9")                        # reported
    src = b / "NEST PACKAGES" / "504050.pdf"; doc.save(src); doc.close()
    out = b / "NEST PACKAGES" / "Move Ticket Omit" / "504050 Move Ticket Omit.pdf"
    out.parent.mkdir()
    logs = []
    ok, warnings = mod._process_pdf(src, out, "V101", logs.append, None, None,
                                    sketch_batch_folder=b)
    assert ok
    assert any("no sketch on file for: NOFILE-9" in w for w in warnings)
    result = fitz.open(out)
    assert len(result) == 2 and len(result[0].get_images()) == 1
    assert "added by TechDeck" in result[0].get_text()
    assert (b / "504050" / "Sketches" / "FK394334_SQBH5016-1-6_1.jpg").exists()
    assert any("1 sketch graphic(s) restored" in l for l in logs)
