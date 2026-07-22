"""Tests for the Emporium decomposition: the arcade_chrome shared layer, the
CATALOG data module, the store_tiles widgets, and the emporium_page re-export
shim that keeps every pre-split import path working."""

from techdeck.core.settings import SettingsManager


# ---- re-export contract ------------------------------------------------------

def test_emporium_page_reexports_are_same_objects():
    """achievements/mystuff/garden_scene/tools historically import these from
    emporium_page — the shim must hand back the exact objects from the new
    homes, not copies."""
    from techdeck.ui.pages import emporium_page as ep
    from techdeck.ui import arcade_chrome as ac, emporium_catalog as cat
    from techdeck.ui.widgets import store_tiles as st

    assert ep.CATALOG is cat.CATALOG
    for name in ("EMP", "PixelDialog", "_SoldStamp", "_draw_bubble",
                 "_equipped_badge", "_garden_dir", "_greyed", "_load_art",
                 "_load_pixmap", "_marquee", "_sprites_dir", "_tile_ring",
                 "_trim_v", "_ascii", "_brighten", "_default_spinner_pixmap"):
        assert getattr(ep, name) is getattr(ac, name), name
    for name in ("StoreTile", "CategoryBox", "ShopWindow"):
        assert getattr(ep, name) is getattr(st, name), name


# ---- catalog data invariants -------------------------------------------------

def test_catalog_ids_unique_and_rows_complete():
    from techdeck.ui.emporium_catalog import CATALOG
    ids = [item["id"] for item in CATALOG]
    assert len(ids) == len(set(ids))
    for item in CATALOG:
        for key in ("id", "name", "category", "sprite", "cost", "kind"):
            assert key in item, f"{item.get('id')} missing {key}"
        assert item["cost"] > 0


def test_catalog_categories_match_store_tabs():
    """Every item's category must be a real store tab, or it silently never
    renders anywhere."""
    from techdeck.ui.emporium_catalog import CATALOG
    from techdeck.ui.pages.emporium_page import EmporiumPage
    tabs = {cat_id for cat_id, _ in EmporiumPage.CATEGORIES}
    for item in CATALOG:
        assert item["category"] in tabs, item["id"]


def test_catalog_bundles_reference_real_ids():
    from techdeck.ui.emporium_catalog import CATALOG
    ids = {item["id"] for item in CATALOG}
    for item in CATALOG:
        for extra in item.get("bundle", []):
            assert extra in ids, f"{item['id']} bundles unknown {extra}"


# ---- chrome helpers ----------------------------------------------------------

def test_ascii_maps_smart_punctuation():
    from techdeck.ui.arcade_chrome import _ascii
    assert _ascii("it’s — “fine”") == "it's - \"fine\""


def test_asset_dirs_resolve_from_new_module_location():
    """arcade_chrome moved up a package level vs emporium_page — the parents[]
    walk must still land on the repo's asset dirs."""
    from techdeck.ui.arcade_chrome import _garden_dir, _sprites_dir
    assert _sprites_dir().is_dir()
    assert (_sprites_dir() / "woogy.tdart").exists()
    assert _garden_dir().is_dir()


def test_load_pixmap_and_greyed(qapp):
    from techdeck.ui.arcade_chrome import _greyed, _load_pixmap
    pm = _load_pixmap("spinner_beyblade.tdart", 72)
    assert pm is not None and not pm.isNull()
    grey = _greyed(pm)
    assert grey is not None and grey.size() == pm.size()
    assert _load_pixmap("does_not_exist.tdart", 72) is None
    assert _greyed(None) is None


# ---- store widgets -----------------------------------------------------------

class _PageStub:
    """The narrow slice of EmporiumPage that StoreTile actually touches."""

    def __init__(self, settings):
        self.settings = settings
        self._bubbles = {"tile": None}
        self.actions = []

    def handle_tile_action(self, item):
        self.actions.append(item["id"])


def _spinner_item():
    from techdeck.ui.emporium_catalog import CATALOG
    return next(i for i in CATALOG if i["kind"] == "spinner")


def test_store_tile_buy_then_owned_states(qapp, tmp_path):
    from techdeck.ui.widgets.store_tiles import StoreTile
    page = _PageStub(SettingsManager(settings_dir=tmp_path))
    item = _spinner_item()
    tile = StoreTile(item, page)

    # fresh save: not owned, SOLD stamp hidden, buy button live
    assert not tile.owned
    assert tile.stamp.isHidden()
    assert tile.action_btn.isEnabled()

    page.settings.unlock_item(item["id"])
    page.settings.set_equipped_spinner(item["id"])
    tile.refresh()
    assert tile.owned and tile.equipped
    assert not tile.stamp.isHidden()
    assert not tile.action_btn.isEnabled()   # EQUIPPED button is inert


def test_store_tile_action_routes_to_page(qapp, tmp_path):
    from techdeck.ui.widgets.store_tiles import StoreTile
    page = _PageStub(SettingsManager(settings_dir=tmp_path))
    item = _spinner_item()
    tile = StoreTile(item, page)
    tile.action_btn.click()
    assert page.actions == [item["id"]]


def test_category_box_selection_toggle(qapp, tmp_path):
    from techdeck.ui.widgets.store_tiles import CategoryBox
    page = _PageStub(SettingsManager(settings_dir=tmp_path))
    box = CategoryBox("toys", "Toys", None, page, box_w=120)
    assert not box.selected
    box.set_selected(True)
    assert box.selected


# ---- the page itself ---------------------------------------------------------

def test_emporium_page_still_builds_after_extraction(qapp, tmp_path):
    """EmporiumPage now pulls its widgets/chrome/data from sibling modules —
    guard that it constructs, builds a tile per catalog item, and can lay out
    a category grid."""
    from techdeck.ui.emporium_catalog import CATALOG
    from techdeck.ui.pages.emporium_page import EmporiumPage
    page = EmporiumPage(SettingsManager(settings_dir=tmp_path))
    assert len(page.tiles) == len(CATALOG)
    page._category = "toys"
    page._populate_grid()
    shown = [t for t in page.tiles if not t.isHidden()]
    assert shown and all(t.item["category"] == "toys" for t in shown)
    page.refresh()   # must not raise
