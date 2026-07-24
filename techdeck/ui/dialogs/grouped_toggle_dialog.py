"""
Grouped Toggle Dialog
=====================
Two-level "which stages should this run include?" dialog: each GROUP is a
checkable top-level row (an app/stage — run it or skip it), and clicking a
group's name expands it to reveal that group's own option toggles underneath.
Styled after SelectionDialog so multi-pick dialogs read the same everywhere.

Unlike SelectionDialog's root->items tree, the two levels here mean different
things: a parent checkbox decides whether the stage RUNS, a child checkbox
tunes HOW it runs. So parents are never tri-state, and unchecking a parent
greys its children (their state is kept and returned regardless).

First used by the consolidated 922 Setup (Teams Setup -> Batch Repeater ->
Pallet Stamper master window). Reached from plugin worker threads via
``console.request_grouped_toggles`` / ``sdk.request_grouped_toggles``.

``groups`` is plain data so it marshals cleanly across threads::

    [{"key": "teams_setup", "label": "922 Teams Setup", "checked": True,
      "children": [{"key": "labels", "label": "Apply pallet labels",
                    "checked": True}]},
     ...]

``result_map()`` returns::

    {"teams_setup": {"enabled": True, "options": {"labels": True}}, ...}
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTreeWidget, QTreeWidgetItem,
)
from PySide6.QtCore import Qt

from techdeck.ui.dialogs.selection_dialog import _glyph_path


class _StageTree(QTreeWidget):
    """QTreeWidget that expands/collapses a top-level group ONLY when its NAME
    is clicked — never when its checkbox is ticked. So turning a stage on/off
    never changes what's unfolded (checkbox = run/skip; name = show options)."""

    def mouseReleaseEvent(self, event):
        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        super().mouseReleaseEvent(event)   # let the base toggle the checkbox
        if not idx.isValid():
            return
        item = self.itemFromIndex(idx)
        if item is None or item.parent() is not None or item.childCount() == 0:
            return
        # Ignore the checkbox indicator + the expand arrow (left edge); only a
        # click on the label text folds/unfolds the group.
        r = self.visualRect(idx)
        if pos.x() <= r.left() + 24:
            return
        item.setExpanded(not item.isExpanded())


class GroupedToggleDialog(QDialog):
    """Tree of checkable groups with per-group option toggles."""

    _KEY_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, groups, *, parent=None,
                 window_title="Select Stages",
                 header="Select Stages to Run",
                 subtext="Click a name to show its options.",
                 run_button_text="Run Selected"):
        super().__init__(parent)

        self._groups = [dict(g) for g in groups]
        self._suppress = False  # guards itemChanged while we grey children

        self.setWindowTitle(window_title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMinimumHeight(420)

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

        if subtext:
            sub = QLabel(subtext)
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"color: {self.theme.text_secondary}; font-size: 12px;")
            layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {self.theme.divider};")
        layout.addWidget(line)

        self.tree = _StageTree()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(22)
        self.tree.setStyleSheet(self._tree_qss())
        layout.addWidget(self.tree, 1)

        self._parents: dict[str, QTreeWidgetItem] = {}
        self._children: dict[str, dict[str, QTreeWidgetItem]] = {}
        for group in self._groups:
            gkey = group["key"]
            parent = QTreeWidgetItem(self.tree)
            parent.setText(0, group.get("label", gkey))
            parent.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                            | Qt.ItemFlag.ItemIsEnabled)
            parent.setCheckState(
                0, Qt.CheckState.Checked if group.get("checked", True)
                else Qt.CheckState.Unchecked)
            parent.setData(0, self._KEY_ROLE, gkey)
            self._parents[gkey] = parent
            self._children[gkey] = {}
            for child_spec in group.get("children", []):
                ckey = child_spec["key"]
                child = QTreeWidgetItem(parent)
                child.setText(0, child_spec.get("label", ckey))
                child.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                               | Qt.ItemFlag.ItemIsEnabled)
                child.setCheckState(
                    0, Qt.CheckState.Checked if child_spec.get("checked", True)
                    else Qt.CheckState.Unchecked)
                child.setData(0, self._KEY_ROLE, ckey)
                self._children[gkey][ckey] = child

        # Groups start collapsed — clicking the name (handled by _StageTree)
        # reveals the options; ticking the checkbox never changes the fold.
        self.tree.itemChanged.connect(self._on_item_changed)

        button_row = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setStyleSheet(
            f"color: {self.theme.text_secondary}; font-size: 12px;")
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

        for gkey, parent in self._parents.items():
            self._apply_child_enable(gkey)
        self._update_count()

    # --- interaction ----------------------------------------------------------

    def _on_item_changed(self, item, column):
        if self._suppress:
            return
        if item.parent() is None:
            gkey = item.data(0, self._KEY_ROLE)
            self._apply_child_enable(gkey)
            # Ticking a stage on/off only greys/ungreys its options — it never
            # folds or unfolds the group (that's the name-click's job). An
            # unchecked stage therefore stays collapsed and skipped.
        self._update_count()

    def _apply_child_enable(self, gkey: str):
        """Grey a group's option rows while the group itself is unchecked.
        Check state is preserved either way — options only READ back when the
        group is enabled, so nothing is lost by toggling the parent."""
        parent = self._parents[gkey]
        enabled = parent.checkState(0) == Qt.CheckState.Checked
        self._suppress = True
        try:
            for child in self._children[gkey].values():
                flags = Qt.ItemFlag.ItemIsUserCheckable
                if enabled:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                child.setFlags(flags)
        finally:
            self._suppress = False

    def _update_count(self):
        enabled = [g for g in self._groups
                   if self._parents[g["key"]].checkState(0)
                   == Qt.CheckState.Checked]
        self.count_label.setText(f"{len(enabled)} of {len(self._groups)} selected")
        self.run_btn.setEnabled(len(enabled) > 0)

    # --- result --------------------------------------------------------------

    def result_map(self) -> dict:
        """{group_key: {"enabled": bool, "options": {child_key: bool}}}"""
        out = {}
        for group in self._groups:
            gkey = group["key"]
            out[gkey] = {
                "enabled": (self._parents[gkey].checkState(0)
                            == Qt.CheckState.Checked),
                "options": {
                    ckey: child.checkState(0) == Qt.CheckState.Checked
                    for ckey, child in self._children[gkey].items()
                },
            }
        return out

    # --- styling (mirrors SelectionDialog) ------------------------------------

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
