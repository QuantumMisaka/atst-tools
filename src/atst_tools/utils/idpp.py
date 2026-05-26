import numpy as np
import warnings
from typing import List

# ASE Imports
from ase import Atoms
from ase.io import read, write
from ase.constraints import FixAtoms
from ase.calculators.singlepoint import SinglePointCalculator
from atst_tools.utils.neb_endpoints import (
    ENDPOINT_PLACEHOLDER,
    ENDPOINT_PROVIDED,
    mark_endpoint_result,
)

# Scipy Imports
from scipy.optimize import linear_sum_assignment

def align_atom_indices(atoms_ref: Atoms, atoms_target: Atoms) -> Atoms:
    """
    Reorder indices of atoms_target to match atoms_ref as closely as possible.
    Note: This function ONLY swaps atom indices, NEVER moves atomic coordinates.
    """
    if len(atoms_ref) != len(atoms_target):
        raise ValueError(f"Atom count mismatch (Ref: {len(atoms_ref)}, Target: {len(atoms_target)})")
    
    new_indices = np.zeros(len(atoms_ref), dtype=int)
    
    # Pre-calculation
    cell = atoms_ref.get_cell()
    pbc = atoms_ref.get_pbc()
    # Calculate inverse cell only if PBC is on and cell is not zero volume
    if np.any(pbc) and np.linalg.det(cell) > 1e-8:
        inv_cell = np.linalg.inv(cell)
        use_mic = True
    else:
        use_mic = False
    
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
        if use_mic:
            scaled_diff = np.dot(diff, inv_cell)
            scaled_diff -= np.round(scaled_diff)
            diff = np.dot(scaled_diff, cell)
            
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
    
    # Reorder atoms according to new indices, inheriting ref's cell info
    sorted_atoms = atoms_target[new_indices]
    sorted_atoms.set_cell(atoms_ref.get_cell())
    sorted_atoms.set_pbc(atoms_ref.get_pbc())
    
    return sorted_atoms


def robust_interpolate(start_atoms: Atoms, end_atoms: Atoms, nimages: int) -> List[Atoms]:
    """Linear interpolation robust to Periodic Boundary Conditions (PBC)."""
    scaled_start = start_atoms.get_scaled_positions()
    scaled_end = end_atoms.get_scaled_positions()
    delta_scaled = scaled_end - scaled_start
    delta_scaled_mic = delta_scaled - np.round(delta_scaled)
    
    path = [start_atoms.copy()]
    total_steps = nimages + 1
    for i in range(1, total_steps):
        alpha = i / total_steps
        current_scaled_pos = scaled_start + alpha * delta_scaled_mic
        image = start_atoms.copy()
        image.set_scaled_positions(current_scaled_pos)
        path.append(image)
    path.append(end_atoms.copy())
    return path


class Fast_IDPPSolver:
    """
    IDPP solver compatible with pymatgen's NEB-like path relaxation.

    The implementation removes the runtime dependency on pymatgen while
    retaining its IDPP update scheme, which is used by the legacy examples.
    """
    def __init__(self, images: List[Atoms], mic: bool = True):
        self.start_atoms = images[0]
        self.end_atoms = images[-1]
        self.nimages = len(images) - 2
        self.natoms = len(self.start_atoms)
        self.cell = self.start_atoms.get_cell()
        self.images = images
        
        if mic and np.linalg.det(self.cell) > 1e-8:
            self.inv_cell = np.linalg.inv(self.cell)
            self.mic = True
        else:
            self.inv_cell = np.eye(3)
            self.mic = False

        d_start = self.start_atoms.get_all_distances(mic=self.mic)
        d_end = self.end_atoms.get_all_distances(mic=self.mic)
        
        factors = np.linspace(0, 1, self.nimages + 2)[1:-1]
        self.target_dists = d_start[None, :, :] + factors[:, None, None] * (d_end - d_start)[None, :, :]

        initial_distances = np.array([img.get_all_distances(mic=self.mic) for img in images[1:-1]])
        avg_dists = (self.target_dists + initial_distances) / 2.0
        self.weights = 1.0 / (avg_dists**4 + np.eye(self.natoms)[None, :, :] * 1e-8)
        self.translations = self._build_translations(images)
        self.initial_positions = np.array([img.get_positions() for img in images[1:-1]])

    def _build_translations(self, images: List[Atoms]) -> np.ndarray:
        translations = np.zeros((self.nimages, self.natoms, self.natoms, 3), dtype=float)
        if not self.mic:
            return translations
        for image_index, image in enumerate(images[1:-1]):
            frac = image.get_scaled_positions(wrap=False)
            for i in range(self.natoms):
                for j in range(i + 1, self.natoms):
                    shift = self._nearest_image(frac[i], frac[j])
                    cart_shift = np.dot(shift, self.cell)
                    translations[image_index, i, j] = cart_shift
                    translations[image_index, j, i] = -cart_shift
        return translations

    def _nearest_image(self, frac_i: np.ndarray, frac_j: np.ndarray) -> np.ndarray:
        best_shift = np.zeros(3, dtype=float)
        best_distance = np.inf
        for sx in (-1, 0, 1):
            for sy in (-1, 0, 1):
                for sz in (-1, 0, 1):
                    shift = np.array([sx, sy, sz], dtype=float)
                    vector = np.dot(frac_j + shift - frac_i, self.cell)
                    distance = float(np.dot(vector, vector))
                    if distance < best_distance:
                        best_distance = distance
                        best_shift = shift
        return best_shift

    def _get_funcs_and_forces(self, coords: np.ndarray):
        funcs = []
        forces = []
        eye = np.eye(self.natoms, dtype=float)
        for image_index in range(self.nimages):
            image_coords = coords[image_index + 1]
            vectors = (
                image_coords[:, np.newaxis, :]
                - image_coords[np.newaxis, :, :]
                - self.translations[image_index]
            )
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
        for image_index in range(1, len(coords) - 1):
            forward = (coords[image_index + 1] - coords[image_index]).ravel()
            backward = (coords[image_index] - coords[image_index - 1]).ravel()
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
    ):
        print(f"  [IDPP] Starting NEB-like optimization ({self.nimages} intermediate images)...")
        coords = np.array([img.get_positions() for img in self.images])
        old_funcs = np.zeros(self.nimages, dtype=float)
        final_funcs = old_funcs.copy()
        max_force = np.inf
        converged = False

        for step in range(maxiter):
            funcs, true_forces = self._get_funcs_and_forces(coords)
            total_forces = self._get_total_forces(coords, true_forces, spring_const=spring_const)

            disp = step_size * total_forces
            disp = np.where(np.abs(disp) > max_disp, np.sign(disp) * max_disp, disp)
            coords[1 : self.nimages + 1] += disp

            max_force = float(np.abs(total_forces).max())
            residual = float(np.sum(np.abs(old_funcs - funcs)))
            final_funcs = funcs
            if residual < tol and max_force < gtol:
                converged = True
                break
            old_funcs = funcs
        else:
            step = maxiter - 1
            warnings.warn("IDPP did not fully converge: maximum iteration number reached")

        print("-" * 60)
        print("                 IDPP CONVERGENCE REPORT            ")
        print("-" * 60)
        print(f"  Status       : {'Converged' if converged else 'Failed'}")
        print(f"  Iterations   : {step + 1}")
        print(f"  Final S_IDPP : {np.sum(final_funcs):.6f}")
        print(f"  Max Force    : {max_force:.6f} (Target: < {gtol})")
        print("-" * 60)
        
        final_images = []
        for i, image in enumerate(self.images):
            new_image = image.copy()
            new_image.set_positions(coords[i])
            final_images.append(new_image)
        return final_images

    @classmethod
    def from_endpoints(cls, start: Atoms, end: Atoms, nimages: int):
        initial_images = robust_interpolate(start, end, nimages)
        return cls(initial_images)


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
    atoms.set_constraint(fix)

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


def _interpolate(method: str, start: Atoms, end: Atoms, n_images: int, tol: float):
    if method == 'IDPP':
        solver = Fast_IDPPSolver.from_endpoints(start, end, n_images)
        return solver.run(tol=tol)
    if method == 'linear':
        return robust_interpolate(start, end, n_images)
    raise ValueError(f'{method} not supported')


def generate(method:str, n_images:int, is_file:str, fs_file:str, 
             output_file:str, format:str,
             fix_height: float=None, fix_dir: int=None,
             mag_ele: list=None, mag_num: list=None,
             no_align: bool=False, tol: float=0.05,
             ts_file: str=None):

    # 1. Read files
    print(f'Reading files: {is_file} and {fs_file}')
    is_atom = read(is_file, format=format)
    fs_atom = read(fs_file, format=format)
    
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

    # 2. Atom Index Alignment
    if not no_align:
        print("Checking atom index consistency (Hungarian Algorithm)...")
        try:
            fs_atom = align_atom_indices(is_atom, fs_atom)
        except Exception as e:
            print(f"❌ Alignment failed: {e}")
            return
    else:
        print("⚠️ Skipping atom index alignment.")

    # 3. Generate Path
    print(f'Generating path, number of images: {n_images}')
    print(f'Optimizing path using {method} method')

    if ts_file is not None:
        print(f'Using TS guess for segmented interpolation: {ts_file}')
        ts_atom = read(ts_file, format=format)
        if not no_align:
            ts_atom = align_atom_indices(is_atom, ts_atom)
        left_count = n_images // 2
        right_count = n_images - left_count
        left_path = _interpolate(method, is_atom, ts_atom, left_count, tol)
        right_path = _interpolate(method, ts_atom, fs_atom, right_count, tol)
        ase_path = left_path[:-1] + right_path
    else:
        ase_path = _interpolate(method, is_atom, fs_atom, n_images, tol)
    
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

    # 5. Write Output
    print(f'Writing path: {output_file}, Number of images: {len(ase_path)}')
    write(output_file, ase_path)
