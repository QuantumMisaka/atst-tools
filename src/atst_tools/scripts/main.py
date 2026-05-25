"""ATST-Tools CLI entry point."""

import argparse
import logging
import numpy as np
from ase.io import read
from ase.mep.neb import NEB
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton
import os
from textwrap import dedent

from atst_tools import package_version
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.config import VALID_CALCULATION_TYPES
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AutoNEBRunner
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow
from atst_tools.workflows.d2s import D2SWorkflow
from atst_tools.workflows.irc import IRCBoundaryError, IRCWorkflow
from atst_tools.utils.io import read_structure
from atst_tools.utils.neb_endpoints import endpoint_policy, ensure_neb_endpoint_results
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band
from atst_tools.utils.idpp import generate

LOGGER = logging.getLogger(__name__)


def _package_version():
    return package_version()


def _template(calculation_type, calculator_name):
    if calculator_name == "dp":
        calculator = """\
calculator:
  name: dp
  dp:
    model: /path/to/model.pb-or-pt
    # Required for multi-head DPA/DPA3 models.
    head: null
    omp: 4
    share_calculator: true
"""
    else:
        calculator = """\
calculator:
  name: abacus
  abacus:
    command: abacus
    # Optional full command for version probing; defaults to bare abacus --version.
    # version_command: abacus --version
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
  # Alternative:
  # make:
  #   init_structure: inputs/init.stru
  #   final_structure: inputs/final.stru
  #   n_images: 5
  #   method: IDPP
  #   output: inputs/init_neb_chain.traj
  fmax: 0.05
  max_steps: 100
  climb: true
  parallel: true
  endpoint_singlepoint: auto
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
  optimizer_kwargs: {}
  parallel: true
  endpoint_singlepoint: auto
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
  endpoint_optimization:
    enabled: true
    skip_if_has_results: true
    fmax: 0.05
    max_steps: 100
  endpoint_singlepoint: auto
  neb:
    n_images: 8
    fmax: 0.20
    max_steps: 100
  dimer:
    fmax: 0.05
    max_steps: 100
  vibration:
    enabled: false
    indices: auto
    threshold: 0.10
    delta: 0.01
    nfree: 2
    name: d2s_vib
    results_file: d2s_vibration_results.json
    thermochemistry:
      model: harmonic
      temperature: 300.0
      ignore_imag_modes: true
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


def _parse_make_fix(value):
    if value is None:
        return None, None
    if isinstance(value, dict):
        return value.get("height"), value.get("dir", value.get("direction"))
    height, direction = str(value).split(":", 1)
    return float(height), int(direction)


def _parse_make_mag(value):
    if value is None:
        return None, None
    if isinstance(value, dict):
        return list(value.keys()), [float(v) for v in value.values()]
    elements = []
    moments = []
    for item in str(value).split(","):
        element, moment = item.split(":", 1)
        elements.append(element)
        moments.append(float(moment))
    return elements, moments


def _abacus_base_directory(config, default):
    base_dir = config.get('calculator', {}).get('abacus', {}).get('directory', default)
    if 'abacus' in config:
        base_dir = config['abacus'].get('directory', base_dir)
    return base_dir


def _get_workflow_calculator(calc_name, config, shared=None, **kwargs):
    if is_dp_calculator(calc_name) and shared is not None:
        kwargs["shared"] = shared
    return CalculatorFactory.get_calculator(calc_name, config, **kwargs)


def _normalized_calculation(config, calc_config):
    """Return a schema-normalized calculation section for direct helper calls."""
    if "config_version" in config:
        return calc_config
    return apply_calculation_defaults(calc_config)

def run_neb(config, calc_name, calc_config):
    """
    Execute NEB calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator (e.g., 'abacus', 'dp').
        calc_config (dict): Calculation-specific configuration.
    """
    LOGGER.info("Starting NEB calculation")
    calc_config = _normalized_calculation(config, calc_config)
    
    # Load Initial Chain
    traj_file = calc_config['trajectory']
    restart = calc_config['restart']
    has_init_chain = bool(calc_config.get('init_chain'))
    has_make = bool(calc_config.get('make'))
    if has_init_chain == has_make:
        raise ValueError("NEB calculation requires exactly one of 'init_chain' or 'make'")

    if has_make:
        make_config = calc_config.get('make') or {}
        init_chain_file = make_config['output']
        fix_height, fix_dir = _parse_make_fix(make_config.get('fix'))
        mag_ele, mag_num = _parse_make_mag(make_config.get('magmom'))
        if not restart:
            generate(
                method=make_config['method'],
                n_images=make_config['n_images'],
                is_file=make_config['init_structure'],
                fs_file=make_config['final_structure'],
                output_file=init_chain_file,
                format=make_config.get('format'),
                fix_height=fix_height,
                fix_dir=fix_dir,
                mag_ele=mag_ele,
                mag_num=mag_num,
                no_align=make_config['no_align'],
                ts_file=make_config.get('ts_guess'),
            )
    else:
        init_chain_file = calc_config['init_chain']
    if restart:
        n_images = make_config['n_images'] + 2 if has_make else len(read(init_chain_file, index=':'))
        init_chain = get_last_neb_band(traj_file, n_images)
    else:
        init_chain = read(init_chain_file, index=':')
    
    # NEB Parameters
    climb = calc_config['climb']
    fmax = calc_config['fmax']
    k = calc_config['k']
    algorism = calc_config['algorism']
    parallel = calc_config['parallel']
    max_steps = calc_config['max_steps']
    opt_name = calc_config['optimizer']
    from ase.parallel import world
    effective_parallel = parallel and world.size > 1
    if parallel and not effective_parallel:
        LOGGER.warning(
            "Image-level NEB parallelism requires MPI-launched atst run; running images serially."
        )

    base_dir = _abacus_base_directory(config, 'run_atst')
    policy = endpoint_policy(calc_config, default="auto")
    ensure_neb_endpoint_results(
        init_chain,
        lambda directory: _get_workflow_calculator(
            calc_name,
            config,
            directory=f"{base_dir}/{directory}",
        ),
        policy=policy,
        directories=("endpoint_initial", "endpoint_final"),
        context="NEB",
    )
    allow_shared = should_share_calculator(calc_name, config, parallel=effective_parallel)
    
    # Initialize NEB
    neb_class = NEB if calc_config.get("neb_backend", "atst") == "ase" else AbacusNEB
    neb = neb_class(init_chain, 
                    parallel=effective_parallel,
                    method=algorism, 
                    k=k,
                    climb=climb,
                    allow_shared_calculator=allow_shared)
    
    # Attach Calculators
    shared_calc = None
    if allow_shared:
        shared_calc = _get_workflow_calculator(
            calc_name,
            config,
            shared=True,
            directory=f"{base_dir}/shared",
        )
    for i, image in enumerate(init_chain[1:-1]):
        if effective_parallel:
            if world.rank == i % world.size:
                # Determine directory logic
                image_dir = f"{base_dir}-rank{world.rank}"
                
                image.calc = _get_workflow_calculator(
                    calc_name, 
                    config, 
                    shared=False,
                    directory=image_dir
                )
        elif shared_calc is not None:
             image.calc = shared_calc
        else:
             image.calc = _get_workflow_calculator(
                    calc_name, 
                    config, 
                    directory=f"{base_dir}/image_{i + 1:03d}"
                )

    # Run
    optimizer = get_optimizer(opt_name)
    opt = optimizer(neb, trajectory=traj_file, **calc_config.get("optimizer_kwargs", {}))
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
    calc_config = _normalized_calculation(config, calc_config)
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
    calc_config = _normalized_calculation(config, calc_config)
    
    # 1. Load Initial Structure
    # Dimer needs a single structure (Transition State guess)
    init_structure = calc_config['init_structure']
    traj_file = calc_config['trajectory']
    if calc_config.get('restart'):
        atoms = get_last_frame(traj_file)
    else:
        if not os.path.exists(init_structure):
         # Try traj
            if os.path.exists('dimer_init.traj'):
                init_structure = 'dimer_init.traj'
        atoms = read_structure(init_structure)
    
    # 2. Parameters
    fmax = calc_config['fmax']
    
    # Displacement
    # User can provide displacement vector or method
    method = calc_config['init_eigenmode_method']
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
        displacement_vector=displacement_vector,
        dimer_separation=calc_config['dimer_separation'],
        max_num_rot=calc_config['max_num_rot'],
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
    calc_config = _normalized_calculation(config, calc_config)
    
    # 1. Load Initial Structure (TS guess)
    init_structure = calc_config['init_structure']
    traj_file = calc_config['trajectory']
    if calc_config.get('restart'):
        atoms = get_last_frame(traj_file)
    else:
        if not os.path.exists(init_structure):
         # Try traj
            if os.path.exists('sella_init.traj'):
                init_structure = 'sella_init.traj'
        atoms = read_structure(init_structure)
    
    # 2. Parameters
    fmax = calc_config['fmax']
    eta = calc_config['eta']
    
    # 3. Run
    sella_run = AbacusSella(
        init_Atoms=atoms,
        config=config,
        calc_name=calc_name,
        calc_config=calc_config,
        traj_file=traj_file,
        sella_eta=eta,
        fmax=fmax,
        order=calc_config['order'],
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
    config = ConfigLoader.normalize(config)
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
        try:
            workflow.run()
        except IRCBoundaryError as exc:
            raise SystemExit(str(exc)) from None
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
