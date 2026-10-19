"""
Unit tests for pyEGClamUI Lite Tkinter interface (src/pyegclamui/gui/tk_app.py).

Comprehensive test coverage for UI state progression, threaded worker event processing,
quarantine operations, error handling, and corner cases.
"""

import os
import queue
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pyegclamui.gui.tk_app as tk_app_mod
from pyegclamui.core.scanner import ScanReport



def _create_test_app(mock_root, initial_path=None):
    """Helper to initialize TkinterApp with properly configured mock core dependencies."""
    mock_detector = MagicMock()
    mock_detector.get_clamscan_path.return_value = "/usr/bin/clamscan"
    mock_detector.check_daemon_socket.return_value = (True, "TCP 3310")
    mock_detector.get_freshclam_path.return_value = "/usr/bin/freshclam"

    mock_updater = MagicMock()
    mock_updater.is_database_recent.return_value = (True, "Up to date")
    mock_updater.run_update.return_value = (True, "Database updated")

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
        app = tk_app_mod.TkinterApp(mock_root, initial_path=initial_path)
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

    with patch.object(tk_app_mod, "tk", mock_tk), patch.object(
        tk_app_mod, "_tk_installed", True
    ):
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

    # Process queue with mocked alert helpers
    with patch.object(app, "_show_warning") as mock_warn:
        app._poll_event_queue()
        mock_warn.assert_called_once()

    assert app.scanned_count == 1
    assert app.threats_count == 1
    assert app.is_scanning is False


def test_tkinter_app_event_queue_clean_scan():
    """Validates scan_done processing when no threats are found."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    mock_report = ScanReport(scan_type="Full Scan")
    mock_report.scanned_files = 42
    mock_report.threats_found = 0
    mock_report.end_time = mock_report.start_time
    app.event_queue.put(("scan_done", mock_report))

    with patch.object(app, "_show_info") as mock_info:
        app._poll_event_queue()
        mock_info.assert_called_once()
        assert "Scan Clean" in mock_info.call_args[0][0]


def test_tkinter_app_unknown_event_in_queue():
    """Validates that unrecognized event tuples in queue do not crash the poller."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    app.event_queue.put(("unknown_custom_event", "payload"))
    # Should drain queue safely
    app._poll_event_queue()


def test_tkinter_app_stop_scan():
    """Validates that _stop_scan triggers scanner.stop() and updates state."""
    mock_root = MagicMock()
    app, _, _, mock_scanner, _ = _create_test_app(mock_root)
    app.is_scanning = True

    app._stop_scan()
    mock_scanner.stop.assert_called_once()

    # Repeated calls should be no-ops
    app._stop_scan()
    assert mock_scanner.stop.call_count == 1


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


def test_tkinter_app_quarantine_restore_actions():
    """Validates restore quarantined file handling user confirmation Yes and No."""
    mock_root = MagicMock()
    app, _, mock_qm, _, _ = _create_test_app(mock_root)

    # 1. No item selected
    app.tree_q.selection.return_value = []
    with patch.object(app, "_show_info") as mock_info:
        app._restore_quarantined()
        mock_info.assert_called_once()

    # 2. Selected item, user confirms YES -> restores successfully
    app.tree_q.selection.return_value = ["item_1"]
    app.tree_q.item.return_value = {
        "values": ("id123", "EICAR", "/home/user/eicar.com", "2026-10-18", "68 B")
    }
    mock_qm.restore_item.return_value = (True, "Restored to /home/user/eicar.com")

    with patch.object(app, "_ask_yes_no", return_value=True), patch.object(
        app, "_show_info"
    ) as mock_info:
        app._restore_quarantined()
        mock_qm.restore_item.assert_called_once_with("id123")
        mock_info.assert_called_once()

    # 3. Selected item, user cancels (NO) -> does not restore
    mock_qm.restore_item.reset_mock()
    with patch.object(app, "_ask_yes_no", return_value=False):
        app._restore_quarantined()
        mock_qm.restore_item.assert_not_called()


def test_tkinter_app_quarantine_delete_actions():
    """Validates delete quarantined file handling user confirmation Yes and No."""
    mock_root = MagicMock()
    app, _, mock_qm, _, _ = _create_test_app(mock_root)

    # 1. No item selected
    app.tree_q.selection.return_value = []
    with patch.object(app, "_show_info") as mock_info:
        app._delete_quarantined()
        mock_info.assert_called_once()

    # 2. Selected item, user confirms YES -> deletes permanently
    app.tree_q.selection.return_value = ["item_1"]
    app.tree_q.item.return_value = {
        "values": ("id999", "Rootkit", "/home/user/bad.ko", "2026-10-18", "12 KB")
    }
    mock_qm.delete_item.return_value = (True, "Deleted bad.ko")

    with patch.object(app, "_ask_yes_no", return_value=True), patch.object(
        app, "_show_info"
    ) as mock_info:
        app._delete_quarantined()
        mock_qm.delete_item.assert_called_once_with("id999")
        mock_info.assert_called_once()

    # 3. Selected item, user cancels (NO) -> does not delete
    mock_qm.delete_item.reset_mock()
    with patch.object(app, "_ask_yes_no", return_value=False):
        app._delete_quarantined()
        mock_qm.delete_item.assert_not_called()


def test_tkinter_app_custom_scan_folder_browser():
    """Validates custom scan with folder chooser selection vs cancellation."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    with patch.object(tk_app_mod, "filedialog") as mock_fd, patch.object(
        app, "_launch_scan"
    ) as mock_launch:
        # User selects folder
        mock_fd.askdirectory.return_value = "/home/user/Documents"
        app._browse_and_scan()
        mock_launch.assert_called_once()

        # User cancels folder chooser
        mock_launch.reset_mock()
        mock_fd.askdirectory.return_value = ""
        app._browse_and_scan()
        mock_launch.assert_not_called()


def test_tkinter_app_on_close_during_scan():
    """Validates window close confirmation during active scan."""
    mock_root = MagicMock()
    app, _, _, mock_scanner, _ = _create_test_app(mock_root)
    app.is_scanning = True

    # User says NO -> do not exit, keep scanning
    with patch.object(app, "_ask_yes_no", return_value=False):
        app._on_close()
        mock_root.destroy.assert_not_called()
        mock_scanner.stop.assert_not_called()

    # User says YES -> stop scan and destroy window
    with patch.object(app, "_ask_yes_no", return_value=True):
        app._on_close()
        mock_scanner.stop.assert_called_once()
        mock_root.destroy.assert_called_once()


def test_tkinter_app_signature_update_events():
    """Validates maintenance log streaming and update completion in event queue."""
    mock_root = MagicMock()
    app = tk_app_mod.TkinterApp.__new__(tk_app_mod.TkinterApp)
    app.root = mock_root
    app.event_queue = queue.Queue()
    app.is_updating = True
    app.btn_update_sig = MagicMock()
    app._log_maint = MagicMock()
    app._show_info = MagicMock()

    app.event_queue.put(("maint_log", "Downloading daily.cvd..."))
    app.event_queue.put(("update_done", "Virus definitions up to date!"))

    app._poll_event_queue()

    app._log_maint.assert_any_call("Downloading daily.cvd...")
    app._log_maint.assert_any_call("Virus definitions up to date!")
    assert app.is_updating is False
    app.btn_update_sig.config.assert_called_with(state=tk_app_mod.tk.NORMAL)
    app._show_info.assert_called_once_with(
        "Signatures Updated", "Virus definitions up to date!"
    )


def test_tkinter_app_scan_cancelled_report():
    """Validates GUI cleanup and warning log when a scan report indicates cancellation."""
    mock_root = MagicMock()
    app = tk_app_mod.TkinterApp.__new__(tk_app_mod.TkinterApp)
    app.root = mock_root
    app.event_queue = queue.Queue()
    app.is_scanning = True
    app.progressbar = MagicMock()
    app.btn_quick = MagicMock()
    app.btn_full = MagicMock()
    app.btn_custom = MagicMock()
    app.btn_stop = MagicMock()
    app.lbl_progress = MagicMock()
    app._log_msg = MagicMock()
    app._show_info = MagicMock()

    cancelled_report = ScanReport("Quick Scan")
    cancelled_report.scanned_files = 42
    cancelled_report.threats_found = 0
    cancelled_report.cancelled = True
    app.event_queue.put(("scan_done", cancelled_report))

    app._poll_event_queue()

    assert app.is_scanning is False
    app.progressbar.stop.assert_called_once()
    app.lbl_progress.config.assert_called_with(text="Scan cancelled.")
    app._show_info.assert_not_called()


def test_tkinter_app_double_launch_protection():
    """Validates that triggering launch while already scanning safely no-ops."""
    app = tk_app_mod.TkinterApp.__new__(tk_app_mod.TkinterApp)
    app.is_scanning = True
    app.scanner = MagicMock()

    # Attempting to launch another scan must return immediately without starting a thread
    app._launch_scan(["/test"], "Quick Scan")
    app.scanner.scan.assert_not_called()


def test_tkinter_app_double_update_protection():
    """Validates that triggering update while already updating safely no-ops."""
    app = tk_app_mod.TkinterApp.__new__(tk_app_mod.TkinterApp)
    app.is_updating = True
    app.updater = MagicMock()

    app._start_signature_update()
    app.updater.run_update.assert_not_called()


def test_tkinter_app_geometry_format_validity():
    """Validates that window geometry specifier is formatted as WxH[+X+Y] without commas and fits screen."""
    import re

    # 1. Standard desktop display (1920x1080)
    mock_root_1080p = MagicMock()
    mock_root_1080p.winfo_screenwidth.return_value = 1920
    mock_root_1080p.winfo_screenheight.return_value = 1080
    app, _, _, _, _ = _create_test_app(mock_root_1080p)

    geo_arg = mock_root_1080p.geometry.call_args[0][0]
    assert "," not in geo_arg, f"Geometry string '{geo_arg}' must not contain commas"
    assert "x" in geo_arg, f"Geometry string '{geo_arg}' must use 'x' separator"
    assert re.match(r"^\d+x\d+(\+\d+\+\d+)?$", geo_arg), f"Invalid geometry format: {geo_arg}"
    assert geo_arg.startswith("840x620")

    # 2. VirtualBox / Small VM display (800x600)
    mock_root_vm = MagicMock()
    mock_root_vm.winfo_screenwidth.return_value = 800
    mock_root_vm.winfo_screenheight.return_value = 600
    app_vm, _, _, _, _ = _create_test_app(mock_root_vm)

    geo_arg_vm = mock_root_vm.geometry.call_args[0][0]
    assert "," not in geo_arg_vm
    assert re.match(r"^\d+x\d+(\+\d+\+\d+)?$", geo_arg_vm)
    w_vm, h_vm = map(int, geo_arg_vm.split("+")[0].split("x"))
    assert w_vm <= 800, f"Width {w_vm} must fit inside 800px display"
    assert h_vm <= 600, f"Height {h_vm} must fit inside 600px display"


def test_tkinter_app_custom_scan_file_browser():
    """Validates single file browser execution."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    with patch.object(tk_app_mod, "filedialog") as mock_fd, patch.object(
        app, "_launch_scan"
    ) as mock_launch:
        mock_fd.askopenfilename.return_value = "/tmp/test_file.exe"
        app._browse_and_scan_file()
        mock_launch.assert_called_once()
        args = mock_launch.call_args[0]
        assert args[0] == ["/tmp/test_file.exe"]


def test_tkinter_app_log_buffer_memory_bounding():
    """Validates that log text buffer prunes older entries when exceeding 1000 lines."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    # Mock index to simulate 1050 lines
    app.txt_log.index.return_value = "1050.0"
    app._log_msg("Test line")
    app.txt_log.delete.assert_called_with("1.0", "50.0")


def test_tkinter_app_missing_engine_scan_guard():
    """Validates that trying to scan without clamscan displays an informative error dialog."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    app.detector.get_clamscan_path.return_value = None
    app.detector.check_daemon_socket.return_value = (False, "Offline")

    with patch.object(app, "_show_error") as mock_err:
        app._launch_scan(["/tmp"], "Test Scan")
        assert app.is_scanning is False
        mock_err.assert_called_once()
        assert "ClamAV Engine Required" in mock_err.call_args[0][0]


def test_tkinter_app_scan_error_report():
    """Validates that scan errors are reported as errors rather than false clean scans."""
    mock_root = MagicMock()
    app, _, _, _, _ = _create_test_app(mock_root)

    err_report = ScanReport("Quick Scan")
    err_report.errors_count = 1
    err_report.summary_text = "Error: clamscan executable not found."
    app.event_queue.put(("scan_done", err_report))

    with patch.object(app, "_show_error") as mock_err, patch.object(
        app, "_show_info"
    ) as mock_info:
        app._poll_event_queue()
        assert app.is_scanning is False
        mock_err.assert_called_once()
        mock_info.assert_not_called()
        assert "Scan Error" in mock_err.call_args[0][0]


if __name__ == "__main__":
    print("\n=== Running test_tk_app.py test suite ===")
    test_run_tkinter_app_when_tk_none()
    print("  [PASS] test_run_tkinter_app_when_tk_none")
    test_run_tkinter_app_on_tcl_error()
    print("  [PASS] test_run_tkinter_app_on_tcl_error")
    test_tkinter_app_event_queue_processing()
    print("  [PASS] test_tkinter_app_event_queue_processing")
    test_tkinter_app_event_queue_clean_scan()
    print("  [PASS] test_tkinter_app_event_queue_clean_scan")
    test_tkinter_app_unknown_event_in_queue()
    print("  [PASS] test_tkinter_app_unknown_event_in_queue")
    test_tkinter_app_stop_scan()
    print("  [PASS] test_tkinter_app_stop_scan")
    test_tkinter_app_quarantine_refresh()
    print("  [PASS] test_tkinter_app_quarantine_refresh")
    test_tkinter_app_quarantine_restore_actions()
    print("  [PASS] test_tkinter_app_quarantine_restore_actions")
    test_tkinter_app_quarantine_delete_actions()
    print("  [PASS] test_tkinter_app_quarantine_delete_actions")
    test_tkinter_app_custom_scan_folder_browser()
    print("  [PASS] test_tkinter_app_custom_scan_folder_browser")
    test_tkinter_app_on_close_during_scan()
    print("  [PASS] test_tkinter_app_on_close_during_scan")
    test_tkinter_app_signature_update_events()
    print("  [PASS] test_tkinter_app_signature_update_events")
    test_tkinter_app_scan_cancelled_report()
    print("  [PASS] test_tkinter_app_scan_cancelled_report")
    test_tkinter_app_double_launch_protection()
    print("  [PASS] test_tkinter_app_double_launch_protection")
    test_tkinter_app_double_update_protection()
    print("  [PASS] test_tkinter_app_double_update_protection")
    test_tkinter_app_geometry_format_validity()
    print("  [PASS] test_tkinter_app_geometry_format_validity")
    test_tkinter_app_custom_scan_file_browser()
    print("  [PASS] test_tkinter_app_custom_scan_file_browser")
    test_tkinter_app_log_buffer_memory_bounding()
    print("  [PASS] test_tkinter_app_log_buffer_memory_bounding")
    test_tkinter_app_missing_engine_scan_guard()
    print("  [PASS] test_tkinter_app_missing_engine_scan_guard")
    test_tkinter_app_scan_error_report()
    print("  [PASS] test_tkinter_app_scan_error_report")
    print("All 20 Tkinter Lite tests passed successfully!\n")


