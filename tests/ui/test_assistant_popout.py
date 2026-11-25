"""The Assistant, popped out (asked for 2026-10-29, built 2026-11-20).

*"Is it possible to have Assistant pop out in a different window? Sometimes I
would like to have it visible, while also being able to run my apps."*

What was built is a panel INSIDE the TechDeck window: a Pop out button lifts the
Assistant's body off its page into a small panel that floats over whatever page
is showing, drags by its title bar, resizes from any edge, and snaps to any of
the four edges of the page area - where the page beside it makes room.

These tests drive the real panel and the real Assistant page inside a stand-in
for the shell's layout (a sidebar, a page stack in a nested layout). The drag
and resize paths are driven through the same methods the mouse handlers call,
with GLOBAL positions, because the title bar moves with the panel and positions
relative to it compound.
"""

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QStackedWidget, QWidget,
)

from techdeck.ui.widgets import assistant_popout as popout_module
from techdeck.ui.widgets.assistant_popout import (
    EDGE_BOTTOM, EDGE_LEFT, EDGE_NONE, EDGE_RIGHT, EDGE_TOP, MIN_H, MIN_W,
    AssistantPopout,
)

SIDEBAR_W = 200
HOST_W, HOST_H = 1200, 800


class _Page(QWidget):
    """A page with a minimum width the test controls."""

    def __init__(self, min_w=300, min_h=200):
        super().__init__()
        self._min = QSize(min_w, min_h)

    def minimumSizeHint(self):
        return self._min

    def sizeHint(self):
        return self._min


@pytest.fixture
def rig(qapp):
    """host[ sidebar | page_area[ page_stack ] ] + the panel, like the shell."""
    host = QWidget()
    main = QHBoxLayout(host)
    main.setContentsMargins(0, 0, 0, 0)
    main.setSpacing(0)
    sidebar = QWidget()
    sidebar.setFixedWidth(SIDEBAR_W)
    main.addWidget(sidebar)
    stack = QStackedWidget()
    home, other = _Page(), _Page()
    stack.addWidget(home)
    stack.addWidget(other)
    # Exactly as the shell does, and BEFORE the panel exists: a hidden page
    # must not floor the window's minimum, and the panel's own page-change
    # hook has to run after this one has restored the new page's real minimum.
    from techdeck.ui.utils import limit_min_size_to_current_page
    limit_min_size_to_current_page(stack)
    area = QHBoxLayout()
    area.setContentsMargins(0, 0, 0, 0)
    area.addWidget(stack)
    main.addLayout(area, 1)
    panel = AssistantPopout(
        host, area, stack,
        bounds_fn=lambda: host.rect().adjusted(sidebar.width(), 0, 0, 0),
        watch=[sidebar])
    host.resize(HOST_W, HOST_H)
    host.show()
    qapp.processEvents()

    class Rig:
        pass

    r = Rig()
    r.host, r.sidebar, r.stack, r.area, r.panel, r.home, r.other = (
        host, sidebar, stack, area, panel, home, other)
    r.body = QLabel("the assistant")
    r.app = qapp
    yield r
    host.close()


def _out(rig, state=None):
    if state is not None:
        rig.panel.restore_state(state)
    rig.panel.pop_out(rig.body)
    rig.app.processEvents()


def _drag(rig, dx, dy, steps=6):
    """Drag the panel by its title bar, in global coordinates."""
    panel = rig.panel
    origin = panel._bar.mapToGlobal(QPoint(60, 12))
    panel._begin_drag(origin)
    for i in range(1, steps + 1):
        panel._drag_to(origin + QPoint(dx * i // steps, dy * i // steps))
        rig.app.processEvents()
    panel._end_drag()
    rig.app.processEvents()


def _margins(rig):
    m = rig.area.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


FLOATING = {"edge": "", "x": 300, "y": 200, "w": 400, "h": 420}


# ── popping out and back ────────────────────────────────────────────────────

def test_it_starts_hidden_and_holds_nothing(rig):
    assert not rig.panel.isVisible()
    assert not rig.panel.is_out()


def test_popping_out_shows_the_body_inside_the_page_area(rig):
    _out(rig)
    assert rig.panel.is_out() and rig.panel.isVisible()
    assert rig.body.parentWidget() is rig.panel
    assert rig.panel.bounds().contains(rig.panel.geometry())
    assert rig.panel.geometry().left() >= SIDEBAR_W, "it must never cover the sidebar"


def test_popping_in_hands_the_same_body_back_and_frees_the_page(rig):
    _out(rig, {"edge": "right", "dock_w": 400})
    assert rig.panel.is_reserving()
    body = rig.panel.pop_in()
    assert body is rig.body, "one Assistant, moved - never a second copy"
    assert not rig.panel.isVisible() and not rig.panel.is_out()
    assert _margins(rig) == (0, 0, 0, 0), "a hidden panel must not keep its strip"


def test_it_floats_above_every_page(rig):
    """It belongs to the HOST, not to a page, so changing page cannot hide it."""
    _out(rig, FLOATING)
    rig.stack.setCurrentWidget(rig.other)
    rig.app.processEvents()
    assert rig.panel.isVisible()
    assert rig.panel.parentWidget() is rig.host
    assert rig.host.children().index(rig.panel) > rig.host.children().index(rig.stack)


# ── dragging ─────────────────────────────────────────────────────────────────

def test_a_drag_moves_it_and_keeps_its_size(rig):
    _out(rig, FLOATING)
    before = rig.panel.geometry()
    _drag(rig, 120, 80)
    after = rig.panel.geometry()
    assert after.topLeft() == before.topLeft() + QPoint(120, 80)
    assert after.size() == before.size()
    assert rig.panel.edge() == EDGE_NONE


def test_a_click_on_the_bar_that_does_not_travel_is_not_a_drag(rig):
    _out(rig, FLOATING)
    settled = []
    rig.panel.geometry_settled.connect(lambda: settled.append(1))
    before = rig.panel.geometry()
    _drag(rig, 2, 1)
    assert rig.panel.geometry() == before and not settled


@pytest.mark.parametrize("dx,dy", [(5000, 0), (-5000, 0), (0, 5000), (0, -5000)])
def test_it_cannot_be_dragged_out_of_the_page_area(rig, dx, dy):
    _out(rig, FLOATING)
    panel = rig.panel
    origin = panel._bar.mapToGlobal(QPoint(60, 12))
    panel._begin_drag(origin)
    panel._drag_to(origin + QPoint(dx, dy))
    assert panel.bounds().contains(panel.geometry())
    panel._end_drag()


# ── snapping to the four edges ───────────────────────────────────────────────

@pytest.mark.parametrize("dx,dy,edge", [
    (5000, 0, EDGE_RIGHT), (-5000, 0, EDGE_LEFT),
    (0, 5000, EDGE_BOTTOM), (0, -5000, EDGE_TOP),
])
def test_dragged_against_an_edge_it_docks_there_and_fills_it(rig, dx, dy, edge):
    _out(rig, FLOATING)
    _drag(rig, dx, dy)
    panel, bounds = rig.panel, rig.panel.bounds()
    geom = panel.geometry()
    assert panel.edge() == edge
    if edge in (EDGE_LEFT, EDGE_RIGHT):
        assert geom.top() == bounds.top() and geom.height() == bounds.height()
        assert (geom.left() == bounds.left() if edge == EDGE_LEFT
                else geom.right() == bounds.right())
    else:
        assert geom.left() == bounds.left() and geom.width() == bounds.width()
        assert (geom.top() == bounds.top() if edge == EDGE_TOP
                else geom.bottom() == bounds.bottom())


def test_the_preview_shows_where_it_will_dock_and_goes_away(rig):
    _out(rig, FLOATING)
    panel = rig.panel
    origin = panel._bar.mapToGlobal(QPoint(60, 12))
    panel._begin_drag(origin)
    panel._drag_to(origin + QPoint(5000, 0))
    assert panel._ghost.isVisible()
    assert panel._ghost.geometry().height() == panel.bounds().height()
    panel._drag_to(origin + QPoint(100, 0))
    assert not panel._ghost.isVisible(), "away from the edge, no preview"
    panel._end_drag()
    assert not panel._ghost.isVisible()


def test_a_docked_panel_makes_the_page_reflow_instead_of_covering_it(rig):
    _out(rig, FLOATING)
    _drag(rig, 5000, 0)
    assert rig.panel.is_reserving()
    assert _margins(rig) == (0, 0, rig.panel.width(), 0)
    rig.app.processEvents()
    assert rig.stack.geometry().right() < rig.panel.geometry().left()


def test_a_page_with_no_room_to_spare_is_overlaid_not_squeezed(rig):
    """Reserving the strip would push the page under its minimum and Qt would
    grow the WINDOW to pay for it. The panel docks over the page instead."""
    rig.home._min = QSize(HOST_W - SIDEBAR_W - 100, 200)     # 100px to spare
    _out(rig, FLOATING)
    _drag(rig, 5000, 0)
    assert rig.panel.edge() == EDGE_RIGHT
    assert not rig.panel.is_reserving()
    assert _margins(rig) == (0, 0, 0, 0)
    assert rig.panel.geometry().right() == rig.panel.bounds().right()


def test_a_docked_panel_never_takes_more_than_its_share(rig):
    _out(rig, {"edge": "right", "dock_w": 5000})
    cap = int(rig.panel.bounds().width() * popout_module.MAX_DOCK_FRACTION)
    assert rig.panel.width() <= cap


def test_changing_page_rechecks_whether_the_page_can_spare_the_strip(rig):
    """...and the WINDOW must not grow to pay for both. A page that needs
    nearly the whole area, arriving beside a reserved strip, would push the
    window's minimum past its width; the strip is given back first."""
    rig.other._min = QSize(HOST_W - SIDEBAR_W - 50, 200)
    _out(rig, {"edge": "right", "dock_w": 400})
    assert rig.panel.is_reserving()
    rig.stack.setCurrentWidget(rig.other)
    rig.app.processEvents()
    assert not rig.panel.is_reserving(), "the wide page gets its width back"
    assert rig.host.width() == HOST_W, "the window grew to fit page + strip"
    rig.stack.setCurrentWidget(rig.home)
    rig.app.processEvents()
    assert rig.panel.is_reserving()
    assert rig.host.width() == HOST_W


def test_dragging_off_a_dock_goes_back_to_the_floating_size(rig):
    _out(rig, FLOATING)
    _drag(rig, 5000, 0)
    assert rig.panel.edge() == EDGE_RIGHT
    _drag(rig, -300, 150)
    assert rig.panel.edge() == EDGE_NONE
    assert rig.panel.size() == QSize(FLOATING["w"], FLOATING["h"])
    assert _margins(rig) == (0, 0, 0, 0)


def test_undocking_does_not_collapse_the_panel(rig):
    """The page area is NOT read off the layout. QLayout.geometry() goes empty
    the moment the layout is invalidated - which is what changing the reserved
    margins does - and a panel sized against an empty rect drops to its
    minimum in the middle of the drag (it did, 2026-11-20)."""
    _out(rig, FLOATING)
    _drag(rig, 5000, 0)
    panel = rig.panel
    origin = panel._bar.mapToGlobal(QPoint(60, 12))
    panel._begin_drag(origin)
    panel._drag_to(origin + QPoint(-200, 100))     # margins change right here
    assert panel.bounds().width() == HOST_W - SIDEBAR_W
    assert panel.size() == QSize(FLOATING["w"], FLOATING["h"])
    panel._end_drag()


# ── the window changing under it ─────────────────────────────────────────────

def test_a_docked_panel_follows_the_window(rig):
    _out(rig, {"edge": "bottom", "dock_h": 300})
    rig.host.resize(1000, 640)
    rig.app.processEvents()
    geom, bounds = rig.panel.geometry(), rig.panel.bounds()
    assert geom.bottom() == bounds.bottom() and geom.width() == bounds.width()


def test_a_floating_panel_is_pulled_back_inside_a_smaller_window(rig):
    _out(rig, {"edge": "", "x": 580, "y": 360, "w": 400, "h": 420})
    rig.host.resize(900, 600)
    rig.app.processEvents()
    assert rig.panel.bounds().contains(rig.panel.geometry())


def test_and_goes_back_where_it_was_when_the_window_grows_again(rig):
    """The clamp is not written back over the place the user chose."""
    _out(rig, {"edge": "", "x": 580, "y": 360, "w": 400, "h": 420})
    home = rig.panel.geometry()
    rig.host.resize(900, 600)
    rig.app.processEvents()
    rig.host.resize(HOST_W, HOST_H)
    rig.app.processEvents()
    assert rig.panel.geometry() == home


def test_the_sidebar_collapsing_moves_the_page_area_under_it(rig):
    _out(rig, {"edge": "left", "dock_w": 400})
    assert rig.panel.geometry().left() == SIDEBAR_W
    rig.sidebar.setFixedWidth(50)
    rig.app.processEvents()
    assert rig.panel.geometry().left() == 50


# ── resizing ─────────────────────────────────────────────────────────────────

def test_floating_every_border_and_corner_resizes(rig):
    _out(rig, FLOATING)
    panel = rig.panel
    w, h = panel.width(), panel.height()
    assert panel._hit_edges(QPoint(2, h // 2)) == "l"
    assert panel._hit_edges(QPoint(w - 2, h // 2)) == "r"
    assert panel._hit_edges(QPoint(w // 2, 2)) == "t"
    assert panel._hit_edges(QPoint(w // 2, h - 2)) == "b"
    assert panel._hit_edges(QPoint(w - 2, h - 2)) == "rb"
    assert panel._hit_edges(QPoint(w // 2, h // 2)) == ""


@pytest.mark.parametrize("edge,inner", [
    (EDGE_RIGHT, "l"), (EDGE_LEFT, "r"), (EDGE_TOP, "b"), (EDGE_BOTTOM, "t")])
def test_docked_only_the_border_facing_the_page_resizes(rig, edge, inner):
    _out(rig, {"edge": edge})
    panel = rig.panel
    w, h = panel.width(), panel.height()
    spots = {"l": QPoint(2, h // 2), "r": QPoint(w - 2, h // 2),
             "t": QPoint(w // 2, 2), "b": QPoint(w // 2, h - 2)}
    for name, spot in spots.items():
        assert panel._hit_edges(spot) == (inner if name == inner else "")


def _resize(rig, hit, dx, dy):
    panel = rig.panel
    panel._resize_edges = hit
    panel._resize_origin = QPoint(0, 0)
    panel._resize_start = QRect(panel.geometry())
    panel._resize_to(QPoint(dx, dy))
    rig.app.processEvents()


def test_a_resize_stops_at_the_minimum(rig):
    _out(rig, FLOATING)
    _resize(rig, "rb", -5000, -5000)
    assert rig.panel.size() == QSize(MIN_W, MIN_H)


def test_a_resize_stops_at_the_page_area(rig):
    _out(rig, FLOATING)
    _resize(rig, "rb", 5000, 5000)
    assert rig.panel.bounds().contains(rig.panel.geometry())


def test_resizing_a_docked_panel_changes_how_thick_the_dock_is(rig):
    _out(rig, {"edge": "right", "dock_w": 400})
    _resize(rig, "l", -100, 0)
    assert rig.panel.width() == 500
    assert rig.panel.geometry().right() == rig.panel.bounds().right()
    assert _margins(rig) == (0, 0, 500, 0), "the page gives up the wider strip"


# ── the tab showing decides how narrow it may be ─────────────────────────────

def test_a_tab_that_needs_more_room_widens_the_panel(rig):
    """Schedule's row of buttons needs ~860px. Squeezed into 400, Qt clips
    every label to a letter or two; the panel grows instead."""
    _out(rig, FLOATING)
    rig.panel.set_content_minimum(700)
    assert rig.panel.width() >= 700
    assert rig.panel.bounds().contains(rig.panel.geometry())


def test_and_narrows_again_for_a_tab_that_does_not(rig):
    """The width the user chose is kept apart from the width being shown."""
    _out(rig, FLOATING)
    home = rig.panel.geometry()
    rig.panel.set_content_minimum(700)
    rig.panel.set_content_minimum(250)
    assert rig.panel.geometry() == home
    assert rig.panel.state()["w"] == FLOATING["w"]


def test_a_tab_cannot_ask_for_more_than_the_page_area(rig):
    _out(rig, FLOATING)
    rig.panel.set_content_minimum(99999)
    assert rig.panel.width() == rig.panel.bounds().width()


# ── remembering where it was ─────────────────────────────────────────────────

def test_its_place_survives_a_round_trip(rig):
    _out(rig, FLOATING)
    _drag(rig, 5000, 0)
    saved = rig.panel.state()
    rig.panel.pop_in()
    rig.panel.restore_state(saved)
    _out(rig)
    assert rig.panel.edge() == EDGE_RIGHT
    assert rig.panel.state() == saved


@pytest.mark.parametrize("junk", [
    None, "nonsense", [], {"edge": "diagonal"}, {"w": "wide", "h": None},
    {"x": -9999, "y": -9999, "w": 99999, "h": 99999}, {"w": 3, "h": 3},
])
def test_a_bad_saved_state_cannot_put_it_off_screen(rig, junk):
    rig.panel.restore_state(junk)
    _out(rig)
    assert rig.panel.edge() in (EDGE_NONE, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM)
    assert rig.panel.bounds().contains(rig.panel.geometry())
    assert rig.panel.width() >= MIN_W and rig.panel.height() >= MIN_H


def test_settings_keep_the_panels_place(qapp):
    from techdeck.core.settings import SettingsManager
    settings = SettingsManager()
    assert settings.get_assistant_popout() == {}
    settings.set_assistant_popout({"edge": "right", "dock_w": 420})
    assert SettingsManager().get_assistant_popout() == {"edge": "right", "dock_w": 420}


# ── the theme ────────────────────────────────────────────────────────────────

def test_the_panel_wears_the_assistants_own_theme(rig):
    """Re-parented into the panel, the body is no longer under the page, so
    the panel has to carry the scoped stylesheet itself."""
    from techdeck.ui.theme_manager import SCOPE_ASSISTANT, get_theme_manager
    assert AssistantPopout.THEME_SCOPE == SCOPE_ASSISTANT
    manager = get_theme_manager()
    try:
        manager.set_scope_theme(SCOPE_ASSISTANT, "light")
        rig.app.processEvents()
        assert manager.scope_stylesheet(SCOPE_ASSISTANT)
        assert rig.panel.styleSheet().startswith(
            manager.scope_stylesheet(SCOPE_ASSISTANT))
    finally:
        manager.set_scope_theme(SCOPE_ASSISTANT, "")


# ── the Assistant page's half ────────────────────────────────────────────────

@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    import techdeck.core.assistant.store as store_module
    original = store_module.AssistantStore.__init__
    monkeypatch.setattr(
        store_module.AssistantStore, "__init__",
        lambda self, base_dir=None: original(self, tmp_path / "assistant"))
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.assistant_page import AssistantPage
    built = AssistantPage(SettingsManager())
    built.REPLY_DELAY_MS = 0
    return built


def test_the_page_has_a_pop_out_button_that_only_asks(page):
    asked = []
    page.pop_out_requested.connect(lambda: asked.append(1))
    page.pop_out_btn.click()
    assert asked == [1]
    assert not page.is_popped_out(), "the shell does the moving, not the button"


def test_releasing_the_body_leaves_a_note_and_goes_compact(page):
    page.show()
    body = page.release_body()
    assert body is page.body and page.is_popped_out()
    assert not page.away_note.isHidden()
    for hidden in (page.title, page.subtitle, page.reminders_btn,
                   page.pop_out_btn, page.chips):
        assert hidden.isHidden()
    for kept in (page.tabs, page.panel, page.command_line):
        assert not kept.isHidden()


def test_reclaiming_it_puts_the_page_back_exactly(page):
    page.show()
    page.release_body()
    page.reclaim_body()
    assert not page.is_popped_out()
    assert page.body.parentWidget() is page
    assert page.away_note.isHidden()
    for shown in (page.title, page.subtitle, page.reminders_btn,
                  page.pop_out_btn, page.chips):
        assert not shown.isHidden()
    margins = page._body_box.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) \
        == page._PAGE_MARGINS


def test_the_tabs_shorten_only_while_it_is_out(page):
    from techdeck.ui.pages.assistant_page import TAB_NOTES
    button = page.tabs._buttons[TAB_NOTES]
    assert button.text() == "Personal Notes"
    page.release_body()
    assert button.text() == "Notes"
    page.reclaim_body()
    assert button.text() == "Personal Notes"


def test_typing_in_the_popped_out_body_reaches_the_same_store(page):
    page.release_body()
    page.submit("/task order the 4130 tube 30m")
    assert [t.title for t in page.store.open_tasks()] == ["order the 4130 tube"]
    page.reclaim_body()
    assert "order the 4130 tube" in page.terminal.toPlainText()


def test_the_width_a_tab_needs_is_read_fresh_on_the_tab_change(page):
    """Asked the instant a tab changes, Qt still answers for the LAST tab
    unless the cached sizes up the parent chain are dropped by hand."""
    from techdeck.ui.pages.assistant_page import TAB_SCHEDULE, TAB_TERMINAL
    page.release_body()
    page.body.resize(400, 440)
    page.body.show()
    seen = []
    page.compact_width_changed.connect(
        lambda: seen.append((page.tabs.current(), page.compact_min_width())))
    page._show_tab(TAB_SCHEDULE)
    page._show_tab(TAB_TERMINAL)
    widths = dict(seen)
    assert widths[TAB_SCHEDULE] > widths[TAB_TERMINAL] + 200, seen


def test_a_reminder_click_does_not_navigate_away_while_popped_out(page):
    """Going to the Assistant page would show the 'popped out' note instead of
    the schedule the reminder was about."""
    import inspect
    src = inspect.getsource(page._on_notification_clicked)
    assert "not self._popped_out" in src


# ── the shell's half, pinned at the source ───────────────────────────────────

def test_the_shell_wires_the_panel_to_the_page_area_not_the_layouts_rect():
    import inspect
    from techdeck.ui import shell
    src = inspect.getsource(shell.MainWindow)
    assert "self.page_area = QHBoxLayout()" in src
    assert "main_layout.addLayout(self.page_area, 1)" in src
    assert "bounds_fn=lambda: central.rect().adjusted(" in src
    assert "watch=[self.sidebar]" in src
    # The panel re-checks the page's minimum on every page change, and that
    # check must run AFTER limit_min_size_to_current_page has restored the new
    # page's real size policy - signals fire in connection order.
    assert (src.index("limit_min_size_to_current_page(self.page_stack)")
            < src.index("AssistantPopout("))
    for wired in ("pop_out_requested.connect(self._pop_out_assistant)",
                  "pop_in_requested.connect(self._pop_in_assistant)",
                  "geometry_settled.connect(self._save_popout_state)",
                  "compact_width_changed.connect("):
        assert wired in src, wired
