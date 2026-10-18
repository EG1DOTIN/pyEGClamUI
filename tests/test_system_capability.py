"""
Unit tests for deterministic system capability inspection (src/pyegclamui/core/system_capability.py).
"""

import sys
from pathlib import Path
from unittest.mock import patch

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
    # Mock 64-bit AMD64
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**63 - 1
    ):
        assert is_64bit_architecture() is True

    # Mock 32-bit i686
    with patch("platform.machine", return_value="i686"):
        assert is_64bit_architecture() is False

    # Mock 32-bit pointer space
    with patch("platform.machine", return_value="x86_64"), patch.object(
        sys, "maxsize", 2**31 - 1
    ):
        assert is_64bit_architecture() is False

    # Mock ARMv7 32-bit
    with patch("platform.machine", return_value="armv7l"):
        assert is_64bit_architecture() is False


def test_determine_gui_tier_logic():
    """Validates deterministic tier selection based on specs and boundaries."""
    # 1. 64-bit with >= 4.0 GB RAM -> pyside6
    with patch(
        "pyegclamui.core.system_capability.is_64bit_architecture", return_value=True
    ), patch(
        "pyegclamui.core.system_capability.get_total_ram_bytes",
        return_value=6 * 1024 * 1024 * 1024,
    ):
        assert determine_gui_tier() == "pyside6"

    # 2. 64-bit with < 4.0 GB RAM (e.g. 2 GB VM) -> tkinter
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


def test_determine_gui_tier_user_overrides():
    """Validates that explicit user override flags take precedence."""
    # Overrides to Qt
    assert determine_gui_tier("pyside6") == "pyside6"
    assert determine_gui_tier("qt6") == "pyside6"
    assert determine_gui_tier("qt") == "pyside6"

    # Overrides to Tkinter
    assert determine_gui_tier("tkinter") == "tkinter"
    assert determine_gui_tier("tk") == "tkinter"
    assert determine_gui_tier("lite") == "tkinter"


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


if __name__ == "__main__":
    print("Running test_system_capability.py...")
    test_is_64bit_architecture_detection()
    print("  [PASS] test_is_64bit_architecture_detection")
    test_determine_gui_tier_logic()
    print("  [PASS] test_determine_gui_tier_logic")
    test_determine_gui_tier_user_overrides()
    print("  [PASS] test_determine_gui_tier_user_overrides")
    test_get_system_specs_structure()
    print("  [PASS] test_get_system_specs_structure")
    print("All system capability tests passed successfully!")
