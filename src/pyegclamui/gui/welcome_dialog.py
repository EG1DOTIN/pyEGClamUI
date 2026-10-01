"""
First-run privacy onboarding and transparency welcome modal for pyEGClamUI.
Provides clear, honest user agency over anonymous metrics before any network activity occurs.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyegclamui.core.telemetry import TelemetryManager


class WelcomeDialog(QDialog):
    """Initial onboarding dialog ensuring 100% transparent user consent."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.telemetry_mgr = TelemetryManager()
        self.selected_mode = "offline"

        self.setWindowTitle("Welcome to pyEGClamUI")
        self.setFixedSize(540, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)

        # Header Title & Shield
        title_box = QVBoxLayout()
        title_box.setSpacing(6)

        title_lbl = QLabel("🛡️ Welcome to pyEGClamUI")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        title_box.addWidget(title_lbl)

        subtitle_lbl = QLabel(
            "pyEGClamUI is 100% Free & Open-Source (GPL-3.0) software.\n"
            "We believe in zero silent telemetry and absolute user privacy."
        )
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #94a3b8; line-height: 1.4;")
        title_box.addWidget(subtitle_lbl)

        layout.addLayout(title_box)

        # Card Container for Options
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2b2d31;
                border: 1px solid #383a40;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        # Option 1: Full Anonymous Diagnostics
        btn_full = QPushButton("🟢  Enable Full Anonymous Diagnostics (Recommended)")
        btn_full.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 12px 16px;
                border-radius: 6px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        btn_full.clicked.connect(lambda: self._select_mode("opted_in"))
        card_layout.addWidget(btn_full)

        desc_full = QLabel(
            "• Shares anonymous OS, ClamAV version, and 30-day active heartbeats.\n"
            "• Helps prioritize operating system support and detect engine crashes.\n"
            "• Zero personal files, usernames, or scan paths are ever transmitted."
        )
        desc_full.setStyleSheet("color: #cbd5e1; font-size: 11px; margin-left: 8px;")
        card_layout.addWidget(desc_full)

        # Option 2: 1-Time Install Count Only
        btn_count = QPushButton("⚪  1-Time Anonymous Install Count Only")
        btn_count.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 12px 16px;
                border-radius: 6px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        btn_count.clicked.connect(lambda: self._select_mode("count_only"))
        card_layout.addWidget(btn_count)

        desc_count = QLabel(
            "• Sends a single anonymous ping confirming installation count.\n"
            "• Zero subsequent heartbeats and zero ongoing diagnostic reports."
        )
        desc_count.setStyleSheet("color: #cbd5e1; font-size: 11px; margin-left: 8px;")
        card_layout.addWidget(desc_count)

        # Option 3: Strictly Offline / Air-Gapped
        btn_offline = QPushButton("🔒  Keep 100% Offline (Air-Gapped / Zero Network)")
        btn_offline.setStyleSheet("""
            QPushButton {
                background-color: #383a40;
                color: #f1f5f9;
                font-weight: bold;
                font-size: 13px;
                padding: 12px 16px;
                border: 1px solid #4b5563;
                border-radius: 6px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        btn_offline.clicked.connect(lambda: self._select_mode("offline"))
        card_layout.addWidget(btn_offline)

        desc_offline = QLabel(
            "• Absolutely zero network requests will ever be made for metrics."
        )
        desc_offline.setStyleSheet("color: #cbd5e1; font-size: 11px; margin-left: 8px;")
        card_layout.addWidget(desc_offline)

        layout.addWidget(card)

        # Footer info
        footer_layout = QHBoxLayout()
        preview_btn = QPushButton("Preview JSON Schema")
        preview_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #38bdf8;
                border: none;
                font-size: 12px;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #7dd3fc;
            }
        """)
        preview_btn.clicked.connect(self._preview_schema)
        footer_layout.addWidget(preview_btn)
        footer_layout.addStretch()

        note_lbl = QLabel("You can change this anytime in Settings")
        note_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_layout.addWidget(note_lbl)

        layout.addLayout(footer_layout)

    def _preview_schema(self):
        """Displays sample JSON payload for transparent inspection."""
        payload_str = self.telemetry_mgr.get_preview_payload()
        QMessageBox.information(
            self,
            "pyEGClamUI Anonymous Data Schema",
            f"Here is the exact data structure shared when enabled:\n\n{payload_str}\n\n"
            "Notice: Zero personal files, browsing history, or documents are collected.",
        )

    def _select_mode(self, mode: str):
        """Persists user decision and triggers optional install ping."""
        self.selected_mode = mode
        self.telemetry_mgr.send_install_event(mode)
        self.accept()
