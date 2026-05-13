"""
LST Organizer Plugin for TechDeck
Wrapper for the full LST Organizer v14 script.

This plugin provides TechDeck integration while preserving the full
700-line functionality of the original LST Organizer script.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any

from techdeck.core.utils import find_python


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    """
    Main plugin execution function.

    Args:
        params: Dictionary containing 'settings', 'log'
        progress_callback: Function to call with progress (0-100)
        cancel_event: threading.Event to check for cancellation
    """
    settings = params.get('settings', {})
    log = params.get('log', print)

    log("📋 Starting LST Organizer...")
    progress_callback(0)

    # Get settings
    base_path = settings.get('base_path', '')
    batch_no = settings.get('batch_number', '')
    master_po = settings.get('master_po_path', '')
    dry_run = settings.get('dry_run', False)

    # Validate settings
    if not base_path:
        log("❌ Base directory not configured!")
        log("Go to: Settings > Plugin Settings > LST Organizer")
        raise ValueError("Base directory not configured")

    if not batch_no:
        log("❌ Batch number not configured!")
        log("Go to: Settings > Plugin Settings > LST Organizer")
        raise ValueError("Batch number not configured")

    base_path_obj = Path(base_path)
    if not base_path_obj.is_dir():
        log(f"❌ Base directory not found: {base_path}")
        raise ValueError(f"Base directory not found: {base_path}")

    log(f"📁 Base directory: {base_path}")
    log(f"🔢 Batch number: {batch_no}")

    # Locate the full LST Organizer script alongside this run.py
    plugin_dir = Path(__file__).parent
    full_script = plugin_dir / "LSTOrganizer_full.py"

    if not full_script.exists():
        log(f"❌ Full LST Organizer script not found at: {full_script}")
        log(f"   Place 'LSTOrganizer_full.py' in the plugin directory:")
        log(f"   {plugin_dir}")
        raise FileNotFoundError(f"LSTOrganizer_full.py not found in {plugin_dir}")

    log("✅ Found full LST Organizer script")
    log("")
    progress_callback(5)

    # Build command
    python_exe = find_python()
    cmd = [
        python_exe,
        str(full_script),
        "--batch", batch_no
    ]

    if master_po:
        cmd.extend(["--po", master_po])
        log(f"📄 Using Master PO: {master_po}")

    if dry_run:
        cmd.append("--kill")
        log("⚠️ DRY RUN MODE - No files will be copied")

    log("🚀 Executing LST Organizer...")
    log("=" * 60)
    progress_callback(10)

    # Execute the full script and stream output
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
        )

        for line in process.stdout:
            if cancel_event.is_set():
                process.terminate()
                log("")
                log("⚠️ Cancelled by user")
                return

            line = line.rstrip()
            if line:
                log(line)

        process.wait()

        log("=" * 60)

        if process.returncode == 0:
            log("✅ LST Organizer completed successfully!")
            progress_callback(100)
        else:
            log(f"❌ LST Organizer exited with code {process.returncode}")
            raise RuntimeError(f"Process exited with error code {process.returncode}")

    except FileNotFoundError:
        log(f"❌ Python interpreter not found: {python_exe}")
        raise RuntimeError(f"Python interpreter not found: {python_exe}")
    except RuntimeError:
        raise
    except Exception as e:
        log(f"❌ Execution error: {e}")
        raise RuntimeError(f"Error executing LST Organizer: {e}")


if __name__ == "__main__":
    import threading

    test_settings = {
        'base_path': input("Enter base path: ").strip() or str(
            Path.home() / "American Steel & Alum"
            / "Communication site - Electric Boat ASA Docs"
            / "Pilot Program"
            / "922 QTDR Production Packages"
        ),
        'batch_number': input("Enter batch number: ").strip(),
        'master_po_path': '',
        'dry_run': False
    }

    cancel_event = threading.Event()

    def progress(p):
        print(f"Progress: {p}%")

    try:
        run(
            params={'settings': test_settings, 'log': print},
            progress_callback=progress,
            cancel_event=cancel_event
        )
        print("\n✅ Done!")
    except Exception as e:
        print(f"\n❌ Failed: {e}")
