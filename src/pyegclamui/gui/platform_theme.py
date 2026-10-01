"""
Cross-platform OS window decoration and theme manager.
Safely integrates dark titlebars on Windows (DWM), macOS, and Linux
without overriding native OS window management, snapping, or multi-monitor gestures.
"""

import sys
from typing import Optional
from PySide6.QtWidgets import QWidget


def apply_dark_titlebar(window: Optional[QWidget]) -> None:
    """
    Applies an immersive dark title bar to the native window frame.
    Guaranteed safe and non-blocking on Windows, Linux, and macOS.
    """
    if window is None:
        return

    # Windows 10 (1809+) and Windows 11 DWM dark caption integration
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof

            hwnd = int(window.winId())
            if not hwnd:
                return

            dwmapi = ctypes.windll.dwmapi

            # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on Win10 1809+ and Win11, 19 on earlier Win10 builds
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            val = c_int(1)
            # Try attribute 20 first
            res = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                byref(val),
                sizeof(val)
            )
            if res != 0:
                # Fallback to attribute 19
                dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1,
                    byref(val),
                    sizeof(val)
                )

            # Windows 11 Caption & Text color (0x00BBGGRR format for #1e1f22: R=0x1e, G=0x1f, B=0x22 -> 0x00221f1e)
            caption_color = c_int(0x00221F1E)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_CAPTION_COLOR,
                byref(caption_color),
                sizeof(caption_color)
            )

            text_color = c_int(0x00FFFFFF)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_TEXT_COLOR,
                byref(text_color),
                sizeof(text_color)
            )
        except Exception:
            # Silently ignore if running in virtual/headless environment or older Windows
            pass

    elif sys.platform == "darwin":
        # macOS: Qt / Cocoa natively synchronizes with the dark mode application appearance
        pass

    elif sys.platform.startswith("linux"):
        # Linux: X11/Wayland window managers (Mutter, KWin, XFWM) follow standard Qt dark palette
        pass
