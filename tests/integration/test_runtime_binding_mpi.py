"""Real-launcher regressions for per-rank runtime device binding (P4)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MPI_TIMEOUT_SECONDS = 30


def _mpi_test_enabled() -> bool:
    """Return whether the opt-in real MPI regression suite is enabled."""
    return os.environ.get("ATST_RUN_MPI_TESTS") == "1"


def _launcher() -> str:
    launcher = shutil.which("mpiexec") or shutil.which("mpirun")
    if launcher is None:
        pytest.skip("no MPI launcher is available")
    return launcher


def _run_mpi(command: list[str], *, cwd: Path, environment: dict[str, str]):
    """Run one launcher command with a bounded timeout that kills peers."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=MPI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        pytest.fail(f"MPI runtime regression timed out after {MPI_TIMEOUT_SECONDS}s")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


RESOLVER_SNIPPET = """\
import json, os, sys
from pathlib import Path
from atst_tools.runtime import devices

out = Path(sys.argv[1])
resolution = devices.resolve_devices(
    devices.parse_device_tokens([0, 1]),
    binding="round_robin",
    environ=dict(os.environ),
)
payload = {
    "effective": list(resolution.effective),
    "mask": resolution.child_mask,
    "notes": list(resolution.notes),
}
with out.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload) + "\\n")
"""


def test_round_robin_assigns_one_device_per_rank(tmp_path: Path) -> None:
    """Each rank of a two-rank launch owns a distinct device from the pool."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    script = tmp_path / "rank_binding.py"
    script.write_text(RESOLVER_SNIPPET, encoding="utf-8")
    out = tmp_path / "ranks.jsonl"

    environment = _environment()
    environment["CUDA_VISIBLE_DEVICES"] = "2,3"
    completed = _run_mpi(
        [_launcher(), "-n", "2", sys.executable, str(script), str(out)],
        cwd=tmp_path,
        environment=environment,
    )
    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    masks = sorted(row["mask"] for row in rows)
    assert masks == ["2", "3"]
    assert all("round_robin_rank_device" in row["notes"] for row in rows)


CLI_DISPATCH_SNIPPET = """\
import json, os, sys
from pathlib import Path
from atst_tools.runtime import cli_dispatch

out = Path(sys.argv[1])
config = Path(sys.argv[2])
plan = cli_dispatch.plan_runtime_launch(
    ["run", str(config), "--devices", "0,1", "--binding", "round_robin"],
    environ=dict(os.environ),
)
if plan is None:
    raise SystemExit("expected an isolated launch plan under MPI")
payload = {
    "mask": plan.environment["CUDA_VISIBLE_DEVICES"],
    "bound": plan.environment.get("ATST_RUNTIME_BOUND"),
    "module": plan.command[1:3],
}
with out.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload) + "\\n")
"""


def test_cli_dispatch_plans_rank_local_masks_under_mpi(tmp_path: Path) -> None:
    """The coordinator path hands each MPI rank its own bound worker command."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    script = tmp_path / "cli_dispatch_rank.py"
    script.write_text(CLI_DISPATCH_SNIPPET, encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        "calculation:\n  type: relax\n  init_structure: init.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )
    out = tmp_path / "plans.jsonl"
    environment = _environment()
    environment["CUDA_VISIBLE_DEVICES"] = "2,3"

    completed = _run_mpi(
        [_launcher(), "-n", "2", sys.executable, str(script), str(out), str(config)],
        cwd=tmp_path,
        environment=environment,
    )
    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert sorted(row["mask"] for row in rows) == ["2", "3"]
    assert all(row["bound"] == "1" for row in rows)
    assert all(row["module"] == ["-m", "atst_tools.api.runner"] for row in rows)
