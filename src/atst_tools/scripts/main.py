# ATST-Tools Main Entry Point

import argparse
import sys
import numpy as np
from pathlib import Path
from ase.io import read
from ase.optimize import FIRE, BFGS

from atst_tools.utils.config import ConfigLoader
from atst_tools.calculators.abacus import AbacusCalculator
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AbacusAutoNEB
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.workflows.d2s import D2SWorkflow

def main():
    parser = argparse.ArgumentParser(description="ATST-Tools: Advanced Transition State Tools")
    parser.add_argument('config', type=str, help='Path to configuration file (YAML)')
    args = parser.parse_args()

    # 1. Load Configuration
    config = ConfigLoader.load(args.config)
    ConfigLoader.validate(config)
    
    calc_config = config['calculation']
    abacus_config = config['abacus']
    calc_type = calc_config['type']

    # 2. Prepare Calculator Parameters
    # Merge DFT parameters from config
    dft_params = abacus_config.get('parameters', {})
    
    # Common settings
    mpi = abacus_config.get('mpi', 1)
    omp = abacus_config.get('omp', 1)
    abacus_cmd = abacus_config.get('command', 'abacus')
    directory = abacus_config.get('directory', 'run_atst')

    # 3. Dispatch Calculation
    if calc_type == 'neb':
        run_neb(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
    elif calc_type == 'autoneb':
        run_autoneb(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
    elif calc_type == 'dimer':
        run_dimer(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
    elif calc_type == 'sella':
        run_sella(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
    elif calc_type == 'd2s':
        workflow = D2SWorkflow(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
        workflow.run()

def get_optimizer(opt_name):
    """Helper to get optimizer class"""
    if opt_name.upper() == 'FIRE':
        return FIRE
    elif opt_name.upper() == 'BFGS':
        return BFGS
    else:
        print(f"Warning: Unknown optimizer {opt_name}, defaulting to FIRE")
        return FIRE

def run_neb(config, dft_params, mpi, omp, abacus_cmd, directory):
    print("=== Starting NEB Calculation ===")
    
    # Load Initial Chain
    init_chain_file = config.get('init_chain', 'init_neb_chain.traj')
    init_chain = read(init_chain_file, index=':')
    
    # NEB Parameters
    climb = config.get('climb', True)
    fmax = config.get('fmax', 0.05)
    k = config.get('k', 0.1)
    algorism = config.get('algorism', 'improvedtangent')
    parallel = config.get('parallel', True)
    opt_name = config.get('optimizer', 'FIRE')
    
    # Initialize NEB
    neb = AbacusNEB(init_chain, 
                    parallel=parallel,
                    method=algorism, 
                    k=k,
                    climb=climb)
    
    # Attach Calculators
    from ase.parallel import world
    for i, image in enumerate(init_chain[1:-1]):
        if parallel:
            if world.rank == i % world.size:
                image.calc = AbacusCalculator.get_calculator(
                    dft_params, 
                    f"{directory}-rank{world.rank}", 
                    mpi, omp, abacus_cmd
                )
        else:
             image.calc = AbacusCalculator.get_calculator(
                    dft_params, 
                    directory, 
                    mpi, omp, abacus_cmd
                )

    # Run
    optimizer = get_optimizer(opt_name)
    opt = optimizer(neb, trajectory='neb.traj')
    opt.run(fmax=fmax)
    print("=== NEB Calculation Finished ===")

def run_autoneb(config, dft_params, mpi, omp, abacus_cmd, directory):
    print("=== Starting AutoNEB Calculation ===")
    
    init_chain_file = config.get('init_chain', 'init_neb_chain.traj')
    # AutoNEB takes list of Atoms
    init_chain = read(init_chain_file, index=':')
    
    # AutoNEB Parameters
    n_simul = config.get('n_simul', 1)
    n_max = config.get('n_max', 10)
    climb = config.get('climb', True)
    fmax = config.get('fmax', 0.05)
    k = config.get('k', 0.1)
    algorism = config.get('algorism', 'improvedtangent')
    prefix = config.get('prefix', 'run_autoneb')
    
    # Helper to attach calculators (AutoNEB calls this dynamically)
    def attach_calculators(images):
        from ase.parallel import world
        for i, image in enumerate(images):
            # Simple round-robin assignment or rank-based?
            # In AutoNEB, it manages parallelization via n_simul.
            # We just give a calculator.
            # Note: AbacusAutoNEB logic handles directory naming internally based on rank?
            # Actually AbacusAutoNEB.set_calculator does it.
            
            # Re-using AbacusCalculator logic:
            # We need unique directory for each image to avoid collision?
            # Or trust AutoNEB's flow.
            # For now, let's create a fresh calculator for each image.
            
            # Warning: directory management in AutoNEB parallel is tricky.
            # AbacusAutoNEB implementation we wrote uses {directory}-rank{rank}.
            
            if world.size > 1:
                calc_dir = f"{directory}-rank{world.rank}"
            else:
                calc_dir = directory
                
            image.calc = AbacusCalculator.get_calculator(
                dft_params, calc_dir, mpi, omp, abacus_cmd
            )

    autoneb = AbacusAutoNEB(attach_calculators, 
                            prefix=prefix, 
                            n_simul=n_simul, 
                            n_max=n_max,
                            k=k,
                            climb=climb,
                            fmax=fmax,
                            method=algorism,
                            parallel=True) # Force parallel True for now
                            
    # Initialize constraints/magmoms from init_chain if needed
    # (This logic was in AbacusAutoNEB.set_init_and_final_conditions)
    # For now, we assume init_chain has them or we rely on AbacusAutoNEB's logic if we integrated it.
    # In our refactored AbacusAutoNEB, we inherited from ASE AutoNEB.
    # We might need to manually set up the all_images list from init_chain first?
    # ASE AutoNEB expects existing .traj files on disk.
    
    # Pre-flight: Write init chain to disk as AutoNEB expects
    # prefix000.traj, prefix{N}.traj
    n_init = len(init_chain)
    for i, atoms in enumerate(init_chain):
        # We need to map 0 -> 000, -1 -> N
        # But AutoNEB expects sequential files.
        # If we have [A, B, C], we write 000, 001, 002?
        # Yes.
        idx = f"{i:03d}"
        write(f"{prefix}{idx}.traj", atoms)
        
    autoneb.run()
    print("=== AutoNEB Calculation Finished ===")

def run_dimer(config, dft_params, mpi, omp, abacus_cmd, directory):
    print("=== Starting Dimer Calculation ===")
    
    init_file = config.get('init_file', 'dimer_init.traj')
    init_atoms = read(init_file)
    
    # Dimer Parameters
    fmax = config.get('fmax', 0.05)
    dimer_sep = config.get('dimer_separation', 0.01)
    max_rot = config.get('max_num_rot', 3)
    init_method = config.get('init_eigenmode_method', 'displacement')
    
    disp_vec = None
    if init_method == 'displacement':
        disp_file = config.get('displacement_file', 'displacement_vector.npy')
        if Path(disp_file).exists():
            disp_vec = np.load(disp_file)
        else:
            raise FileNotFoundError(f"Displacement file {disp_file} not found")
            
    dimer = AbacusDimer(init_atoms, 
                        dft_params, 
                        abacus=abacus_cmd,
                        mpi=mpi, omp=omp, 
                        directory=directory,
                        init_eigenmode_method=init_method,
                        displacement_vector=disp_vec,
                        dimer_separation=dimer_sep,
                        max_num_rot=max_rot)
                        
    dimer.run(fmax=fmax)
    print("=== Dimer Calculation Finished ===")

def run_sella(config, dft_params, mpi, omp, abacus_cmd, directory):
    print("=== Starting Sella Calculation ===")
    
    init_file = config.get('init_file', 'sella_init.stru')
    # Use abacus format for sella input often, or traj
    try:
        init_atoms = read(init_file, format='abacus')
    except:
        init_atoms = read(init_file)
        
    fmax = config.get('fmax', 0.05)
    eta = config.get('eta', 0.005)
    
    sella = AbacusSella(init_atoms,
                        dft_params,
                        abacus=abacus_cmd,
                        mpi=mpi, omp=omp,
                        directory=directory,
                        sella_eta=eta,
                        fmax=fmax)
                        
    sella.run()
    print("=== Sella Calculation Finished ===")

if __name__ == "__main__":
    main()
