"""
Unit tests for deterministic dual-tier GUI dispatcher (src/pyegclamui/gui/app.py).

Comprehensive test coverage for CLI argument parsing, dual-tier routing,
fallback mechanics, exception hooks, and corner cases.
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


def test_parse_gui_options_corner_cases():
    """Validates corner cases: case sensitivity, mixed options, and non-existent paths."""
    # Case insensitive flag parsing
    tier, _, _ = app_mod.parse_gui_options(["app.py", "--UI=TKINTER"])
    assert tier == "tkinter"

    tier, _, _ = app_mod.parse_gui_options(["app.py", "--TIER=QT"])
    assert tier == "pyside6"

    # Non-existent path argument is not treated as target_path
    non_existent = "/non/existent/path/for/pyegclamui/test"
    tier, min_flag, target = app_mod.parse_gui_options(["app.py", non_existent])
    assert target is None

    # Mixed arguments in arbitrary order
    real_path = str(PROJECT_ROOT / "pyproject.toml")
    tier, min_flag, target = app_mod.parse_gui_options(
        ["app.py", "-m", real_path, "--ui=tk"]
    )
    assert tier == "tkinter"
    assert min_flag is True
    assert target == real_path


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


def test_main_dispatch_both_missing_returns_one():
    """Validates that when both PySide6 and Tkinter cannot start, it cleanly returns 1 with diagnostic notice."""
    with patch(
        "pyegclamui.gui.app.determine_gui_tier", return_value="pyside6"
    ), patch.dict(sys.modules, {"PySide6": None, "PySide6.QtCore": None}), patch(
        "pyegclamui.gui.tk_app.run_tkinter_app", return_value=1
    ):
        with patch.object(sys, "argv", ["app.py"]):
            exit_code = app_mod.main()
            assert exit_code == 1


def test_install_crash_handler():
    """Validates that install_crash_handler registers global sys.excepthook."""
    orig_hook = sys.excepthook
    try:
        mock_qapp = MagicMock()
        app_mod.install_crash_handler(mock_qapp)
        assert sys.excepthook != orig_hook

        # KeyboardInterrupt passes to original hook without error
        try:
            raise KeyboardInterrupt("Interrupt test")
        except KeyboardInterrupt:
            # Should not raise exception
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = orig_hook


if __name__ == "__main__":
    print("\n=== Running test_app_dispatch.py test suite ===")
    test_parse_gui_options()
    print("  [PASS] test_parse_gui_options")
    test_parse_gui_options_corner_cases()
    print("  [PASS] test_parse_gui_options_corner_cases")
    test_main_dispatch_to_tkinter_tier()
    print("  [PASS] test_main_dispatch_to_tkinter_tier")
    test_main_dispatch_pyside6_fallback_to_tkinter()
    print("  [PASS] test_main_dispatch_pyside6_fallback_to_tkinter")
    test_main_dispatch_both_missing_returns_one()
    print("  [PASS] test_main_dispatch_both_missing_returns_one")
    test_install_crash_handler()
    print("  [PASS] test_install_crash_handler")
    print("All GUI dispatcher tests passed successfully!\n")
