# AbacusDimer implementation
# part of ATST-Tools

import os
import numpy as np
from ase.io import Trajectory
from ase.mep import DimerControl, MinModeAtoms, MinModeTranslate
from ase.calculators.abacus import AbacusProfile, Abacus
from typing import List, Union

class AbacusDimer:
    """Customize Dimer calculation workflow by using ABACUS"""
    
    def __init__(self, init_Atoms, parameters, abacus='abacus',
                 mpi=1, omp=1, directory='ABACUS', 
                 traj_file='run_dimer.traj',
                 init_eigenmode_method='displacement',
                 displacement_vector: np.ndarray = None,
                 dimer_separation=0.01,
                 max_num_rot=3):
        """Initialize Dimer method by using ASE-ABACUS"""
        self.init_Atoms = init_Atoms
        self.parameters = parameters
        self.abacus = abacus
        self.mpi = mpi
        self.omp = omp
        self.directory = directory
        self.traj_file = traj_file
        self.init_eigenmode_method = init_eigenmode_method
        self.displacement_vector = displacement_vector
        self.dimer_separation = dimer_separation
        self.max_num_rot = max_num_rot
        
    def set_calculator(self):
        """Set Abacus calculators"""
        os.environ['OMP_NUM_THREADS'] = f'{self.omp}'
        # Use mpirun if mpi > 1
        if self.mpi > 1:
            command = f"mpirun -np {self.mpi} {self.abacus}"
        else:
            command = self.abacus
            
        profile = AbacusProfile(command=command)
        out_directory = self.directory
        calc = Abacus(profile=profile, directory=out_directory,
                        **self.parameters)
        return calc
    
    def set_d_mask_by_displacement(self):
        """set mask by displacement"""
        print("=== Set mask by displacement vector where displacement is [0,0,0] ===")
        if self.displacement_vector is None:
            raise ValueError("Displacement vector is None")
        d_mask = self.displacement_vector != np.zeros(3)
        d_mask = d_mask[:,0].tolist()
        return d_mask
    
    def set_d_mask_by_constraint(self):
        """set mask by constraint of Atoms"""
        print("=== Set mask by constraint read from init Atoms ===")
        dimer_init = self.init_Atoms
        d_mask = [True] * len(dimer_init)
        const = dimer_init.constraints
        # const will be empty list if no constraint
        if const:
            # Assuming the first constraint is FixAtoms or similar
            # that has get_indices()
            try:
                const_object = const[0].get_indices()
                for ind in const_object:
                    d_mask[ind] = False
                return d_mask
            except AttributeError:
                print("--- Warning: Constraint does not support get_indices(), ignoring ---")
                return d_mask
        else:
            print("--- Notice: No constraint found in init Atoms, there will be no mask in dimer calculation ---")
            return d_mask
    
    def set_d_mask_by_specified(self, moving_atoms_ind: list):
        """set mask be choosing moving atoms, the others are masked"""
        print(f"=== Set mask by specifing moving atoms {moving_atoms_ind} ===")
        dimer_init = self.init_Atoms
        d_mask = [False] * len(dimer_init)
        for ind in moving_atoms_ind:
            d_mask[ind] = True
        return d_mask
        
    def run(self, fmax=0.05, properties=["energy", "forces", "stress"], moving_atoms_ind: list = None):
        """run dimer calculation workflow"""
        dimer_init = self.init_Atoms
        dimer_init.calc = self.set_calculator()
        dimer_traj = Trajectory(self.traj_file, 'w', dimer_init, properties=properties)
        
        if self.init_eigenmode_method == "displacement":
            if moving_atoms_ind:
                d_mask = self.set_d_mask_by_specified(moving_atoms_ind)
            else:
                d_mask = self.set_d_mask_by_constraint()
                
            d_control = DimerControl(
                                    initial_eigenmode_method=self.init_eigenmode_method, 
                                    displacement_method="vector", 
                                    mask=d_mask,
                                    dimer_separation=self.dimer_separation,
                                    max_num_rot=self.max_num_rot,
                                    )
            d_atoms = MinModeAtoms(dimer_init, d_control)
            d_atoms.displace(displacement_vector=self.displacement_vector)
            
        elif self.init_eigenmode_method == "gauss":
            # leave a way for random displacement
            d_mask = self.set_d_mask_by_constraint()
            d_control = DimerControl(
                                    initial_eigenmode_method=self.init_eigenmode_method, 
                                    mask=d_mask,
                                    dimer_separation=self.dimer_separation,
                                    max_num_rot=self.max_num_rot,
                                    )
            d_atoms = MinModeAtoms(dimer_init, d_control)
        else:
            raise ValueError("init_eigenmode_method must be displacement or gauss")
            
        dimer_relax = MinModeTranslate(d_atoms, trajectory=dimer_traj)
        dimer_relax.run(fmax=fmax)
