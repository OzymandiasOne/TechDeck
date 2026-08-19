"""Reminder settings for the Assistant.

Small on purpose. The only decisions worth surfacing are on/off, how much
warning you want, and whether it may speak outside your working hours.

The dialog is honest about the limitation rather than hiding it: reminders come
from TechDeck itself, so they stop when TechDeck is closed. That sentence is on
screen, next to the Outlook export that solves it.
"""

from __future__ import annotations

from datetime import time
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox, QSpinBox,
    QTimeEdit, QLabel, QDialogButtonBox, QGroupBox, QPushButton,
)
from PySide6.QtCore import Qt, QTime

from techdeck.core.assistant.models import parse_hhmm
from techdeck.core.assistant.notifier import NotifyPrefs
from techdeck.ui.notifier import DesktopNotifier
from techdeck.ui.theme_aware import ThemeAware


class ReminderDialog(QDialog, ThemeAware):
    """Edit :class:`NotifyPrefs`. Read the result with :meth:`result_prefs`."""

    def __init__(self, prefs: NotifyPrefs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reminders")
        self.setMinimumWidth(500)
        self._prefs = NotifyPrefs.from_dict(prefs.to_dict())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 16)
        outer.setSpacing(14)

        self.enabled = QCheckBox("Remind me on this computer")
        self.enabled.setChecked(self._prefs.enabled)
        self.enabled.setStyleSheet("font-weight: 600;")
        outer.addWidget(self.enabled)

        self.caveat = QLabel(
            "These are Windows notifications from TechDeck, so they only "
            "arrive while TechDeck is open. For reminders that reach you with "
            "it closed, export the plan from the Schedule tab as a calendar "
            "file and open it in Outlook.")
        self.caveat.setWordWrap(True)
        outer.addWidget(self.caveat)

        self.options = QGroupBox("What to say, and when")
        form = QFormLayout(self.options)
        form.setSpacing(10)

        lead_row = QHBoxLayout()
        self.lead = QSpinBox()
        self.lead.setRange(0, 120)
        self.lead.setSingleStep(5)
        self.lead.setSuffix(" min")
        self.lead.setValue(self._prefs.lead_minutes)
        self.lead.setMinimumHeight(30)
        lead_row.addWidget(self.lead)
        lead_row.addWidget(QLabel("before a block starts (0 = right on time)"))
        lead_row.addStretch()
        form.addRow("Warn me", lead_row)

        digest_row = QHBoxLayout()
        self.digest = QCheckBox("A summary of the day at")
        self.digest.setChecked(self._prefs.daily_digest)
        self.digest_at = QTimeEdit()
        self.digest_at.setDisplayFormat("h:mm AP")
        stamp = parse_hhmm(self._prefs.digest_at, time(7, 0))
        self.digest_at.setTime(QTime(stamp.hour, stamp.minute))
        self.digest_at.setMinimumHeight(30)
        self.digest_at.setEnabled(self.digest.isChecked())
        self.digest.toggled.connect(self.digest_at.setEnabled)
        digest_row.addWidget(self.digest)
        digest_row.addWidget(self.digest_at)
        digest_row.addStretch()
        form.addRow("Each morning", digest_row)

        self.overdue = QCheckBox("Tell me once a day about anything past its date")
        self.overdue.setChecked(self._prefs.overdue)
        form.addRow("", self.overdue)

        self.quiet = QCheckBox("Stay quiet outside my working hours")
        self.quiet.setChecked(self._prefs.quiet_outside_hours)
        self.quiet.setToolTip(
            "Working hours come from the schedule builder's Advanced section, "
            "or /hours in the terminal.")
        form.addRow("", self.quiet)

        outer.addWidget(self.options)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        self.test_btn = QPushButton("Send a test one")
        self.test_btn.clicked.connect(self._send_test)
        buttons.addButton(self.test_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.enabled.toggled.connect(self._sync)
        self._sync()
        self.setup_theme_awareness()

    def _sync(self):
        on = self.enabled.isChecked()
        self.options.setEnabled(on)
        # Never offer a switch that can't do anything. If Windows won't show a
        # notification on this machine, say so instead of letting someone turn
        # a setting on and wonder why nothing happens.
        if not DesktopNotifier.available():
            self.enabled.setChecked(False)
            self.enabled.setEnabled(False)
            self.options.setEnabled(False)
            self.test_btn.setEnabled(False)
            self.status.setText(DesktopNotifier.unavailable_reason()
                                or "Notifications aren't available here.")
        else:
            self.test_btn.setEnabled(on)

    def _send_test(self):
        notifier = DesktopNotifier(self)
        ok = notifier.notify(
            "TechDeck reminder",
            "This is what a reminder looks like.\n"
            "If you can see this, they work.")
        self.status.setText(
            "Sent. If nothing appeared, check Windows Settings, "
            "Notifications, and make sure TechDeck is allowed."
            if ok else "Couldn't send one. Notifications may be blocked "
                       "for this app in Windows Settings.")

    def apply_theme(self):
        palette = self.get_current_palette()
        self.setStyleSheet(f"QDialog {{ background: {palette.background}; }}")
        for label in (self.caveat, self.status):
            label.setStyleSheet(
                f"color: {palette.text_secondary}; font-size: 11px;")

    def result_prefs(self) -> NotifyPrefs:
        return NotifyPrefs.from_dict({
            "enabled": self.enabled.isChecked(),
            "lead_minutes": self.lead.value(),
            "daily_digest": self.digest.isChecked(),
            "digest_at": self.digest_at.time().toString("HH:mm"),
            "overdue": self.overdue.isChecked(),
            "quiet_outside_hours": self.quiet.isChecked(),
        })
