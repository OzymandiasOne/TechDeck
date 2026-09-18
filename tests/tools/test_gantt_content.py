"""The Gantt chart's project roster must stay structurally sound and complete.

This is the guard for how the chart actually drifted: 911 Scripting Prep
shipped (v0.8.7.3) and simply never got a row, because updating the chart was
a manual end-of-session step -- the same failure mode the tracking workbooks
had before their sync script. The chart content now lives in
`sync_workbook_content.py` and is written by `sync_tracking_workbooks.py`;
these tests check the CONTENT, because the workbook itself lives outside the
repo and is not available on CI runners.

Games-family plugins are excluded on purpose, matching the workbook roster
guard: the chart is a presented record of production automation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import sync_workbook_content as C  # noqa: E402

STATUSES = {C.GANTT_DONE, C.GANTT_DEV, C.GANTT_PLAN, C.GANTT_DEFERRED}


def _projects() -> list:
    return [e for e in C.GANTT_ROWS if e[0] != "SECTION"]


def test_rows_are_complete_and_use_known_statuses():
    for row in _projects():
        name, status, pct, start, end = row
        assert name.strip(), "blank project name"
        assert status in STATUSES, f"{name}: unknown status {status!r}"
        assert 0 <= pct <= 1, f"{name}: completion {pct} outside 0..1"


def test_done_means_one_hundred_percent():
    """A row can't claim Complete while its bar shows partial progress."""
    for name, status, pct, *_ in _projects():
        if status == C.GANTT_DONE:
            assert pct == 1, f"{name}: Complete but {pct:.0%}"
        if status in (C.GANTT_PLAN, C.GANTT_DEFERRED):
            assert pct == 0, f"{name}: {status.split()[0]} but {pct:.0%}"


def test_dates_parse_and_run_forward():
    import sync_tracking_workbooks as S

    for name, _, _, start, end in _projects():
        assert S._gantt_month(start) <= S._gantt_month(end), (
            f"{name}: starts {start} but ends {end}")
        assert S._gantt_span(start, end) >= 1


def test_project_names_are_unique():
    names = [r[0] for r in _projects()]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate chart rows: {sorted(dupes)}"


def test_renames_do_not_collide_with_live_rows():
    names = {r[0] for r in _projects()}
    for old, new in C.GANTT_RENAMES.items():
        assert old not in names, f"content still uses pre-rename name {old!r}"
        assert new in names, f"rename target {new!r} has no content row"


def test_every_deployed_tool_is_on_the_chart():
    """The drift this file exists to prevent: a shipped app with no row.

    Chart rows carry descriptive suffixes ('911 PO PDF Extractor (Support)'),
    so a plugin counts as covered when its display name appears inside any
    project name.
    """
    blob = [r[0] for r in _projects()]
    missing = []
    for path in sorted((ROOT / "plugins").glob("*/plugin.json")):
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
        if meta.get("family", "General") == "Games":
            continue
        if not any(meta["name"] in name for name in blob):
            missing.append(meta["name"])
    assert not missing, f"tools shipped but absent from the Gantt chart: {missing}"
