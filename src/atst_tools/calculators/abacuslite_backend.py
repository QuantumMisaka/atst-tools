"""Resolve the ABACUS ASE backend used by ATST-Tools."""

from __future__ import annotations

import re
import shlex
from typing import Literal

from ase.calculators.genericfileio import read_stdout


BackendSource = Literal["external", "vendored"]


def _load_abacuslite_backend():
    try:
        from abacuslite import Abacus, AbacusProfile

        return Abacus, AbacusProfile, "external"
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite import Abacus, AbacusProfile

        return Abacus, AbacusProfile, "vendored"


Abacus, AbacusProfile, BACKEND_SOURCE = _load_abacuslite_backend()


def _default_version_command(command: str) -> list[str]:
    """Return the default bare ABACUS version-probe command."""
    parts = shlex.split(command)
    if not parts:
        return ["abacus", "--version"]
    executable = parts[-1] if parts[0] in {"mpirun", "mpiexec", "srun"} else parts[0]
    return [executable, "--version"]


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
    "ATSTAbacusProfile",
    "BACKEND_SOURCE",
    "BackendSource",
]
