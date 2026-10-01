"""
Debounced real-time filesystem monitor for pyEGClamUI.
Watches critical user directories and triggers background scans on file completion.
"""

import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from pyegclamui.core.config import Config
from pyegclamui.core.logger import get_logger, log_quarantine_action
from pyegclamui.core.scanner import ClamScanner

logger = get_logger("monitor")

# Temporary and in-flight download extensions to ignore until finalized
IGNORE_EXTENSIONS: Set[str] = {
    ".crdownload",  # Chromium / Chrome / Edge
    ".part",        # Firefox / Wget
    ".tmp",         # Generic temp files
    ".download",    # Safari
    ".partial",     # Download managers
    ".aria2",       # Aria2
    ".lock",        # Lock files
    ".swp",         # Vim swap files
    ".bak",         # Backup files
    ".temp",        # Generic temp files
    ".dmp",         # Crash dumps
}

# Filename prefixes to ignore (e.g. Office lock files, temporary hidden files)
IGNORE_PREFIXES = ("~$", ".~", ".__")


def is_file_ready_for_scan(file_path: Path) -> bool:
    """
    Validates that a file is complete, not an in-progress temp download,
    and accessible for read scanning without exclusive file locks.
    """
    try:
        if not file_path.exists() or not file_path.is_file():
            return False

        # Check for ignored temporary extensions
        if file_path.suffix.lower() in IGNORE_EXTENSIONS:
            return False

        # Check for ignored filename prefixes
        if any(file_path.name.startswith(p) for p in IGNORE_PREFIXES):
            return False

        # Verify file can be opened for reading (ensures file write lock released)
        with open(file_path, "rb") as f:
            f.read(1)
        return True
    except (OSError, PermissionError):
        return False


class DebouncedScanHandler(FileSystemEventHandler):
    """Batches and debounces filesystem events to scan only fully-written files."""

    def __init__(self, on_file_ready: Callable[[str], None], debounce_seconds: float = 1.5):
        super().__init__()
        self.on_file_ready = on_file_ready
        self.debounce_seconds = debounce_seconds
        self.pending_files: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._timer_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._timer_thread.start()

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        # File renamed (e.g. download finished from .crdownload to real filename)
        if not event.is_directory and hasattr(event, "dest_path"):
            self._enqueue(event.dest_path)

    def _enqueue(self, file_path: str):
        path_obj = Path(file_path)
        # Skip immediately if it has an in-progress extension
        if path_obj.suffix.lower() in IGNORE_EXTENSIONS:
            return
        if any(path_obj.name.startswith(p) for p in IGNORE_PREFIXES):
            return

        with self._lock:
            self.pending_files[file_path] = time.time()

    def _process_queue(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=0.3)
            if self._stop_event.is_set():
                break

            now = time.time()
            ready_files: List[str] = []

            with self._lock:
                for path_str, last_mod in list(self.pending_files.items()):
                    if now - last_mod >= self.debounce_seconds:
                        ready_files.append(path_str)
                        del self.pending_files[path_str]

            for path_str in ready_files:
                path_obj = Path(path_str)
                if is_file_ready_for_scan(path_obj):
                    try:
                        self.on_file_ready(path_str)
                    except Exception as e:
                        logger.error(f"Error dispatching {path_str}: {e}")

    def stop(self):
        """Signals worker thread to terminate and clears pending queue."""
        self._stop_event.set()
        with self._lock:
            self.pending_files.clear()


class RealTimeGuard:
    """Manages watchdog observer threads for real-time background protection."""

    def __init__(
        self,
        watch_dirs: Optional[List[Path]] = None,
        on_threat_detected: Optional[Callable[[dict], None]] = None,
        on_scan_completed: Optional[Callable[[str], None]] = None,
    ):
        self.config = Config.get_instance()
        self.scanner = ClamScanner()
        self.custom_watch_dirs = watch_dirs
        self.on_threat_detected = on_threat_detected
        self.on_scan_completed = on_scan_completed
        self.observer: Optional[Observer] = None
        self.handler: Optional[DebouncedScanHandler] = None
        self.is_active = False

        # Live statistics
        self._stats_lock = threading.Lock()
        self.scanned_count = 0
        self.threats_count = 0
        self.last_scanned_file: Optional[str] = None

    def get_watch_directories(self) -> List[Path]:
        """
        Resolves target directories to monitor for newly created files.
        Strictly capped at a maximum of 2 directories for optimal system performance.
        Slot 1: Default Desktop (or user custom override).
        Slot 2: Default Downloads (or user custom override).
        """
        if self.custom_watch_dirs:
            return [d for d in self.custom_watch_dirs if d.exists() and d.is_dir()][:2]

        configured = self.config.get("scan_settings", "monitor_dirs", default=[])
        if configured and isinstance(configured, list):
            paths = [Path(p) for p in configured if p and Path(p).exists() and Path(p).is_dir()]
            if paths:
                return paths[:2]

        home = Path.home()
        defaults = [home / "Desktop", home / "Downloads"]
        return [d for d in defaults if d.exists() and d.is_dir()][:2]

    def update_watch_directories(self, slot1: Optional[str] = None, slot2: Optional[str] = None) -> bool:
        """Updates the 2 monitored directories in config and restarts observer if active."""
        new_dirs = []
        if slot1 and Path(slot1).is_dir():
            new_dirs.append(str(Path(slot1).resolve()))
        if slot2 and Path(slot2).is_dir():
            new_dirs.append(str(Path(slot2).resolve()))
        self.config.set("scan_settings", "monitor_dirs", new_dirs[:2])
        if self.is_active:
            self.stop()
            return self.start()
        return True

    def start(self) -> bool:
        """Starts monitoring user risk directories."""
        if self.is_active:
            return True

        watch_dirs = self.get_watch_directories()
        if not watch_dirs:
            logger.warning("No valid watch directories found to monitor.")
            return False

        self.handler = DebouncedScanHandler(on_file_ready=self._scan_single_file)
        self.observer = Observer()

        watched_any = False
        for d in watch_dirs:
            try:
                self.observer.schedule(self.handler, str(d), recursive=False)
                watched_any = True
                logger.info(f"Real-Time Guard watching: {d}")
            except Exception as e:
                logger.warning(f"Failed to schedule watch on {d}: {e}")

        if not watched_any:
            self.handler.stop()
            self.handler = None
            self.observer = None
            return False

        try:
            self.observer.start()
            self.is_active = True
            logger.info("Real-Time Guard started successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to start observer: {e}")
            if self.handler:
                self.handler.stop()
            self.handler = None
            self.observer = None
            self.is_active = False
            return False

    def stop(self):
        """Stops the real-time background observer."""
        if self.handler:
            self.handler.stop()
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=1.0)
            except Exception:
                pass
        self.is_active = False
        self.observer = None
        self.handler = None

    def get_stats(self) -> dict:
        """Returns snapshot of protection metrics."""
        with self._stats_lock:
            return {
                "active": self.is_active,
                "scanned_count": self.scanned_count,
                "threats_count": self.threats_count,
                "last_scanned_file": self.last_scanned_file,
            }

    def _scan_single_file(self, file_path: str):
        """Worker function executing scan on a debounced, completed file."""
        with self._stats_lock:
            self.scanned_count += 1
            self.last_scanned_file = file_path

        def threat_callback(threat_info: dict):
            with self._stats_lock:
                self.threats_count += 1
            log_quarantine_action(
                threat_info.get("action", "Quarantined"),
                threat_info.get("path", file_path),
                threat_info.get("threat", "Threat"),
            )
            if self.on_threat_detected:
                self.on_threat_detected(threat_info)

        try:
            self.scanner.scan(
                scan_type="Real-Time Guard",
                targets=[file_path],
                on_threat=threat_callback,
                prefer_daemon=True,
            )
            if self.on_scan_completed:
                self.on_scan_completed(file_path)
        except Exception as e:
            logger.error(f"Scan error for {file_path}: {e}")
