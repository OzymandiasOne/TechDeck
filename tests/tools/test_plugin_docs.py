"""One notes file per plugin: docs/plugins/<id>.md.

docs/PLUGINS.md was a single 250,000-character file. Too big to read whole, so
in practice it got SEARCHED, and a search hit arrives without the surrounding
context that makes it safe to act on. On 2026-09-18 it was split: the notes for
plugin `<id>` live in `docs/plugins/<id>.md`, small enough to read in full every
time, and docs/PLUGINS.md is the index + roster.

A naming rule only works while it is true. So:

  - every plugin in plugins/ has its notes file (a new plugin cannot ship
    without one - even a two-line stub beats an id nobody can look up);
  - every notes file belongs to a real plugin, or is one of the `_`-prefixed
    shared files, each of which the index must name (otherwise nothing loads it).

docs/ is stripped from the public mirror, so it is resolved through
`private_doc` (skips there; see tests/conftest.py).
"""
import json
from pathlib import Path

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"


def _real_plugin_ids() -> set:
    return {json.loads(m.read_text(encoding="utf-8"))["id"]
            for m in PLUGINS_DIR.glob("*/plugin.json")}


def test_every_plugin_has_a_notes_file_and_every_file_has_a_plugin(private_doc):
    notes = {p.stem for p in private_doc("docs/plugins").glob("*.md")}
    shared = {n for n in notes if n.startswith("_")}
    per_plugin = notes - shared
    real = _real_plugin_ids()
    assert per_plugin == real, (
        "docs/plugins/ is out of step with plugins/:\n"
        f"  plugins with no notes file: {sorted(real - per_plugin)}\n"
        f"  notes files with no plugin: {sorted(per_plugin - real)}\n"
        "Add docs/plugins/<id>.md for a new plugin (a short stub is fine). For a "
        "removed plugin, move what is worth keeping into "
        "docs/plugins/_removed_plugins.md and delete the file.")


def test_shared_notes_files_are_named_by_the_index(private_doc):
    index = private_doc("docs/PLUGINS.md").read_text(encoding="utf-8")
    shared = sorted(p.name for p in private_doc("docs/plugins").glob("_*.md"))
    unnamed = [n for n in shared if n not in index]
    assert not unnamed, (
        f"docs/PLUGINS.md does not name these shared notes files, so nothing ever "
        f"loads them: {unnamed}")


def test_the_index_stays_an_index(private_doc):
    """The whole point of the split. If deep notes creep back into the index it
    is on its way to 250k again."""
    size = len(private_doc("docs/PLUGINS.md").read_text(encoding="utf-8"))
    assert size <= 8_000, (
        f"docs/PLUGINS.md is {size:,} chars. It is the index + roster only; a "
        f"plugin's notes go in docs/plugins/<id>.md.")
