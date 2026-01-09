"""
Pallet Stamper Plugin for TechDeck
Stamps work-packet PDFs with PO batch number and pallet assignments.

Integrates with TechDeck's console output and settings system.
"""

import os
import sys
from pathlib import Path
import pandas as pd
import fitz  # PyMuPDF
import warnings

# Suppress openpyxl warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


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


def anchor_xy(page):
    """
    Calculate anchor coordinates for stamp based on page rotation.
    
    Args:
        page: PyMuPDF page object
        
    Returns:
        Tuple of (x, y) coordinates
    """
    # Get settings from environment (set by TechDeck)
    h_offset_in = float(os.environ.get('PLUGIN_H_OFFSET_INCHES', '4.0'))
    v_offset_in = float(os.environ.get('PLUGIN_V_OFFSET_INCHES', '7.0'))
    ppi = 72.0  # points per inch
    
    off_x = h_offset_in * ppi
    off_y = v_offset_in * ppi
    w, h = page.rect.width, page.rect.height
    rot = page.rotation % 360

    if rot == 0:       # upright
        x, y = w - off_x, h - off_y
    elif rot == 90:    # rotated CW
        x, y = off_y, h - off_x
    elif rot == 180:   # upside-down
        x, y = off_x, off_y
    elif rot == 270:   # rotated CCW
        x, y = w - off_y, off_x
    else:              # fallback
        x, y = w - off_x, h - off_y
    
    return x, y


def stamp_single(pdf_path: str, batch_no: str, pallet_no: str, font_size: int) -> bool:
    """
    Stamp first page of PDF with batch and pallet info.
    
    Args:
        pdf_path: Path to PDF file
        batch_no: Batch number
        pallet_no: Pallet number
        font_size: Font size in points
        
    Returns:
        True if successful, False otherwise
    """
    try:
        tmp = pdf_path + ".tmp"
        
        with fitz.open(pdf_path) as doc:
            page = doc[0]
            x, y = anchor_xy(page)
            text_rotate = (-page.rotation) % 180

            page.insert_text(
                fitz.Point(x, y),
                f"PO {batch_no}\nPALLET {pallet_no}",
                fontsize=font_size,
                fontname="helv",  # Helvetica-Bold
                fill=(1, 0, 0),   # bright red
                rotate=text_rotate
            )

            doc.save(tmp)
        
        os.replace(tmp, pdf_path)
        return True
        
    except Exception as e:
        print_output(f"PDF error for {pdf_path}: {e}", "ERROR")
        return False


def run(settings: dict) -> dict:
    """
    Main plugin execution function called by TechDeck.
    
    Args:
        settings: Dictionary of plugin settings from TechDeck
        
    Returns:
        Dictionary with status and message
    """
    print_output("Starting Pallet Stamper...", "INFO")
    
    # Get settings
    base_path = settings.get('base_path', '')
    batch_no = settings.get('batch_number', '')
    font_size = settings.get('font_size', 18)
    h_offset = settings.get('h_offset_inches', 4.0)
    v_offset = settings.get('v_offset_inches', 7.0)
    
    # Validate settings
    if not base_path:
        return {
            "success": False,
            "message": "Base directory not configured. Please set it in plugin settings."
        }
    
    if not batch_no:
        return {
            "success": False,
            "message": "Batch number not provided. Please enter it in plugin settings."
        }
    
    # Set environment variables for anchor_xy function
    os.environ['PLUGIN_H_OFFSET_INCHES'] = str(h_offset)
    os.environ['PLUGIN_V_OFFSET_INCHES'] = str(v_offset)
    
    # Construct paths
    batch_path = Path(base_path) / f"Batch {batch_no}"
    doc_folder = batch_path / f"Batch {batch_no} - Documentation"
    xl_path = doc_folder / f"PO H{batch_no} Pallet & Rod Organizer.xlsx"
    
    # Validate paths exist
    if not batch_path.is_dir():
        return {
            "success": False,
            "message": f"Batch folder not found: {batch_path}"
        }
    
    if not xl_path.is_file():
        return {
            "success": False,
            "message": f"Organizer Excel file not found: {xl_path}"
        }
    
    print_output(f"Processing Batch {batch_no}...", "INFO")
    print_output(f"Reading pallet assignments from Excel...", "INFO")
    
    # Read Excel pallet organizer
    try:
        df = pd.read_excel(
            xl_path,
            sheet_name="Pallet Organizer",
            usecols="B,E,H",
            header=3,
            nrows=19
        )
    except Exception as e:
        return {
            "success": False,
            "message": f"Excel read error: {e}"
        }
    
    # Build order-to-pallet mapping
    order_to_pallet = {}
    for col_idx, col in enumerate(df.columns):
        pallet = str(col_idx + 1)
        for order in df[col].dropna():
            order_to_pallet[str(order).strip().upper()] = pallet
    
    print_output(f"Found {len(order_to_pallet)} order-to-pallet mappings", "INFO")
    
    # Process each order folder
    stamped_count = 0
    skipped_count = 0
    error_count = 0
    
    for sub in batch_path.iterdir():
        if not sub.is_dir():
            continue
        
        # Skip documentation folder
        if sub.name.endswith("- Documentation"):
            continue
        
        # Extract order number (everything before first hyphen)
        parts = sub.name.split('-', 1)
        if len(parts) < 1:
            continue
        
        order_no = parts[0].strip().upper()
        pallet_no = order_to_pallet.get(order_no)
        
        if pallet_no is None:
            print_output(f"No pallet assignment for order {order_no}", "WARNING")
            skipped_count += 1
            continue
        
        # Find first PDF in order folder
        pdfs = [f for f in sub.iterdir() if f.suffix.lower() == '.pdf']
        
        if not pdfs:
            print_output(f"No PDF found in {sub.name}", "WARNING")
            skipped_count += 1
            continue
        
        # Stamp the first PDF
        pdf_path = str(pdfs[0])
        if stamp_single(pdf_path, batch_no, pallet_no, font_size):
            print_output(f"✓ Stamped {order_no} → Pallet {pallet_no}", "SUCCESS")
            stamped_count += 1
        else:
            error_count += 1
    
    # Summary
    print_output("", "INFO")
    print_output("=== Stamping Complete ===", "INFO")
    print_output(f"Successfully stamped: {stamped_count}", "SUCCESS")
    
    if skipped_count > 0:
        print_output(f"Skipped: {skipped_count}", "WARNING")
    
    if error_count > 0:
        print_output(f"Errors: {error_count}", "ERROR")
    
    return {
        "success": True,
        "message": f"Stamped {stamped_count} PDFs successfully"
    }


if __name__ == "__main__":
    # For standalone testing
    test_settings = {
        'base_path': os.path.join(
            os.path.expanduser("~"),
            "American Steel & Alum",
            "Communication site - Electric Boat ASA Docs",
            "Pilot Program",
            "922 QTDR Production Packages"
        ),
        'batch_number': input("Enter batch number: ").strip(),
        'font_size': 18,
        'h_offset_inches': 4.0,
        'v_offset_inches': 7.0
    }
    
    result = run(test_settings)
    print(f"\nResult: {result}")
