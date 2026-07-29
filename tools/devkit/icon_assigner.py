"""DevKit Icon Assigner — choose which tile icon each plugin uses.

Left: every discovered plugin with its CURRENT tile icon. Right: a searchable
gallery of every generated icon on disk — the theme-recolored pixel-32 set
plus the static pack sets — plus "(family monogram)" for no custom art.
Click a plugin, click an icon: the assignment is STAGED (plugin row previews
it immediately). Save writes the changes into `PLUGIN_ICON_KEYS` in
`techdeck/ui/plugin_icon.py` — a surgical line patch that keeps untouched
entries and their inline comments byte-identical — then syncs the in-memory
dict and re-emits the theme signals so every visible tile refreshes live.

Source-only (DevKit): editing a code constant is the point — the assignment
must land in the repo to ship, exactly like the icon_editor → generator
hand-off. Frozen builds never see this tool.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from techdeck.ui import plugin_icon as pi

ICON_MODULE_PATH = Path(pi.__file__).resolve()
MONOGRAM_KEY = None          # staged value meaning "no custom icon"
MONOGRAM_LABEL = "(family monogram)"

# Directional eye-follow sprite suffixes (generated variants, not real keys).
_DIRECTION_SUFFIXES = (
    "_up_left", "_up_right", "_down_left", "_down_right",
    "_up", "_down", "_left", "_right",
)


def available_icon_keys() -> list:
    """[(key, set_name)] for every assignable generated icon on disk.

    Themed pixel-32 keys first (its dark folder is the canonical key list),
    then each pack set; a key present in both resolves themed (mirrors
    _load_pixel_icon's order). Eye-follow directional variants are excluded
    (they're sprites of a base key, not assignable icons).
    """
    base = pi._tile_icons_dir()
    seen, out = set(), []
    themed = base / "TechDeck pixel 32" / "dark"
    if themed.is_dir():
        for p in sorted(themed.glob("*.png")):
            out.append((p.stem, "TechDeck pixel 32"))
            seen.add(p.stem)
    for pack in pi._PACK_SETS:
        d = base / pack
        if not d.is_dir():
            continue
        stems = {p.stem for p in d.glob("*.png")}
        for stem in sorted(stems):
            if stem in seen:
                continue
            root = next((stem[: -len(s)] for s in _DIRECTION_SUFFIXES
                         if stem.endswith(s)), None)
            if root and root in stems:
                continue  # directional variant of an eye-follow base
            out.append((stem, pack))
            seen.add(stem)
    return out


def render_key_pixmap(key: str, size: int = 48) -> QPixmap | None:
    """Render an icon KEY the way the tile pipeline would (themed → pack)."""
    theme = pi._current_theme_name()
    folder = theme if theme in pi._PIXEL_THEMES else "dark"
    pixel_dir = pi._tile_icons_dir() / "TechDeck pixel 32"
    for cand in (pixel_dir / folder / f"{key}.png",
                 pixel_dir / "dark" / f"{key}.png"):
        if cand.exists():
            pm = QPixmap(str(cand))
            if not pm.isNull():
                return pm.scaled(size, size,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
    return pi.pack_icon_pixmap(key, size)


def patch_icon_keys_source(changes: dict, path=None) -> None:
    """Rewrite PLUGIN_ICON_KEYS entries in plugin_icon.py, surgically.

    ``changes``: plugin_id -> icon key string (assign/replace) or None
    (remove the entry → monogram fallback). Untouched lines — including
    inline comments — are preserved exactly; replaced lines keep their
    trailing comment. Raises RuntimeError if the block can't be found.
    """
    path = Path(path or ICON_MODULE_PATH)
    text = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.startswith("PLUGIN_ICON_KEYS = {"))
        end = next(i for i in range(start + 1, len(lines))
                   if lines[i].startswith("}"))
    except StopIteration:
        raise RuntimeError("PLUGIN_ICON_KEYS block not found in "
                           f"{path.name} - cannot save assignments.")
    block = lines[start + 1:end]

    def entry_line(pid, key, trailing=""):
        pad = " " * max(1, 28 - (len(pid) + 7))  # value column ~28, like the file
        return f'    "{pid}":{pad}"{key}",{trailing}'

    for pid, key in changes.items():
        pat = re.compile(r'^(\s*)"%s"\s*:\s*"[^"]*"\s*,?(.*)$' % re.escape(pid))
        idx = next((i for i, ln in enumerate(block) if pat.match(ln)), None)
        if key is None:
            if idx is not None:
                block.pop(idx)
        elif idx is not None:
            m = pat.match(block[idx])
            block[idx] = entry_line(pid, key, m.group(2) if m else "")
        else:
            block.append(entry_line(pid, key))

    out = lines[:start + 1] + block + lines[end:]
    path.write_text(newline.join(out) + newline, encoding="utf-8")


def apply_icon_changes(changes: dict) -> None:
    """Patch the source file, sync the live dict, refresh visible tiles."""
    patch_icon_keys_source(changes)
    for pid, key in changes.items():
        if key is None:
            pi.PLUGIN_ICON_KEYS.pop(pid, None)
        else:
            pi.PLUGIN_ICON_KEYS[pid] = key
    # Tile icons re-render in every ThemeAware apply_theme; re-emitting the
    # current theme is the one hook that reaches all mounted tiles (set_theme
    # early-returns on an unchanged name, so emit the signals directly).
    try:
        from techdeck.ui.theme_manager import get_theme_manager
        tm = get_theme_manager()
        tm.theme_changed.emit(tm.get_current_theme())
        tm.palette_changed.emit(tm.get_current_palette())
    except Exception:
        pass  # standalone/test use - nothing mounted to refresh


class IconAssigner(QWidget):
    """The DevKit tool widget (see module docstring)."""

    def __init__(self, plugins=None, parent=None):
        super().__init__(parent)
        if plugins is None:
            from techdeck.core.plugin_loader import PluginLoader
            loader = PluginLoader()
            plugins = loader.discover_plugins()
        self._plugins = sorted(
            plugins, key=lambda p: (getattr(p, "family", ""), p.name.lower()))
        self._staged = {}   # plugin_id -> key str | None (monogram)

        # Toolbar widgets (reparented by the DevKit page toolbar slot).
        self._pending_label = QLabel("")
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.clicked.connect(self._revert)
        self._save_btn = QPushButton("Save to Source")
        self._save_btn.clicked.connect(self._save)
        self._update_pending_ui()

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.addWidget(QLabel("Plugins"))
        self.plugin_list = QListWidget()
        self.plugin_list.setIconSize(QSize(32, 32))
        self.plugin_list.currentItemChanged.connect(self._on_plugin_selected)
        left.addWidget(self.plugin_list, 1)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter icons…")
        self.search.textChanged.connect(self._apply_filter)
        right.addWidget(self.search)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListView.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(48, 48))
        self.gallery.setGridSize(QSize(96, 84))
        self.gallery.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery.setWordWrap(True)
        self.gallery.setUniformItemSizes(True)
        self.gallery.itemClicked.connect(self._on_icon_picked)
        right.addWidget(self.gallery, 1)
        root.addLayout(right, 3)

        self._populate_gallery()
        self._populate_plugins()
        if self.plugin_list.count():
            self.plugin_list.setCurrentRow(0)

    # -- DevKit page contract ------------------------------------------------
    def devkit_toolbar_actions(self):
        return [self._pending_label, self._revert_btn, self._save_btn]

    # -- population ----------------------------------------------------------
    def _populate_plugins(self):
        self.plugin_list.clear()
        for plugin in self._plugins:
            item = QListWidgetItem(plugin.name)
            item.setToolTip(plugin.id)
            item.setData(Qt.ItemDataRole.UserRole, plugin)
            item.setIcon(QIcon(self._plugin_pixmap(plugin)))
            self.plugin_list.addItem(item)

    def _plugin_pixmap(self, plugin) -> QPixmap:
        """Current icon, honouring any staged (unsaved) assignment."""
        pid = plugin.id
        if pid in self._staged:
            key = self._staged[pid]
            if key is not None:
                pm = render_key_pixmap(key, 32)
                if pm is not None:
                    return pm
            return pi._monogram(plugin, 32)
        return pi.plugin_icon_pixmap(plugin, 32)

    def _populate_gallery(self):
        self.gallery.clear()
        mono = QListWidgetItem(MONOGRAM_LABEL)
        mono.setData(Qt.ItemDataRole.UserRole, MONOGRAM_KEY)
        mono.setToolTip("No custom art - the family-colored monogram tile.")
        self.gallery.addItem(mono)
        for key, set_name in available_icon_keys():
            item = QListWidgetItem(key)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(f"{key}  ({set_name})")
            pm = render_key_pixmap(key, 48)
            if pm is not None:
                item.setIcon(QIcon(pm))
            self.gallery.addItem(item)

    # -- interactions ----------------------------------------------------------
    def _apply_filter(self, text):
        needle = text.strip().lower()
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _current_plugin(self):
        item = self.plugin_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _effective_key(self, pid):
        return self._staged.get(pid, pi.PLUGIN_ICON_KEYS.get(pid))

    def _on_plugin_selected(self, current, _previous=None):
        if current is None:
            return
        plugin = current.data(Qt.ItemDataRole.UserRole)
        key = self._effective_key(plugin.id)
        self.gallery.blockSignals(True)
        self.gallery.clearSelection()
        for i in range(self.gallery.count()):
            if self.gallery.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.gallery.item(i).setSelected(True)
                self.gallery.setCurrentRow(i)
                break
        self.gallery.blockSignals(False)

    def _on_icon_picked(self, item):
        plugin = self._current_plugin()
        if plugin is None or item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        pid = plugin.id
        if key == pi.PLUGIN_ICON_KEYS.get(pid):
            self._staged.pop(pid, None)   # picked what's already saved
        else:
            self._staged[pid] = key
        row_item = self.plugin_list.currentItem()
        if row_item is not None:
            row_item.setIcon(QIcon(self._plugin_pixmap(plugin)))
        self._update_pending_ui()

    def _update_pending_ui(self, saved=False):
        n = len(self._staged)
        if n:
            self._pending_label.setText(f"{n} unsaved change(s)")
        else:
            self._pending_label.setText("Saved ✓" if saved else "")
        self._save_btn.setEnabled(bool(n))
        self._revert_btn.setEnabled(bool(n))

    def _revert(self):
        self._staged.clear()
        self._refresh_plugin_icons()
        self._update_pending_ui()
        self._on_plugin_selected(self.plugin_list.currentItem())

    def _save(self):
        if not self._staged:
            return
        try:
            apply_icon_changes(dict(self._staged))
        except Exception as exc:
            self._pending_label.setText(f"Save failed: {exc}")
            return
        self._staged.clear()
        self._refresh_plugin_icons()
        self._update_pending_ui(saved=True)

    def _refresh_plugin_icons(self):
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            item.setIcon(QIcon(self._plugin_pixmap(
                item.data(Qt.ItemDataRole.UserRole))))
