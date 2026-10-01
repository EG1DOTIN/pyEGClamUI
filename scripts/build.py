#!/usr/bin/env python3
"""
pyEGClamUI Cross-Platform Build & Packaging Script.

Automates building standalone binaries and distributable packages across:
  - Windows: pyEGClamUI.exe (zipped standalone executable with assets)
  - Linux:   pyegclamui (tar.gz with executable, desktop entry, and icon)
  - macOS:   pyEGClamUI.app (zipped macOS application bundle)

Usage:
  python scripts/build.py [--clean] [--onefile] [--no-archive]
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

# Ensure stdout/stderr handles UTF-8 safely
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure src/ is on sys.path to retrieve version
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from pyegclamui import __version__
except ImportError:
    __version__ = "3.0.0"


def get_platform_info() -> dict:
    """Returns platform-specific build configuration and naming."""
    sys_plat = sys.platform
    arch = platform.machine().lower()
    if arch in ("amd64", "x86_64"):
        norm_arch = "x86_64"
    elif arch in ("arm64", "aarch64"):
        norm_arch = "arm64"
    else:
        norm_arch = arch

    if sys_plat == "win32":
        return {
            "os_name": "windows",
            "arch": "x64" if norm_arch == "x86_64" else norm_arch,
            "exe_name": "pyEGClamUI.exe",
            "data_sep": ";",
            "icon": REPO_ROOT / "src" / "pyegclamui" / "assets" / "egav.ico",
            "archive_type": "zip",
            "archive_name": f"pyegclamui-v{__version__}-windows-x64.zip",
        }
    elif sys_plat == "darwin":
        return {
            "os_name": "macos",
            "arch": norm_arch,
            "exe_name": "pyEGClamUI",
            "data_sep": ":",
            "icon": REPO_ROOT / "src" / "pyegclamui" / "assets" / "egav.png",
            "archive_type": "zip",
            "archive_name": f"pyegclamui-v{__version__}-macos-{norm_arch}.zip",
        }
    else:
        return {
            "os_name": "linux",
            "arch": norm_arch,
            "exe_name": "pyegclamui",
            "data_sep": ":",
            "icon": REPO_ROOT / "src" / "pyegclamui" / "assets" / "egav.png",
            "archive_type": "tar.gz",
            "archive_name": f"pyegclamui-v{__version__}-linux-{norm_arch}.tar.gz",
        }


def clean_build_dirs():
    """Removes previous build artifacts."""
    print("[CLEAN] Cleaning previous build and dist directories...")
    for dir_name in ["build", "dist"]:
        d = REPO_ROOT / dir_name
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for spec in REPO_ROOT.glob("*.spec"):
        try:
            spec.unlink()
        except OSError:
            pass


def run_pyinstaller(plat_info: dict, onefile: bool = True) -> Path:
    """Executes PyInstaller to compile the standalone binary."""
    entrypoint = REPO_ROOT / "main.py"
    assets_dir = REPO_ROOT / "src" / "pyegclamui" / "assets"
    data_arg = f"{assets_dir}{plat_info['data_sep']}pyegclamui/assets"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        "pyEGClamUI" if plat_info["os_name"] != "linux" else "pyegclamui",
        "--windowed",
        "--add-data",
        data_arg,
        "--collect-all",
        "pyegclamui",
        "--hidden-import",
        "clamd",
        "--hidden-import",
        "watchdog",
        "--hidden-import",
        "psutil",
        "--hidden-import",
        "send2trash",
    ]

    if plat_info["os_name"] == "windows":
        cmd.extend(["--hidden-import", "win32api", "--hidden-import", "win32con"])

    if plat_info["icon"].exists():
        cmd.extend(["--icon", str(plat_info["icon"])])

    if plat_info["os_name"] == "macos":
        # On macOS, onedir bundle produces a clean .app bundle
        cmd.append("--onedir")
    elif onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    cmd.append(str(entrypoint))

    print(f"[BUILD] Running PyInstaller for {plat_info['os_name']} ({plat_info['arch']})...")
    print(f"        Command: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(REPO_ROOT))

    dist_dir = REPO_ROOT / "dist"
    return dist_dir


def create_archive(plat_info: dict, dist_dir: Path) -> Path:
    """Packages the compiled executable and companion files into an archive."""
    archive_path = dist_dir / plat_info["archive_name"]
    print(f"[PACKAGE] Packaging distribution archive: {archive_path.name}...")

    staging_dir = dist_dir / "package_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Copy legal and documentation files
    for doc in ["README.md", "LICENSE"]:
        doc_file = REPO_ROOT / doc
        if doc_file.exists():
            shutil.copy2(doc_file, staging_dir / doc)

    # Copy executable or macOS app bundle
    if plat_info["os_name"] == "macos":
        app_bundle = dist_dir / "pyEGClamUI.app"
        if app_bundle.exists():
            shutil.copytree(app_bundle, staging_dir / "pyEGClamUI.app")
        else:
            # fallback to binary
            bin_file = dist_dir / "pyEGClamUI"
            if bin_file.exists():
                shutil.copy2(bin_file, staging_dir / "pyEGClamUI")
    else:
        binary = dist_dir / plat_info["exe_name"]
        if binary.exists():
            shutil.copy2(binary, staging_dir / plat_info["exe_name"])
            if plat_info["os_name"] == "linux":
                # Ensure executable permissions
                os.chmod(staging_dir / plat_info["exe_name"], 0o755)

    # Platform-specific extras
    if plat_info["os_name"] == "linux":
        desktop_file = REPO_ROOT / "src" / "pyegclamui" / "assets" / "pyegclamui.desktop"
        icon_file = REPO_ROOT / "src" / "pyegclamui" / "assets" / "egav.png"
        if desktop_file.exists():
            shutil.copy2(desktop_file, staging_dir / "pyegclamui.desktop")
        if icon_file.exists():
            shutil.copy2(icon_file, staging_dir / "pyegclamui.png")
        install_sh = REPO_ROOT / "setup" / "install.sh"
        if install_sh.exists():
            shutil.copy2(install_sh, staging_dir / "install.sh")
    elif plat_info["os_name"] == "windows":
        install_ps1 = REPO_ROOT / "setup" / "install.ps1"
        if install_ps1.exists():
            shutil.copy2(install_ps1, staging_dir / "install.ps1")

    # Create zip or tar.gz
    if plat_info["archive_type"] == "zip":
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in staging_dir.rglob("*"):
                zf.write(item, arcname=item.relative_to(staging_dir))
    else:
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(staging_dir, arcname=f"pyegclamui-v{__version__}")

    shutil.rmtree(staging_dir, ignore_errors=True)
    print(f"[OK] Archive created successfully: {archive_path} ({archive_path.stat().st_size:,} bytes)")
    return archive_path


def main():
    parser = argparse.ArgumentParser(description="Build pyEGClamUI standalone executable and package")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before starting")
    parser.add_argument("--onedir", action="store_true", help="Build directory instead of single file")
    parser.add_argument("--no-archive", action="store_true", help="Skip creating zip/tar.gz archive")
    args = parser.parse_args()

    plat_info = get_platform_info()
    print(f"=== Building pyEGClamUI v{__version__} for {plat_info['os_name']} ===")

    if args.clean:
        clean_build_dirs()

    dist_dir = run_pyinstaller(plat_info, onefile=not args.onedir)

    if not args.no_archive:
        archive_path = create_archive(plat_info, dist_dir)
        print(f"[SUCCESS] Build completed! Distributable package ready at:\n   {archive_path}")
    else:
        print(f"[SUCCESS] Binary compilation completed in {dist_dir}!")


if __name__ == "__main__":
    main()
