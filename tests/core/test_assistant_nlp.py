"""The Assistant's rule-based parser.

These tests are the contract for "type what you mean". There is no model behind
it, so every behaviour here is a rule someone can read — and the failure mode
that matters most is a FALSE positive: silently eating a word out of a task's
name is worse than not recognising a shorthand at all. Several tests below
exist only to pin that down.
"""

from datetime import datetime, date

import pytest

from techdeck.core.assistant import nlp


NOW = datetime(2026, 8, 11, 6, 30)      # a Tuesday


# ── durations ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("45m", 45),
    ("45 min", 45),
    ("45 minutes", 45),
    ("2h", 120),
    ("2 hours", 120),
    ("1h30", 90),
    ("1 hr 30 min", 90),
    ("1.5h", 90),
    ("half an hour", 30),
])
def test_parse_duration(text, expected):
    minutes, span = nlp.parse_duration(f"do the thing {text} please")
    assert minutes == expected
    assert span is not None


def test_duration_absent():
    assert nlp.parse_duration("just do it")[0] is None


def test_duration_rejects_absurd_values():
    """A part number like '5000m' is not a 3.5-day task."""
    assert nlp.parse_duration("cut part 5000 minutes")[0] is None


# ── priority ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("order steel urgent", "critical"),
    ("order steel asap", "critical"),
    ("p1 order steel", "critical"),
    ("order steel high priority", "high"),
    ("order steel, high", "high"),
    ("order steel low", "low"),
    ("order steel whenever", "low"),
])
def test_parse_priority(text, expected):
    assert nlp.parse_priority(text)[0] == expected


@pytest.mark.parametrize("text", [
    "high bay rack inspection",
    "low bay lighting fix",
    "medium plate stock count",
])
def test_priority_words_inside_a_name_are_left_alone(text):
    """The regression this rule exists for: an ambiguous word mid-sentence is
    part of the task's NAME, not a priority, and stripping it silently renames
    the user's task."""
    assert nlp.parse_priority(text)[0] is None


# ── dates and times ──────────────────────────────────────────────────────────

def test_today_and_tomorrow():
    assert nlp.parse_when("due today", NOW).day == date(2026, 8, 11)
    assert nlp.parse_when("due tomorrow", NOW).day == date(2026, 8, 12)


def test_weekday_rolls_forward():
    # NOW is Tuesday; "friday" is the coming Friday.
    assert nlp.parse_when("by friday", NOW).day == date(2026, 8, 14)


def test_next_weekday_jumps_a_week():
    assert nlp.parse_when("next tuesday", NOW).day == date(2026, 8, 18)


@pytest.mark.parametrize("text,expected", [
    ("8/14", date(2026, 8, 14)),
    ("2026-08-14", date(2026, 8, 14)),
    ("aug 14", date(2026, 8, 14)),
    ("14 august", date(2026, 8, 14)),
])
def test_explicit_dates(text, expected):
    assert nlp.parse_when(text, NOW).day == expected


def test_relative_days():
    assert nlp.parse_when("in 3 days", NOW).day == date(2026, 8, 14)


def test_times():
    assert nlp.parse_when("at 2pm", NOW).at.hour == 14
    assert nlp.parse_when("at 9:30am", NOW).at.hour == 9
    assert nlp.parse_when("at 9:30am", NOW).at.minute == 30
    assert nlp.parse_when("at noon", NOW).at.hour == 12


def test_bare_afternoon_hour_assumes_the_working_day():
    """'at 2' in a shop is 2 in the afternoon, not 2am."""
    assert nlp.parse_when("at 2", NOW).at.hour == 14
    assert nlp.parse_when("at 9", NOW).at.hour == 9


def test_bare_time_already_past_rolls_to_tomorrow():
    afternoon = datetime(2026, 8, 11, 15, 0)
    assert nlp.parse_when("at 9", afternoon).day == date(2026, 8, 12)


# ── task lines ───────────────────────────────────────────────────────────────

def test_inline_task_line():
    parsed = nlp.parse_task_line("Fix the PO sheet 45m urgent due friday", NOW)
    assert parsed["title"] == "Fix the PO sheet"
    assert parsed["priority"] == "critical"
    assert parsed["estimate_min"] == 45
    assert parsed["deadline"] == "2026-08-14"


def test_priority_is_read_after_the_date_is_removed():
    """Regression: with the estimate and due date still in the line, a bare
    'high' sits mid-sentence, fails the delimiter rule, and used to be left
    stranded in the title."""
    parsed = nlp.parse_task_line("call Dan about rev C 1h30 high due tomorrow", NOW)
    assert parsed["title"] == "call Dan about rev C"
    assert parsed["priority"] == "high"
    assert parsed["estimate_min"] == 90
    assert parsed["deadline"] == "2026-08-12"


def test_pipe_form_is_order_independent():
    a = nlp.parse_task_line("Call Dan | high | 1h30 | due 8/14", NOW)
    b = nlp.parse_task_line("Call Dan | due 8/14 | 1h30 | high", NOW)
    for parsed in (a, b):
        assert parsed["title"] == "Call Dan"
        assert parsed["priority"] == "high"
        assert parsed["estimate_min"] == 90
        assert parsed["deadline"] == "2026-08-14"


def test_leading_bullet_is_stripped():
    assert nlp.parse_task_line("- do a thing", NOW)["title"] == "do a thing"
    assert nlp.parse_task_line("3) do a thing", NOW)["title"] == "do a thing"


def test_at_a_time_is_an_appointment_not_a_deadline():
    parsed = nlp.parse_task_line("safety meeting at 9am 30m", NOW)
    assert parsed["fixed_start"] == "2026-08-11T09:00:00"
    assert "deadline" not in parsed


def test_one_sitting():
    parsed = nlp.parse_task_line("deep clean the nest folders 3h no split", NOW)
    assert parsed["splittable"] is False
    assert parsed["title"] == "deep clean the nest folders"


def test_links_are_lifted_before_anything_else_reads_them():
    """A URL contains ':' and '/' that the time and date patterns would happily
    mis-read."""
    parsed = nlp.parse_task_line(
        "review https://example.com/8/14/spec.pdf 20m", NOW)
    assert parsed["links"] == ["https://example.com/8/14/spec.pdf"]
    assert parsed["title"] == "review"
    assert parsed.get("deadline") is None


def test_windows_path_is_a_link():
    parsed = nlp.parse_task_line(r"check C:\Dev\thing.xlsx 15m", NOW)
    assert parsed["links"] == [r"C:\Dev\thing.xlsx"]


def test_bullet_block():
    tasks = nlp.parse_bullet_block(
        "- fix the PO sheet 45m urgent\n\n2. call Dan | high | 1h\nplain line",
        NOW)
    assert [t["title"] for t in tasks] == ["fix the PO sheet", "call Dan",
                                           "plain line"]


# ── intents ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,kind", [
    ("build me a schedule", "schedule"),
    ("plan my day", "schedule"),
    ("note: gate code is 4417", "note"),
    ("- a bullet line", "note"),
    ("done fix the po sheet", "complete"),
    ("delete fix the po sheet", "delete"),
    ("list tasks", "list_tasks"),
    ("show notes", "list_notes"),
    ("what's on today", "agenda"),
    ("find rev c", "search"),
    ("help", "help"),
    ("remind me to call Dan", "task"),
    ("pick up parts 30m", "task"),
])
def test_intents(text, kind):
    assert nlp.parse_intent(text).kind == kind


def test_unmatched_text_becomes_a_task_capture():
    intent = nlp.parse_intent("order the 4130 tube")
    assert intent.kind == "task"
    assert intent.data["explicit"] is False


def test_explicit_task_verb_is_marked():
    assert nlp.parse_intent("add order the tube").data["explicit"] is True
