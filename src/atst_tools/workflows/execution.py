"""Shared workflow execution helpers for CLI and Python API entry points.

The application service imports this module only after selecting the caller's
MPI world. CLI argument parsing and result presentation remain in scripts.main.
"""

import logging
import os

import numpy as np
from ase.io import read, write
from ase.mep.neb import NEB
from ase.optimize import FIRE, BFGS, LBFGS, QuasiNewton

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.constant_potential import (
    constant_potential_restart_initial_electrons_for_config,
)
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.mep.neb import AbacusNEB
from atst_tools.mep.autoneb import AutoNEBRunner
from atst_tools.mep.dimer import AbacusDimer
from atst_tools.mep.sella import AbacusSella
from atst_tools.mep.ccqn import AbacusCCQN
from atst_tools.workflows.relax import RelaxWorkflow
from atst_tools.workflows.vibration import VibrationWorkflow
from atst_tools.workflows.d2s import D2SWorkflow
from atst_tools.workflows.irc import IRCWorkflow
from atst_tools.workflows.md import MDWorkflow
from atst_tools.workflows.dmf import DMFWorkflow
from atst_tools.workflows.endpoint_relax import relax_neb_endpoints
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.io import read_structure
from atst_tools.utils.neb_endpoints import (
    endpoint_policy,
    ensure_neb_endpoint_results,
    expected_cp_endpoint_identity,
)
from atst_tools.utils.restart_helpers import get_last_frame, get_last_neb_band
from atst_tools.utils.idpp import generate
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.geometry import prepare_fixed_cell_images, fixed_cell_metadata
from atst_tools.utils.convergence import (
    StageRecord,
    as_finite_float,
    as_step_count,
    emit_unconverged_advisory,
)
from atst_tools.utils.mpi import (
    get_ase_world,
    rank_owns_local_image,
    run_pre_run_construction,
    run_rank_zero_section,
    synchronize_rank_failure,
    validate_image_parallel_world,
)

LOGGER = logging.getLogger(__name__)


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


def _relax_neb_endpoints(
    init_chain, config, calc_name, calc_config, base_dir, optimizer_class,
    constant_potential_identity=None,
):
    """Run the shared NEB endpoint Relax stage with workflow calculator setup."""
    def endpoint_calculator(label, atoms):
        calculator_kwargs = {"directory": f"{base_dir}/endpoint_{label}_relax"}
        if calc_config.get("restart"):
            initial_electrons = constant_potential_restart_initial_electrons_for_config(
                atoms, config, allow_recompute=True
            )
            if initial_electrons is not None:
                calculator_kwargs["constant_potential_initial"] = initial_electrons
        return _get_workflow_calculator(calc_name, config, **calculator_kwargs)

    return relax_neb_endpoints(
        init_chain,
        calc_config.get("endpoint_optimization") or {},
        endpoint_calculator,
        optimizer_class,
        constant_potential_identity=constant_potential_identity,
    )


def _sync_parallel_endpoint_results(images, world, prepare_endpoints):
    """Prepare endpoints on rank 0 and share frozen images and stage facts."""
    sync_file = ".atst_neb_endpoint_synced.traj"
    endpoint_stages: list[StageRecord] = []

    def prepare_and_write():
        nonlocal endpoint_stages
        endpoint_stages = prepare_endpoints(images)
        write(sync_file, images, parallel=False)

    run_rank_zero_section(
        world,
        prepare_and_write,
        context="NEB endpoint preparation",
    )
    if hasattr(world, "barrier"):
        world.barrier()
    synchronized_read_error = None
    try:
        synced_images = read(sync_file, index=":", parallel=False)
    except Exception as exc:
        synchronized_read_error = exc
        synced_images = None
    synchronize_rank_failure(
        world,
        synchronized_read_error,
        context="NEB endpoint synchronization read",
    )
    if hasattr(world, "barrier"):
        world.barrier()
    def remove_sync_file():
        try:
            os.remove(sync_file)
        except FileNotFoundError:
            pass
    run_rank_zero_section(
        world,
        remove_sync_file,
        context="NEB endpoint synchronization cleanup",
    )
    if hasattr(world, "barrier"):
        world.barrier()
    return synced_images, endpoint_stages


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

    base_dir = _abacus_base_directory(config, 'run_atst')
    policy = endpoint_policy(calc_config, default="auto")
    endpoint_optimization_enabled = calc_config["endpoint_optimization"]["enabled"]
    optimizer = get_optimizer(calc_config['optimizer'])
    make_endpoint_stages: list[StageRecord] = []
    cp_identity = expected_cp_endpoint_identity(config)

    def require_results_before_never(endpoints):
        """Prevent an enabled endpoint relax from bypassing explicit `never`."""
        if policy == "never":
            ensure_neb_endpoint_results(
                endpoints,
                lambda directory: None,
                policy="never",
                context="NEB",
                constant_potential_identity=cp_identity,
            )

    if has_make:
        make_config = calc_config.get('make') or {}
        init_chain_file = make_config['output']
        fix_height, fix_dir = _parse_make_fix(make_config.get('fix'))
        mag_ele, mag_num = _parse_make_mag(make_config.get('magmom'))
        if not restart:
            def generate_initial_chain():
                def prepare_make_endpoints(initial, final):
                    endpoints = [initial, final]
                    require_results_before_never(endpoints)
                    make_endpoint_stages.extend(
                        _relax_neb_endpoints(
                            endpoints, config, calc_name, calc_config, base_dir, optimizer,
                            constant_potential_identity=cp_identity,
                        )
                    )

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
                    idpp_optimizer=make_config['idpp_optimizer'],
                    image_distribution=make_config['image_distribution'],
                    endpoint_prepare=prepare_make_endpoints if endpoint_optimization_enabled else None,
                )
            if effective_parallel:
                run_rank_zero_section(
                    world,
                    generate_initial_chain,
                    context="NEB initial-chain generation",
                )
            else:
                generate_initial_chain()
            if effective_parallel and hasattr(world, "barrier"):
                world.barrier()
    else:
        init_chain_file = calc_config['init_chain']
    initial_chain_error = None
    try:
        if restart:
            n_images = (
                # Segmented interpolation joins two endpoint-inclusive paths
                # at the TS guess, adding one image to the ordinary band.
                make_config['n_images'] + 2 + (make_config.get('ts_guess') is not None)
                if has_make
                else len(read(init_chain_file, index=':', parallel=False))
            )
            init_chain = get_last_neb_band(traj_file, n_images)
        else:
            init_chain = read(init_chain_file, index=':', parallel=False)
    except Exception as exc:
        initial_chain_error = exc
        init_chain = None
    if effective_parallel:
        synchronize_rank_failure(
            world,
            initial_chain_error,
            context="NEB initial-chain loading",
        )
    if initial_chain_error is not None:
        raise initial_chain_error

    def prepare_runtime_chain():
        return prepare_fixed_cell_images(
            init_chain, context="NEB input", runtime=True, world=world
        )
    init_chain = (
        run_pre_run_construction(world, prepare_runtime_chain, context="NEB cell preparation")
        if effective_parallel else prepare_runtime_chain()
    )

    # NEB Parameters
    climb = calc_config['climb']
    fmax = calc_config['fmax']
    k = calc_config['k']
    algorism = calc_config['algorism']
    max_steps = calc_config['max_steps']
    two_stage = calc_config.get("two_stage", False)
    if effective_parallel:
        validate_image_parallel_world(world, len(init_chain) - 2, "NEB")
        LOGGER.info(
            "Image-level NEB parallelism active: world.size=%s, interior_images=%s",
            world.size,
            len(init_chain) - 2,
        )

    def prepare_endpoints(images):
        """Prepare both NEB endpoints and return their endpoint stage records.

        Args:
            images: NEB band whose endpoints are relaxed and repaired in place.

        Returns:
            One :class:`StageRecord` per endpoint relaxation performed or skipped
            by this call, or an empty list when endpoint optimization is
            disabled.
        """
        if endpoint_optimization_enabled and policy == "never":
            require_results_before_never(images)
        if has_make and not restart and endpoint_optimization_enabled:
            endpoint_records = make_endpoint_stages
        else:
            endpoint_records = _relax_neb_endpoints(
                images, config, calc_name, calc_config, base_dir, optimizer,
                constant_potential_identity=cp_identity,
            )
        ensure_neb_endpoint_results(
            images,
            lambda directory: _get_workflow_calculator(
                calc_name,
                config,
                directory=f"{base_dir}/{directory}",
            ),
            policy=policy,
            directories=("endpoint_initial", "endpoint_final"),
            context="NEB",
            constant_potential_identity=cp_identity,
        )
        return endpoint_records

    endpoint_stages: list[StageRecord] = []
    if effective_parallel:
        init_chain, endpoint_stages = _sync_parallel_endpoint_results(init_chain, world, prepare_endpoints)
    else:
        endpoint_stages = prepare_endpoints(init_chain)
    allow_shared = should_share_calculator(calc_name, config, parallel=effective_parallel)

    neb_class = NEB if calc_config.get("neb_backend", "atst") == "ase" else AbacusNEB

    def construct_calculators():
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
                    calculator_kwargs = {"shared": False, "directory": image_dir}
                    if restart:
                        initial_electrons = constant_potential_restart_initial_electrons_for_config(
                            image, config
                        )
                        if initial_electrons is not None:
                            calculator_kwargs["constant_potential_initial"] = initial_electrons
                    image.calc = _get_workflow_calculator(calc_name, config, **calculator_kwargs)
            elif shared_calc is not None:
                image.calc = shared_calc
            else:
                calculator_kwargs = {"directory": f"{base_dir}/image_{i + 1:03d}"}
                if restart:
                    initial_electrons = constant_potential_restart_initial_electrons_for_config(
                        image, config
                    )
                    if initial_electrons is not None:
                        calculator_kwargs["constant_potential_initial"] = initial_electrons
                image.calc = _get_workflow_calculator(calc_name, config, **calculator_kwargs)

    def construct_neb():
        return neb_class(
            init_chain,
            parallel=effective_parallel,
            world=world,
            method=algorism,
            k=k,
            climb=False if two_stage else climb,
            allow_shared_calculator=allow_shared,
        )

    def construct_optimizer(neb):
        return optimizer(
            neb,
            trajectory=traj_file,
            **calc_config.get("optimizer_kwargs", {}),
        )

    if effective_parallel:
        run_pre_run_construction(
            world,
            construct_calculators,
            context="NEB calculator setup",
        )
        neb = run_pre_run_construction(
            world,
            construct_neb,
            context="NEB engine construction",
        )
        opt = run_pre_run_construction(
            world,
            lambda: construct_optimizer(neb),
            context="NEB optimizer construction",
        )
    else:
        construct_calculators()
        neb = construct_neb()
        opt = construct_optimizer(neb)

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
        if effective_parallel:
            opt = run_pre_run_construction(
                world,
                lambda: optimizer(
                    neb,
                    trajectory=traj_file,
                    **calc_config.get("optimizer_kwargs", {}),
                ),
                context="NEB climbing-stage optimizer construction",
            )
        else:
            opt = optimizer(
                neb,
                trajectory=traj_file,
                **calc_config.get("optimizer_kwargs", {}),
            )
    final_converged = opt.run(fmax=fmax, steps=max_steps)
    final_actual_steps = getattr(opt, "nsteps", None)
    final_record = StageRecord(
        name="ci_neb" if climb else "neb",
        role="final",
        criterion="neb_fmax",
        converged=final_converged,
        fmax=as_finite_float(fmax),
        steps=as_step_count(max_steps),
        actual_steps=as_step_count(final_actual_steps),
    )
    emit_unconverged_advisory(final_record, workflow="neb", world=world)
    warmup_record = StageRecord(
        name="ordinary_neb_warmup",
        role="warmup",
        status="complete" if two_stage else "skipped",
        fmax=as_finite_float(calc_config.get("stage1_fmax", 0.20)),
        steps=as_step_count(calc_config.get("stage1_steps", 20)),
        converged=stage1_converged,
        actual_steps=as_step_count(stage1_actual_steps),
    )
    # Rank 0 owns the endpoint optimizer facts and the manifest in MPI runs.
    # Other ranks receive only the endpoint images needed by the NEB engine.
    stages: list[StageRecord] = list(endpoint_stages)
    stages.extend((warmup_record, final_record))
    def write_manifest():
        write_artifact_manifest(
            calc_config.get("artifact_manifest", "atst_artifacts.json"),
            workflow="neb",
            artifacts=[{"role": "trajectory", "path": traj_file}],
            stages=[record.to_manifest() for record in stages],
            metadata={"fixed_cell": fixed_cell_metadata(init_chain)},
        )

    if effective_parallel:
        run_rank_zero_section(world, write_manifest, context="NEB manifest write")
    else:
        write_manifest()
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
