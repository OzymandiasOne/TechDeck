"""DevKit tool registry — the entries in the Settings > DevKit picker.

Each ToolSpec is one dropdown entry: a label plus a build() that returns the
QWidget mounted into the DevKit embed host. Seeded with just the Pixel Studio;
add tools one at a time (a new entry is a single line). Source-only — this
whole package is excluded from the frozen build.
"""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ToolSpec:
    key: str
    label: str
    build: Callable[[], QWidget]   # returns the widget to embed


def _build_todo_board() -> QWidget:
    # Lazy import so a slow/broken tool can't stall the whole registry.
    from tools.devkit.todo_board import TodoBoard
    return TodoBoard()


def _build_pixel_studio() -> QWidget:
    # Lazy import so a slow/broken tool can't stall the whole registry.
    from tools.devkit.pixel_studio import PixelStudio
    return PixelStudio()


def _build_test_runner() -> QWidget:
    from tools.devkit.diagnostics import AutomatedTestsPanel
    return AutomatedTestsPanel()


def _build_ship_readiness() -> QWidget:
    from tools.devkit.diagnostics import ShipReadinessPanel
    return ShipReadinessPanel()


def _build_pixel_lint() -> QWidget:
    from tools.devkit.diagnostics import PixelLintPanel
    return PixelLintPanel()


DEV_TOOLS = [
    ToolSpec("todo_board", "To-Do Board", _build_todo_board),
    ToolSpec("pixel_studio", "Pixel Studio", _build_pixel_studio),
    ToolSpec("automated_tests", "Automated Tests", _build_test_runner),
    ToolSpec("ship_readiness", "Ship Readiness", _build_ship_readiness),
    ToolSpec("pixel_lint", "Pixel Style Lint", _build_pixel_lint),
]
