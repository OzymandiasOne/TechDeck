"""The Schedule and Tasks tabs.

``SchedulePanel`` renders a generated plan as a day-by-day agenda you can tick
off as you go — ticking a block completes the underlying task everywhere, which
is the whole reason the plan references task ids instead of copying titles.

``TasksPanel`` is the backlog: everything captured but not yet done, ordered by
the same cost-of-delay score the scheduler uses, so the top of the list is
always the thing most worth starting.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QCheckBox, QComboBox, QLineEdit, QMessageBox, QSizePolicy, QMenu,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    PRIORITY_LABELS, Schedule, TaskItem, fmt_day, fmt_duration, fmt_time,
)
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.dialogs.task_edit_dialog import TaskEditDialog

# Priority → accent colour for the little chips. Fixed hues rather than palette
# entries: "critical is red" has to mean the same thing on every theme.
PRIORITY_COLORS = {
    "critical": "#EF4444",
    "high": "#F59E0B",
    "medium": "#3B82F6",
    "low": "#6B7280",
}


def _card(parent=None) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("assistantCard")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


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

    rebuild_requested = Signal()
    export_requested = Signal(str)          # 'md' | 'ics' | 'txt'
    changed = Signal()

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._schedule: Optional[Schedule] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # --- header ----------------------------------------------------------
        header = QHBoxLayout()
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

        self.rebuild_btn = QPushButton("Rebuild")
        self.rebuild_btn.setToolTip("Open the builder again")
        self.rebuild_btn.setMinimumHeight(30)
        self.rebuild_btn.clicked.connect(self.rebuild_requested.emit)
        header.addWidget(self.rebuild_btn)

        self.export_btn = QPushButton("Export ▾")
        self.export_btn.setMinimumHeight(30)
        self.export_btn.clicked.connect(self._show_export_menu)
        header.addWidget(self.export_btn)

        outer.addLayout(header)

        self.scroller = _Scroller()
        outer.addWidget(self.scroller, 1)

        self.setup_theme_awareness()
        self.refresh()

    # -- theme ---------------------------------------------------------------

    def apply_theme(self):
        palette = self.get_current_palette()
        self.stats_label.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 12px;")
        self.setStyleSheet(f"""
            QFrame#assistantCard {{
                background-color: {palette.surface};
                border: 1px solid {palette.border};
                border-radius: 10px;
            }}
        """)
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
        menu.addAction("Calendar file (.ics) — imports into Outlook",
                       lambda: self.export_requested.emit("ics"))
        menu.addAction("Markdown (.md) — paste into Teams",
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
                "Tell me what's on your plate and I'll lay the day out — "
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
        if stats.get("utilization"):
            bits.append(f"{stats['utilization']}% of the day booked")
        if stats.get("buffer_pct"):
            bits.append(f"estimates padded {stats['buffer_pct']}%")
        self.stats_label.setText("  ·  ".join(bits))

        for warning in schedule.warnings:
            self.scroller.box.addWidget(self._banner(warning, palette.warning))

        for day_plan in schedule.days:
            planned = [b for b in day_plan.blocks
                       if b.kind in (BLOCK_TASK, BLOCK_FIXED)]
            if not planned:
                continue
            self.scroller.box.addWidget(self._day_card(day_plan, palette))

        if schedule.unscheduled:
            self.scroller.box.addWidget(self._overflow_card(schedule, palette))

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
            f"font-size: 13px; font-weight: bold; color: {palette.text}; "
            f"background: transparent;")
        box.addWidget(heading)

        total = QLabel(f"{fmt_duration(day_plan.work_minutes())} planned")
        total.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 11px; "
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
        time_label.setStyleSheet(
            f"color: {palette.text_secondary}; background: transparent;")
        layout.addWidget(time_label)

        is_work = block.kind in (BLOCK_TASK, BLOCK_FIXED)
        task = self.store.get_task(block.task_id) if block.task_id else None

        if is_work and task is not None:
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
                f"color: {palette.text_secondary}; background: transparent;")
            layout.addWidget(spacer)

        title = block.title
        if block.kind == BLOCK_FIXED:
            title = f"📌 {title}"
        if block.part and block.part_count > 1:
            title += f"   (part {block.part} of {block.part_count})"

        label = QLabel(title)
        label.setWordWrap(True)
        colour = palette.text if is_work else palette.text_secondary
        weight = "600" if block.kind == BLOCK_FIXED else "normal"
        extra = ""
        if task is not None and task.done:
            extra = "text-decoration: line-through;"
            colour = palette.text_secondary
        label.setStyleSheet(f"color: {colour}; font-weight: {weight}; "
                            f"background: transparent; {extra}")
        layout.addWidget(label, 1)

        # "You are here" — the single most useful thing an agenda can tell you
        # when you glance at it mid-morning.
        start, end = block.start_dt(), block.end_dt()
        if start and end and start <= now < end:
            marker = QLabel("now")
            marker.setStyleSheet(
                f"color: {palette.accent_text}; background: {palette.accent}; "
                f"border-radius: 7px; padding: 1px 8px; font-size: 10px; "
                f"font-weight: bold;")
            layout.addWidget(marker)

        if task is not None and (task.notes or task.links):
            info = QPushButton("⋯")
            info.setFixedSize(24, 22)
            info.setCursor(Qt.CursorShape.PointingHandCursor)
            info.setToolTip("Notes and links")
            info.setStyleSheet(
                f"QPushButton {{ border: none; background: transparent; "
                f"color: {palette.text_secondary}; }}"
                f"QPushButton:hover {{ color: {palette.accent}; }}")
            info.clicked.connect(lambda _c=False, t=task: self._open_task(t))
            layout.addWidget(info)

        return row

    def _overflow_card(self, schedule: Schedule, palette) -> QWidget:
        card = _card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(6)

        heading = QLabel("Didn't fit")
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {palette.warning}; "
            f"background: transparent;")
        box.addWidget(heading)

        note = QLabel("These need a bigger window, a later deadline, or a "
                      "smaller estimate.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 11px; "
            f"background: transparent; margin-bottom: 4px;")
        box.addWidget(note)

        for item in schedule.unscheduled:
            row = QLabel(f"• {item.get('title', '')}  —  {item.get('reason', '')}")
            row.setWordWrap(True)
            row.setStyleSheet(f"color: {palette.text}; background: transparent;")
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

    changed = Signal()
    schedule_requested = Signal()

    FILTERS = [("open", "Open"), ("all", "All"), ("done", "Done")]

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._filter = "open"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # --- quick add -------------------------------------------------------
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.quick_add = QLineEdit()
        self.quick_add.setMinimumHeight(34)
        self.quick_add.setPlaceholderText(
            "Add a task — “order the 4130 tube 20m high due friday”")
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
        outer.addLayout(add_row)

        # --- filter bar ------------------------------------------------------
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.filter_box = QComboBox()
        for key, label in self.FILTERS:
            self.filter_box.addItem(label, key)
        self.filter_box.setMinimumHeight(28)
        self.filter_box.currentIndexChanged.connect(self._on_filter)
        filter_row.addWidget(self.filter_box)

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
        outer.addLayout(filter_row)

        self.scroller = _Scroller()
        outer.addWidget(self.scroller, 1)

        self.setup_theme_awareness()
        self.refresh()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.summary.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 12px;")
        self.setStyleSheet(f"""
            QFrame#assistantCard {{
                background-color: {palette.surface};
                border: 1px solid {palette.border};
                border-radius: 10px;
            }}
        """)
        self.refresh()

    # -- data ----------------------------------------------------------------

    def _visible_tasks(self) -> List[TaskItem]:
        if self._filter == "open":
            tasks = self.store.open_tasks()
        elif self._filter == "done":
            tasks = [t for t in self.store.tasks if t.done]
        else:
            tasks = list(self.store.tasks)
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
        self.summary.setText(summary)

        if not tasks:
            empty = QLabel("Nothing here.\n\nAdd something above, or just type "
                           "it into the terminal.")
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
        card = _card()
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        box = QHBoxLayout(card)
        box.setContentsMargins(12, 8, 10, 8)
        box.setSpacing(10)

        check = QCheckBox()
        check.setChecked(task.done)
        check.toggled.connect(
            lambda checked, tid=task.id: self._set_done(tid, checked))
        box.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)

        middle = QVBoxLayout()
        middle.setSpacing(3)

        title = QLabel(task.label())
        title.setWordWrap(True)
        style = f"color: {palette.text}; font-size: 13px; background: transparent;"
        if task.done:
            style = (f"color: {palette.text_secondary}; font-size: 13px; "
                     f"text-decoration: line-through; background: transparent;")
        title.setStyleSheet(style)
        middle.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        meta.addWidget(self._chip(PRIORITY_LABELS.get(task.priority, "Medium"),
                                  PRIORITY_COLORS.get(task.priority, "#3B82F6")))
        meta.addWidget(self._chip(fmt_duration(task.estimate_min),
                                  palette.text_secondary))
        due = task.deadline_date()
        if due:
            overdue = due < date.today() and not task.done
            meta.addWidget(self._chip(
                ("overdue · " if overdue else "due ") + due.strftime("%b %d"),
                "#EF4444" if overdue else palette.text_secondary))
        fixed = task.fixed_datetime()
        if fixed:
            meta.addWidget(self._chip(f"📌 {fmt_time(fixed)} "
                                      f"{fixed.strftime('%b %d')}",
                                      palette.accent))
        if not task.splittable:
            meta.addWidget(self._chip("one sitting", palette.text_secondary))
        if task.links:
            meta.addWidget(self._chip(f"🔗 {len(task.links)}",
                                      palette.text_secondary))
        meta.addStretch()
        middle.addLayout(meta)

        if task.notes:
            note = QLabel(task.notes.splitlines()[0][:120])
            note.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 11px; "
                f"background: transparent;")
            middle.addWidget(note)

        box.addLayout(middle, 1)

        edit = QPushButton("Edit")
        edit.setFixedHeight(26)
        edit.clicked.connect(lambda _c=False, t=task: self._edit(t))
        box.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)

        remove = QPushButton("✕")
        remove.setFixedSize(26, 26)
        remove.setToolTip("Delete")
        remove.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; "
            f"color: {palette.text_secondary}; font-size: 13px; }}"
            f"QPushButton:hover {{ color: #EF4444; }}")
        remove.clicked.connect(lambda _c=False, t=task: self._delete(t))
        box.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        return card

    @staticmethod
    def _chip(text: str, color: str) -> QLabel:
        chip = QLabel(text)
        chip.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 8px; "
            f"padding: 0px 7px; font-size: 10px; background: transparent;")
        return chip

    # -- actions -------------------------------------------------------------

    def _on_filter(self, _index: int):
        self._filter = self.filter_box.currentData() or "open"
        self.refresh()

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
