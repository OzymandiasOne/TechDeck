"""The Time tab: where the week actually went.

The Schedule tab is the plan. This is the receipt. It reads the clocked
sessions on every task (``TaskItem.sessions``) and answers the question people
actually ask out loud -- *why did this week disappear?* -- with a number per
task and a number per day.

Three design calls worth knowing, because each one is a thing it deliberately
does NOT do:

* **It does not grade anybody.** Logged time sits next to the estimate and
  nothing else happens: no "you were 40% over", no colour-coded shame. A task
  that ran long is information, and the useful thing is to show it.
* **It does not correct estimates from the clock.** The estimate is what the
  person booked; changing it behind them would make the next plan a stranger.
* **It does not invent categories.** The row is a task, because that is the
  only grouping the data actually has. Anything finer would be a guess
  dressed up as a report.

The maths all lives in ``core/assistant/timelog.py``; this is drawing.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from techdeck.core.assistant import timelog
from techdeck.core.assistant.models import fmt_duration
from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme import subtle_tint
from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import SCOPE_ASSISTANT

# The widest a bar may get, in pixels. Bars are drawn as a filled child frame
# rather than a QProgressBar: a progress bar implies a target, and there is no
# target here, only a share of the total.
BAR_MAX_PX = 260


# Both card kinds come from the Schedule/Tasks module so the three tabs cannot
# drift apart.
from techdeck.ui.widgets.assistant_schedule import (  # noqa: E402
    HEADER_MARGINS, _card, _header_card, card_qss,
)


class TimePanel(QWidget, ThemeAware):
    """Totals per task and per day for one range, biggest first."""

    # Follows the Assistant's own theme when one is pinned (Settings ->
    # Personalization -> Assistant Page Theme), else the app's.
    THEME_SCOPE = SCOPE_ASSISTANT

    changed = Signal()
    export_requested = Signal(str)       # the timelog range key

    def __init__(self, store: AssistantStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._range = "week"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # --- header ----------------------------------------------------------
        # Unpainted, matching the Schedule and Tasks tabs: the page runs
        # behind it and the margins keep its last button off the window edge.
        header_card = _header_card()
        header = QHBoxLayout(header_card)
        header.setContentsMargins(*HEADER_MARGINS)
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.headline = QLabel("Nothing clocked yet")
        self.headline.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.sub = QLabel("")
        self.sub.setWordWrap(True)
        titles.addWidget(self.headline)
        titles.addWidget(self.sub)
        header.addLayout(titles, 1)

        self.range_box = QComboBox()
        self.range_box.setMinimumWidth(150)
        self.range_box.setMinimumHeight(30)
        for key, label in timelog.RANGE_CHOICES:
            self.range_box.addItem(label, key)
        self.range_box.setCurrentIndex(
            max(0, self.range_box.findData(self._range)))
        self.range_box.currentIndexChanged.connect(self._on_range)
        header.addWidget(self.range_box)

        self.stop_btn = QPushButton("Stop the clock")
        self.stop_btn.setMinimumHeight(30)
        self.stop_btn.clicked.connect(self._stop_clock)
        header.addWidget(self.stop_btn)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setMinimumHeight(30)
        self.export_btn.setToolTip(
            "Every clocked session in this range, one row each, for Excel")
        self.export_btn.clicked.connect(
            lambda: self.export_requested.emit(self._range))
        header.addWidget(self.export_btn)
        outer.addWidget(header_card)

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self.box = QVBoxLayout(self._body)
        self.box.setContentsMargins(2, 2, 8, 12)
        self.box.setSpacing(10)
        self.scroller.setWidget(self._body)
        outer.addWidget(self.scroller, 1)

        self.setup_theme_awareness()

    # ── theme ────────────────────────────────────────────────────────────────

    def apply_theme(self):
        palette = self.get_current_palette()
        # Header text sits on the page, not on a card, so it takes the
        # page's tones.
        self.headline.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {palette.text}; "
            f"background: transparent;")
        self.sub.setStyleSheet(
            f"color: {palette.text_secondary}; font-size: 12px; "
            f"background: transparent;")
        self.setStyleSheet(card_qss(palette))
        self.refresh()

    # ── data ─────────────────────────────────────────────────────────────────

    def _on_range(self, _index: int):
        self._range = self.range_box.currentData() or "week"
        self.refresh()

    def _clear(self):
        while self.box.count():
            item = self.box.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def refresh(self):
        palette = self.get_current_palette()
        self._clear()
        now = datetime.now()
        report = timelog.build_report(self.store.tasks, self._range, now)
        running = self.store.running_task()

        self.headline.setText(report.label)
        self.sub.setText(report.headline())
        self.stop_btn.setVisible(running is not None)
        if running is not None:
            self.stop_btn.setText(
                f"■ Stop: {running.label()[:28]} "
                f"({fmt_duration(running.logged_minutes(now))})")
        self.export_btn.setEnabled(bool(report.rows))

        if not report.rows:
            empty = QLabel(
                "No time clocked in this range.\n\n"
                "Press ▶ on a task to start the clock, or type "
                "/clockin <task>. Stop it with ■, and this page fills "
                "in on its own.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"color: {palette.text_secondary}; padding: 40px;")
            self.box.addWidget(empty)
            self.box.addStretch()
            return

        self.box.addWidget(self._tasks_card(report, palette))
        if len(report.per_day) > 1:
            self.box.addWidget(self._days_card(report, palette))
        self.box.addStretch()

    # ── cards ────────────────────────────────────────────────────────────────

    def _tasks_card(self, report: timelog.TimeReport, palette) -> QWidget:
        card = _card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(6)

        heading = QLabel("What it went on")
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {palette.on_card}; "
            f"background: transparent;")
        box.addWidget(heading)

        biggest = max(row.minutes for row in report.rows)
        for row in report.rows:
            box.addWidget(self._task_row(row, biggest, palette))
        return card

    def _task_row(self, row: timelog.TaskTotal, biggest: int,
                  palette) -> QWidget:
        host = QWidget()
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        host.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel(row.title)
        title.setWordWrap(True)
        colour = palette.on_card_secondary if row.done else palette.on_card
        title.setStyleSheet(f"color: {colour}; background: transparent;")
        top.addWidget(title, 1)

        if row.running:
            live = QLabel("running")
            live.setStyleSheet(
                f"color: {palette.accent_text}; background: {palette.accent}; "
                f"border-radius: 7px; padding: 1px 8px; font-size: 10px; "
                f"font-weight: bold;")
            top.addWidget(live)

        amount = QLabel(fmt_duration(row.minutes))
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        amount.setFont(mono)
        amount.setStyleSheet(
            f"color: {palette.on_card}; background: transparent; "
            f"font-weight: 600;")
        top.addWidget(amount)
        layout.addLayout(top)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(8)
        bar_row.addWidget(self._bar(row.minutes, biggest, palette))

        # The estimate sits beside the bar as plain text. No ratio, no verdict:
        # the comparison is the user's to make.
        if row.estimate_min:
            note = f"booked {fmt_duration(row.estimate_min)}"
            if row.over_estimate:
                note += f" · over by {fmt_duration(row.minutes - row.estimate_min)}"
            caption = QLabel(note)
            caption.setStyleSheet(
                f"color: {palette.on_card_secondary}; font-size: 11px; "
                f"background: transparent;")
            bar_row.addWidget(caption)
        bar_row.addStretch()
        layout.addLayout(bar_row)
        return host

    def _bar(self, minutes: int, biggest: int, palette) -> QWidget:
        """A share-of-the-biggest bar. Fixed-width filled frame rather than a
        QProgressBar, which would imply a target to reach.

        The track is a tint derived from the card's text, NOT ``palette.border``:
        halloween's `border` and `accent` are the same purple, so a bordered
        track and an accent fill were the same colour and every bar read as
        100% full whatever the number beside it said.
        """
        track = QFrame()
        track.setFixedHeight(6)
        track.setFixedWidth(BAR_MAX_PX)
        track.setStyleSheet(
            f"background: {subtle_tint(palette.on_card)}; border-radius: 3px;")
        fill = QFrame(track)
        share = (minutes / biggest) if biggest else 0.0
        fill.setGeometry(0, 0, max(3, int(BAR_MAX_PX * share)), 6)
        fill.setStyleSheet(
            f"background: {palette.accent}; border-radius: 3px;")
        return track

    def _days_card(self, report: timelog.TimeReport, palette) -> QWidget:
        card = _card()
        card.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(4)

        heading = QLabel("Day by day")
        heading.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {palette.on_card}; "
            f"background: transparent;")
        box.addWidget(heading)

        busiest = report.busiest_day
        biggest = busiest[1] if busiest else 0
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        for day, minutes in report.per_day:
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row.setStyleSheet("background: transparent;")
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 2, 0, 2)
            line.setSpacing(10)

            label = QLabel(f"{day.strftime('%a %b')} {day.day}")
            label.setFont(mono)
            label.setFixedWidth(110)
            label.setStyleSheet(
                f"color: {palette.on_card_secondary}; background: transparent;")
            line.addWidget(label)
            line.addWidget(self._bar(minutes, biggest, palette))

            amount = QLabel(fmt_duration(minutes))
            amount.setFont(mono)
            amount.setStyleSheet(
                f"color: {palette.on_card}; background: transparent;")
            line.addWidget(amount)
            line.addStretch()
            box.addWidget(row)
        return card

    # ── actions ──────────────────────────────────────────────────────────────

    def _stop_clock(self):
        running = self.store.running_task()
        if running is None:
            return
        self.store.clock_out(running.id)
        self.refresh()
        self.changed.emit()
