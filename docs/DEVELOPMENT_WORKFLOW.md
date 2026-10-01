# Development Workflow & Release Engineering Guide

This document defines the official engineering workflow, branching strategy, quality gates, automated deployment pipelines, and release management rules for **pyEGClamUI**.

---

## 1. Branching Strategy & Conventions

pyEGClamUI follows a **Trunk-Based Development** model with short-lived feature and fix branches. The `main` branch serves as the single source of truth for stable, release-ready code.

```mermaid
flowchart LR
    subgraph Development ["Feature / Fix Branches"]
        direction TB
        F1["feature/scheduled-scan"]
        F2["fix/display-lock-hang"]
        F3["docs/workflow-guide"]
    end

    subgraph Trunk ["Main Trunk (Production)"]
        Main["main (Always Green & Deployable)"]
    end

    subgraph CI ["Automated CI Matrix"]
        Win["🪟 windows-latest"]
        Lnx["🐧 ubuntu-latest"]
        Mac["🍎 macos-latest"]
    end

    subgraph Release ["Release Publishing"]
        Tag["git tag vX.Y.Z"]
        GH["GitHub Releases (Executables & Assets)"]
    end

    F1 -->|"Pull Request"| Main
    F2 -->|"Pull Request"| Main
    F3 -->|"Pull Request"| Main

    Main --> Win & Lnx & Mac
    Main -->|"Annotated Tag"| Tag --> GH
```

### Branch Naming Conventions

All branches created off `main` must adhere to standard lowercase descriptive prefixes:

| Branch Prefix | Purpose | Example |
| :--- | :--- | :--- |
| 🟢 `feature/<name>` | New application capability, GUI dialog, or scanning mode | `feature/scheduled-scans` |
| 🟡 `fix/<name>` | Bug fix, regression resolution, or race condition patch | `fix/quarantine-path-resolver` |
| ⚪ `docs/<name>` | Documentation updates, architecture guides, or API specs | `docs/workflow-guide` |
| 🛡️ `chore/<name>` | Dependency updates, tooling enhancements, or CI tweaks | `chore/upgrade-pytest` |

### Working on a Feature Branch

1. **Pull Latest Main**:
   ```bash
   git checkout main
   git pull origin main
   ```
2. **Create Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Develop & Test Inside `.venv`**:
   Execute all changes within the virtual environment and ensure 100% test passage:
   ```bash
   .venv\Scripts\pytest tests/
   ```
4. **Commit with Conventional Messages**:
   Use standard prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`):
   ```bash
   git commit -m "feat(scanner): add custom file size limit filter"
   ```

---

## 2. Quality Gates & Local Validation

Before pushing any branch or requesting review, developers must pass all local quality checks:

| Gate | Tool / Command | Success Criteria |
| :--- | :--- | :--- |
| 🧪 **Unit Tests** | `pytest tests/` | 100% passing across all test suites (115+ tests) |
| ⚡ **Speed Requirement** | `pytest -v tests/` | Total execution completes in under 20 seconds |
| 🛡️ **Headless Isolation** | `QT_QPA_PLATFORM=offscreen` | Zero modal popups (`QMessageBox`) blocking execution |
| 📦 **Packaging Validation** | `python scripts/build.py --no-archive` | Standalone executable compiles without missing imports |

> [!IMPORTANT]
> **Zero-Deletion Policy**: Never permanently delete deprecated code, scripts, or assets. Instead, move obsolete files to `.unused-old-files/<category>/` in compliance with repository governance standards.

---

## 3. Pull Requests & Automated CI Pipeline

When a branch is pushed and a Pull Request is opened against `main`, GitHub Actions automatically triggers the multi-platform matrix:

```mermaid
flowchart TD
    PR["Pull Request to main"] --> Matrix["GitHub Actions Build Matrix"]
    
    subgraph Matrix ["Parallel Multi-Platform Matrix"]
        direction LR
        W["🪟 Windows (windows-latest)<br/>• Python 3.12<br/>• Full Pytest Suite<br/>• PyInstaller .exe Build"]
        L["🐧 Linux (ubuntu-latest)<br/>• Python 3.12<br/>• Offscreen Pytest<br/>• PyInstaller ELF Binary"]
        M["🍎 macOS (macos-latest)<br/>• Python 3.12<br/>• Full Pytest Suite<br/>• PyInstaller .app Bundle"]
    end

    W & L & M --> Gate{"All Matrix Jobs Pass?"}
    Gate -- "🟢 Yes" --> Merge["Ready for Merge into main"]
    Gate -- "🔴 No" --> Block["Merge Blocked / Fix Required"]
```

### Headless Display Architecture

To guarantee identical behavior across developer workstations and cloud CI environments:
* PySide6 tests run with `QT_QPA_PLATFORM=offscreen`.
* Qt dialogs use mock fixtures or guard checks (`if os.getenv("QT_QPA_PLATFORM") != "offscreen":`) to prevent modal blocking.
* No Xvfb server locks or display daemons are required on Linux.

---

## 4. Release Rules & Version Management

pyEGClamUI follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`).

### Version Single Source of Truth (SSOT)

Version numbers are declared in exactly two statutory files:
1. **Runtime SSOT**: [`src/pyegclamui/__init__.py`](../src/pyegclamui/__init__.py) (`__version__ = "X.Y.Z"`)
2. **Packaging SSOT**: [`pyproject.toml`](../pyproject.toml) (`version = "X.Y.Z"`)

Both files must match identically before any release tag is cut. This is strictly verified by [`tests/test_version.py`](../tests/test_version.py).

---

## 5. Deployment & Scratch Staging Architecture

A critical principle of pyEGClamUI release engineering is **document immutability**:
* Repository documentation (`README.md`, `LICENSE`, `docs/*.md`) and source code must remain **100% fixed, clean, and untouched** during packaging.
* Build tools, PyInstaller, and packaging scripts must **never** mutate repository files in place.

```mermaid
flowchart TD
    subgraph SourceRepo ["Repository Root (Fixed & Immutable)"]
        Src["src/pyegclamui/..."]
        Readme["README.md"]
        Lic["LICENSE"]
        Desktop["pyegclamui.desktop"]
        Setup["setup/install.sh"]
    end

    subgraph ScratchArea ["Ephemeral Scratch Staging (dist/package_staging/)"]
        StageExe["Compiled Binary (pyEGClamUI.exe / ELF / .app)"]
        StageDoc["Read-Only Copy: README.md"]
        StageLic["Read-Only Copy: LICENSE"]
        StageDesk["Read-Only Copy: pyegclamui.desktop"]
    end

    subgraph FinalOutput ["Distribution Output (dist/)"]
        Zip["pyegclamui-vX.Y.Z-windows-x64.zip"]
        Tar["pyegclamui-vX.Y.Z-linux-x86_64.tar.gz"]
        MacZip["pyegclamui-vX.Y.Z-macos-*.zip"]
    end

    Src -->|"PyInstaller Compile"| StageExe
    Readme & Lic & Desktop & Setup -->|"Read-Only Snapshot Copy"| ScratchArea
    ScratchArea -->|"Compress & Package"| FinalOutput
    ScratchArea -.->|"shutil.rmtree (Immediate Purge)"| Clean["Scratch Folder Removed"]
```

### How the Scratch Staging Pattern Works

In [`scripts/build.py`](../scripts/build.py):
1. **Compilation Phase**: PyInstaller builds the executable directly into `dist/`.
2. **Scratch Staging Creation**: A dedicated sandbox directory (`dist/package_staging/`) is initialized.
3. **Snapshot Ingestion**: Essential legal and launcher files are copied into the sandbox as read-only copies.
4. **Archive Packaging**: Zip or tar.gz archives are generated from the staging directory contents.
5. **Immediate Cleanup**: `shutil.rmtree(staging_dir)` permanently wipes the scratch folder, leaving the repository tree completely clean.

**Benefits**:
* 🟢 **Zero Git Dirtying**: No leftover temporary files or modified working tree states after building.
* 🟢 **Document Safety**: Production documents are never overwritten, renamed, or corrupted during deployment.
* 🟢 **Isolated Build Artifacts**: All build outputs reside strictly inside `dist/` and `build/`, which are ignored by `.gitignore`.

---

## 6. Step-by-Step Release Checklist

Follow this checklist sequentially whenever releasing a new public version:

| Step | Action | Command / Location |
| :---: | :--- | :--- |
| **1** | Confirm working tree is clean | `git status` (no uncommitted changes) |
| **2** | Run entire test suite locally | `.venv\Scripts\pytest tests/` (115+ passing) |
| **3** | Verify SSOT version alignment | Confirm `src/pyegclamui/__init__.py` == `pyproject.toml` |
| **4** | Push all commits to `main` | `git push origin main` |
| **5** | Create annotated release tag | `git tag -fa vX.Y.Z -m "Release vX.Y.Z"` |
| **6** | Push release tag to GitHub | `git push origin vX.Y.Z --force` |
| **7** | Monitor automated release build | Check [GitHub Actions](https://github.com/EG1DOTIN/pyEGClamUI/actions) |
| **8** | Verify public release downloads | Check [GitHub Releases](https://github.com/EG1DOTIN/pyEGClamUI/releases) |

---

## 7. Related Documentation

* [`VERSIONING.md`](VERSIONING.md) — Single Source of Truth architecture and SemVer specifications.
* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System architecture, thread boundaries, and engine layers.
* [`SECURITY_MODEL.md`](SECURITY_MODEL.md) — Subprocess execution safety and permission policies.
* [`README.md`](README.md) — Complete documentation suite map and subsystem index.
