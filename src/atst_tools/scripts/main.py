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
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow

def main():
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
