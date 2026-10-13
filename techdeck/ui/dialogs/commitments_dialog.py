"""Meetings and other standing claims on the day.

Before this existed, the only way to tell the planner about a 9am production
meeting was to file it as a *task* with a locked start time -- which then sat
in the backlog asking to be ticked off, counted as work you owed somebody, and
inflated every estimate on the page. A meeting is none of those things. It is
time you do not have.

So this dialog edits :class:`~techdeck.core.assistant.models.Commitment`
objects: a title, a start, a length, and either a date (one-off) or a set of
weekdays (the standing huddle). No priority, no estimate, no done state. The
engine simply never plans work into that time.

Reached from the Schedule tab's "Meetings" button and from ``/blocks``.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QLineEdit, QSpinBox, QTimeEdit, QDateEdit, QCheckBox,
    QDialogButtonBox, QGroupBox, QFormLayout, QMessageBox, QRadioButton,
    QButtonGroup, QWidget,
)
from PySide6.QtCore import Qt, QTime, QDate

from techdeck.core.assistant.models import (
    Commitment, WEEKDAY_LABELS, fmt_duration,
)
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import SCOPE_ASSISTANT


class CommitmentsDialog(QDialog, ThemeAware):
    """The list on the left, the one being edited on the right.

    Edits are applied to the store as they are confirmed, not batched behind an
    OK: the list IS the saved state, so there is no half-saved middle where the
    plan and the dialog disagree.
    """

    # Follows the Assistant's own theme when one is pinned (Settings ->
    # Personalization -> Assistant Page Theme), else the app's.
    THEME_SCOPE = SCOPE_ASSISTANT

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Meetings & blocked time")
        self.setMinimumWidth(680)
        self.setMinimumHeight(430)
        self._editing: Optional[Commitment] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        self.blurb = QLabel(
            "Time that is already spoken for. The planner works around it "
            "instead of booking work on top of it.")
        self.blurb.setWordWrap(True)
        outer.addWidget(self.blurb)

        body = QHBoxLayout()
        body.setSpacing(16)

        # --- the list --------------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(8)
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self.list, 1)

        list_buttons = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.new_btn.setMinimumHeight(30)
        self.new_btn.clicked.connect(self._new)
        self.delete_btn = QPushButton("Remove")
        self.delete_btn.setMinimumHeight(30)
        self.delete_btn.clicked.connect(self._delete)
        list_buttons.addWidget(self.new_btn)
        list_buttons.addWidget(self.delete_btn)
        list_buttons.addStretch()
        left.addLayout(list_buttons)
        body.addLayout(left, 1)

        # --- the editor ------------------------------------------------------
        self.editor = QGroupBox("Details")
        form = QFormLayout(self.editor)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Production meeting")
        self.title_field.setMinimumHeight(30)
        form.addRow("What", self.title_field)

        start_row = QHBoxLayout()
        self.start = QTimeEdit()
        self.start.setDisplayFormat("h:mm AP")
        self.start.setMinimumHeight(30)
        self.length = QSpinBox()
        self.length.setRange(5, 12 * 60)
        self.length.setSingleStep(5)
        self.length.setSuffix(" min")
        self.length.setMinimumHeight(30)
        self.length_hint = QLabel()
        self.length.valueChanged.connect(
            lambda value: self.length_hint.setText(f"({fmt_duration(value)})"))
        start_row.addWidget(self.start)
        start_row.addWidget(QLabel("for"))
        start_row.addWidget(self.length)
        start_row.addWidget(self.length_hint)
        start_row.addStretch()
        form.addRow("When", start_row)

        # Weekly vs one-off. Two radios rather than a "repeats?" checkbox: the
        # standing weekly meeting is the common case and should not be the one
        # you have to go and switch on.
        self.repeat_group = QButtonGroup(self)
        self.weekly_radio = QRadioButton("Every week on")
        self.once_radio = QRadioButton("Just once, on")
        self.repeat_group.addButton(self.weekly_radio)
        self.repeat_group.addButton(self.once_radio)
        self.weekly_radio.setChecked(True)

        weekly_row = QHBoxLayout()
        weekly_row.setSpacing(4)
        weekly_row.addWidget(self.weekly_radio)
        self.day_checks: List[QCheckBox] = []
        for index, label in enumerate(WEEKDAY_LABELS):
            check = QCheckBox(label)
            check.setProperty("weekday", index)
            self.day_checks.append(check)
            weekly_row.addWidget(check)
        weekly_row.addStretch()
        weekly_host = QWidget()
        weekly_host.setLayout(weekly_row)
        form.addRow(weekly_host)

        once_row = QHBoxLayout()
        once_row.addWidget(self.once_radio)
        self.once_date = QDateEdit()
        self.once_date.setCalendarPopup(True)
        self.once_date.setDisplayFormat("ddd, MMM d yyyy")
        self.once_date.setMinimumHeight(30)
        once_row.addWidget(self.once_date, 1)
        once_host = QWidget()
        once_host.setLayout(once_row)
        form.addRow(once_host)

        self.weekly_radio.toggled.connect(self._sync_repeat_enabled)
        self._sync_repeat_enabled(True)

        self.notes_field = QLineEdit()
        self.notes_field.setPlaceholderText("Where, who, dial-in … (optional)")
        self.notes_field.setMinimumHeight(30)
        form.addRow("Note", self.notes_field)

        self.active = QCheckBox("Counts against the plan")
        self.active.setToolTip(
            "Untick to keep it on the list without blocking any time — "
            "for a meeting that has been paused.")
        self.active.setChecked(True)
        form.addRow(self.active)

        apply_row = QHBoxLayout()
        self.apply_btn = QPushButton("Save this block")
        self.apply_btn.setProperty("class", "primary")
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.clicked.connect(self._save_current)
        apply_row.addStretch()
        apply_row.addWidget(self.apply_btn)
        form.addRow(apply_row)

        body.addWidget(self.editor, 1)
        outer.addLayout(body, 1)

        self.footer = QLabel("")
        self.footer.setWordWrap(True)
        outer.addWidget(self.footer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

        self.setup_theme_awareness()
        self.refresh()
        if self.store.commitments:
            self.list.setCurrentRow(0)
        else:
            self._new()

    # ── theme ────────────────────────────────────────────────────────────────

    def apply_theme(self):
        palette = self.get_current_palette()
        # Top-level window: not a child of the Assistant page, so it
        # inherits nothing and carries the scoped sheet itself.
        self.setStyleSheet(
            self.scope_stylesheet()
            + f"QDialog {{ background: {palette.background}; }}")
        for label in (self.blurb, self.footer, self.length_hint):
            label.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 12px;")

    # ── data ─────────────────────────────────────────────────────────────────

    def refresh(self, keep_id: str = ""):
        wanted = keep_id or (self.list.currentItem().data(
            Qt.ItemDataRole.UserRole) if self.list.currentItem() else "")
        self.list.blockSignals(True)
        self.list.clear()
        for commitment in self.store.sorted_commitments():
            text = commitment.label()
            if not commitment.active:
                text += "   (off)"
            item = QListWidgetItem(f"{text}\n{commitment.when_label()}")
            item.setData(Qt.ItemDataRole.UserRole, commitment.id)
            self.list.addItem(item)
        self.list.blockSignals(False)

        if wanted:
            for row in range(self.list.count()):
                if self.list.item(row).data(
                        Qt.ItemDataRole.UserRole) == wanted:
                    self.list.setCurrentRow(row)
                    break
        self._update_footer()

    def _update_footer(self):
        active = [c for c in self.store.commitments if c.active]
        if not active:
            self.footer.setText(
                "Nothing blocked out — the planner has the whole day.")
            return
        weekly = sum(c.minutes * len(c.weekdays) for c in active if c.weekly)
        once = sum(1 for c in active if not c.weekly)
        bits = []
        if weekly:
            bits.append(f"{fmt_duration(weekly)} a week in standing blocks")
        if once:
            bits.append(f"{once} one-off{'s' if once != 1 else ''}")
        self.footer.setText("  ·  ".join(bits))

    # ── editing ──────────────────────────────────────────────────────────────

    def _sync_repeat_enabled(self, weekly: bool):
        for check in self.day_checks:
            check.setEnabled(weekly)
        self.once_date.setEnabled(not weekly)

    def _on_selected(self, current, _previous=None):
        if current is None:
            return
        commitment = self.store.get_commitment(
            current.data(Qt.ItemDataRole.UserRole))
        if commitment is None:
            return
        self._load(commitment)

    def _load(self, commitment: Commitment):
        self._editing = commitment
        self.title_field.setText(commitment.title)
        start = commitment.start_time()
        self.start.setTime(QTime(start.hour, start.minute))
        self.length.setValue(max(5, int(commitment.minutes)))
        self.length_hint.setText(f"({fmt_duration(commitment.minutes)})")
        self.notes_field.setText(commitment.notes)
        self.active.setChecked(commitment.active)

        weekly = commitment.weekly
        self.weekly_radio.setChecked(weekly)
        self.once_radio.setChecked(not weekly)
        for check in self.day_checks:
            check.setChecked(check.property("weekday") in commitment.weekdays)
        own = commitment.day_date() or date.today()
        self.once_date.setDate(QDate(own.year, own.month, own.day))
        self._sync_repeat_enabled(weekly)
        self.apply_btn.setText("Save this block")

    def _new(self):
        """A blank one, defaulted to a weekday morning half-hour, which is
        what most of these turn out to be."""
        self._editing = None
        # Drop the selection without handing Qt a null item (the overload
        # takes a QListWidgetItem); -1 is the documented "nothing picked".
        self.list.setCurrentRow(-1)
        self.title_field.clear()
        self.start.setTime(QTime(9, 0))
        self.length.setValue(30)
        self.length_hint.setText(f"({fmt_duration(30)})")
        self.notes_field.clear()
        self.active.setChecked(True)
        self.weekly_radio.setChecked(True)
        for check in self.day_checks:
            check.setChecked(False)
        self.once_date.setDate(QDate.currentDate())
        self._sync_repeat_enabled(True)
        self.apply_btn.setText("Add this block")
        self.title_field.setFocus()

    def _collect(self) -> Optional[Commitment]:
        title = self.title_field.text().strip()
        if not title:
            self.title_field.setFocus()
            QMessageBox.information(self, "Needs a name",
                                    "Give the block a name so you know what "
                                    "it is on the agenda.")
            return None
        weekdays: List[int] = []
        if self.weekly_radio.isChecked():
            weekdays = [int(c.property("weekday")) for c in self.day_checks
                        if c.isChecked()]
            if not weekdays:
                QMessageBox.information(
                    self, "Which days?",
                    "Tick at least one day, or switch it to a one-off.")
                return None

        commitment = self._editing or Commitment()
        commitment.title = title
        qtime = self.start.time()
        commitment.start = f"{qtime.hour():02d}:{qtime.minute():02d}"
        commitment.minutes = int(self.length.value())
        commitment.notes = self.notes_field.text().strip()
        commitment.active = self.active.isChecked()
        if weekdays:
            commitment.weekdays = sorted(weekdays)
            commitment.day = None
        else:
            commitment.weekdays = []
            qdate = self.once_date.date()
            commitment.day = date(qdate.year(), qdate.month(),
                                  qdate.day()).isoformat()
        return commitment

    def _save_current(self):
        commitment = self._collect()
        if commitment is None:
            return
        if self._editing is None:
            self.store.add_commitment(commitment)
        else:
            self.store.update_commitment(commitment)
        self._editing = commitment
        self.refresh(keep_id=commitment.id)

    def _delete(self):
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, "Nothing picked",
                                    "Pick a block on the left first.")
            return
        commitment = self.store.get_commitment(
            item.data(Qt.ItemDataRole.UserRole))
        if commitment is None:
            return
        answer = QMessageBox.question(
            self, "Remove block", f"Remove “{commitment.label()}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_commitment(commitment.id)
        self.refresh()
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._new()
