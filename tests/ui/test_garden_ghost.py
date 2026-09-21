"""The Ghost store item: he haunts the bookshelf in My House
(techdeck/ui/widgets/garden_scene.py, "The Ghost")."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from techdeck.ui import emporium_catalog
from techdeck.ui.widgets import garden_scene as gs


class _Settings:
    TREE_STAGES = 5

    def __init__(self, owned):
        self.owned = set(owned)

    def is_unlocked(self, item_id):
        return item_id in self.owned

    def get_tree_stage(self):
        return 5

    def get_equipped_background(self):
        return ""


@pytest.fixture
def scene(qapp):
    made = []

    def make(owned):
        s = gs.GardenScene(settings=_Settings(owned))
        s.resize(900, 560)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()
        s.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _open(s):
    s._open_target = s._open_progress = 1.0


def _run(s, seconds, dt=0.06):
    """Step the haunt and return the states it passed through, in order."""
    seen = []
    for _ in range(int(seconds / dt)):
        s._update_ghost(dt)
        st = s._ghost["state"]
        if not seen or seen[-1] != st:
            seen.append(st)
    return seen


# ── the store item ───────────────────────────────────────────────────────

def _item():
    return next(c for c in emporium_catalog.CATALOG if c["id"] == gs.GHOST_ITEM)


def test_the_ghost_is_a_seasonal_decoration_that_needs_the_bookshelf():
    item = _item()
    assert item["category"] == "decorations" and item["kind"] == "furniture"
    assert item["requires"] == gs.GHOST_HOST == "deco_books"
    assert item["seasonal"] == "halloween"
    assert item["cost"] > 0


def test_his_store_picture_is_not_the_empty_still():
    """sPet_ItemGhost_0 is fully transparent (he is invisible at rest), so the
    store tile must use a frame where you can actually see him."""
    from PySide6.QtGui import QImage
    img = QImage(str(gs._garden_dir() / _item()["sprite"]))
    assert not img.isNull()
    assert any(img.pixelColor(x, y).alpha() > 0
               for y in range(img.height()) for x in range(img.width()))


def test_all_24_frames_ship():
    assert len(gs.GHOST_FRAMES) == 24
    for name in gs.GHOST_FRAMES:
        assert (gs._garden_dir() / name).is_file(), name


class _Page:
    """Just enough of EmporiumPage to exercise _item_available."""
    from techdeck.ui.pages.emporium_page import EmporiumPage
    _item_available = EmporiumPage._item_available

    def __init__(self, owned):
        self.settings = _Settings(owned)


@pytest.mark.parametrize("season,owned,expected", [
    ("1", {"deco_books"}, True),            # in season, owns the shelf: on sale
    ("1", set(), False),                    # no shelf to hide behind: not sold
    ("0", {"deco_books"}, False),           # out of season: off the shelf
    ("0", {"deco_books", "deco_ghost"}, True),   # already bought: always shown
])
def test_when_the_store_sells_him(monkeypatch, season, owned, expected):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", season)
    monkeypatch.setattr("techdeck.core.constants.halloween_active",
                        lambda settings=None: season == "1")
    assert _Page(owned)._item_available(_item()) is expected


def test_the_owl_still_needs_a_full_tree(monkeypatch):
    """Widening 'requires' to item ids must not break the milestone kind."""
    owl = next(c for c in emporium_catalog.CATALOG if c["id"] == "deco_owl")
    page = _Page(set())
    assert page._item_available(owl) is True
    page.settings.get_tree_stage = lambda: 2
    assert page._item_available(owl) is False


# ── the haunt ────────────────────────────────────────────────────────────

def test_no_ghost_without_buying_him(scene):
    assert scene({"deco_books"})._ghost is None


def test_no_ghost_without_the_bookshelf(scene):
    assert scene({"deco_ghost"})._ghost is None


def test_the_shelf_slides_left_he_comes_out_and_it_slides_home(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost["t"] = 0.0
    assert _run(s, 12) == ["out", "show", "back", "idle"]
    assert s._ghost["slide"] == 0.0 and s._ghost["seen"]
    assert gs.GHOST_DELAY_S[0] <= s._ghost["t"] <= gs.GHOST_DELAY_S[1]


def test_he_only_shows_once_the_shelf_is_fully_out_of_the_way(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost["t"] = 0.0
    while s._ghost["state"] != "show":
        s._update_ghost(0.06)
        assert s._ghost["state"] in ("out", "show")
    assert s._ghost["slide"] == 1.0
    assert gs.GHOST_SHELF_SLIDE < 0                 # to the LEFT


def test_he_lingers_fully_out(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost.update(state="show", idx=gs.GHOST_PEAK_FRAME, wt=0.0,
                    hold=gs.GHOST_PEAK_HOLD_S)
    held = 0.0
    while s._ghost["idx"] == gs.GHOST_PEAK_FRAME:
        s._update_ghost(0.06)
        held += 0.06
    assert held >= gs.GHOST_PEAK_HOLD_S


def test_the_clock_only_runs_while_the_house_is_open(scene):
    s = scene({"deco_books", "deco_ghost"})
    s._ghost["t"] = 1.0
    assert _run(s, 5) == ["idle"]                   # closed: nothing to see
    assert s._ghost["t"] == 1.0
    _open(s)
    assert _run(s, 5)[:2] == ["idle", "out"]


def test_first_visit_is_soon_so_a_buyer_sees_what_he_bought(scene):
    s = scene({"deco_books", "deco_ghost"})
    assert gs.GHOST_FIRST_DELAY_S[0] <= s._ghost["t"] <= gs.GHOST_FIRST_DELAY_S[1]
    assert gs.GHOST_FIRST_DELAY_S[1] < gs.GHOST_DELAY_S[0]


def test_never_slides_the_shelf_out_from_under_buddy(scene):
    s = scene({"deco_books", "deco_ghost", "friend_buddy"})
    _open(s)
    s._ghost["t"] = 0.0
    shelf = s._rec_by_id("deco_books")
    s._buddy["goal"] = shelf                        # he is on his way to read
    assert _run(s, 3) == ["idle"]
    s._buddy["goal"] = None
    assert _run(s, 0.3) == ["out"]                  # the moment he is clear


def test_buddy_cannot_pick_the_shelf_mid_haunt(scene):
    s = scene({"deco_books", "deco_ghost", "friend_buddy"})
    shelf = s._rec_by_id("deco_books")
    assert s._can_use(shelf)
    s._ghost["state"] = "show"
    assert not s._can_use(shelf)
    assert shelf not in s._interactive_int()


def test_navigating_back_puts_the_shelf_home(scene):
    s = scene({"deco_books", "deco_ghost"})
    s._ghost.update(state="show", slide=1.0, idx=9)
    s._reset_ghost()
    assert s._ghost["state"] == "idle" and s._ghost["slide"] == 0.0


def test_it_really_draws_the_shelf_moved_and_the_ghost_in_the_gap(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    bx, by = gs.PLACEMENT["deco_books"]
    home = s._compose_native().toImage()
    s._ghost.update(state="show", slide=1.0, idx=gs.GHOST_PEAK_FRAME)
    out = s._compose_native().toImage()
    # the ghost's pale body now shows where the shelf used to stand
    gap = [out.pixelColor(x, by + 16) for x in range(bx, bx + 12)]
    assert any(c.red() > 150 and c.green() > 150 and c.blue() > 150 for c in gap)
    assert not any(home.pixelColor(x, by + 16).red() > 150
                   and home.pixelColor(x, by + 16).green() > 150
                   for x in range(bx, bx + 12))
    # and the shelf itself has moved 16 px left
    assert out.pixelColor(bx - 12, by + 10) == home.pixelColor(bx + 4, by + 10)


def test_he_fades_into_the_cut_instead_of_being_sliced(scene):
    s = scene({"deco_books", "deco_ghost"})
    img = s._ghost["frames"][0].toImage()           # frame 0: hard against the cut
    w = img.width()
    ys = [y for y in range(img.height()) if img.pixelColor(w - 8, y).alpha() == 255]
    assert ys
    y = ys[len(ys) // 2]
    alphas = [img.pixelColor(x, y).alpha() for x in range(w - 6, w)]
    assert alphas[-1] < alphas[-2] < alphas[-3] < 255
    assert alphas[0] == 255
