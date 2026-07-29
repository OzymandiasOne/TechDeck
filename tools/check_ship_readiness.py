"""TechDeck ship-readiness checker.

Verifies that every plugin in the repo will work "out of the box" in the
FROZEN (PyInstaller) build, not just in dev. Run from the repo root:

    python tools\\check_ship_readiness.py          # static checks only
    python tools\\check_ship_readiness.py --load   # + actually load every plugin
                                                   #   through PluginLoader like the app does

build.ps1 runs this (with --load) before PyInstaller and aborts the build on
any error, so a plugin that would fail on a colleague's machine can never ship.

Why this exists: dev mode (python -m techdeck) sees the full source tree, so a
plugin import like `techdeck.core.plugin_window` always works on the dev box.
The frozen exe only contains modules PyInstaller's static analysis reached from
techdeck/__main__.py plus the spec's `hiddenimports`. Anything a plugin imports
that isn't in that set raises at validation time on every user's machine
("missing dependency: No module named ..."). This bit plugin_sdk first, then
plugin_window (Customer DXF Quoting, v0.8.6). This tool closes that gap for
good (CLAUDE.md Hard Rule 8).

Checks (E = error, fails the build; W = warning):
  E1  plugin.json parses, is an object, id matches the folder name
  E2  family, if present, is one of 902/911/922/General/Games/QA; timeout is a
      non-negative int
  E3  any plugin importing PySide6/PyQt must set requires_main_thread: true
  E4  every .py in the plugin compiles (syntax gate)
  E5  no relative imports in plugins (they are loaded as standalone modules)
  E6  every import a plugin makes must exist in the frozen bundle:
        - stdlib: always OK
        - techdeck.*: the exact module must be statically reachable from
          techdeck/__main__.py or listed in spec hiddenimports
        - PySide6.QtX: the exact Qt submodule must be reachable or listed
          (Qt submodules are independent binaries - QtCharts lesson)
        - other third-party: the top-level package must be reachable or listed
  E7  TechDeck.spec datas must include ('plugins','plugins') and ('assets','assets')
  E8  a batch-number prompt must go through sdk.request_batch_number (the
      family-shared cache), never raw input()/console.request_input/
      get_console_input - otherwise the next same-family plugin in a multi-run
      re-prompts instead of reusing the answer (bit FormingFinder->Kitting,
      v0.8.6.3). Escape hatch for a deliberately non-shared prompt: request_text.
  E9  naming convention (2026-07): the folder/id must be the snake_case slug of
      the Library display name, family-prefixed - 902/911/922/QA names start
      with their family ("911 Setup" -> 911_setup, "QA Gemba Analyzer" ->
      qa_gemba_analyzer), Games ids get a "game_" prefix, and family-less
      ("General") plugins are just the slug of their name.
  E10 no writing with codec "utf-8-sig" - on write it always emits a BOM, and
      BOM-intolerant machine-read formats (DXF must start with a bare group
      code) reject the output as corrupt/"incomplete". Flags both the literal
      write and the decode-candidate-loop idiom that returns the raw codec
      name for later reuse as the write encoding (bit DXF Offset Tool +
      Customer DXF Quoting export, 2026-07-29).
  W1  hardcoded user-specific path (C:\\Users\\<name>) in plugin source
  W2  installed copy in %LOCALAPPDATA% differs from the repo copy (the repo is
      what ships - if you tested the installed copy, the fix may not be here)

Output is ASCII only (this runs from build.ps1).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO / "plugins"
APP_PKG_DIR = REPO / "techdeck"
SPEC_FILE = REPO / "TechDeck.spec"
ENTRY_MODULE = "techdeck.__main__"

# "General" is the current family-less bucket; "other" stays accepted as its
# legacy alias so an un-migrated plugin.json doesn't fail the gate.
VALID_FAMILIES = {"902", "911", "922", "General", "other", "Games", "QA"}
# Packages whose submodules are independent compiled extensions: a plugin
# importing PySide6.QtX needs THAT submodule bundled, not just "PySide6"
# (this is how QtCharts went missing once).
SUBMODULE_STRICT = {"PySide6", "PyQt5", "PyQt6"}
GUI_TOPLEVELS = {"PySide6", "PyQt5", "PyQt6"}

USER_PATH_RE = re.compile(r"[A-Za-z]:\\+Users\\+(?!Public)[A-Za-z0-9_.\- ]+", re.IGNORECASE)

# A prompt asking for a batch number must use sdk.request_batch_number so the
# answer populates the family-shared cache (E8). These are the bypass call
# targets; request_batch_number / request_text are intentionally NOT here.
BATCH_BYPASS_CALLS = {"input", "request_input", "get_console_input"}
BATCH_PROMPT_RE = re.compile(r"batch\s*number", re.IGNORECASE)

# E10: "utf-8-sig" is read-safe (strips a BOM if present) but write-hostile
# (always EMITS one). A decode loop like
#     for enc in ("utf-8-sig", ...): return data.decode(enc), enc
# hands the sig codec to a later write, silently BOM-prefixing the output.
UTF8SIG_ROUNDTRIP_RE = re.compile(r"\.decode\((\w+)\)\s*,\s*\1\b")
UTF8SIG_WRITE_LINE_RE = re.compile(
    r"""(?:\bopen\([^)\n]*["'][wax][tb+]*["']|\bwrite_text\()[^\n]*utf[-_]8[-_]sig""",
    re.IGNORECASE)


def _is_main_guard(node: ast.AST) -> bool:
    """True for an `if __name__ == "__main__":` statement."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    left = node.test.left
    return isinstance(left, ast.Name) and left.id == "__name__"


def _iter_calls_skipping_main(tree: ast.AST):
    """Yield Call nodes, but prune `if __name__ == '__main__'` subtrees.

    Those blocks are standalone-test harnesses that legitimately use raw
    input(); only the real plugin flow (run() and its helpers) must use the SDK.
    """
    stack = [tree]
    while stack:
        node = stack.pop()
        if _is_main_guard(node):
            continue  # skip the whole test-harness block
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def find_bypassed_batch_prompts(tree: ast.AST) -> list[str]:
    """Return prompt strings for batch-number prompts that bypass the SDK.

    Flags a call to input()/console.request_input()/get_console_input() whose
    string arguments mention a "batch number" - those should route through
    sdk.request_batch_number for family-shared caching.
    """
    hits: list[str] = []
    for node in _iter_calls_skipping_main(tree):
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name not in BATCH_BYPASS_CALLS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                    and BATCH_PROMPT_RE.search(arg.value):
                hits.append(arg.value)
    return hits


def stdlib_names() -> set[str]:
    if not hasattr(sys, "stdlib_module_names"):
        raise SystemExit("ERROR: Python 3.10+ required (sys.stdlib_module_names)")
    return set(sys.stdlib_module_names) | {"__future__"}


STDLIB = stdlib_names()


# ---------------------------------------------------------------- spec parsing

def parse_spec() -> tuple[list[str], list[tuple[str, str]]]:
    """Extract hiddenimports and datas string literals from TechDeck.spec."""
    tree = ast.parse(SPEC_FILE.read_text(encoding="utf-8"), filename=str(SPEC_FILE))
    hidden: list[str] = []
    datas: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "hiddenimports" and isinstance(kw.value, (ast.List, ast.Tuple)):
                for elt in kw.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        hidden.append(elt.value)
            elif kw.arg == "datas" and isinstance(kw.value, (ast.List, ast.Tuple)):
                for elt in kw.value.elts:
                    if isinstance(elt, (ast.List, ast.Tuple)) and len(elt.elts) == 2:
                        a, b = elt.elts
                        if (isinstance(a, ast.Constant) and isinstance(a.value, str)
                                and isinstance(b, ast.Constant) and isinstance(b.value, str)):
                            datas.append((a.value, b.value))
    return hidden, datas


# ------------------------------------------------- first-party reachability

def build_module_map() -> dict[str, Path]:
    """Map every techdeck.* module name to its source file."""
    module_map: dict[str, Path] = {}
    for path in APP_PKG_DIR.rglob("*.py"):
        rel = path.relative_to(REPO)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_map[".".join(parts)] = path
    return module_map


def extract_imports(path: Path, modname: str, module_map: dict[str, Path]):
    """Collect import targets from one source file.

    Returns (first_party, third_party, relative_count) where first_party is a
    set of techdeck.* module names, third_party is a set of top-level package
    names plus exact two-level names for SUBMODULE_STRICT packages, and
    relative_count counts relative imports (only legal inside the app package).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    first_party: set[str] = set()
    third_party: set[str] = set()
    relative_count = 0

    is_pkg = path.name == "__init__.py"
    pkg_parts = modname.split(".") if is_pkg else modname.split(".")[:-1]

    def record(name: str, from_alias: bool) -> None:
        top = name.split(".")[0]
        if top == "techdeck":
            if name in module_map:
                first_party.add(name)
            elif not from_alias:
                # Non-existent first-party module: keep it so it gets reported
                # as unresolvable instead of silently dropped.
                first_party.add(name)
        elif top in STDLIB:
            return
        else:
            if from_alias:
                # `from pkg.sub import attr` - attr is usually a function or
                # class; only meaningful as a module for strict packages.
                if top in SUBMODULE_STRICT and name.count(".") == 1:
                    third_party.add(name)
                return
            third_party.add(top)
            if top in SUBMODULE_STRICT:
                parts = name.split(".")
                if len(parts) >= 2:
                    third_party.add(parts[0] + "." + parts[1])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(alias.name, from_alias=False)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_count += 1
                if not modname:
                    continue  # relative import outside a package - reported by caller
                up = node.level - 1
                base = pkg_parts[: len(pkg_parts) - up] if up else list(pkg_parts)
                mod = ".".join(base + (node.module.split(".") if node.module else []))
            else:
                mod = node.module or ""
            if not mod:
                continue
            record(mod, from_alias=False)
            for alias in node.names:
                record(mod + "." + alias.name, from_alias=True)

    return first_party, third_party, relative_count


def compute_frozen_surface(module_map: dict[str, Path], hidden: list[str]):
    """BFS the app's static import graph the way PyInstaller's analysis does.

    Returns (reachable_first_party, available_third_party) where the third-
    party set contains top-level names plus exact PySide6.QtX names that the
    bundle will include.
    """
    per_module = {
        name: extract_imports(path, name, module_map)[:2]
        for name, path in module_map.items()
    }

    roots = {ENTRY_MODULE, "techdeck"}
    for h in hidden:
        if h.split(".")[0] == "techdeck":
            roots.add(h)

    reachable: set[str] = set()
    third_party: set[str] = set()
    stack = [r for r in roots if r in module_map]
    while stack:
        mod = stack.pop()
        if mod in reachable:
            continue
        reachable.add(mod)
        # Importing a module imports (executes) all its parent packages too.
        parts = mod.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent in module_map and parent not in reachable:
                stack.append(parent)
        fp, tp = per_module[mod]
        third_party |= tp
        for target in fp:
            if target in module_map and target not in reachable:
                stack.append(target)

    for h in hidden:
        if h.split(".")[0] != "techdeck":
            third_party.add(h.split(".")[0])
            third_party.add(h)

    return reachable, third_party


# ------------------------------------------------------------- plugin checks

def installed_copy_of(plugin_dir: Path) -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    candidate = Path(base) / "TechDeck" / "plugins" / plugin_dir.name
    return candidate if candidate.is_dir() else None


def check_plugin(plugin_dir: Path, available_fp: set[str], available_tp: set[str],
                 hidden: list[str], module_map: dict[str, Path],
                 errors: list[str], warnings: list[str]) -> None:
    pid = plugin_dir.name

    # --- manifest (E1, E2)
    manifest_file = plugin_dir / "plugin.json"
    manifest = None
    if not manifest_file.is_file():
        errors.append(f"{pid}: missing plugin.json")
    else:
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{pid}: plugin.json does not parse: {exc}")
        else:
            if not isinstance(manifest, dict):
                errors.append(f"{pid}: plugin.json root must be an object")
                manifest = None
    if isinstance(manifest, dict):
        mid = manifest.get("id")
        if mid != pid:
            errors.append(f"{pid}: plugin.json id '{mid}' does not match folder name")
        family = manifest.get("family")
        if family is not None and family not in VALID_FAMILIES:
            errors.append(f"{pid}: invalid family '{family}' (must be 902/911/922/General/Games/QA)")
        timeout = manifest.get("timeout")
        if timeout is not None and (not isinstance(timeout, int) or timeout < 0):
            errors.append(f"{pid}: timeout must be a non-negative integer, got {timeout!r}")

        # --- naming convention (E9): id = family-prefixed slug of the name
        name = manifest.get("name")
        if isinstance(name, str) and name.strip() and family in VALID_FAMILIES:
            if family in ("902", "911", "922", "QA") and not name.startswith(family + " "):
                errors.append(
                    f"{pid}: Library name '{name}' must start with '{family} ' "
                    f"(the Home tile strips the family prefix and shows the badge)")
            slug = re.sub(r"_+", "_",
                          re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")
            expected = f"game_{slug}" if family == "Games" else slug
            if pid != expected:
                errors.append(
                    f"{pid}: folder/id must match the Library name per the naming "
                    f"convention - expected '{expected}' for name '{name}'")

    run_file = plugin_dir / "run.py"
    if not run_file.is_file():
        errors.append(f"{pid}: missing run.py")
        return

    imports_gui = False
    for py_file in sorted(plugin_dir.rglob("*.py")):
        rel = py_file.relative_to(plugin_dir.parent)

        # --- syntax (E4)
        try:
            src = py_file.read_text(encoding="utf-8")
            tree = compile(src, str(py_file), "exec", ast.PyCF_ONLY_AST)
        except SyntaxError as exc:
            errors.append(f"{pid}: {rel} does not compile: {exc}")
            continue

        # --- batch prompt must use the SDK (E8)
        for prompt in find_bypassed_batch_prompts(tree):
            errors.append(
                f"{pid}: {rel} prompts for a batch number ({prompt!r}) via raw "
                f"input/request_input - use sdk.request_batch_number so the "
                f"answer is reused by same-family plugins in a multi-run "
                f"(use sdk.request_text if a non-shared prompt is intended)"
            )

        # --- BOM-writing "utf-8-sig" round-trip (E10)
        if "utf-8-sig" in src or "utf_8_sig" in src:
            if UTF8SIG_ROUNDTRIP_RE.search(src):
                errors.append(
                    f"{pid}: {rel} decodes with a candidate list including "
                    f"'utf-8-sig' and returns that codec name for reuse - a "
                    f"later write with it prepends a BOM, corrupting "
                    f"BOM-intolerant formats like DXF. Map it to 'utf-8' "
                    f"before returning (bit DXF Offset Tool, 2026-07)"
                )
            for line_no, line in enumerate(src.splitlines(), 1):
                if UTF8SIG_WRITE_LINE_RE.search(line):
                    errors.append(
                        f"{pid}: {rel}:{line_no} writes a file with encoding "
                        f"'utf-8-sig' - that always emits a BOM; write "
                        f"'utf-8' instead"
                    )

        fp, tp, rel_count = extract_imports(py_file, "", module_map)

        # --- relative imports (E5)
        if rel_count:
            errors.append(
                f"{pid}: {rel} uses relative imports - plugins are loaded as "
                f"standalone modules, relative imports always fail"
            )

        # --- frozen-bundle coverage (E6)
        for name in sorted(fp):
            if name in available_fp or name in hidden:
                continue
            if name in module_map:
                errors.append(
                    f"{pid}: imports '{name}' which exists in the repo but is NOT "
                    f"bundled in the frozen exe - the main app never imports it. "
                    f"Add '{name}' to hiddenimports in TechDeck.spec (Hard Rule 8)"
                )
            else:
                errors.append(f"{pid}: imports '{name}' which does not exist")
        for name in sorted(tp):
            top = name.split(".")[0]
            if top in GUI_TOPLEVELS:
                imports_gui = True
            if name in available_tp:
                continue
            if "." in name:
                errors.append(
                    f"{pid}: imports '{name}' - that Qt submodule is not bundled. "
                    f"Add '{name}' to hiddenimports in TechDeck.spec"
                )
            else:
                errors.append(
                    f"{pid}: imports third-party package '{name}' which is not "
                    f"bundled - the main app never imports it. Add '{name}' to "
                    f"hiddenimports in TechDeck.spec (Hard Rule 8)"
                )

        # --- hardcoded user paths (W1)
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for match in set(USER_PATH_RE.findall(text)):
            warnings.append(
                f"{pid}: {rel} contains a hardcoded user path '{match}' - this "
                f"will not exist on a colleague's machine; resolve via plugin_sdk"
            )

    # --- GUI thread rule (E3)
    if imports_gui and isinstance(manifest, dict) and manifest.get("requires_main_thread") is not True:
        errors.append(
            f"{pid}: imports a Qt binding but plugin.json does not set "
            f"\"requires_main_thread\": true - creating widgets off the main "
            f"thread crashes (Hard Rule 4)"
        )

    # --- repo vs installed drift (W2)
    installed = installed_copy_of(plugin_dir)
    if installed is not None:
        for fname in ("run.py", "plugin.json"):
            repo_f = plugin_dir / fname
            inst_f = installed / fname
            if repo_f.is_file() and inst_f.is_file():
                # Normalize line endings: git checks out CRLF while Copy-Item /
                # installer copies may be LF - that's not real drift.
                repo_b = repo_f.read_bytes().replace(b"\r\n", b"\n")
                inst_b = inst_f.read_bytes().replace(b"\r\n", b"\n")
                if repo_b != inst_b:
                    warnings.append(
                        f"{pid}: installed copy of {fname} in LOCALAPPDATA differs "
                        f"from the repo - the repo version is what ships. If you "
                        f"tested a fix in the installed copy, port it back "
                        f"(Hard Rule 12 in reverse)"
                    )
                    break


# ---------------------------------------------------------------- --load mode

def load_all_plugins(errors: list[str]) -> int:
    """Load every plugin through PluginLoader exactly like the app does."""
    sys.path.insert(0, str(REPO))
    from techdeck.core.plugin_loader import PluginLoader  # noqa: deferred import

    loader = PluginLoader(PLUGINS_DIR)
    discovered = {p.id for p in loader.discover_plugins()}

    on_disk = {d.name for d in PLUGINS_DIR.iterdir()
               if d.is_dir() and (d / "plugin.json").exists()}
    for missing in sorted(on_disk - discovered):
        errors.append(f"{missing}: present on disk but NOT discovered by PluginLoader "
                      f"- check plugin.json")

    loaded = 0
    for pid in sorted(discovered):
        ok, msg = loader.validate_plugin(pid)
        if ok:
            loaded += 1
        else:
            errors.append(f"{pid}: validate_plugin failed: {msg}")
    return loaded


# ----------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description="TechDeck ship-readiness checker")
    parser.add_argument("--load", action="store_true",
                        help="also load every plugin via PluginLoader (dev-mode "
                             "equivalent of app startup validation)")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    print("TechDeck Ship-Readiness Check")
    print("=" * 60)

    hidden, datas = parse_spec()
    print(f"Spec: {len(hidden)} hiddenimports, {len(datas)} datas entries")

    # E7 - datas
    for required in (("plugins", "plugins"), ("assets", "assets")):
        if required not in datas:
            errors.append(f"TechDeck.spec datas is missing {required!r} - that "
                          f"directory will be absent from the build (Hard Rule 7)")

    module_map = build_module_map()
    reachable_fp, available_tp = compute_frozen_surface(module_map, hidden)
    print(f"App graph: {len(reachable_fp)} first-party modules reachable from "
          f"{ENTRY_MODULE} (of {len(module_map)} in the package)")

    plugin_dirs = sorted(d for d in PLUGINS_DIR.iterdir() if d.is_dir())
    print(f"Checking {len(plugin_dirs)} plugins...")
    print()

    for plugin_dir in plugin_dirs:
        errs_before, warns_before = len(errors), len(warnings)
        check_plugin(plugin_dir, reachable_fp, available_tp, hidden,
                     module_map, errors, warnings)
        if len(errors) > errs_before:
            status = "FAIL"
        elif len(warnings) > warns_before:
            status = "warn"
        else:
            status = "ok"
        print(f"  [{status:>4}] {plugin_dir.name}")

    if args.load:
        print()
        print("Loading every plugin via PluginLoader (--load)...")
        loaded = load_all_plugins(errors)
        print(f"  {loaded} plugin(s) loaded and validated")

    print()
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  W  {w}")
        print()
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  E  {e}")
        print()
        print(f"RESULT: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1

    print(f"RESULT: PASS (0 errors, {len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
