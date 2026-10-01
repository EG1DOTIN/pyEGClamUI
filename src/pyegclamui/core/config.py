"""
Configuration manager for pyEGClamUI.
Stores user settings and state in standard, human-readable JSON files.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from pyegclamui import __version__


class AppPaths:
    """Manages cross-platform standard directories for pyEGClamUI."""

    @staticmethod
    def get_config_dir() -> Path:
        """Returns standard user configuration directory."""
        if sys.platform == "win32":
            base = os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))
            path = Path(base) / "pyEGClamUI"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / "pyEGClamUI"
        else:
            base = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            path = Path(base) / "pyegclamui"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_data_dir() -> Path:
        """Returns standard user application data directory."""
        if sys.platform == "win32":
            base = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            path = Path(base) / "pyEGClamUI"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / "pyEGClamUI"
        else:
            base = os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
            path = Path(base) / "pyegclamui"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_quarantine_dir() -> Path:
        """Returns directory where quarantined threats are safely stored."""
        path = AppPaths.get_data_dir() / "quarantine"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_logs_dir() -> Path:
        """Returns directory where application and scan logs are written."""
        if sys.platform == "win32":
            path = AppPaths.get_data_dir() / "logs"
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Logs" / "pyEGClamUI"
        else:
            base = os.getenv("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
            path = Path(base) / "pyegclamui" / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_package_root() -> Path:
        """Returns root directory of the installed pyegclamui package."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            if (meipass / "pyegclamui").exists():
                return meipass / "pyegclamui"
            return meipass
        return Path(__file__).resolve().parent.parent

    @staticmethod
    def get_asset_path(*subpaths: str) -> Path:
        """Returns absolute path to a bundled asset file."""
        pkg_asset = AppPaths.get_package_root() / "assets" / Path(*subpaths)
        if pkg_asset.exists():
            return pkg_asset
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            alt = Path(sys._MEIPASS) / "assets" / Path(*subpaths)
            if alt.exists():
                return alt
        return pkg_asset

    @staticmethod
    def get_app_icon_path() -> Path:
        """Returns the best available icon file for the current operating system."""
        if sys.platform in ("linux", "darwin"):
            for candidate in ["egav.png", "egav.ico"]:
                p = AppPaths.get_asset_path(candidate)
                if p.exists():
                    return p
        else:
            for candidate in ["egav.ico", "egav.png"]:
                p = AppPaths.get_asset_path(candidate)
                if p.exists():
                    return p
        return AppPaths.get_asset_path("egav.png")


class Config:
    """Manages application settings and preferences."""

    _instance = None

    DEFAULT_CONFIG: Dict[str, Any] = {
        "preferences": {
            "real_time_protection": False,
            "auto_updates": True,
            "action_on_threat": 3,  # 1: Report, 2: Delete/Trash, 3: Quarantine
            "notifications": True,
            "theme": "dark",  # "dark" or "light"
            "close_to_tray": True,
            "confirm_exit_from_tray": True,
            "start_with_system": False,
            "first_run_completed": False,
        },
        "scan_settings": {
            "max_file_size_mb": 50,
            "extract_archives": True,
            "max_extract_size_mb": 100,
            "max_extract_files": 1000,
            "max_recursion": 15,
            "monitor_dirs": [],
            "exclude_extensions": [
                "jpg", "jpeg", "gif", "png", "bmp", "tiff", "webp",
                "mp3", "wav", "flac", "ogg", "m4a",
                "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm"
            ],
            "include_only_extensions": [],
            "custom_clamscan_path": "",
            "custom_clamd_path": "",
            "custom_freshclam_path": "",
            "clamd_tcp_port": 3310,
            "clamd_tcp_host": "127.0.0.1",
            "clamd_unix_socket": "/var/run/clamav/clamd.ctl",
        },
        "user_profile": {
            "user_id": "",
            "display_name": "",
            "email": "",
            "is_anonymous": True,
        },
        "telemetry": {
            "enabled": False,
            "firebase_project_id": "eg1-pyegclamui",
            "share_os_info": True,
            "share_clamav_version": True,
            "share_scan_stats": True,
            "last_active_heartbeat": "",
            "install_reported": False,
        },
        "last_update_check": "",
        "version": __version__
    }

    def __init__(self):
        self.config_file = AppPaths.get_config_dir() / "config.json"
        self.data: Dict[str, Any] = {}
        self.load()

    @classmethod
    def get_instance(cls) -> "Config":
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

    def load(self) -> None:
        """Loads configuration from JSON file or populates defaults if missing."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data = self._deep_merge(self.DEFAULT_CONFIG, loaded)
                    self._ensure_user_id()
                    return
            except Exception as e:
                print(f"[Config] Error reading {self.config_file}: {e}, using defaults.")
        self.data = json.loads(json.dumps(self.DEFAULT_CONFIG))
        self._ensure_user_id()
        self.save()

    def _ensure_user_id(self):
        """Generates an anonymous user ID if none exists."""
        profile = self.data.setdefault("user_profile", {})
        if not profile.get("user_id"):
            import random
            profile["user_id"] = f"Guest{random.randint(10000000, 99999999)}"


    def save(self) -> None:
        """Persists current configuration to JSON file."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Failed to save {self.config_file}: {e}")

    def get(self, *keys: str, default: Any = None) -> Any:
        """Navigates hierarchical keys: config.get('preferences', 'theme')."""
        curr = self.data
        for key in keys:
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
            else:
                return default
        return curr

    def set(self, *keys_and_value: Any) -> None:
        """Sets a value: config.set('preferences', 'theme', 'light')."""
        if len(keys_and_value) < 2:
            raise ValueError("set() requires at least one key and a value")
        keys = keys_and_value[:-1]
        value = keys_and_value[-1]

        curr = self.data
        for key in keys[:-1]:
            curr = curr.setdefault(key, {})
        curr[keys[-1]] = value
        self.save()

    def reset_defaults(self) -> None:
        """Resets all configuration values to defaults."""
        self.data = json.loads(json.dumps(self.DEFAULT_CONFIG))
        self.save()

    @staticmethod
    def _deep_merge(default: dict, override: dict) -> dict:
        result = dict(default)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = Config._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
