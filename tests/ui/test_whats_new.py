"""The NEW! stickers: where they show, when they clear, the cartridge's "?",
and Woogy's answer about the cursed thing."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from techdeck.core import constants
from techdeck.core.settings import SettingsManager
from techdeck.ui import whats_new as wn


def _on(monkeypatch):
    monkeypatch.delenv("TECHDECK_PUPPET_MASTER", raising=False)
    monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", True)
    monkeypatch.setattr(constants, "halloween_active", lambda settings=None: True)
    monkeypatch.setattr(wn, "halloween_active", lambda settings=None: True)


def test_stickers_show_then_clear_one_by_one(tmp_path, monkeypatch):
    _on(monkeypatch)
    s = SettingsManager(settings_dir=tmp_path)
    assert wn.new_badges(s) == {wn.ACCOUNT, wn.MY_STUFF, wn.PUPPET, wn.DECORATIONS, wn.GHOST}
    s.mark_my_stuff_seen()                                   # My Stuff opened: only the sidebar's goes
    assert wn.new_badges(s) == {wn.MY_STUFF, wn.PUPPET, wn.DECORATIONS, wn.GHOST}
    s.unlock_item(wn.GHOST_ID)                               # the Ghost bought: its tab and tile clear
    assert wn.new_badges(s) == {wn.MY_STUFF, wn.PUPPET}
    s.unlock_item(wn.PUPPET_ID)                              # the table played: all gone
    assert wn.new_badges(s) == set()


def test_nothing_is_new_while_the_features_are_off(tmp_path, monkeypatch):
    monkeypatch.delenv("TECHDECK_PUPPET_MASTER", raising=False)
    monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", False)
    monkeypatch.setattr(wn, "halloween_active", lambda settings=None: False)
    assert wn.new_badges(SettingsManager(settings_dir=tmp_path)) == set()


def test_the_cartridge_asks_with_a_question_mark(qapp, tmp_path, monkeypatch):
    _on(monkeypatch)
    from techdeck.ui.pages.mystuff_page import MyStuffPage
    from techdeck.ui import arcade_chrome
    shown = []
    monkeypatch.setattr(arcade_chrome.PixelDialog, "show_message",
                        classmethod(lambda cls, parent, title, body, ok_label="OK": shown.append((title, body))))
    page = MyStuffPage(SettingsManager(settings_dir=tmp_path))
    tile = next(t for t in page.tiles if t.item["id"] == wn.PUPPET_ID)
    assert tile.locked and tile.action_btn.isEnabled()
    tile.action_btn.click()
    assert shown and "ask Woogy" in shown[0][1]


def test_woogy_answers_about_the_cursed_thing(qapp, tmp_path, monkeypatch):
    _on(monkeypatch)
    from techdeck.ui.pages.emporium_page import EmporiumPage
    page = EmporiumPage(SettingsManager(settings_dir=tmp_path))
    page.resize(900, 700); page.grab()                       # paint once so he has a place
    assert not page._woogy_rect.isEmpty()
    c = page._woogy_rect.center()
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(c), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    page.mousePressEvent(ev)
    assert "CURSED" in page._dialogue and "PUPPET MASTER" in page._dialogue
    page.settings.unlock_item(wn.PUPPET_ID)                  # played: he has nothing more to say
    page._set_dialogue(page.DEFAULT_DIALOGUE)
    page.mousePressEvent(ev)
    assert page._dialogue == page.DEFAULT_DIALOGUE


def test_opening_my_stuff_marks_it_seen(qapp, tmp_path, monkeypatch):
    _on(monkeypatch)
    from techdeck.ui.pages.account_page import AccountPage
    s = SettingsManager(settings_dir=tmp_path)
    page = AccountPage(s)
    fired = []
    page.badges_changed.connect(lambda: fired.append(1))
    assert not s.has_seen_my_stuff()
    page.tabs.setCurrentIndex(2)
    assert s.has_seen_my_stuff() and fired


def test_every_sticker_clears_through_the_real_pages(qapp, tmp_path, monkeypatch):
    """Open My Stuff -> the sidebar's clears. Buy the Ghost -> the Ticket Counter
    tab's, the Decorations box's and the Ghost's clear. Discover the table ->
    the My Stuff tab's and the cartridge's clear. All through the pages."""
    _on(monkeypatch)
    from techdeck.ui import arcade_chrome
    from techdeck.ui.pages.account_page import AccountPage
    from techdeck.ui.widgets.sidebar import Sidebar
    from techdeck.core.command_handler import CommandHandler
    from techdeck.core import audio_manager
    monkeypatch.setattr(arcade_chrome.PixelDialog, "show_message",
                        classmethod(lambda cls, parent, title, body, ok_label="OK": None))
    monkeypatch.setattr(audio_manager, "get_audio_manager", lambda: type("A", (), {"play": lambda *a, **k: None})())
    s = SettingsManager(settings_dir=tmp_path)
    s.unlock_item("deco_books"); s.add_tickets(500)
    acc = AccountPage(s)
    side = Sidebar(settings_manager=s); side.refresh_new_badges(s)
    acc.badges_changed.connect(lambda: side.refresh_new_badges(s))
    tabs, boxes = acc._tab_stickers, acc.emporium.cat_buttons
    ghost = next(t for t in acc.emporium.tiles if t.item["id"] == wn.GHOST_ID)
    cartridge = lambda: next(t for t in acc.my_stuff.tiles if t.item["id"] == wn.PUPPET_ID)
    acc._place_stickers()
    assert side._account_sticker.isVisibleTo(side) and tabs[1].isVisibleTo(acc) and tabs[2].isVisibleTo(acc)
    assert ghost.wants_new_sticker() and cartridge().wants_new_sticker()

    acc.tabs.setCurrentIndex(2)                                   # 1. open My Stuff
    assert not side._account_sticker.isVisibleTo(side)
    assert tabs[1].isVisibleTo(acc) and tabs[2].isVisibleTo(acc), "the items' own tabs keep theirs"

    acc.emporium.handle_tile_action(ghost.item)                   # 2. buy the Ghost
    assert s.is_unlocked(wn.GHOST_ID)
    assert not tabs[1].isVisibleTo(acc) and not ghost.wants_new_sticker()
    assert wn.DECORATIONS not in wn.new_badges(s)
    assert tabs[2].isVisibleTo(acc) and cartridge().wants_new_sticker()

    h = CommandHandler.__new__(CommandHandler)                    # 3. the table opens for the first time
    h.settings, h.console, h.main_window = s, None, type("MW", (), {"account_page": acc, "sidebar": side, "library_page": None})()
    assert h.discover_table() is True
    assert not tabs[2].isVisibleTo(acc) and not cartridge().wants_new_sticker()
    assert wn.new_badges(s) == set()
