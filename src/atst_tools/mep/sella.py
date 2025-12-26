# AbacusSella implementation
# part of ATST-Tools

import os
from ase.io import Trajectory
from ase.calculators.abacus import AbacusProfile, Abacus
from sella import Sella, Constraints

class AbacusSella:
    """Customize Sella calculation workflow by using ABACUS"""
    
    def __init__(self, init_Atoms, parameters, abacus='abacus',
                 mpi=1, omp=1, directory='ABACUS', 
                 traj_file='run_sella.traj',
                 sella_eta=0.005,
                 fmax=0.05):
        """Initialize Sella method by using ASE-ABACUS"""
        self.init_Atoms = init_Atoms
        self.parameters = parameters
        self.abacus = abacus
        self.mpi = mpi
        self.omp = omp
        self.directory = directory
        self.traj_file = traj_file
        self.sella_eta = sella_eta
        self.fmax = fmax
        
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
    
    def run(self, fmax=None):
        """run sella calculation workflow"""
        if fmax is None:
            fmax = self.fmax
            
        ts_atoms = self.init_Atoms
        ts_atoms.calc = self.set_calculator()
        
        # Setup Sella constraints if any
        # Sella handles constraints internally but we can also use ase constraints
        # cons = Constraints(ts_atoms) 
        # For now, we rely on Sella's default handling of ASE constraints
        
        traj = Trajectory(self.traj_file, 'w', ts_atoms)
        
        dyn = Sella(
            ts_atoms,
            trajectory=traj,
            eta = self.sella_eta,
        )
        
        dyn.run(fmax=fmax)
        return ts_atoms
