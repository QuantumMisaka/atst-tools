"""ATST-Tools CLI entry point."""

import argparse
import logging
import numpy as np
from ase.io import read
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton
import os
from importlib.metadata import PackageNotFoundError, version
from textwrap import dedent

from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.config import VALID_CALCULATION_TYPES
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AutoNEBRunner
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow
from atst_tools.workflows.d2s import D2SWorkflow
from atst_tools.workflows.irc import IRCWorkflow
from atst_tools.utils.io import read_structure
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band

LOGGER = logging.getLogger(__name__)


def _package_version():
    try:
        return version("atst-tools")
    except PackageNotFoundError:
        return "unknown"


def _template(calculation_type, calculator_name):
    if calculator_name == "dp":
        calculator = """\
calculator:
  name: dp
  dp:
    model: /path/to/model.pb
"""
    else:
        calculator = """\
calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_atst
    kpts: [1, 1, 1]
    parameters:
      calculation: scf
      basis_type: lcao
      ks_solver: cusolver
      ecutwfc: 100
      scf_thr: 1e-6
      cal_force: 1
      pseudo_dir: ./data
      orbital_dir: ./data
      pseudopotentials:
        H: H_ONCV_PBE-1.0.upf
      basissets:
        H: H_gga_6au_100Ry_2s1p.orb
"""

    calculation_blocks = {
        "neb": """\
calculation:
  type: neb
  init_chain: inputs/init_neb_chain.traj
  fmax: 0.05
  max_steps: 100
  climb: true
  parallel: true
""",
        "autoneb": """\
calculation:
  type: autoneb
  init_chain: inputs/init_neb_chain.traj
  prefix: run_autoneb
  n_simul: 4
  n_max: 10
  fmax: [0.20, 0.05]
  maxsteps: 100
  parallel: true
""",
        "dimer": """\
calculation:
  type: dimer
  init_structure: inputs/dimer_init.traj
  fmax: 0.05
  max_steps: 100
  trajectory: dimer.traj
  init_eigenmode_method: displacement
  displacement_vector: inputs/displacement_vector.npy
""",
        "sella": """\
calculation:
  type: sella
  init_structure: inputs/sella_init.stru
  fmax: 0.05
  max_steps: 100
  trajectory: sella.traj
  eta: 0.002
""",
        "d2s": """\
calculation:
  type: d2s
  method: dimer
  init_file: inputs/init.stru
  final_file: inputs/final.stru
  endpoint_max_steps: 100
  neb:
    n_images: 8
    fmax: 0.20
    max_steps: 100
  dimer:
    fmax: 0.05
    max_steps: 100
""",
        "relax": """\
calculation:
  type: relax
  init_structure: inputs/init.stru
  fmax: 0.05
  max_steps: 100
  optimizer: FIRE
  trajectory: relax.traj
""",
        "vibration": """\
calculation:
  type: vibration
  init_structure: inputs/ts_opt.stru
  indices: [0, 1]
  delta: 0.01
  nfree: 2
  name: vib_calc
  temperature: 300.0
  thermochemistry:
    model: harmonic
    temperature: 300.0
    ignore_imag_modes: true
""",
        "irc": """\
calculation:
  type: irc
  init_structure: inputs/ts_opt.stru
  trajectory: irc_log.traj
  normalized_trajectory: norm_irc_log.traj
  direction: both
  fmax: 0.05
  max_steps: 1000
  dx: 0.1
  eta: 0.002
""",
    }
    return calculation_blocks[calculation_type] + "\n" + calculator


def get_optimizer(opt_name):
    """
    Helper to get optimizer class from ASE.

    Args:
        opt_name (str): Name of the optimizer (e.g., 'FIRE', 'BFGS').

    Returns:
        class: The ASE optimizer class. Default is FIRE.
    """
    name = opt_name.upper()
    if name == 'FIRE':
        return FIRE
    elif name == 'BFGS':
        return BFGS
    elif name == 'LBFGS':
        return LBFGS
    elif name == 'QUASINEWTON':
        return QuasiNewton
    else:
        LOGGER.warning("Unknown optimizer %s, defaulting to FIRE", opt_name)
        return FIRE

def run_neb(config, calc_name, calc_config):
    """
    Execute NEB calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator (e.g., 'abacus', 'dp').
        calc_config (dict): Calculation-specific configuration.
    """
    LOGGER.info("Starting NEB calculation")
    
    # Load Initial Chain
    init_chain_file = calc_config.get('init_chain', 'init_neb_chain.traj')
    traj_file = calc_config.get('trajectory', 'neb.traj')
    restart = calc_config.get('restart', False)
    if restart:
        n_images = len(read(init_chain_file, index=':'))
        init_chain = get_last_neb_band(traj_file, n_images)
    else:
        init_chain = read(init_chain_file, index=':')
    
    # NEB Parameters
    climb = calc_config.get('climb', True)
    fmax = calc_config.get('fmax', 0.05)
    k = calc_config.get('k', 0.1)
    algorism = calc_config.get('algorism', 'improvedtangent')
    parallel = calc_config.get('parallel', True)
    max_steps = calc_config.get('max_steps', 100)
    opt_name = calc_config.get('optimizer', 'FIRE')
    from ase.parallel import world
    effective_parallel = parallel and world.size > 1
    if parallel and not effective_parallel:
        LOGGER.warning(
            "Image-level NEB parallelism requires MPI-launched atst run; running images serially."
        )
    
    # Initialize NEB
    neb = AbacusNEB(init_chain, 
                    parallel=effective_parallel,
                    method=algorism, 
                    k=k,
                    climb=climb)
    
    # Attach Calculators
    for i, image in enumerate(init_chain[1:-1]):
        if effective_parallel:
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
                    directory=f"{base_dir}/image_{i + 1:03d}"
                )

    # Run
    optimizer = get_optimizer(opt_name)
    opt = optimizer(neb, trajectory=traj_file)
    opt.run(fmax=fmax, steps=max_steps)
    LOGGER.info("NEB calculation finished")

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
    LOGGER.info("Starting Dimer calculation")
    
    # 1. Load Initial Structure
    # Dimer needs a single structure (Transition State guess)
    init_structure = calc_config.get('init_structure', 'dimer_init.stru')
    traj_file = calc_config.get('trajectory', 'dimer.traj')
    if calc_config.get('restart'):
        atoms = get_last_frame(traj_file)
    else:
        if not os.path.exists(init_structure):
         # Try traj
            if os.path.exists('dimer_init.traj'):
                init_structure = 'dimer_init.traj'
        atoms = read_structure(init_structure)
    
    # 2. Parameters
    fmax = calc_config.get('fmax', 0.05)
    
    # Displacement
    # User can provide displacement vector or method
    method = calc_config.get('init_eigenmode_method', 'displacement')
    displacement_vector = calc_config.get('displacement_vector', None)
    
    if method == 'displacement' and isinstance(displacement_vector, str):
        displacement_vector = np.load(displacement_vector)
    elif method == 'displacement' and displacement_vector is None:
        # Try loading from file
        if os.path.exists('displacement_vector.npy'):
            displacement_vector = np.load('displacement_vector.npy')
        else:
            LOGGER.warning(
                "No displacement vector found for Dimer. The dimer runner will validate this input."
            )
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
    
    dimer.run(fmax=fmax, max_steps=calc_config.get('max_steps'))
    LOGGER.info("Dimer calculation finished")

def run_sella(config, calc_name, calc_config):
    """
    Execute Sella calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    LOGGER.info("Starting Sella calculation")
    
    # 1. Load Initial Structure (TS guess)
    init_structure = calc_config.get('init_structure', 'sella_init.stru')
    traj_file = calc_config.get('trajectory', 'sella.traj')
    if calc_config.get('restart'):
        atoms = get_last_frame(traj_file)
    else:
        if not os.path.exists(init_structure):
         # Try traj
            if os.path.exists('sella_init.traj'):
                init_structure = 'sella_init.traj'
        atoms = read_structure(init_structure)
    
    # 2. Parameters
    fmax = calc_config.get('fmax', 0.05)
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
    LOGGER.info("Sella calculation finished")


def _build_parser():
    description = "ATST-Tools: ASE workflows for ABACUS-first transition-state calculations"
    epilog = dedent(
        """
        Configuration shape:
          calculation.type: neb | autoneb | dimer | sella | d2s | relax | vibration | irc
          calculator.name:  abacus | dp

        Common commands:
          atst run examples/06_relax_H2-Au/config.yaml
          atst run --dry-run examples/01_neb_Li-Si/config.yaml
          atst run --list-types
          atst run --show-template neb --calculator abacus

        Full YAML examples are in examples/. The detailed reference is docs/user/CONFIG_REFERENCE.md.
        """
    )
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('config', nargs='?', help='Path to configuration file (YAML)')
    parser.add_argument('--dry-run', action='store_true', help='Load and validate YAML, then exit without running a calculation')
    parser.add_argument('--restart', action='store_true', help='Resume from workflow checkpoints when supported')
    parser.add_argument('--list-types', action='store_true', help='Print supported calculation types and exit')
    parser.add_argument('--show-template', choices=VALID_CALCULATION_TYPES, help='Print a minimal YAML template for a calculation type')
    parser.add_argument('--calculator', choices=('abacus', 'dp'), default='abacus', help='Calculator used with --show-template')
    parser.add_argument('--log-level', default='INFO', choices=('DEBUG', 'INFO', 'WARNING', 'ERROR'), help='Console log level')
    parser.add_argument('--version', action='version', version=f'%(prog)s {_package_version()}')
    return parser

def run_from_args(args):
    logging.basicConfig(
        level=getattr(logging, getattr(args, "log_level", "INFO")),
        format="%(message)s",
    )

    if getattr(args, "list_types", False):
        print("\n".join(VALID_CALCULATION_TYPES))
        return

    show_template = getattr(args, "show_template", None)
    if show_template:
        print(_template(show_template, getattr(args, "calculator", "abacus")))
        return

    # 1. Load Configuration
    config = ConfigLoader.load(args.config)
    if getattr(args, "restart", False):
        config.setdefault("calculation", {})["restart"] = True
    ConfigLoader.validate(config)
    if getattr(args, "dry_run", False):
        calc_type = config["calculation"]["type"]
        calc_name = config.get("calculator", {}).get("name", "abacus")
        LOGGER.info("Configuration is valid: calculation.type=%s, calculator.name=%s", calc_type, calc_name)
        return
    
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
        workflow = D2SWorkflow(config, calc_name, calc_config)
        workflow.run()
    elif calc_type == 'relax':
        workflow = RelaxWorkflow(config, calc_name, calc_config)
        workflow.run()
    elif calc_type == 'vibration':
        workflow = VibrationWorkflow(config, calc_name, calc_config)
        workflow.run()
    elif calc_type == 'irc':
        workflow = IRCWorkflow(config, calc_name, calc_config)
        workflow.run()
    else:
        raise ValueError(f"Unknown calculation type: {calc_type}")

def main(argv=None):
    """
    Main entry point for ATST-Tools run subcommand.
    Parses arguments, loads config, and dispatches to specific workflows.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if (
        not getattr(args, "config", None)
        and not getattr(args, "list_types", False)
        and not getattr(args, "show_template", None)
    ):
        parser.error("the following arguments are required: config")
    return run_from_args(args)

if __name__ == "__main__":
    main()
