"""
pyEGClamUI - Repository root launcher.
Allows running `python main.py` directly from the repository root.
"""

import os
import sys
from pathlib import Path

# If a local .venv exists and we are not currently running inside it, re-exec with .venv/bin/python
repo_root = Path(__file__).resolve().parent
venv_python = (
    repo_root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
)

if venv_python.is_file() and not os.environ.get("_PYEGCLAMUI_IN_VENV"):
    try:
        if Path(sys.prefix).resolve() != (repo_root / ".venv").resolve():
            os.environ["_PYEGCLAMUI_IN_VENV"] = "1"
            os.execv(str(venv_python), [str(venv_python), str(__file__)] + sys.argv[1:])
    except Exception:
        pass

# Ensure src/ is on sys.path for local development
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from pyegclamui.gui.app import main

if __name__ == "__main__":
    sys.exit(main())

