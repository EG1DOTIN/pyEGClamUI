"""
ClamAV backend engine installer and setup manager for pyEGClamUI.
Handles universal engine installation, PATH registration, and freshclam configuration.
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from pyegclamui.core.config import Config
from pyegclamui.core.detector import ClamEngineDetector


class ClamEngineInstaller:
    """Automates ClamAV engine installation and initial database setup."""

    CLAMAV_WINGET_ID = "Cisco.ClamAV"
    FALLBACK_MSI_URL = "https://www.clamav.net/downloads/production/clamav-1.4.1.win.x64.msi"

    def __init__(self):
        self.detector = ClamEngineDetector()
        self.config = Config.get_instance()
        self.is_cancelling = False

    def is_engine_installed(self) -> bool:
        """Checks if clamscan is already available on the system."""
        return bool(self.detector.get_clamscan_path())

    def install_engine(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Executes universal ClamAV installation.
        Attempts winget first, falls back to direct official MSI download.
        """
        if self.is_engine_installed():
            if on_log:
                on_log("[*] ClamAV engine already installed and detected on PATH.")
            return True, "ClamAV engine is already installed."

        if sys.platform == "win32":
            # Try Winget first if available
            if shutil.which("winget"):
                msg = "Installing ClamAV via Windows Package Manager (winget)..."
                if on_status:
                    on_status(msg)
                if on_log:
                    on_log(f"[*] {msg}")
                if on_progress:
                    on_progress(20)

                success, msg = self._install_via_winget(on_status, on_log)
                if success:
                    self._post_install_configure(on_status, on_progress, on_log)
                    return True, "ClamAV successfully installed via winget."
                else:
                    fallback_msg = f"Winget failed ({msg}). Trying official MSI download fallback..."
                    if on_status:
                        on_status(fallback_msg)
                    if on_log:
                        on_log(f"[!] {fallback_msg}")

            # Fallback to direct MSI download and install
            if on_status:
                on_status("Downloading official Cisco ClamAV installer...")
            if on_log:
                on_log(f"[*] Downloading official Cisco ClamAV installer from {self.FALLBACK_MSI_URL}")
            if on_progress:
                on_progress(40)
            return self._install_via_msi(on_status, on_progress, on_log)
        elif sys.platform.startswith("linux"):
            instructions = self.get_platform_install_instructions()
            if on_status:
                on_status(instructions)
            return False, f"Package installation on Linux requires package manager privileges:\n{instructions}"
        elif sys.platform == "darwin":
            instructions = self.get_platform_install_instructions()
            if on_status:
                on_status(instructions)
            return False, f"Package installation on macOS:\n{instructions}"
        else:
            return False, f"Unsupported platform: {sys.platform}"

    @classmethod
    def get_platform_install_instructions(cls) -> str:
        """Returns tailored package manager commands for the current operating system."""
        if sys.platform.startswith("linux"):
            if shutil.which("apt") or shutil.which("apt-get"):
                return (
                    "Debian/Ubuntu detected. Run:\n"
                    "  sudo apt update && sudo apt install -y clamav clamav-daemon\n"
                    "  sudo systemctl start clamav-daemon"
                )
            elif shutil.which("dnf"):
                return (
                    "Fedora/RHEL detected. Run:\n"
                    "  sudo dnf install -y clamav clamd clamav-update\n"
                    "  sudo systemctl start clamd@scan"
                )
            elif shutil.which("pacman"):
                return (
                    "Arch Linux detected. Run:\n"
                    "  sudo pacman -S clamav\n"
                    "  sudo systemctl start clamav-daemon"
                )
            elif shutil.which("zypper"):
                return "openSUSE detected. Run:\n  sudo zypper install -y clamav clamav-daemon"
            return "Linux detected. Please install ClamAV via your package manager: sudo apt install clamav clamav-daemon"
        elif sys.platform == "darwin":
            if shutil.which("brew"):
                return (
                    "macOS with Homebrew detected. Run:\n"
                    "  brew install clamav\n"
                    "  brew services start clamav"
                )
            elif shutil.which("port"):
                return "macOS with MacPorts detected. Run:\n  sudo port install clamav"
            return "macOS detected. Install Homebrew (https://brew.sh) and run:\n  brew install clamav"
        return "Windows detected. Use automated winget or MSI installation."

    def _install_via_winget(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Runs winget non-interactively with auto-accepted agreements."""
        cmd = [
            "winget", "install", self.CLAMAV_WINGET_ID,
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity"
        ]
        if on_log:
            on_log(f"[*] Executing: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            for line in iter(proc.stdout.readline, ""):
                line_str = line.strip()
                if line_str:
                    if on_status:
                        on_status(line_str)
                    if on_log:
                        on_log(f"    {line_str}")

            proc.wait()
            if proc.returncode == 0:
                if on_log:
                    on_log("[+] Winget package installation finished with exit code 0.")
                return True, "Winget install completed successfully."
            else:
                if on_log:
                    on_log(f"[!] Winget returned non-zero exit code: {proc.returncode}")
                return False, f"Winget returned exit code {proc.returncode}"
        except Exception as e:
            if on_log:
                on_log(f"[!] Winget execution exception: {e}")
            return False, f"Error launching winget: {e}"

    def _install_via_msi(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """Downloads official MSI installer and runs quiet installation."""
        temp_dir = Path(os.getenv("TEMP", "C:/Windows/Temp")) / "pyegclamui_setup"
        temp_dir.mkdir(parents=True, exist_ok=True)
        msi_path = temp_dir / "clamav_installer.msi"

        try:
            if on_status:
                on_status(f"Downloading ClamAV MSI from {self.FALLBACK_MSI_URL}...")
            if on_log:
                on_log(f"[*] Starting download from {self.FALLBACK_MSI_URL} to {msi_path}")

            def reporthook(block_num, block_size, total_size):
                if total_size > 0 and on_progress:
                    downloaded = block_num * block_size
                    percent = int(40 + (downloaded / total_size) * 30)
                    on_progress(min(percent, 70))

            urllib.request.urlretrieve(self.FALLBACK_MSI_URL, str(msi_path), reporthook=reporthook)

            if on_status:
                on_status("Installing ClamAV (msiexec)...")
            if on_log:
                on_log("[*] Download complete. Executing msiexec.exe /qn...")
            if on_progress:
                on_progress(75)

            # Run msiexec quietly
            cmd = ["msiexec.exe", "/i", str(msi_path), "/qn", "/norestart"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if res.returncode == 0:
                if on_log:
                    on_log("[+] msiexec completed successfully.")
                self._post_install_configure(on_status, on_progress, on_log)
                return True, "ClamAV MSI installed successfully."
            else:
                if on_log:
                    on_log(f"[!] msiexec failed ({res.returncode}): {res.stderr}")
                return False, f"msiexec failed with exit code {res.returncode}: {res.stderr}"
        except Exception as e:
            if on_log:
                on_log(f"[!] MSI installer exception: {e}")
            return False, f"Failed to download or install ClamAV MSI: {e}"
        finally:
            if msi_path.exists():
                try:
                    msi_path.unlink()
                except Exception:
                    pass

    def _post_install_configure(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Configures freshclam.conf, registers PATH, and checks for binaries."""
        if on_status:
            on_status("Detecting installed binary directory...")
        if on_log:
            on_log("[*] Inspecting candidate ClamAV directories...")
        if on_progress:
            on_progress(80)

        clam_dir = None
        for candidate in ClamEngineDetector.get_standard_windows_paths():
            if (candidate / "clamscan.exe").is_file():
                clam_dir = candidate
                break

        if not clam_dir:
            default_pf = Path("C:/Program Files/ClamAV")
            if default_pf.exists():
                clam_dir = default_pf

        if clam_dir:
            if on_status:
                on_status(f"Found ClamAV at {clam_dir}. Initializing freshclam.conf...")
            if on_log:
                on_log(f"[+] Located ClamAV engine at {clam_dir}")
            self.initialize_freshclam_conf(clam_dir)
            self.register_path_environment(clam_dir)
            if on_log:
                on_log("[+] freshclam.conf verified and PATH registered in Windows environment.")

        if on_status:
            on_status("ClamAV setup completed!")
        if on_progress:
            on_progress(100)

    @staticmethod
    def initialize_freshclam_conf(clamav_dir: Path) -> Tuple[bool, str]:
        """
        Creates a valid freshclam.conf from freshclam.conf.sample by commenting out 'Example'.
        Essential on Windows to allow freshclam to execute without error.
        """
        conf_target = clamav_dir / "freshclam.conf"
        if conf_target.exists():
            return True, "freshclam.conf already exists."

        sample_candidates = [
            clamav_dir / "freshclam.conf.sample",
            clamav_dir / "conf_examples" / "freshclam.conf.sample",
        ]

        sample_file = None
        for c in sample_candidates:
            if c.is_file():
                sample_file = c
                break

        if not sample_file:
            db_dir = clamav_dir / "database"
            default_content = [
                "# Automatically generated by pyEGClamUI",
                "DatabaseMirror database.clamav.net",
                f"DatabaseDirectory {db_dir}",
            ]
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
                conf_target.write_text("\n".join(default_content) + "\n", encoding="utf-8")
                return True, "Created minimal freshclam.conf."
            except Exception as e:
                return False, f"Failed to create freshclam.conf: {e}"

        try:
            content = sample_file.read_text(encoding="utf-8", errors="replace")
            lines = []
            for line in content.splitlines():
                if line.strip().lower() == "example":
                    lines.append("# Example (Commented out by pyEGClamUI setup)")
                else:
                    lines.append(line)
            conf_target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True, f"Successfully created {conf_target} from sample."
        except Exception as e:
            return False, f"Failed to initialize freshclam.conf: {e}"

    @staticmethod
    def register_path_environment(clamav_dir: Path) -> bool:
        """
        Ensures clamav_dir is present in the current session PATH and Windows User PATH registry.
        """
        dir_str = str(clamav_dir.resolve())
        current_path = os.environ.get("PATH", "")
        if dir_str.lower() not in current_path.lower():
            os.environ["PATH"] = f"{dir_str};{current_path}"

        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
                try:
                    user_path, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    user_path = ""

                if dir_str.lower() not in user_path.lower():
                    new_user_path = f"{user_path};{dir_str}" if user_path else dir_str
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_user_path)
                winreg.CloseKey(key)
                return True
            except Exception as e:
                print(f"[Setup] Registry PATH registration notice: {e}")
        return True


def cli_main():
    """Command-line entry point for pyegclamui-setup."""
    parser = argparse.ArgumentParser(description="pyEGClamUI Engine Setup - Universal ClamAV Installer")
    parser.add_argument("--check", action="store_true", help="Check if ClamAV engine is installed")
    parser.add_argument("--install", action="store_true", help="Install official ClamAV engine automatically")
    args = parser.parse_args()

    installer = ClamEngineInstaller()
    if args.check:
        if installer.is_engine_installed():
            print("OK: ClamAV engine is detected and ready.")
            sys.exit(0)
        else:
            print("NOT FOUND: ClamAV engine is not installed on this system.")
            sys.exit(1)

    print("\n--- pyEGClamUI: Universal ClamAV Setup Wizard ---")
    if installer.is_engine_installed():
        print("ClamAV engine is already installed on this machine.")
        sys.exit(0)

    print("ClamAV is required as the backend engine for virus scanning.")
    choice = input("Do you want to download and install ClamAV universally on your PC? [Y/n]: ").strip().lower()
    if choice in ["", "y", "yes"]:
        def on_st(msg):
            print(f" [*] {msg}")
        def on_pr(p):
            print(f" [Progress: {p}%]")

        success, msg = installer.install_engine(on_status=on_st, on_progress=on_pr)
        print(f"\nResult: {msg}\n")
    else:
        print("\nInstallation cancelled. ClamAV is required to run scans with pyEGClamUI.\n")


if __name__ == "__main__":
    cli_main()