"""Assistant page widgets.

The engine is covered in tests/core; these tests cover the wiring that only
exists on the Qt side, the bullet editor's key handling, the chips reacting to
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
    braces, but a test that writes into another test's store is a flake
    waiting to happen.)
    """
    import techdeck.core.assistant.store as store_module
    original = store_module.AssistantStore.__init__
    monkeypatch.setattr(
        store_module.AssistantStore, "__init__",
        lambda self, base_dir=None: original(self, tmp_path / "assistant"))
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.assistant_page import AssistantPage
    built = AssistantPage(SettingsManager())
    # Answer synchronously here. The real page waits a beat before Woogy
    # speaks; a test asserting straight after submit() would otherwise be
    # racing a QTimer.
    built.REPLY_DELAY_MS = 0
    return built


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
    assert page.tabs.current() == TAB_NOTES
    assert page.stack.currentWidget() is page.notes_panel


def test_personal_notes_sits_apart_on_the_right(page):
    """Terminal / Schedule / Tasks are the working loop; Personal Notes is a
    different activity and is deliberately separated from them."""
    from techdeck.ui.pages.assistant_page import (
        TAB_NOTES, TAB_SCHEDULE, TAB_TASKS, TAB_TERMINAL)
    strip = page.tabs
    left = [strip._left.itemAt(i).widget().text()
            for i in range(strip._left.count())]
    right = [strip._right.itemAt(i).widget().text()
             for i in range(strip._right.count())]
    assert left == ["Terminal", "Schedule", "Tasks"]
    assert right == ["Personal Notes"]


def test_only_one_tab_is_ever_selected_across_both_groups(page):
    """The reason this is buttons and not two QTabBars: a QTabBar always keeps
    one of its own tabs selected, so a split row would show two."""
    from techdeck.ui.pages.assistant_page import TAB_NOTES, TAB_TASKS
    page._show_tab(TAB_NOTES)
    checked = [b for b in page.tabs._buttons.values() if b.isChecked()]
    assert len(checked) == 1 and checked[0].text() == "Personal Notes"

    page._show_tab(TAB_TASKS)
    checked = [b for b in page.tabs._buttons.values() if b.isChecked()]
    assert len(checked) == 1 and checked[0].text() == "Tasks"


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
    page.submit("order the 4130 tube 20m")
    page.submit("/clear")
    assert "4130 tube" not in page.terminal.toPlainText()
    assert page.store.load_chat() == []


def test_a_fresh_page_opens_empty_with_no_greeting(page):
    """No explainer at the top of the box. It gets read once, ignored forever,
    and then sits there being wrong the moment the behaviour changes."""
    assert page.terminal.toPlainText().strip() == ""
    assert page.store.load_chat() == []


def test_history_comes_back_with_no_session_divider(page, tmp_path):
    page.submit("order the 4130 tube 20m")
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.assistant_page import AssistantPage
    reopened = AssistantPage(SettingsManager())
    text = reopened.terminal.toPlainText()
    assert "order the 4130 tube" in text
    assert "session" not in text.lower()


# ── chat layout: avatars and names ───────────────────────────────────────────

def test_woogy_gets_a_round_avatar_from_his_own_sprite(qapp):
    from techdeck.ui.widgets.assistant_terminal import AVATAR_PX, woogy_avatar
    pixmap = woogy_avatar()
    assert not pixmap.isNull()
    assert pixmap.size().width() == AVATAR_PX
    image = pixmap.toImage()
    # Round, so the corners must be transparent and the middle must not be.
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(AVATAR_PX // 2, AVATAR_PX // 2).alpha() > 0


@pytest.mark.parametrize("name,expected", [
    ("Ada Sparks", "AS"),
    ("ASparks", "AS"),
    ("fern.tucker", "FT"),
    ("woogy", "WO"),
    ("", "?"),
])
def test_initials(name, expected):
    from techdeck.ui.widgets.assistant_terminal import _initials
    assert _initials(name) == expected


def test_the_speaker_is_named_woogy_not_a_symbol(qapp):
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    view = TerminalView()
    view.append_line("deck", "Heard.")
    text = view.toPlainText()
    assert "Woogy" in text
    assert "\u25c6" not in text            # the old diamond prefix


def test_the_user_line_is_named_after_the_user(qapp):
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    view = TerminalView()
    view.set_identity("Ada Sparks")
    view.append_line("user", "morning")
    assert "Ada Sparks" in view.toPlainText()


def test_consecutive_lines_from_one_speaker_share_a_head(qapp):
    """Teams groups a run of messages under one avatar. A reply plus its
    footnote should be one block, not two heads."""
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    view = TerminalView()
    view.append_line("deck", "Heard.")
    view.append_line("deck", "Still here.")
    assert view.toPlainText().count("Woogy") == 1


def test_a_system_note_attaches_to_the_message_above_it(qapp):
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    view = TerminalView()
    view.append_line("deck", "Heard.")
    view.append_line("system", "(nothing here gets saved)")
    text = view.toPlainText()
    assert text.count("Woogy") == 1
    assert "nothing here gets saved" in text


def test_clearing_resets_the_grouping(qapp):
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    view = TerminalView()
    view.append_line("deck", "one")
    view.clear()
    view.append_line("deck", "two")
    assert "Woogy" in view.toPlainText()


# ── reminders ────────────────────────────────────────────────────────────────

def test_the_reminder_button_reports_the_current_state(page):
    from techdeck.ui.notifier import DesktopNotifier
    label = page.reminders_btn.text()
    if DesktopNotifier.available():
        assert label == "Reminders on"
        page.submit("/remind off")
        assert page.reminders_btn.text() == "Reminders off"
    else:
        assert label == "Reminders unavailable"


def test_remind_command_persists(page):
    page.submit("/remind 25")
    assert page.store.notify.lead_minutes == 25
    assert page.store.notify.enabled is True
    page.submit("/remind off")
    assert page.store.notify.enabled is False


def test_a_reminder_is_only_ever_sent_once(page, monkeypatch):
    """The page must record what it sent, or every 30-second tick re-fires the
    same popup."""
    from datetime import datetime, timedelta
    from techdeck.core.assistant.models import TaskItem
    from techdeck.core.assistant.scheduler import ScheduleRequest, build_schedule

    sent = []
    monkeypatch.setattr(page.notifier, "notify",
                        lambda title, body, seconds=12: sent.append(title) or True)

    soon = datetime.now() + timedelta(minutes=2)
    task = TaskItem(title="Fix the PO sheet", estimate_min=30,
                    fixed_start=soon.replace(second=0, microsecond=0).isoformat())
    page.store.add_task(task)
    plan = build_schedule(ScheduleRequest(
        tasks=[task], start_day=soon.date(), end_day=soon.date(),
        prefs=page.store.prefs))
    page.store.add_schedule(plan)
    page.store.notify.enabled = True
    page.store.notify.lead_minutes = 30
    page.store.notify.quiet_outside_hours = False
    page.store.notify.daily_digest = False      # keep the test to one signal
    page.store.notify.overdue = False

    page._check_reminders()
    page._check_reminders()
    assert sent == ["Fix the PO sheet"]


def test_a_broken_reminder_check_never_takes_the_page_down(page, monkeypatch):
    import techdeck.ui.pages.assistant_page as module
    monkeypatch.setattr(module, "due_notifications",
                        lambda **_kw: (_ for _ in ()).throw(RuntimeError("nope")))
    page._check_reminders()          # must not raise


def test_avatars_survive_a_clear(qapp):
    """QTextEdit.clear() empties the document's RESOURCE cache along with its
    text. Without re-registering, every message after /clear rendered a
    broken-image icon where the face should be."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    from techdeck.ui.widgets.assistant_terminal import TerminalView

    view = TerminalView()
    view.append_line("deck", "before")
    view.clear()
    view.append_line("deck", "after")

    for name in ("woogy", "user"):
        resource = view.document().resource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(f"techdeck://avatar/{name}"))
        assert resource is not None and not resource.isNull(), name


def test_the_clear_command_leaves_working_avatars(page):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument

    page.submit("/clear")
    page.submit("morning")
    resource = page.terminal.document().resource(
        QTextDocument.ResourceType.ImageResource,
        QUrl("techdeck://avatar/woogy"))
    assert resource is not None and not resource.isNull()


# ── profile picture ──────────────────────────────────────────────────────────

def _square_png(path, colour="#FF00AA", size=400):
    from PySide6.QtGui import QPixmap, QColor
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(colour))
    pixmap.save(str(path), "PNG")
    return path


def test_a_chosen_picture_replaces_the_initials(qapp, tmp_path):
    from techdeck.core.settings import SettingsManager
    from techdeck.ui import avatars

    settings = SettingsManager(tmp_path / "cfg")
    before = avatars.user_avatar(settings, "Ada Sparks", "#2878A8", 48)

    picture = avatars.normalise_for_storage(_square_png(tmp_path / "me.png"))
    picture.save(str(settings.avatar_path()), "PNG")
    after = avatars.user_avatar(settings, "Ada Sparks", "#2878A8", 48)

    assert settings.has_avatar()
    assert before.toImage() != after.toImage()
    # Centre pixel is the picture's colour, not the accent disc.
    assert after.toImage().pixelColor(24, 24).name().lower() == "#ff00aa"


def test_the_picture_is_still_a_circle(qapp, tmp_path):
    from techdeck.core.settings import SettingsManager
    from techdeck.ui import avatars

    settings = SettingsManager(tmp_path / "cfg")
    avatars.normalise_for_storage(
        _square_png(tmp_path / "me.png")).save(str(settings.avatar_path()), "PNG")
    image = avatars.user_avatar(settings, "A B", "#2878A8", 48).toImage()
    assert image.pixelColor(0, 0).alpha() == 0        # corner cut away
    assert image.pixelColor(24, 24).alpha() > 0


def test_a_big_photo_is_shrunk_before_it_is_stored(qapp, tmp_path):
    """A 12 MP phone photo has no business living in the settings folder."""
    from techdeck.ui import avatars
    big = avatars.normalise_for_storage(
        _square_png(tmp_path / "huge.png", size=4000))
    assert max(big.width(), big.height()) == avatars.STORED_AVATAR_PX


def test_a_file_that_is_not_an_image_is_refused(qapp, tmp_path):
    from techdeck.ui import avatars
    dud = tmp_path / "notes.txt"
    dud.write_text("this is not a picture", encoding="utf-8")
    assert avatars.normalise_for_storage(dud) is None


def test_removing_the_picture_falls_back_to_initials(qapp, tmp_path):
    from techdeck.core.settings import SettingsManager
    from techdeck.ui import avatars

    settings = SettingsManager(tmp_path / "cfg")
    avatars.normalise_for_storage(
        _square_png(tmp_path / "me.png")).save(str(settings.avatar_path()), "PNG")
    assert settings.has_avatar()

    assert settings.clear_avatar() is True
    assert not settings.has_avatar()
    assert settings.clear_avatar() is False          # already gone, no error

    fallback = avatars.user_avatar(settings, "Ada Sparks", "#2878A8", 48)
    assert fallback.toImage() == avatars.initials_avatar(
        "Ada Sparks", "#2878A8", 48).toImage()


def test_a_picture_deleted_behind_our_back_falls_back_quietly(qapp, tmp_path):
    from techdeck.core.settings import SettingsManager
    from techdeck.ui import avatars

    settings = SettingsManager(tmp_path / "cfg")
    avatars.normalise_for_storage(
        _square_png(tmp_path / "me.png")).save(str(settings.avatar_path()), "PNG")
    settings.avatar_path().unlink()
    assert not avatars.user_avatar(settings, "A B", "#2878A8", 48).isNull()


def test_the_picture_lives_beside_settings_not_inside_it(tmp_path):
    """settings.json is rewritten in full on every ticket and tile change;
    carrying a photo through all of those is a cost paid forever."""
    import json
    from techdeck.core.settings import SettingsManager
    settings = SettingsManager(tmp_path / "cfg")
    settings.update_user_data(name="Anthony")
    document = json.loads(settings.settings_file.read_text(encoding="utf-8"))
    assert "avatar.png" == settings.avatar_path().name
    assert "png" not in json.dumps(document).lower()


# ── clicking your face ───────────────────────────────────────────────────────

def test_your_avatar_links_to_my_account_and_woogys_does_not(qapp):
    from techdeck.ui.widgets.assistant_terminal import ACCOUNT_URL, TerminalView
    view = TerminalView()
    view.append_line("user", "morning")
    view.append_line("deck", "Woogy is listening.")
    html = view.toHtml()
    assert ACCOUNT_URL in html
    # One link per user message, not one per avatar in the document.
    assert html.count(ACCOUNT_URL) == 2          # the picture and the name


def test_clicking_your_avatar_asks_the_page_to_open_my_account(qapp):
    from techdeck.ui.widgets.assistant_terminal import ACCOUNT_URL, TerminalView
    view = TerminalView()
    fired = []
    view.internal_link_clicked.connect(fired.append)
    view._activate_anchor(ACCOUNT_URL)
    assert fired == [ACCOUNT_URL]


def test_an_external_link_still_goes_to_the_os(qapp, monkeypatch):
    from techdeck.ui.widgets.assistant_terminal import TerminalView
    opened = []
    monkeypatch.setattr(
        "techdeck.ui.widgets.assistant_terminal.QDesktopServices.openUrl",
        lambda url: opened.append(url.toString()))
    view = TerminalView()
    fired = []
    view.internal_link_clicked.connect(fired.append)
    view._activate_anchor("https://example.com")
    assert opened == ["https://example.com"]
    assert fired == []


def test_the_page_navigates_on_an_account_link(page, monkeypatch):
    from techdeck.ui.widgets.assistant_terminal import ACCOUNT_URL
    went = []
    monkeypatch.setattr(page, "_go_to_page", went.append)
    page._on_internal_link(ACCOUNT_URL)
    assert went == ["account"]


# ── the My Account identity card ─────────────────────────────────────────────

@pytest.fixture
def account(qapp, tmp_path):
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.account_page import AccountPage
    settings = SettingsManager(tmp_path / "cfg")
    settings.update_user_data(name="Ada Sparks",
                             email="ada.sparks@example.com")
    return AccountPage(settings)


def test_the_card_shows_the_name_and_email(account):
    assert account.identity_name.text() == "Ada Sparks"
    assert account.identity_email.text() == "ada.sparks@example.com"


def test_remove_only_appears_once_there_is_a_picture(account, tmp_path):
    """The card stays two lines until it has a reason to be three."""
    from techdeck.ui import avatars
    # isHidden(), not isVisible(): the page itself is never shown in a test,
    # so isVisible() is False regardless of what we asked for.
    assert account.clear_avatar_btn.isHidden()

    avatars.normalise_for_storage(
        _square_png(tmp_path / "me.png")
    ).save(str(account.settings.avatar_path()), "PNG")
    account._refresh_avatar()
    assert not account.clear_avatar_btn.isHidden()

    account._clear_avatar()
    assert account.clear_avatar_btn.isHidden()


def test_renaming_yourself_updates_the_card(account):
    account.name_input.setText("Woogy Woogerson")
    account.settings.update_user_data(name="Woogy Woogerson")
    account._refresh_avatar()
    assert account.identity_name.text() == "Woogy Woogerson"


def test_the_avatar_is_the_button(qapp):
    """No "Choose image…" button any more: the picture is the affordance."""
    from techdeck.ui.widgets.avatar_button import AvatarButton
    button = AvatarButton(72)
    fired = []
    button.clicked.connect(lambda: fired.append(True))
    button.clicked.emit()
    assert fired == [True]
    assert button.toolTip() == "Change or add profile picture"


def test_the_camera_only_shows_on_hover(qapp):
    from techdeck.ui.widgets.avatar_button import AvatarButton
    from techdeck.ui import avatars

    button = AvatarButton(72)
    button.set_pixmap(avatars.initials_avatar("A B", "#2878A8", 72))

    resting = button.grab().toImage()
    button._hover = True
    hovered = button.grab().toImage()
    assert resting != hovered

    # The scrim is a CIRCLE: the avatar leaves its corners empty and the hover
    # state must not paint over them. (A widget grab is opaque, so compare the
    # corner across the two states rather than looking for transparency.)
    assert hovered.pixelColor(1, 1) == resting.pixelColor(1, 1)
    # ...while the disc itself got darker.
    assert (hovered.pixelColor(36, 10).lightness()
            < resting.pixelColor(36, 10).lightness())


def test_the_input_hint_is_italic_only_while_it_is_empty(qapp):
    """Styling the field italic outright would italicise what the user TYPES
    as well, which reads as a rendering fault rather than a hint."""
    from techdeck.ui.widgets.assistant_terminal import CommandLine
    line = CommandLine()
    assert "/help" in line.field.placeholderText()
    assert line.field.font().italic()

    line.field.setText("fix the PO sheet")
    assert not line.field.font().italic()

    line.field.clear()
    assert line.field.font().italic()


def test_woogy_waits_a_beat_before_answering(qapp, page):
    """Your line lands at once; his comes after a pause. An instant reply
    reads as a lookup table rather than somebody on the other end."""
    from techdeck.ui.pages.assistant_page import _DEFAULT_REPLY_DELAY_MS
    assert _DEFAULT_REPLY_DELAY_MS > 0

    page.REPLY_DELAY_MS = _DEFAULT_REPLY_DELAY_MS
    page.submit("morning")

    text = page.terminal.toPlainText()
    assert "morning" in text          # yours is there immediately
    assert "Woogy" not in text        # his is not

    # ...and arrives once the timer fires.
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(_DEFAULT_REPLY_DELAY_MS + 250, loop.quit)
    loop.exec()
    assert "Woogy" in page.terminal.toPlainText()


def test_the_work_happens_immediately_even_though_the_reply_waits(qapp, page):
    """Only the RENDERING waits. Doing the work late would let a fast typist
    reorder their own conversation."""
    from techdeck.ui.pages.assistant_page import _DEFAULT_REPLY_DELAY_MS
    page.REPLY_DELAY_MS = _DEFAULT_REPLY_DELAY_MS
    page.submit("/task fix the PO sheet 45m")
    assert [t.title for t in page.store.tasks] == ["fix the PO sheet"]
