"""
TechDeck Constants
Central location for app-wide constants and configuration values.
"""

# Application metadata
APP_NAME = "TechDeck"
APP_VERSION = "0.8.6.4"  # Carrots & More Carrots: ticket economy + Woogy's Emporium + My House/Garden + Achievements; new plugins 922 Setup, QA Gemba Analyzer, 911 SSPO Invoicing Prep, 902 DXF Prep (new 902 family); native folder pickers; Professional theme; smaller build
APP_RELEASE_NAME = "TechDeck Beta"
CONFIG_VERSION = "1.0.0"

# Default profile name (always exists, cannot be deleted)
DEFAULT_PROFILE_NAME = "Default"

# Paths (relative to user's home directory)
# These will be resolved at runtime using Path.home()
SETTINGS_DIR_NAME = "TechDeck"
SETTINGS_FILE_NAME = "settings.json"
METRICS_FILE_NAME = "metrics.jsonl"
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
TICKETS_PER_RUN = 5        # earned per successful plugin run
TICKETS_PER_FEEDBACK = 25  # earned for submitting feedback

# Usage telemetry + feedback delivery (see docs/USAGE_TELEMETRY.md).
# The maintainer's Power Automate flow URL ("When an HTTP request is
# received"). Baked into the build; empty string = webhook disabled, so
# usage events only accumulate in the local spool and feedback falls back
# to the legacy shared-workbook path.
TELEMETRY_WEBHOOK_URL = ""

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
