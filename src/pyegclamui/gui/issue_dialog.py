"""
Hybrid in-app issue reporting and diagnostics modal for pyEGClamUI.
Enables private direct submission via Firestore, sanitized clipboard export for GitHub,
and self-managed screen clipping.
"""

import subprocess
import sys
from typing import Optional

import psutil
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pyegclamui.core.detector import ClamEngineDetector
from pyegclamui.core.telemetry import TelemetryManager, sanitize_log_text


class IssueDialog(QDialog):
    """Interactive issue reporter supporting private cloud dispatch and sanitized GitHub markdown."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.telemetry_mgr = TelemetryManager()
        self.detector = ClamEngineDetector()

        self.setWindowTitle("Report an Issue or Bug - pyEGClamUI")
        self.resize(600, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        # Title & Guidance
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_lbl = QLabel("🐛 Report an Issue or Crash")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        title_box.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Submit diagnostics privately to project maintainers, or copy a sanitized report for GitHub."
        )
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_box.addWidget(desc_lbl)
        layout.addLayout(title_box)

        # Hardware & Diagnostic Summary Card
        specs_card = QFrame()
        specs_card.setStyleSheet("""
            QFrame {
                background-color: #2b2d31;
                border: 1px solid #383a40;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 11px;
            }
        """)
        specs_layout = QVBoxLayout(specs_card)
        specs_layout.setSpacing(4)

        # Gather System Specs
        engine_info = self.detector.get_engine_version()
        clam_ver = engine_info.get("clamav_version", "Not Detected")
        db_ver = engine_info.get("db_version", "Unknown")

        try:
            mem = psutil.virtual_memory()
            total_ram = f"{round(mem.total / (1024 ** 3), 1)} GB"
            avail_ram = f"{round(mem.available / (1024 ** 3), 1)} GB"
        except Exception:
            total_ram = "Unknown"
            avail_ram = "Unknown"

        self.specs_summary = (
            f"• OS: {sys.platform} | Python: {sys.version.split()[0]}\n"
            f"• System Memory: {total_ram} Total ({avail_ram} Available)\n"
            f"• ClamAV Engine: {clam_ver} | Signatures: {db_ver}"
        )
        specs_lbl = QLabel(self.specs_summary)
        specs_layout.addWidget(specs_lbl)
        layout.addWidget(specs_card)

        # User Issue Description
        desc_title = QLabel("Issue Description:")
        desc_title.setStyleSheet("font-weight: 600; color: #e2e8f0; font-size: 12px;")
        layout.addWidget(desc_title)

        self.txt_description = QTextEdit()
        self.txt_description.setPlaceholderText(
            "Please describe what you were doing when the issue occurred...\n"
            "Example: 'Scan stopped unexpectedly when scanning large archive file'."
        )
        self.txt_description.setStyleSheet("""
            QTextEdit {
                background-color: #1e1f22;
                border: 1px solid #383a40;
                border-radius: 6px;
                color: #f8fafc;
                padding: 8px;
                font-size: 12px;
            }
            QTextEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        layout.addWidget(self.txt_description)

        # Log Checkbox
        self.chk_logs = QCheckBox("Include recent sanitized error logs (User paths masked as ~)")
        self.chk_logs.setChecked(True)
        self.chk_logs.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(self.chk_logs)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Snip Screen Button
        btn_snip = QPushButton("📸 Snip Screen")
        btn_snip.setStyleSheet("""
            QPushButton {
                background-color: #383a40;
                color: #e2e8f0;
                font-size: 12px;
                padding: 9px 14px;
                border: 1px solid #4b5563;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        btn_snip.clicked.connect(self._trigger_screen_clip)
        btn_layout.addWidget(btn_snip)

        btn_layout.addStretch()

        # Copy Markdown for GitHub
        btn_copy = QPushButton("📋 Copy for GitHub")
        btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                padding: 9px 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        btn_copy.clicked.connect(self._copy_for_github)
        btn_layout.addWidget(btn_copy)

        # Submit Privately via Firebase
        self.btn_submit = QPushButton("🚀 Submit Privately")
        self.btn_submit.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                padding: 9px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_submit.clicked.connect(self._submit_privately)
        btn_layout.addWidget(self.btn_submit)

        layout.addLayout(btn_layout)

    def _trigger_screen_clip(self):
        """Launches the operating system native screen clipper."""
        from pyegclamui.core.process import spawn_hidden_process
        launched = False
        if sys.platform == "win32":
            try:
                spawn_hidden_process(["explorer", "ms-screenclip:"])
                launched = True
            except Exception:
                pass
        elif sys.platform == "darwin":
            try:
                spawn_hidden_process(["screencapture", "-i", "-c"])
                launched = True
            except Exception:
                pass
        elif sys.platform == "linux":
            for tool in ["gnome-screenshot", "spectacle", "scrot"]:
                try:
                    spawn_hidden_process([tool, "-a" if tool != "scrot" else "-s"])
                    launched = True
                    break
                except Exception:
                    continue

        if not launched:
            QMessageBox.information(
                self,
                "Screen Clipping Tool",
                "Please press Win + Shift + S (Windows) or Cmd + Shift + 4 (macOS)\n"
                "to capture and crop your screen. You can blur any private files before attaching.",
            )

    def _copy_for_github(self):
        """Assembles a path-sanitized markdown issue report and copies to clipboard."""
        description = self.txt_description.toPlainText().strip()
        include_logs = self.chk_logs.isChecked()

        logs_snippet = ""
        if include_logs:
            logs_snippet = self.telemetry_mgr.get_recent_error_logs(max_lines=40)
            logs_snippet = f"\n<details><summary>Sanitized Error Log</summary>\n\n```text\n{logs_snippet}\n```\n</details>\n"

        markdown_report = (
            f"### Bug Description\n{description or '*(No description provided)*'}\n\n"
            f"### Environment & Diagnostics\n"
            f"{self.specs_summary}\n"
            f"{logs_snippet}"
        )

        clipboard = QGuiApplication.clipboard()
        clipboard.setText(sanitize_log_text(markdown_report))

        QMessageBox.information(
            self,
            "Report Copied",
            "Sanitized diagnostic report copied to clipboard!\n\n"
            "Notice: Personal usernames and local paths have been masked with '~'.\n"
            "You can now paste it into GitHub Issues.",
        )

    def _submit_privately(self):
        """Dispatches report directly to Firestore issue_reports collection."""
        description = self.txt_description.toPlainText().strip()
        if not description:
            QMessageBox.warning(
                self, "Description Required", "Please enter a brief description of the issue."
            )
            return

        self.btn_submit.setEnabled(False)
        self.btn_submit.setText("Submitting...")

        def _on_finished(success: bool, msg: str):
            self.btn_submit.setEnabled(True)
            self.btn_submit.setText("🚀 Submit Privately")
            if success:
                QMessageBox.information(
                    self,
                    "Report Sent",
                    "Thank you! Your diagnostic report was submitted privately to project maintainers.\n"
                    "No personal files or paths were included.",
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Submission Failed",
                    f"Could not submit report: {msg}\n\n"
                    "You can alternatively use 'Copy for GitHub' to submit the report manually.",
                )

        self.telemetry_mgr.send_issue_report_async(
            description=description,
            include_logs=self.chk_logs.isChecked(),
            on_complete=_on_finished,
        )
