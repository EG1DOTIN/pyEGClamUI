"""
Unit tests for ClamDaemonServiceManager (Resident daemon status & activation).
"""

from unittest.mock import MagicMock, patch
import pytest

from pyegclamui.core.service_manager import ClamDaemonServiceManager


def test_service_manager_get_status_offline():
    mock_detector = MagicMock()
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (False, "Offline")

    status = mgr.get_status()
    assert status["online"] is False
    assert status["connection"] == "Offline"
    assert status["latency_ms"] is None
    assert "Inactive" in status["mode_badge"]
    assert status["mode"] == "fallback"


def test_service_manager_get_status_online():
    mock_detector = MagicMock()
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (True, "TCP 127.0.0.1:3310")

    with patch.object(mgr, "measure_latency_ms", return_value=1.5):
        status = mgr.get_status()
        assert status["online"] is True
        assert status["connection"] == "TCP 127.0.0.1:3310"
        assert status["latency_ms"] == 1.5
        assert "Active" in status["mode_badge"]
        assert status["mode"] == "resident"


def test_service_manager_measure_latency():
    mock_detector = MagicMock()
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (True, "TCP 127.0.0.1:3310")

    lat = mgr.measure_latency_ms()
    assert lat is not None
    assert lat >= 0.1


def test_service_manager_uac_declined():
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "C:/Program Files/ClamAV/clamscan.exe"
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (False, "Offline")

    logs = []
    # Mock subprocess.run returning exit code 1 (UAC declined) on Windows
    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Elevation was declined by user")
        success, msg = mgr.activate_daemon(on_log=logs.append)
        assert success is False
        assert "declined" in msg.lower() or "cancelled" in msg.lower()
        assert any("UAC" in l or "declined" in l for l in logs)


def test_service_manager_activate_success():
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "C:/Program Files/ClamAV/clamscan.exe"
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    # Initially offline, then becomes online on socket poll
    mgr.client.check_connection.side_effect = [
        (False, "Offline"),  # Initial check in activate_daemon
        (True, "TCP 127.0.0.1:3310"),  # Poll check
        (True, "TCP 127.0.0.1:3310"),  # Latency check
    ]

    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch.object(mgr, "measure_latency_ms", return_value=0.8):
            success, msg = mgr.activate_daemon()
            assert success is True
            assert "active" in msg.lower()


def test_service_manager_activate_windows_passes_database_dir():
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "C:/Program Files/ClamAV/clamscan.exe"
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (False, "Offline")

    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # Fast-fail after 1 poll iteration to test args
        with patch("time.sleep", return_value=None):
            mgr.activate_daemon(timeout_seconds=0.01)

        # Ensure subprocess.run was called with -DatabaseDir in argument list
        called_cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(called_cmd)
        assert "-DatabaseDir" in cmd_str
        assert "-ClamDir" in cmd_str


def test_service_manager_activate_progress_logging():
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "C:/Program Files/ClamAV/clamscan.exe"
    mgr = ClamDaemonServiceManager(mock_detector)
    mgr.client = MagicMock()
    mgr.client.check_connection.return_value = (False, "Offline")

    logs = []
    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("time.sleep", return_value=None):
            # Run with tiny timeout
            success, msg = mgr.activate_daemon(on_log=logs.append, timeout_seconds=0.05)
            assert success is False
            assert "did not respond in time" in msg
            assert any("Verifying ClamD socket" in l for l in logs)

