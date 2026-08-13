"""The Assistant page, TechDeck's personal organizer.

A terminal with tabs above it and a command line below. The terminal is where
you talk to it; the other tabs are where the results live:

    Terminal        the conversation, kept across sessions
    Schedule        the generated plan, tickable as you work through it
    Personal Notes  notes to yourself, nested bullets and all
    Tasks           the backlog everything else is built from

The command line and the word-bubble chips sit **below the tab stack**, so they
stay reachable no matter which tab is showing, you're never more than one line
of typing away from capturing something.

All the thinking happens in ``techdeck.core.assistant``; this module is wiring
and layout.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QFrame, QFileDialog, QMessageBox, QPushButton,
)
from PySide6.QtCore import Qt, QTimer

from techdeck.core.assistant.commands import (
    ACT_CLEAR, ACT_EDIT_NOTE, ACT_EXPORT, ACT_GOTO, ACT_OPEN_WIZARD,
    AssistantBrain, Reply,
)
from techdeck.core.assistant.models import ChatMessage
from techdeck.core.assistant.notifier import due_notifications
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.notifier import DesktopNotifier
from techdeck.core.settings import SettingsManager
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.widgets.assistant_terminal import (
    ACCOUNT_URL, ChipBar, CommandLine, TabStrip, TerminalView,
)
from techdeck.ui.widgets.assistant_notes import NotesPanel
from techdeck.ui.widgets.assistant_schedule import SchedulePanel, TasksPanel

logger = logging.getLogger(__name__)

TAB_TERMINAL, TAB_SCHEDULE, TAB_NOTES, TAB_TASKS = range(4)
_TAB_KEYS = {"terminal": TAB_TERMINAL, "schedule": TAB_SCHEDULE,
             "notes": TAB_NOTES, "tasks": TAB_TASKS}

# How much transcript to show on open. The file keeps far more; this is just
# what's worth scrolling through.
HISTORY_LINES = 300

# How often to look for a reminder that has come due. Thirty seconds is fine
# grained enough that a "10 minutes before" reminder is never more than half a
# minute late, and cheap enough to ignore: the check is a list comprehension
# over one saved plan.
REMINDER_TICK_MS = 30_000

# A full second between your line landing and Woogy answering. An instant reply
# reads as a lookup table; a pause reads as somebody on the other end who had
# to read it first.
_DEFAULT_REPLY_DELAY_MS = 1000

# No greeting, and no session divider. The terminal opens on whatever you last
# said and nothing else. An explainer at the top of a chat box is read once,
# ignored forever, and then sits there being wrong the moment the behaviour
# changes; the chips and /help carry the same information on demand.


class AssistantPage(QWidget, ThemeAware):
    """The whole page. Owns one store, one brain, and four panels."""

    # Overridable so tests can run the reply synchronously. Zero means "now",
    # not "on the next event-loop turn", so a test can assert straight after
    # submit() without pumping timers.
    REPLY_DELAY_MS = _DEFAULT_REPLY_DELAY_MS

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = AssistantStore()
        # Professional theme mutes the goblin, a client demo gets plain
        # acknowledgements, not a feral terminal creature.
        self.brain = AssistantBrain(
            self.store, professional=settings.is_professional())
        # Set when the last thing said could plausibly be a task, so the chip
        # row can offer to file it. Nothing is ever filed off this alone.
        self._can_promote = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(10)

        # ── header ───────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("Assistant")
        self.title.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.subtitle = QLabel(
            "Notes, tasks, and a schedule that actually fits the day.")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)

        self.reminders_btn = QPushButton()
        self.reminders_btn.setMinimumHeight(30)
        self.reminders_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reminders_btn.clicked.connect(self._open_reminder_settings)
        header.addWidget(self.reminders_btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)

        # ── tabs ─────────────────────────────────────────────────────────────
        # Terminal / Schedule / Tasks are the working loop and sit together on
        # the left. Personal Notes is a different activity, so it sits apart on
        # the right rather than being a fourth thing to scan past.
        self.tabs = TabStrip()
        self.tabs.add_tab(TAB_TERMINAL, "Terminal")
        self.tabs.add_tab(TAB_SCHEDULE, "Schedule")
        self.tabs.add_tab(TAB_TASKS, "Tasks")
        self.tabs.add_tab(TAB_NOTES, "Personal Notes", right=True)
        self.tabs.tab_selected.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)

        # ── panels ───────────────────────────────────────────────────────────
        self.terminal = TerminalView(settings=settings)
        self.terminal.set_identity(self._display_name())
        self.terminal.internal_link_clicked.connect(self._on_internal_link)

        terminal_page = QWidget()
        terminal_box = QVBoxLayout(terminal_page)
        terminal_box.setContentsMargins(0, 0, 0, 0)
        terminal_box.addWidget(self.terminal)

        self.schedule_panel = SchedulePanel(self.store)
        self.schedule_panel.rebuild_requested.connect(self.open_wizard)
        self.schedule_panel.export_requested.connect(self._export)
        self.schedule_panel.changed.connect(self._on_data_changed)

        self.notes_panel = NotesPanel(self.store)
        self.notes_panel.changed.connect(self._on_data_changed)

        self.tasks_panel = TasksPanel(self.store)
        self.tasks_panel.changed.connect(self._on_data_changed)
        self.tasks_panel.schedule_requested.connect(self.open_wizard)

        self.panel = QFrame()
        self.panel.setObjectName("assistantPanel")
        panel_box = QVBoxLayout(self.panel)
        panel_box.setContentsMargins(12, 12, 12, 12)

        self.stack = QStackedWidget()
        self.stack.addWidget(terminal_page)
        self.stack.addWidget(self.schedule_panel)
        self.stack.addWidget(self.notes_panel)
        self.stack.addWidget(self.tasks_panel)
        # A hidden panel (the wide schedule table) must not floor the window's
        # minimum width, same rule every stacked host in TechDeck follows.
        from techdeck.ui.utils import limit_min_size_to_current_page
        limit_min_size_to_current_page(self.stack)
        panel_box.addWidget(self.stack)
        outer.addWidget(self.panel, 1)

        # ── chips + command line ─────────────────────────────────────────────
        self.chips = ChipBar()
        self.chips.chip_clicked.connect(self._on_chip)
        outer.addWidget(self.chips)

        self.command_line = CommandLine()
        self.command_line.submitted.connect(self.submit)
        outer.addWidget(self.command_line)

        # ── reminders ────────────────────────────────────────────────────────
        self.notifier = DesktopNotifier(self)
        self.notifier.activated.connect(self._on_notification_clicked)
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(REMINDER_TICK_MS)
        self._reminder_timer.timeout.connect(self._check_reminders)

        self.setup_theme_awareness()
        self._load_history()
        self._refresh_chips()
        self._apply_reminder_prefs()

    def _display_name(self) -> str:
        """Whose initials go on the avatar: the name from My Account if it's
        been filled in, otherwise the Windows login."""
        import os
        data = self.settings.get_user_data() or {}
        return (str(data.get("name") or "").strip()
                or str(data.get("username") or "").strip()
                or os.environ.get("USERNAME", "You"))

    # ── history ──────────────────────────────────────────────────────────────

    def _load_history(self):
        messages = self.store.load_chat(HISTORY_LINES)
        for message in messages:
            self.terminal.append_line(message.role, message.text)
        self.command_line.seed_history(
            [m.text for m in messages if m.role == "user"])

    def _record(self, role: str, text: str):
        self.store.append_chat(ChatMessage(role=role, text=text))

    # ── input ────────────────────────────────────────────────────────────────

    def submit(self, text: str):
        """Run one line through the brain and apply whatever comes back."""
        self.terminal.append_line("user", text)
        self._record("user", text)
        self._show_tab(TAB_TERMINAL)

        try:
            # Handled immediately, shown after a beat. Doing the WORK late
            # would let a fast typist reorder their own conversation; only the
            # rendering waits.
            reply = self.brain.handle(text)
        except Exception as exc:      # never let a parse bug eat the page
            message = f"Something went wrong handling that: {exc}"
            self.terminal.append_line("error", message)
            self._record("error", message)
            return

        if self.REPLY_DELAY_MS > 0:
            QTimer.singleShot(self.REPLY_DELAY_MS, lambda: self._apply(reply))
        else:
            self._apply(reply)

    def _apply(self, reply: Reply):
        for role, line in reply.lines:
            self.terminal.append_line(role, line)
            self._record(role, line)

        self._can_promote = reply.offer_task
        if reply.dirty:
            self._on_data_changed()

        action = reply.action
        if action == ACT_OPEN_WIZARD:
            self.open_wizard(reply.payload.get("range", ""))
        elif action == ACT_GOTO:
            self._show_tab(_TAB_KEYS.get(reply.payload.get("tab", ""),
                                         TAB_TERMINAL))
        elif action == ACT_EXPORT:
            self._export(reply.payload.get("format", "md"))
        elif action == ACT_CLEAR:
            self.terminal.clear()
            self.store.clear_chat()
        elif action == ACT_EDIT_NOTE:
            note_id = reply.payload.get("note_id")
            self.notes_panel.refresh()
            self._show_tab(TAB_NOTES)
            if note_id:
                self.notes_panel.select_note(note_id)

        self._refresh_chips()

    # ── chips ────────────────────────────────────────────────────────────────

    def _refresh_chips(self):
        """Chips follow the state of the desk: no plan yet means the planner is
        the only thing worth offering; once there is one, "what's on today" and
        "replan" earn their place."""
        has_plan = self.store.latest_schedule() is not None
        open_count = len(self.store.open_tasks())

        chips = []
        # Offered only when the last thing said could plausibly be a job, and
        # only ever as an offer, this is the one route from talking to filing,
        # and the user has to take it deliberately.
        if self._can_promote:
            chips.append(("promote", "↑ Make that a task",
                          "File the last thing you said as a task"))
        chips.append(("schedule", "Build a schedule",
                      "Walk through building a time-blocked plan"))
        if has_plan:
            chips.append(("today", "What's on today?",
                          "Show today's blocks from the saved plan"))
            chips.append(("replan", "Replan from now",
                          "Rebuild the plan starting at this minute"))
        chips.append(("note", "Quick note", "Start a note to yourself"))
        chips.append(("task", "Add a task", "Capture something to do"))
        if open_count:
            chips.append(("tasks", f"My tasks ({open_count})",
                          "See everything still open"))
        chips.append(("help", "What can you do?", "Show the command list"))
        self.chips.set_chips(chips)

    def _on_chip(self, key: str):
        if key == "promote":
            # `/task` with no argument files the last thing said.
            self.submit("/task")
        elif key == "schedule":
            self.open_wizard()
        elif key == "today":
            self.submit("/today")
        elif key == "replan":
            self.submit("/replan")
        elif key == "note":
            self.submit("/note")
        elif key == "task":
            self._show_tab(TAB_TASKS)
            self.tasks_panel.quick_add.setFocus()
        elif key == "tasks":
            self.submit("/tasks")
            self._show_tab(TAB_TASKS)
        elif key == "help":
            self.submit("/help")

    # ── wizard ───────────────────────────────────────────────────────────────

    def open_wizard(self, preset_range: str = ""):
        from techdeck.ui.dialogs.schedule_wizard import ScheduleWizard
        wizard = ScheduleWizard(self.store, parent=self.window(),
                                preset_range=preset_range or "")
        if not wizard.exec():
            return
        schedule = wizard.result_schedule()
        self._on_data_changed()
        if schedule is None:
            return
        self.schedule_panel.show_schedule(schedule.id)
        self._show_tab(TAB_SCHEDULE)

        from techdeck.core.assistant.scheduler import summarize
        line = f"Built your plan for {schedule.range_label}."
        self.terminal.append_line("deck", line)
        self._record("deck", line)
        body = summarize(schedule)
        self.terminal.append_line("result", body)
        self._record("result", body)

    # ── export ───────────────────────────────────────────────────────────────

    def _export(self, fmt: str):
        from techdeck.core.assistant import exporters

        schedule = self.schedule_panel._schedule or self.store.latest_schedule()
        if schedule is None:
            QMessageBox.information(self, "Nothing to export",
                                    "Build a schedule first.")
            return

        stem = exporters.safe_filename(
            f"TechDeck plan {schedule.range_label}", "TechDeck plan")
        filters = {"ics": "Calendar file (*.ics)",
                   "md": "Markdown (*.md)",
                   "txt": "Text file (*.txt)"}
        default_dir = Path.home() / "Desktop"
        if not default_dir.exists():
            default_dir = Path.home()

        path, _chosen = QFileDialog.getSaveFileName(
            self.window(), "Save schedule",
            str(default_dir / f"{stem}.{fmt}"),
            filters.get(fmt, "All files (*.*)"))
        if not path:
            return

        if fmt == "ics":
            content = exporters.to_ics(schedule)
        elif fmt == "txt":
            content = exporters.to_text(schedule)
        else:
            content = exporters.to_markdown(schedule)

        try:
            # newline="" keeps the .ics CRLF line endings exactly as built.
            # Python would otherwise translate them to CRCRLF on Windows.
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except OSError as exc:
            QMessageBox.warning(self, "Couldn't save",
                                f"Saving to that location failed:\n\n{exc}")
            return

        message = f"Saved to {path}"
        self.terminal.append_line("system", message)
        self._record("system", message)
        if fmt == "ics":
            hint = ("Double-click the .ics to drop these blocks onto your "
                    "Outlook calendar.")
            self.terminal.append_line("system", hint)
            self._record("system", hint)

    # ── plumbing ─────────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        if index == TAB_SCHEDULE:
            self.schedule_panel.refresh()
        elif index == TAB_TASKS:
            self.tasks_panel.refresh()
        elif index == TAB_NOTES:
            self.notes_panel.refresh(keep_selection=True)
        elif index == TAB_TERMINAL:
            # Coming back to the terminal should leave the caret ready to type.
            QTimer.singleShot(0, self.command_line.focus)

    def _show_tab(self, index: int):
        self.tabs.set_current(index)

    # ── reminders ────────────────────────────────────────────────────────────

    def _apply_reminder_prefs(self):
        """Switch the tray icon and the polling timer to match the saved
        preference, and re-label the header button."""
        notify = self.store.notify
        supported = DesktopNotifier.available()
        on = bool(notify.enabled and supported)

        self.notifier.set_enabled(on)
        if on and not self._reminder_timer.isActive():
            self._reminder_timer.start()
            # Check immediately as well: opening TechDeck at 7:58 should not
            # wait half a minute to mention the 8:00 block.
            QTimer.singleShot(0, self._check_reminders)
        elif not on and self._reminder_timer.isActive():
            self._reminder_timer.stop()

        if not supported:
            self.reminders_btn.setText("Reminders unavailable")
            self.reminders_btn.setToolTip(DesktopNotifier.unavailable_reason())
        elif on:
            self.reminders_btn.setText("Reminders on")
            self.reminders_btn.setToolTip(
                f"{notify.lead_minutes} min warning before each block. "
                f"Click to change.")
        else:
            self.reminders_btn.setText("Reminders off")
            self.reminders_btn.setToolTip("Click to turn them on")

    def _open_reminder_settings(self):
        from techdeck.ui.dialogs.reminder_dialog import ReminderDialog
        dialog = ReminderDialog(self.store.notify, parent=self.window())
        if not dialog.exec():
            return
        self.store.save_notify_prefs(dialog.result_prefs())
        self._apply_reminder_prefs()

    def _check_reminders(self):
        """One tick: find what's due, show it, remember that we did.

        Wrapped whole: a reminder is the least important thing on this page and
        must never be the reason it falls over.
        """
        try:
            pending = due_notifications(
                schedule=self.store.latest_schedule(),
                tasks=self.store.tasks,
                prefs=self.store.prefs,
                notify=self.store.notify,
                now=datetime.now(),
                already_sent=self.store.sent_reminders(),
            )
        except Exception as exc:
            logger.warning("Reminder check failed: %s", exc)
            return

        shown = []
        for note in pending:
            if self.notifier.notify(note.title, note.body):
                shown.append(note.key)
        if shown:
            self.store.mark_reminders_sent(shown)

    def _on_internal_link(self, url: str):
        """A techdeck:// anchor in the transcript. Only one so far: your own
        avatar, which opens My Account because that is where you change it."""
        if url == ACCOUNT_URL:
            self._go_to_page("account")

    def _go_to_page(self, page_id: str):
        """Bring the window forward on another sidebar page."""
        window = self.window()
        try:
            window.showNormal()
            window.raise_()
            window.activateWindow()
            sidebar = getattr(window, "sidebar", None)
            if sidebar is not None:
                sidebar.set_current_page(page_id)
                window._on_page_changed(page_id)
        except Exception as exc:
            logger.warning("Could not open %s: %s", page_id, exc)

    def _on_notification_clicked(self):
        """Clicking a toast (or the tray icon) brings TechDeck forward on the
        Assistant's Schedule tab, which is what the reminder was about."""
        window = self.window()
        try:
            if window is not None:
                window.showNormal()
                window.raise_()
                window.activateWindow()
                sidebar = getattr(window, "sidebar", None)
                if sidebar is not None:
                    sidebar.set_current_page("assistant")
                    window._on_page_changed("assistant")
        except Exception as exc:
            logger.warning("Could not surface the window: %s", exc)
        self._show_tab(TAB_SCHEDULE)

    def _on_data_changed(self):
        """Anything that mutates the store lands here, so the panels the user
        isn't looking at are never stale when they switch to them."""
        current = self.tabs.current()
        if current == TAB_SCHEDULE:
            self.schedule_panel.refresh()
        elif current == TAB_TASKS:
            self.tasks_panel.refresh()
        elif current == TAB_NOTES:
            self.notes_panel.refresh(keep_selection=True)
        self._refresh_chips()

    def refresh(self):
        """Called by the shell when the page becomes visible."""
        # The picture and the name can both have been changed on My Account
        # since we were last shown.
        self.terminal.set_identity(self._display_name())
        self.schedule_panel.refresh()
        self.tasks_panel.refresh()
        self.notes_panel.refresh(keep_selection=True)
        self._refresh_chips()
        QTimer.singleShot(0, self.command_line.focus)

    # ── theme ────────────────────────────────────────────────────────────────

    def apply_theme(self):
        palette = self.get_current_palette()
        self.subtitle.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 12px;")
        self.reminders_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {palette.text_secondary};
                border: 1px solid {palette.border};
                border-radius: 15px;
                padding: 4px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                border-color: {palette.accent};
                color: {palette.accent};
            }}
        """)
        body = palette.console_bg
        self.panel.setStyleSheet(
            f"QFrame#assistantPanel {{ background: {body}; border: none;"
            " border-top-left-radius: 0; border-top-right-radius: 0;"
            " border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }")

