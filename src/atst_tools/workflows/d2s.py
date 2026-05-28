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
from atst_tools.utils.idpp import Fast_IDPPSolver
from atst_tools.utils.io import read_structure
from atst_tools.utils.neb_endpoints import (
    ENDPOINT_OPTIMIZED,
    endpoint_policy,
    ensure_neb_endpoint_results,
    freeze_current_results,
    freeze_results,
    get_endpoint_results,
    has_endpoint_results,
)
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band
from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry


class D2SWorkflow:
    """
    Double-ended to single-ended workflow.

    The workflow performs endpoint optimization, rough DyNEB, then refines the
    highest-energy image with Dimer or Sella.
    """

    def __init__(self, config: Dict[str, Any], calc_name: str, calc_config: Dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config if "config_version" in config else apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.method = calc_config["method"].lower()
        self.neb_config = calc_config["neb"]
        self.single_config = calc_config[self.method]
        self.base_directory = self._base_directory()
        self.restart = calc_config["restart"]

        if self.method not in {"dimer", "sella", "ccqn"}:
            raise ValueError("D2S method must be 'dimer', 'sella', or 'ccqn'")

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

    def _optimize_one_endpoint(self, atoms, calc_dir: str, traj_file: str, logfile: str, fmax: float, max_steps: int):
        atoms.calc = self._get_calc(calc_dir)
        opt = QuasiNewton(atoms, logfile=logfile)
        opt.run(fmax=fmax, steps=max_steps)
        freeze_current_results(atoms, status=ENDPOINT_OPTIMIZED)
        write(traj_file, atoms)
        return atoms

    def optimize_endpoints(self, init_atoms, final_atoms):
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
            return endpoints[0], endpoints[-1]

        print("=== Step 1: Optimizing Endpoints ===")
        skip_if_has_results = endpoint_config["skip_if_has_results"]

        if self.restart and os.path.exists("IS_opt.traj"):
            init_atoms = get_last_frame("IS_opt.traj")
        elif skip_if_has_results and has_endpoint_results(init_atoms):
            print("=== Initial endpoint already has energy/force results; skipping endpoint optimization ===")
        else:
            init_atoms = self._optimize_one_endpoint(
                init_atoms,
                "IS_OPT",
                "IS_opt.traj",
                "opt_is.log",
                fmax,
                max_steps,
            )

        if self.restart and os.path.exists("FS_opt.traj"):
            final_atoms = get_last_frame("FS_opt.traj")
        elif skip_if_has_results and has_endpoint_results(final_atoms):
            print("=== Final endpoint already has energy/force results; skipping endpoint optimization ===")
        else:
            final_atoms = self._optimize_one_endpoint(
                final_atoms,
                "FS_OPT",
                "FS_opt.traj",
                "opt_fs.log",
                fmax,
                max_steps,
            )

        return init_atoms, final_atoms

    def run_rough_neb(self, init_atoms, final_atoms):
        print("=== Step 2: Running Rough NEB ===")
        if self.restart and os.path.exists("neb_rough.traj"):
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
                    atoms.info.get("atst_endpoint_result", "provided"),
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
        opt.run(fmax=fmax, steps=max_steps)
        return images

    def _single_config_with_directory(self, dirname: str) -> Dict[str, Any]:
        config = deepcopy(self.single_config)
        config.setdefault("directory", os.path.join(self.base_directory, dirname))
        return config

    def run_single_ended(self, neb_chain, max_idx: int, ts_guess):
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
            return dimer_traj

        if self.method == "ccqn":
            ccqn_config = self._single_config_with_directory("CCQN")
            ccqn_traj = ccqn_config["trajectory"]
            if self.restart and os.path.exists(ccqn_traj):
                print(f"=== CCQN trajectory exists ({ccqn_traj}); skipping single-ended step ===")
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
            return ccqn_traj

        sella_config = self._single_config_with_directory("SELLA")
        sella_traj = sella_config["trajectory"]
        if self.restart and os.path.exists(sella_traj):
            print(f"=== Sella trajectory exists ({sella_traj}); skipping single-ended step ===")
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
        return sella_traj

    def _vibration_indices(self, neb_chain, vib_config):
        indices = vib_config["indices"]
        if indices in (None, "auto"):
            _, selected, _ = get_displacement_analysis(
                neb_chain,
                thr=vib_config["threshold"],
            )
            return selected
        if indices == "all":
            return None
        return indices

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
        print(f"Wrote {output}")

    def run(self):
        init_file = self.calc_config["init_file"]
        final_file = self.calc_config["final_file"]

        init_atoms = read_structure(init_file)
        final_atoms = read_structure(final_file)
        init_atoms, final_atoms = self.optimize_endpoints(init_atoms, final_atoms)

        neb_chain = self.run_rough_neb(init_atoms, final_atoms)

        print("=== Step 3: Analyzing Rough NEB ===")
        energies = [image.get_potential_energy() for image in neb_chain]
        max_idx = int(np.argmax(energies))
        ts_guess = neb_chain[max_idx].copy()
        print(f"  Highest energy image index: {max_idx}")

        single_traj = self.run_single_ended(neb_chain, max_idx, ts_guess)
        self.run_vibration(neb_chain, ts_guess, single_traj)
        print("=== D2S Workflow Finished ===")
