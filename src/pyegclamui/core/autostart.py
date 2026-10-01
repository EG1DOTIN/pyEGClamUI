"""
Cross-platform system startup manager for pyEGClamUI.
Enables or disables launching pyEGClamUI minimized to tray on system login.
"""

import os
import sys
from pathlib import Path


class AutoStartManager:
    """Manages OS startup auto-launch entries (Windows Registry / Linux XDG Autostart)."""

    APP_KEY = "pyEGClamUI"

    @classmethod
    def is_supported(cls) -> bool:
        """Returns True if auto-start is supported on the current platform."""
        return sys.platform in ("win32", "linux", "darwin")

    @classmethod
    def get_launch_command(cls) -> str:
        """Constructs the command to launch pyEGClamUI minimized to system tray."""
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --minimized'

        # Prefer pythonw.exe on Windows to prevent showing a console window
        python_exec = sys.executable
        if sys.platform == "win32":
            candidate = Path(python_exec).parent / "pythonw.exe"
            if candidate.exists():
                python_exec = str(candidate)

        return f'"{python_exec}" -m pyegclamui.gui.app --minimized'

    @classmethod
    def is_enabled(cls) -> bool:
        """Checks if pyEGClamUI is configured to launch at system startup."""
        if sys.platform == "win32":
            return cls._is_enabled_windows()
        elif sys.platform == "linux":
            return cls._is_enabled_linux()
        elif sys.platform == "darwin":
            return cls._is_enabled_macos()
        return False

    @classmethod
    def set_enabled(cls, enable: bool) -> bool:
        """Enables or disables system startup auto-launch."""
        if sys.platform == "win32":
            return cls._set_enabled_windows(enable)
        elif sys.platform == "linux":
            return cls._set_enabled_linux(enable)
        elif sys.platform == "darwin":
            return cls._set_enabled_macos(enable)
        return False

    # --- Windows Registry (HKCU\...\Run) ---
    @classmethod
    def _is_enabled_windows(cls) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            try:
                val, _ = winreg.QueryValueEx(key, cls.APP_KEY)
                return bool(val)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    @classmethod
    def _set_enabled_windows(cls, enable: bool) -> bool:
        try:
            import winreg

            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                if enable:
                    cmd = cls.get_launch_command()
                    winreg.SetValueEx(key, cls.APP_KEY, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, cls.APP_KEY)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"[AutoStartManager] Windows registry error: {e}")
            return False

    # --- Linux XDG Autostart (~/.config/autostart/) ---
    @classmethod
    def _get_linux_desktop_file(cls) -> Path:
        base = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(base) / "autostart" / "pyegclamui.desktop"

    @classmethod
    def _is_enabled_linux(cls) -> bool:
        return cls._get_linux_desktop_file().exists()

    @classmethod
    def _set_enabled_linux(cls, enable: bool) -> bool:
        try:
            desktop_file = cls._get_linux_desktop_file()
            if enable:
                desktop_file.parent.mkdir(parents=True, exist_ok=True)
                content = (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=pyEGClamUI\n"
                    "Comment=ClamAV Antivirus Desktop Guard\n"
                    "Exec=pyegclamui --minimized\n"
                    "Terminal=false\n"
                    "Icon=pyegclamui\n"
                    "Categories=Utility;Security;\n"
                )
                desktop_file.write_text(content, encoding="utf-8")
            else:
                if desktop_file.exists():
                    desktop_file.unlink()
            return True
        except Exception as e:
            print(f"[AutoStartManager] Linux autostart error: {e}")
            return False

    # --- macOS LaunchAgent (~/Library/LaunchAgents/) ---
    @classmethod
    def _get_macos_plist_file(cls) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / "in.eg1.pyegclamui.plist"

    @classmethod
    def _is_enabled_macos(cls) -> bool:
        return cls._get_macos_plist_file().exists()

    @classmethod
    def _set_enabled_macos(cls, enable: bool) -> bool:
        try:
            plist_file = cls._get_macos_plist_file()
            if enable:
                plist_file.parent.mkdir(parents=True, exist_ok=True)
                python_exec = sys.executable
                content = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0">\n'
                    '<dict>\n'
                    '    <key>Label</key>\n'
                    '    <string>in.eg1.pyegclamui</string>\n'
                    '    <key>ProgramArguments</key>\n'
                    '    <array>\n'
                    f'        <string>{python_exec}</string>\n'
                    '        <string>-m</string>\n'
                    '        <string>pyegclamui.gui.app</string>\n'
                    '        <string>--minimized</string>\n'
                    '    </array>\n'
                    '    <key>RunAtLoad</key>\n'
                    '    <true/>\n'
                    '    <key>KeepAlive</key>\n'
                    '    <false/>\n'
                    '</dict>\n'
                    '</plist>\n'
                )
                plist_file.write_text(content, encoding="utf-8")
            else:
                if plist_file.exists():
                    plist_file.unlink()
            return True
        except Exception as e:
            print(f"[AutoStartManager] macOS launchd error: {e}")
            return False

