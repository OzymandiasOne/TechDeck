"""
Sentry Drone mode — the purchasable picker toy, and who it applies to.

Sentry Drone is an Emporium GADGET (``toy_sentry_drone``). Owning it unlocks the
targeting-drone kill-cam picker (chopper_picker.py) for the apps that make you
pick a file or folder out of Windows Explorer — but it is OPT-IN PER APP, not
all-or-nothing:

* **Ownership** — one flag: ``settings.is_unlocked(ITEM_ID)``. Until it's bought
  the drone never fires anywhere, and the per-app setting stays hidden in
  Settings -> Apps (plugin.json field ``"hidden_unless_unlocked"``).
* **Per-app opt-in** — the plugin's own ``sentry_drone`` boolean setting. A
  plugin advertises that it CAN use the drone simply by declaring that field in
  its plugin.json (see :func:`compatible_plugins`); ``default: false``, so
  nothing changes for anyone who hasn't bought it and switched it on.

Both must be true for the drone to fire — :func:`is_enabled`. That's the single
gate; the SDK (``sdk.sentry_style``) and the console both consult it, so a stale
plugin copy asking for ``style="chopper_gunner"`` still can't summon a drone the
user doesn't own.

The My Stuff gadget tile opens ``SentryConfigDialog``, which is nothing more than
a bulk editor over those same per-plugin settings — one source of truth, so the
window and Settings -> Apps can never disagree.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Catalog id of the Emporium gadget (techdeck/ui/emporium_catalog.py).
ITEM_ID = "toy_sentry_drone"

# The per-plugin boolean setting key. Declaring this field in plugin.json is
# what makes a plugin "Sentry-compatible" — there is no second list to maintain.
SETTING_KEY = "sentry_drone"

# The style token the console understands (chopper_picker.py).
STYLE = "chopper_gunner"

# Boilerplate every compatible plugin.json copies verbatim, so the wording (and
# the hidden-until-bought gate) stays identical everywhere. Kept here as the
# reference copy; tools/check_ship_readiness.py checks plugins against it.
FIELD_LABEL = "Sentry Drone mode"
FIELD_DESCRIPTION = (
    "Pick the file or folder through the targeting-drone kill-cam - crosshair "
    "cursor, lock-on, and a railgun strike on the target. Off = a normal "
    "Explorer dialog."
)


def _settings(settings=None):
    """The live SettingsManager (it's a singleton), or None when unavailable."""
    if settings is not None:
        return settings
    try:
        from techdeck.core.settings import SettingsManager
        return SettingsManager()
    except Exception:
        return None


def is_owned(settings=None) -> bool:
    """True once the Sentry Drone has been bought at Woogy's Emporium."""
    s = _settings(settings)
    if s is None:
        return False
    try:
        return bool(s.is_unlocked(ITEM_ID))
    except Exception:
        return False


def is_enabled(plugin_id: str, settings=None) -> bool:
    """True when the drone is owned AND switched on for this plugin."""
    if not plugin_id or not is_owned(settings):
        return False
    s = _settings(settings)
    if s is None:
        return False
    try:
        return bool(s.get_plugin_setting(plugin_id, SETTING_KEY, False))
    except Exception:
        return False


def set_enabled(plugin_id: str, enabled: bool, settings=None) -> None:
    """Switch the drone on/off for one plugin (the same value Settings shows)."""
    s = _settings(settings)
    if s is None or not plugin_id:
        return
    s.set_plugin_setting(plugin_id, SETTING_KEY, bool(enabled))


def declares_sentry_field(plugin_json: Dict[str, Any]) -> bool:
    """Does this plugin.json declare the sentry_drone settings field?"""
    fields = (plugin_json.get("settings") or {}).get("fields") or []
    return any(isinstance(f, dict) and f.get("key") == SETTING_KEY for f in fields)


def compatible_plugins(plugin_loader=None, settings=None) -> List[Dict[str, Any]]:
    """Every installed plugin that can use the drone, as plain dicts:
    ``{"id", "name", "family", "enabled"}`` sorted by family then name.

    Compatibility is declared, not hardcoded: a plugin is in this list iff its
    plugin.json carries the ``sentry_drone`` field. Add the field to a new
    picker plugin and it shows up here (and in the My Stuff window) for free.
    """
    loader = plugin_loader
    if loader is None:
        try:
            from techdeck.core.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.discover_plugins()
        except Exception:
            logger.exception("Sentry: could not discover plugins")
            return []
    plugins = list(loader.get_all_plugins() or [])
    if not plugins:
        try:
            plugins = list(loader.discover_plugins() or [])
        except Exception:
            plugins = []

    out: List[Dict[str, Any]] = []
    for plugin in plugins:
        try:
            manifest = plugin.path / "plugin.json"
            with open(manifest, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not declares_sentry_field(data):
            continue
        out.append({
            "id": plugin.id,
            "name": plugin.name,
            "family": plugin.family,
            "enabled": is_enabled(plugin.id, settings),
        })
    out.sort(key=lambda p: (p["family"], p["name"].lower()))
    return out


def style_for(plugin_id: str, settings=None) -> Optional[str]:
    """``STYLE`` when the drone should fire for this plugin, else None —
    the value to hand to ``sdk.request_directory(..., style=...)``."""
    return STYLE if is_enabled(plugin_id, settings) else None
