"""
Plugin icon rendering for the Windows-Settings-style tile grid.

Resolution order for a plugin's tile icon:
  1. An image file shipped in the plugin folder, named by the plugin.json `icon`
     field (e.g. "icon.png" / "icon.svg"). Resolved relative to plugin.path.
  2. An emoji glyph, if `icon` is a short non-filename string (legacy plugins set
     one here). Rendered centered, transparent background.
  3. A family-colored rounded-square monogram ("911" / "922" / name initials).
     This guarantees every tile has a recognizable icon before real art exists.

`plugin_icon_pixmap(plugin, size)` is the single entry point used by the tiles.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QBrush, QPainterPath, QIcon,
)

# Fixed, theme-independent family colors for the monogram fallback. Chosen to
# read well on both the dark and light app backgrounds.
_FAMILY_COLORS = {
    "911": "#3B82F6",   # blue
    "922": "#F59E0B",   # amber
    "other": "#8B5CF6",  # violet
}

# Suffixes we treat as "this `icon` value is a file, not an emoji".
_IMAGE_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".ico", ".webp", ".bmp"}

# Render at this multiple of the requested logical size, then tag the pixmap
# with the matching device-pixel-ratio so generated icons stay crisp on HiDPI.
_SCALE = 2


def _icon_is_file(icon: str) -> bool:
    return bool(icon) and Path(icon).suffix.lower() in _IMAGE_EXTS


def _load_icon_file(plugin, size: int) -> QPixmap | None:
    """Load an icon image shipped alongside the plugin, or None if absent/bad."""
    icon = getattr(plugin, "icon", None)
    if not _icon_is_file(icon):
        return None
    path = Path(getattr(plugin, "path", ".")) / icon
    if not path.exists():
        return None
    # QIcon handles both raster (.png/.jpg/...) and .svg (via the qsvg image
    # plugin, bundled by the PyInstaller PySide6 hook).
    pm = QIcon(str(path)).pixmap(QSize(size, size))
    if pm.isNull():
        return None
    return pm


def _new_canvas(size: int) -> QPixmap:
    pm = QPixmap(size * _SCALE, size * _SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(_SCALE)
    return pm


def _monogram_text(plugin) -> str:
    family = getattr(plugin, "family", "other")
    if family in ("911", "922"):
        return family
    name = (getattr(plugin, "name", "") or "?").strip()
    words = [w for w in name.split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper() if name else "?"


def _monogram(plugin, size: int) -> QPixmap:
    """Family-colored rounded-square tile with the family number or initials."""
    text = _monogram_text(plugin)
    color = QColor(_FAMILY_COLORS.get(getattr(plugin, "family", "other"),
                                      _FAMILY_COLORS["other"]))
    pm = _new_canvas(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(0, 0, size, size)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.26, size * 0.26)
    p.fillPath(path, QBrush(color))

    p.setPen(QColor("#FFFFFF"))
    f = QFont('"Segoe UI", Arial, sans-serif')
    f.setBold(True)
    f.setPixelSize(int(size * (0.34 if len(text) >= 3 else 0.44)))
    p.setFont(f)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pm


def _emoji(icon: str, size: int) -> QPixmap:
    """Render an emoji glyph centered on a transparent canvas."""
    pm = _new_canvas(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont('"Segoe UI Emoji", "Segoe UI", sans-serif')
    f.setPixelSize(int(size * 0.78))
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, icon)
    p.end()
    return pm


def plugin_icon_pixmap(plugin, size: int = 48) -> QPixmap:
    """Return a QPixmap for a plugin's tile icon (never None)."""
    pm = _load_icon_file(plugin, size)
    if pm is not None:
        return pm
    icon = getattr(plugin, "icon", None)
    if icon and not _icon_is_file(icon):
        return _emoji(icon, size)
    return _monogram(plugin, size)
