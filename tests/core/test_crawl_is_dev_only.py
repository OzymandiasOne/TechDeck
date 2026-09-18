"""/crawl summons a Halloween crawly on demand. It is a TEST LEVER: colleagues
must never be able to run it - the crawlies exist to catch people off guard, and
a command anyone can type turns the scare into a toy. So it only exists when
running from source; in the installed (frozen) app it reads exactly like a typo.
"""
import sys

import pytest

from techdeck.core.command_handler import CommandHandler


class _Console:
    def __init__(self):
        self.errors, self.system = [], []

    def append_error(self, msg):
        self.errors.append(msg)

    def append_system(self, msg):
        self.system.append(msg)


@pytest.fixture
def handler(monkeypatch):
    """CommandHandler with __init__ bypassed (it builds Qt state we don't
    need); only the command map and the dispatch guard are under test."""
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    monkeypatch.setattr("techdeck.core.command_handler.halloween_active",
                        lambda settings=None: True)
    h = CommandHandler.__new__(CommandHandler)
    h.console = _Console()
    h.settings = None
    h._admin_mode = False
    ran = []
    h.commands = {"/crawl": lambda args: ran.append(args),
                  "/help": lambda args: None}
    return h, ran


def test_crawl_is_listed_as_dev_only():
    assert "/crawl" in CommandHandler._DEV_ONLY_COMMANDS


def test_crawl_runs_from_source(handler, monkeypatch):
    h, ran = handler
    monkeypatch.delattr(sys, "frozen", raising=False)
    h.handle_command("/crawl dangle")
    assert ran == ["dangle"]
    assert h.console.errors == []


def test_crawl_is_an_unknown_command_in_the_installed_app(handler, monkeypatch):
    h, ran = handler
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    h.handle_command("/crawl")
    h.handle_command("/crawl spider")
    assert ran == []
    assert h.console.errors == ["Unknown command: /crawl"] * 2
    # and it looks like any other typo: no hint that it exists
    assert set(h.console.system) == {"Type /help for available commands."}


def test_admin_mode_does_not_unlock_it_in_the_installed_app(handler, monkeypatch):
    h, ran = handler
    h._admin_mode = True
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    h.handle_command("/crawl")
    assert ran == []


def test_crawl_is_not_in_help():
    import inspect
    src = inspect.getsource(CommandHandler)
    start = src.index("def _cmd_help")
    body = src[start:src.index("\n    def ", start + 10)]
    assert "/crawl" not in body
