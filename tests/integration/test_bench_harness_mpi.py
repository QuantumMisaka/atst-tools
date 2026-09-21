"""Real-launcher regression: the batch harness launches an image-parallel case."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

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


SLEEPING_WORKER = """\
import os, time
from pathlib import Path

with (Path.cwd() / "pids.txt").open("a", encoding="utf-8") as handle:
    handle.write(f"{os.getpid()}\\n")
time.sleep(120)
"""


def test_harness_terminates_every_mpi_rank_on_timeout(tmp_path: Path) -> None:
    """A timed-out multi-rank case must not leave any rank behind (review F1)."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec") or shutil.which("mpirun")
    if launcher is None:
        pytest.skip("no MPI launcher is available")
    script = tmp_path / "sleeping_worker.py"
    script.write_text(SLEEPING_WORKER, encoding="utf-8")

    def factory(case, workdir, devices):
        del case, workdir, devices
        return [launcher, "-n", "2", sys.executable, str(script)]

    summary = harness.run_manifest(
        {
            "cases": [
                {
                    "case_id": "mpi-timeout",
                    "config": "config.yaml",
                    "launcher": [launcher, "-n", "2"],
                    "threads": 1,
                    "timeout_s": 3,
                    "workdir": "mpi-timeout",
                }
            ]
        },
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            telemetry=False,
            worker_factory=factory,
            default_threads=1,
        ),
    )
    assert summary["timed_out"] == 1
    pids_path = tmp_path / "out" / "mpi-timeout" / "pids.txt"
    assert pids_path.is_file()
    pids = [int(line) for line in pids_path.read_text(encoding="utf-8").split()]
    assert pids, "both ranks should have recorded their pid"
    deadline = time.monotonic() + 15
    for pid in pids:
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.2)
        else:
            raise AssertionError(f"MPI rank survived the case timeout: {pid}")
