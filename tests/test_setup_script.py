"""
Unit tests for setup/setup.py installer, updater, and diagnostic routines.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "setup"))

from setup import (
    Colors,
    SetupLogger,
    SystemDetector,
    VenvManager,
    ClamAVProvisioner,
    ShortcutManager,
    GlobalUpdater,
    clean_autostart,
    get_app_directories,
    prompt_user,
    run_uninstall,
)


def test_system_detector_properties():
    detector = SystemDetector(PROJECT_ROOT)
    assert detector.is_python_supported() is True
    assert detector.os_type == sys.platform
    assert isinstance(detector.arch, str)

    # Daemon on an unused port should return False
    assert detector.is_daemon_running("127.0.0.1", 59999) is False


def test_setup_logger_callback():
    logs = []
    logger = SetupLogger(verbose=True, callback=lambda msg, lvl: logs.append((msg, lvl)))

    logger.info("Informational message")
    logger.ok("Operation succeeded")
    logger.warn("Warning alert")
    logger.error("Error occurred")
    logger.step(1, 3, "Test Step")
    logger.exec("echo test")

    assert len(logs) == 6
    assert logs[0] == ("Informational message", "info")
    assert logs[1] == ("Operation succeeded", "ok")
    assert logs[2] == ("Warning alert", "warn")
    assert logs[3] == ("Error occurred", "error")
    assert logs[4] == ("[1/3] Test Step", "step")
    assert logs[5] == ("echo test", "exec")


def test_venv_manager_paths():
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        venv_mgr = VenvManager(fake_root, logger)

        py_exe = venv_mgr.get_python_exe()
        assert py_exe is not None
        assert "python" in py_exe.name.lower()

        pyw_exe = venv_mgr.get_pythonw_exe()
        assert pyw_exe is not None

        # Does not exist in clean temporary directory
        assert venv_mgr.exists() is False

        # Create simulated executable
        py_exe.parent.mkdir(parents=True, exist_ok=True)
        py_exe.touch()
        assert venv_mgr.exists() is True


def test_shortcut_manager_linux_generation():
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        (fake_root / "src" / "pyegclamui" / "assets").mkdir(parents=True)
        (fake_root / "src" / "pyegclamui" / "assets" / "egav.png").write_text("dummy", encoding="utf-8")

        venv_mgr = VenvManager(fake_root, logger)
        shortcut_mgr = ShortcutManager(fake_root, venv_mgr, logger)

        # Mock Path.home to point to tmpdir
        orig_home = Path.home
        try:
            Path.home = staticmethod(lambda: fake_root)
            success = shortcut_mgr._create_linux_shortcuts()
            assert success is True

            desktop_file = fake_root / ".local" / "share" / "applications" / "pyegclamui.desktop"
            assert desktop_file.is_file()
            content = desktop_file.read_text(encoding="utf-8")
            assert "Name=pyEGClamUI" in content
            assert "Exec=" in content
        finally:
            Path.home = orig_home


def test_shortcut_manager_macos_generation():
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        venv_mgr = VenvManager(fake_root, logger)
        shortcut_mgr = ShortcutManager(fake_root, venv_mgr, logger)

        orig_home = Path.home
        try:
            Path.home = staticmethod(lambda: fake_root)
            (fake_root / "Desktop").mkdir(parents=True, exist_ok=True)
            success = shortcut_mgr._create_macos_shortcuts()
            assert success is True

            launcher = fake_root / "Desktop" / "pyEGClamUI.command"
            assert launcher.is_file()
            content = launcher.read_text(encoding="utf-8")
            assert "pyegclamui" in content
        finally:
            Path.home = orig_home


def test_global_updater_mock(monkeypatch):
    logger = SetupLogger()
    detector = SystemDetector(PROJECT_ROOT)
    venv_mgr = VenvManager(PROJECT_ROOT, logger)
    clam_prov = ClamAVProvisioner(detector, logger)
    updater = GlobalUpdater(PROJECT_ROOT, venv_mgr, clam_prov, logger)

    # Mock subprocess.run and clam_prov methods
    monkeypatch.setattr(clam_prov, "update_signatures", lambda: True)
    monkeypatch.setattr(venv_mgr, "install_dependencies", lambda: True)

    success = updater.execute_update()
    assert success is True


def test_setup_cli_check_subprocess():
    """Validates that running 'python setup/setup.py --check' executes cleanly."""
    cmd = [sys.executable, str(PROJECT_ROOT / "setup" / "setup.py"), "--check"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "System Diagnostic & Compatibility Audit" in res.stdout
    assert "Python Version" in res.stdout


def test_setup_cli_help_subprocess():
    """Validates that running 'python setup/setup.py --help' executes cleanly."""
    cmd = [sys.executable, str(PROJECT_ROOT / "setup" / "setup.py"), "--help"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "--install" in res.stdout
    assert "--update" in res.stdout
    assert "--check" in res.stdout
    assert "--uninstall" in res.stdout
    assert "--purge-all" in res.stdout


def test_prompt_user_behavior(monkeypatch):
    """Tests prompt_user under purge_all, interactive yes/no, and non-interactive defaults."""
    # purge_all is always True
    assert prompt_user("Delete?", default=False, purge_all=True) is True

    # Monkeypatch interactive input 'y'
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "y")
    assert prompt_user("Delete?", default=False, purge_all=False) is True

    # Monkeypatch interactive input 'n'
    monkeypatch.setattr("builtins.input", lambda: "n")
    assert prompt_user("Delete?", default=False, purge_all=False) is False

    # Non-interactive fallback
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert prompt_user("Delete?", default=False, purge_all=False) is False
    assert prompt_user("Delete?", default=True, purge_all=False) is True


def test_get_app_directories_structure():
    """Validates that standard app directories are resolved across platforms."""
    dirs = get_app_directories()
    assert "config" in dirs
    assert "data" in dirs
    assert "logs" in dirs
    assert "quarantine" in dirs
    assert isinstance(dirs["config"], Path)
    assert isinstance(dirs["data"], Path)


def test_clean_autostart_execution():
    """Validates that clean_autostart runs without throwing exceptions."""
    logger = SetupLogger()
    result = clean_autostart(logger)
    assert isinstance(result, bool)


def test_run_uninstall_purge_all_mock(monkeypatch):
    """Tests run_uninstall in purge_all mode with mocked dependencies."""
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        fake_venv = fake_root / ".venv"
        fake_venv.mkdir()
        fake_config = fake_root / "config"
        fake_config.mkdir()
        fake_data = fake_root / "data"
        fake_data.mkdir()

        venv_mgr = VenvManager(fake_root, logger)
        shortcut_mgr = ShortcutManager(fake_root, venv_mgr, logger)
        detector = SystemDetector(fake_root)
        clam_prov = ClamAVProvisioner(detector, logger)

        # Mock removal methods and isolated app directories
        shortcut_removed = []
        monkeypatch.setattr(shortcut_mgr, "remove_shortcuts", lambda: shortcut_removed.append(True))
        monkeypatch.setattr(clam_prov, "remove_daemon_service", lambda: True)
        monkeypatch.setattr(detector, "is_daemon_running", lambda: False)
        monkeypatch.setattr("setup.get_app_directories", lambda: {
            "config": fake_config,
            "data": fake_data,
            "logs": fake_data / "logs",
            "quarantine": fake_data / "quarantine",
        })

        # Run uninstall with purge_all=True
        run_uninstall(shortcut_mgr, venv_mgr, clam_prov, detector, logger, purge_all=True)

        assert len(shortcut_removed) == 1
        assert not fake_venv.exists()
        assert not fake_config.exists()
        assert not fake_data.exists()

