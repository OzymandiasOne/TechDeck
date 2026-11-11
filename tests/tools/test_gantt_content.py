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


# ---- the two log sheets ------------------------------------------------------
# 'Engineering Tasks' and 'Progress Notes' had no content in version control
# until 2026-11-11, and both stopped on Sep 1 while ten releases shipped. The
# rows below are what the writer matches on, so a malformed or duplicated one
# does not fail loudly -- it silently overwrites or re-appends a row on a
# management-facing sheet.

def test_task_rows_are_well_formed():
    from datetime import datetime

    statuses = {C.TASK_DONE, C.TASK_OPEN, C.TASK_TODO}
    subjects = {C.SUBJECT_TOOLS, C.SUBJECT_FEATURES, C.SUBJECT_ENGINEERING, None}
    for row in C.GANTT_TASKS:
        assert len(row) == 10, f"{row[0]}: expected 10 columns, got {len(row)}"
        task, priority, status, start, due, pct, done, notes, update, subject = row
        assert task.strip() and notes.strip() and update.strip(), (
            f"{task!r}: blank text cell")
        assert priority in {"High", "Normal", "Low"}, f"{task}: {priority!r}"
        assert status in statuses, f"{task}: unknown status {status!r}"
        assert subject in subjects, f"{task}: unknown subject {subject!r}"
        began = datetime.strptime(start, "%Y-%m-%d")
        if due is not None:
            assert began <= datetime.strptime(due, "%Y-%m-%d"), (
                f"{task}: due {due} is before start {start}")
        assert pct is None or 0 <= pct <= 1, f"{task}: completion {pct}"


def test_a_complete_task_is_done_and_an_open_one_is_not():
    """The sheet shows 'Done' off its own column; the two must not disagree."""
    for task, _, status, _, due, pct, done, *_ in C.GANTT_TASKS:
        if status == C.TASK_DONE:
            assert pct == 1 and done == 1 and due, (
                f"{task}: Complete needs 100%, the Done mark and a due date")
        else:
            assert done is None and pct != 1, (
                f"{task}: {status} but marked done or 100%")


def test_task_names_are_unique():
    """Tasks are matched on their name: a duplicate would overwrite its twin."""
    names = [r[0].strip().lower() for r in C.GANTT_TASKS]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate task rows: {sorted(dupes)}"


def test_note_rows_are_well_formed_and_unique():
    from datetime import datetime

    seen = set()
    for row in C.GANTT_NOTES:
        assert len(row) == 5, f"{row[1]}: expected 5 columns, got {len(row)}"
        day, subject, kind, what, outcome = row
        datetime.strptime(day, "%Y-%m-%d")
        assert kind in C.NOTE_TYPES, f"{subject}: unknown type {kind!r}"
        assert subject.strip() and what.strip() and outcome.strip(), (
            f"{subject!r} ({day}): blank text cell")
        key = (subject.strip().lower(), day)
        assert key not in seen, f"duplicate note: {subject} on {day}"
        seen.add(key)


def test_log_rows_are_appended_in_date_order():
    """New rows land at the bottom in LIST order, so the list is the order
    the sheet reads in."""
    starts = [r[3] for r in C.GANTT_TASKS]
    assert starts == sorted(starts), "GANTT_TASKS is not in start-date order"
    days = [r[0] for r in C.GANTT_NOTES]
    assert days == sorted(days), "GANTT_NOTES is not in date order"


def test_log_sheets_use_no_in_house_names():
    """The chart is the management-facing record: same vocabulary rule as the
    Version Controller (see the TONE RULE at the top of the content module)."""
    banned = ("beyblade", "woogy", "arcade", "fidget", "easter egg",
              "emporium", "sentry drone", "chopper gunner", "puppet master",
              "goblin", "reward ticket", "prize ticket", "tickets earned")
    blob = " ".join(str(v).lower()
                    for row in list(C.GANTT_TASKS) + list(C.GANTT_NOTES)
                    for v in row if v is not None)
    for word in banned:
        assert word not in blob, f"in-house term {word!r} on the Gantt chart"


def _sheet(rows, first_row=3):
    """An in-memory worksheet holding `rows` from `first_row` down."""
    import openpyxl

    ws = openpyxl.Workbook().active
    for r, values in enumerate(rows, start=first_row):
        for c, v in enumerate(values, start=1):
            ws.cell(row=r, column=c).value = v
    return ws


def test_a_task_already_on_the_sheet_is_not_appended_again(monkeypatch):
    """Idempotence: the second run of the writer must find nothing to do."""
    from datetime import datetime

    import sync_tracking_workbooks as S

    row = ("Some Task", "High", C.TASK_DONE, "2026-09-02", "2026-09-04", 1, 1,
           "what", "value", C.SUBJECT_TOOLS)
    monkeypatch.setattr(C, "GANTT_TASKS", [row])
    # As Excel hands it back: real dates, and one carrying the stray 04:00
    # that dates written through COM used to pick up.
    on_sheet = [None, "Some Task", "High", C.TASK_DONE,
                datetime(2026, 9, 2, 4, 0), datetime(2026, 9, 4), 1, 1,
                "what", "value", C.SUBJECT_TOOLS]
    notes = []
    updates, appends = S._plan_tasks(_sheet([on_sheet]), notes)
    assert (updates, appends, notes) == ([], [], [])

    updates, appends = S._plan_tasks(_sheet([]), [])
    assert not updates and len(appends) == 1


def test_a_changed_task_is_updated_in_place_not_duplicated(monkeypatch):
    from datetime import datetime

    import sync_tracking_workbooks as S

    row = ("Capstone", "High", C.TASK_OPEN, "2026-10-19", None, 0.4, None,
           "what", "value", None)
    monkeypatch.setattr(C, "GANTT_TASKS", [row])
    on_sheet = [None, "Capstone", "High", C.TASK_OPEN, datetime(2026, 10, 19),
                None, 0.1, None, "what", "value", None]
    updates, appends = S._plan_tasks(_sheet([on_sheet]), [])
    assert appends == []
    assert updates == [(3, 7, 0.4)]          # column G, the completion cell


def test_notes_match_on_subject_and_date(monkeypatch):
    from datetime import datetime

    import sync_tracking_workbooks as S

    note = ("2026-11-11", "A Release", "Milestone", "what", "outcome")
    monkeypatch.setattr(C, "GANTT_NOTES", [note])
    same = [datetime(2026, 11, 11), "A Release", "Milestone", "what", "outcome"]
    updates, appends, last = S._plan_notes(_sheet([same]), [])
    assert (updates, appends, last) == ([], [], 3)

    # The same subject on another day is a different event, so it is appended
    # below the last row rather than rewriting the earlier one.
    earlier = [datetime(2026, 9, 1), "A Release", "Milestone", "old", "old"]
    updates, appends, last = S._plan_notes(_sheet([earlier]), [])
    assert updates == [] and len(appends) == 1 and last == 3


def test_version_history_is_put_back_in_release_order():
    """Two releases logged in one run used to land newest-first (0.8.10 above
    0.8.9), because rows are appended in list order and the list is written
    newest first."""
    import sync_tracking_workbooks as S

    rows = [["Beta 0.7.5-0.7.8", "a"], ["Beta 0.8.8", "b"],
            ["Beta 0.8.10", "d"], ["Beta 0.8.9", "c"], ["In Development", "e"]]
    ws = _sheet(rows)
    assert S.sort_version_history(ws) == 2
    assert [ws.cell(row=r, column=1).value for r in range(3, 8)] == [
        "Beta 0.7.5-0.7.8", "Beta 0.8.8", "Beta 0.8.9", "Beta 0.8.10",
        "In Development"]
    assert ws.cell(row=5, column=2).value == "c"     # the row moved whole
    assert S.sort_version_history(ws) == 0           # and stays put


def test_an_unavailable_test_count_never_reaches_the_sheet():
    """With no count to cite, a row that cites one is held back - it must not
    be written with its '{tests}' placeholder still in it."""
    import sync_tracking_workbooks as S

    assert any("{tests}" in v for row in C.PI_NEW for v in row), (
        "no PI_NEW row cites the test count any more - retire this test")
    notes = []
    held = S.pi_rows(0, notes)
    assert not any("{tests}" in v for row in held for v in row)
    assert len(held) < len(C.PI_NEW) and notes

    filled = S.pi_rows(2765)
    assert len(filled) == len(C.PI_NEW)
    assert any("2765" in v for row in filled for v in row)
    assert not any("{tests}" in v for row in filled for v in row)


def test_no_count_skips_the_suite_run(monkeypatch):
    """--no-count must not start pytest at all: the suite run is the heavy
    part, and the flag exists for a box that cannot afford it."""
    import subprocess

    import sync_tracking_workbooks as S

    def _must_not_run(*args, **kwargs):
        raise AssertionError("the suite was started despite --no-count")

    monkeypatch.setattr(subprocess, "run", _must_not_run)
    monkeypatch.setattr(S, "COUNT_TESTS", False)
    S.test_count.cache_clear()
    try:
        assert S.test_count() == 0
    finally:
        S.test_count.cache_clear()      # do not leave a cached 0 behind


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
