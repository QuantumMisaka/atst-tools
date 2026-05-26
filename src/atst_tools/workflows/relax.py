# Relax Workflow
# part of ATST-Tools

import os
from ase.io import write
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.io import read_structure
from atst_tools.utils.restart_helpers import get_last_frame

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
        self.calc_config = calc_config if "config_version" in config else apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.fmax = calc_config['fmax']
        self.max_steps = calc_config['max_steps']
        self.optimizer_name = calc_config['optimizer']
        self.traj_file = calc_config['trajectory']
        self.logfile = calc_config['logfile']
        self.init_structure = calc_config['init_structure']
        self.restart = calc_config['restart']

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
        if self.restart:
            atoms = get_last_frame(self.traj_file)
        elif not os.path.exists(input_structure):
             # Try traj
             if os.path.exists('init.traj'):
                 input_structure = 'init.traj'
             else:
                 raise FileNotFoundError(f"Initial structure {input_structure} not found")
        else:
            try:
                atoms = read_structure(input_structure)
            except Exception as e:
                print(f"Error reading structure: {e}")
                raise

        # 2. Setup Calculator
        # Extract directory from config or use default
        directory = self.calc_config['directory']
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
