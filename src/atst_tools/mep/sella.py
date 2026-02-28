# AbacusSella implementation
# part of ATST-Tools

from ase.io import Trajectory
from sella import Sella

from atst_tools.calculators.factory import CalculatorFactory

class AbacusSella:
    """
    Customize Sella calculation workflow by using ABACUS.
    
    This class manages the setup and execution of the Sella method for finding
    saddle points (Transition States) using ABACUS as the force calculator.

    Attributes:
        init_Atoms (Atoms): Initial structure (guess for TS).
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        traj_file (str): Output trajectory file.
        sella_eta (float): Sella eta parameter.
        fmax (float): Force convergence criterion.
    """
    
    def __init__(self, init_Atoms, config, calc_name, calc_config,
                 traj_file='run_sella.traj',
                 sella_eta=0.005,
                 fmax=0.05):
        """
        Initialize Sella method by using ASE-ABACUS.

        Args:
            init_Atoms (Atoms): Initial Atoms object.
            config (dict): Global configuration dictionary.
            calc_name (str): Name of the calculator.
            calc_config (dict): Calculation configuration dictionary.
            traj_file (str): Path to output trajectory file.
            sella_eta (float): Sella eta parameter.
            fmax (float): Force convergence criterion.
        """
        self.init_Atoms = init_Atoms
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.traj_file = traj_file
        self.sella_eta = sella_eta
        self.fmax = fmax
        
    def set_calculator(self):
        """
        Set calculators using Factory.

        Returns:
            Calculator: Configured calculator instance.
        """
        directory = self.calc_config.get('directory', 'sella_run')
        if 'abacus' in self.config:
             directory = self.config['abacus'].get('directory', directory)
        
        return CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )
    
    def run(self, fmax=None):
        """
        Run Sella calculation workflow.

        Args:
            fmax (float, optional): Force convergence criterion.
            
        Returns:
            Atoms: The optimized transition state structure.
        """
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
