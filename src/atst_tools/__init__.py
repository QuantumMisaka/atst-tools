"""ATST-Tools package metadata helpers."""

from importlib.metadata import PackageNotFoundError, version as _metadata_version
from pathlib import Path


def _source_tree_version() -> str | None:
    """Return the project version from a local source-tree ``pyproject.toml``."""
    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.exists():
            continue

        in_project = False
        for raw_line in pyproject.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line == "[project]":
                in_project = True
                continue
            if in_project and line.startswith("["):
                return None
            if in_project and line.startswith("version"):
                _, value = line.split("=", 1)
                return value.strip().strip('"').strip("'")
    return None


def package_version() -> str:
    """Return the ATST-Tools package version.

    The package version is governed by ``pyproject.toml``. Source-tree runs
    read that file directly, while installed-package runs use distribution
    metadata generated from the same project version.

    Returns:
        Project package version, or ``"unknown"`` when neither source-tree nor
        installed-package metadata is available.
    """
    return _source_tree_version() or _installed_version()


def _installed_version() -> str:
    try:
        return _metadata_version("atst-tools")
    except PackageNotFoundError:
        return "unknown"


__version__ = package_version()

__all__ = ["__version__", "package_version"]
