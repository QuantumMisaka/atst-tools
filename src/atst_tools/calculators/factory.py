"""Calculator factories for ATST-Tools workflows."""

from __future__ import annotations

import os
import shlex
from typing import Any, Dict

from ase.calculators.calculator import Calculator

from atst_tools.calculators.abacuslite_backend import Abacus, AbacusProfile


_ABACUS_CONTROL_KEYS = {"command", "mpi", "omp", "directory", "parameters"}


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
    if "{mpi}" in command:
        return command.format(mpi=mpi)

    executable = shlex.split(command)[0] if command.strip() else "abacus"
    if mpi > 1 and executable not in {"mpirun", "mpiexec", "srun"}:
        return f"mpirun -np {mpi} {command}"
    return command or "abacus"


def _resolve_directory(path: str | None) -> str | None:
    if path is None:
        return None
    return os.path.abspath(os.path.expanduser(path))


class AbacusFactory:
    """Factory for creating ABACUS ASE calculators through abacuslite."""

    @staticmethod
    def get_calculator(
        config: Dict[str, Any],
        directory: str | None = None,
        mpi: int | None = None,
        omp: int | None = None,
        **kwargs: Any,
    ) -> Calculator:
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

        os.environ["OMP_NUM_THREADS"] = str(omp)
        profile = AbacusProfile(
            command=command,
            pseudo_dir=pseudo_dir,
            orbital_dir=orbital_dir,
            omp_num_threads=omp,
        )
        return Abacus(directory=directory, profile=profile, **parameters)


class DeepPotentialFactory:
    """Factory for creating DeepMD ASE calculators with optional sharing."""

    _instances: Dict[str, Calculator] = {}

    @staticmethod
    def get_calculator(
        config: Dict[str, Any],
        shared: bool = True,
        **kwargs: Any,
    ) -> Calculator:
        try:
            from deepmd.calculator import DP
        except ImportError as exc:
            raise ImportError(
                "deepmd-kit is not installed. Install it to use the DP calculator."
            ) from exc

        dp_params = dict(config.get("calculator", {}).get("dp", {}))
        if not dp_params and "parameters" in config:
            dp_params = dict(config["parameters"])
        dp_params.update(kwargs)

        model_file = dp_params.get("model", "frozen_model.pb")
        type_map = dp_params.get("type_map")
        model_key = os.path.abspath(model_file)

        if shared and model_key in DeepPotentialFactory._instances:
            return DeepPotentialFactory._instances[model_key]

        calc = DP(model=model_file, type_map=type_map)
        if shared:
            DeepPotentialFactory._instances[model_key] = calc
        return calc


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
