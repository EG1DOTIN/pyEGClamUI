"""
Edge case tests for Config manager resilience and deep merging.
"""

import json
import tempfile
from pathlib import Path
from pyegclamui.core.config import Config


def test_config_deep_merge_partial_data():
    default = {
        "preferences": {"theme": "dark", "auto_updates": True, "notifications": True},
        "version": "1.0.0"
    }
    override = {
        "preferences": {"theme": "light"}  # missing auto_updates & notifications
    }
    merged = Config._deep_merge(default, override)

    assert merged["preferences"]["theme"] == "light"
    assert merged["preferences"]["auto_updates"] is True
    assert merged["preferences"]["notifications"] is True
    assert merged["version"] == "1.0.0"


def test_config_get_missing_nested_key():
    config = Config.get_instance()
    # Query non-existent deep keys
    val = config.get("nonexistent_section", "nonexistent_key", default="fallback_val")
    assert val == "fallback_val"


def test_config_set_validation():
    config = Config.get_instance()
    try:
        config.set("only_one_argument")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
