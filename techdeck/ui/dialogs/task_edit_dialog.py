"""Edit one task in full, the long form behind the terminal's one-liner.

Typing ``fix the PO sheet 45m urgent due friday`` covers the common case; this
dialog covers everything else (notes, links, an exact start time, "must be one
sitting"). Both the Tasks tab and the schedule builder open it, so a task has
exactly one editing surface no matter where you found it.
"""

from __future__ import annotations

from datetime import datetime, date, time
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QCheckBox, QDateEdit, QTimeEdit, QPushButton, QLabel,
    QDialogButtonBox, QGroupBox,
)
from PySide6.QtCore import Qt, QDate, QTime

from techdeck.core.assistant.models import (
    PRIORITIES, PRIORITY_LABELS, TaskItem, fmt_duration,
)
from techdeck.ui.theme_aware import ThemeAware


class TaskEditDialog(QDialog, ThemeAware):
    """Returns the edited TaskItem via :meth:`result_task` after ``exec()``."""

    def __init__(self, task: Optional[TaskItem] = None, parent=None,
                 title: str = "Task"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        # Work on a copy so Cancel really cancels.
        self._task = TaskItem.from_dict(task.to_dict()) if task else TaskItem()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.title_field = QLineEdit(self._task.title)
        self.title_field.setPlaceholderText("What needs doing?")
        self.title_field.setMinimumHeight(32)
        form.addRow("Task", self.title_field)

        self.priority = QComboBox()
        for key in PRIORITIES:
            self.priority.addItem(PRIORITY_LABELS[key], key)
        index = self.priority.findData(self._task.priority)
        self.priority.setCurrentIndex(max(0, index))
        self.priority.setMinimumHeight(30)
        form.addRow("Priority", self.priority)

        estimate_row = QHBoxLayout()
        self.estimate = QSpinBox()
        self.estimate.setRange(5, 24 * 60)
        self.estimate.setSingleStep(5)
        self.estimate.setSuffix(" min")
        self.estimate.setValue(max(5, int(self._task.estimate_min or 30)))
        self.estimate.setMinimumHeight(30)
        self.estimate.setMinimumWidth(120)
        self.estimate_hint = QLabel()
        self.estimate.valueChanged.connect(self._update_estimate_hint)
        estimate_row.addWidget(self.estimate)
        estimate_row.addWidget(self.estimate_hint)
        estimate_row.addStretch()
        form.addRow("Time needed", estimate_row)
        self._update_estimate_hint(self.estimate.value())

        outer.addLayout(form)

        # --- when -----------------------------------------------------------
        when_box = QGroupBox("When")
        when_form = QFormLayout(when_box)
        when_form.setSpacing(10)

        deadline_row = QHBoxLayout()
        self.has_deadline = QCheckBox("Must be done by")
        self.deadline = QDateEdit()
        self.deadline.setCalendarPopup(True)
        self.deadline.setDisplayFormat("ddd, MMM d yyyy")
        self.deadline.setMinimumHeight(30)
        existing_due = self._task.deadline_date()
        self.has_deadline.setChecked(existing_due is not None)
        self.deadline.setDate(QDate(existing_due.year, existing_due.month,
                                    existing_due.day) if existing_due
                              else QDate.currentDate())
        self.deadline.setEnabled(self.has_deadline.isChecked())
        self.has_deadline.toggled.connect(self.deadline.setEnabled)
        deadline_row.addWidget(self.has_deadline)
        deadline_row.addWidget(self.deadline, 1)
        when_form.addRow(deadline_row)

        fixed_row = QHBoxLayout()
        self.has_fixed = QCheckBox("Locked to a time")
        self.fixed_date = QDateEdit()
        self.fixed_date.setCalendarPopup(True)
        self.fixed_date.setDisplayFormat("ddd, MMM d")
        self.fixed_date.setMinimumHeight(30)
        self.fixed_time = QTimeEdit()
        self.fixed_time.setDisplayFormat("h:mm AP")
        self.fixed_time.setMinimumHeight(30)
        existing_fixed = self._task.fixed_datetime()
        self.has_fixed.setChecked(existing_fixed is not None)
        if existing_fixed:
            self.fixed_date.setDate(QDate(existing_fixed.year,
                                          existing_fixed.month,
                                          existing_fixed.day))
            self.fixed_time.setTime(QTime(existing_fixed.hour,
                                          existing_fixed.minute))
        else:
            self.fixed_date.setDate(QDate.currentDate())
            self.fixed_time.setTime(QTime(9, 0))
        for widget in (self.fixed_date, self.fixed_time):
            widget.setEnabled(self.has_fixed.isChecked())
            self.has_fixed.toggled.connect(widget.setEnabled)
        fixed_row.addWidget(self.has_fixed)
        fixed_row.addWidget(self.fixed_date, 1)
        fixed_row.addWidget(self.fixed_time, 0)
        when_form.addRow(fixed_row)

        self.one_sitting = QCheckBox(
            "Do it in one sitting (never split across blocks)")
        self.one_sitting.setChecked(not self._task.splittable)
        when_form.addRow(self.one_sitting)

        outer.addWidget(when_box)

        # --- notes + links ---------------------------------------------------
        self.notes = QTextEdit()
        self.notes.setAcceptRichText(False)
        self.notes.setPlaceholderText("Anything you'll want in front of you "
                                      "when you sit down to do this…")
        self.notes.setPlainText(self._task.notes)
        self.notes.setMaximumHeight(90)
        outer.addWidget(QLabel("Notes"))
        outer.addWidget(self.notes)

        self.links = QTextEdit()
        self.links.setAcceptRichText(False)
        self.links.setPlaceholderText(
            r"One per line, https://… or C:\path\to\file.xlsx")
        self.links.setPlainText("\n".join(self._task.links))
        self.links.setMaximumHeight(70)
        outer.addWidget(QLabel("Links / files"))
        outer.addWidget(self.links)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.setup_theme_awareness()
        self.title_field.setFocus()

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(f"QDialog {{ background: {palette.background}; }}")
        self.estimate_hint.setStyleSheet(f"color: {palette.text_secondary};")

    def _update_estimate_hint(self, minutes: int):
        self.estimate_hint.setText(f"({fmt_duration(minutes)})")

    def _accept(self):
        if not self.title_field.text().strip():
            self.title_field.setFocus()
            return
        self.accept()

    def result_task(self) -> TaskItem:
        task = self._task
        task.title = self.title_field.text().strip()
        task.priority = self.priority.currentData() or "medium"
        task.estimate_min = int(self.estimate.value())
        task.splittable = not self.one_sitting.isChecked()
        task.notes = self.notes.toPlainText().strip()
        task.links = [line.strip() for line in
                      self.links.toPlainText().splitlines() if line.strip()]

        if self.has_deadline.isChecked():
            qdate = self.deadline.date()
            task.deadline = date(qdate.year(), qdate.month(),
                                 qdate.day()).isoformat()
        else:
            task.deadline = None

        if self.has_fixed.isChecked():
            qdate, qtime = self.fixed_date.date(), self.fixed_time.time()
            task.fixed_start = datetime(
                qdate.year(), qdate.month(), qdate.day(),
                qtime.hour(), qtime.minute()).isoformat()
        else:
            task.fixed_start = None
        return task
