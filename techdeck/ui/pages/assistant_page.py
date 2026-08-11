"""The Assistant page — TechDeck's personal organizer.

A terminal with tabs above it and a command line below. The terminal is where
you talk to it; the other tabs are where the results live:

    Terminal        the conversation, kept across sessions
    Schedule        the generated plan, tickable as you work through it
    Personal Notes  notes to yourself, nested bullets and all
    Tasks           the backlog everything else is built from

The command line and the word-bubble chips sit **below the tab stack**, so they
stay reachable no matter which tab is showing — you're never more than one line
of typing away from capturing something.

All the thinking happens in ``techdeck.core.assistant``; this module is wiring
and layout.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabBar, QStackedWidget,
    QFrame, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from techdeck.core.assistant.commands import (
    ACT_CLEAR, ACT_EDIT_NOTE, ACT_EXPORT, ACT_GOTO, ACT_OPEN_WIZARD,
    AssistantBrain, Reply,
)
from techdeck.core.assistant.models import ChatMessage
from techdeck.core.assistant.store import AssistantStore
from techdeck.core.settings import SettingsManager
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.widgets.assistant_terminal import (
    ChipBar, CommandLine, TerminalView,
)
from techdeck.ui.widgets.assistant_notes import NotesPanel
from techdeck.ui.widgets.assistant_schedule import SchedulePanel, TasksPanel

TAB_TERMINAL, TAB_SCHEDULE, TAB_NOTES, TAB_TASKS = range(4)
_TAB_KEYS = {"terminal": TAB_TERMINAL, "schedule": TAB_SCHEDULE,
             "notes": TAB_NOTES, "tasks": TAB_TASKS}

# How much transcript to show on open. The file keeps far more; this is just
# what's worth scrolling through.
HISTORY_LINES = 300

GREETING = (
    "Talk to me. Complain, think out loud, whatever — none of it gets filed "
    "unless you ask. Press “Add a task” or type /task when you actually want "
    "something on a list. /help has the rest."
)
GREETING_PROFESSIONAL = (
    "Assistant ready. Free text is not stored as a task — use “Add a task”, "
    "/task, or the Tasks tab. /help lists every command."
)


class AssistantPage(QWidget, ThemeAware):
    """The whole page. Owns one store, one brain, and four panels."""

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = AssistantStore()
        # Professional theme mutes the goblin — a client demo gets plain
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
            "Your desk — notes, tasks, and a schedule that actually fits the day.")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        outer.addLayout(header)

        # ── tabs ─────────────────────────────────────────────────────────────
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("assistantTabBar")
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(False)
        for label in ("Terminal", "Schedule", "Personal Notes", "Tasks"):
            self.tab_bar.addTab(label)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.addWidget(self.tab_bar, 0, Qt.AlignmentFlag.AlignBottom)
        tab_row.addStretch()
        outer.addLayout(tab_row)

        # ── panels ───────────────────────────────────────────────────────────
        self.terminal = TerminalView()

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
        # minimum width — same rule every stacked host in TechDeck follows.
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

        self.setup_theme_awareness()
        self._load_history()
        self._refresh_chips()

    # ── history ──────────────────────────────────────────────────────────────

    def _greeting(self) -> str:
        return (GREETING_PROFESSIONAL if self.settings.is_professional()
                else GREETING)

    def _load_history(self):
        messages = self.store.load_chat(HISTORY_LINES)
        if messages:
            for message in messages:
                self.terminal.append_line(message.role, message.text)
            last = messages[-1].ts[:10]
            today = datetime.now().date().isoformat()
            self.terminal.append_separator(
                "today" if last == today else f"new session · {today}")
            self.command_line.seed_history(
                [m.text for m in messages if m.role == "user"])
        else:
            greeting = self._greeting()
            self.terminal.append_line("deck", greeting)
            self._record("deck", greeting)

    def _record(self, role: str, text: str):
        self.store.append_chat(ChatMessage(role=role, text=text))

    # ── input ────────────────────────────────────────────────────────────────

    def submit(self, text: str):
        """Run one line through the brain and apply whatever comes back."""
        self.terminal.append_line("user", text)
        self._record("user", text)
        self._show_tab(TAB_TERMINAL)

        try:
            reply = self.brain.handle(text)
        except Exception as exc:      # never let a parse bug eat the page
            message = f"Something went wrong handling that: {exc}"
            self.terminal.append_line("error", message)
            self._record("error", message)
            return

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
            greeting = self._greeting()
            self.terminal.append_line("deck", greeting)
            self._record("deck", greeting)
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
        # only ever as an offer — this is the one route from talking to filing,
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
            # newline="" keeps the .ics CRLF line endings exactly as built —
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
        if self.tab_bar.currentIndex() != index:
            self.tab_bar.setCurrentIndex(index)
        else:
            self.stack.setCurrentIndex(index)

    def _on_data_changed(self):
        """Anything that mutates the store lands here, so the panels the user
        isn't looking at are never stale when they switch to them."""
        current = self.tab_bar.currentIndex()
        if current == TAB_SCHEDULE:
            self.schedule_panel.refresh()
        elif current == TAB_TASKS:
            self.tasks_panel.refresh()
        elif current == TAB_NOTES:
            self.notes_panel.refresh(keep_selection=True)
        self._refresh_chips()

    def refresh(self):
        """Called by the shell when the page becomes visible."""
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
        body = palette.console_bg
        self.panel.setStyleSheet(
            f"QFrame#assistantPanel {{ background: {body}; border: none;"
            " border-top-left-radius: 0; border-top-right-radius: 8px;"
            " border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }")
        # Chrome-style tabs: the selected tab fills with the panel colour so it
        # flows into the content, exactly like the plugin console's tab bar.
        self.tab_bar.setStyleSheet(
            "QTabBar#assistantTabBar { background: transparent; }"
            f"QTabBar#assistantTabBar::tab {{ background: {palette.surface};"
            f" color: {palette.text_secondary}; font-weight: bold;"
            " padding: 7px 16px; margin-right: 3px; border: none;"
            " border-top-left-radius: 8px; border-top-right-radius: 8px; }"
            f"QTabBar#assistantTabBar::tab:selected {{ background: {body};"
            f" color: {palette.text}; }}"
            f"QTabBar#assistantTabBar::tab:hover:!selected {{"
            f" background: {palette.surface_hover}; }}")
