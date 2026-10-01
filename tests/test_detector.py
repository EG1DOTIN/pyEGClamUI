"""
Unit tests for ClamEngineDetector.
"""

from pyegclamui.core.detector import ClamEngineDetector


def test_detector_inspection():
    detector = ClamEngineDetector()
    audit = detector.inspect()

    assert "clamscan_path" in audit
    assert "clamd_path" in audit
    assert "freshclam_path" in audit
    assert "daemon_online" in audit
    assert isinstance(audit["daemon_online"], bool)
    assert "version" in audit


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
