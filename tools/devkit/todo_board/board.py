"""The DevKit Dev Board widget — Teams-style buckets + cards over the feedback
backlog.

Layout: a header bar (Refresh / Add bucket / status) over a horizontally
scrolling row of fixed-width `BucketColumn`s. Each column has its own vertical
scroll and is a drop target: dragging a `TaskCard` shows a drop-indicator line
and, on release, moves the card in the `BoardStore` and re-renders.

Everything is repainted from the active theme palette and re-rendered on live
theme change (ThemeAware). Source-only — never in the frozen build.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QCursor, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QToolButton, QMenu, QInputDialog, QMessageBox, QSizePolicy,
    QCheckBox, QDialog, QPlainTextEdit,
)

from techdeck.ui.theme_aware import ThemeAware
from tools.devkit.todo_board.model import (
    BoardStore, load_feedback, flush_writebacks,
    DONE_BUCKET_ID, WONT_DO_BUCKET_ID,
)
from tools.devkit.todo_board.widgets import TaskCard, CARD_MIME, menu_stylesheet

COLUMN_WIDTH = 290
# Hard pixel budget for the toolbar status label. The status text is
# open-ended (counts + write-back notes + a staleness warning), and a QLabel
# reports its full text width as its minimum — so without a cap it drags the
# whole DevKit page, and therefore the window, wider. Anything past the budget
# is elided; the full text and the long-form explanation live in the details
# popup instead (Ⓘ button), which never affects layout.
STATUS_MAX_PX = 230
# Terminal buckets accumulate forever, so cap how many cards render and offer a
# one-click clear. Older completed cards live on in the telemetry Archive.
TERMINAL_BUCKETS = (DONE_BUCKET_ID, WONT_DO_BUCKET_ID)
TERMINAL_CAP = 20


class _CardList(QWidget):
    """The scroll content of one bucket: a vertical stack of cards that accepts
    card drops and draws a drop-indicator line at the insertion gap."""

    dropped = Signal(str, int)   # card key, insert index

    AUTOSCROLL_ZONE = 52       # px from the viewport edge that starts scrolling
    AUTOSCROLL_MAX = 20        # px per tick at the very edge (ramps from 1)
    AUTOSCROLL_INTERVAL = 15   # ms between scroll ticks

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._pal = palette
        self.setAcceptDrops(True)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(8, 8, 8, 8)
        self._v.setSpacing(14)
        self._v.addStretch(1)

        # Indicator is a free child (NOT in the layout) positioned with
        # setGeometry, so hovering never reflows the cards.
        self._indicator = QFrame(self)
        self._indicator.setFixedHeight(3)
        self._indicator.setStyleSheet(
            f"background-color: {palette.accent}; border-radius: 1px;")
        self._indicator.hide()

        # Auto-scroll while a drag hovers near the top/bottom edge. A timer
        # drives it because drag-move events stop firing when the cursor holds
        # still in the zone.
        self._scroll = None
        self._autoscroll_v = 0
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(self.AUTOSCROLL_INTERVAL)
        self._autoscroll_timer.timeout.connect(self._on_autoscroll_tick)

    def set_scroll_area(self, scroll):
        """Wire the owning QScrollArea so drag-near-edge can auto-scroll it."""
        self._scroll = scroll

    def minimumSizeHint(self):
        # The column is fixed-width and its h-scrollbar is off, so a wide card
        # (long chip, unbroken word) must never widen the list past the
        # viewport — extra width just clips. Claim zero minimum width so the
        # resizable scroll area sizes us exactly to the viewport and the
        # word-wrapped labels wrap to fit instead.
        return QSize(0, super().minimumSizeHint().height())

    def add_card(self, card: TaskCard):
        self._v.insertWidget(self._v.count() - 1, card)  # before the stretch

    def _cards(self) -> list:
        out = []
        for i in range(self._v.count()):
            w = self._v.itemAt(i).widget()
            if isinstance(w, TaskCard) and w.isVisible():
                out.append(w)
        return out

    def _index_at(self, y: int) -> int:
        idx = 0
        for w in self._cards():
            if y >= w.y() + w.height() // 2:
                idx += 1
            else:
                break
        return idx

    def _gap_y(self, idx: int, cards: list) -> int:
        top = self._v.contentsMargins().top()
        if not cards:
            return top
        if idx <= 0:
            return max(top, cards[0].y() - 5)
        if idx >= len(cards):
            last = cards[-1]
            return last.y() + last.height() + 3
        return cards[idx].y() - 5

    def _show_indicator(self, y_pos: int):
        m = self._v.contentsMargins()
        self._indicator.setGeometry(
            m.left(), y_pos, self.width() - m.left() - m.right(), 3)
        self._indicator.show()
        self._indicator.raise_()

    # ---- auto-scroll near the edges while dragging ----------------------

    def _update_autoscroll(self):
        if self._scroll is None:
            return
        vp = self._scroll.viewport()
        y = vp.mapFromGlobal(QCursor.pos()).y()
        zone, height = self.AUTOSCROLL_ZONE, vp.height()
        v = 0
        if y < zone:
            v = -max(1, round(self.AUTOSCROLL_MAX * (zone - y) / zone))
        elif y > height - zone:
            v = max(1, round(self.AUTOSCROLL_MAX * (y - (height - zone)) / zone))
        self._autoscroll_v = v
        if v and not self._autoscroll_timer.isActive():
            self._autoscroll_timer.start()
        elif not v and self._autoscroll_timer.isActive():
            self._autoscroll_timer.stop()

    def _on_autoscroll_tick(self):
        if not self._autoscroll_v or self._scroll is None:
            self._stop_autoscroll()
            return
        sb = self._scroll.verticalScrollBar()
        new = max(sb.minimum(), min(sb.maximum(), sb.value() + self._autoscroll_v))
        if new == sb.value():
            return  # already at the end in this direction
        sb.setValue(new)
        # The content moved under a stationary cursor — refresh the indicator.
        y = self.mapFromGlobal(QCursor.pos()).y()
        self._show_indicator(self._gap_y(self._index_at(y), self._cards()))

    def _stop_autoscroll(self):
        self._autoscroll_v = 0
        if self._autoscroll_timer.isActive():
            self._autoscroll_timer.stop()

    # ---- drop target ----------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(CARD_MIME):
            return
        y = event.position().toPoint().y()
        idx = self._index_at(y)
        self._show_indicator(self._gap_y(idx, self._cards()))
        self._update_autoscroll()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._indicator.hide()
        self._stop_autoscroll()

    def dropEvent(self, event):
        self._indicator.hide()
        self._stop_autoscroll()
        if not event.mimeData().hasFormat(CARD_MIME):
            return
        key = bytes(event.mimeData().data(CARD_MIME)).decode("utf-8")
        idx = self._index_at(event.position().toPoint().y())
        self.dropped.emit(key, idx)
        event.acceptProposedAction()


class BucketColumn(QFrame):
    """One bucket: a header (name / count / add / menu) over a scrollable card
    list. Emits high-level intents; the board owns the store and rebuilds."""

    card_dropped = Signal(str, str, int)   # key, bucket_id, index
    add_card_requested = Signal(str)       # bucket_id
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    move_requested = Signal(str, int)      # bucket_id, delta (-1 / +1)
    clear_requested = Signal(str)          # bucket_id — clear all cards off board

    def __init__(self, bucket: dict, palette, parent=None):
        super().__init__(parent)
        self.bucket_id = bucket["id"]
        self._pal = palette
        self.setObjectName("bucketCol")
        self.setFixedWidth(COLUMN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        # Transparent tray — cards float on the page background (Teams-style),
        # which reads cleaner than tinted rectangles, especially on light themes.
        self.setStyleSheet("#bucketCol { background: transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 8, 6, 6)
        outer.setSpacing(6)

        # --- header ---
        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 2, 0)
        header.setSpacing(6)
        self._name = QLabel(bucket["name"])
        nf = self._name.font()
        nf.setPointSize(11)
        nf.setBold(True)
        self._name.setFont(nf)
        self._name.setStyleSheet(f"color: {palette.text}; background: transparent;")
        header.addWidget(self._name)
        self._count = QLabel("0")
        self._count.setStyleSheet(
            f"color: {palette.text_secondary}; background: transparent; font-size: 10pt;")
        header.addWidget(self._count)
        header.addStretch()

        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add a card")
        add_btn.setStyleSheet(self._icon_btn_qss())
        add_btn.clicked.connect(lambda: self.add_card_requested.emit(self.bucket_id))
        header.addWidget(add_btn)

        menu_btn = QToolButton()
        menu_btn.setText("···")
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setStyleSheet(self._icon_btn_qss())
        menu_btn.clicked.connect(lambda: self._open_menu(menu_btn))
        header.addWidget(menu_btn)
        outer.addLayout(header)

        # --- card list in a vertical scroll ---
        self._list = _CardList(palette)
        self._list.dropped.connect(
            lambda key, idx: self.card_dropped.emit(key, self.bucket_id, idx))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # No visible scrollbar — the mouse wheel and drag-near-edge auto-scroll
        # move a long column instead.
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._list)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._list.setStyleSheet("background: transparent;")
        self._list.set_scroll_area(scroll)
        outer.addWidget(scroll, 1)

        # Overflow footer: on a capped terminal bucket, shows "+N older — Clear"
        # and clears the whole bucket off the board when clicked. Hidden until a
        # bucket actually overflows.
        self._overflow = QToolButton()
        self._overflow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._overflow.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._overflow.setToolTip(
            "Clear completed cards off the board (they stay in the telemetry Archive)")
        self._overflow.setStyleSheet(
            f"QToolButton {{ color: {self._pal.text_secondary}; background: transparent; "
            f"border: none; padding: 4px; font-size: 9pt; }}"
            f"QToolButton:hover {{ color: {self._pal.accent}; }}")
        self._overflow.clicked.connect(lambda: self.clear_requested.emit(self.bucket_id))
        self._overflow.hide()
        outer.addWidget(self._overflow)

    def _icon_btn_qss(self) -> str:
        return (f"QToolButton {{ color: {self._pal.text_secondary}; "
                f"background: transparent; border: none; font-size: 15px; "
                f"font-weight: bold; padding: 0 4px; }}"
                f"QToolButton:hover {{ color: {self._pal.accent}; }}")

    def add_card_widget(self, card: TaskCard):
        self._list.add_card(card)

    def set_count(self, n: int):
        self._count.setText(str(n))

    def set_overflow(self, hidden: int):
        """Show/hide the '+N older — Clear' footer for a capped bucket."""
        if hidden > 0:
            self._overflow.setText(f"＋{hidden} older  ·  Clear completed")
            self._overflow.show()
        else:
            self._overflow.hide()

    def _open_menu(self, anchor):
        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet(self._pal))
        act_add = menu.addAction("Add card…")
        act_rename = menu.addAction("Rename bucket…")
        menu.addSeparator()
        act_left = menu.addAction("Move left")
        act_right = menu.addAction("Move right")
        menu.addSeparator()
        act_clear = (menu.addAction("Clear completed cards…")
                     if self.bucket_id in TERMINAL_BUCKETS else None)
        act_delete = menu.addAction("Delete bucket")
        chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        if chosen == act_add:
            self.add_card_requested.emit(self.bucket_id)
        elif chosen == act_rename:
            self.rename_requested.emit(self.bucket_id)
        elif chosen == act_left:
            self.move_requested.emit(self.bucket_id, -1)
        elif chosen == act_right:
            self.move_requested.emit(self.bucket_id, 1)
        elif act_clear is not None and chosen == act_clear:
            self.clear_requested.emit(self.bucket_id)
        elif chosen == act_delete:
            self.delete_requested.emit(self.bucket_id)


class TodoBoard(QWidget, ThemeAware):
    """The DevKit Dev Board tool (mounted first in the DevKit picker)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = BoardStore()
        self._pal = self.get_current_palette()
        self._rebuild_pending = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        # Toolbar controls live in the DevKit page's unified toolbar (handed over
        # via devkit_toolbar_actions), not a header of our own — so the board
        # area is just the buckets. Created here unparented; the page reparents
        # them into its toolbar slot.
        self._status = QLabel("", self)
        self._status_ok = True
        self._writeback_ok = True
        # Elided display + the untruncated text/explanation behind the Ⓘ button.
        self._status_full = ""      # complete one-line status
        self._status_detail = ""    # long-form explanation ("" = nothing extra)
        f = self._status.font()
        f.setPointSize(9)
        self._status.setFont(f)     # set on the widget, not via QSS, so
        self._status.setMaximumWidth(STATUS_MAX_PX)   # QFontMetrics is accurate
        self._status.setMinimumWidth(0)
        self._status.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Preferred)
        self._details_btn = QToolButton(self)
        self._details_btn.setText("ⓘ")
        self._details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._details_btn.setToolTip("Show the full status and what it means")
        self._details_btn.clicked.connect(self._show_status_details)
        self._details_dialog = None
        self._triage_toggle = QCheckBox("Flow triage", self)
        self._triage_toggle.setChecked(self.store.webhook_triage)
        self._triage_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._triage_toggle.setToolTip(
            "Send Status write-backs through the telemetry flow (server-side "
            "workbook update — no local file write, no OneDrive conflicts).\n"
            "Turn on only after the flow's triage branch is built "
            "(docs/USAGE_TELEMETRY.md); without it, triage events append "
            "junk feedback rows.")
        self._triage_toggle.toggled.connect(self.store.set_webhook_triage)
        self._add_bucket_btn = QPushButton("+ Bucket", self)
        self._add_bucket_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_bucket_btn.clicked.connect(self._on_add_bucket)
        self._clear_btn = QPushButton("Clear completed", self)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setToolTip(
            "Clear the Done bucket off the board — items stay in the telemetry Archive")
        self._clear_btn.clicked.connect(self._on_clear_completed)
        self._refresh_btn = QPushButton("Refresh", self)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._sync_and_rebuild)

        # --- columns in a horizontal scroll ---
        self._cols_host = QWidget()
        self._cols_layout = QHBoxLayout(self._cols_host)
        self._cols_layout.setContentsMargins(2, 2, 2, 2)
        self._cols_layout.setSpacing(14)
        self._cols_scroll = QScrollArea()
        self._cols_scroll.setWidgetResizable(True)
        self._cols_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cols_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cols_scroll.setWidget(self._cols_host)
        outer.addWidget(self._cols_scroll, 1)

        self._columns: dict[str, BucketColumn] = {}

        self._sync_and_rebuild()
        self.setup_theme_awareness()   # subscribes + calls apply_theme once

    # ---- data / rebuild --------------------------------------------------

    def _sync_and_rebuild(self):
        # Flush BEFORE reading so the reload reflects the statuses we just
        # wrote (and pending write-backs retry on every Refresh).
        wb_note = self._flush_writebacks()
        load = load_feedback()
        added = self.store.sync(load)
        # Reflect completions made OUTSIDE the board (a Feedback row marked
        # Complete / Won't Do, or archived) by moving those cards into Done /
        # Won't Do — cards the user has already parked terminally are left alone.
        moved = self.store.apply_external_status(load)
        # Readback verification: a delivered-looking write-back whose row
        # still reads "Needs Review" never landed (failed flow run behind the
        # webhook's 202, or the workbook reverted under file mode) — re-queue
        # and re-send it right away.
        requeued = self.store.requeue_stale_writebacks(load)
        if requeued:
            wb_note = self._flush_writebacks() or wb_note
        if load.ok:
            parts = [f"{len(load.feedback)} open", f"{len(load.archive)} archived"]
            if added:
                parts.append(f"+{added} new")
            if moved:
                parts.append(f"{moved} auto-filed")
            if requeued:
                parts.append(f"{requeued} write-back(s) re-sent")
            if wb_note:
                parts.append(wb_note)
            # Freshness of the LOCAL copy we just read. The flow writes the
            # cloud copy on every run by every user, so a local file that
            # hasn't changed in half a day means OneDrive stopped syncing it
            # DOWN — the failure that silently starved this board for six
            # days, indistinguishable from "no new feedback" until now.
            line = "  ·  ".join(p for p in parts if p)
            fresh = self._freshness_note(load)
            if fresh:
                # A staleness WARNING goes first: the label is elided to a pixel
                # budget, so anything trailing can be cut — and the one thing
                # that must never be cut is the reason the board looks empty.
                # The neutral "as of <when>" is fine to lose, so it trails.
                line = (f"{fresh}  ·  {line}" if load.is_stale and line
                        else f"{line}  ·  {fresh}" if line else fresh)
            self._set_status(line, self._freshness_detail(load),
                             keep=fresh if load.is_stale else "")
            self._status_ok = self._writeback_ok and not load.is_stale
        else:
            self._set_status("⚠ " + load.message, self._freshness_detail(load))
            self._status_ok = False
        self._style_status()
        self.rebuild_all()

    def _set_status(self, text: str, detail: str = "", keep: str = ""):
        """Show `text` in the toolbar, elided to STATUS_MAX_PX so a long status
        can never widen the page. The full text goes to the tooltip, and
        `detail` (plus the full text) to the Ⓘ details popup.

        `keep` is a leading fragment that must render in FULL — the budget
        stretches to fit it if needed. Without this the staleness warning got
        clipped mid-word ('⚠ local copy 6 day…'), which is worse than useless.
        Everything after `keep` is still elided, so the growth is bounded by the
        warning's own length rather than by the whole status line.
        """
        self._status_full = text
        self._status_detail = detail
        fm = QFontMetrics(self._status.font())
        budget = STATUS_MAX_PX
        if keep:
            # Room for the kept text PLUS the separator and ellipsis Qt appends,
            # or elidedText eats the tail of `keep` itself to make space.
            budget = max(budget, fm.horizontalAdvance(f"{keep}  ·  …") + 4)
        self._status.setMaximumWidth(budget)
        self._status.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, budget))
        self._status.setToolTip(text)
        self._details_btn.setVisible(bool(text or detail))

    def _show_status_details(self):
        """Open the full status + explanation in its own small window. Kept out
        of the toolbar deliberately: the board must not grow to fit prose."""
        body = self._status_full
        if self._status_detail:
            body = f"{body}\n\n{self._status_detail}" if body else self._status_detail
        dlg = QDialog(self)
        dlg.setWindowTitle("Dev Board — status details")
        dlg.setMinimumSize(520, 240)
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit(body, dlg)
        view.setReadOnly(True)
        lay.addWidget(view)
        close = QPushButton("Close", dlg)
        close.clicked.connect(dlg.close)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self._details_dialog = dlg      # keep a ref so Qt doesn't GC it
        dlg.show()

    def _flush_writebacks(self) -> str:
        """Run a write-back flush if anything is pending; returns a short note
        for the status line ('' when there was nothing to do)."""
        self._writeback_ok = True
        if not self.store.pending_writebacks():
            return ""
        res = flush_writebacks(self.store)
        if not res.ok:
            self._writeback_ok = False
            return f"⚠ {res.attempted} write-back(s) pending — {res.message}"
        if res.via_webhook:
            return (f"{res.written} status update(s) sent to flow"
                    if res.written else "")
        bits = []
        if res.written:
            bits.append(f"{res.written} status(es) written")
        if res.missing:
            bits.append(f"{res.missing} row(s) not on Feedback sheet (archived?)")
        return ", ".join(bits)

    @staticmethod
    def _age_phrase(age_hours: float) -> str:
        """'1 day old' / '3 days old' / '14 hours old'."""
        if age_hours >= 24:
            days = round(age_hours / 24)
            return f"{days} day old" if days == 1 else f"{days} days old"
        hours = max(1, round(age_hours))
        return f"{hours} hour old" if hours == 1 else f"{hours} hours old"

    @classmethod
    def _freshness_note(cls, load) -> str:
        """SHORT freshness chip for the toolbar — 'as of <when>' normally, or
        '⚠ local copy 1 day old' when stale. The why lives in the details
        popup; prose here would widen the page (see STATUS_MAX_PX)."""
        age = load.age_hours
        if age is None:
            return ""
        try:
            stamp = datetime.fromisoformat(load.mtime_iso).strftime("%b %d %H:%M")
        except ValueError:
            return ""
        if not load.is_stale:
            return f"as of {stamp}"
        return f"⚠ local copy {cls._age_phrase(age)}"

    @classmethod
    def _freshness_detail(cls, load) -> str:
        """Long-form explanation for the details popup — only when stale."""
        age = load.age_hours
        if age is None or not load.is_stale:
            return ""
        try:
            stamp = datetime.fromisoformat(load.mtime_iso).strftime("%b %d %Y, %H:%M")
        except ValueError:
            stamp = "unknown"
        where = str(load.path) if load.path else "(workbook not located)"
        return (
            f"The local copy of the telemetry workbook is "
            f"{cls._age_phrase(age)} (last changed {stamp}).\n\n"
            f"The Power Automate flow appends a row to the CLOUD copy on every "
            f"plugin run by every user, so this file should change many times a "
            f"day. That it hasn't means OneDrive has most likely stopped syncing "
            f"it DOWN to this machine — so new feedback will not appear on the "
            f"board, and an empty board looks exactly like 'no new feedback'.\n\n"
            f"To fix: check the OneDrive tray icon for this file, or rename it "
            f"so OneDrive re-downloads a fresh copy under the original name "
            f"(that has broken the deadlock before).\n\n"
            f"File: {where}")

    def _style_status(self):
        # Neutral, legible text — the accent read as an error in warm themes.
        # Font size is set on the widget (not here) so elision measures right.
        color = self._pal.text if self._status_ok else self._pal.warning
        self._status.setStyleSheet(f"color: {color}; background: transparent;")
        self._details_btn.setStyleSheet(
            f"QToolButton {{ color: {color}; background: transparent; "
            f"border: none; padding: 0 2px; font-size: 11pt; }}"
            f"QToolButton:hover {{ color: {self._pal.accent}; }}")

    def devkit_toolbar_actions(self):
        """Widgets the DevKit page hosts in its unified toolbar (right side)."""
        return [self._status, self._details_btn, self._triage_toggle,
                self._add_bucket_btn, self._clear_btn, self._refresh_btn]

    def _schedule_rebuild(self):
        """Rebuild on the next event-loop turn, coalescing multiple calls. Also
        keeps us from destroying widgets while a drag/drop is still on the
        stack."""
        if self._rebuild_pending:
            return
        self._rebuild_pending = True
        QTimer.singleShot(0, self._do_rebuild)

    def _do_rebuild(self):
        self._rebuild_pending = False
        self.rebuild_all()

    def rebuild_all(self):
        # Preserve the horizontal scroll offset. Tearing the columns down and
        # rebuilding destroys the dragged card (its source was hidden mid-drag),
        # so focus falls onto a freshly-created card and QScrollArea scrolls to
        # reveal it — which yanked the board to the far right on every drop.
        # Capture the offset now and restore it once the new layout has settled.
        h_scroll = self._cols_scroll.horizontalScrollBar().value()

        # Tear down existing columns.
        while self._cols_layout.count():
            item = self._cols_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._columns = {}

        for bucket in self.store.buckets:
            col = BucketColumn(bucket, self._pal)
            col.card_dropped.connect(self._on_card_dropped)
            col.add_card_requested.connect(self._on_add_card)
            col.rename_requested.connect(self._on_rename_bucket)
            col.delete_requested.connect(self._on_delete_bucket)
            col.move_requested.connect(self._on_move_bucket)
            col.clear_requested.connect(self._on_clear_bucket)

            keys = [k for k in bucket["cards"] if k in self.store.cards]
            # Terminal buckets accumulate forever — render only the most recent
            # TERMINAL_CAP (newest are appended, so the tail) and surface the rest
            # behind a "+N older — Clear" footer.
            if bucket["id"] in TERMINAL_BUCKETS and len(keys) > TERMINAL_CAP:
                shown, hidden = keys[-TERMINAL_CAP:], len(keys) - TERMINAL_CAP
            else:
                shown, hidden = keys, 0
            for key in shown:
                card = TaskCard(self.store, key, self._pal)
                card.deleted.connect(self._on_card_deleted)
                col.add_card_widget(card)
            col.set_count(len(keys))
            col.set_overflow(hidden)
            self._cols_layout.addWidget(col)
            self._columns[bucket["id"]] = col
        self._cols_layout.addStretch(1)   # left-pack the columns

        # Restore the horizontal offset — now, and again after the event loop
        # settles (a focused child's ensureVisible fires slightly later and
        # would otherwise win, scrolling us to the far right).
        def _restore_h():
            bar = self._cols_scroll.horizontalScrollBar()
            bar.setValue(min(h_scroll, bar.maximum()))
        _restore_h()
        QTimer.singleShot(0, _restore_h)

    # ---- card intents ----------------------------------------------------

    def _on_card_dropped(self, key: str, bucket_id: str, index: int):
        self.store.move_card(key, bucket_id, index)
        # A drop into/out of Done or Won't Do queues a Status write-back —
        # flush it now (moves between working buckets queue nothing, so this
        # touches the workbook only when a status actually changes).
        note = self._flush_writebacks()
        if note:
            self._set_status(note)
            self._status_ok = self._writeback_ok
            self._style_status()
        self._schedule_rebuild()

    def _on_card_deleted(self, key: str):
        self.store.delete_card(key)
        self._schedule_rebuild()

    def _on_add_card(self, bucket_id: str):
        text, ok = QInputDialog.getText(self, "Add card", "Card title:")
        if ok and text.strip():
            self.store.add_manual_card(bucket_id, text.strip())
            self._schedule_rebuild()

    def _on_clear_completed(self):
        """Toolbar button — clear the Done bucket off the board."""
        self._on_clear_bucket(DONE_BUCKET_ID)

    def _on_clear_bucket(self, bucket_id: str):
        b = self.store.bucket(bucket_id)
        if b is None or not b["cards"]:
            return
        n = len(b["cards"])
        resp = QMessageBox.question(
            self, "Clear completed",
            f"Clear {n} card(s) from '{b['name']}' off the board?\n\n"
            f"They stay in the telemetry Archive (the record of record) — this "
            f"only removes them from the board.")
        if resp != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_bucket(bucket_id)
        self._schedule_rebuild()

    # ---- bucket intents --------------------------------------------------

    def _on_add_bucket(self):
        text, ok = QInputDialog.getText(self, "Add bucket", "Bucket name:")
        if ok and text.strip():
            self.store.add_bucket(text.strip())
            self._schedule_rebuild()

    def _on_rename_bucket(self, bucket_id: str):
        b = self.store.bucket(bucket_id)
        current = b["name"] if b else ""
        text, ok = QInputDialog.getText(self, "Rename bucket", "Bucket name:", text=current)
        if ok and text.strip():
            self.store.rename_bucket(bucket_id, text.strip())
            self._schedule_rebuild()

    def _on_delete_bucket(self, bucket_id: str):
        b = self.store.bucket(bucket_id)
        if b is None:
            return
        if len(self.store.buckets) <= 1:
            QMessageBox.information(self, "Delete bucket", "You need at least one bucket.")
            return
        if b["cards"]:
            resp = QMessageBox.question(
                self, "Delete bucket",
                f"'{b['name']}' has {len(b['cards'])} card(s). "
                f"They'll move to '{self.store.buckets[0]['name']}'. Delete the bucket?")
            if resp != QMessageBox.StandardButton.Yes:
                return
        self.store.remove_bucket(bucket_id)
        self._schedule_rebuild()

    def _on_move_bucket(self, bucket_id: str, delta: int):
        ids = [b["id"] for b in self.store.buckets]
        if bucket_id not in ids:
            return
        self.store.move_bucket(bucket_id, ids.index(bucket_id) + delta)
        self._schedule_rebuild()

    # ---- theming ---------------------------------------------------------

    def apply_theme(self):
        self._pal = self.get_current_palette()
        self._style_status()
        btn_qss = (
            f"QPushButton {{ background-color: {self._pal.surface}; "
            f"color: {self._pal.text}; border: 1px solid {self._pal.border}; "
            f"border-radius: 6px; padding: 5px 12px; }}"
            f"QPushButton:hover {{ border-color: {self._pal.accent}; "
            f"color: {self._pal.accent}; }}")
        self._add_bucket_btn.setStyleSheet(btn_qss)
        self._clear_btn.setStyleSheet(btn_qss)
        self._refresh_btn.setStyleSheet(btn_qss)
        self._triage_toggle.setStyleSheet(
            f"QCheckBox {{ color: {self._pal.text_secondary}; "
            f"font-size: 9pt; background: transparent; }}"
            f"QCheckBox:hover {{ color: {self._pal.accent}; }}")
        # Re-render columns/cards in the new palette.
        self.rebuild_all()
