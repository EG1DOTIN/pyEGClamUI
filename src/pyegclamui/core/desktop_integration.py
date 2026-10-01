"""
Linux desktop environment packaging and menu integration for pyEGClamUI.
Handles XDG desktop entry files and hicolor icon installation/uninstallation.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from pyegclamui.core.config import AppPaths


class LinuxDesktopManager:
    """Manages Linux application launcher (.desktop) and system icon integration."""

    DESKTOP_FILENAME = "pyegclamui.desktop"
    ICON_BASENAME = "pyegclamui.png"

    @classmethod
    def is_linux(cls) -> bool:
        """Returns True if the current operating system is Linux."""
        return sys.platform.startswith("linux")

    @classmethod
    def get_applications_dir(cls, user_mode: bool = True) -> Path:
        """Returns the XDG applications directory for desktop entries."""
        if user_mode:
            data_home = os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
            return Path(data_home) / "applications"
        return Path("/usr/share/applications")

    @classmethod
    def get_icon_dirs(cls, user_mode: bool = True) -> List[Tuple[str, Path]]:
        """Returns a list of (resolution, directory) tuples for hicolor icon themes."""
        base = (
            Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "icons" / "hicolor"
            if user_mode
            else Path("/usr/share/icons/hicolor")
        )
        return [
            ("256x256", base / "256x256" / "apps"),
            ("128x128", base / "128x128" / "apps"),
            ("64x64", base / "64x64" / "apps"),
            ("48x48", base / "48x48" / "apps"),
            ("scalable", base / "scalable" / "apps"),
        ]

    @classmethod
    def is_installed(cls, user_mode: bool = True) -> bool:
        """Checks if the .desktop entry is present on the system."""
        desktop_file = cls.get_applications_dir(user_mode=user_mode) / cls.DESKTOP_FILENAME
        return desktop_file.is_file()

    @classmethod
    def generate_desktop_entry_content(cls, exec_cmd: Optional[str] = None) -> str:
        """Loads and formats the XDG desktop entry specification with the appropriate Exec line."""
        asset_desktop = AppPaths.get_asset_path(cls.DESKTOP_FILENAME)
        content = ""
        if asset_desktop.exists():
            content = asset_desktop.read_text(encoding="utf-8")
        else:
            content = (
                "[Desktop Entry]\n"
                "Version=1.0\n"
                "Type=Application\n"
                "Name=pyEGClamUI\n"
                "GenericName=Antivirus GUI\n"
                "Comment=An open-source, cross-platform desktop GUI for ClamAV\n"
                "Exec=pyegclamui %F\n"
                "Icon=pyegclamui\n"
                "Terminal=false\n"
                "StartupNotify=true\n"
                "Categories=Utility;System;Security;\n"
                "Keywords=clamav;antivirus;scanner;security;protection;malware;virus;\n"
                "MimeType=inode/directory;application/x-executable;application/zip;\n"
            )

        if exec_cmd:
            lines = []
            for line in content.splitlines():
                if line.startswith("Exec="):
                    lines.append(f"Exec={exec_cmd}")
                else:
                    lines.append(line)
            content = "\n".join(lines) + "\n"

        return content

    @classmethod
    def install(
        cls, user_mode: bool = True, custom_exec: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Installs the pyegclamui desktop entry and application icons.
        Works in user mode (~/.local/share) without root permissions.
        """
        try:
            # 1. Determine Exec command
            if not custom_exec:
                py_exec = sys.executable
                if shutil.which("pyegclamui"):
                    custom_exec = "pyegclamui %F"
                else:
                    custom_exec = f'"{py_exec}" -m pyegclamui.gui.app %F'

            # 2. Write .desktop file
            apps_dir = cls.get_applications_dir(user_mode=user_mode)
            apps_dir.mkdir(parents=True, exist_ok=True)
            desktop_path = apps_dir / cls.DESKTOP_FILENAME

            content = cls.generate_desktop_entry_content(exec_cmd=custom_exec)
            desktop_path.write_text(content, encoding="utf-8")

            # 3. Copy application icon to hicolor themes
            src_icon = AppPaths.get_asset_path("egav.png")
            if src_icon.exists():
                for _, icon_dir in cls.get_icon_dirs(user_mode=user_mode):
                    icon_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_icon, icon_dir / cls.ICON_BASENAME)

            # 4. Trigger desktop database and icon cache updates if available
            cls._refresh_system_caches(user_mode=user_mode)

            return True, f"Installed desktop launcher to {desktop_path}"
        except Exception as e:
            return False, f"Failed to install desktop launcher: {e}"

    @classmethod
    def uninstall(cls, user_mode: bool = True) -> Tuple[bool, str]:
        """Removes the pyegclamui desktop entry and associated icons."""
        try:
            desktop_path = cls.get_applications_dir(user_mode=user_mode) / cls.DESKTOP_FILENAME
            if desktop_path.exists():
                desktop_path.unlink()

            for _, icon_dir in cls.get_icon_dirs(user_mode=user_mode):
                target_icon = icon_dir / cls.ICON_BASENAME
                if target_icon.exists():
                    target_icon.unlink()

            cls._refresh_system_caches(user_mode=user_mode)
            return True, "Successfully uninstalled desktop launcher and icons."
        except Exception as e:
            return False, f"Failed to uninstall desktop launcher: {e}"

    @classmethod
    def _refresh_system_caches(cls, user_mode: bool = True) -> None:
        """Safely updates XDG desktop database and GTK icon cache without throwing errors."""
        apps_dir = cls.get_applications_dir(user_mode=user_mode)
        update_db = shutil.which("update-desktop-database")
        if update_db and apps_dir.exists():
            try:
                subprocess.run([update_db, str(apps_dir)], capture_output=True, timeout=5, check=False)
            except Exception:
                pass

        icon_cache = shutil.which("gtk-update-icon-cache")
        if icon_cache:
            base_icon_dir = apps_dir.parent / "icons" / "hicolor"
            if base_icon_dir.exists():
                try:
                    subprocess.run(
                        [icon_cache, "-f", "-t", str(base_icon_dir)],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                except Exception:
                    pass
