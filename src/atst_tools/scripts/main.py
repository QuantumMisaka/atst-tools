# ATST-Tools Main Entry Point

import argparse
import sys
import numpy as np
from pathlib import Path
from ase.io import read, write
from ase.optimize import FIRE, BFGS

from atst_tools.utils.config import ConfigLoader
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AbacusAutoNEB
# from atst_tools.mep.dimer import AbacusDimer
# from atst_tools.mep.sella import AbacusSella
from atst_tools.workflows.d2s import D2SWorkflow

def main():
    parser = argparse.ArgumentParser(description="ATST-Tools: Advanced Transition State Tools")
    parser.add_argument('config', type=str, help='Path to configuration file (YAML)')
    args = parser.parse_args()

    # 1. Load Configuration
    config = ConfigLoader.load(args.config)
    ConfigLoader.validate(config)
    
    # New Config Structure Support
    # We expect 'calculation' and 'calculator' sections
    # But for backward compatibility we check if they exist, else we try to parse old structure
    
    if 'calculation' in config:
        calc_config = config['calculation']
    else:
        # Fallback or Error? Let's assume the root is config for now or handle old 'abacus' key
        # If 'abacus' key exists at root, it's likely old config
        if 'abacus' in config:
             calc_config = config # Treat whole config as calculation config in old way? 
             # Actually old way was: config['calculation'] exists, and config['abacus'] exists.
             pass
        else:
             raise ValueError("Invalid config: missing 'calculation' section")

    calc_type = calc_config['type']
    
    # 2. Prepare Calculator
    # We pass the WHOLE config to the factory, it will extract what it needs
    # Determine calculator name
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
        # Or we update D2SWorkflow to use Factory.
        # For now, let's keep D2S as is or update it if possible.
        # D2SWorkflow in current codebase likely hardcodes Abacus. 
        # We should probably pass the factory or config to it.
        # Let's check D2SWorkflow signature.
        # It was: D2SWorkflow(calc_config, dft_params, mpi, omp, abacus_cmd, directory)
        # We will need to refactor D2SWorkflow later. For now, let's try to adapt arguments.
        
        # Extract old-style args for D2S compatibility if needed, or better, refactor D2S.
        # Since this is Sprint 1.3, let's focus on NEB first as per plan.
        pass
        print("D2S workflow update pending in this refactor step.")

def get_optimizer(opt_name):
    """Helper to get optimizer class"""
    if opt_name.upper() == 'FIRE':
        return FIRE
    elif opt_name.upper() == 'BFGS':
        return BFGS
    else:
        print(f"Warning: Unknown optimizer {opt_name}, defaulting to FIRE")
        return FIRE

def run_neb(config, calc_name, calc_config):
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
    # Note: AbacusNEB might be just a wrapper around ASE NEB.
    # We should check if we can just use ASE NEB directly now?
    # AbacusNEB was likely created to add specific Abacus features or just convenience.
    # Let's assume we use AbacusNEB for now but injecting our calculators.
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
                # Create calculator via Factory
                # We can inject rank info into directory if needed
                # The Factory (AbacusFactory) handles mpi/omp internally via config.
                # But for directory, we might want to override.
                
                # We need to construct a config for this specific image?
                # Or just pass the main config and let factory handle it?
                # Factory.get_calculator(name, config, directory=...)
                
                # We need to determine the directory for this image.
                # Old logic: f"{directory}-rank{world.rank}"
                # We should extract 'directory' from config or use default.
                base_dir = config.get('calculator', {}).get('abacus', {}).get('directory', 'run_atst')
                # Or if using old config structure:
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
    # Similar refactoring for AutoNEB...
    # For brevity in this step, I will mark it as TODO or implement basic support
    print("AutoNEB refactoring with Factory is WIP.")
    pass

def run_dimer(config, calc_name, calc_config):
    print("Dimer refactoring with Factory is WIP.")
    pass

def run_sella(config, calc_name, calc_config):
    print("Sella refactoring with Factory is WIP.")
    pass

if __name__ == "__main__":
    main()
