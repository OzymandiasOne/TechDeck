"""911 LST Organizer: 1D 'Parts Id.' token classification.

The fixtures are REAL lines off 'S036 503887 & S029 503750 1D.pdf'
(CDAUGHAN-LT, 2026-08-21): the nesting software now prefixes every part with
its nest as '503887 / H4112842-34' (slash, spaces) — on MULTIPLE ORDERS
diagrams AND new single-order ones. The old classifier split on the first
hyphen, which lands inside the part number, so those diagrams parsed as ZERO
parts and the run died with "No part ids found". These tests pin the slash
form down alongside the two legacy hyphen forms and the bare-part form,
without letting header/footer junk through.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def lst911():
    spec = importlib.util.spec_from_file_location(
        "lst911_run", PLUGINS / "911_lst_organizer" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NEST = "503887"


@pytest.mark.parametrize("token,want", [
    # Bare part = current nest (the original single-order layout).
    ("H4143481-3", (NEST, "H4143481-3")),
    ("H5532004-19-2", (NEST, "H5532004-19-2")),
    # Legacy hyphen prefixes (with and without whitespace).
    ("503874-H4143481-3", ("503874", "H4143481-3")),
    ("503874- H4143481-3", ("503874", "H4143481-3")),
    ("503874 - H4143481-3", ("503874", "H4143481-3")),
    # The 2026-08 slash form, exactly as the S036/S029 diagram renders it.
    ("503887 / H4112842-34", ("503887", "H4112842-34")),
    ("503750 / H4533301-11", ("503750", "H4533301-11")),
    ("503750 / H5410298-13-3", ("503750", "H5410298-13-3")),
    ("503887/H4136053-112", ("503887", "H4136053-112")),
    # Lowercase input still classifies (PDF text case can drift).
    ("503887 / h4112842-34", ("503887", "H4112842-34")),
])
def test_part_tokens_classify(lst911, token, want):
    assert lst911._classify_token(token, NEST) == want


@pytest.mark.parametrize("junk", [
    # Real non-part lines from the same PDF.
    "MULTIPLE ORDERS: S036 503887",
    "S029 503750",
    "BATCH S036 NEST 503887 / BATCH S029 NEST 503750",
    "HSS 2.5 X 2.5 X 0.25 THK TUBE (TUBE LASER)",
    "Cut From Bars :   218019939         Bar Length :   240",
    "Total Bars  (218019939    L=240) : 3",
    "Date & Time : 8/3/2026 7:52:31 AM",
    "TAGS TO USE: 41842R, 41843R, 41844R",
    "( B01 ) :",
    "62.13",
    "17.67",
    "8/3/2026",
    "Parts Id.",
    "Qt. Tot.",
    "",
])
def test_junk_lines_are_ignored(lst911, junk):
    assert lst911._classify_token(junk, NEST) is None
