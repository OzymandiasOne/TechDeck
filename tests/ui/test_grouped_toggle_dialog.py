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


def _two_option_dialog(qapp, checked):
    groups = [{"key": "stage", "label": "Step 2", "checked": checked,
               "children": [
                   {"key": "a", "label": "Folders", "checked": True},
                   {"key": "b", "label": "Binder", "checked": False}]}]
    dlg = GroupedToggleDialog(groups)
    dlg.show()
    qapp.processEvents()
    return dlg


def _shown(dlg):
    return {key: child.checkState(0) == Qt.CheckState.Checked
            for key, child in dlg._children["stage"].items()}


def test_unticking_a_stage_shows_its_options_unticked(qapp):
    """A skipped stage's options used to stay drawn as bright ticks that could
    not be clicked off (2026-11-23). Nothing under a skipped stage runs, so
    nothing under it shows a tick."""
    dlg = _two_option_dialog(qapp, checked=True)
    assert _shown(dlg) == {"a": True, "b": False}

    dlg._parents["stage"].setCheckState(0, Qt.CheckState.Unchecked)
    qapp.processEvents()
    assert _shown(dlg) == {"a": False, "b": False}
    # ...but what they were set to is still what is reported (toggle memory
    # saves this, and must not learn "everything off" from a skipped stage)
    assert dlg.result_map()["stage"]["options"] == {"a": True, "b": False}

    dlg.deleteLater()


def test_ticking_the_stage_again_puts_its_options_back(qapp):
    dlg = _two_option_dialog(qapp, checked=True)
    parent = dlg._parents["stage"]
    parent.setCheckState(0, Qt.CheckState.Unchecked)
    parent.setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()

    assert _shown(dlg) == {"a": True, "b": False}
    for child in dlg._children["stage"].values():
        assert child.flags() & Qt.ItemFlag.ItemIsEnabled   # clickable again
    assert dlg.result_map()["stage"]["options"] == {"a": True, "b": False}

    dlg.deleteLater()


def test_a_stage_that_opens_unticked_shows_no_ticks_under_it(qapp):
    dlg = _two_option_dialog(qapp, checked=False)
    assert _shown(dlg) == {"a": False, "b": False}
    assert dlg.result_map()["stage"]["options"] == {"a": True, "b": False}

    dlg._parents["stage"].setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()
    assert _shown(dlg) == {"a": True, "b": False}        # its declared defaults

    dlg.deleteLater()


def test_an_option_changed_while_on_is_what_comes_back(qapp):
    dlg = _two_option_dialog(qapp, checked=True)
    parent = dlg._parents["stage"]
    dlg._children["stage"]["b"].setCheckState(0, Qt.CheckState.Checked)
    parent.setCheckState(0, Qt.CheckState.Unchecked)
    parent.setCheckState(0, Qt.CheckState.Checked)
    qapp.processEvents()

    assert _shown(dlg) == {"a": True, "b": True}

    dlg.deleteLater()
