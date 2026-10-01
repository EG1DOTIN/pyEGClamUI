"""
Edge case tests for ClamUpdater database freshness and execution safety.
"""

from pyegclamui.core.updater import ClamUpdater


def test_updater_missing_freshclam():
    updater = ClamUpdater()
    # Force detector to return None for freshclam
    updater.detector.find_executable = lambda *args, **kwargs: None

    success, msg = updater.run_update()
    assert not success
    assert "freshclam executable not found" in msg


def test_updater_is_database_recent_not_installed():
    updater = ClamUpdater()
    updater.detector.get_engine_version = lambda: {
        "installed": False,
        "clamav_version": "Not Found",
        "db_date": "Unknown"
    }
    is_recent, msg = updater.is_database_recent()
    assert not is_recent
    assert "not installed" in msg


def test_updater_is_database_recent_outdated():
    updater = ClamUpdater()
    updater.detector.get_engine_version = lambda: {
        "installed": True,
        "clamav_version": "ClamAV 1.4.0",
        "db_version": "27000",
        "db_date": "Jan 01 2020",
    }
    is_recent, msg = updater.is_database_recent(max_days=7)
    assert not is_recent
    assert "Outdated" in msg
