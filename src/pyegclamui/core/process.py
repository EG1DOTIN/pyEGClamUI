"""
================================================================================
pyEGClamUI - Centric Hidden Process & Command Execution Subsystem
================================================================================
Provides a unified, secure, cross-platform architecture for spawning and running
external CLI executables (clamscan, clamd, clamdscan, freshclam, winget, etc.)
with 100% hidden window execution across Windows, Linux, and macOS.
================================================================================
"""

import os
import platform
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# Windows PE COFF machine constants
_PE_MACHINE_X86 = 0x014C
_PE_MACHINE_AMD64 = 0x8664
_PE_MACHINE_ARM64 = 0xAA64


def is_windows_64bit_os() -> bool:
    """
    Returns True if the host Windows operating system is 64-bit (x64 or ARM64).
    Checks WOW64 environment variables as well as pointer width and machine string.
    """
    if sys.maxsize > (2**32):
        return True
    arch_env = (
        os.environ.get("PROCESSOR_ARCHITEW6432", "")
        or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    ).upper()
    if arch_env in ("AMD64", "ARM64", "IA64"):
        return True
    mach = platform.machine().lower()
    return mach in ("amd64", "x86_64", "arm64", "aarch64")


def get_pe_machine_type(exe_path: Union[str, Path]) -> Optional[int]:
    """
    Reads the COFF Machine field from a Windows PE executable header.
    Returns None if the file is not a valid PE binary or cannot be read.
    """
    try:
        with open(exe_path, "rb") as f:
            dos_header = f.read(64)
            if len(dos_header) < 64 or dos_header[:2] != b"MZ":
                return None
            e_lfanew = struct.unpack_from("<I", dos_header, 0x3C)[0]
            if e_lfanew < 64 or e_lfanew > 1024 * 1024:
                return None
            f.seek(e_lfanew)
            pe_header = f.read(6)
            if len(pe_header) < 6 or pe_header[:4] != b"PE\x00\x00":
                return None
            return struct.unpack_from("<H", pe_header, 4)[0]
    except OSError:
        return None


def is_compatible_windows_binary(exe_path: Union[str, Path]) -> Tuple[bool, str]:
    """
    Verifies whether a Windows executable is a valid PE binary compatible with the
    host Windows architecture, preventing WinError 216 (ERROR_EXE_MACHINE_TYPE_MISMATCH).
    Returns (is_compatible, reason).
    """
    path = Path(exe_path)
    if not path.is_file():
        return False, f"File does not exist: {path}"

    # Non-.exe files (e.g. .cmd/.bat/scripts) cannot be checked as PE; allow scripts,
    # reject empty/extensionless files on Windows when looking for native binaries.
    suffix = path.suffix.lower()
    if suffix in (".cmd", ".bat"):
        return True, "Batch script"

    machine = get_pe_machine_type(path)
    if machine is None:
        return False, f"Not a valid Windows PE executable: {path.name}"

    host_arch = (
        os.environ.get("PROCESSOR_ARCHITEW6432", "")
        or os.environ.get("PROCESSOR_ARCHITECTURE", "")
        or platform.machine()
    ).upper()
    is_arm64_host = "ARM64" in host_arch or "AARCH64" in host_arch
    is_64_os = is_windows_64bit_os()

    if machine == _PE_MACHINE_X86:
        return True, "x86 (32-bit)"
    if machine == _PE_MACHINE_AMD64:
        if is_64_os:
            return True, "x64 (64-bit)"
        return False, (
            f"'{path.name}' is a 64-bit (x64) executable and cannot run on 32-bit Windows."
        )
    if machine == _PE_MACHINE_ARM64:
        if is_arm64_host:
            return True, "ARM64"
        return False, (
            f"'{path.name}' is an ARM64 executable and is incompatible with this Windows CPU."
        )

    return False, f"Unsupported PE machine architecture (0x{machine:04x}) in {path.name}"


def format_subprocess_os_error(exc: OSError, binary_name: str = "executable") -> str:
    """Formats OS process launch errors (including WinError 216) into actionable messages."""
    winerror = getattr(exc, "winerror", None)
    if winerror == 216:
        return (
            f"Incompatible Windows executable '{binary_name}' (WinError 216): "
            "This binary architecture or version does not match your Windows OS "
            "(for example, 64-bit binary on 32-bit Windows or corrupted executable). "
            "Please install the ClamAV build matching your system architecture."
        )
    return str(exc)


def get_hidden_subprocess_kwargs() -> Dict[str, Any]:
    """
    Returns platform-specific keyword arguments to ensure subprocesses spawn
    completely hidden with zero console or command prompt window visibility.

    - On Windows: Uses CREATE_NO_WINDOW (0x08000000) and STARTUPINFO SW_HIDE (0).
    - On Linux / macOS: Standard POSIX environment without window creation.
    """
    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32" and hasattr(subprocess, "STARTUPINFO"):
        # Windows API flag: CREATE_NO_WINDOW prevents command prompt flashing
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        # STARTUPINFO guarantees window is hidden even for legacy GUI/console apps
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

    return kwargs


def spawn_hidden_process(
    cmd: List[Union[str, Path]],
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.STDOUT,
    text: bool = True,
    bufsize: int = 1,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> subprocess.Popen:
    """
    Spawns an asynchronous streaming background subprocess with guaranteed hidden
    window properties across all supported operating systems.

    :param cmd: Discrete tokenized command argument list (NEVER uses shell=True).
    :param stdout: Standard output redirection (defaults to subprocess.PIPE).
    :param stderr: Standard error redirection (defaults to subprocess.STDOUT).
    :param text: Decode output streams as UTF-8 text strings (defaults to True).
    :param bufsize: Line-buffering mode (defaults to 1 for real-time stream parsing).
    :param cwd: Optional working directory for the spawned process.
    :param env: Optional custom environment variable mapping.
    :return: An active subprocess.Popen instance.
    """
    normalized_cmd = [str(arg) for arg in cmd]
    process_kwargs = get_hidden_subprocess_kwargs()
    process_kwargs.update(kwargs)

    # Ensure clean UTF-8 encoding handling on Windows console streams
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
        env=env,
        **process_kwargs,
    )


def run_hidden_process(
    cmd: List[Union[str, Path]],
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    check: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """
    Executes a command synchronously to completion with guaranteed hidden window
    properties across all supported operating systems.

    :param cmd: Discrete tokenized command argument list (NEVER uses shell=True).
    :param capture_output: Capture stdout and stderr (defaults to True).
    :param text: Decode output streams as UTF-8 text strings (defaults to True).
    :param timeout: Optional timeout in seconds before raising TimeoutExpired.
    :param check: If True, raises CalledProcessError if returncode != 0.
    :param cwd: Optional working directory for the spawned process.
    :param env: Optional custom environment variable mapping.
    :return: A subprocess.CompletedProcess instance.
    """
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
        env=env,
        **process_kwargs,
    )
