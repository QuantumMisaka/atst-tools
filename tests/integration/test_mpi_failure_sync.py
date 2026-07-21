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
def test_rank_local_endpoint_sync_read_error_releases_every_rank(
    tmp_path: Path, workflow: str
) -> None:
    """A bad synchronized endpoint file must fail before the following barrier."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec") or str(
        Path(sys.executable).with_name("mpiexec")
    )
    if not Path(launcher).is_file():
        pytest.skip("mpiexec is unavailable")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    sync_file = (
        ".atst_neb_endpoint_synced.traj"
        if workflow == "neb"
        else ".atst_autoneb_endpoint_synced.traj"
    )
    smoke = f"""
from mpi4py import MPI

rank = MPI.COMM_WORLD.rank
if {workflow!r} == 'neb':
    from atst_tools.scripts import main as runner_module
    world = runner_module.get_ase_world()
    runner_module.write = lambda *args, **kwargs: None
    def fail_sync_read(path, *args, **kwargs):
        if rank == 0 and str(path) == {sync_file!r}:
            raise OSError('injected synchronized endpoint read failure')
        return []
    runner_module.read = fail_sync_read
    try:
        runner_module._sync_parallel_endpoint_results([], world, lambda images: None)
    except Exception:
        failed = 1
    else:
        failed = 0
else:
    from atst_tools.mep import autoneb as runner_module
    from atst_tools.mep.autoneb import AutoNEBRunner
    world = runner_module.get_ase_world()
    runner_module.write = lambda *args, **kwargs: None
    def fail_sync_read(path, *args, **kwargs):
        if rank == 0 and str(path) == {sync_file!r}:
            raise OSError('injected synchronized endpoint read failure')
        return []
    runner_module.read = fail_sync_read
    runner_module.ensure_neb_endpoint_results = lambda *args, **kwargs: None
    runner = object.__new__(AutoNEBRunner)
    runner.world = world
    runner.parallel = True
    runner.init_chain = []
    runner.calc_config = {{}}
    runner._base_directory = lambda: 'unused'
    runner._get_calculator = lambda *args, **kwargs: None
    try:
        runner._prepare_endpoint_results()
    except Exception:
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
def test_rank_local_initial_chain_read_error_releases_every_rank(
    tmp_path: Path, workflow: str
) -> None:
    """Initial-chain read failures must synchronize before image collectives."""
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
    autoneb_fields = "'n_simul': 2, 'n_max': 4," if workflow == "autoneb" else ""
    smoke = f"""
from mpi4py import MPI
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import WorkflowExecutionError

rank = MPI.COMM_WORLD.rank
if {workflow!r} == 'neb':
    from atst_tools.scripts import main as runner_module
else:
    from atst_tools.mep import autoneb as runner_module

actual_read = runner_module.read
def fail_initial_chain_read(path, *args, **kwargs):
    if rank == 0 and str(path) == 'chain.traj':
        raise OSError('injected rank-local initial-chain read failure')
    return actual_read(path, *args, **kwargs)
runner_module.read = fail_initial_chain_read

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


def test_rank_local_manifest_inspection_error_releases_every_rank(tmp_path: Path) -> None:
    """API manifest inspection failures must synchronize before workflow dispatch."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec") or str(
        Path(sys.executable).with_name("mpiexec")
    )
    if not Path(launcher).is_file():
        pytest.skip("mpiexec is unavailable")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    smoke = """
from mpi4py import MPI
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api import services
from atst_tools.api.models import WorkflowExecutionError

rank = MPI.COMM_WORLD.rank
if rank == 0:
    services._manifest_signature = lambda path: (_ for _ in ()).throw(
        OSError('injected manifest inspection failure')
    )
services._dispatch_normalized = lambda *args, **kwargs: None

try:
    run_workflow(
        {'calculation': {'type': 'relax', 'init_structure': 'unused.traj'},
         'calculator': {'name': 'abacus', 'abacus': {'parameters': {}}}},
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


def test_rank_local_optimizer_construction_failure_releases_every_rank(
    tmp_path: Path,
) -> None:
    """A pre-run optimizer error must stop peers before their first collective."""
    if not _mpi_test_enabled():
        pytest.skip("set ATST_RUN_MPI_TESTS=1 to run real MPI launcher regressions")
    launcher = shutil.which("mpiexec") or str(Path(sys.executable).with_name("mpiexec"))
    if not Path(launcher).is_file():
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
    smoke = """
from mpi4py import MPI
from ase.calculators.calculator import Calculator
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import WorkflowExecutionError
from atst_tools.scripts import main

rank = MPI.COMM_WORLD.rank
main.ensure_neb_endpoint_results = lambda *args, **kwargs: None
main._sync_parallel_endpoint_results = lambda images, *args: images

class NoopCalculator(Calculator):
    implemented_properties = []

class FakeNEB:
    def __init__(self, *args, **kwargs):
        pass

class RankLocalFailingOptimizer:
    def __init__(self, *args, **kwargs):
        if rank == 0:
            raise RuntimeError('injected rank-local optimizer construction failure')

    def run(self, *args, **kwargs):
        MPI.COMM_WORLD.Barrier()

main._get_workflow_calculator = lambda *args, **kwargs: NoopCalculator()
main.AbacusNEB = FakeNEB
main.get_optimizer = lambda *args, **kwargs: RankLocalFailingOptimizer

try:
    run_workflow(
        {
            'calculation': {
                'type': 'neb',
                'init_chain': 'chain.traj',
                'parallel': True,
            },
            'calculator': {'name': 'abacus', 'abacus': {'parameters': {}}},
        },
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
