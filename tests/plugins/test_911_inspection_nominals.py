"""Regression tests for what 911 Inspection Dimensions types into a TARGET cell.

The inspection sheet's MIN/MAX are array formulas that pick their own tolerance,
and they branch on the degree sign::

    =IFS(Z16="", "",
         ISNUMBER(SEARCH("<deg>", Z16)),  <angular +/-1 off AY23>,
         AND(Z16>=$AV$20, Z16<=$AX$20),   <linear band 1>,
         ...)

So an angle written as a bare NUMBER silently gets a linear tolerance. A chamfer
survived because its own value string carries "deg" ("1.75 X 45 deg"), but a
STANDALONE angle's value is just the number -- the " deg" in the printed report is
added from `kind`, which `_as_nominal` never saw. V094 503891 wrote `45` on tab
'67-199' and `68.7` on '-451' (2026-09-01), both with a +/-.1 linear tolerance on
an angle. `kind` is now passed in.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_inspection_dimensions" / "run.py")

DEG = "°"


@pytest.fixture(scope="module")
def rt():
    spec = importlib.util.spec_from_file_location("rt_911_inspection_nominals", PLUGIN)
    assert spec and spec.loader, f"cannot load the plugin at {PLUGIN}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dim(kind, value, ref=False, mods=()):
    return {"kind": kind, "value": value, "ref": ref, "mods": list(mods), "score": 1.0}


# --------------------------------------------------------------- the actual bug

@pytest.mark.parametrize("value", ["45", "68.7", "90"])
def test_standalone_angle_keeps_its_degree_sign(rt, value):
    """The regression: kind='angle' carries no "deg" in its value string."""
    assert rt.nominals_for([_dim("angle", value)]) == [value + DEG]


def test_standalone_angle_is_text_not_a_number(rt):
    """SEARCH() only finds the sign on a string - a float can never match."""
    (written,) = rt.nominals_for([_dim("angle", "45")])
    assert isinstance(written, str)


# ------------------------------------------- everything that must NOT change

def test_chamfer_still_splits_into_land_and_angle(rt):
    assert rt.nominals_for([_dim("chamfer", ".50 X 45 deg")]) == [0.5, "45" + DEG]


def test_reversed_chamfer_still_splits(rt):
    assert rt.nominals_for([_dim("chamfer", "45 deg X .50")]) == ["45" + DEG, 0.5]


@pytest.mark.parametrize("kind,value,expected", [
    ("linear", "22.88", [22.88]),
    ("radius", "0.38", [0.38]),
    ("diameter", "1.25", [1.25]),
    ("linear", ".50 X .50", [0.5, 0.5]),      # snipe: two lengths, no angle
])
def test_non_angles_stay_numbers(rt, kind, value, expected):
    """A number in a TARGET cell is what routes it to the LINEAR tolerance bands."""
    assert rt.nominals_for([_dim(kind, value)]) == expected


def test_ref_dimensions_are_still_excluded(rt):
    assert rt.nominals_for([_dim("angle", "45", ref=True)]) == []


def test_typ_angle_still_goes_last_and_keeps_its_sign(rt):
    """TYP ordering is the user's call - the fix must not disturb it."""
    dims = [_dim("angle", "45", mods=["TYP"]), _dim("linear", "12.00")]
    assert rt.nominals_for(dims) == [12.0, "45" + DEG]


# ------------------------------------------------------- _as_nominal directly

def test_as_nominal_defaults_to_linear(rt):
    """The default must stay non-angular: callers that pass no kind mean linear."""
    assert rt._as_nominal("45") == 45.0


def test_as_nominal_ignores_angle_kind_on_a_non_numeric_value(rt):
    """A value that is not a bare number is not an angle - don't stick a sign on it."""
    assert rt._as_nominal("N/A", "angle") == "N/A"
