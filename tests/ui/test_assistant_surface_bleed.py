"""A page must paint its own background, or its host's bleeds through.

**The trap.** A plain ``QWidget`` ignores ``background-color`` from a
stylesheet unless ``WA_StyledBackground`` is set, so it stays transparent and
shows whatever is behind it. Behind a page is a ``QStackedWidget``, which IS
QFrame-family - and the generated sheet's ``QFrame`` rule paints it
``surface``, beating the earlier ``QStackedWidget`` rule because it comes last
at equal specificity.

On a one-tone theme surface and background look alike and nobody notices. On
halloween, surface is bright orange: on 2026-10-13 it showed through every gap
between the Assistant's cards, and reading it as "the toolbar has a slab
background" sent the first fix off in the wrong direction entirely. The colour
was never the toolbar's - it was the stack showing through the page.

The fix is ``techdeck.ui.utils.paint_own_background``.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QStackedWidget

from techdeck.core.assistant.store import AssistantStore
from techdeck.ui.theme import THEMES, generate_stylesheet
from techdeck.ui.widgets.assistant_schedule import (
    SchedulePanel, TasksPanel, card_qss)
from techdeck.ui.widgets.assistant_time import TimePanel

PANELS = (SchedulePanel, TasksPanel, TimePanel)


@pytest.fixture
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant.json")


def test_every_assistant_tab_paints_its_own_backdrop(store, qapp):
    for cls in PANELS:
        panel = cls(store)
        assert panel.objectName() == "assistantTabPanel", cls.__name__
        from PySide6.QtCore import Qt
        assert panel.testAttribute(Qt.WidgetAttribute.WA_StyledBackground), (
            f"{cls.__name__} does not paint its own background, so the "
            f"stacked host behind it shows through every gap.")


def test_the_backdrop_is_the_page_colour_not_the_card_colour():
    """`background`, not `surface`: a tab has to match the empty space below
    its cards, which is the page's own colour."""
    for name, palette in THEMES.items():
        sheet = card_qss(palette)
        assert "QWidget#assistantTabPanel" in sheet, name
        block = sheet.split("QWidget#assistantTabPanel", 1)[1].split("}", 1)[0]
        assert palette.background in block, name
        assert palette.surface not in block, name


def test_no_surface_bleeds_through_the_gap_under_the_header(store, qapp):
    """The end-to-end proof, on the theme that exposes it: put a tab in the
    stacked host it really lives in and read the pixels in the gap between the
    header card and the first content card."""
    palette = THEMES["halloween"]
    previous = qapp.styleSheet()
    try:
        qapp.setStyleSheet(generate_stylesheet("halloween"))
        for cls in PANELS:
            host = QStackedWidget()
            panel = cls(store)
            host.addWidget(panel)
            host.resize(900, 500)
            host.show()
            qapp.processEvents()

            header = panel.layout().itemAt(0).widget()
            gap_y = header.geometry().bottom() + 5
            image = host.grab().toImage()
            bleed = []
            for x in range(20, 880, 40):
                colour = image.pixelColor(x, gap_y)
                got = f"#{colour.red():02X}{colour.green():02X}{colour.blue():02X}"
                if got.lower() == palette.surface.lower():
                    bleed.append((x, gap_y))
            assert not bleed, (
                f"{cls.__name__}: the stacked host's surface colour "
                f"({palette.surface}) is showing through the gap under the "
                f"header card at {bleed[:3]}. Call "
                f"techdeck.ui.utils.paint_own_background on the panel.")
    finally:
        qapp.setStyleSheet(previous)
