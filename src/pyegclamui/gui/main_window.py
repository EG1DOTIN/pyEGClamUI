"""
Primary dashboard window for pyEGClamUI.
Provides tabs for Status, Scanning, Quarantine Vault, Settings, and About/Credits.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pyegclamui import __version__
from pyegclamui.core.autostart import AutoStartManager
from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.desktop_integration import LinuxDesktopManager
from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.logger import get_logger, log_settings_change, open_log_folder
from pyegclamui.core.monitor import RealTimeGuard
from pyegclamui.core.quarantine import QuarantineManager
from pyegclamui.core.scanner import ClamScanner, ScanType
from pyegclamui.core.service_manager import ClamDaemonServiceManager
from pyegclamui.core.telemetry import TelemetryManager, generate_guest_id
from pyegclamui.core.updater import ClamUpdater
from pyegclamui.gui.icons import IconFactory
from pyegclamui.gui.platform_theme import apply_dark_titlebar
from pyegclamui.gui.scan_dialog import ScanDialog
from pyegclamui.gui.setup_dialog import ClamSetupDialog
from pyegclamui.gui.update_dialog import ClamGlobalUpdateDialog

logger = get_logger("gui")


class DaemonActivationWorker(QThread):
    """Background worker executing elevated ClamD service registration."""
    activation_completed = Signal(bool, str)

    def __init__(self, service_mgr: ClamDaemonServiceManager):
        super().__init__()
        self.service_mgr = service_mgr

    def run(self):
        success, msg = self.service_mgr.activate_daemon()
        self.activation_completed.emit(success, msg)


class MainWindow(QMainWindow):
    """Main desktop interface window."""

    def __init__(self):
        super().__init__()
        self.config = Config.get_instance()
        self.detector = ClamEngineDetector()
        self.quarantine_mgr = QuarantineManager()
        self.updater = ClamUpdater()
        self.scanner = ClamScanner()
        self.telemetry_mgr = TelemetryManager()
        self.service_mgr = ClamDaemonServiceManager(self.detector)
        self._daemon_worker = None

        self.setWindowTitle("pyEGClamUI - Status")
        self.resize(920, 640)
        self.setMinimumSize(800, 560)

        # Set App Icon
        icon_path = AppPaths.get_app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.tray = None
        self.guard = RealTimeGuard(on_threat_detected=self.on_real_time_threat)
        if self.config.get("preferences", "real_time_protection", default=False):
            self.guard.start()

        self.setup_ui()
        self.refresh_status()
        self.refresh_quarantine_table()
        apply_dark_titlebar(self)

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_titlebar(self)
        if not self.config.get("preferences", "first_run_completed", default=False):
            QTimer.singleShot(250, self._show_welcome_dialog)
        else:
            self.telemetry_mgr.send_heartbeat_if_due()

    def _show_welcome_dialog(self):
        # Never launch modal dialog in headless or automated test environments
        if os.getenv("QT_QPA_PLATFORM") == "offscreen" or "pytest" in sys.modules:
            return
        from pyegclamui.gui.welcome_dialog import WelcomeDialog
        dlg = WelcomeDialog(self)
        apply_dark_titlebar(dlg)
        dlg.exec()
        self.refresh_status()

    def set_tray(self, tray):
        """Attaches system tray manager to the window."""
        self.tray = tray
        if self.tray and hasattr(self.tray, "set_protection_state"):
            self.tray.set_protection_state(self.guard.is_active)

    def open_quarantine_tab(self):
        """Switches to the Quarantine tab and brings window to focus."""
        self.tabs.setCurrentIndex(2)
        self.showNormal()
        self.activateWindow()

    def on_toggle_protection_from_tray(self, checked: bool):
        """Called when real-time protection is toggled from tray context menu."""
        self.chk_realtime.setChecked(checked)

    def confirm_exit_from_tray(self):
        """Prompts user to confirm exiting the application entirely from the system tray."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Exit pyEGClamUI")
        msg.setText("Are you sure you want to exit pyEGClamUI?")
        msg.setInformativeText(
            "Exiting will terminate the application, stop Real-Time Guard protection, "
            "and remove the background system tray icon."
        )
        msg.setIcon(QMessageBox.Warning)
        btn_exit = msg.addButton("Exit Application", QMessageBox.AcceptRole)
        btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_cancel)
        apply_dark_titlebar(msg)

        msg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        msg.exec()
        if msg.clickedButton() == btn_exit:
            if self.guard:
                self.guard.stop()
            if self.tray:
                self.tray.hide()
            QApplication.instance().quit()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(14, 14))
        main_layout.addWidget(self.tabs)

        self.setup_status_tab()
        self.setup_scan_tab()
        self.setup_quarantine_tab()
        self.setup_settings_tab()
        self.setup_about_tab()

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._update_window_title()

    def _on_tab_changed(self, index: int) -> None:
        """Dynamically synchronizes window & taskbar title with the currently selected tab."""
        self._update_window_title()

    def _update_window_title(self) -> None:
        """Sets the window title in the format 'pyEGClamUI - <Tab-Name>'."""
        if hasattr(self, "tabs") and self.tabs.count() > 0:
            index = self.tabs.currentIndex()
            if index >= 0:
                tab_name = self.tabs.tabText(index).strip()
                self.setWindowTitle(f"pyEGClamUI - {tab_name}")
                return
        self.setWindowTitle("pyEGClamUI")

    # --- TAB 1: STATUS ---
    def setup_status_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Shield Banner Card - Hero status banner
        self.banner_card = QFrame()
        self.banner_card.setObjectName("bannerCard")
        self._update_banner_style("#166534")

        banner_layout = QHBoxLayout(self.banner_card)
        banner_layout.setContentsMargins(24, 22, 24, 22)
        banner_layout.setSpacing(20)

        # Dynamic Status Shield Icon (64px hero size as originally designed)
        self.banner_icon_lbl = QLabel()
        self.banner_icon_lbl.setStyleSheet("border: none; background: transparent;")
        self.banner_icon_lbl.setPixmap(IconFactory.get_pixmap("shield_ok", "#22c55e", 64))
        banner_layout.addWidget(self.banner_icon_lbl)

        # Banner Text
        banner_text_layout = QVBoxLayout()
        banner_text_layout.setSpacing(4)
        self.banner_title = QLabel("System Protected")
        self.banner_title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.banner_title.setStyleSheet("color: #22c55e; border: none; background: transparent;")

        self.banner_sub = QLabel("Real-time protection is active. Virus signatures are up-to-date.")
        self.banner_sub.setStyleSheet("color: #949ba4; font-size: 13px; border: none; background: transparent;")

        banner_text_layout.addWidget(self.banner_title)
        banner_text_layout.addWidget(self.banner_sub)
        banner_layout.addLayout(banner_text_layout)
        banner_layout.addStretch()

        # Update button with vector refresh icon
        self.update_btn = QPushButton("Check for Updates")
        self._set_update_button_style(is_danger=False)
        self.update_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
        self.update_btn.setIconSize(QSize(14, 14))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.on_check_updates_clicked)
        banner_layout.addWidget(self.update_btn)

        layout.addWidget(self.banner_card)

        # Resident Daemon Acceleration Card
        self.daemon_card = QFrame()
        self.daemon_card.setObjectName("daemonCard")
        self.daemon_card.setStyleSheet("""
            QFrame#daemonCard {
                background-color: #111214;
                border: 1px solid #313338;
                border-radius: 10px;
            }
            QFrame#daemonCard QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)
        daemon_card_layout = QHBoxLayout(self.daemon_card)
        daemon_card_layout.setContentsMargins(18, 14, 18, 14)
        daemon_card_layout.setSpacing(16)

        self.daemon_icon_lbl = QLabel()
        self.daemon_icon_lbl.setPixmap(IconFactory.get_pixmap("flash", "#38bdf8", 32))
        daemon_card_layout.addWidget(self.daemon_icon_lbl)

        daemon_text_layout = QVBoxLayout()
        daemon_text_layout.setSpacing(4)

        daemon_title_row = QHBoxLayout()
        daemon_title_row.setSpacing(8)
        self.lbl_daemon_title = QLabel("Resident Memory Daemon (ClamD)")
        self.lbl_daemon_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.lbl_daemon_title.setStyleSheet("color: #e0e2e8;")
        daemon_title_row.addWidget(self.lbl_daemon_title)

        self.lbl_daemon_badge = QLabel("🟡 Inactive (~800ms)")
        self.lbl_daemon_badge.setStyleSheet(
            "background-color: #713f12; color: #fde047; font-size: 11px; "
            "font-weight: bold; border-radius: 4px; padding: 2px 8px; border: 1px solid #eab308;"
        )
        daemon_title_row.addWidget(self.lbl_daemon_badge)
        daemon_title_row.addStretch()
        daemon_text_layout.addLayout(daemon_title_row)

        self.lbl_daemon_desc = QLabel(
            "Resident daemon is offline. File scans use standalone engine fallback (~800ms cold startup per file)."
        )
        self.lbl_daemon_desc.setStyleSheet("color: #949ba4; font-size: 12px;")
        daemon_text_layout.addWidget(self.lbl_daemon_desc)
        daemon_card_layout.addLayout(daemon_text_layout)
        daemon_card_layout.addStretch()

        self.btn_daemon_action = QPushButton("⚡ Enable ClamD Daemon")
        self.btn_daemon_action.setObjectName("primaryButton")
        self.btn_daemon_action.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #0ea5e9; }
            QPushButton:disabled { background-color: #1e293b; color: #64748b; border-color: #334155; }
        """)
        self.btn_daemon_action.setCursor(Qt.PointingHandCursor)
        self.btn_daemon_action.clicked.connect(self.on_daemon_action_clicked)
        daemon_card_layout.addWidget(self.btn_daemon_action)

        layout.addWidget(self.daemon_card)

        # Info Group Box
        info_group = QGroupBox("ClamAV Engine && Signature Details")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(12)

        self.lbl_engine_ver = QLabel("Engine Version: Checking...")
        self.lbl_db_ver = QLabel("Signature Database: Checking...")
        self.lbl_daemon_status = QLabel("Daemon Service: Checking...")
        self.lbl_clamscan_path = QLabel("ClamScan Executable: Checking...")

        for lbl in [self.lbl_engine_ver, self.lbl_db_ver, self.lbl_daemon_status, self.lbl_clamscan_path]:
            lbl.setStyleSheet("font-size: 13px; color: #e0e2e8;")
            info_layout.addWidget(lbl)

        layout.addWidget(info_group)
        layout.addStretch()

        self.tabs.addTab(tab, IconFactory.get_icon("shield", "#38bdf8", 14), "  Status  ")

    def _update_banner_style(self, border_color: str):
        """Sets precise scoped border styling on the hero card without leaking to child labels or buttons."""
        self.banner_card.setStyleSheet(f"""
            QFrame#bannerCard {{
                background-color: #111214;
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            QFrame#bannerCard QLabel {{
                background-color: transparent;
                border: none;
                padding: 0px;
            }}
        """)

    def _set_update_button_style(self, is_danger: bool = False):
        """Applies explicit high-contrast button styling to guarantee sky-blue or danger appearance."""
        if is_danger:
            self.update_btn.setObjectName("dangerButton")
            self.update_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: #ffffff;
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    border-color: #f87171;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: #b91c1c;
                    color: #ffffff;
                }
            """)
        else:
            self.update_btn.setObjectName("primaryButton")
            self.update_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: #ffffff;
                    border: 1px solid #38bdf8;
                    border-radius: 6px;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #0ea5e9;
                    border-color: #7dd3fc;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: #0369a1;
                    color: #ffffff;
                }
            """)

    def refresh_status(self):
        audit = self.detector.inspect()
        version = audit.get("version", {})

        clamscan_path = audit.get("clamscan_path") or "Not found"
        self.lbl_clamscan_path.setText(f"ClamScan Binary: {clamscan_path}")
        self.lbl_engine_ver.setText(f"Engine Version: {version.get('clamav_version', 'Not Found')}")

        is_recent, db_status_msg = self.updater.is_database_recent()
        self.lbl_db_ver.setText(f"Signature Database: {db_status_msg}")

        # Update ClamD daemon acceleration card & badge
        d_status = self.service_mgr.get_status()
        self.lbl_daemon_desc.setText(d_status["description"])
        if d_status["online"]:
            self.lbl_daemon_badge.setText(d_status["mode_badge"])
            self.lbl_daemon_badge.setStyleSheet(
                "background-color: #14532d; color: #86efac; font-size: 11px; "
                "font-weight: bold; border-radius: 4px; padding: 2px 8px; border: 1px solid #22c55e;"
            )
            self.btn_daemon_action.setText("🔄 Test Latency / Ping")
            self.btn_daemon_action.setEnabled(True)
            self.lbl_daemon_status.setText(f"Daemon Service: Online ({d_status['connection']} - {d_status['latency_label']})")
        else:
            self.lbl_daemon_badge.setText(d_status["mode_badge"])
            self.lbl_daemon_badge.setStyleSheet(
                "background-color: #713f12; color: #fde047; font-size: 11px; "
                "font-weight: bold; border-radius: 4px; padding: 2px 8px; border: 1px solid #eab308;"
            )
            self.btn_daemon_action.setText("⚡ Enable ClamD Daemon")
            self.btn_daemon_action.setEnabled(True)
            self.lbl_daemon_status.setText("Daemon Service: Offline (Standalone engine fallback)")

        # Evaluate 4 core protection components
        engine_ready = bool(audit.get("ready"))
        guard_active = bool(self.guard and self.guard.is_active)
        auto_updates = bool(self.config.get("preferences", "auto_updates", default=True))

        # Dynamic 3-Tier Banner Matrix
        if not engine_ready:
            self._update_banner_style("#991b1b")
            self.banner_title.setText("Engine Not Detected")
            self.banner_title.setStyleSheet("color: #ef4444; border: none; background: transparent;")
            self.banner_sub.setText("ClamAV was not found in PATH or configured folders. Please configure engine.")
            self.banner_icon_lbl.setPixmap(IconFactory.get_pixmap("shield_error", "#ef4444", 64))
            self.update_btn.setText("Configure Engine...")
            self._set_update_button_style(is_danger=True)
            self.update_btn.setIcon(IconFactory.get_icon("browse", "#ffffff", 14))
            self.update_btn.setIconSize(QSize(14, 14))
        elif not guard_active or not is_recent or not auto_updates:
            self._update_banner_style("#854d0e")
            self.banner_title.setText("System at Risk")
            self.banner_title.setStyleSheet("color: #eab308; border: none; background: transparent;")
            self.banner_icon_lbl.setPixmap(IconFactory.get_pixmap("shield_warn", "#eab308", 64))
            self._set_update_button_style(is_danger=False)

            # Prioritize contextual warning description & button action
            if not guard_active and not is_recent:
                self.banner_sub.setText("Real-Time Guard is disabled and virus signatures are outdated.")
                self.update_btn.setText("Update Signatures Now")
                self.update_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
                self.update_btn.setIconSize(QSize(14, 14))
            elif not guard_active:
                self.banner_sub.setText("Real-Time Guard is disabled. Files are not automatically monitored.")
                self.update_btn.setText("Enable Real-Time Guard")
                self.update_btn.setIcon(IconFactory.get_icon("shield", "#ffffff", 14))
                self.update_btn.setIconSize(QSize(14, 14))
            elif not is_recent:
                self.banner_sub.setText("Virus definitions are out-of-date. Newer threats may not be detected.")
                self.update_btn.setText("Update Signatures Now")
                self.update_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
                self.update_btn.setIconSize(QSize(14, 14))
            else:
                self.banner_sub.setText("Automatic daily virus database updates are turned off in Settings.")
                self.update_btn.setText("Check for Updates")
                self.update_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
                self.update_btn.setIconSize(QSize(14, 14))
        else:
            self._update_banner_style("#166534")
            self.banner_title.setText("System Protected")
            self.banner_title.setStyleSheet("color: #22c55e; border: none; background: transparent;")
            self.banner_sub.setText("Real-time protection is active. Virus signatures are up-to-date.")
            self.banner_icon_lbl.setPixmap(IconFactory.get_pixmap("shield_ok", "#22c55e", 64))
            self.update_btn.setText("Check for Updates")
            self._set_update_button_style(is_danger=False)
            self.update_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
            self.update_btn.setIconSize(QSize(14, 14))

    # --- TAB 2: SCAN ---
    def setup_scan_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header_layout = QVBoxLayout()
        header = QLabel("Choose a Scan Mode")
        header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.setStyleSheet("color: #38bdf8;")
        sub_header = QLabel("Select an automated inspection mode to detect and neutralize threats.")
        sub_header.setStyleSheet("color: #949ba4; font-size: 13px;")
        header_layout.addWidget(header)
        header_layout.addWidget(sub_header)
        layout.addLayout(header_layout)

        # 4 Horizontal Cards Layout
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(14)

        cards_layout.addWidget(self._create_scan_card(
            title="Quick Scan",
            desc="Lightweight check focusing on common high-priority directories (Downloads, Desktop, Temp).",
            btn_text="Run Quick Scan",
            icon_name="quick_scan",
            callback=self.on_quick_scan_clicked
        ))

        cards_layout.addWidget(self._create_scan_card(
            title="Full System Scan",
            desc="Thorough scan across all accessible local storage drives and system partitions.",
            btn_text="Run Full Scan",
            icon_name="full_scan",
            callback=self.on_full_scan_clicked
        ))

        cards_layout.addWidget(self._create_scan_card(
            title="Custom Scan",
            desc="Target specific files, folders, or external drives of your choice.",
            btn_text="Select && Scan",
            icon_name="custom_scan",
            callback=self.on_custom_scan_clicked
        ))

        cards_layout.addWidget(self._create_scan_card(
            title="Memory Scan" if sys.platform == "win32" else "Targeted Scan",
            desc="Detects hidden, active threats currently running in system memory." if sys.platform == "win32" else "Targeted inspection of active services and system memory endpoints.",
            btn_text="Scan Memory" if sys.platform == "win32" else "Scan System",
            icon_name="memory_scan",
            callback=self.on_memory_scan_clicked
        ))

        layout.addLayout(cards_layout)
        layout.addStretch()
        self.tabs.addTab(tab, IconFactory.get_icon("quick_scan", "#38bdf8", 14), "  Scan  ")

    def _create_scan_card(self, title: str, desc: str, btn_text: str, icon_name: str, callback) -> QFrame:
        card = QFrame()
        card.setObjectName("scanCard")
        card.setStyleSheet(
            "QFrame#scanCard {"
            "  background-color: #111214;"
            "  border: 1px solid #313338;"
            "  border-radius: 10px;"
            "}"
            "QFrame#scanCard:hover {"
            "  border-color: #0284c7;"
            "  background-color: #14161a;"
            "}"
            "QFrame#scanCard QLabel {"
            "  background-color: transparent;"
            "  border: none;"
            "}"
            "QFrame#scanCard QPushButton#primaryButton {"
            "  padding: 6px 8px;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "  min-height: 22px;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 14, 10, 14)
        card_layout.setSpacing(10)

        # Vector Icon with clear transparent background (scaled to 40 for optimal card balance)
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background-color: transparent; border: none;")
        pix = IconFactory.get_pixmap(icon_name, "#38bdf8", 40)
        icon_lbl.setPixmap(pix)
        card_layout.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lbl.setStyleSheet("color: #38bdf8; background-color: transparent; border: none;")
        card_layout.addWidget(title_lbl)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #949ba4; font-size: 12px; line-height: 1.3; background-color: transparent; border: none;")
        desc_lbl.setMinimumHeight(56)
        card_layout.addWidget(desc_lbl)

        card_layout.addStretch()

        # Sky Blue Button with Pure White text & vector icon (13px icon for plenty of text space)
        btn = QPushButton(btn_text)
        btn.setObjectName("primaryButton")
        btn.setIcon(IconFactory.get_icon(icon_name, "#ffffff", 13))
        btn.setIconSize(QSize(13, 13))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        card_layout.addWidget(btn)

        return card

    def on_quick_scan_clicked(self):
        targets = self.scanner.get_quick_scan_paths()
        dlg = ScanDialog(self, ScanType.QUICK_SCAN, targets)
        dlg.exec()
        self.refresh_quarantine_table()

    def on_full_scan_clicked(self):
        targets = self.scanner.get_system_drives()
        dlg = ScanDialog(self, ScanType.FULL_SCAN, targets)
        dlg.exec()
        self.refresh_quarantine_table()

    def on_custom_scan_clicked(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if folder:
            dlg = ScanDialog(self, ScanType.CUSTOM_SCAN, [folder])
            dlg.exec()
            self.refresh_quarantine_table()

    def on_memory_scan_clicked(self):
        temp_dir = os.getenv("TEMP", str(Path.home()))
        dlg = ScanDialog(self, ScanType.MEMORY_SCAN, [temp_dir])
        dlg.exec()
        self.refresh_quarantine_table()

    # --- TAB 3: QUARANTINE ---
    def setup_quarantine_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("Quarantine Vault")
        header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.setStyleSheet("color: #38bdf8;")
        layout.addWidget(header)

        # Table - strictly non-editable, full row selection with high contrast
        self.quarantine_table = QTableWidget(0, 5)
        self.quarantine_table.setHorizontalHeaderLabels([
            "File Name", "Threat Name", "Original Location", "Date Quarantined", "Size"
        ])
        self.quarantine_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.quarantine_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.quarantine_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.quarantine_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.quarantine_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.quarantine_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.quarantine_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.quarantine_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.quarantine_table)

        # Actions Row with Semantic Buttons & Vector Icons
        action_layout = QHBoxLayout()

        self.refresh_vault_btn = QPushButton("Refresh Vault")
        self.refresh_vault_btn.setObjectName("secondaryButton")
        self.refresh_vault_btn.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
        self.refresh_vault_btn.setIconSize(QSize(14, 14))
        self.refresh_vault_btn.clicked.connect(self.refresh_quarantine_table)
        action_layout.addWidget(self.refresh_vault_btn)

        action_layout.addStretch()

        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setObjectName("successButton")
        self.restore_btn.setIcon(IconFactory.get_icon("restore", "#ffffff", 14))
        self.restore_btn.setIconSize(QSize(14, 14))
        self.restore_btn.clicked.connect(self.on_restore_selected)
        action_layout.addWidget(self.restore_btn)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setIcon(IconFactory.get_icon("delete", "#ffffff", 14))
        self.delete_btn.setIconSize(QSize(14, 14))
        self.delete_btn.clicked.connect(self.on_delete_selected)
        action_layout.addWidget(self.delete_btn)

        self.clear_vault_btn = QPushButton("Empty Vault")
        self.clear_vault_btn.setObjectName("dangerButton")
        self.clear_vault_btn.setIcon(IconFactory.get_icon("delete", "#ffffff", 14))
        self.clear_vault_btn.setIconSize(QSize(14, 14))
        self.clear_vault_btn.clicked.connect(self.on_empty_vault_clicked)
        action_layout.addWidget(self.clear_vault_btn)

        layout.addLayout(action_layout)
        self.tabs.addTab(tab, IconFactory.get_icon("delete", "#38bdf8", 14), "  Quarantine  ")

    def refresh_quarantine_table(self):
        items = self.quarantine_mgr.list_items()
        self.quarantine_table.setRowCount(0)

        for row, item in enumerate(items):
            self.quarantine_table.insertRow(row)

            # Store item id on column 0 item
            name_item = QTableWidgetItem(item.filename)
            name_item.setData(Qt.UserRole, item.item_id)

            threat_item = QTableWidgetItem(item.threat_name)
            threat_item.setForeground(Qt.red)

            path_item = QTableWidgetItem(item.original_path)
            date_item = QTableWidgetItem(item.quarantine_date)

            size_kb = round(item.file_size_bytes / 1024, 1)
            size_item = QTableWidgetItem(f"{size_kb} KB")

            # Explicitly strip editable flag so cell editing is completely stopped
            for col_item in [name_item, threat_item, path_item, date_item, size_item]:
                col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)

            self.quarantine_table.setItem(row, 0, name_item)
            self.quarantine_table.setItem(row, 1, threat_item)
            self.quarantine_table.setItem(row, 2, path_item)
            self.quarantine_table.setItem(row, 3, date_item)
            self.quarantine_table.setItem(row, 4, size_item)

    def on_restore_selected(self):
        row = self.quarantine_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Restore", "Please select an item to restore.")
            return

        item_id = self.quarantine_table.item(row, 0).data(Qt.UserRole)
        filename = self.quarantine_table.item(row, 0).text()

        confirm = QMessageBox.question(
            self,
            "Confirm Restore",
            f"Are you sure you want to restore '{filename}' back to its original location?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            success, msg = self.quarantine_mgr.restore_item(item_id)
            if success:
                QMessageBox.information(self, "Restore Success", msg)
            else:
                QMessageBox.warning(self, "Restore Failed", msg)
            self.refresh_quarantine_table()

    def on_delete_selected(self):
        row = self.quarantine_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Delete", "Please select an item to delete.")
            return

        item_id = self.quarantine_table.item(row, 0).data(Qt.UserRole)
        filename = self.quarantine_table.item(row, 0).text()

        confirm = QMessageBox.question(
            self,
            "Confirm Permanent Deletion",
            f"Are you sure you want to permanently delete '{filename}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.quarantine_mgr.delete_item(item_id)
            self.refresh_quarantine_table()

    def on_empty_vault_clicked(self):
        confirm = QMessageBox.question(
            self,
            "Empty Vault",
            "Permanently delete all quarantined threats? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            count = self.quarantine_mgr.clear_vault()
            QMessageBox.information(self, "Vault Cleared", f"Deleted {count} item(s) from quarantine.")
            self.refresh_quarantine_table()

    # --- TAB 4: SETTINGS ---
    def setup_settings_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # 2-Column Responsive Grid Layout for tight space utilization
        grid = QGridLayout()
        grid.setSpacing(12)

        # Box 1: Protection & Preferences
        pref_group = QGroupBox("Protection Preferences && Threat Remediation")
        pref_layout = QVBoxLayout(pref_group)
        pref_layout.setContentsMargins(12, 12, 12, 12)
        pref_layout.setSpacing(8)

        self.chk_realtime = QCheckBox("Enable Real-Time Guard (Watches Downloads && Desktop)")
        self.chk_realtime.setChecked(self.config.get("preferences", "real_time_protection", default=False))
        self.chk_realtime.toggled.connect(self.on_realtime_toggled)
        pref_layout.addWidget(self.chk_realtime)

        self.chk_autoupdates = QCheckBox("Automatic Daily Virus Database Updates")
        self.chk_autoupdates.setChecked(self.config.get("preferences", "auto_updates", default=True))
        pref_layout.addWidget(self.chk_autoupdates)

        self.chk_notifications = QCheckBox("Show Desktop Notifications on Threat Detection")
        self.chk_notifications.setChecked(self.config.get("preferences", "notifications", default=True))
        pref_layout.addWidget(self.chk_notifications)

        self.chk_close_to_tray = QCheckBox("Minimize to system tray when closing window")
        self.chk_close_to_tray.setChecked(self.config.get("preferences", "close_to_tray", default=True))
        pref_layout.addWidget(self.chk_close_to_tray)

        os_startup_label = "Windows startup" if sys.platform == "win32" else "system login / startup"
        self.chk_autostart = QCheckBox(f"Start pyEGClamUI minimized on {os_startup_label}")
        self.chk_autostart.setChecked(AutoStartManager.is_enabled())
        if not AutoStartManager.is_supported():
            self.chk_autostart.setEnabled(False)
        pref_layout.addWidget(self.chk_autostart)

        # Action on threat
        action_label = QLabel("Action to take when a threat is detected:")
        action_label.setStyleSheet("margin-top: 4px; font-weight: bold; color: #38bdf8;")
        pref_layout.addWidget(action_label)

        self.radio_group = QButtonGroup(self)
        self.radio_report = QRadioButton("Report Only (Do not modify file)")
        self.radio_trash = QRadioButton("Move to Trash / Delete")
        self.radio_quarantine = QRadioButton("Move to Quarantine Vault (Recommended)")

        self.radio_group.addButton(self.radio_report, 1)
        self.radio_group.addButton(self.radio_trash, 2)
        self.radio_group.addButton(self.radio_quarantine, 3)

        action_pref = self.config.get("preferences", "action_on_threat", default=3)
        if action_pref == 1:
            self.radio_report.setChecked(True)
        elif action_pref == 2:
            self.radio_trash.setChecked(True)
        else:
            self.radio_quarantine.setChecked(True)

        pref_layout.addWidget(self.radio_report)
        pref_layout.addWidget(self.radio_trash)
        pref_layout.addWidget(self.radio_quarantine)
        pref_layout.addStretch()

        grid.addWidget(pref_group, 0, 0)

        # Box 2: Scan Limits & Archive Handling
        scan_group = QGroupBox("Scan Limits && Archive Handling")
        scan_layout = QVBoxLayout(scan_group)
        scan_layout.setContentsMargins(12, 12, 12, 12)
        scan_layout.setSpacing(8)

        # Max file size
        row_size = QHBoxLayout()
        row_size.addWidget(QLabel("Do not scan files larger than:"))
        self.spin_max_size = QSpinBox()
        self.spin_max_size.setRange(1, 4096)
        self.spin_max_size.setSuffix(" MB")
        self.spin_max_size.setValue(self.config.get("scan_settings", "max_file_size_mb", default=50))
        row_size.addWidget(self.spin_max_size)
        scan_layout.addLayout(row_size)

        # Archives
        self.chk_archives = QCheckBox("Inspect compressed archives (.zip, .rar, .tar, .7z)")
        self.chk_archives.setChecked(self.config.get("scan_settings", "extract_archives", default=True))
        scan_layout.addWidget(self.chk_archives)

        # Max extract size
        row_ext_size = QHBoxLayout()
        row_ext_size.addWidget(QLabel("Max uncompressed archive size:"))
        self.spin_max_extract_size = QSpinBox()
        self.spin_max_extract_size.setRange(10, 8192)
        self.spin_max_extract_size.setSuffix(" MB")
        self.spin_max_extract_size.setValue(self.config.get("scan_settings", "max_extract_size_mb", default=100))
        row_ext_size.addWidget(self.spin_max_extract_size)
        scan_layout.addLayout(row_ext_size)

        # Max files count
        row_files = QHBoxLayout()
        row_files.addWidget(QLabel("Max files to extract from archive:"))
        self.spin_max_extract_files = QSpinBox()
        self.spin_max_extract_files.setRange(10, 100000)
        self.spin_max_extract_files.setValue(self.config.get("scan_settings", "max_extract_files", default=1000))
        row_files.addWidget(self.spin_max_extract_files)
        scan_layout.addLayout(row_files)

        # Max recursion
        row_rec = QHBoxLayout()
        row_rec.addWidget(QLabel("Max nested sub-archive depth:"))
        self.spin_max_recursion = QSpinBox()
        self.spin_max_recursion.setRange(1, 100)
        self.spin_max_recursion.setValue(self.config.get("scan_settings", "max_recursion", default=15))
        row_rec.addWidget(self.spin_max_recursion)
        scan_layout.addLayout(row_rec)

        scan_layout.addStretch()
        grid.addWidget(scan_group, 0, 1)

        # Box 3: Extension Filtering
        ext_group = QGroupBox("File Extension Filtering")
        ext_layout = QVBoxLayout(ext_group)
        ext_layout.setContentsMargins(12, 12, 12, 12)
        ext_layout.setSpacing(6)

        ext_layout.addWidget(QLabel("Exclude file extensions from scan (comma-separated):"))
        self.txt_exclude_ext = QLineEdit()
        self.txt_exclude_ext.setPlaceholderText("e.g. iso, vmdk, vdi, mp3, mp4")
        excludes = self.config.get("scan_settings", "exclude_extensions", default=[])
        self.txt_exclude_ext.setText(", ".join(excludes) if isinstance(excludes, list) else str(excludes))
        ext_layout.addWidget(self.txt_exclude_ext)

        ext_layout.addWidget(QLabel("Scan only specific extensions (whitelist, empty = scan all):"))
        self.txt_include_ext = QLineEdit()
        self.txt_include_ext.setPlaceholderText("e.g. exe, dll, bat, cmd, docm (leave empty to scan all)")
        includes = self.config.get("scan_settings", "include_only_extensions", default=[])
        self.txt_include_ext.setText(", ".join(includes) if isinstance(includes, list) else str(includes))
        ext_layout.addWidget(self.txt_include_ext)

        ext_layout.addStretch()
        grid.addWidget(ext_group, 1, 0)

        # Box 4: ClamAV Engine Configuration && Service Linkage
        engine_group = QGroupBox("ClamAV Engine Configuration && Service Linkage")
        engine_layout = QVBoxLayout(engine_group)
        engine_layout.setContentsMargins(14, 14, 14, 14)
        engine_layout.setSpacing(10)

        engine_desc = QLabel(
            "Manage your ClamAV backend engine, verify daemon connectivity, or run the universal setup wizard."
        )
        engine_desc.setWordWrap(True)
        engine_desc.setStyleSheet("color: #949ba4; font-size: 12px;")
        engine_layout.addWidget(engine_desc)

        # Status summary label
        self.lbl_settings_engine_status = QLabel()
        self.lbl_settings_engine_status.setStyleSheet("color: #e0e2e8; font-size: 12px; font-weight: 500;")
        clamscan_active = self.detector.inspect().get("clamscan_path") or "Not configured"
        self.lbl_settings_engine_status.setText(f"Active ClamScan: {clamscan_active}")
        engine_layout.addWidget(self.lbl_settings_engine_status)

        # Wizard trigger button
        self.btn_reconfigure_engine = QPushButton("Configure Engine / Run Setup Wizard...")
        self.btn_reconfigure_engine.setObjectName("secondaryButton")
        self.btn_reconfigure_engine.setIcon(IconFactory.get_icon("browse", "#ffffff", 14))
        self.btn_reconfigure_engine.setIconSize(QSize(14, 14))
        self.btn_reconfigure_engine.setCursor(Qt.PointingHandCursor)
        self.btn_reconfigure_engine.clicked.connect(self.on_reconfigure_engine_clicked)
        engine_layout.addWidget(self.btn_reconfigure_engine)

        # clamd socket / host
        row_socket = QHBoxLayout()
        row_socket.addWidget(QLabel("clamd Socket / Host:"))
        self.txt_clamd_socket = QLineEdit()
        self.txt_clamd_socket.setPlaceholderText("127.0.0.1:3310 or /var/run/clamav/clamd.ctl")
        socket_val = self.config.get("scan_settings", "clamd_unix_socket", default="") or ""
        if not socket_val:
            host = self.config.get("scan_settings", "clamd_tcp_host", default="127.0.0.1")
            port = self.config.get("scan_settings", "clamd_tcp_port", default=3310)
            socket_val = f"{host}:{port}"
        self.txt_clamd_socket.setText(socket_val)
        row_socket.addWidget(self.txt_clamd_socket)
        engine_layout.addLayout(row_socket)

        # Hidden or programmatic binary line edits for backward compatibility
        self.txt_clamscan_path = QLineEdit()
        self.txt_clamscan_path.setVisible(False)
        self.txt_clamscan_path.setText(self.config.get("scan_settings", "custom_clamscan_path", default="") or "")

        self.txt_clamd_path = QLineEdit()
        self.txt_clamd_path.setVisible(False)
        self.txt_clamd_path.setText(self.config.get("scan_settings", "custom_clamd_path", default="") or "")

        self.txt_freshclam_path = QLineEdit()
        self.txt_freshclam_path.setVisible(False)
        self.txt_freshclam_path.setText(self.config.get("scan_settings", "custom_freshclam_path", default="") or "")

        engine_layout.addWidget(self.txt_clamscan_path)
        engine_layout.addWidget(self.txt_clamd_path)
        engine_layout.addWidget(self.txt_freshclam_path)

        engine_layout.addStretch()
        grid.addWidget(engine_group, 1, 1)

        # Box 5: Monitored Folders (Strictly 2 Folders Max)
        folder_group = QGroupBox("Real-Time Monitored Folders (Max 2)")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)

        folder_desc = QLabel(
            "For optimal real-time performance, exactly two critical folders are monitored. "
            "Default: Desktop and Downloads."
        )
        folder_desc.setWordWrap(True)
        folder_desc.setStyleSheet("color: #949ba4; font-size: 11px;")
        folder_layout.addWidget(folder_desc)

        monitor_dirs = self.config.get("scan_settings", "monitor_dirs", default=[])
        home_path = Path.home()
        slot1_val = monitor_dirs[0] if len(monitor_dirs) > 0 and monitor_dirs[0] else str(home_path / "Desktop")
        slot2_val = monitor_dirs[1] if len(monitor_dirs) > 1 and monitor_dirs[1] else str(home_path / "Downloads")

        # Slot 1
        row_slot1 = QHBoxLayout()
        row_slot1.addWidget(QLabel("Folder 1:"))
        self.txt_watch_slot1 = QLineEdit()
        self.txt_watch_slot1.setPlaceholderText(str(home_path / "Desktop"))
        self.txt_watch_slot1.setText(slot1_val)
        self.btn_browse_slot1 = QPushButton("Browse...")
        self.btn_browse_slot1.setObjectName("secondaryButton")
        self.btn_browse_slot1.clicked.connect(self.on_browse_watch_slot1)
        row_slot1.addWidget(self.txt_watch_slot1, 1)
        row_slot1.addWidget(self.btn_browse_slot1)
        folder_layout.addLayout(row_slot1)

        # Slot 2
        row_slot2 = QHBoxLayout()
        row_slot2.addWidget(QLabel("Folder 2:"))
        self.txt_watch_slot2 = QLineEdit()
        self.txt_watch_slot2.setPlaceholderText(str(home_path / "Downloads"))
        self.txt_watch_slot2.setText(slot2_val)
        self.btn_browse_slot2 = QPushButton("Browse...")
        self.btn_browse_slot2.setObjectName("secondaryButton")
        self.btn_browse_slot2.clicked.connect(self.on_browse_watch_slot2)
        row_slot2.addWidget(self.txt_watch_slot2, 1)
        row_slot2.addWidget(self.btn_browse_slot2)
        folder_layout.addLayout(row_slot2)

        # Reset button
        self.btn_reset_folders = QPushButton("Reset to Default Folders")
        self.btn_reset_folders.setObjectName("secondaryButton")
        self.btn_reset_folders.clicked.connect(self.on_reset_watch_folders_clicked)
        folder_layout.addWidget(self.btn_reset_folders)

        folder_layout.addStretch()
        grid.addWidget(folder_group, 2, 0)

        # Box 6: User Profile && Diagnostics Telemetry (Opt-In)
        telemetry_group = QGroupBox("User Profile && Diagnostics Telemetry (Opt-In)")
        telemetry_layout = QVBoxLayout(telemetry_group)
        telemetry_layout.setContentsMargins(12, 12, 12, 12)
        telemetry_layout.setSpacing(8)

        profile_row = QHBoxLayout()
        self.txt_user_id = QLineEdit()
        self.txt_user_id.setPlaceholderText("Name, Email, or Guest ID")
        self.txt_user_id.setToolTip("Optional identifier, email, or guest ID for diagnostics and issue reporting")
        current_user_id = (
            self.config.get("user_profile", "user_id", default="")
            or self.telemetry_mgr.get_or_create_user_id()
        )
        self.txt_user_id.setText(current_user_id)
        self.btn_gen_guest = QPushButton("New Guest ID")
        self.btn_gen_guest.setObjectName("secondaryButton")
        self.btn_gen_guest.clicked.connect(self.on_generate_guest_id_clicked)
        profile_row.addWidget(self.txt_user_id, 1)
        profile_row.addWidget(self.btn_gen_guest)
        telemetry_layout.addLayout(profile_row)

        self.chk_telemetry_master = QCheckBox("Enable Anonymous Diagnostics & Crash Telemetry")
        is_telem_enabled = self.config.get("telemetry", "enabled", default=False)
        self.chk_telemetry_master.setChecked(is_telem_enabled)
        self.chk_telemetry_master.toggled.connect(self.on_telemetry_master_toggled)
        telemetry_layout.addWidget(self.chk_telemetry_master)

        # Granular checkboxes container
        self.telem_sub_widget = QWidget()
        telem_sub_layout = QVBoxLayout(self.telem_sub_widget)
        telem_sub_layout.setContentsMargins(16, 0, 0, 0)
        telem_sub_layout.setSpacing(4)

        self.chk_share_os = QCheckBox("Share OS platform and architecture")
        self.chk_share_os.setChecked(self.config.get("telemetry", "share_os_info", default=True))
        telem_sub_layout.addWidget(self.chk_share_os)

        self.chk_share_clamav = QCheckBox("Share ClamAV engine & signature version")
        self.chk_share_clamav.setChecked(self.config.get("telemetry", "share_clamav_version", default=True))
        telem_sub_layout.addWidget(self.chk_share_clamav)

        self.chk_share_scan_stats = QCheckBox("Share protection & threat count metrics")
        self.chk_share_scan_stats.setChecked(self.config.get("telemetry", "share_scan_stats", default=True))
        telem_sub_layout.addWidget(self.chk_share_scan_stats)

        self.telem_sub_widget.setEnabled(is_telem_enabled)
        telemetry_layout.addWidget(self.telem_sub_widget)

        # Telemetry Action Buttons
        telem_btns = QHBoxLayout()
        self.btn_preview_telem = QPushButton("Preview Data")
        self.btn_preview_telem.setObjectName("secondaryButton")
        self.btn_preview_telem.clicked.connect(self.on_preview_telemetry_clicked)
        telem_btns.addWidget(self.btn_preview_telem)

        self.btn_test_telem = QPushButton("Send Test Report")
        self.btn_test_telem.setObjectName("secondaryButton")
        self.btn_test_telem.clicked.connect(self.on_send_test_telemetry_clicked)
        telem_btns.addWidget(self.btn_test_telem)
        telemetry_layout.addLayout(telem_btns)

        telemetry_layout.addStretch()
        grid.addWidget(telemetry_group, 2, 1)

        layout.addLayout(grid)

        # Linux Desktop Integration (if Linux)
        if LinuxDesktopManager.is_linux():
            desktop_group = QGroupBox("Linux Desktop Integration")
            desktop_layout = QHBoxLayout(desktop_group)
            desktop_layout.setContentsMargins(12, 10, 12, 10)
            installed = LinuxDesktopManager.is_installed()
            self.lbl_desktop_status = QLabel(
                "Installed in Application Menu" if installed else "Not installed in Application Menu"
            )
            self.btn_toggle_desktop = QPushButton(
                "Uninstall Menu Entry" if installed else "Add to Application Menu"
            )
            self.btn_toggle_desktop.clicked.connect(self.on_toggle_desktop_entry)
            desktop_layout.addWidget(self.lbl_desktop_status)
            desktop_layout.addStretch()
            desktop_layout.addWidget(self.btn_toggle_desktop)
            layout.addWidget(desktop_group)

        # Bottom Buttons Bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_reset_defaults = QPushButton("Reset Defaults")
        self.btn_reset_defaults.setObjectName("secondaryButton")
        self.btn_reset_defaults.setIcon(IconFactory.get_icon("defaults", "#ffffff", 14))
        self.btn_reset_defaults.setIconSize(QSize(14, 14))
        self.btn_reset_defaults.setCursor(Qt.PointingHandCursor)
        self.btn_reset_defaults.clicked.connect(self.on_reset_defaults_clicked)
        btn_layout.addWidget(self.btn_reset_defaults)

        self.btn_refresh_settings = QPushButton("Reload")
        self.btn_refresh_settings.setObjectName("secondaryButton")
        self.btn_refresh_settings.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
        self.btn_refresh_settings.setIconSize(QSize(14, 14))
        self.btn_refresh_settings.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_settings.clicked.connect(self.on_refresh_settings_clicked)
        btn_layout.addWidget(self.btn_refresh_settings)

        btn_layout.addStretch()

        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setObjectName("primaryButton")
        self.btn_save_settings.setIcon(IconFactory.get_icon("save", "#ffffff", 14))
        self.btn_save_settings.setIconSize(QSize(14, 14))
        self.btn_save_settings.setCursor(Qt.PointingHandCursor)
        self.btn_save_settings.clicked.connect(self.on_save_settings_clicked)
        btn_layout.addWidget(self.btn_save_settings)

        scroll.setWidget(content)
        tab_layout.addWidget(scroll, 1)

        # Pinned bottom action bar outside scroll area
        btn_bar = QWidget()
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(16, 8, 16, 12)
        btn_bar_layout.addLayout(btn_layout)
        tab_layout.addWidget(btn_bar)

        self.tabs.addTab(tab, IconFactory.get_icon("settings", "#38bdf8", 14), "  Settings  ")

    def on_reconfigure_engine_clicked(self):
        dlg = ClamSetupDialog(self)
        if dlg.exec():
            audit = self.detector.inspect()
            clamscan_path = audit.get("clamscan_path") or "Not configured"
            if hasattr(self, "lbl_settings_engine_status"):
                self.lbl_settings_engine_status.setText(f"Active ClamScan: {clamscan_path}")
            self.txt_clamscan_path.setText(self.config.get("scan_settings", "custom_clamscan_path", "") or "")
            self.txt_clamd_path.setText(self.config.get("scan_settings", "custom_clamd_path", "") or "")
            self.txt_freshclam_path.setText(self.config.get("scan_settings", "custom_freshclam_path", "") or "")
            self.refresh_status()

    def on_browse_clamscan(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select clamscan executable", "", "Executables (*.exe);;All Files (*)")
        if file:
            self.txt_clamscan_path.setText(file)

    def on_browse_clamd(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select clamd executable", "", "Executables (*.exe);;All Files (*)")
        if file:
            self.txt_clamd_path.setText(file)

    def on_browse_freshclam(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select freshclam executable", "", "Executables (*.exe);;All Files (*)")
        if file:
            self.txt_freshclam_path.setText(file)

    def on_browse_watch_slot1(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder 1 to Monitor", self.txt_watch_slot1.text())
        if folder:
            self.txt_watch_slot1.setText(folder)

    def on_browse_watch_slot2(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder 2 to Monitor", self.txt_watch_slot2.text())
        if folder:
            self.txt_watch_slot2.setText(folder)

    def on_reset_watch_folders_clicked(self):
        home = Path.home()
        self.txt_watch_slot1.setText(str(home / "Desktop"))
        self.txt_watch_slot2.setText(str(home / "Downloads"))

    def on_generate_guest_id_clicked(self):
        self.txt_user_id.setText(generate_guest_id())
        self.btn_gen_guest.setEnabled(False)
        self.btn_gen_guest.setToolTip("Guest ID already generated")

    def on_telemetry_master_toggled(self, checked: bool):
        self.telem_sub_widget.setEnabled(checked)

    def on_preview_telemetry_clicked(self):
        current_user = self.txt_user_id.text().strip() or self.telemetry_mgr.get_or_create_user_id()
        self.config.set("user_profile", "user_id", current_user)
        self.config.set("telemetry", "share_os_info", self.chk_share_os.isChecked())
        self.config.set("telemetry", "share_clamav_version", self.chk_share_clamav.isChecked())
        self.config.set("telemetry", "share_scan_stats", self.chk_share_scan_stats.isChecked())

        preview_json = self.telemetry_mgr.get_preview_payload()

        dlg = QDialog(self)
        dlg.setWindowTitle("Telemetry Data Preview")
        dlg.resize(520, 420)
        apply_dark_titlebar(dlg)

        layout = QVBoxLayout(dlg)
        lbl = QLabel(
            "Below is the exact JSON data that will be transmitted to the Firestore database.\n"
            "Only checked/consented items are included:"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        txt_view = QTextEdit()
        txt_view.setReadOnly(True)
        txt_view.setPlainText(preview_json)
        layout.addWidget(txt_view)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        dlg.exec()

    def on_send_test_telemetry_clicked(self):
        if not self.chk_telemetry_master.isChecked():
            QMessageBox.warning(
                self,
                "Telemetry Disabled",
                "Telemetry is currently disabled. Please check 'Enable Anonymous Diagnostics & Crash Telemetry' first."
            )
            return

        self.on_save_settings_clicked()

        self.btn_test_telem.setEnabled(False)
        self.btn_test_telem.setText("Sending...")

        def on_done(success: bool, msg: str):
            def update_ui():
                self.btn_test_telem.setEnabled(True)
                self.btn_test_telem.setText("Send Test Report")
                if success:
                    QMessageBox.information(self, "Telemetry Status", f"Success: {msg}")
                else:
                    QMessageBox.warning(self, "Telemetry Status", f"Submission Result: {msg}")
            QTimer.singleShot(0, update_ui)

        self.telemetry_mgr.send_telemetry_async(on_complete=on_done)

    def on_reset_defaults_clicked(self):
        confirm = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all settings to recommended defaults?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            defaults = Config.DEFAULT_CONFIG
            pref = defaults["preferences"]
            scan = defaults["scan_settings"]

            self.chk_realtime.setChecked(pref.get("real_time_protection", False))
            self.chk_autoupdates.setChecked(pref.get("auto_updates", True))
            self.chk_notifications.setChecked(pref.get("notifications", True))
            self.chk_close_to_tray.setChecked(pref.get("close_to_tray", True))
            self.chk_autostart.setChecked(pref.get("start_with_system", False))
            self.radio_quarantine.setChecked(True)

            self.spin_max_size.setValue(scan.get("max_file_size_mb", 50))
            self.chk_archives.setChecked(scan.get("extract_archives", True))
            self.spin_max_extract_size.setValue(scan.get("max_extract_size_mb", 100))
            self.spin_max_extract_files.setValue(scan.get("max_extract_files", 1000))
            self.spin_max_recursion.setValue(scan.get("max_recursion", 15))

            excludes = scan.get("exclude_extensions", [])
            self.txt_exclude_ext.setText(", ".join(excludes) if isinstance(excludes, list) else str(excludes))
            includes = scan.get("include_only_extensions", [])
            self.txt_include_ext.setText(", ".join(includes) if isinstance(includes, list) else str(includes))

            self.txt_clamscan_path.setText("")
            self.txt_clamd_path.setText("")
            self.txt_freshclam_path.setText("")
            self.txt_clamd_socket.setText("127.0.0.1:3310")

            home = Path.home()
            self.txt_watch_slot1.setText(str(home / "Desktop"))
            self.txt_watch_slot2.setText(str(home / "Downloads"))

            self.chk_telemetry_master.setChecked(False)
            self.chk_share_os.setChecked(True)
            self.chk_share_clamav.setChecked(True)
            self.chk_share_scan_stats.setChecked(True)

            if hasattr(self, "lbl_settings_engine_status"):
                audit = self.detector.inspect()
                clamscan_path = audit.get("clamscan_path") or "Not configured"
                self.lbl_settings_engine_status.setText(f"Active ClamScan: {clamscan_path}")

            self.on_save_settings_clicked()

    def on_refresh_settings_clicked(self):
        pref = self.config.get("preferences", default={})
        scan = self.config.get("scan_settings", default={})

        self.chk_realtime.setChecked(pref.get("real_time_protection", False))
        self.chk_autoupdates.setChecked(pref.get("auto_updates", True))
        self.chk_notifications.setChecked(pref.get("notifications", True))
        self.chk_close_to_tray.setChecked(pref.get("close_to_tray", True))
        self.chk_autostart.setChecked(AutoStartManager.is_enabled())

        action_pref = pref.get("action_on_threat", 3)
        if action_pref == 1:
            self.radio_report.setChecked(True)
        elif action_pref == 2:
            self.radio_trash.setChecked(True)
        else:
            self.radio_quarantine.setChecked(True)

        self.spin_max_size.setValue(scan.get("max_file_size_mb", 50))
        self.chk_archives.setChecked(scan.get("extract_archives", True))
        self.spin_max_extract_size.setValue(scan.get("max_extract_size_mb", 100))
        self.spin_max_extract_files.setValue(scan.get("max_extract_files", 1000))
        self.spin_max_recursion.setValue(scan.get("max_recursion", 15))

        excludes = scan.get("exclude_extensions", [])
        self.txt_exclude_ext.setText(", ".join(excludes) if isinstance(excludes, list) else str(excludes))
        includes = scan.get("include_only_extensions", [])
        self.txt_include_ext.setText(", ".join(includes) if isinstance(includes, list) else str(includes))

        self.txt_clamscan_path.setText(scan.get("custom_clamscan_path", "") or "")
        self.txt_clamd_path.setText(scan.get("custom_clamd_path", "") or "")
        self.txt_freshclam_path.setText(scan.get("custom_freshclam_path", "") or "")

        socket_val = scan.get("clamd_unix_socket", "") or ""
        if not socket_val:
            host = scan.get("clamd_tcp_host", "127.0.0.1")
            port = scan.get("clamd_tcp_port", 3310)
            socket_val = f"{host}:{port}"
        self.txt_clamd_socket.setText(socket_val)

        monitor_dirs = scan.get("monitor_dirs", [])
        home = Path.home()
        slot1_default = str(home / "Desktop")
        slot2_default = str(home / "Downloads")
        self.txt_watch_slot1.setText(monitor_dirs[0] if len(monitor_dirs) > 0 and monitor_dirs[0] else slot1_default)
        self.txt_watch_slot2.setText(monitor_dirs[1] if len(monitor_dirs) > 1 and monitor_dirs[1] else slot2_default)

        profile = self.config.get("user_profile", default={})
        self.txt_user_id.setText(profile.get("user_id", "") or self.telemetry_mgr.get_or_create_user_id())

        telem = self.config.get("telemetry", default={})
        self.chk_telemetry_master.setChecked(telem.get("enabled", False))
        self.chk_share_os.setChecked(telem.get("share_os_info", True))
        self.chk_share_clamav.setChecked(telem.get("share_clamav_version", True))
        self.chk_share_scan_stats.setChecked(telem.get("share_scan_stats", True))

        if hasattr(self, "lbl_settings_engine_status"):
            audit = self.detector.inspect()
            clamscan_path = audit.get("clamscan_path") or "Not configured"
            self.lbl_settings_engine_status.setText(f"Active ClamScan: {clamscan_path}")

    def on_toggle_desktop_entry(self):
        if LinuxDesktopManager.is_installed():
            success, msg = LinuxDesktopManager.uninstall()
        else:
            success, msg = LinuxDesktopManager.install()

        if success:
            QMessageBox.information(self, "Desktop Integration", msg)
        else:
            QMessageBox.warning(self, "Desktop Integration", msg)

        installed = LinuxDesktopManager.is_installed()
        if hasattr(self, "lbl_desktop_status"):
            self.lbl_desktop_status.setText(
                "Installed in Application Menu" if installed else "Not installed in Application Menu"
            )
        if hasattr(self, "btn_toggle_desktop"):
            self.btn_toggle_desktop.setText(
                "Uninstall Menu Entry" if installed else "Add to Application Menu"
            )

    def on_realtime_toggled(self, checked: bool):
        if checked:
            success = self.guard.start()
            if not success:
                if os.getenv("QT_QPA_PLATFORM") != "offscreen" and "pytest" not in sys.modules:
                    QMessageBox.warning(self, "Real-Time Guard", "Failed to start file guard. Check folder permissions.")
                self.chk_realtime.setChecked(False)
        else:
            self.guard.stop()

        if self.tray and hasattr(self.tray, "set_protection_state"):
            self.tray.set_protection_state(self.guard.is_active)

        self.refresh_status()

    def on_save_settings_clicked(self):
        self.config.set("preferences", "real_time_protection", self.chk_realtime.isChecked())
        self.config.set("preferences", "auto_updates", self.chk_autoupdates.isChecked())
        self.config.set("preferences", "notifications", self.chk_notifications.isChecked())
        self.config.set("preferences", "close_to_tray", self.chk_close_to_tray.isChecked())
        self.config.set("preferences", "action_on_threat", self.radio_group.checkedId())
        self.config.set("scan_settings", "max_file_size_mb", self.spin_max_size.value())
        self.config.set("scan_settings", "extract_archives", self.chk_archives.isChecked())
        self.config.set("scan_settings", "max_extract_size_mb", self.spin_max_extract_size.value())
        self.config.set("scan_settings", "max_extract_files", self.spin_max_extract_files.value())
        self.config.set("scan_settings", "max_recursion", self.spin_max_recursion.value())

        # Extensions
        raw_excludes = [x.strip().lstrip(".") for x in self.txt_exclude_ext.text().split(",") if x.strip()]
        self.config.set("scan_settings", "exclude_extensions", raw_excludes)

        raw_includes = [x.strip().lstrip(".") for x in self.txt_include_ext.text().split(",") if x.strip()]
        self.config.set("scan_settings", "include_only_extensions", raw_includes)

        # Paths
        self.config.set("scan_settings", "custom_clamscan_path", self.txt_clamscan_path.text().strip())
        self.config.set("scan_settings", "custom_clamd_path", self.txt_clamd_path.text().strip())
        self.config.set("scan_settings", "custom_freshclam_path", self.txt_freshclam_path.text().strip())

        socket_txt = self.txt_clamd_socket.text().strip()
        if ":" in socket_txt:
            parts = socket_txt.split(":")
            self.config.set("scan_settings", "clamd_tcp_host", parts[0])
            try:
                self.config.set("scan_settings", "clamd_tcp_port", int(parts[1]))
            except ValueError:
                pass
        elif socket_txt:
            self.config.set("scan_settings", "clamd_unix_socket", socket_txt)

        # Monitored Folders (Max 2)
        slot1 = self.txt_watch_slot1.text().strip()
        slot2 = self.txt_watch_slot2.text().strip()
        watch_dirs = [d for d in [slot1, slot2] if d]
        self.config.set("scan_settings", "monitor_dirs", watch_dirs[:2])
        if self.guard:
            self.guard.update_watch_directories(slot1, slot2)

        # User Profile & Telemetry
        user_val = self.txt_user_id.text().strip() or self.telemetry_mgr.get_or_create_user_id()
        self.config.set("user_profile", "user_id", user_val)
        if "@" in user_val:
            self.config.set("user_profile", "email", user_val)
            self.config.set("user_profile", "is_anonymous", False)
        else:
            self.config.set("user_profile", "display_name", user_val)
            self.config.set("user_profile", "is_anonymous", user_val.startswith("Guest"))

        self.config.set("telemetry", "enabled", self.chk_telemetry_master.isChecked())
        self.config.set("telemetry", "share_os_info", self.chk_share_os.isChecked())
        self.config.set("telemetry", "share_clamav_version", self.chk_share_clamav.isChecked())
        self.config.set("telemetry", "share_scan_stats", self.chk_share_scan_stats.isChecked())

        if AutoStartManager.is_supported():
            AutoStartManager.set_enabled(self.chk_autostart.isChecked())
            self.config.set("preferences", "start_with_system", self.chk_autostart.isChecked())

        if self.tray and hasattr(self.tray, "set_protection_state"):
            self.tray.set_protection_state(self.guard.is_active)

        self.refresh_status()
        log_settings_change("User updated settings via Settings tab")
        QMessageBox.information(self, "Settings Saved", "Your settings have been updated successfully.")

    # --- TAB 5: ABOUT ---
    def setup_about_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("pyEGClamUI")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet("color: #38bdf8;")

        version_lbl = QLabel(f"Version {__version__}")
        version_lbl.setStyleSheet("color: #949ba4; font-size: 13px;")

        desc = QLabel(
            "An open-source, cross-platform desktop graphical user interface for the ClamAV engine. Built with Python 3.9+ and PySide6 (Qt) under the GNU General Public License v3.0 (GPL-3.0)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #e0e2e8; margin-top: 8px; line-height: 1.4;")

        credits_lbl = QLabel(
            '<b>Developed by:</b> EG1 ( <a href="https://eg1.in" style="color: #38bdf8; text-decoration: none;">https://eg1.in</a> )<br>'
            '<b>Website:</b> <a href="https://av.eg1.in" style="color: #38bdf8; text-decoration: none;">https://av.eg1.in</a><br>'
            '<b>GitHub:</b> <a href="https://github.com/EG1DOTIN/pyEGClamUI" style="color: #38bdf8; text-decoration: none;">https://github.com/EG1DOTIN/pyEGClamUI</a><br>'
            '<b>License:</b> <a href="https://www.gnu.org/licenses/gpl-3.0.html" style="color: #38bdf8; text-decoration: none;">GNU General Public License v3.0 or later (GPL-3.0-or-later)</a>'
        )
        credits_lbl.setOpenExternalLinks(True)
        credits_lbl.setStyleSheet("margin-top: 10px; color: #949ba4; line-height: 1.6;")

        # Trademark Disclaimer
        disclaimer = QLabel(
            "<b>Trademark Notice:</b> ClamAV(R) is a registered trademark of Cisco Systems, Inc. "
            "pyEGClamUI is an independent open-source frontend and is not affiliated with, endorsed by, "
            "or sponsored by Cisco Systems, Inc."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(
            "background-color: #111214; border: 1px solid #313338; border-radius: 6px; padding: 12px; color: #949ba4; font-size: 11px; margin-top: 15px;"
        )

        # Diagnostics && Community Support Box
        diag_group = QGroupBox("Diagnostics, Logs && Community Support")
        diag_layout = QVBoxLayout(diag_group)
        diag_layout.setContentsMargins(14, 14, 14, 14)
        diag_layout.setSpacing(10)

        diag_desc = QLabel(
            "Access local application error and scan report logs, or submit bug reports with screenshots to GitHub."
        )
        diag_desc.setWordWrap(True)
        diag_desc.setStyleSheet("color: #949ba4; font-size: 12px;")
        diag_layout.addWidget(diag_desc)

        diag_btns = QHBoxLayout()
        diag_btns.setSpacing(10)

        btn_open_logs = QPushButton("Open Log Folder")
        btn_open_logs.setObjectName("secondaryButton")
        btn_open_logs.setIcon(IconFactory.get_icon("browse", "#ffffff", 14))
        btn_open_logs.setIconSize(QSize(14, 14))
        btn_open_logs.setCursor(Qt.PointingHandCursor)
        btn_open_logs.clicked.connect(self.on_open_logs_clicked)
        diag_btns.addWidget(btn_open_logs)

        btn_report_issue = QPushButton("Report Issue / Diagnostics")
        btn_report_issue.setObjectName("primaryButton")
        btn_report_issue.setIcon(IconFactory.get_icon("shield", "#ffffff", 14))
        btn_report_issue.setIconSize(QSize(14, 14))
        btn_report_issue.setCursor(Qt.PointingHandCursor)
        btn_report_issue.clicked.connect(self.on_report_issue_clicked)
        diag_btns.addWidget(btn_report_issue)

        diag_layout.addLayout(diag_btns)

        layout.addWidget(title)
        layout.addWidget(version_lbl)
        layout.addWidget(desc)
        layout.addWidget(credits_lbl)
        layout.addWidget(diag_group)
        layout.addWidget(disclaimer)
        layout.addStretch()

        self.tabs.addTab(tab, IconFactory.get_icon("info", "#38bdf8", 14), "  About  ")

    def on_open_logs_clicked(self):
        open_log_folder()

    def on_report_issue_clicked(self):
        from pyegclamui.gui.issue_dialog import IssueDialog
        dlg = IssueDialog(self)
        apply_dark_titlebar(dlg)
        dlg.exec()

    def on_take_screenshot_clicked(self):
        try:
            pixmap = self.grab()
            save_dir = AppPaths.get_logs_dir()
            from datetime import datetime
            filename = f"screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
            target_path = save_dir / filename
            pixmap.save(str(target_path), "PNG")

            msg = QMessageBox(self)
            msg.setWindowTitle("Screenshot Captured")
            msg.setText("Application screenshot saved successfully.")
            msg.setInformativeText(f"Saved to:\n{target_path}\n\nYou can attach this image when reporting an issue.")
            msg.setIcon(QMessageBox.Information)
            btn_folder = msg.addButton("Open Folder", QMessageBox.ActionRole)
            msg.addButton(QMessageBox.Ok)
            apply_dark_titlebar(msg)
            msg.exec()
            if msg.clickedButton() == btn_folder:
                open_log_folder()
        except Exception as e:
            QMessageBox.warning(self, "Screenshot Failed", f"Could not capture screenshot: {e}")

    def on_check_updates_clicked(self):
        audit = self.detector.inspect()
        if not audit.get("ready"):
            self.on_reconfigure_engine_clicked()
            return

        if not self.guard.is_active and "Enable" in self.update_btn.text():
            self.chk_realtime.setChecked(True)
            self.refresh_status()
            return

        dialog = ClamGlobalUpdateDialog(self, updater=self.updater)
        dialog.exec()
        self.refresh_status()

    def on_daemon_action_clicked(self):
        d_status = self.service_mgr.get_status()
        if d_status["online"]:
            lat = self.service_mgr.measure_latency_ms()
            lat_str = f"{lat:.2f} ms" if lat is not None else "<20 ms"
            QMessageBox.information(
                self,
                "ClamD Daemon Socket Verification",
                f"Resident memory daemon is active on {d_status['connection']}.\n\n"
                f"Round-trip ping latency: {lat_str}\n"
                "Real-Time Guard scans are accelerated in memory with sub-20ms latency."
            )
            self.refresh_status()
        else:
            self.btn_daemon_action.setEnabled(False)
            self.btn_daemon_action.setText("Activating Daemon... Check UAC")
            self._daemon_worker = DaemonActivationWorker(self.service_mgr)
            self._daemon_worker.activation_completed.connect(self.on_daemon_activation_finished)
            self._daemon_worker.start()

    def on_daemon_activation_finished(self, success: bool, msg: str):
        self.refresh_status()
        if success:
            QMessageBox.information(
                self,
                "ClamD Daemon Service Activated",
                f"{msg}\n\nResident acceleration is now online with sub-20ms scan speeds!"
            )
        else:
            QMessageBox.warning(
                self,
                "ClamD Service Notice",
                f"{msg}\n\npyEGClamUI will continue operating safely using standalone engine fallback mode."
            )

    def on_update_completed(self, success: bool, msg: str):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for Updates")
        self.refresh_status()
        if success:
            QMessageBox.information(self, "Update Status", msg)
        else:
            QMessageBox.warning(self, "Update Failed", msg)

    def on_real_time_threat(self, threat_info: dict):
        threat_name = threat_info.get("threat", "Unknown Threat")
        file_path = threat_info.get("path", "Unknown File")
        action = threat_info.get("action", "Isolated")

        if self.tray:
            self.tray.notify(
                f"Antivirus Alert: {action}",
                f"Threat: {threat_name}\nFile: {Path(file_path).name}",
                is_warning=True,
            )

        if self.isVisible():
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                self,
                "Real-Time Threat Detected!",
                f"Threat detected: {threat_name}\nFile: {file_path}\nAction taken: {action}"
            ))
        self.refresh_quarantine_table()

    def closeEvent(self, event):
        close_to_tray = self.config.get("preferences", "close_to_tray", default=True)
        if close_to_tray and self.tray and self.tray.isVisible():
            event.ignore()
            self.hide()
            if self.config.get("preferences", "notifications", default=True):
                self.tray.notify(
                    "pyEGClamUI Running in Background",
                    "pyEGClamUI is still running and protecting your PC from the system tray.",
                    is_warning=False,
                )
        else:
            if self.guard:
                self.guard.stop()
            super().closeEvent(event)
