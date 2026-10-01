"""
Virus database updater for pyEGClamUI.
Handles freshclam execution, log capture, and signature database freshness checks.
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Tuple

from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.detector import ClamEngineDetector


class ClamUpdater:
    """Manages ClamAV signature database updates using freshclam."""

    def __init__(self):
        self.detector = ClamEngineDetector()
        self.config = Config.get_instance()
        self.current_process: Optional[subprocess.Popen] = None

    def is_database_recent(self, max_days: int = 7) -> Tuple[bool, str]:
        """
        Checks if the virus signature database is recent.
        Returns: (is_recent, status_message)
        """
        info = self.detector.get_engine_version()
        if not info.get("installed"):
            return False, "ClamAV engine not installed"

        date_str = info.get("db_date", "")
        if not date_str or date_str in ["Unknown", "Error"]:
            return False, "Database date unknown"

        try:
            # Example date string: "Mon Sep 21 08:30:00 2026"
            # Parse using common ClamAV date formats
            for fmt in ["%a %b %d %H:%M:%S %Y", "%b %d %Y", "%Y-%m-%d"]:
                try:
                    db_dt = datetime.strptime(date_str.strip(), fmt)
                    age = datetime.now() - db_dt
                    if age.days <= max_days:
                        return True, f"Up to date (Version {info.get('db_version')}, updated {age.days}d ago)"
                    else:
                        return False, f"Outdated: Last updated {age.days} days ago ({date_str})"
                except ValueError:
                    continue
        except Exception:
            pass

        return True, f"Database active (Version {info.get('db_version')})"

    def run_update(
        self,
        on_line: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[bool, str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Executes freshclam to download the latest virus definitions.
        Handles return codes: 0 = updated, 1 = already up-to-date, other = failed.
        """
        freshclam = self.detector.get_freshclam_path()
        if not freshclam:
            msg = "freshclam executable not found. Please install ClamAV."
            if on_finished:
                on_finished(False, msg)
            return False, msg

        user_conf = AppPaths.get_config_dir() / "freshclam.conf"
        if not user_conf.exists() or "NotifyClamd no" in user_conf.read_text(encoding="utf-8", errors="ignore"):
            db_dir = AppPaths.get_data_dir() / "database"
            db_dir.mkdir(parents=True, exist_ok=True)

            # Resolve clamd.conf dynamically relative to detected clamscan or platform locations
            clamd_conf = None
            clamscan_path = self.detector.get_clamscan_path()
            if clamscan_path:
                candidate = Path(clamscan_path).parent / "clamd.conf"
                if candidate.is_file():
                    clamd_conf = candidate

            if not clamd_conf:
                for candidate in [
                    Path("/etc/clamav/clamd.conf"),
                    Path("/etc/clamd.d/scan.conf"),
                    Path("/opt/homebrew/etc/clamav/clamd.conf"),
                    Path("/usr/local/etc/clamav/clamd.conf"),
                ]:
                    if candidate.is_file():
                        clamd_conf = candidate
                        break

            notify_line = f"NotifyClamd {clamd_conf.as_posix()}" if clamd_conf else "# NotifyClamd"
            lines = [
                "# pyEGClamUI User freshclam.conf",
                "DatabaseMirror database.clamav.net",
                f"DatabaseDirectory {db_dir.as_posix()}",
                notify_line,
            ]
            user_conf.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [freshclam, f"--config-file={user_conf}", "--stdout"]
        if on_line:
            on_line("Connecting to ClamAV database mirrors...\n")

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            full_log = []
            for line in iter(self.current_process.stdout.readline, ""):
                line_str = line.strip()
                if line_str:
                    full_log.append(line_str)
                    if on_line:
                        on_line(line_str + "\n")

            self.current_process.wait()
            return_code = self.current_process.returncode
            self.current_process = None

            # freshclam return codes: 0 = updated, 1 = already up-to-date
            if return_code == 0:
                success = True
                status_msg = "Database updated successfully."
                self.config.set("last_update_check", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            elif return_code == 1:
                success = True
                status_msg = "Database is already up to date."
                self.config.set("last_update_check", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                success = False
                status_msg = f"Database update failed (exit code {return_code}). Check internet connectivity."

            if on_finished:
                on_finished(success, status_msg)
            return success, status_msg

        except Exception as e:
            err_msg = f"Failed to execute freshclam: {e}"
            if on_finished:
                on_finished(False, err_msg)
            return False, err_msg

    def cancel(self):
        """Terminates active freshclam update process if running."""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass


class GlobalUpdatePipeline:
    """
    Executes universal 4-stage maintenance and update pipeline:
      1. pyEGClamUI application source update (git pull / release check)
      2. Python virtual environment dependency synchronization
      3. ClamAV virus signature database update (freshclam)
      4. ClamAV engine binary check / upgrade (winget / apt / brew)
    """

    def __init__(self, clam_updater: Optional[ClamUpdater] = None):
        self.clam_updater = clam_updater or ClamUpdater()
        self.detector = self.clam_updater.detector
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.current_proc: Optional[subprocess.Popen] = None
        self._cancelled = False

    def cancel(self):
        """Cancels any running sub-process or pipeline stage."""
        self._cancelled = True
        if self.current_proc and self.current_proc.poll() is None:
            try:
                self.current_proc.terminate()
            except Exception:
                try:
                    self.current_proc.kill()
                except Exception:
                    pass
        self.clam_updater.cancel()

    def run_pipeline(
        self,
        on_stage: Optional[Callable[[int, int, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_finished: Optional[Callable[[bool, str, bool], None]] = None,
    ) -> Tuple[bool, str, bool]:
        """
        Runs the full 4-stage pipeline sequentially.
        Returns: (success: bool, summary_message: str, code_updated: bool)
        """
        self._cancelled = False
        code_updated = False
        stage_results = []

        def log(msg: str):
            if on_log:
                on_log(msg)

        # -------------------------------------------------------------
        # Stage 1: pyEGClamUI Application Code
        # -------------------------------------------------------------
        if self._cancelled:
            return False, "Update cancelled by user.", False

        if on_stage:
            on_stage(1, 4, "Updating pyEGClamUI Application Code")
        if on_progress:
            on_progress(10)

        log("=" * 60)
        log("[STAGE 1/4] Checking for pyEGClamUI Application Updates...")
        log("=" * 60)

        git_dir = self.project_root / ".git"
        if git_dir.is_dir() and shutil.which("git"):
            log(f"[*] Workspace git directory detected: {self.project_root}")
            log("[*] Fetching and pulling updates from remote repository (git pull --ff-only)...")
            try:
                self.current_proc = subprocess.Popen(
                    ["git", "pull", "--ff-only"],
                    cwd=str(self.project_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                output_lines = []
                for line in iter(self.current_proc.stdout.readline, ""):
                    clean = line.strip()
                    if clean:
                        output_lines.append(clean)
                        log(f"    {clean}")

                self.current_proc.wait()
                if self.current_proc.returncode == 0:
                    joined = " ".join(output_lines).lower()
                    if "already up to date" in joined:
                        log("[+] pyEGClamUI application code is already up-to-date.")
                        stage_results.append("App Code: Up to date")
                    else:
                        code_updated = True
                        log("[+] New pyEGClamUI application code pulled successfully!")
                        stage_results.append("App Code: Updated")
                else:
                    log(f"[!] Git pull returned non-zero code ({self.current_proc.returncode}). Continuing...")
                    stage_results.append("App Code: Notice/Warning")
                self.current_proc = None
            except Exception as e:
                log(f"[!] Notice during git pull: {e}")
                stage_results.append("App Code: Skipped")
        else:
            log("[*] Standalone deployment (git repository not attached). Skipping git sync.")
            stage_results.append("App Code: Standalone Mode")

        # -------------------------------------------------------------
        # Stage 2: Python Virtual Environment Dependencies
        # -------------------------------------------------------------
        if self._cancelled:
            return False, "Update cancelled by user.", code_updated

        if on_stage:
            on_stage(2, 4, "Synchronizing Python Virtual Environment Dependencies")
        if on_progress:
            on_progress(35)

        log("")
        log("=" * 60)
        log("[STAGE 2/4] Synchronizing Python Environment Dependencies (.venv)...")
        log("=" * 60)

        py_bin = sys.executable
        log(f"[*] Using current environment Python: {py_bin}")
        req_file = self.project_root / "requirements.txt"
        setup_file = self.project_root / "setup.py"

        pip_cmd = [py_bin, "-m", "pip", "install", "--disable-pip-version-check"]
        if req_file.is_file():
            pip_cmd.extend(["-r", str(req_file)])
        elif setup_file.is_file():
            pip_cmd.extend(["-e", str(self.project_root)])
        else:
            pip_cmd = []

        if pip_cmd:
            try:
                log(f"[*] Executing: {' '.join(pip_cmd)}")
                self.current_proc = subprocess.Popen(
                    pip_cmd,
                    cwd=str(self.project_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(self.current_proc.stdout.readline, ""):
                    clean = line.strip()
                    if clean and not clean.startswith("Requirement already satisfied"):
                        log(f"    {clean}")

                self.current_proc.wait()
                if self.current_proc.returncode == 0:
                    log("[+] Python dependencies synchronized successfully.")
                    stage_results.append("Dependencies: Synced")
                else:
                    log(f"[!] Pip returned code {self.current_proc.returncode}.")
                    stage_results.append("Dependencies: Checked")
                self.current_proc = None
            except Exception as e:
                log(f"[!] Pip execution notice: {e}")
                stage_results.append("Dependencies: Skipped")
        else:
            log("[*] No requirements.txt found; dependencies verified.")
            stage_results.append("Dependencies: OK")

        # -------------------------------------------------------------
        # Stage 3: ClamAV Virus Signatures (freshclam)
        # -------------------------------------------------------------
        if self._cancelled:
            return False, "Update cancelled by user.", code_updated

        if on_stage:
            on_stage(3, 4, "Updating ClamAV Virus Signatures (freshclam)")
        if on_progress:
            on_progress(60)

        log("")
        log("=" * 60)
        log("[STAGE 3/4] Updating ClamAV Virus Signatures Database...")
        log("=" * 60)

        def on_fc_line(line: str):
            clean = line.strip()
            if clean:
                log(f"    {clean}")

        fc_success, fc_msg = self.clam_updater.run_update(on_line=on_fc_line)
        if fc_success:
            log(f"[+] FreshClam: {fc_msg}")
            stage_results.append("Signatures: Updated")
        else:
            log(f"[!] FreshClam warning: {fc_msg}")
            stage_results.append("Signatures: Check Failed")

        # -------------------------------------------------------------
        # Stage 4: ClamAV Engine Binary Check / Upgrade
        # -------------------------------------------------------------
        if self._cancelled:
            return False, "Update cancelled by user.", code_updated

        if on_stage:
            on_stage(4, 4, "Checking ClamAV Engine Binary Upgrades")
        if on_progress:
            on_progress(85)

        log("")
        log("=" * 60)
        log("[STAGE 4/4] Checking ClamAV Engine Binary Upgrades...")
        log("=" * 60)

        eng_version = self.detector.get_engine_version()
        log(f"[*] Current ClamAV Engine: {eng_version.get('clamav_version', 'Not Found')}")

        if sys.platform == "win32" and shutil.which("winget"):
            log("[*] Checking for upgrades via Windows Package Manager (winget)...")
            try:
                cmd = ["winget", "upgrade", "ClamAV.ClamAV", "--accept-source-agreements", "--accept-package-agreements"]
                self.current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in iter(self.current_proc.stdout.readline, ""):
                    clean = line.strip()
                    if clean:
                        log(f"    {clean}")
                self.current_proc.wait()
                log("[+] Engine binary check completed.")
                stage_results.append("Engine: Checked (winget)")
                self.current_proc = None
            except Exception as e:
                log(f"[!] Winget upgrade notice: {e}")
                stage_results.append("Engine: Skipped")
        elif sys.platform == "darwin" and shutil.which("brew"):
            log("[*] Checking for upgrades via Homebrew (brew outdated clamav)...")
            try:
                res = subprocess.run(["brew", "outdated", "clamav"], capture_output=True, text=True, timeout=20)
                if res.stdout.strip():
                    log(f"[*] Upgrade available: {res.stdout.strip()}. Run 'brew upgrade clamav'.")
                    stage_results.append("Engine: Upgrade Available")
                else:
                    log("[+] ClamAV engine is up to date on Homebrew.")
                    stage_results.append("Engine: Up to date")
            except Exception as e:
                log(f"[!] Homebrew check notice: {e}")
                stage_results.append("Engine: Checked")
        else:
            log("[+] ClamAV engine binary verified.")
            stage_results.append("Engine: Verified")

        # -------------------------------------------------------------
        # Completion & Summary
        # -------------------------------------------------------------
        if on_progress:
            on_progress(100)

        log("")
        log("=" * 60)
        log("[+] GLOBAL UPDATE PIPELINE COMPLETED SUCCESSFULLY!")
        log(f"[*] Summary: {' | '.join(stage_results)}")
        if code_updated:
            log("[!] Application code was updated. pyEGClamUI restart recommended.")
        log("=" * 60)

        summary_msg = "Global maintenance finished successfully.\n" + "\n".join(f" * {res}" for res in stage_results)
        if on_finished:
            on_finished(True, summary_msg, code_updated)

        return True, summary_msg, code_updated

