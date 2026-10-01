"""Tests for the Library decomposition: FlowLayout, the library card widgets,
ProfileDialog, and the library_page re-export shim."""

from techdeck.core.settings import SettingsManager


class _Plugin:
    id = "batch_auditor"
    name = "911 Fake App"
    family = "911"
    description = "A description for the info popup."
    icon = None
    path = None


def _palette():
    from techdeck.ui.theme_manager import get_theme_manager
    return get_theme_manager().get_current_palette()


def test_library_page_reexports_are_same_objects():
    from techdeck.ui.pages import library_page as lp
    from techdeck.ui.widgets import flow_layout as fl, library_card as lc
    from techdeck.ui.dialogs import profile_dialog as pd
    assert lp.FlowLayout is fl.FlowLayout
    assert lp.LibraryPluginCard is lc.LibraryPluginCard
    assert lp.PluginInfoDialog is lc.PluginInfoDialog
    assert lp._MissingLibraryTile is lc._MissingLibraryTile
    assert lp.ProfileDialog is pd.ProfileDialog


def test_flow_layout_wraps_and_reports_height(qapp):
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import QRect
    from techdeck.ui.widgets.flow_layout import FlowLayout
    host = QWidget()
    lay = FlowLayout(host, margin=0, hspacing=10, vspacing=10)
    for _ in range(4):
        w = QWidget(host)
        w.setFixedSize(100, 50)
        lay.addWidget(w)
    assert lay.count() == 4
    # 4 x 100px tiles + spacing in a 250px row -> must wrap to 2 rows
    two_rows = lay.heightForWidth(250)
    one_row = lay.heightForWidth(1000)
    assert two_rows > one_row
    lay.setGeometry(QRect(0, 0, 250, two_rows))
    xs = {lay.itemAt(i).geometry().x() for i in range(4)}
    ys = {lay.itemAt(i).geometry().y() for i in range(4)}
    assert len(ys) >= 2          # actually wrapped
    assert min(xs) == 0          # left-packed


def test_library_card_toggle_and_family_strip(qapp):
    from techdeck.ui.widgets.library_card import LibraryPluginCard
    card = LibraryPluginCard(_Plugin(), "desc", "batch_auditor", _palette())
    # family prefix stripped from the visible name; badge carries the family
    assert card.name_label.text() == "Fake App"
    assert card.family_badge.text() == "911"
    fired = []
    card.toggled.connect(fired.append)
    assert not card.is_checked()
    card.set_checked(True)               # programmatic: no signal
    assert card.is_checked() and fired == []


def test_missing_library_tile_starts_checked(qapp):
    from techdeck.ui.widgets.library_card import _MissingLibraryTile
    tile = _MissingLibraryTile("gone_plugin", _palette())
    assert tile.tile_id == "gone_plugin"
    assert tile._is_checked                # still in the kit until deselected
    tile.restyle(_palette())               # live-theme restamp must not raise


def test_profile_dialog_name_roundtrip(qapp):
    from techdeck.ui.dialogs.profile_dialog import ProfileDialog
    dlg = ProfileDialog("edit", current_name="Engineering")
    assert dlg.get_name() == "Engineering"
    dlg.name_input.setText("  QA  ")
    assert dlg.get_name() == "QA"
    assert not dlg.delete_requested


def test_library_page_still_builds_after_extraction(qapp, tmp_path):
    from techdeck.ui.pages.library_page import LibraryPage
    page = LibraryPage(SettingsManager(settings_dir=tmp_path))
    assert hasattr(page, "profile_combo")


class _LockedPlugin:
    id = "game_puppet_master"
    name = "Puppet Master"
    family = "Games"
    description = "His table."
    icon = None
    path = None


def test_a_locked_library_card_is_greyed_and_inert(qapp):
    """A `show_locked` cartridge sits in the Library greyed out: no selection
    on click, no info button, a dimmed name - until it is unlocked."""
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QMouseEvent
    from techdeck.ui.widgets.library_card import LibraryPluginCard
    theme = _palette()
    card = LibraryPluginCard(_LockedPlugin(), "His table.", "game_puppet_master", theme, is_selected=True, locked=True)
    assert card.is_locked() and not card.is_checked(), "a locked card cannot be in the kit"
    assert not card.info_btn.isVisibleTo(card)
    toggles = []
    card.toggled.connect(lambda c: toggles.append(c))
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(30, 30), QPointF(30, 30),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.mousePressEvent(ev)
    assert toggles == [] and not card.is_checked()
    open_card = LibraryPluginCard(_LockedPlugin(), "His table.", "game_puppet_master", theme)
    assert not open_card.is_locked() and open_card.info_btn.isVisibleTo(open_card)
    # the greyed icon is grey: every opaque pixel has r == g == b
    img = card.icon_label.pixmap().toImage()
    opaque = [img.pixelColor(x, y) for x in range(img.width()) for y in range(img.height())
              if img.pixelColor(x, y).alpha() > 0]
    assert opaque and all(c.red() == c.green() == c.blue() for c in opaque)
