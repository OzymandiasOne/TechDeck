"""
Nest Selection Dialog
======================
Modal dialog shown by 911 Setup after the user enters a batch number. It
displays the batch as a tree: a checkable batch-folder root with one checkable
child per nest in the batch. Checking/unchecking the root toggles every nest;
individual nests can be toggled freely.

Nests that already have a folder in the batch are marked "already set up" so the
operator can tell a fresh run from a re-run at a glance. The dialog returns the
list of nests the user chose to run, or None if they cancelled.
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
    out_path = out_dir / f"nestsel-{kind}-{stamp}.svg"
    out_path.write_text(svg, encoding="utf-8")
    return out_path.as_posix()


class NestSelectionDialog(QDialog):
    """Tree of batch -> nests with checkboxes. selected_nests() returns the picks."""

    _NEST_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, batch_number, all_nests, existing_nests=None, parent=None):
        super().__init__(parent)

        self._all_nests = list(all_nests)
        self._existing = set(existing_nests or [])
        self._suppress = False  # guards itemChanged while we sync parent/children

        self.setWindowTitle(f"911 Setup - Batch {batch_number}")
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

        header = QLabel("Select Nests to Run")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        n = len(self._all_nests)
        existing_n = len([x for x in self._all_nests if x in self._existing])
        sub = f"Batch {batch_number} - {n} nest(s) found."
        if existing_n:
            sub += f" {existing_n} already set up (re-running overwrites them)."
        else:
            sub += " Check the nests you want to set up."
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

        self.root = QTreeWidgetItem(self.tree)
        self.root.setText(0, f"Batch {batch_number}  (all nests)")
        self.root.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        self.root.setCheckState(0, Qt.CheckState.Checked)

        for nest in self._all_nests:
            child = QTreeWidgetItem(self.root)
            label = nest
            if nest in self._existing:
                label = f"{nest}      - already set up"
            child.setText(0, label)
            child.setData(0, self._NEST_ROLE, nest)
            child.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            child.setCheckState(0, Qt.CheckState.Checked)

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

        self.run_btn = QPushButton("Run Selected")
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
        picks = self.selected_nests()
        self.count_label.setText(f"{len(picks)} of {len(self._all_nests)} selected")
        self.run_btn.setEnabled(len(picks) > 0)

    # --- result --------------------------------------------------------------

    def selected_nests(self):
        """Return checked nests in their original batch-list order."""
        out = []
        for i in range(self.root.childCount()):
            child = self.root.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:
                out.append(child.data(0, self._NEST_ROLE))
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
