"""
Active scanner dialog for pyEGClamUI.
Displays live scan metrics, file counters, elapsed time, and threat notifications in a QDialog.
"""

from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyegclamui.core.config import AppPaths
from pyegclamui.core.scanner import ClamScanner, ScanReport
from pyegclamui.gui.icons import IconFactory
from pyegclamui.gui.platform_theme import apply_dark_titlebar


class ScanWorker(QThread):
    """Background worker thread executing clamscan without freezing the UI."""

    file_scanned = Signal(str)
    threat_found = Signal(dict)
    status_changed = Signal(str)
    scan_completed = Signal(object)

    def __init__(self, scanner: ClamScanner, scan_type: str, targets: List[str]):
        super().__init__()
        self.scanner = scanner
        self.scan_type = scan_type
        self.targets = targets

    def run(self):
        report = self.scanner.scan(
            scan_type=self.scan_type,
            targets=self.targets,
            on_progress=lambda f: self.file_scanned.emit(f),
            on_threat=lambda t: self.threat_found.emit(t),
            on_status=lambda s: self.status_changed.emit(s),
            prefer_daemon=True,
        )
        self.scan_completed.emit(report)


class ScanDialog(QDialog):
    """Live progress dialog displaying active scanning telemetry and identified threats."""

    def __init__(
        self,
        parent: Optional[QWidget],
        scan_type: str,
        targets: List[str],
        auto_start: bool = True,
    ):
        super().__init__(parent)
        self.scanner = ClamScanner()
        self.scan_type = scan_type
        self.targets = targets
        self.worker: Optional[ScanWorker] = None
        self.elapsed_seconds = 0
        self.report: Optional[ScanReport] = None
        self.start_time = datetime.now()

        self.setWindowTitle(f"pyEGClamUI - {scan_type}")
        self.resize(750, 520)
        self.setMinimumSize(600, 400)

        # Set window icon
        icon_path = AppPaths.get_asset_path("egav.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setup_ui()
        if auto_start:
            self.start_scan()
        apply_dark_titlebar(self)


    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_titlebar(self)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        self.title_label = QLabel(f"Running {self.scan_type}...")
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.title_label.setStyleSheet("color: #38bdf8;")
        layout.addWidget(self.title_label)

        # Currently scanned file label
        self.current_file_label = QLabel("Initializing engine...")
        self.current_file_label.setStyleSheet("color: #949ba4; font-family: monospace; font-size: 11px;")
        self.current_file_label.setWordWrap(False)
        layout.addWidget(self.current_file_label)

        # Progress bar (Indeterminate pulse during scan)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Marquee mode
        layout.addWidget(self.progress_bar)

        # Stats Cards Row
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #111214; border: 1px solid #313338; border-radius: 8px;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 12, 15, 12)

        self.files_count_label = QLabel("Scanned Files: 0")
        self.files_count_label.setFont(QFont("Segoe UI", 12, QFont.Bold))

        self.threats_count_label = QLabel("Threats: 0")
        self.threats_count_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.threats_count_label.setStyleSheet("color: #22c55e;")  # Green until threat found

        self.timer_label = QLabel("Elapsed: 0s")
        self.timer_label.setFont(QFont("Segoe UI", 12))
        self.timer_label.setStyleSheet("color: #949ba4;")

        stats_layout.addWidget(self.files_count_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.threats_count_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.timer_label)

        layout.addWidget(stats_frame)

        # Threats Table
        self.threats_table = QTableWidget(0, 4)
        self.threats_table.setHorizontalHeaderLabels(["Time", "Threat Name", "Action Taken", "File Path"])
        self.threats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.threats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.threats_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.threats_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.threats_table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.stop_btn = QPushButton("Stop Scan")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setIcon(IconFactory.get_icon("stop", "#ffffff", 14))
        self.stop_btn.setIconSize(QSize(14, 14))
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryButton")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        # Timer for elapsed seconds
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
        self.elapsed_timer.start(1000)

    def start_scan(self):
        self.worker = ScanWorker(self.scanner, self.scan_type, self.targets)
        self.worker.file_scanned.connect(self.on_file_scanned)
        self.worker.threat_found.connect(self.on_threat_found)
        self.worker.status_changed.connect(self.on_status_changed)
        self.worker.scan_completed.connect(self.on_scan_completed)
        self.worker.start()

    def update_elapsed_time(self):
        elapsed = int((datetime.now() - self.start_time).total_seconds())
        self.timer_label.setText(f"Elapsed: {elapsed}s")

    def on_file_scanned(self, filepath: str):
        self.current_file_label.setText(f"Scanning: {filepath}")
        current_count = int(self.files_count_label.text().split(":")[-1].strip()) + 1
        self.files_count_label.setText(f"Scanned Files: {current_count}")

    def on_threat_found(self, threat_info: dict):
        row = self.threats_table.rowCount()
        self.threats_table.insertRow(row)

        time_item = QTableWidgetItem(threat_info.get("time", ""))
        name_item = QTableWidgetItem(threat_info.get("threat", ""))
        action_item = QTableWidgetItem(threat_info.get("action", ""))
        path_item = QTableWidgetItem(threat_info.get("path", ""))

        # Highlight threat row in crimson
        for item in [time_item, name_item, action_item, path_item]:
            item.setForeground(QColor("#ef4444"))

        self.threats_table.setItem(row, 0, time_item)
        self.threats_table.setItem(row, 1, name_item)
        self.threats_table.setItem(row, 2, action_item)
        self.threats_table.setItem(row, 3, path_item)

        current_threats = self.threats_table.rowCount()
        self.threats_count_label.setText(f"Threats: {current_threats}")
        self.threats_count_label.setStyleSheet("color: #ef4444; font-weight: bold;")

    def on_status_changed(self, status: str):
        self.current_file_label.setText(status)

    def on_scan_completed(self, report: ScanReport):
        self.report = report
        self.elapsed_timer.stop()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        self.stop_btn.setEnabled(False)
        self.close_btn.setEnabled(True)

        if report.cancelled:
            self.title_label.setText("Scan Cancelled")
            self.title_label.setStyleSheet("color: #eab308;")
        elif report.threats_found > 0:
            self.title_label.setText(f"Scan Finished - {report.threats_found} Threat(s) Found!")
            self.title_label.setStyleSheet("color: #ef4444;")
        else:
            self.title_label.setText("Scan Finished - No Threats Detected")
            self.title_label.setStyleSheet("color: #22c55e;")

        self.files_count_label.setText(f"Scanned Files: {report.scanned_files}")

    def on_stop_clicked(self):
        self.stop_btn.setEnabled(False)
        self.current_file_label.setText("Stopping scanner...")
        self.scanner.stop()

    def closeEvent(self, event):
        if self.scanner.is_running:
            self.scanner.stop()
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        super().closeEvent(event)

