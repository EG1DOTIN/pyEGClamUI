"""
Unit tests for pyegclamui.core.process module.
Validates centric hidden process execution across Windows, Linux, and macOS.
"""

import struct
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from pyegclamui.core.process import (
    format_subprocess_os_error,
    get_hidden_subprocess_kwargs,
    get_pe_machine_type,
    is_compatible_windows_binary,
    run_hidden_process,
    spawn_hidden_process,
)


def test_get_hidden_subprocess_kwargs_structure():
    """Verifies platform-specific kwargs returned by get_hidden_subprocess_kwargs."""
    kwargs = get_hidden_subprocess_kwargs()
    assert isinstance(kwargs, dict)
    if sys.platform == "win32":
        assert "creationflags" in kwargs
        assert "startupinfo" in kwargs
        assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        assert kwargs["startupinfo"].wShowWindow == getattr(subprocess, "SW_HIDE", 0)


def test_run_hidden_process_execution():
    """Verifies synchronous execution via run_hidden_process."""
    cmd = [sys.executable, "-c", "import sys; print('CENTRIC_PROCESS_OK')"]
    res = run_hidden_process(cmd, capture_output=True, timeout=10)
    assert res.returncode == 0
    assert "CENTRIC_PROCESS_OK" in res.stdout


def test_run_hidden_process_timeout():
    """Verifies timeout handling in run_hidden_process."""
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    with pytest.raises(subprocess.TimeoutExpired):
        run_hidden_process(cmd, timeout=0.5)


def test_spawn_hidden_process_streaming():
    """Verifies streaming execution via spawn_hidden_process."""
    cmd = [
        sys.executable,
        "-c",
        "import sys; print('LINE1', flush=True); print('LINE2', flush=True)",
    ]
    proc = spawn_hidden_process(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    for line in iter(proc.stdout.readline, ""):
        clean = line.strip()
        if clean:
            lines.append(clean)
    proc.wait(timeout=5)
    assert proc.returncode == 0
    assert lines == ["LINE1", "LINE2"]


def _make_fake_pe(path: Path, machine: int) -> Path:
    """Creates a minimal synthetic PE header for architecture validation tests."""
    buf = bytearray(0x90)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, 0x80)
    buf[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", buf, 0x84, machine)
    path.write_bytes(bytes(buf))
    return path


def test_pe_machine_type_and_windows_compatibility(tmp_path: Path):
    exe_x86 = _make_fake_pe(tmp_path / "clamscan_x86.exe", 0x014C)
    exe_x64 = _make_fake_pe(tmp_path / "clamscan_x64.exe", 0x8664)
    exe_arm64 = _make_fake_pe(tmp_path / "clamscan_arm64.exe", 0xAA64)
    invalid_exe = tmp_path / "corrupt.exe"
    invalid_exe.write_bytes(b"<html>404 Not Found</html>")

    assert get_pe_machine_type(exe_x86) == 0x014C
    assert get_pe_machine_type(exe_x64) == 0x8664
    assert get_pe_machine_type(exe_arm64) == 0xAA64
    assert get_pe_machine_type(invalid_exe) is None

    # Simulate 32-bit x86 Windows host: x64 & ARM64 must be rejected
    with patch("pyegclamui.core.process.is_windows_64bit_os", return_value=False), patch.dict(
        "os.environ", {"PROCESSOR_ARCHITECTURE": "x86", "PROCESSOR_ARCHITEW6432": ""}
    ):
        assert is_compatible_windows_binary(exe_x86)[0] is True
        assert is_compatible_windows_binary(exe_x64)[0] is False
        assert is_compatible_windows_binary(exe_arm64)[0] is False
        assert is_compatible_windows_binary(invalid_exe)[0] is False

    # Simulate 64-bit AMD64 Windows host: x86 & x64 allowed, ARM64 rejected
    with patch("pyegclamui.core.process.is_windows_64bit_os", return_value=True), patch.dict(
        "os.environ", {"PROCESSOR_ARCHITECTURE": "AMD64", "PROCESSOR_ARCHITEW6432": ""}
    ):
        assert is_compatible_windows_binary(exe_x86)[0] is True
        assert is_compatible_windows_binary(exe_x64)[0] is True
        assert is_compatible_windows_binary(exe_arm64)[0] is False


def test_format_subprocess_os_error_winerror_216():
    err = OSError("Incompatible binary")
    err.winerror = 216
    formatted = format_subprocess_os_error(err, "clamscan.exe")
    assert "WinError 216" in formatted
    assert "clamscan.exe" in formatted
