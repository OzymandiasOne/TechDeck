"""tools/devkit/sandbox_922.py - `reset` deletes folders on SharePoint, so the one
guard that keeps it inside 'Automation Test Environment' is pinned here."""

import pytest

from tools.devkit import sandbox_922 as sbx


def test_reset_guard_allows_only_paths_inside_the_sandbox(tmp_path):
    box = tmp_path / sbx.SANDBOX_NAME
    (box / "Batch 900").mkdir(parents=True)
    assert sbx._inside_sandbox(box / "Batch 900", box) == (box / "Batch 900").resolve()
    with pytest.raises(RuntimeError):
        sbx._inside_sandbox(tmp_path / "Batch 498", box)      # a real batch
    with pytest.raises(RuntimeError):
        sbx._inside_sandbox(box, box)                          # the sandbox itself
    with pytest.raises(RuntimeError):
        sbx._inside_sandbox(tmp_path / "x" / "Batch 900", tmp_path / "x")  # wrong name


def test_live_items_are_all_sandbox_children():
    # Everything reset wipes is a direct child name, never a path that climbs out.
    for item in sbx.LIVE_ITEMS:
        assert "/" not in item and "\\" not in item and ".." not in item


def test_batch_number_is_not_a_real_one():
    # A number that collides with a real batch would let a by-number lookup
    # in the REAL root stamp real packets. Real batches are ~500 in 2026.
    assert int(sbx.BATCH) >= 900
    assert sbx.PALLET_SPLIT and len(sbx.PALLET_SPLIT) == len(sbx.ORDERS)
