"""
Centric pytest configuration and shared fixtures for pyEGClamUI test suite.
Ensures headless Qt QPA initialization across Windows, Linux, and macOS.
"""

import os
import sys

# Ensure headless Qt offscreen platform is set before any PySide6 modules load
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Shared single QApplication session fixture with clean teardown."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pyEGClamUI-Test"])
    yield app
