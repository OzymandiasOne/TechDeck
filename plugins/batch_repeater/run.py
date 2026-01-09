"""
Batch Repeater Plugin for TechDeck
Copies repeat orders from previous batches into new batch REPEAT BATCHES folder.

Workflow:
1. Read Excel spreadsheet to identify all PO columns
2. Find orders in new PO column
3. Locate each order in previous PO columns (most recent)
4. Copy order folders from old batches to new batch REPEAT BATCHES folder
"""

import os
import sys
import re
import shutil
from pathlib import Path
import pandas as pd


def print_output(msg: str, level: str = "INFO"):
    """
    Print formatted output to TechDeck console.
    
    Args:
        msg: Message to print
        level: Log level (INFO, WARNING, ERROR, SUCCESS)
    """
    prefix = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "✅"
    }.get(level, "•")
    
    print(f"{prefix} {msg}")
    sys.stdout.flush()


def find_batch_root(source_po: int, base_path: Path, completed_root: Path, search_recursive: bool) -> Path | None:
    """
    Locate the folder named 'Batch {source_po}' by checking:
      1) Active path root
      2) Direct child of completed folder
      3) Any nested child under completed folder (if recursive enabled)
    
    Args:
        source_po: Source PO/batch number
        base_path: Base directory path
        completed_root: Completed batches folder path
        search_recursive: Whether to search recursively
        
    Returns:
        Path to batch folder if found, else None
    """
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
    if search_recursive and completed_root.exists():
        target_lower = target.lower()
        for root, dirs, _ in os.walk(completed_root):
            for d in dirs:
                if d.lower() == target_lower:
                    return Path(root) / d
    
    return None


def run(settings: dict) -> dict:
    """
    Main plugin execution function called by TechDeck.
    
    Args:
        settings: Dictionary of plugin settings from TechDeck
        
    Returns:
        Dictionary with status and message
    """
    print_output("Starting Batch Repeater...", "INFO")
    
    # Get settings
    base_path_str = settings.get('base_path', '')
    spreadsheet_name = settings.get('spreadsheet_name', '922 MPL.xlsx')
    sheet_name = settings.get('sheet_name', 'PO 321+')
    new_po_str = settings.get('new_po_number', '')
    completed_folder = settings.get('completed_folder_name', '1 - Completed')
    search_recursive = settings.get('search_recursively', True)
    
    # Validate required settings
    if not base_path_str:
        return {
            "success": False,
            "message": "Base directory not configured. Please set it in plugin settings."
        }
    
    if not new_po_str:
        return {
            "success": False,
            "message": "New PO number not provided. Please enter it in plugin settings."
        }
    
    # Convert to types
    try:
        new_po_num = int(new_po_str)
    except ValueError:
        return {
            "success": False,
            "message": f"Invalid PO number: '{new_po_str}'. Must be digits only."
        }
    
    base_path = Path(base_path_str)
    completed_root = base_path / completed_folder
    spreadsheet_path = base_path / spreadsheet_name
    
    # Validate paths
    if not base_path.is_dir():
        return {
            "success": False,
            "message": f"Base directory not found: {base_path}"
        }
    
    if not spreadsheet_path.is_file():
        return {
            "success": False,
            "message": f"Spreadsheet not found: {spreadsheet_path}"
        }
    
    print_output(f"Base directory: {base_path}", "INFO")
    print_output(f"Spreadsheet: {spreadsheet_name}", "INFO")
    print_output(f"Sheet: {sheet_name}", "INFO")
    print_output(f"New PO: {new_po_num}", "INFO")
    print_output("", "INFO")
    
    # Read Excel file
    print_output("Reading Excel spreadsheet...", "INFO")
    try:
        df = pd.read_excel(spreadsheet_path, sheet_name=sheet_name, header=2)
    except Exception as e:
        return {
            "success": False,
            "message": f"Error reading spreadsheet: {e}"
        }
    
    # Identify PO columns
    print_output("Identifying PO columns...", "INFO")
    po_columns: dict[int, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.strip().lower().startswith("po"):
            m = re.search(r"(\d+)", col)
            if m:
                po_num = int(m.group(1))
                po_columns[po_num] = col
    
    if not po_columns:
        return {
            "success": False,
            "message": "No PO columns found in spreadsheet."
        }
    
    print_output(f"Found {len(po_columns)} PO columns", "SUCCESS")
    
    # Check if new PO exists in spreadsheet
    if new_po_num not in po_columns:
        available_pos = sorted(po_columns.keys())
        return {
            "success": False,
            "message": f"PO {new_po_num} not found in spreadsheet. Available POs: {available_pos}"
        }
    
    new_po_col = po_columns[new_po_num]
    print_output(f"Using column '{new_po_col}' for PO {new_po_num}", "INFO")
    
    # Setup destination folders
    new_po_folder = base_path / f"Batch {new_po_num}"
    new_po_folder.mkdir(exist_ok=True)
    print_output(f"Created batch folder: {new_po_folder.name}", "SUCCESS")
    
    repeat_batch_folder = new_po_folder / "REPEAT BATCHES"
    repeat_batch_folder.mkdir(exist_ok=True)
    print_output(f"Created repeat folder: {repeat_batch_folder.name}", "SUCCESS")
    print_output("", "INFO")
    
    # Get unique orders in new PO column
    print_output("Analyzing orders in new PO...", "INFO")
    new_po_orders = {
        str(order).strip()
        for order in df[new_po_col]
        if pd.notna(order) and str(order).strip()
    }
    print_output(f"Found {len(new_po_orders)} unique orders in PO {new_po_num}", "SUCCESS")
    
    # Find source PO for each order (most recent previous PO)
    print_output("Searching for repeat orders in previous batches...", "INFO")
    orders_to_copy: dict[str, int] = {}
    
    for order in new_po_orders:
        source_po_num = None
        for po_num, col in po_columns.items():
            # Only look at POs before the new one
            if po_num >= new_po_num:
                continue
            
            column_values = df[col].dropna().astype(str).str.strip()
            if order in column_values.values:
                # Keep the most recent (highest PO number)
                if source_po_num is None or po_num > source_po_num:
                    source_po_num = po_num
        
        if source_po_num is not None:
            orders_to_copy[order] = source_po_num
    
    print_output(f"Found {len(orders_to_copy)} repeat orders to copy", "SUCCESS")
    
    if not orders_to_copy:
        print_output("No repeat orders found. All orders are new!", "INFO")
        return {
            "success": True,
            "message": "No repeat orders found. All orders are new."
        }
    
    print_output("", "INFO")
    print_output("Copying order folders...", "INFO")
    
    # Copy folders
    copied_count = 0
    not_found_count = 0
    error_count = 0
    
    for order, source_po in orders_to_copy.items():
        # Find source batch root
        batch_root = find_batch_root(source_po, base_path, completed_root, search_recursive)
        
        if not batch_root:
            print_output(
                f"Source Batch {source_po} not found for order {order}",
                "WARNING"
            )
            not_found_count += 1
            continue
        
        # Locate specific order folder inside batch root
        found_folder = None
        try:
            for entry in os.listdir(batch_root):
                entry_path = batch_root / entry
                if entry_path.is_dir() and order.lower() in entry.lower():
                    found_folder = entry_path
                    break
        except FileNotFoundError:
            print_output(f"Batch {source_po} vanished while scanning", "ERROR")
            error_count += 1
            continue
        except PermissionError:
            print_output(f"Permission denied accessing Batch {source_po}", "ERROR")
            error_count += 1
            continue
        
        if not found_folder:
            print_output(
                f"Order folder '{order}' not found in Batch {source_po}",
                "WARNING"
            )
            not_found_count += 1
            continue
        
        # Copy to repeat batch folder
        destination_folder = repeat_batch_folder / found_folder.name
        try:
            shutil.copytree(found_folder, destination_folder, dirs_exist_ok=True)
            print_output(
                f"✓ Copied {order} from Batch {source_po}",
                "SUCCESS"
            )
            copied_count += 1
        except PermissionError as e:
            print_output(
                f"Permission denied copying {order}: {e}",
                "ERROR"
            )
            error_count += 1
        except Exception as e:
            print_output(
                f"Failed to copy {order} from Batch {source_po}: {e}",
                "ERROR"
            )
            error_count += 1
    
    # Summary
    print_output("", "INFO")
    print_output("=== Copy Complete ===", "INFO")
    print_output(f"Successfully copied: {copied_count}", "SUCCESS")
    
    if not_found_count > 0:
        print_output(f"Not found: {not_found_count}", "WARNING")
    
    if error_count > 0:
        print_output(f"Errors: {error_count}", "ERROR")
    
    return {
        "success": True,
        "message": f"Copied {copied_count} repeat order folders successfully"
    }


if __name__ == "__main__":
    # For standalone testing
    test_settings = {
        'base_path': str(Path.home() / "American Steel & Alum" / "Communication site - Electric Boat ASA Docs" / "Pilot Program" / "922 QTDR Production Packages"),
        'spreadsheet_name': '922 MPL.xlsx',
        'sheet_name': 'PO 321+',
        'new_po_number': input("Enter new PO number: ").strip(),
        'completed_folder_name': '1 - Completed',
        'search_recursively': True
    }
    
    result = run(test_settings)
    print(f"\nResult: {result}")
