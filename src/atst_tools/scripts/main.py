"""ATST-Tools CLI entry point."""

import argparse
import logging
from textwrap import dedent

from atst_tools.utils.mpi import bootstrap_mpi_for_ase

bootstrap_mpi_for_ase()

from atst_tools import package_version
from atst_tools.api import RunOptions, validate_config
from atst_tools.api.services import run_workflow_from_cli
from atst_tools.api.models import (
    ConfigValidationError,
    MPIConfigurationError,
    UnsupportedDependencyError,
    WorkflowExecutionError,
)
from atst_tools.utils.config import ConfigLoader, VALID_CALCULATION_TYPES
from atst_tools.workflows.irc import IRCBoundaryError
from atst_tools.workflows.execution import (
    get_optimizer,
    run_autoneb,
    run_ccqn,
    run_dimer,
    run_neb,
    run_sella,
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
        "constant_potential": """\
calculation:
  type: constant_potential
  init_structure: inputs/init.stru
  directory: constant_potential_run
  results_file: constant_potential_results.json
  log_file: constant_potential.log
  checkpoint_file: constant_potential_checkpoint.json
""",
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
  eta: 0.005
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
    if calculation_type == "constant_potential":
        calculator += """\
  constant_potential:
    # Required boundary profile: reference_fcp is reference-only; use
    # compensated_gate for optimization workflows after preparing the gate.
    energy_boundary: reference_fcp
    # Set exactly one of potential_v or potentials_v.
    potential_v: 0.0
    # potentials_v: [-0.2, 0.0, 0.2]
    reference_electrode: SHE
    work_ref: 4.6
    work_ref_source: "declared calibration source"
    reference_electrons: 216
    potential_tolerance_v: 0.01
    max_iterations: 100
    capacitance_initial: 0.0125
    capacitance_unit: e/(V Angstrom^2)
"""
    return calculation_blocks[calculation_type] + "\n" + calculator


def _build_parser():
    description = "ATST-Tools: ASE workflows for ABACUS-first transition-state calculations"
    epilog = dedent(
        """
        Configuration shape:
          calculation.type: constant_potential | neb | autoneb | dimer | sella | ccqn | d2s | relax | vibration | irc | md | dmf
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
        result = run_workflow_from_cli(args.config, options)
    except ConfigValidationError as exc:
        if isinstance(exc.__cause__, (FileNotFoundError, IsADirectoryError)):
            raise exc.__cause__ from None
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
        LOGGER.info(
            "Configuration is valid: calculation.type=%s, calculator.name=%s",
            result.workflow,
            result.metadata["calculator_name"],
        )
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
