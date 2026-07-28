"""GroupedToggleDialog — checkbox vs name-click separation.

Ticking a stage on/off must never fold/unfold it (checkbox = run/skip);
only clicking the label folds/unfolds. So an unchecked stage stays collapsed
and skipped.
"""

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent

from techdeck.ui.dialogs.grouped_toggle_dialog import GroupedToggleDialog


def _dialog(qapp):
    groups = [{"key": "stage", "label": "Batch Repeater", "checked": True,
               "children": [{"key": "tag", "label": "Label REPEAT cards",
                             "checked": True}]}]
    dlg = GroupedToggleDialog(groups)
    dlg.resize(460, 420)
    dlg.show()
    qapp.processEvents()
    return dlg


def _release_at(dlg, x, y):
    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    dlg.tree.mouseReleaseEvent(ev)


def test_uncheck_stays_collapsed_and_skipped(qapp):
    dlg = _dialog(qapp)
    parent = dlg._parents["stage"]
    assert not parent.isExpanded()

    parent.setCheckState(0, Qt.CheckState.Unchecked)
    qapp.processEvents()

    assert not parent.isExpanded()                       # did NOT auto-expand
    child = dlg._children["stage"]["tag"]
    assert not (child.flags() & Qt.ItemFlag.ItemIsEnabled)   # child greyed
    result = dlg.result_map()["stage"]
    assert result["enabled"] is False                    # stage skipped
    assert result["options"]["tag"] is True              # child state preserved

    dlg.deleteLater()


def test_disabled_child_stays_greyed_and_reports_false(qapp):
    groups = [{"key": "stage", "label": "Repeater", "checked": False,
               "children": [
                   {"key": "live", "label": "Grab models", "checked": True},
                   {"key": "nc", "label": "Grab NC files - offline for now",
                    "checked": False, "disabled": True}]}]
    dlg = GroupedToggleDialog(groups)
    dlg.show()
    qapp.processEvents()

    parent = dlg._parents["stage"]
    live = dlg._children["stage"]["live"]
    nc = dlg._children["stage"]["nc"]

    parent.setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()
    assert live.flags() & Qt.ItemFlag.ItemIsEnabled      # live option enabled
    assert not (nc.flags() & Qt.ItemFlag.ItemIsEnabled)  # disabled stays greyed

    nc.setCheckState(0, Qt.CheckState.Checked)           # defensive: forced check
    result = dlg.result_map()["stage"]["options"]
    assert result == {"live": True, "nc": False}         # still reports False

    dlg.deleteLater()


def test_name_click_expands_checkbox_click_does_not(qapp):
    dlg = _dialog(qapp)
    parent = dlg._parents["stage"]
    idx = dlg.tree.indexFromItem(parent, 0)
    r = dlg.tree.visualRect(idx)
    cy = r.center().y()

    _release_at(dlg, r.left() + 40, cy)                  # name area
    qapp.processEvents()
    assert parent.isExpanded()

    before = parent.isExpanded()
    _release_at(dlg, r.left() + 5, cy)                   # checkbox area
    qapp.processEvents()
    assert parent.isExpanded() == before                 # unchanged by checkbox click

    dlg.deleteLater()
