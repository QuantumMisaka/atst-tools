#!/usr/bin/env python3
"""Build and clean-install a wheel, then execute the public API release gates."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_IMPORT = (
    "from atst_tools.api import "
    "CCQNOptions, RunOptions, WorkflowResult, run_ccqn, run_workflow, validate_config"
)
H2_AU_API_EXAMPLE = ROOT / "examples" / "12_ccqn_H2-Au"
MPI_SMOKE_TIMEOUT_SECONDS = 60


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    environment_overrides: dict[str, str] | None = None,
) -> None:
    """Run one release-gate command and relay a useful failure."""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    if environment_overrides is not None:
        environment.update(environment_overrides)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd,
        env=environment,
        timeout=timeout,
    )
    if completed.returncode:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        raise subprocess.CalledProcessError(completed.returncode, command)


def _run_mpi_command(command: list[str], *, cwd: Path, timeout: int) -> None:
    """Run an MPI launcher in its own session and clean up all ranks on timeout."""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            process.communicate()
        raise
    if process.returncode:
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        raise subprocess.CalledProcessError(process.returncode, command)


def _wheel_from_args(wheel: str | None, temporary_root: Path) -> Path:
    """Return a supplied wheel or build one outside the repository tree."""
    if wheel is not None:
        candidate = Path(wheel).resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"Wheel not found: {candidate}")
        return candidate

    source_tree = temporary_root / "source"
    shutil.copytree(
        ROOT,
        source_tree,
        ignore=shutil.ignore_patterns(
            ".git", "build", "dist", ".pytest_cache", "__pycache__", "*.pyc"
        ),
    )
    wheel_dir = temporary_root / "wheel"
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(wheel_dir),
            str(source_tree),
        ]
    )
    wheels = sorted(wheel_dir.glob("atst_tools-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected exactly one ATST-Tools wheel, found: {wheels}")
    return wheels[0]


def _copy_h2_au_api_fixture(temporary_root: Path) -> Path:
    """Copy the maintained lightweight H2/Au API example into the test workspace."""
    fixture = temporary_root / "h2-au-api-example"
    shutil.copytree(H2_AU_API_EXAMPLE, fixture)
    (fixture / "sitecustomize.py").write_text(
        "\"\"\"Bound the installed-wheel CCQN example without replacing its API.\"\"\"\n"
        "\n"
        "from atst_tools.mep.ccqn import AbacusCCQN\n"
        "from atst_tools.utils.artifacts import write_artifact_manifest\n"
        "\n"
        "\n"
        "def _return_copied_atoms(self):\n"
        "    write_artifact_manifest(\n"
        "        self.calc_config.get('artifact_manifest', 'atst_artifacts.json'),\n"
        "        workflow='ccqn',\n"
        "        artifacts=[],\n"
        "        stages=[{'name': 'ccqn', 'status': 'complete'}],\n"
        "    )\n"
        "    return self.init_Atoms.copy()\n"
        "\n"
        "\n"
        "AbacusCCQN.run = _return_copied_atoms\n",
        encoding="utf-8",
    )
    return fixture


def _run_h2_au_api_example(python: Path, temporary_root: Path) -> None:
    """Run the real H2/Au API example with its narrow installed-wheel fixture."""
    fixture = _copy_h2_au_api_fixture(temporary_root)
    _run(
        [str(python), "ccqn_api_auto_modes.py"],
        cwd=fixture,
        environment_overrides={"PYTHONPATH": str(fixture)},
    )


def _run_mpi_smoke(python: Path, temporary_root: Path) -> None:
    """Run bounded two-rank public API and pre-run failure-synchronization gates."""
    launcher = shutil.which("mpiexec")
    if launcher is None:
        print("MPI smoke skipped: mpiexec is unavailable")
        return

    setup_chain = (
        "from ase import Atoms; from ase.io import write; "
        "write('mpi_failure_chain.traj', "
        "[Atoms('H', positions=[[float(index), 0, 0]]) for index in range(4)])"
    )
    _run([str(python), "-c", setup_chain], cwd=temporary_root)
    smoke = """
from mpi4py import MPI
from ase.calculators.calculator import Calculator
from atst_tools.api import RunOptions, run_workflow
from atst_tools.api.models import WorkflowExecutionError
from atst_tools.scripts import main
from atst_tools.mep import autoneb

rank = MPI.COMM_WORLD.rank


class NoopCalculator(Calculator):
    implemented_properties = []


def fail_endpoint_preparation(*args, **kwargs):
    raise RuntimeError('injected root endpoint failure')


def assert_failure(calculation, module):
    if rank == 0:
        module.ensure_neb_endpoint_results = fail_endpoint_preparation
    try:
        run_workflow(
            {
                'calculation': calculation,
                'calculator': {'name': 'abacus', 'abacus': {'parameters': {}}},
            },
            RunOptions(),
        )
    except WorkflowExecutionError:
        failed = 1
    else:
        failed = 0
    assert MPI.COMM_WORLD.allreduce(failed) == 2


assert_failure(
    {'type': 'neb', 'init_chain': 'mpi_failure_chain.traj', 'parallel': True}, main
)
assert_failure(
    {
        'type': 'autoneb',
        'init_chain': 'mpi_failure_chain.traj',
        'parallel': True,
        'n_simul': 2,
        'n_max': 3,
    },
    autoneb,
)


main.ensure_neb_endpoint_results = lambda *args, **kwargs: None
main._sync_parallel_endpoint_results = lambda images, *args: images
main._get_workflow_calculator = lambda *args, **kwargs: NoopCalculator()


class FakeNEB:
    def __init__(self, *args, **kwargs):
        pass


class RankLocalFailingOptimizer:
    def __init__(self, *args, **kwargs):
        if rank == 0:
            raise RuntimeError('injected rank-local optimizer construction failure')

    def run(self, *args, **kwargs):
        MPI.COMM_WORLD.Barrier()


main.AbacusNEB = FakeNEB
main.get_optimizer = lambda *args, **kwargs: RankLocalFailingOptimizer
try:
    run_workflow(
        {
            'calculation': {
                'type': 'neb',
                'init_chain': 'mpi_failure_chain.traj',
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
    _run_mpi_command(
        [launcher, "-n", "2", str(python), "-c", smoke],
        cwd=temporary_root,
        timeout=MPI_SMOKE_TIMEOUT_SECONDS,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the temporary wheel clean-install and public API release gates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        help="Existing wheel to verify; otherwise build a temporary wheel first.",
    )
    parser.add_argument(
        "--mpi-smoke",
        action="store_true",
        help="Run a bounded two-rank public API smoke test when mpiexec is available.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="atst-wheel-api-") as temporary:
        temporary_root = Path(temporary)
        wheel = _wheel_from_args(args.wheel, temporary_root)
        venv = temporary_root / "venv"
        _run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)])
        python = venv / "bin" / "python"
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(wheel),
            ]
        )
        import_check = (
            "import site; from pathlib import Path; "
            "import atst_tools; "
            "location = Path(atst_tools.__file__).resolve(); "
            "site_packages = tuple(Path(path).resolve() for path in site.getsitepackages()); "
            "assert any(location.is_relative_to(path) for path in site_packages), location; "
            f"assert not location.is_relative_to(Path({str(ROOT)!r}).resolve()), location; "
            f"{PUBLIC_IMPORT}"
        )
        _run([str(python), "-c", import_check], cwd=temporary_root)
        _run_h2_au_api_example(python, temporary_root)
        if args.mpi_smoke:
            _run_mpi_smoke(python, temporary_root)

    print("wheel clean-install public API gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
