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


def _build_pixel_studio() -> QWidget:
    # Lazy import so a slow/broken tool can't stall the whole registry.
    from tools.devkit.pixel_studio import PixelStudio
    return PixelStudio()


DEV_TOOLS = [
    ToolSpec("pixel_studio", "Pixel Studio", _build_pixel_studio),
]
