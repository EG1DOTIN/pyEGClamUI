"""
Engine detector for pyEGClamUI.
Discovers clamscan, clamd, and freshclam executables and verifies socket connectivity.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.daemon import ClamDaemonClient
from pyegclamui.core.process import run_hidden_process


class ClamEngineDetector:
    """Discovers and inspects installed ClamAV binaries and running daemons."""

    STANDARD_UNIX_SOCKETS = ClamDaemonClient.STANDARD_UNIX_SOCKETS

    def __init__(self):
        self.config = Config.get_instance()
        self._cached_version: Optional[Tuple[float, Dict[str, Any]]] = None
        self._cached_inspect: Optional[Tuple[float, Dict[str, Any]]] = None
        self._cache_ttl: float = 6.0

    def invalidate_cache(self) -> None:
        """Clears cached inspect and engine version data."""
        self._cached_version = None
        self._cached_inspect = None

    @classmethod
    def get_standard_windows_paths(cls) -> List[Path]:
        """Returns standard Windows search directories, safely filtering out empty env vars."""
        paths = [
            Path("C:/Program Files/ClamAV"),
            Path("C:/Program Files (x86)/ClamAV"),
            Path("C:/ClamAV"),
        ]
        for env_var in ["LOCALAPPDATA", "APPDATA", "ProgramFiles", "ProgramFiles(x86)"]:
            val = os.getenv(env_var)
            if val and val.strip():
                paths.append(Path(val) / "ClamAV")
        return paths

    @classmethod
    def get_standard_unix_paths(cls) -> List[Path]:
        """Returns standard Linux, BSD, and macOS search directories for ClamAV binaries."""
        return [
            # Standard Linux / Unix
            Path("/usr/bin"),
            Path("/usr/sbin"),
            Path("/usr/local/bin"),
            Path("/usr/local/sbin"),
            # macOS Homebrew (Apple Silicon)
            Path("/opt/homebrew/bin"),
            Path("/opt/homebrew/sbin"),
            # macOS MacPorts
            Path("/opt/local/bin"),
            Path("/opt/local/sbin"),
        ]

    def find_executable(self, binary_name: str, custom_key: Optional[str] = None) -> Optional[str]:
        """Locates an executable in custom config, system PATH, or standard OS directories."""
        # 1. Check custom path in config
        if custom_key:
            custom_path = self.config.get("scan_settings", custom_key)
            if custom_path and Path(custom_path).is_file() and os.access(custom_path, os.X_OK):
                return str(Path(custom_path).resolve())

        # 2. Check system PATH
        ext = ".exe" if sys.platform == "win32" else ""
        bin_with_ext = binary_name + ext
        found = shutil.which(bin_with_ext) or shutil.which(binary_name)
        if found:
            return str(Path(found).resolve())

        # 3. Check standard Windows directories
        if sys.platform == "win32":
            for base in self.get_standard_windows_paths():
                candidate = base / bin_with_ext
                if candidate.is_file():
                    return str(candidate.resolve())

        # 4. Check common Unix and macOS directories
        for base in self.get_standard_unix_paths():
            candidate = base / binary_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())

        return None

    def get_clamscan_path(self) -> Optional[str]:
        return self.find_executable("clamscan", "custom_clamscan_path")

    def get_clamdscan_path(self) -> Optional[str]:
        return self.find_executable("clamdscan", "custom_clamdscan_path")

    def get_clamd_path(self) -> Optional[str]:
        return self.find_executable("clamd", "custom_clamd_path")

    def get_freshclam_path(self) -> Optional[str]:
        return self.find_executable("freshclam", "custom_freshclam_path")

    def check_daemon_socket(self) -> Tuple[bool, str]:
        """
        Tests if clamd daemon is responding via TCP or Unix domain socket.
        Returns: (is_online, connection_type)
        """
        client = ClamDaemonClient()
        return client.check_connection()

    def get_engine_version(self, force: bool = False) -> Dict[str, Any]:
        """
        Queries clamscan/clamd for version and signature database date.
        Returns cached dictionary if queried within cache_ttl unless force=True.
        """
        now = time.time()
        if not force and self._cached_version:
            ts, cached_data = self._cached_version
            if now - ts < self._cache_ttl:
                return cached_data

        clamscan = self.get_clamscan_path()
        if not clamscan:
            res = {
                "installed": False,
                "clamav_version": "Not Found",
                "db_version": "Unknown",
                "db_date": "Unknown",
                "raw": "clamscan executable not found in PATH"
            }
            self._cached_version = (now, res)
            return res

        try:
            db_dir = AppPaths.get_database_dir()
            cmd = [clamscan, "--version"]
            if db_dir.is_dir() and any(db_dir.glob("*.c*d")):
                cmd.extend(["--database", str(db_dir.resolve())])

            result = run_hidden_process(
                cmd,
                capture_output=True,
                timeout=5,
                check=False,
            )
            raw = result.stdout.strip() or result.stderr.strip()
            # Typical format: "ClamAV 1.4.1/27584/Mon Sep 21 08:30:00 2026"
            parts = raw.split("/")
            clamav_ver = parts[0].strip() if len(parts) > 0 else "ClamAV"
            db_ver = parts[1].strip() if len(parts) > 1 else "Unknown"
            db_date = parts[2].strip() if len(parts) > 2 else "Unknown"

            res = {
                "installed": True,
                "clamav_version": clamav_ver,
                "db_version": db_ver,
                "db_date": db_date,
                "raw": raw
            }
        except Exception as e:
            res = {
                "installed": True,
                "clamav_version": "ClamAV",
                "db_version": "Error",
                "db_date": str(e),
                "raw": f"Failed to query clamscan: {e}"
            }

        self._cached_version = (now, res)
        return res

    def inspect(self, force: bool = False) -> Dict[str, Any]:
        """Full system audit of ClamAV availability with TTL caching."""
        now = time.time()
        if not force and self._cached_inspect:
            ts, cached_data = self._cached_inspect
            if now - ts < self._cache_ttl:
                return cached_data

        clamscan = self.get_clamscan_path()
        clamdscan = self.get_clamdscan_path()
        clamd = self.get_clamd_path()
        freshclam = self.get_freshclam_path()
        daemon_online, daemon_conn = self.check_daemon_socket()
        version_info = self.get_engine_version(force=force)

        res = {
            "clamscan_path": clamscan,
            "clamdscan_path": clamdscan,
            "clamd_path": clamd,
            "freshclam_path": freshclam,
            "daemon_online": daemon_online,
            "daemon_connection": daemon_conn,
            "version": version_info,
            "ready": bool(clamscan or clamdscan or daemon_online),
        }
        self._cached_inspect = (now, res)
        return res
