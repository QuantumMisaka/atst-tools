#!/usr/bin/env python3
"""Build and clean-install a wheel, then execute the public API release gates."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
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
    """Run a bounded two-rank public API dry-run when an MPI launcher exists."""
    launcher = shutil.which("mpiexec")
    if launcher is None:
        print("MPI smoke skipped: mpiexec is unavailable")
        return

    smoke = (
        "from atst_tools.api import RunOptions, run_workflow; "
        "result = run_workflow("
        "{'calculation': {'type': 'relax', 'init_structure': 'initial.traj'}, "
        "'calculator': {'name': 'abacus', 'abacus': {'parameters': {}}}}, "
        "RunOptions(dry_run=True)); "
        "assert result.status == 'validated'"
    )
    _run(
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
