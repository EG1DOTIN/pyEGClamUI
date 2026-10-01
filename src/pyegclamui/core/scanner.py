"""
Core scanner engine for pyEGClamUI.
Handles process execution, real-time output parsing, threat remediation, and progress callbacks.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil
from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.daemon import ClamDaemonClient
from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.logger import get_logger, log_scan_report
from pyegclamui.core.quarantine import QuarantineManager

logger = get_logger("scanner")


class ScanType:
    QUICK_SCAN = "Quick Scan"
    FULL_SCAN = "Full Scan"
    CUSTOM_SCAN = "Custom Scan"
    MEMORY_SCAN = "Memory Scan"


class ScanReport:
    """Encapsulates scan metrics and threat detections."""

    def __init__(self, scan_type: str):
        self.scan_type = scan_type
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.scanned_files: int = 0
        self.scanned_dirs: int = 0
        self.threats_found: int = 0
        self.threats_list: List[Dict[str, str]] = []
        self.errors_count: int = 0
        self.errors_list: List[Dict[str, str]] = []
        self.cancelled: bool = False
        self.summary_text: str = ""

    def duration_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return round((end - self.start_time).total_seconds(), 1)


class ClamScanner:
    """Executes clamscan with safe arguments and parses live progress."""

    def __init__(self):
        self.config = Config.get_instance()
        self.detector = ClamEngineDetector()
        self.daemon_client = ClamDaemonClient()
        self.quarantine_mgr = QuarantineManager()
        self.current_process: Optional[subprocess.Popen] = None
        self.is_running = False
        self._cancelled = False

    def get_system_drives(self) -> List[str]:
        """Cross-platform drive partition enumeration using psutil."""
        drives = []
        for part in psutil.disk_partitions(all=False):
            mount = part.mountpoint
            if sys.platform == "win32":
                if part.fstype and not mount.startswith(("\\\\", "//")):
                    drives.append(mount)
            else:
                if mount in ["/", "/home"] or mount.startswith("/media/") or mount.startswith("/Volumes/"):
                    if Path(mount).is_dir():
                        drives.append(mount)
        return list(dict.fromkeys(drives)) or ["/"]

    def get_quick_scan_paths(self) -> List[str]:
        """Returns standard high-risk user directories for fast scanning."""
        home = Path.home()
        candidates = [
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
        ]
        if sys.platform == "win32":
            candidates.extend([
                Path(os.getenv("TEMP", "")),
                Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
            ])
        else:
            candidates.extend([
                Path("/tmp"),
                home / ".local" / "bin",
            ])
        return [str(p.resolve()) for p in candidates if p and p.exists() and p.is_dir()]

    def build_clamscan_args(self, targets: List[str]) -> List[str]:
        """Builds safe, discrete argument array for clamscan process execution."""
        clamscan_path = self.detector.get_clamscan_path()
        if not clamscan_path:
            raise FileNotFoundError("clamscan executable not found. Please verify ClamAV is installed.")

        args = [
            clamscan_path,
            "--recursive",
            "--stdout",
            "--bell",
        ]

        user_db = AppPaths.get_data_dir() / "database"
        if user_db.is_dir() and any(user_db.glob("*.c*d")):
            args.extend(["--database", str(user_db.resolve())])

        # File size limits
        max_size_mb = self.config.get("scan_settings", "max_file_size_mb", default=50)
        if max_size_mb > 0:
            args.append(f"--max-filesize={max_size_mb}M")

        # Archive extraction
        extract_archives = self.config.get("scan_settings", "extract_archives", default=True)
        if not extract_archives:
            args.append("--scan-archive=no")
        else:
            max_ext_mb = self.config.get("scan_settings", "max_extract_size_mb", default=100)
            max_ext_files = self.config.get("scan_settings", "max_extract_files", default=1000)
            max_rec = self.config.get("scan_settings", "max_recursion", default=15)
            args.extend([
                f"--max-scansize={max_ext_mb}M",
                f"--max-filesize={max_size_mb}M",
                f"--max-files={max_ext_files}",
                f"--max-recursion={max_rec}"
            ])

        # Exclusions / Inclusions
        scan_only = self.config.get("scan_settings", "include_only_extensions", default=[])
        if scan_only:
            for ext in scan_only:
                clean_ext = ext.lstrip(".")
                args.append(f"--include=.*\\.{clean_ext}$")
        else:
            excludes = self.config.get("scan_settings", "exclude_extensions", default=[])
            for ext in excludes:
                clean_ext = ext.lstrip(".")
                args.append(f"--exclude=.*\\.{clean_ext}$")

        # Target paths
        args.extend(targets)
        return args

    def parse_line(self, line_str: str) -> Optional[Dict[str, Any]]:
        """
        Parses a single line of output from clamscan.
        Handles threats, clean files, errors, warnings, and summary statistics.
        Robust against Windows drive letters, spaces, and colons in filenames.
        """
        line_str = line_str.strip()
        if not line_str:
            return None

        # 1. Threat detected: "<path>: <threat_name> FOUND"
        if line_str.endswith("FOUND"):
            m = re.search(r"^(.*):\s+(.+?)\s+FOUND$", line_str)
            if m:
                return {
                    "type": "threat",
                    "path": m.group(1).strip(),
                    "threat": m.group(2).strip(),
                }

        # 2. Clean file: "<path>: OK"
        if line_str.endswith("OK"):
            m = re.search(r"^(.*):\s+OK$", line_str)
            clean_path = m.group(1).strip() if m else line_str[:-2].strip().rstrip(":")
            return {
                "type": "ok",
                "path": clean_path,
            }

        # 3. File error: "<path>: <error_msg> ERROR"
        if line_str.endswith("ERROR"):
            m = re.search(r"^(.*):\s+(.+?)\s+ERROR$", line_str)
            if m:
                return {
                    "type": "error",
                    "path": m.group(1).strip(),
                    "error": m.group(2).strip(),
                }
            return {"type": "error", "path": "", "error": line_str}

        # 4. Warning: "<path>: <warning_msg> WARNING"
        if line_str.endswith("WARNING"):
            m = re.search(r"^(.*):\s+(.+?)\s+WARNING$", line_str)
            if m:
                return {
                    "type": "warning",
                    "path": m.group(1).strip(),
                    "warning": m.group(2).strip(),
                }

        # 5. Summary statistics
        if "Scanned files:" in line_str:
            try:
                count = int(line_str.split(":")[-1].strip())
                return {"type": "summary_scanned_files", "count": count}
            except ValueError:
                pass
        elif "Infected files:" in line_str:
            try:
                count = int(line_str.split(":")[-1].strip())
                return {"type": "summary_infected_files", "count": count}
            except ValueError:
                pass
        elif "Total errors:" in line_str:
            try:
                count = int(line_str.split(":")[-1].strip())
                return {"type": "summary_errors", "count": count}
            except ValueError:
                pass

        return {"type": "raw", "text": line_str}

    def _remediate_threat(self, file_path: str, threat_name: str, action_preference: int) -> str:
        """Applies configured remediation action (Report, Trash, or Quarantine)."""
        if action_preference == 2:  # Delete / Trash
            try:
                from send2trash import send2trash
                send2trash(file_path)
                return "Moved to Trash"
            except Exception:
                try:
                    os.remove(file_path)
                    return "Deleted"
                except Exception as ex:
                    return f"Delete Failed ({ex})"
        elif action_preference == 3:  # Quarantine
            q_item = self.quarantine_mgr.quarantine_file(file_path, threat_name)
            return "Quarantined" if q_item else "Quarantine Failed"
        return "Reported"

    def scan_with_daemon(
        self,
        scan_type: str,
        targets: List[str],
        on_progress: Optional[Callable[[str], None]] = None,
        on_threat: Optional[Callable[[Dict[str, str]], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> ScanReport:
        """Executes high-performance scan using clamd Unix domain or TCP socket."""
        self.is_running = True
        self._cancelled = False
        report = ScanReport(scan_type=scan_type)

        if not targets:
            report.summary_text = "No target paths specified for scanning."
            report.end_time = datetime.now()
            self.is_running = False
            return report

        if on_status:
            on_status(f"Starting {scan_type} via ClamAV Daemon...")

        action_preference = self.config.get("preferences", "action_on_threat", default=3)

        for target in targets:
            if self._cancelled:
                break
            results = self.daemon_client.scan_path(target, contscan=True)
            for res in results:
                if self._cancelled:
                    break
                status = res.get("status")
                file_path = res.get("path", "")
                if status == "FOUND":
                    threat_name = res.get("threat", "Threat")
                    action_taken = self._remediate_threat(file_path, threat_name, action_preference)
                    threat_info = {
                        "path": file_path,
                        "threat": threat_name,
                        "action": action_taken,
                        "time": datetime.now().strftime("%H:%M:%S"),
                    }
                    report.threats_found += 1
                    report.threats_list.append(threat_info)
                    if on_threat:
                        on_threat(threat_info)
                elif status == "OK":
                    report.scanned_files += 1
                    if on_progress:
                        on_progress(file_path)
                elif status == "ERROR":
                    report.errors_count += 1
                    report.errors_list.append({
                        "path": file_path,
                        "error": res.get("error", "Daemon scan error"),
                    })

        report.end_time = datetime.now()
        report.cancelled = self._cancelled
        self.is_running = False

        log_scan_report(
            scan_type=report.scan_type,
            duration_sec=report.duration_seconds(),
            scanned_count=report.scanned_files,
            threats_count=report.threats_found,
            targets=targets,
            details="Engine: clamd daemon",
        )

        if on_status:
            status_msg = (
                "Scan cancelled."
                if report.cancelled
                else f"Scan finished. Found {report.threats_found} threat(s)."
            )
            on_status(status_msg)

        return report

    def scan(
        self,
        scan_type: str,
        targets: List[str],
        on_progress: Optional[Callable[[str], None]] = None,
        on_threat: Optional[Callable[[Dict[str, str]], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        prefer_daemon: bool = False,
    ) -> ScanReport:
        """
        Executes scan synchronously (intended to run inside a worker thread).
        If prefer_daemon is True and clamd is online, routes to scan_with_daemon.
        """
        self.is_running = True
        self._cancelled = False
        report = ScanReport(scan_type=scan_type)

        if not targets:
            report.summary_text = "No target paths specified for scanning."
            report.end_time = datetime.now()
            self.is_running = False
            return report

        if prefer_daemon:
            daemon_online, daemon_type = self.daemon_client.check_connection()
            if daemon_online:
                return self.scan_with_daemon(
                    scan_type=scan_type,
                    targets=targets,
                    on_progress=on_progress,
                    on_threat=on_threat,
                    on_status=on_status,
                )

        try:
            cmd = self.build_clamscan_args(targets)
        except FileNotFoundError as fnf:
            daemon_online, _ = self.daemon_client.check_connection()
            if daemon_online:
                return self.scan_with_daemon(
                    scan_type=scan_type,
                    targets=targets,
                    on_progress=on_progress,
                    on_threat=on_threat,
                    on_status=on_status,
                )
            report.summary_text = f"Error: {fnf}"
            report.end_time = datetime.now()
            self.is_running = False
            return report
        except Exception as e:
            report.summary_text = f"Error: {e}"
            report.end_time = datetime.now()
            self.is_running = False
            return report

        if on_status:
            on_status(f"Starting {scan_type}...")

        # Setup process
        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as e:
            report.summary_text = f"Failed to start scanner process: {e}"
            report.end_time = datetime.now()
            self.is_running = False
            return report

        action_preference = self.config.get("preferences", "action_on_threat", default=3)

        # Output parser loop
        for line in iter(self.current_process.stdout.readline, ""):
            parsed = self.parse_line(line)
            if not parsed:
                continue

            ptype = parsed.get("type")

            if ptype == "threat":
                file_path = parsed["path"]
                threat_name = parsed["threat"]
                action_taken = self._remediate_threat(file_path, threat_name, action_preference)

                threat_info = {
                    "path": file_path,
                    "threat": threat_name,
                    "action": action_taken,
                    "time": datetime.now().strftime("%H:%M:%S")
                }
                report.threats_found += 1
                report.threats_list.append(threat_info)

                if on_threat:
                    on_threat(threat_info)

            elif ptype == "ok":
                report.scanned_files += 1
                if on_progress:
                    on_progress(parsed["path"])

            elif ptype == "error":
                report.errors_count += 1
                report.errors_list.append({"path": parsed.get("path", ""), "error": parsed.get("error", "")})

            elif ptype == "summary_scanned_files":
                report.scanned_files = parsed["count"]

            elif ptype == "summary_infected_files":
                if parsed["count"] > report.threats_found:
                    report.threats_found = parsed["count"]

            elif ptype == "summary_errors":
                report.errors_count = parsed["count"]

        self.current_process.wait()
        report.end_time = datetime.now()
        report.cancelled = self._cancelled
        self.is_running = False
        self.current_process = None

        log_scan_report(
            scan_type=report.scan_type,
            duration_sec=report.duration_seconds(),
            scanned_count=report.scanned_files,
            threats_count=report.threats_found,
            targets=targets,
            details="Engine: clamscan executable",
        )

        if on_status:
            status_msg = "Scan cancelled." if report.cancelled else f"Scan finished. Found {report.threats_found} threat(s)."
            on_status(status_msg)

        return report

    def stop(self) -> None:
        """Gracefully terminates the active scan process."""
        self._cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
        self.is_running = False


def cli_main() -> None:
    """Command-line entry point for `pyegclamui-scan`."""
    parser = argparse.ArgumentParser(description="pyEGClamUI CLI Scanner - Fast, cross-platform ClamAV interface")
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to scan (default: current dir)")
    parser.add_argument("-q", "--quick", action="store_true", help="Perform quick scan on system risk directories")
    parser.add_argument("-f", "--full", action="store_true", help="Perform full scan on all available disk drives")
    parser.add_argument("-a", "--action", type=int, choices=[1, 2, 3], help="Action: 1=Report, 2=Trash/Delete, 3=Quarantine")
    args = parser.parse_args()

    scanner = ClamScanner()
    if args.action:
        Config.get_instance().set("preferences", "action_on_threat", args.action)

    if args.quick:
        targets = scanner.get_quick_scan_paths()
        scan_type = ScanType.QUICK_SCAN
    elif args.full:
        targets = scanner.get_system_drives()
        scan_type = ScanType.FULL_SCAN
    else:
        targets = [str(Path(p).resolve()) for p in args.paths]
        scan_type = ScanType.CUSTOM_SCAN

    print(f"\n--- pyEGClamUI Scanner ({scan_type}) ---")
    print(f"Target(s): {', '.join(targets)}\n")

    def on_prog(f):
        print(f" [OK] {f}")

    def on_threat(t):
        print(f" [!] THREAT: {t['threat']} in {t['path']} -> {t['action']}")

    report = scanner.scan(
        scan_type=scan_type,
        targets=targets,
        on_progress=on_prog,
        on_threat=on_threat
    )

    print("\n--- Scan Results ---")
    print(f"Duration:        {report.duration_seconds()} seconds")
    print(f"Files Scanned:   {report.scanned_files}")
    print(f"Threats Found:   {report.threats_found}")
    print(f"Errors:          {report.errors_count}")
    for t in report.threats_list:
        print(f"  * {t['threat']} ({t['path']}) -> {t['action']}")
    print("---------------------\n")


if __name__ == "__main__":
    cli_main()
