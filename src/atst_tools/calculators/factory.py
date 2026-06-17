"""Calculator factories for ATST-Tools workflows."""

from __future__ import annotations

import os
import re
import shlex
import logging
from typing import Any, Dict

from ase.calculators.calculator import Calculator

from atst_tools.calculators.abacuslite_backend import Abacus, ATSTAbacusProfile, BACKEND_SOURCE
from atst_tools.calculators.dp import DeepPotentialFactory
from atst_tools.utils.mpi import mpi_launcher_detected


_ABACUS_CONTROL_KEYS = {"command", "mpi", "omp", "directory", "parameters", "version_command"}
_MPI_ENV_KEYS_TO_CLEAR = (
    "OMPI_COMM_WORLD_SIZE",
    "OMPI_COMM_WORLD_RANK",
    "OMPI_COMM_WORLD_LOCAL_RANK",
    "OMPI_COMM_WORLD_LOCAL_SIZE",
    "OMPI_UNIVERSE_SIZE",
    "PMI_SIZE",
    "PMI_RANK",
    "PMIX_RANK",
    "PMIX_NAMESPACE",
    "MPI_LOCALRANKID",
)
LOGGER = logging.getLogger(__name__)
_ABACUS_BACKEND_LOGGED = False
_SHELL_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_MPI_LAUNCHERS = {"mpirun", "mpiexec", "srun"}


def _abacus_section(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return ABACUS calculator settings from the supported config layouts."""
    if "calculator" in config:
        return dict(config.get("calculator", {}).get("abacus", {}))
    if "abacus" in config:
        return dict(config.get("abacus", {}))
    return dict(config)


def _as_mp_kpts(kpts: Any) -> Any:
    if isinstance(kpts, list) and len(kpts) == 3:
        return {
            "mode": "mp-sampling",
            "nk": kpts,
            "gamma-centered": True,
            "kshift": [0, 0, 0],
        }
    return kpts


def _build_abacus_command(command: str, mpi: int) -> str:
    _validate_abacus_command(command)
    if "{mpi}" in command:
        return command.format(mpi=mpi)

    executable = _effective_abacus_executable(command)
    if mpi > 1 and executable not in _MPI_LAUNCHERS:
        return f"mpirun -np {mpi} {command}"
    if mpi == 1 and executable not in _MPI_LAUNCHERS and mpi_launcher_detected():
        clear_env = " ".join(f"-u {key}" for key in _MPI_ENV_KEYS_TO_CLEAR)
        return f"env {clear_env} {command or 'abacus'}"
    return command or "abacus"


def _effective_abacus_executable(command: str) -> str:
    parts = shlex.split(command)
    if not parts:
        return "abacus"
    if parts[0] != "env":
        return parts[0]

    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "--":
            index += 1
            break
        if token == "-u" and index + 1 < len(parts):
            index += 2
            continue
        if token.startswith("--unset="):
            index += 1
            continue
        if token in {"-i", "-0"}:
            index += 1
            continue
        if _SHELL_ASSIGNMENT_RE.match(token):
            index += 1
            continue
        break
    return parts[index] if index < len(parts) else "env"


def _validate_abacus_command(command: str) -> None:
    parts = shlex.split(command)
    if parts and _SHELL_ASSIGNMENT_RE.match(parts[0]):
        raise ValueError(
            "calculator.abacus.command is executed without a shell and cannot start with "
            f"a shell-style environment assignment ({parts[0]!r}). Use calculator.abacus.omp "
            "for OMP_NUM_THREADS, or wrap other environment variables with an explicit "
            "`env VAR=value ...` command or site wrapper."
        )


def _resolve_directory(path: str | None) -> str | None:
    if path is None:
        return None
    return os.path.abspath(os.path.expanduser(path))


class AbacusFactory:
    """Factory for creating ABACUS ASE calculators through abacuslite."""

    @staticmethod
    def _log_backend_source_once() -> None:
        global _ABACUS_BACKEND_LOGGED
        if not _ABACUS_BACKEND_LOGGED:
            LOGGER.info("Using %s abacuslite backend for ABACUS calculator.", BACKEND_SOURCE)
            _ABACUS_BACKEND_LOGGED = True

    @staticmethod
    def get_calculator(
        config: Dict[str, Any],
        directory: str | None = None,
        mpi: int | None = None,
        omp: int | None = None,
        **kwargs: Any,
    ) -> Calculator:
        AbacusFactory._log_backend_source_once()
        abacus_config = _abacus_section(config)
        raw_parameters = dict(abacus_config.get("parameters", {}))

        parameters = {
            key: value
            for key, value in abacus_config.items()
            if key not in _ABACUS_CONTROL_KEYS
        }
        parameters.update(raw_parameters)
        parameters.update(kwargs)

        if "pp" in parameters:
            parameters["pseudopotentials"] = parameters.pop("pp")
        if "basis" in parameters:
            parameters["basissets"] = parameters.pop("basis")
        if "basis_dir" in parameters:
            parameters["orbital_dir"] = parameters.pop("basis_dir")
        if "kpts" in parameters:
            parameters["kpts"] = _as_mp_kpts(parameters["kpts"])

        pseudo_dir = _resolve_directory(parameters.pop("pseudo_dir", None))
        orbital_dir = _resolve_directory(parameters.pop("orbital_dir", None))

        mpi = int(mpi if mpi is not None else abacus_config.get("mpi", 1))
        omp = int(omp if omp is not None else abacus_config.get("omp", 1))
        directory = directory or abacus_config.get("directory", ".")
        command = _build_abacus_command(abacus_config.get("command", "abacus"), mpi)
        version_command = abacus_config.get("version_command")

        os.environ["OMP_NUM_THREADS"] = str(omp)
        profile = ATSTAbacusProfile(
            command=command,
            pseudo_dir=pseudo_dir,
            orbital_dir=orbital_dir,
            omp_num_threads=omp,
            version_command=version_command,
        )
        return Abacus(directory=directory, profile=profile, **parameters)


class CalculatorFactory:
    """Unified factory for calculator construction."""

    @staticmethod
    def get_calculator(name: str, config: Dict[str, Any], **kwargs: Any) -> Calculator:
        name = name.lower()
        if name == "abacus":
            return AbacusFactory.get_calculator(config, **kwargs)
        if name in {"dp", "deepmd"}:
            return DeepPotentialFactory.get_calculator(config, **kwargs)
        raise ValueError(f"Unsupported calculator: {name}. Supported: 'abacus', 'dp'")
