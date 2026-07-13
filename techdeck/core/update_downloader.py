"""
TechDeck Update Downloader
Downloads and installs updates from GitHub releases.
"""

import requests
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QObject, Signal


class UpdateDownloader(QObject):
    """Background worker for downloading installer using Python threading."""
    
    # Signals
    progress_updated = Signal(int, int)  # (bytes_downloaded, total_bytes)
    download_complete = Signal(str)      # installer_path
    download_failed = Signal(str)        # error_message
    
    def __init__(self, download_url: str, version: str):
        """
        Initialize downloader.
        
        Args:
            download_url: URL to installer .exe
            version: Version being downloaded (for filename)
        """
        super().__init__()
        self.download_url = download_url
        self.version = version
        self.cancelled = False
        self._thread = None
    
    def start(self):
        """Start download in background thread."""
        self._thread = threading.Thread(target=self._download, daemon=True)
        self._thread.start()
    
    def _download(self):
        """Download installer in background."""
        import sys
        print(f"[DOWNLOADER] Starting download from: {self.download_url}", flush=True)
        try:
            # Create temp directory for installer
            temp_dir = Path(tempfile.gettempdir()) / "TechDeck"
            temp_dir.mkdir(exist_ok=True)
            installer_path = temp_dir / f"TechDeck-Setup-{self.version}.exe"
            
            # Download with progress tracking
            print("[DOWNLOADER] Sending HTTP request...", flush=True)
            response = requests.get(
                self.download_url,
                stream=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                timeout=30
            )
            
            print(f"[DOWNLOADER] Response status: {response.status_code}", flush=True)
            if response.status_code != 200:
                print(f"[DOWNLOADER] Emitting download_failed signal", flush=True)
                self.download_failed.emit(f"Download failed: HTTP {response.status_code}")
                return
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.cancelled:
                        installer_path.unlink(missing_ok=True)
                        return
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress_updated.emit(downloaded, total_size)
            
            self.download_complete.emit(str(installer_path))
            
        except requests.RequestException as e:
            print(f"[DOWNLOADER] RequestException: {e}", flush=True)
            self.download_failed.emit(f"Network error: {str(e)}")
        except Exception as e:
            print(f"[DOWNLOADER] Exception: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.download_failed.emit(f"Download error: {str(e)}")
    
    def cancel(self):
        """Cancel download."""
        self.cancelled = True


def run_installer_and_exit(installer_path: str) -> None:
    """
    Launch installer, wait for completion, and restart TechDeck.
    
    Creates a temporary batch script that:
    1. Waits for installer to complete
    2. Restarts TechDeck
    3. Cleans up temp files
    
    Args:
        installer_path: Path to downloaded installer .exe
    """
    import sys
    import os
    print(f"[INSTALLER] Launching installer: {installer_path}", flush=True)
    
    # Get TechDeck executable path
    if getattr(sys, 'frozen', False):
        # Running as compiled .exe
        techdeck_exe = sys.executable
    else:
        # Running from Python - can't auto-restart
        print("[INSTALLER] Running from Python, cannot auto-restart", flush=True)
        subprocess.Popen([installer_path])
        sys.exit(0)
        return
    
    # Create restart helper script
    temp_dir = Path(tempfile.gettempdir()) / "TechDeck"
    restart_script = temp_dir / "restart_techdeck.bat"
    
    # NOTE: delays use `ping -n N` instead of `timeout` — timeout.exe refuses
    # to run without an interactive console stdin, and under the old
    # DETACHED_PROCESS launch each timeout call also got a brand-new VISIBLE
    # console allocated (the two cmd windows that flashed during restart).
    # ping waits N-1 seconds and works in any console context.
    batch_content = f'''@echo off
REM Wait for installer to finish
start /wait "" "{installer_path}" /SILENT /CLOSEAPPLICATIONS

REM Wait a moment for files to settle
ping 127.0.0.1 -n 3 >nul

REM Restart TechDeck
start "" "{techdeck_exe}"

REM Clean up
ping 127.0.0.1 -n 2 >nul
del "{installer_path}"
del "%~f0"
'''

    try:
        restart_script.write_text(batch_content, encoding='utf-8')
        print(f"[INSTALLER] Created restart script: {restart_script}", flush=True)

        # Launch the restart script in a HIDDEN console (CREATE_NO_WINDOW),
        # not DETACHED_PROCESS: a detached cmd has no console at all, so every
        # console child it spawns (timeout/ping/etc.) gets a fresh visible
        # console window — the split-second cmd flashes users saw during the
        # update restart. With CREATE_NO_WINDOW the children inherit the one
        # hidden console and nothing ever shows on screen.
        subprocess.Popen(
            ['cmd', '/c', str(restart_script)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        print("[INSTALLER] Restart script launched, exiting TechDeck...", flush=True)
        sys.exit(0)
        
    except Exception as e:
        print(f"[INSTALLER] Failed to create restart script: {e}", flush=True)
        # Fallback: just run installer without restart
        subprocess.Popen([installer_path])
        sys.exit(0)
