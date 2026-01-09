"""
LST Organizer Plugin for TechDeck
Wrapper for the full LST Organizer v14 script.

This plugin provides TechDeck integration while preserving the full
700-line functionality of the original LST Organizer script.
"""

import os
import sys
import subprocess
from pathlib import Path


def print_output(msg: str, level: str = "INFO"):
    """Print formatted output to TechDeck console."""
    prefix = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "✅"
    }.get(level, "•")
    print(f"{prefix} {msg}")
    sys.stdout.flush()


def run(settings: dict) -> dict:
    """
    Main plugin execution function called by TechDeck.
    
    Args:
        settings: Dictionary of plugin settings from TechDeck
        
    Returns:
        Dictionary with status and message
    """
    print_output("Starting LST Organizer...", "INFO")
    
    # Get settings
    base_path = settings.get('base_path', '')
    batch_no = settings.get('batch_number', '')
    master_po = settings.get('master_po_path', '')
    dry_run = settings.get('dry_run', False)
    
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
    
    base_path_obj = Path(base_path)
    if not base_path_obj.is_dir():
        return {
            "success": False,
            "message": f"Base directory not found: {base_path}"
        }
    
    print_output(f"Base directory: {base_path}", "INFO")
    print_output(f"Batch number: {batch_no}", "INFO")
    
    # Locate the full LST Organizer script
    # It should be placed alongside this run.py file
    plugin_dir = Path(__file__).parent
    full_script = plugin_dir / "LSTOrganizer_full.py"
    
    if not full_script.exists():
        return {
            "success": False,
            "message": f"Full LST Organizer script not found at: {full_script}\n\n" +
                      "Please place 'LSTOrganizer_full.py' in the plugin directory:\n" +
                      f"{plugin_dir}"
        }
    
    print_output("Found full LST Organizer script", "SUCCESS")
    print_output("", "INFO")
    
    # Build command
    cmd = [
        sys.executable,  # Python interpreter
        str(full_script),
        "--batch", batch_no
    ]
    
    if master_po:
        cmd.extend(["--po", master_po])
        print_output(f"Using Master PO: {master_po}", "INFO")
    
    if dry_run:
        cmd.append("--kill")
        print_output("DRY RUN MODE - No files will be copied", "WARNING")
    
    print_output("Executing LST Organizer...", "INFO")
    print_output("=" * 60, "INFO")
    
    # Execute the full script and capture output
    try:
        # Set environment to use the base path
        env = os.environ.copy()
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        
        # Stream output to console
        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                # Parse line and add appropriate emoji
                if "ERROR" in line.upper():
                    print_output(line, "ERROR")
                elif "WARNING" in line.upper() or "⚠" in line:
                    print_output(line, "WARNING")
                elif "✓" in line or "Complete" in line:
                    print_output(line, "SUCCESS")
                else:
                    print(line)  # Direct output without emoji prefix
            sys.stdout.flush()
        
        process.wait()
        
        print_output("=" * 60, "INFO")
        
        if process.returncode == 0:
            print_output("LST Organizer completed successfully!", "SUCCESS")
            return {
                "success": True,
                "message": "LST files organized successfully"
            }
        else:
            print_output(f"LST Organizer exited with code {process.returncode}", "ERROR")
            return {
                "success": False,
                "message": f"Process exited with error code {process.returncode}"
            }
    
    except FileNotFoundError:
        return {
            "success": False,
            "message": f"Python interpreter not found: {sys.executable}"
        }
    except Exception as e:
        print_output(f"Execution error: {e}", "ERROR")
        return {
            "success": False,
            "message": f"Error executing LST Organizer: {e}"
        }


if __name__ == "__main__":
    # For standalone testing
    test_settings = {
        'base_path': input("Enter base path: ").strip() or str(Path.home() / "American Steel & Alum" / "Communication site - Electric Boat ASA Docs" / "Pilot Program" / "922 QTDR Production Packages"),
        'batch_number': input("Enter batch number: ").strip(),
        'master_po_path': '',
        'dry_run': False
    }
    
    result = run(test_settings)
    print(f"\nResult: {result}")
