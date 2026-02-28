# ATST-Tools Main Entry Point

import argparse
import numpy as np
from ase.io import read
from ase.optimize import FIRE, BFGS
import os

from atst_tools.utils.config import ConfigLoader
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AutoNEBRunner
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow

def get_optimizer(opt_name):
    """
    Helper to get optimizer class from ASE.

    Args:
        opt_name (str): Name of the optimizer (e.g., 'FIRE', 'BFGS').

    Returns:
        class: The ASE optimizer class. Default is FIRE.
    """
    if opt_name.upper() == 'FIRE':
        return FIRE
    elif opt_name.upper() == 'BFGS':
        return BFGS
    else:
        print(f"Warning: Unknown optimizer {opt_name}, defaulting to FIRE")
        return FIRE

def run_neb(config, calc_name, calc_config):
    """
    Execute NEB calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator (e.g., 'abacus', 'dp').
        calc_config (dict): Calculation-specific configuration.
    """
    print("=== Starting NEB Calculation ===")
    
    # Load Initial Chain
    init_chain_file = calc_config.get('init_chain', 'init_neb_chain.traj')
    init_chain = read(init_chain_file, index=':')
    
    # NEB Parameters
    climb = calc_config.get('climb', True)
    fmax = calc_config.get('fmax', 0.05)
    k = calc_config.get('k', 0.1)
    algorism = calc_config.get('algorism', 'improvedtangent')
    parallel = calc_config.get('parallel', True)
    opt_name = calc_config.get('optimizer', 'FIRE')
    
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
                # Determine directory logic
                base_dir = config.get('calculator', {}).get('abacus', {}).get('directory', 'run_atst')
                if 'abacus' in config:
                     base_dir = config['abacus'].get('directory', 'run_atst')
                
                image_dir = f"{base_dir}-rank{world.rank}"
                
                image.calc = CalculatorFactory.get_calculator(
                    calc_name, 
                    config, 
                    directory=image_dir
                )
        else:
             base_dir = config.get('calculator', {}).get('abacus', {}).get('directory', 'run_atst')
             if 'abacus' in config:
                 base_dir = config['abacus'].get('directory', 'run_atst')
                 
             image.calc = CalculatorFactory.get_calculator(
                    calc_name, 
                    config, 
                    directory=base_dir
                )

    # Run
    optimizer = get_optimizer(opt_name)
    opt = optimizer(neb, trajectory='neb.traj')
    opt.run(fmax=fmax)
    print("=== NEB Calculation Finished ===")

def run_autoneb(config, calc_name, calc_config):
    """
    Execute AutoNEB calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    runner = AutoNEBRunner(config, calc_name, calc_config)
    runner.run()

def run_dimer(config, calc_name, calc_config):
    """
    Execute Dimer calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    print("=== Starting Dimer Calculation ===")
    
    # 1. Load Initial Structure
    # Dimer needs a single structure (Transition State guess)
    init_structure = calc_config.get('init_structure', 'dimer_init.stru')
    if not os.path.exists(init_structure):
         # Try traj
         if os.path.exists('dimer_init.traj'):
             init_structure = 'dimer_init.traj'
    
    atoms = read(init_structure)
    
    # 2. Parameters
    fmax = calc_config.get('fmax', 0.05)
    traj_file = calc_config.get('trajectory', 'dimer.traj')
    
    # Displacement
    # User can provide displacement vector or method
    method = calc_config.get('init_eigenmode_method', 'displacement')
    displacement_vector = calc_config.get('displacement_vector', None)
    
    if method == 'displacement' and displacement_vector is None:
        # Try loading from file
        if os.path.exists('displacement_vector.npy'):
            displacement_vector = np.load('displacement_vector.npy')
        else:
            print("Warning: No displacement vector found for Dimer. Using default [0.01, ...]")
            # AbacusDimer might handle None? It raises ValueError.
            # We should probably ask user or default to something?
            # Let's let AbacusDimer handle the error if not provided.
    
    # 3. Run
    dimer = AbacusDimer(
        init_Atoms=atoms,
        config=config,
        calc_name=calc_name,
        calc_config=calc_config,
        traj_file=traj_file,
        init_eigenmode_method=method,
        displacement_vector=displacement_vector
    )
    
    dimer.run(fmax=fmax)
    print("=== Dimer Calculation Finished ===")

def run_sella(config, calc_name, calc_config):
    """
    Execute Sella calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    print("=== Starting Sella Calculation ===")
    
    # 1. Load Initial Structure (TS guess)
    init_structure = calc_config.get('init_structure', 'sella_init.stru')
    if not os.path.exists(init_structure):
         # Try traj
         if os.path.exists('sella_init.traj'):
             init_structure = 'sella_init.traj'
    
    atoms = read(init_structure)
    
    # 2. Parameters
    fmax = calc_config.get('fmax', 0.05)
    traj_file = calc_config.get('trajectory', 'sella.traj')
    eta = calc_config.get('eta', 0.005) # Sella eta parameter
    
    # 3. Run
    sella_run = AbacusSella(
        init_Atoms=atoms,
        config=config,
        calc_name=calc_name,
        calc_config=calc_config,
        traj_file=traj_file,
        sella_eta=eta,
        fmax=fmax
    )
    
    sella_run.run()
    print("=== Sella Calculation Finished ===")

def main():
    """
    Main entry point for ATST-Tools CLI.
    Parses arguments, loads config, and dispatches to specific workflows.
    """
    parser = argparse.ArgumentParser(description="ATST-Tools: Advanced Transition State Tools")
    parser.add_argument('config', type=str, help='Path to configuration file (YAML)')
    args = parser.parse_args()

    # 1. Load Configuration
    config = ConfigLoader.load(args.config)
    ConfigLoader.validate(config)
    
    # New Config Structure Support
    if 'calculation' in config:
        calc_config = config['calculation']
    else:
        if 'abacus' in config:
             calc_config = config 
             pass
        else:
             raise ValueError("Invalid config: missing 'calculation' section")

    calc_type = calc_config['type']
    
    # 2. Prepare Calculator Name
    if 'calculator' in config:
        calc_name = config['calculator'].get('name', 'abacus')
    elif 'abacus' in config:
        calc_name = 'abacus'
    else:
        calc_name = 'abacus' # Default

    # 3. Dispatch Calculation
    if calc_type == 'neb':
        run_neb(config, calc_name, calc_config)
    elif calc_type == 'autoneb':
        run_autoneb(config, calc_name, calc_config)
    elif calc_type == 'dimer':
        run_dimer(config, calc_name, calc_config)
    elif calc_type == 'sella':
        run_sella(config, calc_name, calc_config)
    elif calc_type == 'd2s':
        # D2S might need specific handling as it manages its own calculators often?
        pass
        print("D2S workflow update pending in this refactor step.")
    elif calc_type == 'relax':
        workflow = RelaxWorkflow(config, calc_name, calc_config)
        workflow.run()
    elif calc_type == 'vibration':
        workflow = VibrationWorkflow(config, calc_name, calc_config)
        workflow.run()
    else:
        raise ValueError(f"Unknown calculation type: {calc_type}")

if __name__ == "__main__":
    main()
