"""
TechDeck Constants
Central location for app-wide constants and configuration values.
"""

import os as _os


# ---------------------------------------------------------------------------
# Puppet Master release gate (2026-08-10)
# ---------------------------------------------------------------------------
# The Cheshire-cat console entity is FINISHED and merged on main — the face,
# the summon animations, the 2501 voice, /help delivery. It is being held for a
# Halloween 2026 themed release, so it must not reach colleagues before then.
#
# Reverting it was never an option: it is spread across ~20 commits that other
# console work sits on top of. So it ships DORMANT instead, gated at its three
# (and only three) entry points:
#
#   1. the console's startup greeting + its "redefine" summon link
#   2. the /puppetmaster command
#   3. the techdeck://cat/summon link route
#
# Nothing else can reach it: ConsoleCat is a lazy singleton created only by
# those paths, and active_cat() returns None until one of them runs — so the
# free-text routing and the /help takeover stay dormain automatically.
#
# GOING LIVE AT HALLOWEEN IS THIS ONE FLAG plus merging `halloween-update`
# (which holds the later refinements: hot-reloading script, slang matching,
# the pinned output area, the harvest log).
#
# Set TECHDECK_PUPPET_MASTER=1 in the environment to wake him locally without
# editing code — that is how to demo or test him before the flag flips.
PUPPET_MASTER_ENABLED = False

_TRUTHY = {"1", "true", "yes", "on"}


def puppet_master_enabled() -> bool:
    """True when the Puppet Master may appear. Env override wins so the
    feature can be exercised on a dev machine while shipping off."""
    override = _os.environ.get("TECHDECK_PUPPET_MASTER", "").strip().lower()
    if override:
        return override in _TRUTHY
    return PUPPET_MASTER_ENABLED


# Application metadata
APP_NAME = "TechDeck"
APP_VERSION = "0.8.7.4"  # Plate Work - 911 Setup handles PLATE batches; Scripting Prep type-once PO block
APP_RELEASE_NAME = "TechDeck Beta"
CONFIG_VERSION = "1.0.0"

# Default profile name (always exists, cannot be deleted)
DEFAULT_PROFILE_NAME = "Default"

# Paths (relative to user's home directory)
# These will be resolved at runtime using Path.home()
SETTINGS_DIR_NAME = "TechDeck"
SETTINGS_FILE_NAME = "settings.json"
PLUGINS_DIR_NAME = "plugins"

# UI Constants
# Width chosen so the Home tile grid fits exactly 5 columns at startup: sidebar
# (200) + 5*HOME_TILE_W(140) + margins/spacing/scrollbar. The grid reflows to
# more/fewer columns as the window resizes (see TileGridController).
WINDOW_DEFAULT_WIDTH = 1024
WINDOW_DEFAULT_HEIGHT = 800
CONSOLE_MIN_HEIGHT = 150
CONSOLE_DEFAULT_HEIGHT = 280
CONSOLE_MAX_HEIGHT = 400

# Tile dimensions
TILE_MIN_WIDTH = 150
TILE_MIN_HEIGHT = 120

# Tickets (Woogy's Emporium economy)
TICKETS_PER_RUN = 5        # per successful run, x result.ticket_units when an
                           # orchestrating run reports several systems (922 Setup)
TICKETS_PER_FEEDBACK = 25  # earned for submitting feedback

# Usage telemetry + feedback delivery (see docs/USAGE_TELEMETRY.md).
# The maintainer's Power Automate flow URL ("When a Teams webhook request
# is received"). Baked into the build; empty string = webhook disabled, so
# usage events only accumulate in the local spool and feedback falls back
# to the legacy shared-workbook path.
TELEMETRY_WEBHOOK_URL = "https://REDACTED-ENVIRONMENT.api.powerplatform.com:443/powerautomate/automations/direct/cu/07/workflows/REDACTED-WORKFLOW-ID/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=REDACTED"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # ISO 8601 UTC

# Exit codes (following README spec)
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SETTINGS_ERROR = 2
EXIT_CONFIG_VERSION_MISMATCH = 3
EXIT_NOT_FOUND = 4
EXIT_FILE_LOCKED = 5
EXIT_PERMISSION_ERROR = 7
EXIT_PLUGIN_ERROR = 7
EXIT_DATA_ERROR = 8
EXIT_UNKNOWN = 9
