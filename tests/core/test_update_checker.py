"""Tests for update version/mandatory logic and the SHA-256 verify helpers."""

import hashlib

from techdeck.core.update_checker import UpdateInfo
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
