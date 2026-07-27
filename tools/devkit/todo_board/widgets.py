"""Card, label-chip, and checklist widgets for the DevKit To-Do Board.

`TaskCard` is the Teams-style card: colored label chips, a title, a meta line,
and an inline checklist whose items strike through when ticked. It is also the
drag SOURCE — a native `QDrag` carrying the card's key, so `BucketColumn` (in
board.py) can drop it into another bucket.

Content edits (checklist, labels, title) mutate the injected `BoardStore`
directly and re-render in place; structural changes (delete) are emitted to the
board via the `deleted` signal so it can rebuild.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QDrag, QFont, QColor
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QToolButton, QCheckBox,
    QLineEdit, QMenu, QApplication, QWidget, QInputDialog,
)

from techdeck.ui.widgets.flow_layout import FlowLayout

CARD_MIME = "application/x-techdeck-todocard"

# Family colors match the Home tile badges; everything else gets a stable color
# from a small chip palette so a given label is always the same hue.
_FAMILY_COLORS = {
    "902": "#06B6D4", "911": "#3B82F6", "922": "#F59E0B",
    "QA": "#10B981", "Games": "#A855F7", "General": "#8B5CF6",
}
_CHIP_PALETTE = ["#0EA5E9", "#8B5CF6", "#EC4899", "#F97316",
                 "#14B8A6", "#EF4444", "#84CC16", "#6366F1"]
_NEUTRAL = "#6B7280"


def label_color(text: str) -> str:
    """Pick a chip color for a label. Family-tagged features use the family
    color; suggestion-box/other buckets go neutral; anything else gets a stable
    hashed color."""
    t = (text or "").strip()
    if not t:
        return _NEUTRAL
    for fam, color in _FAMILY_COLORS.items():
        if t == fam or t.startswith(fam + " "):
            return color
    low = t.lower()
    if "game" in low or "asa" in low:
        return _FAMILY_COLORS["Games"]
    if "suggestion" in low or low in ("other", "new", "n/a", "general"):
        return _NEUTRAL
    return _CHIP_PALETTE[sum(ord(c) for c in t) % len(_CHIP_PALETTE)]


def _readable_on(hex_color: str) -> str:
    """Black or white text, whichever reads better on the given fill."""
    c = QColor(hex_color)
    luminance = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
    return "#1A1A1A" if luminance > 0.6 else "#FFFFFF"


def _format_date(date_iso: str) -> str:
    if not date_iso:
        return ""
    try:
        dt = datetime.fromisoformat(date_iso)
    except ValueError:
        return date_iso[:10]
    fmt = "%b %d" if dt.year == datetime.now().year else "%b %d, %Y"
    return dt.strftime(fmt)


class LabelChip(QFrame):
    """A small filled, rounded label with an inline remove (×) button."""

    def __init__(self, text: str, on_remove, parent=None):
        super().__init__(parent)
        color = label_color(text)
        fg = _readable_on(color)
        self.setObjectName("labelChip")
        self.setStyleSheet(
            f"#labelChip {{ background-color: {color}; border-radius: 7px; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(7, 1, 3, 1)
        row.setSpacing(2)
        lbl = QLabel(text)
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {fg}; background: transparent;")
        row.addWidget(lbl)
        x = QToolButton()
        x.setText("×")
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(
            f"QToolButton {{ color: {fg}; background: transparent; border: none; "
            f"font-size: 11px; font-weight: bold; padding: 0px; }}"
            f"QToolButton:hover {{ color: #FFFFFF; }}")
        x.clicked.connect(lambda: on_remove(text))
        row.addWidget(x)


class _ChecklistRow(QWidget):
    """One checklist item: a checkbox + text that strikes through when done,
    plus a hover-revealed delete button."""

    def __init__(self, text: str, done: bool, palette, on_toggle, on_delete, parent=None):
        super().__init__(parent)
        self._palette = palette
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.box = QCheckBox()
        self.box.setChecked(done)
        self.box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.box.toggled.connect(lambda _c: on_toggle())
        row.addWidget(self.box, 0, Qt.AlignmentFlag.AlignTop)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self._apply_text_style(done)
        row.addWidget(self.label, 1)

        self.delete_btn = QToolButton()
        self.delete_btn.setText("×")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setToolTip("Delete task")
        self.delete_btn.setStyleSheet(
            f"QToolButton {{ color: {palette.text_secondary}; background: transparent; "
            f"border: none; font-size: 13px; }}"
            f"QToolButton:hover {{ color: {palette.error}; }}")
        self.delete_btn.clicked.connect(on_delete)
        row.addWidget(self.delete_btn, 0, Qt.AlignmentFlag.AlignTop)

    def _apply_text_style(self, done: bool):
        f = self.label.font()
        f.setStrikeOut(done)
        self.label.setFont(f)
        color = self._palette.text_secondary if done else self._palette.text
        self.label.setStyleSheet(f"color: {color}; background: transparent;")


class TaskCard(QFrame):
    """A draggable board card backed by one entry in the BoardStore."""

    deleted = Signal(str)   # card key — board removes it and rebuilds

    def __init__(self, store, key: str, palette, parent=None):
        super().__init__(parent)
        self.store = store
        self.key = key
        self._pal = palette
        self._press_global = QPoint()

        self.setObjectName("todoCard")
        self.setAcceptDrops(False)
        self._apply_frame_style()

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(10, 8, 8, 10)
        self._outer.setSpacing(7)

        # --- top row: labels (wrapping) + menu button ---
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self._labels_host = QWidget()
        self._labels_flow = FlowLayout(self._labels_host, margin=0, hspacing=4, vspacing=4)
        top.addWidget(self._labels_host, 1)

        self._menu_btn = QToolButton()
        self._menu_btn.setText("···")   # middle dots — in-font on Segoe UI
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet(
            f"QToolButton {{ color: {palette.text_secondary}; background: transparent; "
            f"border: none; font-size: 15px; font-weight: bold; padding: 0 2px; }}"
            f"QToolButton:hover {{ color: {palette.accent}; }}")
        self._menu_btn.clicked.connect(self._open_menu)
        top.addWidget(self._menu_btn, 0, Qt.AlignmentFlag.AlignTop)
        self._outer.addLayout(top)

        # --- title ---
        self._title = QLabel()
        self._title.setWordWrap(True)
        tf = QFont()
        tf.setPointSize(10)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        self._title.setStyleSheet(f"color: {palette.text}; background: transparent;")
        self._outer.addWidget(self._title)

        # --- meta (user · date · source) ---
        self._meta = QLabel()
        mf = QFont()
        mf.setPointSize(8)
        self._meta.setFont(mf)
        self._meta.setStyleSheet(f"color: {palette.text_secondary}; background: transparent;")
        self._outer.addWidget(self._meta)

        # --- checklist section (rebuilt in place) ---
        self._checklist_host = QWidget()
        self._checklist_v = QVBoxLayout(self._checklist_host)
        self._checklist_v.setContentsMargins(0, 2, 0, 0)
        self._checklist_v.setSpacing(4)
        self._outer.addWidget(self._checklist_host)

        self._render()

    # ---- rendering -------------------------------------------------------

    def _card(self) -> dict:
        return self.store.cards.get(self.key, {})

    def _render(self):
        c = self._card()
        self._title.setText(c.get("title", ""))
        self._render_meta(c)
        self._render_labels(c)
        self._render_checklist(c)

    def _render_meta(self, c: dict):
        bits = []
        if c.get("user"):
            bits.append(c["user"])
        date = _format_date(c.get("date", ""))
        if date:
            bits.append(date)
        if c.get("source") == "archive":
            bits.append("archived")
        elif c.get("source") == "manual":
            bits.append("manual")
        self._meta.setText("  ·  ".join(bits))
        self._meta.setVisible(bool(bits))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_labels(self, c: dict):
        self._clear_layout(self._labels_flow)
        labels = c.get("labels", [])
        for text in labels:
            self._labels_flow.addWidget(LabelChip(text, self._on_remove_label))
        self._labels_host.setVisible(bool(labels))
        self._labels_host.updateGeometry()

    def _render_checklist(self, c: dict):
        self._clear_layout(self._checklist_v)
        items = c.get("checklist", [])
        if items:
            done = sum(1 for i in items if i.get("done"))
            progress = QLabel(f"{done} / {len(items)} done")
            pf = QFont()
            pf.setPointSize(8)
            pf.setBold(True)
            progress.setFont(pf)
            accent = self._pal.success if done == len(items) else self._pal.text_secondary
            progress.setStyleSheet(f"color: {accent}; background: transparent;")
            self._checklist_v.addWidget(progress)
        for idx, item in enumerate(items):
            self._checklist_v.addWidget(_ChecklistRow(
                item.get("text", ""), item.get("done", False), self._pal,
                on_toggle=lambda i=idx: self._on_toggle_item(i),
                on_delete=lambda i=idx: self._on_delete_item(i)))

        add = QLineEdit()
        add.setPlaceholderText("+ Add a task")
        add.setFrame(False)
        add.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; "
            f"color: {self._pal.text}; font-size: 9pt; padding: 1px 0; }}")
        add.returnPressed.connect(lambda le=add: self._on_add_item(le))
        self._checklist_v.addWidget(add)

    # ---- content edits (mutate store, re-render in place) ----------------

    def _on_add_item(self, line_edit: QLineEdit):
        text = line_edit.text().strip()
        if not text:
            return
        self.store.add_checklist_item(self.key, text)
        self._render_checklist(self._card())
        # Refocus the (freshly rebuilt) add field so several tasks flow quickly.
        last = self._checklist_v.itemAt(self._checklist_v.count() - 1)
        if last and isinstance(last.widget(), QLineEdit):
            last.widget().setFocus()

    def _on_toggle_item(self, index: int):
        self.store.toggle_checklist_item(self.key, index)
        self._render_checklist(self._card())

    def _on_delete_item(self, index: int):
        self.store.remove_checklist_item(self.key, index)
        self._render_checklist(self._card())

    def _on_remove_label(self, text: str):
        self.store.remove_label(self.key, text)
        self._render_labels(self._card())

    def _open_menu(self):
        menu = QMenu(self)
        act_label = menu.addAction("Add label…")
        act_rename = None
        if self._card().get("source") == "manual":
            act_rename = menu.addAction("Rename…")
        menu.addSeparator()
        act_delete = menu.addAction("Delete card")
        chosen = menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))
        if chosen is None:
            return
        if chosen == act_label:
            text, ok = QInputDialog.getText(self, "Add label", "Label:")
            if ok and text.strip():
                self.store.add_label(self.key, text.strip())
                self._render_labels(self._card())
        elif act_rename is not None and chosen == act_rename:
            text, ok = QInputDialog.getText(
                self, "Rename card", "Title:", text=self._card().get("title", ""))
            if ok and text.strip():
                self.store.set_title(self.key, text.strip())
                self._title.setText(text.strip())
        elif chosen == act_delete:
            self.deleted.emit(self.key)

    # ---- theming ---------------------------------------------------------

    def _apply_frame_style(self):
        self.setStyleSheet(
            f"#todoCard {{ background-color: {self._pal.surface}; "
            f"border: 1px solid {self._pal.border}; border-radius: 8px; }}"
            f"#todoCard:hover {{ border-color: {self._pal.accent}; }}")

    # ---- drag source -----------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        moved = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
        if moved < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(CARD_MIME, self.key.encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())
        self.setVisible(False)   # hide source while dragging (board rebuilds on drop)
        result = drag.exec(Qt.DropAction.MoveAction)
        # If the drop landed, the board is rebuilding — leave this stale card
        # hidden so it doesn't flash back into its old slot. Only a cancelled
        # drag needs the source restored.
        if result != Qt.DropAction.MoveAction:
            self.setVisible(True)
