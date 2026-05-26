"""Shared pytest configuration for ATST-Tools tests."""

from __future__ import annotations

import pytest


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
