"""Edit one task in full, the long form behind the terminal's one-liner.

Typing ``fix the PO sheet 45m urgent due friday`` covers the common case; this
dialog covers everything else (notes, links, an exact start time, "must be one
sitting"). Both the Tasks tab and the schedule builder open it, so a task has
exactly one editing surface no matter where you found it.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QCheckBox, QDateEdit, QTimeEdit, QPushButton, QLabel,
    QDialogButtonBox, QGroupBox, QMessageBox,
)
from PySide6.QtCore import Qt, QDate, QTime

from techdeck.core.assistant.models import (
    PRIORITIES, PRIORITY_LABELS, ChecklistItem, TaskItem, fmt_duration,
    now_iso,
)
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import SCOPE_ASSISTANT


class TaskEditDialog(QDialog, ThemeAware):
    """Returns the edited TaskItem via :meth:`result_task` after ``exec()``."""

    # Follows the Assistant's own theme when one is pinned (Settings ->
    # Personalization -> Assistant Page Theme), else the app's.
    THEME_SCOPE = SCOPE_ASSISTANT

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

        # Parked on somebody else. A waiting task is deliberately NOT
        # scheduled, so the checkbox says what it costs, and naming the person
        # stays optional: a forced prompt is a reason to skip the flag.
        waiting_row = QHBoxLayout()
        self.waiting = QCheckBox("Waiting on someone else")
        self.waiting.setToolTip(
            "It won't be scheduled until you take it back off them. "
            "You'll get a nudge if it sits too long.")
        self.waiting.setChecked(self._task.waiting)
        self.waiting_on = QLineEdit(self._task.waiting_on)
        self.waiting_on.setPlaceholderText("who or what (optional)")
        self.waiting_on.setMinimumHeight(30)
        self.waiting_on.setEnabled(self.waiting.isChecked())
        self.waiting.toggled.connect(self.waiting_on.setEnabled)
        waiting_row.addWidget(self.waiting)
        waiting_row.addWidget(self.waiting_on, 1)
        when_form.addRow(waiting_row)

        outer.addWidget(when_box)

        # --- steps ----------------------------------------------------------
        # Authored as TEXT, one step per line, parsed with the same grammar as
        # a task line. That keeps a long project's checklist as fast to write
        # as it is to say, and gives per-step times and dates for free instead
        # of a grid of spinboxes. Ticking steps off happens on the Tasks tab,
        # one click each, which is the job this box would be bad at.
        steps_box = QGroupBox("Steps")
        steps_layout = QVBoxLayout(steps_box)
        steps_layout.setSpacing(6)

        self.steps_hint = QLabel(
            "One per line. Each can carry its own time and date: "
            "“order the tube 20m due friday”. Start a line with x to mark it "
            "done. Tick them off on the Tasks tab.")
        self.steps_hint.setWordWrap(True)
        steps_layout.addWidget(self.steps_hint)

        self.steps = QTextEdit()
        self.steps.setAcceptRichText(False)
        self.steps.setPlaceholderText(
            "x pull the drawings 15m\nbuild the kit sheet 45m due friday\n"
            "walk it to QA 10m")
        self.steps.setPlainText(self._steps_to_text(self._task))
        self.steps.setMaximumHeight(110)
        steps_layout.addWidget(self.steps)

        roll_row = QHBoxLayout()
        self.roll_btn = QPushButton("Use the steps' total as the estimate")
        self.roll_btn.setMinimumHeight(28)
        self.roll_btn.setToolTip(
            "Adds up the times on the steps and puts it in “Time needed”")
        self.roll_btn.clicked.connect(self._roll_up_estimate)
        roll_row.addWidget(self.roll_btn)
        roll_row.addStretch()
        steps_layout.addLayout(roll_row)

        outer.addWidget(steps_box)

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

    # ── steps as text ────────────────────────────────────────────────────────

    @staticmethod
    def _steps_to_text(task: TaskItem) -> str:
        """Round-trip the checklist back to the shape it was typed in.

        A done step comes back with its ``x `` marker, and a step's own time
        and date are re-appended in the inline form the parser reads, so
        editing the box never quietly drops what the step already knew.
        """
        lines = []
        for step in task.checklist:
            bits = [step.text.strip()]
            if step.estimate_min:
                bits.append(f"{step.estimate_min}m")
            if step.deadline:
                bits.append(f"due {step.deadline}")
            prefix = "x " if step.done else ""
            lines.append(prefix + " ".join(bit for bit in bits if bit))
        return "\n".join(lines)

    def _parse_steps(self) -> List[ChecklistItem]:
        """Read the box back into steps, keeping each one's identity.

        Matching by TEXT rather than by position: a step that keeps its words
        keeps its id, its done stamp and the reminders already sent about it,
        even when the line above it was deleted.
        """
        from techdeck.core.assistant import nlp

        existing = {step.text.strip().lower(): step
                    for step in self._task.checklist}
        out: List[ChecklistItem] = []
        for raw in self.steps.toPlainText().splitlines():
            line = raw.strip()
            if not line:
                continue
            done = False
            # "x ", "X ", "[x] " and "- [x] " all mean the same thing, because
            # all four are things people type.
            for marker in ("- [x] ", "[x] ", "x ", "X "):
                if line.lower().startswith(marker.lower()):
                    done = True
                    line = line[len(marker):].strip()
                    break
            parsed = nlp.parse_task_line(line)
            text = (parsed.get("title") or "").strip()
            if not text:
                continue
            step = existing.get(text.lower())
            if step is None:
                step = ChecklistItem(text=text)
            step.text = text
            step.estimate_min = int(parsed.get("estimate_min") or 0)
            step.deadline = parsed.get("deadline")
            if done and not step.done:
                step.done_at = now_iso()
            elif not done:
                step.done_at = None
            step.done = done
            out.append(step)
        return out

    def _roll_up_estimate(self):
        """Put the steps' total into Time needed. Explicit, on a button: a
        silently derived estimate would make the next plan a stranger."""
        total = sum(step.estimate_min for step in self._parse_steps())
        if total <= 0:
            QMessageBox.information(
                self, "No times on the steps",
                "Add a time to at least one step first — "
                "“pull the drawings 15m”.")
            return
        self.estimate.setValue(max(5, min(self.estimate.maximum(), total)))

    def apply_theme(self):
        palette = self.get_current_palette()
        # Top-level window: not a child of the Assistant page, so it
        # inherits nothing and carries the scoped sheet itself.
        self.setStyleSheet(
            self.scope_stylesheet()
            + f"QDialog {{ background: {palette.background}; }}")
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
        task.checklist = self._parse_steps()

        # waiting_since is stamped only when the flag GOES on, so re-saving
        # the task (or correcting who you are waiting on) does not restart the
        # clock the follow-up nudge counts from.
        waiting = self.waiting.isChecked()
        if waiting and not task.waiting:
            task.waiting_since = now_iso()
        elif not waiting:
            task.waiting_since = None
        task.waiting = waiting
        task.waiting_on = (self.waiting_on.text().strip() if waiting else "")

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
