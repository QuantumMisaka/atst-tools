"""ASE calculator decorator for fixed-electrode-potential evaluations.

The decorator owns the electronic-number loop.  Its wrapped calculator is
rebuilt for every candidate electron count through an explicit factory
callback, which keeps the backend evaluation identity ``(R, cell, N_e,
fixed_settings)`` and prevents recursive CP wrapping.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
from ase.calculators.calculator import Calculator, all_changes

from atst_tools.utils.electrochemistry import chebyshev_derivative, surface_area


_ENERGY_BOUNDARIES = {"reference_fcp", "compensated_gate"}


class ConstantPotentialError(RuntimeError):
    """Base exception for constant-potential evaluation failures."""


class ConstantPotentialEvaluationError(ConstantPotentialError):
    """Raised when one fixed-electron backend evaluation is unusable."""


class ConstantPotentialConvergenceError(ConstantPotentialError):
    """Raised when the potential tolerance cannot be reached."""


_FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_VACUUM_LINE_RE = re.compile(
    r"^\s*The\s+vacuum\s+level\s+is\s+(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s+eV\s*$",
    re.IGNORECASE,
)
_VACUUM_KEYS = ("vacuum_level", "vacuum", "Vvac", "v_vac", "electrostatic_potential_vacuum")
_FERMI_KEYS = ("efermi", "fermi", "fermi_level", "E_Fermi")
_SCF_SUCCESS_MARKER = re.compile(r"charge\s+density\s+convergence\s+is\s+achieved", re.IGNORECASE)
_SCF_FAILURE_MARKER = re.compile(
    r"charge\s+density\s+convergence\s+(?:is\s+)?(?:not|has\s+not)\s+achieved|"
    r"scf\s+(?:did\s+not|not)\s+converge",
    re.IGNORECASE,
)

CP_FACTS_INFO_KEY = "atst_constant_potential_facts"
CP_IDENTITY_INFO_KEY = "atst_constant_potential_identity"
CP_FACTS_SCHEMA = "atst-constant-potential-facts-v1"
_ABACUS_CONTROL_KEYS = {"command", "mpi", "omp", "directory", "parameters", "version_command"}
_FIXED_BOUNDARY_KEYS = (
    "gate_flag",
    "imp_sol",
    "efield_dir",
    "zgate",
    "block",
    "block_down",
    "block_up",
    "block_height",
    "efield_flag",
    "dip_cor_flag",
    "efield_amp",
    "efield_pos_max",
    "efield_pos_dec",
    "out_chg",
    "out_pot",
    "cal_force",
    "nspin",
    "two_fermi",
    "nupdown",
)
_CP_FACT_KEYS = (
    "energy",
    "free_energy",
    "raw_energy",
    "raw_free_energy",
    "efermi",
    "vacuum_level",
    "fermishift",
    "energy_boundary",
    "profile_status",
    "boundary_parameters",
    "compensation",
    "mu_calc",
    "mu_target",
    "potential_calc",
    "potential_target",
    "residual_mu",
    "residual_v",
    "omega_correction",
    "nelec",
    "reference_electrons",
    "delta_nelec",
    "forces",
    "scf_converged",
    "cp_converged",
    "cp_iterations",
    "cp_history",
)
_CP_REQUIRED_FACT_KEYS = frozenset(_CP_FACT_KEYS)
_CP_REQUIRED_IDENTITY_KEYS = frozenset(
    {
        "energy_boundary",
        "potential_v",
        "target_mu_ev",
        "reference_electrode",
        "work_ref",
        "work_ref_source",
        "reference_pH",
        "temperature_K",
        "reference_electrons",
        "boundary_parameters",
        "energy_definition",
        "calculator",
    }
)
_CP_REQUIRED_FINITE_FACT_KEYS = frozenset(
    {
        "energy",
        "free_energy",
        "raw_energy",
        "raw_free_energy",
        "efermi",
        "mu_calc",
        "mu_target",
        "residual_mu",
        "residual_v",
        "omega_correction",
        "nelec",
        "reference_electrons",
        "delta_nelec",
    }
)


def _finite(value: Any, name: str) -> float:
    """Convert a scalar to a finite float."""
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConstantPotentialEvaluationError(f"{name} must be a finite number") from exc
    if not np.isfinite(result):
        raise ConstantPotentialEvaluationError(f"{name} must be a finite number")
    return result


def _jsonable(value: Any) -> Any:
    """Convert common ASE/NumPy values into JSON-safe values."""
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def constant_potential_geometry_fingerprint(atoms: Any) -> str:
    """Return a deterministic fingerprint of the ASE geometry and cell."""
    digest = hashlib.sha256()
    numbers = np.asarray(atoms.numbers, dtype="<i8")
    positions = np.asarray(atoms.positions, dtype="<f8")
    cell = np.asarray(atoms.cell.array, dtype="<f8")
    pbc = np.asarray(atoms.pbc, dtype=np.uint8)
    for value in (numbers, positions, cell, pbc):
        digest.update(np.asarray(value).tobytes(order="C"))
    return digest.hexdigest()


def _sha256_file(path: Path) -> str | None:
    """Hash one fixed input asset, preserving missing assets explicitly."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def _resolve_fixed_asset(value: Any, directory: Any, base: Path) -> Path:
    """Resolve an ABACUS asset using the calculator's cwd-relative rules."""
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        root = Path(str(directory)).expanduser() if directory else base
        if not root.is_absolute():
            root = base / root
        path = root / path
    return path.resolve()


def _abacus_parameters_from_config(config: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Return the CP and merged ABACUS parameter mappings from common layouts."""
    if not isinstance(config, Mapping):
        return {}, {}
    calculator = config.get("calculator")
    if isinstance(calculator, Mapping):
        cp = calculator.get("constant_potential")
        abacus = calculator.get("abacus")
    else:
        cp = config.get("constant_potential")
        abacus = config.get("abacus")
    cp_mapping = cp if isinstance(cp, Mapping) else {}
    abacus_mapping = abacus if isinstance(abacus, Mapping) else {}
    parameters = {
        key: value for key, value in abacus_mapping.items() if key not in _ABACUS_CONTROL_KEYS
    }
    raw_parameters = abacus_mapping.get("parameters", {})
    if isinstance(raw_parameters, Mapping):
        parameters.update(dict(raw_parameters))
    if "pp" in parameters:
        parameters["pseudopotentials"] = parameters["pp"]
    if "basis" in parameters:
        parameters["basissets"] = parameters["basis"]
    if "basis_dir" in parameters:
        parameters["orbital_dir"] = parameters["basis_dir"]
    return cp_mapping, parameters


def fixed_hamiltonian_identity_for_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Build the fixed Hamiltonian identity used by CP endpoint handoff.

    The electron count is intentionally omitted because it changes inside the
    CP Newton loop.  All other merged ABACUS settings are retained alongside
    content hashes for pseudopotentials, orbitals, and explicit KPT files.
    Resolved paths are retained only as provenance; endpoint matching uses the
    species/kind/content digest and therefore survives a moved run directory.
    Boundary/output defaults are the same defaults injected by the CP factory.
    """
    cp, parameters = _abacus_parameters_from_config(config)
    has_backend_context = isinstance(config.get("calculator"), Mapping) or isinstance(config.get("abacus"), Mapping)
    if not has_backend_context:
        return {}
    boundary = str(cp.get("energy_boundary", "reference_fcp"))
    parameters = dict(parameters)
    parameters.setdefault("out_pot", 2)
    parameters.setdefault("cal_force", 1)
    if boundary == "compensated_gate":
        parameters["out_chg"] = "1 12"

    boundary_parameters = {
        key: _jsonable(parameters[key]) for key in _FIXED_BOUNDARY_KEYS if key in parameters
    }
    fixed_parameters = {
        str(key): _jsonable(value)
        for key, value in parameters.items()
        if key not in {"nelec", "pseudopotentials", "basissets", "pp", "basis", "pseudo_dir", "orbital_dir", "basis_dir", "kpt_file", "KPT"}
    }
    base = Path.cwd().resolve()

    def asset_records(mapping: Any, directory: Any, kind: str) -> list[dict[str, Any]]:
        if not isinstance(mapping, Mapping):
            return []
        records = []
        for species, filename in sorted(mapping.items(), key=lambda item: str(item[0])):
            path = _resolve_fixed_asset(filename, directory, base)
            digest = _sha256_file(path)
            if digest is None:
                raise ValueError(f"fixed {kind} asset is missing or unreadable: {path}")
            records.append(
                {
                    "kind": kind,
                    "species": str(species),
                    "sha256": digest,
                    "provenance": {
                        "configured_name": str(filename),
                        "path": str(path),
                    },
                }
            )
        return records

    assets: dict[str, Any] = {
        "pseudopotentials": asset_records(
            parameters.get("pseudopotentials"), parameters.get("pseudo_dir"), "pseudopotential"
        ),
        "orbitals": asset_records(
            parameters.get("basissets"), parameters.get("orbital_dir"), "orbital"
        ),
        "kpoints": {"specification": _jsonable(parameters.get("kpts", [1, 1, 1]))},
    }
    kpt_file = parameters.get("kpt_file", parameters.get("KPT"))
    if kpt_file is not None:
        path = _resolve_fixed_asset(kpt_file, None, base)
        digest = _sha256_file(path)
        if digest is None:
            raise ValueError(f"fixed k-point asset is missing or unreadable: {path}")
        assets["kpoints"]["file"] = {
            "sha256": digest,
            "provenance": {
                "configured_name": str(kpt_file),
                "path": str(path),
            },
        }
    return {
        "boundary_parameters": boundary_parameters,
        "parameters": fixed_parameters,
        "assets": assets,
    }


def _mapping_contains(actual: Any, expected: Any) -> bool:
    """Compare an expected identity as a recursive subset of actual facts."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(
            key == "provenance"
            or (key in actual and _mapping_contains(actual[key], value))
            for key, value in expected.items()
        )
    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
            return False
        return all(_mapping_contains(item, value) for item, value in zip(actual, expected))
    return actual == expected


def clear_constant_potential_facts(atoms: Any) -> None:
    """Remove CP facts and identity markers from an ASE atoms object."""
    if atoms is None or not hasattr(atoms, "info"):
        return
    atoms.info.pop(CP_FACTS_INFO_KEY, None)
    atoms.info.pop(CP_IDENTITY_INFO_KEY, None)


def _same_finite_float(left: Any, right: Any) -> bool:
    """Compare two serialized scalar values without accepting non-finite data."""
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(left_value) or not np.isfinite(right_value):
        return False
    return bool(np.isclose(left_value, right_value, rtol=1e-10, atol=1e-12))


def _constant_potential_facts_error(
    atoms: Any, payload: Any, *, require_duplicate_identity: bool = True
) -> str | None:
    """Return a fail-closed validation error for one durable CP envelope."""
    if atoms is None or not hasattr(atoms, "info"):
        return "constant-potential facts require an ASE atoms object"
    if not isinstance(payload, Mapping):
        return "constant-potential facts envelope is not a mapping"
    if payload.get("schema") != CP_FACTS_SCHEMA or payload.get("workflow") != "constant_potential":
        return "constant-potential facts schema or workflow is unsupported"
    if payload.get("status") != "complete" or payload.get("cp_converged") is not True:
        return "constant-potential facts are not a complete converged result"
    try:
        geometry_fingerprint = constant_potential_geometry_fingerprint(atoms)
    except (AttributeError, TypeError, ValueError):
        return "constant-potential facts geometry cannot be fingerprinted"
    if payload.get("geometry_fingerprint") != geometry_fingerprint:
        return "constant-potential facts geometry fingerprint does not match"

    identity = payload.get("identity")
    facts = payload.get("facts")
    if not isinstance(identity, Mapping):
        return "constant-potential facts identity is missing or malformed"
    if not isinstance(facts, Mapping):
        return "constant-potential facts facts mapping is missing or malformed"
    duplicate_identity = atoms.info.get(CP_IDENTITY_INFO_KEY)
    if require_duplicate_identity and (
        not isinstance(duplicate_identity, Mapping)
        or _jsonable(duplicate_identity) != _jsonable(identity)
    ):
        return "constant-potential facts duplicate identity is missing or inconsistent"

    missing_identity = sorted(key for key in _CP_REQUIRED_IDENTITY_KEYS if key not in identity)
    if missing_identity:
        return f"constant-potential facts identity is missing required fields: {', '.join(missing_identity)}"
    missing_facts = sorted(key for key in _CP_REQUIRED_FACT_KEYS if key not in facts)
    if missing_facts:
        return f"constant-potential facts are missing required fields: {', '.join(missing_facts)}"

    if facts["cp_converged"] is not True or facts["scf_converged"] is not True:
        return "constant-potential facts require cp_converged=true and scf_converged=true"
    if not isinstance(facts["energy_boundary"], str) or facts["energy_boundary"] not in _ENERGY_BOUNDARIES:
        return "constant-potential facts energy_boundary is unsupported"
    if facts["energy_boundary"] != identity["energy_boundary"]:
        return "constant-potential facts boundary disagrees with identity"
    if not isinstance(facts["profile_status"], str) or not facts["profile_status"]:
        return "constant-potential facts profile_status is malformed"
    if not isinstance(facts["boundary_parameters"], Mapping):
        return "constant-potential facts boundary_parameters is malformed"
    if not isinstance(identity["boundary_parameters"], Mapping):
        return "constant-potential facts identity boundary_parameters is malformed"
    if not _mapping_contains(identity["boundary_parameters"], facts["boundary_parameters"]):
        return "constant-potential facts boundary parameters disagree with identity"
    if not isinstance(identity["calculator"], str) or not identity["calculator"]:
        return "constant-potential facts identity calculator is malformed"
    expected_definition = (
        "omega_compensated_gate"
        if facts["energy_boundary"] == "compensated_gate"
        else "omega_aligned"
    )
    if identity["energy_definition"] != expected_definition:
        return "constant-potential facts identity energy definition is inconsistent"

    for key in _CP_REQUIRED_FINITE_FACT_KEYS:
        if not _same_finite_float(facts[key], facts[key]):
            return f"constant-potential facts {key} is not finite"
    if not _same_finite_float(identity["reference_electrons"], identity["reference_electrons"]):
        return "constant-potential facts identity reference_electrons is not finite"
    if not _same_finite_float(facts["reference_electrons"], identity["reference_electrons"]):
        return "constant-potential facts reference_electrons disagrees with identity"
    if not _same_finite_float(
        facts["delta_nelec"], float(facts["nelec"]) - float(facts["reference_electrons"])
    ):
        return "constant-potential facts delta_nelec is inconsistent with electron counts"
    if not _same_finite_float(
        facts["residual_mu"], float(facts["mu_calc"]) - float(facts["mu_target"])
    ):
        return "constant-potential facts residual_mu is inconsistent with mu_calc and mu_target"
    if not _same_finite_float(
        facts["energy"], float(facts["raw_energy"]) + float(facts["omega_correction"])
    ) or not _same_finite_float(
        facts["free_energy"], float(facts["raw_free_energy"]) + float(facts["omega_correction"])
    ):
        return "constant-potential facts energy correction is inconsistent"

    if facts["energy_boundary"] == "compensated_gate":
        if not _same_finite_float(identity["target_mu_ev"], facts["mu_target"]):
            return "constant-potential facts mu_target disagrees with identity"
        if facts["vacuum_level"] is not None or facts["fermishift"] is not None:
            return "constant-potential compensated-gate facts must not contain a vacuum reference"
        if facts["potential_calc"] is not None or facts["potential_target"] is not None:
            return "constant-potential compensated-gate facts must not contain a voltage target"
        if not _same_finite_float(facts["residual_v"], facts["residual_mu"]):
            return "constant-potential compensated-gate residual_v must equal residual_mu"
        compensation = facts["compensation"]
        if not isinstance(compensation, Mapping):
            return "constant-potential compensated-gate compensation evidence is missing"
        required_compensation = (
            "boundary",
            "gate_derivative_ev",
            "dipole_derivative_ev",
            "compensation_derivative_ev",
            "integrated_electrons",
            "density_electron_error",
            "ionic_valence_electrons",
            "total_dipole_ry_au",
            "density_precision",
            "density_electron_tolerance",
        )
        missing_compensation = [
            key for key in required_compensation if key not in compensation
        ]
        if missing_compensation:
            return (
                "constant-potential compensated-gate compensation is missing required fields: "
                + ", ".join(missing_compensation)
            )
        if compensation["boundary"] != "compensated_gate":
            return "constant-potential compensation boundary is inconsistent"
        for key in (
            "gate_derivative_ev",
            "dipole_derivative_ev",
            "compensation_derivative_ev",
            "integrated_electrons",
            "density_electron_error",
            "ionic_valence_electrons",
            "total_dipole_ry_au",
            "density_electron_tolerance",
        ):
            if not _same_finite_float(compensation[key], compensation[key]):
                return f"constant-potential compensation {key} is not finite"
        try:
            density_precision = float(compensation["density_precision"])
        except (TypeError, ValueError):
            return "constant-potential compensation density_precision is malformed"
        if not np.isfinite(density_precision) or not density_precision.is_integer() or density_precision < 10:
            return "constant-potential compensation density_precision is invalid"
        if float(compensation["density_electron_tolerance"]) <= 0:
            return "constant-potential compensation density_electron_tolerance is invalid"
        if not _same_finite_float(
            compensation["compensation_derivative_ev"],
            float(compensation["gate_derivative_ev"])
            + float(compensation["dipole_derivative_ev"]),
        ):
            return "constant-potential compensation derivative is inconsistent"
        if not _same_finite_float(
            facts["mu_calc"],
            float(facts["efermi"]) + float(compensation["compensation_derivative_ev"]),
        ):
            return "constant-potential compensated chemical potential is inconsistent"
        if not _same_finite_float(
            facts["omega_correction"], -float(facts["mu_target"]) * float(facts["delta_nelec"])
        ):
            return "constant-potential compensated grand-potential correction is inconsistent"
        # Match the same PP-valence tolerance used by read_gate_compensation.
        if abs(float(compensation["ionic_valence_electrons"]) - float(facts["reference_electrons"])) > 1e-6:
            return "constant-potential compensation ionic valence disagrees with reference electrons"
        if not _same_finite_float(compensation["density_electron_error"],
                                  float(compensation["integrated_electrons"])
                                  - float(facts["nelec"])):
            return "constant-potential compensation density error is inconsistent"
        if abs(float(compensation["density_electron_error"])) > float(
            compensation["density_electron_tolerance"]
        ):
            return "constant-potential compensation density error exceeds tolerance"
    else:
        for key in ("vacuum_level", "fermishift", "potential_calc", "potential_target"):
            if not _same_finite_float(facts[key], facts[key]):
                return f"constant-potential reference fact {key} is not finite"
        if not _same_finite_float(facts["fermishift"], -float(facts["vacuum_level"])):
            return "constant-potential reference fermishift is inconsistent with vacuum_level"
        if not _same_finite_float(
            facts["mu_calc"], float(facts["efermi"]) + float(facts["fermishift"])
        ):
            return "constant-potential reference chemical potential is inconsistent"
        if not _same_finite_float(
            facts["omega_correction"],
            (float(facts["fermishift"]) - float(facts["mu_target"])) * float(facts["delta_nelec"]),
        ):
            return "constant-potential reference grand-potential correction is inconsistent"
        if not _same_finite_float(identity["potential_v"], facts["potential_target"]):
            return "constant-potential facts potential_target disagrees with identity"
        try:
            expected_mu = -(
                float(identity["potential_v"]) + float(identity["work_ref"])
            )
        except (TypeError, ValueError):
            return "constant-potential reference identity work_ref is malformed"
        if not _same_finite_float(facts["mu_target"], expected_mu):
            return "constant-potential facts mu_target disagrees with identity"
        try:
            expected_residual_v = float(facts["potential_calc"]) - float(facts["potential_target"])
        except (TypeError, ValueError):
            return "constant-potential reference potential values are malformed"
        if not _same_finite_float(facts["residual_v"], expected_residual_v):
            return "constant-potential facts residual_v is inconsistent with voltage values"
    try:
        forces = np.asarray(facts["forces"], dtype=float)
    except (TypeError, ValueError):
        return "constant-potential facts forces are malformed"
    if forces.shape != (len(atoms), 3) or not np.all(np.isfinite(forces)):
        return "constant-potential facts forces have invalid shape or values"
    try:
        iterations = float(facts["cp_iterations"])
    except (TypeError, ValueError):
        return "constant-potential facts cp_iterations is malformed"
    if not np.isfinite(iterations) or iterations < 0 or not iterations.is_integer():
        return "constant-potential facts cp_iterations is invalid"
    if not isinstance(facts["cp_history"], list) or not facts["cp_history"]:
        return "constant-potential facts cp_history is missing or empty"
    try:
        json.dumps(_jsonable(payload), allow_nan=False)
    except (TypeError, ValueError):
        return "constant-potential facts are not finite JSON"
    return None


def publish_constant_potential_facts(
    atoms: Any, results: Mapping[str, Any], identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist one validated CP result envelope on the evaluated atoms."""
    if not isinstance(results, Mapping) or not isinstance(identity, Mapping):
        raise ConstantPotentialEvaluationError("constant-potential facts require result and identity mappings")
    facts = {key: _jsonable(results[key]) for key in _CP_FACT_KEYS if key in results}
    payload = {
        "schema": CP_FACTS_SCHEMA,
        "workflow": "constant_potential",
        "status": "complete",
        "geometry_fingerprint": constant_potential_geometry_fingerprint(atoms),
        "identity": _jsonable(identity),
        "facts": facts,
        "cp_converged": facts.get("cp_converged") is True,
    }
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConstantPotentialEvaluationError("constant-potential facts are not finite JSON") from exc
    validation_error = _constant_potential_facts_error(
        atoms, payload, require_duplicate_identity=False
    )
    if validation_error is not None:
        raise ConstantPotentialEvaluationError(validation_error)
    atoms.info[CP_FACTS_INFO_KEY] = payload
    atoms.info[CP_IDENTITY_INFO_KEY] = copy.deepcopy(payload["identity"])
    return copy.deepcopy(payload)


def read_constant_potential_facts(atoms: Any) -> dict[str, Any] | None:
    """Read and validate CP facts persisted on an ASE atoms object."""
    if atoms is None or not hasattr(atoms, "info"):
        return None
    payload = atoms.info.get(CP_FACTS_INFO_KEY)
    if _constant_potential_facts_error(atoms, payload) is not None:
        return None
    return copy.deepcopy(dict(payload))


def constant_potential_restart_initial_electrons(
    atoms: Any,
    expected_identity: Mapping[str, Any],
    potential_tolerance_v: float,
    *,
    allow_recompute: bool = False,
) -> float | None:
    """Return the last evaluated electron count for a matching CP frame.

    A structure trajectory is a nuclear checkpoint; it does not serialize the
    calculator's custom result fields.  This helper consumes the durable facts
    envelope copied into ``Atoms.info`` and therefore only returns an electron
    count after validating the complete SCF/CP result, geometry, fixed
    Hamiltonian identity, target, and current residual tolerance.  A missing or
    stale envelope may be treated as an explicit recomputation when
    ``allow_recompute`` is true; otherwise restart fails closed.

    The returned value is the completed evaluation's ``nelec``.  It never uses
    a Newton candidate or a partially written history record.
    """
    if not isinstance(expected_identity, Mapping):
        raise ConstantPotentialError("constant-potential restart identity is missing or malformed")
    try:
        tolerance = float(potential_tolerance_v)
    except (TypeError, ValueError) as exc:
        raise ConstantPotentialError("constant-potential restart tolerance is malformed") from exc
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ConstantPotentialError("constant-potential restart tolerance must be positive and finite")

    has_payload = atoms is not None and hasattr(atoms, "info") and CP_FACTS_INFO_KEY in atoms.info
    if not has_payload:
        if allow_recompute:
            return None
        raise ConstantPotentialError("constant-potential restart checkpoint is missing")
    raw_payload = atoms.info.get(CP_FACTS_INFO_KEY)
    validation_error = _constant_potential_facts_error(atoms, raw_payload)
    payload = read_constant_potential_facts(atoms)
    if validation_error is not None or payload is None:
        if allow_recompute:
            return None
        detail = validation_error or "constant-potential facts could not be read"
        raise ConstantPotentialError(
            f"constant-potential restart checkpoint is stale or malformed: {detail}"
        )

    identity = payload.get("identity")
    if not isinstance(identity, Mapping) or not _mapping_contains(identity, expected_identity):
        if allow_recompute:
            return None
        raise ConstantPotentialError(
            "constant-potential restart checkpoint identity does not match the requested calculation"
        )
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        if allow_recompute:
            return None
        raise ConstantPotentialError("constant-potential restart checkpoint facts are malformed")

    residual_key = "residual_mu" if facts.get("energy_boundary") == "compensated_gate" else "residual_v"
    try:
        residual = float(facts[residual_key])
        nelec = float(facts["nelec"])
    except (KeyError, TypeError, ValueError) as exc:
        if allow_recompute:
            return None
        raise ConstantPotentialError(
            "constant-potential restart checkpoint is missing its evaluated residual or electron count"
        ) from exc
    if not np.isfinite(residual) or not np.isfinite(nelec) or nelec < 0:
        if allow_recompute:
            return None
        raise ConstantPotentialError(
            "constant-potential restart checkpoint has a non-finite or negative evaluated electron count"
        )
    if abs(residual) > tolerance:
        if allow_recompute:
            return None
        raise ConstantPotentialError(
            "constant-potential restart checkpoint residual exceeds the current tolerance"
        )
    return nelec


def _first_finite(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    """Return the first finite scalar found under ``keys``."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            try:
                value = float(mapping[key])
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                return value
    return None


def _read_vacuum_from_logs(directory: str | Path, suffix: str | None = None) -> float | None:
    """Read the last explicit vacuum level from an ABACUS output log.

    The parser is deliberately conservative: only lines containing the word
    ``vacuum`` are considered, and a missing/invalid line remains missing
    rather than falling back to a previous evaluation directory.
    """
    root = Path(directory)
    candidates = []
    if suffix:
        candidates.append(root / f"OUT.{suffix}" / "running_scf.log")
    else:
        candidates.append(root / "running_scf.log")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            match = _VACUUM_LINE_RE.match(line)
            if match is None:
                continue
            try:
                # This is Vvac itself. The reference fermishift is -Vvac.
                return float(match.group("value"))
            except ValueError:
                continue
    return None


def _backend_log_paths(calculator: Any) -> tuple[Path, ...]:
    """Return only the current backend's SCF log candidates."""
    directory = getattr(calculator, "directory", None)
    if directory is None:
        return ()
    root = Path(directory)
    parameters = getattr(calculator, "parameters", {})
    suffix = getattr(calculator, "suffix", None)
    if suffix is None and isinstance(parameters, Mapping):
        suffix = parameters.get("suffix")
    suffix = str(suffix or "ABACUS")
    return (root / f"OUT.{suffix}" / "running_scf.log",)


def _backend_scf_converged(calculator: Any, results: Mapping[str, Any]) -> bool | None:
    """Read an explicit SCF-validity fact from results or the current log."""
    for key in ("scf_converged", "scf_convergence", "scf_status", "convergence"):
        if key not in results or results[key] is None:
            continue
        value = results[key]
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"converged", "convergence achieved", "true", "yes", "ok"}:
                return True
            if normalized in {"not converged", "failed", "false", "no", "error"}:
                return False
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return None
    for path in _backend_log_paths(calculator):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _SCF_FAILURE_MARKER.search(text):
            return False
        if _SCF_SUCCESS_MARKER.search(text):
            return True
    return None


def _calculator_result(calculator: Any) -> dict[str, Any]:
    """Return a detached result mapping from an ASE calculator."""
    results = getattr(calculator, "results", None)
    return dict(results) if isinstance(results, Mapping) else {}


def _backend_efermi(calculator: Any, results: Mapping[str, Any]) -> float | None:
    """Extract the backend Fermi level without using an undeclared property."""
    value = _first_finite(results, _FERMI_KEYS)
    if value is not None:
        return value
    getter = getattr(calculator, "get_fermi_level", None)
    if callable(getter):
        try:
            return _finite(getter(), "Fermi level")
        except (AttributeError, ConstantPotentialError, TypeError, ValueError):
            return None
    return None


def _backend_vacuum(calculator: Any, results: Mapping[str, Any]) -> float | None:
    """Extract the vacuum level from results or the current backend directory."""
    value = _first_finite(results, _VACUUM_KEYS)
    if value is not None:
        return value
    # Some calculator adapters expose the old ``fermishift`` directly.  It is
    # a gauge shift, so Vvac = -fermishift under the §4 contract.
    shift = _first_finite(results, ("fermishift", "fermi_shift"))
    if shift is not None:
        return -shift
    directory = getattr(calculator, "directory", None)
    parameters = getattr(calculator, "parameters", {})
    suffix = getattr(calculator, "suffix", None)
    if suffix is None and isinstance(parameters, Mapping):
        suffix = parameters.get("suffix")
    # abacuslite binds the default output directory to OUT.ABACUS.
    suffix = str(suffix or "ABACUS")
    return _read_vacuum_from_logs(directory, suffix) if directory is not None else None


def _call_inner_factory(factory: Callable[[float, str], Any], nelec: float, directory: Path) -> Any:
    """Call a backend factory with the narrow CP callback contract.

    The callback contract is intentionally narrow so a backend ``TypeError``
    is never mistaken for a signature mismatch and retried.
    """
    return factory(nelec, str(directory))


class ConstantPotentialCalculator(Calculator):
    """Decorate an ASE calculator with one fixed-chemical-potential Newton loop.

    ``reference_fcp`` reproduces the frozen vacuum/work-function FCP-v2
    candidate algorithm.  ``compensated_gate`` consumes same-run density
    derivatives from the explicit ABACUS gate/dipole boundary and uses the
    declared target chemical potential directly.  The two profiles share the
    electronic-number loop but never share a missing or inferred reference.

    Args:
        inner_factory: Callable that constructs one fresh fixed-electron ASE
        calculator.  It receives ``(nelec, directory)``.
        potential_v: Target electrode potential in volts.
        reference_electrons: Required neutral/model-zero-charge electron count.
        initial_electrons: First backend electron-count guess.
        work_ref: Explicit reference electrode work function in eV.
        potential_tolerance_v: Absolute potential residual tolerance in volts.
        max_iterations: Maximum number of backend evaluations.
        capacitance_initial: Initial capacitance, per area by default.
        capacitance_unit: ``e/(V Angstrom^2)`` or total ``e/V``.
        nelec_min, nelec_max: Optional candidate electron-count bounds.
        nelec_step_max: Optional absolute step limit per Newton update.
        directory: Root directory for per-evaluation backend runs.
    """

    name = "constant_potential"
    implemented_properties = ["energy", "free_energy", "forces"]
    default_parameters: dict[str, Any] = {}

    def __init__(
        self,
        inner_factory: Callable[..., Any],
        potential_v: float | None,
        reference_electrons: float,
        *,
        initial_electrons: float | None = None,
        energy_boundary: str = "reference_fcp",
        target_mu_ev: float | None = None,
        reference_electrode: str = "SHE",
        work_ref: float | None = None,
        work_ref_source: str | None = None,
        reference_pH: float | None = None,
        temperature_K: float | None = None,
        potential_tolerance_v: float = 0.01,
        max_iterations: int = 100,
        capacitance_initial: float = 1.0 / 80.0,
        capacitance_unit: str = "e/(V Angstrom^2)",
        nelec_min: float | None = None,
        nelec_max: float | None = None,
        nelec_step_max: float | None = None,
        directory: str | Path = ".",
        vacuum_axis: int = 2,
        interface_count: int = 1,
        fixed_hamiltonian_identity: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.inner_factory = inner_factory
        self.energy_boundary = str(energy_boundary)
        if self.energy_boundary not in _ENERGY_BOUNDARIES:
            raise ValueError(f"energy_boundary must be one of {sorted(_ENERGY_BOUNDARIES)}")
        self.potential_v = None if potential_v is None else _finite(potential_v, "potential_v")
        self.target_mu_ev = None if target_mu_ev is None else _finite(target_mu_ev, "target_mu_ev")
        self.reference_electrons = _finite(reference_electrons, "reference_electrons")
        if self.reference_electrons < 0:
            raise ValueError("reference_electrons must be non-negative")
        if initial_electrons is None:
            raise ValueError(
                "initial_electrons is required; reference_electrons is the model-zero-charge value "
                "and cannot be used as an initial guess"
            )
        self.initial_electrons = _finite(
            initial_electrons,
            "initial_electrons",
        )
        self.reference_electrode = str(reference_electrode)
        if not self.reference_electrode.strip():
            raise ValueError("reference_electrode must not be empty")
        self.work_ref_source = None if work_ref_source is None else str(work_ref_source)
        if self.work_ref_source is not None and not self.work_ref_source.strip():
            raise ValueError("work_ref_source must not be blank")
        self.reference_pH = None if reference_pH is None else _finite(reference_pH, "reference_pH")
        self.temperature_K = None if temperature_K is None else _finite(temperature_K, "temperature_K")
        if self.temperature_K is not None and self.temperature_K <= 0:
            raise ValueError("temperature_K must be positive")
        self._declared_work_ref = None if work_ref is None else _finite(work_ref, "work_ref")
        self.work_ref: float | None = None
        self._validate_boundary_settings()
        self.profile_status = (
            "reference_only_unvalidated"
            if self.energy_boundary == "reference_fcp"
            else "compensated_gate_pending_scientific_acceptance"
        )
        self.potential_tolerance_v = _finite(potential_tolerance_v, "potential_tolerance_v")
        if self.potential_tolerance_v <= 0:
            raise ValueError("potential_tolerance_v must be positive")
        self.max_iterations = int(max_iterations)
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        self.capacitance_initial = _finite(capacitance_initial, "capacitance_initial")
        if self.capacitance_initial <= 0:
            raise ValueError("capacitance_initial must be positive")
        self.capacitance_unit = str(capacitance_unit)
        if self.capacitance_unit not in {"e/V", "e/(V Angstrom^2)", "e/V/A^2", "e/(V A^2)"}:
            raise ValueError("capacitance_unit must be 'e/V' or 'e/(V Angstrom^2)'")
        self.nelec_min = None if nelec_min is None else _finite(nelec_min, "nelec_min")
        self.nelec_max = None if nelec_max is None else _finite(nelec_max, "nelec_max")
        current_min = getattr(self, "nelec_min", None)
        current_max = getattr(self, "nelec_max", None)
        if current_min is not None and current_max is not None and current_min > current_max:
            raise ValueError("nelec_min must not exceed nelec_max")
        self.nelec_step_max = None if nelec_step_max is None else _finite(nelec_step_max, "nelec_step_max")
        if self.nelec_step_max is not None and self.nelec_step_max <= 0:
            raise ValueError("nelec_step_max must be positive")
        self.directory = Path(directory)
        self.vacuum_axis = int(vacuum_axis)
        if self.vacuum_axis not in (0, 1, 2):
            raise ValueError("vacuum_axis must be 0, 1, or 2")
        self.interface_count = int(interface_count)
        if self.interface_count not in (1, 2):
            raise ValueError("interface_count must be 1 or 2")
        self.last_evaluation: dict[str, Any] | None = None
        self.evaluation_history: list[dict[str, Any]] = []
        self.diagnostics: dict[str, Any] = {}
        self._actual_boundary_parameters: dict[str, Any] = {}
        self._fixed_hamiltonian_identity = _jsonable(fixed_hamiltonian_identity or {})
        self._batch_counter = 0
        self._evaluation_root = Path(self.directory)

    def _validate_boundary_settings(self) -> None:
        """Validate boundary-specific fields before an evaluation starts."""
        if self.energy_boundary == "reference_fcp":
            if self.potential_v is None:
                raise ValueError("reference_fcp requires potential_v")
            if self.target_mu_ev is not None:
                raise ValueError("target_mu_ev is only valid for compensated_gate")
            if self._declared_work_ref is None or self.work_ref_source is None:
                raise ValueError("reference_fcp requires work_ref and work_ref_source")
            self._refresh_work_reference()
            return
        if self.potential_v is not None:
            raise ValueError("compensated_gate does not accept potential_v")
        if self.target_mu_ev is None:
            raise ValueError("compensated_gate requires target_mu_ev")
        if self.reference_electrode.strip().lower() != "custom":
            raise ValueError("compensated_gate requires reference_electrode=custom")
        if self._declared_work_ref is not None or self.work_ref_source is not None:
            raise ValueError("compensated_gate does not accept work_ref/work_ref_source")
        if self.reference_pH is not None or self.temperature_K is not None:
            raise ValueError("compensated_gate does not accept reference_pH/temperature_K")
        self.work_ref = None

    def _refresh_work_reference(self) -> None:
        """Apply the declared SHE/custom calibration and optional RHE shift."""
        if self.energy_boundary == "compensated_gate":
            self.work_ref = None
            return
        if self.reference_electrode.strip().upper() == "RHE":
            if self.reference_pH is None or self.temperature_K is None:
                raise ValueError("RHE reference requires reference_pH and temperature_K")
            correction = 8.617333262145e-5 * self.temperature_K * math.log(10.0) * self.reference_pH
            self.work_ref = self._declared_work_ref - correction
            return
        if self.reference_pH is not None or self.temperature_K is not None:
            raise ValueError("reference_pH and temperature_K are only valid for a RHE reference")
        self.work_ref = self._declared_work_ref

    def _record_actual_boundary_parameters(self, parameters: Any) -> None:
        """Record boundary INPUT facts from the calculator used for this SCF."""
        if not isinstance(parameters, Mapping):
            return
        keys = (
            "gate_flag",
            "imp_sol",
            "efield_dir",
            "zgate",
            "block",
            "block_down",
            "block_up",
            "block_height",
            "efield_flag",
            "dip_cor_flag",
            "efield_amp",
            "efield_pos_max",
            "efield_pos_dec",
            "out_chg",
            "out_pot",
            "nspin",
            "two_fermi",
            "nupdown",
        )
        self._actual_boundary_parameters = {
            key: self._jsonable(parameters[key]) for key in keys if key in parameters
        }

    @property
    def target_mu(self) -> float:
        """Return the target electron chemical potential in eV."""
        if self.energy_boundary == "compensated_gate":
            assert self.target_mu_ev is not None
            return self.target_mu_ev
        assert self.potential_v is not None and self.work_ref is not None
        return -(self.potential_v + self.work_ref)

    @property
    def constant_potential_identity(self) -> dict[str, Any]:
        """Return the CP identity used by endpoint and restart validation."""
        configured_boundary = {}
        if isinstance(self._fixed_hamiltonian_identity, Mapping):
            configured_boundary = self._fixed_hamiltonian_identity.get("boundary_parameters", {})
        boundary_parameters = dict(configured_boundary) if isinstance(configured_boundary, Mapping) else {}
        boundary_parameters.update(self._actual_boundary_parameters)
        identity = {
            "energy_boundary": self.energy_boundary,
            "potential_v": self.potential_v,
            "target_mu_ev": self.target_mu_ev,
            "reference_electrode": self.reference_electrode,
            "work_ref": self.work_ref,
            "work_ref_source": self.work_ref_source,
            "reference_pH": self.reference_pH,
            "temperature_K": self.temperature_K,
            "reference_electrons": self.reference_electrons,
            "boundary_parameters": copy.deepcopy(boundary_parameters),
            "energy_definition": (
                "omega_compensated_gate" if self.energy_boundary == "compensated_gate" else "omega_aligned"
            ),
            "calculator": self.name,
        }
        if self._fixed_hamiltonian_identity:
            identity["fixed_hamiltonian"] = copy.deepcopy(self._fixed_hamiltonian_identity)
        return identity

    def set(self, **kwargs: Any) -> dict[str, Any]:
        """Update CP parameters and invalidate cached ASE results."""
        changed = super().set(**kwargs)
        if "energy_boundary" in kwargs:
            self.energy_boundary = str(kwargs["energy_boundary"])
            if self.energy_boundary not in _ENERGY_BOUNDARIES:
                raise ValueError(f"energy_boundary must be one of {sorted(_ENERGY_BOUNDARIES)}")
            changed["energy_boundary"] = self.energy_boundary
        if "potential_v" in kwargs:
            self.potential_v = None if kwargs["potential_v"] is None else _finite(kwargs["potential_v"], "potential_v")
            changed["potential_v"] = self.potential_v
        if "target_mu_ev" in kwargs:
            self.target_mu_ev = None if kwargs["target_mu_ev"] is None else _finite(kwargs["target_mu_ev"], "target_mu_ev")
            changed["target_mu_ev"] = self.target_mu_ev
        if "reference_electrons" in kwargs:
            self.reference_electrons = _finite(kwargs["reference_electrons"], "reference_electrons")
            if self.reference_electrons < 0:
                raise ValueError("reference_electrons must be non-negative")
            changed["reference_electrons"] = self.reference_electrons
        if "initial_electrons" in kwargs:
            self.initial_electrons = _finite(kwargs["initial_electrons"], "initial_electrons")
            changed["initial_electrons"] = self.initial_electrons
        if "reference_electrode" in kwargs:
            self.reference_electrode = str(kwargs["reference_electrode"])
            if not self.reference_electrode.strip():
                raise ValueError("reference_electrode must not be empty")
            changed["reference_electrode"] = self.reference_electrode
        if "work_ref" in kwargs:
            self._declared_work_ref = None if kwargs["work_ref"] is None else _finite(kwargs["work_ref"], "work_ref")
            changed["work_ref"] = self._declared_work_ref
        if "work_ref_source" in kwargs:
            self.work_ref_source = None if kwargs["work_ref_source"] is None else str(kwargs["work_ref_source"])
            if self.work_ref_source is not None and not self.work_ref_source.strip():
                raise ValueError("work_ref_source must not be blank")
            changed["work_ref_source"] = self.work_ref_source
        if "reference_pH" in kwargs:
            self.reference_pH = None if kwargs["reference_pH"] is None else _finite(kwargs["reference_pH"], "reference_pH")
            changed["reference_pH"] = self.reference_pH
        if "temperature_K" in kwargs:
            self.temperature_K = None if kwargs["temperature_K"] is None else _finite(kwargs["temperature_K"], "temperature_K")
            if self.temperature_K is not None and self.temperature_K <= 0:
                raise ValueError("temperature_K must be positive")
            changed["temperature_K"] = self.temperature_K
        if "potential_tolerance_v" in kwargs:
            self.potential_tolerance_v = _finite(kwargs["potential_tolerance_v"], "potential_tolerance_v")
            if self.potential_tolerance_v <= 0:
                raise ValueError("potential_tolerance_v must be positive")
            changed["potential_tolerance_v"] = self.potential_tolerance_v
        if "max_iterations" in kwargs:
            self.max_iterations = int(kwargs["max_iterations"])
            if self.max_iterations <= 0:
                raise ValueError("max_iterations must be positive")
            changed["max_iterations"] = self.max_iterations
        if "capacitance_initial" in kwargs:
            self.capacitance_initial = _finite(kwargs["capacitance_initial"], "capacitance_initial")
            if self.capacitance_initial <= 0:
                raise ValueError("capacitance_initial must be positive")
            changed["capacitance_initial"] = self.capacitance_initial
        if "capacitance_unit" in kwargs:
            self.capacitance_unit = str(kwargs["capacitance_unit"])
            if self.capacitance_unit not in {"e/V", "e/(V Angstrom^2)", "e/V/A^2", "e/(V A^2)"}:
                raise ValueError("capacitance_unit must be 'e/V' or 'e/(V Angstrom^2)'")
            changed["capacitance_unit"] = self.capacitance_unit
        for key in ("nelec_min", "nelec_max", "nelec_step_max"):
            if key not in kwargs:
                continue
            value = None if kwargs[key] is None else _finite(kwargs[key], key)
            if key == "nelec_step_max" and value is not None and value <= 0:
                raise ValueError("nelec_step_max must be positive")
            setattr(self, key, value)
            changed[key] = value
        current_min = getattr(self, "nelec_min", None)
        current_max = getattr(self, "nelec_max", None)
        if current_min is not None and current_max is not None and current_min > current_max:
            raise ValueError("nelec_min must not exceed nelec_max")
        if "vacuum_axis" in kwargs:
            self.vacuum_axis = int(kwargs["vacuum_axis"])
            if self.vacuum_axis not in (0, 1, 2):
                raise ValueError("vacuum_axis must be 0, 1, or 2")
            changed["vacuum_axis"] = self.vacuum_axis
        if "interface_count" in kwargs:
            self.interface_count = int(kwargs["interface_count"])
            if self.interface_count not in (1, 2):
                raise ValueError("interface_count must be 1 or 2")
            changed["interface_count"] = self.interface_count
        if changed and hasattr(self, "energy_boundary"):
            self._validate_boundary_settings()
            self.profile_status = (
                "reference_only_unvalidated"
                if self.energy_boundary == "reference_fcp"
                else "compensated_gate_pending_scientific_acceptance"
            )
            self.results.clear()
            self.last_evaluation = None
            self.evaluation_history = []
        return changed

    def _surface_area(self, atoms: Any) -> float:
        """Return the configured total/per-area conversion surface."""
        try:
            return surface_area(atoms.cell.array, self.vacuum_axis)
        except (AttributeError, ValueError, TypeError) as exc:
            raise ConstantPotentialEvaluationError(
                "a positive 3x3 cell surface area is required for per-area capacitance"
            ) from exc

    def _initial_capacitance(self, atoms: Any) -> float:
        """Return total capacitance in electrons per volt."""
        if self.capacitance_unit == "e/V":
            return self.capacitance_initial
        return self.capacitance_initial * self._surface_area(atoms)

    def _validate_candidate(self, nelec: float, inner_parameters: Mapping[str, Any] | None = None) -> float:
        """Validate and return one backend electron-count candidate."""
        candidate = _finite(nelec, "candidate electron count")
        if candidate < 0:
            raise ConstantPotentialConvergenceError(
                f"candidate electron count {candidate} must be non-negative"
            )
        if self.nelec_min is not None and candidate < self.nelec_min - 1e-12:
            raise ConstantPotentialConvergenceError(
                f"candidate electron count {candidate} is below nelec_min={self.nelec_min}"
            )
        if self.nelec_max is not None and candidate > self.nelec_max + 1e-12:
            raise ConstantPotentialConvergenceError(
                f"candidate electron count {candidate} exceeds nelec_max={self.nelec_max}"
            )
        if inner_parameters:
            nbands = inner_parameters.get("nbands")
            nspin = int(inner_parameters.get("nspin", 1) or 1)
            if nspin not in (1, 2):
                raise ConstantPotentialConvergenceError(
                    f"constant-potential evaluation supports nspin=1 or nspin=2, got {nspin}"
                )
            if nbands is not None:
                try:
                    nbands_value = float(nbands)
                except (TypeError, ValueError):
                    max_electrons = math.inf
                else:
                    # ABACUS uses nbands=0 for automatic band selection.  For
                    # both supported occupations the total state capacity is
                    # two electrons per band; nspin=2 distributes those states
                    # across the two collinear channels.
                    max_electrons = 2.0 * nbands_value if nbands_value > 0 else math.inf
                if np.isfinite(max_electrons) and candidate > max_electrons + 1e-12:
                    raise ConstantPotentialConvergenceError(
                        f"candidate electron count {candidate} exceeds nbands capacity {max_electrons}"
                    )
        return candidate

    def _evaluate(self, atoms: Any, nelec: float, index: int) -> dict[str, Any]:
        """Perform one fixed-electron backend evaluation and collect facts."""
        directory = self._evaluation_root / f"evaluation_{index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        # Bounds are checked before constructing or launching the backend.  A
        # backend-specific nbands capacity check follows once its parameters
        # are available below.
        nelec = self._validate_candidate(nelec)
        try:
            inner = _call_inner_factory(self.inner_factory, nelec, directory)
            parameters = getattr(inner, "parameters", {})
            if isinstance(parameters, Mapping):
                # ABACUS derives the two-Fermi spin state from nupdown.  A CP
                # scan cannot preserve a fixed, auditable conjugate boundary
                # when that explicit spin-population control is present,
                # including the seemingly neutral value nupdown=0.
                if "nupdown" in parameters:
                    raise ConstantPotentialEvaluationError(
                        "constant-potential profiles do not support explicit nupdown"
                    )
                if parameters.get("two_fermi"):
                    raise ConstantPotentialEvaluationError(
                        "constant-potential profiles do not support two_fermi"
                    )
            self._record_actual_boundary_parameters(parameters)
            nelec = self._validate_candidate(nelec, parameters if isinstance(parameters, Mapping) else None)
            probe = atoms.copy()
            probe.calc = inner
            # Requesting energy first lets file-backed calculators populate all
            # same-run facts.  Forces are then read from that same calculator.
            # The outer ASE atoms object applies its constraints once when it
            # consumes the published CP result.  Suppress them on this private
            # probe so Hookean/constraint energy and force contributions are
            # not applied a second time inside the electronic loop.
            energy = float(probe.get_potential_energy(force_consistent=False, apply_constraint=False))
            free_energy = float(probe.get_potential_energy(force_consistent=True, apply_constraint=False))
            forces = np.asarray(probe.get_forces(apply_constraint=False), dtype=float)
        except ConstantPotentialError:
            raise
        except Exception as exc:
            raise ConstantPotentialEvaluationError(
                f"fixed-electron evaluation failed at nelec={nelec}: {exc}"
            ) from exc
        raw_results = _calculator_result(inner)
        scf_converged = _backend_scf_converged(inner, raw_results)
        if scf_converged is not True:
            status = "not converged" if scf_converged is False else "missing convergence evidence"
            raise ConstantPotentialEvaluationError(
                f"fixed-electron evaluation at nelec={nelec} has {status}"
            )
        if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
            raise ConstantPotentialEvaluationError(
                f"fixed-electron evaluation at nelec={nelec} returned invalid forces"
            )
        raw_energy = _first_finite(raw_results, ("energy",))
        raw_free_energy = _first_finite(raw_results, ("free_energy",))
        if raw_energy is None:
            raw_energy = _finite(energy, "raw energy")
        if raw_free_energy is None:
            raw_free_energy = _finite(free_energy, "raw free energy")
        efermi = _backend_efermi(inner, raw_results)
        if efermi is None:
            raise ConstantPotentialEvaluationError(
                f"fixed-electron evaluation at nelec={nelec} did not provide a finite Fermi level"
            )
        efermi = _finite(efermi, "Fermi level")
        delta_n = nelec - self.reference_electrons
        vacuum: float | None = None
        compensation: dict[str, Any] | None = None
        if self.energy_boundary == "reference_fcp":
            vacuum = _backend_vacuum(inner, raw_results)
            if vacuum is None:
                raise ConstantPotentialEvaluationError(
                    f"fixed-electron evaluation at nelec={nelec} did not provide a finite vacuum reference"
                )
            vacuum = _finite(vacuum, "vacuum level")
            mu_calc = efermi - vacuum
            assert self.work_ref is not None and self.potential_v is not None
            potential_calc = (vacuum - efermi) - self.work_ref
            residual_mu = mu_calc - self.target_mu
            residual_v = potential_calc - self.potential_v
            correction = (-vacuum - self.target_mu) * delta_n
        else:
            try:
                from atst_tools.utils.gate_compensation import read_gate_compensation

                compensation = dict(read_gate_compensation(directory, nelec, self.reference_electrons))
            except Exception as exc:
                raise ConstantPotentialEvaluationError(
                    f"compensated_gate compensation evidence is unavailable at nelec={nelec}: {exc}"
                ) from exc
            derivative = _finite(
                compensation.get("compensation_derivative_ev"),
                "compensation derivative",
            )
            mu_calc = efermi + derivative
            potential_calc = None
            residual_mu = mu_calc - self.target_mu
            # eV and V have the same numerical residual when one electron's
            # charge unit is used. Keep residual_v as a compatibility alias so
            # the existing Newton loop and StageRecord can remain shared.
            residual_v = residual_mu
            correction = -self.target_mu * delta_n
        if not np.isfinite(residual_mu) or not np.isfinite(residual_v):
            raise ConstantPotentialEvaluationError("constant-potential residual is not finite")
        # ``correction`` is computed above from the selected boundary.  It is
        # deliberately applied only to the energy bookkeeping; backend forces
        # remain the same-run raw forces for the compensated profile.
        omega_energy = raw_energy + correction
        omega_free_energy = raw_free_energy + correction
        result: dict[str, Any] = {
            "nelec": nelec,
            "reference_electrons": self.reference_electrons,
            "delta_nelec": delta_n,
            "raw_energy": raw_energy,
            "raw_free_energy": raw_free_energy,
            "energy": omega_energy,
            "free_energy": omega_free_energy,
            "forces": forces.copy(),
            "efermi": efermi,
            "vacuum_level": vacuum,
            "fermishift": None if vacuum is None else -vacuum,
            "scf_converged": True,
            "energy_boundary": self.energy_boundary,
            "profile_status": self.profile_status,
            "boundary_parameters": copy.deepcopy(self._actual_boundary_parameters),
            "compensation": compensation,
            "mu_calc": mu_calc,
            "mu_target": self.target_mu,
            "potential_calc": potential_calc,
            "potential_target": self.potential_v,
            "residual_mu": residual_mu,
            "residual_v": residual_v,
            "omega_correction": correction,
            "directory": str(directory),
            "evaluation_index": index,
            "inner_results": copy.deepcopy(raw_results),
            "valid": True,
        }
        return result

    def _next_candidate(self, current: dict[str, Any], history: list[dict[str, Any]], capacitance: float) -> tuple[float, dict[str, Any]]:
        """Calculate the next Newton candidate using measured residuals."""
        fit_info: dict[str, Any] = {
            "fit_degree": None,
            "fit_rss_eV2": None,
            "derivative_eV_per_e": None,
            "derivative_source": "initial_capacitance",
            "fit_status": "not_attempted",
        }
        derivative = 1.0 / capacitance
        samples = [item for item in history if item.get("valid")]
        if len(samples) >= 2:
            try:
                fitted = chebyshev_derivative(
                    [item["nelec"] for item in samples],
                    [item["mu_calc"] for item in samples],
                    current["nelec"],
                )
                fit_info.update(fitted)
                if float(fitted["derivative_eV_per_e"]) > 0:
                    derivative = float(fitted["derivative_eV_per_e"])
                    fit_info["derivative_source"] = "chebyshev_forward_difference"
                    fit_info["fit_status"] = "accepted"
                else:
                    fit_info["fit_status"] = "fallback"
                    fit_info["fit_error"] = "fitted derivative is not positive"
                    fit_info["derivative_source"] = "fallback_previous_capacitance"
            except (ValueError, TypeError, KeyError, ConstantPotentialError) as exc:
                # A rank-deficient/non-finite fit falls back to the previous
                # valid positive inverse capacitance, but the durable history
                # must identify that fallback explicitly.
                fit_info["fit_status"] = "fallback"
                fit_info["fit_error"] = str(exc)
                fit_info["derivative_source"] = "fallback_previous_capacitance"
        if derivative <= 0 or not np.isfinite(derivative):
            derivative = 1.0 / capacitance
        fit_info["derivative_eV_per_e"] = derivative
        raw_next = current["nelec"] - current["residual_mu"] / derivative
        next_candidate = raw_next
        if self.nelec_step_max is not None:
            delta = np.clip(raw_next - current["nelec"], -self.nelec_step_max, self.nelec_step_max)
            next_candidate = current["nelec"] + float(delta)
        if self.nelec_min is not None:
            next_candidate = max(next_candidate, self.nelec_min)
        if self.nelec_max is not None:
            next_candidate = min(next_candidate, self.nelec_max)
        fit_info["candidate_unbounded"] = raw_next
        fit_info["candidate_nelec"] = next_candidate
        return float(next_candidate), fit_info

    def _new_evaluation_batch(self) -> Path:
        """Reserve a fresh batch directory, including across calculator restarts."""
        root = Path(self.directory)
        root.mkdir(parents=True, exist_ok=True)
        existing_indices = []
        for path in root.glob("batch_*"):
            if not path.is_dir():
                continue
            try:
                existing_indices.append(int(path.name.removeprefix("batch_")))
            except ValueError:
                continue
        next_index = max([self._batch_counter, *existing_indices], default=0) + 1
        while True:
            batch = root / f"batch_{next_index:04d}"
            try:
                batch.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                next_index += 1
                continue
            self._batch_counter = next_index
            return batch

    def calculate(
        self,
        atoms: Any = None,
        properties: tuple[str, ...] = ("energy",),
        system_changes: tuple[str, ...] = all_changes,
    ) -> None:
        """Run the electronic-number loop and publish only a converged state."""
        if atoms is not None:
            # A changed geometry must not leave a prior CP envelope available to
            # trajectory/NEB consumers while the new electronic loop runs.
            clear_constant_potential_facts(atoms)
        super().calculate(atoms, properties, system_changes)
        if atoms is None:
            raise ConstantPotentialEvaluationError("constant-potential calculation requires atoms")
        self.results.clear()
        self.last_evaluation = None
        self.evaluation_history = []
        self._actual_boundary_parameters = {}
        self._evaluation_root = self._new_evaluation_batch()
        self.diagnostics = {
            "potential_target": self.potential_v,
            "mu_target": self.target_mu,
            "reference_electrons": self.reference_electrons,
            "status": "running",
        }
        final: dict[str, Any] | None = None
        try:
            current_nelec = self._validate_candidate(self.initial_electrons)
            capacitance = self._initial_capacitance(atoms)
            for index in range(1, self.max_iterations + 1):
                evaluation = self._evaluate(atoms, current_nelec, index)
                history_record = {
                    key: value
                    for key, value in evaluation.items()
                    if key not in {"forces", "inner_results"}
                }
                history_record["converged"] = abs(float(evaluation["residual_v"])) <= self.potential_tolerance_v
                self.evaluation_history.append(history_record)
                self.last_evaluation = evaluation
                if history_record["converged"]:
                    final = evaluation
                    break
                if index >= self.max_iterations:
                    raise ConstantPotentialConvergenceError(
                        f"constant-potential tolerance not reached after {self.max_iterations} iterations"
                    )
                current_nelec, fit_info = self._next_candidate(
                    evaluation, self.evaluation_history, capacitance
                )
                history_record.update(fit_info)
                if fit_info.get("derivative_source") == "chebyshev_forward_difference":
                    derivative = float(fit_info["derivative_eV_per_e"])
                    if derivative > 0 and np.isfinite(derivative):
                        capacitance = 1.0 / derivative
                if math.isclose(current_nelec, evaluation["nelec"], rel_tol=0.0, abs_tol=1e-14):
                    raise ConstantPotentialConvergenceError(
                        "constant-potential update produced no electron-count progress"
                    )
            if final is None:
                raise ConstantPotentialConvergenceError("constant-potential calculation did not converge")
        except ConstantPotentialError as exc:
            self.diagnostics.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "last_evaluation": self._jsonable(self.last_evaluation),
                    "history": self._jsonable(self.evaluation_history),
                }
            )
            # Deliberately do not publish energy/forces from a non-converged
            # state.  The last valid evaluation remains available for durable
            # diagnostics and recovery, but ASE optimizers cannot consume it.
            raise
        self.results = {
            "energy": float(final["energy"]),
            "free_energy": float(final["free_energy"]),
            "forces": np.asarray(final["forces"], dtype=float).copy(),
            "raw_energy": float(final["raw_energy"]),
            "raw_free_energy": float(final["raw_free_energy"]),
            "efermi": float(final["efermi"]),
            "vacuum_level": None if final["vacuum_level"] is None else float(final["vacuum_level"]),
            "fermishift": None if final["fermishift"] is None else float(final["fermishift"]),
            "energy_boundary": final["energy_boundary"],
            "profile_status": self.profile_status,
            "boundary_parameters": self._jsonable(final["boundary_parameters"]),
            "compensation": self._jsonable(final["compensation"]),
            "mu_calc": float(final["mu_calc"]),
            "mu_target": float(final["mu_target"]),
            "potential_calc": None if final["potential_calc"] is None else float(final["potential_calc"]),
            "potential_target": None if final["potential_target"] is None else float(final["potential_target"]),
            "residual_mu": float(final["residual_mu"]),
            "residual_v": float(final["residual_v"]),
            "omega_correction": float(final["omega_correction"]),
            "nelec": float(final["nelec"]),
            "reference_electrons": float(final["reference_electrons"]),
            "delta_nelec": float(final["delta_nelec"]),
            # Preserve explicit same-run backend convergence evidence.  Durable
            # CP consumers must not infer SCF success from CP history alone.
            "scf_converged": True,
            "cp_converged": True,
            "cp_iterations": int(final["evaluation_index"]),
            "cp_history": self._jsonable(self.evaluation_history),
            "cp_identity": self.constant_potential_identity,
        }
        publish_constant_potential_facts(atoms, self.results, self.constant_potential_identity)
        self.diagnostics.update(
            {
                "status": "converged",
                "cp_iterations": int(final["evaluation_index"]),
                "history": self._jsonable(self.evaluation_history),
            }
        )

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Detach NumPy values for logs and manifests."""
        if isinstance(value, Mapping):
            return {str(key): ConstantPotentialCalculator._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [ConstantPotentialCalculator._jsonable(item) for item in value]
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value


# Short alias retained for callers that use the common FCP vocabulary.
ConstantPotential = ConstantPotentialCalculator


def constant_potential_identity_for_config(
    config: Mapping[str, Any], target: float | None = None
) -> dict[str, Any] | None:
    """Return the CP identity represented by a normalized config mapping."""
    if not isinstance(config, Mapping):
        return None
    cp = config.get("constant_potential")
    if not isinstance(cp, Mapping) and isinstance(config.get("calculator"), Mapping):
        cp = config["calculator"].get("constant_potential")
    if not isinstance(cp, Mapping) and "energy_boundary" in config:
        cp = config
    if not isinstance(cp, Mapping):
        return None
    boundary = str(cp.get("energy_boundary", "reference_fcp"))
    if boundary == "compensated_gate":
        if target is None:
            target = cp.get("target_mu_ev")
        if target is None:
            return None
        identity = {
            "energy_boundary": boundary,
            "potential_v": None,
            "target_mu_ev": float(target),
            "reference_electrode": str(cp.get("reference_electrode", "custom")),
            "work_ref": None,
            "work_ref_source": None,
            "reference_pH": None,
            "temperature_K": None,
            "reference_electrons": float(cp["reference_electrons"]),
            "boundary_parameters": {},
            "energy_definition": "omega_compensated_gate",
            "calculator": "constant_potential",
        }
        fixed_hamiltonian = fixed_hamiltonian_identity_for_config(config)
        if fixed_hamiltonian:
            identity["fixed_hamiltonian"] = fixed_hamiltonian
            identity["boundary_parameters"] = copy.deepcopy(
                fixed_hamiltonian.get("boundary_parameters", {})
            )
        return identity
    if target is None:
        target = cp.get("potential_v")
    if target is None:
        return None
    reference_electrode = str(cp.get("reference_electrode", "SHE"))
    work_ref = float(cp["work_ref"])
    ph = cp.get("reference_pH")
    temperature = cp.get("temperature_K")
    if reference_electrode.strip().upper() == "RHE" and ph is not None and temperature is not None:
        work_ref -= 8.617333262145e-5 * float(temperature) * math.log(10.0) * float(ph)
    identity = {
        "energy_boundary": boundary,
        "potential_v": float(target),
        "target_mu_ev": None,
        "reference_electrode": reference_electrode,
        "work_ref": work_ref,
        "work_ref_source": cp.get("work_ref_source"),
        "reference_pH": ph,
        "temperature_K": temperature,
        "reference_electrons": float(cp["reference_electrons"]),
        "boundary_parameters": {},
        "energy_definition": "omega_aligned",
        "calculator": "constant_potential",
    }
    fixed_hamiltonian = fixed_hamiltonian_identity_for_config(config)
    if fixed_hamiltonian:
        identity["fixed_hamiltonian"] = fixed_hamiltonian
        identity["boundary_parameters"] = copy.deepcopy(
            fixed_hamiltonian.get("boundary_parameters", {})
        )
    return identity


def constant_potential_restart_initial_electrons_for_config(
    atoms: Any,
    config: Mapping[str, Any],
    *,
    allow_recompute: bool = False,
) -> float | None:
    """Resolve a CP restart electron count from a workflow configuration.

    Relax and NEB workflows use a scalar target and a single current
    potential/chemical-potential tolerance.  This adapter derives the same
    identity the calculator factory uses, then delegates all durable-envelope
    validation to :func:`constant_potential_restart_initial_electrons`.
    """
    if not isinstance(config, Mapping):
        return None
    calculator = config.get("calculator")
    cp = calculator.get("constant_potential") if isinstance(calculator, Mapping) else None
    if not isinstance(cp, Mapping):
        return None
    boundary = str(cp.get("energy_boundary", "reference_fcp"))
    target_key = "target_mu_ev" if boundary == "compensated_gate" else "potential_v"
    target = cp.get(target_key)
    if target is None:
        raise ConstantPotentialError(
            f"constant-potential restart requires scalar {target_key} for this workflow"
        )
    expected_identity = constant_potential_identity_for_config(config, target=float(target))
    if expected_identity is None:
        raise ConstantPotentialError("constant-potential restart identity could not be constructed")
    return constant_potential_restart_initial_electrons(
        atoms,
        expected_identity,
        cp.get("potential_tolerance_v", 0.01),
        allow_recompute=allow_recompute,
    )


__all__ = [
    "ConstantPotential",
    "ConstantPotentialCalculator",
    "ConstantPotentialConvergenceError",
    "ConstantPotentialError",
    "ConstantPotentialEvaluationError",
    "CP_FACTS_INFO_KEY",
    "CP_IDENTITY_INFO_KEY",
    "CP_FACTS_SCHEMA",
    "clear_constant_potential_facts",
    "constant_potential_geometry_fingerprint",
    "fixed_hamiltonian_identity_for_config",
    "constant_potential_identity_for_config",
    "constant_potential_restart_initial_electrons",
    "constant_potential_restart_initial_electrons_for_config",
    "publish_constant_potential_facts",
    "read_constant_potential_facts",
]
