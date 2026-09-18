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
