# ATST-Tools Configuration Reference

**Version**: 2.2.8
**Last Updated**: 2026-09-20
**Status**: Release candidate 2.2.8 reference; the CP candidate is documented separately

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

The installed package schema governs YAML variables. `atst run` validates and
normalizes the input before dispatching workflows, so optional variables get
schema defaults before runtime. Use `atst config validate --print-normalized`
to inspect the exact defaults that will be applied.

The same YAML path or an equivalent mapping can be passed to `run_workflow()`
through the stable [Python API reference](PYTHON_API_REFERENCE.md). Both
interfaces preserve existing schema defaults and interpret relative paths from
the process current working directory rather than the YAML file's parent.

---

## 1. Top-Level Structure

```yaml
calculation:
  type: <task_type>  # Required. Options: constant_potential, neb, autoneb, dimer, sella, ccqn, d2s, relax, vibration, irc, md, dmf
  # ... task specific parameters ...

calculator:
  name: <engine_name> # Required. Options: abacus, dp
  # ... engine specific parameters ...

runtime:              # Optional: device binding, thread budget and run evidence
  devices: [0]
  binding: inherit
  threads: auto
  telemetry: false
```

The optional `runtime` section is described in [section 4](#4-runtime-section).

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
| `type` | string | **Required** | Task type: `constant_potential`, `neb`, `autoneb`, `dimer`, `sella`, `ccqn`, `d2s`, `relax`, `vibration`, `irc`, `md`, `dmf`. |
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

`auto` (default) trusts only endpoint results explicitly marked by ATST as
`computed`/`optimized`/`provided`; missing, placeholder, or unmarked (e.g.
uploaded-chain/foreign) results are recomputed with the current run's calculator so
the path and its endpoints stay consistent. `always` recomputes both endpoints.
`never` preserves user-provided readable endpoint results and raises only when an
endpoint lacks meaningful energy/force results.

The trust marker is the per-image `atst_endpoint_result` attribute that ATST
workflows write (`computed` after a single-point, `optimized` after endpoint
relaxation, `provided` when readable input results are adopted). A foreign chain
(e.g. an uploaded trajectory) carries no such marker and its readable values are
therefore recomputed under `auto` — this prevents stale/foreign endpoint energies
from poisoning the path profile (a known AutoNEB climbing-image phase crash root cause).

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
Slurm submission commands; use your site launch script to start the outer Python
MPI command, and keep all ABACUS executable details in `calculator.abacus`.

Image parallel 是可选能力；默认的单进程 NEB/AutoNEB 不导入 mpi4py。通过外部 MPI 启动前，先按用户指南完成 mpi4py import 与 two-rank launcher 预检；若 wheel 与站点 MPI 不兼容，应使用站点 `mpicc` 从源码重装 mpi4py。

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
| `record_events` | bool | `true` | Write a flushed JSONL sidecar beside the trajectory (`sella.events.jsonl` by default); false disables event recording. No extra energy/force evaluations. |
| `hessian_progress` | bool | `false` | Enable native Sella numerical-Hessian text progress, independently of JSONL recording. Explicit true requires runtime support. |

A Sella trajectory includes force-evaluation geometries, including finite-difference
probes; its frame count is **not** the optimizer step count. The event sidecar
records the initial state separately from completed optimizer steps, and links
observed numerical-Hessian probes to native zero-based trajectory IDs when
available. Unmapped frames remain unclassified. These hooks cover numerical
Hessian diagonalization, not every possible Hessian construction path or failed
force evaluation. Missing runtime capabilities are recorded explicitly.

Read-only trajectory summaries expose frame indices and actual optimizer steps
separately. Missing, truncated, or mismatched sidecars do not establish convergence
or a complete frame mapping. Geometry-only restart begins a new event sequence;
it does not restore optimizer state. Recording can be disabled with
`calculation.record_events: false`; older ATST runtimes reject these new keys,
so upgrade the runtime before setting them explicitly.


### 2.6 CCQN (Cone-Shaped Constrained Quasi-Newton)

PRFO evaluates the completed displacement against its previous quadratic model
(before the TS-BFGS Hessian update), then updates the trust radius before solving
the next step. This corrects the earlier one-step delay and use of the updated
Hessian in that comparison; existing radius thresholds are unchanged.
**Type**: `ccqn`

Reference: Wu, Y.; Wang, H. *Cone-Shaped Constrained Quasi-Newton Method:
Efficient and Robust Single-Ended Transition State Optimization Algorithm.*
J. Chem. Theory Comput. (2025). <https://doi.org/10.1021/acs.jctc.5c01015>

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Initial transition-state guess. |
| `e_vector_method` | string | `ic` | Cone-axis method: `ic` from reactive bonds or `interp` from a product-like structure. |
| `interp_direction` | string | `product` | `interp` cone-axis target: `product` (MIC displacement to `product_file`) or `midpoint` (centre frame of the fixed-budget IDPP path towards the product, eq. 18 of the CCQN paper; solver status and path quality are reported in `diagnostics_file`). |
| `reactive_bonds` | string/list | `None` | Required for `ic`; 1-based pairs such as `"1-2,3-4"` or `[[1, 2], [3, 4]]`. |
| `product_file` | string/null | `None` | Required for standalone `interp`; product-like structure with matching atom order. |
| `align_product_indices` | bool | `false` | Reorder `product_file` atom indices to match the initial structure before interpolation. |
| `auto_reactive_bonds` | dict | disabled | Enumerate ranked molecule-surface reactive bond candidates for `ic` mode. |
| `mode_manifest` | string | `ccqn_mode_manifest.json` | JSON manifest for enumerated and selected CCQN modes, including the effective current-structure bonds/elements, direction method/source, index base, and structure identity. |
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

CCQN is a single-ended transition-state optimizer. In `ic` mode, the user supplies chemically meaningful reactive bonds or enables `auto_reactive_bonds`. In `interp` mode the cone axis is built from `product_file`, and `interp_direction` selects the target: `product` uses the displacement from the current structure to the product configuration, while `midpoint` follows eq. 18 of the CCQN paper and points at the midpoint (`path[len(path) // 2]`) of an IDPP path generated between the current structure and the product (seven inner images, tolerance `0.05`). The path is re-solved from the current geometry at every uphill step, which costs seconds of pure geometry work per step for medium systems, so `product` remains the default. `accept_initial_converged` is intended for final-TS confirmation examples that start from a separately verified saddle point; keep it false for ordinary searches.

The mode manifest keeps the legacy v1 shape and adds audit facts without introducing required configuration: `effective_bonds` is 1-based in the consumed structure and `effective_elements` gives the endpoint symbols in the same order; `method` and `selection_source` identify the direction path; `structure_identity` records the configured `init_structure` when present, atom count, the ordered-symbol digest, and a digest of the initial positions, cell, and periodic-boundary flags. The legacy `selected_mode.reactive_bonds` remains an internal 0-based field and is labelled accordingly. These facts are also copied into the `metadata` object of `artifact_manifest` for summary consumers.

Midpoint semantics and the IDPP budget: `x_mid` is the centre frame of the IDPP path **as produced inside the solver's fixed iteration budget** (2000 iterations), not of a fully relaxed path. When the solver reports `Failed`, the path was truncated and `x_mid` is the centre frame of that truncated path. This is recorded as a fact and never upgraded into a hard failure: CCQN keeps stepping, and the first unconverged path of a run prints one English advisory (`stage=ccqn_interp_path`, with the observed and budgeted iteration counts). Per-step provenance for `midpoint` runs is written to `diagnostics_file`, where every uphill step carries `idpp_path_status` (`Converged`/`Failed`), `idpp_iterations`, `idpp_final_S_IDPP` and `idpp_max_force`; `product` and `ic` runs carry no `idpp_*` fields, so their diagnostics are unchanged.

Path quality (is the midpoint trustworthy?): a truncated path can also be **physically broken** — the interpolation may push atoms into each other, and the midpoint axis then points away from the reaction coordinate. Every `midpoint` solve therefore measures the tightest interatomic contact along the path (all frames, all atom pairs, minimum image convention) and grades it per atom pair against that same pair's smaller endpoint separation:

| Diagnostics field (uphill steps of `midpoint` runs only) | Meaning |
| :--- | :--- |
| `idpp_path_min_distance` | Smallest interatomic distance on any frame, in Angstrom. |
| `idpp_path_min_distance_pair` | The pair reaching it, as 1-based `"i-j"`. |
| `idpp_path_min_distance_ratio` | Worst compression: the smallest, over all frames and pairs, of `d(pair, frame) / min(d(pair, start), d(pair, end))`. |
| `idpp_path_min_distance_ratio_pair` | The pair responsible for that worst compression, as 1-based `"i-j"`. |

`idpp_path_min_distance_ratio < 0.5` marks the path as **not physical**: some pair is squeezed to less than half of its separation in either endpoint, which a pure interpolation of a physical path does not do. The comparison is deliberately per pair rather than against the global endpoint minimum, because the tightest bond of a system (for example a 1 Angstrom X-H bond) would otherwise mask a collapsed metal-metal contact. The first unphysical path of a run prints one English advisory (`stage=ccqn_interp_path`, with the observed distance, the offending pair, its endpoint separation and the ratio threshold); the run continues. When that flag appears, the `midpoint` axis is **not trustworthy**: cross-check the direction with `interp_direction: product` or validate the path with IRC/NEB before drawing conclusions from the trajectory.

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

Example interpolation mode with the paper eq. 18 midpoint axis:

```yaml
calculation:
  type: ccqn
  init_structure: inputs/ts_guess.traj
  e_vector_method: interp
  interp_direction: midpoint
  product_file: inputs/product.traj
  align_product_indices: true
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

### 2.11 Constant-Potential Evaluation (development candidate)
**Type**: `constant_potential`

`constant_potential` is an unreleased ABACUS-only development candidate. It
evaluates one fixed structure at one target or scans an ordered list of targets
serially. The electronic-number loop is supplied by the
`calculator.constant_potential` decorator; target units and boundary-specific
fields are documented in [§3.1a](#31a-constant-potential-decorator).

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `type` | string | **Required** | Must be `constant_potential`. |
| `init_structure` | string | **Required** | Structure read for every fixed-geometry target. |
| `directory` | string | `constant_potential_run` | Root for per-target calculator evaluations and the final trajectory. |
| `results_file` | string | `constant_potential_results.json` | JSON result envelope containing status, target points, analysis, and calculator identity. |
| `log_file` | string | `constant_potential.log` | Tabular per-target log; compensated-gate residuals are in eV. |
| `checkpoint_file` | string | `constant_potential_checkpoint.json` | Atomic completed-point checkpoint used by `restart: true`. |
| `artifact_manifest` | string | `atst_artifacts.json` | Manifest for results, log, checkpoint, input/final structures, and point artifacts. |
| `restart` | bool | `false` | Resume only when target order, structure, CP settings, and fixed ABACUS asset contents match exactly. |

The target itself belongs in `calculator.constant_potential`: use exactly one
scalar (`potential_v` or `target_mu_ev`) for a single evaluation, or one
non-empty list (`potentials_v` or `target_mu_values_ev`) for a serial scan.
Duplicate and non-finite targets are rejected. The scan carries the previous
point's electron count only as the next initial guess; every point still writes
its own SCF/CP identity and result.

`reference_fcp` is retained for reproducing the frozen vacuum/work-reference
algorithm and is marked reference-only. It may be used by this fixed-geometry
workflow for algorithm comparison, but it is rejected for `relax` and `neb`.
The `compensated_gate` boundary consumes the same-run gate/dipole density terms,
uses a custom target chemical potential, and is the only CP boundary accepted by
fixed-cell `relax` and ordinary `neb`. Those optimization workflows require one
scalar target and do not support a target list, cell relaxation, or CP stress.

For CP `relax` and `neb`, restart reads the last complete trajectory frame or
band. Each restarted calculator uses the corresponding frame's last evaluated
electron count only after validating its persisted CP facts, geometry, target,
fixed Hamiltonian, and current residual tolerance. Missing or mismatched facts
fail closed for the relaxation frame and NEB interior images. The configured
NEB endpoint policy still governs endpoint recomputation. This resumes from a
completed electronic evaluation; it does not resume a partially completed SCF
or restore the optimizer's Hessian, velocities, or electronic fitting history.
Each new evaluation gets a fresh directory, preserving earlier SCF evidence.

On success, the workflow writes `constant_potential_results.json`,
`constant_potential.log`, `constant_potential_checkpoint.json`,
`constant_potential_run/point_####_<target>/result.json`,
`constant_potential_run/final_structure.traj`, and `atst_artifacts.json` (with
the configured output names substituted). A failed target leaves previously
completed points in the result/checkpoint artifacts and writes a failed
manifest; the run remains failed and no incomplete energy/force state is
published for optimization.

The factory rejects CP for `autoneb`, `dimer`, `sella`, `ccqn`, `d2s`,
`vibration`, `irc`, `md`, and `dmf`. This candidate also rejects explicit
`nupdown` (including `0`) and `two_fermi`; supported profiles use one common
Fermi level. No claim of Paimon/public tool-chain acceptance or package release
is made by this section.

---

## 3. Calculator Section

The `calculator` section configures the underlying compute engine (DFT or ML Potential).

### 3.1 ABACUS (DFT)
**Name**: `abacus`
> **Note**: For backward compatibility, parameters can also be placed under an `abacus` root key instead of `calculator.abacus`.
> For GPU LCAO calculations, choose a site-compatible GPU solver according to
> the documentation for the installed ABACUS version.
> ATST-Tools imports an independently installed `abacuslite` package first and falls back to the vendored `src/atst_tools/external/ASE_interface/abacuslite` snapshot if that import is unavailable.

For `calculation: scf`, abacuslite automatically identifies the latest running
log frame corresponding to the current STRU, accepting periodic-equivalent
coordinates (including valid cross-cell movement) in the existing cell. It
still rejects different structures, cells, atom counts/orders, malformed or
non-finite data, and singular cells. Native `relax`, `md`, and `MD_dump` keep
their existing last-frame behavior. This is automatic and adds no YAML
configuration field or user-selectable tolerance.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `command` | string | `abacus` | Command to execute ABACUS (e.g., `mpirun -np 4 abacus`). |
| `mpi` | int | `1` | Number of MPI processes (deprecated, use `command` to specify mpirun). |
| `omp` | int | unset | Number of OpenMP threads per process. The schema leaves it unset: an omitted key keeps a `runtime.threads` budget, while runs without any runtime request keep the historical default of 1. |
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

`pseudopotentials`, `basissets`, `pseudo_dir`, and `orbital_dir` are ABACUS
top-level fields, not `parameters` entries. `atst prepare` (reverse
configuration generation from a completed ABACUS run directory) resolves
`pseudo_dir`/`orbital_dir` and the STRU-derived
`pseudopotentials`/`basissets` into these top-level fields, and the active
`abacuslite` writer injects them into the generated `INPUT` accordingly. Only
`pseudo_dir`/`orbital_dir` have a schema default (`.`); `pseudopotentials` and
`basissets` are required.

### 3.1a Constant-Potential Decorator
**Path**: `calculator.constant_potential`

The decorator is valid only when `calculator.name: abacus`. Its fields are
strictly schema-governed; unknown keys, non-finite numbers, blank provenance,
duplicate targets, and invalid boundary combinations are rejected before an
ABACUS run starts. `reference_electrons` is the explicit model-zero-charge
count (`N0`) and is required for every boundary. It is never inferred from the
prepared input or silently reused as the first SCF guess. Set the prepared
`calculator.abacus.parameters.nelec` explicitly for that initial guess (the
factory keeps the two values separate).

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `energy_boundary` | string | **Required** | `reference_fcp` for the frozen vacuum/work-reference algorithm, or `compensated_gate` for the explicit gate/dipole boundary. |
| `reference_electrons` | float | **Required** | Model-zero-charge electron count `N0`; finite and non-negative. |
| `potential_v` | float | `null` | One target electrode potential in V; reference boundary only and mutually exclusive with `potentials_v`. |
| `potentials_v` | list[float] | `null` | Ordered non-empty voltage scan in V; reference boundary only. |
| `target_mu_ev` | float | `null` | One custom conjugate chemical-potential target in eV; compensated boundary only and mutually exclusive with `target_mu_values_ev`. |
| `target_mu_values_ev` | list[float] | `null` | Ordered non-empty custom chemical-potential scan in eV; compensated boundary only. |
| `reference_electrode` | string | `SHE` | Named reference for `reference_fcp`; must be `custom` for `compensated_gate`. This label does not calibrate a compensated target to SHE/RHE. |
| `work_ref` | float | `null` | Explicit reference-electrode work function in eV; required for `reference_fcp`. `work_ref_eV` is an accepted input alias. |
| `work_ref_source` | string | `null` | Required provenance for `work_ref` under `reference_fcp`. |
| `reference_pH` | float | `null` | RHE pH; only valid when `reference_electrode: RHE`. |
| `temperature_K` | float | `null` | Positive temperature for RHE conversion; required with `reference_pH` for RHE. |
| `potential_tolerance_v` | float | `0.01` | Positive absolute residual tolerance. Under `compensated_gate`, the numerical residual is `residual_mu_eV` in eV; the historical field name is retained for schema compatibility. |
| `max_iterations` | int | `100` | Maximum fresh ABACUS evaluations per target. |
| `capacitance_initial` | float | `0.0125` | Positive initial capacitance in `capacitance_unit`. |
| `capacitance_unit` | string | `e/(V Angstrom^2)` | `e/V` for total capacitance or `e/(V Angstrom^2)` for per-area updates. |
| `nelec_min` | float | `null` | Optional lower bound for a candidate electron count. |
| `nelec_max` | float | `null` | Optional upper bound for a candidate electron count. |
| `nelec_step_max` | float | `null` | Optional positive maximum absolute Newton update in electrons. |
| `vacuum_axis` | int | `2` | Cell axis index (`0`, `1`, or `2`) used by surface/density analysis. |
| `interface_count` | int | `1` | Area normalization for scan analysis: one or two interfaces. |

For `reference_fcp`, exactly one of `potential_v`/`potentials_v` is required,
and `work_ref` plus `work_ref_source` are required. An RHE reference also needs
both `reference_pH` and `temperature_K`; those fields are rejected for SHE or
other named references. The runtime records a finite vacuum level and its
fermishift from the current backend output; it does not consume a stale log
from an earlier evaluation.

For `compensated_gate`, exactly one of `target_mu_ev`/`target_mu_values_ev` is
required, `reference_electrode` must be `custom`, and voltage/work-reference/RHE
fields are invalid. Gate, blocking, field, dipole, and sawtooth settings remain
ABACUS `INPUT` parameters under `calculator.abacus.parameters`; they are not
duplicated in the CP block. Keep those actual settings fixed across a scan or
optimization. ATST requests high-precision charge output (`out_chg: "1 12"`)
for the inner compensated evaluations and validates the density integral,
gate/dipole derivatives, and compensation identity from the same run. The
compensated profile requires a usable vacuum/field geometry and fixed cell;
implicit solvent, cell filters, and stress are outside this candidate scope.

Common-Fermi occupation is required. Explicit `nupdown` is rejected even when
its value is `0`, and `two_fermi` is rejected. The first fixed-electron guess
comes from the prepared ABACUS `nelec`; `N0` remains the separately declared
reference used in `delta_nelec` and `Omega` accounting.

The scan analysis uses the target coordinate recorded in the result. For
`reference_fcp`, it reports the historical voltage response (`dQ/dU`). For
`compensated_gate`, it reports the positive electronic response `dN/dmu`, with
units `e^2/(eV Angstrom^2)` (or `e^2/eV` for total capacitance), and names the
zero-charge crossing `zero_charge_mu_ev`. It does not call that custom
chemical-potential crossing an experimentally calibrated PZC. Fewer than two
identifiable points, a non-bracketed crossing, or a non-finite/degenerate fit
leaves the corresponding analysis field unavailable.

Successful CP results also persist a validated facts envelope in ASE
`Atoms.info` for trajectory, relax, and NEB consumers. The envelope contains a
geometry fingerprint, the complete CP boundary, finite energy/force/electron/
residual facts, SCF and CP convergence markers, and fixed-Hamiltonian asset
identity (PP/ORB/KPT content hashes). Consumers reject missing, stale,
non-finite, geometrically changed, boundary-changed, or asset-changed facts;
moving an unchanged asset file is allowed because content hashes, not paths,
define the physical identity. Reference-fcp facts remain reference-only and
must not be used to claim optimization energy/force consistency.

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

## 4. Runtime Section

`runtime` is optional. Without it, `atst run` keeps the legacy in-process
behavior and writes no additional files. Any runtime request (a `runtime`
section, a runtime CLI option, or `ATST_VISIBLE_DEVICES`) switches the run to
the isolated worker path: devices and thread budgets are applied before the
scientific stack is imported, and telemetry writes `runtime_evidence.json`
next to the artifact manifest.

DP 后端与制品（2026-09-22）：ATST 按制品后缀判定类型并存证——`.pt` 原始 checkpoint（推荐）、
`.pth` 冻结归档（TorchScript，**与导出时的 deepmd-kit 构建锁定**）、`.pb`/`.pbtxt` TF 图（kind 级）。
多任务（multi-task）PT 模型**必须**给 `head`：缺失或名称错误会抛 `DeepPotentialError`，
消息列出可用 heads 并给出 `dp --pt show <model> model-branch`（`dp --pt freeze -c <ckpt> -o out [--head <branch>]`
是 PT 出品 `.pth` 的入口）。冻结归档若与当前构建算子不匹配，首次求值即被翻译为可操作错误
（建议改用原始 `.pt` 或与归档匹配的构建）；`CUDA out of memory` 等真实错误原样上抛。
线程预算：`runtime.threads` 同时写 `OMP_NUM_THREADS` 与 deepmd 自荐的
`DP_INTRA_OP_PARALLELISM_THREADS`/`DP_INTER_OP_PARALLELISM_THREADS`；`calculator.dp.omp` 只设 OMP（既有语义不变）。
`dp_model_identity()` 可回读 kind/backend/head/ntypes/rcut/type_map 等事实（会加载模型元数据，约数秒，不在默认运行路径调用）。

```yaml
runtime:
  devices: [0]        # 0-based indices inside the inherited visible set, or full GPU UUIDs
  binding: inherit    # inherit | round_robin
  threads: auto       # positive integer, or "auto" to follow the CPU affinity mask
  telemetry:          # boolean shorthand, or {enabled: true, interval_s: 1.0}
    enabled: false
    interval_s: 1.0
```

Semantics:

- `devices` is a request, never a way to widen the visible set. It is resolved
  against `CUDA_VISIBLE_DEVICES` (the caller's binding) together with the
  trusted allocation facts in `ATST_ALLOCATION_DEVICES` (`count=N` or a token
  list). Explicit selection is refused when the whole node is visible and no
  trusted allocation is available; MIG device selection is not supported.
- `binding` defaults to `inherit`. `round_robin` maps `local_rank` onto the
  resolved device pool and fails closed for multi-node launcher shapes,
  unknown local ranks, or pools that are not caller-bound.
- `threads` is applied to the worker environment before the scientific stack
  is imported (`OMP_NUM_THREADS` and its BLAS siblings). Only a `omp` the user
  actually wrote counts as explicit, so a `calculator.abacus` block without that
  key keeps the runtime budget; an explicit value still wins and its override of
  the runtime budget is recorded as the `runtime_threads_overridden` counter and
  the `runtime_threads_effective` gauge in the evidence document (plus an English
  warning). Runs without any runtime request keep the historical behaviour,
  including the default thread value of 1.
- `telemetry` enables `runtime_evidence.json`: the environment triple, device
  facts, per-process counters (`dp.*`, `abacus.*` builds and force calls) and
  host GPU samples taken by a single sampler on rank 0, including a sampled
  memory peak (`telemetry.sampler.memory_peak_mib`, marked `sampled_peak`).
  Successful MPI runs also sum the canonical counters across ranks
  (`counters_mpi`). Missing tools or permissions degrade to `unavailable`;
  measurement never masks a workflow result.

## 5. Configuration Maintenance

Installed-package schemas reject unknown `calculation`, strict CP, and DP
calculator fields. ABACUS INPUT variables belong under
`calculator.abacus.parameters`, which is intentionally pass-through; the CP
decorator itself remains strict. Maintainers changing schema fields or
generated parameter documentation should follow the
[developer handover](../developer/HANDOVER.md).

## 6. Example Configuration

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

For the unreleased constant-potential candidate, keep the gate/dipole settings
in the ABACUS block and declare the CP boundary separately. This is a schema
shape example; derive the target chemical potential and geometry-specific gate
positions for the actual input:

```yaml
calculation:
  type: constant_potential
  init_structure: inputs/STRU
  directory: constant_potential_run
  results_file: constant_potential_results.json
  log_file: constant_potential.log
  checkpoint_file: constant_potential_checkpoint.json

calculator:
  name: abacus
  abacus:
    command: abacus
    directory: abacus_base
    kpts: [1, 1, 1]
    pseudo_dir: ../data
    orbital_dir: ../data
    pseudopotentials:
      Pt: Pt_ONCV_PBE-1.0.upf
    basissets:
      Pt: Pt_gga_6au_100Ry_2s1p.orb
    parameters:
      calculation: scf
      basis_type: lcao
      nspin: 1                 # common-Fermi profile
      nelec: 216.9             # initial guess; it is not N0
      efield_flag: 1
      dip_cor_flag: 1
      efield_amp: 0.0
      efield_dir: 0            # choose the actual vacuum/field axis
      gate_flag: 1
      zgate: 0.7
      efield_pos_max: 0.8      # fixed dipole position
      efield_pos_dec: 0.1      # fixed dipole width
      out_pot: 2
      cal_force: 1
      out_chg: "1 12"          # also enforced for compensated evaluations
    constant_potential:
      energy_boundary: compensated_gate
      reference_electrode: custom
      target_mu_ev: 15.0        # derive for this boundary and input
      reference_electrons: 216.0
      potential_tolerance_v: 1.0e-6
      max_iterations: 100
      capacitance_initial: 0.0125
      capacitance_unit: e/(V Angstrom^2)
```

The fixture-specific `zgate`, axis, blocking interval, pseudopotential
valence, target, and `reference_electrons` in this example are illustrative;
they must agree with the actual `INPUT`/`STRU`/PP files. For a compensated
profile, changing any fixed gate/dipole setting changes the Hamiltonian
identity and invalidates old checkpoints or persisted endpoint facts. See
[`examples/19_constant_potential_Pt/README.md`](../../examples/19_constant_potential_Pt/README.md)
for the bounded Pt fixture and its scientific limitations.
