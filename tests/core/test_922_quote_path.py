r"""Where the 922 master quote lives (master_parts.quote_path).

The Batch Repeater, 922 Setup's MPL stage and tools/mpl_build_master.py looked
for `2 - Planning\EB 922 H# Quote.xlsx`; the file actually sits in
`2 - Planning\Batch Setup\Quote\`. Nothing crashed - every run just logged
"the quote workbook is missing" and typed new MASTER PARTS rows from tube
serials only (found 2026-09-28). One home now, and this gate keeps it that way.
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _mp():
    spec = importlib.util.spec_from_file_location(
        "mp_quote_test", REPO / "plugins" / "922_batch_repeater" / "master_parts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_quote_lives_in_batch_setup(tmp_path):
    mp = _mp()
    real = tmp_path / "2 - Planning" / "Batch Setup" / "Quote" / "EB 922 H# Quote.xlsx"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"x")
    assert mp.quote_path(tmp_path) == real


def test_old_spot_is_still_found(tmp_path):
    mp = _mp()
    old = tmp_path / "2 - Planning" / "EB 922 H# Quote.xlsx"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    assert mp.quote_path(tmp_path) == old


def test_missing_quote_names_the_current_folder(tmp_path):
    mp = _mp()
    assert mp.quote_path(tmp_path) == tmp_path / mp.QUOTE_RELPATH
    assert "Batch Setup" in str(mp.quote_path(tmp_path))


def test_nobody_else_hardcodes_the_quote_path():
    offenders = []
    for folder in ("plugins", "tools", "techdeck"):
        for py in (REPO / folder).rglob("*.py"):
            if py.name == "master_parts.py" or "devkit" in py.parts:
                continue
            if "H# Quote.xlsx" in py.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(py.relative_to(REPO)))
    assert not offenders, f"use master_parts.quote_path(): {offenders}"
