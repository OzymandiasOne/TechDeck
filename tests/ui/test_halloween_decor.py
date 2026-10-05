"""Corner cobwebs + the one-at-a-time crawlies (widgets/halloween_decor.py)."""
import math
import random

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QWidget

from techdeck.ui.widgets import halloween_decor as hd


class _Settings:
    def __init__(self, theme="halloween", professional=False):
        self._theme, self._pro = theme, professional

    def get_theme(self):
        return self._theme

    def is_professional(self):
        return self._pro


@pytest.fixture
def host(qapp):
    w = QWidget()
    w.resize(1000, 700)
    w.show()
    yield w
    # Free the Qt objects NOW, while the QApplication still exists. Left to
    # the garbage collector they can outlive it and corrupt the heap at exit.
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def season(monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")


def _decor(host, settings=None, seed=7):
    return hd.HalloweenDecor(host, settings=settings or _Settings(),
                             rng=random.Random(seed))


def _run_out(critter, dt=1 / 60, limit=6000):
    n = 0
    while not critter._gone:
        critter.advance(dt)
        n += 1
        assert n < limit, "the crawly never left the window"
    return n


# ── the gate ─────────────────────────────────────────────────────────────

def test_gate_needs_the_season_and_the_halloween_theme(monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    assert hd.decor_active(_Settings()) is True
    assert hd.decor_active(_Settings(theme="dark")) is False
    assert hd.decor_active(_Settings(professional=True)) is False
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    assert hd.decor_active(_Settings()) is False


def test_out_of_season_there_is_nothing_at_all(host, monkeypatch):
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    decor = _decor(host)
    decor.refresh()
    assert decor._webs == []
    assert not decor._clock.isActive()
    assert host.findChildren(hd.CornerWeb) == []


# ── cobwebs ──────────────────────────────────────────────────────────────

def test_two_webs_small_top_right_large_bottom_left(host, season):
    decor = _decor(host)
    decor.refresh()
    webs = {w.corner: w for w in decor._webs}
    assert set(webs) == {"tr", "bl"}
    small, large = webs["tr"], webs["bl"]
    assert small.width() < large.width() and small.height() < large.height()
    assert small.geometry().right() == host.width() - 1 and small.y() == 0
    assert large.x() == 0 and large.geometry().bottom() == host.height() - 1


def test_webs_are_click_through_and_follow_a_resize(host, season):
    decor = _decor(host)
    decor.refresh()
    for web in decor._webs:
        assert web.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    host.resize(1300, 900)
    for web in decor._webs:
        web.place()
    webs = {w.corner: w for w in decor._webs}
    assert webs["tr"].geometry().right() == 1299
    assert webs["bl"].geometry().bottom() == 899


@pytest.mark.parametrize("corner", ["tr", "bl"])
def test_the_web_is_silk_in_its_own_corner_not_a_filled_box(qapp, corner):
    img = hd.render_web(160, corner).toImage()
    inked = [(x, y) for y in range(0, 160, 2) for x in range(0, 160, 2)
             if img.pixelColor(x, y).alpha() > 60]
    assert 80 < len(inked) < 0.35 * 80 * 80     # strands, not a slab
    near = (159, 0) if corner == "tr" else (0, 159)
    far = (0, 159) if corner == "tr" else (159, 0)
    dist = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    closer = sum(dist(p, near) < dist(p, far) for p in inked)
    assert closer > 0.8 * len(inked)


def test_the_top_right_web_is_a_true_quarter_circle(qapp):
    """Wall to wall (90 degrees) and the same radius all the way round."""
    size = hd.WEB_SMALL_PX
    img = hd.render_web(size, "tr", quarter=True).toImage()
    corner = (size - 1, 0)

    def farthest(lo, hi):
        """How far from the corner the silk reaches, within an angle band."""
        best = 0.0
        for y in range(size):
            for x in range(size):
                if img.pixelColor(x, y).alpha() < 90:
                    continue
                dx, dy = corner[0] - x, y - corner[1]
                ang = math.degrees(math.atan2(dy, dx))
                if lo <= ang < hi:
                    best = max(best, math.hypot(dx, dy))
        return best

    bands = [farthest(a, a + 15) for a in range(0, 90, 15)]
    # every 15-degree slice, INCLUDING the two against the walls, reaches
    # the rim: a full 90 degrees, one radius
    assert min(bands) > 0.90 * size
    assert max(bands) - min(bands) < 0.10 * size
    # the old kite, by contrast, is clearly shorter through the middle
    kite = hd.render_web(size, "tr", quarter=False).toImage()
    img = kite
    assert farthest(38, 52) < 0.90 * size


def test_only_the_top_right_web_is_the_quarter_circle(host, season):
    decor = _decor(host)
    decor.refresh()
    webs = {w.corner: w for w in decor._webs}
    assert webs["tr"].width() == hd.WEB_SMALL_PX        # radius unchanged
    assert (webs["tr"]._pix.toImage()
            == hd.render_web(hd.WEB_SMALL_PX, "tr", quarter=True).toImage())
    assert (webs["bl"]._pix.toImage()
            == hd.render_web(hd.WEB_LARGE_PX, "bl", quarter=False).toImage())


# ── one web per tab ──────────────────────────────────────────────────────

OTHER_TABS = ["library", "settings", "account", "assistant", "devkit"]


def _touches_border(web, host):
    g = web.geometry()
    return {"tl": g.left() == 0 and g.top() == 0,
            "tr": g.right() == host.width() - 1 and g.top() == 0,
            "bl": g.left() == 0 and g.bottom() == host.height() - 1,
            "br": (g.right() == host.width() - 1
                   and g.bottom() == host.height() - 1),
            "top": g.top() == 0,
            "bottom": g.bottom() == host.height() - 1,
            "left": g.left() == 0,
            "right": g.right() == host.width() - 1}[web.corner]


def test_home_keeps_its_approved_pair(host, season):
    decor = _decor(host)
    decor.refresh()
    assert decor.page() == "home"
    assert sorted(w.corner for w in decor._webs) == ["bl", "tr"]


@pytest.mark.parametrize("tab", OTHER_TABS)
def test_every_other_tab_wears_exactly_one_web_on_the_border(host, season, tab):
    decor = _decor(host)
    decor.refresh()
    decor.set_page(tab)
    assert len(decor._webs) == 1
    web = decor._webs[0]
    assert _touches_border(web, host)
    assert web.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    host.resize(1280, 860)                      # and it stays there
    web.place()
    assert _touches_border(web, host)


def test_no_two_tabs_put_their_web_in_the_same_place():
    spots = [(where, round(along, 2))
             for tab in OTHER_TABS
             for where, _size, along, _seed, _q in hd.WEB_LAYOUTS[tab]]
    assert len(set(spots)) == len(spots) == len(OTHER_TABS)
    home = {where for where, *_ in hd.WEB_LAYOUTS["home"]}
    assert not home & {where for where, _ in spots}
    # a real mix: corners AND webs hung off the middle of an edge
    assert {w for w, _ in spots} & set(hd.CORNERS)
    assert {w for w, _ in spots} & set(hd.EDGES)


def test_switching_tabs_swaps_the_webs_and_leaves_none_behind(host, season):
    decor = _decor(host)
    decor.refresh()
    for tab in OTHER_TABS + ["home"]:
        decor.set_page(tab)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        live = [w for w in host.findChildren(hd.CornerWeb) if w.isVisible()]
        assert len(live) == len(decor._webs) == len(hd.WEB_LAYOUTS[tab])


def test_a_tab_nobody_listed_still_gets_one_web(host, season):
    decor = _decor(host)
    decor.refresh()
    decor.set_page("page9")
    assert len(decor._webs) == 1 and _touches_border(decor._webs[0], host)


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_an_edge_web_hangs_off_its_border_as_a_half_circle(qapp, edge):
    r = 120
    img = hd.render_web(r, edge, 41).toImage()
    wide = edge in ("top", "bottom")
    assert (img.width(), img.height()) == ((2 * r, r) if wide else (r, 2 * r))
    anchor = {"top": (r, 0), "bottom": (r, r - 1),
              "left": (0, r), "right": (r - 1, r)}[edge]
    inked = [(x, y) for y in range(0, img.height(), 2)
             for x in range(0, img.width(), 2)
             if img.pixelColor(x, y).alpha() > 60]
    assert len(inked) > 120
    far = max(math.hypot(x - anchor[0], y - anchor[1]) for x, y in inked)
    assert 0.7 * r < far <= 1.25 * r            # a fan of about that radius
    # silk on BOTH sides of the anchor: a half circle, not a quarter
    along = [(x - anchor[0]) if wide else (y - anchor[1]) for x, y in inked]
    assert min(along) < -0.5 * r and max(along) > 0.5 * r


def test_an_edge_web_sits_where_its_tab_says_along_the_edge(host, season):
    decor = _decor(host)
    decor.refresh()
    decor.set_page("settings")
    web = decor._webs[0]
    where, _size, along, _seed, _q = hd.WEB_LAYOUTS["settings"][0]
    assert where == "top"
    centre = web.geometry().center().x()
    assert centre == pytest.approx(along * host.width(), abs=2)


def test_changing_tab_never_touches_the_crawly_clock(host, season):
    decor = _decor(host)
    decor.refresh()
    left = decor._clock.remainingTime()
    critter = decor.spawn("spider", dangle=False)
    critter._timer.stop()
    decor.set_page("library")
    assert decor.current() is critter           # still out, still the only one
    assert not critter._gone
    decor.set_page("home")
    assert decor.current() is critter
    assert left > 0


def test_webs_are_drawn_once_not_on_every_tab_switch(host, season, monkeypatch):
    calls = []
    real = hd.render_web
    monkeypatch.setattr(hd, "_WEB_CACHE", {})
    monkeypatch.setattr(hd, "render_web",
                        lambda *a, **k: (calls.append(a), real(*a, **k))[1])
    decor = _decor(host)
    decor.refresh()
    for _ in range(3):
        for tab in OTHER_TABS + ["home"]:
            decor.set_page(tab)
    assert len(calls) == 2 + len(OTHER_TABS)


def test_the_webs_are_drawn_see_through(host, season):
    assert 0.4 <= hd.WEB_OPACITY < 1.0
    decor = _decor(host)
    decor.refresh()
    web = next(w for w in decor._webs if w.corner == "bl")
    drawn, shown = web._pix.toImage(), web.grab().toImage()
    peak = lambda img: max(img.pixelColor(x, y).alpha()
                           for y in range(0, img.height(), 3)
                           for x in range(0, img.width(), 3))
    assert peak(shown) < peak(drawn)
    assert peak(shown) == pytest.approx(peak(drawn) * hd.WEB_OPACITY, abs=6)


def test_leaving_the_halloween_theme_takes_it_all_down(host, season):
    settings = _Settings()
    decor = _decor(host, settings)
    decor.refresh()
    decor.spawn("spider", dangle=False)
    settings._theme = "dark"
    decor.refresh()
    assert decor._webs == [] and decor.current() is None
    assert not decor._clock.isActive()
    settings._theme = "halloween"
    decor.refresh()
    assert len(decor._webs) == 2 and decor._clock.isActive()


# ── the rendered clips ───────────────────────────────────────────────────

def test_the_spider_ships_with_its_walk_and_hang_clips(qapp):
    assert "spider" in hd.available_kinds()
    walk, hang = hd.load_clip("spider", "walk"), hd.load_clip("spider", "hang")
    assert walk is not None and len(walk.frames) == 16
    assert hang is not None and len(hang.frames) == 12
    assert walk.frames[0].width() == walk.size == 256
    assert walk.loop_travel_px > 0


def test_the_roach_ships_with_its_walk_clip(qapp):
    assert "roach" in hd.available_kinds()
    walk = hd.load_clip("roach", "walk")
    assert walk is not None and len(walk.frames) == 16
    assert walk.frames[0].width() == walk.size == 256
    # a longer stride than the spider's: it covers more ground per loop
    assert walk.loop_travel_px > hd.load_clip("spider", "walk").loop_travel_px


def test_the_roach_runs_and_is_the_fastest_thing_in_the_app(host, season):
    assert hd.KINDS["roach"].speed > hd.KINDS["spider"].speed
    critter = _decor(host).spawn("roach")
    assert critter is not None and critter.kind == "roach"
    critter._timer.stop()
    _run_out(critter)
    assert critter._entered


def test_only_a_spider_ever_dangles(host, season):
    roach = _decor(host).spawn("roach", dangle=True)
    assert roach is not None and roach.dangle is False


def test_never_the_same_kind_twice_running(host, season):
    decor = _decor(host, seed=3)
    seen = []
    for _ in range(10):
        critter = decor.spawn()
        seen.append(critter.kind)
        critter._timer.stop()
        critter.leave()
    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert set(seen) == set(hd.available_kinds())


def test_a_kind_with_no_frames_never_appears(host, season, monkeypatch, tmp_path):
    monkeypatch.setattr(hd, "_critter_dir", lambda: tmp_path)
    monkeypatch.setattr(hd, "_CLIPS", {})
    decor = _decor(host)
    assert hd.available_kinds() == []
    assert decor.spawn() is None and decor.spawn("spider") is None


def test_unknown_kind_is_refused(host, season):
    assert _decor(host).spawn("butterfly") is None


# ── crawlies ─────────────────────────────────────────────────────────────

def test_it_crosses_the_window_and_is_click_through(host, season):
    decor = _decor(host)
    critter = decor.spawn("spider", dangle=False)
    assert critter is not None and critter.kind == "spider"
    assert critter.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    critter._timer.stop()
    _run_out(critter)
    assert critter._entered
    assert decor.current() is None


def test_only_one_at_a_time(host, season):
    decor = _decor(host)
    first = decor.spawn("spider", dangle=False)
    assert decor.spawn("spider") is None
    assert decor.current() is first
    first._timer.stop()
    _run_out(first)
    assert decor.spawn("spider") is not None


def test_fast_and_sporadic(host, season):
    """Short violent darts, a new heading for each, freezes in between."""
    decor = _decor(host, seed=11)
    critter = decor.spawn("spider", dangle=False)
    critter._timer.stop()
    top, headings, freezes, darts = 0.0, set(), 0, 0
    was_moving = True
    while not critter._gone:
        critter.advance(1 / 60)
        top = max(top, critter._speed)
        if critter._moving != was_moving:
            freezes += (not critter._moving)
            darts += critter._moving
            was_moving = critter._moving
        if critter._moving:
            headings.add(round(critter._aim, 2))
    assert top > 450                        # it BOLTS
    assert freezes >= 2 and darts >= 2      # stop-start, not a glide
    assert len(headings) >= 3               # and never in one straight line


def test_every_seed_still_gets_out_of_the_window(host, season):
    for seed in range(12):
        decor = _decor(host, seed=seed)
        critter = decor.spawn("spider", dangle=False)
        critter._timer.stop()
        _run_out(critter)
        assert critter._age <= hd.MAX_TRIP_S + 0.1


def test_the_spider_is_three_quarters_size_and_no_slower(host, season):
    spec = hd.KINDS["spider"]
    assert spec.px == 96.0                  # 128 px, scaled down 25%
    assert spec.speed == 560.0              # size is NOT a speed knob
    critter = _decor(host).spawn("spider", dangle=False)
    critter._timer.stop()
    assert critter._px == 96.0
    assert critter._want == 560.0
    # a smaller sprite covers less ground per gait loop, so feet stay planted
    walk = hd.load_clip("spider", "walk")
    assert critter._loop_px == pytest.approx(walk.loop_travel_px * 96 / walk.size)


def test_legs_follow_the_ground_but_never_strobe(host, season):
    decor = _decor(host)
    critter = decor.spawn("spider", dangle=False)
    critter._timer.stop()
    n = len(critter._clip.frames)
    # a slow creep: exactly distance-driven, one loop per loop_travel_px
    critter._gait = 0.0
    critter._step_gait(critter._loop_px / 4, 1.0)
    assert critter._gait == pytest.approx(n / 4)
    # a sprint: capped, so the loop cannot alias against the refresh rate
    critter._gait = 0.0
    critter._step_gait(critter._loop_px * 3, 1 / 60)
    assert critter._gait == pytest.approx(hd.MAX_GAIT_FRAMES_PER_S / 60)


def test_the_clock_rearms_only_after_the_crawly_has_left(host, season):
    decor = _decor(host)
    decor.refresh()
    decor._clock.stop()
    decor._on_clock()
    critter = decor.current()
    assert critter is not None
    assert not decor._clock.isActive()      # no second visitor can be queued
    critter._timer.stop()
    _run_out(critter)
    assert decor._clock.isActive()


def test_visits_are_never_less_than_ten_minutes_apart(host, season):
    assert hd.EVERY_MS[0] >= 10 * 60 * 1000
    decor = _decor(host, seed=5)
    decor._first = False
    gaps = set()
    for _ in range(200):
        decor._arm()
        gaps.add(decor._clock.interval())
    decor._clock.stop()
    assert min(gaps) >= 10 * 60 * 1000
    assert len(gaps) > 50                   # but never on a learnable beat


def test_the_gap_is_measured_from_when_the_last_one_left(host, season):
    decor = _decor(host)
    decor.refresh()
    decor._clock.stop()
    critter = decor.spawn("spider", dangle=False)
    critter._timer.stop()
    _run_out(critter)
    assert decor._clock.isActive()
    assert decor._clock.interval() >= 10 * 60 * 1000


def test_never_two_at_once_whatever_asks(host, season):
    """The clock, a second clock tick, and /crawl all go through spawn()."""
    decor = _decor(host)
    decor.refresh()
    first = decor.spawn("spider", dangle=True)
    decor._on_clock()
    decor._on_clock()
    assert decor.spawn("spider", dangle=False) is None
    assert decor.current() is first
    assert len(host.findChildren(hd.Critter)) == 1


def test_no_visit_while_the_window_is_minimized(host, season):
    decor = _decor(host)
    decor.refresh()
    host.showMinimized()
    decor._on_clock()
    assert decor.current() is None
    assert decor._clock.isActive()          # it tries again later


def test_dangling_spider_drops_in_jerks_hangs_and_bolts_back_up(host, season):
    decor = _decor(host)
    spider = decor.spawn("spider", dangle=True)
    assert spider.dangle
    spider._timer.stop()
    stages, lowest, held, n, tops = [], 0, 0, 0, set()
    while not spider._gone:
        spider.advance(1 / 60)
        if not stages or stages[-1] != spider._stage:
            stages.append(spider._stage)
        held += spider._stage == "drop" and spider._hold > 0
        if spider._stage == "hang":
            tops.add(spider.y())
        lowest = max(lowest, spider.height())
        n += 1
        assert n < 6000
    assert stages == ["drop", "hang", "turn", "climb"]
    assert held > 0                          # it snatched at least once
    assert tops == {0}                       # the thread starts at the top edge
    assert 0.3 * host.height() < lowest < 0.85 * host.height()


def test_clear_sends_the_crawly_away_but_keeps_the_webs(host, season):
    decor = _decor(host)
    decor.refresh()
    decor.spawn("spider", dangle=False)
    decor.clear()
    assert decor.current() is None
    assert len(decor._webs) == 2


def test_it_paints_something(host, season):
    decor = _decor(host)
    critter = decor.spawn("spider", dangle=False)
    critter._timer.stop()
    for _ in range(40):
        critter.advance(1 / 60)
    img = critter.grab().toImage()
    assert any(img.pixelColor(x, y).alpha() > 0
               for y in range(0, img.height(), 4)
               for x in range(0, img.width(), 4))
