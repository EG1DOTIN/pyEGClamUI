"""
Unit tests for ClamScanner drive enumeration and target resolution.
"""

from pathlib import Path
from pyegclamui.core.scanner import ClamScanner


def test_system_drives_detection():
    scanner = ClamScanner()
    drives = scanner.get_system_drives()
    assert len(drives) > 0
    for drive in drives:
        assert isinstance(drive, str)
        assert len(drive) > 0


def test_quick_scan_paths():
    scanner = ClamScanner()
    paths = scanner.get_quick_scan_paths()
    assert len(paths) > 0
    for p in paths:
        assert Path(p).is_dir()


def test_build_clamdscan_args():
    scanner = ClamScanner()
    clamdscan = scanner.detector.get_clamdscan_path()
    if clamdscan:
        args = scanner.build_clamdscan_args(["test_target"])
        assert args[0] == clamdscan
        assert "--stdout" in args
        assert "--multiscan" in args
        assert "test_target" in args
