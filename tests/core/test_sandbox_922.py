"""The 922 test sandbox switch (TECHDECK_SANDBOX_922_ROOT).

A test batch lives in '922 QTDR Production Packages\\Automation Test
Environment'. Several 922 apps re-find a batch by NUMBER under the resolved
root, and the MPL stage / Batch Repeater write '<root>\\922 MPL.xlsx' - so a
sandbox is only safe if the sandbox folder IS the root for every app, and if
nothing is posted to the live Teams board. Both are one SDK choke point each.
"""

import sys

from techdeck.core import plugin_sdk as sdk


def test_sandbox_root_beats_a_saved_override(monkeypatch, tmp_path):
    monkeypatch.setenv(sdk.SANDBOX_922_ENV, str(tmp_path))
    assert sdk.resolve_922_root(r"C:\real\922 QTDR Production Packages") == tmp_path
    assert sdk.resolve_922_root("") == tmp_path


def test_no_sandbox_means_normal_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv(sdk.SANDBOX_922_ENV, raising=False)
    assert sdk.sandbox_922_root() is None
    assert sdk.resolve_922_root(str(tmp_path)) == tmp_path


def test_frozen_build_ignores_the_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv(sdk.SANDBOX_922_ENV, str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert sdk.sandbox_922_root() is None


def test_batch_lookup_by_number_stays_in_the_sandbox(monkeypatch, tmp_path):
    (tmp_path / "Batch 900").mkdir()
    monkeypatch.setenv(sdk.SANDBOX_922_ENV, str(tmp_path))
    root = sdk.resolve_922_root("")
    assert sdk.find_922_batch_path(root, "900") == tmp_path / "Batch 900"


def test_sandbox_never_posts_a_webhook(monkeypatch, tmp_path):
    monkeypatch.setenv(sdk.SANDBOX_922_ENV, str(tmp_path))
    previews = []
    monkeypatch.setattr(sdk, "write_payload_preview",
                        lambda payload, name, log: previews.append(name))
    import requests

    def boom(*a, **k):
        raise AssertionError("a sandbox run must not reach the network")
    monkeypatch.setattr(requests, "post", boom)
    lines = []
    assert sdk.post_webhook("https://example.invalid/flow", {"a": 1}, lines.append)
    assert previews == ["last_sandbox_webhook_payload.json"]
    assert any("SANDBOX" in l for l in lines)
