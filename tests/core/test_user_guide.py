"""The in-app User Guide: path resolution, open behavior, and the surfaces
that must keep offering it (/guide command, Settings button, build step)."""

from pathlib import Path

import techdeck.core.user_guide as ug

REPO = Path(__file__).resolve().parents[2]


def test_guide_path_points_into_assets_docs():
    p = ug.guide_path()
    assert p.name == "TechDeck User Guide.pdf"
    assert p.parent == REPO / "assets" / "docs"


def test_open_guide_missing_file_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(ug, "guide_path", lambda: tmp_path / "nope.pdf")
    ok, message = ug.open_guide()
    assert not ok
    assert "build_user_guide" in message  # dev-mode hint names the builder


def test_open_guide_opens_existing_file(monkeypatch, tmp_path):
    pdf = tmp_path / "TechDeck User Guide.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    opened = []
    monkeypatch.setattr(ug, "guide_path", lambda: pdf)
    monkeypatch.setattr(ug.os, "startfile", opened.append, raising=False)
    ok, message = ug.open_guide()
    assert ok
    assert opened == [str(pdf)]


def test_guide_surfaces_are_wired():
    """The command registry, /help text, Settings button, and build step must
    all keep offering the guide - removing any of them orphans the manual."""
    handler = (REPO / "techdeck" / "core" / "command_handler.py").read_text(encoding="utf-8")
    assert "'/guide': self._cmd_guide" in handler
    assert '"  /guide' in handler  # the /help listing line

    settings_page = (REPO / "techdeck" / "ui" / "pages" / "settings_page.py").read_text(encoding="utf-8")
    assert "Open User Guide" in settings_page

    build = (REPO / "build.ps1").read_text(encoding="ascii")
    assert "build_user_guide.py" in build
