"""
Unit tests for deterministic system capability inspection (src/pyegclamui/core/system_capability.py).

Comprehensive test coverage for hardware specifications, edge cases, and boundary conditions.
"""

import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Ensure src is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pyegclamui.core.system_capability import (
    MIN_RAM_BYTES_TIER1,
    determine_gui_tier,
    get_system_specs,
    get_total_ram_bytes,
    is_64bit_architecture,
)


def test_is_64bit_architecture_detection():
    """Validates 64-bit vs 32-bit architecture determination."""
    # 64-bit AMD64 / x86_64
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**63 - 1
    ):
        assert is_64bit_architecture() is True

    # 64-bit ARM (aarch64 / arm64)
    with patch("platform.machine", return_value="aarch64"), patch.object(
        sys, "maxsize", 2**63 - 1
    ):
        assert is_64bit_architecture() is True

    with patch("platform.machine", return_value="arm64"), patch.object(
        sys, "maxsize", 2**63 - 1
    ):
        assert is_64bit_architecture() is True

    # 32-bit legacy x86 variants
    for arch in ("i386", "i486", "i586", "i686", "x86"):
        with patch("platform.machine", return_value=arch), patch.object(
            sys, "maxsize", 2**31 - 1
        ):
            assert is_64bit_architecture() is False

    # 32-bit ARM variants
    for arm_arch in ("armv7l", "armv7a", "armv7", "armv6l", "armhf"):
        with patch("platform.machine", return_value=arm_arch):
            assert is_64bit_architecture() is False

    # 32-bit pointer space on a 64-bit OS machine string (e.g. 32-bit Python on 64-bit OS)
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**31 - 1
    ):
        assert is_64bit_architecture() is False


def test_determine_gui_tier_logic():
    """Validates deterministic tier selection based on specs and boundaries."""
    # 1. 64-bit with 6.0 GB RAM -> pyside6
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=6 * 1024 * 1024 * 1024,
    ):
        assert determine_gui_tier() == "pyside6"

    # 2. 64-bit with 2.0 GB RAM (e.g. 2 GB VM) -> tkinter
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=2 * 1024 * 1024 * 1024,
    ):
        assert determine_gui_tier() == "tkinter"

    # 3. 32-bit architecture -> tkinter regardless of RAM
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=False
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=8 * 1024 * 1024 * 1024,
    ):
        assert determine_gui_tier() == "tkinter"


def test_ram_threshold_vram_reserve_boundary():
    """Validates RAM boundary handling including hardware VRAM/BIOS reserve margin."""
    # 3.85 GB reported on physical 4GB machine (above calibrated 3.75GB threshold) -> pyside6
    ram_3_85gb = int(3.85 * 1024 * 1024 * 1024)
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes", return_value=ram_3_85gb
    ):
        assert determine_gui_tier() == "pyside6"

    # 3.0 GB system -> strictly below threshold -> tkinter
    ram_3gb = 3 * 1024 * 1024 * 1024
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes", return_value=ram_3gb
    ):
        assert determine_gui_tier() == "tkinter"

    # Boundary: 1 byte below MIN_RAM_BYTES_TIER1 -> tkinter
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=MIN_RAM_BYTES_TIER1 - 1,
    ):
        assert determine_gui_tier() == "tkinter"

    # Boundary: exactly MIN_RAM_BYTES_TIER1 -> pyside6
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=MIN_RAM_BYTES_TIER1,
    ):
        assert determine_gui_tier() == "pyside6"


def test_determine_gui_tier_user_overrides():
    """Validates that explicit user override flags take precedence."""
    # Overrides to Qt
    assert determine_gui_tier("pyside6") == "pyside6"
    assert determine_gui_tier("qt6") == "pyside6"
    assert determine_gui_tier("qt") == "pyside6"
    assert determine_gui_tier("tier1") == "pyside6"
    assert determine_gui_tier("  QT6  ") == "pyside6"
    assert determine_gui_tier("PYSIDE6") == "pyside6"

    # Overrides to Tkinter
    assert determine_gui_tier("tkinter") == "tkinter"
    assert determine_gui_tier("tk") == "tkinter"
    assert determine_gui_tier("lite") == "tkinter"
    assert determine_gui_tier("tier2") == "tkinter"
    assert determine_gui_tier("  LITE  ") == "tkinter"
    assert determine_gui_tier("TK") == "tkinter"

    # Unrecognized or neutral override falls through to deterministic hardware check
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=8 * 1024 * 1024 * 1024,
    ):
        assert determine_gui_tier("auto") == "pyside6"
        assert determine_gui_tier("default") == "pyside6"
        assert determine_gui_tier("unknown_flag") == "pyside6"


def test_proc_meminfo_parser_robustness():
    """Validates Linux /proc/meminfo parsing with valid, irregular, and malformed files."""
    sample_meminfo = (
        "MemTotal:        8163584 kB\n"
        "MemFree:         1234567 kB\n"
        "MemAvailable:    4567890 kB\n"
    )

    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "linux"
    ), patch("os.path.isfile", return_value=True), patch(
        "builtins.open", mock_open(read_data=sample_meminfo)
    ):
        ram = get_total_ram_bytes()
        assert ram == 8163584 * 1024

    # Irregular spacing/tabs
    irregular_meminfo = "MemTotal:\t  4096000\t  kB\n"
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "linux"
    ), patch("os.path.isfile", return_value=True), patch(
        "builtins.open", mock_open(read_data=irregular_meminfo)
    ):
        ram = get_total_ram_bytes()
        assert ram == 4096000 * 1024

    # Malformed meminfo without MemTotal falls back to safe default
    corrupt_meminfo = "SomethingElse: 1234 kB\n"
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "linux"
    ), patch("os.path.isfile", return_value=True), patch(
        "builtins.open", mock_open(read_data=corrupt_meminfo)
    ), patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ):
        ram = get_total_ram_bytes()
        assert ram == 8 * 1024 * 1024 * 1024  # 64-bit safe default


def test_macos_sysctl_memsize_query():
    """Validates macOS sysctl hw.memsize query parsing and error fallback."""
    # Successful query: 16 GB (17179869184 bytes)
    mock_sub = MagicMock()
    mock_sub.stdout = "17179869184\n"
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "darwin"
    ), patch("subprocess.run", return_value=mock_sub):
        ram = get_total_ram_bytes()
        assert ram == 17179869184

    # Subprocess error fallback
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "darwin"
    ), patch(
        "subprocess.run", side_effect=subprocess.SubprocessError("Failed to run sysctl")
    ), patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ):
        ram = get_total_ram_bytes()
        assert ram == 8 * 1024 * 1024 * 1024


def test_windows_ctypes_ram_query():
    """Validates Windows ctypes GlobalMemoryStatusEx query and exception handling."""
    import ctypes

    def mock_status_ex(ref):
        ref._obj.ullTotalPhys = 16 * 1024 * 1024 * 1024
        return True

    mock_kernel32 = type("K32", (), {"GlobalMemoryStatusEx": staticmethod(mock_status_ex)})()
    mock_windll = type("WinDLL", (), {"kernel32": mock_kernel32})()

    # Success case
    with patch.dict(sys.modules, {"psutil": None}), patch("sys.platform", "win32"):
        with patch.object(ctypes, "windll", mock_windll, create=True):
            ram = get_total_ram_bytes()
            assert ram == 16 * 1024 * 1024 * 1024

    # Windows exception fallback to safe default
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "win32"
    ), patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ):
        ram = get_total_ram_bytes()
        assert ram == 8 * 1024 * 1024 * 1024



def test_all_ram_detectors_failure_fallback_32bit():
    """Validates fallback to 2 GB default on 32-bit systems when all counters fail."""
    with patch.dict(sys.modules, {"psutil": None}), patch(
        "sys.platform", "unknown_os"
    ), patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=False
    ):
        ram = get_total_ram_bytes()
        assert ram == 2 * 1024 * 1024 * 1024


def test_get_system_specs_structure():
    """Validates that get_system_specs returns complete metadata structure."""
    specs = get_system_specs()
    assert "platform" in specs
    assert "os_release" in specs
    assert "machine" in specs
    assert "is_64bit" in specs
    assert "ram_bytes" in specs
    assert "ram_gb" in specs
    assert "gui_tier" in specs
    assert "gui_name" in specs
    assert specs["gui_tier"] in ("pyside6", "tkinter")
    assert isinstance(specs["ram_gb"], float)
    assert specs["ram_bytes"] > 0


if __name__ == "__main__":
    print("Running test_system_capability.py...")
    test_is_64bit_architecture_detection()
    print("  [PASS] test_is_64bit_architecture_detection")
    test_determine_gui_tier_logic()
    print("  [PASS] test_determine_gui_tier_logic")
    test_ram_threshold_vram_reserve_boundary()
    print("  [PASS] test_ram_threshold_vram_reserve_boundary")
    test_determine_gui_tier_user_overrides()
    print("  [PASS] test_determine_gui_tier_user_overrides")
    test_proc_meminfo_parser_robustness()
    print("  [PASS] test_proc_meminfo_parser_robustness")
    test_macos_sysctl_memsize_query()
    print("  [PASS] test_macos_sysctl_memsize_query")
    test_windows_ctypes_ram_query()
    print("  [PASS] test_windows_ctypes_ram_query")
    test_all_ram_detectors_failure_fallback_32bit()
    print("  [PASS] test_all_ram_detectors_failure_fallback_32bit")
    test_get_system_specs_structure()
    print("  [PASS] test_get_system_specs_structure")
    print("All system capability tests passed successfully!")

