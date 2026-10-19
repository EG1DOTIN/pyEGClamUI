"""
Unit tests for setup and platform edge cases (setup/setup.py).

Comprehensive test coverage for:
  - SystemDetector executable discovery across platforms (Windows, macOS, Linux)
  - ClamAV socket connectivity timeouts and refused connections
  - VenvManager architecture detection and runtime verification corner cases
  - Diagnostic report output with various system configurations
"""

import platform
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root and setup/ are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "setup"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import setup as setup_mod
from setup import Colors, SetupLogger, SystemDetector, VenvManager, run_diagnostic_check


def test_system_detector_executable_discovery():
    """Validates executable discovery for clamscan, freshclam, and clamd across paths."""
    detector = SystemDetector(PROJECT_ROOT)

    # 1. When shutil.which finds executable
    with patch("shutil.which", return_value="/usr/local/bin/clamscan"):
        p = detector.get_clamscan_path()
        assert p == Path("/usr/local/bin/clamscan")

    with patch("shutil.which", return_value="/usr/local/bin/freshclam"):
        p = detector.get_freshclam_path()
        assert p == Path("/usr/local/bin/freshclam")

    with patch("shutil.which", return_value="/usr/local/bin/clamd"):
        p = detector.get_clamd_path()
        assert p == Path("/usr/local/bin/clamd")

    # 2. When which returns None, checks candidate files
    with patch("shutil.which", return_value=None), patch(
        "sys.platform", "win32"
    ), patch.object(Path, "is_file", return_value=True):
        detector.os_type = "win32"
        p = detector.get_clamscan_path()
        assert p is not None
        assert "ClamAV" in str(p)

    # 3. When binary completely missing
    with patch("shutil.which", return_value=None), patch.object(
        Path, "is_file", return_value=False
    ):
        detector.os_type = "linux"
        assert detector.get_clamscan_path() is None
        assert detector.get_freshclam_path() is None
        assert detector.get_clamd_path() is None


def test_system_detector_daemon_connectivity_edge_cases():
    """Validates clamd TCP socket checks on timeout, refused connection, and success."""
    detector = SystemDetector(PROJECT_ROOT)

    # Success
    with patch("socket.create_connection", return_value=MagicMock()):
        assert detector.is_daemon_running() is True

    # ConnectionRefusedError
    with patch(
        "socket.create_connection",
        side_effect=ConnectionRefusedError("Connection refused"),
    ):
        assert detector.is_daemon_running() is False

    # Socket Timeout
    with patch("socket.create_connection", side_effect=socket.timeout("Timed out")):
        assert detector.is_daemon_running() is False

    # Generic OSError
    with patch(
        "socket.create_connection", side_effect=OSError("Network is unreachable")
    ):
        assert detector.is_daemon_running() is False


def test_venv_manager_is_32bit_edge_cases():
    """Validates 32-bit architecture checks across platforms."""
    logger = SetupLogger()
    mgr = VenvManager(PROJECT_ROOT, logger)

    for arch in ("i386", "i686", "x86", "armv7l", "armv6l"):
        with patch("platform.machine", return_value=arch):
            assert mgr._is_32bit_architecture() is True

    # 64-bit machine on 64-bit Python
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**63 - 1
    ):
        assert mgr._is_32bit_architecture() is False

    # 32-bit pointer space on Linux
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**31 - 1
    ), patch("sys.platform", "linux"):
        assert mgr._is_32bit_architecture() is True


def test_verify_pyside6_runtime_shared_library_missing():
    """Validates diagnostic advice when PySide6 is installed but missing system shared libraries."""
    logs = []
    logger = SetupLogger(callback=lambda msg, lvl: logs.append((msg, lvl)))
    mgr = VenvManager(PROJECT_ROOT, logger)

    class MockLibError:
        returncode = 1
        stderr = "ImportError: libGL.so.1: cannot open shared object file: No such file or directory"
        stdout = ""

    with patch("setup.run_hidden_process", return_value=MockLibError()), patch(
        "sys.platform", "linux"
    ):
        fake_py = PROJECT_ROOT / ".venv" / "bin" / "python"
        res = mgr._verify_pyside6_runtime(fake_py)
        assert res is True
        log_texts = [msg for msg, _ in logs]
        assert any("Qt GUI shared libraries are missing" in m for m in log_texts)
        assert any("libgl1" in m for m in log_texts)


def test_run_diagnostic_check_output():
    """Validates that run_diagnostic_check prints memory, arch, and tier information."""
    detector = SystemDetector(PROJECT_ROOT)
    logger = SetupLogger()
    venv_mgr = VenvManager(PROJECT_ROOT, logger)

    with patch.object(detector, "is_python_supported", return_value=True), patch.object(
        detector, "get_clamscan_path", return_value=Path("/usr/bin/clamscan")
    ), patch.object(
        detector, "get_freshclam_path", return_value=Path("/usr/bin/freshclam")
    ), patch.object(
        detector, "is_daemon_running", return_value=True
    ), patch.object(
        venv_mgr, "exists", return_value=True
    ), patch.object(
        venv_mgr, "is_cross_platform_corrupted", return_value=False
    ), patch(
        "builtins.print"
    ) as mock_print:
        run_diagnostic_check(detector, venv_mgr, logger)
        printed_lines = [
            " ".join(str(a) for a in call.args) for call in mock_print.call_args_list
        ]
        assert any("Memory & Arch:" in line for line in printed_lines)
        assert any("Qualified GUI Tier:" in line for line in printed_lines)
        assert any(
            "ALL SYSTEMS READY FOR EXECUTION" in line for line in printed_lines
        )


def test_system_detector_package_manager():
    """Validates detection of OS package managers and fallback when none found."""
    detector = SystemDetector(PROJECT_ROOT)

    # When apt is present
    with patch("shutil.which", side_effect=lambda name: "/usr/bin/apt" if name == "apt" else None):
        assert detector.detect_package_manager() == "apt"

    # When dnf is present
    with patch("shutil.which", side_effect=lambda name: "/usr/bin/dnf" if name == "dnf" else None):
        assert detector.detect_package_manager() == "dnf"

    # When winget is present on Windows
    with patch("shutil.which", side_effect=lambda name: "C:\\winget.exe" if name == "winget" else None):
        assert detector.detect_package_manager() == "winget"

    # When none found
    with patch("shutil.which", return_value=None):
        assert detector.detect_package_manager() is None


def test_ensure_linux_prerequisites_non_linux_and_no_pm():
    """Validates that non-Linux or systems without package manager exit cleanly."""
    detector = SystemDetector(PROJECT_ROOT)
    logger = SetupLogger()

    # Non-Linux
    detector.os_type = "win32"
    assert detector.ensure_linux_prerequisites(logger) is True

    detector.os_type = "darwin"
    assert detector.ensure_linux_prerequisites(logger) is True

    # Linux without package manager
    detector.os_type = "linux"
    with patch.object(detector, "detect_package_manager", return_value=None):
        assert detector.ensure_linux_prerequisites(logger) is True


def test_venv_manager_binary_resolution():
    """Validates correct resolution of python and pythonw executable paths per platform."""
    logger = SetupLogger()
    mgr = VenvManager(PROJECT_ROOT, logger)

    # Windows
    with patch("sys.platform", "win32"):
        py = mgr.get_python_exe()
        assert py.name == "python.exe"
        assert "Scripts" in str(py)

    # POSIX (Linux/macOS)
    with patch("sys.platform", "linux"):
        py = mgr.get_python_exe()
        pw = mgr.get_pythonw_exe()
        assert py.name == "python"
        assert "bin" in str(py)
        assert pw == py



def test_system_detector_has_virus_signatures():
    """Validates signature database detection when .cvd or .cld files are present."""
    detector = SystemDetector(PROJECT_ROOT)

    # 1. When no database files exist
    with patch.object(Path, "is_dir", return_value=False):
        assert detector.has_virus_signatures() is False

    # 2. When valid .cvd database file exists
    fake_cvd = MagicMock()
    fake_cvd.is_file.return_value = True
    fake_cvd.suffix = ".cvd"
    fake_cvd.stat.return_value.st_size = 5000000

    with patch.object(Path, "is_dir", return_value=True), patch.object(
        Path, "iterdir", return_value=[fake_cvd]
    ):
        assert detector.has_virus_signatures() is True


def test_clamav_provisioner_low_spec_selection_and_fallback():
    """Validates that low-spec systems select standalone clamav and fallbacks work."""
    logger = SetupLogger()
    detector = SystemDetector(PROJECT_ROOT)
    detector.os_type = "linux"
    prov = setup_mod.ClamAVProvisioner(detector, logger)

    # 1. Low-RAM system (< 3.75 GB RAM) prefers standalone clamav
    executed_cmds = []

    def mock_run(cmd, **kwargs):
        executed_cmds.append(cmd)
        m = MagicMock()
        m.returncode = 0
        return m

    def mock_get_path():
        return Path("/usr/bin/clamscan") if executed_cmds else None

    with patch.object(detector, "get_clamscan_path", side_effect=mock_get_path), \
         patch.object(detector, "detect_package_manager", return_value="apt"), \
         patch.object(detector, "is_64bit", return_value=False), \
         patch.object(detector, "get_total_ram_bytes", return_value=int(1.5 * 1024 * 1024 * 1024)), \
         patch("setup.run_hidden_process", side_effect=mock_run), \
         patch("shutil.which", return_value="/usr/bin/sudo"):

        res = prov.install_engine()
        assert res is True
        # Check that executed commands did NOT attempt clamav-daemon
        flat = " ".join(" ".join(c) for c in executed_cmds)
        assert "clamav-daemon" not in flat
        assert "clamav" in flat


if __name__ == "__main__":
    print("\n=== Running test_setup_edge_cases.py test suite ===")
    test_system_detector_executable_discovery()
    print("  [PASS] test_system_detector_executable_discovery")
    test_system_detector_daemon_connectivity_edge_cases()
    print("  [PASS] test_system_detector_daemon_connectivity_edge_cases")
    test_venv_manager_is_32bit_edge_cases()
    print("  [PASS] test_venv_manager_is_32bit_edge_cases")
    test_verify_pyside6_runtime_shared_library_missing()
    print("  [PASS] test_verify_pyside6_runtime_shared_library_missing")
    test_run_diagnostic_check_output()
    print("  [PASS] test_run_diagnostic_check_output")
    test_system_detector_package_manager()
    print("  [PASS] test_system_detector_package_manager")
    test_ensure_linux_prerequisites_non_linux_and_no_pm()
    print("  [PASS] test_ensure_linux_prerequisites_non_linux_and_no_pm")
    test_venv_manager_binary_resolution()
    print("  [PASS] test_venv_manager_binary_resolution")
    test_system_detector_has_virus_signatures()
    print("  [PASS] test_system_detector_has_virus_signatures")
    test_clamav_provisioner_low_spec_selection_and_fallback()
    print("  [PASS] test_clamav_provisioner_low_spec_selection_and_fallback")
    print("All 10 setup edge case tests passed successfully!\n")

