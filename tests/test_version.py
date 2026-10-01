"""
Unit tests for application versioning integrity and single-source-of-truth synchronization.
"""

import re
from pathlib import Path
import pyegclamui


def test_version_format():
    """Validates that __version__ follows Semantic Versioning (MAJOR.MINOR.PATCH)."""
    version = pyegclamui.__version__
    assert isinstance(version, str)
    assert len(version.strip()) > 0

    # SemVer regex pattern (e.g., 3.0.0, 3.1.0-beta.1)
    semver_pattern = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
    assert re.match(semver_pattern, version) is not None, (
        f"__version__ '{version}' does not adhere to Semantic Versioning (e.g. 3.0.0)"
    )


def test_version_matches_pyproject_toml():
    """Ensures src/pyegclamui/__init__.py and pyproject.toml are strictly synchronized."""
    project_root = Path(__file__).resolve().parent.parent
    pyproject_path = project_root / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found at project root"

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert match is not None, "version entry missing in pyproject.toml"

    pyproject_version = match.group(1)
    assert pyegclamui.__version__ == pyproject_version, (
        f"Version mismatch! __init__.py has '{pyegclamui.__version__}', "
        f"but pyproject.toml has '{pyproject_version}'."
    )


def test_version_components():
    """Validates that major, minor, and patch numbers are valid integers."""
    base_version = pyegclamui.__version__.split("-")[0].split("+")[0]
    parts = base_version.split(".")
    assert len(parts) == 3, f"Expected 3 parts in base version, got: {parts}"
    major, minor, patch = parts
    assert major.isdigit() and int(major) >= 0
    assert minor.isdigit() and int(minor) >= 0
    assert patch.isdigit() and int(patch) >= 0
