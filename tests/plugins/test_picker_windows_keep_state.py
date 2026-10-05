"""A picker window must never throw away what the user typed.

MieTrak Tools and Sheet Metal Calculators both host several tools behind a
left-hand list. Both first REBUILT the right-hand panel on every pick, so a
half-built hardware code - or half-entered calculator inputs - vanished the
moment the user clicked away to check something and came back (2026-09-23:
build a code, open Code Reference to see what it means, return, and the code
you were checking was gone).

The fix is structural: build every page once and switch a QStackedWidget. These
pin it for both windows, through every way of looking away - another tool in the
list, and another view's tab.
"""

import importlib.util
from pathlib import Path

import pytest
from PySide6.QtWidgets import QScrollArea

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def _load(plugin_id):
    spec = importlib.util.spec_from_file_location(
        "%s_run_keepstate" % plugin_id, PLUGINS / plugin_id / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mt():
    return _load("mietrak_tools")


@pytest.fixture(scope="module")
def smc():
    return _load("sheet_metal_calculators")


@pytest.fixture
def window(qapp):
    """Show a window, pump events, and always close it after the test."""
    made = []

    def _open(cls):
        win = cls()
        win.show()
        qapp.processEvents()
        made.append(win)
        return win

    yield _open
    for win in made:
        win.close()
        win.deleteLater()
    qapp.processEvents()


TOOL = "hardware_code_generator"


def _build_a_code(gen):
    gen.material.setCurrentIndex(gen.material.findData("304"))
    gen.hardware.setCurrentIndex(gen.hardware.findData("HHCS"))
    gen.thread_size.setCurrentIndex(gen.thread_size.findData("1024"))
    gen.length.setCurrentIndex(gen.length.findData("C"))
    return gen.current_code()


# -- MieTrak Tools ---------------------------------------------------------------

def test_mietrak_code_survives_a_trip_through_the_other_tabs(mt, window, qapp):
    win = window(mt.MieTrakTools)
    gen = win.views[TOOL]["Generator"]
    built = _build_a_code(gen)
    assert built == "HW304-HHCS-1024-C"

    for name in ("Code Reference", "Code Reader", "Generator"):
        win.tabs[TOOL][name].click()
        qapp.processEvents()

    assert win.views[TOOL]["Generator"] is gen          # same widget, not a rebuild
    assert gen.current_code() == built


def test_mietrak_code_survives_picking_another_tool(mt, window, qapp, monkeypatch):
    """Only one tool ships today, so add a second to drive the left-hand list."""
    extra = {"id": "extra", "name": "Extra", "description": "",
             "widget": mt.HardwareCodeReader}
    monkeypatch.setattr(mt, "TOOLS", list(mt.TOOLS) + [extra])
    win = window(mt.MieTrakTools)
    gen = win.views[TOOL]["Generator"]
    built = _build_a_code(gen)

    win._list.setCurrentRow(1)
    qapp.processEvents()
    win._list.setCurrentRow(0)
    qapp.processEvents()

    assert gen.current_code() == built


def test_mietrak_reader_keeps_its_code_across_tabs(mt, window, qapp):
    win = window(mt.MieTrakTools)
    win.tabs[TOOL]["Code Reader"].click()
    reader = win.views[TOOL]["Code Reader"]
    reader.code_in.setText("HWZP5-HHCS-F16-2")
    win.tabs[TOOL]["Generator"].click()
    win.tabs[TOOL]["Code Reader"].click()
    qapp.processEvents()
    assert reader.code_in.text() == "HWZP5-HHCS-F16-2"


def test_mietrak_generator_has_its_three_tabs_and_the_description_follows(mt, window, qapp):
    win = window(mt.MieTrakTools)
    assert list(win.tabs[TOOL]) == ["Generator", "Code Reference", "Code Reader"]
    assert win.tabs[TOOL]["Generator"].isChecked()

    views = {v["name"]: v for v in mt.TOOLS[0]["views"]}
    page = win._pages.currentWidget()
    shown = lambda: [lab.text() for lab in page.findChildren(mt.QLabel)
                     if lab.text() in {v["description"] for v in views.values()}]

    win.tabs[TOOL]["Code Reader"].click()
    qapp.processEvents()
    assert win.tabs[TOOL]["Code Reader"].isChecked()
    assert not win.tabs[TOOL]["Generator"].isChecked()
    assert shown() == [views["Code Reader"]["description"]]


def test_mietrak_scroll_bar_does_not_touch_the_fields(mt, window):
    """User's call, 2026-09-23: the bar sat hard against the dropdowns' right
    edge. Every view's scrolled content keeps a gutter before the bar."""
    win = window(mt.MieTrakTools)
    scrolls = win.findChildren(QScrollArea)
    assert scrolls
    for scroll in scrolls:
        assert scroll.widget().layout().contentsMargins().right() >= 10


# -- Sheet Metal Calculators ----------------------------------------------------

def _first_number_field(form):
    for spec, widget in form._fields.values():
        if spec.get("type", "number") == "number":
            return widget
    raise AssertionError("calculator has no number field")


def test_calculator_inputs_survive_picking_another_calculator(smc, window, qapp):
    assert len(smc.CALCULATORS) >= 2, "needs two calculators to switch between"
    win = window(smc.SheetMetalCalculators)
    form = win.forms[0]
    field = _first_number_field(form)
    field.setText("12.5")

    win._list.setCurrentRow(1)
    qapp.processEvents()
    win._list.setCurrentRow(0)
    qapp.processEvents()

    assert win.forms[0] is form
    assert field.text() == "12.5"
