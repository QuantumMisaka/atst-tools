"""MPI helpers for ASE image-level parallel workflows."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any


_MPI_LAUNCH_ENV_KEYS = (
    "OMPI_COMM_WORLD_SIZE",
    "PMI_SIZE",
    "PMIX_RANK",
    "PMIX_NAMESPACE",
    "MPI_LOCALRANKID",
)


def mpi_launcher_detected(environ: dict[str, str] | None = None) -> bool:
    """Return whether the current process appears to be under an MPI launcher."""
    env = os.environ if environ is None else environ
    return any(key in env for key in _MPI_LAUNCH_ENV_KEYS)


def bootstrap_mpi_for_ase() -> None:
    """Import mpi4py before ASE resolves ``ase.parallel.world``.

    ASE selects its MPI backend lazily. It only uses mpi4py if the package is
    already imported when ``ase.parallel.world`` resolves its communicator.
    """
    if "mpi4py" in sys.modules or not mpi_launcher_detected():
        return
    try:
        importlib.import_module("mpi4py")
    except ImportError as exc:
        raise RuntimeError(
            "MPI-launched ATST-Tools requires mpi4py before ASE can expose "
            "image-level parallelism. Create an MPI-enabled environment with "
            "the same OpenMPI stack as ABACUS LTS 3.10.1, for example: "
            "module load abacus/LTSv3.10.1-sm70-auto; "
            "MPICC=\"$(which mpicc)\" python -m pip install --no-binary=mpi4py mpi4py"
        ) from exc


def get_ase_world() -> Any:
    """Return ASE's current MPI world communicator."""
    bootstrap_mpi_for_ase()
    from ase.parallel import world

    return world


def validate_image_parallel_world(world: Any, expected: int, context: str) -> None:
    """Validate the one-rank-per-active-image topology used by ATST-Tools."""
    if int(world.size) != int(expected):
        raise ValueError(
            f"Image-level parallelism requires MPI ranks ({world.size}) "
            f"to equal active interior images ({expected})."
            f" Context: {context}."
        )


def rank_owns_local_image(world: Any, local_image_index: int) -> bool:
    """Return whether the rank owns an active image in one-rank-per-image mode."""
    return int(world.rank) == int(local_image_index)
