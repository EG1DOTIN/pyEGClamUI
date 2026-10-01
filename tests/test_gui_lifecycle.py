"""
Unit and integration tests for PySide6 GUI in offscreen mode.
"""

import os
from unittest.mock import MagicMock
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication
from pyegclamui.gui.main_window import MainWindow
from pyegclamui.gui.scan_dialog import ScanDialog
from pyegclamui.gui.update_dialog import ClamUpdateDialog, UpdateWorker
from pyegclamui.core.scanner import ScanType, ScanReport


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()



@pytest.fixture
def main_win(qapp, monkeypatch):
    from pyegclamui.core.config import Config
    from pyegclamui.core.daemon import ClamDaemonClient
    Config.get_instance().set("preferences", "first_run_completed", True)
    monkeypatch.setattr(ClamDaemonClient, "check_connection", lambda self: (False, "Offline (mock)"))
    win = MainWindow()
    yield win
    if hasattr(win, "guard") and win.guard:
        win.guard.stop()
    win.close()
    win.deleteLater()
    qapp.processEvents()



def test_main_window_tabs_and_controls(main_win):
    win = main_win
    assert win.tabs.count() == 5
    expected_tabs = ["Status", "Scan", "Quarantine", "Settings", "About"]
    for i, name in enumerate(expected_tabs):
        assert name in win.tabs.tabText(i)

    # Verify key dashboard and action controls exist
    assert win.lbl_engine_ver is not None
    assert win.lbl_db_ver is not None
    assert win.lbl_daemon_status is not None
    assert win.lbl_clamscan_path is not None
    assert win.update_btn is not None
    assert win.quarantine_table is not None
    assert win.refresh_vault_btn is not None
    assert win.restore_btn is not None
    assert win.delete_btn is not None
    assert win.clear_vault_btn is not None
    assert win.chk_realtime is not None
    assert win.chk_notifications is not None
    assert win.chk_close_to_tray is not None
    assert win.chk_autostart is not None
    assert win.spin_max_size is not None
    assert win.chk_archives is not None
    assert win.btn_save_settings is not None


def test_main_window_tab_switching(main_win):
    win = main_win
    expected_tabs = ["Status", "Scan", "Quarantine", "Settings", "About"]
    assert win.windowTitle() == "pyEGClamUI - Status"
    for i, name in enumerate(expected_tabs):
        win.tabs.setCurrentIndex(i)
        assert win.tabs.currentIndex() == i
        assert win.windowTitle() == f"pyEGClamUI - {name}"


def test_main_window_tray_and_close_behavior(main_win, qapp):
    """Validates tray attachment, quarantine shortcut, and close-to-tray event handling."""
    win = main_win
    mock_tray = MagicMock()
    mock_tray.isVisible.return_value = True

    win.set_tray(mock_tray)
    assert win.tray is mock_tray

    # 1. Test quarantine navigation from tray
    win.open_quarantine_tab()
    assert win.tabs.currentIndex() == 2

    # 2. Test protection toggle from tray
    win.on_toggle_protection_from_tray(True)
    assert win.chk_realtime.isChecked() is True
    win.on_toggle_protection_from_tray(False)
    assert win.chk_realtime.isChecked() is False

    # 3. Test close-to-tray handling (event should be ignored, window hidden)
    win.config.set("preferences", "close_to_tray", True)
    close_event = QCloseEvent()
    win.closeEvent(close_event)
    assert close_event.isAccepted() is False
    assert mock_tray.notify.called

    # 4. Test normal close when close_to_tray is disabled
    win.config.set("preferences", "close_to_tray", False)
    close_event2 = QCloseEvent()
    win.closeEvent(close_event2)
    assert close_event2.isAccepted() is True


def test_scan_dialog_callbacks(main_win, qapp):
    win = main_win
    dlg = ScanDialog(win, ScanType.QUICK_SCAN, ["."], auto_start=False)
    assert "Quick Scan" in dlg.windowTitle()
    assert dlg.stop_btn is not None
    assert dlg.close_btn is not None

    # 1. Test live file progress callback
    dlg.on_file_scanned("C:/test/file.exe")
    assert "file.exe" in dlg.current_file_label.text()
    assert "1" in dlg.files_count_label.text()

    # 2. Test threat reporting callback
    dlg.on_threat_found({
        "time": "12:00:00",
        "threat": "Win.Test.EICAR",
        "action": "Quarantined",
        "path": "C:/test/eicar.com"
    })
    assert dlg.threats_table.rowCount() == 1
    assert "1" in dlg.threats_count_label.text()

    # 3. Test scan completion handler
    report = ScanReport(ScanType.QUICK_SCAN)
    report.scanned_files = 10
    report.threats_found = 1
    dlg.on_scan_completed(report)
    assert dlg.close_btn.isEnabled()
    assert not dlg.stop_btn.isEnabled()
    assert "Finished" in dlg.title_label.text()
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()


def test_update_dialog_and_worker(main_win, qapp):
    win = main_win

    # 1. Test progress line parsing
    line_bracket = "Time: 4.8s, ETA: 12.8s [======>                  ] 23.00MiB/84.95MiB"
    pct, stage = UpdateWorker._parse_progress(line_bracket)
    assert pct == 24
    assert "23.00MiB/84.95MiB" in stage
    assert "ETA: 12.8s" in stage

    line_mirror = "Connecting to database.clamav.net..."
    pct_m, stage_m = UpdateWorker._parse_progress(line_mirror)
    assert pct_m == -1
    assert "Connecting" in stage_m

    line_done = "Database updated successfully."
    pct_d, stage_d = UpdateWorker._parse_progress(line_done)
    assert pct_d == 100

    # 2. Test ClamUpdateDialog initialization and UI handlers
    mock_updater = MagicMock()
    mock_updater.run_update.return_value = (True, "Database updated successfully.")
    dlg = ClamUpdateDialog(win, updater=mock_updater)

    assert "Virus Signature Update" in dlg.windowTitle()
    assert dlg.btn_close is not None
    assert dlg.btn_cancel is not None

    # Test line emitted
    dlg.on_line_emitted("Downloading main.cvd")
    assert "Downloading main.cvd" in dlg.txt_console.toPlainText()

    # Test progress changed
    dlg.on_progress_changed(50, "Downloading definitions: 50%")
    assert dlg.progress_bar.value() == 50
    assert "50%" in dlg.lbl_status.text()

    # Test toggle console drawer
    dlg.on_toggle_console(True)
    assert not dlg.txt_console.isHidden()
    dlg.on_toggle_console(False)
    assert dlg.txt_console.isHidden()

    # Test update completion
    dlg.on_update_completed(True, "Database updated successfully.")
    assert dlg.btn_close.isEnabled()
    assert not dlg.btn_cancel.isEnabled()
    assert "Successfully" in dlg.lbl_status.text()

    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()

