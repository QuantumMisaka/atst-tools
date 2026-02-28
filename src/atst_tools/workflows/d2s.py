# D2S (Double-to-Single) Workflow
# part of ATST-Tools

import os
import numpy as np
from ase.io import read, write
from ase.mep.neb import DyNEB
from ase.optimize import FIRE, QuasiNewton

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.idpp import Fast_IDPPSolver
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella

class D2SWorkflow:
    """
    Double-to-Single (D2S) Workflow:
    1. Optimize IS/FS (Optional)
    2. Generate Rough NEB Path (IDPP)
    3. Run Rough NEB
    4. Pick highest image
    5. Run Single-Ended Search (Dimer/Sella)
    """
    
    def __init__(self, config, dft_params, mpi, omp, abacus_cmd, directory):
        """
        Initialize D2S Workflow.

        Args:
            config (dict): Workflow configuration.
            dft_params (dict): DFT calculator parameters.
            mpi (int): Number of MPI processes.
            omp (int): Number of OpenMP threads.
            abacus_cmd (str): Command to run ABACUS.
            directory (str): Base directory for calculation.
        """
        self.config = config
        self.dft_params = dft_params
        self.mpi = mpi
        self.omp = omp
        self.abacus_cmd = abacus_cmd
        self.directory = directory
        
        # Parse D2S config
        self.method = config.get('method', 'dimer') # dimer or sella
        self.neb_config = config.get('neb', {})
        self.single_config = config.get(self.method, {})

    def _get_calc(self, sub_dir):
        """
        Helper to get calculator with specific directory using CalculatorFactory.
        
        Args:
            sub_dir (str): Sub-directory for calculation.
            
        Returns:
            Calculator: Configured calculator instance.
        """
        # Create a config dict compatible with CalculatorFactory
        # We need to wrap dft_params into the expected structure
        calc_config = {
            'calculator': {
                'name': 'abacus',
                'abacus': self.dft_params
            },
            'command': self.abacus_cmd
        }
        
        return CalculatorFactory.get_calculator(
            'abacus', 
            calc_config, 
            directory=os.path.join(self.directory, sub_dir),
            mpi=self.mpi,
            omp=self.omp
        )

    def optimize_endpoints(self, init_atoms, final_atoms):
        """
        Optimize Initial and Final States.

        Args:
            init_atoms (Atoms): Initial structure.
            final_atoms (Atoms): Final structure.

        Returns:
            tuple: (optimized_init_atoms, optimized_final_atoms)
        """
        print("=== Step 1: Optimizing Endpoints ===")
        
        # Optimize IS
        print("  Optimizing Initial State (IS)...")
        init_atoms.calc = self._get_calc("IS_OPT")
        opt_is = QuasiNewton(init_atoms, logfile='opt_is.log')
        opt_is.run(fmax=0.05)
        write("IS_opt.traj", init_atoms)
        
        # Optimize FS
        print("  Optimizing Final State (FS)...")
        final_atoms.calc = self._get_calc("FS_OPT")
        opt_fs = QuasiNewton(final_atoms, logfile='opt_fs.log')
        opt_fs.run(fmax=0.05)
        write("FS_opt.traj", final_atoms)
        
        return init_atoms, final_atoms

    def run_rough_neb(self, init_atoms, final_atoms):
        """
        Run Rough NEB to find approximate TS.

        Args:
            init_atoms (Atoms): Initial structure.
            final_atoms (Atoms): Final structure.

        Returns:
            list: List of Atoms objects representing the rough NEB path.
        """
        print("=== Step 2: Running Rough NEB ===")
        
        n_images = self.neb_config.get('n_images', 8)
        fmax = self.neb_config.get('fmax', 0.8) # Rough convergence
        algorism = self.neb_config.get('algorism', 'improvedtangent')
        climb = self.neb_config.get('climb', True)
        
        print(f"  Generating {n_images} images via IDPP...")
        
        solver = Fast_IDPPSolver.from_endpoints(init_atoms, final_atoms, n_images)
        images = solver.run() # This returns the path list [IS, img1...imgN, FS]
        
        # Attach Calculators
        # We'll stick to serial DyNEB for "Rough" phase unless configured otherwise
        # to avoid massive resource usage for a rough guess.
        
        for i, img in enumerate(images[1:-1]):
            img.calc = self._get_calc("NEB") # Shared directory for serial? Or NEB_image?
            # DyNEB usually runs images one by one or needs allow_shared_calculator=True
        
        # Use DyNEB
        neb = DyNEB(images, climb=climb, dynamic_relaxation=True, fmax=fmax,
                    method=algorism, parallel=False, allow_shared_calculator=True)
        
        opt = FIRE(neb, trajectory='neb_rough.traj')
        opt.run(fmax=fmax)
        
        return images

    def run(self):
        """
        Execute the full D2S workflow.
        """
        # 0. Load Inputs
        init_file = self.config.get('init_file')
        final_file = self.config.get('final_file')
        
        if not init_file or not final_file:
            raise ValueError("D2S workflow requires 'init_file' and 'final_file'")
            
        init_atoms = read(init_file)
        final_atoms = read(final_file)
        
        # 1. Optimize
        init_atoms, final_atoms = self.optimize_endpoints(init_atoms, final_atoms)
        
        # 2. Rough NEB
        neb_chain = self.run_rough_neb(init_atoms, final_atoms)
        
        # 3. Analyze NEB for TS guess
        print("=== Step 3: Analyzing Rough NEB ===")
        energies = [img.get_potential_energy() for img in neb_chain]
        max_idx = np.argmax(energies)
        ts_guess = neb_chain[max_idx].copy()
        print(f"  Highest energy image index: {max_idx}")
        
        # 4. Single-Ended Search
        print(f"=== Step 4: Running Single-Ended Search ({self.method.upper()}) ===")
        
        if self.method == 'dimer':
            # Calculate displacement vector
            idx_before = max(0, max_idx - 1)
            idx_after = min(len(neb_chain)-1, max_idx + 1)
            
            vec = neb_chain[idx_before].positions - neb_chain[idx_after].positions
            norm = np.linalg.norm(vec)
            if norm < 1e-3:
                print("Warning: Neighbor images are too close, using random displacement.")
                disp_vec = None
            else:
                disp_vec = vec / norm * 0.01 # Normalize to 0.01 Angstrom
            
            fmax = self.single_config.get('fmax', 0.05)
            
            # Construct a config for AbacusDimer
            # It expects 'calculator' section or similar
            # We need to adapt dft_params
            dimer_config = {
                'calculator': {
                    'name': 'abacus',
                    'abacus': self.dft_params
                },
                'command': self.abacus_cmd
            }
            
            dimer = AbacusDimer(ts_guess, 
                                dimer_config, # Passing constructed config
                                'abacus',
                                self.single_config,
                                traj_file='dimer.traj',
                                init_eigenmode_method='displacement',
                                displacement_vector=disp_vec)
            dimer.run(fmax=fmax)
            
        elif self.method == 'sella':
            fmax = self.single_config.get('fmax', 0.05)
            eta = self.single_config.get('eta', 0.005)
            
            sella_config = {
                'calculator': {
                    'name': 'abacus',
                    'abacus': self.dft_params
                },
                'command': self.abacus_cmd
            }
            
            sella = AbacusSella(ts_guess,
                                sella_config,
                                'abacus',
                                self.single_config,
                                traj_file='sella.traj',
                                sella_eta=eta,
                                fmax=fmax)
            sella.run()
            
        print("=== D2S Workflow Finished ===")
