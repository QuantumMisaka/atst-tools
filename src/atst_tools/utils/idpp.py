import contextlib
import io

import numpy as np
import warnings
from typing import Callable, List

# ASE Imports
from ase import Atoms
from ase.io import write
from ase.constraints import FixAtoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.geometry import find_mic
from ase.optimize import FIRE
from ase.utils.abc import Optimizable
from atst_tools.calculators.constant_potential import read_constant_potential_facts
from atst_tools.utils.geometry import prepare_fixed_cell_images
from atst_tools.utils.neb_endpoints import (
    ENDPOINT_PLACEHOLDER,
    ENDPOINT_PROVIDED,
    freeze_results,
    get_endpoint_results,
    mark_endpoint_result,
)
from atst_tools.utils.io import read_structure
from atst_tools.utils.path_geometry import validate_path_geometry
from atst_tools.utils.path_sampling import allocate_segment_images

# Scipy Imports
from scipy.optimize import linear_sum_assignment

def align_atom_indices(atoms_ref: Atoms, atoms_target: Atoms) -> Atoms:
    """
    Reorder indices of atoms_target to match atoms_ref as closely as possible.
    Note: This function ONLY swaps atom indices, NEVER moves atomic coordinates.
    """
    if len(atoms_ref) != len(atoms_target):
        raise ValueError(f"Atom count mismatch (Ref: {len(atoms_ref)}, Target: {len(atoms_target)})")
    atoms_ref, atoms_target = prepare_fixed_cell_images(
        [atoms_ref, atoms_target], context="Atom alignment"
    )
    
    new_indices = np.zeros(len(atoms_ref), dtype=int)
    
    # Pre-calculation
    cell = atoms_ref.get_cell()
    pbc = atoms_ref.get_pbc()
    
    chemical_symbols = np.array(atoms_ref.get_chemical_symbols())
    unique_elements = sorted(list(set(chemical_symbols)))
    
    ref_pos = atoms_ref.get_positions()
    target_pos = atoms_target.get_positions()
    
    total_dist_sq = 0.0
    
    for element in unique_elements:
        # 1. Group by element
        mask = (chemical_symbols == element)
        indices_ref = np.where(mask)[0]
        
        target_symbols = np.array(atoms_target.get_chemical_symbols())
        indices_target = np.where(target_symbols == element)[0]
        
        if len(indices_ref) != len(indices_target):
            raise ValueError(f"Count mismatch for element {element}!")
            
        n_elem = len(indices_ref)
        
        # 2. Build cost matrix
        pos_sub_ref = ref_pos[indices_ref]       
        pos_sub_target = target_pos[indices_target] 
        
        # Vectorized difference: (n, 1, 3) - (1, n, 3) -> (n, n, 3)
        diff = pos_sub_ref[:, np.newaxis, :] - pos_sub_target[np.newaxis, :, :]
        
        # 3. Minimum Image Convention (MIC) - ONLY for distance calculation
        diff = find_mic(diff.reshape(-1, 3), cell, pbc)[0].reshape(diff.shape)
            
        dist_matrix_sq = np.sum(diff**2, axis=2)
        
        # 4. Hungarian Algorithm
        row_ind, col_ind = linear_sum_assignment(dist_matrix_sq)
        
        # 5. Map indices
        for k in range(n_elem):
            global_idx_ref = indices_ref[row_ind[k]]
            global_idx_target = indices_target[col_ind[k]]
            new_indices[global_idx_ref] = global_idx_target
            total_dist_sq += dist_matrix_sq[row_ind[k], col_ind[k]]

    print(f"  [Alignment] Atom indices alignment done. MSD: {total_dist_sq:.4f} Å²")
    
    # Slicing retains the target's prepared cell, arrays, and constraints.
    sorted_atoms = atoms_target[new_indices]
    if atoms_target.calc is not None:
        results = dict(atoms_target.calc.results)
        for key in ("forces", "magmoms", "charges", "energies", "stresses"):
            if key in results:
                results[key] = np.asarray(results[key])[new_indices]
        sorted_atoms.calc = SinglePointCalculator(sorted_atoms, **results)
    
    return sorted_atoms


def robust_interpolate(start_atoms: Atoms, end_atoms: Atoms, nimages: int, *, reference=None) -> List[Atoms]:
    """Interpolate Cartesian positions using the reference's periodic MIC.

    Args:
        start_atoms: Starting endpoint, retained as a private copy.
        end_atoms: Ending endpoint, retained at its input Cartesian position.
        nimages: Number of intermediate images.
        reference: Common reference for a segmented path; defaults to start.

    Returns:
        Prepared endpoints and unconstrained linear intermediate positions.
    """
    reference = start_atoms if reference is None else reference
    start_atoms, end_atoms = prepare_fixed_cell_images(
        [start_atoms, end_atoms], context="Path interpolation", reference=reference
    )
    delta, _ = find_mic(
        end_atoms.positions - start_atoms.positions, reference.cell, reference.pbc
    )
    
    path = [start_atoms.copy()]
    total_steps = nimages + 1
    for i in range(1, total_steps):
        alpha = i / total_steps
        current_pos = start_atoms.positions + alpha * delta
        image = start_atoms.copy()
        # Preserve the historical linear geometry.  Fast_IDPPSolver anchors
        # each constrained image at this initial position before its first
        # projected update, so a constrained endpoint pair with different
        # coordinates does not acquire a start-to-end jump at the last frame.
        image.set_positions(current_pos, apply_constraint=False)
        path.append(image)
    path.append(end_atoms.copy())
    return path


#: Periodic image shifts in the reference scan order (``sx`` outer, ``sz`` inner).
_MIC_SHIFT_CANDIDATES = np.array(
    [(sx, sy, sz) for sx in (-1, 0, 1) for sy in (-1, 0, 1) for sz in (-1, 0, 1)],
    dtype=float,
)

#: Number of atom pairs handled per allocation block by the vectorized scan.
#: Blocks are independent, so this only bounds peak memory.
_MIC_PAIR_BLOCK = 2048


def _mic_shift_rank_positions() -> np.ndarray:
    """Return each shift candidate's position in the reference rank order.

    The reference scan ranks candidates by
    ``(‖shift‖², |components|, signed components)``.  Those triples are distinct
    for all 27 candidates, so their sorted order is a strict total order and the
    scan's tuple comparison is equivalent to comparing these positions.

    Returns:
        Integer rank position per candidate, indexed like ``_MIC_SHIFT_CANDIDATES``.
    """
    ranks = [
        (
            float(np.dot(shift, shift)),
            tuple(abs(int(value)) for value in shift),
            tuple(int(value) for value in shift),
        )
        for shift in _MIC_SHIFT_CANDIDATES
    ]
    positions = np.empty(len(ranks), dtype=np.int64)
    for position, index in enumerate(sorted(range(len(ranks)), key=ranks.__getitem__)):
        positions[index] = position
    return positions


_MIC_SHIFT_RANK_POSITIONS = _mic_shift_rank_positions()


class _IDPPOptimizable(Optimizable):
    """Adapt the existing projected IDPP band force to an ASE optimizer."""

    def __init__(self, solver, coords: np.ndarray, *, spring_const: float):
        self.spring_const = spring_const
        self.solver = solver
        self.coords = coords
        self._cache = None

    def evaluate(self):
        """Return objective and projected band force once per coordinate state."""
        if self._cache is None:
            funcs, true_forces = self.solver._get_funcs_and_forces(self.coords)
            total_forces = self.solver._get_total_forces(
                self.coords, true_forces, spring_const=self.spring_const
            )
            if self.solver._has_constraints:
                total_forces = self.solver._project_forces(self.coords, total_forces)
            if not np.isfinite(funcs).all() or not np.isfinite(total_forces).all():
                raise ValueError("IDPP objective and forces must be finite")
            self._cache = funcs, total_forces
        return self._cache

    def ndofs(self):
        """Return the number of Cartesian interior-image degrees of freedom."""
        return self.coords[1:-1].size

    def get_x(self):
        """Return a private flat array of the current interior coordinates."""
        return self.coords[1:-1].ravel().copy()

    def set_x(self, x):
        """Set interior coordinates and apply their original ASE constraints."""
        self.coords[1:-1] = x.reshape(self.coords[1:-1].shape)
        if self.solver._has_constraints:
            self.solver._project_positions(self.coords)
        self._cache = None

    def get_gradient(self):
        """Return the negative NEB band force consumed by FIRE's dynamics."""
        return -self.evaluate()[1].ravel()

    def get_value(self):
        """Return the summed pair-distance objective for diagnostics."""
        return float(self.evaluate()[0].sum())

    def iterimages(self):
        """Yield copies of the complete current band."""
        for image, positions in zip(self.solver.images, self.coords):
            current = image.copy()
            current.set_positions(positions, apply_constraint=False)
            yield current


class Fast_IDPPSolver:
    """
    IDPP solver compatible with pymatgen's NEB-like path relaxation.

    The implementation retains the historical distance objective and NEB band
    force without requiring pymatgen. ASE FIRE relaxes the current-MIC band
    by default; the historical clipped fixed-step update remains available.
    """
    def __init__(self, images: List[Atoms], mic: bool = True, *, reference=None):
        images = prepare_fixed_cell_images(images, context="IDPP input", reference=reference)
        self.start_atoms = images[0]
        self.end_atoms = images[-1]
        if len(images) < 2:
            raise ValueError("IDPP requires both endpoint images")
        self.nimages = len(images) - 2
        self.natoms = len(self.start_atoms)
        self.cell = (self.start_atoms if reference is None else reference).get_cell()
        self.images = images
        self._constraint_images = [image.copy() for image in images[1:-1]]
        self._has_constraints = any(image.constraints for image in self._constraint_images)
        if self._has_constraints:
            for image in self._constraint_images:
                image.set_positions(image.get_positions(), apply_constraint=True)
            distance_images = [images[0], *self._constraint_images, images[-1]]
        else:
            distance_images = images

        #: Self-reported outcome of the last :meth:`run` call.  ``None`` means
        #: the solver has not run yet; the remaining fields mirror the
        #: ``IDPP CONVERGENCE REPORT`` block printed by :meth:`run`.
        self.status: str | None = None
        self.converged: bool | None = None
        self.iterations: int | None = None
        self.final_s_idpp: float | None = None
        self.max_force: float | None = None
        self.maxiter: int | None = None
        self.tol: float | None = None
        self.gtol: float | None = None
        
        if mic and np.any(self.start_atoms.pbc):
            self.inv_cell = np.linalg.inv(self.cell.complete())
            self.mic = True
        else:
            self.inv_cell = np.eye(3)
            self.mic = False

        for image_index, image in enumerate(distance_images):
            self._validate_pair_geometry(image.positions, image_index)

        d_start = self.start_atoms.get_all_distances(mic=self.mic)
        d_end = self.end_atoms.get_all_distances(mic=self.mic)
        
        factors = np.linspace(0, 1, self.nimages + 2)[1:-1]
        self.target_dists = d_start[None, :, :] + factors[:, None, None] * (d_end - d_start)[None, :, :]

        initial_distances = np.array(
            [img.get_all_distances(mic=self.mic) for img in distance_images[1:-1]]
        ).reshape(self.nimages, self.natoms, self.natoms)
        avg_dists = (self.target_dists + initial_distances) / 2.0
        self.weights = 1.0 / (avg_dists**4 + np.eye(self.natoms)[None, :, :] * 1e-8)
        self.translations = self._build_translations(distance_images)
        self.initial_positions = np.array([img.get_positions() for img in distance_images[1:-1]])

    def _project_positions(self, coords: np.ndarray) -> None:
        """Apply each intermediate image's ASE position constraints in place."""
        for image_index, image in enumerate(self._constraint_images, start=1):
            image.set_positions(coords[image_index], apply_constraint=True)
            coords[image_index] = image.get_positions()

    def _project_forces(self, coords: np.ndarray, forces: np.ndarray) -> np.ndarray:
        """Apply each intermediate image's ASE force constraints."""
        projected = np.array(forces, dtype=float, copy=True)
        for image_index, image in enumerate(self._constraint_images, start=1):
            image.set_positions(coords[image_index], apply_constraint=False)
            for constraint in image.constraints:
                adjust_forces = getattr(constraint, "adjust_forces", None)
                if adjust_forces is not None:
                    adjust_forces(image, projected[image_index - 1])
        return projected

    def _mic_tie_tolerance(self) -> float:
        """Return the tie tolerance of the reference nearest-image scan.

        Returns:
            ``max(1e-8, 1e-9 * max_row_norm_squared_of_cell)``.
        """
        return max(1e-8, 1e-9 * float(np.max(np.sum(np.asarray(self.cell) ** 2, axis=1))))

    def _mic_candidate_cartesians(self, frac_i: np.ndarray, frac_j: np.ndarray) -> np.ndarray:
        """Return the MIC displacement vector for every candidate shift and pair.

        Reproduces the reference arithmetic ``(frac_j + shift - frac_i) @ cell``
        with plain ordered elementwise operations.  That matters for the bitwise
        contract: batched BLAS matmul accumulates with a different rounding path
        and is not bitwise identical to ``np.dot`` on a single 3-vector.

        Args:
            frac_i: Unwrapped scaled positions of the first atoms, shape ``(P, 3)``.
            frac_j: Unwrapped scaled positions of the second atoms, shape ``(P, 3)``.

        Returns:
            Cartesian candidates with shape ``(P, 27, 3)`` in scan order.
        """
        cell = np.asarray(self.cell, dtype=float)
        vectors = frac_j[:, None, :] + _MIC_SHIFT_CANDIDATES[None, :, :] - frac_i[:, None, :]
        cartesian = np.empty(vectors.shape, dtype=float)
        for column in range(3):
            cartesian[:, :, column] = (
                vectors[:, :, 0] * cell[0, column]
                + vectors[:, :, 1] * cell[1, column]
                + vectors[:, :, 2] * cell[2, column]
            )
        return cartesian

    @staticmethod
    def _scan_nearest_candidates(distances: np.ndarray, tie_tol: float) -> np.ndarray:
        """Return the candidate index the reference scan would select per pair.

        Visits the candidates in the reference order and applies the reference
        replacement rule, so the sequential scan semantics (including its
        ``tie_tol`` band and rank tie-break) are preserved exactly.

        Args:
            distances: Squared candidate distances with shape ``(P, 27)``.
            tie_tol: Tie tolerance from :meth:`_mic_tie_tolerance`.

        Returns:
            Selected candidate index per pair, shape ``(P,)``.
        """
        pairs = distances.shape[0]
        best_distance = np.full(pairs, np.inf, dtype=float)
        best_rank = np.full(pairs, len(_MIC_SHIFT_CANDIDATES), dtype=np.int64)
        best_index = np.zeros(pairs, dtype=np.int64)
        for index in range(len(_MIC_SHIFT_CANDIDATES)):
            candidate = distances[:, index]
            rank = _MIC_SHIFT_RANK_POSITIONS[index]
            replaces = (candidate < best_distance - tie_tol) | (
                (np.abs(candidate - best_distance) <= tie_tol) & (rank < best_rank)
            )
            best_distance = np.where(replaces, candidate, best_distance)
            best_rank = np.where(replaces, rank, best_rank)
            best_index = np.where(replaces, index, best_index)
        return best_index

    def _mic_shift_cartesians(self, shifts: np.ndarray) -> np.ndarray:
        """Return ``shift @ cell`` for a batch of periodic image shifts.

        Args:
            shifts: Shift vectors with shape ``(P, 3)``.

        Returns:
            Cartesian shift vectors with shape ``(P, 3)``, computed with the same
            plain ordered arithmetic as the reference ``np.dot(shift, cell)``.
        """
        cell = np.asarray(self.cell, dtype=float)
        cartesian = np.empty((shifts.shape[0], 3), dtype=float)
        for column in range(3):
            cartesian[:, column] = (
                shifts[:, 0] * cell[0, column]
                + shifts[:, 1] * cell[1, column]
                + shifts[:, 2] * cell[2, column]
            )
        return cartesian

    def _build_translations(self, images: List[Atoms]) -> np.ndarray:
        """Return per-image nearest-image translations for every atom pair.

        Preserve the historical 27-candidate tie order when it reaches a true
        nearest image. ASE's general MIC supplies the answer when a pair is
        unwrapped by multiple cells or a skew cell needs a farther lattice
        shift. This initialization snapshot is refreshed from current coordinates
        during each objective and force evaluation.

        Args:
            images: Full image list; only the intermediate images are measured.

        Returns:
            Array with shape ``(nimages, natoms, natoms, 3)``, all zeros when
            MIC is disabled.
        """
        translations = np.zeros((self.nimages, self.natoms, self.natoms, 3), dtype=float)
        if not self.mic:
            return translations
        tie_tol = self._mic_tie_tolerance()
        i_index, j_index = np.triu_indices(self.natoms, k=1)
        for image_index, image in enumerate(images[1:-1]):
            if not self.start_atoms.pbc.all():
                raw = image.positions[j_index] - image.positions[i_index]
                mic_vectors = find_mic(raw, self.cell, self.start_atoms.pbc)[0]
                shifts = np.rint((mic_vectors - raw) @ self.inv_cell)
                shifts[:, ~self.start_atoms.pbc] = 0
                cart_shift = self._mic_shift_cartesians(shifts)
                translations[image_index, i_index, j_index] = cart_shift
                translations[image_index, j_index, i_index] = -cart_shift
                continue
            frac = image.get_scaled_positions(wrap=False)
            frac_i = frac[i_index]
            frac_j = frac[j_index]
            for start in range(0, len(i_index), _MIC_PAIR_BLOCK):
                stop = start + _MIC_PAIR_BLOCK
                cartesian = self._mic_candidate_cartesians(frac_i[start:stop], frac_j[start:stop])
                distances = np.sum(cartesian * cartesian, axis=-1)
                selected = self._scan_nearest_candidates(distances, tie_tol)
                shifts = _MIC_SHIFT_CANDIDATES[selected].copy()
                raw = image.positions[j_index[start:stop]] - image.positions[i_index[start:stop]]
                mic_vectors = find_mic(raw, self.cell, self.start_atoms.pbc)[0]
                selected_distances = distances[np.arange(len(selected)), selected]
                mic_distances = np.sum(mic_vectors * mic_vectors, axis=-1)
                missed = selected_distances > mic_distances + tie_tol
                if np.any(missed):
                    shifts[missed] = np.rint((mic_vectors[missed] - raw[missed]) @ self.inv_cell)
                cart_shift = self._mic_shift_cartesians(shifts)
                translations[image_index, i_index[start:stop], j_index[start:stop]] = cart_shift
                translations[image_index, j_index[start:stop], i_index[start:stop]] = -cart_shift
        return translations

    def _nearest_image(self, frac_i: np.ndarray, frac_j: np.ndarray) -> np.ndarray:
        best_shift = np.zeros(3, dtype=float)
        best_distance = np.inf
        best_rank = (np.inf, (np.inf, np.inf, np.inf), (np.inf, np.inf, np.inf))
        tie_tol = self._mic_tie_tolerance()
        for sx in (-1, 0, 1):
            for sy in (-1, 0, 1):
                for sz in (-1, 0, 1):
                    shift = np.array([sx, sy, sz], dtype=float)
                    vector = np.dot(frac_j + shift - frac_i, self.cell)
                    distance = float(np.dot(vector, vector))
                    rank = (
                        float(np.dot(shift, shift)),
                        tuple(abs(int(value)) for value in shift),
                        tuple(int(value) for value in shift),
                    )
                    if distance < best_distance - tie_tol or (
                        abs(distance - best_distance) <= tie_tol and rank < best_rank
                    ):
                        best_distance = distance
                        best_shift = shift
                        best_rank = rank
        return best_shift

    def _validate_pair_geometry(self, positions: np.ndarray, image_index: int):
        """Return current upper-pair MIC vectors, rejecting undefined geometry.

        Args:
            positions: Cartesian atom positions for one image.
            image_index: Zero-based path frame index for the error context.

        Returns:
            Upper-triangle atom indices and the corresponding MIC vectors.

        Raises:
            ValueError: If positions are non-finite or a pair overlaps.
        """
        if not np.isfinite(positions).all():
            raise ValueError(f"IDPP image {image_index + 1}: positions must be finite")
        i_index, j_index = np.triu_indices(self.natoms, k=1)
        vectors = positions[j_index] - positions[i_index]
        if self.mic and len(vectors):
            vectors = find_mic(vectors, self.cell, self.start_atoms.pbc)[0]
        distances = np.linalg.norm(vectors, axis=1)
        overlapping = np.flatnonzero(distances <= 1e-12)
        if len(overlapping):
            pair = overlapping[0]
            raise ValueError(
                f"IDPP image {image_index + 1}: overlapping atoms "
                f"{i_index[pair] + 1}-{j_index[pair] + 1} under the active distance convention"
            )
        return i_index, j_index, vectors

    def _get_funcs_and_forces(self, coords: np.ndarray):
        """Evaluate the IDPP objective and its force on the same current MIC."""
        funcs = []
        forces = []
        eye = np.eye(self.natoms, dtype=float)
        for image_index in range(self.nimages):
            image_coords = coords[image_index + 1]
            i_index, j_index, pair_vectors = self._validate_pair_geometry(
                image_coords, image_index + 1
            )
            # Only solve each unordered pair once: MIC choices at an exact
            # half-cell tie need not be antisymmetric when solved separately.
            vectors = np.zeros((self.natoms, self.natoms, 3), dtype=float)
            vectors[i_index, j_index] = -pair_vectors
            vectors[j_index, i_index] = pair_vectors
            raw = image_coords[j_index] - image_coords[i_index]
            self.translations[image_index, i_index, j_index] = pair_vectors - raw
            self.translations[image_index, j_index, i_index] = raw - pair_vectors
            trial_dist = np.linalg.norm(vectors, axis=2)
            delta = trial_dist - self.target_dists[image_index]
            aux = delta * self.weights[image_index] / (trial_dist + eye)
            funcs.append(0.5 * np.sum(delta**2 * self.weights[image_index]))
            gradients = np.sum(aux[:, :, np.newaxis] * vectors, axis=1)
            forces.append(-2.0 * gradients)
        return np.array(funcs), np.array(forces)

    @staticmethod
    def _unit_vector(vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        if norm < 1e-15:
            return np.zeros_like(vector)
        return vector / norm

    def _get_total_forces(self, coords: np.ndarray, true_forces: np.ndarray, spring_const: float):
        total_forces = []
        displacements = np.diff(coords, axis=0)
        if self.mic:
            displacements = find_mic(
                displacements.reshape(-1, 3), self.cell, self.start_atoms.pbc
            )[0].reshape(displacements.shape)
        for image_index in range(1, len(coords) - 1):
            forward = displacements[image_index].ravel()
            backward = displacements[image_index - 1].ravel()
            tangent = self._unit_vector(self._unit_vector(forward) + self._unit_vector(backward))
            spring_force = spring_const * (np.linalg.norm(forward) - np.linalg.norm(backward)) * tangent
            flat_force = true_forces[image_index - 1].copy().ravel()
            total_force = true_forces[image_index - 1] + (
                spring_force - np.dot(flat_force, tangent) * tangent
            ).reshape(self.natoms, 3)
            total_forces.append(total_force)
        return np.array(total_forces)

    def run(
        self,
        maxiter=2000,
        tol=1e-4,
        gtol=1e-3,
        step_size=0.05,
        max_disp=0.05,
        spring_const=5.0,
        *,
        optimizer="fire",
    ):
        """Relax the band with FIRE or the historical clipped fixed step.

        FIRE changes only the update scheme; both optimizers use the same
        current-MIC objective, projected NEB force and ASE constraints. The
        convergence force is the maximum absolute Cartesian component, rather
        than ASE FIRE's default maximum per-atom Euclidean force norm.

        Args:
            maxiter: Maximum number of coordinate updates.
            tol: Required summed change in per-image IDPP objectives.
            gtol: Required maximum absolute projected band-force component.
            step_size: Fixed-step multiplier, used only by ``legacy``.
            max_disp: Per-coordinate displacement cap, used only by ``legacy``.
            spring_const: NEB spring constant used by both optimizers.
            optimizer: ``fire`` (default) or ``legacy``. FIRE uses ASE's
                ``dt=0.1``, ``dtmax=1.0`` and a global band-step cap of 0.2 Å.

        Returns:
            A private complete band, including the unchanged endpoints.

        Raises:
            ValueError: If the optimizer is unknown, maxiter is non-positive,
                or the evaluated geometry, objective or force is undefined.
        """
        if optimizer not in ("fire", "legacy"):
            raise ValueError("IDPP optimizer must be 'fire' or 'legacy'")
        if maxiter < 1:
            raise ValueError("IDPP maxiter must be positive")
        print(f"  [IDPP] Starting NEB-like optimization ({self.nimages} intermediate images, {optimizer})...")
        coords = np.array([img.get_positions() for img in self.images])
        # Public image objects can be edited after construction. Endpoints are
        # not evaluated by the interior force loop, including an empty band.
        for endpoint_index in (0, len(coords) - 1):
            self._validate_pair_geometry(coords[endpoint_index], endpoint_index)
        if self._has_constraints:
            self._project_positions(coords)
        old_funcs = np.zeros(self.nimages, dtype=float)
        final_funcs = old_funcs.copy()
        max_force = 0.0
        converged = not self.nimages
        iterations = 0

        if self.nimages:
            domain = _IDPPOptimizable(self, coords, spring_const=spring_const)
            # The projected NEB force is not the gradient of the summed IDPP
            # objective, so FIRE's optional energy-downhill check stays off.
            fire = (
                FIRE(domain, logfile=None, dt=0.1, dtmax=1.0, maxstep=0.2)
                if optimizer == "fire" else None
            )
            for step in range(maxiter):
                funcs, total_forces = domain.evaluate()
                max_force = float(np.abs(total_forces).max())
                residual = float(np.sum(np.abs(old_funcs - funcs)))
                final_funcs = funcs
                iterations = step + 1
                if residual < tol and max_force < gtol:
                    converged = True
                    break
                old_funcs = funcs.copy()
                if fire is not None:
                    # Calling step directly retains our component/residual
                    # stopping test and reuses the cached current force.
                    fire.step()
                else:
                    disp = step_size * total_forces
                    disp = np.where(np.abs(disp) > max_disp, np.sign(disp) * max_disp, disp)
                    domain.set_x(domain.get_x() + disp.ravel())
            else:
                # The last iteration performed a displacement. Report and
                # judge the returned state, including its constraint projection.
                final_funcs, total_forces = domain.evaluate()
                max_force = float(np.abs(total_forces).max())
                residual = float(np.sum(np.abs(old_funcs - final_funcs)))
                converged = residual < tol and max_force < gtol
                if not converged:
                    warnings.warn("IDPP did not fully converge: maximum iteration number reached")

        # Self-reported outcome, readable by callers that cannot rely on the
        # printed report (for example when the solver runs quietly inside an
        # optimizer step).  Field values match the report printed below.
        self.status = 'Converged' if converged else 'Failed'
        self.converged = bool(converged)
        self.iterations = int(iterations)
        self.final_s_idpp = float(np.sum(final_funcs))
        self.max_force = float(max_force)
        self.maxiter = int(maxiter)
        self.tol = float(tol)
        self.gtol = float(gtol)

        print("-" * 60)
        print("                 IDPP CONVERGENCE REPORT            ")
        print("-" * 60)
        print(f"  Status       : {'Converged' if converged else 'Failed'}")
        print(f"  Iterations   : {iterations}")
        print(f"  Final S_IDPP : {np.sum(final_funcs):.6f}")
        print(f"  Max Force    : {max_force:.6f} (Target: < {gtol})")
        print("-" * 60)
        
        final_images = []
        for i, image in enumerate(self.images):
            new_image = image.copy()
            new_image.set_positions(
                coords[i],
                apply_constraint=self._has_constraints and 0 < i < len(coords) - 1,
            )
            final_images.append(new_image)
        return final_images

    @classmethod
    def from_endpoints(cls, start: Atoms, end: Atoms, nimages: int, *, reference=None):
        initial_images = robust_interpolate(start, end, nimages, reference=reference)
        return cls(initial_images, reference=reference)


# ==========================================
# Helper Functions for Fix and Mag
# ==========================================

def set_fix_for_Atoms(atoms: Atoms, fix_height: float=0, fix_dir: int=1,):
    # maybe we should set constaints independently in here
    if fix_dir not in [0, 1, 2]:
        raise ValueError("fix_dir should be 0, 1 or 2 for x, y or z")
    direction = {0: "x", 1: "y", 2: "z"}
    mask = atoms.get_scaled_positions()[:, fix_dir] <= fix_height
    fix = FixAtoms(mask=mask)
    print(f"Fix Atoms below {fix_height} in direction {direction[fix_dir]}")
    if not any(
        isinstance(existing, FixAtoms) and np.array_equal(existing.index, fix.index)
        for existing in atoms.constraints
    ):
        atoms.set_constraint([*atoms.constraints, fix])

def set_magmom_for_Atoms(atoms: Atoms, mag_ele: list=[], mag_num: list=[]):
    """Set Atoms Object magmom by element"""
    # init magmom can only be set to intermediate images
    init_magmom = atoms.get_initial_magnetic_moments()
    if len(mag_ele) != len(mag_num):
        raise SyntaxWarning("mag_ele and mag_num have different length")
    for mag_pair in zip(mag_ele, mag_num):
        ele_ind = [atom.index for atom in atoms if atom.symbol == mag_pair[0]]
        init_magmom[ele_ind] = mag_pair[1]
    atoms.set_initial_magnetic_moments(init_magmom)
    print(f"Set initial magmom for {mag_ele} to {mag_num}")

# ==========================================
# NEB Initial Guess Path Generation
# ==========================================

def _apply_image_metadata(
    ase_path,
    is_atom,
    fs_atom,
    is_e,
    is_f,
    fs_e,
    fs_f,
    is_status,
    fs_status,
    fix_height,
    fix_dir,
    mag_ele,
    mag_num,
):
    ase_path[0].calc = SinglePointCalculator(ase_path[0].copy(), energy=is_e, forces=is_f)
    ase_path[-1].calc = SinglePointCalculator(ase_path[-1].copy(), energy=fs_e, forces=fs_f)
    mark_endpoint_result(ase_path[0], is_status)
    mark_endpoint_result(ase_path[-1], fs_status)

    if fix_height is not None:
        for image in ase_path[1:-1]:
            set_fix_for_Atoms(image, fix_height, fix_dir)

    if mag_ele is not None:
        for image in ase_path[1:-1]:
            set_magmom_for_Atoms(image, mag_ele, mag_num)
    return ase_path


#: Keys written into the optional ``path_status`` mapping of
#: :func:`interpolate_path` and :func:`_interpolate`.
_PATH_STATUS_KEYS = (
    'method',
    'status',
    'iterations',
    'maxiter',
    'final_S_IDPP',
    'max_force',
)


def _interpolate(
    method: str,
    start: Atoms,
    end: Atoms,
    n_images: int,
    tol: float,
    path_status: dict | None = None,
    *,
    reference=None,
    idpp_optimizer="fire",
):
    if method == 'IDPP':
        solver = Fast_IDPPSolver.from_endpoints(start, end, n_images, reference=reference)
        images = solver.run(tol=tol, optimizer=idpp_optimizer)
        if path_status is not None:
            path_status.update(
                method='IDPP',
                status=solver.status,
                iterations=solver.iterations,
                maxiter=solver.maxiter,
                final_S_IDPP=solver.final_s_idpp,
                max_force=solver.max_force,
            )
        return images
    if method == 'linear':
        # Linear interpolation reproduces the endpoints exactly and has no
        # iterative solver, so there is no convergence fact to report.
        return robust_interpolate(start, end, n_images, reference=reference)
    raise ValueError(f'{method} not supported')


def interpolate_path(
    start: Atoms,
    end: Atoms,
    n_images: int,
    method: str = 'IDPP',
    tol: float = 0.05,
    quiet: bool = False,
    *,
    path_status: dict | None = None,
    idpp_optimizer: str = 'fire',
) -> List[Atoms]:
    """Return an interpolated path between two endpoint structures.

    This is the public entry point for the path generator used by NEB input
    preparation; it does not run any energy or force evaluation.

    Args:
        start: Starting endpoint structure.
        end: Ending endpoint structure.
        n_images: Number of intermediate images between the endpoints.
        method: Interpolation method, ``IDPP`` or ``linear``.
        tol: Convergence tolerance forwarded to the IDPP relaxation.
        quiet: Suppress solver progress output on ``stdout`` when ``True``.
        idpp_optimizer: IDPP update scheme, ``fire`` (default) or ``legacy``.
        path_status: Optional mapping updated in place with the solver outcome,
            so callers that run quietly can still observe it.  It always
            receives the keys ``method``, ``status``, ``iterations``,
            ``maxiter``, ``final_S_IDPP`` and ``max_force``; ``status`` is
            ``"Converged"`` or ``"Failed"`` for ``IDPP``, while ``linear``
            reports its method with ``None`` values because that path is exact.

    Returns:
        Frame list with ``n_images + 2`` entries. Both endpoints are included
        at index ``0`` and ``-1`` with their input positions.

    Raises:
        ValueError: If ``method`` is not supported.
    """
    if path_status is not None:
        path_status.clear()
        path_status.update(dict.fromkeys(_PATH_STATUS_KEYS))
        path_status['method'] = method
    if quiet:
        with contextlib.redirect_stdout(io.StringIO()):
            return _interpolate(method, start, end, n_images, tol, path_status, idpp_optimizer=idpp_optimizer)
    return _interpolate(method, start, end, n_images, tol, path_status, idpp_optimizer=idpp_optimizer)


def generate(method:str, n_images:int, is_file:str, fs_file:str, 
             output_file:str, format:str,
             fix_height: float=None, fix_dir: int=None,
             mag_ele: list=None, mag_num: list=None,
             no_align: bool=False, tol: float=0.05,
             ts_file: str=None,
             endpoint_prepare: Callable[[Atoms, Atoms], None] | None=None,
             *, idpp_optimizer: str='fire', image_distribution: str='length'):
    """Generate a band, optionally preparing aligned endpoints before interpolation.

    ``endpoint_prepare`` is used by the NEB workflow to relax endpoints when
    their energy/force results are missing. Direct path generation remains a
    calculation-free operation when no callback is supplied.

    ``image_distribution`` allocates extra images by MIC endpoint chord length
    (``length``) or the historical ``equal`` split. A supplied TS frame is
    additional to ``n_images`` and retained exactly during generation. It is
    an intentional user-provided anchor, not a request to optimize it away.
    ``idpp_optimizer`` selects ``fire`` or historical ``legacy`` updates.
    """

    if idpp_optimizer not in ('fire', 'legacy'):
        raise ValueError("idpp_optimizer must be 'fire' or 'legacy'")
    if image_distribution not in ('length', 'equal'):
        raise ValueError("image_distribution must be 'length' or 'equal'")

    # 1. Read files
    print(f'Reading files: {is_file} and {fs_file}')
    is_atom = read_structure(is_file, format=format, parallel=False)
    fs_atom = read_structure(fs_file, format=format, parallel=False)
    is_atom, fs_atom = prepare_fixed_cell_images(
        [is_atom, fs_atom], context="Path generation"
    )

    # Align before reading cached forces so their atom order follows the output.
    if not no_align:
        print("Checking atom index consistency (Hungarian Algorithm)...")
        fs_atom = align_atom_indices(is_atom, fs_atom)
    else:
        print("Skipping atom index alignment.")

    if endpoint_prepare is not None:
        # The run-time endpoint Relax must see the same explicit fixed-atom and
        # magnetic setup requested for this path before it evaluates forces.
        # ASE invalidates a SinglePointCalculator when initial magmoms change;
        # this is not evidence that otherwise usable input E/F need Relax.
        for endpoint in (is_atom, fs_atom):
            cached = get_endpoint_results(endpoint)
            cp_facts = (
                read_constant_potential_facts(endpoint, check_geometry=False)
                if cached is not None else None
            )
            if fix_height is not None:
                set_fix_for_Atoms(endpoint, fix_height, fix_dir)
            if mag_ele is not None:
                set_magmom_for_Atoms(endpoint, mag_ele, mag_num)
            if cached is not None:
                freeze_results(endpoint, *cached, status=ENDPOINT_PROVIDED, cp_facts=cp_facts)
        endpoint_prepare(is_atom, fs_atom)
    
    # Store single point calculation results if available
    try:
        is_e = is_atom.get_potential_energy()
        is_f = is_atom.get_forces()
    except:
        is_e = 0.0
        is_f = np.zeros((len(is_atom), 3))
        is_status = ENDPOINT_PLACEHOLDER
    else:
        is_status = ENDPOINT_PROVIDED
        
    try:
        fs_e = fs_atom.get_potential_energy()
        fs_f = fs_atom.get_forces()
    except:
        fs_e = 0.0
        fs_f = np.zeros((len(fs_atom), 3))
        fs_status = ENDPOINT_PLACEHOLDER
    else:
        fs_status = ENDPOINT_PROVIDED

    # IDPP must see the optional fixed-height rule while it optimizes the
    # path.  Prepare private endpoint copies so the public endpoint frames
    # retain their input constraints and positions.
    interpolation_start = is_atom.copy()
    interpolation_end = fs_atom.copy()
    interpolation_ts = None
    if fix_height is not None:
        set_fix_for_Atoms(interpolation_start, fix_height, fix_dir)
        set_fix_for_Atoms(interpolation_end, fix_height, fix_dir)

    # 3. Generate Path
    print(f'Generating path, number of images: {n_images}')
    print(f'Optimizing path using {method} method')

    if ts_file is not None:
        print(f'Using TS guess for segmented interpolation: {ts_file}')
        ts_atom = read_structure(ts_file, format=format, parallel=False)
        ts_atom = prepare_fixed_cell_images(
            [is_atom, ts_atom], context="Path TS guess"
        )[-1]
        if not no_align:
            ts_atom = align_atom_indices(is_atom, ts_atom)
        interpolation_ts = ts_atom.copy()
        if fix_height is not None:
            set_fix_for_Atoms(interpolation_ts, fix_height, fix_dir)
        if image_distribution == 'length':
            left_count, right_count = allocate_segment_images(
                [interpolation_start, interpolation_ts, interpolation_end], n_images
            )
        else:
            left_count = n_images // 2
            right_count = n_images - left_count
        print(f"Segment image allocation ({image_distribution}): {left_count} + TS + {right_count}")
        left_path = _interpolate(method, interpolation_start, interpolation_ts, left_count, tol, reference=is_atom, idpp_optimizer=idpp_optimizer)
        right_path = _interpolate(method, interpolation_ts, interpolation_end, right_count, tol, reference=is_atom, idpp_optimizer=idpp_optimizer)
        ase_path = left_path[:-1] + right_path
    else:
        ase_path = _interpolate(method, interpolation_start, interpolation_end, n_images, tol, idpp_optimizer=idpp_optimizer)

    # Restore the prepared endpoint objects. The temporary copies above
    # exist only to carry generation constraints into IDPP.
    ase_path[0] = is_atom.copy()
    ase_path[-1] = fs_atom.copy()
    
    # 4. Post-processing: Add Calculator, Fix, Magmom
    _apply_image_metadata(
        ase_path,
        is_atom,
        fs_atom,
        is_e,
        is_f,
        fs_e,
        fs_f,
        is_status,
        fs_status,
        fix_height,
        fix_dir,
        mag_ele,
        mag_num,
    )

    # 5. Validate the actual path before publishing an input band.
    validate_path_geometry(ase_path, context="Generated NEB path")
    print(f'Writing path: {output_file}, Number of images: {len(ase_path)}')
    write(output_file, ase_path, parallel=False)
