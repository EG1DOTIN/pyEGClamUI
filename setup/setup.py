#!/usr/bin/env python3
"""
================================================================================
pyEGClamUI - Unified Cross-Platform Setup, Update & Deployment Engine
================================================================================
100% Free & Open-Source (FOSS) Python Standard Library Implementation.
Supports Windows, Linux, and macOS.

Usage:
    python setup/setup.py [--install] [--update] [--check] [--shortcuts-only]
                          [--uninstall] [--with-clamav] [--no-clamav]
                          [--verbose] [--start] [--gui]
================================================================================
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ------------------------------------------------------------------------------
# 1. Cross-Platform Terminal Colors & Logging System
# ------------------------------------------------------------------------------
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    @classmethod
    def disable(cls):
        """Disables colors for terminals without ANSI support."""
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE"]:
            setattr(cls, attr, "")


# Enable ANSI escape sequences on Windows 10/11 console
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        Colors.disable()


class SetupLogger:
    """Real-time streaming logger with support for terminal ANSI and GUI callbacks."""

    def __init__(self, verbose: bool = False, callback: Optional[Callable[[str, str], None]] = None):
        self.verbose = verbose
        self.callback = callback

    def _emit(self, tag: str, color: str, message: str, level: str):
        formatted = f"{color}{Colors.BOLD}[{tag}]{Colors.RESET} {message}"
        print(formatted, flush=True)
        if self.callback:
            self.callback(message, level)

    def info(self, message: str):
        self._emit("INFO", Colors.CYAN, message, "info")

    def ok(self, message: str):
        self._emit("SUCCESS", Colors.GREEN, message, "ok")

    def warn(self, message: str):
        self._emit("WARNING", Colors.YELLOW, message, "warn")

    def error(self, message: str):
        self._emit("ERROR", Colors.RED, message, "error")

    def step(self, step_num: int, total_steps: int, title: str):
        header = f"\n{Colors.BLUE}{Colors.BOLD}==> [{step_num}/{total_steps}] {title}{Colors.RESET}"
        print(header, flush=True)
        if self.callback:
            self.callback(f"[{step_num}/{total_steps}] {title}", "step")

    def exec(self, command_str: str):
        if self.verbose:
            self._emit("EXEC", Colors.MAGENTA, command_str, "exec")


# ------------------------------------------------------------------------------
# Centric Cross-Platform Hidden Subprocess Execution
# ------------------------------------------------------------------------------
def get_hidden_subprocess_kwargs() -> Dict[str, Any]:
    """Returns platform kwargs to ensure 100% hidden window execution."""
    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32" and hasattr(subprocess, "STARTUPINFO"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
    return kwargs


def spawn_hidden_process(
    cmd: List[Any],
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.STDOUT,
    text: bool = True,
    bufsize: int = 1,
    cwd: Optional[Union[str, Path]] = None,
    **kwargs: Any,
) -> subprocess.Popen:
    """Spawns an asynchronous streaming background subprocess with guaranteed hidden window."""
    normalized_cmd = [str(arg) for arg in cmd]
    process_kwargs = get_hidden_subprocess_kwargs()
    process_kwargs.update(kwargs)
    if text and "encoding" not in process_kwargs and "errors" not in process_kwargs:
        process_kwargs["encoding"] = "utf-8"
        process_kwargs["errors"] = "replace"
    return subprocess.Popen(
        normalized_cmd,
        stdout=stdout,
        stderr=stderr,
        text=text,
        bufsize=bufsize,
        cwd=str(cwd) if cwd else None,
        **process_kwargs,
    )


def run_hidden_process(
    cmd: List[Any],
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    check: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Executes a command synchronously to completion with guaranteed hidden window."""
    normalized_cmd = [str(arg) for arg in cmd]
    process_kwargs = get_hidden_subprocess_kwargs()
    process_kwargs.update(kwargs)
    if text and "encoding" not in process_kwargs and "errors" not in process_kwargs:
        process_kwargs["encoding"] = "utf-8"
        process_kwargs["errors"] = "replace"
    return subprocess.run(
        normalized_cmd,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        check=check,
        cwd=str(cwd) if cwd else None,
        **process_kwargs,
    )


# ------------------------------------------------------------------------------
# 2. System Architecture & Environment Detector
# ------------------------------------------------------------------------------
class SystemDetector:
    """Audits system capabilities, Python versions, and ClamAV presence."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.os_type = sys.platform  # 'win32', 'linux', 'darwin'
        self.arch = platform.machine()
        self.py_version = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)

    def is_python_supported(self) -> bool:
        """Returns True if Python >= 3.9."""
        return self.py_version >= (3, 9, 0)

    def get_clamscan_path(self) -> Optional[Path]:
        """Resolves absolute path to clamscan executable."""
        found = shutil.which("clamscan")
        if found:
            return Path(found)

        # Standard Windows locations
        if self.os_type == "win32":
            win_candidates = [
                Path("C:/Program Files/ClamAV/clamscan.exe"),
                Path("C:/Program Files (x86)/ClamAV/clamscan.exe"),
                Path(os.environ.get("LOCALAPPDATA", "")) / "ClamAV" / "clamscan.exe",
            ]
            for c in win_candidates:
                if c.is_file():
                    return c
        elif self.os_type == "darwin":
            mac_candidates = [
                Path("/opt/homebrew/bin/clamscan"),
                Path("/usr/local/bin/clamscan"),
            ]
            for c in mac_candidates:
                if c.is_file():
                    return c
        elif self.os_type.startswith("linux"):
            linux_candidates = [
                Path("/usr/bin/clamscan"),
                Path("/usr/local/bin/clamscan"),
            ]
            for c in linux_candidates:
                if c.is_file():
                    return c
        return None

    def get_freshclam_path(self) -> Optional[Path]:
        """Resolves absolute path to freshclam executable."""
        found = shutil.which("freshclam")
        if found:
            return Path(found)
        if self.os_type == "win32":
            p = Path("C:/Program Files/ClamAV/freshclam.exe")
            if p.is_file():
                return p
        return None

    def get_clamd_path(self) -> Optional[Path]:
        """Resolves absolute path to clamd daemon executable."""
        found = shutil.which("clamd")
        if found:
            return Path(found)
        if self.os_type == "win32":
            p = Path("C:/Program Files/ClamAV/clamd.exe")
            if p.is_file():
                return p
        return None

    def is_daemon_running(self, host: str = "127.0.0.1", port: int = 3310) -> bool:
        """Tests TCP socket connection to resident clamd service."""
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def detect_package_manager(self) -> Optional[str]:
        """Detects available OS package manager."""
        for pm in ["winget", "apt", "dnf", "pacman", "brew"]:
            if shutil.which(pm):
                return pm
        return None

    def ensure_linux_prerequisites(self, logger: SetupLogger) -> bool:
        """Verifies and provisions Linux system packages needed for venv, C extensions, and Qt6."""
        if not self.os_type.startswith("linux"):
            return True

        pm = self.detect_package_manager()
        if not pm:
            return True

        can_passwordless = (
            shutil.which("sudo") is not None
            and run_hidden_process(["sudo", "-n", "true"], capture_output=True).returncode == 0
        )

        if pm == "apt":
            dpkg_query = shutil.which("dpkg-query")
            missing_pkgs: list[str] = []

            # Only check for python3-venv if Python cannot already create venvs with pip
            has_venv_ensurepip = False
            try:
                import venv, ensurepip
                has_venv_ensurepip = True
            except ImportError:
                pass

            if not has_venv_ensurepip:
                missing_pkgs.append("python3-venv")

            test_pkgs = [
                "python3-dev",
                "build-essential",
                "libgl1",
                "libegl1",
                "libxkbcommon-x11-0",
                "libdbus-1-3",
                "libxcb-cursor0",
            ]
            if dpkg_query:
                for pkg in test_pkgs:
                    res = run_hidden_process([dpkg_query, "-W", "-f='${Status}'", pkg], capture_output=True)
                    if "install ok installed" not in res.stdout:
                        missing_pkgs.append(pkg)

            if missing_pkgs:
                logger.info(f"Missing Linux system packages for Python/Qt6: {', '.join(missing_pkgs)}")
                if can_passwordless:
                    logger.info("Attempting automated installation of missing system prerequisites (sudo)...")
                    run_hidden_process(["sudo", "apt-get", "update"], capture_output=True)
                    install_cmd = ["sudo", "apt-get", "install", "-y"] + missing_pkgs
                    logger.exec(" ".join(install_cmd))
                    res = run_hidden_process(install_cmd, capture_output=not logger.verbose)
                    if res.returncode == 0:
                        logger.ok("Linux system prerequisites installed successfully.")
                        return True
                    else:
                        logger.warn("Automated installation via sudo failed. If dependencies fail, run:")
                        logger.warn(f"  sudo apt-get install -y {' '.join(missing_pkgs)}")
                elif shutil.which("sudo") and sys.stdin.isatty():
                    logger.info("Attempting interactive installation of missing system prerequisites...")
                    subprocess.run(["sudo", "apt-get", "update"])
                    res = subprocess.run(["sudo", "apt-get", "install", "-y"] + missing_pkgs)
                    if res.returncode == 0:
                        logger.ok("Linux system prerequisites installed successfully.")
                        return True
                else:
                    logger.warn("System packages needed. If dependency installation fails, please install:")
                    logger.warn(f"  sudo apt-get install -y {' '.join(missing_pkgs)}")

        elif pm == "dnf":
            if can_passwordless:
                logger.info("Verifying Fedora/RHEL development and Qt prerequisites...")
                run_hidden_process(
                    ["sudo", "dnf", "install", "-y", "python3-devel", "gcc", "mesa-libGL", "libxkbcommon-x11", "xcb-util-cursor"],
                    capture_output=not logger.verbose,
                )
            else:
                logger.info("Note: On Fedora/RHEL, if Qt6 libraries are needed, run:")
                logger.info("  sudo dnf install -y python3-devel gcc mesa-libGL libxkbcommon-x11 xcb-util-cursor")

        elif pm == "pacman":
            if can_passwordless:
                logger.info("Verifying Arch Linux development and Qt prerequisites...")
                run_hidden_process(
                    ["sudo", "pacman", "-S", "--noconfirm", "--needed", "base-devel", "libxkbcommon-x11", "xcb-util-cursor"],
                    capture_output=not logger.verbose,
                )
            else:
                logger.info("Note: On Arch Linux, if Qt6 libraries are needed, run:")
                logger.info("  sudo pacman -S --noconfirm --needed base-devel libxkbcommon-x11 xcb-util-cursor")

        return True


# ------------------------------------------------------------------------------
# 3. Virtual Environment & Dependency Manager
# ------------------------------------------------------------------------------
class VenvManager:
    """Manages isolated .venv creation, pip upgrades, and package installation."""

    def __init__(self, project_root: Path, logger: SetupLogger, detector: Optional[SystemDetector] = None):
        self.project_root = project_root
        self.logger = logger
        self.detector = detector
        self.venv_dir = project_root / ".venv"

    def get_python_exe(self) -> Path:
        """Resolves python binary path inside .venv."""
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    def get_pythonw_exe(self) -> Path:
        """Resolves windowless pythonw binary path inside .venv (Windows)."""
        if sys.platform == "win32":
            pw = self.venv_dir / "Scripts" / "pythonw.exe"
            if pw.is_file():
                return pw
        return self.get_python_exe()

    def is_cross_platform_corrupted(self) -> bool:
        """Checks if .venv exists but was built on a different operating system."""
        if not self.venv_dir.is_dir():
            return False
        # Windows venv on non-Windows host
        if sys.platform != "win32" and (self.venv_dir / "Scripts").is_dir():
            return True
        # Unix/Linux venv on Windows host
        if sys.platform == "win32" and (self.venv_dir / "bin").is_dir() and not (self.venv_dir / "Scripts").is_dir():
            return True
        # Inspect pyvenv.cfg for foreign OS path patterns
        cfg_file = self.venv_dir / "pyvenv.cfg"
        if cfg_file.is_file():
            try:
                cfg_content = cfg_file.read_text(encoding="utf-8", errors="replace")
                if sys.platform != "win32":
                    if ":\\" in cfg_content or "home = " in cfg_content and "\\" in cfg_content:
                        return True
                else:
                    for line in cfg_content.splitlines():
                        if line.strip().startswith("home = ") and (line.strip().endswith("/bin") or "/usr" in line):
                            return True
            except Exception:
                pass
        return False

    def exists(self) -> bool:
        """Checks if .venv is provisioned and functional."""
        if self.is_cross_platform_corrupted():
            return False
        return self.get_python_exe().is_file()

    def create(self) -> bool:
        """Provisions a fresh .venv in the project root."""
        self.logger.info(f"Creating isolated virtual environment at {self.venv_dir}...")

        # If cross-platform corrupted or non-functional directory exists, wipe it cleanly
        if self.venv_dir.is_dir() and (self.is_cross_platform_corrupted() or not self.exists()):
            self.logger.warn("Cleaning up incompatible or partial virtual environment before recreating...")
            shutil.rmtree(self.venv_dir, ignore_errors=True)

        system_site = sys.platform.startswith("linux")
        try:
            import venv
            builder = venv.EnvBuilder(with_pip=True, clear=True, system_site_packages=system_site)
            builder.create(self.venv_dir)
            self.logger.ok("Virtual environment (.venv) successfully created.")
            return True
        except Exception as e:
            self.logger.warn(f"Standard venv module failed ({e}), falling back to subprocess...")
            cmd = [sys.executable, "-m", "venv"]
            if system_site:
                cmd.append("--system-site-packages")
            cmd.append(str(self.venv_dir))
            self.logger.exec(" ".join(cmd))
            res = run_hidden_process(cmd, capture_output=True)
            if res.returncode == 0:
                self.logger.ok("Virtual environment (.venv) created via subprocess.")
                return True

            # Debian/Ubuntu fallback: If ensurepip failed due to missing python3-venv package
            if sys.platform.startswith("linux"):
                self.logger.warn("Subprocess venv creation failed. Attempting creation without pip...")
                cmd_nopip = [sys.executable, "-m", "venv", "--without-pip"]
                if system_site:
                    cmd_nopip.append("--system-site-packages")
                cmd_nopip.append(str(self.venv_dir))
                res_nopip = run_hidden_process(cmd_nopip, capture_output=True)
                if res_nopip.returncode == 0:
                    self.logger.ok("Virtual environment created (--without-pip). Bootstrapping pip...")
                    py_exe = self.get_python_exe()
                    boot_res = run_hidden_process([str(py_exe), "-m", "ensurepip", "--default-pip"], capture_output=True)
                    if boot_res.returncode == 0:
                        self.logger.ok("Pip bootstrapped successfully.")
                        return True

            self.logger.error(f"Failed to create .venv: {res.stderr}")
            if sys.platform.startswith("linux"):
                self.logger.error("On Debian/Ubuntu systems, install the venv package using:")
                self.logger.error("  sudo apt-get install -y python3-venv python3-pip")
            return False

    def _is_32bit_architecture(self) -> bool:
        """Determines if the running platform or Python runtime is 32-bit."""
        mach = platform.machine().lower()
        return (
            mach in ("i386", "i686", "i486", "i586", "x86", "armv7l", "armv6l")
            or (sys.maxsize <= 2**32 and sys.platform != "win32")
        )

    def _verify_pyside6_runtime(self, py_exe: Path) -> bool:
        """Verifies PySide6 Qt GUI availability and displays appropriate platform advice."""
        check_cmd = [str(py_exe), "-c", "import PySide6; from PySide6 import QtWidgets, QtCore; print('OK')"]
        res = run_hidden_process(check_cmd, capture_output=True)
        if res.returncode == 0:
            self.logger.ok("PySide6 Qt GUI runtime verified successfully.")
            return True

        err_output = res.stderr.strip()
        is_32bit = self._is_32bit_architecture()

        if "No module named 'PySide6'" in err_output or "ModuleNotFoundError" in err_output:
            if is_32bit:
                self.logger.warn(f"32-bit architecture ({platform.machine()}) detected.")
                self.logger.info("PySide6 (Qt6 GUI) is 64-bit only and not available for 32-bit Linux.")
            else:
                self.logger.warn("PySide6 GUI framework is not installed in the environment.")
                pip_hint = ".venv\\Scripts\\pip install 'PySide6>=6.2.0'" if sys.platform == "win32" else ".venv/bin/pip install 'PySide6>=6.2.0'"
                self.logger.info("To install GUI support on 64-bit systems, run:")
                self.logger.info(f"  {pip_hint}")

            self.logger.ok("pyEGClamUI Core Antivirus CLI tools installed and ready:")
            self.logger.ok("  pyegclamui-scan --quick        (Fast ClamAV Scan)")
            self.logger.ok("  pyegclamui-scan --full         (Comprehensive Scan)")
            self.logger.ok("  pyegclamui-scan --path <dir>   (Scan Custom Directory)")
            self.logger.ok("  pyegclamui-setup               (ClamAV Engine Setup)")
            return True

        self.logger.warn("PySide6 package is installed, but Qt GUI shared libraries are missing on this system.")
        if err_output:
            self.logger.warn(f"Diagnostic error: {err_output}")
        if sys.platform.startswith("linux"):
            self.logger.warn("Linux systems require X11/GL system libraries for Qt6. Run:")
            self.logger.warn("  sudo apt-get install -y libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 libxcb-cursor0")
        return True

    def install_dependencies(self) -> bool:
        """Installs or upgrades pyEGClamUI dependencies into .venv."""
        py_exe = self.get_python_exe()
        if not py_exe.is_file():
            self.logger.error("Virtual environment Python binary not found. Cannot install dependencies.")
            return False

        is_32bit = self._is_32bit_architecture()
        if is_32bit:
            self.logger.info(f"System architecture: {platform.machine()} (32-bit). Configuring core antivirus modules...")

        # 1. Upgrade pip, setuptools, wheel
        self.logger.info("Upgrading core build utilities (pip, setuptools, wheel)...")
        upgrade_cmd = [
            str(py_exe),
            "-m",
            "pip",
            "install",
            "--prefer-binary",
            "--default-timeout=120",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ]
        self.logger.exec(" ".join(upgrade_cmd))
        up_res = run_hidden_process(upgrade_cmd, capture_output=True)
        if up_res.returncode != 0:
            self.logger.warn(f"Notice during build utilities upgrade: {up_res.stderr.strip()}")

        # 2. Install project in editable development mode
        self.logger.info("Installing pyEGClamUI and dependencies into .venv...")
        install_cmd = [
            str(py_exe),
            "-m",
            "pip",
            "install",
            "--prefer-binary",
            "--default-timeout=120",
            "-e",
            str(self.project_root),
        ]
        self.logger.exec(" ".join(install_cmd))

        captured_output: list[str] = []
        process = spawn_hidden_process(
            install_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            cwd=str(self.project_root),
        )

        for line in iter(process.stdout.readline, ""):
            line_str = line.strip()
            if line_str:
                captured_output.append(line_str)
                if self.logger.verbose:
                    print(f"  {Colors.DIM}{line_str}{Colors.RESET}", flush=True)

        process.wait()
        if process.returncode == 0:
            self.logger.ok("pyEGClamUI packages and dependencies installed successfully.")
            return self._verify_pyside6_runtime(py_exe)

        # Installation failed - display buffered error lines to user
        self.logger.error("Failed to install dependencies via 'pip install -e .'")
        print(f"\n{Colors.RED}--- pip installation error output ---{Colors.RESET}")
        for err_line in captured_output[-25:]:
            print(f"  {Colors.YELLOW}{err_line}{Colors.RESET}")
        print(f"{Colors.RED}-------------------------------------{Colors.RESET}\n")

        # Fallback 1: Try editable installation without build isolation (utilizes local venv build tools)
        self.logger.info("Retrying editable installation with local build tools (--no-build-isolation)...")
        nobuild_cmd = [
            str(py_exe),
            "-m",
            "pip",
            "install",
            "--no-build-isolation",
            "--prefer-binary",
            "--default-timeout=120",
            "-e",
            str(self.project_root),
        ]
        self.logger.exec(" ".join(nobuild_cmd))
        nobuild_res = run_hidden_process(nobuild_cmd, capture_output=True)
        if nobuild_res.returncode == 0:
            self.logger.ok("pyEGClamUI installed successfully via local build tools.")
            return self._verify_pyside6_runtime(py_exe)

        # Fallback 2: Try installing dependencies from requirements.txt directly
        req_file = self.project_root / "requirements.txt"
        if req_file.is_file():
            self.logger.info("Retrying dependency installation via requirements.txt fallback...")
            req_cmd = [
                str(py_exe),
                "-m",
                "pip",
                "install",
                "--prefer-binary",
                "--default-timeout=120",
                "-r",
                str(req_file),
            ]
            self.logger.exec(" ".join(req_cmd))
            req_res = run_hidden_process(req_cmd, capture_output=True)
            if req_res.returncode == 0:
                nodeps_cmd = [
                    str(py_exe),
                    "-m",
                    "pip",
                    "install",
                    "--no-build-isolation",
                    "--no-deps",
                    "-e",
                    str(self.project_root),
                ]
                res_nodeps = run_hidden_process(nodeps_cmd, capture_output=True)
                if res_nodeps.returncode == 0:
                    self.logger.ok("pyEGClamUI installed successfully via requirements.txt fallback.")
                    return self._verify_pyside6_runtime(py_exe)

        # Fallback 3: Direct core installation (clamd, psutil, watchdog, send2trash) + package install
        self.logger.info("Retrying with core antivirus dependencies...")
        core_pkgs = ["clamd>=1.0.2", "psutil>=5.9.0", "watchdog>=3.0.0", "send2trash>=1.8.0"]
        if sys.platform == "win32":
            core_pkgs.append("pywin32>=305")

        core_cmd = [
            str(py_exe),
            "-m",
            "pip",
            "install",
            "--prefer-binary",
            "--default-timeout=120",
        ] + core_pkgs
        self.logger.exec(" ".join(core_cmd))
        core_res = run_hidden_process(core_cmd, capture_output=True)
        if core_res.returncode == 0:
            if not is_32bit:
                # Try lightweight PySide6-Essentials on 64-bit systems
                pyside_cmd = [
                    str(py_exe),
                    "-m",
                    "pip",
                    "install",
                    "--prefer-binary",
                    "--default-timeout=120",
                    "PySide6-Essentials>=6.2.0",
                ]
                run_hidden_process(pyside_cmd, capture_output=True)

            nodeps_cmd = [
                str(py_exe),
                "-m",
                "pip",
                "install",
                "--no-build-isolation",
                "--no-deps",
                "-e",
                str(self.project_root),
            ]
            self.logger.exec(" ".join(nodeps_cmd))
            nodeps_res = run_hidden_process(nodeps_cmd, capture_output=True)
            if nodeps_res.returncode == 0:
                self.logger.ok("pyEGClamUI core engine installed successfully via core fallback.")
                return self._verify_pyside6_runtime(py_exe)

        # Linux-specific diagnostic advice
        if sys.platform.startswith("linux"):
            arch = platform.machine().lower()
            if is_32bit:
                self.logger.warn(f"Note: Architecture is {arch} (32-bit). PySide6 is not supported on 32-bit Linux.")
                self.logger.info("pyEGClamUI CLI scanner and daemon are operational:")
                self.logger.info("  pyegclamui-scan --quick / --full / --path <dir>")
            elif arch in ("aarch64", "arm64"):
                self.logger.warn(f"Note: Architecture is {arch}. Official PyPI wheels for PySide6 may be unavailable.")
                self.logger.info("On Debian/Ubuntu ARM, install PySide6 via system packages:")
                self.logger.info("  sudo apt-get install -y python3-pyside6")
            else:
                self.logger.info("If PySide6 failed on Debian/Ubuntu, verify system packages:")
                self.logger.info("  sudo apt-get install -y python3-venv python3-pip python3-dev build-essential libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 libxcb-cursor0")

        return False


# ------------------------------------------------------------------------------
# 4. ClamAV Engine Provisioner & Daemon Automator
# ------------------------------------------------------------------------------
class ClamAVProvisioner:
    """Installs ClamAV, initializes signatures, and configures clamd background daemon."""

    def __init__(self, detector: SystemDetector, logger: SetupLogger):
        self.detector = detector
        self.logger = logger

    def install_engine(self) -> bool:
        """Executes native OS installation of ClamAV engine."""
        if self.detector.get_clamscan_path():
            self.logger.ok(f"ClamAV engine already installed at: {self.detector.get_clamscan_path()}")
            return True

        self.logger.info(f"ClamAV not found. Initiating installation for {self.detector.os_type}...")

        if self.detector.os_type == "win32":
            if shutil.which("winget"):
                self.logger.info("Installing ClamAV via Windows Package Manager (winget)...")
                cmd = ["winget", "install", "--id", "Cisco.ClamAV", "-e", "--accept-source-agreements", "--accept-package-agreements", "--silent"]
                self.logger.exec(" ".join(cmd))
                res = run_hidden_process(cmd)
                if not (res.returncode == 0 or self.detector.get_clamscan_path()):
                    cmd_alt = ["winget", "install", "ClamAV.ClamAV", "--accept-source-agreements", "--accept-package-agreements", "--silent"]
                    run_hidden_process(cmd_alt)
                if self.detector.get_clamscan_path():
                    self.logger.ok("ClamAV installed successfully via winget.")
                    self.configure_windows_daemon()
                    return True
                self.logger.warn("Winget returned non-zero. Verifying manual installation...")
            else:
                self.logger.warn("winget not available on this Windows system.")
                self.logger.info("Please install ClamAV manually from: https://www.clamav.net/downloads")
                return False

        elif self.detector.os_type.startswith("linux"):
            pm = self.detector.detect_package_manager()
            can_passwordless = (
                shutil.which("sudo") is not None
                and run_hidden_process(["sudo", "-n", "true"], capture_output=True).returncode == 0
            )
            if pm == "apt":
                self.logger.info("Installing ClamAV on Debian/Ubuntu...")
                if can_passwordless:
                    run_hidden_process(["sudo", "apt-get", "update"], capture_output=True)
                    run_hidden_process(["sudo", "apt-get", "install", "-y", "clamav", "clamav-daemon"], capture_output=not self.logger.verbose)
                elif sys.stdin.isatty() and shutil.which("sudo"):
                    subprocess.run(["sudo", "apt-get", "update"])
                    subprocess.run(["sudo", "apt-get", "install", "-y", "clamav", "clamav-daemon"])
                else:
                    self.logger.warn("Sudo privileges needed to install ClamAV. Run:")
                    self.logger.warn("  sudo apt-get update && sudo apt-get install -y clamav clamav-daemon")
            elif pm == "dnf":
                self.logger.info("Installing ClamAV on Fedora/RHEL...")
                if can_passwordless:
                    run_hidden_process(["sudo", "dnf", "install", "-y", "clamav", "clamd", "clamav-update"], capture_output=not self.logger.verbose)
                elif sys.stdin.isatty() and shutil.which("sudo"):
                    subprocess.run(["sudo", "dnf", "install", "-y", "clamav", "clamd", "clamav-update"])
                else:
                    self.logger.warn("Sudo privileges needed to install ClamAV. Run:")
                    self.logger.warn("  sudo dnf install -y clamav clamd clamav-update")
            elif pm == "pacman":
                self.logger.info("Installing ClamAV on Arch Linux...")
                if can_passwordless:
                    run_hidden_process(["sudo", "pacman", "-S", "--noconfirm", "clamav"], capture_output=not self.logger.verbose)
                elif sys.stdin.isatty() and shutil.which("sudo"):
                    subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "clamav"])
                else:
                    self.logger.warn("Sudo privileges needed to install ClamAV. Run:")
                    self.logger.warn("  sudo pacman -S --noconfirm clamav")

        elif self.detector.os_type == "darwin":
            if shutil.which("brew"):
                self.logger.info("Installing ClamAV via Homebrew...")
                run_hidden_process(["brew", "install", "clamav"])
            else:
                self.logger.warn("Homebrew not found. Please install Homebrew or ClamAV manually.")

        return bool(self.detector.get_clamscan_path())

    def configure_daemon_service(self):
        """Prepares daemon configurations and activates background service across platforms."""
        if self.detector.is_daemon_running():
            self.logger.ok("ClamAV daemon is already active and listening on port 3310.")
            return

        if self.detector.os_type == "win32":
            self.configure_windows_daemon()
        elif self.detector.os_type.startswith("linux"):
            self.logger.info("Activating clamav-daemon service on Linux...")
            try:
                can_passwordless = (
                    shutil.which("sudo") is not None
                    and run_hidden_process(["sudo", "-n", "true"], capture_output=True).returncode == 0
                )
                if can_passwordless:
                    res = run_hidden_process(["sudo", "systemctl", "enable", "--now", "clamav-daemon"], capture_output=True)
                elif sys.stdin.isatty() and shutil.which("sudo"):
                    res = subprocess.run(["sudo", "systemctl", "enable", "--now", "clamav-daemon"])
                else:
                    res = None
                if (res and res.returncode == 0) or self.detector.is_daemon_running():
                    self.logger.ok("clamav-daemon service activated.")
                else:
                    self.logger.warn("Could not automatically activate clamav-daemon service. Scanner will use standard clamscan fallback.")
            except Exception as e:
                self.logger.warn(f"Notice on activating clamav-daemon: {e}. Scanner will use standard clamscan fallback.")
        elif self.detector.os_type == "darwin":
            if shutil.which("brew"):
                self.logger.info("Starting ClamAV background service via Homebrew...")
                try:
                    run_hidden_process(["brew", "services", "start", "clamav"])
                    if self.detector.is_daemon_running():
                        self.logger.ok("ClamAV daemon service activated via Homebrew.")
                except Exception as e:
                    self.logger.warn(f"Could not start brew service: {e}. Scanner will use standard clamscan fallback.")

    def remove_daemon_service(self):
        """Stops and unregisters the ClamAV daemon background service across platforms."""
        if self.detector.os_type == "win32":
            self.logger.info("Stopping and unregistering 'clamd' Windows Service...")
            clamav_dir = Path("C:/Program Files/ClamAV")
            clamd_exe = clamav_dir / "clamd.exe"
            try:
                run_hidden_process(
                    ["powershell", "-NoProfile", "-Command", "Stop-Service -Name 'clamd' -Force -ErrorAction SilentlyContinue"],
                    capture_output=True,
                )
            except Exception:
                pass

            removed = False
            if clamd_exe.is_file():
                try:
                    res = run_hidden_process([str(clamd_exe), "--uninstall-service"], capture_output=True)
                    if res.returncode == 0:
                        removed = True
                except Exception:
                    pass

            if not removed:
                try:
                    res = run_hidden_process(["sc.exe", "delete", "clamd"], capture_output=True)
                    if res.returncode == 0:
                        removed = True
                except Exception:
                    pass

            if removed or not self.detector.is_daemon_running():
                self.logger.ok("ClamAV daemon Windows Service removed.")
            else:
                self.logger.warn("Administrator privileges required to unregister service. Run 'sc.exe delete clamd' as Admin.")

        elif self.detector.os_type.startswith("linux"):
            self.logger.info("Stopping and disabling clamav-daemon service on Linux...")
            try:
                can_passwordless = (
                    shutil.which("sudo") is not None
                    and run_hidden_process(["sudo", "-n", "true"], capture_output=True).returncode == 0
                )
                if can_passwordless:
                    res = run_hidden_process(["sudo", "systemctl", "disable", "--now", "clamav-daemon"], capture_output=True)
                elif sys.stdin.isatty() and shutil.which("sudo"):
                    res = subprocess.run(["sudo", "systemctl", "disable", "--now", "clamav-daemon"])
                else:
                    res = None
                if res and res.returncode == 0:
                    self.logger.ok("clamav-daemon service disabled and stopped.")
                else:
                    self.logger.warn("Could not disable clamav-daemon. Run manually: sudo systemctl disable --now clamav-daemon")
            except Exception as e:
                self.logger.warn(f"Could not disable clamav-daemon: {e}")

        elif self.detector.os_type == "darwin":
            if shutil.which("brew"):
                self.logger.info("Stopping ClamAV service via Homebrew...")
                try:
                    run_hidden_process(["brew", "services", "stop", "clamav"])
                    self.logger.ok("ClamAV background service stopped via Homebrew.")
                except Exception as e:
                    self.logger.warn(f"Failed to stop brew service: {e}")

    def configure_windows_daemon(self):
        """Prepares clamd.conf, freshclam.conf, and starts Windows Service on TCP 3310."""
        clamav_dir = Path("C:/Program Files/ClamAV")
        if not clamav_dir.is_dir():
            return

        if self.detector.is_daemon_running():
            self.logger.ok("ClamAV daemon is already running on TCP 3310.")
            return

        # Check if helper script is available
        setup_dir = Path(__file__).resolve().parent
        candidate_scripts = [
            setup_dir / "windows" / "setup_clamd_service.ps1",
            setup_dir / "setup_clamd_service.ps1",
        ]
        service_script = next((s for s in candidate_scripts if s.is_file()), candidate_scripts[0])
        if service_script.is_file():
            self.logger.info("Configuring ClamAV resident service (UAC prompt will appear to authorize service registration)...")
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(service_script)]
            run_hidden_process(cmd)
            # Recheck with polling after script completes
            for _ in range(6):
                time.sleep(1)
                if self.detector.is_daemon_running():
                    self.logger.ok("ClamAV daemon successfully activated on TCP 3310!")
                    return

        self.logger.info("Attempting direct configuration in Program Files...")
        clamd_conf = clamav_dir / "clamd.conf"
        sample_clamd = clamav_dir / "conf_examples" / "clamd.conf.sample"
        if not clamd_conf.is_file() and sample_clamd.is_file():
            try:
                content = sample_clamd.read_text(encoding="utf-8", errors="replace")
                lines = []
                for line in content.splitlines():
                    if line.strip().lower() == "example":
                        lines.append("# Example")
                    else:
                        lines.append(line)
                lines.append("\n# Added by pyEGClamUI")
                lines.append("TCPSocket 3310")
                lines.append("TCPAddr 127.0.0.1")
                user_db = Path.home() / "AppData" / "Local" / "pyEGClamUI" / "database"
                if user_db.is_dir():
                    lines.append(f'DatabaseDirectory "{user_db.as_posix()}"')
                clamd_conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.logger.ok("Generated clamd.conf with TCPSocket 3310 enabled.")
            except Exception as e:
                self.logger.warn(f"Administrator privileges needed to write clamd.conf: {e}")

        fc_conf = clamav_dir / "freshclam.conf"
        sample_fc = clamav_dir / "conf_examples" / "freshclam.conf.sample"
        if not fc_conf.is_file() and sample_fc.is_file():
            try:
                content = sample_fc.read_text(encoding="utf-8", errors="replace")
                lines = [l if l.strip().lower() != "example" else "# Example" for l in content.splitlines()]
                fc_conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.logger.ok("Generated freshclam.conf.")
            except Exception as e:
                self.logger.warn(f"Administrator privileges needed to write freshclam.conf: {e}")

        clamd_exe = clamav_dir / "clamd.exe"
        if clamd_exe.is_file():
            self.logger.info("Installing and starting 'clamd' background Windows Service...")
            run_hidden_process([str(clamd_exe), "--install-service"], capture_output=True)
            run_hidden_process(["powershell", "-Command", "Start-Service -Name 'clamd' -ErrorAction SilentlyContinue"], capture_output=True)

    def update_signatures(self) -> bool:
        """Executes freshclam to download latest virus definitions."""
        fc_path = self.detector.get_freshclam_path()
        if not fc_path:
            self.logger.warn("freshclam executable not found. Skipping signature update.")
            return False

        self.logger.info("Updating virus signatures via freshclam (this may take a moment)...")
        cmd = [str(fc_path)]
        self.logger.exec(" ".join(cmd))
        res = run_hidden_process(cmd, capture_output=not self.logger.verbose)
        if res.returncode == 0:
            self.logger.ok("Virus definitions successfully updated.")
            return True
        else:
            self.logger.info("freshclam completed (database up to date or service locked).")
            return True


# ------------------------------------------------------------------------------
# 5. Desktop Shortcuts & OS Application Menu Manager
# ------------------------------------------------------------------------------
class ShortcutManager:
    """Creates crisp Desktop and Start Menu shortcuts pointing to .venv without terminal popups."""

    def __init__(self, project_root: Path, venv_mgr: VenvManager, logger: SetupLogger):
        self.project_root = project_root
        self.venv_mgr = venv_mgr
        self.logger = logger
        self.icon_ico = project_root / "src" / "pyegclamui" / "assets" / "egav.ico"
        self.icon_png = project_root / "src" / "pyegclamui" / "assets" / "egav.png"

    def create_shortcuts(self) -> bool:
        """Creates desktop and system application menu shortcuts."""
        self.logger.info("Creating user desktop and application shortcuts...")
        if sys.platform == "win32":
            return self._create_windows_shortcuts()
        elif sys.platform.startswith("linux"):
            return self._create_linux_shortcuts()
        elif sys.platform == "darwin":
            return self._create_macos_shortcuts()
        return False

    def remove_shortcuts(self) -> bool:
        """Removes application shortcuts across Windows, Linux, and macOS."""
        self.logger.info("Removing pyEGClamUI shortcuts...")
        removed_any = False
        if sys.platform == "win32":
            desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "pyEGClamUI.lnk"
            start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "pyEGClamUI.lnk"
            for s in [desktop, start_menu]:
                if s.is_file():
                    try:
                        s.unlink()
                        self.logger.ok(f"Removed shortcut: {s}")
                        removed_any = True
                    except Exception as e:
                        self.logger.warn(f"Failed to remove {s}: {e}")
            return True
        elif sys.platform.startswith("linux"):
            targets = [
                Path.home() / ".local" / "share" / "applications" / "pyegclamui.desktop",
                Path.home() / "Desktop" / "pyegclamui.desktop",
                Path.home() / ".local" / "share" / "icons" / "hicolor" / "128x128" / "apps" / "pyegclamui.png"
            ]
            cli_names = [
                "pyegclamui",
                "egclam",
                "pyclamui",
                "pyegclamui-lite",
                "pyclamui-lite",
                "pyegclamui-scan",
                "pyegclamui-setup",
            ]
            for b_dir in [Path.home() / ".local" / "bin", Path("/usr/local/bin")]:
                for cmd_name in cli_names:
                    targets.append(b_dir / cmd_name)

            for s in targets:
                if s.is_file():
                    try:
                        s.unlink()
                        self.logger.ok(f"Removed Linux entry: {s}")
                        removed_any = True
                    except Exception as e:
                        self.logger.warn(f"Failed to remove {s}: {e}")
            return True

        elif sys.platform == "darwin":
            targets = [
                Path.home() / "Desktop" / "pyEGClamUI.command",
                Path.home() / "Applications" / "pyEGClamUI.command"
            ]
            for s in targets:
                if s.is_file():
                    try:
                        s.unlink()
                        self.logger.ok(f"Removed macOS launcher: {s}")
                        removed_any = True
                    except Exception as e:
                        self.logger.warn(f"Failed to remove {s}: {e}")
            return True
        return False

    def _create_windows_shortcuts(self) -> bool:
        """Creates Windows .lnk shortcuts on Desktop & Start Menu using pythonw.exe."""
        pythonw_exe = self.venv_mgr.get_pythonw_exe()
        if not pythonw_exe.is_file():
            self.logger.error("pythonw.exe not found in .venv. Cannot generate Windows shortcuts.")
            return False

        user_profile = os.environ.get("USERPROFILE", str(Path.home()))
        app_data = os.environ.get("APPDATA", str(Path(user_profile) / "AppData" / "Roaming"))

        desktop_dir = Path(user_profile) / "Desktop"
        start_menu_dir = Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

        desktop_dir.mkdir(parents=True, exist_ok=True)
        start_menu_dir.mkdir(parents=True, exist_ok=True)

        targets = [
            desktop_dir / "pyEGClamUI.lnk",
            start_menu_dir / "pyEGClamUI.lnk"
        ]

        # Use PowerShell COM WScript.Shell to create standard Windows .lnk files
        ps_script = f"""
        $WshShell = New-Object -comObject WScript.Shell
        $Targets = @('{str(targets[0])}', '{str(targets[1])}')
        foreach ($TargetPath in $Targets) {{
            $Shortcut = $WshShell.CreateShortcut($TargetPath)
            $Shortcut.TargetPath = '{str(pythonw_exe)}'
            $Shortcut.Arguments = '-m pyegclamui'
            $Shortcut.WorkingDirectory = '{str(self.project_root)}'
            $Shortcut.IconLocation = '{str(self.icon_ico)},0'
            $Shortcut.Description = 'pyEGClamUI - ClamAV Antivirus Desktop Interface'
            $Shortcut.Save()
        }}
        """

        try:
            run_hidden_process(["powershell", "-Command", ps_script], check=True, capture_output=True)
            self.logger.ok(f"Desktop shortcut created: {targets[0]}")
            self.logger.ok(f"Start Menu entry created: {targets[1]}")
            return True
        except Exception as e:
            self.logger.warn(f"Failed to create Windows shortcuts via PowerShell: {e}")
            return False

    def _create_linux_shortcuts(self) -> bool:
        """Installs XDG .desktop launcher and hicolor app icon."""
        python_exe = self.venv_mgr.get_python_exe()
        apps_dir = Path.home() / ".local" / "share" / "applications"
        icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "128x128" / "apps"

        apps_dir.mkdir(parents=True, exist_ok=True)
        icons_dir.mkdir(parents=True, exist_ok=True)

        target_icon = icons_dir / "pyegclamui.png"
        if self.icon_png.is_file():
            shutil.copyfile(self.icon_png, target_icon)

        desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=pyEGClamUI
GenericName=Antivirus Interface
Comment=Open-source desktop graphical interface for ClamAV
Exec="{python_exe}" -m pyegclamui %F
Icon={target_icon}
Terminal=false
StartupNotify=true
Categories=Utility;System;Security;
Path={self.project_root}
Actions=QuickScan;

[Desktop Action QuickScan]
Name=Run Quick Scan
Exec="{python_exe}" -m pyegclamui.core.scanner --quick
"""
        target_desktop = apps_dir / "pyegclamui.desktop"
        target_desktop.write_text(desktop_content, encoding="utf-8")
        target_desktop.chmod(0o755)
        self.logger.ok(f"Linux application menu entry installed: {target_desktop}")

        # If user has a Desktop directory, create desktop shortcut too
        desktop_dir = Path.home() / "Desktop"
        if desktop_dir.is_dir():
            user_desktop_link = desktop_dir / "pyegclamui.desktop"
            try:
                user_desktop_link.write_text(desktop_content, encoding="utf-8")
                user_desktop_link.chmod(0o755)
                self.logger.ok(f"Linux desktop shortcut installed: {user_desktop_link}")
            except Exception as e:
                self.logger.warn(f"Notice on creating user desktop shortcut: {e}")

        # Install terminal CLI command wrappers (e.g. pyegclamui, egclam, pyclamui, pyegclamui-lite)
        commands_map = {
            "pyegclamui": f'exec "{python_exe}" -m pyegclamui "$@"',
            "egclam": f'exec "{python_exe}" -m pyegclamui "$@"',
            "pyclamui": f'exec "{python_exe}" -m pyegclamui "$@"',
            "pyegclamui-lite": f'exec "{python_exe}" -m pyegclamui.gui.tk_app "$@"',
            "pyclamui-lite": f'exec "{python_exe}" -m pyegclamui.gui.tk_app "$@"',
            "pyegclamui-scan": f'exec "{python_exe}" -m pyegclamui.core.scanner "$@"',
            "pyegclamui-setup": f'exec "{python_exe}" -m pyegclamui.core.setup_engine "$@"',
        }

        user_bin_dir = Path.home() / ".local" / "bin"
        target_bin_dirs = [user_bin_dir]
        usr_local_bin = Path("/usr/local/bin")
        if os.access(usr_local_bin, os.W_OK):
            target_bin_dirs.append(usr_local_bin)

        for b_dir in target_bin_dirs:
            try:
                b_dir.mkdir(parents=True, exist_ok=True)
                for cmd_name, cmd_exec in commands_map.items():
                    wrapper = b_dir / cmd_name
                    wrapper.write_text(f"#!/usr/bin/env bash\n{cmd_exec}\n", encoding="utf-8")
                    wrapper.chmod(0o755)
                self.logger.ok(f"Linux terminal CLI wrappers installed: {b_dir}")
            except Exception as e:
                self.logger.warn(f"Notice on installing CLI wrappers in {b_dir}: {e}")

        return True


    def _create_macos_shortcuts(self) -> bool:
        """Creates macOS desktop launch command script."""
        python_exe = self.venv_mgr.get_python_exe()
        desktop_dir = Path.home() / "Desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop = desktop_dir / "pyEGClamUI.command"
        content = f"""#!/bin/bash
cd "{self.project_root}"
"{python_exe}" -m pyegclamui
"""
        desktop.write_text(content, encoding="utf-8")
        desktop.chmod(0o755)
        self.logger.ok(f"macOS desktop launcher created: {desktop}")

        apps_dir = Path.home() / "Applications"
        if apps_dir.is_dir():
            app_launcher = apps_dir / "pyEGClamUI.command"
            try:
                app_launcher.write_text(content, encoding="utf-8")
                app_launcher.chmod(0o755)
                self.logger.ok(f"macOS Applications launcher created: {app_launcher}")
            except Exception:
                pass

        return True


# ------------------------------------------------------------------------------
# 6. Global Maintenance & Updater (--update)
# ------------------------------------------------------------------------------
class GlobalUpdater:
    """Synchronously refreshes ClamAV database, engine binary, and pyEGClamUI repo."""

    def __init__(self, project_root: Path, venv_mgr: VenvManager, clam_prov: ClamAVProvisioner, logger: SetupLogger):
        self.project_root = project_root
        self.venv_mgr = venv_mgr
        self.clam_prov = clam_prov
        self.logger = logger

    def execute_update(self) -> bool:
        """Runs full stack update."""
        self.logger.info("Executing Global Maintenance & Update...")

        # 1. Update Git repository if applicable
        if (self.project_root / ".git").is_dir() and shutil.which("git"):
            self.logger.info("Checking for pyEGClamUI updates from git remote repository...")
            res = run_hidden_process(["git", "pull", "--ff-only"], cwd=str(self.project_root), capture_output=True)
            if res.returncode == 0:
                self.logger.ok(f"Git pull: {res.stdout.strip()}")
            else:
                self.logger.warn(f"Git pull notice: {res.stderr.strip()}")

        # 2. Refresh Python dependencies
        self.logger.info("Refreshing dependencies in virtual environment...")
        self.venv_mgr.install_dependencies()

        # 3. Update ClamAV virus signatures
        self.logger.info("Updating ClamAV virus signature databases...")
        self.clam_prov.update_signatures()

        # 4. Check for ClamAV engine binary upgrades
        if sys.platform == "win32" and shutil.which("winget"):
            self.logger.info("Checking for ClamAV engine binary upgrades via winget...")
            run_hidden_process(["winget", "upgrade", "ClamAV.ClamAV", "--silent"], capture_output=True)

        self.logger.ok("Global update sequence completed successfully.")
        return True


# ------------------------------------------------------------------------------
# 7. Pre-Flight Health Diagnostic Audit (--check)
# ------------------------------------------------------------------------------
def run_diagnostic_check(detector: SystemDetector, venv_mgr: VenvManager, logger: SetupLogger):
    """Outputs a formatted system compatibility report."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}======================================================{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}   pyEGClamUI System Diagnostic & Compatibility Audit  {Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}======================================================{Colors.RESET}\n")

    # Python Check
    py_ok = detector.is_python_supported()
    py_status = f"{Colors.GREEN}Supported (Python {sys.version.split()[0]}){Colors.RESET}" if py_ok else f"{Colors.RED}Unsupported (Python >= 3.9 required){Colors.RESET}"
    print(f" * Operating System:    {platform.system()} {platform.release()} ({detector.arch})")
    print(f" * Python Version:      {py_status}")

    # Hardware Capability & Deterministic GUI Qualification
    try:
        from pyegclamui.core.system_capability import get_system_specs
        specs = get_system_specs()
        gui_tier_str = f"{Colors.GREEN}{specs['gui_name']}{Colors.RESET}"
        ram_str = f"{specs['ram_gb']} GB ({'64-bit' if specs['is_64bit'] else '32-bit'})"
    except Exception:
        is_64 = sys.maxsize > 2**32
        gui_tier_str = f"{Colors.GREEN}Modern Qt6 Suite{Colors.RESET}" if is_64 else f"{Colors.GREEN}pyEGClamUI Lite (Tkinter){Colors.RESET}"
        ram_str = "Auto-detected"
    print(f" * Memory & Arch:       {ram_str}")
    print(f" * Qualified GUI Tier:  {gui_tier_str}")

    # Virtual Environment Check
    venv_ok = venv_mgr.exists()
    if venv_mgr.is_cross_platform_corrupted():
        venv_status = f"{Colors.RED}Corrupted (Built for different OS - run setup to repair){Colors.RESET}"
    else:
        venv_status = f"{Colors.GREEN}Active ({venv_mgr.venv_dir}){Colors.RESET}" if venv_ok else f"{Colors.YELLOW}Not Created{Colors.RESET}"
    print(f" * Local .venv Status:  {venv_status}")

    # Linux-specific prerequisites audit
    if detector.os_type.startswith("linux"):
        has_venv = True
        try:
            import venv, ensurepip
        except ImportError:
            has_venv = False
        if not has_venv:
            print(f" * Linux System Venv:  {Colors.RED}Missing python3-venv package (sudo apt install python3-venv){Colors.RESET}")

    # ClamAV Binaries Check
    clamscan = detector.get_clamscan_path()
    clam_status = f"{Colors.GREEN}Found ({clamscan}){Colors.RESET}" if clamscan else f"{Colors.RED}Not Installed{Colors.RESET}"
    print(f" * ClamAV Scanner:      {clam_status}")

    freshclam = detector.get_freshclam_path()
    fc_status = f"{Colors.GREEN}Found ({freshclam}){Colors.RESET}" if freshclam else f"{Colors.YELLOW}Not Found{Colors.RESET}"
    print(f" * FreshClam Updater:   {fc_status}")

    daemon_running = detector.is_daemon_running()
    daemon_status = f"{Colors.GREEN}Active & Responding (TCP 3310 - Sub-20ms Scan){Colors.RESET}" if daemon_running else f"{Colors.YELLOW}Offline / Service Inactive{Colors.RESET}"
    print(f" * clamd Daemon:        {daemon_status}")

    print(f"\n{Colors.CYAN}------------------------------------------------------{Colors.RESET}")
    if py_ok and venv_ok and clamscan:
        print(f"{Colors.GREEN}{Colors.BOLD}STATUS: ALL SYSTEMS READY FOR EXECUTION{Colors.RESET}\n")
    else:
        print(f"{Colors.YELLOW}{Colors.BOLD}STATUS: SETUP REQUIRED - RUN 'python setup/setup.py --install'{Colors.RESET}\n")


# ------------------------------------------------------------------------------
# 8. Uninstaller Helpers & Routine (--uninstall)
# ------------------------------------------------------------------------------
def clean_autostart(logger: SetupLogger) -> bool:
    """Removes operating system login auto-launch entries across Windows, Linux, and macOS."""
    cleaned = False
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, "pyEGClamUI")
                logger.ok("Removed Windows startup registry entry.")
                cleaned = True
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.warn(f"Notice on cleaning startup registry: {e}")
    elif sys.platform.startswith("linux"):
        base = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        auto_file = Path(base) / "autostart" / "pyegclamui.desktop"
        if auto_file.is_file():
            try:
                auto_file.unlink()
                logger.ok(f"Removed Linux autostart entry: {auto_file}")
                cleaned = True
            except Exception as e:
                logger.warn(f"Notice on cleaning autostart: {e}")
    elif sys.platform == "darwin":
        plist_file = Path.home() / "Library" / "LaunchAgents" / "in.eg1.pyegclamui.plist"
        if plist_file.is_file():
            try:
                plist_file.unlink()
                logger.ok(f"Removed macOS LaunchAgent: {plist_file}")
                cleaned = True
            except Exception as e:
                logger.warn(f"Notice on cleaning LaunchAgent: {e}")
    return cleaned


def get_app_directories() -> dict:
    """Returns standard user directories for application configuration, data, logs, and quarantine."""
    dirs = {}
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        localappdata = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        dirs["config"] = Path(appdata) / "pyEGClamUI"
        dirs["data"] = Path(localappdata) / "pyEGClamUI"
        dirs["logs"] = Path(localappdata) / "pyEGClamUI" / "logs"
        dirs["quarantine"] = Path(localappdata) / "pyEGClamUI" / "quarantine"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "pyEGClamUI"
        dirs["config"] = base
        dirs["data"] = base
        dirs["logs"] = Path.home() / "Library" / "Logs" / "pyEGClamUI"
        dirs["quarantine"] = base / "quarantine"
    else:
        config_base = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        data_base = os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        dirs["config"] = Path(config_base) / "pyegclamui"
        dirs["data"] = Path(data_base) / "pyegclamui"
        dirs["logs"] = Path(data_base) / "pyegclamui" / "logs"
        dirs["quarantine"] = Path(data_base) / "pyegclamui" / "quarantine"
    return dirs


def prompt_user(question: str, default: bool = False, purge_all: bool = False) -> bool:
    """Prompts the user with a yes/no question, safely falling back if non-interactive."""
    if purge_all:
        return True
    if not sys.stdin.isatty():
        return default
    try:
        suffix = " [Y/n]: " if default else " [y/N]: "
        print(f"{Colors.CYAN}{question}{suffix}{Colors.RESET}", end="", flush=True)
        resp = input().strip().lower()
        if not resp:
            return default
        return resp in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def run_uninstall(
    shortcut_mgr: ShortcutManager,
    venv_mgr: VenvManager,
    clam_prov: ClamAVProvisioner,
    detector: SystemDetector,
    logger: SetupLogger,
    purge_all: bool = False
):
    """Executes clean, interactive removal of all pyEGClamUI components."""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}======================================================{Colors.RESET}")
    print(f"{Colors.YELLOW}{Colors.BOLD}        pyEGClamUI Clean Uninstaller & Removal        {Colors.RESET}")
    print(f"{Colors.YELLOW}{Colors.BOLD}======================================================{Colors.RESET}\n")

    # 1. Desktop & Start Menu / Application Menu Shortcuts (Always removed)
    shortcut_mgr.remove_shortcuts()

    # 2. System Auto-Launch on Login (Always cleaned)
    clean_autostart(logger)

    # 3. Resident ClamAV Daemon Background Service
    daemon_running = detector.is_daemon_running()
    service_status = "active & responding" if daemon_running else "installed / inactive"
    print(f"\n{Colors.BOLD}[Component] ClamAV Background Service ({service_status}){Colors.RESET}")
    if prompt_user("Do you wish to stop and remove/disable the ClamAV daemon background service?", default=False, purge_all=purge_all):
        clam_prov.remove_daemon_service()
    else:
        logger.info("Preserved ClamAV daemon background service.")

    # 4. User Configuration, Diagnostic Logs & Quarantine Vault
    app_dirs = get_app_directories()
    config_dir = app_dirs["config"]
    data_dir = app_dirs["data"]
    quarantine_dir = app_dirs["quarantine"]

    has_data = config_dir.is_dir() or data_dir.is_dir()
    if has_data:
        q_count = 0
        if quarantine_dir.is_dir():
            try:
                q_count = len(list(quarantine_dir.glob("*.quarantine")))
            except Exception:
                q_count = 0

        print(f"\n{Colors.BOLD}[Component] Application Settings, Logs & Quarantine Vault{Colors.RESET}")
        if q_count > 0:
            print(f"  {Colors.YELLOW}⚠️  CAUTION: Found {q_count} quarantined threat sample(s) in {quarantine_dir}. Purging will permanently delete them!{Colors.RESET}")

        if prompt_user("Do you wish to delete all user settings, scan logs, and quarantined threats?", default=False, purge_all=purge_all):
            for d in [config_dir, data_dir]:
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
                    logger.ok(f"Purged directory: {d}")
        else:
            logger.info("Preserved user configuration, logs, and quarantine vault.")

    # 5. Local Virtual Environment (.venv)
    if venv_mgr.venv_dir.is_dir() or venv_mgr.exists():
        print(f"\n{Colors.BOLD}[Component] Local Python Virtual Environment (.venv){Colors.RESET}")
        if prompt_user("Do you wish to remove the local virtual environment (.venv)?", default=False, purge_all=purge_all):
            if venv_mgr.venv_dir.is_dir():
                shutil.rmtree(venv_mgr.venv_dir, ignore_errors=True)
                logger.ok("Removed .venv directory.")
        else:
            logger.info("Preserved .venv directory.")

    print(f"\n{Colors.GREEN}{Colors.BOLD}======================================================{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}       pyEGClamUI Uninstallation Completed Cleanly     {Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}======================================================{Colors.RESET}\n")

    # 6. Informational guidance for ClamAV engine itself
    print(f"{Colors.CYAN}Tip: To also uninstall the underlying ClamAV antivirus engine:{Colors.RESET}")
    if detector.os_type == "win32":
        print(f"  * Windows (winget):      {Colors.BOLD}winget uninstall ClamAV.ClamAV{Colors.RESET}")
    elif detector.os_type.startswith("linux"):
        print(f"  * Linux (Debian/Ubuntu): {Colors.BOLD}sudo apt purge clamav clamav-daemon{Colors.RESET}")
        print(f"  * Linux (Fedora/RHEL):   {Colors.BOLD}sudo dnf remove clamav clamd{Colors.RESET}")
    elif detector.os_type == "darwin":
        print(f"  * macOS (Homebrew):      {Colors.BOLD}brew uninstall clamav{Colors.RESET}")
    print()


# ------------------------------------------------------------------------------
# 9. Main CLI Entry Point & Dispatcher
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="pyEGClamUI - Unified Cross-Platform Setup, Update & Deployment Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup/setup.py                      # Default full installation
  python setup/setup.py --check              # Run system compatibility audit
  python setup/setup.py --update             # Update signatures, engine, and app
  python setup/setup.py --shortcuts-only     # Recreate desktop shortcuts
  python setup/setup.py --uninstall          # Clean interactive component removal
  python setup/setup.py --uninstall -y       # Complete silent purge of all components
        """
    )
    parser.add_argument("--install", action="store_true", help="Perform complete environment and application setup (Default)")
    parser.add_argument("--update", action="store_true", help="Synchronously update ClamAV database, engine, and pyEGClamUI")
    parser.add_argument("--check", action="store_true", help="Perform pre-flight health diagnostic check only")
    parser.add_argument("--shortcuts-only", action="store_true", help="Create or restore desktop and application menu shortcuts")
    parser.add_argument("--uninstall", action="store_true", help="Cleanly remove pyEGClamUI components, services, and shortcuts")
    parser.add_argument("--purge-all", "-y", "--yes", action="store_true", help="Purge all components and services without interactive prompts")
    parser.add_argument("--with-clamav", action="store_true", help="Enforce automatic ClamAV engine installation if missing")
    parser.add_argument("--no-clamav", action="store_true", help="Skip ClamAV engine provisioning step")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose step-by-step diagnostic execution logs")
    parser.add_argument("--start", action="store_true", help="Launch pyEGClamUI GUI immediately after completion")

    args = parser.parse_args()

    # Determine Project Root (parent directory of setup/)
    project_root = Path(__file__).resolve().parent.parent

    logger = SetupLogger(verbose=args.verbose)
    detector = SystemDetector(project_root)
    venv_mgr = VenvManager(project_root, logger, detector)
    clam_prov = ClamAVProvisioner(detector, logger)
    shortcut_mgr = ShortcutManager(project_root, venv_mgr, logger)
    updater = GlobalUpdater(project_root, venv_mgr, clam_prov, logger)

    # 1. Action: Diagnostic Audit
    if args.check:
        run_diagnostic_check(detector, venv_mgr, logger)
        sys.exit(0)

    # 2. Action: Clean Uninstall
    if args.uninstall:
        run_uninstall(shortcut_mgr, venv_mgr, clam_prov, detector, logger, purge_all=args.purge_all)
        sys.exit(0)

    # 3. Action: Shortcuts Only
    if args.shortcuts_only:
        if not venv_mgr.exists():
            logger.error("Cannot create shortcuts: .venv does not exist yet. Run setup first.")
            sys.exit(1)
        shortcut_mgr.create_shortcuts()
        sys.exit(0)

    # 4. Action: Global Update
    if args.update:
        updater.execute_update()
        if args.start:
            spawn_hidden_process([str(venv_mgr.get_python_exe()), "-m", "pyegclamui"], cwd=str(project_root))
        sys.exit(0)

    # 5. Default Action: Full Installation
    print(f"\n{Colors.CYAN}{Colors.BOLD}======================================================{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}        pyEGClamUI Universal Setup Engine             {Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}======================================================{Colors.RESET}")

    total_steps = 5

    # Step 1: Pre-flight check
    logger.step(1, total_steps, "Pre-Flight System Environment Audit")
    if not detector.is_python_supported():
        logger.error(f"Python 3.9 or higher is required. Found Python {sys.version.split()[0]}.")
        sys.exit(1)
    logger.ok(f"Python environment compatible ({sys.version.split()[0]}).")
    if detector.os_type.startswith("linux"):
        detector.ensure_linux_prerequisites(logger)

    # Step 2: Virtual Environment Setup
    logger.step(2, total_steps, "Provisioning Isolated Virtual Environment (.venv)")
    if not venv_mgr.exists():
        if not venv_mgr.create():
            sys.exit(1)
    else:
        logger.ok(f"Existing virtual environment detected at {venv_mgr.venv_dir}.")

    # Step 3: Install Package Dependencies
    logger.step(3, total_steps, "Installing pyEGClamUI Dependencies")
    if not venv_mgr.install_dependencies():
        sys.exit(1)

    # Step 4: ClamAV Engine Verification & Setup
    logger.step(4, total_steps, "ClamAV Backend Engine Check")
    if not args.no_clamav:
        if not detector.get_clamscan_path():
            logger.info("ClamAV engine not detected.")
            clam_prov.install_engine()
        else:
            # Activate background daemon service if not active
            if not detector.is_daemon_running():
                clam_prov.configure_daemon_service()

    # Step 5: Desktop Shortcuts
    logger.step(5, total_steps, "Configuring Desktop & Application Menu Shortcuts")
    shortcut_mgr.create_shortcuts()

    print(f"\n{Colors.GREEN}{Colors.BOLD}======================================================{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}       pyEGClamUI Setup Completed Successfully!       {Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}======================================================{Colors.RESET}\n")

    manual_exe = venv_mgr.get_python_exe()
    try:
        rel_exe = f".{os.sep}{manual_exe.relative_to(project_root)}"
    except ValueError:
        rel_exe = str(manual_exe)

    print(f" * Desktop Shortcut: Created on your desktop.")
    print(f" * Manual Launch:   {rel_exe} -m pyegclamui")
    print(f" * Maintenance:     python setup/setup.py --update\n")

    if args.start:
        logger.info("Launching pyEGClamUI...")
        spawn_hidden_process([str(venv_mgr.get_python_exe()), "-m", "pyegclamui"], cwd=str(project_root))


if __name__ == "__main__":
    main()
