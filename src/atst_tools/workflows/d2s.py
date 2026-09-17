"""Double-ended to single-ended transition-state workflow."""

from __future__ import annotations

import os
import json
from copy import deepcopy
from typing import Any, Dict

import numpy as np
from ase.io import read, write
from ase.mep.neb import DyNEB
from ase.optimize import FIRE, QuasiNewton
from ase.vibrations import Vibrations

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.mep.ccqn import AbacusCCQN
from atst_tools.utils.analysis import get_displacement_analysis
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.convergence import (
    StageRecord,
    as_finite_float,
    as_step_count,
)
from atst_tools.utils.idpp import Fast_IDPPSolver
from atst_tools.utils.io import read_structure
from atst_tools.utils.neb_endpoints import (
    ENDPOINT_COMPUTED,
    ENDPOINT_OPTIMIZED,
    ENDPOINT_PROVIDED,
    endpoint_policy,
    ensure_neb_endpoint_results,
    freeze_current_results,
    freeze_results,
    get_endpoint_results,
    has_endpoint_results,
)
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band
from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.ts_validation import build_ts_validation_summary
from atst_tools.workflows.dmf import DMFWorkflow


def _stage_payload(record: Any) -> dict[str, Any]:
    """Return a manifest-ready stage dict for a stage record or a legacy dict.

    Args:
        record: A :class:`StageRecord` or an already manifest-shaped mapping,
            for example the experimental DMF rough record.

    Returns:
        The stage as a JSON-safe dict.
    """
    return record.to_manifest() if isinstance(record, StageRecord) else record


class D2SWorkflow:
    """
    Double-ended to single-ended workflow.

    The workflow performs endpoint optimization, rough DyNEB, then refines the
    highest-energy image with Dimer, Sella, or CCQN.
    """

    def __init__(self, config: Dict[str, Any], calc_name: str, calc_config: Dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.method = calc_config["method"].lower()
        self.rough_method = calc_config.get("rough_method", "neb").lower()
        self.neb_config = calc_config["neb"]
        self.dmf_config = calc_config["dmf"]
        self.single_config = calc_config[self.method]
        self.base_directory = self._base_directory()
        self.restart = calc_config["restart"]
        self._rough_stage_artifacts: list[dict[str, Any]] = []
        self._rough_stage_record = {"name": "rough_neb", "status": "complete"}
        self._rough_ts_guess = None
        self._rough_candidate_index = None
        self._single_ended_stage_record: StageRecord | None = None

        if self.method not in {"dimer", "sella", "ccqn"}:
            raise ValueError("D2S method must be 'dimer', 'sella', or 'ccqn'")
        if self.rough_method not in {"neb", "dmf"}:
            raise ValueError("D2S rough_method must be 'neb' or 'dmf'")

    def _base_directory(self) -> str:
        if "calculator" in self.config:
            calc_section = self.config.get("calculator", {}).get(self.calc_name, {})
            return self.calc_config.get("directory", calc_section.get("directory", self.calc_config["directory"]))
        return self.calc_config["directory"]

    def _get_calc(self, sub_dir: str, shared: bool | None = None):
        directory = os.path.join(self.base_directory, sub_dir)
        kwargs = {"directory": directory}
        if is_dp_calculator(self.calc_name) and shared is not None:
            kwargs["shared"] = shared
        return CalculatorFactory.get_calculator(self.calc_name, self.config, **kwargs)

    def _endpoint_optimization_config(self) -> Dict[str, Any]:
        return dict(self.calc_config["endpoint_optimization"])

    def _optimize_one_endpoint(
        self,
        atoms,
        calc_dir: str,
        traj_file: str,
        logfile: str,
        fmax: float,
        max_steps: int,
        label: str,
    ) -> StageRecord:
        """Relax one NEB endpoint and report its optimizer-owned facts.

        Args:
            atoms: Endpoint structure relaxed in place.
            calc_dir: Calculator working directory below the workflow base directory.
            traj_file: Trajectory file written for the relaxed endpoint.
            logfile: Optimizer log file.
            fmax: Configured force threshold.
            max_steps: Configured step budget.
            label: Endpoint identity used in the stage name, ``initial`` or ``final``.

        Returns:
            The :class:`StageRecord` for this endpoint, carrying the
            ``opt.run()`` return value and the observed step count.
        """
        atoms.calc = self._get_calc(calc_dir)
        opt = QuasiNewton(atoms, logfile=logfile)
        converged_signal = opt.run(fmax=fmax, steps=max_steps)
        freeze_current_results(atoms, status=ENDPOINT_OPTIMIZED)
        write(traj_file, atoms)
        return StageRecord(
            name=f"endpoint_{label}_relax",
            role="endpoint",
            criterion="ase_optimizer",
            converged=converged_signal,
            fmax=as_finite_float(fmax),
            steps=as_step_count(max_steps),
            actual_steps=as_step_count(getattr(opt, "nsteps", None)),
        )

    @staticmethod
    def _skipped_endpoint_record(label: str) -> StageRecord:
        """Return the record for an endpoint whose optimization was skipped.

        Args:
            label: Endpoint identity used in the stage name, ``initial`` or ``final``.

        Returns:
            A record with ``status="skipped"`` and no optimizer-owned facts,
            because no optimizer ran for that endpoint in this invocation.
        """
        return StageRecord(
            name=f"endpoint_{label}_relax",
            role="endpoint",
            criterion="ase_optimizer",
            status="skipped",
        )

    def optimize_endpoints(self, init_atoms, final_atoms):
        """Optimize or validate both NEB endpoints and report their stages.

        An endpoint skipped by restart or by ``skip_if_has_results`` gets a
        record with ``status="skipped"`` and no optimizer-owned facts, because
        no optimizer ran for it.  Endpoints receive no convergence advisory of
        their own.

        Args:
            init_atoms: Initial-state endpoint.
            final_atoms: Final-state endpoint.

        Returns:
            A ``(init_atoms, final_atoms, records)`` tuple, where ``records``
            holds one :class:`StageRecord` per endpoint in ``initial``/``final``
            order, or the legacy disabled-stage dict when endpoint optimization
            is switched off.
        """
        endpoint_config = self._endpoint_optimization_config()
        fmax = endpoint_config["fmax"]
        max_steps = endpoint_config["max_steps"]

        if not endpoint_config["enabled"]:
            print("=== Step 1: Endpoint optimization disabled; validating endpoint results ===")
            endpoints = [init_atoms, final_atoms]
            ensure_neb_endpoint_results(
                endpoints,
                lambda directory: self._get_calc(directory),
                policy=endpoint_policy(self.calc_config, default="auto"),
                directories=("IS_SP", "FS_SP"),
                context="D2S",
            )
            return endpoints[0], endpoints[-1], [{"name": "endpoint_optimization", "status": "skipped"}]

        print("=== Step 1: Optimizing Endpoints ===")
        skip_if_has_results = endpoint_config["skip_if_has_results"]
        records: list[StageRecord] = []

        if self.restart and os.path.exists("IS_opt.traj"):
            init_atoms = get_last_frame("IS_opt.traj")
            records.append(self._skipped_endpoint_record("initial"))
        elif skip_if_has_results and has_endpoint_results(init_atoms):
            print("=== Initial endpoint already has energy/force results; skipping endpoint optimization ===")
            records.append(self._skipped_endpoint_record("initial"))
        else:
            records.append(
                self._optimize_one_endpoint(
                    init_atoms,
                    "IS_OPT",
                    "IS_opt.traj",
                    "opt_is.log",
                    fmax,
                    max_steps,
                    "initial",
                )
            )

        if self.restart and os.path.exists("FS_opt.traj"):
            final_atoms = get_last_frame("FS_opt.traj")
            records.append(self._skipped_endpoint_record("final"))
        elif skip_if_has_results and has_endpoint_results(final_atoms):
            print("=== Final endpoint already has energy/force results; skipping endpoint optimization ===")
            records.append(self._skipped_endpoint_record("final"))
        else:
            records.append(
                self._optimize_one_endpoint(
                    final_atoms,
                    "FS_OPT",
                    "FS_opt.traj",
                    "opt_fs.log",
                    fmax,
                    max_steps,
                    "final",
                )
            )

        return init_atoms, final_atoms, records

    def run_rough_neb(self, init_atoms, final_atoms):
        """Run the rough DyNEB stage and record the FIRE optimizer's facts.

        The ``FIRE.run()`` return value is kept as the stage's convergence
        signal.  A restart that reuses ``neb_rough.traj`` reports
        ``status="skipped"`` with an unknown convergence signal, because no
        optimizer ran in this invocation.

        Args:
            init_atoms: Optimized initial-state endpoint.
            final_atoms: Optimized final-state endpoint.

        Returns:
            The rough NEB band images.
        """
        print("=== Step 2: Running Rough NEB ===")
        self._rough_stage_artifacts = [{"role": "rough_neb_trajectory", "path": "neb_rough.traj"}]
        self._rough_ts_guess = None
        self._rough_candidate_index = None
        if self.restart and os.path.exists("neb_rough.traj"):
            self._rough_stage_record = StageRecord(
                name="rough_neb",
                role="rough",
                criterion="neb_fmax",
                status="skipped",
                converged=None,
            )
            return get_last_neb_band("neb_rough.traj", self.neb_config["n_images"] + 2)

        n_images = self.neb_config["n_images"]
        fmax = self.neb_config["fmax"]
        algorism = self.neb_config["algorism"]
        climb = self.neb_config["climb"]
        scale_fmax = self.neb_config["scale_fmax"]
        max_steps = self.neb_config["max_steps"]

        input_endpoint_results = []
        for atoms in (init_atoms, final_atoms):
            results = get_endpoint_results(atoms)
            input_endpoint_results.append(
                (
                    results[0],
                    results[1],
                    atoms.info.get("atst_endpoint_result"),
                )
                if results is not None
                else None
            )

        solver = Fast_IDPPSolver.from_endpoints(init_atoms, final_atoms, n_images)
        images = solver.run(
            maxiter=self.neb_config["idpp_maxiter"],
            tol=self.neb_config["idpp_tol"],
        )
        for index, cached in zip((0, -1), input_endpoint_results):
            if cached is not None:
                energy, forces, status = cached
                freeze_results(images[index], energy, forces, status=status)

        ensure_neb_endpoint_results(
            images,
            lambda directory: self._get_calc(f"NEB/{directory}"),
            policy=endpoint_policy(self.calc_config, default="auto"),
            directories=("endpoint_initial", "endpoint_final"),
            context="D2S rough DyNEB",
        )
        for index, cached in zip((0, -1), input_endpoint_results):
            if cached is not None:
                energy, forces, status = cached
                if status in {ENDPOINT_PROVIDED, ENDPOINT_COMPUTED, ENDPOINT_OPTIMIZED}:
                    freeze_results(images[index], energy, forces, status=status)
        allow_shared = should_share_calculator(self.calc_name, self.config, parallel=False)
        shared_calc = self._get_calc("NEB/shared", shared=True) if allow_shared else None
        for index, image in enumerate(images[1:-1], start=1):
            image.calc = shared_calc or self._get_calc(f"NEB/image_{index:03d}")

        neb = DyNEB(
            images,
            climb=climb,
            dynamic_relaxation=True,
            fmax=fmax,
            method=algorism,
            parallel=False,
            scale_fmax=scale_fmax,
            allow_shared_calculator=allow_shared,
        )
        opt = FIRE(neb, trajectory="neb_rough.traj", **self.neb_config.get("optimizer_kwargs", {}))
        converged_signal = opt.run(fmax=fmax, steps=max_steps)
        self._rough_stage_record = StageRecord(
            name="rough_neb",
            role="rough",
            criterion="neb_fmax",
            converged=converged_signal,
            fmax=as_finite_float(fmax),
            steps=as_step_count(max_steps),
            actual_steps=as_step_count(getattr(opt, "nsteps", None)),
        )
        return images

    def _dmf_candidate_index(self, summary: dict[str, Any], chain_length: int) -> int | None:
        tmax = summary.get("tmax")
        if tmax is None or chain_length <= 0:
            return None

        tmax_value = float(tmax)
        t_eval = summary.get("t_eval")
        if t_eval is not None and len(t_eval) == chain_length:
            values = np.asarray(t_eval, dtype=float)
            if values.shape == (chain_length,) and np.all(np.isfinite(values)):
                return int(np.argmin(np.abs(values - tmax_value)))

        index = int(round(tmax_value * max(chain_length - 1, 0)))
        return min(max(index, 0), chain_length - 1)

    def run_rough_dmf(self, init_atoms, final_atoms):
        """Run the experimental DMF rough stage and return the sampled path."""
        print("=== Step 2: Running Rough DMF (experimental) ===")
        dmf_config = deepcopy(self.dmf_config)
        dmf_config["type"] = "dmf"
        dmf_config.setdefault("init_file", "dmf_endpoint_initial.traj")
        dmf_config.setdefault("final_file", "dmf_endpoint_final.traj")

        for key in ("init_file", "final_file", "trajectory", "tmax_trajectory", "summary_file", "artifact_manifest"):
            parent = os.path.dirname(dmf_config[key])
            if parent:
                os.makedirs(parent, exist_ok=True)

        write(dmf_config["init_file"], init_atoms)
        write(dmf_config["final_file"], final_atoms)

        summary = DMFWorkflow(self.config, self.calc_name, dmf_config).run()
        chain = read(dmf_config["trajectory"], index=":")
        self._rough_ts_guess = read(dmf_config["tmax_trajectory"])
        tmax = summary.get("tmax")
        self._rough_candidate_index = self._dmf_candidate_index(summary, len(chain))
        self._rough_stage_artifacts = [
            {"role": "dmf_path", "path": dmf_config["trajectory"]},
            {"role": "dmf_candidate", "path": dmf_config["tmax_trajectory"]},
            {"role": "dmf_summary", "path": dmf_config["summary_file"]},
            {"role": "dmf_artifact_manifest", "path": dmf_config["artifact_manifest"]},
        ]
        self._rough_stage_record = {
            "name": "rough_dmf",
            "status": "complete",
            "experimental": True,
            "tmax": tmax,
        }
        return chain

    def _single_config_with_directory(self, dirname: str) -> Dict[str, Any]:
        """Return the refinement configuration with an explicit directory.

        Args:
            dirname: Refinement subdirectory used as the fallback directory.

        Returns:
            A deep copy of the configured refinement block.
        """
        config = deepcopy(self.single_config)
        config.setdefault("directory", os.path.join(self.base_directory, dirname))
        return config

    def run_single_ended(self, neb_chain, max_idx: int, ts_guess):
        """Run the single-ended refinement and record its convergence facts.

        The refinement's own stage record is reused when the constituent
        exposes one, so no advisory is emitted a second time from D2S.  Restart
        skips report ``status="skipped"`` with an unknown convergence signal.

        Args:
            neb_chain: Rough NEB band images.
            max_idx: Index of the highest-energy rough image.
            ts_guess: Transition-state guess handed to the refinement.

        Returns:
            Path of the refinement trajectory.
        """
        print(f"=== Step 4: Running Single-Ended Search ({self.method.upper()}) ===")

        if self.method == "dimer":
            idx_before = max(0, max_idx - 1)
            idx_after = min(len(neb_chain) - 1, max_idx + 1)
            vec = neb_chain[idx_before].positions - neb_chain[idx_after].positions
            norm = np.linalg.norm(vec)
            disp_vec = None if norm < 1e-3 else vec / norm * 0.01
            dimer_config = self._single_config_with_directory("DIMER")
            dimer_traj = dimer_config["trajectory"]
            if self.restart and os.path.exists(dimer_traj):
                print(f"=== Dimer trajectory exists ({dimer_traj}); skipping single-ended step ===")
                self._single_ended_stage_record = StageRecord(
                    name="dimer",
                    role="final",
                    criterion="dimer",
                    status="skipped",
                    converged=None,
                )
                return dimer_traj
            dimer = AbacusDimer(
                ts_guess,
                self.config,
                self.calc_name,
                dimer_config,
                traj_file=dimer_traj,
                init_eigenmode_method=dimer_config["init_eigenmode_method"],
                displacement_vector=disp_vec,
                dimer_separation=dimer_config["dimer_separation"],
                max_num_rot=dimer_config["max_num_rot"],
            )
            dimer.run(
                fmax=dimer_config["fmax"],
                max_steps=dimer_config.get("max_steps"),
            )
            # Dimer exposes no optimizer termination signal, so convergence
            # stays unknown instead of being invented.
            self._single_ended_stage_record = StageRecord(
                name="dimer",
                role="final",
                criterion="dimer",
                converged=None,
            )
            return dimer_traj

        if self.method == "ccqn":
            ccqn_config = self._single_config_with_directory("CCQN")
            # D2S owns the top-level manifest, so the nested CCQN refinement
            # must not write one of its own.
            ccqn_config["artifact_manifest"] = None
            ccqn_traj = ccqn_config["trajectory"]
            if self.restart and os.path.exists(ccqn_traj):
                print(f"=== CCQN trajectory exists ({ccqn_traj}); skipping single-ended step ===")
                self._single_ended_stage_record = StageRecord(
                    name="ccqn",
                    role="final",
                    status="skipped",
                    converged=None,
                )
                return ccqn_traj
            product_atoms = None
            if ccqn_config.get("e_vector_method", "interp") == "interp":
                idx_after = min(len(neb_chain) - 1, max_idx + 1)
                idx_before = max(0, max_idx - 1)
                ref_idx = idx_after if idx_after != max_idx else idx_before
                product_atoms = neb_chain[ref_idx].copy()
                product_atoms.set_cell(ts_guess.get_cell())
                product_atoms.set_pbc(ts_guess.get_pbc())
            ccqn = AbacusCCQN(
                ts_guess,
                self.config,
                self.calc_name,
                ccqn_config,
                traj_file=ccqn_traj,
                product_atoms=product_atoms,
            )
            ccqn.run()
            self._single_ended_stage_record = getattr(ccqn, "last_stage_record", None)
            return ccqn_traj

        sella_config = self._single_config_with_directory("SELLA")
        sella_traj = sella_config["trajectory"]
        if self.restart and os.path.exists(sella_traj):
            print(f"=== Sella trajectory exists ({sella_traj}); skipping single-ended step ===")
            self._single_ended_stage_record = StageRecord(
                name="sella",
                role="final",
                status="skipped",
                converged=None,
            )
            return sella_traj
        sella = AbacusSella(
            ts_guess,
            self.config,
            self.calc_name,
            sella_config,
            traj_file=sella_traj,
            sella_eta=sella_config["eta"],
            fmax=sella_config["fmax"],
        )
        sella.run()
        self._single_ended_stage_record = getattr(sella, "last_stage_record", None)
        return sella_traj

    def _vibration_indices(self, neb_chain, vib_config):
        indices = vib_config["indices"]
        if indices in (None, "auto"):
            if self._rough_candidate_index is not None:
                return self._displacement_indices_at(neb_chain, self._rough_candidate_index, vib_config["threshold"])
            _, selected, _ = get_displacement_analysis(
                neb_chain,
                thr=vib_config["threshold"],
            )
            return selected
        if indices == "all":
            return None
        return indices

    def _displacement_indices_at(self, chain, index: int, threshold: float):
        if len(chain) < 2:
            return []
        idx_before = max(0, index - 1)
        idx_after = min(len(chain) - 1, index + 1)
        if idx_before == idx_after:
            return []
        displacement = chain[idx_before].positions - chain[idx_after].positions
        length = np.linalg.norm(displacement)
        if length < 1e-6:
            return []
        magnitudes = np.linalg.norm(displacement, axis=1) / length
        return [int(atom_index) for atom_index, value in enumerate(magnitudes) if value > threshold]

    def run_vibration(self, neb_chain, ts_guess, single_traj):
        """Run the optional D2S vibration stage."""
        vib_config = self.calc_config["vibration"]
        if not vib_config["enabled"]:
            return

        print("=== Step 5: Running Optional Vibration Analysis ===")
        if single_traj and os.path.exists(single_traj):
            atoms = read(single_traj, index=-1)
        else:
            atoms = ts_guess.copy()

        atoms.calc = self._get_calc(vib_config["directory"])
        indices = self._vibration_indices(neb_chain, vib_config)
        name = vib_config["name"]
        vib = Vibrations(
            atoms,
            indices=indices,
            delta=vib_config["delta"],
            nfree=vib_config["nfree"],
            name=name,
        )
        vib.run()
        vib.summary()

        energies = vib.get_energies()
        frequencies = vib.get_frequencies()
        zpe = vib.get_zero_point_energy()
        thermo = compute_vibration_thermochemistry(atoms, energies, vib_config, zpe)
        results = {
            "frequencies": frequencies.real.tolist(),
            "imaginary_frequencies": frequencies.imag.tolist(),
            "zpe": float(zpe),
            "indices": indices,
            "thermo": thermo,
        }
        output = vib_config["results_file"]
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=4)
        validation = build_ts_validation_summary(results, source=output)
        validation_file = vib_config.get("validation_file", "d2s_ts_validation.json")
        with open(validation_file, "w", encoding="utf-8") as handle:
            json.dump(validation, handle, indent=4)
        print(f"Wrote {output}")

    def run(self):
        """Run the full D2S workflow and persist its truthful stage facts.

        The manifest records one stage per performed step: endpoint
        optimization, rough path, single-ended refinement and the optional
        vibration analysis.  Artifacts, prints, return value and exit semantics
        are unchanged.
        """
        init_file = self.calc_config["init_file"]
        final_file = self.calc_config["final_file"]

        init_atoms = read_structure(init_file)
        final_atoms = read_structure(final_file)
        init_atoms, final_atoms, endpoint_records = self.optimize_endpoints(init_atoms, final_atoms)

        if self.rough_method == "dmf":
            neb_chain = self.run_rough_dmf(init_atoms, final_atoms)
        else:
            neb_chain = self.run_rough_neb(init_atoms, final_atoms)

        print("=== Step 3: Analyzing Rough NEB ===")
        if self.rough_method == "dmf" and self._rough_candidate_index is not None:
            max_idx = self._rough_candidate_index
        else:
            try:
                energies = [image.get_potential_energy() for image in neb_chain]
                max_idx = int(np.argmax(energies))
            except Exception:
                if self._rough_candidate_index is None:
                    raise
                max_idx = self._rough_candidate_index
        ts_guess = self._rough_ts_guess.copy() if self._rough_ts_guess is not None else neb_chain[max_idx].copy()
        print(f"  Highest energy image index: {max_idx}")

        single_traj = self.run_single_ended(neb_chain, max_idx, ts_guess)
        self.run_vibration(neb_chain, ts_guess, single_traj)
        artifacts = [*self._rough_stage_artifacts, {"role": "single_ended_trajectory", "path": single_traj}]
        vibration_config = self.calc_config.get("vibration", {})
        if vibration_config.get("enabled"):
            artifacts.append({"role": "vibration_results", "path": vibration_config["results_file"]})
            artifacts.append({"role": "ts_validation", "path": vibration_config.get("validation_file", "d2s_ts_validation.json")})
        single_ended_record = self._single_ended_stage_record
        if single_ended_record is None:
            # The refinement was handled by a caller-provided stub, so no
            # optimizer-owned fact is available for it.
            single_ended_record = {"name": self.method, "status": "complete"}
        write_artifact_manifest(
            self.calc_config.get("artifact_manifest", "atst_artifacts.json"),
            workflow="d2s",
            artifacts=artifacts,
            stages=[
                *(_stage_payload(record) for record in endpoint_records),
                _stage_payload(self._rough_stage_record),
                _stage_payload(single_ended_record),
                {"name": "vibration", "status": "complete" if vibration_config.get("enabled") else "skipped"},
            ],
        )
        print("=== D2S Workflow Finished ===")
