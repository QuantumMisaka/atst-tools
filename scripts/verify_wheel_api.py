#!/usr/bin/env python3
"""Build and clean-install a wheel, then check the six stable API imports."""

from __future__ import annotations

import argparse
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


def _run(command: list[str]) -> None:
    """Run one release-gate command and relay a useful failure."""
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
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


def main(argv: list[str] | None = None) -> int:
    """Run the temporary wheel clean-install and public import verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        help="Existing wheel to verify; otherwise build a temporary wheel first.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="atst-wheel-api-") as temporary:
        temporary_root = Path(temporary)
        wheel = _wheel_from_args(args.wheel, temporary_root)
        venv = temporary_root / "venv"
        _run([sys.executable, "-m", "venv", str(venv)])
        python = venv / "bin" / "python"
        _run([str(python), "-m", "pip", "install", str(wheel)])
        _run([str(python), "-c", PUBLIC_IMPORT])

    print("wheel clean-install public API import passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
