"""Tests for the ship-readiness gate's E11/E12/E13/E14 checks.

E11: the drone loadout menu (My Stuff -> SET UP) is discovered from plugin
manifests (sentry_mode.compatible_plugins) - there is no second list - so a
plugin that gains a file/folder picker without gaining the sentry_drone
settings field silently never appears there. E11 makes that unshippable.

E12: fitz cannot save in place (Hard Rule 5) - a raw .save() on a doc opened
from a file must go through sdk.save_pdf_atomic. The hand-rolled version
shipped the bug class once (922 Pallet Stamper kept a private copy that
missed the SDK's later fixes).

E13: raw workbook/PDF content reads die on OneDrive cloud placeholders and
files open in Excel (Hard Rule 13) - the resilient SDK loaders exist for
every case and are cheap no-ops on healthy local files, so there is no
legitimate raw-read call site.

E14: Windows fails a file operation past 260 characters (Hard Rule 14) with a
"No such file or directory" that names a folder which plainly exists. The
Pilot Program tree is already ~190 characters deep, so this is one long output
filename away on every plugin - 911 SSPO Award Review hit it at 277.
"""

from __future__ import annotations

import ast
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_ship_readiness as C  # noqa: E402


def _calls(src: str) -> list[str]:
    return C.find_drone_picker_calls(ast.parse(textwrap.dedent(src)))


def test_detects_every_picker_call_name():
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick")
            sdk.request_file(params, "pick")
            sdk.pick_directory_gui(params, "pick")
            sdk.pick_file_gui(params, "pick")
            sdk.request_nest_targets(params, "pick", "start")
    """
    assert sorted(_calls(src)) == ["pick_directory_gui", "pick_file_gui",
                                   "request_directory", "request_file",
                                   "request_nest_targets"]


def test_style_empty_string_is_exempt():
    # style="" forces the plain dialog - that prompt never uses the drone.
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick", style="")
    """
    assert _calls(src) == []


def test_style_none_still_counts():
    # style=None is the default "ask sentry_style(params)" path - drone-capable.
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_directory(params, "pick", style=None)
    """
    assert _calls(src) == ["request_directory"]


def test_main_guard_harness_is_skipped():
    src = """
        if __name__ == "__main__":
            sdk.request_directory({}, "pick")
    """
    assert _calls(src) == []


def test_unrelated_calls_not_flagged():
    src = """
        def run(params, progress_callback, cancel_event):
            sdk.request_batch_number(params, "Enter batch number:")
            sdk.request_text(params, "Which line?")
    """
    assert _calls(src) == []


# --- end-to-end through check_plugin -----------------------------------------

_MANIFEST = {
    "id": "922_fake_picker",
    "name": "922 Fake Picker",
    "family": "922",
    "settings": {"fields": []},
}

_RUN = textwrap.dedent("""
    def run(params, progress_callback, cancel_event):
        sdk.request_directory(params, "Select the batch folder")
""")

_DRONE_FIELD = {
    "key": "sentry_drone",
    "type": "boolean",
    "label": "Sentry Drone mode",
    "default": False,
    "hidden_unless_unlocked": "toy_sentry_drone",
}


def _check(tmp_path: Path, manifest: dict) -> list[str]:
    plugin = tmp_path / manifest["id"]
    plugin.mkdir()
    (plugin / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin / "run.py").write_text(_RUN, encoding="utf-8")
    errors: list[str] = []
    C.check_plugin(plugin, set(), set(), [], {}, errors, [])
    return [e for e in errors if "sentry_drone" in e]


def test_picker_without_drone_field_fails(tmp_path):
    assert _check(tmp_path, dict(_MANIFEST)) != []


def test_picker_with_drone_field_passes(tmp_path):
    manifest = dict(_MANIFEST)
    manifest["settings"] = {"fields": [dict(_DRONE_FIELD)]}
    assert _check(tmp_path, manifest) == []


# --- E12: raw fitz in-place saves ---------------------------------------------

def _fitz_saves(src: str) -> list[int]:
    return C.find_raw_fitz_saves(ast.parse(textwrap.dedent(src)))


def test_e12_flags_save_on_doc_opened_from_file():
    src = """
        def stamp(pdf_path):
            doc = fitz.open(pdf_path)
            doc.save(pdf_path)
    """
    assert len(_fitz_saves(src)) == 1


def test_e12_flags_the_handrolled_tmp_replace_idiom():
    # The exact shape 922 Pallet Stamper carried: save to tmp, replace later.
    src = """
        def stamp(pdf_path):
            doc = fitz.open(pdf_path)
            doc.save(pdf_path + ".tmp", incremental=False)
            os.replace(pdf_path + ".tmp", pdf_path)
    """
    assert len(_fitz_saves(src)) == 1


def test_e12_new_empty_doc_is_exempt():
    # fitz.open() with no args = a brand-new in-memory doc; saving it to a
    # new path holds no handle on any source file (merge/report builders).
    src = """
        def build_report(out_path):
            doc = fitz.open()
            doc.new_page()
            doc.save(out_path)
    """
    assert _fitz_saves(src) == []


def test_e12_stream_doc_is_exempt():
    src = """
        def from_bytes(data, out_path):
            doc = fitz.open(stream=data, filetype="pdf")
            doc.save(out_path)
    """
    assert _fitz_saves(src) == []


def test_e12_non_fitz_save_not_flagged():
    src = """
        def write(out_path):
            wb = Workbook()
            wb.save(out_path)
    """
    assert _fitz_saves(src) == []


def test_e12_main_guard_harness_is_skipped():
    src = """
        doc = fitz.open("x.pdf")
        if __name__ == "__main__":
            doc.save("x.pdf")
    """
    assert _fitz_saves(src) == []


# --- E13: raw Excel content reads ---------------------------------------------

def _raw_reads(src: str) -> list[str]:
    return [name for _ln, name, _repl
            in C.find_raw_content_reads(ast.parse(textwrap.dedent(src)))]


def test_e13_flags_each_raw_read_with_its_replacement():
    src = """
        def read(path):
            wb = load_workbook(path)
            wb2 = openpyxl.load_workbook(path)
            df = pd.read_excel(path)
            xls = pd.ExcelFile(path)
    """
    tree = ast.parse(textwrap.dedent(src))
    hits = C.find_raw_content_reads(tree)
    assert [h[1] for h in hits] == ["load_workbook", "load_workbook",
                                    "read_excel", "ExcelFile"]
    assert all(h[2].startswith("sdk.") for h in hits)


def test_e13_resilient_calls_not_flagged():
    src = """
        def read(path, log):
            wb = sdk.load_workbook_resilient(path, log=log)
            df = sdk.read_excel_resilient(path, log=log)
            xls = sdk.open_excel_resilient(path, log=log)
    """
    assert _raw_reads(src) == []


def test_e13_read_excel_on_resilient_handle_is_exempt():
    # 922 Batch Repeater's MPL pattern: the FILE was opened resiliently once;
    # later pd.read_excel calls read from the in-memory ExcelFile handle.
    src = """
        def read(path, log):
            xls = sdk.open_excel_resilient(path, log=log)
            raw = pd.read_excel(xls, sheet_name="PO", header=None)
            df = pd.read_excel(xls, sheet_name="PO", header=2)
    """
    assert _raw_reads(src) == []


def test_e13_read_excel_on_a_plain_path_still_flagged():
    src = """
        def read(path, log):
            xls = sdk.open_excel_resilient(path, log=log)
            df = pd.read_excel(path)   # the PATH, not the handle
    """
    assert _raw_reads(src) == ["read_excel"]


# --- E13: PDF opens without hydration -----------------------------------------

def _pdf_opens(src: str) -> list[str]:
    return [name for _ln, name
            in C.find_unhydrated_pdf_opens(ast.parse(textwrap.dedent(src)))]


def test_e13_flags_fitz_open_without_ensure_local():
    src = """
        def read(pdf_path):
            doc = fitz.open(pdf_path)
    """
    assert _pdf_opens(src) == ["fitz.open"]


def test_e13_ensure_local_in_same_function_passes():
    src = """
        def read(pdf_path):
            sdk.ensure_local(pdf_path)
            doc = fitz.open(pdf_path)
    """
    assert _pdf_opens(src) == []


def test_e13_guard_in_another_function_does_not_cover():
    # The guard must sit at the read site - hydration in the CALLER is
    # invisible here and ensure_local is a cheap no-op on local files,
    # so requiring it next to the open is always safe.
    src = """
        def caller(pdf_path):
            sdk.ensure_local(pdf_path)
            helper(pdf_path)

        def helper(pdf_path):
            doc = fitz.open(pdf_path)
    """
    assert _pdf_opens(src) == ["fitz.open"]


def test_e13_pdfreader_same_rules():
    flagged = """
        def read(pdf_path):
            reader = PdfReader(pdf_path)
    """
    guarded = """
        def read(pdf_path):
            sdk.ensure_local(pdf_path)
            reader = PdfReader(pdf_path)
    """
    assert _pdf_opens(flagged) == ["PdfReader"]
    assert _pdf_opens(guarded) == []


def test_e13_new_empty_fitz_doc_never_needs_hydration():
    src = """
        def build():
            doc = fitz.open()
    """
    assert _pdf_opens(src) == []


# ── E14: MAX_PATH ───────────────────────────────────────────────────────────

def _max_path(src: str) -> list[str]:
    return [what for _ln, what, _fix
            in C.find_max_path_risks(ast.parse(textwrap.dedent(src)))]


def test_e14_flags_raw_mkdir_and_makedirs():
    src = """
        def prep(out_dir):
            out_dir.mkdir(parents=True, exist_ok=True)
            os.makedirs(out_dir / "sub", exist_ok=True)
    """
    assert _max_path(src) == ["mkdir()", "makedirs()"]


def test_e14_ensure_dir_is_the_accepted_form():
    src = """
        def prep(out_dir):
            sdk.ensure_dir(out_dir)
    """
    assert _max_path(src) == []


def test_e14_flags_a_raw_workbook_save():
    src = """
        def write(out_path):
            wb = openpyxl.Workbook()
            wb.save(out_path)
    """
    assert _max_path(src) == ["Workbook.save()"]


def test_e14_flags_a_raw_save_on_a_loaded_workbook():
    src = """
        def edit(path):
            wb = sdk.load_workbook_resilient(path)
            wb.save(path)
    """
    assert _max_path(src) == ["Workbook.save()"]


def test_e14_sdk_save_workbook_passes():
    src = """
        def write(out_path):
            wb = openpyxl.Workbook()
            sdk.save_workbook(wb, out_path)
    """
    assert _max_path(src) == []


def test_e14_explicit_long_path_wrap_passes():
    """Some callers do their own lock handling around the save and must keep
    it - wrapping the path themselves is the documented escape hatch."""
    src = """
        def write(out_path):
            wb = openpyxl.Workbook()
            try:
                wb.save(sdk.long_path(out_path))
            except PermissionError:
                wb.save(sdk.long_path(out_path.with_suffix(".2.xlsx")))
    """
    assert _max_path(src) == []


def test_e14_flags_raw_shutil_path_ops():
    src = """
        def move_things(src, dest):
            shutil.copy2(src, dest)
            shutil.move(src, dest)
            shutil.rmtree(dest)
            shutil.copytree(src, dest, dirs_exist_ok=True)
    """
    assert _max_path(src) == ["shutil.copy2()", "shutil.move()",
                              "shutil.rmtree()", "shutil.copytree()"]


def test_e14_wrapped_shutil_passes():
    src = """
        def move_things(src, dest):
            shutil.copy2(sdk.long_path(src), sdk.long_path(dest))
            shutil.rmtree(sdk.long_path(dest))
    """
    assert _max_path(src) == []


def test_e14_half_wrapped_shutil_is_still_flagged():
    src = """
        def move_things(src, dest):
            shutil.copy2(sdk.long_path(src), dest)
    """
    assert _max_path(src) == ["shutil.copy2()"]


def test_e14_copy_resilient_passes():
    src = """
        def stage(src, dest, log):
            sdk.copy_resilient(src, dest, log)
    """
    assert _max_path(src) == []


def test_e14_bundled_template_paths_are_exempt():
    """A plugin-bundled file lives under the install path, which is short by
    construction - wrapping it would be noise."""
    src = """
        def seed(dest):
            shutil.copy2(Path(__file__).with_name("template.xlsx"),
                         sdk.long_path(dest))
    """
    assert _max_path(src) == []


def test_e14_non_shutil_save_not_flagged():
    src = """
        def draw(path):
            painter.save()
            settings.save()
    """
    assert _max_path(src) == []


def test_e14_main_guard_harness_is_skipped():
    src = """
        if __name__ == "__main__":
            out = Path("x")
            out.mkdir()
            shutil.copy2("a", "b")
    """
    assert _max_path(src) == []


def test_e14_flags_silent_path_predicates():
    """These answer False instead of raising, so the guard they gate fires and
    the plugin overwrites work that was already there."""
    src = """
        def check(dest):
            if not dest.exists():
                make(dest)
            if dest.is_file() or dest.parent.is_dir():
                pass
    """
    # Two of them share a line, so compare as a set.
    assert sorted(_max_path(src)) == [".exists()", ".is_dir()", ".is_file()"]


def test_e14_sdk_predicates_pass():
    src = """
        def check(dest):
            if not sdk.exists(dest):
                make(dest)
            if sdk.is_file(dest) or sdk.is_dir(dest.parent):
                pass
    """
    assert _max_path(src) == []


def test_e14_predicate_with_arguments_is_not_a_path_check():
    """Path.exists() takes no arguments; a same-named call that does is some
    other object's method and must not be flagged."""
    src = """
        def check(store):
            if store.exists("key"):
                pass
    """
    assert _max_path(src) == []


def test_e14_the_whole_plugin_roster_is_clean():
    """The 2026-08-21 sweep: no plugin may reintroduce a raw long-path op."""
    offenders = []
    for run_py in sorted((ROOT / "plugins").rglob("run.py")):
        tree = ast.parse(run_py.read_text(encoding="utf-8"))
        for line_no, what, _fix in C.find_max_path_risks(tree):
            offenders.append(f"{run_py.parent.name}:{line_no} {what}")
    assert offenders == []
