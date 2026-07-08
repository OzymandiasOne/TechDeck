"""
TechDeck Feedback Writer
========================
Delivers a feedback submission to the maintainer.

PRIMARY PATH — telemetry webhook (when TELEMETRY_WEBHOOK_URL is set): the
submission POSTs to the maintainer's Power Automate flow, which appends it
to a collection workbook in the maintainer's own OneDrive. Works for every
user regardless of which SharePoint libraries their machine syncs — there
is no SharePoint location all users share, which is why the webhook exists.
See docs/USAGE_TELEMETRY.md for the flow recipe.

LEGACY PATH (webhook not configured in this build): append a row to the
shared TechDeck_Suggestions.xlsx workbook in the OneDrive-synced 922
library. Schema (matches the existing workbook):
    Sheet:   "Feedback"
    Cols:    A=Suggestion, B=Which Feature?, C=Date Logged, D=Action Taken?
Concurrent-write conflicts are tolerated (rare at feedback volume): OneDrive
creates a conflict copy the maintainer merges manually. If the file is
locked (open in Excel), the write retries a few times then surfaces a clear
error.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# The workbook lives in the 'Notes' subfolder of the 922 QTDR library. We find
# that library via plugin_sdk.library_roots(), which covers EVERY way OneDrive
# may have synced it: the whole-site 'Pilot Program' layout, a directly-synced
# single library named 'Communication site - 922 QTDR Production Packages', and
# any folder a user pointed a 922 app at in Settings > Apps. The old code only
# reconstructed '<pilot root>/922 QTDR Production Packages/Notes', so a machine
# that synced the library directly (no 'Pilot Program' parent) never found the
# workbook and feedback submission failed — the bug this resolves.
_FEEDBACK_LIBRARY = "922 QTDR Production Packages"
_FEEDBACK_SUBDIR = "Notes"
_FEEDBACK_FILENAME = "TechDeck_Suggestions.xlsx"
_FEEDBACK_SHEET_NAME = "Feedback"


def feedback_candidate_paths() -> list:
    """Every location we look for the workbook (also used for error messages)."""
    from techdeck.core import plugin_sdk as sdk
    return [root / _FEEDBACK_SUBDIR / _FEEDBACK_FILENAME
            for root in sdk.library_roots(_FEEDBACK_LIBRARY)]


def feedback_file_path() -> Optional[Path]:
    """First EXISTING candidate for the shared feedback workbook across every
    OneDrive sync layout, or None if it isn't synced anywhere."""
    for candidate in feedback_candidate_paths():
        if candidate.exists():
            return candidate
    return None


def _expected_locations() -> list:
    """Representative paths where the workbook SHOULD live (existing or not) —
    for the not-found error message, since feedback_candidate_paths() only lists
    libraries that actually exist on disk (none, when nothing is synced)."""
    from techdeck.core import plugin_sdk as sdk
    out = [root / _FEEDBACK_LIBRARY / _FEEDBACK_SUBDIR / _FEEDBACK_FILENAME
           for root in sdk.pilot_program_roots()]
    # The directly-synced single-library layout, too.
    out.append(Path.home() / "American Steel & Alum"
               / f"Communication site - {_FEEDBACK_LIBRARY}"
               / _FEEDBACK_SUBDIR / _FEEDBACK_FILENAME)
    return out


# ---------------------------------------------------------------------------
# Workbook helpers
# ---------------------------------------------------------------------------

def _append_row_with_retry(path: Path, row: list, max_attempts: int = 4,
                           delay_seconds: float = 0.75) -> None:
    """
    Open the workbook, append to the Feedback sheet, save. Retries on
    PermissionError (file locked by another process - usually Excel itself
    or an OS sync). After max_attempts, re-raises the last error so the
    caller can show it to the user.
    """
    from techdeck.core import plugin_sdk as sdk
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            wb = sdk.load_workbook_resilient(path)
            try:
                if _FEEDBACK_SHEET_NAME not in wb.sheetnames:
                    raise ValueError(
                        f"Sheet '{_FEEDBACK_SHEET_NAME}' not found in "
                        f"{path.name}. Existing sheets: {wb.sheetnames}"
                    )
                ws = wb[_FEEDBACK_SHEET_NAME]
                ws.append(row)
                wb.save(path)
            finally:
                wb.close()
            return
        except PermissionError as e:
            last_err = e
            logger.warning(
                f"Feedback write attempt {attempt}/{max_attempts} failed "
                f"(file locked): {e}"
            )
            time.sleep(delay_seconds)
        except Exception:
            # Non-lock errors aren't worth retrying
            raise

    assert last_err is not None
    raise last_err


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_feedback(suggestion: str, which_feature: str) -> str:
    """
    Deliver a feedback submission and return a short human-readable phrase
    describing where it went (dropped into the dialog's success message,
    e.g. "sent to the TechDeck developer" / "saved to X.xlsx").

    Args:
        suggestion: The user's suggestion or bug report text.
        which_feature: Which feature/plugin it relates to.

    Webhook path raises:
        RuntimeError: delivery failed (offline, flow down) — retryable.

    Legacy workbook path raises:
        FileNotFoundError: if the workbook does not exist (OneDrive not
            synced, or file was renamed/moved).
        PermissionError: if the file is locked and all retries failed.
        ValueError: if the workbook is missing the expected Feedback sheet.
        OSError: for other I/O problems.
    """
    from techdeck.core.constants import TELEMETRY_WEBHOOK_URL
    if TELEMETRY_WEBHOOK_URL:
        from techdeck.core.usage_tracker import send_feedback_event
        try:
            send_feedback_event(suggestion, which_feature)
        except Exception as e:
            logger.warning(f"Feedback webhook delivery failed: {e}")
            raise RuntimeError(
                "Could not reach the feedback service. Check your network "
                "connection and try again in a minute."
            ) from e
        logger.info("Feedback delivered via telemetry webhook")
        return "sent to the TechDeck developer"

    path = feedback_file_path()

    if path is None:
        tried = "\n".join(f"  {p}" for p in _expected_locations())
        raise FileNotFoundError(
            f"{_FEEDBACK_FILENAME} was not found in any OneDrive location. "
            f"Expected it in one of:\n{tried}\n\n"
            "Make sure the '922 QTDR Production Packages' SharePoint library is "
            "synced to OneDrive on this machine (either via the whole "
            "'Communication site - Electric Boat ASA Docs' site, or the library "
            "synced directly), with the workbook under its Notes folder."
        )

    # Match the existing schema: A=Suggestion, B=Which Feature, C=Date Logged,
    # D=Action Taken? (left blank for the maintainer).
    row = [
        suggestion,
        which_feature,
        datetime.now(),
        None,
    ]

    _append_row_with_retry(path, row)
    logger.info(f"Feedback row appended to {path}")
    return f"saved to {path.name}"
