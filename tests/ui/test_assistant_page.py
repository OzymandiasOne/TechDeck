"""Assistant page widgets.

The engine is covered in tests/core; these tests cover the wiring that only
exists on the Qt side — the bullet editor's key handling, the chips reacting to
state, the terminal's HTML escaping, and the fact that typing a line actually
reaches the store and the transcript.
"""

from datetime import date, datetime

import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent

from techdeck.core.assistant.models import Note, TaskItem
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.widgets.assistant_notes import BulletEditor, NotesPanel
from techdeck.ui.widgets.assistant_schedule import SchedulePanel, TasksPanel
from techdeck.ui.widgets.assistant_terminal import ChipBar, CommandLine, TerminalView


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant")


def _press(widget, key, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


# ── bullet editor ────────────────────────────────────────────────────────────

def test_enter_continues_a_bullet(qapp):
    editor = BulletEditor()
    editor.setPlainText("- first item")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    _press(editor, Qt.Key.Key_Return)
    assert editor.toPlainText().splitlines()[-1] == "- "


def test_enter_keeps_the_nesting_level(qapp):
    editor = BulletEditor()
    editor.setPlainText("  - nested item")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    _press(editor, Qt.Key.Key_Return)
    assert editor.toPlainText().splitlines()[-1] == "  - "


def test_enter_on_an_empty_nested_bullet_steps_back_out(qapp):
    editor = BulletEditor()
    editor.setPlainText("    - ")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    _press(editor, Qt.Key.Key_Return)
    assert editor.toPlainText().splitlines()[-1] == "  - "


def test_enter_on_a_plain_line_is_a_normal_newline(qapp):
    editor = BulletEditor()
    editor.setPlainText("not a bullet")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    _press(editor, Qt.Key.Key_Return, text="\n")
    assert editor.toPlainText().count("\n") == 1


def test_tab_nests_and_shift_tab_un_nests(qapp):
    editor = BulletEditor()
    editor.setPlainText("- item")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    _press(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "  - item"
    _press(editor, Qt.Key.Key_Backtab)
    assert editor.toPlainText() == "- item"


def test_add_bullet_converts_the_current_line(qapp):
    editor = BulletEditor()
    editor.setPlainText("plain line")
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    editor.add_bullet()
    assert editor.toPlainText() == "- plain line"


# ── notes panel ──────────────────────────────────────────────────────────────

def test_notes_panel_lists_and_selects(qapp, store):
    store.add_note(Note(title="Gate code", body="- 4417"))
    panel = NotesPanel(store)
    assert panel.list.count() == 1
    assert panel.editor.toPlainText() == "- 4417"


def test_editing_a_note_saves_it(qapp, store):
    note = store.add_note(Note(title="Gate code", body=""))
    panel = NotesPanel(store)
    panel.editor.setPlainText("- 4417")
    panel._save_current()
    assert store.get_note(note.id).body == "- 4417"


def test_switching_notes_flushes_the_pending_save(qapp, store):
    first = store.add_note(Note(title="first"))
    store.add_note(Note(title="second"))
    panel = NotesPanel(store)
    panel.select_note(first.id)
    panel.editor.setPlainText("typed but not yet autosaved")
    panel._flush()
    assert "typed but not yet autosaved" in store.get_note(first.id).body


def test_the_filter_narrows_the_list(qapp, store):
    store.add_note(Note(title="Gate code"))
    store.add_note(Note(title="Shutdown checklist"))
    panel = NotesPanel(store)
    panel.search.setText("gate")
    assert panel.list.count() == 1


# ── tasks panel ──────────────────────────────────────────────────────────────

def test_quick_add_parses_shorthand(qapp, store):
    panel = TasksPanel(store)
    panel.quick_add.setText("order the 4130 tube 20m urgent due today")
    panel._quick_add()
    task = store.tasks[0]
    assert task.title == "order the 4130 tube"
    assert task.priority == "critical"
    assert task.estimate_min == 20
    assert task.deadline == date.today().isoformat()


def test_tasks_panel_ranks_by_cost_of_delay(qapp, store):
    store.add_task(TaskItem(title="slow", priority="critical", estimate_min=180))
    store.add_task(TaskItem(title="fast", priority="high", estimate_min=15))
    panel = TasksPanel(store)
    assert [t.title for t in panel._visible_tasks()][0] == "fast"


def test_the_done_filter_shows_only_finished_work(qapp, store):
    open_task = store.add_task(TaskItem(title="open"))
    done_task = store.add_task(TaskItem(title="done"))
    store.set_done(done_task.id)
    panel = TasksPanel(store)
    panel._filter = "done"
    assert [t.title for t in panel._visible_tasks()] == ["done"]
    panel._filter = "open"
    assert [t.title for t in panel._visible_tasks()] == [open_task.title]


# ── schedule panel ───────────────────────────────────────────────────────────

def test_schedule_panel_is_calm_when_there_is_no_plan(qapp, store):
    panel = SchedulePanel(store)
    assert panel.range_label.text() == "No plan yet"
    assert not panel.export_btn.isEnabled()


def test_schedule_panel_renders_a_saved_plan(qapp, store):
    from techdeck.core.assistant.scheduler import ScheduleRequest, build_schedule
    store.add_task(TaskItem(title="Fix the PO sheet", estimate_min=45))
    plan = build_schedule(ScheduleRequest(
        tasks=store.open_tasks(), start_day=date(2026, 8, 11),
        end_day=date(2026, 8, 11), prefs=store.prefs, label="Today",
        now=datetime(2026, 8, 11, 6, 0)))
    store.add_schedule(plan)
    panel = SchedulePanel(store)
    assert panel.range_label.text() == "Today"
    assert panel.export_btn.isEnabled()


# ── terminal ─────────────────────────────────────────────────────────────────

def test_terminal_escapes_html_instead_of_rendering_it(qapp):
    view = TerminalView()
    view.append_line("user", "<b>not bold</b> & <script>")
    text = view.toPlainText()
    assert "<b>not bold</b>" in text
    assert "not bold" in text


def test_terminal_preserves_the_indentation_of_block_output(qapp):
    view = TerminalView()
    view.append_line("result", "Today\n  7:00 AM  • Fix the PO sheet")
    assert "  7:00 AM" in view.toPlainText()


def test_command_line_history_recall(qapp):
    line = CommandLine()
    sent = []
    line.submitted.connect(sent.append)
    line.field.setText("first")
    line._submit()
    line.field.setText("second")
    line._submit()
    assert sent == ["first", "second"]
    line._recall(-1)
    assert line.field.text() == "second"
    line._recall(-1)
    assert line.field.text() == "first"
    line._recall(1)
    assert line.field.text() == "second"


def test_command_line_ignores_blank_input(qapp):
    line = CommandLine()
    sent = []
    line.submitted.connect(sent.append)
    line.field.setText("   ")
    line._submit()
    assert sent == []


def test_chip_bar_emits_its_key(qapp):
    bar = ChipBar()
    fired = []
    bar.chip_clicked.connect(fired.append)
    bar.set_chips([("schedule", "Build a schedule", "tip")])
    bar._buttons[0].click()
    assert fired == ["schedule"]


def test_chip_bar_replaces_rather_than_appends(qapp):
    bar = ChipBar()
    bar.set_chips([("a", "A", ""), ("b", "B", "")])
    bar.set_chips([("c", "C", "")])
    assert [b.text() for b in bar._buttons] == ["C"]


# ── schedule wizard ──────────────────────────────────────────────────────────

def _wizard(store):
    from techdeck.ui.dialogs.schedule_wizard import ScheduleWizard
    return ScheduleWizard(store)


def test_wizard_loads_the_open_backlog(qapp, store):
    store.add_task(TaskItem(title="Fix the PO sheet", estimate_min=45))
    store.add_task(TaskItem(title="Call Dan", estimate_min=90))
    wizard = _wizard(store)
    assert wizard.table.rowCount() == 2
    assert len(wizard._checked_tasks()) == 2


def test_wizard_starts_with_one_empty_row_when_there_is_nothing(qapp, store):
    wizard = _wizard(store)
    assert wizard.table.rowCount() == 1
    assert wizard._checked_tasks() == []          # blank titles don't count


def test_typing_shorthand_into_the_task_cell_fills_the_row(qapp, store):
    wizard = _wizard(store)
    wizard.table.item(0, 0).setText("fix the PO sheet 45m urgent")
    qapp.processEvents()
    task = wizard._row_tasks[0]
    assert task.title == "fix the PO sheet"
    assert task.priority == "critical"
    assert task.estimate_min == 45


def test_removing_a_row_keeps_the_remaining_rows_wired_to_themselves(qapp, store):
    """Every cell widget's callback captured its row index; deleting a row
    shifts them all, so a stale binding would write one task's edits onto
    its neighbour."""
    for title in ("first", "second", "third"):
        store.add_task(TaskItem(title=title, estimate_min=30))
    wizard = _wizard(store)
    wizard._remove_row(0)
    qapp.processEvents()

    assert [t.title for t in wizard._row_tasks] == ["second", "third"]
    # Edit the LAST row's estimate; it must land on "third", not "second".
    wizard.table.cellWidget(1, 2).setValue(75)
    qapp.processEvents()
    assert wizard._row_tasks[1].estimate_min == 75
    assert wizard._row_tasks[0].estimate_min == 30


def test_untick_excludes_a_task_from_the_plan_but_not_the_backlog(qapp, store):
    store.add_task(TaskItem(title="keep", estimate_min=30))
    store.add_task(TaskItem(title="skip", estimate_min=30))
    wizard = _wizard(store)
    row = next(r for r in range(wizard.table.rowCount())
               if wizard.table.item(r, 0).text() == "skip")
    wizard.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
    assert [t.title for t in wizard._checked_tasks()] == ["keep"]
    assert len(store.tasks) == 2


def test_a_due_cell_normalizes_to_the_date_it_resolved_to(qapp, store):
    store.add_task(TaskItem(title="a", estimate_min=30))
    wizard = _wizard(store)
    wizard.table.cellWidget(0, 3).setText("tomorrow")
    wizard._normalize_due(0)
    from datetime import date, timedelta
    expected = (date.today() + timedelta(days=1)).isoformat()
    assert wizard.table.cellWidget(0, 3).text() == expected
    assert wizard._row_tasks[0].deadline == expected


def test_generating_saves_the_plan_and_the_tasks(qapp, store):
    wizard = _wizard(store)
    wizard.table.item(0, 0).setText("fix the PO sheet 45m")
    qapp.processEvents()
    assert wizard._generate() is True
    assert store.latest_schedule() is not None
    assert [t.title for t in store.tasks] == ["fix the PO sheet"]


def test_stepping_back_from_the_review_discards_the_draft_plan(qapp, store):
    wizard = _wizard(store)
    wizard.table.item(0, 0).setText("fix the PO sheet 45m")
    qapp.processEvents()
    wizard._next()          # step 1 -> 2
    wizard._next()          # step 2 -> build + step 3
    assert store.latest_schedule() is not None
    wizard._back()
    assert store.latest_schedule() is None


def test_pasted_lines_become_rows(qapp, store):
    from techdeck.ui.dialogs.schedule_wizard import PasteTasksDialog
    dialog = PasteTasksDialog()
    dialog.editor.setPlainText("- fix the PO sheet 45m urgent\n2. call Dan | high | 1h")
    tasks = dialog.parsed_tasks()
    assert [t.title for t in tasks] == ["fix the PO sheet", "call Dan"]
    assert tasks[0].priority == "critical"
    assert tasks[1].estimate_min == 60


def test_the_wizard_persists_advanced_preferences(qapp, store):
    wizard = _wizard(store)
    wizard.buffer.setValue(30)
    wizard.table.item(0, 0).setText("a 30m")
    qapp.processEvents()
    wizard._generate()
    assert store.prefs.buffer_pct == 30


# ── the page itself ──────────────────────────────────────────────────────────

@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    """A real AssistantPage pointed at a throwaway store.

    (The session conftest already redirects %LOCALAPPDATA%, so this is belt and
    braces — but a test that writes into another test's store is a flake
    waiting to happen.)
    """
    import techdeck.core.assistant.store as store_module
    original = store_module.AssistantStore.__init__
    monkeypatch.setattr(
        store_module.AssistantStore, "__init__",
        lambda self, base_dir=None: original(self, tmp_path / "assistant"))
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.assistant_page import AssistantPage
    return AssistantPage(SettingsManager())


def test_typing_is_answered_and_kept_but_never_filed(page):
    page.submit("this rev C is a nightmare")
    assert page.store.tasks == []
    assert page.store.notes == []
    assert "this rev C is a nightmare" in page.terminal.toPlainText()
    # And it survives the session: the transcript is on disk, not just on screen.
    assert any(m.role == "user" for m in page.store.load_chat())


def test_an_explicit_task_command_does_file(page):
    page.submit("/task fix the PO sheet 45m urgent")
    assert page.store.tasks[0].title == "fix the PO sheet"


def test_the_make_that_a_task_chip_appears_only_for_actionable_lines(page):
    page.submit("call Dan about the rev C")
    assert "↑ Make that a task" in [b.text() for b in page.chips._buttons]

    page.submit("this printer is garbage")
    assert "↑ Make that a task" not in [b.text() for b in page.chips._buttons]


def test_pressing_the_chip_is_what_actually_files_it(page):
    page.submit("call Dan about the rev C")
    assert page.store.tasks == []
    chip = next(b for b in page.chips._buttons if b.text() == "↑ Make that a task")
    chip.click()
    assert page.store.tasks[0].title == "call Dan about the rev C"


def test_a_command_that_asks_for_a_tab_switch_gets_one(page):
    page.submit("/notes")
    from techdeck.ui.pages.assistant_page import TAB_NOTES
    assert page.tab_bar.currentIndex() == TAB_NOTES


def test_chips_adapt_to_whether_there_is_a_plan(page):
    labels = [b.text() for b in page.chips._buttons]
    assert "What's on today?" not in labels

    from techdeck.core.assistant.models import Schedule
    page.store.add_schedule(Schedule(range_label="Today"))
    page._refresh_chips()
    labels = [b.text() for b in page.chips._buttons]
    assert "What's on today?" in labels
    assert "Replan from now" in labels


def test_a_parser_crash_is_reported_not_fatal(page, monkeypatch):
    """A bad line must never take the page down with it."""
    def boom(*_args, **_kwargs):
        raise ValueError("kaboom")
    monkeypatch.setattr(page.brain, "handle", boom)
    page.submit("anything")
    assert "kaboom" in page.terminal.toPlainText()


def test_clear_wipes_the_view_and_the_stored_history(page):
    # Not "fix the PO sheet" — the greeting uses that as its example.
    page.submit("order the 4130 tube 20m")
    page.submit("/clear")
    assert "4130 tube" not in page.terminal.toPlainText()
    assert [m.role for m in page.store.load_chat()] == ["deck"]   # the greeting
