#!/usr/bin/env python3
"""
pyEGClamUI Root Setup Script.

Supports:
  1. Standard packaging & editable installs:
     pip install -e .
  2. Direct CLI installer execution:
     python setup.py [--install] [--update] [--check] [--shortcuts-only] [--uninstall]
  3. Module import compatibility:
     Re-exports setup installer components from setup/setup.py.
"""

import importlib.util
import sys
from pathlib import Path

# Standard Setuptools build commands used by pip and build tools
SETUPTOOLS_COMMANDS = {
    "bdist_wheel",
    "sdist",
    "egg_info",
    "dist_info",
    "develop",
    "build",
    "build_py",
    "build_ext",
    "clean",
}

if __name__ == "__main__":
    args = sys.argv[1:]
    # If invoked with setuptools distribution build commands, pass to setuptools
    is_setuptools_build = bool(args and args[0] in SETUPTOOLS_COMMANDS)

    if not is_setuptools_build:
        # User CLI execution (e.g. python setup.py, python setup.py --check, --help, --install, etc.)
        import subprocess

        installer_script = Path(__file__).resolve().parent / "setup" / "setup.py"
        if installer_script.is_file():
            sys.exit(subprocess.call([sys.executable, str(installer_script)] + args))

# Re-export public components from setup/setup.py so 'import setup' works seamlessly everywhere
try:
    _installer_file = Path(__file__).resolve().parent / "setup" / "setup.py"
    if _installer_file.is_file():
        _spec = importlib.util.spec_from_file_location("_pyegclamui_setup", _installer_file)
        if _spec and _spec.loader:
            _inner_mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_inner_mod)
            for _attr in dir(_inner_mod):
                if not _attr.startswith("_"):
                    globals()[_attr] = getattr(_inner_mod, _attr)
except Exception:
    pass

# Package distribution setup for setuptools / pip
try:
    from setuptools import setup

    setup()
except (ImportError, ModuleNotFoundError):
    pass
