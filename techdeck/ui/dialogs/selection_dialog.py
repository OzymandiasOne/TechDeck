"""
Selection Dialog
================
Generic modal "pick which items to run" dialog: a checkable root row that
toggles every item, one checkable child per item, and a flag on items that have
already been done (so a fresh run reads differently from a re-run at a glance).
Returns the list of items the user chose, or None if they cancelled.

Originally factored out of 911 Setup's nest picker so other plugins (e.g. the
922 Batch Repeater) get the identical layout. ``NestSelectionDialog`` is now a
thin subclass that supplies the 911 wording.
"""

import hashlib
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTreeWidget, QTreeWidgetItem,
)
from PySide6.QtCore import Qt


# A QTreeWidget with a stylesheet won't draw Qt's native checkmark, so we paint
# our own checkmark / dash glyph into the indicator. Tinted to the theme and
# cached per (kind, color) in the temp folder, mirroring ui.utils SVG caching.
_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<path d="M3.5 8.6 L6.6 11.6 L12.6 4.6" fill="none" stroke="{c}" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_DASH_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<path d="M4 8 L12 8" fill="none" stroke="{c}" stroke-width="2.2" '
    'stroke-linecap="round"/></svg>'
)


def _glyph_path(kind: str, color: str) -> str:
    """Write a checkmark/dash SVG tinted to color and return a posix path for QSS."""
    svg = (_CHECK_SVG if kind == "check" else _DASH_SVG).format(c=color)
    stamp = hashlib.md5(f"{kind}|{color}".encode("utf-8")).hexdigest()[:8]
    out_dir = Path(tempfile.gettempdir()) / "techdeck_svg_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sel-{kind}-{stamp}.svg"
    out_path.write_text(svg, encoding="utf-8")
    return out_path.as_posix()


class SelectionDialog(QDialog):
    """Tree of root -> items with checkboxes. selected() returns the picks."""

    _ITEM_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, items, done_items=None, *, parent=None,
                 window_title="Select Items",
                 header="Select Items to Run",
                 root_label="All items",
                 noun="item",
                 done_label="already done",
                 overwrite_note="re-running overwrites them",
                 prompt_note=None,
                 subhead_prefix="",
                 run_button_text="Run Selected",
                 default_checked=True):
        super().__init__(parent)

        self._items = list(items)
        self._done = set(done_items or [])
        self._noun = noun
        self._done_label = done_label
        self._suppress = False  # guards itemChanged while we sync parent/children

        self.setWindowTitle(window_title)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setMinimumHeight(460)

        from techdeck.ui.theme_manager import get_theme_manager
        self.theme = get_theme_manager().get_current_palette()
        self._check_img = _glyph_path("check", self.theme.accent_text)
        self._dash_img = _glyph_path("dash", self.theme.accent_text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header_lbl = QLabel(header)
        header_lbl.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header_lbl)

        n = len(self._items)
        done_n = len([x for x in self._items if x in self._done])
        sub = f"{subhead_prefix}{n} {noun}(s) found."
        if done_n:
            sub += f" {done_n} {done_label} ({overwrite_note})."
        elif prompt_note:
            sub += f" {prompt_note}"
        subhead = QLabel(sub)
        subhead.setWordWrap(True)
        subhead.setStyleSheet(f"color: {self.theme.text_secondary}; font-size: 12px;")
        layout.addWidget(subhead)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {self.theme.divider};")
        layout.addWidget(line)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(22)
        self.tree.setStyleSheet(self._tree_qss())
        layout.addWidget(self.tree, 1)

        init_state = Qt.CheckState.Checked if default_checked else Qt.CheckState.Unchecked

        self.root = QTreeWidgetItem(self.tree)
        self.root.setText(0, root_label)
        self.root.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        self.root.setCheckState(0, init_state)

        for item in self._items:
            child = QTreeWidgetItem(self.root)
            label = item
            if item in self._done:
                label = f"{item}      - {done_label}"
            child.setText(0, label)
            child.setData(0, self._ITEM_ROLE, item)
            child.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            child.setCheckState(0, init_state)

        self.tree.expandItem(self.root)
        self.tree.itemChanged.connect(self._on_item_changed)

        button_row = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setStyleSheet(f"color: {self.theme.text_secondary}; font-size: 12px;")
        button_row.addWidget(self.count_label)
        button_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        self.run_btn = QPushButton(run_button_text)
        self.run_btn.setMinimumHeight(34)
        self.run_btn.setMinimumWidth(140)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setStyleSheet(self._run_button_qss())
        self.run_btn.clicked.connect(self.accept)
        button_row.addWidget(self.run_btn)

        layout.addLayout(button_row)

        self._update_count()

    # --- check-state sync ----------------------------------------------------

    def _on_item_changed(self, item, column):
        if self._suppress:
            return
        self._suppress = True
        try:
            if item is self.root:
                state = item.checkState(0)
                if state != Qt.CheckState.PartiallyChecked:
                    for i in range(self.root.childCount()):
                        self.root.child(i).setCheckState(0, state)
            else:
                self._sync_root_state()
        finally:
            self._suppress = False
        self._update_count()

    def _sync_root_state(self):
        total = self.root.childCount()
        checked = sum(
            1 for i in range(total)
            if self.root.child(i).checkState(0) == Qt.CheckState.Checked
        )
        if checked == 0:
            self.root.setCheckState(0, Qt.CheckState.Unchecked)
        elif checked == total:
            self.root.setCheckState(0, Qt.CheckState.Checked)
        else:
            self.root.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _update_count(self):
        picks = self.selected()
        self.count_label.setText(f"{len(picks)} of {len(self._items)} selected")
        self.run_btn.setEnabled(len(picks) > 0)

    # --- result --------------------------------------------------------------

    def selected(self):
        """Return checked items in their original (input) order."""
        out = []
        for i in range(self.root.childCount()):
            child = self.root.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:
                out.append(child.data(0, self._ITEM_ROLE))
        return out

    # --- styling -------------------------------------------------------------

    def _tree_qss(self) -> str:
        t = self.theme
        return f"""
            QTreeWidget {{
                background-color: {t.surface};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }}
            QTreeWidget::item {{ height: 28px; }}
            QTreeWidget::item:selected {{
                background-color: {t.tile_selected};
                color: {t.text};
                border-radius: 4px;
            }}
            QTreeView::indicator {{
                width: 18px; height: 18px;
                border: 1px solid {t.border_strong};
                border-radius: 4px;
                background: {t.background};
            }}
            QTreeView::indicator:unchecked:hover {{
                border: 1px solid {t.accent};
            }}
            QTreeView::indicator:checked {{
                border: 1px solid {t.accent};
                background: {t.accent};
                image: url("{self._check_img}");
            }}
            QTreeView::indicator:indeterminate {{
                border: 1px solid {t.accent};
                background: {t.accent};
                image: url("{self._dash_img}");
            }}
        """

    def _run_button_qss(self) -> str:
        t = self.theme
        return f"""
            QPushButton {{
                background-color: {t.accent_two};
                color: {t.accent_two_text};
                border: none;
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t.accent_two_hover}; }}
            QPushButton:pressed {{ background-color: {t.accent_two_pressed}; }}
            QPushButton:disabled {{
                background-color: {t.border};
                color: {t.text_secondary};
            }}
        """
