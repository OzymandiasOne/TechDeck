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


def find_batch_root(source_po: int, base_path: Path, completed_root: Path) -> Optional[Path]:
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
    
    # 3) Nested child (recursive search)
    if completed_root.exists():
        target_lower = target.lower()
        for root, dirs, _ in os.walk(completed_root):
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
    
    log("🚀 Starting 922 Batch Repeater v2.0.0...")
    progress_callback(0)
    
    # FIXED: Get settings with correct keys matching plugin.json
    base_directory = settings.get('base_directory', '')
    spreadsheet_filename = settings.get('spreadsheet_filename', '')
    
    # Validate settings
    if not base_directory:
        log("❌ Base directory not configured!")
        log("Go to: Settings > Plugin Settings > Batch Repeater")
        raise ValueError("Base directory not configured")
    
    if not spreadsheet_filename:
        log("❌ Spreadsheet filename not configured!")
        log("Go to: Settings > Plugin Settings > Batch Repeater")
        raise ValueError("Spreadsheet filename not configured")
    
    # Construct full path
    base_path = Path(base_directory)
    if not base_path.exists():
        log(f"❌ Base directory not found: {base_path}")
        raise ValueError(f"Base directory not found: {base_path}")
    
    spreadsheet_path = base_path / spreadsheet_filename
    if not spreadsheet_path.exists():
        log(f"❌ Spreadsheet not found: {spreadsheet_path}")
        raise ValueError(f"Spreadsheet not found: {spreadsheet_path}")
    
    completed_root = base_path / COMPLETED_FOLDER_NAME
    
    log("")
    log(f"📁 Base directory: {base_path}")
    log(f"📊 Spreadsheet: {spreadsheet_path.name}")
    log(f"📄 Sheet: {SHEET_NAME}")
    log("")
    
    progress_callback(5)
    
    # === ASK FOR BATCH FOLDER NAME ===
    log("📝 Input required from user...")
    batch_name_input = get_console_input(
        params,
        "Enter batch number or full folder name (e.g., '429' or 'Batch 429')"
    )

    actual_batch_name = batch_name_input.strip()
    if not actual_batch_name:
        log("❌ Batch name cannot be empty!")
        raise ValueError("Batch name cannot be empty")
    
    # Accept bare number input (e.g. "429" → "Batch 429")
    if actual_batch_name.isdigit():
        actual_batch_name = f"Batch {actual_batch_name}"

    log(f"✅ Using batch name: {actual_batch_name}")
    
    # === EXTRACT PO NUMBER FROM BATCH NAME ===
    # Look for numbers in the batch name
    po_match = re.search(r'\d+', actual_batch_name)
    if not po_match:
        log("❌ Could not find PO number in batch name!")
        log("   Batch name must contain a number (e.g., 'Batch 429')")
        raise ValueError("Could not extract PO number from batch name")
    
    new_po_num = int(po_match.group())
    log(f"✅ Extracted PO: {new_po_num}")
    
    log("")
    log(f"🔢 PO Number: {new_po_num}")
    log(f"📂 Batch folder: {actual_batch_name}")
    log("")
    
    progress_callback(10)
    
    # Check for cancellation
    if cancel_event.is_set():
        log("Operation cancelled")
        return
    
    # Read Excel file
    log("📖 Reading Excel spreadsheet...")
    try:
        df = pd.read_excel(spreadsheet_path, sheet_name=SHEET_NAME, header=2)
    except Exception as e:
        log(f"❌ Error reading spreadsheet: {e}")
        raise RuntimeError(f"Error reading spreadsheet: {e}")
    
    progress_callback(15)
    
    # Identify PO columns
    log("🔍 Identifying PO columns...")
    po_columns: Dict[int, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.strip().lower().startswith("po"):
            m = re.search(r"(\d+)", col)
            if m:
                po_num = int(m.group(1))
                po_columns[po_num] = col
    
    if not po_columns:
        log("❌ No PO columns found in spreadsheet.")
        raise ValueError("No PO columns found in spreadsheet.")
    
    log(f"✅ Found {len(po_columns)} PO columns")
    progress_callback(20)
    
    # Check if new PO exists
    if new_po_num not in po_columns:
        available_pos = sorted(po_columns.keys())
        log(f"❌ PO {new_po_num} not found. Available: {available_pos}")
        raise ValueError(f"PO {new_po_num} not found. Available: {available_pos}")
    
    new_po_col = po_columns[new_po_num]
    log(f"Using column '{new_po_col}'")
    
    # Setup destination folders
    new_po_folder = base_path / actual_batch_name
    new_po_folder.mkdir(exist_ok=True)
    log(f"📂 Created: {new_po_folder.name}")
    
    repeat_batch_folder = new_po_folder / "REPEAT BATCHES"
    repeat_batch_folder.mkdir(exist_ok=True)
    log(f"📂 Created: REPEAT BATCHES")
    log("")
    
    progress_callback(25)
    
    # Get unique orders
    log("🔎 Analyzing orders...")
    new_po_orders = {
        str(order).strip()
        for order in df[new_po_col]
        if pd.notna(order) and str(order).strip()
    }
    log(f"✅ Found {len(new_po_orders)} unique orders")
    
    progress_callback(30)
    
    # Find source PO for each order
    log("🔍 Searching for repeat orders...")
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
    
    log(f"✅ Found {len(orders_to_copy)} repeat orders")
    progress_callback(35)
    
    if not orders_to_copy:
        log("🎉 No repeat orders! All new!")
        progress_callback(100)
        return
    
    log("")
    log("📦 Copying order folders...")
    
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
            log("⚠️ Cancelled by user")
            log(f"Copied {copied_count} of {total_orders}")
            return
        
        progress = base_progress + int((idx / total_orders) * progress_range)
        progress_callback(progress)
        
        batch_root = find_batch_root(source_po, base_path, completed_root)
        
        if not batch_root:
            log(f"⚠️ Batch {source_po} not found for {order}")
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
            log(f"❌ Error accessing Batch {source_po}: {e}")
            error_count += 1
            continue
        
        if not found_folder:
            log(f"⚠️ '{order}' not found in Batch {source_po}")
            not_found_count += 1
            continue
        
        destination_folder = repeat_batch_folder / found_folder.name
        try:
            shutil.copytree(found_folder, destination_folder, dirs_exist_ok=True)
            log(f"✔ Copied {order} from Batch {source_po}")
            copied_count += 1
        except Exception as e:
            log(f"❌ Failed to copy {order}: {e}")
            error_count += 1
    
    progress_callback(95)
    
    # Summary
    log("")
    log("=" * 50)
    log("📊 COPY SUMMARY")
    log("=" * 50)
    log(f"✅ Successfully copied: {copied_count}")
    
    if not_found_count > 0:
        log(f"⚠️ Not found: {not_found_count}")
    
    if error_count > 0:
        log(f"❌ Errors: {error_count}")
    
    log("=" * 50)
    
    progress_callback(100)
    
    if error_count > 0 or not_found_count > 0:
        log("⚠️ Completed with warnings")
    else:
        log("🎉 All done successfully!")


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
        print("\n✅ Done!")
    except Exception as e:
        print(f"\n❌ Failed: {e}")
