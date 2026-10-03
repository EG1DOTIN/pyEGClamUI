"""
Unit tests for ClamEngineInstaller and ClamSetupDialog wizard.
"""

import os
import tempfile
from pathlib import Path
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from pyegclamui.core.setup_engine import ClamEngineInstaller
from pyegclamui.gui.setup_dialog import ClamSetupDialog



@pytest.fixture
def setup_dialog(qapp):
    dlg = ClamSetupDialog()
    yield dlg
    dlg.close()
    dlg.deleteLater()
    qapp.processEvents()


def test_installer_is_engine_installed():
    installer = ClamEngineInstaller()
    # Returns boolean matching detector
    assert isinstance(installer.is_engine_installed(), bool)


def test_initialize_freshclam_conf_from_sample():
    with tempfile.TemporaryDirectory() as tmpdir:
        clam_dir = Path(tmpdir)
        sample_file = clam_dir / "freshclam.conf.sample"
        sample_file.write_text("DatabaseMirror database.clamav.net\nExample\nLogSyslog yes\n", encoding="utf-8")

        success, msg = ClamEngineInstaller.initialize_freshclam_conf(clam_dir)
        assert success

        target_conf = clam_dir / "freshclam.conf"
        assert target_conf.exists()
        content = target_conf.read_text(encoding="utf-8")
        assert "# Example" in content
        assert "DatabaseMirror database.clamav.net" in content


def test_initialize_freshclam_conf_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        clam_dir = Path(tmpdir)
        # No sample file present
        success, msg = ClamEngineInstaller.initialize_freshclam_conf(clam_dir)
        assert success
        target_conf = clam_dir / "freshclam.conf"
        assert target_conf.exists()
        content = target_conf.read_text(encoding="utf-8")
        assert "DatabaseMirror" in content


def test_register_path_environment():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        res = ClamEngineInstaller.register_path_environment(test_dir)
        assert res is True
        path_env = os.environ.get("PATH", "").lower()
        assert str(test_dir.resolve()).lower() in path_env or str(test_dir).lower() in path_env


def test_setup_dialog_ui(setup_dialog):
    dlg = setup_dialog
    assert "Setup Wizard" in dlg.windowTitle()
    assert dlg.card_auto is not None
    assert dlg.card_locate is not None
    assert dlg.btn_auto_install is not None
    assert dlg.btn_browse is not None
    assert dlg.btn_decline is not None
    assert dlg.progress_bar is not None
    assert not dlg.progress_frame.isVisible()

    # Test progress and status updates
    dlg.on_status_update("Testing download...")
    assert dlg.lbl_progress_status.text() == "Testing download..."
    dlg.on_progress_update(50)
    assert dlg.progress_bar.value() == 50

    # Test verbose console drawer
    dlg.progress_frame.setVisible(True)
    assert dlg.txt_console is not None
    dlg.on_verbose_toggled(False)
    assert dlg.txt_console.isHidden()
    dlg.on_verbose_toggled(True)
    assert not dlg.txt_console.isHidden()
    assert not dlg.btn_copy_log.isHidden()

    dlg.on_log_emitted("[*] Live installation streaming test line")
    assert "Live installation streaming test line" in dlg.txt_console.toPlainText()

    dlg.on_copy_log_clicked()
    assert dlg.btn_copy_log.text() == "Copied!"


def test_install_engine_with_on_log(monkeypatch):
    installer = ClamEngineInstaller()
    logs = []

    # Mock internal installer routines to prevent real network / package manager calls in CI
    def fake_winget(on_status=None, on_log=None):
        if on_status:
            on_status("Mock winget running...")
        if on_log:
            on_log("[*] Mock winget log entry")
        return True, "Mock winget success"

    monkeypatch.setattr(installer, "_install_via_winget", fake_winget)
    monkeypatch.setattr(installer, "_post_install_configure", lambda *a, **kw: None)
    monkeypatch.setattr(installer, "_install_via_msi", lambda *a, **kw: (True, "Mock MSI success"))

    success, msg = installer.install_engine(on_log=lambda l: logs.append(l))
    assert isinstance(success, bool)
    assert len(logs) > 0 or success


def test_setup_dialog_browse_valid_folder(setup_dialog, monkeypatch):
    dlg = setup_dialog
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        clamscan_name = "clamscan.exe" if os.name == "nt" else "clamscan"
        clamd_name = "clamd.exe" if os.name == "nt" else "clamd"
        freshclam_name = "freshclam.exe" if os.name == "nt" else "freshclam"

        (tmp_path / clamscan_name).write_text("dummy", encoding="utf-8")
        (tmp_path / clamd_name).write_text("dummy", encoding="utf-8")
        (tmp_path / freshclam_name).write_text("dummy", encoding="utf-8")

        monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory", lambda *args, **kwargs: str(tmp_path))
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", lambda *args, **kwargs: None)

        finished_results = []
        dlg.setup_finished.connect(lambda res: finished_results.append(res))

        dlg.on_browse_clicked()

        assert len(finished_results) == 1
        assert finished_results[0] is True
        assert clamscan_name in dlg.config.get("scan_settings", "custom_clamscan_path")
        assert clamd_name in dlg.config.get("scan_settings", "custom_clamd_path")
        assert freshclam_name in dlg.config.get("scan_settings", "custom_freshclam_path")


def test_setup_dialog_browse_invalid_folder(setup_dialog, monkeypatch):
    dlg = setup_dialog
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty folder without clamscan
        monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory", lambda *args, **kwargs: str(tmpdir))
        warning_shown = []
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *args, **kwargs: warning_shown.append(True))

        dlg.on_browse_clicked()
        assert len(warning_shown) == 1


def test_setup_dialog_browse_cancelled(setup_dialog, monkeypatch):
    dlg = setup_dialog
    # User clicks Cancel on folder picker
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getExistingDirectory", lambda *args, **kwargs: "")
    dlg.on_browse_clicked()
    # Should cleanly return without crashing


def test_setup_dialog_decline_yes(setup_dialog, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    dlg = setup_dialog
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", lambda *args, **kwargs: QMessageBox.Yes)

    finished_results = []
    dlg.setup_finished.connect(lambda res: finished_results.append(res))

    dlg.on_decline_clicked()
    assert len(finished_results) == 1
    assert finished_results[0] is False


def test_setup_dialog_decline_no(setup_dialog, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    dlg = setup_dialog
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", lambda *args, **kwargs: QMessageBox.No)

    finished_results = []
    dlg.setup_finished.connect(lambda res: finished_results.append(res))

    dlg.on_decline_clicked()
    assert len(finished_results) == 0


def test_setup_dialog_install_finished_success(setup_dialog, monkeypatch):
    dlg = setup_dialog
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", lambda *args, **kwargs: None)

    finished_results = []
    dlg.setup_finished.connect(lambda res: finished_results.append(res))

    dlg.on_install_finished(True, "Engine successfully installed")
    assert dlg.progress_bar.value() == 100
    assert "installed" in dlg.lbl_progress_status.text()
    assert len(finished_results) == 1
    assert finished_results[0] is True


def test_setup_dialog_install_finished_failure(setup_dialog, monkeypatch):
    dlg = setup_dialog
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *args, **kwargs: None)

    finished_results = []
    dlg.setup_finished.connect(lambda res: finished_results.append(res))

    dlg.on_install_finished(False, "Network download timed out")
    assert "failed" in dlg.lbl_progress_status.text().lower()
    assert dlg.card_auto.isEnabled()
    assert dlg.card_locate.isEnabled()
    assert len(finished_results) == 0


def test_setup_dialog_close_event(setup_dialog):
    from PySide6.QtGui import QCloseEvent
    dlg = setup_dialog
    event = QCloseEvent()
    dlg.closeEvent(event)
    assert event.isAccepted()
