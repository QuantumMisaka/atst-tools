"""Real-launcher regression: the batch harness launches an image-parallel case."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from atst_tools.bench import harness


ROOT = Path(__file__).resolve().parents[2]


def _mpi_test_enabled() -> bool:
    return os.environ.get("ATST_RUN_MPI_TESTS") == "1"


def test_harness_runs_an_mpi_launched_case(tmp_path: Path) -> None:
    """A case with a launcher keeps the harness report and timeout contract."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec") or shutil.which("mpirun")
    if launcher is None:
        pytest.skip("no MPI launcher is available")

    config = tmp_path / "config.yaml"
    config.write_text(
        "calculation:\n"
        "  type: relax\n"
        "  init_structure: initial.traj\n"
        "calculator:\n"
        "  name: abacus\n"
        "  abacus:\n"
        "    parameters: {}\n",
        encoding="utf-8",
    )
    manifest = {
        "cases": [
            {
                "case_id": "mpi-dry-run",
                "config": str(config),
                "launcher": [launcher, "-n", "2"],
                "args": ["--dry-run"],
                "threads": 1,
                "timeout_s": 60,
            }
        ]
    }
    summary = harness.run_manifest(
        manifest,
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            telemetry=False,
            default_threads=1,
        ),
    )
    assert summary["succeeded"] == 1
    row = summary["cases"][0]
    assert row["launcher"][:2] == [launcher, "-n"]
    assert row["args"] == ["--dry-run"]
    result = json.loads(
        (tmp_path / "out" / "mpi-dry-run" / harness.DEFAULT_RESULT_JSON).read_text(
            encoding="utf-8"
        )
    )
    assert result["schema"] == "atst-api-result-v1"
    assert result["status"] == "success"
    assert result["is_root"] is True
