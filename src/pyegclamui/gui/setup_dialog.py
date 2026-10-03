"""
Setup Wizard Dialog for pyEGClamUI.
Guides users through automatic installation, custom path selection, or setup decline.
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, QThread, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyegclamui.core.config import AppPaths, Config
from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.setup_engine import ClamEngineInstaller
from pyegclamui.gui.icons import IconFactory
from pyegclamui.gui.platform_theme import apply_dark_titlebar


class SetupWorker(QThread):
    """Background worker executing ClamAV installation without freezing the UI."""

    status_changed = Signal(str)
    progress_changed = Signal(int)
    log_emitted = Signal(str)
    installation_completed = Signal(bool, str)

    def __init__(self, installer: ClamEngineInstaller):
        super().__init__()
        self.installer = installer

    def run(self):
        success, msg = self.installer.install_engine(
            on_status=lambda s: self.status_changed.emit(s),
            on_progress=lambda p: self.progress_changed.emit(p),
            on_log=lambda l: self.log_emitted.emit(l)
        )
        self.installation_completed.emit(success, msg)


class ClamSetupDialog(QDialog):
    """Modern wizard dialog prompting users to download, locate, or decline ClamAV engine."""

    setup_finished = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.installer = ClamEngineInstaller()
        self.detector = ClamEngineDetector()
        self.config = Config.get_instance()
        self.worker: Optional[SetupWorker] = None

        self.setWindowTitle("pyEGClamUI - ClamAV Engine Setup Wizard")
        self.resize(700, 520)
        self.setMinimumSize(600, 440)

        # Set App Icon
        icon_path = AppPaths.get_asset_path("egav.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setup_ui()
        apply_dark_titlebar(self)

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_titlebar(self)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("ClamAV Engine Setup Required")
        header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.setStyleSheet("color: #38bdf8;")
        layout.addWidget(header)

        sub = QLabel(
            "pyEGClamUI is a desktop graphical manager for the open-source ClamAV(R) engine. "
            "To perform virus scanning, quarantine threats, and download updates, the backend "
            "engine must be installed on your computer."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #949ba4; font-size: 13px; line-height: 1.4;")
        layout.addWidget(sub)

        # Card 1: Automatic Universal Install (Recommended)
        self.card_auto = QFrame()
        self.card_auto.setStyleSheet("background-color: #111214; border: 1px solid #38bdf8; border-radius: 8px;")
        auto_layout = QVBoxLayout(self.card_auto)
        auto_layout.setContentsMargins(16, 14, 16, 14)

        auto_title = QLabel("1. Install Official ClamAV Universally (Recommended)")
        auto_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        auto_title.setStyleSheet("color: #38bdf8;")
        auto_desc = QLabel(
            "Downloads and installs the official Cisco ClamAV engine into 'C:\\Program Files\\ClamAV', "
            "configures Windows system PATH so other apps can share it, and prepares signature updating."
        )
        auto_desc.setWordWrap(True)
        auto_desc.setStyleSheet("color: #e0e2e8; font-size: 12px;")

        self.btn_auto_install = QPushButton("Download && Install ClamAV")
        self.btn_auto_install.setObjectName("primaryButton")
        self.btn_auto_install.setIcon(IconFactory.get_icon("save", "#ffffff", 14))
        self.btn_auto_install.setIconSize(QSize(14, 14))
        self.btn_auto_install.setCursor(Qt.PointingHandCursor)
        self.btn_auto_install.clicked.connect(self.on_auto_install_clicked)

        auto_layout.addWidget(auto_title)
        auto_layout.addWidget(auto_desc)
        auto_layout.addWidget(self.btn_auto_install, alignment=Qt.AlignLeft)
        layout.addWidget(self.card_auto)

        # Card 2: Locate Existing Installation
        self.card_locate = QFrame()
        self.card_locate.setStyleSheet("background-color: #111214; border: 1px solid #313338; border-radius: 8px;")
        locate_layout = QVBoxLayout(self.card_locate)
        locate_layout.setContentsMargins(16, 14, 16, 14)

        locate_title = QLabel("2. I Already Have ClamAV (Locate Directory)")
        locate_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        locate_desc = QLabel(
            "If ClamAV is already installed or extracted in a custom folder, select the directory containing 'clamscan.exe'."
        )
        locate_desc.setWordWrap(True)
        locate_desc.setStyleSheet("color: #e0e2e8; font-size: 12px;")

        self.btn_browse = QPushButton("Browse Folder...")
        self.btn_browse.setObjectName("secondaryButton")
        self.btn_browse.setIcon(IconFactory.get_icon("browse", "#ffffff", 14))
        self.btn_browse.setIconSize(QSize(14, 14))
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self.on_browse_clicked)

        locate_layout.addWidget(locate_title)
        locate_layout.addWidget(locate_desc)
        locate_layout.addWidget(self.btn_browse, alignment=Qt.AlignLeft)
        layout.addWidget(self.card_locate)

        # Progress & Status Area (Hidden initially)
        self.progress_frame = QFrame()
        self.progress_frame.setStyleSheet("background-color: #111214; border: 1px solid #313338; border-radius: 8px;")
        self.progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_frame)
        prog_layout.setContentsMargins(16, 14, 16, 14)

        self.lbl_progress_status = QLabel("Preparing installation...")
        self.lbl_progress_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Verbose Console Drawer Controls
        console_ctrl_layout = QHBoxLayout()
        self.chk_verbose = QCheckBox("Show Detailed Execution Log (Verbose Console)")
        self.chk_verbose.setStyleSheet("color: #949ba4; font-size: 12px;")
        self.chk_verbose.toggled.connect(self.on_verbose_toggled)

        self.btn_copy_log = QPushButton("Copy Output")
        self.btn_copy_log.setObjectName("secondaryButton")
        self.btn_copy_log.setMaximumWidth(100)
        self.btn_copy_log.setVisible(False)
        self.btn_copy_log.clicked.connect(self.on_copy_log_clicked)

        console_ctrl_layout.addWidget(self.chk_verbose)
        console_ctrl_layout.addStretch()
        console_ctrl_layout.addWidget(self.btn_copy_log)

        # Verbose Terminal Viewer
        self.txt_console = QPlainTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setMaximumHeight(150)
        self.txt_console.setStyleSheet(
            "background-color: #0b0e14; color: #38bdf8; "
            "font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace; "
            "font-size: 11px; border: 1px solid #1f2937; border-radius: 6px; padding: 6px;"
        )
        self.txt_console.setVisible(False)

        prog_layout.addWidget(self.lbl_progress_status)
        prog_layout.addWidget(self.progress_bar)
        prog_layout.addLayout(console_ctrl_layout)
        prog_layout.addWidget(self.txt_console)
        layout.addWidget(self.progress_frame)

        layout.addStretch()

        # Footer Buttons
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_decline = QPushButton("Decline && Close")
        self.btn_decline.setObjectName("dangerButton")
        self.btn_decline.setIcon(IconFactory.get_icon("stop", "#ffffff", 14))
        self.btn_decline.setIconSize(QSize(14, 14))
        self.btn_decline.setCursor(Qt.PointingHandCursor)
        self.btn_decline.clicked.connect(self.on_decline_clicked)
        footer.addWidget(self.btn_decline)

        layout.addLayout(footer)

    def on_verbose_toggled(self, checked: bool):
        """Shows or hides detailed terminal output view."""
        self.txt_console.setVisible(checked)
        self.btn_copy_log.setVisible(checked)
        if checked:
            self.resize(self.width(), self.height() + 120)

    def on_copy_log_clicked(self):
        """Copies console buffer to system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.txt_console.toPlainText())
            self.btn_copy_log.setText("Copied!")
            self.btn_copy_log.setEnabled(False)

    def on_auto_install_clicked(self):
        """Starts background worker for automatic ClamAV installation."""
        self.card_auto.setEnabled(False)
        self.card_locate.setEnabled(False)
        self.btn_decline.setEnabled(False)
        self.progress_frame.setVisible(True)
        self.progress_bar.setValue(10)
        self.lbl_progress_status.setText("Starting installation...")
        self.txt_console.clear()
        self.txt_console.appendPlainText("[*] Initializing pyEGClamUI setup worker...")

        self.worker = SetupWorker(self.installer)
        self.worker.status_changed.connect(self.on_status_update)
        self.worker.progress_changed.connect(self.on_progress_update)
        self.worker.log_emitted.connect(self.on_log_emitted)
        self.worker.installation_completed.connect(self.on_install_finished)
        self.worker.start()

    def on_log_emitted(self, line: str):
        """Appends streaming log lines to the verbose console drawer."""
        self.txt_console.appendPlainText(line)
        sb = self.txt_console.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def on_status_update(self, msg: str):
        self.lbl_progress_status.setText(msg)

    def on_progress_update(self, val: int):
        self.progress_bar.setValue(val)

    def on_install_finished(self, success: bool, msg: str):
        self.card_auto.setEnabled(True)
        self.card_locate.setEnabled(True)
        self.btn_decline.setEnabled(True)

        if success:
            self.progress_bar.setValue(100)
            self.lbl_progress_status.setText("ClamAV successfully installed and configured!")
            QMessageBox.information(
                self,
                "Setup Successful",
                "ClamAV engine has been installed and configured successfully!\n\n"
                "pyEGClamUI is now ready for scanning and updates."
            )
            self.setup_finished.emit(True)
            self.accept()
        else:
            self.lbl_progress_status.setText(f"Installation failed: {msg}")
            QMessageBox.warning(
                self,
                "Installation Failed",
                f"Automatic ClamAV installation could not be completed:\n{msg}\n\n"
                "You can install ClamAV manually from https://www.clamav.net/downloads and select its folder."
            )

    def on_browse_clicked(self):
        """Allows user to select an existing directory containing clamscan."""
        folder = QFileDialog.getExistingDirectory(self, "Select ClamAV Folder (containing clamscan.exe)")
        if not folder:
            return

        folder_path = Path(folder)
        clamscan_cand = folder_path / "clamscan.exe" if sys.platform == "win32" else folder_path / "clamscan"

        if clamscan_cand.is_file():
            self.config.set("scan_settings", "custom_clamscan_path", str(clamscan_cand.resolve()))

            clamdscan_cand = folder_path / "clamdscan.exe" if sys.platform == "win32" else folder_path / "clamdscan"
            if clamdscan_cand.is_file():
                self.config.set("scan_settings", "custom_clamdscan_path", str(clamdscan_cand.resolve()))

            clamd_cand = folder_path / "clamd.exe" if sys.platform == "win32" else folder_path / "clamd"
            if clamd_cand.is_file():
                self.config.set("scan_settings", "custom_clamd_path", str(clamd_cand.resolve()))

            fresh_cand = folder_path / "freshclam.exe" if sys.platform == "win32" else folder_path / "freshclam"
            if fresh_cand.is_file():
                self.config.set("scan_settings", "custom_freshclam_path", str(fresh_cand.resolve()))

            # Register in PATH
            ClamEngineInstaller.register_path_environment(folder_path)

            QMessageBox.information(
                self,
                "ClamAV Linked",
                f"Successfully linked ClamAV at:\n{folder_path}\n\npyEGClamUI is ready."
            )
            self.setup_finished.emit(True)
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Executable Not Found",
                f"Could not find 'clamscan' inside:\n{folder_path}\n\n"
                "Please choose the folder containing clamscan.exe."
            )

    def on_decline_clicked(self):
        """Warns the user and closes setup."""
        confirm = QMessageBox.question(
            self,
            "Decline Engine Setup",
            "Without the ClamAV backend engine, pyEGClamUI cannot scan files or remove threats.\n\n"
            "Are you sure you want to exit without setting up ClamAV?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.setup_finished.emit(False)
            self.reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        super().closeEvent(event)