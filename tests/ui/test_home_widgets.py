"""Tests for the Home tile widgets extracted from home_page.py, plus a
regression guard that HomePage still builds after the extraction."""

from techdeck.core.settings import SettingsManager


class _Plugin:
    id = "batch_auditor"
    name = "Batch Auditor"
    family = "General"
    icon = None
    path = None


def _palette():
    from techdeck.ui.theme_manager import get_theme_manager
    return get_theme_manager().get_current_palette()


def test_plugin_card_builds_and_status(qapp):
    from techdeck.ui.widgets.plugin_card import PluginCard
    card = PluginCard(_Plugin(), "a description", "batch_auditor", _palette())
    assert card.tile_id == "batch_auditor"
    for status in (PluginCard.STATUS_RUNNING, PluginCard.STATUS_SUCCESS,
                   PluginCard.STATUS_ERROR, PluginCard.STATUS_IDLE):
        card.set_status(status)          # must not raise
    # drag protocol + selection signals are present
    assert hasattr(card, "drag_started")
    assert hasattr(card, "toggled")


def test_missing_tile_builds(qapp):
    from techdeck.ui.widgets.plugin_card import _MissingTile
    removed = []
    tile = _MissingTile("gone_plugin", _palette(), removed.append)
    assert tile.tile_id == "gone_plugin"
    assert hasattr(tile, "drag_started")


def test_tile_grid_controller_order_and_slots(qapp, tmp_path):
    from PySide6.QtWidgets import QWidget, QScrollArea
    from techdeck.ui.widgets.tile_grid import TileGridController, _GridSurface
    surface = _GridSurface()
    scroll = QScrollArea()
    scroll.setWidget(surface)
    surface.resize(600, 400)

    ctrl = TileGridController(surface, SettingsManager(settings_dir=tmp_path))
    ctrl.set_scroll_area(scroll)
    order = ["a", "b", "c"]
    widgets = {t: QWidget(surface) for t in order}
    ctrl.set_tiles(order, widgets)

    assert ctrl.get_order() == order
    # Two different slots resolve to different positions.
    p0, p1 = ctrl.slot_pos(0, 3), ctrl.slot_pos(1, 3)
    assert (p0.x(), p0.y()) != (p1.x(), p1.y())


def test_home_page_still_builds_after_extraction(qapp, tmp_path):
    """The page now imports PluginCard/TileGridController from sibling modules —
    guard that it still constructs and wires the controller."""
    from techdeck.ui.pages.home_page import HomePage
    hp = HomePage(SettingsManager(settings_dir=tmp_path))
    assert type(hp._tile_ctrl).__name__ == "TileGridController"
