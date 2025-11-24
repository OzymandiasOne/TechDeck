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
                headers={'User-Agent': f'TechDeck/{self.version}'},
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
    Launch installer and exit TechDeck.
    
    The installer will run silently and update TechDeck files.
    TechDeck must be closed for the installer to replace files.
    
    Args:
        installer_path: Path to downloaded installer .exe
    """
    print(f"[INSTALLER] Would launch: {installer_path}", flush=True)
    print("[INSTALLER] sys.exit() is DISABLED for testing", flush=True)
    # TEMPORARILY DISABLED FOR TESTING
    # try:
    #     # Launch installer
    #     subprocess.Popen(
    #         [installer_path, '/SILENT', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS'],
    #         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    #     )
    #     import sys
    #     sys.exit(0)
    # except Exception as e:
    #     print(f"Failed to launch installer: {e}")
    #     subprocess.Popen([installer_path])
    #     import sys
    #     sys.exit(0)
