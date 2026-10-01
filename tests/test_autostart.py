"""
Unit tests for AutoStartManager (cross-platform startup configuration).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pyegclamui.core.autostart import AutoStartManager


def test_autostart_supported():
    """Validates that auto-start support is correctly reported for current OS."""
    supported = AutoStartManager.is_supported()
    if sys.platform in ("win32", "linux", "darwin"):
        assert supported is True
    else:
        assert supported is False


def test_autostart_launch_command():
    """Validates launch command formatting with --minimized flag."""
    cmd = AutoStartManager.get_launch_command()
    assert "--minimized" in cmd
    assert "pyegclamui" in cmd.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific registry test")
def test_autostart_windows_enable_and_disable():
    """Validates real Windows registry toggling for the current user."""
    # Ensure starting in a clean disabled state
    AutoStartManager.set_enabled(False)
    assert AutoStartManager.is_enabled() is False

    # Enable and verify
    success = AutoStartManager.set_enabled(True)
    assert success is True
    assert AutoStartManager.is_enabled() is True

    # Disable and verify cleanup
    success = AutoStartManager.set_enabled(False)
    assert success is True
    assert AutoStartManager.is_enabled() is False


def test_autostart_linux_mock(tmp_path: Path):
    """Validates Linux .desktop autostart file generation and removal."""
    mock_desktop = tmp_path / "autostart" / "pyegclamui.desktop"

    with patch.object(AutoStartManager, "_get_linux_desktop_file", return_value=mock_desktop):
        # Test enable
        assert AutoStartManager._set_enabled_linux(True) is True
        assert mock_desktop.exists()
        content = mock_desktop.read_text(encoding="utf-8")
        assert "[Desktop Entry]" in content
        assert "Exec=pyegclamui --minimized" in content
        assert AutoStartManager._is_enabled_linux() is True

        # Test disable
        assert AutoStartManager._set_enabled_linux(False) is True
        assert not mock_desktop.exists()
        assert AutoStartManager._is_enabled_linux() is False


def test_autostart_macos_mock(tmp_path: Path):
    """Validates macOS launchd .plist file generation and removal."""
    mock_plist = tmp_path / "LaunchAgents" / "in.eg1.pyegclamui.plist"

    with patch.object(AutoStartManager, "_get_macos_plist_file", return_value=mock_plist):
        # Test enable
        assert AutoStartManager._set_enabled_macos(True) is True
        assert mock_plist.exists()
        content = mock_plist.read_text(encoding="utf-8")
        assert "in.eg1.pyegclamui" in content
        assert "--minimized" in content
        assert "<key>RunAtLoad</key>" in content
        assert AutoStartManager._is_enabled_macos() is True

        # Test disable
        assert AutoStartManager._set_enabled_macos(False) is True
        assert not mock_plist.exists()
        assert AutoStartManager._is_enabled_macos() is False
