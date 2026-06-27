"""Experimental Direct MaxFlux workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import write

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.io import read_structure


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


class DMFWorkflow:
    """Run the experimental Direct MaxFlux path optimizer."""

    def __init__(self, config: dict[str, Any], calc_name: str, calc_config: dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)
        self.base_directory = self._base_directory()

    def _base_directory(self) -> str:
        calc_section = self.config.get("calculator", {}).get(self.calc_name, {})
        return self.calc_config.get("directory", calc_section.get("directory", "dmf_run"))

    def _get_calc(self, index: int):
        kwargs: dict[str, Any] = {"directory": f"{self.base_directory}/image_{index:03d}"}
        if is_dp_calculator(self.calc_name):
            kwargs["shared"] = False
        return CalculatorFactory.get_calculator(self.calc_name, self.config, **kwargs)

    def _load_pydmf(self):
        try:
            from atst_tools.external.pydmf.dmf import DirectMaxFlux, interpolate_fbenm
        except ImportError as exc:
            if getattr(exc, "name", None) == "cyipopt" or "cyipopt" in str(exc):
                raise RuntimeError(
                    "DMF requires cyipopt/IPOPT. Install them in the active environment, "
                    "for example: conda install -c conda-forge cyipopt ipopt"
                ) from exc
            raise
        return DirectMaxFlux, interpolate_fbenm

    def _validate_pbc(self, init_atoms: Atoms, final_atoms: Atoms) -> None:
        if not (init_atoms.pbc.any() or final_atoms.pbc.any()):
            return

        mode = self.calc_config["pbc_mode"]
        if mode == "reject":
            raise ValueError(
                "DMF pbc_mode=reject refuses periodic endpoints because MIC/fractional-coordinate support is not validated. "
                "Use pbc_mode=cartesian_unwrapped with confirm_pbc_risk=true only for pre-unwrapped fixed-cell inputs."
            )
        if not np.array_equal(init_atoms.pbc, final_atoms.pbc):
            raise ValueError("DMF pbc_mode=cartesian_unwrapped requires identical endpoint PBC flags")
        if not np.allclose(init_atoms.cell.array, final_atoms.cell.array):
            raise ValueError("DMF pbc_mode=cartesian_unwrapped requires identical endpoint cells")
        if self.calc_config["remove_rotation_and_translation"]:
            raise ValueError(
                "DMF pbc_mode=cartesian_unwrapped requires remove_rotation_and_translation=false"
            )
        if not self.calc_config["confirm_pbc_risk"]:
            raise ValueError("DMF pbc_mode=cartesian_unwrapped requires confirm_pbc_risk=true")

    def _ipopt_options(self) -> dict[str, Any]:
        ipopt_options = dict(self.calc_config.get("ipopt_options", {}))
        if isinstance(self.calc_config["tol"], float):
            ipopt_options.setdefault("tol", self.calc_config["tol"])
        return ipopt_options

    def _build_initial_path(self, ref_images, DirectMaxFlux, interpolate_fbenm, ipopt_options):
        common = {
            "nsegs": self.calc_config["nsegs"],
            "dspl": self.calc_config["dspl"],
            "nmove": self.calc_config["nmove"],
            "remove_rotation_and_translation": self.calc_config["remove_rotation_and_translation"],
            "parallel": self.calc_config["parallel"],
            "update_teval": self.calc_config["update_teval"],
        }
        beta = self.calc_config.get("beta")
        if beta is not None:
            common["beta"] = beta

        initial_path = self.calc_config["initial_path"]
        if initial_path == "linear":
            return DirectMaxFlux(ref_images, calc_factory=self._get_calc, **common)

        fbenm_result = interpolate_fbenm(
            ref_images,
            nmove=self.calc_config["nmove"],
            correlated=(initial_path == "cfbenm"),
            dmf_options={
                "nsegs": self.calc_config["nsegs"],
                "dspl": self.calc_config["dspl"],
                "remove_rotation_and_translation": self.calc_config["remove_rotation_and_translation"],
            },
            ipopt_options=ipopt_options,
        )
        return DirectMaxFlux(ref_images, coefs=fbenm_result.coefs, calc_factory=self._get_calc, **common)

    def _candidate_from_history(self, dmf) -> tuple[float | None, Atoms]:
        tmax_values = getattr(dmf.history, "tmax", [])
        tmax_images = getattr(dmf.history, "images_tmax", [])
        if tmax_images:
            return float(tmax_values[-1]) if tmax_values else None, tmax_images[-1].copy()

        energies = []
        for image in dmf.images:
            try:
                energies.append(float(image.get_potential_energy()))
            except Exception:
                energies.append(float("nan"))
        finite = [index for index, energy in enumerate(energies) if np.isfinite(energy)]
        if not finite:
            return None, dmf.images[len(dmf.images) // 2].copy()
        max_idx = max(finite, key=lambda index: energies[index])
        tmax = max_idx / max(len(dmf.images) - 1, 1)
        return float(tmax), dmf.images[max_idx].copy()

    def _evaluate_candidate(self, candidate: Atoms, index: int) -> dict[str, float | None]:
        evaluated = candidate.copy()
        evaluated.calc = self._get_calc(index)
        energy = float(evaluated.get_potential_energy())
        forces = np.asarray(evaluated.get_forces(), dtype=float)
        candidate.calc = SinglePointCalculator(candidate, energy=energy, forces=forces)
        return {
            "energy": energy,
            "fmax": float(np.linalg.norm(forces, axis=1).max()) if len(forces) else 0.0,
        }

    def _final_t_eval(self, dmf) -> list[float] | None:
        t_eval = getattr(dmf, "t_eval", None)
        if t_eval is None:
            return None
        values = np.asarray(t_eval, dtype=float).ravel()
        return [float(value) for value in values]

    def run(self) -> dict[str, Any]:
        """Execute DMF and write path, candidate, summary, and manifest artifacts."""
        init_atoms = read_structure(self.calc_config["init_file"])
        final_atoms = read_structure(self.calc_config["final_file"])
        self._validate_pbc(init_atoms, final_atoms)

        DirectMaxFlux, interpolate_fbenm = self._load_pydmf()
        ipopt_options = self._ipopt_options()
        dmf = self._build_initial_path([init_atoms, final_atoms], DirectMaxFlux, interpolate_fbenm, ipopt_options)
        if ipopt_options:
            dmf.add_ipopt_options(ipopt_options)
        _, info = dmf.solve(tol=self.calc_config["tol"])

        trajectory = self.calc_config["trajectory"]
        tmax_trajectory = self.calc_config["tmax_trajectory"]
        Path(trajectory).parent.mkdir(parents=True, exist_ok=True)
        Path(tmax_trajectory).parent.mkdir(parents=True, exist_ok=True)
        write(trajectory, dmf.images)
        tmax, candidate = self._candidate_from_history(dmf)
        candidate_results = self._evaluate_candidate(candidate, len(dmf.images))
        write(tmax_trajectory, candidate)

        summary = {
            "workflow": "dmf",
            "experimental": True,
            "result_type": "ts_candidate",
            "validated_ts": False,
            "initial_path": self.calc_config["initial_path"],
            "pbc_mode": self.calc_config["pbc_mode"],
            "confirm_pbc_risk": self.calc_config["confirm_pbc_risk"],
            "remove_rotation_and_translation": self.calc_config["remove_rotation_and_translation"],
            "nmove": self.calc_config["nmove"],
            "n_images": len(dmf.images),
            "t_eval": self._final_t_eval(dmf),
            "tmax": tmax,
            "tmax_candidate": candidate_results,
            "ipopt_status": info,
            "ipopt_options": self.calc_config.get("ipopt_options", {}),
            "outputs": {
                "trajectory": trajectory,
                "tmax_trajectory": tmax_trajectory,
            },
        }
        summary_file = Path(self.calc_config["summary_file"])
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(_json_ready(summary), indent=2), encoding="utf-8")

        write_artifact_manifest(
            self.calc_config["artifact_manifest"],
            workflow="dmf",
            artifacts=[
                {"role": "evaluation_path", "path": trajectory},
                {"role": "tmax_candidate", "path": tmax_trajectory},
                {"role": "summary", "path": str(summary_file)},
            ],
            stages=[
                {"name": "initial_path", "status": "complete", "method": self.calc_config["initial_path"]},
                {"name": "direct_maxflux", "status": "complete", "tol": self.calc_config["tol"]},
            ],
            metadata={
                "experimental": True,
                "result_type": "ts_candidate",
                "validated_ts": False,
                "pbc_mode": self.calc_config["pbc_mode"],
            },
        )
        return summary
