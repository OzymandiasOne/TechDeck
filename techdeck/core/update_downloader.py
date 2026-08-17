"""
TechDeck Update Downloader
Downloads and installs updates from GitHub releases.
"""

import hashlib
import logging
import requests
import subprocess
import tempfile
import threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


def sha256_file(path) -> str:
    """Return the lowercase hex SHA-256 of a file's bytes on disk. Reads in
    chunks so a large installer never has to fit in memory."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_matches(actual_hex: str, expected_hex: str) -> bool:
    """Constant-shape compare of two hex digests, normalized (stripped,
    lowercased). Empty/None expected -> False (an unpinned manifest must not
    count as 'verified')."""
    if not expected_hex or not actual_hex:
        return False
    return actual_hex.strip().lower() == expected_hex.strip().lower()


class UpdateDownloader(QObject):
    """Background worker for downloading installer using Python threading."""
    
    # Signals
    progress_updated = Signal(int, int)  # (bytes_downloaded, total_bytes)
    download_complete = Signal(str)      # installer_path
    download_failed = Signal(str)        # error_message
    
    def __init__(self, download_url: str, version: str, expected_sha256: str = ""):
        """
        Initialize downloader.

        Args:
            download_url: URL to installer .exe
            version: Version being downloaded (for filename)
            expected_sha256: Optional hex SHA-256 of the installer from the
                manifest. When set, the downloaded bytes are verified against it
                and a mismatch aborts (the file is deleted, never executed).
        """
        super().__init__()
        self.download_url = download_url
        self.version = version
        self.expected_sha256 = (expected_sha256 or "").strip().lower()
        self.cancelled = False
        self._thread = None
    
    def start(self):
        """Start download in background thread."""
        self._thread = threading.Thread(target=self._download, daemon=True)
        self._thread.start()
    
    def _download(self):
        """Download installer in background."""
        logger.info("Starting installer download from: %s", self.download_url)
        try:
            # Create temp directory for installer
            temp_dir = Path(tempfile.gettempdir()) / "TechDeck"
            temp_dir.mkdir(exist_ok=True)
            installer_path = temp_dir / f"TechDeck-Setup-{self.version}.exe"

            # Download with progress tracking
            response = requests.get(
                self.download_url,
                stream=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error("Installer download failed: HTTP %s", response.status_code)
                self.download_failed.emit(f"Download failed: HTTP {response.status_code}")
                return
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            hasher = hashlib.sha256()

            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.cancelled:
                        installer_path.unlink(missing_ok=True)
                        return

                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        self.progress_updated.emit(downloaded, total_size)

            # Integrity check: if the manifest pinned a SHA-256, the bytes we ran
            # to disk must match it before we hand the .exe to the installer.
            # This is the guard against a tampered manifest/download pointing at
            # an arbitrary executable.
            actual = hasher.hexdigest()
            if self.expected_sha256:
                if not sha256_matches(actual, self.expected_sha256):
                    logger.error("Installer SHA-256 mismatch: expected %s, got %s",
                                 self.expected_sha256, actual)
                    installer_path.unlink(missing_ok=True)
                    self.download_failed.emit(
                        "Update verification failed: the downloaded installer "
                        "does not match the expected checksum. The update was "
                        "not installed. Please try again later.")
                    return
                logger.info("Installer SHA-256 verified OK")
            else:
                logger.warning("No SHA-256 in manifest; download unverified "
                               "(sha256=%s)", actual)

            self.download_complete.emit(str(installer_path))
            
        except requests.RequestException as e:
            logger.error("Installer download network error: %s", e)
            self.download_failed.emit(f"Network error: {str(e)}")
        except Exception as e:
            logger.exception("Installer download error")
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
    logger.info("Launching installer: %s", installer_path)

    # This exit bypasses MainWindow.closeEvent (sys.exit from a timer slot),
    # so stamp the clean exit HERE - without it every successful auto-update
    # recorded clean_exit:false and looked like a crash in the next debug
    # report (and would trigger the crash-report offer on restart).
    from techdeck.core import hang_watchdog
    hang_watchdog.mark_clean_exit()

    # Get TechDeck executable path
    if getattr(sys, 'frozen', False):
        # Running as compiled .exe
        techdeck_exe = sys.executable
    else:
        # Running from Python - can't auto-restart
        logger.info("Running from Python, cannot auto-restart")
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
        logger.info("Created restart script: %s", restart_script)

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
        
        logger.info("Restart script launched, exiting TechDeck...")
        sys.exit(0)

    except Exception:
        logger.exception("Failed to create restart script; running installer "
                         "without auto-restart")
        # Fallback: just run installer without restart
        subprocess.Popen([installer_path])
        sys.exit(0)
