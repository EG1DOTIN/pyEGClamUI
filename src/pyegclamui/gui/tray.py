"""
System tray manager for pyEGClamUI.
Handles background tray icon, quick actions, status tooltips, and desktop notifications.
"""

from typing import Callable, Optional

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from pyegclamui.core.config import AppPaths, Config


class SystemTrayManager(QSystemTrayIcon):
    """Manages the background system tray icon, menu, and notifications."""

    def __init__(
        self,
        parent: QWidget,
        on_open_dashboard: Callable[[], None],
        on_quick_scan: Callable[[], None],
        on_check_updates: Callable[[], None],
        on_exit: Callable[[], None],
        on_open_quarantine: Optional[Callable[[], None]] = None,
        on_toggle_protection: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(parent)
        self.config = Config.get_instance()
        self.on_open_dashboard = on_open_dashboard
        self.on_quick_scan = on_quick_scan
        self.on_check_updates = on_check_updates
        self.on_exit = on_exit
        self.on_open_quarantine = on_open_quarantine
        self.on_toggle_protection = on_toggle_protection

        self.action_protection: Optional[QAction] = None
        self.setup_icon()
        self.setup_menu()
        self.activated.connect(self.on_activated)

    def setup_icon(self):
        icon_path = AppPaths.get_app_icon_path()
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        self.setToolTip("pyEGClamUI - ClamAV Antivirus")

    def setup_menu(self):
        menu = QMenu()

        action_open = QAction("Open Dashboard", menu)
        action_open.triggered.connect(self.on_open_dashboard)
        menu.addAction(action_open)

        menu.addSeparator()

        # Protection toggle action
        if self.on_toggle_protection:
            self.action_protection = QAction("Real-Time Protection", menu)
            self.action_protection.setCheckable(True)
            is_active = self.config.get("preferences", "real_time_protection", default=False)
            self.action_protection.setChecked(is_active)
            self.action_protection.toggled.connect(self.on_toggle_protection)
            menu.addAction(self.action_protection)

        action_scan = QAction("Run Quick Scan", menu)
        action_scan.triggered.connect(self.on_quick_scan)
        menu.addAction(action_scan)

        if self.on_open_quarantine:
            action_quarantine = QAction("Quarantine Vault", menu)
            action_quarantine.triggered.connect(self.on_open_quarantine)
            menu.addAction(action_quarantine)

        action_update = QAction("Check for Updates", menu)
        action_update.triggered.connect(self.on_check_updates)
        menu.addAction(action_update)

        menu.addSeparator()

        action_exit = QAction("Exit pyEGClamUI", menu)
        action_exit.triggered.connect(self.on_exit)
        menu.addAction(action_exit)

        self.setContextMenu(menu)

    def set_protection_state(self, active: bool):
        """Updates the check state and tooltip to reflect active protection."""
        if self.action_protection:
            self.action_protection.blockSignals(True)
            self.action_protection.setChecked(active)
            self.action_protection.blockSignals(False)

        status_text = "Protected" if active else "Protection Inactive"
        self.setToolTip(f"pyEGClamUI - {status_text}")

    def on_activated(self, reason):
        if reason in [QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick]:
            self.on_open_dashboard()

    def notify(self, title: str, message: str, is_warning: bool = False):
        """Displays a desktop balloon notification if enabled in preferences."""
        if not self.config.get("preferences", "notifications", default=True):
            return

        icon = QSystemTrayIcon.Warning if is_warning else QSystemTrayIcon.Information
        self.showMessage(title, message, icon, 5000)
