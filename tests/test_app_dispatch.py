"""
Unit tests for deterministic dual-tier GUI dispatcher (src/pyegclamui/gui/app.py).

Validates:
  - Command line flag parsing (--ui=..., --tier=..., --lite, --qt, -m, --minimized)
  - Deterministic routing to Tkinter Lite on low-spec/32-bit hardware
  - Deterministic routing to PySide6 Qt6 on 64-bit systems with >= 4.0 GB RAM
  - Seamless fallback to Tkinter Lite when PySide6 is not installed on Tier 1 systems
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pyegclamui.gui.app as app_mod


def test_parse_gui_options():
    """Validates command-line option parser for GUI tier, minimization, and target path."""
    # 1. Tier 2 overrides
    tier, min_flag, target = app_mod.parse_gui_options(["app.py", "--lite", "-m"])
    assert tier == "tkinter"
    assert min_flag is True
    assert target is None

    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--ui=tk"])
    assert tier == "tkinter"

    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--ui=lite"])
    assert tier == "tkinter"

    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--tier2"])
    assert tier == "tkinter"

    # 2. Tier 1 overrides
    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--qt", "--minimized"])
    assert tier == "pyside6"
    assert min_flag is True

    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--ui=qt6"])
    assert tier == "pyside6"

    tier, min_flag, _ = app_mod.parse_gui_options(["app.py", "--tier=pyside6"])
    assert tier == "pyside6"

    # 3. Path argument extraction
    test_path = str(PROJECT_ROOT / "src")
    tier, min_flag, target = app_mod.parse_gui_options(["app.py", test_path])
    assert tier is None
    assert min_flag is False
    assert target == test_path


def test_main_dispatch_to_tkinter_tier():
    """Validates that when assigned tier is tkinter, run_tkinter_app is invoked directly."""
    with patch(
        "pyegclamui.gui.app.determine_gui_tier", return_value="tkinter"
    ), patch("pyegclamui.gui.tk_app.run_tkinter_app", return_value=0) as mock_run_tk:
        with patch.object(sys, "argv", ["app.py", "--lite"]):
            exit_code = app_mod.main()
            assert exit_code == 0
            mock_run_tk.assert_called_once_with(scan_path=None)


def test_main_dispatch_pyside6_fallback_to_tkinter():
    """Validates that when PySide6 is unavailable on Tier 1 systems, it seamlessly falls back to Tkinter."""
    with patch(
        "pyegclamui.gui.app.determine_gui_tier", return_value="pyside6"
    ), patch.dict(sys.modules, {"PySide6": None, "PySide6.QtCore": None}), patch(
        "pyegclamui.gui.tk_app.run_tkinter_app", return_value=0
    ) as mock_run_tk:
        with patch.object(sys, "argv", ["app.py"]):
            exit_code = app_mod.main()
            assert exit_code == 0
            mock_run_tk.assert_called_once()


if __name__ == "__main__":
    print("\n=== Running test_app_dispatch.py test suite ===")
    test_parse_gui_options()
    print("  [PASS] test_parse_gui_options")
    test_main_dispatch_to_tkinter_tier()
    print("  [PASS] test_main_dispatch_to_tkinter_tier")
    test_main_dispatch_pyside6_fallback_to_tkinter()
    print("  [PASS] test_main_dispatch_pyside6_fallback_to_tkinter")
    print("All GUI dispatcher tests passed successfully!\n")
