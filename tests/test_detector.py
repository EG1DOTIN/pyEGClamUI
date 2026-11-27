"""
Unit tests for ClamEngineDetector.
"""

from pyegclamui.core.detector import ClamEngineDetector


def test_detector_inspection():
    detector = ClamEngineDetector()
    audit = detector.inspect()

    assert "clamscan_path" in audit
    assert "clamdscan_path" in audit
    assert "clamd_path" in audit
    assert "freshclam_path" in audit
    assert "daemon_online" in audit
    assert isinstance(audit["daemon_online"], bool)
    assert "version" in audit
    clamdscan = detector.get_clamdscan_path()
    assert clamdscan is None or isinstance(clamdscan, str)


def test_detector_unix_and_macos_paths():
    unix_paths = [p.as_posix() for p in ClamEngineDetector.get_standard_unix_paths()]
    assert any("/opt/homebrew/bin" in p for p in unix_paths)
    assert any("/opt/homebrew/sbin" in p for p in unix_paths)
    assert any("/usr/bin" in p for p in unix_paths)
    assert any("/usr/sbin" in p for p in unix_paths)


def test_detector_standard_unix_sockets():
    socket_paths = [p.as_posix() for p in ClamEngineDetector.STANDARD_UNIX_SOCKETS]
    assert any("clamd.ctl" in p for p in socket_paths)
    assert any("clamd.sock" in p for p in socket_paths)


def test_detector_caching():
    detector = ClamEngineDetector()
    first_inspect = detector.inspect()
    second_inspect = detector.inspect()
    assert first_inspect is second_inspect

    detector.invalidate_cache()
    assert detector._cached_inspect is None
    assert detector._cached_version is None


def test_detector_get_engine_version_with_signatures_no_unbound_db_date(tmp_path, monkeypatch):
    """Regression test: db_date must always be initialized even when signatures exist on Linux."""
    db_file = tmp_path / "main.cvd"
    db_file.write_bytes(b"X" * 2048)

    detector = ClamEngineDetector()
    monkeypatch.setattr(detector, "get_clamscan_path", lambda: "/usr/bin/clamscan")
    monkeypatch.setattr(detector, "get_standard_database_directories", lambda: [tmp_path])

    class FakeResult:
        stdout = "ClamAV 1.4.1/27584/Mon Sep 21 08:30:00 2026\n"
        stderr = ""

    monkeypatch.setattr("pyegclamui.core.detector.run_hidden_process", lambda *a, **kw: FakeResult())

    info = detector.get_engine_version(force=True)
    assert info["installed"] is True
    assert info["clamav_version"] == "ClamAV 1.4.1"
    assert info["db_version"] == "27584"
    assert info["db_date"] == "Mon Sep 21 08:30:00 2026"
    assert info["has_signatures"] is True


def test_detector_get_engine_version_two_parts_no_unbound_db_date(tmp_path, monkeypatch):
    """Regression test: clamscan --version output without date still sets db_date='Unknown'."""
    db_file = tmp_path / "daily.cld"
    db_file.write_bytes(b"X" * 2048)

    detector = ClamEngineDetector()
    monkeypatch.setattr(detector, "get_clamscan_path", lambda: "/usr/bin/clamscan")
    monkeypatch.setattr(detector, "get_standard_database_directories", lambda: [tmp_path])

    class FakeResult:
        stdout = "ClamAV 1.4.1/27584\n"
        stderr = ""

    monkeypatch.setattr("pyegclamui.core.detector.run_hidden_process", lambda *a, **kw: FakeResult())

    info = detector.get_engine_version(force=True)
    assert info["installed"] is True
    assert info["db_version"] == "27584"
    assert info["db_date"] == "Unknown"


def test_detector_handles_winerror_216_gracefully(monkeypatch):
    """Verifies WinError 216 marks binary incompatible rather than reporting installed=True."""
    detector = ClamEngineDetector()
    monkeypatch.setattr(detector, "get_clamscan_path", lambda: "C:/ClamAV/clamscan.exe")
    monkeypatch.setattr(detector, "get_clamdscan_path", lambda: None)
    monkeypatch.setattr(detector, "check_daemon_socket", lambda: (False, "Offline"))

    def raise_216(*args, **kwargs):
        err = OSError("Incompatible executable")
        err.winerror = 216
        raise err

    monkeypatch.setattr("pyegclamui.core.detector.run_hidden_process", raise_216)

    audit = detector.inspect(force=True)
    assert audit["version"]["installed"] is False
    assert audit["version"]["clamav_version"] == "Incompatible Binary"
    assert audit["ready"] is False
