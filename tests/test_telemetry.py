"""
Unit tests for opt-in transparent telemetry, RAM metrics, issue reporter, and user profile manager.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from pyegclamui.core.config import Config
from pyegclamui.core.telemetry import (
    TelemetryManager,
    generate_guest_id,
    get_local_ip,
    sanitize_log_text,
)


def test_generate_guest_id():
    guest_id = generate_guest_id()
    assert guest_id.startswith("Guest")
    assert len(guest_id) == 13  # "Guest" (5) + 8 digits = 13 chars
    assert guest_id[5:].isdigit()


def test_get_local_ip():
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_telemetry_payload_respects_consent():
    config = Config.get_instance()
    mgr = TelemetryManager()

    # Configure specific consent flags
    config.set("user_profile", "user_id", "TestUser123")
    config.set("telemetry", "share_os_info", True)
    config.set("telemetry", "share_clamav_version", True)
    config.set("telemetry", "share_scan_stats", True)

    payload = mgr.build_payload()
    assert payload["client_id"] == "TestUser123"
    assert "os_platform" in payload
    assert "clamav_version" in payload
    assert "total_ram_gb" in payload
    assert "available_ram_gb" in payload
    assert "hostname" not in payload
    assert "ip_address" not in payload
    assert "scan_stats" in payload


def test_telemetry_preview_is_valid_json():
    mgr = TelemetryManager()
    preview = mgr.get_preview_payload()
    data = json.loads(preview)
    assert "client_id" in data
    assert "app_name" in data
    assert data["app_name"] == "pyEGClamUI"


def test_send_telemetry_blocked_when_disabled():
    config = Config.get_instance()
    config.set("telemetry", "enabled", False)

    mgr = TelemetryManager()
    success, msg = mgr.send_telemetry()
    assert success is False
    assert "disabled" in msg.lower()


def test_firestore_field_conversion():
    mgr = TelemetryManager()
    sample = {
        "client_id": "Guest12345678",
        "is_active": True,
        "count": 42,
        "ratio": 3.14,
        "details": {"key": "val"},
    }
    doc = mgr._convert_to_firestore_fields(sample)
    fields = doc["fields"]
    assert fields["client_id"]["stringValue"] == "Guest12345678"
    assert fields["is_active"]["booleanValue"] is True
    assert fields["count"]["integerValue"] == "42"
    assert fields["ratio"]["doubleValue"] == 3.14
    assert "stringValue" in fields["details"]


def test_sanitize_log_text():
    home = str(Path.home())
    sample_log = f"Error in {home}\\Downloads\\malware.exe at C:\\Users\\Administrator"
    sanitized = sanitize_log_text(sample_log)
    assert home not in sanitized
    assert "~" in sanitized


def test_send_install_event_offline():
    config = Config.get_instance()
    mgr = TelemetryManager()

    success, msg = mgr.send_install_event("offline")
    assert success is True
    assert "offline" in msg.lower()
    assert config.get("preferences", "first_run_completed") is True
    assert config.get("telemetry", "enabled") is False


def test_issue_report_requires_description():
    mgr = TelemetryManager()
    success, msg = mgr.send_issue_report("   ")
    assert success is False
    assert "description" in msg.lower()
