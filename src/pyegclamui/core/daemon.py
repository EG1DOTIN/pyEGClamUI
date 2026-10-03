"""
ClamAV Daemon (clamd) socket client and communication manager for pyEGClamUI.
Provides Unix domain socket and TCP socket communication with clamd across Linux, macOS, and Windows.
"""

import io
import socket
import struct
import sys
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union

from pyegclamui.core.config import Config


class ClamDaemonClient:
    """
    Client for interacting with the ClamAV daemon (clamd) via Unix or TCP sockets.
    Implements standard ClamAV protocol commands: PING, VERSION, STATS, RELOAD,
    SCAN, CONTSCAN, MULTISCAN, and INSTREAM.
    """

    STANDARD_UNIX_SOCKETS: List[Path] = [
        Path("/var/run/clamav/clamd.ctl"),
        Path("/run/clamav/clamd.ctl"),
        Path("/var/run/clamd.scan/clamd.sock"),
        Path("/run/clamd.scan/clamd.sock"),
        Path("/tmp/clamd.socket"),
        Path("/opt/homebrew/var/run/clamav/clamd.sock"),
        Path("/opt/homebrew/var/run/clamav/clamd.ctl"),
        Path("/usr/local/var/run/clamav/clamd.sock"),
    ]

    def __init__(
        self,
        unix_socket: Optional[Union[str, Path]] = None,
        tcp_host: Optional[str] = None,
        tcp_port: Optional[int] = None,
        timeout: float = 2.0,
    ):
        self.config = Config.get_instance()
        self.unix_socket = Path(unix_socket) if unix_socket else None
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.timeout = timeout

    def _resolve_socket_target(self) -> Tuple[Optional[str], Optional[Tuple[str, int]]]:
        """
        Determines the socket target to connect to.
        Returns (unix_socket_path_str, None) or (None, (tcp_host, tcp_port)).
        """
        # 1. Custom or explicit Unix socket
        if self.unix_socket and self.unix_socket.exists():
            return str(self.unix_socket), None

        configured_unix = self.config.get("scan_settings", "clamd_unix_socket", default="")
        if configured_unix and Path(configured_unix).exists():
            return configured_unix, None

        # 2. Probe standard Unix sockets if AF_UNIX is available
        if hasattr(socket, "AF_UNIX"):
            for candidate in self.STANDARD_UNIX_SOCKETS:
                if candidate.exists():
                    return str(candidate), None

        # 3. Fallback to TCP Socket
        host = self.tcp_host or self.config.get(
            "scan_settings", "clamd_tcp_host", default="127.0.0.1"
        )
        port = self.tcp_port or int(
            self.config.get("scan_settings", "clamd_tcp_port", default=3310)
        )
        return None, (host, port)

    def _create_socket(self, timeout: Optional[float] = None) -> socket.socket:
        """Establishes and returns an open socket connection to clamd."""
        eff_timeout = timeout if timeout is not None else self.timeout
        unix_path, tcp_target = self._resolve_socket_target()

        if unix_path and hasattr(socket, "AF_UNIX"):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(eff_timeout)
            s.connect(unix_path)
            return s
        elif tcp_target:
            host, port = tcp_target
            s = socket.create_connection((host, port), timeout=eff_timeout)
            return s
        else:
            raise ConnectionRefusedError("No viable clamd Unix socket or TCP target found.")

    def check_connection(self, timeout: float = 0.5) -> Tuple[bool, str]:
        """
        Verifies whether clamd is reachable and responding to PING.
        Returns: (is_online, connection_description)
        """
        unix_path, tcp_target = self._resolve_socket_target()
        target_name = (
            f"Unix Socket ({unix_path})"
            if unix_path
            else f"TCP ({tcp_target[0]}:{tcp_target[1]})"
            if tcp_target
            else "Unknown"
        )

        try:
            with self._create_socket(timeout=timeout) as s:
                s.sendall(b"PING\n")
                resp = s.recv(32).strip()
                if b"PONG" in resp:
                    return True, target_name
        except (OSError, ConnectionError, socket.timeout):
            pass

        return False, "Offline"

    def ping(self) -> bool:
        """Sends PING to clamd; returns True if PONG is received."""
        try:
            with self._create_socket() as s:
                s.sendall(b"PING\n")
                resp = s.recv(32).strip()
                return b"PONG" in resp
        except (OSError, ConnectionError, socket.timeout):
            return False

    def version(self) -> str:
        """Queries clamd for the engine version and signature date."""
        try:
            with self._create_socket() as s:
                s.sendall(b"VERSION\n")
                resp = s.recv(256).decode("utf-8", errors="replace").strip()
                return resp
        except (OSError, ConnectionError, socket.timeout) as e:
            return f"Error querying clamd version: {e}"

    def stats(self) -> str:
        """Queries clamd for daemon statistics (queue, threads, memory)."""
        try:
            with self._create_socket() as s:
                s.sendall(b"STATS\n")
                chunks = []
                while True:
                    data = s.recv(1024)
                    if not data:
                        break
                    chunks.append(data.decode("utf-8", errors="replace"))
                return "".join(chunks).strip()
        except (OSError, ConnectionError, socket.timeout) as e:
            return f"Error querying clamd stats: {e}"

    def reload(self) -> bool:
        """Commands clamd to reload its signature database into memory."""
        try:
            with self._create_socket() as s:
                s.sendall(b"RELOAD\n")
                resp = s.recv(64).strip()
                return b"RELOADING" in resp
        except (OSError, ConnectionError, socket.timeout):
            return False

    def shutdown(self) -> bool:
        """Requests graceful shutdown of clamd daemon (if permitted)."""
        try:
            with self._create_socket() as s:
                s.sendall(b"SHUTDOWN\n")
                return True
        except (OSError, ConnectionError, socket.timeout):
            return False

    @staticmethod
    def parse_response_line(line: str) -> Dict[str, Any]:
        """
        Parses a single clamd response line.
        Formats:
          '/path/to/file: OK'
          '/path/to/file: Eicar-Test-Signature FOUND'
          '/path/to/file: Can't open file ERROR'
        """
        line = line.strip()
        if not line:
            return {"status": "EMPTY", "path": "", "threat": "", "error": ""}

        parts = line.rsplit(":", 1)
        if len(parts) < 2:
            return {"status": "RAW", "path": "", "raw": line}

        file_path = parts[0].strip()
        result_part = parts[1].strip()

        if result_part == "OK":
            return {"status": "OK", "path": file_path, "threat": "", "error": ""}
        elif result_part.endswith("FOUND"):
            threat = result_part[:-5].strip()
            return {"status": "FOUND", "path": file_path, "threat": threat, "error": ""}
        elif result_part.endswith("ERROR"):
            err_msg = result_part[:-5].strip()
            return {"status": "ERROR", "path": file_path, "threat": "", "error": err_msg}

        return {"status": "UNKNOWN", "path": file_path, "raw": result_part}

    def scan_path(self, target_path: Union[str, Path], contscan: bool = True) -> List[Dict[str, Any]]:
        """
        Instructs clamd to scan a file or directory path on the local filesystem.
        Uses CONTSCAN (scans whole directory without stopping on first infected file)
        or SCAN (stops on first infected file).
        """
        path_str = str(Path(target_path).resolve())
        cmd_verb = "CONTSCAN" if contscan else "SCAN"
        cmd = f"{cmd_verb} {path_str}\n"

        results = []
        try:
            with self._create_socket() as s:
                s.sendall(cmd.encode("utf-8"))
                buffer = ""
                while True:
                    chunk = s.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            results.append(self.parse_response_line(line))
                if buffer.strip():
                    results.append(self.parse_response_line(buffer))
        except (OSError, ConnectionError, socket.timeout) as e:
            results.append({"status": "ERROR", "path": path_str, "error": str(e)})

        return results

    def multiscan(self, target_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Uses MULTISCAN to scan directory trees concurrently with all available clamd threads.
        """
        path_str = str(Path(target_path).resolve())
        cmd = f"MULTISCAN {path_str}\n"

        results = []
        try:
            with self._create_socket() as s:
                s.sendall(cmd.encode("utf-8"))
                buffer = ""
                while True:
                    chunk = s.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            results.append(self.parse_response_line(line))
                if buffer.strip():
                    results.append(self.parse_response_line(buffer))
        except (OSError, ConnectionError, socket.timeout) as e:
            results.append({"status": "ERROR", "path": path_str, "error": str(e)})

        return results

    def scan_stream(
        self, data_source: Union[bytes, BinaryIO], chunk_size: int = 4096
    ) -> Dict[str, Any]:
        """
        Scans an in-memory byte buffer or open binary stream via ClamAV's INSTREAM protocol.
        Format: [4-byte big-endian chunk length][chunk bytes] ... [4-byte 0x00000000].
        This completely bypasses filesystem permissions, allowing user-level applications
        to scan restricted user files with a system clamd service!
        """
        if isinstance(data_source, bytes):
            stream = io.BytesIO(data_source)
        else:
            stream = data_source

        try:
            with self._create_socket() as s:
                s.sendall(b"zINSTREAM\0")

                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    chunk_len = len(chunk)
                    # 4 bytes unsigned int, big-endian network order
                    header = struct.pack(">I", chunk_len)
                    s.sendall(header + chunk)

                # Send 4 zero bytes to indicate end of stream
                s.sendall(struct.pack(">I", 0))

                # Read response
                resp = s.recv(512).decode("utf-8", errors="replace").strip()
                # Typical response: "stream: OK" or "stream: Eicar-Signature FOUND"
                return self.parse_response_line(resp)
        except (OSError, ConnectionError, socket.timeout) as e:
            return {"status": "ERROR", "path": "stream", "error": str(e)}
