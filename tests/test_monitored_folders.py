"""
Unit tests for the strict 2-folder monitored watch guard.
"""

import tempfile
from pathlib import Path
from pyegclamui.core.config import Config
from pyegclamui.core.monitor import RealTimeGuard


def test_watch_directories_capped_at_two():
    with tempfile.TemporaryDirectory() as d1, \
         tempfile.TemporaryDirectory() as d2, \
         tempfile.TemporaryDirectory() as d3:

        p1, p2, p3 = Path(d1), Path(d2), Path(d3)
        # Passing 3 custom directories should strictly cap to 2
        guard = RealTimeGuard(watch_dirs=[p1, p2, p3])
        watch_dirs = guard.get_watch_directories()

        assert len(watch_dirs) == 2
        assert p1 in watch_dirs
        assert p2 in watch_dirs
        assert p3 not in watch_dirs


def test_update_watch_directories():
    config = Config.get_instance()
    original_dirs = config.get("scan_settings", "monitor_dirs", default=[])

    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        guard = RealTimeGuard()
        success = guard.update_watch_directories(slot1=d1, slot2=d2)
        assert success is True

        configured = config.get("scan_settings", "monitor_dirs")
        assert len(configured) == 2
        assert str(Path(d1).resolve()) in configured
        assert str(Path(d2).resolve()) in configured

    # Revert config
    config.set("scan_settings", "monitor_dirs", original_dirs)


def test_default_watch_directories_fallback():
    guard = RealTimeGuard()
    # When no custom directories are provided and monitor_dirs is empty
    config = Config.get_instance()
    original_dirs = config.get("scan_settings", "monitor_dirs", default=[])
    config.set("scan_settings", "monitor_dirs", [])

    try:
        dirs = guard.get_watch_directories()
        assert len(dirs) <= 2
        home = Path.home()
        expected = [home / "Desktop", home / "Downloads"]
        for d in dirs:
            assert d in expected
    finally:
        config.set("scan_settings", "monitor_dirs", original_dirs)
