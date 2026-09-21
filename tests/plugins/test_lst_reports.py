"""The shared color-coded PDF report (sdk.ReportPdf) and the 911 LST
Organizer's use of it.

The layout helper was promoted out of the 922 LST Organizer on 2026-09-21 so
the 911 organizer (and the 902 Part Validator) draw the same report. These
tests pin the things a reader depends on: the report lands where it was asked
to, every attention section names its parts, a clean run says so, and a long
report page-breaks instead of running off the sheet.
"""

import importlib.util
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from techdeck.core import plugin_sdk as sdk

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def _load(plugin_id):
    spec = importlib.util.spec_from_file_location(
        f"{plugin_id}_run", PLUGINS / plugin_id / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lst911():
    return _load("911_lst_organizer")


def _text(pdf_path):
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc), doc.page_count
    finally:
        doc.close()


INFO = {"pdf": "S035 503874 1D.pdf", "batch": "S035", "nest": "503874"}


def test_report_pdf_creates_parent_and_page_breaks(tmp_path):
    out = tmp_path / "made" / "by" / "save" / "r.pdf"
    d = sdk.ReportPdf()
    d.text("TITLE", size=17, bold=True)
    d.header_row(["A", "B"], [200, 200])
    for i in range(120):
        d.row([f"row {i}", "x" * 400], [200, 200])   # long cell must clip
    d.save(out)
    text, pages = _text(out)
    assert pages >= 3
    assert "row 0" in text and "row 119" in text
    assert "x" * 400 not in text                      # clipped to the column


def test_report_pdf_wrap_keeps_the_whole_sentence(tmp_path):
    long = "DXF: the file is blank; IGES: corrupt - lines lost: says 14 directory lines, has 13"
    clipped, wrapped = sdk.ReportPdf(), sdk.ReportPdf()
    clipped.row(["H1-1", long], [140, 160])
    wrapped.row(["H1-1", long], [140, 160], wrap=True)
    assert wrapped.y > clipped.y                       # the row grew to fit
    clipped.save(tmp_path / "c.pdf"); wrapped.save(tmp_path / "w.pdf")
    flat = lambda t: " ".join(t.split())
    assert "has 13" not in flat(_text(tmp_path / "c.pdf")[0])
    assert long in flat(_text(tmp_path / "w.pdf")[0])


def test_report_pdf_new_page(tmp_path):
    d = sdk.ReportPdf()
    d.new_page()                                        # untouched page: no-op
    d.text("page one")
    d.new_page()
    d.text("page two")
    d.save(tmp_path / "p.pdf")
    doc = fitz.open(tmp_path / "p.pdf")
    pages = [pg.get_text() for pg in doc]
    doc.close()
    assert len(pages) == 2 and "page two" in pages[1] and "page two" not in pages[0]


def test_911_report_names_every_problem(lst911, tmp_path):
    rows = [
        ("H4143481-3", "503874", "S035", ["H4143481-3A_P_Tube1.lst"], "H4143481-3A"),
        ("H4143481-4", "503874", "S035", None, None),
        ("H4112842-34", "503887", "S036", ["H4112842-34.lst"], None),
    ]
    out = tmp_path / "LST Report - S035 503874.pdf"
    lst911._write_report(out, INFO, rows, {"503750": ["H4130401-22M"]}, 2,
                         ["Failed to copy X.lst: locked"])
    text, _pages = _text(out)
    assert "911 LST Organizer" in text and "S035 503874" in text
    assert "MISSING" in text and "H4143481-4" in text          # missing part named
    assert "NEST NOT FOUND" in text and "H4130401-22M" in text  # unresolved nest's part
    assert "MATCHED BY REVISION LETTER" in text and "H4143481-3A" in text
    assert "COPY PROBLEMS" in text and "Failed to copy X.lst" in text
    assert "Nest 503887" in text and "H4112842-34.lst" in text  # pull list by nest
    assert "Every part on the diagram" not in text


def test_911_report_clean_run_says_so(lst911, tmp_path):
    rows = [("H4143481-3", "503874", "S035", ["H4143481-3.lst"], None)]
    out = tmp_path / "clean.pdf"
    lst911._write_report(out, INFO, rows, {}, 1, [])
    text, _pages = _text(out)
    assert "Every part on the diagram has its .lst." in text
    for heading in ("NEST NOT FOUND", "COPY PROBLEMS", "MATCHED BY REVISION LETTER"):
        assert heading not in text


def test_922_organizer_draws_with_the_shared_helper():
    lst922 = _load("922_lst_organizer")
    assert lst922._Pdf is sdk.ReportPdf


class _Console:
    def __init__(self, accepts):
        self.accepts, self.calls = accepts, []

    def append_link(self, text, target, **kw):
        if set(kw) - self.accepts:
            raise TypeError("unexpected keyword")
        self.calls.append((text, target, kw))


@pytest.mark.parametrize("accepts,want_text", [
    ({"prefix", "at_run_end"}, "Open it"),
    ({"prefix"}, "Open it"),
    (set(), "[REPORT] Open it"),          # oldest console: prefix folded in
])
def test_link_output_degrades_across_console_versions(accepts, want_text):
    con = _Console(accepts)
    sdk.link_output({"console": con, "log": lambda *_: None},
                    "Open it", "C:/x/report.pdf", prefix="[REPORT]")
    assert len(con.calls) == 1
    assert con.calls[0][0] == want_text


def test_link_output_headless_logs_the_path():
    lines = []
    sdk.link_output({"log": lines.append}, "Open it", "C:/x/report.pdf")
    assert lines == ["Open it: C:/x/report.pdf"]
