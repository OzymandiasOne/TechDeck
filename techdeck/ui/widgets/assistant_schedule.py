"""The Schedule and Tasks tabs.

``SchedulePanel`` renders a generated plan as a day-by-day agenda you can tick
off as you go, ticking a block completes the underlying task everywhere, which
is the whole reason the plan references task ids instead of copying titles.

``TasksPanel`` is the backlog: everything captured but not yet done, ordered by
the same cost-of-delay score the scheduler uses, so the top of the list is
always the thing most worth starting.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QCheckBox, QComboBox, QLineEdit, QMessageBox, QSizePolicy, QMenu,
    QInputDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_BUSY, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    PRIORITY_LABELS, Schedule, TaskItem, fmt_day, fmt_duration, fmt_time,
)
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme import mix, readable_on
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.utils import mark_icon_button
from techdeck.ui.theme_manager import SCOPE_ASSISTANT
from techdeck.ui.dialogs.task_edit_dialog import TaskEditDialog

# Priority → accent colour for the little chips. Fixed hues rather than palette
# entries: "critical is red" has to mean the same thing on every theme.
PRIORITY_COLORS = {
    "critical": "#EF4444",
    "high": "#F59E0B",
    "medium": "#3B82F6",
    "low": "#6B7280",
}

# Parked-on-somebody-else amber. Same reasoning as the priority hues: "waiting"
# has to mean the same thing on every theme, so it is a fixed colour.
WAITING_COLOR = "#F59E0B"


def _card(parent=None) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("assistantCard")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


def _header_card(parent=None) -> QFrame:
    """The toolbar strip at the top of a tab.

    Its own object name so it can be a quiet step away from the content cards
    under it. With both on `surface` the page was one unbroken slab of colour
    and the controls read as part of the agenda, which is the opposite of what
    a toolbar is for.
    """
    frame = QFrame(parent)
    frame.setObjectName("assistantHeader")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


def card_qss(palette) -> str:
    """The shared look of both card kinds. One definition, three tabs."""
    return f"""
        QFrame#assistantCard {{
            background-color: {palette.surface};
            border: 1px solid {palette.card_border or palette.border};
            border-radius: 10px;
        }}
        QFrame#assistantHeader {{
            background-color: {mix(palette.surface, palette.on_card, 0.12)};
            border: 1px solid {palette.card_border or palette.border};
            border-radius: 10px;
        }}
    """


class _Scroller(QScrollArea):
    """Vertical scroll area with a transparent viewport, used by both panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.box = QVBoxLayout(self.body)
        self.box.setContentsMargins(2, 2, 8, 12)
        self.box.setSpacing(10)
        self.setWidget(self.body)

    def clear(self):
        while self.box.count():
            item = self.box.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


# ── Schedule ─────────────────────────────────────────────────────────────────

class SchedulePanel(QWidget, ThemeAware):
    """Shows the saved plan. Emits ``rebuild_requested`` for the page to act on."""

    # Follows the Assistant's own theme when one is pinned (Settings ->
    # Personalization -> Assistant Page Theme), else the app's.
    THEME_SCOPE = SCOPE_ASSISTANT

    rebuild_requested = Signal()
    export_requested = Signal(str)          # 'md' | 'ics' | 'txt'
    blocks_requested = Signal()             # open the meetings editor
    changed = Signal()

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._schedule: Optional[Schedule] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # --- header ----------------------------------------------------------
        # In a card of its own, like everything else on the page. It used to
        # be a bare row on the panel: square corners, text against the panel
        # edge and the Export button flush with the right-hand side, which
        # read as a strip jammed into the corner rather than a toolbar.
        header_card = _header_card()
        header = QHBoxLayout(header_card)
        header.setContentsMargins(16, 12, 16, 12)
        header.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.range_label = QLabel("No plan yet")
        self.range_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.stats_label = QLabel("")
        titles.addWidget(self.range_label)
        titles.addWidget(self.stats_label)
        header.addLayout(titles, 1)

        self.history = QComboBox()
        self.history.setMinimumWidth(190)
        self.history.setMinimumHeight(30)
        self.history.setToolTip("Look back at an earlier plan")
        self.history.currentIndexChanged.connect(self._on_history_pick)
        header.addWidget(self.history)

        self.blocks_btn = QPushButton("Meetings")
        self.blocks_btn.setToolTip(
            "Meetings and blocked-out time the planner has to work around")
        self.blocks_btn.setMinimumHeight(30)
        self.blocks_btn.clicked.connect(self.blocks_requested.emit)
        header.addWidget(self.blocks_btn)

        self.rebuild_btn = QPushButton("Rebuild")
        self.rebuild_btn.setToolTip("Open the builder again")
        self.rebuild_btn.setMinimumHeight(30)
        self.rebuild_btn.clicked.connect(self.rebuild_requested.emit)
        header.addWidget(self.rebuild_btn)

        self.export_btn = QPushButton("Export ▾")
        self.export_btn.setMinimumHeight(30)
        self.export_btn.clicked.connect(self._show_export_menu)
        header.addWidget(self.export_btn)

        outer.addWidget(header_card)

        self.scroller = _Scroller()
        outer.addWidget(self.scroller, 1)

        self.setup_theme_awareness()
        self.refresh()

    # -- theme ---------------------------------------------------------------

    def apply_theme(self):
        palette = self.get_current_palette()
        # The header sits on a card now, so its text takes the card's tones.
        self.range_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {palette.on_card}; "
            f"background: transparent;")
        self.stats_label.setStyleSheet(
            f"color: {palette.on_card_secondary}; font-size: 12px; "
            f"background: transparent;")
        self.setStyleSheet(card_qss(palette))
        self.refresh(keep_history=True)

    # -- data ----------------------------------------------------------------

    def refresh(self, keep_history: bool = False):
        schedules = self.store.schedules
        if not keep_history:
            self.history.blockSignals(True)
            self.history.clear()
            for entry in schedules:
                stamp = entry.created_at.replace("T", " ")[5:16]
                self.history.addItem(f"{entry.range_label}  ·  {stamp}", entry.id)
            self.history.setEnabled(bool(schedules))
            self.history.blockSignals(False)

        chosen_id = self.history.currentData() if schedules else None
        self._schedule = (self.store.get_schedule(chosen_id) if chosen_id
                          else self.store.latest_schedule())
        self._render()

    def show_schedule(self, schedule_id: str):
        self.refresh()
        index = self.history.findData(schedule_id)
        if index >= 0:
            self.history.setCurrentIndex(index)

    def _on_history_pick(self, _index: int):
        chosen = self.history.currentData()
        if chosen:
            self._schedule = self.store.get_schedule(chosen)
            self._render()

    def _show_export_menu(self):
        menu = QMenu(self)
        menu.addAction("Calendar file (.ics) for Outlook",
                       lambda: self.export_requested.emit("ics"))
        menu.addAction("Markdown (.md) for Teams",
                       lambda: self.export_requested.emit("md"))
        menu.addAction("Plain text (.txt)",
                       lambda: self.export_requested.emit("txt"))
        menu.exec(self.export_btn.mapToGlobal(
            self.export_btn.rect().bottomLeft()))

    # -- rendering -----------------------------------------------------------

    def _render(self):
        palette = self.get_current_palette()
        self.scroller.clear()
        schedule = self._schedule

        if schedule is None:
            self.range_label.setText("No plan yet")
            self.stats_label.setText(
                "Press “Build a schedule” below the terminal, or type /schedule.")
            self.export_btn.setEnabled(False)
            empty = QLabel(
                "Nothing planned yet.\n\n"
                "Tell me what's on your plate and I'll lay the day out: "
                "what to do, when, and what won't fit.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {palette.text_secondary}; padding: 40px;")
            self.scroller.box.addWidget(empty)
            self.scroller.box.addStretch()
            return

        self.export_btn.setEnabled(True)
        self.range_label.setText(schedule.range_label or "Plan")
        stats = schedule.stats or {}
        bits = [f"{stats.get('tasks_placed', 0)} tasks",
                f"{fmt_duration(stats.get('work_minutes', 0))} of work"]
        if stats.get("committed_minutes"):
            bits.append(f"{fmt_duration(stats['committed_minutes'])} booked")
        if stats.get("utilization"):
            bits.append(f"{stats['utilization']}% of the day booked")
        if stats.get("buffer_pct"):
            bits.append(f"estimates padded {stats['buffer_pct']}%")
        self.stats_label.setText("  ·  ".join(bits))

        for warning in schedule.warnings:
            self.scroller.box.addWidget(self._banner(warning, palette.warning))

        for day_plan in schedule.days:
            planned = [b for b in day_plan.blocks
                       if b.kind in (BLOCK_TASK, BLOCK_FIXED, BLOCK_BUSY)]
            if not planned:
                continue
            self.scroller.box.addWidget(self._day_card(day_plan, palette))

        # "Didn't fit" and "waiting on someone" are different problems, so they
        # get different cards: one is a squeeze you can fix by moving work, the
        # other is somebody else's turn and nothing you do to the plan helps.
        didnt_fit = [i for i in schedule.unscheduled if not i.get("waiting")]
        parked = [i for i in schedule.unscheduled if i.get("waiting")]
        if didnt_fit:
            self.scroller.box.addWidget(
                self._overflow_card(didnt_fit, palette))
        if parked:
            self.scroller.box.addWidget(self._waiting_card(parked, palette))

        self.scroller.box.addStretch()

    def _banner(self, text: str, color: str) -> QWidget:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background: rgba(245, 158, 11, 0.14); color: {color}; "
            f"border: 1px solid {color}; border-radius: 8px; padding: 9px 12px;")
        return label

    def _day_card(self, day_plan, palette) -> QWidget:
        card = _card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(4)

        day_date = day_plan.date_obj()
        heading = QLabel(fmt_day(day_date) if day_date else day_plan.day)
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {palette.on_card}; "
            f"background: transparent;")
        box.addWidget(heading)

        total_text = f"{fmt_duration(day_plan.work_minutes())} planned"
        booked = day_plan.committed_minutes()
        if booked:
            total_text += f"  \u00b7  {fmt_duration(booked)} already booked"
        total = QLabel(total_text)
        total.setStyleSheet(
            f"color: {palette.on_card_secondary}; font-size: 11px; "
            f"background: transparent; margin-bottom: 6px;")
        box.addWidget(total)

        now = datetime.now()
        for block in day_plan.blocks:
            box.addWidget(self._block_row(block, palette, now))
        return card

    def _block_row(self, block, palette, now: datetime) -> QWidget:
        row = QWidget()
        # Explicitly transparent: without it the row picks up the app
        # stylesheet's default QWidget fill and every line reads as a stripe
        # against the card behind it.
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        time_label = QLabel(block.time_range())
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        time_label.setFont(mono)
        time_label.setFixedWidth(140)
        # Right-aligned so every row's time ends against the tick column
        # instead of trailing off into a ragged gap. The times vary in width
        # ("7:00 AM-8:30 AM" vs "11:30 AM-12:00 PM") and left-aligning them
        # left the eye nothing to follow down the page.
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
        time_label.setStyleSheet(
            f"color: {palette.on_card_secondary}; background: transparent;")
        layout.addWidget(time_label)

        is_work = block.kind in (BLOCK_TASK, BLOCK_FIXED)
        task = self.store.get_task(block.task_id) if block.task_id else None

        if block.kind == BLOCK_BUSY:
            # Not your work, so there is nothing to tick. A marker keeps the
            # row aligned with the checkboxes above and below it.
            spacer = QLabel("\u25a0")
            spacer.setFixedWidth(18)
            spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # The card's own quiet tone, not accent_two: that is a CTA colour
            # (poison green on halloween) and a meeting is the opposite of a
            # call to action. The filled square against lunch's dot, plus the
            # bold title, is all the distinction the row needs.
            spacer.setStyleSheet(
                f"color: {palette.on_card_secondary}; background: transparent;")
            layout.addWidget(spacer)
        elif is_work and task is not None:
            check = QCheckBox()
            check.setChecked(task.done)
            check.setToolTip("Mark done")
            check.toggled.connect(
                lambda checked, tid=task.id: self._set_done(tid, checked))
            layout.addWidget(check)
        else:
            spacer = QLabel("·" if block.kind in (BLOCK_BREAK, BLOCK_LUNCH) else "")
            spacer.setFixedWidth(18)
            spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spacer.setStyleSheet(
                f"color: {palette.on_card_secondary}; background: transparent;")
            layout.addWidget(spacer)

        title = block.title
        if block.kind == BLOCK_FIXED:
            title = f"📌 {title}"
        if block.kind == BLOCK_BUSY and block.note:
            title += f"   \u00b7 {block.note.splitlines()[0][:60]}"

        label = QLabel(title)
        # One line per block. A wrapped QLabel reports a deliberately narrow
        # sizeHint, which broke "911 scribe sheets for L022" across two lines
        # in a row with half the card still empty beside it. An agenda is read
        # by scanning down the times, so a row that is sometimes two lines
        # tall is worse than a long name being cut - and the full name is one
        # hover away.
        label.setWordWrap(False)
        label.setToolTip(block.title)
        colour = palette.on_card if is_work else palette.on_card_secondary
        if block.kind == BLOCK_BUSY:
            colour = palette.on_card
        weight = ("600" if block.kind in (BLOCK_FIXED, BLOCK_BUSY)
                  else "normal")
        extra = ""
        if task is not None and task.done:
            extra = "text-decoration: line-through;"
            colour = palette.on_card_secondary
        label.setStyleSheet(f"color: {colour}; font-weight: {weight}; "
                            f"background: transparent; {extra}")
        # Maximum, not Preferred: the title takes the width it needs and no
        # more, so "part 2 of 3" and the "now" pill sit against it instead of
        # being flung to the right-hand edge - but it can still shrink and
        # wrap when the window is narrow. With plain stretch it grew to fill
        # the row and wrapped a title that had plenty of room.
        label.setSizePolicy(QSizePolicy.Policy.Maximum,
                            QSizePolicy.Policy.Preferred)
        layout.addWidget(label, 0)

        # "part 2 of 3" qualifies the title, it is not part of it. As its own
        # quiet label it stops competing with the name of the job.
        if block.part and block.part_count > 1:
            part = QLabel(f"part {block.part} of {block.part_count}")
            part.setStyleSheet(
                f"color: {palette.on_card_secondary}; font-size: 11px; "
                f"background: transparent;")
            layout.addWidget(part, 0)

        # "You are here", the single most useful thing an agenda can tell you
        # when you glance at it mid-morning. It sits NEXT TO the block it is
        # about: floated out at the right-hand edge it read as a badge on the
        # card rather than on the row.
        start, end = block.start_dt(), block.end_dt()
        if start and end and start <= now < end:
            marker = QLabel("now")
            marker.setStyleSheet(
                f"color: {palette.accent_text}; background: {palette.accent}; "
                f"border-radius: 7px; padding: 1px 8px; font-size: 10px; "
                f"font-weight: bold;")
            layout.addWidget(marker, 0)

        layout.addStretch(1)

        if task is not None and (task.notes or task.links):
            info = QPushButton("⋯")
            info.setFixedSize(24, 22)
            mark_icon_button(info)   # padding:0, or the glyph has no room
            info.setCursor(Qt.CursorShape.PointingHandCursor)
            info.setToolTip("Notes and links")
            info.setStyleSheet(
                f"QPushButton {{ border: none; background: transparent; "
                f"color: {palette.on_card_secondary}; }}"
                f"QPushButton:hover {{ color: {palette.accent}; }}")
            info.clicked.connect(lambda _c=False, t=task: self._open_task(t))
            layout.addWidget(info)

        return row

    def _waiting_card(self, items, palette) -> QWidget:
        """Work the plan skipped because somebody else has it.

        Shown rather than dropped: a task parked on a colleague is the single
        easiest thing to lose track of, precisely because nothing on the
        agenda ever mentions it again.
        """
        card = _card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(6)

        heading = QLabel("Not planned \u2014 you're waiting on someone")
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; "
            f"color: {readable_on(WAITING_COLOR, palette.surface, palette.on_card)}; "
            f"background: transparent;")
        box.addWidget(heading)

        note = QLabel("These come back into the plan the moment you take them "
                      "off whoever has them.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {palette.on_card_secondary}; font-size: 11px; "
            f"background: transparent; margin-bottom: 4px;")
        box.addWidget(note)

        for item in items:
            row = QLabel(f"\u2022 {item.get('title', '')} "
                         f"({item.get('reason', 'waiting')})")
            row.setWordWrap(True)
            row.setStyleSheet(
                f"color: {palette.on_card}; background: transparent;")
            box.addWidget(row)
        return card

    def _overflow_card(self, items, palette) -> QWidget:
        card = _card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(6)

        heading = QLabel("Didn't fit")
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; "
            f"color: {readable_on(palette.warning, palette.surface, palette.on_card)}; "
            f"background: transparent;")
        box.addWidget(heading)

        note = QLabel("These need a bigger window, a later deadline, or a "
                      "smaller estimate.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {palette.on_card_secondary}; font-size: 11px; "
            f"background: transparent; margin-bottom: 4px;")
        box.addWidget(note)

        for item in items:
            row = QLabel(f"• {item.get('title', '')}: {item.get('reason', '')}")
            row.setWordWrap(True)
            row.setStyleSheet(
                f"color: {palette.on_card}; background: transparent;")
            box.addWidget(row)
        return card

    # -- actions -------------------------------------------------------------

    def _set_done(self, task_id: str, done: bool):
        self.store.set_done(task_id, done)
        self.changed.emit()
        self._render()

    def _open_task(self, task: TaskItem):
        dialog = TaskEditDialog(task, parent=self.window(), title="Task details")
        if dialog.exec():
            self.store.update_task(dialog.result_task())
            self.changed.emit()
            self._render()


# ── Tasks ────────────────────────────────────────────────────────────────────

class TasksPanel(QWidget, ThemeAware):
    """The backlog. Quick-add at the top, ranked list below."""

    # Follows the Assistant's own theme when one is pinned (Settings ->
    # Personalization -> Assistant Page Theme), else the app's.
    THEME_SCOPE = SCOPE_ASSISTANT

    changed = Signal()
    schedule_requested = Signal()

    FILTERS = [("open", "Open"), ("waiting", "Waiting on someone"),
               ("all", "All"), ("done", "Done")]

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._filter = "open"
        self._search = ""
        # Which tasks have their steps unfolded. Session-only and keyed by id:
        # a backlog where every project is expanded by default is a wall, and
        # a remembered expansion is a preference nobody asked to set.
        self._expanded: set[str] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # --- quick add + filters, in one header card -------------------------
        # Both rows live on a card, matching the Schedule tab and the task
        # cards below: a bare row on the panel reads as a strip wedged into
        # the corner, with its last button flush against the window edge.
        header_card = _header_card()
        header_box = QVBoxLayout(header_card)
        header_box.setContentsMargins(16, 12, 16, 12)
        header_box.setSpacing(8)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.quick_add = QLineEdit()
        self.quick_add.setMinimumHeight(34)
        self.quick_add.setPlaceholderText(
            "Add a task: “order the 4130 tube 20m high due friday”")
        self.quick_add.returnPressed.connect(self._quick_add)
        add_row.addWidget(self.quick_add, 1)

        self.add_btn = QPushButton("Add")
        self.add_btn.setMinimumHeight(34)
        self.add_btn.setMinimumWidth(70)
        self.add_btn.clicked.connect(self._quick_add)
        add_row.addWidget(self.add_btn)

        self.detail_btn = QPushButton("Add with details…")
        self.detail_btn.setMinimumHeight(34)
        self.detail_btn.clicked.connect(self._add_detailed)
        add_row.addWidget(self.detail_btn)
        header_box.addLayout(add_row)

        # --- filter bar ------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.filter_box = QComboBox()
        for key, label in self.FILTERS:
            self.filter_box.addItem(label, key)
        self.filter_box.setMinimumHeight(28)
        self.filter_box.currentIndexChanged.connect(self._on_filter)
        filter_row.addWidget(self.filter_box)

        # Searching the backlog, asked for 2026-10-09. Live rather than
        # behind a button: by the time you have typed three letters the list
        # is short enough to read, and there is nothing to press.
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(28)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self._on_search)
        filter_row.addWidget(self.search)

        self.summary = QLabel("")
        filter_row.addWidget(self.summary, 1)

        self.plan_btn = QPushButton("Build a schedule")
        self.plan_btn.setProperty("class", "primary")
        self.plan_btn.setMinimumHeight(28)
        self.plan_btn.clicked.connect(self.schedule_requested.emit)
        filter_row.addWidget(self.plan_btn)

        self.purge_btn = QPushButton("Clear finished")
        self.purge_btn.setMinimumHeight(28)
        self.purge_btn.clicked.connect(self._purge)
        filter_row.addWidget(self.purge_btn)
        header_box.addLayout(filter_row)
        outer.addWidget(header_card)

        self.scroller = _Scroller()
        outer.addWidget(self.scroller, 1)

        self.setup_theme_awareness()
        self.refresh()

    def apply_theme(self):
        palette = self.get_current_palette()
        # The summary sits on the header card, so it takes the card's tones.
        self.summary.setStyleSheet(
            f"color: {palette.on_card_secondary}; font-size: 12px; "
            f"background: transparent;")
        self.setStyleSheet(card_qss(palette))
        self.refresh()

    # -- data ----------------------------------------------------------------

    def _visible_tasks(self) -> List[TaskItem]:
        if self._filter == "open":
            tasks = self.store.open_tasks()
        elif self._filter == "waiting":
            tasks = self.store.waiting_tasks()
        elif self._filter == "done":
            tasks = [t for t in self.store.tasks if t.done]
        else:
            tasks = list(self.store.tasks)
        # The search runs over the title, the notes, the links AND the steps,
        # because "I know I wrote that PO number down" has to find it wherever
        # it was written. Applied after the filter so the two compose.
        needle = self._search.strip().lower()
        if needle:
            def mentions(task: TaskItem) -> bool:
                parts = [task.title, task.notes, task.waiting_on]
                parts.extend(task.links)
                parts.extend(step.text for step in task.checklist)
                return any(needle in (part or "").lower() for part in parts)
            tasks = [t for t in tasks if mentions(t)]
        today = date.today()
        # Open work is ranked by cost-of-delay (same order the scheduler uses);
        # finished work reads best newest-first.
        if self._filter == "done":
            tasks.sort(key=lambda t: t.done_at or t.updated_at, reverse=True)
        else:
            tasks.sort(key=lambda t: (t.done, -t.score(today), t.created_at))
        return tasks

    def refresh(self):
        palette = self.get_current_palette()
        self.scroller.clear()
        tasks = self._visible_tasks()

        open_tasks = self.store.open_tasks()
        total = sum(t.estimate_min for t in open_tasks)
        overdue = sum(1 for t in open_tasks
                      if t.deadline_date() and t.deadline_date() < date.today())
        summary = (f"{len(open_tasks)} open · {fmt_duration(total)} of work")
        if overdue:
            summary += f" · {overdue} overdue"
        parked = len([t for t in open_tasks if t.waiting])
        if parked:
            summary += f" · {parked} waiting"
        running = self.store.running_task()
        if running is not None:
            summary += (f" · ▶ {fmt_duration(running.logged_minutes())} on "
                        f"{running.label()[:24]}")
        self.summary.setText(summary)

        if not tasks:
            if self._search.strip():
                message = (f"Nothing matches “{self._search.strip()}”.\n\n"
                           f"Try fewer words, or switch the filter to All.")
            else:
                message = ("Nothing here.\n\nAdd something above, or just "
                           "type it into the terminal.")
            empty = QLabel(message)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {palette.text_secondary}; padding: 40px;")
            self.scroller.box.addWidget(empty)
            self.scroller.box.addStretch()
            return

        for task in tasks:
            self.scroller.box.addWidget(self._task_row(task, palette))
        self.scroller.box.addStretch()

    def _task_row(self, task: TaskItem, palette) -> QWidget:
        """One backlog card: the task, then its steps if they are unfolded.

        The card is a column so the steps can live INSIDE it rather than as a
        separate card underneath: a step belongs to its task, and two cards
        read as two jobs.
        """
        card = _card()
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        column = QVBoxLayout(card)
        column.setContentsMargins(12, 8, 10, 8)
        column.setSpacing(6)

        top = QWidget()
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top.setStyleSheet("background: transparent;")
        box = QHBoxLayout(top)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        column.addWidget(top)

        # Right-click is the quiet route to the state changes that would
        # otherwise need a button each. Everything here is also reachable from
        # Edit and from the terminal, so nothing lives ONLY in a menu.
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda point, t=task, host=card: self._row_menu(t, host, point))

        check = QCheckBox()
        check.setChecked(task.done)
        check.toggled.connect(
            lambda checked, tid=task.id: self._set_done(tid, checked))
        box.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)

        middle = QVBoxLayout()
        middle.setSpacing(3)

        title = QLabel(task.label())
        title.setWordWrap(True)
        style = f"color: {palette.on_card}; font-size: 13px; background: transparent;"
        if task.done:
            style = (f"color: {palette.on_card_secondary}; font-size: 13px; "
                     f"text-decoration: line-through; background: transparent;")
        title.setStyleSheet(style)
        middle.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        meta.addWidget(self._chip(PRIORITY_LABELS.get(task.priority, "Medium"),
                                  PRIORITY_COLORS.get(task.priority, "#3B82F6")))
        meta.addWidget(self._chip(fmt_duration(task.estimate_min),
                                  palette.on_card_secondary))
        due = task.deadline_date()
        if due:
            overdue = due < date.today() and not task.done
            meta.addWidget(self._chip(
                ("overdue · " if overdue else "due ") + due.strftime("%b %d"),
                "#EF4444" if overdue else palette.on_card_secondary))
        fixed = task.fixed_datetime()
        if fixed:
            meta.addWidget(self._chip(f"📌 {fmt_time(fixed)} "
                                      f"{fixed.strftime('%b %d')}",
                                      palette.accent))
        if not task.splittable:
            meta.addWidget(self._chip("one sitting", palette.on_card_secondary))
        if task.links:
            meta.addWidget(self._chip(f"🔗 {len(task.links)}",
                                      palette.on_card_secondary))
        if task.waiting:
            # No icon: U+23F8 (pause) is not in the shipped font and renders
            # as a missing-glyph box on every theme. The words carry it.
            meta.addWidget(self._chip(task.waiting_label(), WAITING_COLOR))
        logged = task.logged_minutes()
        if logged:
            # Logged time sits beside the estimate and nothing else happens:
            # no ratio, no verdict. A task that ran long is information.
            meta.addWidget(self._chip(f"{fmt_duration(logged)} logged",
                                      palette.accent if task.is_running
                                      else palette.on_card_secondary))
        done_steps, total_steps = task.checklist_progress()
        if total_steps:
            open_now = task.id in self._expanded
            steps_chip = self._chip(
                f"{'▾' if open_now else '▸'} {done_steps}/{total_steps} steps",
                palette.accent if open_now else palette.on_card_secondary)
            steps_chip.setCursor(Qt.CursorShape.PointingHandCursor)
            steps_chip.setToolTip("Show the steps")
            # A clickable QLabel rather than a button: a button here would be a
            # fifth control on a row that is meant to read as one line.
            steps_chip.mousePressEvent = (
                lambda _event, tid=task.id: self._toggle_steps(tid))
            meta.addWidget(steps_chip)
        meta.addStretch()
        middle.addLayout(meta)

        if task.notes:
            note = QLabel(task.notes.splitlines()[0][:120])
            note.setStyleSheet(
                f"color: {palette.on_card_secondary}; font-size: 11px; "
                f"background: transparent;")
            middle.addWidget(note)

        next_step = task.next_step()
        if next_step is not None and task.id not in self._expanded:
            # Folded away, the one line worth surfacing is what comes next.
            peek = QLabel(f"next: {next_step.label()[:90]}")
            peek.setStyleSheet(
                f"color: {palette.on_card_secondary}; font-size: 11px; "
                f"background: transparent;")
            middle.addWidget(peek)

        box.addLayout(middle, 1)

        if not task.done:
            clock = QPushButton("■" if task.is_running else "▶")
            clock.setFixedSize(26, 26)
            mark_icon_button(clock)   # padding:0, or the glyph has no room
            clock.setCursor(Qt.CursorShape.PointingHandCursor)
            clock.setToolTip("Stop the clock" if task.is_running
                             else "Start the clock on this")
            accent = palette.accent if task.is_running else palette.on_card_secondary
            clock.setStyleSheet(
                f"QPushButton {{ border: none; background: transparent; "
                f"color: {accent}; font-size: 13px; }}"
                f"QPushButton:hover {{ color: {palette.accent}; }}")
            clock.clicked.connect(
                lambda _c=False, t=task: self._toggle_clock(t))
            box.addWidget(clock, 0, Qt.AlignmentFlag.AlignTop)

        edit = QPushButton("Edit")
        edit.setFixedHeight(26)
        # Same family as the icon-button trap: the theme's 8px vertical
        # padding leaves a 26px-high button ~10px for text that needs ~15,
        # and the label renders clipped ("Fdit"). Padding it explicitly is
        # the fix; the height stays, so the row does not grow.
        edit.setStyleSheet("padding: 2px 10px;")
        edit.clicked.connect(lambda _c=False, t=task: self._edit(t))
        box.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)

        remove = QPushButton("✕")
        remove.setFixedSize(26, 26)
        mark_icon_button(remove)   # padding:0, or the glyph has no room
        remove.setToolTip("Delete")
        remove.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; "
            f"color: {palette.on_card_secondary}; font-size: 13px; }}"
            f"QPushButton:hover {{ color: #EF4444; }}")
        remove.clicked.connect(lambda _c=False, t=task: self._delete(t))
        box.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)

        if total_steps and task.id in self._expanded:
            column.addWidget(self._steps_block(task, palette))
        return card

    def _steps_block(self, task: TaskItem, palette) -> QWidget:
        """The unfolded checklist. Ticking is one click, here; AUTHORING the
        steps is typing, in the task dialog. Each job in the place it fits."""
        host = QWidget()
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        host.setStyleSheet("background: transparent;")
        box = QVBoxLayout(host)
        box.setContentsMargins(34, 2, 0, 2)
        box.setSpacing(2)

        today = date.today()
        for step in task.checklist:
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row.setStyleSheet("background: transparent;")
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)

            tick = QCheckBox()
            tick.setChecked(step.done)
            tick.toggled.connect(
                lambda checked, tid=task.id, sid=step.id:
                self._set_step_done(tid, sid, checked))
            line.addWidget(tick)

            text = QLabel(step.label())
            text.setWordWrap(True)
            style = (f"color: {palette.on_card_secondary}; font-size: 12px; "
                     f"background: transparent;")
            if step.done:
                style += " text-decoration: line-through;"
            text.setStyleSheet(style)
            # The chips belong to THIS step, so they sit right after its
            # words. Given the row's stretch they drifted to the far right
            # edge instead, where they read as belonging to the card.
            line.addWidget(text, 0)

            if step.estimate_min:
                line.addWidget(self._chip(fmt_duration(step.estimate_min),
                                          palette.on_card_secondary))
            due = step.deadline_date()
            if due:
                late = due < today and not step.done
                line.addWidget(self._chip(
                    ("overdue · " if late else "by ") + due.strftime("%b %d"),
                    "#EF4444" if late else palette.on_card_secondary))
            line.addStretch()
            box.addWidget(row)

        rolled = task.checklist_minutes()
        if rolled:
            foot = QLabel(f"{fmt_duration(rolled)} across the steps · "
                          f"the task is booked for "
                          f"{fmt_duration(task.estimate_min)}")
            foot.setStyleSheet(
                f"color: {palette.on_card_secondary}; font-size: 11px; "
                f"background: transparent;")
            box.addWidget(foot)
        return host

    def _chip(self, text: str, color: str) -> QLabel:
        """A small outlined label on a card.

        The colour goes through ``readable_on``. Status hues are fixed on
        purpose - "critical is red" has to mean the same thing on every theme
        - but a fixed hue cannot know what it will be painted on, and amber on
        halloween's pumpkin card is the same colour twice: the chip vanishes.
        Where the hue does not read, the card's own text colour is used and
        the WORD carries the meaning instead.
        """
        palette = self.get_current_palette()
        colour = readable_on(color, palette.surface, palette.on_card_secondary)
        chip = QLabel(text)
        chip.setStyleSheet(
            f"color: {colour}; border: 1px solid {colour}; "
            f"border-radius: 8px; padding: 0px 7px; font-size: 10px; "
            f"background: transparent;")
        return chip

    # -- actions -------------------------------------------------------------

    def _on_filter(self, _index: int):
        self._filter = self.filter_box.currentData() or "open"
        self.refresh()

    def _on_search(self, text: str):
        self._search = text or ""
        self.refresh()

    def _toggle_steps(self, task_id: str):
        if task_id in self._expanded:
            self._expanded.discard(task_id)
        else:
            self._expanded.add(task_id)
        self.refresh()

    def _set_step_done(self, task_id: str, step_id: str, done: bool):
        self.store.set_step_done(task_id, step_id, done)
        self.refresh()
        self.changed.emit()

    def _toggle_clock(self, task: TaskItem):
        """▶/■ on a row. Starting one stops whatever else was running, which
        the store enforces; this just tells the user it happened."""
        if task.is_running:
            self.store.clock_out(task.id)
        else:
            self.store.clock_in(task.id)
        self.refresh()
        self.changed.emit()

    def _row_menu(self, task: TaskItem, host: QWidget, point):
        menu = QMenu(self)
        if task.is_running:
            menu.addAction("Stop the clock",
                           lambda t=task: self._toggle_clock(t))
        elif not task.done:
            menu.addAction("Start the clock",
                           lambda t=task: self._toggle_clock(t))
        if task.waiting:
            menu.addAction("Take it back off them",
                           lambda t=task: self._set_waiting(t, False))
        else:
            menu.addAction("Waiting on someone…",
                           lambda t=task: self._set_waiting(t, True))
        menu.addSeparator()
        menu.addAction("Edit…", lambda t=task: self._edit(t))
        menu.addAction("Delete", lambda t=task: self._delete(t))
        menu.exec(host.mapToGlobal(point))

    def _set_waiting(self, task: TaskItem, waiting: bool):
        """Park or unpark a task. Asking WHO is optional: the flag alone is
        the useful part, and a forced prompt would make people skip it."""
        who = ""
        if waiting:
            who, accepted = QInputDialog.getText(
                self, "Waiting on someone",
                f"Who or what is “{task.label()}” waiting on?\n"
                f"(Leave it blank if you'd rather not say.)",
                text=task.waiting_on)
            if not accepted:
                return
            who = (who or "").strip()
        self.store.set_waiting(task.id, waiting, who)
        self.refresh()
        self.changed.emit()

    def _quick_add(self):
        text = self.quick_add.text().strip()
        if not text:
            return
        from techdeck.core.assistant import nlp
        parsed = nlp.parse_task_line(text)
        if not parsed.get("title"):
            return
        task = TaskItem(
            title=parsed["title"],
            priority=parsed.get("priority", "medium"),
            estimate_min=int(parsed.get("estimate_min", 30)),
            deadline=parsed.get("deadline"),
            fixed_start=parsed.get("fixed_start"),
            splittable=bool(parsed.get("splittable", True)),
            links=list(parsed.get("links", [])),
        )
        self.store.add_task(task)
        self.quick_add.clear()
        self.refresh()
        self.changed.emit()

    def _add_detailed(self):
        dialog = TaskEditDialog(parent=self.window(), title="New task")
        seed = self.quick_add.text().strip()
        if seed:
            dialog.title_field.setText(seed)
        if dialog.exec():
            self.store.add_task(dialog.result_task())
            self.quick_add.clear()
            self.refresh()
            self.changed.emit()

    def _edit(self, task: TaskItem):
        dialog = TaskEditDialog(task, parent=self.window(), title="Edit task")
        if dialog.exec():
            self.store.update_task(dialog.result_task())
            self.refresh()
            self.changed.emit()

    def _delete(self, task: TaskItem):
        answer = QMessageBox.question(
            self, "Delete task", f"Delete “{task.label()}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_task(task.id)
        self.refresh()
        self.changed.emit()

    def _set_done(self, task_id: str, done: bool):
        self.store.set_done(task_id, done)
        self.refresh()
        self.changed.emit()

    def _purge(self):
        finished = [t for t in self.store.tasks if t.done]
        if not finished:
            QMessageBox.information(self, "Nothing to clear",
                                    "No finished tasks to clear out.")
            return
        answer = QMessageBox.question(
            self, "Clear finished",
            f"Remove {len(finished)} finished task"
            f"{'s' if len(finished) != 1 else ''} for good?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.purge_done(keep_days=0)
        self.refresh()
        self.changed.emit()
