# Relax Workflow
# part of ATST-Tools

import os
from ase.io import read, write
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.io import read_structure

class RelaxWorkflow:
    """
    Workflow for geometry optimization (relaxation).

    Attributes:
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        fmax (float): Force convergence criterion.
        max_steps (int): Maximum optimization steps.
        optimizer_name (str): Name of optimizer.
        traj_file (str): Output trajectory file.
        logfile (str): Log file path.
        init_structure (str): Path to initial structure file.
    """
    
    def __init__(self, config, calc_name, calc_config):
        """
        Initialize RelaxWorkflow.

        Args:
            config (dict): Global configuration.
            calc_name (str): Calculator name.
            calc_config (dict): Calculation configuration.
        """
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.fmax = calc_config.get('fmax', 0.05)
        self.max_steps = calc_config.get('max_steps', 200)
        self.optimizer_name = calc_config.get('optimizer', 'FIRE')
        self.traj_file = calc_config.get('trajectory', 'relax.traj')
        self.logfile = calc_config.get('logfile', 'relax.log')
        self.init_structure = calc_config.get('init_structure', 'init.stru')
        self.restart = calc_config.get('restart', False)

    def _get_optimizer(self):
        """
        Get the optimizer class.

        Returns:
            class: ASE optimizer class.
        """
        if self.optimizer_name.upper() == 'FIRE':
            return FIRE
        elif self.optimizer_name.upper() == 'BFGS':
            return BFGS
        elif self.optimizer_name.upper() == 'LBFGS':
            return LBFGS
        elif self.optimizer_name.upper() == 'QUASINEWTON':
            return QuasiNewton
        else:
            print(f"Warning: Unknown optimizer {self.optimizer_name}, defaulting to FIRE")
            return FIRE

    def run(self):
        """
        Execute the relaxation workflow.
        """
        print(f"=== Starting Relaxation with {self.calc_name} ===")
        
        # 1. Read Structure
        input_structure = self.init_structure
        if self.restart and os.path.exists(self.traj_file):
            input_structure = self.traj_file

        if not os.path.exists(input_structure):
             # Try traj
             if os.path.exists('init.traj'):
                 input_structure = 'init.traj'
             else:
                 raise FileNotFoundError(f"Initial structure {input_structure} not found")

        try:
            # Try reading as abacus format first if suffix matches or generic
            if self.restart and input_structure == self.traj_file:
                atoms = read(input_structure, index=-1)
            else:
                atoms = read_structure(input_structure)
        except Exception as e:
            print(f"Error reading structure: {e}")
            raise

        # 2. Setup Calculator
        # Extract directory from config or use default
        directory = self.calc_config.get('directory', 'relax_run')
        if 'abacus' in self.config:
             # Fallback to old config location if present
             directory = self.config['abacus'].get('directory', directory)
        
        atoms.calc = CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )

        # 3. Setup Optimizer
        Optimizer = self._get_optimizer()
        opt = Optimizer(atoms, trajectory=self.traj_file, logfile=self.logfile)
        
        # 4. Run
        opt.run(fmax=self.fmax, steps=self.max_steps)
        
        # 5. Save Final Structure
        write("final_relaxed.traj", atoms)
        # Also write standard format like xyz or poscar/stru
        # write("final_relaxed.stru", atoms, format='abacus') # Need ase-abacus support for this format string or use ext
        
        print(f"=== Relaxation Finished. Final energy: {atoms.get_potential_energy():.4f} eV ===")
