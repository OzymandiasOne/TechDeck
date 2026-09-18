"""Regression tests for which OCR tokens 911 Inspection Dimensions calls a dimension.

Every real LENGTH on these drawings is printed to two decimal places, so a length
with no decimal point is a misread. `classify` applied that to a LONE token from the
start -- but a compound ("78 X 68.7") matched its own branch and returned before ever
reaching the test, so a ".78" read as "78" reached tab '-451' as a 78in dimension on
a 13.66in part (V094 503891, 2026-09-01).

The rule cannot be applied to the whole token. A chamfer is "<length> X <degrees>",
and the DEGREES half is legitimately a bare integer -- across every report on disk,
each real chamfer read "<len> X 45 deg". Testing the whole token would have deleted
all of them. So it applies to the LENGTH halves only.

The corpus below is not invented: it is every distinct compound shape found in the
four real run reports on disk (503841, 503891, the bevel_test set and the Aug-20
multi-nest run) -- 27 compound readings, 9 distinct shapes.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_inspection_dimensions" / "run.py")

# (token as the OCR emits it, what it is, the value classify must produce)
REAL_COMPOUNDS = [
    (".31X.31", "snipe", ".31 X .31"),
    (".50X.50", "snipe", ".50 X .50"),
    ("1.0X1.0", "snipe", "1.0 X 1.0"),
    ("1.00X1.00", "snipe", "1.00 X 1.00"),
    (".50X45°", "chamfer", ".50 X 45 deg"),
    ("1.00X45°", "chamfer", "1.00 X 45 deg"),
    ("1.75X45°", "chamfer", "1.75 X 45 deg"),
    (".78X68.7°", "chamfer", ".78 X 68.7 deg"),
    ("45°X.50", "chamfer, angle first", "45 deg X .50"),
]

# The one the rule exists for: a ".78" whose leading dot the OCR lost.
MISREAD = "78X68.7°"


@pytest.fixture
def rt():
    """A fresh module per test - _STRICT_COMPOUNDS is module state."""
    spec = importlib.util.spec_from_file_location("rt_911_inspection_tokens", PLUGIN)
    assert spec and spec.loader, f"cannot load the plugin at {PLUGIN}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------- the real corpus survives

@pytest.mark.parametrize("token,label,expected", REAL_COMPOUNDS,
                         ids=[c[1] + " " + c[0] for c in REAL_COMPOUNDS])
def test_every_real_compound_still_reads(rt, token, label, expected):
    """If any of these start returning None the rule is eating real work."""
    result = rt.classify(token)
    assert result is not None, f"{label} {token} was thrown away"
    assert result[1] == expected


def test_a_chamfers_bare_integer_degrees_are_never_touched(rt):
    """The whole point: "45" is a real angle, not a bad length."""
    kind, value, _ = rt.classify(".50X45°")
    assert kind == "chamfer"
    assert value.endswith("45 deg")


# ------------------------------------------------------------------- the misread

def test_the_misread_is_dropped(rt):
    assert rt.classify(MISREAD) is None


def test_the_same_token_with_its_decimal_point_is_kept(rt):
    """Proves the rule keys on the missing point, not on the number."""
    assert rt.classify(".78X68.7°") is not None


def test_a_bare_length_in_a_snipe_is_dropped(rt):
    assert rt.classify("1X1.00") is None
    assert rt.classify("1.00X1") is None


def test_a_bare_length_before_the_degrees_half_is_dropped(rt):
    """Both chamfer spellings, so neither branch can be missed."""
    assert rt.classify("78X68.7°") is None      # <len> X <deg>
    assert rt.classify("68.7°X78") is None      # <deg> X <len>


# --------------------------------------------------------------- the escape hatch

def test_unticking_the_setting_restores_the_old_behaviour(rt):
    """The setting is the rollback: no rebuild, no release."""
    rt._STRICT_COMPOUNDS = False
    result = rt.classify(MISREAD)
    assert result is not None
    assert result[1] == "78 X 68.7 deg"


def test_the_escape_hatch_does_not_disturb_real_compounds(rt):
    rt._STRICT_COMPOUNDS = False
    for token, label, expected in REAL_COMPOUNDS:
        assert rt.classify(token)[1] == expected, label


def test_lone_token_rule_is_not_governed_by_the_setting(rt):
    """Unticking goes back to TODAY's behaviour, not to no checks at all.

    A lone bare integer has been rejected since v0.1 (it is a view tag or a stray
    stroke); the setting only ever governs the compound halves.
    """
    rt._STRICT_COMPOUNDS = False
    assert rt.classify("74") is None
    assert rt.classify("4") is None


# ------------------------------------------------- ordinary tokens are unaffected

@pytest.mark.parametrize("token,expected_kind", [
    ("22.88", "linear"),
    ("R.40", "radius"),
    ("45°", "angle"),
    (".31", "linear"),
])
def test_simple_tokens_are_unchanged(rt, token, expected_kind):
    result = rt.classify(token)
    assert result is not None and result[0] == expected_kind
