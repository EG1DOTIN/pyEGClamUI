#!/usr/bin/env python3
"""
================================================================================
pyEGClamUI - Windows Installer Staging & Preparation Pipeline
================================================================================
Prepares the complete offline staging directory for Inno Setup compiler:
  1. Downloads official signed Python 3.12 64-bit embedded runtime.
  2. Enables site-packages & path resolution in python312._pth.
  3. Populates all pip dependencies into staging/lib.
  4. Copies pyEGClamUI application source and assets into staging/src.
  5. Bundles official ClamAV Windows binaries into staging/engine.
  6. Copies Windows background service automation scripts.

Versioning: Centric Single Source of Truth (SSOT) from src/pyegclamui/__init__.py.
================================================================================
"""

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# Repository root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# Centric Version Resolution (SSOT)
def get_version() -> str:
    init_py = REPO_ROOT / "src" / "pyegclamui" / "__init__.py"
    if init_py.is_file():
        content = init_py.read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return m.group(1).strip()
    raise RuntimeError(f"Unable to extract __version__ from {init_py}")

VERSION = get_version()
EMBED_PYTHON_URL = "https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip"
CLAMAV_WIN_URL = "https://www.clamav.net/downloads/production/clamav-1.4.1.win.x64.zip"

BUILD_DIR = REPO_ROOT / "build"
CACHE_DIR = BUILD_DIR / "cache"
STAGING_DIR = BUILD_DIR / "windows_installer_staging"


def log(msg: str):
    print(f"[STAGING] {msg}", flush=True)


def download_file(url: str, dest_path: Path):
    """Downloads a remote file with progress reporting and local caching."""
    if dest_path.is_file() and dest_path.stat().st_size > 1024:
        log(f"Using cached download: {dest_path.name}")
        return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_path.with_suffix(".tmp")
    log(f"Downloading {dest_path.name} from {url}...")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) pyEGClamUI-Installer"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(temp_dest, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        if temp_dest.is_file():
            temp_dest.replace(dest_path)
            log(f"Downloaded successfully: {dest_path.name} ({dest_path.stat().st_size // 1024} KB)")
    except Exception as e:
        if temp_dest.is_file():
            temp_dest.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download {url}: {e}") from e


def setup_embedded_python(target_dir: Path):
    """Extracts official embedded Python and configures _pth for site-packages."""
    log("Setting up official Python 3.12 Embedded Runtime...")
    target_dir.mkdir(parents=True, exist_ok=True)

    cache_zip = CACHE_DIR / "python-3.12.3-embed-amd64.zip"
    download_file(EMBED_PYTHON_URL, cache_zip)

    with zipfile.ZipFile(cache_zip, "r") as z:
        z.extractall(target_dir)

    # Configure python312._pth to enable import site and relative lib/src folders
    pth_files = list(target_dir.glob("*._pth"))
    if not pth_files:
        raise FileNotFoundError("Could not locate *._pth file in embedded Python distribution.")

    pth_file = pth_files[0]
    pth_content = (
        "python312.zip\n"
        ".\n"
        "..\\lib\n"
        "..\\src\n"
        "import site\n"
    )
    pth_file.write_text(pth_content, encoding="utf-8")
    log(f"Configured {pth_file.name} for isolated site-packages loading.")


def install_dependencies(target_lib_dir: Path):
    """Installs required Python packages into staging/lib directory."""
    log("Populating dependencies into staging/lib...")
    target_lib_dir.mkdir(parents=True, exist_ok=True)

    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.is_file():
        raise FileNotFoundError(f"Missing requirements.txt at {req_file}")

    core_pkgs = [
        "PySide6>=6.5.0",
        "clamd>=1.0.2",
        "psutil>=5.9.0",
        "watchdog>=3.0.0",
        "send2trash>=1.8.0",
        "pywin32>=305",
    ]

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(target_lib_dir),
        *core_pkgs,
        "--no-warn-script-location",
        "--quiet",
    ]
    log(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    log("Production dependencies successfully installed into staging/lib.")


def copy_application_files(staging_dir: Path):
    """Copies application source code, entrypoints, and launch helpers."""
    log("Copying pyEGClamUI application source and assets...")
    
    # 1. Source package
    src_dest = staging_dir / "src" / "pyegclamui"
    if src_dest.exists():
        shutil.rmtree(src_dest)
    shutil.copytree(
        REPO_ROOT / "src" / "pyegclamui",
        src_dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    )

    # 2. Main entrypoint & launchers
    shutil.copy2(REPO_ROOT / "main.py", staging_dir / "main.py")
    if (REPO_ROOT / "launch.bat").is_file():
        shutil.copy2(REPO_ROOT / "launch.bat", staging_dir / "launch.bat")

    # 3. Setup helpers
    setup_dest = staging_dir / "setup"
    setup_dest.mkdir(parents=True, exist_ok=True)
    svc_script = REPO_ROOT / "setup" / "windows" / "setup_clamd_service.ps1"
    if not svc_script.is_file():
        svc_script = REPO_ROOT / "setup" / "setup_clamd_service.ps1"
    if svc_script.is_file():
        shutil.copy2(svc_script, setup_dest / "setup_clamd_service.ps1")

    inst_script = REPO_ROOT / "setup" / "windows" / "install_clamav.ps1"
    if not inst_script.is_file():
        inst_script = REPO_ROOT / "setup" / "install_clamav.ps1"
    if inst_script.is_file():
        shutil.copy2(inst_script, setup_dest / "install_clamav.ps1")

    # 4. License
    if (REPO_ROOT / "LICENSE").is_file():
        shutil.copy2(REPO_ROOT / "LICENSE", staging_dir / "LICENSE.txt")

    log("Application files staged successfully.")


def bundle_clamav_engine(target_engine_dir: Path):
    """Bundles official ClamAV Windows binaries for full offline installer capability."""
    log("Bundling ClamAV backend engine...")
    target_engine_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check if local ClamAV installation already exists
    local_clamav = Path("C:/Program Files/ClamAV")
    essential_files = ["clamscan.exe", "clamdscan.exe", "clamd.exe", "freshclam.exe"]
    if local_clamav.is_dir() and all((local_clamav / f).is_file() for f in essential_files):
        log(f"Copying ClamAV binaries from local installation: {local_clamav}")
        ignored_extensions = {".pdb", ".lib", ".exp", ".ilk", ".obj", ".iobj", ".ipdb", ".log", ".a"}
        for item in local_clamav.glob("*"):
            if item.is_file() and item.suffix.lower() not in ignored_extensions:
                shutil.copy2(item, target_engine_dir / item.name)
        log("Local ClamAV binaries bundled successfully (development symbols excluded).")
        return

    # 2. Otherwise download official ClamAV Windows release
    cache_clamav = CACHE_DIR / "clamav-1.4.1.win.x64.zip"
    try:
        download_file(CLAMAV_WIN_URL, cache_clamav)
        with zipfile.ZipFile(cache_clamav, "r") as z:
            z.extractall(target_engine_dir)
        # Flatten if extracted into subfolder
        subfolders = [p for p in target_engine_dir.iterdir() if p.is_dir()]
        if len(subfolders) == 1 and any((subfolders[0] / f).is_file() for f in essential_files):
            sub = subfolders[0]
            for child in sub.iterdir():
                shutil.move(str(child), str(target_engine_dir / child.name))
            sub.rmdir()
        # Clean any debug/development files
        for p in list(target_engine_dir.glob("**/*")):
            if p.is_file() and p.suffix.lower() in {".pdb", ".lib", ".exp", ".ilk", ".obj", ".iobj", ".ipdb", ".log", ".a"}:
                p.unlink()
        log("Downloaded ClamAV binaries bundled successfully.")
    except Exception as e:
        log(f"[WARNING] Could not bundle ClamAV binaries ({e}). Installer will link existing ClamAV on target machine.")


def find_iscc() -> Path | None:
    """Finds Inno Setup compiler executable (ISCC.exe)."""
    which_iscc = shutil.which("iscc") or shutil.which("ISCC") or shutil.which("ISCC.exe")
    if which_iscc:
        return Path(which_iscc)

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(local_appdata) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(local_appdata) / "Programs" / "Inno Setup 5" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 5\ISCC.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def compile_installer(iss_file: Path) -> bool:
    """Invokes Inno Setup compiler ISCC.exe with centric dynamic AppVersion."""
    iscc = find_iscc()
    if not iscc:
        log("[INFO] ISCC.exe not found on local machine. (Pre-installed on GitHub Actions windows-latest runners).")
        return False

    dist_dir = REPO_ROOT / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(iscc),
        f"/DAppVersion={VERSION}",
        str(iss_file),
    ]
    log(f"Compiling Inno Setup installer using: {iscc}")
    log(f"Command: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if res.returncode == 0:
        log(f"[SUCCESS] Installer created successfully in: {dist_dir}")
        return True
    else:
        log(f"[ERROR] ISCC.exe failed with exit code: {res.returncode}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="pyEGClamUI Windows Installer Staging & Build")
    parser.add_argument("--compile", action="store_true", help="Compile Inno Setup script after staging")
    parser.add_argument("--skip-deps", action="store_true", help="Skip downloading embedded Python and pip packages if staging already exists")
    args = parser.parse_args()

    log(f"Starting Windows Installer Staging for pyEGClamUI v{VERSION}")
    
    # 1. Clean Staging Directory (unless skip-deps is requested)
    if not args.skip_deps:
        if STAGING_DIR.exists():
            log(f"Cleaning previous staging directory: {STAGING_DIR}")
            shutil.rmtree(STAGING_DIR, ignore_errors=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Setup Components
    python_dir = STAGING_DIR / "python"
    lib_dir = STAGING_DIR / "lib"
    if not (args.skip_deps and python_dir.is_dir() and lib_dir.is_dir()):
        setup_embedded_python(python_dir)
        install_dependencies(lib_dir)
    else:
        log("Reusing cached embedded Python and dependencies in staging/...")

    copy_application_files(STAGING_DIR)

    log("================================================================================")
    log(f"Staging completed successfully in: {STAGING_DIR}")
    log(f"Centric Version: {VERSION}")
    log("================================================================================")

    iss_candidate = REPO_ROOT / "setup" / "windows" / "pyegclamui_installer.iss"
    if not iss_candidate.is_file():
        iss_candidate = REPO_ROOT / "setup" / "pyegclamui_installer.iss"

    if args.compile or find_iscc():
        if iss_candidate.is_file():
            ok = compile_installer(iss_candidate)
            if not ok and args.compile:
                sys.exit(1)
        else:
            log(f"[ERROR] Inno Setup script not found at {iss_candidate}")
            if args.compile:
                sys.exit(1)
    else:
        log("Ready for Inno Setup compilation (ISCC.exe).")


if __name__ == "__main__":
    main()
