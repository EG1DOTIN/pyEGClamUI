"""
Dual-track timestamped logging subsystem for pyEGClamUI.
Provides specialized loggers for errors and operational audit reports with 2MB timestamped rotation.
"""

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyegclamui.core.config import AppPaths

MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB size cap


class TimestampedFileHandler(logging.Handler):
    """
    Thread-safe logging handler that writes to timestamped log files
    (YYYY-MM-DD-HH-MM-<log_type>.log) and rotates to a new timestamped file
    when the 2MB size cap is reached.
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_type: str = "errors",
        max_bytes: int = MAX_LOG_BYTES,
        logs_dir: Optional[Path] = None,
    ):
        super().__init__()
        target_dir = log_dir if log_dir is not None else logs_dir
        if target_dir is None:
            target_dir = AppPaths.get_logs_dir()
        self.log_dir = Path(target_dir)
        self.log_type = log_type
        self.max_bytes = max_bytes
        self.lock = threading.RLock()
        self.stream = None
        self.current_path: Optional[Path] = None
        self._ensure_file()

    def _get_new_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        filename = f"{timestamp}-{self.log_type}.log"
        path = self.log_dir / filename
        # Ensure unique name if created in the same minute
        counter = 1
        while path.exists() and path.stat().st_size >= self.max_bytes:
            filename = f"{timestamp}-{self.log_type}-{counter}.log"
            path = self.log_dir / filename
            counter += 1
        return path

    def _ensure_file(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Find latest log file for this type
        existing = sorted(
            [p for p in self.log_dir.glob(f"*-{self.log_type}*.log") if p.is_file()],
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )

        if existing and existing[0].stat().st_size < self.max_bytes:
            self.current_path = existing[0]
        else:
            self.current_path = self._get_new_path()

        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
        self.stream = open(self.current_path, "a", encoding="utf-8")

    def emit(self, record: logging.LogRecord):
        with self.lock:
            try:
                if self.current_path and self.current_path.exists():
                    if self.current_path.stat().st_size >= self.max_bytes:
                        self._ensure_file()
                msg = self.format(record) + "\n"
                if self.stream:
                    self.stream.write(msg)
                    self.stream.flush()
            except Exception:
                self.handleError(record)

    def close(self):
        with self.lock:
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            super().close()


# Module-level references
_errors_logger: Optional[logging.Logger] = None
_reports_logger: Optional[logging.Logger] = None
_logger_initialized = False


def setup_logging(
    log_dir: Optional[Path] = None,
    custom_logs_dir: Optional[Path] = None,
    force: bool = False,
) -> None:
    """Initializes dual-track error and report logging."""
    global _errors_logger, _reports_logger, _logger_initialized
    if _logger_initialized and not force:
        return
    if force:
        shutdown_logging()

    target_dir = log_dir if log_dir is not None else custom_logs_dir
    if target_dir is None:
        target_dir = AppPaths.get_logs_dir()
    log_dir = Path(target_dir)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Errors Logger (Warnings, Errors, Criticals, Crashes)
    _errors_logger = logging.getLogger("pyegclamui")
    _errors_logger.setLevel(logging.WARNING)
    _errors_logger.propagate = False

    errors_handler = TimestampedFileHandler(log_dir, "errors", max_bytes=MAX_LOG_BYTES)
    errors_handler.setFormatter(formatter)
    errors_handler.setLevel(logging.WARNING)
    _errors_logger.addHandler(errors_handler)

    # Console stream handler for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    _errors_logger.addHandler(console_handler)

    # 2. Reports Logger (Operational & Audit Reports)
    _reports_logger = logging.getLogger("pyegclamui.reports")
    _reports_logger.setLevel(logging.INFO)
    _reports_logger.propagate = False

    report_formatter = logging.Formatter(
        fmt="%(asctime)s [REPORT] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    reports_handler = TimestampedFileHandler(log_dir, "report", max_bytes=MAX_LOG_BYTES)
    reports_handler.setFormatter(report_formatter)
    reports_handler.setLevel(logging.INFO)
    _reports_logger.addHandler(reports_handler)

    _logger_initialized = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Returns the primary application logger."""
    if not _logger_initialized:
        setup_logging()
    if name:
        return logging.getLogger(f"pyegclamui.{name}")
    return logging.getLogger("pyegclamui")


def log_scan_report(
    scan_type: str,
    duration_sec: float,
    scanned_count: int,
    threats_count: int,
    targets: List[str],
    details: Optional[str] = None,
) -> None:
    """Writes a structured scan execution audit entry into report.log."""
    if not _logger_initialized:
        setup_logging()
    target_str = ", ".join(targets[:3])
    if len(targets) > 3:
        target_str += f" (+{len(targets) - 3} more)"

    msg = (
        f"Scan Completed | Type: '{scan_type}' | Scanned: {scanned_count} | "
        f"Threats: {threats_count} | Duration: {duration_sec:.2f}s | Target(s): [{target_str}]"
    )
    if details:
        msg += f" | Details: {details}"
    if _reports_logger:
        _reports_logger.info(msg)


def log_quarantine_action(action: str, file_path: str, threat_name: str) -> None:
    """Writes a quarantine isolation, restore, or delete event into report.log."""
    if not _logger_initialized:
        setup_logging()
    msg = f"Quarantine Action: {action.upper()} | File: '{file_path}' | Threat: '{threat_name}'"
    if _reports_logger:
        _reports_logger.info(msg)


def log_settings_change(changes: Any) -> None:
    """Writes user settings modification events into report.log."""
    if not _logger_initialized:
        setup_logging()
    if isinstance(changes, dict):
        items = [f"{k}={v}" for k, v in changes.items()]
        msg = f"Settings Updated | {', '.join(items)}"
    else:
        msg = f"Settings Updated | {changes}"
    if _reports_logger:
        _reports_logger.info(msg)


def open_log_folder() -> bool:
    """Opens the logs directory in the native OS file explorer."""
    logs_dir = AppPaths.get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(logs_dir))
            return True
        elif sys.platform == "darwin":
            from pyegclamui.core.process import run_hidden_process
            run_hidden_process(["open", str(logs_dir)], check=False)
            return True
        else:
            from pyegclamui.core.process import run_hidden_process
            run_hidden_process(["xdg-open", str(logs_dir)], check=False)
            return True
    except Exception as e:
        logger = get_logger("logger")
        logger.error(f"Failed to open log directory '{logs_dir}': {e}")
        return False


def shutdown_logging() -> None:
    """Flushes and closes all handlers on pyegclamui loggers and resets initialization state."""
    global _errors_logger, _reports_logger, _logger_initialized
    for log in [_errors_logger, _reports_logger]:
        if log:
            for handler in list(log.handlers):
                try:
                    handler.flush()
                    handler.close()
                except Exception:
                    pass
                log.removeHandler(handler)
    _errors_logger = None
    _reports_logger = None
    _logger_initialized = False
