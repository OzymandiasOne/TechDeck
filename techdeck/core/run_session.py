"""
RunSession — the mutable state of one Home "Run Selected" run.

Consolidates the flags that used to be scattered across HomePage (`_is_running`,
`_plugin_queue`, `_plugin_params`, `_shared_state`, and the pause/shelve flags)
into one named object owned by RunController. Pure state — no Qt, no logic.
"""

from dataclasses import dataclass, field
from typing import Optional


def _fresh_shared() -> dict:
    """A per-run, per-family scratch dict. plugin_sdk.request_batch_number caches
    the first answer here so same-family plugins in a multi-run reuse it."""
    return {"911": {}, "922": {}, "General": {}}


@dataclass
class RunSession:
    is_running: bool = False              # True while any plugin is executing
    queue: list = field(default_factory=list)          # remaining tile_ids to run
    params: dict = field(default_factory=dict)         # params dict handed to the executor
    shared_state: dict = field(default_factory=_fresh_shared)
    # Pause / resume (Phase C): paused between a pause event and /resume;
    # paused_tile_id is the plugin parked when pause hit (re-queued at the head).
    paused: bool = False
    paused_tile_id: Optional[str] = None
    # Deferred shelve (Phase D): /shelve mid-run lets the current plugin finish,
    # then saves the remainder (consumed in RunController._on_plugin_complete).
    shelve_after_current: bool = False
