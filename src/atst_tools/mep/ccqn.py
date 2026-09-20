"""Cone-shaped constrained quasi-Newton transition-state optimizer.

References:
    Wu, Y.; Wang, H. Cone-Shaped Constrained Quasi-Newton Method: Efficient
    and Robust Single-Ended Transition State Optimization Algorithm.
    J. Chem. Theory Comput. (2025).
    https://doi.org/10.1021/acs.jctc.5c01015
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import numpy as np
from ase.geometry import find_mic
from ase.io import write
from ase.optimize.optimize import Optimizer
from scipy.linalg import eigh
from scipy.optimize import brentq, minimize

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.convergence import (
    StageRecord,
    as_finite_float,
    as_step_count,
    emit_unconverged_advisory,
)
from atst_tools.utils.idpp import align_atom_indices, interpolate_path
from atst_tools.utils.reactive_modes import enumerate_reactive_bond_modes

# Interpolation-based cone axis (paper eq. 18): the path towards the product is
# resolved with seven inner images, so the nine-frame path makes
# ``path[len(path) // 2]`` the centre inner image.
CCQN_INTERP_PATH_IMAGES = 7
CCQN_INTERP_PATH_TOL = 0.05
#: A midpoint path is called unphysical when some atom pair is compressed below
#: this fraction of that pair's smallest endpoint separation.
CCQN_INTERP_PATH_MIN_DISTANCE_RATIO = 0.5
#: Shared direction-family message; the YAML schema prefixes it with
#: ``calculation.`` and the embedded-API mapping reuses it verbatim.
CCQN_INTERP_DIRECTION_ERROR = "interp_direction='midpoint' requires e_vector_method='interp'"


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


def _ccqn_interp_midpoint_e_vector(
    atoms,
    product_atoms,
    path_status: dict | None = None,
    path_quality: dict | None = None,
) -> np.ndarray:
    """Return the normalized cone axis from the interpolation path midpoint.

    Implements eq. 18 of the CCQN paper: ``e = (x_mid - x) / |x_mid - x|``,
    where ``x_mid`` is the centre frame of an IDPP path generated between the
    current and product configurations.

    Args:
        atoms: Current ASE atoms.
        product_atoms: Product-like reference geometry with matching atom count.
        path_status: Optional mapping updated in place with the IDPP solver
            outcome of the generated path (see ``interpolate_path``).
        path_quality: Optional mapping updated in place with the path quality
            facts of the generated path (see
            :func:`_ccqn_interp_path_quality`).

    Returns:
        Flattened normalized MIC displacement from current to the path
        midpoint. Returns zeros if the midpoint coincides with the current
        geometry.
    """
    path = interpolate_path(
        atoms,
        product_atoms,
        CCQN_INTERP_PATH_IMAGES,
        method="IDPP",
        tol=CCQN_INTERP_PATH_TOL,
        quiet=True,
        path_status=path_status,
    )
    if path_quality is not None:
        path_quality.clear()
        path_quality.update(_ccqn_interp_path_quality(path))
    midpoint = path[len(path) // 2]
    raw = midpoint.get_positions() - atoms.get_positions()
    mic, _ = find_mic(raw, atoms.get_cell(), atoms.get_pbc())
    e_vec = mic.flatten()
    norm = np.linalg.norm(e_vec)
    return e_vec / norm if norm > 1e-8 else np.zeros_like(e_vec)


def _ccqn_interp_path_quality(frames) -> dict[str, Any]:
    """Return the tightest interatomic contact facts of an interpolated path.

    Every atom pair is graded against its own endpoints: the smallest distance
    that pair reaches on any frame is compared with the smaller of the two
    endpoint distances for that same pair.  A pair driven far below both
    endpoints is the signature of an unconverged path relaxation rather than of
    a reaction coordinate, and the path midpoint is then not a trustworthy axis
    estimate.

    The reference is deliberately per pair: a global endpoint minimum would be
    dominated by the tightest bond of the system (for example a 1 Ang X-H bond)
    and could hide a collapsed metal-metal contact.

    Distances use the minimum image convention whenever the frames are periodic.

    Args:
        frames: Path frames, including both endpoints.

    Returns:
        Mapping with ``min_distance_A``, ``min_distance_pair`` (0-based),
        ``min_distance_ratio``, ``ratio_pair`` (0-based) and
        ``ratio_reference_A``. Empty when the path has no atom pair to measure.
    """
    if len(frames) < 2 or len(frames[0]) < 2:
        return {}
    natoms = len(frames[0])
    use_mic = bool(np.any(frames[0].get_pbc()))
    pair_mask = ~np.eye(natoms, dtype=bool)
    start_distances = frames[0].get_all_distances(mic=use_mic)
    end_distances = frames[-1].get_all_distances(mic=use_mic)
    reference = np.minimum(start_distances, end_distances)
    measured = pair_mask & (reference > 0.0)
    safe_reference = np.where(measured, reference, 1.0)

    min_distance = np.inf
    min_pair = (0, 0)
    worst_ratio = np.inf
    worst_pair = (0, 0)
    worst_reference = np.inf
    for index, frame in enumerate(frames):
        if index == 0:
            distances = start_distances
        elif index == len(frames) - 1:
            distances = end_distances
        else:
            distances = frame.get_all_distances(mic=use_mic)
        masked = np.where(pair_mask, distances, np.inf)
        row, column = np.unravel_index(int(np.argmin(masked)), masked.shape)
        if masked[row, column] < min_distance:
            min_distance = float(masked[row, column])
            min_pair = (int(row), int(column))
        ratios = np.where(measured, distances / safe_reference, np.inf)
        row, column = np.unravel_index(int(np.argmin(ratios)), ratios.shape)
        if ratios[row, column] < worst_ratio:
            worst_ratio = float(ratios[row, column])
            worst_pair = (int(row), int(column))
            worst_reference = float(reference[row, column])

    return {
        "min_distance_A": min_distance,
        "min_distance_pair": min_pair,
        "min_distance_ratio": worst_ratio,
        "ratio_pair": worst_pair,
        "ratio_reference_A": worst_reference,
    }


def _emit_unphysical_path_advisory(quality: dict[str, Any]) -> None:
    """Print one English advisory for an interpolation path that is not physical.

    Mirrors :func:`atst_tools.utils.convergence.emit_unconverged_advisory`:
    diagnostic only, never raises, and it changes no return value, workflow
    status or manifest. The caller prints it at most once per optimizer instance.

    Args:
        quality: Path quality facts from :func:`_ccqn_interp_path_quality`.
    """
    row, column = quality["ratio_pair"]
    print(
        "Warning: CCQN interpolation path is not physical\n"
        "(workflow=ccqn, stage=ccqn_interp_path, "
        f"path_min_distance={quality['min_distance_A']:.3f} Ang, "
        f"worst_ratio={quality['min_distance_ratio']:.3f}, "
        f"atom_pair={row + 1}-{column + 1}, "
        f"pair_endpoint_min={quality['ratio_reference_A']:.3f} Ang, "
        f"threshold_ratio={CCQN_INTERP_PATH_MIN_DISTANCE_RATIO:.3f}).\n"
        "An IDPP path that compresses an atom pair far below its endpoint separation "
        "makes the midpoint cone axis untrustworthy; cross-check with "
        "interp_direction=product or validate the path with IRC/NEB."
    )


def ccqn_interp_e_vector(
    atoms,
    product_atoms,
    direction: str = "product",
    *,
    path_status: dict | None = None,
    path_quality: dict | None = None,
) -> np.ndarray:
    """Return the normalized interpolation-based CCQN cone axis.

    Args:
        atoms: Current ASE atoms.
        product_atoms: Product-like reference geometry with matching atom count.
        direction: ``product`` keeps the MIC displacement towards the product
            configuration; ``midpoint`` uses the midpoint of an IDPP path
            towards the product, per eq. 18 of the CCQN paper.
        path_status: Optional mapping updated in place with the IDPP solver
            outcome when ``direction="midpoint"``. The ``product`` direction
            generates no path, so the mapping is left untouched there.
        path_quality: Optional mapping updated in place with the path quality
            facts of ``direction="midpoint"`` (see
            :func:`_ccqn_interp_path_quality`). Like ``path_status`` it is left
            untouched when no path is generated.

    Returns:
        Flattened normalized MIC displacement from current to reference.

    Raises:
        ValueError: If atom counts differ or ``direction`` is unknown.
    """
    if product_atoms is None:
        raise ValueError("product_atoms is required for e_vector_method='interp'")
    if len(product_atoms) != len(atoms):
        raise ValueError(f"product_atoms atom count mismatch: {len(product_atoms)} vs {len(atoms)}")
    normalized_direction = str(direction).lower()
    if normalized_direction not in {"product", "midpoint"}:
        raise ValueError("interp_direction must be 'product' or 'midpoint'")
    if normalized_direction == "midpoint":
        return _ccqn_interp_midpoint_e_vector(
            atoms,
            product_atoms,
            path_status=path_status,
            path_quality=path_quality,
        )
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
        interp_direction: str = "product",
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
            interp_direction: For ``e_vector_method='interp'``, ``product``
                points at the product configuration and ``midpoint`` points at
                the midpoint of an IDPP path towards it (paper eq. 18).
        """
        super().__init__(atoms, restart=restart, logfile=logfile, trajectory=trajectory, master=master)
        self.e_vector_method = str(e_vector_method).lower()
        self.product_atoms = product_atoms
        self.interp_direction = str(interp_direction).lower()
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
        #: IDPP path outcome of the most recent ``midpoint`` uphill step, or
        #: ``None`` when no path was solved (``product``/``ic`` modes).
        self.interp_path_status: dict[str, Any] | None = None
        self._interp_path_advisory_emitted = False
        #: Path quality facts of the most recent ``midpoint`` uphill step, or
        #: ``None`` when no path was solved (``product``/``ic`` modes).
        self.interp_path_quality: dict[str, Any] | None = None
        self._interp_path_quality_advisory_emitted = False

        if self.e_vector_method not in {"ic", "interp"}:
            raise ValueError("e_vector_method must be 'ic' or 'interp'")
        if self.e_vector_method == "interp" and product_atoms is None:
            raise ValueError("product_atoms is required for e_vector_method='interp'")
        if self.e_vector_method == "ic" and not self.reactive_bonds:
            raise ValueError("reactive_bonds is required for e_vector_method='ic'")
        if self.interp_direction not in {"product", "midpoint"}:
            raise ValueError("interp_direction must be 'product' or 'midpoint'")
        if self.interp_direction == "midpoint" and self.e_vector_method != "interp":
            raise ValueError(CCQN_INTERP_DIRECTION_ERROR)
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

    def _record_interp_path_status(self, status: dict[str, Any] | None) -> None:
        """Store the midpoint path outcome and advise once when it is unconverged.

        The IDPP path has a fixed iteration budget and may be truncated, in
        which case ``x_mid`` is the centre frame of a path that did not
        converge. That is recorded as a fact: it is never upgraded into a hard
        failure, and the shared advisory is printed only for the first
        unconverged path of this optimizer instance so long runs stay readable.

        Args:
            status: Path status mapping, empty for entry points that generate
                no path.
        """
        reported = status or {}
        self.interp_path_status = dict(reported) if reported.get("status") else None
        if self.interp_path_status is None or self.interp_path_status.get("status") != "Failed":
            return
        if self._interp_path_advisory_emitted:
            return
        self._interp_path_advisory_emitted = True
        emit_unconverged_advisory(
            StageRecord(
                name="ccqn_interp_path",
                role="diagnostic",
                criterion="idpp_path",
                converged=False,
                steps=as_step_count(self.interp_path_status.get("maxiter")),
                actual_steps=as_step_count(self.interp_path_status.get("iterations")),
            ),
            workflow="ccqn",
        )

    def _record_interp_path_quality(self, quality: dict[str, Any] | None) -> None:
        """Store the midpoint path quality facts and advise once when unphysical.

        A path that compresses atom pairs far below their endpoint separation
        makes the midpoint axis untrustworthy. That is reported as a fact: it is
        never upgraded into a hard failure, the run keeps stepping, and the
        advisory is printed only for the first such path of this optimizer
        instance.

        Args:
            quality: Path quality mapping, empty for entry points that generate
                no path.
        """
        reported = quality or {}
        self.interp_path_quality = dict(reported) if reported else None
        if self.interp_path_quality is None:
            return
        ratio = self.interp_path_quality.get("min_distance_ratio")
        if ratio is None or not np.isfinite(ratio) or ratio >= CCQN_INTERP_PATH_MIN_DISTANCE_RATIO:
            return
        if self._interp_path_quality_advisory_emitted:
            return
        self._interp_path_quality_advisory_emitted = True
        _emit_unphysical_path_advisory(self.interp_path_quality)

    def _record_diagnostics(self, *, energy: float, gradient: np.ndarray, step: np.ndarray, eigvals: np.ndarray) -> None:
        payload = {
            "step": len(self.diagnostics_steps),
            "mode": self.mode,
            "energy_eV": energy,
            "max_force_eV_per_A": float(np.linalg.norm(gradient.reshape(-1, 3), axis=1).max()),
            "step_norm_A": float(np.linalg.norm(step)),
            "min_eigenvalue": float(eigvals[0]) if len(eigvals) else None,
            "trust_radius_saddle_A": self.trust_radius_saddle,
            "trust_radius_uphill_A": self.trust_radius_uphill,
        }
        if self.mode == "uphill" and self.interp_path_status is not None:
            payload.update(
                {
                    "idpp_path_status": self.interp_path_status.get("status"),
                    "idpp_iterations": as_step_count(self.interp_path_status.get("iterations")),
                    "idpp_final_S_IDPP": as_finite_float(self.interp_path_status.get("final_S_IDPP")),
                    "idpp_max_force": as_finite_float(self.interp_path_status.get("max_force")),
                }
            )
            if self.interp_path_quality is not None:
                min_pair = self.interp_path_quality.get("min_distance_pair", (0, 0))
                ratio_pair = self.interp_path_quality.get("ratio_pair", (0, 0))
                payload.update(
                    {
                        "idpp_path_min_distance": as_finite_float(
                            self.interp_path_quality.get("min_distance_A")
                        ),
                        "idpp_path_min_distance_pair": f"{min_pair[0] + 1}-{min_pair[1] + 1}",
                        "idpp_path_min_distance_ratio": as_finite_float(
                            self.interp_path_quality.get("min_distance_ratio")
                        ),
                        "idpp_path_min_distance_ratio_pair": f"{ratio_pair[0] + 1}-{ratio_pair[1] + 1}",
                    }
                )
        self.diagnostics_steps.append(payload)
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
            status: dict[str, Any] = {}
            quality: dict[str, Any] = {}
            e_vec = ccqn_interp_e_vector(
                self.atoms,
                self.product_atoms,
                direction=self.interp_direction,
                path_status=status,
                path_quality=quality,
            )
            # The path is re-solved from the current geometry on every call, so
            # the recorded status and quality always describe this step.
            self._record_interp_path_status(status)
            self._record_interp_path_quality(quality)
            return e_vec
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

    def _solve_prfo(self, gradient, eigvals, eigvecs, energy, *, previous_prediction=None) -> np.ndarray:
        # Assess the completed step before choosing the next restricted step.
        if self.prev_positions is not None and self.prev_gradient is not None and self.prev_energy is not None:
            prev_step = self.atoms.get_positions().flatten() - self.prev_positions
            predicted = previous_prediction
            if predicted is None:
                predicted = float(self.prev_gradient @ prev_step + 0.5 * prev_step @ self.hessian_matrix @ prev_step)
            actual = float(energy - self.prev_energy)
            rho = actual / predicted if abs(predicted) > 1e-8 else 1.0
            old_radius = self.trust_radius_saddle
            if rho < 0.2 or rho > 5.0:
                self.trust_radius_saddle = max(self.trust_radius_saddle_min, old_radius * np.sqrt(0.65))
            elif (1.0 / 1.035) < rho < 1.035 and abs(np.linalg.norm(prev_step) - old_radius) < 1e-3:
                self.trust_radius_saddle = min(self.trust_radius_saddle_max, old_radius * np.sqrt(1.15))

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

        return step

    def step(self, forces=None) -> None:
        """Perform one CCQN optimizer step."""
        if forces is None:
            forces = self.atoms.get_forces()
        forces = np.asarray(forces, dtype=float).reshape(-1, 3)
        gradient = -forces.flatten()
        positions = self.atoms.get_positions().flatten()
        energy = float(self.atoms.get_potential_energy())

        previous_prediction = None
        if self.prev_positions is not None and self.prev_gradient is not None:
            step_prev = positions - self.prev_positions
            # Eq. 19 uses B_k, before the secant update to B_{k+1}. Use the
            # actual displacement, including any ASE constraint adjustments.
            previous_prediction = float(
                self.prev_gradient @ step_prev
                + 0.5 * step_prev @ self.hessian_matrix @ step_prev
            )
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
            step = self._solve_prfo(
                gradient, eigvals, eigvecs, energy,
                previous_prediction=previous_prediction,
            )

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
        self.mode_manifest_facts: dict[str, Any] = {}

    @staticmethod
    def _mode_bond_elements(atoms, bonds: list[tuple[int, int]]) -> list[list[str]]:
        """Return endpoint elements for internal 0-based bond pairs.

        The optimizer consumes 0-based pairs internally, while the manifest is
        an agent-facing audit artifact.  Keeping the element labels beside the
        effective pairs makes a converted structure's endpoint identity
        inspectable without asking a reader to infer it from atom numbers.
        """
        symbols = atoms.get_chemical_symbols()
        return [[symbols[left], symbols[right]] for left, right in bonds]

    def _structure_identity(self, atoms) -> dict[str, Any]:
        """Return stable identity facts for the structure consumed by CCQN."""
        symbols = atoms.get_chemical_symbols()
        ordered_symbols = "\x00".join(symbols).encode("utf-8")
        geometry = {
            "positions_A": np.asarray(atoms.get_positions(), dtype=np.float64).tolist(),
            "cell_A": np.asarray(atoms.get_cell(), dtype=np.float64).tolist(),
            "pbc": [bool(value) for value in atoms.get_pbc()],
        }
        source = self.calc_config.get("init_structure")
        return {
            "source": str(source) if source is not None else None,
            "natoms": len(atoms),
            "ordered_symbols_sha256": hashlib.sha256(ordered_symbols).hexdigest(),
            "geometry_sha256": hashlib.sha256(
                json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def _write_mode_manifest(
        self,
        modes: list[dict[str, Any]],
        selected: dict[str, Any] | None,
        *,
        atoms,
        effective_bonds: list[tuple[int, int]],
        selection_source: str,
    ) -> None:
        manifest_file = self.calc_config.get("mode_manifest")
        method = str(self.calc_config.get("e_vector_method", "ic")).strip().lower()
        interp_direction = str(self.calc_config.get("interp_direction", "product")).strip().lower()
        effective_bonds_1based = [[left + 1, right + 1] for left, right in effective_bonds]
        effective_elements = self._mode_bond_elements(atoms, effective_bonds)
        structure_identity = self._structure_identity(atoms)

        # Preserve the v1 manifest shape and selected-mode fields while adding
        # explicit, current-structure facts.  These fields are intentionally
        # derived after any auto selection and before the 0-based optimizer
        # handoff, so they describe what CCQN actually consumes.
        annotated_modes = []
        for mode in modes:
            annotated = dict(mode)
            mode_bonds = [tuple(pair) for pair in mode.get("reactive_bonds", [])]
            annotated["effective_elements"] = self._mode_bond_elements(atoms, mode_bonds)
            annotated.setdefault("reactive_bonds_index_base", 0)
            annotated_modes.append(annotated)
        if selected is not None:
            selected = dict(selected)
            selected.setdefault("effective_elements", effective_elements)
            selected.setdefault("selection_source", selection_source)
            selected.setdefault("method", method)
            if "reactive_bonds" in selected:
                selected.setdefault("reactive_bonds_index_base", 0)

        payload = {
            "schema_version": "atst-ccqn-mode-manifest-v1",
            "method": method,
            "selection_source": interp_direction if method == "interp" else selection_source,
            "effective_index_base": 1,
            "effective_bonds": effective_bonds_1based,
            "effective_elements": effective_elements,
            "structure_identity": structure_identity,
            "selected_mode": selected,
            "modes": annotated_modes,
        }
        self.mode_manifest_facts = {
            "method": method,
            "selection_source": payload["selection_source"],
            "effective_index_base": 1,
            "effective_bonds": effective_bonds_1based,
            "effective_elements": effective_elements,
            "structure_identity": structure_identity,
        }
        if manifest_file:
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
        """Run CCQN and return the optimized atoms.

        The optimizer's ``run()`` return value is treated as the authoritative
        convergence signal: a known ``False`` prints one shared English
        advisory, and the same record is written as the manifest stage.  The
        return value and the artifact list are unaffected by the advisory.  The
        record is also exposed as ``last_stage_record`` for nesting workflows,
        and an explicit ``artifact_manifest: None`` disables the manifest write
        so only the owning workflow writes one.

        Returns:
            The optimized ASE ``Atoms`` object.
        """
        # Direction-family guard: raised before any calculator is built or any
        # working directory is touched, with the message the YAML schema uses.
        if (
            str(self.calc_config.get("interp_direction", "product")).strip().lower() == "midpoint"
            and str(self.calc_config.get("e_vector_method", "ic")).strip().lower() != "interp"
        ):
            raise ValueError(CCQN_INTERP_DIRECTION_ERROR)
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

        configured_reactive_bonds = parse_reactive_bonds(
            self.calc_config.get("reactive_bonds"), natoms=len(atoms)
        )
        reactive_bonds = configured_reactive_bonds
        modes = []
        selected_mode = None
        auto_config = self.calc_config.get("auto_reactive_bonds") or {}
        method = str(self.calc_config.get("e_vector_method", "ic")).strip().lower()
        selection_source = "not_applicable"
        if method == "interp":
            selection_source = str(self.calc_config.get("interp_direction", "product")).strip().lower()
        if method == "ic" and reactive_bonds:
            selection_source = "explicit"
            selected_mode = {
                "reactive_bonds": [list(pair) for pair in reactive_bonds],
                "reactive_bonds_1based": [[left + 1, right + 1] for left, right in reactive_bonds],
            }
        if method == "ic" and not reactive_bonds and auto_config.get("enabled"):
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
            selection_source = "auto"
        elif method == "ic" and not reactive_bonds:
            selection_source = "none"
        self._write_mode_manifest(
            modes,
            selected_mode,
            atoms=atoms,
            effective_bonds=reactive_bonds if method == "ic" else [],
            selection_source=selection_source,
        )
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
            interp_direction=self.calc_config.get("interp_direction", "product"),
        )
        max_steps = self.calc_config.get("max_steps")
        fmax_threshold = self.calc_config.get("fmax", 0.05)
        if max_steps is None:
            converged_signal = optimizer.run(fmax=fmax_threshold)
        else:
            converged_signal = optimizer.run(fmax=fmax_threshold, steps=max_steps)
        stage_record = StageRecord(
            name="ccqn",
            role="final",
            criterion="ccqn_prfo",
            converged=converged_signal,
            fmax=as_finite_float(fmax_threshold),
            steps=as_step_count(max_steps),
            actual_steps=as_step_count(getattr(optimizer, "nsteps", None)),
        )
        emit_unconverged_advisory(stage_record, workflow="ccqn")
        # Expose the same record to callers (e.g. nested D2S refinement) so the
        # owning workflow can persist the facts without re-deriving them.
        self.last_stage_record = stage_record
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
        # An explicit ``None`` disables the manifest, which lets a nesting
        # workflow (D2S) stay the only writer of the top-level manifest.
        manifest_path = self.calc_config.get("artifact_manifest", "atst_artifacts.json")
        if manifest_path is not None:
            write_artifact_manifest(
                manifest_path,
                workflow="ccqn",
                artifacts=artifacts,
                stages=[stage_record.to_manifest()],
                metadata=self.mode_manifest_facts,
            )
        return atoms
