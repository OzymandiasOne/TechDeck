"""922 Setup's MPL stage must only ever WARN — including on a surprise.

The stage's docstring has promised since v2.6.0 that "every failure path warns
LOUDLY (popup + warning outcome) and returns False — never raises, so the
remaining stages still run". Every failure it had thought of did exactly that.
One it had not thought of did not: the borrowed Repeater helper grew an
argument (fixed in v2.8.2), the `TypeError` came straight out of `run()`, and
the batch lost its Teams cards, its pallet stamps and its repeat pull as well
as its MPL column.

`tests/tools/test_sibling_call_arity.py` stops that specific drift at build
time. This pins the second layer: the unforeseeable failure is exactly the one
that must still only warn.

Cancel is the one thing that must get THROUGH, which is why
`sdk.raise_if_cancelled` raises a BaseException.
"""

import importlib.util
import threading
from pathlib import Path

import pytest

from techdeck.core import plugin_sdk as sdk

_PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def _setup():
    spec = importlib.util.spec_from_file_location(
        "setup922_guard_test", _PLUGINS / "922_setup" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stage(monkeypatch):
    """922 Setup with the MPL stage's body replaced by a chosen explosion.

    Swapping `_mpl_update_stage` is the honest stand-in for any failure inside
    it — the borrowed sibling call, the workbook read, a settings shape nobody
    expected. The guard is in `_run_mpl_update`, which is what gets exercised.
    """
    mod = _setup()
    warnings = []
    monkeypatch.setattr(
        mod, "_label_stage_problem",
        lambda params, message, title=None: warnings.append(message))

    def run_with(exc):
        def boom(*_args, **_kwargs):
            raise exc
        monkeypatch.setattr(mod, "_mpl_update_stage", boom)
        shared = {}
        result = mod._run_mpl_update(
            {"log": lambda *_a: None, "settings": {}, "console": None},
            lambda _p: None, threading.Event(), Path("Batch 900"), "900", shared)
        return result, shared, warnings

    return run_with


def test_an_unexpected_error_warns_and_lets_the_run_carry_on(stage):
    result, shared, warnings = stage(TypeError(
        "_update_mpl_sheets() missing 1 required positional argument: 'params'"))

    assert result is False                      # the stage did not count as done
    assert shared["922"]["mpl_update_done"] is False
    assert len(warnings) == 1                   # loud, and once
    assert "TypeError" in warnings[0]           # the real error is named
    # 'repeat_folders' must stay ABSENT: present means detection completed, and
    # an empty list would tell the card stage "no repeats" when it never looked.
    assert "repeat_folders" not in shared["922"]


def test_the_warning_tells_them_what_to_do_about_it(stage):
    _result, _shared, warnings = stage(RuntimeError("the MPL grew a third head"))

    message = warnings[0]
    assert "Batch Repeater" in message          # the second pass that fixes it
    assert "untagged" in message                # what the cards will look like
    assert "debug report" in message            # how it gets back to us


def test_cancel_still_gets_through(stage):
    with pytest.raises(sdk.PluginCancelled):
        stage(sdk.PluginCancelled("cancelled"))


def test_a_clean_stage_is_passed_through_untouched(monkeypatch):
    mod = _setup()
    monkeypatch.setattr(
        mod, "_mpl_update_stage",
        lambda params, cb, ce, bp, b, shared: shared.setdefault(
            "922", {}).update(repeat_folders=["A-H1"], mpl_update_done=True) or True)

    shared = {}
    result = mod._run_mpl_update(
        {"log": lambda *_a: None}, lambda _p: None, threading.Event(),
        Path("Batch 900"), "900", shared)

    assert result is True
    assert shared["922"] == {"repeat_folders": ["A-H1"], "mpl_update_done": True}
