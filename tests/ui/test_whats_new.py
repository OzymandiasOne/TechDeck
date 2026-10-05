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
