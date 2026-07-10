"""
<My Plugin> — TechDeck plugin.

Replace this docstring with a short description of what the plugin does, the
runtime inputs it prompts for, and the output it produces.

Folder name MUST equal the "id" in plugin.json (single underscores).
"""

from __future__ import annotations

from pathlib import Path

# SDK bootstrap — works both in-process (TechDeck/frozen exe) and for standalone
# CLI testing (python plugins/<id>/run.py). Prefer SDK helpers over re-rolling
# path/Excel/PDF logic.
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

VERSION = "1.0.0"


def run(params: dict, progress_callback, cancel_event):
    """Entry point. MUST keep this exact signature.

    params['log']          -> thread-safe console logger (falls back to print)
    params['settings']     -> dict of values from plugin.json `settings.fields`
    params['console']      -> ConsoleWidget (None when run headless)
    params['plugin_family']-> "911" | "922" | "other" (injected by the executor)
    progress_callback(int) -> report 0..100
    cancel_event           -> threading.Event; check .is_set() inside long loops
    """
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log("=" * 60)
    log(f"My Plugin v{VERSION}")
    log("=" * 60)

    # --- Resolve inputs -----------------------------------------------------
    # Prefer SDK auto-discovery; fall back to a settings path; prompt only if
    # nothing else works. Use request_text for free-form prompts (NOT
    # request_batch_number unless the answer really is a batch number).
    base = settings.get("base_path", "").strip()
    base_path = Path(base) if base else None
    if base_path is None:
        # e.g. base_path = sdk.resolve_911_qtdr_root()  /  resolve_922_root()
        raw = sdk.request_text(params, "Paste the base directory:")
        if cancel_event.is_set():
            return
        base_path = Path((raw or "").strip().strip('"'))

    if not base_path or not base_path.exists():
        log(f"ERROR: directory not found: {base_path}")
        return
    log(f"Base: {base_path}")
    progress_callback(10)

    # --- Do the work --------------------------------------------------------
    # Look Excel columns up by header NAME via the SDK, never a fixed index:
    #   import openpyxl
    #   wb = openpyxl.load_workbook(path, data_only=True); ws = wb.active
    #   header_row, cols = sdk.find_header_row(ws, ["Nest Pkg Nbr", "PPN Quantity"])
    #   nest_col = cols["NEST PKG NBR"]
    #
    # fitz cannot save in place — use sdk.save_pdf_atomic(doc, dest).
    # Check cancel_event in long loops and keep logging so the idle watchdog
    # (1800s of no activity) never trips.

    if cancel_event.is_set():
        return
    progress_callback(50)

    # ... real work here ...

    progress_callback(100)
    log("\nDONE.")


if __name__ == "__main__":
    # Headless smoke test: python plugins/<id>/run.py
    import threading
    run({"log": print, "settings": {}, "console": None},
        lambda p: print(f"[{p}%]"), threading.Event())
