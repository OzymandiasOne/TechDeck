"""
Part Sketch Extractor Plugin for TechDeck
Extracts PART SKETCH data from PDF packets into Excel.

Based on part_sketch_extractor.py v1.4.1
Integrates with TechDeck's console output and settings system.
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
    print_output("Starting Part Sketch Extractor...", "INFO")
    
    # Get settings
    pdf_folder = settings.get('pdf_folder', '')
    output_file = settings.get('output_file', '')
    extract_drawings = settings.get('extract_drawings', False)
    resume_mode = settings.get('resume_mode', False)
    verbose_mode = settings.get('verbose_mode', False)
    
    # Validate settings
    if not pdf_folder:
        return {
            "success": False,
            "message": "PDF folder not configured. Please set it in plugin settings."
        }
    
    pdf_folder_path = Path(pdf_folder)
    if not pdf_folder_path.is_dir():
        return {
            "success": False,
            "message": f"PDF folder not found: {pdf_folder}"
        }
    
    # Count PDFs
    pdf_files = list(pdf_folder_path.glob("*.pdf"))
    if not pdf_files:
        return {
            "success": False,
            "message": f"No PDF files found in: {pdf_folder}"
        }
    
    print_output(f"PDF Folder: {pdf_folder}", "INFO")
    print_output(f"Found {len(pdf_files)} PDF files to process", "SUCCESS")
    
    # Determine output file
    if output_file:
        output_path = Path(output_file)
        print_output(f"Output: {output_file}", "INFO")
    else:
        output_path = pdf_folder_path / "part_sketches.xlsx"
        print_output(f"Output: {output_path} (auto-generated)", "INFO")
    
    # Locate the full Part Sketch Extractor script
    plugin_dir = Path(__file__).parent
    full_script = plugin_dir / "part_sketch_extractor_full.py"
    
    if not full_script.exists():
        return {
            "success": False,
            "message": f"Full Part Sketch Extractor script not found at: {full_script}\n\n" +
                      "Please place 'part_sketch_extractor_full.py' in the plugin directory:\n" +
                      f"{plugin_dir}"
        }
    
    print_output("Found full Part Sketch Extractor script", "SUCCESS")
    print_output("", "INFO")
    
    # Build command
    cmd = [
        sys.executable,  # Python interpreter
        str(full_script),
        str(pdf_folder)
    ]
    
    if output_file:
        cmd.extend(["--output", str(output_path)])
    
    if extract_drawings:
        cmd.append("--extract-drawings")
        print_output("Drawing extraction enabled - will create extracted_drawings.pdf", "INFO")
    
    if resume_mode:
        cmd.append("--resume")
        print_output("Resume mode enabled - using checkpointing", "INFO")
    
    if verbose_mode:
        cmd.append("--explain")
        print_output("Verbose mode enabled - detailed extraction trace", "INFO")
    
    print_output("", "INFO")
    print_output("Extracting PART SKETCH data from PDFs...", "INFO")
    print_output("=" * 60, "INFO")
    
    # Execute the full script and capture output
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Stream output to console
        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                
                # Parse line and add appropriate emoji
                if "[error]" in line.lower():
                    print_output(line, "ERROR")
                elif "[warn]" in line.lower():
                    print_output(line, "WARNING")
                elif "done" in line.lower() or "rows added" in line.lower():
                    print_output(line, "SUCCESS")
                elif "[why]" in line.lower():
                    print(f"  {line}")  # Indent debug traces
                else:
                    print(line)  # Direct output
            sys.stdout.flush()
        
        process.wait()
        
        print_output("=" * 60, "INFO")
        
        if process.returncode == 0:
            print_output("Part Sketch Extractor completed successfully!", "SUCCESS")
            print_output(f"Excel file: {output_path}", "SUCCESS")
            
            if extract_drawings:
                drawings_path = pdf_folder_path / "extracted_drawings.pdf"
                if drawings_path.exists():
                    print_output(f"Extracted drawings: {drawings_path}", "SUCCESS")
            
            # Try to get row count from output
            row_count = 0
            for line in output_lines:
                if "rows added" in line.lower():
                    import re
                    match = re.search(r'(\d+)', line)
                    if match:
                        row_count = int(match.group(1))
            
            if row_count > 0:
                print_output(f"Total rows added: {row_count}", "INFO")
            
            return {
                "success": True,
                "message": f"Extracted PART SKETCH data from {len(pdf_files)} PDFs successfully"
            }
        else:
            print_output(f"Part Sketch Extractor exited with code {process.returncode}", "ERROR")
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
            "message": f"Error executing Part Sketch Extractor: {e}"
        }


if __name__ == "__main__":
    # For standalone testing
    test_settings = {
        'pdf_folder': input("Enter PDF folder path: ").strip(),
        'output_file': '',
        'extract_drawings': input("Extract drawings? (y/n): ").strip().lower() == 'y',
        'resume_mode': False,
        'verbose_mode': input("Verbose mode? (y/n): ").strip().lower() == 'y'
    }
    
    result = run(test_settings)
    print(f"\nResult: {result}")
