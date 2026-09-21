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


def test_his_house_sprite_is_the_small_hand_drawn_one():
    """~25% smaller than the 13x22 rip (his call: "he's really big"), REDRAWN
    rather than resampled so the dome and droopy eyes survive."""
    from techdeck.ui import pixel_art
    data = pixel_art.load(gs._garden_dir().parent / "sprites" / gs.GHOST_SPRITE)
    w, h = pixel_art.dimensions(data)
    assert (w, h) == (10, 17)
    assert 0.70 <= w / 13 <= 0.80 and 0.70 <= h / 22 <= 0.80
    rows = data["rows"]
    assert rows[0].count("B") < rows[1].count("B") <= rows[3].count("B") + 4
    # mirror-symmetric face: he must not look lopsided
    for r in rows:
        assert [c == "." for c in r] == [c == "." for c in r[::-1]]
        assert [c in "EK" for c in r] == [c in "EK" for c in r[::-1]]


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


def test_the_whole_haunt_in_order(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost["t"] = 0.0
    assert _run(s, 14) == ["out", "emerge", "linger", "retreat", "back", "idle"]
    assert s._ghost["slide"] == 0.0 and s._ghost["fade"] == 0 and s._ghost["seen"]
    assert gs.GHOST_DELAY_S[0] <= s._ghost["t"] <= gs.GHOST_DELAY_S[1]


def test_the_shelf_slides_to_the_right(scene):
    assert gs.GHOST_SHELF_SLIDE > 0
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    bx, by = gs.PLACEMENT["deco_books"]
    home = s._compose_native().toImage()
    s._ghost.update(state="emerge", slide=1.0, fade=0)
    moved = s._compose_native().toImage()
    d = gs.GHOST_SHELF_SLIDE
    for dx in (2, 8, 13):
        assert moved.pixelColor(bx + d + dx, by + 10) == home.pixelColor(bx + dx, by + 10)


# ── the hidden passage ───────────────────────────────────────────────────

def _shelf_black_bbox():
    """The black shadow inside the bookshelf sprite, measured from the art."""
    from PySide6.QtGui import QImage
    img = QImage(str(gs._garden_dir() / "sPet_ItemBooks_0.png"))
    pts = [(x, y) for y in range(img.height()) for x in range(img.width())
           if img.pixelColor(x, y).alpha() and img.pixelColor(x, y).rgb() & 0xFFFFFF == 0]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def test_the_passage_is_exactly_the_shelfs_black_shadow(scene):
    s = scene({"deco_books", "deco_ghost"})
    x0, y0, w, h = _shelf_black_bbox()
    assert (x0, y0) == (0, 0)
    pas = s._ghost["passage"]
    assert (pas.width(), pas.height()) == (w, h) == (16, 26)
    img = pas.toImage()
    assert all(img.pixelColor(x, y).alpha() == 255
               and img.pixelColor(x, y).rgb() & 0xFFFFFF == 0
               for y in range(h) for x in range(w))


def test_at_rest_the_passage_is_invisible_under_the_shelf(scene):
    """It overlaps the shelf's own black exactly, so owning the ghost must not
    change how the room looks until the shelf moves."""
    with_ghost = scene({"deco_books", "deco_ghost"})
    without = scene({"deco_books"})
    _open(with_ghost), _open(without)
    assert with_ghost._compose_native().toImage() == without._compose_native().toImage()


def test_the_passage_stays_put_and_is_uncovered_as_the_shelf_slides(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    shelf = s._rec_by_id("deco_books")
    bx, by = gs.PLACEMENT["deco_books"]
    rect = s._passage_rect(shelf)
    assert (rect.x(), rect.y()) == (bx, by)
    for slide in (0.0, 0.5, 1.0):
        s._ghost.update(state="out", slide=slide)
        assert s._passage_rect(shelf) == rect           # it NEVER moves
    s._ghost.update(state="emerge", slide=1.0, fade=0)
    img = s._compose_native().toImage()
    black = lambda c: c.alpha() == 255 and c.rgb() & 0xFFFFFF == 0
    assert all(black(img.pixelColor(x, y))
               for y in range(by, by + rect.height())
               for x in range(bx, bx + rect.width()))
    # ...and just below it the room's floor shows, not black
    assert not black(img.pixelColor(bx + 8, by + rect.height() + 2))


# ── the ghost in the passage ─────────────────────────────────────────────

def _pale(c):
    return c.red() > 120 and c.green() > 120 and c.blue() > 120


def test_his_bottom_sits_on_the_bottom_of_the_passage(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    shelf = s._rec_by_id("deco_books")
    rect = s._passage_rect(shelf)
    gx, gy = s._ghost_pos(shelf)
    pm = s._ghost["pm"]
    assert gy + pm.height() == rect.y() + rect.height()
    assert gx - rect.x() == rect.x() + rect.width() - (gx + pm.width())   # centred
    # and that is where he is really painted
    s._ghost.update(state="linger", slide=1.0, fade=len(gs.GHOST_FADE) - 1, age=0.0)
    img = s._compose_native().toImage()
    bottom = rect.y() + rect.height() - 1
    assert all(_pale(img.pixelColor(x, bottom)) for x in range(gx, gx + pm.width()))
    assert not any(_pale(img.pixelColor(x, bottom + 1))
                   for x in range(rect.x(), rect.x() + rect.width()))


def test_he_never_shows_outside_the_passage(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    shelf = s._rec_by_id("deco_books")
    rect = s._passage_rect(shelf)
    s._ghost.update(state="emerge", slide=1.0, fade=0)
    empty = s._compose_native().toImage()
    for age in (0.0, 0.3, 0.6, 0.9, 1.2):
        s._ghost.update(state="linger", fade=len(gs.GHOST_FADE) - 1, age=age)
        img = s._compose_native().toImage()
        changed = [(x, y) for y in range(img.height()) for x in range(img.width())
                   if img.pixelColor(x, y) != empty.pixelColor(x, y)]
        assert changed
        assert all(rect.contains(x, y) for x, y in changed)


def test_he_fades_in_out_of_the_dark_in_hard_steps(scene):
    assert gs.GHOST_FADE[0] == 0.0 and list(gs.GHOST_FADE) == sorted(gs.GHOST_FADE)
    assert 0.8 <= gs.GHOST_FADE[-1] < 1.0               # ghostly, never solid
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost.update(state="emerge", slide=1.0, fade=0, wt=0.0)
    levels = []
    while s._ghost["state"] == "emerge":
        s._update_ghost(0.03)
        if not levels or levels[-1] != s._ghost["fade"]:
            levels.append(s._ghost["fade"])
    assert levels == list(range(1, len(gs.GHOST_FADE)))
    # brighter at every step, in the actual pixels
    shelf = s._rec_by_id("deco_books")
    gx, gy = s._ghost_pos(shelf)
    seen = []
    for lvl in range(1, len(gs.GHOST_FADE)):
        s._ghost.update(state="emerge", fade=lvl)
        seen.append(s._compose_native().toImage().pixelColor(gx + 1, gy + 14).red())
    assert seen == sorted(seen) and len(set(seen)) == len(seen)


def test_he_only_appears_once_the_shelf_is_fully_aside(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost["t"] = 0.0
    while s._ghost["state"] != "emerge":
        s._update_ghost(0.06)
        assert s._ghost["fade"] == 0
    assert s._ghost["slide"] == 1.0


def test_he_is_gone_before_the_shelf_comes_home(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost.update(state="retreat", slide=1.0, fade=2, wt=0.0)
    while s._ghost["state"] == "retreat":
        s._update_ghost(0.03)
    assert s._ghost["state"] == "back" and s._ghost["fade"] == 0


def test_he_lingers_and_only_bobs_upward(scene):
    s = scene({"deco_books", "deco_ghost"})
    _open(s)
    s._ghost.update(state="linger", slide=1.0, fade=len(gs.GHOST_FADE) - 1,
                    hold=gs.GHOST_HOLD_S, age=0.0)
    held, repaints = 0.0, 0
    while s._ghost["state"] == "linger":
        repaints += bool(s._update_ghost(0.06))
        held += 0.06
    assert held >= gs.GHOST_HOLD_S and repaints > 10


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


def test_never_moves_the_shelf_while_buddy_is_using_it(scene):
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
    s._ghost["state"] = "linger"
    assert not s._can_use(shelf)
    assert shelf not in s._interactive_int()


def test_navigating_back_puts_the_shelf_home(scene):
    s = scene({"deco_books", "deco_ghost"})
    s._ghost.update(state="linger", slide=1.0, fade=4)
    s._reset_ghost()
    assert s._ghost["state"] == "idle" and s._ghost["slide"] == 0.0
    assert s._ghost["fade"] == 0
