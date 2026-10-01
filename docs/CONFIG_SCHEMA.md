# Configuration & Data Schemas

This document defines the complete persistent storage specifications, JSON schemas, default configurations, and metadata formats utilized by **pyEGClamUI**.

---

## 1. User Configuration File (`config.json`)

* **Source File**: [`../src/pyegclamui/core/config.py`](../src/pyegclamui/core/config.py) (`Config`, `AppPaths`)

The application stores all user settings, scan limits, engine overrides, and preferences in a human-readable JSON file.

### 1.1 Storage Locations

* **Windows**: `%APPDATA%\pyEGClamUI\config.json`
* **Linux**: `~/.config/pyegclamui/config.json`
* **macOS**: `~/Library/Application Support/pyEGClamUI/config.json`

### 1.2 Default Configuration JSON

```json
{
  "version": "3.0.0",
  "preferences": {
    "theme": "dark",
    "real_time_protection": false,
    "auto_updates": true,
    "notifications": true,
    "close_to_tray": true,
    "start_with_system": false,
    "action_on_threat": 3
  },
  "scan_settings": {
    "max_file_size_mb": 50,
    "extract_archives": true,
    "max_extract_size_mb": 100,
    "max_extract_files": 1000,
    "max_recursion": 15,
    "monitor_dirs": [],
    "exclude_extensions": [
      "jpg", "jpeg", "png", "gif", "bmp", "mp3", "mp4", "mkv", "avi"
    ],
    "include_only_extensions": [],
    "custom_clamscan_path": "",
    "custom_clamd_path": "",
    "custom_freshclam_path": "",
    "clamd_unix_socket": "/var/run/clamav/clamd.ctl",
    "clamd_tcp_host": "127.0.0.1",
    "clamd_tcp_port": 3310
  },
  "user_profile": {
    "user_id": "Guest48291042",
    "display_name": "",
    "email": "",
    "is_anonymous": true
  },
  "telemetry": {
    "enabled": false,
    "firebase_project_id": "eg1-pyegclamui",
    "share_os_info": true,
    "share_clamav_version": true,
    "share_scan_stats": true
  }
}
```

### 1.3 Configuration Field Specification

| Section | Key | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `preferences` | `theme` | `string` | `"dark"` | Active UI theme (`"dark"` or `"light"`) |
| `preferences` | `real_time_protection` | `boolean` | `false` | Enables background watchdog monitoring on Desktop and Downloads |
| `preferences` | `auto_updates` | `boolean` | `true` | Enables automatic background virus database freshness checks |
| `preferences` | `notifications` | `boolean` | `true` | Enables native desktop balloon notifications on threat detection |
| `preferences` | `close_to_tray` | `boolean` | `true` | When `true`, closing window minimizes to system tray instead of exiting |
| `preferences` | `start_with_system` | `boolean` | `false` | Launches pyEGClamUI minimized to system tray on user login |
| `preferences` | `action_on_threat` | `integer` | `3` | Remediation mode: `1` = Report Only, `2` = Move to Trash, `3` = Quarantine |
| `scan_settings` | `monitor_dirs` | `array` | `[]` | Monitored directories (strictly capped at 2, defaults to Desktop & Downloads) |
| `scan_settings` | `max_file_size_mb` | `integer` | `50` | Maximum file size in MB to inspect |
| `scan_settings` | `extract_archives` | `boolean` | `true` | Inspects contents of compressed archives (`.zip`, `.rar`, `.tar`, `.7z`) |
| `scan_settings` | `max_extract_size_mb` | `integer` | `100` | Maximum uncompressed archive extraction size limit |
| `scan_settings` | `max_extract_files` | `integer` | `1000` | Maximum number of files to extract from archives |
| `scan_settings` | `max_recursion` | `integer` | `15` | Maximum nested directory or archive recursion depth |
| `scan_settings` | `exclude_extensions` | `array` | `["jpg", ...]` | File extensions to skip during scans |
| `scan_settings` | `include_only_extensions` | `array` | `[]` | When non-empty, only scan files matching these extensions |
| `scan_settings` | `custom_clamscan_path` | `string` | `""` | Manual absolute path override for `clamscan` executable |
| `scan_settings` | `custom_clamd_path` | `string` | `""` | Manual absolute path override for `clamd` executable |
| `scan_settings` | `custom_freshclam_path` | `string` | `""` | Manual absolute path override for `freshclam` executable |
| `scan_settings` | `clamd_unix_socket` | `string` | `"/var/run/clamav/clamd.ctl"` | clamd Unix domain socket path |
| `scan_settings` | `clamd_tcp_host` | `string` | `"127.0.0.1"` | TCP hostname for clamd daemon |
| `scan_settings` | `clamd_tcp_port` | `integer` | `3310` | TCP port number for clamd daemon |
| `user_profile` | `user_id` | `string` | `"Guest..."` | Unique identifier (Name, Email, or auto-generated `GuestXXXXXXXX`) |
| `user_profile` | `display_name` | `string` | `""` | Optional user display name |
| `user_profile` | `email` | `string` | `""` | Optional contact email address |
| `user_profile` | `is_anonymous` | `boolean` | `true` | Flags whether user identity is anonymous |
| `telemetry` | `enabled` | `boolean` | `false` | Master opt-in switch for diagnostics telemetry (disabled by default) |
| `telemetry` | `firebase_project_id` | `string` | `"eg1-pyegclamui"` | Firebase project ID for REST document storage |
| `telemetry` | `share_os_info` | `boolean` | `true` | Consented sharing of OS platform & version |
| `telemetry` | `share_clamav_version` | `boolean` | `true` | Consented sharing of ClamAV engine & signature version |
| `telemetry` | `share_scan_stats` | `boolean` | `true` | Consented sharing of protection metrics |

---

## 2. Quarantine Vault Manifest (`metadata.json`)

* **Source File**: [`../src/pyegclamui/core/quarantine.py`](../src/pyegclamui/core/quarantine.py) (`QuarantineManager`)

The quarantine vault catalogs isolated items in an internal JSON manifest stored alongside quarantined files.

### 2.1 Manifest JSON Schema Reference

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "QuarantineManifest",
  "type": "object",
  "patternProperties": {
    "^[0-9a-fA-F-]{36}$": {
      "type": "object",
      "required": [
        "id",
        "original_path",
        "filename",
        "threat_name",
        "quarantine_time",
        "file_size",
        "sha256"
      ],
      "properties": {
        "id": {
          "type": "string",
          "description": "Unique UUID v4 identifying the quarantined item"
        },
        "original_path": {
          "type": "string",
          "description": "Original absolute filesystem path before isolation"
        },
        "filename": {
          "type": "string",
          "description": "Original basename of the quarantined file"
        },
        "threat_name": {
          "type": "string",
          "description": "ClamAV virus/malware classification string"
        },
        "quarantine_time": {
          "type": "string",
          "description": "ISO 8601 UTC timestamp of isolation"
        },
        "file_size": {
          "type": "integer",
          "description": "File size in bytes"
        },
        "sha256": {
          "type": "string",
          "description": "Hexadecimal SHA-256 cryptographic digest of the file"
        }
      }
    }
  }
}
```

### 2.2 Sample `metadata.json` Entry

```json
{
  "a1b2c3d4-e5f6-7890-abcd-ef1234567890": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "original_path": "C:\\Users\\User\\Downloads\\suspicious_installer.exe",
    "filename": "suspicious_installer.exe",
    "threat_name": "Win.Test.EICAR_HDB-1",
    "quarantine_time": "2026-09-21T16:45:00.000Z",
    "file_size": 68,
    "sha256": "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
  }
}
```

---

## 3. Dual-Track Timestamped Logging Architecture

* **Source File**: [`../src/pyegclamui/core/logger.py`](../src/pyegclamui/core/logger.py) (`TimestampedFileHandler`, `setup_logging`)

All logging operations are partitioned into two dedicated streams, strictly size-capped at 2 MB with automatic timestamped rotation.

### 3.1 Directory Locations
* **Windows**: `%LOCALAPPDATA%\pyEGClamUI\logs\`
* **Linux**: `~/.local/state/pyegclamui/logs/`
* **macOS**: `~/Library/Logs/pyEGClamUI/`

### 3.2 Log File Specifications

| Log Stream | Filename Pattern | Maximum Size | Contents |
| :--- | :--- | :--- | :--- |
| **Errors Log** | `YYYY-MM-DD-HH-MM-errors.log` | 2 MB | Warnings, engine detection failures, subprocess errors, and uncaught crash exceptions (`sys.excepthook`) |
| **Audit Report Log** | `YYYY-MM-DD-HH-MM-report.log` | 2 MB | Operational audit records: scans executed with duration/metrics, quarantine isolation/restore actions, and settings changes |

---

## 4. Opt-In Firestore Telemetry REST Payload Schema

* **Source File**: [`../src/pyegclamui/core/telemetry.py`](../src/pyegclamui/core/telemetry.py) (`TelemetryManager`)

Telemetry is **100% Opt-In** (disabled by default) and requires explicit user consent checkboxes before any diagnostic data is transmitted to the Firebase Firestore REST endpoint (`https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/telemetry`).

### 4.1 Consented JSON Document Structure

```json
{
  "client_id": "Guest48291042",
  "app_name": "pyEGClamUI",
  "app_version": "3.0.0",
  "timestamp": "2026-09-22T12:00:00.000000+00:00",
  "display_name": "John Doe",
  "email": "john@example.com",
  "os_platform": "win32",
  "os_version": "win32 (Python 3.12.3)",
  "clamav_version": "ClamAV 1.5.4",
  "signature_db_version": "28130",
  "signature_db_date": "Mon Sep 21 04:30:00 2026",
  "scan_stats": {
    "action_on_threat": 3,
    "real_time_enabled": true
  }
}
```
*(Fields `display_name` and `email` are only included if explicitly entered in the User Profile by the user. Hostname and IP address are never collected)*.
