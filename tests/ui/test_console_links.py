"""Tests for console inline-link markup ([[label|url]]) and the techdeck://
internal link scheme (anchor routing + CommandHandler dispatch)."""

from techdeck.core.command_handler import CommandHandler
from techdeck.core.settings import SettingsManager
from techdeck.ui.widgets.console import ConsoleWidget


class _ConsoleStub:
    """Records what CommandHandler prints, no Qt needed."""

    def __init__(self):
        self.errors = []
        self.systems = []

    def append_error(self, text):
        self.errors.append(text)

    def append_system(self, text):
        self.systems.append(text)


# ── markup ────────────────────────────────────────────────────────────────

def test_markup_to_html_builds_inline_anchor(qapp):
    c = ConsoleWidget()
    html = c.markup_to_html(
        "Click [[here|techdeck://cmd/dash]] now.", "#ABCDEF")
    assert '<a href="techdeck://cmd/dash"' in html
    assert "color: #ABCDEF" in html
    assert ">here</a>" in html
    assert html.startswith("Click ")
    assert html.endswith(" now.")


def test_markup_escapes_text_outside_anchors(qapp):
    c = ConsoleWidget()
    html = c.markup_to_html("a < b [[x|techdeck://cmd/dash]] & c", "#FFF")
    assert "&lt;" in html
    assert "&amp;" in html


def test_markup_without_spans_is_plain_escaped_text(qapp):
    c = ConsoleWidget()
    assert c.markup_to_html("no links <here>", "#FFF") == "no links &lt;here&gt;"


def test_append_markup_renders_into_document(qapp):
    c = ConsoleWidget()
    c.append_markup(
        "Your effort to remain what you are is what limits you. "
        "I can help [[redefine|techdeck://cat/summon]] those limits.")
    assert "redefine" in c.output.toPlainText()


# ── anchor activation ─────────────────────────────────────────────────────

def test_internal_anchor_emits_signal_not_os(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "techdeck.ui.widgets.console.QDesktopServices.openUrl",
        lambda url: opened.append(url))
    c = ConsoleWidget()
    got = []
    c.internal_link_clicked.connect(got.append)
    c._activate_anchor("techdeck://cat/summon")
    assert got == ["techdeck://cat/summon"]
    assert opened == []


def test_external_anchor_still_goes_to_os(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "techdeck.ui.widgets.console.QDesktopServices.openUrl",
        lambda url: opened.append(url))
    c = ConsoleWidget()
    got = []
    c.internal_link_clicked.connect(got.append)
    c._activate_anchor("file:///C:/somewhere/report.pdf")
    assert len(opened) == 1
    assert got == []


# ── CommandHandler routing ────────────────────────────────────────────────

def _handler(tmp_path, stub):
    return CommandHandler(SettingsManager(settings_dir=tmp_path), stub)


def test_cmd_verb_dispatches_with_segments_as_args(tmp_path):
    handler = _handler(tmp_path, _ConsoleStub())
    calls = []
    handler.commands["/probe"] = lambda args: calls.append(args)
    handler.handle_internal_link("techdeck://cmd/probe/alpha/beta")
    assert calls == ["alpha beta"]


def test_cmd_verb_without_args(tmp_path):
    handler = _handler(tmp_path, _ConsoleStub())
    calls = []
    handler.commands["/probe"] = lambda args: calls.append(args)
    handler.handle_internal_link("techdeck://cmd/probe")
    assert calls == [""]


def test_unknown_verb_reports_unroutable(tmp_path):
    stub = _ConsoleStub()
    handler = _handler(tmp_path, stub)
    handler.handle_internal_link("techdeck://teleport/home")
    assert stub.errors
    assert "Unroutable" in stub.errors[0]


def test_non_techdeck_url_is_ignored(tmp_path):
    stub = _ConsoleStub()
    handler = _handler(tmp_path, stub)
    handler.handle_internal_link("https://example.com/x")
    assert stub.errors == []
