"""
Unit tests for pyEGClamUI Lite Tkinter interface (src/pyegclamui/gui/tk_app.py).

Validates:
  - Graceful handling when Tkinter is not installed (tk is None)
  - Headless display error handling (TclError)
  - TkinterApp initialization with mock root
  - Thread-safe event queue processing (progress, threats, scan completion)
  - Quarantine treeview population and operations
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pyegclamui.gui.tk_app as tk_app_mod
from pyegclamui.core.scanner import ScanReport


def _create_test_app(mock_root):
    """Helper to initialize TkinterApp with properly configured mock core dependencies."""
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "/usr/bin/clamscan"
    mock_detector.check_daemon_socket.return_value = (True, "TCP 3310")
    mock_detector.get_freshclam_path.return_value = "/usr/bin/freshclam"

    mock_updater = MagicMock()
    mock_updater.is_database_recent.return_value = (True, "Up to date")

    mock_scanner = MagicMock()
    mock_scanner.get_quick_scan_paths.return_value = ["/home/user/Downloads"]
    mock_scanner.get_system_drives.return_value = ["/"]

    mock_qm = MagicMock()
    mock_qm.list_items.return_value = []

    with patch("pyegclamui.gui.tk_app.tk", MagicMock()), patch(
        "pyegclamui.gui.tk_app.ttk", MagicMock()
    ), patch("pyegclamui.gui.tk_app.Config.get_instance"), patch(
        "pyegclamui.gui.tk_app.ClamEngineDetector", return_value=mock_detector
    ), patch(
        "pyegclamui.gui.tk_app.QuarantineManager", return_value=mock_qm
    ), patch(
        "pyegclamui.gui.tk_app.ClamScanner", return_value=mock_scanner
    ), patch(
        "pyegclamui.gui.tk_app.ClamUpdater", return_value=mock_updater
    ):
        app = tk_app_mod.TkinterApp(mock_root)
        app.tree_q = MagicMock()
        app.tree_q.get_children.return_value = []
        return app, mock_detector, mock_qm, mock_scanner, mock_updater


def test_run_tkinter_app_when_tk_none():
    """Validates that run_tkinter_app exits with code 1 if tk is None."""
    with patch.object(tk_app_mod, "tk", None):
        exit_code = tk_app_mod.run_tkinter_app()
        assert exit_code == 1


def test_run_tkinter_app_on_tcl_error():
    """Validates that run_tkinter_app handles TclError (headless/no DISPLAY) gracefully."""
    mock_tk = MagicMock()

    class MockTclError(Exception):
        pass

    mock_tk.TclError = MockTclError
    mock_tk.Tk.side_effect = MockTclError("no display name and no $DISPLAY environment variable")

    with patch.object(tk_app_mod, "tk", mock_tk):
        exit_code = tk_app_mod.run_tkinter_app()
        assert exit_code == 1


def test_tkinter_app_event_queue_processing():
    """Validates that TkinterApp correctly handles threaded worker events in queue."""
    mock_root = MagicMock()
    mock_root.after = MagicMock()

    app, _, _, _, _ = _create_test_app(mock_root)
    app.scan_start_time = 1000.0

    # Simulate scanning events
    app.event_queue.put(("progress_file", "/home/user/document.pdf"))
    app.event_queue.put(
        (
            "threat_found",
            {
                "path": "/home/user/virus.exe",
                "threat": "Win.Test.EICAR_HDB-1",
                "action": "Quarantined",
            },
        )
    )

    mock_report = ScanReport(scan_type="Quick Scan")
    mock_report.scanned_files = 1
    mock_report.threats_found = 1
    mock_report.end_time = mock_report.start_time
    app.event_queue.put(("scan_done", mock_report))

    # Process queue
    with patch.object(tk_app_mod, "messagebox", MagicMock()):
        app._poll_event_queue()

    assert app.scanned_count == 1
    assert app.threats_count == 1
    assert app.is_scanning is False


def test_tkinter_app_stop_scan():
    """Validates that _stop_scan triggers scanner.stop() and updates state."""
    mock_root = MagicMock()
    app, _, _, mock_scanner, _ = _create_test_app(mock_root)
    app.is_scanning = True

    app._stop_scan()
    mock_scanner.stop.assert_called_once()


def test_tkinter_app_quarantine_refresh():
    """Validates that quarantine view loads and displays vault items."""
    mock_root = MagicMock()

    class FakeItem:
        item_id = "abc12345"
        threat_name = "Trojan.Dropper"
        original_path = "/home/user/test.exe"
        quarantine_date = "2026-10-18 10:00:00"
        file_size_bytes = 2048

    app, _, mock_qm, _, _ = _create_test_app(mock_root)
    mock_qm.list_items.return_value = [FakeItem()]

    app._refresh_quarantine_view()
    app.tree_q.insert.assert_called_once()
    inserted_values = app.tree_q.insert.call_args[1]["values"]
    assert inserted_values[0] == "abc12345"
    assert inserted_values[1] == "Trojan.Dropper"
    assert inserted_values[4] == "2 KB"


if __name__ == "__main__":
    print("\n=== Running test_tk_app.py test suite ===")
    test_run_tkinter_app_when_tk_none()
    print("  [PASS] test_run_tkinter_app_when_tk_none")
    test_run_tkinter_app_on_tcl_error()
    print("  [PASS] test_run_tkinter_app_on_tcl_error")
    test_tkinter_app_event_queue_processing()
    print("  [PASS] test_tkinter_app_event_queue_processing")
    test_tkinter_app_stop_scan()
    print("  [PASS] test_tkinter_app_stop_scan")
    test_tkinter_app_quarantine_refresh()
    print("  [PASS] test_tkinter_app_quarantine_refresh")
    print("All Tkinter Lite tests passed successfully!\n")
