# ATST-Tools Configuration Reference

**Version**: 2.2.0
**Last Updated**: 2026-06-27
**Status**: Maintained

This document is the hand-written semantic reference for `config.yaml` files
used by `atst run`. It explains workflow behavior, common configuration
patterns, backend boundaries, and migration notes. The generated parameter
table is maintained separately in
[YAML_INPUT_VARIABLES.md](YAML_INPUT_VARIABLES.md), which is the main lookup
entry for schema-governed non-calculator YAML fields.

The configuration is divided into two main sections: `calculation` (task
definition) and `calculator` (engine configuration). New configurations should
use this two-section layout; root-level `abacus` is retained only as a
migration path for legacy inputs.

YAML variables are governed by the Pydantic schema in
`src/atst_tools/utils/config_schema.py`. `atst run` validates and normalizes the
input before dispatching workflows, so optional variables get schema defaults
before runtime. Use `atst config validate --print-normalized` to inspect the
exact defaults that will be applied.

The same YAML path or an equivalent mapping can be passed to `run_workflow()`
through the stable [Python API reference](PYTHON_API_REFERENCE.md). Both
interfaces preserve existing schema defaults and interpret relative paths from
the process current working directory rather than the YAML file's parent.

---

## 1. Top-Level Structure

```yaml
calculation:
  type: <task_type>  # Required. Options: neb, autoneb, dimer, sella, ccqn, d2s, relax, vibration, irc, md, dmf
  # ... task specific parameters ...

calculator:
  name: <engine_name> # Required. Options: abacus, dp
  # ... engine specific parameters ...
```

Useful CLI checks:

```bash
atst run --dry-run config.yaml
atst config validate config.yaml --print-normalized
atst config validate config.yaml --output used_config.yaml
atst run --list-types
atst run --show-template neb --calculator abacus
```

There is no `config_version` field in ATST-Tools YAML. The active schema is the
schema shipped with the installed package version, and unknown top-level fields
are rejected.

---

## 2. Calculation Section

The `calculation` section defines the type of task and its parameters.

### 2.1 Common Parameters (All Types)
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `type` | string | **Required** | Task type: `neb`, `autoneb`, `dimer`, `sella`, `ccqn`, `d2s`, `relax`, `vibration`, `irc`, `md`, `dmf`. |
| `restart` | bool | `false` | Resume from workflow checkpoints when supported. CLI equivalent: `atst run --restart config.yaml`. |

Other common names such as `fmax`, `max_steps`, `optimizer`, `trajectory`, and `parallel` are type-specific in the schema because their defaults differ by workflow.

### 2.2 Nudged Elastic Band (NEB)
**Type**: `neb`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_chain` | string | One of `init_chain` / `make` | Path to the initial chain file (e.g., `init_neb_chain.traj`). |
| `climb` | bool | `True` | Enable Climbing Image NEB (CI-NEB). |
| `two_stage` | bool | `False` | Run a short ordinary NEB warm-up before enabling CI-NEB. |
| `stage1_steps` | int/null | `20` | Maximum ordinary NEB warm-up steps when `two_stage: true`; warm-up stops when `stage1_fmax` is reached or this limit is exhausted. `null` uses the ASE optimizer default step limit. |
| `stage1_fmax` | float | `0.20` | Warm-up force threshold when `two_stage: true`. |
| `k` | float | `0.1` | Spring constant for the band (eV/Å²). |
| `algorism` | string | `improvedtangent` | Tangent method. |
| `neb_backend` | string | `atst` | Experimental backend selector: `atst` uses the validated compatibility wrapper; `ase` uses native ASE NEB. |
| `trajectory` | string | `neb.traj` | NEB trajectory. Restart uses the latest band from this file when available. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `parallel` | bool | `true` | Enable MPI image-level parallelism when available. |
| `optimizer` | string | `FIRE` | ASE optimizer. |
| `optimizer_kwargs` | dict | `{}` | Extra keyword arguments forwarded to the ASE optimizer constructor. |
| `max_steps` | int | `100` | Maximum optimizer steps. |
| `fmax` | float | `0.05` | Force convergence threshold. |
| `endpoint_singlepoint` | string | `auto` | Endpoint result policy: `auto`, `always`, or `never`. |
| `endpoint_optimization` | dict | disabled | Optional endpoint relaxation before ordinary NEB. |

`init_chain` and `make` are mutually exclusive. Use `init_chain` when the chain already exists; use nested `make` when `atst run` should generate the chain immediately before launching NEB:

```yaml
calculation:
  type: neb
  make:
    init_structure: inputs/init.stru
    final_structure: inputs/final.stru
    n_images: 5
    method: IDPP
    output: inputs/init_neb_chain.traj
    ts_guess: null
    fix: null       # optional HEIGHT:DIR or {height: 0.25, dir: 2}
    magmom: null    # optional Fe:2.5,O:1.0 or {Fe: 2.5, O: 1.0}
    no_align: false
  fmax: 0.05
```

The nested NEB `make.method` value accepts `IDPP` (default) or `linear`. `IDPP` starts from the aligned linear interpolation and then runs the in-repository `Fast_IDPPSolver`; `linear` writes the aligned linear interpolation directly. `init_structure`, `final_structure`, and `ts_guess` may be ABACUS `STRU` / `.stru` files. Their mobility flags are preserved as ASE constraints in the generated chain and in ABACUS image input writing, including full `m 0 0 0` fixed atoms and partial Cartesian mobility such as `m 1 0 1`. `sort_tol` / pymatgen autosort is intentionally dropped.

ASE NEB/DyNEB does not optimize endpoint images, but tangent and barrier analysis use endpoint energies. If a chain was made from pure structures, `atst neb make` writes placeholder endpoint results. `atst run` repairs these by default with endpoint single-point calculations before constructing NEB:

```yaml
calculation:
  type: neb
  init_chain: inputs/init_neb_chain.traj
  endpoint_singlepoint: auto  # auto, always, or never
```

`auto` computes only missing/placeholder endpoint results and prints a warning. `always` recomputes both endpoints. `never` rejects missing/placeholder endpoint results.

For CI-NEB stability, `two_stage: true` first constructs the band with `climb=False`, runs ordinary NEB with `stage1_fmax` and `stage1_steps`, then sets `neb.climb = climb` and runs the final stage with `fmax` and `max_steps`. The first stage uses ASE optimizer stop semantics: it stops when either `stage1_fmax` is reached or `stage1_steps` is exhausted. The default `stage1_steps: 20` is a bounded warm-up, not a guarantee that the ordinary NEB stage will reach `stage1_fmax`. Set `stage1_steps: null` only when you intentionally want the first stage to rely on `stage1_fmax` and ASE's very large default optimizer step limit; this can be expensive for ABACUS.

For MPI image-level NEB, launch the Python workflow itself under MPI and keep
one Python rank per interior image:

```bash
mpirun -np <number-of-interior-images> atst run config.yaml
```

When `parallel: true` and ASE sees `world.size > 1`, ATST-Tools requires the MPI
rank count to equal `len(init_chain) - 2`. Each active image gets its own ABACUS
calculator directory such as `run_neb/image_001`, following the same
image-isolated directory model used by the vendored abacuslite NEB example.
This outer MPI layer is separate from `calculator.abacus.mpi`, which controls
the ABACUS subprocess count for one image. ATST-Tools does not run or generate
Slurm submission commands; use your site job script to launch the outer Python
MPI command, and keep all ABACUS executable details in `calculator.abacus`.

### 2.3 AutoNEB
**Type**: `autoneb`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `prefix` | string | `run_autoneb` | Prefix for output files and directories. |
| `init_chain` | string | **Required** | Path to the initial guess chain. |
| `n_simul` | positive int/null | `null` | Number of images to optimize simultaneously; null means `world.size`. |
| `n_max` | int | `10` | Maximum number of images in the band. |
| `neb_backend` | string | `atst` | Experimental backend selector: `atst` uses the validated compatibility wrapper; `ase` uses native ASE AutoNEB. |
| `maxsteps` | int/list[int] | `100` | Maximum optimization steps per iteration; a two-value list follows ASE AutoNEB's normal/climbing-stage schedule. |
| `iter_folder` | string | `AutoNEB_iter` | Folder to store iteration results. |
| `parallel` | bool | `true` | Enable MPI image-level parallelism when available. |
| `optimizer` | string | `FIRE` | `FIRE` or `BFGS`. |
| `optimizer_kwargs` | dict | `{}` | Keyword arguments forwarded to the ASE optimizer constructor; for difficult FIRE AutoNEB runs, consider `downhill_check: true` and a smaller `maxstep`. |
| `climb` | bool | `true` | Enable climbing image refinement. |
| `fmax` | float/list[float] | `0.05` | Force threshold or AutoNEB threshold schedule. |
| `endpoint_singlepoint` | string | `auto` | Same endpoint result policy as ordinary NEB. |

For MPI AutoNEB, launch with one Python rank per simultaneously optimized
image. If `n_simul` is set, `world.size` must equal `n_simul`; if `n_simul` is
`null`, ATST-Tools uses `world.size`. The same outer/inner MPI distinction as
ordinary NEB applies.

### 2.3b Molecular Dynamics (MD)
**Type**: `md`

ATST-Tools supports two MD drivers:

- `driver: ase`: ASE owns the MD integrator/thermostat/barostat while ABACUS or
  DP provides forces through the normal ASE calculator interface.
- `driver: abacus_native`: ABACUS owns the MD run. ATST-Tools uses abacuslite to
  prepare `INPUT`, `KPT`, and `STRU`, starts the ABACUS command in the configured
  directory, then collects `running_md.log` / `MD_dump` outputs.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `driver` | string | `ase` | `ase` or `abacus_native`. |
| `init_structure` | string | **Required** | Initial structure file. |
| `steps` | int | `100` | Number of MD steps. |
| `ensemble` | string | `nvt` | ASE driver ensemble: `nve`, `nvt`, or `npt`. Ignored by `abacus_native`. |
| `algorithm` | string | `bussi` | ASE algorithm: `velocityverlet`, `bussi`, `langevin`, `nvtberendsen`, or `nptberendsen`. |
| `timestep_fs` | float | `1.0` | ASE timestep in fs. |
| `temperature_K` | float | `300.0` | Initial or target temperature. |
| `trajectory` | string | `md.traj` | ASE trajectory written by either driver. |
| `logfile` | string | `md.log` | ASE MD log file for `driver: ase`. |
| `summary_file` | string | `md_summary.json` | JSON summary output. |
| `final_structure` | string | `md_final.traj` | Final structure output. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `postprocess.summary.enabled` | bool | `true` | Write MD post-processing summary after a successful workflow. |
| `postprocess.summary.output` | string | `md_post_summary.json` | MD post-processing summary JSON output. |
| `postprocess.convert.enabled` | bool | `false` | Convert MD trajectory after a successful workflow. |
| `postprocess.convert.format` | string | `extxyz` | Output format: `traj`, `extxyz`, `cif`, `stru`, or `xyz`. |
| `postprocess.convert.output_prefix` | string | `md_post` | Output prefix or directory for converted MD frames. |
| `postprocess.convert.frame` | int/null | `null` | Optional single frame index to convert. |
| `postprocess.convert.stride` | int | `1` | Frame stride for conversion. |
| `directory` | string | `md_run` | ASE calculator directory or ABACUS native run directory. |
| `poll_interval_seconds` | float | `5.0` | ABACUS native process polling interval. |

For `driver: ase`, algorithm compatibility is explicit: `nve` uses
`velocityverlet`; `nvt` uses `bussi`, `langevin`, or `nvtberendsen`; `npt` uses
`nptberendsen`. NPT requires calculator stress support. For ABACUS, set
`cal_stress: 1`; for DP, use a model that provides virial/stress.

For `driver: abacus_native`, `calculator.name` must be `abacus`, and ABACUS MD
keywords are passed directly through `calculator.abacus.parameters`. ATST-Tools
only requires `calculation: md` and does not rename ABACUS-specific MD INPUT
variables.

After successful MD workflows, ATST-Tools writes a post-processing summary by
default. Trajectory conversion is opt-in in YAML or can be run later with
`atst md post`.

### 2.3c Direct MaxFlux (DMF, experimental)
**Type**: `dmf`

DMF is an experimental standalone Direct MaxFlux path optimizer. It writes a
transition-state candidate from the path maximum (`tmax`), not a validated TS.
Use Dimer, Sella, CCQN, vibration, and IRC validation before reporting a final
transition state.

ATST-Tools vendors PyDMF under `atst_tools.external.pydmf`, but runtime still
requires `cyipopt` and IPOPT in the active environment.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_file` | string | **Required** | Initial endpoint structure. |
| `final_file` | string | **Required** | Final endpoint structure. |
| `directory` | string | `dmf_run` | Calculator working directory. |
| `trajectory` | string | `dmf_path.traj` | DMF evaluation path trajectory. |
| `tmax_trajectory` | string | `dmf_tmax.traj` | Highest-energy candidate trajectory with single-point energy/forces attached. |
| `summary_file` | string | `dmf_summary.json` | JSON summary with `experimental: true`, `result_type: ts_candidate`, `validated_ts: false`, `nmove`, and final `t_eval`. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `initial_path` | string | `cfbenm` | Initial path generator: `linear`, `fbenm`, or `cfbenm`. |
| `nsegs` | int | `4` | Number of B-spline segments. |
| `dspl` | int | `3` | B-spline polynomial degree. |
| `nmove` | int | `10` | Number of movable DMF evaluation images; the written path has `nmove + 2` images including endpoints. |
| `beta` | float/null | `null` | Optional DirectMaxFlux beta override. |
| `update_teval` | bool | `true` | Enable adaptive evaluation point updates. |
| `tol` | string/float | `middle` | IPOPT tolerance preset or numeric value. |
| `ipopt_options` | dict | `{}` | Additional IPOPT options forwarded to PyDMF, such as `max_iter` or `print_level`. |
| `parallel` | bool | `false` | Enable PyDMF threaded energy/force evaluation. |
| `remove_rotation_and_translation` | bool | `true` | Remove global translation/rotation for non-periodic systems. |
| `pbc_mode` | string | `reject` | `reject` or experimental `cartesian_unwrapped`. |
| `confirm_pbc_risk` | bool | `false` | Required for `pbc_mode: cartesian_unwrapped`. |

Periodic endpoints are rejected by default. The experimental
`cartesian_unwrapped` mode requires identical endpoint cell/PBC flags,
`initial_path: linear`, `confirm_pbc_risk: true`, and
`remove_rotation_and_translation: false`. It uses the current Cartesian
positions as supplied and does not provide MIC-aware or fractional-coordinate
DMF.

```yaml
calculation:
  type: dmf
  init_file: inputs/init.xyz
  final_file: inputs/final.xyz
  initial_path: cfbenm
  pbc_mode: reject

calculator:
  name: dp
  dp:
    model: ../../temp_repos/dp_model/DPA-3.1-3M.pt
    head: Omat24
```

### 2.4 Dimer Method
**Type**: `dimer`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure (e.g., `dimer_init.traj`). |
| `init_eigenmode_method` | string | `displacement` | Method to initialize eigenmode: `displacement`. |
| `displacement_vector` | string | `None` | Path to numpy file containing displacement vector (e.g., `vector.npy`). |
| `trajectory` | string | `dimer.traj` | Dimer trajectory. Restart uses the last frame when available. |
| `fmax` | float | `0.05` | Force convergence threshold. |
| `max_steps` | int/null | `null` | Maximum optimizer steps; null lets ASE run until convergence. |
| `dimer_separation` | float | `0.01` | Dimer finite-difference separation. |
| `max_num_rot` | int | `3` | Maximum dimer rotations per step. |
| `directory` | string | `dimer_run` | Calculator working directory. |

### 2.5 Sella (Saddle Point Finder)
**Type**: `sella`

Reference: Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
Jónsson, H. *Sella, an Open-Source Chemical Kinetics Environment.*
J. Chem. Theory Comput. **18** (8), 4914-4930 (2022). <https://doi.org/10.1021/acs.jctc.2c00395>

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure. |
| `eta` | float | `0.005` | Sella parameter (step size control). |
| `order` | int | `1` | Saddle point order (1 for TS). |
| `trajectory` | string | `sella.traj` | Sella trajectory. Restart uses the last frame when available. |
| `fmax` | float | `0.05` | Force convergence threshold. |
| `max_steps` | int/null | `null` | Maximum optimizer steps; null lets Sella run until convergence. |
| `directory` | string | `sella_run` | Calculator working directory. |

### 2.6 CCQN (Cone-Shaped Constrained Quasi-Newton)
**Type**: `ccqn`

Reference: Wu, Y.; Wang, H. *Cone-Shaped Constrained Quasi-Newton Method:
Efficient and Robust Single-Ended Transition State Optimization Algorithm.*
J. Chem. Theory Comput. (2025). <https://doi.org/10.1021/acs.jctc.5c01015>

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Initial transition-state guess. |
| `e_vector_method` | string | `ic` | Cone-axis method: `ic` from reactive bonds or `interp` from a product-like structure. |
| `reactive_bonds` | string/list | `None` | Required for `ic`; 1-based pairs such as `"1-2,3-4"` or `[[1, 2], [3, 4]]`. |
| `product_file` | string/null | `None` | Required for standalone `interp`; product-like structure with matching atom order. |
| `align_product_indices` | bool | `false` | Reorder `product_file` atom indices to match the initial structure before interpolation. |
| `auto_reactive_bonds` | dict | disabled | Enumerate ranked molecule-surface reactive bond candidates for `ic` mode. |
| `mode_manifest` | string | `ccqn_mode_manifest.json` | JSON manifest for enumerated and selected CCQN modes. |
| `diagnostics_file` | string/null | `ccqn_diagnostics.json` | Step-level CCQN diagnostics JSON. |
| `ic_mode` | string | `democratic` | `democratic` normalizes each bond contribution; `sum` uses raw projected contributions. |
| `cos_phi` | float | `0.5` | Cosine of the cone half angle. |
| `trust_radius_uphill` | float | `0.1` | Fixed uphill trust radius. |
| `trust_radius_saddle_initial` | float | `0.05` | Initial PRFO trust radius after entering the saddle region. |
| `trajectory` | string | `ccqn.traj` | CCQN trajectory. Restart uses the last frame when available. |
| `logfile` | string | `ccqn.log` | Optimizer log file. |
| `final_structure` | string | `ccqn_final.extxyz` | Final optimized structure. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `fmax` | float | `0.05` | Force convergence threshold. CCQN only declares convergence in PRFO mode. |
| `max_steps` | int/null | `200` | Maximum optimizer steps. |
| `hessian` | bool | `false` | Use calculator Hessian when available; ABACUS force-only use normally leaves this false. |
| `accept_initial_converged` | bool | `false` | Accept an already force-converged TS guess before taking an uphill CCQN step. |
| `directory` | string | `ccqn_run` | Calculator working directory. |

CCQN is a single-ended transition-state optimizer. In `ic` mode, the user supplies chemically meaningful reactive bonds or enables `auto_reactive_bonds`. In `interp` mode, CCQN uses the displacement from the current structure to `product_file` as the cone axis. `accept_initial_converged` is intended for final-TS confirmation examples that start from a separately verified saddle point; keep it false for ordinary searches.

Example automatic IC mode setup:

```yaml
calculation:
  type: ccqn
  init_structure: inputs/ts_guess.traj
  e_vector_method: ic
  auto_reactive_bonds:
    enabled: true
    molecule_indices: "1-12"
    active_catalyst_indices: "13-40"
    cutoff_A: 3.0
    max_modes: 20
  mode_manifest: ccqn_mode_manifest.json
  diagnostics_file: ccqn_diagnostics.json
```

### 2.7 Structure Relaxation (Relax)
**Type**: `relax`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure file. |
| `fmax` | float | `0.05` | Force convergence threshold. |
| `max_steps` | int | `200` | Maximum optimizer steps. |
| `optimizer` | string | `FIRE` | ASE optimizer name. |
| `trajectory` | string | `relax.traj` | Relaxation trajectory. Restart uses the last frame when available. |
| `logfile` | string | `relax.log` | Optimizer log file. |
| `directory` | string | `relax_run` | Calculator working directory. |

### 2.8 Vibration Analysis
**Type**: `vibration`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the optimized structure. |
| `delta` | float | `0.01` | Displacement step size (Å). |
| `nfree` | int | `2` | Number of displacements per degree of freedom (2 or 4). |
| `indices` | list[int] | `None` | List of atom indices to vibrate. If None, all atoms are vibrated. |
| `name` | string | `vib` | Name prefix for vibration files. |
| `results_file` | string | `vibration_results.json` | Vibration JSON output. |
| `validation_file` | string | `ts_validation.json` | Transition-state validation JSON output. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `restart` | bool | `false` | Reuse existing ASE vibration cache files. The default removes stale cache files before running. |
| `directory` | string | `vib_run` | Calculator working directory. |

Thermochemistry is controlled by an optional nested block:

```yaml
calculation:
  type: vibration
  init_structure: inputs/ts_opt.stru
  thermochemistry:
    model: harmonic        # harmonic or ideal_gas
    temperature: 300.0
    ignore_imag_modes: true
    energy_threshold: 1.0e-6
```

`model: harmonic` uses ASE `HarmonicThermo` and reports ZPE, entropy, internal energy, and Helmholtz free energy. This is the default for surfaces, adsorbates, TS local modes, and solid-like approximations. Before thermochemistry is evaluated, ATST-Tools keeps only real vibrational energies greater than `energy_threshold` (eV); the default `1.0e-6` removes near-zero finite-difference noise modes that can appear in high-symmetry crystals.

For isolated small molecules, use `model: ideal_gas`:

```yaml
thermochemistry:
  model: ideal_gas
  temperature: 298.15
  pressure: 101325.0
  geometry: linear          # monatomic, linear, or nonlinear
  symmetrynumber: 2
  spin: 0
  ignore_imag_modes: true
  energy_threshold: 1.0e-6
```

This uses ASE `IdealGasThermo` and includes translational, rotational, and vibrational degrees of freedom in the reported Gibbs free energy.

After a vibration run, ATST-Tools writes `results_file`, a standardized `validation_file`, and an `atst_artifacts.json` manifest. The validation summary currently checks whether exactly one significant imaginary mode is present; it is intended as a machine-readable TS sanity check, not a substitute for chemical inspection.

### 2.9 D2S (Double-Ended to Single-Ended)
**Type**: `d2s`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `method` | string | `dimer` | Single-ended method: `dimer`, `sella`, or `ccqn`. |
| `rough_method` | string | `neb` | Rough double-ended method. `neb` is the supported default; `dmf` enables the experimental DMF rough stage. |
| `init_file` | string | **Required** | Initial state structure file. |
| `final_file` | string | **Required** | Final state structure file. |
| `neb` | dict | `{}` | Configuration for the rough DyNEB phase. |
| `dmf` | dict | `{}` | Experimental rough DMF configuration used when `rough_method: dmf`. |
| `dimer` | dict | `{}` | Configuration for Dimer phase (if method=dimer). |
| `sella` | dict | `{}` | Configuration for Sella phase (if method=sella). |
| `ccqn` | dict | `{}` | Configuration for CCQN phase (if method=ccqn). |
| `endpoint_optimization` | dict | Enabled by default | Endpoint optimization policy before rough DyNEB. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |

D2S optimizes endpoints by default, then builds the rough DyNEB chain when
`rough_method: neb`. `neb.idpp_maxiter` and `neb.idpp_tol` configure the
in-repository Fast IDPP path optimizer. `neb.scale_fmax` is forwarded to ASE
`DyNEB(scale_fmax=...)`, and `neb.optimizer_kwargs` is forwarded to the rough
DyNEB FIRE optimizer. With `rough_method: dmf`, D2S writes optimized endpoints
for the standalone DMF runner, reads the DMF evaluation path, records
`dmf_candidate -> single_ended -> validation` artifacts, and then continues to
the selected Dimer/Sella/CCQN stage. When the DMF summary includes final
`t_eval`, D2S selects neighboring rough-path images from the actual evaluation
grid around `tmax`; legacy summaries without `t_eval` fall back to the uniform
grid estimate. DMF remains experimental and is not the default production path
until refinement plus vibration/IRC runtime validation is available. If
`method: ccqn`, the default `ccqn.e_vector_method: interp` uses the
highest-energy rough NEB image and its neighboring image as a local
product-like reference, so no user reactive-bond input is required. If
`ccqn.e_vector_method: ic`, set `ccqn.reactive_bonds`. If input endpoints
already carry energy/force results, this stage is skipped by default:

```yaml
calculation:
  type: d2s
  endpoint_optimization:
    enabled: true
    skip_if_has_results: true
    fmax: 0.05
    max_steps: 200
  endpoint_singlepoint: auto
```

Set `endpoint_optimization.enabled: false` only when the supplied endpoints already have meaningful results or when `endpoint_singlepoint: auto/always` should perform endpoint single-point calculations instead. `endpoint_singlepoint: never` rejects missing/placeholder endpoint results.

Optional vibration can be enabled after the single-ended Dimer/Sella step:

```yaml
calculation:
  type: d2s
  vibration:
    enabled: false
    indices: auto        # auto, all, or explicit list such as [0, 1, 2]
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
```

`indices: auto` uses the rough NEB displacement analysis to select the main moving atoms. `indices: all` passes `None` to ASE `Vibrations`.

### 2.10 IRC
**Type**: `irc`

IRC supports the Sella backend and an opt-in descent backend. The Sella backend follows the legacy main-branch `sella_IRC.py` behavior through YAML. It starts from a TS structure, runs Sella IRC forward, reverse, or both directions, and writes a normalized trajectory for the combined mode.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `backend` | string | `sella` | `sella` for strict Sella IRC, or `descent` for mode-displaced downhill relaxation. |
| `init_structure` | string | **Required** | TS structure used as the IRC starting point. |
| `trajectory` | string | `irc_log.traj` | IRC trajectory. Restart appends from the last frame. |
| `artifact_manifest` | string | `atst_artifacts.json` | Workflow artifact manifest JSON output. |
| `normalized_trajectory` | string | `norm_<trajectory>` | Output for normalized forward/reverse trajectory when `direction: both`. |
| `direction` | string | `both` | `both`, `forward`, or `reverse`. |
| `mode_vector` | string/null | `None` | Required NumPy mode vector for `backend: descent`. |
| `descent_delta` | float | `0.1` | Initial displacement along the normalized mode vector for descent backend. |
| `fmax` | float | `0.05` | IRC convergence criterion. |
| `max_steps` | int | `1000` | Steps per IRC direction. |
| `dx` | float | `0.1` | IRC step size. |
| `eta` | float | `0.0001` | Sella IRC parameter. |
| `gamma` | float | `0.1` | Sella IRC parameter. |
| `irctol` | float | `0.01` | IRC tolerance. |
| `keep_going` | bool | `false` | Forwarded to `sella.IRC`. |
| `directory` | string | `irc_run` | Calculator working directory. |

---

## 3. Calculator Section

The `calculator` section configures the underlying compute engine (DFT or ML Potential).

### 3.1 ABACUS (DFT)
**Name**: `abacus`
> **Note**: For backward compatibility, parameters can also be placed under an `abacus` root key instead of `calculator.abacus`.
> On the SAI GPU validation environment, LCAO examples use `ks_solver: cusolver`.
> ATST-Tools imports an independently installed `abacuslite` package first and falls back to the vendored `src/atst_tools/external/ASE_interface/abacuslite` snapshot if that import is unavailable.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `command` | string | `abacus` | Command to execute ABACUS (e.g., `mpirun -np 4 abacus`). |
| `mpi` | int | `1` | Number of MPI processes (deprecated, use `command` to specify mpirun). |
| `omp` | int | `1` | Number of OpenMP threads per process. |
| `directory` | string | `.` | Working directory for the calculator. |
| `kpts` | list[int] | `[1, 1, 1]` | K-points sampling (e.g., `[3, 3, 3]`). |
| `pseudopotentials` | dict | **Required** | Map of element symbol to UPF file name. |
| `basissets` | dict | **Required** | Map of element symbol to ORB file name (for LCAO). |
| `pseudo_dir` | string | `.` | Directory containing pseudopotential files. |
| `orbital_dir` | string | `.` | Directory containing basis set files. |
| `parameters` | dict | `{}` | Key-value pairs for ABACUS `INPUT` file (e.g., `ecutwfc`, `scf_thr`). |

`command` may be a bare executable (`abacus`), an explicit launcher
(`mpirun -np 4 abacus`, `srun -n 4 abacus`), or a template using `{mpi}` such
as `mpirun -np {mpi} abacus`. This command is the inner ABACUS execution command
for one image; it is not the outer image-level MPI launcher. In image-level MPI
mode, a bare single-process ABACUS command is run with outer MPI launcher
variables removed so ABACUS does not accidentally join the Python MPI world.
`command` is executed without a shell, so do not start it with shell-style
environment assignments such as `OMP_NUM_THREADS=4 abacus`; use `omp: 4`
instead. For other environment variables, use an explicit `env VAR=value ...`
command or a site wrapper, and set `version_command` when version probing needs
a different lightweight command.

The same `calculator.abacus` block can be used for local input preparation:

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
```

This writes `INPUT`, `KPT`, and `STRU` through the active `abacuslite` writer.
It is a pre-processing helper only; run submission and resource management stay
outside ATST-Tools.

### 3.2 Deep Potential (DP)
**Name**: `dp`

DP support uses the unified deepmd-kit ASE interface, `deepmd.calculator.DP`.
deepmd-kit detects the model backend from the model file; ATST-Tools does not
provide a separate backend selector. Multi-head DPA/DPA3 models should set
`head`.

> **Note**: In most cases, you only need to provide the `model` parameter.
> `type_map` and `type_dict` are optional and only needed for special cases
> where manual override of type mapping is required.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `model` | string | **Required** | Path to the frozen model file (`.pb`, `.pt`, etc.). |
| `head` | string/null | `None` | Model head for multi-head DPA/DPA3 models. |
| `type_map` | list[string] | `None` | **Optional**: Element order converted to deepmd-kit `type_dict`. Mutually exclusive with `type_dict`. |
| `type_dict` | dict[string,int] | `None` | **Optional**: Explicit deepmd-kit element-to-type-index mapping. |
| `omp` | int | unset | OpenMP thread count for DP evaluation (`OMP_NUM_THREADS`). |
| `share_calculator` | bool | `true` | Reuse one DP calculator where ASE permits shared calculators, especially serial NEB/DyNEB/AutoNEB. |

---

## 4. Schema Governance

The YAML schema is the source of truth for variable types, defaults, and descriptions. When adding a new workflow or calculator option:

1. Add the field to `src/atst_tools/utils/config_schema.py`.
2. Provide a type, default when safe, and `Field(description=...)`.
3. Add validation for enums, positive numeric values, and mutually exclusive inputs.
4. Regenerate `docs/user/YAML_INPUT_VARIABLES.md` with `python -m atst_tools.utils.config_docs`.
5. Update this reference and one example YAML when the option is user-facing.
6. Add or update unit tests around `ConfigLoader.normalize()` / `validate()`.

Unknown `calculation` and DP calculator fields are rejected by default. ABACUS INPUT variables should go under `calculator.abacus.parameters`, which is intentionally pass-through.

## 5. Example Configuration

See `examples/` directory for full working examples of each calculation type.

```yaml
# minimal_example.yaml
calculation:
  type: relax
  init_structure: init.stru
  fmax: 0.01

calculator:
  name: dp
  dp:
    model: /path/to/model.pb-or-pt
    head: null
    share_calculator: true
```
