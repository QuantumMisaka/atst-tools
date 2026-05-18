# AbacusDimer implementation
# part of ATST-Tools

import numpy as np
from ase.mep import DimerControl, MinModeAtoms, MinModeTranslate as _ASEMinModeTranslate
from ase.mep.dimer import norm, normalize
from typing import List, Union

from atst_tools.calculators.factory import CalculatorFactory


class MinModeTranslate(_ASEMinModeTranslate):
    """ASE Dimer translator with local divergence/NaN-step backport.

    Backport source: development `ase/ase` commits `0072551d6` and
    `849c29d51`. Remove this subclass when the validated production ASE
    release includes the same checks in `ase.mep.dimer.MinModeTranslate`.
    """

    def step(self, f=None):
        """Perform one minimum-mode translation step."""
        atoms = self.dimeratoms
        if f is None:
            f = atoms.get_forces()
        r = atoms.get_positions()
        curv = atoms.get_curvature()
        f0p = f.copy()
        r0 = r.copy()
        direction = f0p.copy()
        if self.cg_on:
            direction = self.get_cg_direction(direction)
        if norm(direction) == np.inf:
            raise RuntimeError("Dimer calculation diverged")
        direction = normalize(direction)
        if curv > 0.0:
            step = direction * self.max_step
        else:
            r0t = r0 + direction * self.trial_step
            f0tp = self.dimeratoms.get_projected_forces(r0t)
            force = np.vdot((f0tp + f0p), direction) / 2.0
            curvature = np.vdot((f0tp - f0p), direction) / self.trial_step
            step = (-force / curvature + self.trial_step / 2.0) * direction
            if norm(step) > self.max_step or np.isnan(norm(step)):
                step = direction * self.max_step
        self.log(f0p, norm(step))

        atoms.set_positions(r + step)

        self.f0 = f.flat.copy()
        self.r0 = r.flat.copy()


class AbacusDimer:
    """
    Customize Dimer calculation workflow by using ABACUS.
    
    This class manages the setup and execution of the Dimer method for finding
    saddle points (Transition States) using ABACUS as the force calculator.

    Attributes:
        init_Atoms (Atoms): Initial structure (guess for TS).
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        traj_file (str): Output trajectory file.
        init_eigenmode_method (str): Method to initialize eigenmode ('displacement' or 'gauss').
        displacement_vector (np.ndarray): Displacement vector for initialization.
        dimer_separation (float): Separation between dimer images.
        max_num_rot (int): Maximum number of rotations per step.
    """
    
    def __init__(self, init_Atoms, config, calc_name, calc_config,
                 traj_file='run_dimer.traj',
                 init_eigenmode_method='displacement',
                 displacement_vector: np.ndarray = None,
                 dimer_separation=0.01,
                 max_num_rot=3):
        """
        Initialize Dimer method by using ASE-ABACUS.

        Args:
            init_Atoms (Atoms): Initial Atoms object.
            config (dict): Global configuration dictionary.
            calc_name (str): Name of the calculator.
            calc_config (dict): Calculation configuration dictionary.
            traj_file (str): Path to output trajectory file.
            init_eigenmode_method (str): 'displacement' or 'gauss'.
            displacement_vector (np.ndarray, optional): Vector for initial displacement.
            dimer_separation (float): Finite difference separation.
            max_num_rot (int): Max rotations.
        """
        self.init_Atoms = init_Atoms
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.traj_file = traj_file
        self.init_eigenmode_method = init_eigenmode_method
        self.displacement_vector = displacement_vector
        self.dimer_separation = dimer_separation
        self.max_num_rot = max_num_rot
        
    def set_calculator(self):
        """
        Set calculators using Factory.

        Returns:
            Calculator: Configured calculator instance.
        """
        directory = self.calc_config.get('directory', 'dimer_run')
        if 'abacus' in self.config:
             directory = self.config['abacus'].get('directory', directory)
        
        return CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )
    
    def set_d_mask_by_displacement(self):
        """
        Set mask by displacement vector where displacement is [0,0,0].

        Returns:
            list: Boolean mask list.
        """
        print("=== Set mask by displacement vector where displacement is [0,0,0] ===")
        if self.displacement_vector is None:
            raise ValueError("Displacement vector is None")
        displacement = np.asarray(self.displacement_vector)
        if displacement.ndim != 2 or displacement.shape[1] != 3:
            raise ValueError("displacement_vector must have shape (natoms, 3)")
        d_mask = (np.linalg.norm(displacement, axis=1) > 0.0).tolist()
        return d_mask
    
    def set_d_mask_by_constraint(self):
        """
        Set mask by constraint of Atoms.

        Returns:
            list: Boolean mask list based on constraints.
        """
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
        """
        Set mask by choosing moving atoms, the others are masked.

        Args:
            moving_atoms_ind (list): List of indices of atoms allowed to move.

        Returns:
            list: Boolean mask list.
        """
        print(f"=== Set mask by specifing moving atoms {moving_atoms_ind} ===")
        dimer_init = self.init_Atoms
        d_mask = [False] * len(dimer_init)
        for ind in moving_atoms_ind:
            d_mask[ind] = True
        return d_mask
        
    def run(self, fmax=0.05, properties=["energy", "forces", "stress"], moving_atoms_ind: list = None,
            max_steps: int = None):
        """
        Run dimer calculation workflow.

        Args:
            fmax (float): Force convergence criterion.
            properties (list): Properties to calculate.
            moving_atoms_ind (list, optional): List of moving atom indices.
        """
        dimer_init = self.init_Atoms
        dimer_init.calc = self.set_calculator()
        
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
            
        # MinModeTranslate is the optimizer
        dimer_relax = MinModeTranslate(d_atoms, trajectory=self.traj_file)
        if max_steps is None:
            dimer_relax.run(fmax=fmax)
        else:
            dimer_relax.run(fmax=fmax, steps=max_steps)
