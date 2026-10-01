"""
Unit tests for the cross-platform packaging and build script (scripts/build.py).
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure scripts directory can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build


def test_get_platform_info_current():
    """Validates platform info dictionary for the active environment."""
    info = build.get_platform_info()
    assert "os_name" in info
    assert info["os_name"] in ("windows", "linux", "macos")
    assert "arch" in info
    assert "exe_name" in info
    assert "data_sep" in info
    assert "icon" in info
    assert "archive_type" in info
    assert "archive_name" in info
    assert build.__version__ in info["archive_name"]


def test_get_platform_info_windows():
    """Validates platform info when mocked for Windows."""
    with patch("sys.platform", "win32"), patch("platform.machine", return_value="AMD64"):
        info = build.get_platform_info()
        assert info["os_name"] == "windows"
        assert info["arch"] == "x64"
        assert info["exe_name"] == "pyEGClamUI.exe"
        assert info["data_sep"] == ";"
        assert info["archive_type"] == "zip"
        assert "windows" in info["archive_name"]


def test_get_platform_info_linux():
    """Validates platform info when mocked for Linux."""
    with patch("sys.platform", "linux"), patch("platform.machine", return_value="x86_64"):
        info = build.get_platform_info()
        assert info["os_name"] == "linux"
        assert info["arch"] == "x86_64"
        assert info["exe_name"] == "pyegclamui"
        assert info["data_sep"] == ":"
        assert info["archive_type"] == "tar.gz"
        assert "linux" in info["archive_name"]


def test_get_platform_info_macos():
    """Validates platform info when mocked for macOS."""
    with patch("sys.platform", "darwin"), patch("platform.machine", return_value="arm64"):
        info = build.get_platform_info()
        assert info["os_name"] == "macos"
        assert info["arch"] == "arm64"
        assert info["exe_name"] == "pyEGClamUI"
        assert info["data_sep"] == ":"
        assert info["archive_type"] == "zip"
        assert "macos" in info["archive_name"]
