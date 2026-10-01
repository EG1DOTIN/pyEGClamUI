"""
ClamAV Daemon Service Manager for pyEGClamUI.
Handles cross-platform discovery, activation, latency testing, and lifecycle
management of the resident ClamD memory daemon.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from pyegclamui.core.daemon import ClamDaemonClient
from pyegclamui.core.detector import ClamEngineDetector


class ClamDaemonServiceManager:
    """
    Manages resident ClamD daemon service state, latency verification,
    and platform-specific 1-click elevated activation.
    """

    def __init__(self, detector: Optional[ClamEngineDetector] = None):
        self.detector = detector or ClamEngineDetector()
        self.client = ClamDaemonClient()

    def get_status(self) -> Dict[str, any]:
        """
        Queries daemon connectivity, socket type, and response latency.
        """
        online, conn_str = self.client.check_connection()
        latency_ms = None

        if online:
            latency_ms = self.measure_latency_ms()

        return {
            "online": online,
            "connection": conn_str,
            "latency_ms": latency_ms,
            "latency_label": f"{latency_ms:.1f} ms" if latency_ms is not None else "N/A",
            "mode": "resident" if online else "fallback",
            "mode_title": "Resident Daemon Active" if online else "Daemon Service Inactive",
            "mode_badge": "🟢 Active (<20ms)" if online else "🟡 Inactive (~800ms)",
            "description": (
                f"ClamD resident memory daemon is serving scans on {conn_str} with {latency_ms:.1f}ms latency."
                if online
                else "Resident daemon is offline. File scans use standalone engine fallback (~800ms per file)."
            ),
        }

    def measure_latency_ms(self) -> Optional[float]:
        """Sends a PING command to ClamD and measures round-trip response time in milliseconds."""
        try:
            start_time = time.perf_counter()
            online, _ = self.client.check_connection()
            if not online:
                return None
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return max(0.1, round(elapsed_ms, 2))
        except Exception:
            return None

    def activate_daemon(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        timeout_seconds: int = 12,
    ) -> Tuple[bool, str]:
        """
        Triggers elevated service registration and startup across Windows, Linux, and macOS.
        Polls the daemon socket until active or timeout.
        """
        def log(msg: str):
            if on_log:
                on_log(msg)

        log("[*] Initializing ClamD service activation...")

        # If already online, return immediately
        status = self.get_status()
        if status["online"]:
            log(f"[+] ClamD daemon is already online and active on {status['connection']}.")
            return True, f"ClamD is already active on {status['connection']}."

        if sys.platform == "win32":
            success, msg = self._activate_windows(log)
        elif sys.platform.startswith("linux"):
            success, msg = self._activate_linux(log)
        elif sys.platform == "darwin":
            success, msg = self._activate_macos(log)
        else:
            return False, f"Unsupported operating system: {sys.platform}"

        if not success:
            return False, msg

        # Poll socket until online
        log("[*] Verifying ClamD socket connection on 127.0.0.1:3310...")
        start_poll = time.time()
        while time.time() - start_poll < timeout_seconds:
            time.sleep(0.6)
            online, conn_info = self.client.check_connection()
            if online:
                latency = self.measure_latency_ms()
                lat_str = f" ({latency:.1f}ms latency)" if latency else ""
                log(f"[+] ClamD daemon is now connected on {conn_info}{lat_str}!")
                return True, f"ClamD daemon service is active on {conn_info}."

        log("[!] Timed out waiting for ClamD socket response.")
        return False, "Service started, but ClamD socket (127.0.0.1:3310) did not respond in time."

    def _activate_windows(self, log: Callable[[str], None]) -> Tuple[bool, str]:
        """Executes setup_clamd_service.ps1 with Windows Administrator UAC elevation."""
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        script_path = project_root / "setup" / "setup_clamd_service.ps1"

        if not script_path.is_file():
            log(f"[!] PowerShell activation script not found: {script_path}")
            return False, f"Missing script: {script_path}"

        clam_path = self.detector.get_clamscan_path()
        clam_dir = str(Path(clam_path).parent) if clam_path else ""

        log("[*] Requesting Windows Administrator elevation (UAC prompt)...")
        # Launch elevated PowerShell process with -Verb RunAs
        ps_args = f"-NoProfile -ExecutionPolicy Bypass -File \"{script_path}\""
        if clam_dir:
            ps_args += f" -ClamDir \"{clam_dir}\""

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '{ps_args}'",
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if res.returncode != 0:
                log(f"[!] Elevation request or script exited with code {res.returncode}: {res.stderr.strip()}")
                return False, "UAC prompt was declined or service registration was cancelled."
            log("[+] Elevated PowerShell service configuration completed.")
            return True, "Elevation completed."
        except subprocess.TimeoutExpired:
            log("[!] Elevation script timed out.")
            return False, "UAC elevation timed out."
        except Exception as e:
            log(f"[!] Subprocess launch error: {e}")
            return False, f"Failed to launch elevation process: {e}"

    def _activate_linux(self, log: Callable[[str], None]) -> Tuple[bool, str]:
        """Activates clamav-daemon on Linux using pkexec or systemctl."""
        services = ["clamav-daemon", "clamd@scan"]
        for svc in services:
            log(f"[*] Attempting to enable and start {svc} via systemctl...")
            if shutil.which("pkexec"):
                cmd = ["pkexec", "systemctl", "enable", "--now", svc]
            else:
                cmd = ["sudo", "systemctl", "enable", "--now", svc]

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if res.returncode == 0:
                    log(f"[+] Started {svc} successfully.")
                    return True, f"Started {svc}."
            except Exception as e:
                log(f"[!] Notice trying {svc}: {e}")

        return False, "Could not start clamav-daemon via systemctl. Please run 'sudo systemctl enable --now clamav-daemon'."

    def _activate_macos(self, log: Callable[[str], None]) -> Tuple[bool, str]:
        """Activates ClamAV background daemon on macOS using Homebrew services."""
        if not shutil.which("brew"):
            return False, "Homebrew is required to manage ClamAV daemon on macOS."

        log("[*] Starting ClamAV service via Homebrew: brew services start clamav...")
        try:
            res = subprocess.run(["brew", "services", "start", "clamav"], capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                log("[+] Homebrew service started successfully.")
                return True, "Homebrew service started."
            return False, f"brew services failed: {res.stderr.strip()}"
        except Exception as e:
            return False, f"Failed to execute brew services: {e}"
