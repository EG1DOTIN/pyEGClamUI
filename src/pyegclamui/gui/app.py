"""
Application lifecycle manager for pyEGClamUI.
Initializes PySide6 QApplication, applies dark theme styles, and runs the desktop event loop.
"""

import platform
import sys

from pyegclamui.core.config import AppPaths
from pyegclamui.core.logger import get_logger, open_log_folder, setup_logging

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


def main() -> int:
    """Main application execution function."""
    setup_logging()

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from pyegclamui.gui.main_window import MainWindow
        from pyegclamui.gui.styles import DARK_THEME_QSS
        from pyegclamui.gui.tray import SystemTrayManager
    except ImportError as e:
        arch = platform.machine()
        print("\n" + "=" * 68)
        print("  pyEGClamUI - Desktop Graphical Interface Notice")
        print("=" * 68)
        print(f"  PySide6 (Qt6 GUI) is not available: {e}")
        if arch.lower() in ("i386", "i686", "x86", "armv7l"):
            print(f"  Note: Your architecture is {arch} (32-bit). PyPI wheels for PySide6")
            print("  are 64-bit only. On Debian/antiX/Ubuntu 32-bit, you may test:")
            print("    sudo apt-get install -y python3-pyside6")
        else:
            print("  To install the GUI framework on 64-bit systems, run:")
            print("    pip install 'PySide6>=6.2.0'")
            print("  or on Debian/Ubuntu:")
            print("    sudo apt-get install -y python3-pyside6")
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

    # Check command line flags: --minimized or -m
    start_minimized = "--minimized" in sys.argv or "-m" in sys.argv
    if not start_minimized:
        window.show()

    return app.exec()



if __name__ == "__main__":
    sys.exit(main())
