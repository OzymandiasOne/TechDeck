"""A plugin that calls into a sibling plugin must call it with the right arguments.

Reported 2026-10-20, from a colleague's debug report. 922 Setup's "Fill Out MPL
+ Find Repeats" stage crashed on the first run of every batch:

    TypeError: _update_mpl_sheets() missing 1 required positional argument: 'params'

922 Setup does not own that logic -- the MPL maintenance lives in 922 Batch
Repeater and 922 Setup borrows it through `sdk.load_sibling` ("one home for the
logic", which is the right call). On 2026-10-08 the Repeater's helper gained a
`params` argument so it could raise an action item when the MPL is open in
Excel. The Repeater's own call site was updated. 922 Setup's was not, and
nothing caught it: a cross-module call resolved by `importlib` at runtime is
invisible to every import check, every linter run over one plugin, and every
test that does not actually execute that stage. It shipped in 0.8.7.9 and broke
922 Setup for six days.

This gate is the eradication step. It walks every plugin's `run.py`, works out
which siblings that file loads (any plugin id that appears in it as a string
literal), and for every `<alias>.<function>(...)` call whose function is a
top-level def in one of those siblings, checks the call supplies enough
arguments and not too many.

It is static and conservative. A call it cannot read statically -- `*args`,
`**kwargs`, a computed attribute name -- is skipped rather than guessed at, so
it fails on real drift and never on honest code. Today it inspects 20 real
cross-plugin calls across five plugins.
"""

import ast
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"

# Names that are never a sibling module, so an attribute call on them is not a
# cross-plugin call even when the attribute happens to share a sibling's name.
NOT_A_SIBLING = {"sdk", "self", "cls", "os", "re", "json", "np", "pd", "fitz",
                 "Path", "shutil", "sys", "time", "math", "params", "settings"}


def _plugin_ids():
    return {d.name for d in PLUGINS.iterdir() if (d / "run.py").is_file()}


def _top_level_funcs(path):
    """{name: FunctionDef} for the module's own top-level functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _signature(fn):
    """(required, accepted, takes_star_args, positional names)."""
    args = fn.args
    positional = ([p.arg for p in args.posonlyargs]
                  + [p.arg for p in args.args])
    required = len(positional) - len(args.defaults)
    return required, len(positional), args.vararg is not None, positional


def _cross_plugin_calls():
    """Every statically readable call from one plugin into a sibling.

    Yields (caller_id, ast.Call, alias, attr, sibling_id, FunctionDef).
    """
    ids = _plugin_ids()
    for pdir in sorted(PLUGINS.iterdir()):
        run = pdir / "run.py"
        if not run.is_file():
            continue
        tree = ast.parse(run.read_text(encoding="utf-8"))

        # Which siblings can this file reach? Loading one always names it by
        # id somewhere in the file -- directly in sdk.load_sibling, or in the
        # local wrapper's caller. Matching any id-shaped string literal keeps
        # the gate working through either shape of indirection.
        siblings = {}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in ids
                    and node.value != pdir.name):
                siblings[node.value] = _top_level_funcs(
                    PLUGINS / node.value / "run.py")
        if not siblings:
            continue

        own = set(_top_level_funcs(run))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            base = node.func.value
            if not isinstance(base, ast.Name) or base.id in NOT_A_SIBLING:
                continue
            attr = node.func.attr
            if attr in own:
                continue  # the plugin's own function, shadowing the name
            if any(isinstance(a, ast.Starred) for a in node.args):
                continue  # *args -- the count is not knowable here
            if any(k.arg is None for k in node.keywords):
                continue  # **kwargs -- same
            for sid, funcs in siblings.items():
                if attr in funcs:
                    yield pdir.name, node, base.id, attr, sid, funcs[attr]


def test_cross_plugin_calls_match_the_sibling_signature():
    drift = []
    for caller, node, alias, attr, sid, fn in _cross_plugin_calls():
        required, accepted, star, names = _signature(fn)
        lineno = node.lineno
        positional = len(node.args)
        keywords = {k.arg for k in node.keywords if k.arg}
        supplied = positional + len(keywords & set(names))
        if supplied < required:
            drift.append(
                f"{caller}/run.py:{lineno}: {alias}.{attr}() supplies "
                f"{supplied} of the {required} argument(s) "
                f"{sid}.{attr}() requires ({', '.join(names)})")
        elif positional > accepted and not star:
            drift.append(
                f"{caller}/run.py:{lineno}: {alias}.{attr}() passes "
                f"{positional} positional argument(s), but {sid}.{attr}() "
                f"accepts {accepted} ({', '.join(names)})")

    assert not drift, (
        "A plugin calls a sibling plugin's function with the wrong arguments. "
        "This crashes at runtime only, on the stage that uses it:\n  "
        + "\n  ".join(drift))


def test_the_gate_actually_sees_the_cross_plugin_calls():
    """Guard against the check silently inspecting nothing.

    Every rule here is only worth its line count while it still matches real
    code. If a refactor changes how siblings are loaded, this fails instead of
    the gate quietly passing on an empty list.
    """
    calls = list(_cross_plugin_calls())
    callers = {c[0] for c in calls}
    assert len(calls) >= 15, f"only {len(calls)} cross-plugin call(s) found"
    assert "922_setup" in callers
    assert "911_setup" in callers
