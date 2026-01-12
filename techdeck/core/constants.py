"""
TechDeck Constants
Central location for app-wide constants and configuration values.
"""

# Application metadata
APP_NAME = "TechDeck"
APP_VERSION = "0.7.6"  # Changed from 0.7.6 to test live updates
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
WINDOW_DEFAULT_WIDTH = 1200
WINDOW_DEFAULT_HEIGHT = 800
CONSOLE_MIN_HEIGHT = 150
CONSOLE_DEFAULT_HEIGHT = 250
CONSOLE_MAX_HEIGHT = 400

# Tile dimensions
TILE_MIN_WIDTH = 150
TILE_MIN_HEIGHT = 120

# Access control
ACCESS_CHECK_URL = "https://example.com/techdeck/allowlist.json"  # TODO: Update with real URL
ACCESS_CHECK_INTERVAL_HOURS = 24
OFFLINE_GRACE_PERIOD_DAYS = 7

# API Configuration
OPENAI_MODEL = "gpt-4-turbo-preview"
OPENAI_MAX_TOKENS = 4000
OPENAI_TEMPERATURE = 0.7

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
