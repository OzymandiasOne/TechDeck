"""The Qt side of the 2026-10-09 Assistant requests.

The engine is covered in tests/core; these cover the wiring that only exists
on the Qt side: the Tasks tab's search box and filters, the steps folding out
under a task, the ▶/■ clock button, the Time tab, and the task dialog's
text-authored checklist.
"""

from datetime import date, datetime, timedelta

import pytest

from techdeck.core.assistant.models import (
    ChecklistItem, Commitment, TaskItem, WorkSession,
)
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.dialogs.task_edit_dialog import TaskEditDialog
from techdeck.ui.widgets.assistant_schedule import SchedulePanel, TasksPanel
from techdeck.ui.widgets.assistant_time import TimePanel


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


def _titles(panel: TasksPanel):
    return [t.label() for t in panel._visible_tasks()]


# ── searching the backlog ────────────────────────────────────────────────────

def test_the_search_box_narrows_the_list(store, qapp):
    store.add_task(TaskItem(title="Fix the PO sheet"))
    store.add_task(TaskItem(title="Order the 4130 tube"))
    panel = TasksPanel(store)

    panel.search.setText("tube")
    assert _titles(panel) == ["Order the 4130 tube"]
    panel.search.setText("")
    assert len(_titles(panel)) == 2


def test_the_search_reaches_notes_links_and_steps(store, qapp):
    store.add_task(TaskItem(title="Rollout", notes="PO 1000129724"))
    store.add_task(TaskItem(title="Scribe sheet", checklist=[
        ChecklistItem(text="pull the drawings")]))
    store.add_task(TaskItem(title="Elsewhere",
                            links=[r"C:\Pilot Program\thing.xlsx"]))
    panel = TasksPanel(store)

    panel.search.setText("1000129724")
    assert _titles(panel) == ["Rollout"]
    panel.search.setText("drawings")
    assert _titles(panel) == ["Scribe sheet"]
    panel.search.setText("pilot program")
    assert _titles(panel) == ["Elsewhere"]


def test_search_and_filter_compose(store, qapp):
    store.add_task(TaskItem(title="Tube order", done=True))
    store.add_task(TaskItem(title="Tube scribe"))
    panel = TasksPanel(store)
    panel.search.setText("tube")

    panel.filter_box.setCurrentIndex(panel.filter_box.findData("done"))
    assert _titles(panel) == ["Tube order"]
    panel.filter_box.setCurrentIndex(panel.filter_box.findData("open"))
    assert _titles(panel) == ["Tube scribe"]


def test_a_search_with_no_hits_says_what_was_searched_for(store, qapp):
    store.add_task(TaskItem(title="Fix the PO sheet"))
    panel = TasksPanel(store)
    panel.search.setText("zzzz")
    labels = [panel.scroller.box.itemAt(i).widget()
              for i in range(panel.scroller.box.count())]
    text = " ".join(getattr(w, "text", lambda: "")() for w in labels)
    assert "zzzz" in text


def test_there_is_a_waiting_filter(store, qapp):
    store.add_task(TaskItem(title="Mine"))
    parked = store.add_task(TaskItem(title="Theirs"))
    store.set_waiting(parked.id, True, "Dan")
    panel = TasksPanel(store)

    panel.filter_box.setCurrentIndex(panel.filter_box.findData("waiting"))
    assert _titles(panel) == ["Theirs"]


# ── steps on a task row ──────────────────────────────────────────────────────

def test_steps_are_folded_away_until_asked_for(store, qapp):
    """A backlog where every project is expanded by default is a wall."""
    task = store.add_task(TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings"),
        ChecklistItem(text="build the kit sheet")]))
    panel = TasksPanel(store)
    assert task.id not in panel._expanded

    panel._toggle_steps(task.id)
    assert task.id in panel._expanded
    panel._toggle_steps(task.id)
    assert task.id not in panel._expanded


def test_ticking_a_step_saves_it(store, qapp):
    task = store.add_task(TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings")]))
    panel = TasksPanel(store)
    panel._set_step_done(task.id, task.checklist[0].id, True)

    saved = AssistantStore(store.dir).get_task(task.id)
    assert saved is not None and saved.checklist_progress() == (1, 1)


# ── the clock button ─────────────────────────────────────────────────────────

def test_the_clock_button_starts_and_stops(store, qapp):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    panel = TasksPanel(store)

    panel._toggle_clock(store.get_task(task.id))
    assert store.get_task(task.id).is_running
    panel._toggle_clock(store.get_task(task.id))
    assert not store.get_task(task.id).is_running


def test_the_running_task_is_named_in_the_summary_line(store, qapp):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    panel = TasksPanel(store)
    panel._toggle_clock(store.get_task(task.id))
    panel.refresh()
    assert "Fix the PO sheet" in panel.summary.text()


# ── the Time tab ─────────────────────────────────────────────────────────────

def _with_time(store, title, minutes, when=None):
    when = when or datetime.now().replace(hour=9, minute=0, second=0,
                                          microsecond=0)
    task = TaskItem(title=title)
    task.sessions.append(WorkSession(
        start=when.isoformat(),
        end=(when + timedelta(minutes=minutes)).isoformat()))
    return store.add_task(task)


def test_the_time_tab_says_so_when_nothing_is_clocked(store, qapp):
    panel = TimePanel(store)
    panel.refresh()
    assert "Nothing clocked" in panel.sub.text()
    assert not panel.export_btn.isEnabled()


def test_the_time_tab_totals_the_range(store, qapp):
    _with_time(store, "Fix the PO sheet", 45)
    _with_time(store, "Order the tube", 15)
    panel = TimePanel(store)
    panel.refresh()
    assert "1h" in panel.sub.text()
    assert panel.export_btn.isEnabled()


def test_the_time_tab_offers_to_stop_a_running_clock(store, qapp):
    task = store.add_task(TaskItem(title="Fix the PO sheet"))
    store.clock_in(task.id)
    panel = TimePanel(store)
    panel.refresh()
    assert panel.stop_btn.isVisible() or panel.stop_btn.isVisibleTo(panel)

    panel._stop_clock()
    assert store.running_task() is None


def test_an_old_session_is_outside_this_week(store, qapp):
    _with_time(store, "Ancient history", 60,
               when=datetime.now() - timedelta(days=60))
    panel = TimePanel(store)
    panel.refresh()
    assert "Nothing clocked" in panel.sub.text()

    panel.range_box.setCurrentIndex(panel.range_box.findData("all"))
    assert "1h" in panel.sub.text()


# ── the task dialog's steps box ──────────────────────────────────────────────

def test_steps_are_authored_as_text_and_parsed(qapp):
    dialog = TaskEditDialog(TaskItem(title="Rollout"))
    dialog.steps.setPlainText(
        "x pull the drawings 15m\nbuild the kit sheet 45m due 2026-10-16")
    task = dialog.result_task()

    assert [s.text for s in task.checklist] == [
        "pull the drawings", "build the kit sheet"]
    assert task.checklist[0].done and task.checklist[0].estimate_min == 15
    assert task.checklist[1].deadline == "2026-10-16"


def test_a_steps_identity_survives_an_edit_of_the_box(qapp):
    """Matching by text, not position: a step that keeps its words keeps its
    id, its done stamp and the reminders already sent about it."""
    original = TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings", done=True),
        ChecklistItem(text="build the kit sheet")])
    keep_id = original.checklist[1].id

    dialog = TaskEditDialog(original)
    dialog.steps.setPlainText("build the kit sheet\nwalk it to QA")
    task = dialog.result_task()
    assert task.checklist[0].id == keep_id


def test_the_steps_box_round_trips(qapp):
    task = TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings", estimate_min=15, done=True),
        ChecklistItem(text="walk it to QA", deadline="2026-10-16")])
    dialog = TaskEditDialog(task)
    assert dialog.steps.toPlainText().splitlines() == [
        "x pull the drawings 15m", "walk it to QA due 2026-10-16"]


def test_rolling_the_steps_up_fills_the_estimate(qapp):
    dialog = TaskEditDialog(TaskItem(title="Rollout", estimate_min=30))
    dialog.steps.setPlainText("pull the drawings 15m\nbuild the sheet 45m")
    dialog._roll_up_estimate()
    assert dialog.estimate.value() == 60


def test_the_waiting_flag_round_trips_through_the_dialog(qapp):
    dialog = TaskEditDialog(TaskItem(title="Order the tube"))
    dialog.waiting.setChecked(True)
    dialog.waiting_on.setText("Dan")
    task = dialog.result_task()
    assert task.waiting and task.waiting_on == "Dan"
    assert task.waiting_since

    dialog.waiting.setChecked(False)
    cleared = dialog.result_task()
    assert not cleared.waiting and cleared.waiting_since is None


# ── the Schedule tab ─────────────────────────────────────────────────────────

def test_the_schedule_tab_offers_the_meetings_editor(store, qapp):
    seen = []
    panel = SchedulePanel(store)
    panel.blocks_requested.connect(lambda: seen.append(True))
    panel.blocks_btn.click()
    assert seen == [True]


def test_a_meeting_shows_on_the_agenda_without_a_tick_box(store, qapp):
    """Not your work, so there is nothing to tick."""
    from PySide6.QtWidgets import QCheckBox

    from techdeck.core.assistant.models import SchedulePrefs
    from techdeck.core.assistant.scheduler import (
        ScheduleRequest, build_schedule,
    )

    day = date.today() + timedelta(days=1)
    store.add_commitment(Commitment(title="Production meeting", start="09:00",
                                    minutes=60, day=day.isoformat()))
    schedule = build_schedule(ScheduleRequest(
        tasks=[TaskItem(title="Job", estimate_min=60)], start_day=day,
        end_day=day, prefs=SchedulePrefs(),
        commitments=store.commitments))
    store.add_schedule(schedule)

    panel = SchedulePanel(store)
    panel.refresh()
    busy = [b for b in schedule.all_blocks() if b.title == "Production meeting"]
    row = panel._block_row(busy[0], panel.get_current_palette(),
                           datetime.now())
    assert not row.findChildren(QCheckBox)


# ── the looks, after the 2026-10-13 pass ─────────────────────────────────────

def test_the_dialog_snaps_a_meeting_to_the_five_minute_grid(store, qapp):
    """The spinner steps by a minute, so 9:04 is one stray press away, and a
    plan full of 9:04-9:34 rows reads as machine output."""
    from PySide6.QtCore import QTime

    from techdeck.ui.dialogs.commitments_dialog import CommitmentsDialog

    dialog = CommitmentsDialog(store)
    dialog._new()
    dialog.title_field.setText("Standup")
    dialog.start.setTime(QTime(9, 4))
    dialog.day_checks[2].setChecked(True)
    dialog._save_current()

    assert store.commitments[0].start == "09:05"


def test_the_dialog_rolls_an_almost_midnight_snap(store, qapp):
    from PySide6.QtCore import QTime

    from techdeck.ui.dialogs.commitments_dialog import CommitmentsDialog

    dialog = CommitmentsDialog(store)
    dialog._new()
    dialog.title_field.setText("Late one")
    dialog.start.setTime(QTime(23, 59))
    dialog.day_checks[2].setChecked(True)
    dialog._save_current()

    assert store.commitments[0].start == "00:00"


def test_a_step_keeps_its_chips_beside_it(store, qapp):
    """They drifted to the far right edge, where they read as belonging to
    the card rather than to the step.

    Asserted on the LAYOUT rather than on pixels: a widget inside a scroll
    area has no real geometry until the panel is shown, and the thing that
    actually went wrong was the order and the stretch, not the arithmetic.
    """
    from PySide6.QtWidgets import QLabel

    task = store.add_task(TaskItem(title="Rollout", checklist=[
        ChecklistItem(text="pull the drawings", estimate_min=15,
                      deadline="2026-10-16")]))
    panel = TasksPanel(store)
    panel._toggle_steps(task.id)
    panel.refresh()

    card = panel.scroller.box.itemAt(0).widget()
    steps = card.layout().itemAt(1).widget()          # the unfolded block
    row = steps.layout().itemAt(0).widget()           # the first step
    line = row.layout()

    texts = []
    for index in range(line.count()):
        item = line.itemAt(index)
        widget = item.widget()
        if widget is None:
            texts.append("<stretch>")
        elif isinstance(widget, QLabel):
            texts.append(widget.text())
        else:
            texts.append(type(widget).__name__)

    # tick, the step's words, then ITS chips, and only then the stretch that
    # pushes the leftovers away.
    assert texts == ["QCheckBox", "pull the drawings", "15m", "by Oct 16",
                     "<stretch>"]


def test_the_task_row_shows_all_three_of_its_buttons(store, qapp):
    """The clock and the delete button were being drawn with no room for
    their glyph and vanished entirely."""
    from PySide6.QtWidgets import QPushButton

    store.add_task(TaskItem(title="Fix the PO sheet"))
    panel = TasksPanel(store)
    panel.refresh()

    card = panel.scroller.box.itemAt(0).widget()
    buttons = card.findChildren(QPushButton)
    assert len(buttons) == 3
    for button in buttons:
        assert button.property("iconOnly") == "true" or button.text() == "Edit"


def test_every_assistant_header_is_the_same_row(store, qapp):
    """All three tabs open with the same header row, inset the same way, so
    they cannot drift apart. Its margins are the only thing keeping the last
    button off the window edge, now that the row has no fill of its own."""
    from PySide6.QtWidgets import QFrame

    from techdeck.ui.widgets.assistant_schedule import HEADER_MARGINS

    for panel in (SchedulePanel(store), TasksPanel(store), TimePanel(store)):
        first = panel.layout().itemAt(0).widget()
        assert isinstance(first, QFrame), type(panel).__name__
        assert first.objectName() == "assistantHeader", type(panel).__name__
        margins = first.layout().contentsMargins()
        got = (margins.left(), margins.top(), margins.right(), margins.bottom())
        assert got == HEADER_MARGINS, type(panel).__name__
        assert margins.right() > 0, type(panel).__name__


def test_the_header_row_is_not_painted(qapp):
    """A fill of its own made a full-width coloured band across the top of
    every tab: a seam where the page should just carry on behind the row,
    down to the cards. Only the cards get a surface."""
    from techdeck.ui.theme import THEMES
    from techdeck.ui.widgets.assistant_schedule import card_qss

    for name, palette in THEMES.items():
        sheet = card_qss(palette)
        assert "QFrame#assistantHeader" in sheet, name
        block = sheet.split("QFrame#assistantHeader", 1)[1].split("}", 1)[0]
        assert "transparent" in block, name
        assert "border: none" in block, name
        assert palette.surface.lower() not in block.lower(), name
