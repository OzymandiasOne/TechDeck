"""The shared CAD-AND-SHOP-PRINTS / 7000 scan and the repeater's repeat audit.

The tree shapes below are the real ones off Batch 485 (2026-08-05): a plain
part (`CAD-AND-SHOP-PRINTS/{DYPN}/7000`), an assembly that adds a level
(`.../{DYPN}-Asm-1/{DYPN}/7000`), and non-tube orders that have no 7000 folder
at all — which is normal, not a finding.
"""

import importlib.util
import threading
from pathlib import Path

import pytest

from techdeck.core import plugin_sdk as sdk

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def repeater():
    spec = importlib.util.spec_from_file_location(
        "repeater_run", PLUGINS / "922_batch_repeater" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _order(root: Path, name: str, parts=(), *, cad=True, empty=()):
    """Build one order folder. `parts` get a 7000 with a .lst; `empty` get a
    7000 with everything BUT the .lst (the real failure shape)."""
    folder = root / name
    folder.mkdir(parents=True)
    if not cad:
        return folder
    cad_dir = folder / "CAD-AND-SHOP-PRINTS"
    cad_dir.mkdir()
    for p in parts:
        seven = cad_dir / p / "7000"
        seven.mkdir(parents=True)
        (seven / f"{p}-STEP.lst").write_text("lst", encoding="utf-8")
        (seven / f"{p}-STEP.pdf").write_text("pdf", encoding="utf-8")
    for p in empty:
        seven = cad_dir / p / "7000"
        seven.mkdir(parents=True)
        (seven / f"{p}-STEP.pdf").write_text("pdf", encoding="utf-8")
    return folder


# ── sdk.scan_shop_print_lsts ────────────────────────────────────────────────

def test_finds_the_lsts_and_the_structure(tmp_path):
    f = _order(tmp_path, "BK464664-R7211263-H10", ["R7211263-H10-3A"])
    scan = sdk.scan_shop_print_lsts(f)

    assert [p.name for p in scan.lsts] == ["R7211263-H10-3A-STEP.lst"]
    assert scan.all_lsts == scan.lsts
    assert scan.has_cad and len(scan.cad_dirs) == 1
    assert len(scan.seven_k) == 1
    assert scan.empty_7000 == []


def test_an_assembly_adds_a_level_and_still_resolves(tmp_path):
    # Batch 485: .../CAD-AND-SHOP-PRINTS/R7653561-H6-Asm-1/R7653561-H6-4A/7000
    f = tmp_path / "BL392376-R7653561-H6"
    for piece in ("R7653561-H6-4A", "R7653561-H6-4B"):
        seven = f / "CAD-AND-SHOP-PRINTS" / "R7653561-H6-Asm-1" / piece / "7000"
        seven.mkdir(parents=True)
        (seven / f"{piece}-STEP.lst").write_text("lst", encoding="utf-8")

    scan = sdk.scan_shop_print_lsts(f)
    assert len(scan.lsts) == 2 and len(scan.seven_k) == 2


def test_a_non_tube_order_has_cad_prints_but_no_7000(tmp_path):
    f = _order(tmp_path, "X4671182-E6551567-H15", [])
    scan = sdk.scan_shop_print_lsts(f)

    assert scan.has_cad          # so it is NOT a missing-CAD finding...
    assert scan.seven_k == []    # ...and having no 7000 folder is normal
    assert scan.lsts == [] and scan.empty_7000 == []


def test_an_empty_7000_is_separated_from_a_missing_one(tmp_path):
    f = _order(tmp_path, "FK361265-H6455572-H12", ["H6455572-H12-2"],
               empty=["H6455572-H12-3"])
    scan = sdk.scan_shop_print_lsts(f)

    assert len(scan.lsts) == 1
    assert len(scan.seven_k) == 2
    assert [p.parent.name for p in scan.empty_7000] == ["H6455572-H12-3"]


def test_no_cad_folder_at_all(tmp_path):
    f = _order(tmp_path, "BK573366-R8651569-H2", cad=False)
    scan = sdk.scan_shop_print_lsts(f)

    assert not scan.has_cad
    assert scan.lsts == [] and scan.seven_k == []


def test_a_stray_7000_outside_the_cad_tree_is_ignored(tmp_path):
    f = _order(tmp_path, "X8390862-H7655461-H12", ["H7655461-H12-4"])
    stray = f / "Scrap" / "7000"
    stray.mkdir(parents=True)
    (stray / "not-a-shop-print.lst").write_text("lst", encoding="utf-8")

    scan = sdk.scan_shop_print_lsts(f)
    assert [p.name for p in scan.lsts] == ["H7655461-H12-4-STEP.lst"]


def test_scanning_a_repeat_folder_directly_still_returns_its_files(tmp_path):
    # The repeat-preference test runs on the path RELATIVE to order_dir — with
    # an absolute test, everything under REPEAT BATCHES would be discarded and
    # the repeater's audit would report every repeat as empty.
    f = _order(tmp_path / "Batch 485" / "REPEAT BATCHES",
               "BK423594-R7653561-H6", ["R7653561-H6-4A"])
    scan = sdk.scan_shop_print_lsts(f)

    assert len(scan.lsts) == 1


def test_a_non_repeat_path_wins_over_a_repeat_copy(tmp_path):
    # Batch 484's FK345540 really does carry its part twice, once under REPEAT\.
    f = _order(tmp_path, "FK345540-H5223262-H48", ["H5223262-H48-5"])
    old = f / "REPEAT" / "CAD-AND-SHOP-PRINTS" / "H5223262-H48-5" / "7000"
    old.mkdir(parents=True)
    (old / "stale.lst").write_text("lst", encoding="utf-8")

    scan = sdk.scan_shop_print_lsts(f)
    # The PULL list drops the REPEAT copy...
    assert [p.name for p in scan.lsts] == ["H5223262-H48-5-STEP.lst"]
    # ...but an AUDIT counting against seven_k must see both, or the folder
    # reads as "1 .lst in 2 7000 folders" and looks like it's missing one.
    assert len(scan.all_lsts) == 2 and len(scan.seven_k) == 2
    assert scan.empty_7000 == []


def test_a_cancelled_scan_stops_early(tmp_path):
    f = _order(tmp_path, "BK464664-R7211263-H10", ["R7211263-H10-3A"])
    ev = threading.Event()
    ev.set()

    assert sdk.scan_shop_print_lsts(f, ev).lsts == []


def test_a_missing_folder_scans_empty(tmp_path):
    scan = sdk.scan_shop_print_lsts(tmp_path / "nope")
    assert not scan.has_cad and scan.lsts == []


# ── the 922 Batch Repeater audit ────────────────────────────────────────────

def test_the_audit_flags_only_the_actionable_findings(repeater, tmp_path):
    rb = tmp_path / "REPEAT BATCHES"
    _order(rb, "BK423594-R7653561-H6", ["R7653561-H6-4A", "R7653561-H6-4B"])
    _order(rb, "X3454742-E6551567-H15", [])                    # non-tube: fine
    _order(rb, "BK423596-R7653561-H4", cad=False)              # finding
    _order(rb, "BK423604-R7653561-H10", ["R7653561-H10-3A"],
           empty=["R7653561-H10-3B"])                          # finding
    lines = []

    checked, total, problems = repeater._audit_repeat_shop_prints(
        rb, lines.append, threading.Event())

    assert checked == 4
    assert total == 3                                # 2 + 0 + 0 + 1
    assert [name for name, _why in problems] == [
        "BK423596-R7653561-H4", "BK423604-R7653561-H10"]
    assert "no CAD-AND-SHOP-PRINTS folder" in problems[0][1]
    assert "R7653561-H10-3B" in problems[1][1]
    # The non-tube order is reported as information, never as a problem.
    assert any("no tube parts" in ln for ln in lines)


def test_the_audit_is_clean_when_every_repeat_has_its_files(repeater, tmp_path):
    rb = tmp_path / "REPEAT BATCHES"
    _order(rb, "BK423594-R7653561-H6", ["R7653561-H6-4A"])
    _order(rb, "X2484747-H8651461-H4", ["H8651461-H4-4"])

    checked, total, problems = repeater._audit_repeat_shop_prints(
        rb, lambda *_a: None, threading.Event())

    assert (checked, total, problems) == (2, 2, [])


def test_the_audit_survives_a_missing_repeat_batches_folder(repeater, tmp_path):
    checked, total, problems = repeater._audit_repeat_shop_prints(
        tmp_path / "REPEAT BATCHES", lambda *_a: None, threading.Event())

    assert (checked, total, problems) == (0, 0, [])


def test_the_audit_honours_cancel(repeater, tmp_path):
    rb = tmp_path / "REPEAT BATCHES"
    _order(rb, "BK423594-R7653561-H6", ["R7653561-H6-4A"])
    ev = threading.Event()
    ev.set()

    with pytest.raises(BaseException) as exc:
        repeater._audit_repeat_shop_prints(rb, lambda *_a: None, ev)
    assert type(exc.value).__name__ == "PluginCancelled"
