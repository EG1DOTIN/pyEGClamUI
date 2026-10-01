"""
Opt-in transparent telemetry, diagnostic metrics, and issue reporter for pyEGClamUI.
Communicates with Firebase Firestore REST API using Python's standard library.
"""

import json
import os
import random
import socket
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import psutil

from pyegclamui import __version__
from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.logger import get_logger

logger = get_logger("telemetry")


def generate_guest_id() -> str:
    """Generates an anonymous user identifier like Guest48291042."""
    rand_digits = random.randint(10000000, 99999999)
    return f"Guest{rand_digits}"


def get_local_ip() -> str:
    """Resolves local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def sanitize_log_text(raw_text: str) -> str:
    """
    Sanitizes log traces by masking personal user directories, usernames,
    and hostnames to protect privacy when submitting reports or copying to clipboard.
    """
    if not raw_text:
        return ""

    sanitized = raw_text

    # Replace user home path with ~
    home_str = str(Path.home())
    if home_str in sanitized:
        sanitized = sanitized.replace(home_str, "~")
    # Also handle forward-slash version of home
    home_fwd = home_str.replace("\\", "/")
    if home_fwd in sanitized:
        sanitized = sanitized.replace(home_fwd, "~")

    # Mask Windows AppData paths
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data and local_app_data in sanitized:
        sanitized = sanitized.replace(local_app_data, "<LOCALAPPDATA>")

    app_data = os.getenv("APPDATA", "")
    if app_data and app_data in sanitized:
        sanitized = sanitized.replace(app_data, "<APPDATA>")

    # Mask username if still present
    user_name = os.getenv("USERNAME", "") or os.getenv("USER", "")
    if user_name and len(user_name) >= 3 and user_name in sanitized:
        sanitized = sanitized.replace(user_name, "<user>")

    # Mask hostname
    try:
        host = socket.gethostname()
        if host and host in sanitized:
            sanitized = sanitized.replace(host, "<hostname>")
    except Exception:
        pass

    return sanitized


class TelemetryManager:
    """Manages user-consented, transparent diagnostics collection, heartbeats, and Firestore dispatch."""

    def __init__(self):
        self.config = Config.get_instance()
        self.detector = ClamEngineDetector()

    def get_or_create_user_id(self) -> str:
        """Retrieves user ID or initializes an anonymous Guest ID."""
        user_id = self.config.get("user_profile", "user_id", default="")
        if not user_id:
            user_id = generate_guest_id()
            self.config.set("user_profile", "user_id", user_id)
        return user_id

    def build_payload(self) -> Dict[str, Any]:
        """
        Builds telemetry payload strictly adhering to user consent checkboxes.
        Returns a dictionary of consented fields.
        """
        user_id = self.get_or_create_user_id()
        display_name = self.config.get("user_profile", "display_name", default="").strip()
        email = self.config.get("user_profile", "email", default="").strip()

        # Base identification
        payload: Dict[str, Any] = {
            "client_id": user_id,
            "app_name": "pyEGClamUI",
            "app_version": __version__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if display_name:
            payload["display_name"] = display_name
        if email:
            payload["email"] = email

        # Optional consented fields
        if self.config.get("telemetry", "share_os_info", default=True):
            payload["os_platform"] = sys.platform
            payload["os_version"] = f"{sys.platform} (Python {sys.version.split()[0]})"
            try:
                mem = psutil.virtual_memory()
                payload["total_ram_gb"] = round(mem.total / (1024 ** 3), 1)
                payload["available_ram_gb"] = round(mem.available / (1024 ** 3), 1)
            except Exception:
                pass

        if self.config.get("telemetry", "share_clamav_version", default=True):
            engine_info = self.detector.get_engine_version()
            payload["clamav_version"] = engine_info.get("clamav_version", "Unknown")
            payload["signature_db_version"] = engine_info.get("db_version", "Unknown")
            payload["signature_db_date"] = engine_info.get("db_date", "Unknown")

        if self.config.get("telemetry", "share_scan_stats", default=True):
            payload["scan_stats"] = {
                "action_on_threat": self.config.get("preferences", "action_on_threat", default=3),
                "real_time_enabled": self.config.get("preferences", "real_time_protection", default=False),
            }

        return payload

    def get_preview_payload(self) -> str:
        """Returns pretty-printed JSON of the exact telemetry payload."""
        payload = self.build_payload()
        return json.dumps(payload, indent=2)

    def _convert_to_firestore_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Formats standard python dictionary into Firestore Document REST structure."""
        fields: Dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, bool):
                fields[k] = {"booleanValue": v}
            elif isinstance(v, int):
                fields[k] = {"integerValue": str(v)}
            elif isinstance(v, float):
                fields[k] = {"doubleValue": v}
            elif isinstance(v, dict):
                fields[k] = {"stringValue": json.dumps(v)}
            else:
                fields[k] = {"stringValue": str(v)}
        return {"fields": fields}

    def _post_firestore_document(
        self, collection: str, payload: Dict[str, Any], timeout: float = 4.0
    ) -> Tuple[bool, str]:
        """Internal helper to dispatch a document to any Firestore collection."""
        project_id = self.config.get("telemetry", "firebase_project_id", default="eg1-pyegclamui")
        if not project_id or project_id == "disabled":
            return False, "Firebase project ID not configured."

        firestore_doc = self._convert_to_firestore_fields(payload)
        data = json.dumps(firestore_doc).encode("utf-8")
        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection}"

        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 201):
                    return True, "Data sent successfully."
                return False, f"Server responded with HTTP {resp.status}"
        except urllib.error.HTTPError as he:
            err_msg = f"HTTP Error {he.code}: {he.reason}"
            logger.warning(f"Firestore submission error ({collection}): {err_msg}")
            return False, err_msg
        except Exception as e:
            err_msg = f"Network Error: {e}"
            logger.warning(f"Firestore submission error ({collection}): {err_msg}")
            return False, err_msg

    def send_telemetry(self, timeout: float = 3.0) -> Tuple[bool, str]:
        """
        Synchronously sends payload to Firebase Firestore REST API.
        Returns: (success: bool, message: str)
        """
        if not self.config.get("telemetry", "enabled", default=False):
            return False, "Telemetry is disabled in user preferences."

        payload = self.build_payload()
        success, msg = self._post_firestore_document("telemetry", payload, timeout=timeout)
        if success:
            logger.info("Telemetry report dispatched successfully.")
            return True, "Telemetry data sent successfully."
        return False, msg

    def send_telemetry_async(self, on_complete: Optional[Callable[[bool, str], None]] = None) -> None:
        """Dispatches telemetry asynchronously in a background thread."""
        if not self.config.get("telemetry", "enabled", default=False):
            if on_complete:
                on_complete(False, "Telemetry is disabled.")
            return

        def _worker():
            success, msg = self.send_telemetry()
            if on_complete:
                on_complete(success, msg)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def send_install_event(self, telemetry_mode: str, timeout: float = 4.0) -> Tuple[bool, str]:
        """
        Handles initial 1-time installation registration based on user's choice:
        - 'opted_in': Enables full telemetry and sends initial install ping.
        - 'count_only': Disables ongoing telemetry but sends 1-time anonymous count.
        - 'offline': Strict air-gapped mode. Zero network requests.
        """
        self.config.set("preferences", "first_run_completed", True)

        if telemetry_mode == "offline":
            self.config.set("telemetry", "enabled", False)
            self.config.set("telemetry", "install_reported", True)
            return True, "Offline mode configured. Zero network activity."

        if telemetry_mode == "count_only":
            self.config.set("telemetry", "enabled", False)
            self.config.set("telemetry", "install_reported", True)
            payload: Dict[str, Any] = {
                "client_id": "anonymous_install",
                "event": "install",
                "telemetry_mode": "count_only",
                "app_version": __version__,
                "os_platform": sys.platform,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            try:
                mem = psutil.virtual_memory()
                payload["total_ram_gb"] = round(mem.total / (1024 ** 3), 1)
            except Exception:
                pass
            return self._post_firestore_document("telemetry", payload, timeout=timeout)

        # Full opt-in mode
        self.config.set("telemetry", "enabled", True)
        self.config.set("telemetry", "install_reported", True)
        payload = self.build_payload()
        payload["event"] = "install"
        payload["telemetry_mode"] = "opted_in"
        return self._post_firestore_document("telemetry", payload, timeout=timeout)

    def send_heartbeat_if_due(self, timeout: float = 3.0) -> None:
        """
        Evaluates whether 30 days have elapsed since the last active heartbeat.
        If due and telemetry is enabled, asynchronously pings the 'active_installations' collection.
        This provides authentic active user metrics without requiring an uninstallation hook.
        """
        if not self.config.get("telemetry", "enabled", default=False):
            return

        last_str = self.config.get("telemetry", "last_active_heartbeat", default="").strip()
        now_dt = datetime.now(timezone.utc)
        today_str = now_dt.strftime("%Y-%m-%d")

        if last_str:
            try:
                last_dt = datetime.strptime(last_str, "%Y-%m-%d").date()
                if (now_dt.date() - last_dt).days < 30:
                    return  # Not due yet
            except Exception:
                pass

        def _worker():
            user_id = self.get_or_create_user_id()
            payload: Dict[str, Any] = {
                "client_id": user_id,
                "event": "heartbeat",
                "app_version": __version__,
                "os_platform": sys.platform,
                "timestamp": now_dt.isoformat(),
                "active_month": now_dt.strftime("%Y-%m"),
            }
            try:
                mem = psutil.virtual_memory()
                payload["total_ram_gb"] = round(mem.total / (1024 ** 3), 1)
                payload["available_ram_gb"] = round(mem.available / (1024 ** 3), 1)
            except Exception:
                pass

            success, _ = self._post_firestore_document("active_installations", payload, timeout=timeout)
            if success:
                self.config.set("telemetry", "last_active_heartbeat", today_str)

        threading.Thread(target=_worker, daemon=True).start()

    def get_recent_error_logs(self, max_lines: int = 50) -> str:
        """Retrieves and sanitizes the most recent error log snippet for issue reporting."""
        try:
            logs_dir = AppPaths.get_logs_dir()
            error_logs = sorted(
                list(logs_dir.glob("*-errors*.log")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not error_logs:
                return "No error log files found."

            with open(error_logs[0], "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                snippet = "".join(lines[-max_lines:])
                return sanitize_log_text(snippet)
        except Exception as e:
            return f"Could not read error log: {e}"

    def send_issue_report(
        self, description: str, include_logs: bool = True, timeout: float = 5.0
    ) -> Tuple[bool, str]:
        """
        Sends an issue report directly and privately to the Firestore 'issue_reports' collection.
        Does not require a GitHub account and masks personal paths automatically.
        """
        if not description or not description.strip():
            return False, "Please enter an issue description."

        user_id = self.get_or_create_user_id()
        engine_info = self.detector.get_engine_version()

        payload: Dict[str, Any] = {
            "client_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app_version": __version__,
            "os_platform": sys.platform,
            "os_version": f"{sys.platform} (Python {sys.version.split()[0]})",
            "clamav_engine": engine_info.get("clamav_version", "Unknown"),
            "signature_db_version": engine_info.get("db_version", "Unknown"),
            "user_description": description.strip(),
        }

        try:
            mem = psutil.virtual_memory()
            payload["total_ram_gb"] = round(mem.total / (1024 ** 3), 1)
            payload["available_ram_gb"] = round(mem.available / (1024 ** 3), 1)
        except Exception:
            pass

        if include_logs:
            payload["sanitized_error_trace"] = self.get_recent_error_logs(max_lines=60)
        else:
            payload["sanitized_error_trace"] = "Excluded by user."

        return self._post_firestore_document("issue_reports", payload, timeout=timeout)

    def send_issue_report_async(
        self,
        description: str,
        include_logs: bool = True,
        on_complete: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Asynchronously submits an issue report to Firestore."""
        def _worker():
            success, msg = self.send_issue_report(description, include_logs=include_logs)
            if on_complete:
                on_complete(success, msg)

        threading.Thread(target=_worker, daemon=True).start()
