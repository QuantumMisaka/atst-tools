"""Calculator factories for ATST-Tools workflows."""

from __future__ import annotations

import os
import re
import shlex
import logging
import math
from copy import deepcopy
from typing import Any, Dict

from ase.calculators.calculator import Calculator

from atst_tools.calculators.abacuslite_backend import Abacus, ATSTAbacusProfile, BACKEND_SOURCE
from atst_tools.calculators.constant_potential import (
    ConstantPotentialCalculator,
    fixed_hamiltonian_identity_for_config,
)
from atst_tools.calculators.dp import DeepPotentialFactory
from atst_tools.runtime import counters as runtime_counters
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


def _effective_omp(abacus_config: Dict[str, Any], omp_override: int | None) -> int:
    """Return the ABACUS OMP budget without clobbering a runtime thread budget.

    An explicit ``calculator.abacus.omp`` (argument or YAML) always wins.  When
    it is absent, an inherited ``OMP_NUM_THREADS`` (for example set by
    ``runtime.threads`` before the scientific stack was imported) is preserved;
    without one the historical default of 1 is written to the environment.
    """
    explicit = omp_override if omp_override is not None else abacus_config.get("omp")
    if explicit is not None:
        value = int(explicit)
        os.environ["OMP_NUM_THREADS"] = str(value)
        return value
    inherited = os.environ.get("OMP_NUM_THREADS", "").strip()
    if inherited:
        try:
            return int(inherited)
        except ValueError:
            pass
    os.environ["OMP_NUM_THREADS"] = "1"
    return 1


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
        omp = _effective_omp(abacus_config, omp)
        directory = directory or abacus_config.get("directory", ".")
        command = _build_abacus_command(abacus_config.get("command", "abacus"), mpi)
        version_command = abacus_config.get("version_command")

        profile = ATSTAbacusProfile(
            command=command,
            pseudo_dir=pseudo_dir,
            orbital_dir=orbital_dir,
            omp_num_threads=omp,
            version_command=version_command,
        )
        calculator = Abacus(directory=directory, profile=profile, **parameters)
        return runtime_counters.instrument_calculator(
            calculator,
            build_key="abacus.calculator_built",
            call_key="abacus.force_calls",
        )


class CalculatorFactory:
    """Unified factory for calculator construction."""

    @staticmethod
    def get_calculator(name: str, config: Dict[str, Any], **kwargs: Any) -> Calculator:
        name = name.lower()
        if name == "abacus":
            constant_potential = (
                config.get("calculator", {}).get("constant_potential")
                if isinstance(config.get("calculator", {}), dict)
                else None
            )
            if constant_potential is not None:
                return _constant_potential_calculator(config, constant_potential, kwargs)
            return AbacusFactory.get_calculator(config, **kwargs)
        if name in {"dp", "deepmd"}:
            calculator_section = config.get("calculator", {})
            if isinstance(calculator_section, dict) and calculator_section.get("constant_potential") is not None:
                raise ValueError("calculator.constant_potential requires calculator.name=abacus")
            return DeepPotentialFactory.get_calculator(config, **kwargs)
        raise ValueError(f"Unsupported calculator: {name}. Supported: 'abacus', 'dp'")


def _constant_potential_calculator(
    config: Dict[str, Any], cp_config: Dict[str, Any], kwargs: Dict[str, Any]
) -> ConstantPotentialCalculator:
    """Build one CP decorator around fresh, unwrapped ABACUS calculators."""
    supported_workflows = {"constant_potential", "relax", "neb"}
    workflow = config.get("calculation", {}).get("type") if isinstance(config.get("calculation"), dict) else None
    if workflow is not None and workflow not in supported_workflows:
        raise ValueError(
            "calculator.constant_potential is supported only for calculation.type in "
            f"{sorted(supported_workflows)}; got {workflow!r}"
        )
    options = dict(cp_config)
    energy_boundary = str(options.get("energy_boundary", "reference_fcp"))
    if energy_boundary not in {"reference_fcp", "compensated_gate"}:
        raise ValueError("calculator.constant_potential.energy_boundary is unsupported")
    if workflow in {"relax", "neb"} and energy_boundary != "compensated_gate":
        raise ValueError(
            "calculation.type=relax/neb requires energy_boundary=compensated_gate; "
            "reference_fcp is not a validated optimization boundary"
        )
    target = options.pop("potential_v", None)
    if energy_boundary == "compensated_gate":
        target = options.pop("target_mu_ev", None)
    else:
        options.pop("target_mu_ev", None)
    target_override = kwargs.pop("constant_potential_target", None)
    if target_override is not None:
        target = target_override
    if target is None:
        targets = options.pop(
            "target_mu_values_ev" if energy_boundary == "compensated_gate" else "potentials_v",
            None,
        )
        if not targets:
            raise ValueError("constant-potential calculator requires a target value")
        target = targets[0]
    else:
        options.pop("potentials_v", None)
        options.pop("target_mu_values_ev", None)

    required_fields = ("reference_electrons",)
    if energy_boundary == "reference_fcp":
        required_fields = ("work_ref", "work_ref_source", "reference_electrons")
    for required in required_fields:
        if options.get(required) is None:
            raise ValueError(f"calculator.constant_potential.{required} is required")

    root_directory = kwargs.get("directory")
    if root_directory is None:
        calculator_section = config.get("calculator", {})
        abacus_section = calculator_section.get("abacus", {}) if isinstance(calculator_section, dict) else {}
        root_directory = abacus_section.get("directory", ".") if isinstance(abacus_section, dict) else "."
    root_directory = str(root_directory)
    initial_override = kwargs.pop("constant_potential_initial", None)
    if initial_override is not None:
        initial_override = float(initial_override)

    # ``nupdown`` is the ABACUS control that activates the two-Fermi spin
    # state.  It is not a harmless optional switch for a CP boundary: even
    # nupdown=0 must be rejected so every profile has one auditable occupation
    # convention.  Check the merged top-level/parameters layout before any
    # backend directory is created; the runtime callback repeats this check for
    # direct calculator use and backend-reported parameters.
    abacus_section = _abacus_section(config)
    prepared_parameters = {
        key: value
        for key, value in abacus_section.items()
        if key not in _ABACUS_CONTROL_KEYS
    }
    raw_prepared = abacus_section.get("parameters", {})
    if isinstance(raw_prepared, dict):
        prepared_parameters.update(raw_prepared)
    if "nupdown" in prepared_parameters:
        raise ValueError(
            "calculator.constant_potential does not support explicit nupdown; "
            "use a common-Fermi nspin profile"
        )
    if prepared_parameters.get("two_fermi"):
        raise ValueError(
            "calculator.constant_potential does not support two_fermi"
        )

    # The callback closes over a copy of the original backend configuration and
    # mutates only the CP-owned evaluation copy.  This keeps the prepared INPUT
    # immutable and prevents recursively wrapping the inner backend.
    def inner_factory(nelec: float, directory: str):
        local_config = deepcopy(config)
        calculator_section = local_config.setdefault("calculator", {})
        abacus_section = calculator_section.setdefault("abacus", {})
        parameters = dict(abacus_section.get("parameters", {}))
        parameters["nelec"] = float(nelec)
        parameters.setdefault("calculation", "scf")
        parameters.setdefault("out_pot", 2)
        parameters.setdefault("cal_force", 1)
        if energy_boundary == "compensated_gate":
            # Compensation is evaluated from the same-run density.  Do not
            # overwrite gate/dipole geometry from the prepared INPUT; the
            # reader records and validates those actual parameters.
            parameters["out_chg"] = "1 12"
        abacus_section["parameters"] = parameters
        calculator_section.pop("constant_potential", None)
        local_kwargs = dict(kwargs)
        local_kwargs["directory"] = directory
        return AbacusFactory.get_calculator(local_config, **local_kwargs)

    if options.get("reference_electrons") is None:
        raise ValueError(
            "calculator.constant_potential.reference_electrons is required; "
            "the initial ABACUS nelec is not a model-zero-charge definition"
        )
    if initial_override is not None:
        options["initial_electrons"] = initial_override
    else:
        # N0 is a separately declared model-zero-charge reference.  The first
        # SCF guess follows the prepared ABACUS INPUT instead; silently using
        # N0 here would erase an explicit nelec/nelec_delta preparation choice.
        abacus_section = _abacus_section(config)
        prepared_parameters = (
            abacus_section.get("parameters", {}) if isinstance(abacus_section, dict) else {}
        )
        prepared_nelec = prepared_parameters.get("nelec") if isinstance(prepared_parameters, dict) else None
        if prepared_nelec is None and isinstance(abacus_section, dict):
            prepared_nelec = abacus_section.get("nelec")
        if prepared_nelec is not None:
            try:
                options["initial_electrons"] = float(prepared_nelec)
            except (TypeError, ValueError) as exc:
                raise ValueError("calculator.abacus.parameters.nelec must be finite when used as the CP initial guess") from exc
            if not math.isfinite(options["initial_electrons"]):
                raise ValueError("calculator.abacus.parameters.nelec must be finite when used as the CP initial guess")
    return ConstantPotentialCalculator(
        inner_factory=inner_factory,
        potential_v=None if energy_boundary == "compensated_gate" else float(target),
        target_mu_ev=float(target) if energy_boundary == "compensated_gate" else None,
        directory=root_directory,
        fixed_hamiltonian_identity=fixed_hamiltonian_identity_for_config(config),
        **options,
    )
