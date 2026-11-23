"""922 Production Packets opens the standard steps window (v1.15.0).

Asked for 2026-11-23: the app was the one multi-step 922 app with no tick-box
window. Its second half was a switch in Settings > Apps, so going from the
first run to the second meant leaving the app to flip it, and remembering to
flip it back before the next batch.

What is pinned here:
- the window lists the three steps, and step 2 starts unticked on every run;
- the ticks decide what runs, and nothing else does (the old setting is gone);
- closing the window, or ticking nothing, runs nothing and asks for no batch;
- a run that skipped the packet drawings never reports "0 tubes without a
  print" - nobody looked, and the report has to say so.
"""
import importlib.util
import json
import pathlib
import threading

import pytest

PLUGIN_DIR = (pathlib.Path(__file__).resolve().parents[2]
              / "plugins" / "922_production_packets")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location(
        "pp_steps_test", PLUGIN_DIR / "run.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Console:
    """A console that answers the steps window with fixed ticks (or a cancel)."""

    def __init__(self, ticks, sub=None):
        self.ticks = ticks
        self.sub = sub              # {child key: bool} override, else defaults
        self.groups = None
        self.kwargs = None

    def request_grouped_toggles(self, groups, **kwargs):
        self.groups, self.kwargs = groups, kwargs
        if self.ticks is None:
            return None
        return {g["key"]: {
            "enabled": g["key"] in self.ticks,
            "options": {c["key"]: (self.sub or {}).get(c["key"], c["checked"])
                        for c in g.get("children", [])}}
                for g in groups}


@pytest.fixture
def rig(mod, monkeypatch, tmp_path):
    """run() with the batch pick and both halves replaced by recorders."""
    calls = []
    seen_options = []
    batch = tmp_path / "Batch 999"
    batch.mkdir()

    def pick(params, override=""):
        calls.append(("pick",))
        return "999", str(batch)

    def step_one(params, log, batch_no, batch_path, root, progress, cancel,
                 do_list, do_packets, more_to_come=False):
        calls.append(("one", do_list, do_packets, more_to_come))

    def step_two(params, settings, log, batch_no, batch_path, root, progress,
                 cancel, options=None):
        calls.append(("two",))
        seen_options.append(options)
        return True

    monkeypatch.setattr(mod.sdk, "resolve_922_root", lambda override="": tmp_path)
    monkeypatch.setattr(mod.sdk, "request_922_batch_folder", pick)
    monkeypatch.setattr(mod, "_step_one", step_one)
    monkeypatch.setattr(mod, "_run_step_two", step_two)

    def go(ticks, settings=None, sub=None):
        console = _Console(ticks, sub)
        cancel = threading.Event()
        mod.run({"console": console, "log": lambda *_a: None,
                 "settings": settings or {}}, lambda _p: None, cancel)
        return console, cancel

    go.options = seen_options
    return go, calls


# ── the window itself ───────────────────────────────────────────────────────

def test_the_window_lists_the_three_steps_in_run_order(mod):
    keys = [g["key"] for g in mod._dialog_groups()]
    assert keys == [mod.STEP_LIST, mod.STEP_PACKETS, mod.STEP_BINDERS]


def test_step_two_starts_unticked_and_the_first_half_ticked(mod):
    ticked = {g["key"]: g["checked"] for g in mod._dialog_groups()}
    assert ticked == {mod.STEP_LIST: True, mod.STEP_PACKETS: True,
                      mod.STEP_BINDERS: False}


def test_the_window_is_not_sticky(mod):
    """Last run's ticks are the wrong default for the next batch's first run:
    step 2 ticked there fails for want of 1Ds nobody has nested yet."""
    source = (PLUGIN_DIR / "run.py").read_text(encoding="utf-8")
    assert "remember_as=" not in source


def test_run_opens_the_window_with_the_standard_wording(rig, mod):
    go, _calls = rig
    console, _cancel = go({mod.STEP_LIST})
    assert [g["key"] for g in console.groups] == [
        mod.STEP_LIST, mod.STEP_PACKETS, mod.STEP_BINDERS]
    assert console.kwargs["run_button_text"] == "Run Selected"
    assert console.kwargs["window_title"] == "922 Production Packets"


# ── the ticks decide what runs ──────────────────────────────────────────────

def test_the_default_ticks_run_the_first_half_only(rig, mod):
    go, calls = rig
    go({mod.STEP_LIST, mod.STEP_PACKETS})
    assert calls == [("pick",), ("one", True, True, False)]


def test_only_step_two_ticked_runs_only_step_two(rig, mod):
    go, calls = rig
    go({mod.STEP_BINDERS})
    assert calls == [("pick",), ("two",)]


def test_the_cutting_list_can_be_left_alone(rig, mod):
    """The reason to untick it: lengths typed into the workbook by hand."""
    go, calls = rig
    go({mod.STEP_PACKETS})
    assert calls == [("pick",), ("one", False, True, False)]


def test_everything_ticked_runs_the_first_half_then_the_second(rig, mod):
    go, calls = rig
    go({mod.STEP_LIST, mod.STEP_PACKETS, mod.STEP_BINDERS})
    assert calls == [("pick",), ("one", True, True, True), ("two",)]


def test_the_old_settings_switch_no_longer_decides_anything(rig, mod):
    """A profile that still carries the retired switch as ON must not be
    thrown into step 2: the window is the only thing that picks the steps."""
    go, calls = rig
    go({mod.STEP_LIST, mod.STEP_PACKETS},
       settings={"production_run_binders": True})
    assert calls == [("pick",), ("one", True, True, False)]


def test_the_retired_switch_is_out_of_the_manifest():
    manifest = json.loads(
        (PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    keys = [f["key"] for f in manifest["settings"]["fields"]]
    assert "production_run_binders" not in keys
    source = (PLUGIN_DIR / "run.py").read_text(encoding="utf-8")
    assert "production_run_binders" not in source


# ── backing out runs nothing ────────────────────────────────────────────────

def test_closing_the_window_runs_nothing_and_asks_for_no_batch(rig):
    go, calls = rig
    _console, cancel = go(None)
    assert calls == []
    assert cancel.is_set()


def test_ticking_nothing_runs_nothing_and_asks_for_no_batch(rig):
    go, calls = rig
    _console, cancel = go(set())
    assert calls == []
    assert cancel.is_set()


# ── step 2's own ticks: one per thing it builds ─────────────────────────────

def test_step_two_lists_what_it_builds_and_the_first_half_has_no_options(mod):
    groups = {g["key"]: g for g in mod._dialog_groups()}
    assert groups[mod.STEP_LIST]["children"] == []
    assert groups[mod.STEP_PACKETS]["children"] == []
    children = groups[mod.STEP_BINDERS]["children"]
    assert [c["key"] for c in children] == [
        mod.STEP2_1DS, mod.STEP2_COVERS, mod.STEP2_BIND]
    assert all(c["checked"] for c in children)
    # the two folder rows are named after the folders on disk
    assert children[0]["label"].startswith(mod.MARKED_FOLDER)
    assert children[1]["label"].startswith(mod.COVERS_FOLDER)


def test_the_ticks_under_step_two_reach_step_two(rig, mod):
    go, calls = rig
    go({mod.STEP_BINDERS}, sub={mod.STEP2_COVERS: False})
    assert calls == [("pick",), ("two",)]
    assert go.options[-1] == {mod.STEP2_1DS: True, mod.STEP2_COVERS: False,
                              mod.STEP2_BIND: True}


def test_step_two_with_nothing_under_it_selected_is_not_run(rig, mod):
    go, calls = rig
    nothing = {mod.STEP2_1DS: False, mod.STEP2_COVERS: False,
               mod.STEP2_BIND: False}
    _console, cancel = go({mod.STEP_BINDERS}, sub=nothing)
    assert calls == [] and cancel.is_set()

    go({mod.STEP_LIST, mod.STEP_BINDERS}, sub=nothing)
    # the first half runs alone, and ends with its own "what next" note
    assert calls == [("pick",), ("one", True, False, False)]


@pytest.fixture
def two(mod, monkeypatch, tmp_path):
    """_step_two with every reader and writer replaced by a recorder.

    Two packets: 1.1 on pallet 1 and SAW.1. Returns (call, seen, dirs) where
    `seen` counts what was asked for and written.
    """
    batch = tmp_path / "Batch 999"
    packets_dir = (batch / "Batch 999 - Documentation" / mod.PACKETS_FOLDER
                   / mod.PACKETS_SUBFOLDER)
    run_dir = packets_dir / mod.rs.RUN_FOLDER
    packets = {
        "1.1": {"serial": "218019941", "pallet": "1",
                "material": "HSS 2.0 X 2.0 X 0.188 NOM"},
        "SAW.1": {"serial": "218002101", "pallet": mod.SAW_PALLET,
                  "material": "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"},
    }
    seen = {"asked": 0, "annotated": [], "covers": [], "bound": {}}

    def ask(params, title, start=""):
        seen["asked"] += 1
        return str(tmp_path / "my 1ds")

    def annotate(src, dest, info, saw, log):
        seen["annotated"].append(dest.name)
        return ["drop blank"]

    def cover_pdf(template, dest, *args, **kwargs):
        seen["covers"].append(dest.name)
        return dest

    def bind(dest, pages, log):
        seen["bound"][dest.name] = [p.name for p in pages]
        return (dest, len(pages)) if pages else None

    monkeypatch.setattr(mod.rs, "read_cutting_list", lambda path, log: packets)
    monkeypatch.setattr(mod.sdk, "request_directory", ask)
    monkeypatch.setattr(mod.rs, "read_tracker", lambda *a: {})
    monkeypatch.setattr(mod.rs, "match_1ds", lambda folder, pk, log: {
        "1.1": pathlib.Path("1.1.pdf"), "SAW.1": pathlib.Path("SAW.1.pdf")})
    monkeypatch.setattr(mod.rs, "annotate", annotate)
    monkeypatch.setattr(mod, "_organizer", lambda *a: tmp_path / "org.xlsx")
    monkeypatch.setattr(mod, "read_cover_blocks", lambda path, log: {
        "1": {"listing": [], "materials": [
            "HSS 2.0 X 2.0 X 0.188 NOM",
            "HSS 5.0 X 5.0 X 0.50 NOM (SAW CUT)"]}})
    monkeypatch.setattr(mod.rs, "cover_pdf", cover_pdf)
    monkeypatch.setattr(mod.rs, "packet_drawings", lambda folder: {})
    monkeypatch.setattr(mod.rs, "bind", bind)

    def call(options):
        return mod._step_two({}, {}, lambda *_a: None, "999", batch, tmp_path,
                             lambda _p: None, threading.Event(), options)

    return call, seen, (run_dir / mod.MARKED_FOLDER,
                        run_dir / mod.COVERS_FOLDER)


def _only(mod, *on):
    return {key: key in on
            for key in (mod.STEP2_1DS, mod.STEP2_COVERS, mod.STEP2_BIND)}


def test_step_two_with_everything_selected_builds_all_three(two):
    call, seen, _dirs = two
    _run_dir, written, have, total = call(None)
    assert seen["asked"] == 1
    assert sorted(seen["annotated"]) == ["1.1.pdf", "SAW.1.pdf"]
    assert sorted(seen["covers"]) == ["_1.pdf", "_SAW.pdf"]
    assert seen["bound"] == {"PALLET 1.pdf": ["_1.pdf", "1.1.pdf"],
                             "SAW TUBES.pdf": ["_SAW.pdf", "SAW.1.pdf"]}
    assert (have, total, len(written)) == (2, 2, 2)


def test_cover_sheets_alone_ask_for_no_1ds_and_bind_nothing(two, mod):
    call, seen, _dirs = two
    _run_dir, written, have, _total = call(_only(mod, mod.STEP2_COVERS))
    assert seen["asked"] == 0
    assert seen["annotated"] == [] and seen["bound"] == {}
    assert sorted(seen["covers"]) == ["_1.pdf", "_SAW.pdf"]
    # no 1D was looked at, so there is no "N of M have a 1D" to report
    assert have is None and written == []


def test_marked_up_1ds_alone_build_no_covers_and_no_binders(two, mod):
    call, seen, _dirs = two
    _run_dir, written, have, _total = call(_only(mod, mod.STEP2_1DS))
    assert seen["asked"] == 1
    assert sorted(seen["annotated"]) == ["1.1.pdf", "SAW.1.pdf"]
    assert seen["covers"] == [] and seen["bound"] == {}
    assert have == 2 and written == []


def test_binders_alone_use_what_is_already_in_the_two_folders(two, mod):
    """Re-binding after fixing a cover by hand must not rebuild that cover,
    or the hand fix is gone."""
    call, seen, (marked_dir, covers_dir) = two
    marked_dir.mkdir(parents=True)
    covers_dir.mkdir(parents=True)
    (marked_dir / "1.1.pdf").write_bytes(b"x")
    (covers_dir / "_1.pdf").write_bytes(b"x")

    _run_dir, written, have, total = call(_only(mod, mod.STEP2_BIND))
    assert seen["asked"] == 0
    assert seen["annotated"] == [] and seen["covers"] == []
    assert seen["bound"]["PALLET 1.pdf"] == ["_1.pdf", "1.1.pdf"]
    # SAW.1 has no marked-up 1D on disk: counted, so the run can flag it
    assert (have, total, len(written)) == (1, 2, 1)


# ── the report on a run that skipped the packet drawings ────────────────────

def _entry(part):
    return {"part": part, "order": "FL100001", "serial": "218019941",
            "desc": "2.0 X 2.0 X 0.188 NOM", "packet": "1.1", "pallet": "1",
            "length": 12.5, "qty": 1, "review": False, "source": "assembly"}


def _report_text(mod, tmp_path, no_sheet):
    import fitz
    dest = tmp_path / "Production Packets Report (TechDeck) - Batch 999.pdf"
    mod._write_report(dest, "999", [("218019941", [_entry("H1-H2-3A")])],
                      no_sheet, [], lambda *_a: None)
    with fitz.open(str(dest)) as doc:
        return " ".join(page.get_text() for page in doc)


def test_a_run_without_packet_drawings_does_not_report_zero_missing_prints(
        mod, tmp_path):
    text = _report_text(mod, tmp_path, None)
    assert mod.NOT_BOUND in text


def test_a_run_with_packet_drawings_still_reports_the_count(mod, tmp_path):
    text = _report_text(mod, tmp_path, [])
    assert mod.NOT_BOUND not in text
