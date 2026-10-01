"""
Unit tests for LinuxDesktopManager XDG desktop entries and hicolor icons.
"""

from pathlib import Path
from pyegclamui.core.desktop_integration import LinuxDesktopManager


def test_desktop_entry_generation():
    content = LinuxDesktopManager.generate_desktop_entry_content(exec_cmd="pyegclamui --minimized")
    assert "[Desktop Entry]" in content
    assert "Exec=pyegclamui --minimized" in content
    assert "Name=pyEGClamUI" in content
    assert "Categories=" in content
    assert "Icon=" in content


def test_desktop_install_and_uninstall_in_temp_dir(tmp_path):
    fake_apps_dir = tmp_path / "share" / "applications"
    fake_icon_dir = tmp_path / "share" / "icons" / "hicolor" / "256x256" / "apps"

    def mock_get_apps_dir(user_mode=True):
        return fake_apps_dir

    def mock_get_icon_dirs(user_mode=True):
        return [("256x256", fake_icon_dir)]

    orig_apps = LinuxDesktopManager.get_applications_dir
    orig_icons = LinuxDesktopManager.get_icon_dirs
    try:
        LinuxDesktopManager.get_applications_dir = mock_get_apps_dir
        LinuxDesktopManager.get_icon_dirs = mock_get_icon_dirs

        # Test initially not installed
        assert LinuxDesktopManager.is_installed() is False

        # Test install
        success, msg = LinuxDesktopManager.install(user_mode=True, custom_exec="pyegclamui %F")
        assert success is True
        assert LinuxDesktopManager.is_installed() is True
        desktop_file = fake_apps_dir / "pyegclamui.desktop"
        assert desktop_file.is_file()
        assert "Exec=pyegclamui %F" in desktop_file.read_text(encoding="utf-8")

        # Test uninstall
        success, msg = LinuxDesktopManager.uninstall(user_mode=True)
        assert success is True
        assert LinuxDesktopManager.is_installed() is False
        assert not desktop_file.exists()

    finally:
        LinuxDesktopManager.get_applications_dir = orig_apps
        LinuxDesktopManager.get_icon_dirs = orig_icons
