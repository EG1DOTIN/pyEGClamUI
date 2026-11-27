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
from pyegclamui.core.process import (
    format_subprocess_os_error,
    is_compatible_windows_binary,
    run_hidden_process,
)


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
        # Check bundled / portable engine relative to application
        try:
            pkg_root = AppPaths.get_package_root()
            for rel in [pkg_root.parent / "engine", pkg_root / "engine", Path(sys.executable).parent / "engine"]:
                if rel.is_dir():
                    paths.insert(0, rel)
        except Exception:
            pass

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

    @staticmethod
    def _is_usable_executable(candidate: Path) -> bool:
        """Checks file existence, execute permission, and Windows PE compatibility."""
        if not candidate.is_file():
            return False
        if sys.platform == "win32":
            ok, _ = is_compatible_windows_binary(candidate)
            return ok
        return os.access(candidate, os.X_OK)

    def find_executable(self, binary_name: str, custom_key: Optional[str] = None) -> Optional[str]:
        """Locates an executable in custom config, system PATH, or standard OS directories."""
        ext = ".exe" if sys.platform == "win32" else ""
        bin_with_ext = binary_name + ext

        # 1. Check custom path in config
        if custom_key:
            custom_path = self.config.get("scan_settings", custom_key)
            if custom_path:
                cand = Path(custom_path)
                if self._is_usable_executable(cand):
                    return str(cand.resolve())

        # 2. Check system PATH (on Windows, require .exe match first so scripts aren't picked)
        found = shutil.which(bin_with_ext)
        if not found and sys.platform != "win32":
            found = shutil.which(binary_name)
        if found:
            cand = Path(found)
            if self._is_usable_executable(cand):
                return str(cand.resolve())

        # 3. Check standard Windows directories
        if sys.platform == "win32":
            for base in self.get_standard_windows_paths():
                candidate = base / bin_with_ext
                if self._is_usable_executable(candidate):
                    return str(candidate.resolve())

        # 4. Check common Unix and macOS directories
        if sys.platform != "win32":
            for base in self.get_standard_unix_paths():
                candidate = base / binary_name
                if self._is_usable_executable(candidate):
                    return str(candidate.resolve())

        return None

    @classmethod
    def get_standard_database_directories(cls) -> List[Path]:
        """Returns standard locations where ClamAV virus databases are stored."""
        dirs = [
            AppPaths.get_database_dir(),
        ]
        if sys.platform == "win32":
            dirs.extend([
                Path("C:/Program Files/ClamAV/database"),
                Path("C:/Program Files (x86)/ClamAV/database"),
                Path("C:/ProgramData/ClamAV/db"),
            ])
            val = os.getenv("LOCALAPPDATA")
            if val and val.strip():
                dirs.append(Path(val) / "ClamAV" / "db")
        elif sys.platform == "darwin":
            dirs.extend([
                Path("/opt/homebrew/var/lib/clamav"),
                Path("/usr/local/var/lib/clamav"),
                Path("/var/lib/clamav"),
            ])
        else:
            dirs.extend([
                Path("/var/lib/clamav"),
                Path("/usr/local/share/clamav"),
                Path("/var/clamav"),
            ])
        return dirs

    @staticmethod
    def _dir_has_signatures(db_dir: Path) -> bool:
        """Fast directory scan checking for valid .cvd/.cld database files (> 1 KB)."""
        if not db_dir.is_dir():
            return False
        try:
            with os.scandir(db_dir) as entries:
                for entry in entries:
                    name_lower = entry.name.lower()
                    if (name_lower.endswith(".cvd") or name_lower.endswith(".cld")) and entry.is_file():
                        if entry.stat().st_size > 1000:
                            return True
        except (PermissionError, OSError):
            return False
        return False

    def get_active_database_dir(self) -> Optional[Path]:
        """Returns the first directory containing valid ClamAV virus signatures."""
        for d in self.get_standard_database_directories():
            if self._dir_has_signatures(d):
                return d
        return None

    def has_virus_signatures(self) -> bool:
        """Checks whether valid ClamAV virus signature databases (.cvd, .cld) are present."""
        return self.get_active_database_dir() is not None

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
                "has_signatures": False,
                "raw": "clamscan executable not found in PATH"
            }
            self._cached_version = (now, res)
            return res

        try:
            active_db_dir = self.get_active_database_dir()
            cmd = [clamscan, "--version"]
            if active_db_dir is not None:
                cmd.extend(["--database", str(active_db_dir.resolve())])

            result = run_hidden_process(
                cmd,
                capture_output=True,
                timeout=5,
                check=False,
            )
            raw = result.stdout.strip() or result.stderr.strip()
            # Typical format: "ClamAV 1.4.1/27584/Mon Sep 21 08:30:00 2026"
            parts = raw.split("/")
            clamav_ver = parts[0].strip() if len(parts) > 0 and parts[0].strip() else "ClamAV"
            db_ver = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "Unknown"
            db_date = parts[2].strip() if len(parts) > 2 and parts[2].strip() else "Unknown"
            has_sigs = active_db_dir is not None
            if not has_sigs and (db_ver in ("Unknown", "0", "") or "No supported database" in raw):
                db_ver = "Missing (Update Required)"
                db_date = "Run FreshClam"

            res = {
                "installed": True,
                "clamav_version": clamav_ver,
                "db_version": db_ver,
                "db_date": db_date,
                "has_signatures": has_sigs,
                "raw": raw,
            }
        except OSError as e:
            err_msg = format_subprocess_os_error(e, Path(clamscan).name)
            is_incompatible = getattr(e, "winerror", None) == 216
            res = {
                "installed": not is_incompatible,
                "clamav_version": "Incompatible Binary" if is_incompatible else "ClamAV",
                "db_version": "Error",
                "db_date": "Error" if is_incompatible else err_msg,
                "has_signatures": False,
                "raw": f"Failed to query clamscan: {err_msg}",
            }
        except Exception as e:
            res = {
                "installed": True,
                "clamav_version": "ClamAV",
                "db_version": "Error",
                "db_date": str(e),
                "has_signatures": False,
                "raw": f"Failed to query clamscan: {e}",
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
        # Reuse signature scan from get_engine_version when clamscan was queried
        has_signatures = (
            bool(version_info.get("has_signatures"))
            if clamscan
            else self.has_virus_signatures()
        )
        engine_usable = bool(version_info.get("installed", True)) if clamscan else False

        res = {
            "clamscan_path": clamscan if engine_usable else None,
            "clamdscan_path": clamdscan,
            "clamd_path": clamd,
            "freshclam_path": freshclam,
            "daemon_online": daemon_online,
            "daemon_connection": daemon_conn,
            "version": version_info,
            "has_signatures": has_signatures,
            "ready": bool((clamscan and engine_usable) or clamdscan or daemon_online),
            "fully_operational": bool(
                ((clamscan and engine_usable) or clamdscan or daemon_online) and has_signatures
            ),
        }
        self._cached_inspect = (now, res)
        return res
