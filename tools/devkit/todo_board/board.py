"""The DevKit To-Do Board widget — Teams-style buckets + cards over the feedback
backlog.

Layout: a header bar (Refresh / Add bucket / status) over a horizontally
scrolling row of fixed-width `BucketColumn`s. Each column has its own vertical
scroll and is a drop target: dragging a `TaskCard` shows a drop-indicator line
and, on release, moves the card in the `BoardStore` and re-renders.

Everything is repainted from the active theme palette and re-rendered on live
theme change (ThemeAware). Source-only — never in the frozen build.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QToolButton, QMenu, QInputDialog, QMessageBox, QSizePolicy,
)

from techdeck.ui.theme_aware import ThemeAware
from tools.devkit.todo_board.model import BoardStore, load_feedback
from tools.devkit.todo_board.widgets import TaskCard, CARD_MIME

COLUMN_WIDTH = 290


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

    def __init__(self, bucket: dict, palette, parent=None):
        super().__init__(parent)
        self.bucket_id = bucket["id"]
        self._pal = palette
        self.setObjectName("bucketCol")
        self.setFixedWidth(COLUMN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            "#bucketCol { background-color: rgba(127,127,127,0.06); "
            "border-radius: 10px; }")

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

    def _icon_btn_qss(self) -> str:
        return (f"QToolButton {{ color: {self._pal.text_secondary}; "
                f"background: transparent; border: none; font-size: 15px; "
                f"font-weight: bold; padding: 0 4px; }}"
                f"QToolButton:hover {{ color: {self._pal.accent}; }}")

    def add_card_widget(self, card: TaskCard):
        self._list.add_card(card)

    def set_count(self, n: int):
        self._count.setText(str(n))

    def _open_menu(self, anchor):
        menu = QMenu(self)
        act_add = menu.addAction("Add card…")
        act_rename = menu.addAction("Rename bucket…")
        menu.addSeparator()
        act_left = menu.addAction("Move left")
        act_right = menu.addAction("Move right")
        menu.addSeparator()
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
        elif chosen == act_delete:
            self.delete_requested.emit(self.bucket_id)


class TodoBoard(QWidget, ThemeAware):
    """The DevKit To-Do Board tool (mounted first in the DevKit picker)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = BoardStore()
        self._pal = self.get_current_palette()
        self._rebuild_pending = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(10)

        # --- header bar ---
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self._title = QLabel("To-Do Board")
        tf = self._title.font()
        tf.setPointSize(15)
        tf.setBold(True)
        self._title.setFont(tf)
        bar.addWidget(self._title)
        self._status = QLabel("")
        bar.addWidget(self._status)
        bar.addStretch()
        self._add_bucket_btn = QPushButton("+ Bucket")
        self._add_bucket_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_bucket_btn.clicked.connect(self._on_add_bucket)
        bar.addWidget(self._add_bucket_btn)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._sync_and_rebuild)
        bar.addWidget(self._refresh_btn)
        outer.addLayout(bar)

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
        load = load_feedback()
        added = self.store.sync(load)
        if load.ok:
            msg = load.message
            if added:
                msg += f"  ·  +{added} new"
            self._status.setText(msg)
            self._status.setStyleSheet(
                f"color: {self._pal.text_secondary}; font-size: 9pt;")
        else:
            self._status.setText("⚠ " + load.message)
            self._status.setStyleSheet(f"color: {self._pal.warning}; font-size: 9pt;")
        self.rebuild_all()

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
            for key in bucket["cards"]:
                if key not in self.store.cards:
                    continue
                card = TaskCard(self.store, key, self._pal)
                card.deleted.connect(self._on_card_deleted)
                col.add_card_widget(card)
            col.set_count(len(bucket["cards"]))
            self._cols_layout.addWidget(col)
            self._columns[bucket["id"]] = col
        self._cols_layout.addStretch(1)   # left-pack the columns

    # ---- card intents ----------------------------------------------------

    def _on_card_dropped(self, key: str, bucket_id: str, index: int):
        self.store.move_card(key, bucket_id, index)
        self._schedule_rebuild()

    def _on_card_deleted(self, key: str):
        self.store.delete_card(key)
        self._schedule_rebuild()

    def _on_add_card(self, bucket_id: str):
        text, ok = QInputDialog.getText(self, "Add card", "Card title:")
        if ok and text.strip():
            self.store.add_manual_card(bucket_id, text.strip())
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
        self._title.setStyleSheet(f"color: {self._pal.text};")
        btn_qss = (
            f"QPushButton {{ background-color: {self._pal.surface}; "
            f"color: {self._pal.text}; border: 1px solid {self._pal.border}; "
            f"border-radius: 6px; padding: 5px 12px; }}"
            f"QPushButton:hover {{ border-color: {self._pal.accent}; "
            f"color: {self._pal.accent}; }}")
        self._add_bucket_btn.setStyleSheet(btn_qss)
        self._refresh_btn.setStyleSheet(btn_qss)
        # Re-render columns/cards in the new palette.
        self.rebuild_all()
