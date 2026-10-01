"""
pyEGClamUI - Repository root launcher.
Allows running `python main.py` directly from the repository root.
"""

import sys
from pathlib import Path

# Ensure src/ is on sys.path for local development
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from pyegclamui.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
