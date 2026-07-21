"""Package metadata governance tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def test_runtime_dependency_policy_is_explicit() -> None:
    """Default install dependencies should be explicit and lightweight."""
    project = _project_metadata()

    assert project["requires-python"] == ">=3.10"
    assert project["dependencies"] == [
        "ase>=3.28.0",
        "numpy>=1.26,<3",
        "scipy>=1.13,<2",
        "pydantic>=2,<3",
        "ruamel.yaml>=0.18,<0.20",
        "seekpath>=2.2,<3",
        "sella>=2.5,<3",
    ]


def test_optional_dependency_groups_cover_feature_specific_stacks() -> None:
    """Heavy or feature-specific stacks should be opt-in extras."""
    optional = _project_metadata()["optional-dependencies"]

    assert optional["plot"] == ["matplotlib>=3.9,<4"]
    assert optional["dp"] == ["deepmd-kit>=3.1.3"]
    assert optional["parallel"] == ["mpi4py>=4.1.2"]
    assert optional["test"] == ["pytest>=8.4,<10"]
    assert optional["release"] == ["build>=1.5,<2", "twine>=6.2,<7"]
    assert optional["dev"] == [
        "pytest>=8.4,<10",
        "build>=1.5,<2",
        "twine>=6.2,<7",
    ]


def test_wheel_release_gate_script_exposes_a_clean_install_check() -> None:
    """Release verification is available without leaving build artifacts in-tree."""
    script = ROOT / "scripts" / "verify_wheel_api.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--wheel" in result.stdout


def test_wheel_release_gate_rejects_source_tree_imports() -> None:
    """The wheel gate must isolate imports from inherited source paths."""
    script = (ROOT / "scripts" / "verify_wheel_api.py").read_text(encoding="utf-8")

    assert "PYTHONPATH" in script
    assert "site.getsitepackages" in script
    assert "atst_tools.__file__" in script
    assert "is_relative_to" in script
