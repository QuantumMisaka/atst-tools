# Calculator interface for ABACUS
# part of ATST-Tools

import os
from ase.calculators.abacus import Abacus, AbacusProfile

class AbacusCalculator:
    """Helper to setup ABACUS calculator"""
    
    @staticmethod
    def get_calculator(parameters: dict, directory: str, 
                      mpi: int = 1, omp: int = 1, 
                      abacus_cmd: str = 'abacus') -> Abacus:
        """
        Get Configured Abacus Calculator
        
        Args:
            parameters (dict): ABACUS input parameters
            directory (str): Calculation directory
            mpi (int): Number of MPI processes
            omp (int): Number of OpenMP threads
            abacus_cmd (str): Command to run ABACUS
        """
        os.environ['OMP_NUM_THREADS'] = f'{omp}'
        
        # Determine command
        if mpi > 1:
            command = f"mpirun -np {mpi} {abacus_cmd}"
        else:
            command = abacus_cmd
            
        profile = AbacusProfile(command=command)
        
        calc = Abacus(profile=profile, directory=directory, **parameters)
        return calc
