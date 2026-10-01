"""
Unit tests for RealTimeGuard and DebouncedScanHandler.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from watchdog.events import FileCreatedEvent

from pyegclamui.core.monitor import (
    DebouncedScanHandler,
    RealTimeGuard,
    is_file_ready_for_scan,
)


def test_is_file_ready_filters_temp_extensions(tmp_path: Path):
    """Ensures in-flight browser downloads (.crdownload, .part, etc.) are ignored."""
    for ext in [".crdownload", ".part", ".tmp", ".download", ".partial", ".aria2"]:
        temp_file = tmp_path / f"download_file{ext}"
        temp_file.write_text("partial byte stream", encoding="utf-8")
        assert is_file_ready_for_scan(temp_file) is False


def test_is_file_ready_filters_office_lock_prefixes(tmp_path: Path):
    """Ensures temporary lock prefixes (~$) are ignored."""
    lock_file = tmp_path / "~$SecretDocument.docx"
    lock_file.write_text("lock data", encoding="utf-8")
    assert is_file_ready_for_scan(lock_file) is False


def test_is_file_ready_valid_file(tmp_path: Path):
    """Ensures complete, standard files pass readiness verification."""
    clean_file = tmp_path / "installer.exe"
    clean_file.write_bytes(b"\x4D\x5A\x90\x00" + b"\x00" * 100)
    assert is_file_ready_for_scan(clean_file) is True


def test_debounced_handler_queue_and_dispatch(tmp_path: Path):
    """Validates that rapid file writes are debounced before triggering callback."""
    dispatched_files = []

    def on_ready(path_str: str):
        dispatched_files.append(path_str)

    target_file = tmp_path / "complete_payload.bin"
    target_file.write_bytes(b"data-chunk-1")

    # Short debounce for test speed
    handler = DebouncedScanHandler(on_file_ready=on_ready, debounce_seconds=0.2)
    try:
        # Simulate initial file creation event
        handler.on_created(FileCreatedEvent(str(target_file)))

        # Simulate subsequent write chunk
        time.sleep(0.05)
        target_file.write_bytes(b"data-chunk-2-finished")
        handler.on_modified(FileCreatedEvent(str(target_file)))

        # Wait for debounce window (0.2s + processing margin)
        time.sleep(0.5)

        # File should be dispatched exactly once
        assert len(dispatched_files) == 1
        assert dispatched_files[0] == str(target_file)
    finally:
        handler.stop()


def test_real_time_guard_lifecycle(tmp_path: Path):
    """Validates starting, stopping, and directory resolution for RealTimeGuard."""
    watch_dir = tmp_path / "WatchedFolder"
    watch_dir.mkdir()

    guard = RealTimeGuard(watch_dirs=[watch_dir])
    assert guard.is_active is False

    started = guard.start()
    assert started is True
    assert guard.is_active is True

    # Check initial stats
    stats = guard.get_stats()
    assert stats["active"] is True
    assert stats["scanned_count"] == 0
    assert stats["threats_count"] == 0

    guard.stop()
    assert guard.is_active is False


def test_real_time_guard_threat_callback(tmp_path: Path):
    """Validates that detected threats increment metrics and trigger user callbacks."""
    threat_events = []

    def handle_threat(threat_info: dict):
        threat_events.append(threat_info)

    guard = RealTimeGuard(watch_dirs=[tmp_path], on_threat_detected=handle_threat)

    mock_report = MagicMock()
    mock_report.scanned_files = 1
    mock_report.infected_files = 1

    test_file = tmp_path / "eicar.com"
    test_file.write_text("EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", encoding="utf-8")

    def mock_scan(scan_type, targets, on_threat=None, **kwargs):
        if on_threat:
            on_threat({"path": str(test_file), "threat": "Win.Test.EICAR_HDB-1", "action": "Quarantined"})
        return mock_report

    with patch.object(guard.scanner, "scan", side_effect=mock_scan):
        guard._scan_single_file(str(test_file))

    stats = guard.get_stats()
    assert stats["scanned_count"] == 1
    assert stats["threats_count"] == 1
    assert stats["last_scanned_file"] == str(test_file)

    assert len(threat_events) == 1
    assert threat_events[0]["threat"] == "Win.Test.EICAR_HDB-1"
    assert threat_events[0]["action"] == "Quarantined"
