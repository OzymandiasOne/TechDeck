"""Tests for update version/mandatory logic and the SHA-256 verify helpers."""

import hashlib

import requests

from techdeck.core import update_checker as uc
from techdeck.core.update_checker import UpdateChecker, UpdateInfo
from techdeck.core.update_downloader import sha256_file, sha256_matches


def test_is_newer_than():
    u = UpdateInfo({"version": "1.2.0"})
    assert u.is_newer_than("1.1.0") is True
    assert u.is_newer_than("1.2.0") is False
    assert u.is_newer_than("2.0.0") is False


def test_is_newer_than_bad_version_is_false():
    assert UpdateInfo({"version": "not-a-version"}).is_newer_than("1.0.0") is False


def test_manifest_key_aliasing():
    old = UpdateInfo({"latest_version": "3.0", "installer_sha256": "ABCD",
                      "min_supported_version": "2.0", "mandatory": True})
    assert old.version == "3.0"
    assert old.sha256 == "abcd"          # normalized to lowercase
    assert old.min_version == "2.0"
    assert old.critical is True          # legacy mandatory -> critical

    new = UpdateInfo({"version": "3.0", "sha256": "EF01", "min_version": "2.0",
                      "critical": True})
    assert new.sha256 == "ef01"
    assert new.critical is True


def test_requires_mandatory_update():
    assert UpdateInfo({"version": "2.0", "critical": True}
                      ).requires_mandatory_update("1.9") is True
    assert UpdateInfo({"version": "2.0", "min_version": "1.5"}
                      ).requires_mandatory_update("1.4") is True
    assert UpdateInfo({"version": "2.0", "min_version": "1.0"}
                      ).requires_mandatory_update("1.4") is False


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "installer.bin"
    data = b"pretend installer bytes"
    p.write_bytes(data)
    assert sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_sha256_matches_normalizes_and_rejects():
    assert sha256_matches("ABC123", "abc123") is True
    assert sha256_matches("  abc123  ", "abc123") is True
    assert sha256_matches("abc", "def") is False
    # An unpinned/empty expected hash must never count as verified.
    assert sha256_matches("abc", "") is False
    assert sha256_matches("", "abc") is False


# ---- last_error: "up to date" vs "the check failed" -------------------------
# check_now() returns None for BOTH. last_error is what lets the manual
# Settings check tell them apart — it used to say "you're running the latest
# version" on a dead network.

class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_failed_check_sets_last_error(monkeypatch):
    checker = UpdateChecker("1.0.0", "https://example.invalid/manifest.json")

    def _boom(*args, **kwargs):
        raise requests.RequestException("connection refused")
    monkeypatch.setattr(uc.requests, "get", _boom)

    assert checker.check_now() is None
    assert checker.last_error is not None
    assert "connection refused" in checker.last_error


def test_clean_no_update_clears_last_error(monkeypatch):
    checker = UpdateChecker("1.0.0", "https://example.invalid/manifest.json")
    checker.last_error = "stale error from an earlier failed check"

    monkeypatch.setattr(
        uc.requests, "get",
        lambda *a, **k: _FakeResponse({"version": "1.0.0"}))

    assert checker.check_now() is None      # same version -> no update
    assert checker.last_error is None       # ...and NOT an error


def test_http_error_sets_last_error(monkeypatch):
    checker = UpdateChecker("1.0.0", "https://example.invalid/manifest.json")
    response = _FakeResponse({})
    response.status_code = 503
    monkeypatch.setattr(uc.requests, "get", lambda *a, **k: response)

    assert checker.check_now() is None
    assert "503" in (checker.last_error or "")
