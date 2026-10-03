"""
Unit tests for pyegclamui.core.process module.
Validates centric hidden process execution across Windows, Linux, and macOS.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pyegclamui.core.process import (
    get_hidden_subprocess_kwargs,
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
