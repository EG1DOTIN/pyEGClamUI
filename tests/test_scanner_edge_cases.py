"""
Edge case tests for ClamScanner line parsing and process safety.
"""

from pyegclamui.core.scanner import ClamScanner, ScanReport


def test_parse_line_clean_file_windows():
    scanner = ClamScanner()
    line = r"C:\Users\John Doe\Documents\My Report.docx: OK"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "ok"
    assert parsed["path"] == r"C:\Users\John Doe\Documents\My Report.docx"
    assert not parsed["path"].endswith(":")


def test_parse_line_clean_file_unix():
    scanner = ClamScanner()
    line = "/var/log/custom:service:name.log: OK"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "ok"
    assert parsed["path"] == "/var/log/custom:service:name.log"


def test_parse_line_threat_detection():
    scanner = ClamScanner()
    line = r"C:\Downloads\malware_sample.exe: Win.Test.EICAR_HDB-1 FOUND"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "threat"
    assert parsed["path"] == r"C:\Downloads\malware_sample.exe"
    assert parsed["threat"] == "Win.Test.EICAR_HDB-1"


def test_parse_line_threat_with_colons():
    scanner = ClamScanner()
    line = r"C:\Folder:2\archive:part1.bin: Exploit.Payload FOUND"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "threat"
    assert parsed["path"] == r"C:\Folder:2\archive:part1.bin"
    assert parsed["threat"] == "Exploit.Payload"


def test_parse_line_error_message():
    scanner = ClamScanner()
    line = r"C:\Windows\System32\locked.sys: Can't open file or directory ERROR"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "error"
    assert parsed["path"] == r"C:\Windows\System32\locked.sys"
    assert "Can't open" in parsed["error"]


def test_parse_line_warning_message():
    scanner = ClamScanner()
    line = r"C:\Archive\huge.zip: Oversized.Zip WARNING"
    parsed = scanner.parse_line(line)

    assert parsed is not None
    assert parsed["type"] == "warning"
    assert parsed["path"] == r"C:\Archive\huge.zip"
    assert parsed["warning"] == "Oversized.Zip"


def test_parse_line_summary_metrics():
    scanner = ClamScanner()
    assert scanner.parse_line("Scanned files: 250") == {"type": "summary_scanned_files", "count": 250}
    assert scanner.parse_line("Infected files: 5") == {"type": "summary_infected_files", "count": 5}
    assert scanner.parse_line("Total errors: 3") == {"type": "summary_errors", "count": 3}


def test_parse_line_empty_and_whitespace():
    scanner = ClamScanner()
    assert scanner.parse_line("") is None
    assert scanner.parse_line("    \n  ") is None


def test_scan_empty_targets():
    scanner = ClamScanner()
    report = scanner.scan(scan_type="Custom Scan", targets=[])
    assert not report.cancelled
    assert "No target paths" in report.summary_text
