"""
Unit tests for setup/setup.py installer, updater, and diagnostic routines.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
try:
    import pytest
except ImportError:
    pytest = None

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


def test_venv_manager_cross_platform_corruption():
    """Validates that foreign OS venvs (e.g. Windows Scripts on Linux) are flagged as corrupted."""
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        venv_mgr = VenvManager(fake_root, logger)

        if sys.platform != "win32":
            # Simulate Windows venv copied to Linux
            scripts_dir = fake_root / ".venv" / "Scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "python.exe").touch()
            assert venv_mgr.is_cross_platform_corrupted() is True
            assert venv_mgr.exists() is False
        else:
            # Simulate Linux venv copied to Windows
            bin_dir = fake_root / ".venv" / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").touch()
            assert venv_mgr.is_cross_platform_corrupted() is True
            assert venv_mgr.exists() is False


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
            (fake_root / "Desktop").mkdir(parents=True, exist_ok=True)
            success = shortcut_mgr._create_linux_shortcuts()
            assert success is True

            desktop_file = fake_root / ".local" / "share" / "applications" / "pyegclamui.desktop"
            assert desktop_file.is_file()
            content = desktop_file.read_text(encoding="utf-8")
            assert "Name=pyEGClamUI" in content
            assert "Exec=" in content

            user_desktop = fake_root / "Desktop" / "pyegclamui.desktop"
            assert user_desktop.is_file()

            # Verify terminal CLI command wrappers
            bin_dir = fake_root / ".local" / "bin"
            assert bin_dir.is_dir()
            for cmd in ["pyegclamui", "egclam", "pyclamui", "pyegclamui-lite", "pyclamui-lite", "pyegclamui-scan", "pyegclamui-setup"]:
                wrapper_file = bin_dir / cmd
                assert wrapper_file.is_file(), f"Expected CLI wrapper {wrapper_file} to exist"
                content = wrapper_file.read_text(encoding="utf-8")
                assert "#!/usr/bin/env bash" in content
                assert "exec " in content
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

            # Verify macOS CLI wrappers in ~/.local/bin
            bin_dir = fake_root / ".local" / "bin"
            assert bin_dir.is_dir()
            for cmd in ["pyegclamui", "egclam", "pyclamui", "pyegclamui-lite", "pyclamui-lite"]:
                wrapper = bin_dir / cmd
                assert wrapper.is_file()
                assert "exec " in wrapper.read_text(encoding="utf-8")
        finally:
            Path.home = orig_home


def test_shortcut_manager_windows_generation():
    """Validates Windows CLI command wrappers generation into WindowsApps folder."""
    logger = SetupLogger()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_root = Path(tmpdir)
        venv_mgr = VenvManager(fake_root, logger)
        shortcut_mgr = ShortcutManager(fake_root, venv_mgr, logger)

        # Mock pythonw.exe in .venv/Scripts
        pyw = fake_root / ".venv" / "Scripts" / "pythonw.exe"
        pyw.parent.mkdir(parents=True, exist_ok=True)
        pyw.write_text("", encoding="utf-8")

        fake_home = fake_root / "UserHome"
        win_apps = fake_home / "AppData" / "Local" / "Microsoft" / "WindowsApps"
        win_apps.mkdir(parents=True, exist_ok=True)

        orig_env = os.environ.copy()
        try:
            os.environ["USERPROFILE"] = str(fake_home)
            os.environ["APPDATA"] = str(fake_home / "AppData" / "Roaming")

            # Mock powershell and python binary resolution
            with patch("setup.run_hidden_process") as mock_proc, patch.object(
                venv_mgr, "get_pythonw_exe", return_value=pyw
            ), patch.object(
                venv_mgr, "get_python_exe", return_value=pyw
            ):
                mock_proc.return_value = MagicMock(returncode=0)
                success = shortcut_mgr._create_windows_shortcuts()
                assert success is True

                for cmd in ["pyegclamui", "egclam", "pyclamui", "pyegclamui-lite", "pyclamui-lite"]:
                    wrapper = win_apps / f"{cmd}.cmd"
                    assert wrapper.is_file(), f"Expected Windows wrapper {wrapper} to exist"
                    content = wrapper.read_text(encoding="utf-8")
                    assert "@echo off" in content
                    assert "-m pyegclamui" in content
        finally:
            os.environ.clear()
            os.environ.update(orig_env)


class SimpleMonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=None):
        if value is None and isinstance(target, str):
            value = name
            import importlib
            mod_name, attr_name = target.rsplit(".", 1)
            target = importlib.import_module(mod_name)
            name = attr_name
        orig = getattr(target, name)
        self._undo.append((target, name, orig))
        setattr(target, name, value)

    def undo(self):
        for target, name, orig in reversed(self._undo):
            setattr(target, name, orig)
        self._undo.clear()


def test_global_updater_mock(monkeypatch=None):
    if monkeypatch is None:
        mp = SimpleMonkeyPatch()
    else:
        mp = monkeypatch
    try:
        logger = SetupLogger()
        detector = SystemDetector(PROJECT_ROOT)
        venv_mgr = VenvManager(PROJECT_ROOT, logger)
        clam_prov = ClamAVProvisioner(detector, logger)
        updater = GlobalUpdater(PROJECT_ROOT, venv_mgr, clam_prov, logger)

        # Mock subprocess.run and clam_prov methods
        mp.setattr(clam_prov, "update_signatures", lambda: True)
        mp.setattr(venv_mgr, "install_dependencies", lambda: True)

        success = updater.execute_update()
        assert success is True
    finally:
        if monkeypatch is None:
            mp.undo()


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


def test_root_setup_cli_forwarding():
    """Validates that running 'python setup.py --check' from root forwards correctly."""
    cmd = [sys.executable, str(PROJECT_ROOT / "setup.py"), "--check"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "System Diagnostic & Compatibility Audit" in res.stdout


def test_root_setup_cli_help_forwarding():
    """Validates that running 'python setup.py --help' forwards correctly."""
    cmd = [sys.executable, str(PROJECT_ROOT / "setup.py"), "--help"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "pyEGClamUI - Unified Cross-Platform Setup" in res.stdout
    assert "--install" in res.stdout


def test_root_setup_module_reexport():
    """Validates that importing setup directly from project root re-exports public installer symbols."""
    code = "import setup; assert hasattr(setup, 'SystemDetector'); assert hasattr(setup, 'VenvManager'); print('OK')"
    cmd = [sys.executable, "-c", code]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "OK" in res.stdout


def test_root_setup_editable_wheel_forwarding():
    """Validates that setuptools packaging commands (e.g. editable_wheel) are handled by setuptools, not installer."""
    cmd = [sys.executable, str(PROJECT_ROOT / "setup.py"), "editable_wheel", "--help"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    assert "editable_wheel" in res.stdout
    assert "unrecognized arguments" not in res.stderr


def test_prompt_user_behavior(monkeypatch=None):
    """Tests prompt_user under purge_all, interactive yes/no, and non-interactive defaults."""
    if monkeypatch is None:
        mp = SimpleMonkeyPatch()
    else:
        mp = monkeypatch

    try:
        # purge_all is always True
        assert prompt_user("Delete?", default=False, purge_all=True) is True

        # Monkeypatch interactive input 'y'
        mp.setattr(sys.stdin, "isatty", lambda: True)
        mp.setattr("builtins.input", lambda: "y")
        assert prompt_user("Delete?", default=False, purge_all=False) is True

        # Monkeypatch interactive input 'n'
        mp.setattr("builtins.input", lambda: "n")
        assert prompt_user("Delete?", default=False, purge_all=False) is False

        # Non-interactive fallback
        mp.setattr(sys.stdin, "isatty", lambda: False)
        assert prompt_user("Delete?", default=False, purge_all=False) is False
        assert prompt_user("Delete?", default=True, purge_all=False) is True
    finally:
        if monkeypatch is None:
            mp.undo()


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


def test_run_uninstall_purge_all_mock(monkeypatch=None):
    """Tests run_uninstall in purge_all mode with mocked dependencies."""
    if monkeypatch is None:
        mp = SimpleMonkeyPatch()
    else:
        mp = monkeypatch

    try:
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
            mp.setattr(shortcut_mgr, "remove_shortcuts", lambda: shortcut_removed.append(True))
            mp.setattr(clam_prov, "remove_daemon_service", lambda: True)
            mp.setattr(detector, "is_daemon_running", lambda: False)
            mp.setattr("setup.get_app_directories", lambda: {
                "config": fake_config,
                "data": fake_data,
                "logs": fake_data / "logs",
                "quarantine": fake_data / "quarantine",
            })

            # Run uninstall with purge_all=True
            run_uninstall(shortcut_mgr, venv_mgr, clam_prov, detector, logger, purge_all=True)

            assert len(shortcut_removed) == 1
    finally:
        if monkeypatch is None:
            mp.undo()
        assert not fake_venv.exists()
        assert not fake_config.exists()
        assert not fake_data.exists()


def test_is_32bit_architecture_detection(monkeypatch=None):
    """Validates 32-bit architecture detection for i686/i386/armv7."""
    logger = SetupLogger()
    venv_mgr = VenvManager(PROJECT_ROOT, logger)

    import platform
    orig_machine = platform.machine

    try:
        platform.machine = lambda: "i686"
        assert venv_mgr._is_32bit_architecture() is True

        platform.machine = lambda: "i386"
        assert venv_mgr._is_32bit_architecture() is True

        platform.machine = lambda: "armv7l"
        assert venv_mgr._is_32bit_architecture() is True

        platform.machine = lambda: "x86_64"
        # On 64-bit systems sys.maxsize > 2**32
        if sys.maxsize > 2**32:
            assert venv_mgr._is_32bit_architecture() is False
    finally:
        platform.machine = orig_machine


def test_verify_pyside6_runtime_when_missing():
    """Validates that _verify_pyside6_runtime handles missing PySide6 cleanly without crashing."""
    logs = []
    logger = SetupLogger(callback=lambda msg, lvl: logs.append((msg, lvl)))
    venv_mgr = VenvManager(PROJECT_ROOT, logger)

    import setup as setup_mod
    orig_run = setup_mod.run_hidden_process

    class MockResult:
        returncode = 1
        stderr = "ModuleNotFoundError: No module named 'PySide6'"
        stdout = ""

    try:
        setup_mod.run_hidden_process = lambda *args, **kwargs: MockResult()
        fake_py = PROJECT_ROOT / ".venv" / "bin" / "python"
        result = venv_mgr._verify_pyside6_runtime(fake_py)
        assert result is True

        # Check logged messages
        log_texts = [msg for msg, lvl in logs]
        assert any("Core Antivirus CLI tools installed" in m for m in log_texts)
    finally:
        setup_mod.run_hidden_process = orig_run


def test_app_main_cli_fallback_when_pyside6_missing():
    """Validates that pyegclamui.gui.app.main exits with helpful CLI instructions when PySide6 is unavailable."""
    import pyegclamui.gui.app as app_mod
    import builtins

    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError(f"No module named '{name}'")
        return orig_import(name, *args, **kwargs)

    try:
        builtins.__import__ = mock_import
        exit_code = app_mod.main()
        assert exit_code == 1
    finally:
        builtins.__import__ = orig_import


if __name__ == "__main__":
    print("\n=== Running test_setup_script.py test suite ===")
    test_funcs = [
        test_system_detector_properties,
        test_setup_logger_callback,
        test_venv_manager_paths,
        test_venv_manager_cross_platform_corruption,
        test_shortcut_manager_linux_generation,
        test_shortcut_manager_macos_generation,
        test_shortcut_manager_windows_generation,
        test_global_updater_mock,
        test_setup_cli_check_subprocess,
        test_setup_cli_help_subprocess,
        test_root_setup_cli_forwarding,
        test_root_setup_cli_help_forwarding,
        test_root_setup_module_reexport,
        test_root_setup_editable_wheel_forwarding,
        test_prompt_user_behavior,
        test_get_app_directories_structure,
        test_clean_autostart_execution,
        test_run_uninstall_purge_all_mock,
        test_is_32bit_architecture_detection,
        test_verify_pyside6_runtime_when_missing,
        test_app_main_cli_fallback_when_pyside6_missing,
    ]
    passed = 0
    for fn in test_funcs:
        fn()
        passed += 1
        print(f"  [PASS] {fn.__name__}")
    print(f"\nAll {passed} setup and platform tests completed successfully!\n")


