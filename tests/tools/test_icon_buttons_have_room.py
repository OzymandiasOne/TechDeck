"""An icon-only button must have room for its glyph.

**The trap.** The generated stylesheet gives every ``QPushButton``
``padding: 8px 16px``. On a button with a small fixed size that padding is
wider than the button itself: the content rect goes negative and Qt draws
**nothing** - no glyph, no warning, no clue in the logs. The control is simply
not there, and it looks like a layout bug rather than a style one.

It cost the Assistant its clock *and* its delete button on 2026-10-13, found
only by sampling the pixels where they should have been. Nine buttons across
the app were in the same trap at the time.

**The fix** is ``techdeck.ui.utils.mark_icon_button``, which sets the
``iconOnly`` property that a ``padding: 0`` rule keys on. This gate checks
that every small fixed-size button either takes that route or sets its own
padding, so the class cannot ship again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[2] / "techdeck" / "ui"

# Below this, the stylesheet's 16px horizontal padding leaves a glyph no room.
SMALL_PX = 60
FIXED_SIZE = re.compile(r"([\w.]+)\.setFixedSize\((\d+)\s*,\s*(\d+)\)")
# How far around the call to look for the button's own styling.
WINDOW_BEFORE, WINDOW_AFTER = 12, 14


def _button_sites():
    """Every small fixed-size call that is plausibly on a button."""
    for path in sorted(UI.rglob("*.py")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            match = FIXED_SIZE.search(line)
            if not match:
                continue
            name, width, height = match.group(1), int(match.group(2)), int(match.group(3))
            if width > SMALL_PX or height > SMALL_PX:
                continue
            window = "\n".join(
                lines[max(0, index - WINDOW_BEFORE):index + WINDOW_AFTER])
            if "QPushButton" not in window and "QToolButton" not in window:
                continue
            yield path, index + 1, name, window


def test_the_padding_rule_exists_for_icon_buttons():
    """The whole fix rests on this one rule being in the generated sheet."""
    from techdeck.ui.theme import generate_stylesheet

    sheet = generate_stylesheet("dark")
    assert 'QPushButton[iconOnly="true"]' in sheet
    block = sheet.split('QPushButton[iconOnly="true"]', 1)[1][:160]
    assert "padding: 0px" in block


def test_the_helper_sets_the_property_the_rule_keys_on(qapp):
    from PySide6.QtWidgets import QPushButton

    from techdeck.ui.utils import mark_icon_button

    button = QPushButton("▶")
    mark_icon_button(button, size=26)
    assert button.property("iconOnly") == "true"
    assert button.size().width() == 26 and button.size().height() == 26


def test_every_small_fixed_size_button_has_room_for_its_glyph():
    offenders = []
    for path, line_no, name, window in _button_sites():
        marked = f"mark_icon_button({name}" in window
        own_padding = re.search(r"padding\s*:", window) is not None
        if not marked and not own_padding:
            offenders.append(
                f"{path.relative_to(UI.parent.parent)}:{line_no} -> {name}")
    assert not offenders, (
        "These buttons are small and fixed-size but never reset the theme's "
        "padding, so their glyph has no room and Qt draws nothing:\n  "
        + "\n  ".join(offenders)
        + "\n\nCall techdeck.ui.utils.mark_icon_button(<button>) on each.")


@pytest.mark.parametrize("theme", ["dark", "halloween"])
def test_a_marked_button_actually_paints_its_glyph(qapp, theme, destroy_qt):
    """The end-to-end proof: render one and count the colours where the glyph
    is. An unpainted glyph leaves a single flat background colour, which is
    exactly what the bug looked like."""
    from PySide6.QtWidgets import QPushButton

    from techdeck.ui.theme import generate_stylesheet
    from techdeck.ui.utils import mark_icon_button

    # The application stylesheet is global and outlives this test, including
    # its font-size, which another test measures against a pixel budget. Put
    # it back whatever happens.
    previous = qapp.styleSheet()
    try:
        qapp.setStyleSheet(generate_stylesheet(theme))
        button = QPushButton("✕")
        mark_icon_button(button, size=26)
        button.show()
        qapp.processEvents()
        image = button.grab().toImage()
    finally:
        qapp.setStyleSheet(previous)
        # A shown top-level widget left standing is destroyed at interpreter
        # shutdown, after the QApplication - which aborts the run. See the
        # destroy_qt fixture.
        destroy_qt(button)

    colours = {image.pixel(x, y)
               for x in range(image.width()) for y in range(image.height())}
    assert len(colours) > 1, (
        f"The glyph did not paint under the {theme} theme - the button is "
        f"one flat colour, which is the padding bug all over again.")
