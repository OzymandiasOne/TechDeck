"""Header lookups must survive a header GROWING extra words.

Found live 2026-08-11. The EB 922 Schedule's rating column was renamed
`RATING` → `RATING/PC COUNT`. Both difficulty readers looked it up exactly, so
both silently found nothing:

  * every Teams card posted with NO difficulty label
  * the packet stamp found ZERO ratings and stamped none, behind a warning
    popup that is easy to dismiss

It had shipped working in v0.8.6.11 and rotted the moment someone appended two
words to a spreadsheet header. Hard Rule 1 says look columns up by NAME rather
than position — this is the other half of that rule: a header name is a lookup
key, but it is also human text, and humans add words to it.

`prefix_ok` stays OPT-IN. Loosening every lookup would let a required `QTY`
latch onto `QTY SHIPPED` on some other sheet and read the wrong column
silently — trading a loud failure for a quiet one.
"""

import openpyxl
import pytest

from techdeck.core import plugin_sdk as sdk


# The real CURRENT PIPELINE header row, copied off the live schedule
# 2026-08-11 — trailing spaces and all.
LIVE_HEADERS = ["DEPT. ", "BATCH / NEST", "DATE ", "NOTES",
                "RATING/PC COUNT", "STATUS ", "TECH TEAM NOTES",
                "RATING SYSTEM (HR)"]


@pytest.fixture
def live_sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["EB 922 SCHEDULE"])          # a title row above the headers
    ws.append(LIVE_HEADERS)
    ws.append([911, "V102 504098", None, "HSS 6 X 4 TUBE", None,
               "NEED TEAMS/SETUP", None, None])
    return ws


# ── header_col ──────────────────────────────────────────────────────────────
def test_it_finds_a_header_that_grew_extra_words():
    assert sdk.header_col({"RATING/PC COUNT": 5}, "RATING") == 5


def test_an_exact_match_still_wins():
    """When both exist, the exact header is the one that was asked for."""
    assert sdk.header_col({"RATING/PC COUNT": 5, "RATING": 9}, "RATING") == 9


def test_the_leftmost_prefix_match_wins_when_there_is_no_exact_one():
    assert sdk.header_col({"RATING SYSTEM (HR)": 8, "RATING/PC COUNT": 5},
                          "RATING") == 5


def test_a_genuinely_absent_header_is_still_none():
    assert sdk.header_col({"RATING/PC COUNT": 5}, "MATERIAL") is None


def test_it_does_not_match_a_header_that_merely_contains_the_name():
    """Prefix, not substring — 'RATING' must not latch onto 'PC RATING', which
    would be a different column entirely."""
    assert sdk.header_col({"PC RATING": 5}, "RATING") is None


@pytest.mark.parametrize("asked", ["rating", "  RATING  ", "Rating"])
def test_lookup_is_case_and_whitespace_insensitive(asked):
    assert sdk.header_col({"RATING/PC COUNT": 5}, asked) == 5


# ── find_header_row(prefix_ok=...) ──────────────────────────────────────────
def test_the_live_header_row_is_not_found_by_an_exact_match(live_sheet):
    """The bug, reproduced: this is what both readers were doing."""
    row, hdr = sdk.find_header_row(live_sheet, ["BATCH / NEST", "RATING"])
    assert row is None and hdr == {}


def test_prefix_ok_finds_it(live_sheet):
    row, hdr = sdk.find_header_row(live_sheet, ["BATCH / NEST", "RATING"],
                                   prefix_ok=True)
    assert row == 2
    assert sdk.header_col(hdr, "RATING") == 5          # RATING/PC COUNT
    assert sdk.header_col(hdr, "BATCH / NEST") == 2
    assert sdk.header_col(hdr, "STATUS") == 6          # 'STATUS ' stripped


def test_exact_matching_is_still_the_default(live_sheet):
    """The guard on the opt-in: nothing else in the app changes behaviour."""
    exact_row, _ = sdk.find_header_row(live_sheet, ["BATCH / NEST", "NOTES"])
    assert exact_row == 2, "an exact-matchable row must still be found exactly"
    missing, _ = sdk.find_header_row(live_sheet, ["BATCH / NEST", "RATING"])
    assert missing is None, "prefix matching must not leak into the default"


def test_a_required_header_that_is_genuinely_missing_still_fails(live_sheet):
    row, hdr = sdk.find_header_row(live_sheet, ["BATCH / NEST", "MATERIAL"],
                                   prefix_ok=True)
    assert row is None and hdr == {}


def test_prefix_ok_does_not_match_a_substring_header():
    """The false-positive this opt-in is designed to avoid: a required 'QTY'
    must not satisfy itself against 'TOTAL QTY'."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["DYPN", "TOTAL QTY"])
    row, _ = sdk.find_header_row(ws, ["DYPN", "QTY"], prefix_ok=True)
    assert row is None
