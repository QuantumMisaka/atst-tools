"""Resolve the ABACUS ASE backend used by ATST-Tools."""

from __future__ import annotations

import re
import shlex
from importlib.util import find_spec
from pathlib import Path
from typing import Literal

from ase.calculators.genericfileio import read_stdout


BackendSource = Literal["external"]


def _load_abacuslite_backend():
    if find_spec("abacuslite") is None:
        raise ModuleNotFoundError(
            "abacuslite is required by ATST-Tools; install abacuslite>=1.2.1,<2",
            name="abacuslite",
        )
    from abacuslite import Abacus, AbacusProfile, AbacusSocketIO

    return Abacus, AbacusProfile, AbacusSocketIO, "external"


Abacus, AbacusProfile, AbacusSocketIO, BACKEND_SOURCE = _load_abacuslite_backend()


def socket_input_parameters(parameters: dict) -> dict:
    """Apply the backend's socket-mode INPUT rules to ABACUS parameters.

    Delegates to ``AbacusSocketIO._socket_inp`` so prepared INPUT files match
    what the socket calculator writes: ``socket_driver = 1``,
    ``calculation = scf`` and normalized ``cal_force``/``cal_stress``.

    Args:
        parameters: ABACUS INPUT parameters.

    Returns:
        A new parameter mapping with socket-mode values applied.

    Raises:
        ValueError: If ``calculation`` is not ``scf`` or a ``cal_*`` flag is
            not a boolean value.
    """
    return AbacusSocketIO._socket_inp(parameters)


def import_generalio():
    """Return general I/O from the installed calculator backend."""
    from abacuslite.io import generalio
    return generalio


def import_latestio():
    """Return current-output readers from the installed backend."""
    from abacuslite.io import latestio
    return latestio


def import_legacyio():
    """Return legacy-output readers from the installed backend."""
    from abacuslite.io import legacyio
    return legacyio


def import_ksampling():
    """Return K-point conversion helpers from the installed backend."""
    from abacuslite.utils import ksampling
    return ksampling


def _skip_env_prefix(parts: list[str], index: int) -> int:
    """Skip explicit env wrappers without changing the calculation command."""
    while index < len(parts) and Path(parts[index]).name == "env":
        index += 1
        while index < len(parts):
            if parts[index] == "--":
                index += 1
                break
            if parts[index] in {"-u", "--unset"}:
                index += 2
                continue
            if parts[index].startswith("-"):
                index += 1
                continue
            if "=" in parts[index]:
                index += 1
                continue
            break
    return index


def _command_executable(command: str) -> str:
    """Find a bare command's executable or retain legacy MPI-last behavior."""
    parts = shlex.split(command)
    if not parts:
        return "abacus"
    index = _skip_env_prefix(parts, 0)
    if index >= len(parts):
        return "abacus"
    if Path(parts[index]).name in {"mpirun", "mpiexec", "srun"}:
        return parts[-1]
    return parts[index]


def _default_version_command(command: str) -> list[str]:
    """Return the default bare ABACUS version-probe command."""
    return [_command_executable(command), "--version"]


class ATSTAbacusProfile(AbacusProfile):
    """ABACUS profile with ATST-managed version probing.

    The run command may be MPI-wrapped for calculations, but version probing is
    a lightweight environment check and defaults to a bare executable call.
    """

    def __init__(self, *args, version_command: str | None = None, **kwargs):
        """Initialize an ATST ABACUS profile.

        Args:
            *args: Positional arguments passed to abacuslite's profile.
            version_command: Optional full command used for version probing.
            **kwargs: Keyword arguments passed to abacuslite's profile.
        """
        super().__init__(*args, **kwargs)
        self.version_command = version_command

    @staticmethod
    def parse_version(stdout: str) -> str:
        """Parse ABACUS version output from legacy and LTS banner formats."""
        for pattern in (r"ABACUS version (\S+)", r"ABACUS\s+(v\S+)"):
            match = re.search(pattern, stdout)
            if match is not None:
                return match.group(1)
        raise RuntimeError(f"Could not parse ABACUS version from output: {stdout!r}")

    def version(self) -> str:
        """Return the ABACUS version using ATST's version-probe command."""
        command = (
            shlex.split(self.version_command)
            if self.version_command
            else _default_version_command(self.command)
        )
        return self.parse_version(read_stdout(command))


__all__ = [
    "Abacus",
    "AbacusProfile",
    "AbacusSocketIO",
    "ATSTAbacusProfile",
    "BACKEND_SOURCE",
    "BackendSource",
]
