"""The tracking workbook's tool roster must match the app's actual tool set.

This is the guard for the drift the workbook audit turned up: the sheet had
five tools filed under the wrong workflow heading and four listed under names
they had been renamed away from, plus one entry that was not a tool at all but
a stage inside another one. Every one of those is a silent error -- the sheet
still reads fine, it is just wrong -- so nothing caught them for months.

Checking the content module against `plugins/*/plugin.json` turns all four
failure modes into a test failure the moment a tool is added, renamed, moved
between families, or invented.

Games-family plugins are excluded on purpose: the workbook is the presented
record and lists production automation only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import sync_workbook_tools as T  # noqa: E402

SECTION_FOR_FAMILY = {
    "911": "911 QTDR PRODUCTION PACKAGE WORKFLOW",
    "922": "922 QTDR PALLET PACKAGE WORKFLOW",
    "902": "902 QTDR PRODUCTION PACKAGE WORKFLOW",
}
SHARED_SECTION = "QUALITY, ESTIMATING & SHOP TOOLS"

# Dev-only tooling is no longer an allowlist to maintain here. It lives under
# tools/devkit/, which TechDeck.spec excludes from every frozen build, so it is
# not in plugins/ and never reaches this scan. (The comment this replaces
# pointed at a DEV_ONLY_PLUGINS in TechDeck.spec that did not exist - the kind
# of rot a hand-maintained second list attracts.) Games are still skipped
# below: those DO ship, they are just not ASA production automation.


def _plugins() -> dict:
    """{display name: family} for every non-Games plugin on disk."""
    out = {}
    for path in sorted((ROOT / "plugins").glob("*/plugin.json")):
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
        family = meta.get("family", "General")
        if family == "Games":
            continue
        out[meta["name"]] = family
    return out


def _sheet_rows() -> list:
    return [(section, row) for section, rows in T.TOOL_SECTIONS for row in rows]


def test_every_deployed_tool_is_listed():
    missing = set(_plugins()) - {row[0] for _, row in _sheet_rows()}
    assert not missing, f"tools shipped but absent from the workbook: {sorted(missing)}"


def test_no_listed_tool_is_invented():
    """A row naming something that is not a plugin -- a stage inside another
    tool, or a name that no longer exists after a rename."""
    extra = {row[0] for _, row in _sheet_rows()} - set(_plugins())
    assert not extra, f"workbook lists non-existent tools: {sorted(extra)}"


@pytest.mark.parametrize("section,row", _sheet_rows(),
                         ids=[r[0] for _, r in _sheet_rows()])
def test_tool_is_under_its_own_workflow_section(section, row):
    family = _plugins().get(row[0])
    if family is None:
        pytest.skip("covered by test_no_listed_tool_is_invented")
    expected = SECTION_FOR_FAMILY.get(family, SHARED_SECTION)
    assert section == expected, (
        f"{row[0]} is a {family} tool but is filed under {section!r}")


def test_rows_are_complete():
    for section, row in _sheet_rows():
        assert len(row) == 5, f"{row[0]}: expected 5 columns, got {len(row)}"
        assert all(str(v).strip() for v in row), f"{row[0]} has a blank cell"


def test_roadmap_phases_are_known():
    allowed = {"Delivered", "Planned", "Research", "Backlog"}
    for row in T.ROADMAP_ROWS:
        assert len(row) == 5, f"{row[1]}: expected 5 columns"
        assert row[4] in allowed, f"{row[1]} has unknown phase {row[4]!r}"


def test_roadmap_items_are_unique():
    names = [r[1] for r in T.ROADMAP_ROWS]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate roadmap items: {sorted(dupes)}"


def test_roadmap_covers_every_workflow():
    """The sheet used to hold 922 and platform items only, so the whole 911
    programme was invisible on the one sheet a reader turns to for direction."""
    flows = {r[3] for r in T.ROADMAP_ROWS}
    for expected in ("911", "922", "Platform"):
        assert expected in flows, f"roadmap has no {expected} items"


def test_presented_record_uses_no_in_house_names():
    """The Version Controller is read outside the team. Engagement features are
    logged, but under what they do -- never the in-house names."""
    # "ticket" is deliberately NOT a bare banned word: "911 Remove Ticket" is a
    # real tool and move tickets are real shop documents. Only the reward
    # currency's phrasings are banned.
    banned = ("beyblade", "woogy", "arcade", "fidget", "easter egg",
              "emporium", "sentry drone", "chopper gunner",
              "reward ticket", "prize ticket", "tickets earned")
    blob = " ".join(
        str(v).lower() for _, row in _sheet_rows() for v in row
    ) + " " + " ".join(str(v).lower() for row in T.ROADMAP_ROWS for v in row)
    for word in banned:
        assert word not in blob, f"in-house term {word!r} in the presented record"


def test_view_reset_clears_the_saved_scroll_position():
    """A sheet remembers where it was last scrolled to as `topLeftCell` on the
    view, and openpyxl carries that through a rewrite. With a frozen pane the
    two disagree -- view says 'open at row 17', pane says 'the scrollable
    region starts at row 3' -- Excel obeys the view, and the sheet opens
    stranded at the bottom with the rows above unreachable. Three sheets
    shipped like that before `_view()` existed.
    """
    import openpyxl

    import sync_tracking_workbooks as S

    ws = openpyxl.Workbook().active
    ws.sheet_view.topLeftCell = "A17"          # as if last saved scrolled down
    S._view(ws, "A3")

    assert ws.sheet_view.topLeftCell is None, "stale scroll position survived"
    assert ws.freeze_panes == "A3"
    assert ws.sheet_view.showGridLines is False
    for sel in ws.sheet_view.selection or []:
        assert sel.activeCell == "A3", "selection left below the frozen rows"


def test_test_count_does_not_double_quiet_pytest():
    """pytest.ini already sets `addopts = -q`. Passing another -q makes it -qq,
    which suppresses the summary line test_count() reads -- so it returned 0 on
    a fully green suite, and a 0 leaves the sheet's stale number in place.

    Checked statically: actually calling test_count() from inside the suite
    would spawn the suite recursively.
    """
    import inspect
    import re

    import sync_tracking_workbooks as S

    src = inspect.getsource(S.test_count)
    cmd = re.search(r"\[sys\.executable[^\]]*\]", src).group(0)
    assert '"-q"' not in cmd and "'-q'" not in cmd, (
        f"test_count passes -q on top of pytest.ini's: {cmd}")

    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "-q" in ini, ("pytest.ini no longer sets -q, so test_count must "
                         "pass it itself for the summary format it parses")
