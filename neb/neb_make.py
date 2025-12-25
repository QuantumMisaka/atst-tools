import argparse
import numpy as np
import warnings
from typing import List

# ASE Imports
from ase import Atoms
from ase.io import read, write
from ase.constraints import FixAtoms
from ase.calculators.singlepoint import SinglePointCalculator

# Scipy Imports
from scipy.optimize import linear_sum_assignment, minimize

'''
Refactored by JamesMisaka/ATST-Tools
Based on original work by mosey and enhanced with Fast_IDPPSolver and Hungarian Algorithm

Dependencies:
1. scipy: pip install scipy
2. ase: pip install ase
'''

# ==========================================
# Aligning Algorithm & FastIDPP Solver Contritubed by Jerry
# ==========================================

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
    Fast IDPP Solver based on Scipy L-BFGS-B.
    Removes dependency on pymatgen.
    """
    def __init__(self, images: List[Atoms], mic: bool = True):
        self.start_atoms = images[0]
        self.end_atoms = images[-1]
        self.nimages = len(images) - 2
        self.natoms = len(self.start_atoms)
        self.cell = self.start_atoms.get_cell()
        
        if mic and np.linalg.det(self.cell) > 1e-8:
            self.inv_cell = np.linalg.inv(self.cell)
            self.mic = True
        else:
            self.inv_cell = np.eye(3)
            self.mic = False

        # 1. Pre-calculate target distance matrices
        d_start = self.start_atoms.get_all_distances(mic=self.mic)
        d_end = self.end_atoms.get_all_distances(mic=self.mic)
        
        factors = np.linspace(0, 1, self.nimages + 2)[1:-1]
        self.target_dists = d_start[None, :, :] + factors[:, None, None] * (d_end - d_start)[None, :, :]

        # 2. Pre-calculate weights
        avg_dists = (d_start[None, :, :] + d_end[None, :, :]) / 2.0 
        self.weights = 1.0 / (avg_dists**4 + np.eye(self.natoms)[None, :, :] * 1e-12)

        self.initial_positions = np.array([img.get_positions() for img in images[1:-1]])

    def _objective_function(self, flat_coords):
        coords = flat_coords.reshape((self.nimages, self.natoms, 3))
        
        if self.mic:
            scaled_coords = np.dot(coords, self.inv_cell)
            diff_scaled = scaled_coords[:, :, None, :] - scaled_coords[:, None, :, :]
            diff_scaled -= np.round(diff_scaled)
            vectors = np.dot(diff_scaled, self.cell)
        else:
            vectors = coords[:, :, None, :] - coords[:, None, :, :]

        current_dists = np.linalg.norm(vectors, axis=3)
        delta_dists = current_dists - self.target_dists
        energy = 0.5 * np.sum(self.weights * delta_dists**2)

        with np.errstate(divide='ignore', invalid='ignore'):
            prefactor = (self.weights * delta_dists) / (current_dists + 1e-12)
        
        gradients = 2.0 * np.einsum('nij,nijk->nik', prefactor, vectors)
        return energy, gradients.flatten()

    def run(self, maxiter=2000, tol=1e-4):
        print(f"  [IDPP] Starting L-BFGS-B optimization ({self.nimages} intermediate images)...")
        x0 = self.initial_positions.flatten()
        res = minimize(
            self._objective_function, x0, method='L-BFGS-B', jac=True, 
            options={'maxiter': maxiter, 'gtol': tol, 'disp': False}
        )
        
        final_grads = res.jac.reshape((self.nimages, self.natoms, 3))
        fmax = np.max(np.linalg.norm(final_grads, axis=2))
        
        print("-" * 60)
        print("                 IDPP CONVERGENCE REPORT            ")
        print("-" * 60)
        print(f"  Status       : {'✅ Converged' if res.success else '❌ Failed'}")
        print(f"  Message      : {res.message}")
        print(f"  Iterations   : {res.nit}")
        print(f"  Final S_IDPP : {res.fun:.6f}")
        print(f"  Max Force    : {fmax:.6f} (Target: < {tol})")
        print("-" * 60)

        if not res.success:
            warnings.warn(f"IDPP did not fully converge: {res.message}")

        optimized_coords = res.x.reshape((self.nimages, self.natoms, 3))
        final_images = [self.start_atoms.copy()]
        for i in range(self.nimages):
            img = self.start_atoms.copy()
            img.set_positions(optimized_coords[i])
            final_images.append(img)
        final_images.append(self.end_atoms.copy())
        
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

def generate(method:str, n_images:int, is_file:str, fs_file:str, 
             output_file:str, format:str,
             fix_height: float=None, fix_dir: int=None,
             mag_ele: list=None, mag_num: list=None,
             no_align: bool=False, tol: float=0.05):

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
        
    try:
        fs_e = fs_atom.get_potential_energy()
        fs_f = fs_atom.get_forces()
    except:
        fs_e = 0.0
        fs_f = np.zeros((len(fs_atom), 3))

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
    
    if method == 'IDPP':
        solver = Fast_IDPPSolver.from_endpoints(is_atom, fs_atom, n_images)
        ase_path = solver.run(tol=tol)
    elif method == 'linear':
        ase_path = robust_interpolate(is_atom, fs_atom, n_images)
    else:
        raise ValueError(f'{method} not supported')
    
    # 4. Post-processing: Add Calculator, Fix, Magmom
    ase_path[0].calc = SinglePointCalculator(ase_path[0].copy(), energy=is_e, forces=is_f)
    ase_path[-1].calc = SinglePointCalculator(ase_path[-1].copy(), energy=fs_e, forces=fs_f)

    if fix_height is not None:
        for image in ase_path[1:-1]:
            set_fix_for_Atoms(image, fix_height, fix_dir)
    
    if mag_ele is not None:
        for image in ase_path[1:-1]:
            set_magmom_for_Atoms(image, mag_ele, mag_num)

    # 5. Write Output
    print(f'Writing path: {output_file}, Number of images: {len(ase_path)}')
    write(output_file, ase_path)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Make input files for NEB calculation')
    parser.add_argument('-n', type=int, help='Number of intermediate images', required=True)
    parser.add_argument('-f','--format', type=str, default=None, help='Format of the input files (e.g., abacus-out, extxyz, cif)')
    parser.add_argument('-i', '--input',type=str, default=None, help='IS and FS file', nargs=2, required=True)
    parser.add_argument('-m', '--method',type=str, default='IDPP', help='Method to generate images', choices=['IDPP','linear'])
    parser.add_argument('-o', type=str, default='init_neb_chain.traj', help='Output file')
    parser.add_argument('--no-align', action='store_true', help='Skip atom index alignment')
    parser.add_argument('--tol', type=float, default=0.05, help='IDPP convergence tolerance (eV/A, default: 0.05)')
    parser.add_argument('--fix', type=str, default=None, help='[height]:[direction] : fix atom below height (fractional) in direction (0,1,2 for x,y,z), default None')
    parser.add_argument('--mag',type=str, default=None, help='[element1]:[magmom1],[element2]:[magmom2],... : set initial magmom for atoms of element, default None')

    args = parser.parse_args()

    fix_height = None
    fix_dir = None
    mag_ele = None
    mag_num = None

    if args.fix:
        fix_height, fix_dir = args.fix.split(':')
        fix_height = float(fix_height)
        fix_dir = int(fix_dir)
    if args.mag:
        mag_ele = [i.split(':')[0] for i in args.mag.split(',')]
        mag_num = [float(i.split(':')[1]) for i in args.mag.split(',')]
    
    generate(method=args.method, n_images=args.n, is_file=args.input[0], fs_file=args.input[1], 
             output_file=args.o, format=args.format,
             fix_height=fix_height, fix_dir=fix_dir,
             mag_ele=mag_ele, mag_num=mag_num,
             no_align=args.no_align, tol=args.tol)
if __name__ == '__main__':
    main()
