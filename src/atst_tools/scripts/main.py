"""ATST-Tools CLI entry point."""

import argparse
import logging
from atst_tools.utils.mpi import bootstrap_mpi_for_ase

bootstrap_mpi_for_ase()

import numpy as np
from ase.io import read, write
from ase.mep.neb import NEB
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton
import os
from textwrap import dedent

from atst_tools import package_version
from atst_tools.api import RunOptions, validate_config
from atst_tools.api.services import run_workflow_from_cli
from atst_tools.api.models import (
    ConfigValidationError,
    MPIConfigurationError,
    UnsupportedDependencyError,
    WorkflowExecutionError,
)
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.config import VALID_CALCULATION_TYPES
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.abacus_io import run_abacus_check_input_dry_run
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AutoNEBRunner
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.mep.ccqn import AbacusCCQN
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow
from atst_tools.workflows.d2s import D2SWorkflow
from atst_tools.workflows.irc import IRCBoundaryError, IRCWorkflow
from atst_tools.workflows.md import MDWorkflow
from atst_tools.workflows.dmf import DMFWorkflow
from atst_tools.utils.io import read_structure
from atst_tools.utils.neb_endpoints import (
    ENDPOINT_OPTIMIZED,
    endpoint_policy,
    ensure_neb_endpoint_results,
    freeze_current_results,
    has_endpoint_results,
)
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band
from atst_tools.utils.idpp import generate
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.mpi import (
    get_ase_world,
    rank_owns_local_image,
    validate_image_parallel_world,
)

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
  two_stage: true
  stage1_steps: 20
  stage1_fmax: 0.2
  parallel: true
  endpoint_singlepoint: auto
  endpoint_optimization:
    enabled: false
    skip_if_has_results: true
    fmax: 0.05
    max_steps: 100
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
        "ccqn": """\
calculation:
  type: ccqn
  init_structure: inputs/ccqn_init.stru
  fmax: 0.05
  max_steps: 200
  trajectory: ccqn.traj
  logfile: ccqn.log
  final_structure: ccqn_final.extxyz
  e_vector_method: ic
  reactive_bonds: "1-2"
  auto_reactive_bonds:
    enabled: false
    molecule_indices: null
    cutoff_A: 3.0
    max_modes: 20
  mode_manifest: ccqn_mode_manifest.json
  diagnostics_file: ccqn_diagnostics.json
  ic_mode: democratic
  cos_phi: 0.5
  trust_radius_uphill: 0.1
  trust_radius_saddle_initial: 0.05
  accept_initial_converged: false
""",
        "d2s": """\
calculation:
  type: d2s
  method: dimer
  # Keep neb for supported production runs; dmf is an experimental rough-stage option.
  rough_method: neb
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
  dmf:
    initial_path: linear
    pbc_mode: reject
    confirm_pbc_risk: false
    remove_rotation_and_translation: true
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
    validation_file: d2s_ts_validation.json
    thermochemistry:
      model: harmonic
      temperature: 300.0
      ignore_imag_modes: true
      energy_threshold: 1.0e-6
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
  results_file: vibration_results.json
  validation_file: ts_validation.json
  thermochemistry:
    model: harmonic
    temperature: 300.0
    ignore_imag_modes: true
    energy_threshold: 1.0e-6
""",
        "irc": """\
calculation:
  type: irc
  init_structure: inputs/ts_opt.stru
  backend: sella
  trajectory: irc_log.traj
  normalized_trajectory: norm_irc_log.traj
  direction: both
  # For backend: descent, provide a NumPy mode vector.
  mode_vector: null
  descent_delta: 0.1
  fmax: 0.05
  max_steps: 1000
  dx: 0.1
  eta: 0.002
""",
        "md": """\
calculation:
  type: md
  driver: ase
  init_structure: inputs/init.stru
  ensemble: nvt
  algorithm: bussi
  steps: 100
  timestep_fs: 1.0
  temperature_K: 300.0
  taut_fs: 10.0
  trajectory: md.traj
  logfile: md.log
  loginterval: 1
  summary_file: md_summary.json
  final_structure: md_final.traj
  postprocess:
    summary:
      enabled: true
      output: md_post_summary.json
    convert:
      enabled: false
      format: extxyz
      output_prefix: md_post
  # For ABACUS native MD use:
  # driver: abacus_native
  # calculator.name must be abacus, and ABACUS MD INPUT variables are passed
  # through calculator.abacus.parameters with calculation: md.
""",
        "dmf": """\
calculation:
  type: dmf
  # Experimental Direct MaxFlux TS candidate workflow.
  # PBC is rejected by default. The cartesian_unwrapped mode is experimental,
  # assumes fixed-cell pre-unwrapped Cartesian endpoints, and does not provide
  # MIC or fractional-coordinate support.
  init_file: inputs/init.xyz
  final_file: inputs/final.xyz
  directory: dmf_run
  trajectory: dmf_path.traj
  tmax_trajectory: dmf_tmax.traj
  summary_file: dmf_summary.json
  artifact_manifest: atst_artifacts.json
  initial_path: cfbenm
  nsegs: 4
  dspl: 3
  nmove: 10
  beta: null
  update_teval: true
  tol: middle
  ipopt_options:
    max_iter: 50
    print_level: 0
  parallel: false
  remove_rotation_and_translation: true
  pbc_mode: reject
  confirm_pbc_risk: false
  # To opt in to the experimental PBC path:
  # initial_path: linear
  # pbc_mode: cartesian_unwrapped
  # confirm_pbc_risk: true
  # remove_rotation_and_translation: false
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
    return apply_calculation_defaults(calc_config)


def _relax_neb_endpoints(init_chain, config, calc_name, calc_config, base_dir, optimizer_class):
    endpoint_config = calc_config.get("endpoint_optimization") or {}
    if not endpoint_config.get("enabled"):
        return
    skip_existing = endpoint_config.get("skip_if_has_results", True)
    for label, atoms in (("initial", init_chain[0]), ("final", init_chain[-1])):
        if skip_existing and has_endpoint_results(atoms):
            continue
        atoms.calc = _get_workflow_calculator(
            calc_name,
            config,
            directory=f"{base_dir}/endpoint_{label}_relax",
        )
        opt = optimizer_class(atoms, trajectory=f"endpoint_{label}_relax.traj")
        opt.run(fmax=endpoint_config.get("fmax", 0.05), steps=endpoint_config.get("max_steps", 100))
        freeze_current_results(atoms, status=ENDPOINT_OPTIMIZED)


def _sync_parallel_endpoint_results(images, world, prepare_endpoints):
    """Run endpoint preparation on rank 0 and share frozen results via a temp chain."""
    sync_file = ".atst_neb_endpoint_synced.traj"
    if world.rank == 0:
        prepare_endpoints(images)
        write(sync_file, images)
    if hasattr(world, "barrier"):
        world.barrier()
    synced_images = read(sync_file, index=":", parallel=False)
    if hasattr(world, "barrier"):
        world.barrier()
    if world.rank == 0:
        try:
            os.remove(sync_file)
        except FileNotFoundError:
            pass
    if hasattr(world, "barrier"):
        world.barrier()
    return synced_images


def run_neb(config, calc_name, calc_config, world=None):
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

    parallel = calc_config['parallel']
    world = world if world is not None else get_ase_world()
    effective_parallel = parallel and world.size > 1
    if parallel and not effective_parallel:
        LOGGER.warning(
            "Image-level NEB parallelism requires MPI-launched atst run; running images serially."
        )

    if has_make:
        make_config = calc_config.get('make') or {}
        init_chain_file = make_config['output']
        fix_height, fix_dir = _parse_make_fix(make_config.get('fix'))
        mag_ele, mag_num = _parse_make_mag(make_config.get('magmom'))
        if not restart:
            if not effective_parallel or world.rank == 0:
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
            if effective_parallel and hasattr(world, "barrier"):
                world.barrier()
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
    max_steps = calc_config['max_steps']
    opt_name = calc_config['optimizer']
    two_stage = calc_config.get("two_stage", False)
    if effective_parallel:
        validate_image_parallel_world(world, len(init_chain) - 2, "NEB")
        LOGGER.info(
            "Image-level NEB parallelism active: world.size=%s, interior_images=%s",
            world.size,
            len(init_chain) - 2,
        )

    base_dir = _abacus_base_directory(config, 'run_atst')
    policy = endpoint_policy(calc_config, default="auto")
    optimizer = get_optimizer(opt_name)

    def prepare_endpoints(images):
        _relax_neb_endpoints(images, config, calc_name, calc_config, base_dir, optimizer)
        return ensure_neb_endpoint_results(
            images,
            lambda directory: _get_workflow_calculator(
                calc_name,
                config,
                directory=f"{base_dir}/{directory}",
            ),
            policy=policy,
            directories=("endpoint_initial", "endpoint_final"),
            context="NEB",
        )

    if effective_parallel:
        init_chain = _sync_parallel_endpoint_results(init_chain, world, prepare_endpoints)
    else:
        prepare_endpoints(init_chain)
    allow_shared = should_share_calculator(calc_name, config, parallel=effective_parallel)
    
    # Initialize NEB
    neb_class = NEB if calc_config.get("neb_backend", "atst") == "ase" else AbacusNEB
    neb = neb_class(init_chain, 
                    parallel=effective_parallel,
                    world=world,
                    method=algorism, 
                    k=k,
                    climb=False if two_stage else climb,
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
            if rank_owns_local_image(world, i):
                # Determine directory logic
                image_dir = f"{base_dir}/image_{i + 1:03d}"
                
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
    opt = optimizer(neb, trajectory=traj_file, **calc_config.get("optimizer_kwargs", {}))
    stage1_converged = None
    stage1_actual_steps = None
    if two_stage:
        stage1_steps = calc_config.get("stage1_steps", 20)
        if stage1_steps is None:
            stage1_converged = opt.run(fmax=calc_config.get("stage1_fmax", 0.20))
        else:
            stage1_converged = opt.run(fmax=calc_config.get("stage1_fmax", 0.20), steps=stage1_steps)
        stage1_actual_steps = getattr(opt, "nsteps", None)
        neb.climb = climb
        opt = optimizer(neb, trajectory=traj_file, **calc_config.get("optimizer_kwargs", {}))
    final_converged = opt.run(fmax=fmax, steps=max_steps)
    final_actual_steps = getattr(opt, "nsteps", None)
    write_artifact_manifest(
        calc_config.get("artifact_manifest", "atst_artifacts.json"),
        workflow="neb",
        artifacts=[{"role": "trajectory", "path": traj_file}],
        stages=[
            {
                "name": "ordinary_neb_warmup",
                "status": "complete" if two_stage else "skipped",
                "fmax": calc_config.get("stage1_fmax", 0.20),
                "steps": calc_config.get("stage1_steps", 20),
                "converged": stage1_converged,
                "actual_steps": stage1_actual_steps,
            },
            {
                "name": "ci_neb" if climb else "neb",
                "status": "complete",
                "fmax": fmax,
                "steps": max_steps,
                "converged": final_converged,
                "actual_steps": final_actual_steps,
            },
        ],
    )
    LOGGER.info("NEB calculation finished")
    return init_chain if world.rank == 0 else None

def run_autoneb(config, calc_name, calc_config, world=None):
    """
    Execute AutoNEB calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    calc_config = _normalized_calculation(config, calc_config)
    runner = AutoNEBRunner(config, calc_name, calc_config, world=world)
    return runner.run()

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
    return atoms

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
    
    final_atoms = sella_run.run()
    LOGGER.info("Sella calculation finished")
    return final_atoms


def run_ccqn(config, calc_name, calc_config):
    """
    Execute CCQN calculation workflow.

    Args:
        config (dict): Full configuration dictionary.
        calc_name (str): Name of the calculator.
        calc_config (dict): Calculation-specific configuration.
    """
    LOGGER.info("Starting CCQN calculation")
    calc_config = _normalized_calculation(config, calc_config)

    init_structure = calc_config["init_structure"]
    traj_file = calc_config["trajectory"]
    atoms = get_last_frame(traj_file) if calc_config.get("restart") else read_structure(init_structure)

    ccqn = AbacusCCQN(
        init_Atoms=atoms,
        config=config,
        calc_name=calc_name,
        calc_config=calc_config,
        traj_file=traj_file,
    )
    final_atoms = ccqn.run()
    LOGGER.info("CCQN calculation finished")
    return final_atoms


def _build_parser():
    description = "ATST-Tools: ASE workflows for ABACUS-first transition-state calculations"
    epilog = dedent(
        """
        Configuration shape:
          calculation.type: neb | autoneb | dimer | sella | ccqn | d2s | relax | vibration | irc | md | dmf
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

    options = RunOptions(
        dry_run=getattr(args, "dry_run", False),
        restart=getattr(args, "restart", False),
        check_input=getattr(args, "check_input", False),
        check_input_timeout=getattr(args, "check_input_timeout", 120),
        abacus_executable=getattr(args, "abacus_executable", None),
    )
    try:
        if options.dry_run:
            # The shared API path performs the authoritative validation after
            # applying command-line overrides; retain the legacy log ordering.
            LOGGER.info("Configuration is valid: validation delegated to workflow API")
        result = run_workflow_from_cli(args.config, options)
    except ConfigValidationError as exc:
        raise ValueError(str(exc)) from None
    except MPIConfigurationError as exc:
        if exc.__cause__ is not None:
            raise exc.__cause__ from None
        raise ValueError(str(exc)) from None
    except UnsupportedDependencyError as exc:
        if exc.__cause__ is not None:
            raise exc.__cause__ from None
        raise RuntimeError(str(exc)) from None
    except WorkflowExecutionError as exc:
        if isinstance(exc.__cause__, IRCBoundaryError):
            raise SystemExit(str(exc.__cause__)) from None
        if exc.__cause__ is not None:
            raise exc.__cause__ from None
        raise RuntimeError(str(exc)) from None
    if options.dry_run:
        preflight = getattr(result, "metadata", {}).get("check_input_preflight")
        if preflight is not None:
            if preflight["status"] == "passed":
                LOGGER.info(
                    "ABACUS check-input preflight passed: checked=%s",
                    preflight["checked"],
                )
            else:
                LOGGER.info(
                    "ABACUS check-input preflight skipped: calculator.name=%s",
                    preflight["calculator_name"],
                )
    return result

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
