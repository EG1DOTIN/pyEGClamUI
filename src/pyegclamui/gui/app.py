"""
Application lifecycle manager for pyEGClamUI.

Deterministic Dual-Tier Desktop Dispatcher:
  - Tier 1: Modern Qt6 / PySide6 Suite (64-bit OS & RAM >= 4.0 GB)
  - Tier 2: pyEGClamUI Lite Tkinter Dashboard (32-bit OR RAM < 4.0 GB)
  - Seamless fallback to Tier 2 if PySide6 is not installed on Tier 1 systems.
"""

import os
import platform
import sys
from typing import Optional, Tuple

from pyegclamui.core.config import AppPaths
from pyegclamui.core.logger import get_logger, open_log_folder, setup_logging
from pyegclamui.core.system_capability import (
    determine_gui_tier,
    get_system_specs,
)

logger = get_logger("app")


def install_crash_handler(qapp_cls=None):
    """Installs global exception hook to capture unhandled fatal exceptions."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught fatal exception:", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            if qapp_cls:
                app_instance = qapp_cls.instance()
                if app_instance:
                    from PySide6.QtWidgets import QMessageBox
                    msg = QMessageBox()
                    msg.setWindowTitle("pyEGClamUI - Critical Error")
                    msg.setText("An unexpected error occurred in pyEGClamUI.")
                    msg.setInformativeText(
                        f"{exc_type.__name__}: {exc_value}\n\n"
                        "Error details have been saved to the errors log file."
                    )
                    msg.setIcon(QMessageBox.Critical)
                    btn_logs = msg.addButton("Open Log Folder", QMessageBox.ActionRole)
                    msg.addButton(QMessageBox.Close)
                    msg.exec()
                    if msg.clickedButton() == btn_logs:
                        open_log_folder()
        except Exception:
            pass

    sys.excepthook = handle_exception


class GuiOptions(tuple):
    """Tuple subclass preserving (tier_override, start_minimized, target_path) compatibility while exposing scan_mode."""

    def __new__(cls, tier_override: Optional[str], start_minimized: bool, target_path: Optional[str], scan_mode: Optional[str] = None):
        return super().__new__(cls, (tier_override, start_minimized, target_path))

    def __init__(self, tier_override: Optional[str], start_minimized: bool, target_path: Optional[str], scan_mode: Optional[str] = None):
        self.tier_override = tier_override
        self.start_minimized = start_minimized
        self.target_path = target_path
        self.scan_mode = scan_mode


def parse_gui_options(args: list[str]) -> GuiOptions:
    """
    Parses CLI arguments for GUI tier override, minimization, target scan path, and scan mode.
    Returns: GuiOptions tuple compatible with (tier_override, start_minimized, target_path)
    """
    tier_override: Optional[str] = None
    start_minimized: bool = False
    target_path: Optional[str] = None
    scan_mode: Optional[str] = None

    i = 1
    while i < len(args):
        arg = args[i]
        arg_lower = arg.lower()
        if arg_lower in ("--minimized", "-m"):
            start_minimized = True
        elif arg_lower in ("--quick", "-q"):
            scan_mode = "quick"
        elif arg_lower == "--full":
            scan_mode = "full"
        elif arg_lower in ("--lite", "--tk", "--tkinter", "--tier2"):
            tier_override = "tkinter"
        elif arg_lower in ("--qt", "--qt6", "--pyside6", "--tier1"):
            tier_override = "pyside6"
        elif arg_lower.startswith("--ui="):
            val = arg.split("=", 1)[1].strip().lower()
            if val in ("tk", "tkinter", "lite", "tier2"):
                tier_override = "tkinter"
            elif val in ("qt", "qt6", "pyside6", "tier1"):
                tier_override = "pyside6"
            else:
                tier_override = val
        elif arg_lower.startswith("--tier="):
            val = arg.split("=", 1)[1].strip().lower()
            if val in ("tk", "tkinter", "lite", "tier2"):
                tier_override = "tkinter"
            elif val in ("qt", "qt6", "pyside6", "tier1"):
                tier_override = "pyside6"
            else:
                tier_override = val
        elif arg_lower.startswith("--path="):
            target_path = arg.split("=", 1)[1].strip()
        elif arg_lower in ("--path", "-p") and i + 1 < len(args):
            i += 1
            target_path = args[i]
        elif not arg.startswith("-") and os.path.exists(arg):
            target_path = arg
        i += 1

    return GuiOptions(tier_override, start_minimized, target_path, scan_mode)


def main() -> int:
    """Main application execution function with deterministic dual-tier GUI routing."""
    setup_logging()

    options = parse_gui_options(sys.argv)
    tier_override = options.tier_override
    start_minimized = options.start_minimized
    target_path = options.target_path
    scan_mode = options.scan_mode

    assigned_tier = determine_gui_tier(tier_override)
    specs = get_system_specs()

    logger.info(
        "Hardware Profile: %s (%s, %s GB RAM). Assigned GUI Tier: %s (Override: %s)",
        specs.get("os_release"),
        specs.get("machine"),
        specs.get("ram_gb"),
        assigned_tier,
        tier_override or "None",
    )

    # --------------------------------------------------------------------------
    # Tier 2: pyEGClamUI Lite (Tkinter Dashboard)
    # --------------------------------------------------------------------------
    if assigned_tier == "tkinter":
        logger.info("Executing pyEGClamUI Lite Tkinter interface...")
        from pyegclamui.gui.tk_app import run_tkinter_app
        return run_tkinter_app(scan_path=target_path, scan_mode=scan_mode)

    # --------------------------------------------------------------------------
    # Tier 1: Modern Qt6 / PySide6 Suite
    # --------------------------------------------------------------------------
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from pyegclamui.gui.main_window import MainWindow
        from pyegclamui.gui.styles import DARK_THEME_QSS
        from pyegclamui.gui.tray import SystemTrayManager
    except ImportError as e:
        logger.warning(
            "PySide6 (Qt6 GUI) runtime is not available (%s). Falling back to pyEGClamUI Lite...",
            e,
        )
        from pyegclamui.gui.tk_app import run_tkinter_app
        fallback_res = run_tkinter_app(scan_path=target_path, scan_mode=scan_mode)
        if fallback_res == 0:
            return 0

        # Both PySide6 and Tkinter could not start graphical window
        arch = platform.machine()
        print("\n" + "=" * 68)
        print("  pyEGClamUI - Desktop Graphical Interface Notice")
        print("=" * 68)
        print(f"  PySide6 (Qt6 GUI) is not available: {e}")
        if arch.lower() in ("i386", "i686", "x86", "armv7l"):
            print(f"  Note: Your architecture is {arch} (32-bit). PySide6 (Qt6 GUI)")
            print("  is 64-bit only and not available for 32-bit Linux distributions.")
            print("  To enable the Lite interface on 32-bit systems, install Tkinter:")
            print("    sudo apt-get install -y python3-tk")
        else:
            print("  To install the GUI framework on 64-bit systems, run:")
            print("    pip install 'PySide6>=6.2.0'")
            print("  or on Debian/Ubuntu:")
            print("    sudo apt-get install -y python3-pyside6 python3-tk")
        print("\n  The pyEGClamUI Core Antivirus Engine is fully operational via CLI:")
        print("    pyegclamui-scan --quick        (Fast ClamAV Scan)")
        print("    pyegclamui-scan --full         (Comprehensive System Scan)")
        print("    pyegclamui-scan --path <dir>   (Scan Custom Directory)")
        print("    pyegclamui-setup               (ClamAV Engine Configuration)")
        print("=" * 68 + "\n")
        return 1

    install_crash_handler(QApplication)

    # Ensure High-DPI support
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("pyEGClamUI")
    app.setOrganizationName("EG1")
    app.setQuitOnLastWindowClosed(False)

    # Set Application Icon
    icon_path = AppPaths.get_app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Apply global modern dark theme
    app.setStyleSheet(DARK_THEME_QSS)

    window = MainWindow()

    def show_dashboard():
        window.showNormal()
        window.activateWindow()

    # Initialize System Tray
    tray = SystemTrayManager(
        parent=window,
        on_open_dashboard=show_dashboard,
        on_quick_scan=window.on_quick_scan_clicked,
        on_check_updates=window.on_check_updates_clicked,
        on_open_quarantine=window.open_quarantine_tab,
        on_toggle_protection=window.on_toggle_protection_from_tray,
        on_exit=window.confirm_exit_from_tray,
    )
    window.set_tray(tray)
    tray.show()

    if not start_minimized:
        window.show()

    # Trigger initial scan if requested via CLI
    if scan_mode == "quick":
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, window.on_quick_scan_clicked)
    elif scan_mode == "full":
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, window.on_full_scan_clicked)
    elif target_path and os.path.exists(target_path):
        from PySide6.QtCore import QTimer
        from pyegclamui.core.scanner import ScanType
        from pyegclamui.gui.scan_dialog import ScanDialog
        def _start_path():
            dlg = ScanDialog(window, ScanType.CUSTOM_SCAN, [target_path])
            dlg.exec()
            window.refresh_quarantine_table()
        QTimer.singleShot(300, _start_path)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
