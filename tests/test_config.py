"""
Unit tests for configuration manager and directory resolution.
"""

import tempfile
from pathlib import Path
from pyegclamui.core.config import AppPaths, Config


def test_app_paths():
    config_dir = AppPaths.get_config_dir()
    data_dir = AppPaths.get_data_dir()
    quarantine_dir = AppPaths.get_quarantine_dir()

    assert config_dir.exists()
    assert data_dir.exists()
    assert quarantine_dir.exists()


def test_config_defaults():
    config = Config.get_instance()
    assert config.get("preferences", "action_on_threat") in [1, 2, 3]
    assert config.get("scan_settings", "max_file_size_mb") > 0
    assert isinstance(config.get("scan_settings", "exclude_extensions"), list)


def test_config_set_and_get():
    config = Config.get_instance()
    original_size = config.get("scan_settings", "max_file_size_mb")

    config.set("scan_settings", "max_file_size_mb", 99)
    assert config.get("scan_settings", "max_file_size_mb") == 99

    # Revert
    config.set("scan_settings", "max_file_size_mb", original_size)
    assert config.get("scan_settings", "max_file_size_mb") == original_size
