"""Constant-potential single-point and serial fixed-geometry scan workflow."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from ase.io import write
from ase.calculators.singlepoint import SinglePointCalculator

from atst_tools.calculators.constant_potential import (
    ConstantPotentialError,
    _mapping_contains,
    constant_potential_identity_for_config,
    publish_constant_potential_facts,
)
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.electrochemistry import PotentialScanPoint, analyze_potential_scan, surface_area
from atst_tools.utils.io import read_structure
from atst_tools.utils.convergence import StageRecord


class ConstantPotentialWorkflow:
    """Run one target or a serial list of fixed-geometry potentials."""

    def __init__(self, config: dict[str, Any], calc_name: str, calc_config: dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)
        self.init_structure = self.calc_config["init_structure"]
        self.results_file = self.calc_config.get("results_file", "constant_potential_results.json")
        self.log_file = self.calc_config.get("log_file", "constant_potential.log")
        self.checkpoint_file = self.calc_config.get("checkpoint_file", "constant_potential_checkpoint.json")
        self.artifact_manifest = self.calc_config.get("artifact_manifest", "atst_artifacts.json")
        self.directory = Path(self.calc_config.get("directory", "constant_potential_run"))
        self.restart = bool(self.calc_config.get("restart", False))
        calculator = config.get("calculator", {})
        self.cp_config = dict(calculator.get("constant_potential") or {})
        self.energy_boundary = str(self.cp_config.get("energy_boundary", "reference_fcp"))
        self.target_field = "target_mu_ev" if self.energy_boundary == "compensated_gate" else "potential_v"
        self.targets = self._targets()

    def _checkpoint_identity(self) -> dict[str, Any]:
        """Return the fixed research identity used to validate restart files."""
        relevant = {
            key: self.cp_config.get(key)
            for key in (
                "energy_boundary",
                "reference_electrode",
                "work_ref",
                "work_ref_source",
                "reference_electrons",
                "reference_pH",
                "temperature_K",
                "potential_tolerance_v",
                "max_iterations",
                "capacitance_initial",
                "capacitance_unit",
                "nelec_min",
                "nelec_max",
                "nelec_step_max",
                "vacuum_axis",
                "interface_count",
            )
        }
        relevant["energy_boundary"] = self.energy_boundary
        calculator = deepcopy(self.config.get("calculator", {}))
        if isinstance(calculator, dict):
            calculator.pop("constant_potential", None)
        return {
            "workflow": "constant_potential",
            "target_field": self.target_field,
            "targets": self.targets,
            "settings": relevant,
            "calculator": self._jsonable(calculator),
            "fixed_assets": self._fixed_asset_identity(),
            "input_structure": self._structure_identity(),
        }

    @staticmethod
    def _file_sha256(path: Path) -> str | None:
        """Return a file digest, preserving a missing asset as explicit state."""
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        except OSError:
            return None

    @staticmethod
    def _resolve_asset_path(value: Any, directory: Any, base: Path) -> Path:
        """Resolve a configured ABACUS asset using the factory's cwd rule."""
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            root = Path(str(directory)).expanduser() if directory else base
            if not root.is_absolute():
                root = base / root
            path = root / path
        return path.resolve()

    def _fixed_asset_identity(self) -> dict[str, Any]:
        """Digest fixed ABACUS files and the generated k-point specification.

        The ordinary calculator mapping records filenames, which is not enough
        for restart safety: replacing ``Pt.upf`` in place must invalidate a
        completed scan.  This identity mirrors the factory's alias merging and
        records both resolved paths and content digests.  K-points are usually
        generated from a mapping, so their normalized specification is included
        even when no standalone KPT path is configured.
        """
        calculator = self.config.get("calculator", {})
        abacus = calculator.get("abacus", {}) if isinstance(calculator, Mapping) else {}
        abacus = dict(abacus) if isinstance(abacus, Mapping) else {}
        control_keys = {"command", "directory", "mpi", "omp", "parameters", "version_command"}
        parameters = {
            key: value for key, value in abacus.items() if key not in control_keys
        }
        raw_parameters = abacus.get("parameters", {})
        if isinstance(raw_parameters, Mapping):
            parameters.update(dict(raw_parameters))
        if "pp" in parameters:
            parameters["pseudopotentials"] = parameters["pp"]
        if "basis" in parameters:
            parameters["basissets"] = parameters["basis"]
        if "basis_dir" in parameters:
            parameters["orbital_dir"] = parameters["basis_dir"]

        base = Path.cwd().resolve()

        def records(mapping: Any, directory: Any, kind: str) -> list[dict[str, Any]]:
            if not isinstance(mapping, Mapping):
                return []
            output = []
            for species, filename in sorted(mapping.items(), key=lambda item: str(item[0])):
                path = self._resolve_asset_path(filename, directory, base)
                output.append(
                    {
                        "kind": kind,
                        "species": str(species),
                        "configured_name": str(filename),
                        "path": str(path),
                        "sha256": self._file_sha256(path),
                    }
                )
            return output

        pseudo_dir = parameters.get("pseudo_dir")
        orbital_dir = parameters.get("orbital_dir")
        assets: dict[str, Any] = {
            "pseudopotentials": records(
                parameters.get("pseudopotentials"), pseudo_dir, "pseudopotential"
            ),
            "orbitals": records(
                parameters.get("basissets"), orbital_dir, "orbital"
            ),
            "kpoints": {
                "specification": self._jsonable(parameters.get("kpts", [1, 1, 1]))
            },
        }
        kpt_file = parameters.get("kpt_file", parameters.get("KPT"))
        if kpt_file is not None:
            path = self._resolve_asset_path(kpt_file, None, base)
            assets["kpoints"]["file"] = {
                "configured_name": str(kpt_file),
                "path": str(path),
                "sha256": self._file_sha256(path),
            }
        return assets

    def _structure_identity(self) -> dict[str, str | None]:
        """Return the input path and content digest used by restart checks."""
        path = Path(self.init_structure)
        digest = None
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            pass
        return {"path": str(path), "sha256": digest}

    def _load_checkpoint(self) -> list[dict[str, Any]]:
        """Load completed points after exact identity validation."""
        if not self.restart:
            return []
        path = Path(self.checkpoint_file)
        if not path.is_file():
            raise ValueError(f"constant-potential restart checkpoint not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Unable to read constant-potential checkpoint: {path}") from exc
        if payload.get("schema") != "atst-constant-potential-checkpoint-v1":
            raise ValueError("constant-potential checkpoint schema is unsupported")
        if payload.get("identity") != self._checkpoint_identity():
            raise ValueError(
                "constant-potential checkpoint identity does not match targets or fixed settings; "
                "start a new directory"
            )
        points = payload.get("points")
        if not isinstance(points, list):
            raise ValueError("constant-potential checkpoint points are malformed")
        if len(points) > len(self.targets):
            raise ValueError("constant-potential checkpoint contains more points than configured targets")
        expected = list(range(len(points)))
        actual = [point.get("index") for point in points if isinstance(point, dict)]
        if actual != expected:
            raise ValueError("constant-potential checkpoint has non-contiguous or malformed point records")
        try:
            expected_force_shape = (len(read_structure(self.init_structure)), 3)
        except Exception as exc:
            raise ValueError("constant-potential checkpoint input structure is unreadable") from exc
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                raise ValueError("constant-potential checkpoint contains a malformed point record")
            try:
                target = float(point[self.target_field])
                nelec = float(point["nelec"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("constant-potential checkpoint point is missing a finite state") from exc
            if target != self.targets[index] or not np.isfinite(nelec):
                raise ValueError("constant-potential checkpoint point does not match target order")
            if point.get("cp_converged") is not True:
                raise ValueError("constant-potential checkpoint may contain only converged points")
            for key in ("energy", "raw_energy", "free_energy", "raw_free_energy", "residual_v"):
                if key not in point:
                    if key in {"energy", "residual_v"}:
                        raise ValueError(f"constant-potential checkpoint point is missing {key}")
                    continue
                try:
                    value = float(point[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"constant-potential checkpoint {key} is not finite") from exc
                if not np.isfinite(value):
                    raise ValueError(f"constant-potential checkpoint {key} is not finite")
            try:
                forces = np.asarray(point["forces"], dtype=float)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("constant-potential checkpoint point forces are malformed") from exc
            if forces.shape != expected_force_shape or not np.all(np.isfinite(forces)):
                raise ValueError("constant-potential checkpoint point forces have invalid shape or values")
            tolerance = float(self.cp_config.get("potential_tolerance_v", 0.01))
            if abs(float(point["residual_v"])) > tolerance:
                raise ValueError("constant-potential checkpoint point residual exceeds configured tolerance")
            expected_cp_identity = constant_potential_identity_for_config(
                self.config, target=target
            )
            actual_cp_identity = point.get("cp_identity")
            if not isinstance(actual_cp_identity, Mapping) or expected_cp_identity is None:
                raise ValueError("constant-potential checkpoint point is missing CP identity")
            checkpoint_identity = {
                key: value
                for key, value in expected_cp_identity.items()
                if key not in {"boundary_parameters", "fixed_hamiltonian"}
            }
            if not _mapping_contains(actual_cp_identity, checkpoint_identity):
                raise ValueError("constant-potential checkpoint point CP identity does not match")
        next_initial = payload.get("next_initial_electrons")
        if points:
            try:
                if float(next_initial) != float(points[-1]["nelec"]):
                    raise ValueError("constant-potential checkpoint next guess does not match last point")
            except (TypeError, ValueError) as exc:
                raise ValueError("constant-potential checkpoint next guess is malformed") from exc
        return [dict(point) for point in points]

    def _write_checkpoint(self, points: list[dict[str, Any]], next_initial_electrons: float | None) -> None:
        """Atomically persist the completed-point boundary and next guess."""
        self._write_json(
            self.checkpoint_file,
            {
                "schema": "atst-constant-potential-checkpoint-v1",
                "identity": self._checkpoint_identity(),
                "points": points,
                "next_initial_electrons": next_initial_electrons,
            },
        )

    def _targets(self) -> list[float]:
        """Return validated target potentials or chemical potentials in order."""
        scalar_key = "target_mu_ev" if self.energy_boundary == "compensated_gate" else "potential_v"
        list_key = "target_mu_values_ev" if self.energy_boundary == "compensated_gate" else "potentials_v"
        potential = self.cp_config.get(scalar_key)
        potentials = self.cp_config.get(list_key)
        if (potential is None) == (potentials is None):
            raise ValueError(f"constant-potential workflow requires {scalar_key} or {list_key}")
        targets = [float(potential)] if potential is not None else [float(value) for value in potentials]
        if not targets:
            raise ValueError(f"constant-potential {list_key} must not be empty")
        if len(set(targets)) != len(targets):
            raise ValueError(f"constant-potential {list_key} must not contain duplicates")
        return targets

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Detach NumPy/ASE-adjacent values for JSON artifacts."""
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "tolist"):
            return value.tolist()
        if isinstance(value, dict):
            return {str(key): ConstantPotentialWorkflow._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [ConstantPotentialWorkflow._jsonable(item) for item in value]
        if hasattr(value, "item"):
            return value.item()
        return value

    @staticmethod
    def _target_slug(target: float) -> str:
        """Return a stable, collision-free human-readable target slug."""
        text = f"{target:.12g}".replace("-", "m").replace("+", "p").replace(".", "d")
        return text or "zero"

    def _write_json(self, path: str | Path, payload: Any) -> None:
        """Write a JSON artifact atomically within its parent directory."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.tmp")
        temporary.write_text(json.dumps(self._jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(output)

    def _write_failure_manifest(self, points: list[dict[str, Any]], error: BaseException) -> None:
        """Publish a durable partial-result manifest before propagating failure."""
        residual_key = "residual_mu_eV" if self.energy_boundary == "compensated_gate" else "residual_v"
        residual_unit = "eV" if self.energy_boundary == "compensated_gate" else "V"
        stages = []
        for point in points:
            stages.append(
                StageRecord(
                    name=f"potential_{point['index']:04d}",
                    status="complete",
                    converged=bool(point.get("cp_converged", False)),
                    role="potential_point",
                    criterion="constant_potential",
                    iteration=int(point.get("cp_iterations", 0) or 0),
                    measured={residual_key: float(point.get(residual_key, point.get("residual_v", 0.0)))},
                    measured_unit=residual_unit,
                ).to_manifest()
            )
        stages.append(
            StageRecord(
                name="constant_potential",
                status="failed",
                converged=False,
                role="final",
                criterion="constant_potential",
                measured={"completed_points": float(len(points))},
                measured_unit="count",
            ).to_manifest()
        )
        write_artifact_manifest(
            self.artifact_manifest,
            workflow="constant_potential",
            artifacts=self._artifact_list(points),
            stages=stages,
            metadata={
                "status": "failed",
                "energy_boundary": self.energy_boundary,
                ("target_mu_values_ev" if self.energy_boundary == "compensated_gate" else "targets_v"): self.targets,
                "error_type": type(error).__name__,
                "error": str(error),
                "completed_points": len(points),
            },
        )

    def _artifact_list(self, points: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
        """Describe the durable CP workflow outputs."""
        artifacts = [
            {"role": "results", "path": self.results_file},
            {"role": "constant_potential_log", "path": self.log_file},
            {"role": "checkpoint", "path": self.checkpoint_file},
            {"role": "input_structure", "path": self.init_structure},
            {"role": "final_structure", "path": str(self.directory / "final_structure.traj")},
            {"role": "artifact_manifest", "path": self.artifact_manifest},
        ]
        for point in points or []:
            path = point.get("point_artifact")
            if path:
                artifacts.append({"role": "potential_point", "path": str(path)})
        return artifacts

    def run(self):
        """Execute all targets serially and return the final CP-atoms object."""
        atoms = read_structure(self.init_structure)
        points: list[dict[str, Any]] = self._load_checkpoint()
        previous_nelec: float | None = (
            float(points[-1]["nelec"]) if points else None
        )
        final_atoms = None
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            for index, target in enumerate(self.targets[len(points) :], start=len(points)):
                point_dir = self.directory / f"point_{index:04d}_{self._target_slug(target)}"
                local_config = deepcopy(self.config)
                local_cp = dict(local_config.get("calculator", {}).get("constant_potential", {}))
                if self.energy_boundary == "compensated_gate":
                    local_cp["target_mu_ev"] = target
                    local_cp.pop("target_mu_values_ev", None)
                else:
                    local_cp["potential_v"] = target
                    local_cp.pop("potentials_v", None)
                local_config.setdefault("calculator", {})["constant_potential"] = local_cp
                local_kwargs: dict[str, Any] = {"directory": str(point_dir), "constant_potential_target": target}
                if previous_nelec is not None:
                    local_kwargs["constant_potential_initial"] = previous_nelec
                point_atoms = atoms.copy()
                calculator = CalculatorFactory.get_calculator(self.calc_name, local_config, **local_kwargs)
                point_atoms.calc = calculator
                energy = float(point_atoms.get_potential_energy())
                forces = point_atoms.get_forces()
                result = dict(getattr(calculator, "results", {}))
                result.update(
                    {
                        "index": index,
                        self.target_field: target,
                        "forces": forces,
                        "cp_converged": bool(result.get("cp_converged", False)),
                    }
                )
                result["energy"] = energy
                if self.energy_boundary == "compensated_gate":
                    result["residual_mu_eV"] = float(result["residual_mu"])
                result["structure"] = self.init_structure
                point_file = point_dir / "result.json"
                self._write_json(point_file, result)
                point_summary = self._jsonable(result)
                point_summary["point_artifact"] = str(point_file)
                points.append(point_summary)
                previous_nelec = float(result["nelec"])
                final_atoms = point_atoms
                self._write_checkpoint(points, previous_nelec)
            if final_atoms is None and points:
                # A fully completed restart still returns a usable final
                # structure without silently re-running the backend.
                final_atoms = atoms.copy()
                last = points[-1]
                final_atoms.calc = SinglePointCalculator(
                    final_atoms,
                    energy=float(last["energy"]),
                    forces=np.asarray(last["forces"], dtype=float),
                )
                if isinstance(last.get("cp_identity"), dict):
                    publish_constant_potential_facts(final_atoms, last, last["cp_identity"])
            analysis = None
            if len(points) > 1:
                reference_electrons = float(self.cp_config["reference_electrons"])
                # Use the configured vacuum axis rather than a cell helper that
                # might silently select the wrong plane for a slab.
                axis = int(self.cp_config.get("vacuum_axis", 2))
                area = surface_area(final_atoms.cell.array, axis)
                analysis = analyze_potential_scan(
                    [
                        PotentialScanPoint(
                            potential_v=float(point[self.target_field]),
                            electrons=float(point["nelec"]),
                            converged=bool(point["cp_converged"]),
                        )
                        for point in points
                    ],
                    reference_electrons=reference_electrons,
                    area_A2=area,
                    interface_count=int(self.cp_config.get("interface_count", 1)),
                    coordinate=self.target_field,
                )
                analysis["target_field"] = self.target_field
            payload = {
                "schema": "atst-constant-potential-result-v1",
                "workflow": "constant_potential",
                "status": "complete",
                "energy_boundary": self.energy_boundary,
                ("target_mu_values_ev" if self.energy_boundary == "compensated_gate" else "targets_v"): self.targets,
                "points": points,
                "analysis": analysis,
                "calculator_identity": (
                    getattr(getattr(final_atoms, "calc", None), "constant_potential_identity", None)
                    or (points[-1].get("cp_identity") if points else None)
                ),
            }
            self._write_json(self.results_file, payload)
            residual_field = "residual_mu_eV" if self.energy_boundary == "compensated_gate" else "residual_v"
            log_lines = [
                f"constant_potential\tindex\t{self.target_field}\tnelec\tmu_calc\t{residual_field}\tconverged",
            ]
            for point in points:
                log_lines.append(
                    "constant_potential\t{index}\t{target:.12g}\t{nelec:.12g}\t{mu_calc:.12g}\t{residual:.12g}\t{cp_converged}".format(
                        target=point[self.target_field],
                        residual=point[residual_field],
                        **point,
                    )
                )
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
            stages = [
                StageRecord(
                    name=f"potential_{point['index']:04d}",
                    status="complete",
                    converged=bool(point["cp_converged"]),
                    role="potential_point",
                    criterion="constant_potential",
                    iteration=int(point["cp_iterations"]),
                    measured=(
                        {"residual_mu_eV": float(point["residual_mu_eV"])}
                        if self.energy_boundary == "compensated_gate"
                        else {"residual_v": float(point["residual_v"])}
                    ),
                    measured_unit=("eV" if self.energy_boundary == "compensated_gate" else "V"),
                ).to_manifest()
                for point in points
            ]
            stages.append(
                StageRecord(
                    name="constant_potential",
                    status="complete",
                    converged=True,
                    role="final",
                    criterion="constant_potential",
                    measured={"completed_points": float(len(points))},
                    measured_unit="count",
                ).to_manifest()
            )
            write_artifact_manifest(
                self.artifact_manifest,
                workflow="constant_potential",
                artifacts=self._artifact_list(points),
                stages=stages,
                metadata={
                    "status": "complete",
                    "point_count": len(points),
                    "energy_boundary": self.energy_boundary,
                    ("target_mu_values_ev" if self.energy_boundary == "compensated_gate" else "targets_v"): self.targets,
                    "analysis": analysis,
                },
            )
            if final_atoms is not None:
                write(self.directory / "final_structure.traj", final_atoms)
            return final_atoms
        except Exception as exc:
            self._write_json(
                self.results_file,
                {
                    "schema": "atst-constant-potential-result-v1",
                    "workflow": "constant_potential",
                    "status": "failed",
                    "energy_boundary": self.energy_boundary,
                    ("target_mu_values_ev" if self.energy_boundary == "compensated_gate" else "targets_v"): self.targets,
                    "points": points,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            self._write_failure_manifest(points, exc)
            if isinstance(exc, ConstantPotentialError):
                raise
            raise


__all__ = ["ConstantPotentialWorkflow"]
