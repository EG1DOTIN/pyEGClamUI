"""
Unit tests for ClamDaemonClient socket communication, protocols, and response parsing.
"""

import io
import socket
import struct
from unittest.mock import MagicMock, patch

from pyegclamui.core.daemon import ClamDaemonClient


def test_daemon_parse_response_line_ok():
    line = "/home/user/document.pdf: OK"
    parsed = ClamDaemonClient.parse_response_line(line)
    assert parsed["status"] == "OK"
    assert parsed["path"] == "/home/user/document.pdf"
    assert parsed["threat"] == ""
    assert parsed["error"] == ""


def test_daemon_parse_response_line_found():
    line = "/tmp/download/payload.bin: Win.Trojan.Generic-99 FOUND"
    parsed = ClamDaemonClient.parse_response_line(line)
    assert parsed["status"] == "FOUND"
    assert parsed["path"] == "/tmp/download/payload.bin"
    assert parsed["threat"] == "Win.Trojan.Generic-99"


def test_daemon_parse_response_line_error():
    line = "/root/secret.key: Permission denied. ERROR"
    parsed = ClamDaemonClient.parse_response_line(line)
    assert parsed["status"] == "ERROR"
    assert parsed["path"] == "/root/secret.key"
    assert "Permission denied" in parsed["error"]


def test_daemon_parse_response_line_empty():
    parsed = ClamDaemonClient.parse_response_line("   \n")
    assert parsed["status"] == "EMPTY"


def test_daemon_standard_sockets_defined():
    client = ClamDaemonClient()
    assert len(client.STANDARD_UNIX_SOCKETS) >= 5
    socket_strs = [str(p) for p in client.STANDARD_UNIX_SOCKETS]
    assert any("clamd.ctl" in s for s in socket_strs)
    assert any("homebrew" in s for s in socket_strs)


def make_mock_socket() -> MagicMock:
    s = MagicMock()
    s.__enter__.return_value = s
    return s


def test_daemon_ping_protocol():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.return_value = b"PONG\n"

    with patch.object(client, "_create_socket", return_value=mock_socket):
        is_pong = client.ping()
        assert is_pong is True
        mock_socket.sendall.assert_called_once_with(b"PING\n")


def test_daemon_version_protocol():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.return_value = b"ClamAV 1.4.1/28000/Mon Sep 21 2026\n"

    with patch.object(client, "_create_socket", return_value=mock_socket):
        ver = client.version()
        assert "ClamAV 1.4.1" in ver
        mock_socket.sendall.assert_called_once_with(b"VERSION\n")


def test_daemon_stats_protocol():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.side_effect = [b"POOLS: 1\nSTATE: VALID PRIMARY\nTHREADS: live 2  idle 0\n", b""]

    with patch.object(client, "_create_socket", return_value=mock_socket):
        stats = client.stats()
        assert "POOLS: 1" in stats
        assert "THREADS: live 2" in stats
        mock_socket.sendall.assert_called_once_with(b"STATS\n")


def test_daemon_reload_protocol():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.return_value = b"RELOADING\n"

    with patch.object(client, "_create_socket", return_value=mock_socket):
        reloaded = client.reload()
        assert reloaded is True
        mock_socket.sendall.assert_called_once_with(b"RELOAD\n")


def test_daemon_scan_path_protocol():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.side_effect = [
        b"/tmp/file1.txt: OK\n/tmp/file2.exe: Eicar-Test-Signature FOUND\n",
        b""
    ]

    with patch.object(client, "_create_socket", return_value=mock_socket):
        results = client.scan_path("/tmp", contscan=True)
        assert len(results) == 2
        assert results[0]["status"] == "OK"
        assert results[1]["status"] == "FOUND"
        assert results[1]["threat"] == "Eicar-Test-Signature"


def test_daemon_scan_stream_instream_framing():
    client = ClamDaemonClient()
    mock_socket = make_mock_socket()
    mock_socket.recv.return_value = b"stream: OK\n"

    data_payload = b"Hello, ClamAV!"
    with patch.object(client, "_create_socket", return_value=mock_socket):
        res = client.scan_stream(data_payload)
        assert res["status"] == "OK"

        # Verify zINSTREAM header and 4-byte chunk framing
        calls = mock_socket.sendall.call_args_list
        assert calls[0][0][0] == b"zINSTREAM\0"

        # Second call should have 4-byte length prefix + data
        expected_len = struct.pack(">I", len(data_payload))
        assert calls[1][0][0] == expected_len + data_payload

        # Third call must be the 4-byte 0x00000000 stream terminator
        assert calls[2][0][0] == struct.pack(">I", 0)


def test_daemon_offline_handling():
    client = ClamDaemonClient(tcp_host="127.0.0.1", tcp_port=65432, timeout=0.1)
    is_online, desc = client.check_connection()
    assert is_online is False
    assert desc == "Offline"
    assert client.ping() is False
