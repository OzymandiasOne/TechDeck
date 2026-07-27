"""Tests for the DevKit Dev Board (source-only dev tool).

Data-layer tests use a temp state file; widget tests use the offscreen `qapp`
and stub `load_feedback` so they never read the maintainer's real telemetry
workbook.
"""

from tools.devkit.todo_board.model import (
    BoardStore, FeedbackEntry, FeedbackLoad,
)


def _entry(idx: int, which_feature: str, source: str) -> FeedbackEntry:
    return FeedbackEntry(
        key=f"{source}{idx}", title=f"suggestion {idx}", user="tester",
        date_iso=f"2026-07-2{idx}T09:00:00", which_feature=which_feature,
        version="0.8.6.9", orig_status="Needs Review", source=source)


def _load(feedback=(), archive=()) -> FeedbackLoad:
    return FeedbackLoad(feedback=list(feedback), archive=list(archive),
                        path=None, ok=True, message="stub")


# ---- registry --------------------------------------------------------------

def test_todo_board_is_default_devkit_page():
    from tools.devkit.registry import DEV_TOOLS
    assert DEV_TOOLS[0].key == "todo_board"        # mounts first => default page
    assert DEV_TOOLS[0].label == "Dev Board"


# ---- data layer ------------------------------------------------------------

def test_sync_routes_feedback_to_todo_and_archive_to_done(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    added = store.sync(_load(
        feedback=[_entry(1, "911 Setup", "feedback"), _entry(2, "Other", "feedback")],
        archive=[_entry(3, "922 Kitting", "archive")]))
    assert added == 3
    assert len(store.bucket("todo")["cards"]) == 2
    assert len(store.bucket("done")["cards"]) == 1
    # feedback label seeded from Which Feature
    todo_key = store.bucket("todo")["cards"][0]
    assert "911 Setup" in store.cards[todo_key]["labels"] or \
           "Other" in store.cards[todo_key]["labels"]


def test_sync_is_idempotent(tmp_path):
    load = _load(feedback=[_entry(1, "911 Setup", "feedback")])
    store = BoardStore(path=tmp_path / "b.json")
    assert store.sync(load) == 1
    assert BoardStore(path=tmp_path / "b.json").sync(load) == 0   # reloaded, no dupes


def test_newest_feedback_lands_on_top(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    store.sync(_load(feedback=[_entry(1, "A", "feedback"), _entry(5, "B", "feedback")]))
    top = store.bucket("todo")["cards"][0]
    assert store.cards[top]["date"] == "2026-07-25T09:00:00"   # idx 5 is newest


def test_move_card_reorder_contract(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    store.add_manual_card("todo", "C")
    kb = store.add_manual_card("todo", "B")
    ka = store.add_manual_card("todo", "A")   # add_manual inserts at 0 => [A, B, C]
    titles = lambda: [store.cards[k]["title"] for k in store.bucket("todo")["cards"]]
    assert titles() == ["A", "B", "C"]
    store.move_card(ka, "todo", 2)            # A to end among [B, C]
    assert titles() == ["B", "C", "A"]
    store.move_card(kb, "done", 0)            # cross-bucket
    assert store.bucket_of(kb)["id"] == "done"
    assert titles() == ["C", "A"]


def test_checklist_mutations(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    k = store.add_manual_card("todo", "task")
    store.add_checklist_item(k, "one")
    store.add_checklist_item(k, "two")
    store.toggle_checklist_item(k, 0)
    items = store.cards[k]["checklist"]
    assert [i["text"] for i in items] == ["one", "two"]
    assert items[0]["done"] is True
    store.remove_checklist_item(k, 0)
    assert [i["text"] for i in store.cards[k]["checklist"]] == ["two"]


def test_label_add_remove(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    k = store.add_manual_card("todo", "task")
    store.add_label(k, "bug")
    store.add_label(k, "bug")            # dedup
    assert store.cards[k]["labels"] == ["bug"]
    store.remove_label(k, "bug")
    assert store.cards[k]["labels"] == []


def test_delete_bucket_reassigns_cards(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    k = store.add_manual_card("done", "orphan-me")
    store.remove_bucket("done")
    assert store.bucket("done") is None
    assert store.bucket_of(k) is store.buckets[0]    # fell back to first bucket


def test_reconcile_files_orphan_cards(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    store.cards["ghost"] = {"title": "x", "checklist": [], "labels": []}
    store._reconcile()
    assert store.bucket_of("ghost") is not None      # placed, not lost


# ---- widgets ---------------------------------------------------------------

def test_label_color_mapping():
    from tools.devkit.todo_board.widgets import label_color
    assert label_color("911 Setup") == "#3B82F6"     # family color
    assert label_color("922 Kitting") == "#F59E0B"
    assert label_color("Other") == "#6B7280"         # neutral
    assert label_color("Custom Tag") == label_color("Custom Tag")   # stable


def test_task_card_renders_title_labels_checklist(qapp, tmp_path):
    from techdeck.ui.theme_manager import get_theme_manager
    from tools.devkit.todo_board.widgets import TaskCard, LabelChip
    store = BoardStore(path=tmp_path / "b.json")
    k = store.add_manual_card("todo", "Fix the thing")
    store.add_label(k, "911 Setup")
    store.add_checklist_item(k, "step")
    card = TaskCard(store, k, get_theme_manager().get_current_palette())
    card.show()
    qapp.processEvents()
    assert card._title.text() == "Fix the thing"
    assert card.findChildren(LabelChip)


def test_board_builds_with_stubbed_feedback(qapp, tmp_path, monkeypatch):
    from tools.devkit.todo_board import model
    from tools.devkit.todo_board import board as board_mod
    monkeypatch.setattr(model, "_state_path", lambda: tmp_path / "todo_board.json")
    monkeypatch.setattr(board_mod, "load_feedback", lambda: _load(
        feedback=[_entry(1, "911 Setup", "feedback"), _entry(2, "Other", "feedback")],
        archive=[_entry(3, "922 Kitting", "archive")]))
    board = board_mod.TodoBoard()
    board.show()
    qapp.processEvents()
    assert list(board._columns) == ["todo", "in_progress", "done", "wont_do"]
    assert len(board.store.bucket("todo")["cards"]) == 2
    assert len(board.store.bucket("done")["cards"]) == 1

    # a drop moves the card and the board rebuilds cleanly
    key = board.store.bucket("todo")["cards"][0]
    board._on_card_dropped(key, "in_progress", 0)
    board._do_rebuild()
    qapp.processEvents()
    assert board.store.bucket_of(key)["id"] == "in_progress"

    # theme rebuild must not raise
    board.apply_theme()
    qapp.processEvents()


# ---- write-back ------------------------------------------------------------

def _make_telemetry_workbook(path, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Feedback"
    ws.append(["Timestamp", "User", "Machine", "Suggestion",
               "Which Feature", "TechDeck Version", "Status"])
    for row in rows:
        ws.append(row)
    arch = wb.create_sheet("Archive")
    arch.append(["Timestamp", "User", "Machine", "Suggestion",
                 "Which Feature", "TechDeck Version", "Status"])
    wb.save(path)


def _status_cell(path, row=2):
    import openpyxl
    wb = openpyxl.load_workbook(path)
    try:
        return wb["Feedback"].cell(row=row, column=7).value
    finally:
        wb.close()


def test_writeback_done_then_restore(tmp_path, monkeypatch):
    from tools.devkit.todo_board.model import flush_writebacks, load_feedback
    xlsx = tmp_path / "TechDeck Telemetry.xlsx"
    _make_telemetry_workbook(xlsx, [
        ["2026-07-01 10:00:00", "amy", "M1", "add dark mode",
         "Shell", "0.8.6", "Needs Review"]])
    monkeypatch.setenv("TECHDECK_TELEMETRY_XLSX", str(xlsx))
    store = BoardStore(path=tmp_path / "b.json")
    load = load_feedback()
    assert load.ok
    store.sync(load)
    key = store.bucket("todo")["cards"][0]

    store.move_card(key, "done", 0)
    assert store.pending_writebacks() == [(key, "Complete")]
    res = flush_writebacks(store)
    assert res.ok and res.written == 1
    assert _status_cell(xlsx) == "Complete"
    assert store.cards[key]["written_status"] == "Complete"
    assert store.pending_writebacks() == []           # idempotent — no re-write

    store.move_card(key, "todo", 0)                   # drag back out
    res = flush_writebacks(store)
    assert res.ok and res.written == 1
    assert _status_cell(xlsx) == "Needs Review"
    assert store.cards[key]["written_status"] == ""


def test_writeback_manual_edit_wins_on_restore(tmp_path, monkeypatch):
    import openpyxl
    from tools.devkit.todo_board.model import flush_writebacks, load_feedback
    xlsx = tmp_path / "TechDeck Telemetry.xlsx"
    _make_telemetry_workbook(xlsx, [
        ["2026-07-01 10:00:00", "amy", "M1", "add dark mode",
         "Shell", "0.8.6", "Needs Review"]])
    monkeypatch.setenv("TECHDECK_TELEMETRY_XLSX", str(xlsx))
    store = BoardStore(path=tmp_path / "b.json")
    store.sync(load_feedback())
    key = store.bucket("todo")["cards"][0]

    store.move_card(key, "wont_do", 0)
    assert flush_writebacks(store).written == 1
    assert _status_cell(xlsx) == "Won't Do"

    # Maintainer overrides the cell in Excel...
    wb = openpyxl.load_workbook(xlsx)
    wb["Feedback"].cell(row=2, column=7).value = "Deferred"
    wb.save(xlsx)
    wb.close()

    # ...so dragging back out must NOT stomp it.
    store.move_card(key, "todo", 0)
    res = flush_writebacks(store)
    assert res.ok and res.written == 0 and res.adopted == 1
    assert _status_cell(xlsx) == "Deferred"
    assert store.cards[key]["written_status"] == ""   # cleared; not retried
    assert store.pending_writebacks() == []


def test_writeback_adopts_row_missing_from_sheet(tmp_path, monkeypatch):
    from tools.devkit.todo_board.model import flush_writebacks
    xlsx = tmp_path / "TechDeck Telemetry.xlsx"
    _make_telemetry_workbook(xlsx, [])                # header only — row archived
    monkeypatch.setenv("TECHDECK_TELEMETRY_XLSX", str(xlsx))
    store = BoardStore(path=tmp_path / "b.json")
    store.sync(_load(feedback=[_entry(1, "911 Setup", "feedback")]))
    key = store.bucket("todo")["cards"][0]
    store.move_card(key, "done", 0)
    res = flush_writebacks(store)
    assert res.ok and res.missing == 1 and res.written == 0
    assert store.cards[key]["written_status"] == "Complete"   # adopted
    assert store.pending_writebacks() == []           # never stuck pending


def test_writeback_skips_manual_and_archive_cards(tmp_path):
    store = BoardStore(path=tmp_path / "b.json")
    store.add_manual_card("done", "hand-written task")
    store.sync(_load(archive=[_entry(3, "922 Kitting", "archive")]))  # lands in done
    assert store.pending_writebacks() == []
