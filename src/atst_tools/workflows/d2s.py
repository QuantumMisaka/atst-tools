# D2S (Double-to-Single) Workflow
# part of ATST-Tools

import os
import numpy as np
from copy import deepcopy
from ase.io import read, write, Trajectory
from ase.mep.neb import NEBTools, DyNEB
from ase.optimize import FIRE, QuasiNewton

from atst_tools.calculators.abacus import AbacusCalculator
from atst_tools.utils.idpp import generate
from atst_tools.mep.neb import AbacusNEB
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
        """Helper to get calculator with specific directory"""
        return AbacusCalculator.get_calculator(
            self.dft_params, 
            os.path.join(self.directory, sub_dir), 
            self.mpi, self.omp, self.abacus_cmd
        )

    def optimize_endpoints(self, init_atoms, final_atoms):
        """Optimize Initial and Final States"""
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
        """Run Rough NEB to find approximate TS"""
        print("=== Step 2: Running Rough NEB ===")
        
        n_images = self.neb_config.get('n_images', 8)
        fmax = self.neb_config.get('fmax', 0.8) # Rough convergence
        algorism = self.neb_config.get('algorism', 'improvedtangent')
        climb = self.neb_config.get('climb', True)
        
        # Generate IDPP Path
        # Note: We use our internal generate function or IDPP solver directly
        # For simplicity, we assume linear/idpp generation here.
        # But `generate` writes to file. We might want direct object handling.
        # Let's use IDPP solver directly from utils.
        from atst_tools.utils.idpp import Fast_IDPPSolver
        
        print(f"  Generating {n_images} images via IDPP...")
        # Create list of images
        images = [init_atoms] 
        for i in range(n_images):
            images.append(init_atoms.copy())
        images.append(final_atoms)
        
        solver = Fast_IDPPSolver.from_endpoints(init_atoms, final_atoms, n_images)
        images = solver.run() # This returns the path list [IS, img1...imgN, FS]
        
        # Attach Calculators
        # Note: D2S scripts use DyNEB (Serial) for efficiency usually, 
        # but we can support parallel if user wants.
        # Defaulting to Serial DyNEB as per original script logic for now?
        # The original script used DyNEB with parallel=False.
        
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
            # Vector = (Before - After) / Norm
            # Check boundary conditions
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
            
            dimer = AbacusDimer(ts_guess, 
                                self.dft_params, 
                                abacus=self.abacus_cmd,
                                mpi=self.mpi, omp=self.omp, 
                                directory=os.path.join(self.directory, "DIMER"),
                                init_eigenmode_method='displacement',
                                displacement_vector=disp_vec)
            dimer.run(fmax=fmax)
            
        elif self.method == 'sella':
            fmax = self.single_config.get('fmax', 0.05)
            eta = self.single_config.get('eta', 0.005)
            
            sella = AbacusSella(ts_guess,
                                self.dft_params,
                                abacus=self.abacus_cmd,
                                mpi=self.mpi, omp=self.omp,
                                directory=os.path.join(self.directory, "SELLA"),
                                sella_eta=eta,
                                fmax=fmax)
            sella.run()
            
        print("=== D2S Workflow Finished ===")
