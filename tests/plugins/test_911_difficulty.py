"""Regression tests for the 911 difficulty-rating lookup.

Both bugs these cover were found by cross-checking the openpyxl read against
an Excel-COM read of the SAME live sheet, and both failed SILENTLY (a nest
just came out unrated), which is exactly the shape that reaches production:

1. SIMPLE is a THEME fill (theme 9 + tint) on the real schedule while MEDIUM
   and DIFFICULT are literal RGB. openpyxl exposes no ``.rgb`` for theme
   colours, so all 85 SIMPLE rows read as unrated.
2. Nest ids are not always numeric ("V085 S20085"), so a ``\\d{5,6}`` token
   regex dropped those rows (Hard Rule 3's alphanumeric-nest class).
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "911_remove_ticket" / "run.py")


@pytest.fixture(scope="module")
def rt():
    spec = importlib.util.spec_from_file_location("rt_911_remove_ticket", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Real clrScheme from EB 922 Schedule.xlsx (accent6 = 4EA72E).
THEME_XML = """<a:theme><a:themeElements><a:clrScheme name="x">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="0E2841"/></a:dk2>
<a:lt2><a:srgbClr val="E8E8E8"/></a:lt2>
<a:accent1><a:srgbClr val="156082"/></a:accent1>
<a:accent2><a:srgbClr val="E97132"/></a:accent2>
<a:accent3><a:srgbClr val="196B24"/></a:accent3>
<a:accent4><a:srgbClr val="0F9ED5"/></a:accent4>
<a:accent5><a:srgbClr val="A02B93"/></a:accent5>
<a:accent6><a:srgbClr val="4EA72E"/></a:accent6>
<a:hlink><a:srgbClr val="467886"/></a:hlink>
<a:folHlink><a:srgbClr val="96607D"/></a:folHlink>
</a:clrScheme></a:themeElements></a:theme>"""


class _FakeWB:
    loaded_theme = THEME_XML


def test_theme_scheme_parses_in_excel_index_order(rt):
    """Excel swaps dk1/lt1 and dk2/lt2 relative to the XML order."""
    rgbs = rt._theme_rgbs(_FakeWB())
    assert len(rgbs) == 12
    assert rgbs[0] == (255, 255, 255)   # index 0 = lt1, NOT dk1
    assert rgbs[1] == (0, 0, 0)         # index 1 = dk1
    assert rgbs[9] == (0x4E, 0xA7, 0x2E)  # index 9 = accent6


def test_theme_tint_resolves_to_the_simple_green(rt):
    """accent6 + tint 0.8 must land on the legend's SIMPLE green.

    Ground truth (218,242,208) came from Excel's own DisplayFormat. The naive
    per-channel tint approximation lands ~7 away; the HLS one lands within 1.
    """
    rgbs = rt._theme_rgbs(_FakeWB())
    got = rt._apply_tint(rgbs[9], 0.7999816888943144)
    dist = sum((a - b) ** 2 for a, b in zip(got, (218, 242, 208))) ** 0.5
    assert dist <= 2.0, f"{got} too far from Excel's (218,242,208)"
    assert rt._match_fill(got) == "SIMPLE"


@pytest.mark.parametrize("rgb,expected", [
    ((218, 242, 208), "SIMPLE"),
    ((249, 236, 143), "MEDIUM"),
    ((250, 148, 155), "DIFFICULT"),
    ((217, 217, 217), None),      # legend N/A
    ((191, 191, 191), None),      # SHIPPED conditional-format grey
    ((255, 255, 255), None),      # unrated
    (None, None),
])
def test_legend_colours_map(rt, rgb, expected):
    assert rt._match_fill(rgb) == expected


def test_near_miss_colour_still_resolves(rt):
    """A hand-recoloured cell a few shades off must not read as unrated."""
    assert rt._match_fill((214, 245, 205)) == "SIMPLE"


def test_unrelated_colour_does_not_resolve(rt):
    assert rt._match_fill((30, 60, 200)) is None


@pytest.mark.parametrize("nest,expected", [
    ("503884", "MEDIUM"),
    ("S20085", "DIFFICULT"),            # alphanumeric nest
    ("s20085", "DIFFICULT"),            # case-insensitive
    ("503884 MOVE TICKET OMIT-", "MEDIUM"),   # digits pulled from a stem
    ("999999", None),
    ("", None),
])
def test_lookup_handles_numeric_and_alphanumeric_nests(rt, nest, expected):
    diff_map = {"503884": "MEDIUM", "S20085": "DIFFICULT"}
    assert rt._lookup_difficulty(diff_map, nest) == expected


def test_lookup_on_empty_map_is_none(rt):
    assert rt._lookup_difficulty({}, "503884") is None


def test_difficulty_colours_defined_for_every_label(rt):
    labels = {v for v in rt.DIFFICULTY_FILLS.values() if v}
    assert labels == set(rt.DIFFICULTY_COLORS)
