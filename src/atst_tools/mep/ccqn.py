"""Cone-shaped constrained quasi-Newton transition-state optimizer.

References:
    Wu, Y.; Wang, H. Cone-Shaped Constrained Quasi-Newton Method: Efficient
    and Robust Single-Ended Transition State Optimization Algorithm.
    J. Chem. Theory Comput. (2025).
    https://doi.org/10.1021/acs.jctc.5c01015
"""

from __future__ import annotations

import os
import json
from typing import Any

import numpy as np
from ase.geometry import find_mic
from ase.io import write
from ase.optimize.optimize import Optimizer
from scipy.linalg import eigh
from scipy.optimize import brentq, minimize

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.idpp import align_atom_indices
from atst_tools.utils.reactive_modes import enumerate_reactive_bond_modes


def parse_reactive_bonds(value: Any, natoms: int | None = None) -> list[tuple[int, int]]:
    """Parse 1-based reactive bond pairs into canonical 0-based pairs.

    Args:
        value: Bond specification. Accepted forms are ``"1-2,3-4"`` or a
            sequence of two-item sequences.
        natoms: Optional atom count used for bounds validation.

    Returns:
        Sorted unique 0-based atom-index pairs.

    Raises:
        ValueError: If a pair is malformed, self-referential, or out of range.
    """
    if value in (None, ""):
        return []

    raw_pairs: list[tuple[int, int]] = []
    if isinstance(value, str):
        for token in value.split(","):
            text = token.strip()
            if not text:
                continue
            if "-" not in text:
                raise ValueError(f"Invalid reactive bond token: {text!r}")
            left, right = text.split("-", 1)
            raw_pairs.append((int(left) - 1, int(right) - 1))
    else:
        for item in value:
            if isinstance(item, dict):
                left = item.get("a", item.get("i", item.get("from")))
                right = item.get("b", item.get("j", item.get("to")))
            else:
                if len(item) != 2:
                    raise ValueError(f"Invalid reactive bond pair: {item!r}")
                left, right = item
            raw_pairs.append((int(left) - 1, int(right) - 1))

    pairs: set[tuple[int, int]] = set()
    for left, right in raw_pairs:
        if left == right:
            raise ValueError("Reactive bond cannot reference the same atom twice")
        if left < 0 or right < 0 or (natoms is not None and (left >= natoms or right >= natoms)):
            raise ValueError(f"Reactive bond index out of range: {(left + 1, right + 1)}")
        pairs.add(tuple(sorted((left, right))))
    return sorted(pairs)


def ccqn_ic_e_vector(atoms, forces, reactive_bonds, ic_mode: str = "democratic") -> np.ndarray:
    """Return the normalized IC-based CCQN cone axis.

    Args:
        atoms: ASE atoms at the current geometry.
        forces: Current ASE forces with shape ``(natoms, 3)``.
        reactive_bonds: 0-based reactive bond pairs.
        ic_mode: ``democratic`` normalizes each bond contribution; ``sum`` uses
            raw projected force contributions.

    Returns:
        Flattened normalized e-vector. Returns zeros if no valid direction is
        available.
    """
    coords = atoms.get_positions()
    natoms = len(atoms)
    bonds = parse_reactive_bonds([(i + 1, j + 1) for i, j in reactive_bonds], natoms=natoms)
    if not bonds:
        return np.zeros(natoms * 3)

    bond_array = np.asarray(bonds, dtype=int)
    i_idx = bond_array[:, 0]
    j_idx = bond_array[:, 1]
    raw_v = coords[j_idx] - coords[i_idx]
    v_ij, _ = find_mic(raw_v, atoms.get_cell(), atoms.get_pbc())
    norm_v = np.linalg.norm(v_ij, axis=1)
    valid = norm_v > 1e-8
    if not np.any(valid):
        return np.zeros(natoms * 3)

    v_ij = v_ij[valid]
    i_idx = i_idx[valid]
    j_idx = j_idx[valid]
    forces = np.asarray(forces, dtype=float).reshape(natoms, 3)
    f_i = forces[i_idx]
    f_j = forces[j_idx]
    dot_vj = np.sum(v_ij * f_j, axis=1)
    dot_vi = np.sum(v_ij * f_i, axis=1)
    dot_vv = np.sum(v_ij * v_ij, axis=1)
    p_ij_num = v_ij * (dot_vj / dot_vv)[:, None] - v_ij * (dot_vi / dot_vv)[:, None]

    e_matrix = np.zeros_like(coords)
    if str(ic_mode).lower() == "democratic":
        norm_p = np.linalg.norm(p_ij_num, axis=1)
        valid_p = norm_p > 1e-8
        if not np.any(valid_p):
            return np.zeros(natoms * 3)
        p_ij = p_ij_num[valid_p] / norm_p[valid_p][:, None]
        np.add.at(e_matrix, i_idx[valid_p], p_ij)
        np.add.at(e_matrix, j_idx[valid_p], -p_ij)
    else:
        np.add.at(e_matrix, i_idx, p_ij_num)
        np.add.at(e_matrix, j_idx, -p_ij_num)

    e_vec = e_matrix.flatten()
    norm = np.linalg.norm(e_vec)
    return e_vec / norm if norm > 1e-8 else e_vec


def ccqn_interp_e_vector(atoms, product_atoms) -> np.ndarray:
    """Return the normalized interpolation-based CCQN cone axis.

    Args:
        atoms: Current ASE atoms.
        product_atoms: Product-like reference geometry with matching atom count.

    Returns:
        Flattened normalized MIC displacement from current to reference.

    Raises:
        ValueError: If atom counts differ.
    """
    if product_atoms is None:
        raise ValueError("product_atoms is required for e_vector_method='interp'")
    if len(product_atoms) != len(atoms):
        raise ValueError(f"product_atoms atom count mismatch: {len(product_atoms)} vs {len(atoms)}")
    raw = product_atoms.get_positions() - atoms.get_positions()
    mic, _ = find_mic(raw, atoms.get_cell(), atoms.get_pbc())
    e_vec = mic.flatten()
    norm = np.linalg.norm(e_vec)
    return e_vec / norm if norm > 1e-8 else np.zeros_like(e_vec)


class _HessianManager:
    """Manage CCQN Hessian initialization and TS-BFGS updates."""

    def __init__(self, atoms, hessian: bool = False, initial_scale: float = 70.0):
        self.atoms = atoms
        self.hessian = hessian
        self.initial_scale = initial_scale

    def initialize(self) -> np.ndarray:
        """Return an initial approximate Hessian."""
        if self.hessian and getattr(self.atoms, "calc", None) is not None:
            get_hessian = getattr(self.atoms.calc, "get_hessian", None)
            if get_hessian is not None:
                return np.asarray(get_hessian(self.atoms), dtype=float).reshape(3 * len(self.atoms), 3 * len(self.atoms))
        return np.eye(3 * len(self.atoms), dtype=float) * self.initial_scale

    def update(self, hessian, step, gradient_delta, eigvals=None, eigvecs=None) -> np.ndarray:
        """Return the TS-BFGS-updated approximate Hessian."""
        if eigvals is None or eigvecs is None:
            eigvals, eigvecs = eigh(hessian)
        step_proj = eigvecs.T @ step
        z_vec = eigvecs @ (np.abs(eigvals) * step_proj)
        s_ty = float(step @ gradient_delta)
        s_tz = float(step @ z_vec)
        s_ms = s_ty**2 + s_tz**2
        if abs(s_ms) < 1e-12:
            return hessian

        u_vec = (s_ty * gradient_delta + s_tz * z_vec) / s_ms
        j_vec = gradient_delta - hessian @ step
        return hessian + np.outer(j_vec, u_vec) + np.outer(u_vec, j_vec) - float(j_vec @ step) * np.outer(u_vec, u_vec)


class CCQNOptimizer(Optimizer):
    """ASE optimizer implementing the CCQN transition-state algorithm."""

    def __init__(
        self,
        atoms,
        restart=None,
        logfile="-",
        trajectory=None,
        master=None,
        e_vector_method: str = "ic",
        product_atoms=None,
        reactive_bonds=None,
        ic_mode: str = "democratic",
        cos_phi: float = 0.5,
        trust_radius_uphill: float = 0.1,
        trust_radius_saddle_initial: float = 0.05,
        trust_radius_saddle_min: float = 5.0e-3,
        trust_radius_saddle_max: float = 0.2,
        hessian: bool = False,
        accept_initial_converged: bool = False,
        diagnostics_file: str | None = None,
    ):
        """Initialize a CCQN optimizer.

        Args:
            atoms: ASE atoms to optimize.
            restart: ASE optimizer restart path.
            logfile: ASE optimizer log file.
            trajectory: ASE trajectory path or object.
            master: ASE parallel master flag.
            e_vector_method: ``ic`` or ``interp``.
            product_atoms: Product-like reference for ``interp``.
            reactive_bonds: 0-based reactive bonds for ``ic``.
            ic_mode: IC contribution mode, ``democratic`` or ``sum``.
            cos_phi: Cone half-angle cosine.
            trust_radius_uphill: Fixed uphill trust radius.
            trust_radius_saddle_initial: Initial PRFO trust radius.
            trust_radius_saddle_min: Minimum PRFO trust radius.
            trust_radius_saddle_max: Maximum PRFO trust radius.
            hessian: Use calculator Hessian when available.
            accept_initial_converged: Treat an already force-converged TS guess
                as a PRFO-region point before the first optimizer step.
            diagnostics_file: Optional JSON file for step-level diagnostics.
        """
        super().__init__(atoms, restart=restart, logfile=logfile, trajectory=trajectory, master=master)
        self.e_vector_method = str(e_vector_method).lower()
        self.product_atoms = product_atoms
        self.reactive_bonds = list(reactive_bonds or [])
        self.ic_mode = str(ic_mode).lower()
        self.cos_phi = float(cos_phi)
        self.trust_radius_uphill = float(trust_radius_uphill)
        self.trust_radius_saddle = float(trust_radius_saddle_initial)
        self.trust_radius_saddle_initial = float(trust_radius_saddle_initial)
        self.trust_radius_saddle_min = float(trust_radius_saddle_min)
        self.trust_radius_saddle_max = float(trust_radius_saddle_max)
        self.mode = "uphill"
        self._hessian_manager = _HessianManager(atoms, hessian=hessian)
        self.hessian_matrix = self._hessian_manager.initialize()
        self.prev_gradient = None
        self.prev_positions = None
        self.prev_energy = None
        self.eigvals = None
        self.eigvecs = None
        self.diagnostics_file = diagnostics_file
        self.diagnostics_steps = []

        if self.e_vector_method not in {"ic", "interp"}:
            raise ValueError("e_vector_method must be 'ic' or 'interp'")
        if self.e_vector_method == "interp" and product_atoms is None:
            raise ValueError("product_atoms is required for e_vector_method='interp'")
        if self.e_vector_method == "ic" and not self.reactive_bonds:
            raise ValueError("reactive_bonds is required for e_vector_method='ic'")
        if accept_initial_converged:
            self.mode = "prfo"

    def _write_diagnostics(self) -> None:
        if not self.diagnostics_file:
            return
        payload = {
            "schema_version": "atst-ccqn-diagnostics-v1",
            "steps": self.diagnostics_steps,
        }
        os.makedirs(os.path.dirname(self.diagnostics_file) or ".", exist_ok=True)
        with open(self.diagnostics_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _record_diagnostics(self, *, energy: float, gradient: np.ndarray, step: np.ndarray, eigvals: np.ndarray) -> None:
        self.diagnostics_steps.append(
            {
                "step": len(self.diagnostics_steps),
                "mode": self.mode,
                "energy_eV": energy,
                "max_force_eV_per_A": float(np.linalg.norm(gradient.reshape(-1, 3), axis=1).max()),
                "step_norm_A": float(np.linalg.norm(step)),
                "min_eigenvalue": float(eigvals[0]) if len(eigvals) else None,
                "trust_radius_saddle_A": self.trust_radius_saddle,
                "trust_radius_uphill_A": self.trust_radius_uphill,
            }
        )
        self._write_diagnostics()

    def converged(self, forces=None) -> bool:
        """Return whether CCQN has converged to a PRFO saddle-region point."""
        if forces is None:
            forces = self.atoms.get_forces()
        if np.isscalar(forces):
            fmax = float(forces)
        else:
            forces = np.asarray(forces, dtype=float).reshape(-1, 3)
            fmax = float(np.sqrt((forces**2).sum(axis=1).max()))
        return fmax < float(getattr(self, "fmax", 0.05)) and self.mode == "prfo"

    def gradient_converged(self, gradient) -> bool:
        """Return convergence from ASE flattened gradient convention."""
        return self.converged(-np.asarray(gradient, dtype=float).reshape(-1, 3))

    def _calculate_e_vector(self, forces) -> np.ndarray:
        if self.e_vector_method == "interp":
            return ccqn_interp_e_vector(self.atoms, self.product_atoms)
        return ccqn_ic_e_vector(self.atoms, forces, self.reactive_bonds, ic_mode=self.ic_mode)

    def _select_mode(self, eigvals) -> None:
        min_eig = float(eigvals[0])
        if self.mode == "uphill" and min_eig < -1e-6:
            self.mode = "prfo"
            self.trust_radius_saddle = self.trust_radius_saddle_initial
        elif self.mode == "prfo" and min_eig > 1e-2:
            self.mode = "uphill"

    def _solve_uphill(self, gradient, e_vec) -> np.ndarray:
        if np.linalg.norm(e_vec) < 1e-10:
            return np.zeros_like(gradient)
        radius = self.trust_radius_uphill
        s0 = e_vec * radius

        def objective(step):
            return float(gradient @ step + 0.5 * step @ self.hessian_matrix @ step)

        def jac_objective(step):
            return gradient + self.hessian_matrix @ step

        constraints = [
            {"type": "eq", "fun": lambda step: float(step @ step - radius**2), "jac": lambda step: 2.0 * step},
            {
                "type": "ineq",
                "fun": lambda step: float(e_vec @ step - self.cos_phi * radius),
                "jac": lambda step: e_vec,
            },
        ]
        result = minimize(
            objective,
            s0,
            jac=jac_objective,
            constraints=constraints,
            method="SLSQP",
            options={"maxiter": 1000, "ftol": 1e-8},
        )
        return np.asarray(result.x if result.success else s0, dtype=float)

    @staticmethod
    def _rfo_subproblem(lambdas, gradient, mode, alpha_sq=1.0):
        dim = len(lambdas)
        if dim == 0:
            return np.array([], dtype=float)
        alpha = np.sqrt(max(float(alpha_sq), 1e-15))
        aug = np.zeros((dim + 1, dim + 1), dtype=float)
        aug[:dim, :dim] = np.diag(lambdas)
        aug[:dim, dim] = gradient / alpha
        aug[dim, :dim] = gradient / alpha
        values, vectors = eigh(aug)
        index = -1 if mode == "max" else 0
        scale = vectors[-1, index]
        if abs(scale) < 1e-15:
            return -np.linalg.pinv(np.diag(lambdas), rcond=1e-15) @ gradient
        return vectors[:dim, index] / scale * alpha

    def _solve_prfo(self, gradient, eigvals, eigvecs, energy) -> np.ndarray:
        g_tilde = eigvecs.T @ gradient
        unc_max = -np.linalg.pinv(np.diag(eigvals[:1]), rcond=1e-15) @ g_tilde[:1]
        unc_min = -np.linalg.pinv(np.diag(eigvals[1:]), rcond=1e-15) @ g_tilde[1:]
        step_unc = eigvecs @ np.concatenate([unc_max, unc_min])
        if np.linalg.norm(step_unc) <= self.trust_radius_saddle:
            step = step_unc
        else:
            def residual(alpha_sq):
                s_max = self._rfo_subproblem(eigvals[:1], g_tilde[:1], "max", alpha_sq)
                s_min = self._rfo_subproblem(eigvals[1:], g_tilde[1:], "min", alpha_sq)
                return float(np.sum(s_max**2) + np.sum(s_min**2) - self.trust_radius_saddle**2)

            try:
                alpha_sq = brentq(residual, 1e-20, 1e6, xtol=1e-12)
                step = eigvecs @ np.concatenate(
                    [
                        self._rfo_subproblem(eigvals[:1], g_tilde[:1], "max", alpha_sq),
                        self._rfo_subproblem(eigvals[1:], g_tilde[1:], "min", alpha_sq),
                    ]
                )
            except ValueError:
                step = step_unc * (self.trust_radius_saddle / max(np.linalg.norm(step_unc), 1e-15))

        if self.prev_positions is not None and self.prev_gradient is not None and self.prev_energy is not None:
            prev_step = self.atoms.get_positions().flatten() - self.prev_positions
            predicted = float(self.prev_gradient @ prev_step + 0.5 * prev_step @ self.hessian_matrix @ prev_step)
            actual = float(energy - self.prev_energy)
            rho = actual / predicted if abs(predicted) > 1e-8 else 1.0
            old_radius = self.trust_radius_saddle
            if rho < 0.2 or rho > 5.0:
                self.trust_radius_saddle = max(self.trust_radius_saddle_min, old_radius * np.sqrt(0.65))
            elif (1.0 / 1.035) < rho < 1.035 and abs(np.linalg.norm(prev_step) - old_radius) < 1e-3:
                self.trust_radius_saddle = min(self.trust_radius_saddle_max, old_radius * np.sqrt(1.15))
        return step

    def step(self, forces=None) -> None:
        """Perform one CCQN optimizer step."""
        if forces is None:
            forces = self.atoms.get_forces()
        forces = np.asarray(forces, dtype=float).reshape(-1, 3)
        gradient = -forces.flatten()
        positions = self.atoms.get_positions().flatten()
        energy = float(self.atoms.get_potential_energy())

        if self.prev_positions is not None and self.prev_gradient is not None:
            step_prev = positions - self.prev_positions
            gradient_delta = gradient - self.prev_gradient
            if np.linalg.norm(step_prev) > 1e-8:
                self.hessian_matrix = self._hessian_manager.update(
                    self.hessian_matrix,
                    step_prev,
                    gradient_delta,
                    eigvals=self.eigvals,
                    eigvecs=self.eigvecs,
                )

        eigvals, eigvecs = eigh(self.hessian_matrix)
        self.eigvals = eigvals
        self.eigvecs = eigvecs
        self._select_mode(eigvals)

        if self.mode == "uphill":
            e_vec = self._calculate_e_vector(forces)
            step = self._solve_uphill(gradient, e_vec)
        else:
            step = self._solve_prfo(gradient, eigvals, eigvecs, energy)

        self.atoms.set_positions((positions + step).reshape(-1, 3))
        self._record_diagnostics(energy=energy, gradient=gradient, step=step, eigvals=eigvals)
        self.prev_positions = positions
        self.prev_gradient = gradient
        self.prev_energy = energy


class AbacusCCQN:
    """Run CCQN with an ATST calculator backend.

    References:
        Wu, Y.; Wang, H. Cone-Shaped Constrained Quasi-Newton Method:
        Efficient and Robust Single-Ended Transition State Optimization
        Algorithm. J. Chem. Theory Comput. (2025).
        https://doi.org/10.1021/acs.jctc.5c01015
    """

    def __init__(
        self,
        init_Atoms,
        config: dict[str, Any],
        calc_name: str,
        calc_config: dict[str, Any],
        traj_file: str = "ccqn.traj",
        product_atoms=None,
        calculator=None,
    ):
        """Initialize a CCQN workflow runner.

        Args:
            init_Atoms: Initial TS guess.
            config: Full ATST configuration.
            calc_name: Calculator backend name.
            calc_config: CCQN calculation block.
            traj_file: Optimizer trajectory path.
            product_atoms: Optional product-like reference for interp mode.
            calculator: Optional caller-provided ASE calculator.
        """
        self.init_Atoms = init_Atoms
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.traj_file = traj_file
        self.product_atoms = product_atoms
        self.calculator = calculator

    def _write_mode_manifest(self, modes: list[dict[str, Any]], selected: dict[str, Any] | None) -> None:
        manifest_file = self.calc_config.get("mode_manifest")
        if not manifest_file:
            return
        payload = {
            "schema_version": "atst-ccqn-mode-manifest-v1",
            "selected_mode": selected,
            "modes": modes,
        }
        os.makedirs(os.path.dirname(manifest_file) or ".", exist_ok=True)
        with open(manifest_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def set_calculator(self):
        """Return the supplied calculator or create a workflow-local one."""
        if self.calculator is not None:
            return self.calculator
        directory = self.calc_config.get("directory", "ccqn_run")
        return CalculatorFactory.get_calculator(self.calc_name, self.config, directory=directory)

    def run(self):
        """Run CCQN and return the optimized atoms."""
        atoms = self.init_Atoms.copy() if self.calculator is not None else self.init_Atoms
        atoms.calc = self.set_calculator()
        product_atoms = self.product_atoms
        if product_atoms is None and self.calc_config.get("product_file"):
            from atst_tools.utils.io import read_structure

            product_atoms = read_structure(self.calc_config["product_file"])
            product_atoms.set_cell(atoms.get_cell())
            product_atoms.set_pbc(atoms.get_pbc())
        if product_atoms is not None and self.calc_config.get("align_product_indices"):
            product_atoms = align_atom_indices(atoms, product_atoms)

        reactive_bonds = parse_reactive_bonds(self.calc_config.get("reactive_bonds"), natoms=len(atoms))
        modes = []
        selected_mode = None
        auto_config = self.calc_config.get("auto_reactive_bonds") or {}
        if self.calc_config.get("e_vector_method", "ic") == "ic" and not reactive_bonds and auto_config.get("enabled"):
            modes = enumerate_reactive_bond_modes(
                atoms,
                molecule_indices=auto_config.get("molecule_indices"),
                active_molecule_indices=auto_config.get("active_molecule_indices"),
                active_catalyst_indices=auto_config.get("active_catalyst_indices"),
                cutoff_A=auto_config.get("cutoff_A", 3.0),
                max_modes=auto_config.get("max_modes", 20),
                max_bonds_per_mode=auto_config.get("max_bonds_per_mode", 1),
                bond_detect_scale=auto_config.get("bond_detect_scale", 1.2),
            )
            if not modes:
                raise ValueError("auto_reactive_bonds found no candidate reactive modes")
            selected_mode = modes[0]
            reactive_bonds = [tuple(pair) for pair in selected_mode["reactive_bonds"]]
        if modes or self.calc_config.get("mode_manifest"):
            self._write_mode_manifest(modes, selected_mode)
        optimizer = CCQNOptimizer(
            atoms,
            logfile=self.calc_config.get("logfile", "ccqn.log"),
            trajectory=self.traj_file,
            e_vector_method=self.calc_config.get("e_vector_method", "ic"),
            product_atoms=product_atoms,
            reactive_bonds=reactive_bonds,
            ic_mode=self.calc_config.get("ic_mode", "democratic"),
            cos_phi=self.calc_config.get("cos_phi", 0.5),
            trust_radius_uphill=self.calc_config.get("trust_radius_uphill", 0.1),
            trust_radius_saddle_initial=self.calc_config.get("trust_radius_saddle_initial", 0.05),
            hessian=self.calc_config.get("hessian", False),
            accept_initial_converged=self.calc_config.get("accept_initial_converged", False),
            diagnostics_file=self.calc_config.get("diagnostics_file"),
        )
        max_steps = self.calc_config.get("max_steps")
        if max_steps is None:
            optimizer.run(fmax=self.calc_config.get("fmax", 0.05))
        else:
            optimizer.run(fmax=self.calc_config.get("fmax", 0.05), steps=max_steps)
        final_structure = self.calc_config.get("final_structure")
        if final_structure:
            os.makedirs(os.path.dirname(final_structure) or ".", exist_ok=True)
            write(final_structure, atoms)
        artifacts = [{"role": "trajectory", "path": self.traj_file}]
        if final_structure:
            artifacts.append({"role": "ts_structure", "path": final_structure})
        if self.calc_config.get("mode_manifest"):
            artifacts.append({"role": "ccqn_mode_manifest", "path": self.calc_config["mode_manifest"]})
        if self.calc_config.get("diagnostics_file"):
            artifacts.append({"role": "ccqn_diagnostics", "path": self.calc_config["diagnostics_file"]})
        write_artifact_manifest(
            self.calc_config.get("artifact_manifest", "atst_artifacts.json"),
            workflow="ccqn",
            artifacts=artifacts,
            stages=[{"name": "ccqn", "status": "complete"}],
        )
        return atoms
