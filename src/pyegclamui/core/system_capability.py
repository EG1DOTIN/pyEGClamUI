"""
pyEGClamUI - Deterministic System Capability Inspector.

Evaluates hardware specifications (CPU architecture, pointer bit-width, physical RAM)
against deterministic thresholds to route to the appropriate GUI tier:
  - Tier 1: Modern Qt6 / PySide6 Suite (64-Bit OS/CPU, Physical RAM >= 4.0 GB)
  - Tier 2: pyEGClamUI Lite Tkinter Dashboard (32-Bit OR Physical RAM < 4.0 GB)
"""

import os
import platform
import subprocess
import sys
from typing import Any, Literal

GuiTier = Literal["pyside6", "tkinter"]

# Deterministic Threshold Limits
MIN_RAM_BYTES_TIER1: int = 4 * 1024 * 1024 * 1024  # 4.0 GB
LEGACY_ARCHS: set[str] = {"i386", "i686", "i486", "i586", "x86", "armv7l", "armv6l"}


def is_64bit_architecture() -> bool:
    """
    Returns True if the runtime environment and CPU architecture are strictly 64-bit.
    Evaluates both pointer address space (sys.maxsize) and CPU machine string.
    """
    arch = platform.machine().lower()
    is_pointer_64 = sys.maxsize > (2**32)
    return is_pointer_64 and (arch not in LEGACY_ARCHS)


def get_total_ram_bytes() -> int:
    """
    Determines total physical system RAM in bytes using standard library,
    psutil, or OS-native kernel counters.
    """
    # 1. psutil (standard cross-platform dependency if installed)
    try:
        import psutil

        return int(psutil.virtual_memory().total)
    except Exception:
        pass

    # 2. Linux /proc/meminfo
    if sys.platform.startswith("linux") and os.path.isfile("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb * 1024
        except Exception:
            pass

    # 3. macOS sysctl hw.memsize
    if sys.platform == "darwin":
        try:
            res = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True
            )
            return int(res.stdout.strip())
        except Exception:
            pass

    # 4. Windows ctypes GlobalMemoryStatusEx
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys)
        except Exception:
            pass

    # Safe default: on 64-bit assume 8 GB, on 32-bit assume 2 GB
    return (8 if is_64bit_architecture() else 2) * 1024 * 1024 * 1024


def determine_gui_tier(user_override: str | None = None) -> GuiTier:
    """
    Deterministically evaluates system capabilities to pick the appropriate GUI tier.
    Does NOT rely on trial-and-error PySide6 imports.

    Returns:
      - 'pyside6': Modern Qt6 GUI (64-Bit OS & RAM >= 4.0 GB)
      - 'tkinter': pyEGClamUI Lite Dashboard (32-Bit OR RAM < 4.0 GB)
    """
    # Explicit user CLI / config override
    if user_override:
        norm = user_override.strip().lower()
        if norm in ("pyside6", "qt6", "qt", "tier1"):
            return "pyside6"
        if norm in ("tkinter", "tk", "lite", "tier2"):
            return "tkinter"

    # Deterministic limit check
    if not is_64bit_architecture():
        return "tkinter"

    total_ram = get_total_ram_bytes()
    if total_ram < MIN_RAM_BYTES_TIER1:
        return "tkinter"

    return "pyside6"


def get_system_specs() -> dict[str, Any]:
    """Returns a dictionary summarizing detected system specifications and assigned GUI tier."""
    arch = platform.machine()
    is_64 = is_64bit_architecture()
    ram_bytes = get_total_ram_bytes()
    ram_gb = round(ram_bytes / (1024**3), 2)
    tier = determine_gui_tier()

    return {
        "platform": sys.platform,
        "os_release": f"{platform.system()} {platform.release()}",
        "machine": arch,
        "is_64bit": is_64,
        "ram_bytes": ram_bytes,
        "ram_gb": ram_gb,
        "gui_tier": tier,
        "gui_name": "Modern Qt6 Suite" if tier == "pyside6" else "pyEGClamUI Lite (Tkinter)",
    }
