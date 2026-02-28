import numpy as np
from typing import List, Tuple
from ase import Atoms

def get_displacement_analysis(neb_chain: List[Atoms], thr: float = 0.10) -> Tuple[int, List[int], np.ndarray]:
    """
    Analyze the NEB chain to find the transition state and the atoms with significant displacement.
    
    This function identifies the transition state (image with highest energy) and calculates
    the displacement vector of the reaction coordinate at the TS. It then identifies atoms
    that move significantly based on a threshold.

    Args:
        neb_chain (List[Atoms]): List of Atoms objects representing the NEB path.
        thr (float): Threshold for normalized displacement to consider an atom as "moving".
                     Default is 0.10.
        
    Returns:
        tuple: A tuple containing:
            - ts_index (int): Index of the transition state image.
            - main_indices (List[int]): List of indices of atoms with significant displacement.
            - norm_vector (np.ndarray): Normalized displacement vector (magnitude per atom).
    """
    # 1. Identify TS image (highest energy)
    energies = [image.get_potential_energy() if image.calc else image.info.get('energy', 0.0) for image in neb_chain]
    max_energy = max(energies)
    ts_index = energies.index(max_energy)
    
    # 2. Calculate displacement vector around TS
    # We look at the immediate neighbors of the TS. 
    idx_before = max(0, ts_index - 1)
    idx_after = min(len(neb_chain) - 1, ts_index + 1)
    
    if idx_before == idx_after:
        # Should not happen in a valid NEB chain unless length is 1
        return ts_index, [], np.zeros(0)

    img_before = neb_chain[idx_before]
    img_after = neb_chain[idx_after]
    
    # Calculate displacement
    displacement_vector = img_before.positions - img_after.positions
    
    # 3. Normalize and filter
    len_vector = np.linalg.norm(displacement_vector)
    if len_vector < 1e-6:
        return ts_index, [], np.zeros(len(displacement_vector))
        
    # Calculate norm of displacement per atom
    atom_displacements = np.linalg.norm(displacement_vector, axis=1)
    
    # Normalize by the total length of the mode vector
    norm_vector = atom_displacements / len_vector
    
    main_indices = [ind for ind, val in enumerate(norm_vector) if val > thr]
    
    return ts_index, main_indices, norm_vector
