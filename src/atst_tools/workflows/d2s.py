"""Double-ended to single-ended transition-state workflow."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict

import numpy as np
from ase.io import read, write
from ase.mep.neb import DyNEB
from ase.optimize import FIRE, QuasiNewton

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.utils.idpp import Fast_IDPPSolver
from atst_tools.utils.io import read_structure


class D2SWorkflow:
    """
    Double-ended to single-ended workflow.

    The workflow performs endpoint optimization, rough DyNEB, then refines the
    highest-energy image with Dimer or Sella.
    """

    def __init__(self, config: Dict[str, Any], calc_name: str, calc_config: Dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.method = calc_config.get("method", "dimer").lower()
        self.neb_config = calc_config.get("neb", {})
        self.single_config = calc_config.get(self.method, {})
        self.base_directory = self._base_directory()
        self.restart = calc_config.get("restart", False)

        if self.method not in {"dimer", "sella"}:
            raise ValueError("D2S method must be 'dimer' or 'sella'")

    def _base_directory(self) -> str:
        if "calculator" in self.config:
            calc_section = self.config.get("calculator", {}).get(self.calc_name, {})
            return self.calc_config.get("directory", calc_section.get("directory", "run_d2s"))
        return self.calc_config.get("directory", "run_d2s")

    def _get_calc(self, sub_dir: str):
        directory = os.path.join(self.base_directory, sub_dir)
        return CalculatorFactory.get_calculator(
            self.calc_name,
            self.config,
            directory=directory,
        )

    def optimize_endpoints(self, init_atoms, final_atoms):
        print("=== Step 1: Optimizing Endpoints ===")
        fmax = self.calc_config.get("endpoint_fmax", 0.05)
        max_steps = self.calc_config.get("endpoint_max_steps", 200)

        if self.restart and os.path.exists("IS_opt.traj"):
            init_atoms = read("IS_opt.traj", index=-1)
        else:
            init_atoms.calc = self._get_calc("IS_OPT")
            opt_is = QuasiNewton(init_atoms, logfile="opt_is.log")
            opt_is.run(fmax=fmax, steps=max_steps)
            write("IS_opt.traj", init_atoms)

        if self.restart and os.path.exists("FS_opt.traj"):
            final_atoms = read("FS_opt.traj", index=-1)
        else:
            final_atoms.calc = self._get_calc("FS_OPT")
            opt_fs = QuasiNewton(final_atoms, logfile="opt_fs.log")
            opt_fs.run(fmax=fmax, steps=max_steps)
            write("FS_opt.traj", final_atoms)

        return init_atoms, final_atoms

    def run_rough_neb(self, init_atoms, final_atoms):
        print("=== Step 2: Running Rough NEB ===")
        if self.restart and os.path.exists("neb_rough.traj"):
            all_images = read("neb_rough.traj", index=":")
            return all_images[-(self.neb_config.get("n_images", 8) + 2):]

        n_images = self.neb_config.get("n_images", 8)
        fmax = self.neb_config.get("fmax", 0.8)
        algorism = self.neb_config.get("algorism", "improvedtangent")
        climb = self.neb_config.get("climb", True)
        max_steps = self.neb_config.get("max_steps", 200)

        solver = Fast_IDPPSolver.from_endpoints(init_atoms, final_atoms, n_images)
        images = solver.run()

        images[0].calc = self._get_calc("NEB/endpoint_initial")
        images[-1].calc = self._get_calc("NEB/endpoint_final")
        for index, image in enumerate(images[1:-1], start=1):
            image.calc = self._get_calc(f"NEB/image_{index:03d}")

        neb = DyNEB(
            images,
            climb=climb,
            dynamic_relaxation=True,
            fmax=fmax,
            method=algorism,
            parallel=False,
            allow_shared_calculator=self.calc_name in {"dp", "deepmd"},
        )
        opt = FIRE(neb, trajectory="neb_rough.traj")
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
            dimer_traj = dimer_config.get("trajectory", "dimer.traj")
            if self.restart and os.path.exists(dimer_traj):
                print(f"=== Dimer trajectory exists ({dimer_traj}); skipping single-ended step ===")
                return
            dimer = AbacusDimer(
                ts_guess,
                self.config,
                self.calc_name,
                dimer_config,
                traj_file=dimer_traj,
                init_eigenmode_method=dimer_config.get(
                    "init_eigenmode_method", "displacement"
                ),
                displacement_vector=disp_vec,
                dimer_separation=dimer_config.get("dimer_separation", 0.01),
                max_num_rot=dimer_config.get("max_num_rot", 3),
            )
            dimer.run(
                fmax=dimer_config.get("fmax", 0.05),
                max_steps=dimer_config.get("max_steps"),
            )
            return

        sella_config = self._single_config_with_directory("SELLA")
        sella_traj = sella_config.get("trajectory", "sella.traj")
        if self.restart and os.path.exists(sella_traj):
            print(f"=== Sella trajectory exists ({sella_traj}); skipping single-ended step ===")
            return
        sella = AbacusSella(
            ts_guess,
            self.config,
            self.calc_name,
            sella_config,
            traj_file=sella_traj,
            sella_eta=sella_config.get("eta", 0.005),
            fmax=sella_config.get("fmax", 0.05),
        )
        sella.run()

    def run(self):
        init_file = self.calc_config.get("init_file")
        final_file = self.calc_config.get("final_file")
        if not init_file or not final_file:
            raise ValueError("D2S workflow requires 'init_file' and 'final_file'")

        init_atoms = read_structure(init_file)
        final_atoms = read_structure(final_file)
        init_atoms, final_atoms = self.optimize_endpoints(init_atoms, final_atoms)

        neb_chain = self.run_rough_neb(init_atoms, final_atoms)

        print("=== Step 3: Analyzing Rough NEB ===")
        energies = [image.get_potential_energy() for image in neb_chain]
        max_idx = int(np.argmax(energies))
        ts_guess = neb_chain[max_idx].copy()
        print(f"  Highest energy image index: {max_idx}")

        self.run_single_ended(neb_chain, max_idx, ts_guess)
        print("=== D2S Workflow Finished ===")
