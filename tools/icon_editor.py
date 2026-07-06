"""
TechDeck Tile-Icon Editor
=========================

The pixel editor (tools/pixel_editor.py), specialised for the TILE ICONS that
live as code: the hand-editable `_<KEY>_GRID` / `_<KEY>_TONES` blocks inside
tools/generate_tile_icons_32.py (theme-recolored set) and
tools/generate_pack_icons.py (static native-color "TechDeck pack pixel" set).
No more hand-typing 32x32 ASCII grids into the scripts.

    python tools/icon_editor.py

Icon menu:
  Open Icon from Scripts...  — lists every grid-based icon in both generator
                               scripts and loads it onto the canvas.
  Save Icon to Scripts...    — asks for the icon NAME (the key) and whether it
                               is THEME-RECOLORED or STATIC, then writes the
                               grid + tones into the right script (replacing
                               the existing block on a re-save, inserting +
                               registering a brand-new icon), and re-runs that
                               generator so the PNGs are refreshed immediately.

Theme-recolored icons are repainted per theme BY LUMINANCE RANK — draw with
tonal contrast (outline darkest, highlight lightest); the exact hues you pick
only survive in the static set. After saving a NEW icon, point a plugin at it
via PLUGIN_ICON_KEYS in techdeck/ui/plugin_icon.py.

Everything else (tools, palette, zoom, import, .tdart save) is inherited from
the pixel editor.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))        # tools/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))    # repo root

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox,
)

from pixel_editor import Editor

ROOT = Path(__file__).resolve().parents[1]
THEMED_SCRIPT = ROOT / "tools" / "generate_tile_icons_32.py"
PACK_SCRIPT = ROOT / "tools" / "generate_pack_icons.py"
PACK_SET = "TechDeck pack pixel"
GRID_SIZE = 32
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

MODE_THEMED = "themed (recolored per theme)"
MODE_STATIC = "static (keeps these exact colors)"


# ── script IO ────────────────────────────────────────────────────────────────
def _const(key: str) -> str:
    return key.upper()


def parse_icon(text: str, key: str):
    """(rows, tones) for `key`'s grid/tones consts in `text`, or None."""
    k = _const(key)
    gm = re.search(rf"^_{k}_GRID = \[\n(.*?)^\]\n", text, re.S | re.M)
    tm = re.search(rf"^_{k}_TONES = (\{{.*?\}})\s*$", text, re.M)
    if not gm or not tm:
        return None
    rows = re.findall(r'"([^"]*)"', gm.group(1))
    tones = ast.literal_eval(tm.group(1))
    return rows, tones


def list_icons():
    """{key: mode} for every grid-based icon in both scripts."""
    out = {}
    for script, mode in ((THEMED_SCRIPT, "themed"), (PACK_SCRIPT, "static")):
        text = script.read_text(encoding="utf-8")
        for m in re.finditer(r"^_([A-Z0-9_]+)_GRID = \[", text, re.M):
            out[m.group(1).lower()] = mode
    return out


def format_block(key: str, rows, tones) -> str:
    k = _const(key)
    grid = "\n".join(f'    "{r}",' for r in rows)
    tone = ", ".join(f'"{c}": "{h}"' for c, h in sorted(tones.items()))
    return f"_{k}_GRID = [\n{grid}\n]\n_{k}_TONES = {{{tone}}}\n"


def save_icon_to_script(key: str, static: bool, rows, tones) -> Path:
    """Insert or replace `key`'s block in the right generator script.
    New THEMED icons also get their draw fn + ICONS entry; new STATIC icons get
    a "TechDeck pack pixel" SETS entry. Returns the script path."""
    script = PACK_SCRIPT if static else THEMED_SCRIPT
    text = script.read_text(encoding="utf-8")
    k = _const(key)
    block = format_block(key, rows, tones)

    if parse_icon(text, key):
        # Re-save: swap the grid + tones in place; registration already exists.
        text = re.sub(rf"^_{k}_GRID = \[\n.*?^\]\n", block.split(f"_{k}_TONES")[0],
                      text, count=1, flags=re.S | re.M)
        text = re.sub(rf"^_{k}_TONES = \{{.*?\}}\s*$",
                      block.splitlines()[-1], text, count=1, flags=re.M)
    elif static:
        anchor = re.search(rf'^SETS = \{{\n(\s*)"{re.escape(PACK_SET)}": \{{\n',
                           text, re.M)
        if not anchor:
            raise RuntimeError(f'could not find SETS["{PACK_SET}"] in {script.name}')
        text = text[:anchor.start()] + block + "\n\n" + text[anchor.start():]
        entry = f'        "{key}": (_{k}_GRID, _{k}_TONES),\n'
        anchor = re.search(rf'^SETS = \{{\n\s*"{re.escape(PACK_SET)}": \{{\n',
                           text, re.M)
        text = text[:anchor.end()] + entry + text[anchor.end():]
    else:
        anchor = re.search(r"^ICONS = \{\n", text, re.M)
        if not anchor:
            raise RuntimeError(f"could not find ICONS registry in {script.name}")
        fn = f"\ndef {key}(d):\n    _draw_grid(d, _{k}_GRID, _{k}_TONES)\n\n\n"
        text = text[:anchor.start()] + block + fn + text[anchor.start():]
        anchor = re.search(r"^ICONS = \{\n", text, re.M)
        text = (text[:anchor.end()] + f'    "{key}": {key},\n' + text[anchor.end():])

    script.write_text(text, encoding="utf-8")
    return script


def regenerate(static: bool) -> str:
    """Re-run the generator so the PNGs match the script. Returns its output."""
    script = PACK_SCRIPT if static else THEMED_SCRIPT
    args = [sys.executable, str(script)] + ([PACK_SET] if static else [])
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(args, capture_output=True, text=True, env=env,
                          cwd=str(ROOT))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "generator failed")
    return (proc.stdout or "").strip()


# ── save dialog ──────────────────────────────────────────────────────────────
class SaveIconDialog(QDialog):
    def __init__(self, key="", static=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Icon to Scripts")
        form = QFormLayout(self)
        self.name_edit = QLineEdit(key)
        self.name_edit.setPlaceholderText("snake_case key, e.g. mr_beans")
        form.addRow("Icon name", self.name_edit)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([MODE_THEMED, MODE_STATIC])
        self.mode_combo.setCurrentIndex(1 if static else 0)
        form.addRow("Color scheme", self.mode_combo)
        note = QLabel("Themed icons are repainted per theme by luminance rank;\n"
                      "static icons keep these exact colors on every theme.")
        note.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def result_values(self):
        return (self.name_edit.text().strip().lower(),
                self.mode_combo.currentIndex() == 1)


# ── the editor ───────────────────────────────────────────────────────────────
class IconEditor(Editor):
    def __init__(self):
        super().__init__()
        self.icon_key = None
        self.icon_static = False
        self._update_title()

        iconm = self.menuBar().addMenu("&Icon")
        iconm.addAction("Open Icon from Scripts...",
                        self.open_icon).setShortcut("Ctrl+Shift+O")
        # No shortcut: Ctrl+Shift+S is the inherited .tdart Save As, and plain
        # Ctrl+S already routes here once an icon is open (see save_file).
        iconm.addAction("Save Icon to Scripts...", self.save_icon)
        self.statusBar().showMessage(
            "Icon menu: open/save the tile icons that live in the generator scripts")

    def save_file(self):
        """Plain Save (Ctrl+S / File > Save): with an icon from the scripts
        open, save THE ICON back to its script (dialog pre-filled — one OK
        saves over what you opened) instead of forking a .tdart file. Untitled
        or imported art still falls through to the .tdart save."""
        if self.icon_key:
            return self.save_icon()
        return super().save_file()

    def open_icon(self):
        if not self._confirm_discard():
            return
        icons = list_icons()
        if not icons:
            QMessageBox.information(self, "No icons", "No grid-based icons found.")
            return
        labels = [f"{k}   [{m}]" for k, m in sorted(icons.items())]
        pick, ok = QInputDialog.getItem(
            self, "Open icon", "Icon (from the generator scripts):",
            labels, 0, False)
        if not ok:
            return
        key = pick.split()[0]
        static = icons[key] == "static"
        script = PACK_SCRIPT if static else THEMED_SCRIPT
        rows, tones = parse_icon(script.read_text(encoding="utf-8"), key)
        self.canvas.load({"palette": tones, "rows": rows})
        self._rebuild_swatches()
        self.icon_key, self.icon_static = key, static
        self.path = None
        self._mark_clean()
        w, h = self.canvas.grid_size()
        self.statusBar().showMessage(
            f"Opened {key} ({icons[key]}, {w}x{h}, {len(tones)} tones)")

    def save_icon(self):
        w, h = self.canvas.grid_size()
        if (w, h) != (GRID_SIZE, GRID_SIZE):
            QMessageBox.warning(
                self, "Wrong size",
                f"Tile icons are {GRID_SIZE}x{GRID_SIZE}; this canvas is {w}x{h}.\n"
                "Use Edit > Resize / Add lines first.")
            return
        rows = ["".join(r) for r in self.canvas.rows]
        used = {ch for row in rows for ch in row if ch != "."}
        if not used:
            QMessageBox.warning(self, "Empty", "The canvas is empty.")
            return
        tones = {ch: self.canvas.palette[ch] for ch in sorted(used)}

        dlg = SaveIconDialog(self.icon_key or "", self.icon_static, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        key, static = dlg.result_values()
        if not _KEY_RE.match(key):
            QMessageBox.warning(self, "Bad name",
                                "Name must be snake_case (a-z, 0-9, _).")
            return
        existing = list_icons()
        if key in existing and (existing[key] == "static") != static:
            QMessageBox.warning(
                self, "Name taken",
                f'"{key}" already exists as a {existing[key]} icon — the app '
                "resolves themed before static, so one key can't be both.\n"
                "Pick another name (or re-save it in its original mode).")
            return

        try:
            script = save_icon_to_script(key, static, rows, tones)
            out = regenerate(static)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.icon_key, self.icon_static = key, static
        self._mark_clean()
        msg = f"Saved {key} into {script.name} — {out}"
        if key not in existing:
            msg += (f'\n\nNew icon: point a plugin at it via PLUGIN_ICON_KEYS '
                    f'in techdeck/ui/plugin_icon.py:  "<plugin_id>": "{key}"')
            QMessageBox.information(self, "Icon saved", msg)
        self.statusBar().showMessage(f"Saved {key} + regenerated PNGs")

    def _update_title(self):
        # Extends the pixel editor's title with the icon key when one is open.
        if getattr(self, "icon_key", None):
            self.setWindowTitle(
                f"TechDeck Icon Editor — {self.icon_key}"
                f"{' [static]' if self.icon_static else ' [themed]'}"
                f"{'*' if self.dirty else ''}")
        else:
            super()._update_title()
            self.setWindowTitle(self.windowTitle().replace(
                "Pixel Editor", "Icon Editor"))


def main():
    app = QApplication(sys.argv)
    ed = IconEditor()
    ed.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
