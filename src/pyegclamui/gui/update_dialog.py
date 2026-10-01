"""
Live global maintenance and full-stack update dialog for pyEGClamUI.
Sequentially executes and displays:
  1. pyEGClamUI application source update (git pull / release check)
  2. Python virtual environment dependency synchronization (.venv)
  3. ClamAV virus signature database update (freshclam)
  4. ClamAV engine binary check / upgrade (winget / apt / brew)

Provides 4-stage visual indicators, live progress bars, and streaming monospace logs.
"""

import re
import sys
from datetime import datetime
from typing import Optional, Tuple

from PySide6.QtCore import QProcess, QSize, QThread, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyegclamui.core.config import AppPaths
from pyegclamui.core.updater import ClamUpdater, GlobalUpdatePipeline
from pyegclamui.gui.icons import IconFactory
from pyegclamui.gui.platform_theme import apply_dark_titlebar


class GlobalUpdateWorker(QThread):
    """Background worker thread executing 4-stage GlobalUpdatePipeline."""

    line_emitted = Signal(str)
    stage_changed = Signal(int, int, str)
    progress_changed = Signal(int, str)
    update_completed = Signal(bool, str, bool)

    def __init__(self, pipeline: GlobalUpdatePipeline):
        super().__init__()
        self.pipeline = pipeline

    def run(self):
        def on_stage(current: int, total: int, title: str):
            self.stage_changed.emit(current, total, title)

        def on_log(line: str):
            clean = line.strip()
            if clean:
                self.line_emitted.emit(clean)
                percent, stage_hint = self._parse_progress(clean)
                if percent >= 0 or stage_hint:
                    self.progress_changed.emit(percent, stage_hint)

        def on_progress(p: int):
            self.progress_changed.emit(p, "")

        def on_finished(success: bool, summary: str, code_updated: bool):
            self.update_completed.emit(success, summary, code_updated)

        self.pipeline.run_pipeline(
            on_stage=on_stage,
            on_log=on_log,
            on_progress=on_progress,
            on_finished=on_finished,
        )

    @staticmethod
    def _parse_progress(line: str) -> Tuple[int, str]:
        """Parses percentage and descriptive stage hints from freshclam or pip output."""
        percent = -1
        stage = ""

        # FreshClam bracket parsing: [=======>                  ] 23.00MiB/84.95MiB
        match_bracket = re.search(r'\[([=\s>]+)\]\s*([\d\.]+[KMGT]?i?B/)?([\d\.]+[KMGT]?i?B)', line)
        if match_bracket:
            bar_content = match_bracket.group(1)
            total_slots = len(bar_content)
            fill_slots = bar_content.count('=')
            if total_slots > 0:
                percent = int((fill_slots / total_slots) * 100)

            size_str = match_bracket.group(0).split(']')[-1].strip()
            eta_match = re.search(r'ETA:\s*([\d\.]+[a-z]+)', line)
            eta_str = f" (ETA: {eta_match.group(1)})" if eta_match else ""
            stage = f"Downloading definitions: {size_str}{eta_str}"
            return percent, stage

        if "update process started" in line.lower():
            stage = "Initializing ClamAV update process..."
        elif "connecting" in line.lower() or "retrying" in line.lower():
            stage = "Connecting to ClamAV CDN mirrors..."
        elif "testing database" in line.lower() or "verifying" in line.lower():
            stage = "Verifying signature database integrity..."
        elif "database is up to date" in line.lower():
            percent = 100
            stage = "Database is already up to date."
        elif "updated successfully" in line.lower() or "bytecode.cvd updated" in line.lower():
            percent = 100
            stage = "Signatures updated successfully."

        return percent, stage


class ClamGlobalUpdateDialog(QDialog):
    """
    Polished modal dialog providing complete visibility and streaming logs
    during full-stack maintenance and global updates.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        updater: Optional[ClamUpdater] = None,
        pipeline: Optional[GlobalUpdatePipeline] = None,
    ):
        super().__init__(parent)
        self.updater = updater or ClamUpdater()
        self.pipeline = pipeline or GlobalUpdatePipeline(self.updater)
        self.worker: Optional[GlobalUpdateWorker] = None
        self.logs: list[str] = []
        self.success = False
        self.code_updated = False

        self.setWindowTitle("pyEGClamUI - Virus Signature Update & Global Maintenance")
        self.resize(680, 520)
        self.setMinimumSize(580, 420)

        for candidate in ["egav.png", "egav.ico"]:
            icon_path = AppPaths.get_asset_path(candidate)
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        self.setup_ui()
        self.start_pipeline()
        apply_dark_titlebar(self)

    def showEvent(self, event):
        super().showEvent(event)
        apply_dark_titlebar(self)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header with icon and title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(IconFactory.get_pixmap("refresh", "#38bdf8", 40))
        header_layout.addWidget(self.icon_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(3)
        self.title_label = QLabel("Global System Maintenance & Update")
        self.title_label.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.title_label.setStyleSheet("color: #38bdf8;")

        self.sub_label = QLabel(
            "Synchronizing application code, virtualenv dependencies, virus signatures, and engine binaries."
        )
        self.sub_label.setStyleSheet("color: #949ba4; font-size: 12px;")

        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.sub_label)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 4-Stage Visual Indicators Card
        stages_frame = QFrame()
        stages_frame.setStyleSheet("background-color: #111214; border: 1px solid #313338; border-radius: 8px;")
        stages_layout = QHBoxLayout(stages_frame)
        stages_layout.setContentsMargins(12, 10, 12, 10)
        stages_layout.setSpacing(8)

        self.stage_badges = []
        stage_names = ["1. App Code", "2. Dependencies", "3. Signatures", "4. Engine Core"]
        for idx, name in enumerate(stage_names):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(self._badge_style("pending"))
            stages_layout.addWidget(lbl)
            self.stage_badges.append(lbl)

        layout.addWidget(stages_frame)

        # Main Progress Card
        card = QFrame()
        card.setStyleSheet("background-color: #111214; border: 1px solid #313338; border-radius: 8px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        self.lbl_status = QLabel("Initializing global update sequence...")
        self.lbl_status.setStyleSheet("color: #e0e2e8; font-size: 13px; font-weight: bold;")
        card_layout.addWidget(self.lbl_status)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1f22;
                border: 1px solid #313338;
                border-radius: 5px;
                height: 18px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 4px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        self.lbl_detail = QLabel("Connecting to update endpoints...")
        self.lbl_detail.setStyleSheet("color: #949ba4; font-size: 11px;")
        card_layout.addWidget(self.lbl_detail)

        layout.addWidget(card)

        # Verbose Console Drawer Controls
        ctrl_layout = QHBoxLayout()
        self.chk_console = QCheckBox("Show Detailed Output Logs")
        self.chk_console.setStyleSheet("color: #949ba4; font-size: 12px;")
        self.chk_console.setChecked(True)
        self.chk_console.toggled.connect(self.on_toggle_console)

        self.btn_copy = QPushButton("Copy Output")
        self.btn_copy.setObjectName("secondaryButton")
        self.btn_copy.setMaximumWidth(100)
        self.btn_copy.clicked.connect(self.on_copy_output)

        ctrl_layout.addWidget(self.chk_console)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.btn_copy)
        layout.addLayout(ctrl_layout)

        # Verbose Monospace Terminal Viewer
        self.txt_console = QPlainTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setStyleSheet(
            "background-color: #0b0e14; color: #38bdf8; "
            "font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace; "
            "font-size: 11px; border: 1px solid #1f2937; border-radius: 6px; padding: 6px;"
        )
        layout.addWidget(self.txt_console)

        # Action Buttons Footer
        footer = QHBoxLayout()
        self.btn_restart = QPushButton("Restart pyEGClamUI")
        self.btn_restart.setObjectName("primaryButton")
        self.btn_restart.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: #ffffff;
                border: 1px solid #22c55e;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #22c55e; }
        """)
        self.btn_restart.setIcon(IconFactory.get_icon("refresh", "#ffffff", 14))
        self.btn_restart.setVisible(False)
        self.btn_restart.clicked.connect(self.on_restart_clicked)
        footer.addWidget(self.btn_restart)

        footer.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondaryButton")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        footer.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("primaryButton")
        self.btn_close.setEnabled(False)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)

        layout.addLayout(footer)

    def _badge_style(self, state: str) -> str:
        """Returns scoped badge styling for stage badges."""
        if state == "active":
            return "background-color: #0369a1; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: 1px solid #38bdf8;"
        elif state == "completed":
            return "background-color: #14532d; color: #86efac; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: 1px solid #22c55e;"
        elif state == "warning":
            return "background-color: #713f12; color: #fde047; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: 1px solid #eab308;"
        else:  # pending
            return "background-color: #1e1f22; color: #6b7280; border-radius: 4px; padding: 4px 8px; border: 1px solid #313338;"

    def start_pipeline(self):
        """Spawns background update worker thread."""
        self.worker = GlobalUpdateWorker(self.pipeline)
        self.worker.line_emitted.connect(self.on_line_emitted)
        self.worker.stage_changed.connect(self.on_stage_changed)
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.update_completed.connect(self.on_pipeline_completed)
        self.worker.start()

    def on_stage_changed(self, current: int, total: int, title: str):
        """Updates stage badges visually."""
        self.lbl_status.setText(f"[Stage {current}/{total}] {title}")
        for idx, lbl in enumerate(self.stage_badges):
            stage_idx = idx + 1
            if stage_idx < current:
                lbl.setStyleSheet(self._badge_style("completed"))
            elif stage_idx == current:
                lbl.setStyleSheet(self._badge_style("active"))
            else:
                lbl.setStyleSheet(self._badge_style("pending"))

    def on_line_emitted(self, line: str):
        """Appends output to console drawer and keeps log buffer."""
        self.logs.append(line)
        self.txt_console.appendPlainText(line)
        scrollbar = self.txt_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_progress_changed(self, percent: int, stage_hint: str):
        """Updates progress bar and status hint dynamically."""
        if percent >= 0:
            self.progress_bar.setValue(percent)
        if stage_hint:
            self.lbl_status.setText(stage_hint)
            self.lbl_detail.setText(f"Stage timestamp: {datetime.now().strftime('%H:%M:%S')}")

    def on_pipeline_completed(self, success: bool, summary: str, code_updated: bool):
        """Handles final update status and shows restart prompt if necessary."""
        self.success = success
        self.code_updated = code_updated
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

        for lbl in self.stage_badges:
            lbl.setStyleSheet(self._badge_style("completed" if success else "warning"))

        if success:
            self.progress_bar.setValue(100)
            self.lbl_status.setText("Global Maintenance Completed Successfully!")
            self.lbl_status.setStyleSheet("color: #22c55e; font-size: 13px; font-weight: bold;")
            self.icon_lbl.setPixmap(IconFactory.get_pixmap("shield_ok", "#22c55e", 40))

            if code_updated:
                self.lbl_detail.setText("pyEGClamUI core code was updated. Please restart the app to load new features.")
                self.btn_restart.setVisible(True)
            else:
                self.lbl_detail.setText("All components are up to date and synchronized.")
        else:
            self.lbl_status.setText("Global Update Finished with Notices")
            self.lbl_status.setStyleSheet("color: #eab308; font-size: 13px; font-weight: bold;")
            self.icon_lbl.setPixmap(IconFactory.get_pixmap("shield_warn", "#eab308", 40))
            self.lbl_detail.setText(summary)

    def on_update_completed(self, success: bool, summary: str, code_updated: bool = False):
        """Compatibility wrapper for legacy single-stage update callers."""
        self.on_pipeline_completed(success, summary, code_updated)

    def on_toggle_console(self, checked: bool):
        self.txt_console.setVisible(checked)
        self.btn_copy.setVisible(checked)
        if checked:
            self.resize(self.width(), 520)
        else:
            self.resize(self.width(), 340)

    def on_copy_output(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText("\n".join(self.logs))
        self.btn_copy.setText("Copied!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self.btn_copy.setText("Copy Output"))

    def on_cancel_clicked(self):
        self.lbl_status.setText("Cancelling update...")
        self.pipeline.cancel()
        if self.worker:
            self.worker.wait(1500)
        self.reject()

    def on_restart_clicked(self):
        """Restarts pyEGClamUI application."""
        QProcess.startDetached(sys.executable, sys.argv)
        QGuiApplication.quit()


# Compatibility aliases for legacy callers
ClamUpdateDialog = ClamGlobalUpdateDialog
UpdateWorker = GlobalUpdateWorker
