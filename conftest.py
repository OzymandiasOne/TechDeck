"""Pytest bootstrap.

Runs Qt headless (QT_QPA_PLATFORM must be set before any QApplication is
created, so it is set here at collection time) and makes the repo-root
packages (`techdeck`, `tools`) importable. The session-scoped `qapp` fixture
gives widget tests one offscreen QApplication with a theme applied so palette
reads succeed.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


@pytest.fixture(scope="session")
def qapp():
    """A single offscreen QApplication for widget tests, with a theme set so
    ThemeAware/palette reads work."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    try:
        from techdeck.ui.theme_manager import get_theme_manager
        get_theme_manager().set_theme("dark")
    except Exception:
        pass
    yield app
