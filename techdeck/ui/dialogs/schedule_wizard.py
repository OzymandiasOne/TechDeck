"""The "Build a schedule" flow.

Three steps, in the order a person actually thinks about their day:

1. **What are we covering?**, the window, plus the shape of your working day
   tucked behind Advanced so nobody has to look at it twice.
2. **What's on your plate?**, one row per task. The Task cell takes shorthand
   (``fix the PO sheet 45m urgent due friday``) and fills the other cells in,
   and a whole list can be pasted in at once. Everything typed here becomes a
   real task, so nothing is retyped next time.
3. **Here's the plan**, the generated agenda, what didn't fit, and why.

The dialog owns no scheduling logic; it collects a
:class:`~techdeck.core.assistant.scheduler.ScheduleRequest` and hands it over.
"""

from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QPushButton, QStackedWidget, QWidget, QRadioButton, QButtonGroup,
    QDateEdit, QSpinBox, QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QComboBox, QLineEdit, QHeaderView, QTextEdit, QMessageBox, QAbstractItemView,
    QFrame, QTimeEdit, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QDate, QTime, Signal
from PySide6.QtGui import QFont

from techdeck.core.assistant import nlp
from techdeck.core.assistant.models import (
    PRIORITIES, PRIORITY_LABELS, Schedule, SchedulePrefs, TaskItem,
    fmt_duration, parse_hhmm,
)
from techdeck.core.assistant.scheduler import (
    RANGE_CHOICES, ScheduleRequest, build_schedule, resolve_range, summarize,
)
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.dialogs.task_edit_dialog import TaskEditDialog
from techdeck.ui.theme_aware import ThemeAware

COL_TASK, COL_PRIORITY, COL_ESTIMATE, COL_DUE, COL_MORE = range(5)


class PasteTasksDialog(QDialog):
    """Bulk entry, paste the list you already wrote somewhere else."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste your list")
        self.setMinimumSize(560, 380)
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 18, 18, 14)
        box.setSpacing(10)

        blurb = QLabel(
            "One task per line. Dashes and numbering are fine, and any "
            "estimate, priority or due date on the line gets picked up:\n\n"
            "    - fix the PO sheet 45m urgent due friday\n"
            "    2. call Dan about rev C | high | 1h30\n"
            "    order 4130 tube 20m")
        blurb.setWordWrap(True)
        box.addWidget(blurb)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        box.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add them")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.editor.setFocus()

    def parsed_tasks(self) -> List[TaskItem]:
        out: List[TaskItem] = []
        for fields in nlp.parse_bullet_block(self.editor.toPlainText()):
            out.append(TaskItem(
                title=fields["title"],
                priority=fields.get("priority", "medium"),
                estimate_min=int(fields.get("estimate_min", 30)),
                deadline=fields.get("deadline"),
                fixed_start=fields.get("fixed_start"),
                splittable=bool(fields.get("splittable", True)),
                links=list(fields.get("links", [])),
            ))
        return out


class ScheduleWizard(QDialog, ThemeAware):
    """Collects the answers, builds the plan, saves it on accept."""

    STEP_TITLES = ["What are we planning?", "What's on your plate?",
                   "Here's the plan"]

    def __init__(self, store: AssistantStore, parent=None,
                 preset_range: str = ""):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Build a schedule")
        self.setMinimumSize(880, 620)
        self._row_tasks: List[TaskItem] = []
        self._schedule: Optional[Schedule] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 18)
        outer.setSpacing(14)

        self.heading = QLabel(self.STEP_TITLES[0])
        self.heading.setStyleSheet("font-size: 19px; font-weight: bold;")
        outer.addWidget(self.heading)

        self.step_label = QLabel("Step 1 of 3")
        outer.addWidget(self.step_label)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step_range())
        self.stack.addWidget(self._build_step_tasks())
        self.stack.addWidget(self._build_step_review())
        outer.addWidget(self.stack, 1)

        # --- navigation ------------------------------------------------------
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.back_btn = QPushButton("Back")
        self.back_btn.setMinimumHeight(34)
        self.back_btn.setMinimumWidth(90)
        self.back_btn.clicked.connect(self._back)
        nav.addWidget(self.back_btn)
        nav.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.clicked.connect(self.reject)
        nav.addWidget(self.cancel_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.setProperty("class", "primary")
        self.next_btn.setMinimumHeight(34)
        self.next_btn.setMinimumWidth(140)
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.next_btn)
        outer.addLayout(nav)

        self.setup_theme_awareness()
        if preset_range:
            self._select_range(preset_range)
        self._load_open_tasks()
        self._sync_nav()

    # ── step 1: range ────────────────────────────────────────────────────────

    def _build_step_range(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)

        blurb = QLabel("Pick the window. I'll only plan inside your working "
                       "hours, and I'll never plan into the past.")
        blurb.setWordWrap(True)
        box.addWidget(blurb)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.range_group = QButtonGroup(self)
        self._range_buttons: Dict[str, QRadioButton] = {}
        for index, (key, label) in enumerate(RANGE_CHOICES):
            button = QRadioButton(label)
            button.setMinimumHeight(30)
            button.setProperty("rangeKey", key)
            self.range_group.addButton(button, index)
            self._range_buttons[key] = button
            grid.addWidget(button, index // 2, index % 2)
        self._range_buttons["rest_of_today"].setChecked(True)
        self.range_group.buttonClicked.connect(lambda _b: self._sync_range_inputs())
        box.addLayout(grid)

        # Date inputs, shown only for the two ranges that need them.
        self.date_row = QWidget()
        date_form = QHBoxLayout(self.date_row)
        date_form.setContentsMargins(0, 0, 0, 0)
        date_form.setSpacing(8)
        self.from_label = QLabel("Day")
        self.from_date = QDateEdit(QDate.currentDate())
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("ddd, MMM d yyyy")
        self.from_date.setMinimumHeight(30)
        self.to_label = QLabel("through")
        self.to_date = QDateEdit(QDate.currentDate().addDays(4))
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("ddd, MMM d yyyy")
        self.to_date.setMinimumHeight(30)
        for widget in (self.from_label, self.from_date, self.to_label, self.to_date):
            date_form.addWidget(widget)
        date_form.addStretch()
        box.addWidget(self.date_row)

        # --- advanced --------------------------------------------------------
        self.advanced = QGroupBox("Your working day")
        self.advanced.setCheckable(True)
        self.advanced.setChecked(False)
        advanced_form = QFormLayout(self.advanced)
        advanced_form.setSpacing(9)

        prefs = self.store.prefs
        self.day_start = QTimeEdit(_qtime(prefs.day_start, 7, 0))
        self.day_start.setDisplayFormat("h:mm AP")
        self.day_end = QTimeEdit(_qtime(prefs.day_end, 15, 30))
        self.day_end.setDisplayFormat("h:mm AP")
        hours_row = QHBoxLayout()
        hours_row.addWidget(self.day_start)
        hours_row.addWidget(QLabel("to"))
        hours_row.addWidget(self.day_end)
        hours_row.addStretch()
        advanced_form.addRow("Hours", hours_row)

        self.lunch_start = QTimeEdit(_qtime(prefs.lunch_start, 11, 30))
        self.lunch_start.setDisplayFormat("h:mm AP")
        self.lunch_minutes = QSpinBox()
        self.lunch_minutes.setRange(0, 180)
        self.lunch_minutes.setSingleStep(5)
        self.lunch_minutes.setSuffix(" min")
        self.lunch_minutes.setValue(prefs.lunch_minutes)
        lunch_row = QHBoxLayout()
        lunch_row.addWidget(self.lunch_start)
        lunch_row.addWidget(QLabel("for"))
        lunch_row.addWidget(self.lunch_minutes)
        lunch_row.addWidget(QLabel("(0 = skip it)"))
        lunch_row.addStretch()
        advanced_form.addRow("Lunch", lunch_row)

        self.focus_block = QSpinBox()
        self.focus_block.setRange(0, 480)
        self.focus_block.setSingleStep(15)
        self.focus_block.setSuffix(" min")
        self.focus_block.setValue(prefs.focus_block_min)
        self.breather = QSpinBox()
        self.breather.setRange(0, 60)
        self.breather.setSingleStep(5)
        self.breather.setSuffix(" min")
        self.breather.setValue(prefs.breather_min)
        focus_row = QHBoxLayout()
        focus_row.addWidget(self.focus_block)
        focus_row.addWidget(QLabel("of work, then a"))
        focus_row.addWidget(self.breather)
        focus_row.addWidget(QLabel("breather (0 = never break)"))
        focus_row.addStretch()
        advanced_form.addRow("Focus", focus_row)

        self.min_chunk = QSpinBox()
        self.min_chunk.setRange(5, 240)
        self.min_chunk.setSingleStep(5)
        self.min_chunk.setSuffix(" min")
        self.min_chunk.setValue(prefs.min_chunk_min)
        advanced_form.addRow("Smallest useful slice", self.min_chunk)

        self.buffer = QSpinBox()
        self.buffer.setRange(0, 100)
        self.buffer.setSingleStep(5)
        self.buffer.setSuffix(" %")
        self.buffer.setValue(prefs.buffer_pct)
        self.buffer.setToolTip(
            "Everyone underestimates. This pads every estimate so the plan "
            "survives contact with the actual day.")
        advanced_form.addRow("Pad estimates by", self.buffer)

        self.weekends = QCheckBox("Plan on weekends too")
        self.weekends.setChecked(prefs.include_weekends)
        advanced_form.addRow("", self.weekends)

        box.addWidget(self.advanced)
        box.addStretch()
        self._sync_range_inputs()
        return page

    def _select_range(self, key: str):
        button = self._range_buttons.get(key)
        if button is not None:
            button.setChecked(True)
            self._sync_range_inputs()

    def _current_range_key(self) -> str:
        for key, button in self._range_buttons.items():
            if button.isChecked():
                return key
        return "rest_of_today"

    def _sync_range_inputs(self):
        key = self._current_range_key()
        needs_one = key == "pick_day"
        needs_two = key == "custom"
        self.date_row.setVisible(needs_one or needs_two)
        self.to_label.setVisible(needs_two)
        self.to_date.setVisible(needs_two)
        self.from_label.setText("From" if needs_two else "Day")

    def _collect_prefs(self) -> SchedulePrefs:
        prefs = SchedulePrefs.from_dict({
            "day_start": self.day_start.time().toString("HH:mm"),
            "day_end": self.day_end.time().toString("HH:mm"),
            "lunch_start": self.lunch_start.time().toString("HH:mm"),
            "lunch_minutes": self.lunch_minutes.value(),
            "include_weekends": self.weekends.isChecked(),
            "focus_block_min": self.focus_block.value(),
            "breather_min": self.breather.value(),
            "min_chunk_min": self.min_chunk.value(),
            "buffer_pct": self.buffer.value(),
        })
        return prefs

    # ── step 2: tasks ────────────────────────────────────────────────────────

    def _build_step_tasks(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        blurb = QLabel(
            "Tick what to include. Type a task however you'd say it: "
            "“fix the PO sheet 45m urgent due friday” fills in the rest of "
            "the row for you.")
        blurb.setWordWrap(True)
        box.addWidget(blurb)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Task", "Priority", "Time needed", "Due", ""])
        self.table.verticalHeader().setVisible(False)
        # Cell widgets (combo/spin/line-edit) are ~28px tall; the default row
        # height clips them, so the Due box loses its bottom edge.
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_TASK, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_PRIORITY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ESTIMATE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_DUE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_MORE, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_PRIORITY, 110)
        self.table.setColumnWidth(COL_ESTIMATE, 110)
        self.table.setColumnWidth(COL_DUE, 130)
        self.table.setColumnWidth(COL_MORE, 50)
        self.table.itemChanged.connect(self._on_item_changed)
        box.addWidget(self.table, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        add_btn = QPushButton("Add a task")
        add_btn.setMinimumHeight(32)
        add_btn.clicked.connect(lambda: self._add_row(TaskItem(), focus=True))
        controls.addWidget(add_btn)

        paste_btn = QPushButton("Paste a list…")
        paste_btn.setMinimumHeight(32)
        paste_btn.clicked.connect(self._paste_list)
        controls.addWidget(paste_btn)

        remove_btn = QPushButton("Remove selected")
        remove_btn.setMinimumHeight(32)
        remove_btn.clicked.connect(self._remove_selected)
        controls.addWidget(remove_btn)

        controls.addStretch()
        self.tick_all = QCheckBox("Tick everything")
        self.tick_all.setChecked(True)
        self.tick_all.toggled.connect(self._tick_all)
        controls.addWidget(self.tick_all)

        self.load_total = QLabel("")
        controls.addWidget(self.load_total)
        box.addLayout(controls)
        return page

    def _load_open_tasks(self):
        for task in self.store.open_tasks():
            self._add_row(task, checked=True)
        if not self._row_tasks:
            self._add_row(TaskItem())
        self._update_load_total()

    def _add_row(self, task: TaskItem, checked: bool = True, focus: bool = False):
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self._row_tasks.append(task)

        item = QTableWidgetItem(task.title)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                      | Qt.ItemFlag.ItemIsEditable)
        item.setCheckState(Qt.CheckState.Checked if checked
                           else Qt.CheckState.Unchecked)
        self.table.setItem(row, COL_TASK, item)

        priority = QComboBox()
        for key in PRIORITIES:
            priority.addItem(PRIORITY_LABELS[key], key)
        priority.setCurrentIndex(max(0, priority.findData(task.priority)))
        priority.currentIndexChanged.connect(
            lambda _i, r=row: self._pull_row(r))
        self.table.setCellWidget(row, COL_PRIORITY, priority)

        estimate = QSpinBox()
        estimate.setRange(5, 24 * 60)
        estimate.setSingleStep(5)
        estimate.setSuffix(" min")
        estimate.setValue(max(5, int(task.estimate_min or 30)))
        estimate.valueChanged.connect(lambda _v, r=row: self._pull_row(r))
        self.table.setCellWidget(row, COL_ESTIMATE, estimate)

        due = QLineEdit(task.deadline or "")
        due.setPlaceholderText("friday")
        due.setToolTip("Type a day: friday, tomorrow, 8/14. Or leave it blank")
        due.editingFinished.connect(lambda r=row: self._normalize_due(r))
        self.table.setCellWidget(row, COL_DUE, due)

        more = QPushButton("···")
        more.setToolTip("Notes, links, exact start time, “one sitting”")
        more.setFixedSize(40, 28)
        more.clicked.connect(lambda _c=False, r=row: self._open_details(r))
        self.table.setCellWidget(row, COL_MORE, more)

        self.table.blockSignals(False)
        if focus:
            self.table.setCurrentCell(row, COL_TASK)
            self.table.editItem(item)
        self._update_load_total()

    def _on_item_changed(self, item: QTableWidgetItem):
        """A typed Task cell is run through the shorthand parser, and anything
        it recognises is lifted into the neighbouring cells."""
        if item.column() != COL_TASK:
            return
        row = item.row()
        if row >= len(self._row_tasks):
            return
        text = item.text().strip()
        task = self._row_tasks[row]

        parsed = nlp.parse_task_line(text) if text else {}
        title = parsed.get("title", text)

        self.table.blockSignals(True)
        if title != text:
            item.setText(title)
        task.title = title

        if "priority" in parsed:
            widget = self.table.cellWidget(row, COL_PRIORITY)
            if widget is not None:
                widget.setCurrentIndex(max(0, widget.findData(parsed["priority"])))
        if "estimate_min" in parsed:
            widget = self.table.cellWidget(row, COL_ESTIMATE)
            if widget is not None:
                widget.setValue(int(parsed["estimate_min"]))
        if "deadline" in parsed:
            widget = self.table.cellWidget(row, COL_DUE)
            if widget is not None:
                widget.setText(parsed["deadline"])
        if "fixed_start" in parsed:
            task.fixed_start = parsed["fixed_start"]
        if "splittable" in parsed:
            task.splittable = bool(parsed["splittable"])
        if parsed.get("links"):
            task.links = list(dict.fromkeys(task.links + list(parsed["links"])))
        self.table.blockSignals(False)

        self._pull_row(row)

    def _pull_row(self, row: int):
        """Read the widgets back into the row's TaskItem."""
        if row >= len(self._row_tasks):
            return
        task = self._row_tasks[row]
        item = self.table.item(row, COL_TASK)
        if item is not None:
            task.title = item.text().strip()
        priority = self.table.cellWidget(row, COL_PRIORITY)
        if priority is not None:
            task.priority = priority.currentData() or "medium"
        estimate = self.table.cellWidget(row, COL_ESTIMATE)
        if estimate is not None:
            task.estimate_min = int(estimate.value())
        due = self.table.cellWidget(row, COL_DUE)
        if due is not None:
            task.deadline = _parse_due(due.text())
        self._update_load_total()

    def _normalize_due(self, row: int):
        """Rewrite whatever was typed in the Due cell as the date it resolved
        to, instant, unambiguous feedback instead of a silent guess."""
        widget = self.table.cellWidget(row, COL_DUE)
        if widget is None:
            return
        resolved = _parse_due(widget.text())
        widget.setText(resolved or "")
        self._pull_row(row)

    def _open_details(self, row: int):
        if row >= len(self._row_tasks):
            return
        self._pull_row(row)
        dialog = TaskEditDialog(self._row_tasks[row], parent=self,
                                title="Task details")
        if not dialog.exec():
            return
        task = dialog.result_task()
        self._row_tasks[row] = task
        self.table.blockSignals(True)
        item = self.table.item(row, COL_TASK)
        if item is not None:
            item.setText(task.title)
        priority = self.table.cellWidget(row, COL_PRIORITY)
        if priority is not None:
            priority.setCurrentIndex(max(0, priority.findData(task.priority)))
        estimate = self.table.cellWidget(row, COL_ESTIMATE)
        if estimate is not None:
            estimate.setValue(max(5, task.estimate_min))
        due = self.table.cellWidget(row, COL_DUE)
        if due is not None:
            due.setText(task.deadline or "")
        self.table.blockSignals(False)
        self._update_load_total()

    def _paste_list(self):
        dialog = PasteTasksDialog(self)
        if not dialog.exec():
            return
        tasks = dialog.parsed_tasks()
        if not tasks:
            QMessageBox.information(self, "Nothing found",
                                    "I couldn't find any tasks in that.")
            return
        # An untouched placeholder row would otherwise sit above the paste.
        if len(self._row_tasks) == 1 and not self._row_tasks[0].title.strip():
            self._remove_row(0)
        for task in tasks:
            self._add_row(task, checked=True)

    def _remove_selected(self):
        rows = sorted({index.row() for index in
                       self.table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            current = self.table.currentRow()
            if current < 0:
                return
            rows = [current]
        for row in rows:
            self._remove_row(row)
        if not self._row_tasks:
            self._add_row(TaskItem())

    def _remove_row(self, row: int):
        if 0 <= row < len(self._row_tasks):
            self.table.removeRow(row)
            del self._row_tasks[row]
            self._rebind_row_callbacks()
            self._update_load_total()

    def _rebind_row_callbacks(self):
        """Row indices shift when a row is removed, and the lambdas captured the
        OLD index, re-point every one of them at its current row."""
        for row in range(self.table.rowCount()):
            priority = self.table.cellWidget(row, COL_PRIORITY)
            if priority is not None:
                try:
                    priority.currentIndexChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                priority.currentIndexChanged.connect(
                    lambda _i, r=row: self._pull_row(r))
            estimate = self.table.cellWidget(row, COL_ESTIMATE)
            if estimate is not None:
                try:
                    estimate.valueChanged.disconnect()
                except (TypeError, RuntimeError):
                    pass
                estimate.valueChanged.connect(lambda _v, r=row: self._pull_row(r))
            due = self.table.cellWidget(row, COL_DUE)
            if due is not None:
                try:
                    due.editingFinished.disconnect()
                except (TypeError, RuntimeError):
                    pass
                due.editingFinished.connect(lambda r=row: self._normalize_due(r))
            more = self.table.cellWidget(row, COL_MORE)
            if more is not None:
                try:
                    more.clicked.disconnect()
                except (TypeError, RuntimeError):
                    pass
                more.clicked.connect(lambda _c=False, r=row: self._open_details(r))

    def _tick_all(self, checked: bool):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_TASK)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked if checked
                                   else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_load_total()

    def _checked_tasks(self) -> List[TaskItem]:
        out: List[TaskItem] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_TASK)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            self._pull_row(row)
            if row < len(self._row_tasks) and self._row_tasks[row].title.strip():
                out.append(self._row_tasks[row])
        return out

    def _update_load_total(self):
        tasks = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_TASK)
            if item is not None and item.checkState() == Qt.CheckState.Checked \
                    and row < len(self._row_tasks) \
                    and self._row_tasks[row].title.strip():
                tasks.append(self._row_tasks[row])
        total = sum(t.estimate_min for t in tasks)
        self.load_total.setText(
            f"{len(tasks)} ticked · {fmt_duration(total)} of work")

    # ── step 3: review ───────────────────────────────────────────────────────

    def _build_step_review(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        self.review_summary = QLabel("")
        self.review_summary.setWordWrap(True)
        box.addWidget(self.review_summary)

        self.review_view = QTextEdit()
        self.review_view.setReadOnly(True)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.review_view.setFont(font)
        self.review_view.setFrameShape(QFrame.Shape.NoFrame)
        box.addWidget(self.review_view, 1)
        return page

    def _generate(self) -> bool:
        tasks = self._checked_tasks()
        if not tasks:
            QMessageBox.information(
                self, "Nothing to plan",
                "Tick at least one task before I can build anything.")
            return False

        prefs = self._collect_prefs()
        self.store.save_prefs(prefs)

        # Everything on the grid becomes a real task, so the backlog and the
        # plan can never drift apart.
        known = {t.id for t in self.store.tasks}
        for task in self._row_tasks:
            if not task.title.strip():
                continue
            if task.id in known:
                self.store.update_task(task)
            else:
                self.store.add_task(task)

        key = self._current_range_key()
        anchor = _qdate_to_date(self.from_date.date())
        end_anchor = _qdate_to_date(self.to_date.date())
        start_day, end_day, label = resolve_range(
            key, anchor=anchor, end_anchor=end_anchor)

        first_start: Optional[time] = None
        if key == "rest_of_today":
            now = datetime.now()
            first_start = time(now.hour, now.minute)

        self._schedule = build_schedule(ScheduleRequest(
            tasks=tasks, start_day=start_day, end_day=end_day, prefs=prefs,
            label=label, first_day_start=first_start))
        self.store.add_schedule(self._schedule)
        self._render_review()
        return True

    def _render_review(self):
        schedule = self._schedule
        if schedule is None:
            return
        palette = self.get_current_palette()
        stats = schedule.stats or {}
        bits = [f"{stats.get('tasks_placed', 0)} tasks placed",
                f"{fmt_duration(stats.get('work_minutes', 0))} of work"]
        if stats.get("tasks_unplaced"):
            bits.append(f"{stats['tasks_unplaced']} didn't fit")
        headline = "  ·  ".join(bits)
        colour = palette.warning if schedule.warnings else palette.text_secondary
        self.review_summary.setText(headline)
        self.review_summary.setStyleSheet(f"color: {colour}; font-size: 12px;")
        self.review_view.setPlainText(summarize(schedule))

    # ── navigation ───────────────────────────────────────────────────────────

    def _sync_nav(self):
        index = self.stack.currentIndex()
        self.heading.setText(self.STEP_TITLES[index])
        self.step_label.setText(f"Step {index + 1} of 3")
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setText(
            ["Next", "Build it", "Save this plan"][index])

    def _next(self):
        index = self.stack.currentIndex()
        if index == 0:
            self.stack.setCurrentIndex(1)
        elif index == 1:
            if not self._generate():
                return
            self.stack.setCurrentIndex(2)
        else:
            self.accept()
        self._sync_nav()

    def _back(self):
        index = self.stack.currentIndex()
        if index > 0:
            # Stepping back from the review discards the generated plan; it is
            # regenerated on the way forward, so a stale one can't be saved.
            if index == 2 and self._schedule is not None:
                self.store.delete_schedule(self._schedule.id)
                self._schedule = None
            self.stack.setCurrentIndex(index - 1)
            self._sync_nav()

    def result_schedule(self) -> Optional[Schedule]:
        return self._schedule

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(f"QDialog {{ background: {palette.background}; }}")
        self.step_label.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 12px;")
        if hasattr(self, "review_view"):
            self.review_view.setStyleSheet(
                f"QTextEdit {{ background: {palette.console_bg}; "
                f"color: {palette.console_text}; border: 1px solid "
                f"{palette.border}; border-radius: 8px; padding: 10px; }}")
        if hasattr(self, "table"):
            self.table.setStyleSheet(f"""
                QTableWidget {{
                    background: {palette.surface};
                    border: 1px solid {palette.border};
                    border-radius: 8px;
                    gridline-color: {palette.border};
                    color: {palette.text};
                }}
                QHeaderView::section {{
                    background: {palette.background};
                    color: {palette.text_secondary};
                    border: none;
                    border-bottom: 1px solid {palette.border};
                    padding: 6px;
                    font-weight: bold;
                }}
            """)
        if hasattr(self, "load_total"):
            self.load_total.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 12px;")


# ── small helpers ────────────────────────────────────────────────────────────

def _qtime(value: str, hour: int, minute: int) -> QTime:
    parsed = parse_hhmm(value, time(hour, minute))
    return QTime(parsed.hour, parsed.minute)


def _qdate_to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


def _parse_due(text: str) -> Optional[str]:
    """Free-text due date → ISO date string, or None. Accepts what's already
    ISO so re-normalising a cell is idempotent."""
    text = (text or "").strip()
    if not text:
        return None
    when = nlp.parse_when(text)
    if when.day is not None:
        return when.day.isoformat()
    return None
