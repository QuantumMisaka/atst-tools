"""Real-launcher regressions for image-parallel failure synchronization."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MPI_TIMEOUT_SECONDS = 15


def _mpi_test_enabled() -> bool:
    """Return whether the opt-in real MPI regression suite is enabled."""
    return os.environ.get("ATST_RUN_MPI_TESTS") == "1"


def _run_mpi(command: list[str], *, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a launcher command with a timeout that also terminates peer ranks."""
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
        pytest.fail(f"MPI regression timed out after {MPI_TIMEOUT_SECONDS} seconds")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


@pytest.mark.parametrize("workflow", ["neb", "autoneb"])
def test_root_endpoint_failure_releases_every_image_parallel_rank(
    tmp_path: Path, workflow: str
) -> None:
    """A root-only endpoint error must not leave its peer at a barrier."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec")
    bundled_launcher = Path(sys.executable).with_name("mpiexec")
    if launcher is None and bundled_launcher.is_file():
        launcher = str(bundled_launcher)
    if launcher is None:
        pytest.skip("mpiexec is unavailable")

    setup = (
        "from ase import Atoms; from ase.io import write; "
        "write('chain.traj', [Atoms('H', positions=[[float(i), 0, 0]]) for i in range(4)])"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    subprocess.run(
        [sys.executable, "-c", setup],
        cwd=tmp_path,
        env=environment,
        check=True,
        timeout=MPI_TIMEOUT_SECONDS,
    )
    autoneb_fields = "'n_simul': 2, 'n_max': 3," if workflow == "autoneb" else ""
    smoke = f"""
from mpi4py import MPI
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import WorkflowExecutionError

rank = MPI.COMM_WORLD.rank
if {workflow!r} == 'neb':
    from atst_tools.scripts import main as runner_module
else:
    from atst_tools.mep import autoneb as runner_module

if rank == 0:
    def fail_endpoint_preparation(*args, **kwargs):
        raise RuntimeError('injected root endpoint failure')
    runner_module.ensure_neb_endpoint_results = fail_endpoint_preparation

calculation = {{
    'type': {workflow!r},
    'init_chain': 'chain.traj',
    'parallel': True,
    {autoneb_fields}
}}
try:
    run_workflow(
        {{'calculation': calculation,
          'calculator': {{'name': 'abacus', 'abacus': {{'parameters': {{}}}}}}}},
        RunOptions(),
    )
except WorkflowExecutionError:
    failed = 1
else:
    failed = 0

assert MPI.COMM_WORLD.allreduce(failed) == 2
"""
    completed = _run_mpi(
        [launcher, "-n", "2", sys.executable, "-c", smoke],
        cwd=tmp_path,
        environment=environment,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("workflow", ["neb", "autoneb"])
def test_root_calculator_setup_failure_releases_every_image_parallel_rank(
    tmp_path: Path, workflow: str
) -> None:
    """A rank-local calculator setup error must preempt NEB collectives."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec")
    bundled_launcher = Path(sys.executable).with_name("mpiexec")
    if launcher is None and bundled_launcher.is_file():
        launcher = str(bundled_launcher)
    if launcher is None:
        pytest.skip("mpiexec is unavailable")

    setup = (
        "from ase import Atoms; "
        "from ase.io import write; "
        "chain = [Atoms('H', positions=[[float(i), 0, 0]]) for i in range(4)]; "
        "write('chain.traj', chain)"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    subprocess.run(
        [sys.executable, "-c", setup],
        cwd=tmp_path,
        env=environment,
        check=True,
        timeout=MPI_TIMEOUT_SECONDS,
    )
    autoneb_fields = "'n_simul': 2, 'n_max': 4," if workflow == "autoneb" else ""
    smoke = f"""
from mpi4py import MPI
from ase.calculators.calculator import Calculator
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import WorkflowExecutionError

rank = MPI.COMM_WORLD.rank
class NoopCalculator(Calculator):
    implemented_properties = []
if {workflow!r} == 'neb':
    from atst_tools.scripts import main as runner_module
    runner_module.ensure_neb_endpoint_results = lambda *args, **kwargs: None
    runner_module._sync_parallel_endpoint_results = lambda images, *args: images
    class FakeNEB:
        def __init__(self, *args, **kwargs):
            pass
    class CollectiveOptimizer:
        def __init__(self, *args, **kwargs):
            MPI.COMM_WORLD.Barrier()
    runner_module.AbacusNEB = FakeNEB
    runner_module.get_optimizer = lambda *args, **kwargs: CollectiveOptimizer
    def fail_on_root(*args, **kwargs):
        if rank == 0:
            raise RuntimeError('injected root calculator setup failure')
        return NoopCalculator()
    runner_module._get_workflow_calculator = fail_on_root
else:
    from atst_tools.mep import autoneb as runner_module
    from atst_tools.mep.autoneb import AutoNEBRunner
    runner_module.ensure_neb_endpoint_results = lambda *args, **kwargs: None
    def run_until_next_collective(self):
        self.attach_calculators([self.init_chain[1], self.init_chain[2]])
        MPI.COMM_WORLD.Barrier()
    AutoNEBRunner.run = run_until_next_collective
    def fail_on_root(self, *args, **kwargs):
        if rank == 0:
            raise RuntimeError('injected root calculator setup failure')
        return NoopCalculator()
    AutoNEBRunner._get_calculator = fail_on_root

calculation = {{
    'type': {workflow!r},
    'init_chain': 'chain.traj',
    'parallel': True,
    'neb_backend': 'atst',
    {autoneb_fields}
}}
try:
    run_workflow(
        {{'calculation': calculation,
          'calculator': {{'name': 'abacus', 'abacus': {{'parameters': {{}}}}}}}},
        RunOptions(),
    )
except WorkflowExecutionError:
    failed = 1
else:
    failed = 0

assert MPI.COMM_WORLD.allreduce(failed) == 2
"""
    completed = _run_mpi(
        [launcher, "-n", "2", sys.executable, "-c", smoke],
        cwd=tmp_path,
        environment=environment,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
