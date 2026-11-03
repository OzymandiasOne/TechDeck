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
PUPPET_MASTER_ENABLED = True    # flipped for the Halloween Update (0.8.7.8, 2026-10-05)

_TRUTHY = {"1", "true", "yes", "on"}


def puppet_master_enabled(settings=None) -> bool:
    """True when the Puppet Master may appear: the app is WEARING the
    halloween theme, and professional is not the user's own pick.

    He is no longer a calendar feature. Anthony, 2026-11-03: "puppetmaster
    should be relegated to just halloween theme (halloween theme stays on
    everyone's techdecks)." In season everyone wears halloween, so everyone
    still gets him exactly as before; out of season he belongs to whoever
    chooses the theme on purpose, which is why the picker now stocks
    halloween all year (SettingsPage._theme_choices). Hiding the theme in
    November would wall him off for good.

    The read is the WORN theme (``get_theme``), never the stored one: a user
    on dark during the season is shown the halloween look and should get him
    with it. Professional opts out even while wearing it, the same carve-out
    ``is_professional`` exists for - no puppet talking over a client demo.

    ``PUPPET_MASTER_ENABLED`` stays the master kill switch above all of this,
    and ``TECHDECK_PUPPET_MASTER`` still wins outright so he can be exercised
    on a dev machine in July. Fails CLOSED: any error reading settings hides
    him rather than leaking him.

    ``settings`` is injectable for tests, like ``halloween_active``.
    """
    override = _os.environ.get("TECHDECK_PUPPET_MASTER", "").strip().lower()
    if override:
        return override in _TRUTHY
    if not PUPPET_MASTER_ENABLED:
        return False
    try:
        if settings is None:
            from techdeck.core.settings import SettingsManager
            settings = SettingsManager()
        if settings.is_professional():
            return False
        return settings.get_theme() == "halloween"
    except Exception:
        return False


def gate_enabled(name: str) -> bool:
    """A plugin.json `gate` by name: the plugin is not discovered at all while
    its gate is shut (so it is absent from the Library, /moredetails, Sentry -
    everything). Unknown gate names are shut, so a typo cannot leak a plugin."""
    return {"puppet_master": puppet_master_enabled}.get(name, lambda: False)()


# ── The Halloween season gate ──────────────────────────────────────────────
# Every Halloween-update feature (theme visuals, the bat, the ghost, /seance,
# limited Emporium stock, garden props, the Haunting) checks ONE switch:
# halloween_active(). Two layers:
#
#   is_halloween_season()  — the calendar window, Oct 1 – Nov 2 inclusive
#                            (long enough to be an event, gone before anyone
#                            reports it as a bug). TECHDECK_HALLOWEEN=1/0
#                            overrides it for dev work in any month — same
#                            contract as TECHDECK_PUPPET_MASTER above.
#   halloween_active()     — the season AND not the professional theme; the
#                            professional theme suppresses the FEATURES
#                            (crawlies, /seance, stock, props), exactly like
#                            every other personality feature.
#
# The THEME is not one of those features. A seasonal theme we decide the app
# should open in applies to EVERYONE in season, professional included (his
# call, 2026-10-16) — see effective_theme(). Professional keeps its sober
# feature set because is_professional() reads the STORED choice, not the theme
# actually being worn.
#
# Features must check the function at USE time (never cache it at import), so
# a session left open across Nov 2 midnight quietly reverts to normal.

HALLOWEEN_SEASON = ((10, 1), (11, 2))   # inclusive (month, day) window


def is_halloween_season(today=None) -> bool:
    """True inside the Halloween window. Pass ``today`` (a date) for pure
    calendar logic — tests do; otherwise the env override wins, then the
    real clock."""
    if today is None:
        override = _os.environ.get("TECHDECK_HALLOWEEN", "").strip().lower()
        if override:
            return override in _TRUTHY
        import datetime
        today = datetime.date.today()
    return (HALLOWEEN_SEASON[0] <= (today.month, today.day)
            <= HALLOWEEN_SEASON[1])


def effective_theme(stored: str, opt_out_year=None, today=None) -> str:
    """The theme the app actually WEARS, given the user's stored choice.

    THE ONE PLACE this rule lives. It had been written twice — in
    SettingsManager.get_theme and again in __main__._current_theme_name for
    the splash — so the two could drift.

    In season the seasonal theme is the default for EVERYONE, professional
    included: a theme we decide the app should open in is a decision about
    the product, not a personality feature (his call, 2026-10-16, after a
    user on professional silently missed the whole Halloween look). The
    only thing that overrides it is an EXPLICIT opt-out: picking another
    theme during a season records that year (SettingsManager.set_theme),
    and the opt-out expires with the year, so next October the magic
    returns.

    Professional's sober FEATURE set is unaffected — that is
    SettingsManager.is_professional(), which reads the STORED theme, never
    this.
    """
    if not is_halloween_season(today):
        return stored
    import datetime
    year = (today or datetime.date.today()).year
    if opt_out_year == year:
        return stored
    return "halloween"


def halloween_active(settings=None) -> bool:
    """The one switch Halloween features check: season on AND the
    professional theme off. ``settings`` injectable for tests; defaults to
    the real SettingsManager (imported lazily — settings.py imports this
    module)."""
    if not is_halloween_season():
        return False
    try:
        if settings is None:
            from techdeck.core.settings import SettingsManager
            settings = SettingsManager()
        return not settings.is_professional()
    except Exception:
        return False


# Application metadata
APP_NAME = "TechDeck"
APP_VERSION = "0.8.9"  # New app: 922 Production Packets builds the tube cutting list, the material binders and the production run binders; a work packet that lost its text still reads; a narrow invoice date prints in full
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
