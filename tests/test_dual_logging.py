"""
Unit tests for the timestamped dual-track logging system (2MB rotation).
"""

import logging
import tempfile
from pathlib import Path

from pyegclamui.core.logger import (
    TimestampedFileHandler,
    log_quarantine_action,
    log_scan_report,
    log_settings_change,
    setup_logging,
    shutdown_logging,
)


def test_timestamped_file_handler_creation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        handler = TimestampedFileHandler(logs_dir=tmp_path, log_type="errors", max_bytes=2 * 1024 * 1024)

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Test error message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.close()

        # Check created file
        log_files = list(tmp_path.glob("*-errors*.log"))
        assert len(log_files) == 1
        content = log_files[0].read_text(encoding="utf-8")
        assert "Test error message" in content


def test_timestamped_file_handler_rotation_at_limit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Small max_bytes = 200 bytes to easily test rollover
        handler = TimestampedFileHandler(logs_dir=tmp_path, log_type="report", max_bytes=200)

        for i in range(15):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"Scan record log entry index #{i:03d} - standard line filling bytes.",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        handler.close()

        # Verify multiple timestamped rotated files were generated
        log_files = list(tmp_path.glob("*-report*.log"))
        assert len(log_files) >= 2


def test_high_level_logging_helpers():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            setup_logging(custom_logs_dir=tmp_path, force=True)

            log_scan_report(
                scan_type="Quick Scan",
                duration_sec=1.25,
                scanned_count=10,
                threats_count=0,
                targets=["C:\\target"],
            )
            log_quarantine_action("Quarantined", "C:\\virus.exe", "EICAR-Test-Signature")
            log_settings_change("Updated real-time guard preferences")

            # Report log should capture all of these
            report_logs = list(tmp_path.glob("*-report*.log"))
            assert len(report_logs) >= 1
            content = report_logs[0].read_text(encoding="utf-8")
            assert "Quick Scan" in content
            assert "EICAR-Test-Signature" in content
            assert "Updated real-time guard preferences" in content
        finally:
            shutdown_logging()
