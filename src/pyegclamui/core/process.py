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
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


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
