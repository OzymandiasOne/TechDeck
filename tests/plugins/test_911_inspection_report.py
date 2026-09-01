"""What the 911 Inspection Dimensions report puts in front of an inspector.

The report IS this app's output - somebody works down it with the drawing in
hand - so its shape is a contract, not cosmetics. It leads with the things that
need a human, and everything else answers "what went on my sheet" or "what was
left off and why".

Also covers sdk.show_report's two paths: with a console the report goes on
screen and NOTHING is written; headless it writes the file itself, so a run can
never lose its output.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_inspection_dimensions" / "run.py")


@pytest.fixture(scope="module")
def rt():
    spec = importlib.util.spec_from_file_location("rt_911_inspection_report", PLUGIN)
    assert spec and spec.loader, f"cannot load the plugin at {PLUGIN}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dim(kind, value, ref=False, mods=(), score=1.0):
    return {"kind": kind, "value": value, "ref": ref, "mods": list(mods),
            "score": score, "bb": (0, 0, 1, 1), "raw": value}


def _part(part="H4524567-201", tab="67-201", dims=None, welds=(), misreads=(),
          problem="", values=(27.75, 22.25)):
    rec = {"part": part, "page": 3, "views": 0, "problem": problem, "notes": [],
           "misreads": list(misreads), "welds": list(welds),
           "dims": dims if dims is not None else [_dim("linear", "27.75")]}
    if values and not problem:
        rec["filled"] = {"tab": tab, "values": list(values)}
    return rec


def _report(rt, parts, fills=(), elapsed=10.0, failures=None):
    return rt.build_report(r"C:\x\503891", [("packet.pdf", parts)],
                           list(fills), elapsed, failures)


# ------------------------------------------------- the action list comes first

def test_check_section_is_above_the_numbers(rt):
    text = _report(rt, [_part()])
    assert text.index("CHECK THESE FIRST") < text.index("WHAT WENT ON EACH SHEET")


def test_a_low_confidence_reading_is_called_out(rt):
    text = _report(rt, [_part(dims=[_dim("linear", ".50", score=0.42)])])
    assert "the reader was unsure" in text


def test_a_confident_reading_is_not_called_out(rt):
    text = _report(rt, [_part(dims=[_dim("linear", ".50", score=0.99)])])
    assert "CHECK THESE FIRST   (none)" in text


def test_a_binned_misread_is_shown_with_the_likely_repair(rt):
    """The safety net on the strict-length rule: it must never vanish silently."""
    text = _report(rt, [_part(misreads=[rt.misread_compound("78X68.7\u00b0")])])
    # the reason is wrapped to the column width, so compare on collapsed text
    flat = " ".join(text.split())
    assert "78 X 68.7 deg" in flat
    assert '".78 X 68.7 deg"' in flat
    assert "misread" in flat


def test_a_hand_typed_tolerance_is_called_out(rt):
    """Writing a nominal next to somebody's hand-typed min/max is worse than not."""
    fills = [("wb", "p", [{"tab": "-305", "part": "P", "written": 3,
                           "status": "filled 3", "stale": ["AB16"]}])]
    text = _report(rt, [_part()], fills)
    assert "cell AB16" in text
    assert "typed in by hand" in text


def test_an_unreadable_pdf_says_why(rt):
    text = rt.build_report(r"C:\x", [("packet.pdf", [])], [], 1.0,
                           {"packet.pdf": "the drawing reader could not start up"})
    assert "could not start up" in text


# ---------------------------------------------------------------- the numbers

def test_the_values_written_are_listed_under_their_tab(rt):
    text = _report(rt, [_part(tab="67-201", values=(27.75, 22.25, "45\u00b0"))])
    assert "67-201" in text
    assert "27.75" in text and "45\u00b0" in text


def test_a_weld_prep_says_where_its_angle_came_from(rt):
    """An inspector seeing a 45 on the sheet must be able to trace it."""
    text = _report(rt, [_part(welds=[{"code": "KB114", "side": "", "score": 0.9}])])
    assert "weld prep" in text and "KB114" in text


def test_typ_guidance_appears_only_when_there_is_a_typ(rt):
    plain = _report(rt, [_part(dims=[_dim("linear", "1.00")])])
    assert "TYP values sit LAST" not in plain
    typ = _report(rt, [_part(dims=[_dim("linear", "1.00", mods=["TYP"])])])
    assert "TYP values sit LAST" in typ


# ------------------------------------------------------------ the fat is gone

def test_drawing_notes_are_not_printed(rt):
    """OCR's reading of the drawing's own notes was noise to an inspector."""
    rec = _part()
    rec["notes"] = ["001AV - H4524567-201 F0RMED VIEW - T0P HIGH STR STEEL ANGLE"]
    assert "F0RMED VIEW" not in _report(rt, [rec])


def test_title_block_fields_the_sheet_already_carries_are_not_repeated(rt):
    rec = _part()
    rec.update({"work_order": "X5588573", "rev": "B/01", "qty": "1",
                "noun": "ANGLE", "size": "2.000 X 2.000", "fab_dim": "27.75"})
    text = _report(rt, [rec])
    assert "X5588573" not in text
    assert "Rev/Seq" not in text and "FAB DIM" not in text


def test_ref_dimensions_are_listed_but_not_as_an_action(rt):
    text = _report(rt, [_part(dims=[_dim("linear", "27.75"),
                                    _dim("linear", "2.00", ref=True)])])
    assert "NOT INSPECTED" in text
    assert text.index("CHECK THESE FIRST") < text.index("NOT INSPECTED")


# ------------------------------------------------------- sdk.show_report paths

def test_show_report_with_a_console_writes_nothing(tmp_path):
    """Saving is the reader's choice once it is on screen."""
    from techdeck.core import plugin_sdk as sdk

    shown = []

    class Console:
        def show_report(self, *args):
            shown.append(args)

    target = tmp_path / "report.txt"
    note = sdk.show_report({"console": Console()}, "T", "S", "BODY", str(target))
    assert len(shown) == 1
    assert not target.exists()
    assert "Save as .txt" in note


def test_show_report_headless_writes_the_file(tmp_path):
    """No console (or an older TechDeck) must never lose the run's output."""
    from techdeck.core import plugin_sdk as sdk

    target = tmp_path / "report.txt"
    note = sdk.show_report({"log": lambda *_: None}, "T", "S", "BODY", str(target))
    assert target.read_text(encoding="utf-8") == "BODY"
    assert str(target) in note


def test_show_report_falls_back_to_the_log_with_no_path():
    from techdeck.core import plugin_sdk as sdk

    logged = []
    sdk.show_report({"log": logged.append}, "T", "S", "BODY", "")
    assert logged == ["BODY"]
