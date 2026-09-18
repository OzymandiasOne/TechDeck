"""Windows MAX_PATH (260 char) resilience — Hard Rule 14.

The Pilot Program tree burns ~190 characters before a plugin adds anything, so
a descriptive output filename tips the write past Win32's 260-char cap and the
save dies with ``FileNotFoundError [Errno 2] No such file or directory`` on a
folder that plainly exists (911 SSPO Award Review at 277 chars,
DESKTOP-DD35L5F, 2026-08-21).

These tests pin the escape hatch (`sdk.long_path`) and the helpers that must
use it, and they build genuinely over-length paths so a regression fails here
rather than on a user's machine.
"""

import os

import pytest

from techdeck.core import plugin_sdk as sdk

WIN_ONLY = pytest.mark.skipif(os.name != "nt", reason="MAX_PATH is a Win32 cap")

B = chr(92)                 # backslash, spelled out so escaping can't bite
DOS_PREFIX = B * 2 + "?" + B
UNC_PREFIX = DOS_PREFIX + "UNC" + B

# The real path from the bug report (277 chars).
REPORTED_FAILURE = (
    "C:" + B + "Users" + B + "MattOverfield" + B + "American Steel & Alum" + B
    + "Communication site - Electric Boat ASA Docs" + B + "Pilot Program" + B
    + "1. 1000129724 - Strategic Partnership, Steel Processing Offload" + B
    + "VTDX Award Records" + B + "1000129724 SSPO Award 12" + B
    + "911 SSPO AWARD REVIEW - 1000129724 SSPO Award 12 - 2026-08-21.xlsx"
)


def _deep_dir(tmp_path, target_len=300):
    """A directory under tmp_path whose full path exceeds `target_len`."""
    d = tmp_path
    while len(str(d)) < target_len:
        d = d / ("d" * 40)
    return d


# ── long_path() ──────────────────────────────────────────────────────────────

def test_reported_failure_path_is_actually_over_the_cap():
    assert len(REPORTED_FAILURE) > 260


@WIN_ONLY
def test_short_paths_are_returned_untouched():
    short = "C:" + B + "Dev" + B + "TechDeck" + B + "out.xlsx"
    assert sdk.long_path(short) == short


@WIN_ONLY
def test_long_path_gets_the_extended_length_prefix():
    got = sdk.long_path(REPORTED_FAILURE)
    assert got.startswith(DOS_PREFIX)
    assert got.endswith(".xlsx")


@WIN_ONLY
def test_long_path_is_idempotent():
    once = sdk.long_path(REPORTED_FAILURE)
    assert sdk.long_path(once) == once


@WIN_ONLY
def test_unc_share_uses_the_unc_spelling():
    unc = B * 2 + "server" + B + "share" + ("" + B + "z" * 30) * 9
    assert len(unc) > 260
    got = sdk.long_path(unc)
    assert got.startswith(UNC_PREFIX)
    assert "server" + B + "share" in got


@WIN_ONLY
def test_relative_segments_are_normalized_away(tmp_path):
    """The prefix disables path normalization, so long_path must normalize
    first — a surviving '..' would make Win32 reject the path outright."""
    messy = str(_deep_dir(tmp_path) / ".." / "out.xlsx")
    got = sdk.long_path(messy)
    assert got.startswith(DOS_PREFIX)
    assert ".." not in got


def test_long_path_accepts_path_objects(tmp_path):
    assert sdk.long_path(tmp_path).endswith(str(tmp_path)[-10:])


# ── ensure_dir() ─────────────────────────────────────────────────────────────

@WIN_ONLY
def test_ensure_dir_creates_a_tree_past_max_path(tmp_path):
    """os.makedirs() walks up to the drive root and chokes on the '\\\\?' head,
    which is exactly why ensure_dir exists."""
    deep = _deep_dir(tmp_path)
    assert len(str(deep)) > 260
    sdk.ensure_dir(deep)
    assert os.path.isdir(sdk.long_path(deep))


def test_ensure_dir_is_idempotent(tmp_path):
    d = tmp_path / "a" / "b"
    sdk.ensure_dir(d)
    sdk.ensure_dir(d)
    assert d.is_dir()


# ── save_workbook() ──────────────────────────────────────────────────────────

@WIN_ONLY
def test_save_workbook_writes_past_max_path(tmp_path):
    """The regression itself: openpyxl's zipfile write on a 277-char path."""
    openpyxl = pytest.importorskip("openpyxl")
    out = _deep_dir(tmp_path) / "911 SSPO AWARD REVIEW - long name - 2026-08-21.xlsx"
    assert len(str(out)) > 260

    wb = openpyxl.Workbook()
    wb.active["A1"] = "hello"
    sdk.save_workbook(wb, out)

    assert os.path.isfile(sdk.long_path(out))
    reopened = openpyxl.load_workbook(sdk.long_path(out))
    assert reopened.active["A1"].value == "hello"


def test_save_workbook_creates_the_parent_folder(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "brand" / "new" / "book.xlsx"
    sdk.save_workbook(openpyxl.Workbook(), out)
    assert out.is_file()


def test_save_workbook_reports_a_locked_destination(tmp_path):
    """A workbook the user still has open in Excel must produce the plain
    'close it and run again' instruction, not a raw Errno 13."""
    class _Locked:
        def save(self, path):
            raise PermissionError(13, "Permission denied")

    with pytest.raises(sdk.UserFacingError) as err:
        sdk.save_workbook(_Locked(), tmp_path / "book.xlsx")
    assert "open in another program" in err.value.problem


# ── the helpers that must route through long_path ────────────────────────────

@WIN_ONLY
def test_copy_resilient_survives_a_long_destination(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("payload", encoding="utf-8")
    dest_dir = sdk.ensure_dir(_deep_dir(tmp_path))
    dest = dest_dir / "copied.txt"
    assert len(str(dest)) > 260

    sdk.copy_resilient(src, dest)
    with open(sdk.long_path(dest), encoding="utf-8") as fh:
        assert fh.read() == "payload"


@WIN_ONLY
def test_load_workbook_resilient_reads_a_long_path(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = sdk.ensure_dir(_deep_dir(tmp_path)) / "book.xlsx"
    assert len(str(out)) > 260
    sdk.save_workbook(openpyxl.Workbook(), out)

    wb = sdk.load_workbook_resilient(out)
    assert wb.active is not None


@WIN_ONLY
def test_save_pdf_atomic_survives_a_long_path(tmp_path):
    fitz = pytest.importorskip("fitz")
    dest = sdk.ensure_dir(_deep_dir(tmp_path)) / "stamped.pdf"
    assert len(str(dest)) > 260

    doc = fitz.open()
    doc.new_page()
    sdk.save_pdf_atomic(doc, dest)

    assert os.path.isfile(sdk.long_path(dest))
    # No stray temp PDF left beside it.
    leftovers = [n for n in os.listdir(sdk.long_path(dest.parent))
                 if n.lower().endswith(".pdf") and n != dest.name]
    assert leftovers == []


@WIN_ONLY
def test_merge_pdfs_survives_a_long_path(tmp_path):
    fitz = pytest.importorskip("fitz")
    deep = sdk.ensure_dir(_deep_dir(tmp_path))
    parts = []
    for i in range(2):
        p = deep / f"part{i}.pdf"
        d = fitz.open()
        d.new_page()
        d.save(sdk.long_path(p))
        d.close()
        parts.append(p)

    out = deep / "merged.pdf"
    assert len(str(out)) > 260
    sdk.merge_pdfs(parts, out)

    merged = fitz.open(sdk.long_path(out))
    assert merged.page_count == 2
    merged.close()


@WIN_ONLY
def test_is_cloud_placeholder_does_not_blow_up_on_a_long_path(tmp_path):
    """A stat() that silently fails on an over-length path would make every
    long-path file look like a normal local file — the check must still run."""
    out = sdk.ensure_dir(_deep_dir(tmp_path)) / "f.txt"
    with open(sdk.long_path(out), "w", encoding="utf-8") as fh:
        fh.write("x")
    assert sdk.is_cloud_placeholder(out) is False


# ── the prefix is genuinely handed to the underlying call ────────────────────
#
# This dev box has LongPathsEnabled=1, so a helper that FORGOT long_path would
# still pass the round-trip tests above and only fail on a user's machine.
# These spies pin the actual argument instead of the outcome.

@WIN_ONLY
def test_copy_resilient_hands_shutil_a_prefixed_destination(tmp_path, monkeypatch):
    seen = {}

    def spy(src, dest, *a, **k):
        seen["src"], seen["dest"] = src, dest

    monkeypatch.setattr(sdk.shutil, "copy2", spy)
    src = tmp_path / "s.txt"
    src.write_text("x", encoding="utf-8")
    sdk.copy_resilient(src, _deep_dir(tmp_path) / "d.txt")

    assert str(seen["dest"]).startswith(DOS_PREFIX)


@WIN_ONLY
def test_load_workbook_resilient_hands_openpyxl_a_prefixed_path(tmp_path, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    seen = {}

    def spy(path, **kwargs):
        seen["path"] = path
        return "wb"

    monkeypatch.setattr(openpyxl, "load_workbook", spy)
    long_target = _deep_dir(tmp_path) / "book.xlsx"
    assert sdk.load_workbook_resilient(long_target) == "wb"
    assert str(seen["path"]).startswith(DOS_PREFIX)


@WIN_ONLY
def test_save_workbook_hands_openpyxl_a_prefixed_path(tmp_path):
    seen = {}

    class _Spy:
        def save(self, path):
            seen["path"] = path

    out = _deep_dir(tmp_path) / "book.xlsx"
    sdk.save_workbook(_Spy(), out)
    assert str(seen["path"]).startswith(DOS_PREFIX)
    # ...and the folder was created for it.
    assert os.path.isdir(sdk.long_path(out.parent))


@WIN_ONLY
def test_short_paths_never_get_the_prefix(tmp_path):
    """The prefix is stricter than a normal path (no relative segments, no
    forward slashes), so it must stay off anything that does not need it."""
    seen = {}

    class _Spy:
        def save(self, path):
            seen["path"] = path

    out = tmp_path / "book.xlsx"
    assert len(str(out)) < 240
    sdk.save_workbook(_Spy(), out)
    assert not str(seen["path"]).startswith(DOS_PREFIX)


# ── exists / is_file / is_dir ────────────────────────────────────────────────

@WIN_ONLY
def test_predicates_see_a_file_past_max_path(tmp_path):
    """The silent member of the family: the raw calls answer False for a file
    that is sitting right there, so a 'create it if missing' guard fires and
    overwrites real work."""
    deep = sdk.ensure_dir(_deep_dir(tmp_path))
    f = deep / "already-here.xlsx"
    with open(sdk.long_path(f), "w", encoding="utf-8") as fh:
        fh.write("real work")
    assert len(str(f)) > 260

    assert sdk.exists(f) is True
    assert sdk.is_file(f) is True
    assert sdk.is_dir(f) is False
    assert sdk.is_dir(deep) is True


def test_predicates_agree_with_pathlib_on_short_paths(tmp_path):
    f = tmp_path / "f.txt"
    assert (sdk.exists(f), sdk.is_file(f), sdk.is_dir(f)) == (False, False, False)
    f.write_text("x", encoding="utf-8")
    assert (sdk.exists(f), sdk.is_file(f), sdk.is_dir(f)) == (True, True, False)
    assert (sdk.exists(tmp_path), sdk.is_dir(tmp_path)) == (True, True)
