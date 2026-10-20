"""Build gate: the two-way-flow rules nobody should have to remember.

Three rules carry real cost if broken, and all three are mechanically
checkable, so they are a gate rather than a line in a doc (Fix Protocol
step 3):

E-FLOW-1  **No flow call inside a loop.** A two-way call costs 1-5 s and the
          platform hard-caps an answer at 120 s. One call per queued row turns
          a 35-row job into a frozen app, and a loop over a flow is how you
          discover the 120 s cap in front of a user. A long job answers at once
          with a job id; the app asks again later.

E-FLOW-2  **A plugin never talks to a flow with `requests` directly.** The
          timeout, the fallback, the command_id, the sandbox guard and the
          outbox all live in `plugin_sdk`. A direct call silently opts out of
          every one of them, which is exactly how Batch 488 logged DONE on 35
          cards that never existed.

E-FLOW-3  **No flow address in the repo outside constants.py.** The publish
          scrub only redacts the patterns it knows, and a flow address is
          effectively public the moment it ships (techdeck-flows skill, §4) —
          but it should still not be scattered where the scrub cannot see it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Calls that reach a flow over the network. `flush_outbox` is included on
# purpose: it delivers a whole queue itself, so wrapping it in a loop is the
# same mistake wearing a hat.
FLOW_CALLS = {"ask_flow", "flush_outbox", "post_webhook"}

LOOP_NODES = (ast.For, ast.AsyncFor, ast.While,
              ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _python_files() -> list[Path]:
    files = sorted((ROOT / "plugins").rglob("run.py"))
    files += sorted((ROOT / "techdeck").rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts]


def _called_name(node: ast.Call) -> str:
    """'ask_flow' from `ask_flow(...)`, `sdk.ask_flow(...)` or
    `flow_client.ask_flow(...)`."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_no_flow_call_happens_inside_a_loop():
    """E-FLOW-1. One call, one answer. A batch of work is ONE call that returns
    a job id -- never a call per item."""
    offenders = []
    for path in _python_files():
        # The client's own outbox loop is the one legitimate place: it is the
        # delivery mechanism, bounded by `limit`, and it stops on the first
        # unreachable flow instead of hammering it.
        if path.name == "flow_client.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, LOOP_NODES):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and _called_name(inner) in FLOW_CALLS:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{inner.lineno} "
                        f"{_called_name(inner)}() inside a "
                        f"{type(node).__name__.lower()}")
    assert not offenders, (
        "A flow call inside a loop (E-FLOW-1). A two-way call costs 1-5 s and "
        "the platform cannot answer after 120 s: send ONE call with the whole "
        "batch and let the flow hand back a job id.\n  "
        + "\n  ".join(offenders))


def test_no_plugin_posts_to_a_flow_on_its_own():
    """E-FLOW-2. Every flow call goes through the SDK, which owns the timeout,
    the fallback, the command_id, the sandbox guard and the outbox."""
    offenders = []
    for path in sorted((ROOT / "plugins").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\brequests\s*\.\s*(post|put|patch|request)\b",
                                 text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line} {match.group(0)}")
    assert not offenders, (
        "A plugin is posting on its own (E-FLOW-2). Use sdk.ask_flow (two-way) "
        "or sdk.post_webhook (one-way): a direct call has no timeout, no "
        "fallback, no command_id, no sandbox guard and no outbox.\n  "
        + "\n  ".join(offenders))


def test_no_flow_address_outside_constants():
    """E-FLOW-3. One place holds them, so the publish scrub can find them all."""
    pattern = re.compile(r"https://[^\s\"']*(?:powerplatform\.com|logic\.azure\.com)"
                         r"[^\s\"']*")
    allowed = {
        Path("techdeck/core/constants.py"),
        Path("tests/tools/test_two_way_flow_rules.py"),
        Path("tests/tools/test_publish_scrub.py"),
    }
    offenders = []
    for path in _python_files():
        rel = path.relative_to(ROOT)
        if rel in allowed:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            line = path.read_text(encoding="utf-8").count("\n", 0, match.start()) + 1
            offenders.append(f"{rel}:{line}")
    assert not offenders, (
        "A flow address outside constants.py (E-FLOW-3). Put it in "
        "techdeck/core/constants.py so the publish scrub can redact it.\n  "
        + "\n  ".join(offenders))


def test_the_sdk_re_exports_the_two_way_helpers():
    """A plugin imports the SDK and nothing else. If a helper stops being
    re-exported, every plugin that uses it breaks at runtime, not at import."""
    from techdeck.core import plugin_sdk as sdk
    for name in ("ask_flow", "FlowAnswer", "queue_command", "flush_outbox",
                 "outbox_depth", "flow_cache_get", "flow_cache_put",
                 "new_command_id", "build_envelope"):
        assert hasattr(sdk, name), f"sdk.{name} is missing"
