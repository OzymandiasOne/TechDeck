"""Corner cobwebs + the one-at-a-time crawlies (widgets/halloween_decor.py)."""
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


def _run_out(critter, dt=0.05, limit=4000):
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


def test_leaving_the_halloween_theme_takes_it_all_down(host, season):
    settings = _Settings()
    decor = _decor(host, settings)
    decor.refresh()
    decor.spawn("roach")
    settings._theme = "dark"
    decor.refresh()
    assert decor._webs == [] and decor.current() is None
    assert not decor._clock.isActive()
    settings._theme = "halloween"
    decor.refresh()
    assert len(decor._webs) == 2 and decor._clock.isActive()


# ── crawlies ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", sorted(hd.KINDS))
def test_every_kind_has_its_art_and_crosses_the_window(host, season, kind):
    decor = _decor(host)
    critter = decor.spawn(kind, dangle=False)
    assert critter is not None and critter.kind == kind
    assert len(critter._frames) == hd.KINDS[kind]["frames"]
    assert critter.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    critter._timer.stop()
    _run_out(critter)
    assert decor.current() is None


def test_only_one_at_a_time(host, season):
    decor = _decor(host)
    first = decor.spawn("spider", dangle=False)
    assert decor.spawn("roach") is None
    assert decor.current() is first
    first._timer.stop()
    _run_out(first)
    assert decor.spawn("roach") is not None


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
    assert hd.EVERY_MS[0] <= decor._clock.interval() <= hd.EVERY_MS[1]


def test_no_visit_while_the_window_is_minimized(host, season):
    decor = _decor(host)
    decor.refresh()
    host.showMinimized()
    decor._on_clock()
    assert decor.current() is None
    assert decor._clock.isActive()          # it tries again later


def test_variety_never_the_same_kind_twice_running(host, season):
    decor = _decor(host, seed=3)
    seen = []
    for _ in range(12):
        critter = decor.spawn()
        seen.append(critter.kind)
        critter._timer.stop()
        critter.leave()
    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert set(seen) == set(hd.KINDS)


def test_it_scurries_and_freezes_but_a_centipede_never_stops(host, season):
    decor = _decor(host)
    roach = decor.spawn("roach")
    roach._timer.stop()
    states = set()
    for _ in range(200):
        roach.advance(0.05)
        if roach._gone:
            break
        states.add(roach._moving)
    assert states == {True, False}
    roach.leave()
    centi = decor.spawn("centipede")
    centi._timer.stop()
    while not centi._gone:
        centi.advance(0.05)
        assert centi._moving or centi._gone


def test_the_sprite_faces_the_way_it_runs(host, season):
    decor = _decor(host)
    critter = decor.spawn("roach")       # roach art is taller than wide
    critter._timer.stop()
    tall = critter.height() > critter.width()
    assert tall == (critter.heading in ("up", "down"))


def test_dangling_spider_comes_down_hangs_and_climbs_back(host, season):
    decor = _decor(host)
    spider = decor.spawn("spider", dangle=True)
    assert spider.dangle and spider.x() >= 0
    spider._timer.stop()
    stages, lowest = [], 0
    n = 0
    while not spider._gone:
        spider.advance(0.05)
        if not stages or stages[-1] != spider._stage:
            stages.append(spider._stage)
        lowest = max(lowest, spider.height())
        n += 1
        assert n < 4000
    assert stages == ["drop", "hang", "climb"]
    assert spider.y() == 0                   # the thread starts at the top edge
    assert 0.3 * host.height() < lowest < 0.8 * host.height()


def test_only_a_spider_dangles(host, season):
    decor = _decor(host)
    roach = decor.spawn("roach", dangle=True)
    assert roach.dangle is False


def test_clear_sends_the_crawly_away_but_keeps_the_webs(host, season):
    decor = _decor(host)
    decor.refresh()
    decor.spawn("centipede")
    decor.clear()
    assert decor.current() is None
    assert len(decor._webs) == 2


def test_missing_art_means_no_crawly_not_a_crash(host, season, monkeypatch, tmp_path):
    monkeypatch.setattr(hd, "_critter_dir", lambda: tmp_path)
    decor = _decor(host)
    decor.refresh()
    assert decor._webs == []
    assert decor.spawn("spider") is None


def test_unknown_kind_is_refused(host, season):
    assert _decor(host).spawn("butterfly") is None
