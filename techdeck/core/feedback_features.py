"""
Feedback "Which Feature?" option list — built live from the installed app
library so it can never go stale.

Behaviour (user spec, 2026-07-30):
  * The dropdown always reflects whatever plugins the Library currently has —
    add a plugin and it shows up automatically. This INCLUDES locked plugins
    (e.g. ASA: The Video Game): they ship on disk and are only hidden in the
    Library, so the loader still discovers them and users can report on things
    they haven't unlocked.
  * A plugin that disappears from the roster is RETIRED, not dropped — it stays
    in the list with a " (RETIRED)" suffix so someone can still file feedback
    about it right after it's pulled.
  * A retired entry is purged once it has survived `PURGE_AFTER_UPDATES` (5)
    TechDeck version updates — i.e. once the dropdown has been rebuilt under 5
    distinct APP_VERSION values while the plugin was still absent.
  * A retired plugin that comes back (re-installed) is silently un-retired.

State persists in settings under "feedback_features":
    {
      "active":  ["911 Setup", "922 Setup", ...],           # last-seen roster
      "retired": {"Old Plugin": {"updates": 2, "last_version": "0.8.6.10"}},
    }

`get_feature_options()` is the only entry point the UI needs. It reconciles the
state against the live roster (persisting the result) and returns the ordered
list to drop straight into the combo box.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from techdeck.core.constants import APP_VERSION
from techdeck.core.plugin_loader import PluginLoader

logger = logging.getLogger(__name__)

# Fixed, non-plugin entries. "General" leads; the catch-alls close the list.
TOP_FIXED = ["TechDeck (General)"]
BOTTOM_FIXED = ["New - Suggestion Box", "Other"]

RETIRED_SUFFIX = " (RETIRED)"
PURGE_AFTER_UPDATES = 5

# Family display order for a stable, grouped dropdown (unknown families last).
_FAMILY_ORDER = {"902": 0, "911": 1, "922": 2, "QA": 3, "General": 4, "Games": 5}


def _live_plugin_names(plugin_loader: Optional[PluginLoader]) -> List[str]:
    """Display names of every installed plugin (locked ones included), grouped
    by family then name so the dropdown order is stable across rebuilds."""
    loader = plugin_loader
    if loader is None:
        loader = PluginLoader()
        loader.discover_plugins()
    plugins = sorted(
        loader.get_all_plugins(),
        key=lambda p: (_FAMILY_ORDER.get(p.family, 99), (p.name or "").lower()),
    )
    names: List[str] = []
    seen = set()
    for p in plugins:
        name = (p.name or "").strip()
        # Two plugins shouldn't share a display name, but never double an entry.
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def get_feature_options(settings=None,
                        plugin_loader: Optional[PluginLoader] = None) -> List[str]:
    """Ordered "Which Feature?" options, reconciled against the live roster.

    `settings` may be None (persistence is simply skipped — the list is built
    fresh from the live roster with no retirement tracking).
    """
    live = _live_plugin_names(plugin_loader)

    # No settings -> can't persist retirement state; just show the live roster.
    if settings is None:
        return _compose(live, {})

    state = settings.get_feedback_feature_state() or {}
    active = list(state.get("active", []))
    retired = dict(state.get("retired", {}))

    # First run: seed the baseline from the live roster so nothing is falsely
    # retired on the very first open.
    if not active and not retired:
        settings.set_feedback_feature_state({"active": live, "retired": {}})
        return _compose(live, {})

    # Discovery hiccup (roster momentarily empty): don't retire the whole app —
    # return the last-known list untouched.
    if not live:
        logger.warning("Feedback feature list: live roster came back empty; "
                       "keeping the persisted list.")
        return _compose(active, retired)

    live_set = set(live)
    active_set = set(active)

    # 1) Re-instate anything that came back; register brand-new plugins.
    for name in live:
        retired.pop(name, None)
        active_set.add(name)

    # 2) Retire actives that are no longer in the live roster.
    for name in list(active_set):
        if name not in live_set:
            active_set.discard(name)
            retired.setdefault(name, {"updates": 0, "last_version": APP_VERSION})

    # 3) Advance each retired entry's clock once per observed version change,
    #    and purge once it has ridden out PURGE_AFTER_UPDATES of them.
    for name in list(retired.keys()):
        info = retired[name]
        if info.get("last_version") != APP_VERSION:
            info["updates"] = int(info.get("updates", 0)) + 1
            info["last_version"] = APP_VERSION
        if int(info.get("updates", 0)) >= PURGE_AFTER_UPDATES:
            del retired[name]

    # Persist reconciled state; keep `active` in live (family/name) order.
    new_active = [n for n in live if n in active_set]
    settings.set_feedback_feature_state({"active": new_active, "retired": retired})
    return _compose(new_active, retired)


def _compose(active: List[str], retired: dict) -> List[str]:
    """Assemble the final dropdown: fixed top, active plugins, retired (suffixed,
    alphabetical), fixed bottom."""
    options = list(TOP_FIXED)
    options += active
    options += [n + RETIRED_SUFFIX for n in sorted(retired, key=str.lower)]
    options += BOTTOM_FIXED
    return options
