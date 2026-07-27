"""DevKit Dev Board — a Teams-style bucket + card board for working the
feedback backlog.

Cards are auto-generated from the maintainer's telemetry workbook (one card per
Feedback row, plus Archive rows into Done), labelled by the feature/tool they
pertain to, draggable between buckets, and each carries a checklist of tasks you
can tick off. See board.py for the widget and model.py for the data layer.

Source-only: this package lives under tools/ (excluded from the frozen build),
so it only runs on the maintainer's dev machine — the one place the telemetry
workbook is synced.
"""

__all__ = ["TodoBoard"]


def __getattr__(name):
    # Lazy so importing the data layer (model.py) doesn't pull in PySide6.
    if name == "TodoBoard":
        from tools.devkit.todo_board.board import TodoBoard
        return TodoBoard
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
