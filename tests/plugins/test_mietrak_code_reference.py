"""MieTrak Tools - the Code Reference tool: decoder + rendered sheet.

The generator answers "what code do I need?"; this half answers "what IS this
code?" and "what are my choices?". Both are pure functions, so they test
headless - no Qt, no window.

The decoder is the round trip of ``build_hardware_code``, so these also guard
the assembly rule from the other direction: anything the generator can build,
the decoder must read back.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "mietrak_tools" / "run.py")


@pytest.fixture(scope="module")
def mt():
    spec = importlib.util.spec_from_file_location("mietrak_tools_run", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _by_role(segments):
    return {seg.role: seg for seg in segments}


# -- decoding ----------------------------------------------------------------

def test_decodes_a_set_screw(mt):
    segments, system, problem = mt.decode_hardware_code("HW188-SETSCR-1024-C")
    assert (system, problem) == ("IMPERIAL", "")
    seen = _by_role(segments)
    assert seen["material"].meanings == ["18-8 STAINLESS STEEL"]
    assert seen["hardware"].meanings == ["SET SCREW"]
    assert seen["thread"].meanings == ["10-24"]
    assert seen["length"].meanings == ['3/16"']


def test_decodes_a_metric_stud(mt):
    segments, system, problem = mt.decode_hardware_code("HW304-STUD-M10150-40")
    assert (system, problem) == ("METRIC", "")
    seen = _by_role(segments)
    assert seen["thread"].meanings == ["M10x1.5"]
    assert seen["length"].meanings == ["40mm"]


def test_nut_decodes_with_no_length(mt):
    segments, _system, problem = mt.decode_hardware_code("HW304-HNUT-M10150")
    assert problem == ""
    assert "length" not in _by_role(segments)


def test_washer_decodes_a_screw_size_not_a_thread(mt):
    segments, _system, problem = mt.decode_hardware_code("HWG-FWSH-F")
    assert problem == ""
    seen = _by_role(segments)
    assert "thread" not in seen
    assert seen["screw"].meanings == ['3/8"']


def test_washer_gauge_size_keeps_its_hash_and_gains_no_inch_mark(mt):
    """#6 is a gauge, not a fraction of an inch - it must not become 6"."""
    segments, _system, _problem = mt.decode_hardware_code("HWG-FWSH-6")
    assert _by_role(segments)["screw"].meanings == ["#6"]


def test_the_f16_collision_reports_both_threads(mt):
    """1/4-20 and 3/8-16 share F16 in the original program. The whole point of
    a reference is that it SAYS so rather than silently picking one."""
    segments, _system, _problem = mt.decode_hardware_code("HWZP5-HHCS-F16-2")
    assert _by_role(segments)["thread"].meanings == ["1/4-20", "3/8-16"]


def test_lower_case_and_whitespace_are_accepted(mt):
    segments, _system, problem = mt.decode_hardware_code("  hw188-setscr-1024-c ")
    assert problem == ""
    assert _by_role(segments)["material"].meanings == ["18-8 STAINLESS STEEL"]


# -- decoding what a user actually pastes ------------------------------------

def test_a_code_that_is_not_one_says_so_and_does_not_raise(mt):
    segments, system, problem = mt.decode_hardware_code("NONSENSE")
    assert (segments, system) == ([], "")
    assert "HW" in problem


def test_empty_input_is_silent(mt):
    assert mt.decode_hardware_code("") == ([], "", "")


def test_unknown_piece_is_flagged_but_the_rest_still_decodes(mt):
    segments, _system, problem = mt.decode_hardware_code("HWXX-HHCS-H13-2")
    assert "XX" in problem
    seen = _by_role(segments)
    assert seen["material"].meanings == []        # the bad piece
    assert seen["hardware"].meanings == ["CAP SCREW, HEX HEAD"]   # the rest reads


def test_unknown_hardware_type_still_reads_the_rest(mt):
    segments, _system, problem = mt.decode_hardware_code("HW188-BLERG-1024-C")
    assert "BLERG" in problem
    assert _by_role(segments)["material"].meanings == ["18-8 STAINLESS STEEL"]


def test_a_missing_piece_names_what_is_missing(mt):
    _segments, _system, problem = mt.decode_hardware_code("HWB-HHCS-H13")
    assert "length" in problem.lower()


def test_too_many_pieces_is_reported(mt):
    _segments, _system, problem = mt.decode_hardware_code("HWB-HHCS-H13-2-9")
    assert "more pieces" in problem


# -- the round trip: anything the generator builds, the decoder reads ---------

@pytest.mark.parametrize("system", ["IMPERIAL", "METRIC"])
def test_every_generated_code_decodes_cleanly(mt, system):
    """Walk every material x type x size the generator offers and assert the
    decoder reads it back with no complaint. This is the guard that keeps the
    two halves from drifting when a table gains a row."""
    for material_label, material in mt.MATERIAL_OPTIONS:
        for hardware_label, hardware in mt.HARDWARE_OPTIONS:
            kwargs = {}
            for role in mt.hardware_fields_needed(hardware):
                kwargs["%s_code" % role] = mt.ROLE_TABLES[role][system][0][1]
            code = mt.build_hardware_code(material, hardware, **kwargs)
            _segments, got_system, problem = mt.decode_hardware_code(code)
            assert problem == "", (code, material_label, hardware_label, problem)
            assert got_system == system, (code, got_system)


# -- the rendered sheet ------------------------------------------------------

def test_anatomy_names_every_piece_of_a_code(mt):
    html = mt.anatomy_html()
    for piece in ("HW", "188", "SETSCR", "1024", "Material", "Thread", "Length"):
        assert piece in html
    # The rows-per-type rule and the suffix scheme are the two things a user
    # cannot work out from the generator alone.
    assert "A nut has no length" in html
    assert "threads per inch" in html


def test_tables_cover_every_option_for_the_system(mt):
    for system in mt.SYSTEMS:
        html = mt.tables_html(system)
        for table in (mt.MATERIAL_OPTIONS, mt.HARDWARE_OPTIONS,
                      mt.THREAD_OPTIONS[system], mt.LENGTH_OPTIONS[system],
                      mt.SCREW_OPTIONS[system]):
            for _label, value in table:
                assert ">%s<" % value in html, (system, value)


def test_the_f16_caveat_rides_with_the_imperial_thread_table(mt):
    assert "F16" in mt.tables_html("IMPERIAL")
    assert "hardware buyer" in mt.tables_html("IMPERIAL")
    assert "hardware buyer" not in mt.tables_html("METRIC")


def test_the_filter_narrows_and_reports_an_empty_result(mt):
    narrowed = mt.tables_html("IMPERIAL", "washer")
    assert "WASHER, FLAT" in narrowed
    assert "18-8 STAINLESS STEEL" not in narrowed
    assert "matches" in mt.tables_html("IMPERIAL", "zzzz")


def test_the_filter_matches_the_code_as_well_as_the_name(mt):
    assert "SET SCREW" in mt.tables_html("IMPERIAL", "setscr")


def test_decode_html_is_safe_for_whatever_gets_pasted(mt):
    """The box takes free text, so a stray angle bracket must not become markup."""
    html = mt.decode_html("HW<script>-HHCS-H13-2")     # codes are upper-cased
    assert "<script>" not in html.lower()
    assert "&lt;script&gt;" in html.lower()


def test_breakdown_reads_the_generated_code_back(mt):
    html = mt.breakdown_html("HW188-SETSCR-1024-C")
    assert "18-8 STAINLESS STEEL" in html
    assert "10-24" in html
    assert "Code Reference" in html          # the pointer to the full chart
    assert mt.breakdown_html("nonsense") == ""
