"""Shared pytest configuration for ATST-Tools tests."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT_LEAK_FILES = ("md_final.traj", "md_post_summary.json")


def pytest_addoption(parser):
    """Register opt-in switches for expensive external tests."""
    parser.addoption(
        "--run-slurm",
        action="store_true",
        default=False,
        help="run tests marked slurm that may submit or require scheduler jobs",
    )


def pytest_collection_modifyitems(config, items):
    """Skip Slurm-dependent tests unless explicitly requested."""
    if config.getoption("--run-slurm"):
        return
    skip_slurm = pytest.mark.skip(reason="need --run-slurm option to run")
    for item in items:
        if "slurm" in item.keywords:
            item.add_marker(skip_slurm)


@pytest.fixture(autouse=True)
def guard_root_md_artifact_leaks():
    """Fail tests that leave known MD artifacts in the repository root."""
    yield
    leaked = [name for name in ROOT_LEAK_FILES if Path(name).exists()]
    assert leaked == [], f"test leaked root-level artifacts: {leaked}"
