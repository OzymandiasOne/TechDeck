"""
Batch Repeater Plugin for TechDeck v2.0.0 - WITH CONSOLE INPUT!
Copies repeat orders from previous batches into new batch REPEAT BATCHES folder.

NEW: Prompts for PO number and batch name via console during execution!
FIXED: Settings keys now match plugin.json, proper logging to TechDeck console
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

# Hardcoded constants
SHEET_NAME = "PO 321+"
COMPLETED_FOLDER_NAME = "1 - Completed"


def get_console_input(params: Dict[str, Any], prompt: str) -> str:
    """
    Get input from user via TechDeck console.
    
    Args:
        params: Plugin params (contains 'console' reference)
        prompt: Question to ask user
        
    Returns:
        User's input as string
    """
    console = params.get('console')
    if console and hasattr(console, 'request_input'):
        return console.request_input(prompt)
    raise RuntimeError(
        "Batch Repeater requires user input but no TechDeck console is available. "
        "Run this plugin from within TechDeck."
    )


def find_batch_root(source_po: int, base_path: Path, completed_root: Path,
                    cancel_event=None) -> Optional[Path]:
    """Locate the folder named 'Batch {source_po}'."""
    target = f"Batch {source_po}"

    # 1) Active root
    candidate1 = base_path / target
    if candidate1.exists():
        return candidate1

    # 2) Direct child of completed
    candidate2 = completed_root / target
    if candidate2.exists():
        return candidate2

    # 3) Nested child (recursive search). Poll cancel_event while walking the
    # '1 - Completed' archive — it can be a very large OneDrive tree, and without
    # the check a Cancel click can't interrupt this walk.
    if completed_root.exists():
        target_lower = target.lower()
        for i, (root, dirs, _) in enumerate(os.walk(completed_root)):
            if cancel_event is not None and i % 64 == 0 and cancel_event.is_set():
                break
            for d in dirs:
                if d.lower() == target_lower:
                    return Path(root) / d

    return None


def run(params: Dict[str, Any], progress_callback, cancel_event) -> None:
    """
    Main plugin execution function.
    
    Args:
        params: Dictionary containing 'settings', 'console', and 'log'
        progress_callback: Function to call with progress (0-100)
        cancel_event: threading.Event to check for cancellation
    """
    settings = params.get('settings', {})
    log = params.get('log', print)  # Get log callback
    
    log("Starting 922 Batch Repeater v2.0.0...")
    progress_callback(0)
    
    # Base directory is an optional override; auto-discover by default so the
    # user never has to configure a path everyone already shares.
    base_directory = settings.get('base_directory', '')
    spreadsheet_filename = (settings.get('spreadsheet_filename', '') or '').strip() or '922 MPL.xlsx'

    base_path = sdk.resolve_922_root(base_directory)
    if base_path is None or not base_path.exists():
        log("ERROR: Could not locate '922 QTDR Production Packages'.")
        log("Verify OneDrive is synced, or set Base Directory in plugin settings.")
        raise ValueError("922 QTDR Production Packages root not found")

    spreadsheet_path = base_path / spreadsheet_filename
    if not spreadsheet_path.exists():
        log(f"ERROR: Spreadsheet not found: {spreadsheet_path}")
        raise ValueError(f"Spreadsheet not found: {spreadsheet_path}")

    completed_root = base_path / COMPLETED_FOLDER_NAME
    
    log("")
    log(f"Base directory: {base_path}")
    log(f"Spreadsheet: {spreadsheet_path.name}")
    log(f"Sheet: {SHEET_NAME}")
    log("")
    
    progress_callback(5)
    
    # === ASK FOR BATCH FOLDER NAME ===
    log("Input required from user...")
    batch_name_input = sdk.request_batch_number(
        params,
        "Enter batch number or full folder name (e.g., '429' or 'Batch 429')"
    )

    raw_input = batch_name_input.strip()
    if not raw_input:
        log("ERROR: Batch name cannot be empty!")
        raise ValueError("Batch name cannot be empty")

    # Extract a number from whatever the user typed
    num_match = re.search(r'\d+', raw_input)
    if num_match:
        extracted_num = num_match.group()
        # Search base_path for any folder whose name contains that exact number
        # (not preceded or followed by another digit, so "467" won't match "14670")
        number_pattern = re.compile(r'(?<!\d)' + re.escape(extracted_num) + r'(?!\d)')
        matched_folder = None
        try:
            for entry in os.listdir(base_path):
                if (base_path / entry).is_dir() and number_pattern.search(entry):
                    matched_folder = entry
                    break
        except (FileNotFoundError, PermissionError) as e:
            log(f"WARNING: Could not scan base directory: {e}")

        if matched_folder:
            actual_batch_name = matched_folder
            log(f"Matched existing folder: {actual_batch_name}")
        else:
            actual_batch_name = f"Batch {extracted_num}"
            log(f"No existing folder found - will create: {actual_batch_name}")
    else:
        # No number in input - use raw input as folder name (will create new)
        actual_batch_name = raw_input
        log(f"Using batch name: {actual_batch_name}")
    
    # === EXTRACT PO NUMBER FROM BATCH NAME ===
    # Look for numbers in the batch name
    po_match = re.search(r'\d+', actual_batch_name)
    if not po_match:
        log("ERROR: Could not find PO number in batch name!")
        log("   Batch name must contain a number (e.g., 'Batch 429')")
        raise ValueError("Could not extract PO number from batch name")
    
    new_po_num = int(po_match.group())
    log(f"Extracted PO: {new_po_num}")
    
    log("")
    log(f"PO Number: {new_po_num}")
    log(f"Batch folder: {actual_batch_name}")
    log("")
    
    progress_callback(10)
    
    # Check for cancellation
    if cancel_event.is_set():
        log("Operation cancelled")
        return
    
    # Read Excel file
    log("Reading Excel spreadsheet...")
    try:
        sdk.ensure_local(spreadsheet_path, log)  # OneDrive placeholder -> download first (Hard Rule 13)
        df = pd.read_excel(spreadsheet_path, sheet_name=SHEET_NAME, header=2)
    except Exception as e:
        log(f"ERROR: Error reading spreadsheet: {e}")
        raise RuntimeError(f"Error reading spreadsheet: {e}")
    
    progress_callback(15)
    
    # Identify PO columns
    log("Identifying PO columns...")
    po_columns: Dict[int, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.strip().lower().startswith("po"):
            m = re.search(r"(\d+)", col)
            if m:
                po_num = int(m.group(1))
                po_columns[po_num] = col
    
    if not po_columns:
        log("ERROR: No PO columns found in spreadsheet.")
        raise ValueError("No PO columns found in spreadsheet.")
    
    log(f"Found {len(po_columns)} PO columns")
    progress_callback(20)
    
    # Check if new PO exists
    if new_po_num not in po_columns:
        available_pos = sorted(po_columns.keys())
        log(f"ERROR: PO {new_po_num} not found. Available: {available_pos}")
        raise ValueError(f"PO {new_po_num} not found. Available: {available_pos}")
    
    new_po_col = po_columns[new_po_num]
    log(f"Using column '{new_po_col}'")
    
    # Setup destination folders
    new_po_folder = base_path / actual_batch_name
    new_po_folder.mkdir(exist_ok=True)
    log(f"Created: {new_po_folder.name}")
    
    repeat_batch_folder = new_po_folder / "REPEAT BATCHES"
    repeat_batch_folder.mkdir(exist_ok=True)
    log(f"Created: REPEAT BATCHES")
    log("")
    
    progress_callback(25)
    
    # Get unique orders
    log("Analyzing orders...")
    new_po_orders = {
        str(order).strip()
        for order in df[new_po_col]
        if pd.notna(order) and str(order).strip()
    }
    log(f"Found {len(new_po_orders)} unique orders")
    
    progress_callback(30)
    
    # Find source PO for each order
    log("Searching for repeat orders...")
    orders_to_copy: Dict[str, int] = {}
    
    for order in new_po_orders:
        source_po_num = None
        for po_num, col in po_columns.items():
            if po_num >= new_po_num:
                continue
            
            column_values = df[col].dropna().astype(str).str.strip()
            if order in column_values.values:
                if source_po_num is None or po_num > source_po_num:
                    source_po_num = po_num
        
        if source_po_num is not None:
            orders_to_copy[order] = source_po_num
    
    log(f"Found {len(orders_to_copy)} repeat orders")
    progress_callback(35)
    
    if not orders_to_copy:
        log("No repeat orders! All new!")
        progress_callback(100)
        return
    
    log("")
    log("Copying order folders...")
    
    # Copy folders with progress
    copied_count = 0
    not_found_count = 0
    error_count = 0
    
    total_orders = len(orders_to_copy)
    base_progress = 35
    progress_range = 60
    
    for idx, (order, source_po) in enumerate(orders_to_copy.items()):
        if cancel_event.is_set():
            log("")
            log("WARNING: Cancelled by user")
            log(f"Copied {copied_count} of {total_orders}")
            return
        
        progress = base_progress + int((idx / total_orders) * progress_range)
        progress_callback(progress)

        # Locating a batch may walk the whole '1 - Completed' archive (slow on a
        # large OneDrive tree); announce it first so the walk doesn't look frozen.
        log(f"[{idx + 1}/{total_orders}] Locating Batch {source_po} for {order}...")
        batch_root = find_batch_root(source_po, base_path, completed_root, cancel_event)
        
        if not batch_root:
            log(f"WARNING: Batch {source_po} not found for {order}")
            not_found_count += 1
            continue
        
        found_folder = None
        try:
            for entry in os.listdir(batch_root):
                entry_path = batch_root / entry
                if entry_path.is_dir() and order.lower() in entry.lower():
                    found_folder = entry_path
                    break
        except (FileNotFoundError, PermissionError) as e:
            log(f"ERROR: Error accessing Batch {source_po}: {e}")
            error_count += 1
            continue
        
        if not found_folder:
            log(f"WARNING: '{order}' not found in Batch {source_po}")
            not_found_count += 1
            continue
        
        destination_folder = repeat_batch_folder / found_folder.name
        try:
            shutil.copytree(found_folder, destination_folder, dirs_exist_ok=True)
            log(f"Copied {order} from Batch {source_po}")
            copied_count += 1
        except Exception as e:
            log(f"ERROR: Failed to copy {order}: {e}")
            error_count += 1
    
    progress_callback(95)
    
    # Summary
    log("")
    log("=" * 50)
    log("COPY SUMMARY")
    log("=" * 50)
    log(f"Successfully copied: {copied_count}")
    
    if not_found_count > 0:
        log(f"Not found: {not_found_count}")
    
    if error_count > 0:
        log(f"Errors: {error_count}")
    
    log("=" * 50)
    
    progress_callback(100)
    
    if error_count > 0 or not_found_count > 0:
        log("WARNING: Completed with warnings")
    else:
        log("All done successfully!")


if __name__ == "__main__":
    # Standalone testing
    import threading
    
    test_settings = {
        'base_directory': input("Base directory path: ").strip(),
        'spreadsheet_filename': input("Spreadsheet filename [922 MPL.xlsx]: ").strip() or "922 MPL.xlsx"
    }
    
    cancel_event = threading.Event()
    
    def progress(p):
        print(f"Progress: {p}%")
    
    try:
        run(
            params={'settings': test_settings, 'console': None},
            progress_callback=progress,
            cancel_event=cancel_event
        )
        print("\nDone!")
    except Exception as e:
        print(f"\nERROR: Failed: {e}")
