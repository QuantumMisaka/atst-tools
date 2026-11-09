# Stable Python API Reference

**Audience:** Python users embedding ATST-Tools in another program.

**Lifecycle:** reference — maintained with each public API release.

**Purpose:** stable imports, execution boundaries, and result ownership for the
`atst_tools.api` integration surface.

ATST-Tools supports two equivalent ways to run schema-backed workflows:

- Use the CLI and YAML for interactive, scripted, and scheduled calculations.
- Use this API when another Python program needs validation, structured results,
  or the ATST-specific embedded CCQN calculation.

Both routes use the same YAML schema and workflow services. The CLI remains the
terminal adapter; the API does not replace the CLI, YAML examples, a scheduler,
or a calculator runtime. For command syntax, see the maintained
[CLI reference](CLI_REFERENCE.md). For project installation, examples, and
source, see the [repository README](../../README.md) and the
[ATST-Tools repository](https://github.com/QuantumMisaka/atst-tools).
This reference describes the [2.3.3 API](../releases/RELEASE_NOTES_2.3.3.md).
Additions since 2.2.0
(progress events, plotting helpers, and the profiles/plots result extensions)
are marked "(2.2.1)".

## Installation

ATST-Tools requires Python 3.10 or later:

```bash
pip install atst-tools
pip install "atst-tools[parallel]"  # only for externally launched image-parallel NEB/AutoNEB; serial use does not install mpi4py
```

For image-parallel execution, the external host owns a `mpi4py` installation
that matches its MPI launcher; serial API use does not need `mpi4py`.

The package installs the workflow layer, not a universal calculation backend.
Install and configure the ASE calculator runtime required by your calculation.
For configuration-driven ABACUS work, that includes the normal executable,
pseudopotential, orbital, and site runtime setup. The embedded CCQN API accepts
an already-created ASE calculator, so its configuration remains the caller's
responsibility.

## Stable imports

The stable root imports in the current 2.3.3 release are:

```python
from atst_tools.api import (
    CCQNOptions,
    RunOptions,
    WorkflowResult,
    validate_ts,
    build_config_from_abacus_dir,
    ccqn_energy_curve,
    neb_energy_profile,
    run_ccqn,
    run_workflow,
    sella_energy_curve,
    validate_config,
    RuntimeBindingError,
)
```

Workflow, calculator, MEP, and historical compatibility paths are not stable
integration surfaces. Do not couple an application to their constructors or
helper functions; use the names above instead. `validate_ts` was added in
2.2.9 and is a stable lazy root import in 2.3.1. `RuntimeBindingError` is raised
when a runtime device-binding request is inadmissible.

### `build_config_from_abacus_dir(abacus_run_dir, *, workflow="neb", init_structure=None, final_structure=None, n_images=5, gate_dirs=None)`

Read an existing ABACUS run directory and return a calculator/calculation
configuration mapping. This helper prepares configuration only; it does not
launch ABACUS or write a YAML file. The current implementation supports
`workflow="neb"` only and rejects other workflow names.

It reads `INPUT` and `STRU`, derives K points from `gamma_only`, `kspacing`,
or `KPT`, and rejects line-mode K points for force evaluation. Calculator
parameters are inherited with `calculation="scf"` and `cal_force=1`;
`pseudo_dir` and `orbital_dir` are resolved relative to the source directory.
`cal_stress` is not forcibly overwritten. LCAO structures need orbital filenames.
When supplied, `gate_dirs` requires parseable energy and forces in each endpoint
directory. Missing source directories raise `FileNotFoundError`; explicit
input checks raise `ValueError`. Underlying parser exceptions are propagated.

```python
from atst_tools.api import build_config_from_abacus_dir, validate_config

config = build_config_from_abacus_dir(
    "relaxed_initial",
    final_structure="relaxed_product/STRU",
    gate_dirs=["relaxed_initial", "relaxed_product"],
)
config = validate_config(config)
```

The default NEB configuration is image-parallel; callers choose runtime resources
and may adjust the mapping before validation/execution. Both endpoint structures
default to the source `STRU`, so a reaction calculation needs an explicit product.
This root export is the supported integration entry; the helpers under
`atst_tools.utils.reverse_config` remain implementation details.

### `validate_config(config_source)`

Accepts either a YAML path or a mapping and returns a detached, normalized
configuration dictionary using the installed ATST schema and defaults. It does
not mutate a supplied mapping. Schema, YAML, and configuration-path I/O errors
are raised as `ConfigValidationError` with the original exception preserved as
its cause.

```python
from atst_tools.api import validate_config

config = validate_config(
    {
        "calculation": {"type": "relax", "init_structure": "x.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }
)
print(config["calculation"]["type"])
```

### `run_workflow(config_source, options=RunOptions())`

Runs a validated YAML path or equivalent mapping and returns a
`WorkflowResult`. It supports every current `calculation.type`: the released
NEB, AutoNEB, Dimer, Sella, CCQN, D2S, Relax, Vibration, IRC, MD, and
experimental DMF workflows, plus ABACUS-only `constant_potential` evaluations.
`RunOptions` exposes the CLI-equivalent controls:

- `dry_run`, `restart`, `check_input`, and `check_input_timeout` select the
  same workflow/preflight behaviors as the command path. `check_input=True`
  requires `dry_run=True`; otherwise the API raises `ConfigValidationError`
  before it constructs a communicator or dispatches a workflow.
- `abacus_executable` overrides the executable used only for ABACUS
  check-input preflight.
- `world` accepts an existing communicator for embedding. It is not a
  scheduler or launcher interface.
- `progress` (2.2.1) enables structured NDJSON progress events. With
  `progress_stream` (a writable text stream; standard output by default) the
  driver writes one JSON line per event (`workflow_start`, then one
  `image_step` per NEB/AutoNEB band image with `workflow`, `image`,
  `energy_eV`, `step`, and `ts` fields); the same event mapping is forwarded
  to `progress_callback` when supplied, so Python consumers never parse
  stdout. The CLI `--progress` flag and this option share the same driver
  emission. In image-parallel workflows, a stream or callback failure on one
  rank is synchronized so every rank exits with an API workflow failure
  instead of leaving peers blocked in a later collective.
- `profiles` (2.2.1) adds an opt-in per-image (NEB/AutoNEB) or per-step
  (Sella/CCQN) energy and force summary to the result envelope. `plots`
  (2.2.1) renders the workflow energy plot PNG and records its relative path
  in the result document and artifact manifest. Both extensions are
  best-effort: a missing optional dependency or unreadable input omits them
  rather than failing a completed workflow, and they never alter the
  established result fields.

```python
from atst_tools.api import RunOptions, run_workflow

result = run_workflow("config.yaml", RunOptions(dry_run=True))
print(result.status, result.artifact_manifest)
```

The `calculator.constant_potential` mapping uses the same `run_workflow` route
and strict schema as the CLI; it does not add a new stable root import. It
supports fixed-geometry serial evaluations/scans and fixed-cell
`compensated_gate` `relax`/serial `neb` calls. Fixed-cell ASE MD also uses
`calculation.type: md` with this decorator and one scalar `target_mu_ev`.
CP MD is supported since 2.3.2; real-backend validation covers short trajectories.
`reference_fcp` remains limited to fixed-geometry evaluations. CP MD writes a
per-step checkpoint and diagnostics under `calculation.directory`; a restart
adds the requested `steps` to the saved global step. See the
[CP configuration reference](CONFIG_REFERENCE.md#211-constant-potential-evaluation)
for target units, energy definitions and restart requirements.

### Process runner for external hosts

An external host that needs a process boundary, stable exit status, and a
machine-readable handoff can use the installed runner. It is not a
separate stable root import and it does not replace the `atst` CLI:

```bash
python -m atst_tools.api.runner \
  --config config.yaml \
  --workdir run_sella \
  --result-json atst_api_result.json
```

The runner accepts the same configuration-driven controls as `RunOptions`:
`--config`, `--workdir`, `--result-json`, `--dry-run`, `--restart`,
`--check-input`, `--check-input-timeout`, `--abacus-executable`, and
`--progress`; the 2.2.1 result extensions are enabled with `--profiles` and
`--plots`.
`--config` is resolved against the caller directory before the runner enters
`--workdir`; relative paths inside the YAML continue to use the runner work
directory, matching the configuration-driven API's CWD semantics.
`--result-json` is relative to `--workdir` unless an absolute path is supplied.
The runner enters `--workdir` only for its own process and restores its caller
directory before returning.

On success, root rank atomically replaces the requested result file with an
`atst-api-result-v1` JSON document. It contains `schema`, `status`, `workflow`,
`is_root`, `workdir`, `artifact_manifest`, `artifacts`, and `metadata`. The
`artifact_manifest` value is absolute; the manifest remains the durable
scientific artifact authority, while the JSON file is an external-host handoff.
On an `ATSTAPIError`, root rank instead writes `status: "error"` with a typed
error document. Exit code `0` means success, `2` means a public ATST API error,
and `1` means an unexpected runner failure.

For externally launched image-parallel NEB or AutoNEB, every rank runs the same
command, but only root rank publishes or replaces the JSON file. The runner
never starts Slurm or an outer `mpirun`/`srun` launch: scheduler, launcher, resource
allocation, and rank topology remain the caller's responsibility. A configured
calculator command may launch ABACUS MPI inside each workflow process.

### `run_ccqn(atoms, calculator, options=CCQNOptions())`

Runs ATST's CCQN single-ended transition-state search with caller-provided ASE
`Atoms` and calculator objects. `CCQNOptions` mirrors the CCQN schema controls:
`fmax`, `max_steps`, `trajectory`, `logfile`, `final_structure`,
`e_vector_method`, `interp_direction`, `reactive_bonds`, `auto_reactive_bonds`, `product_atoms`,
`mode_manifest`, `diagnostics_file`, `ic_mode`, `cos_phi`,
`trust_radius_uphill`, `trust_radius_saddle_initial`, `hessian`,
`accept_initial_converged`, and `artifact_manifest`.

Automatic reactive modes are enabled by supplying an
`auto_reactive_bonds` mapping, for example
`{"enabled": True, "cutoff_A": 3.5, "max_modes": 8}`. See the executable
[H2/Au automatic-mode example](../../examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py).

For production ABACUS CCQN injection, the caller must supply a caller-created,
correctly configured `abacuslite` ASE calculator. The caller's normal ABACUS
pseudopotential, orbital, executable/runtime, and site setup must already be
ready; ATST does not configure it. ATST-Tools does not install or require
ABACUS as a package dependency for this API.

### Plotting helpers

The plotting helpers (2.2.1) render transition-state visualization PNGs with the
headless matplotlib Agg backend and return the written path. matplotlib is an
optional dependency (`pip install "atst-tools[plot]"`); when it is missing
these helpers raise a clear `ImportError` and the CLI reports the same message
with exit code 1. Importing `atst_tools.api` never requires matplotlib.

```python
from atst_tools.api import neb_energy_profile, sella_energy_curve, ccqn_energy_curve

profile = neb_energy_profile(chain, "neb_profile.png")    # E vs image + barrier
curve = sella_energy_curve("run_sella.traj", "sella.png")  # E vs step
curve = ccqn_energy_curve("ccqn.traj", "ccqn.png")         # E vs step
```

`neb_energy_profile(chain, output_png, *, title=None, barrier=True, dpi=300)`
plots the band energies relative to the first image and annotates the maximum
relative-energy image with its barrier value (disable with `barrier=False`).
`sella_energy_curve(traj, output_png, *, title=None, dpi=300)` and
`ccqn_energy_curve(traj, output_png, *, title=None, dpi=300)` consume the
per-step energies directly from the trajectory frames (frame index == step).
Trajectory energies are read from frozen calculator results or
`atoms.info["energy"]`, never by launching new calculations.

The equivalent command-line entry is `python -m atst_tools.utils.plot`, a thin
adapter over the same functions:

```bash
python -m atst_tools.utils.plot neb --chain chain.traj --output-png neb_profile.png
python -m atst_tools.utils.plot sella --traj run_sella.traj --output-png sella.png
python -m atst_tools.utils.plot ccqn --traj ccqn.traj --output-png ccqn.png
```

The CLI flags map one-to-one onto the API parameters (`--chain`, `--traj`,
`--output-png`, `--title`, `--dpi`, `--no-barrier`), and each invocation writes
the same figure the corresponding Python call would produce.

## Results and artifacts

`WorkflowResult` is a frozen container with `workflow`, `status`, `is_root`,
`artifact_manifest`, `artifacts`, `metadata`, `final_atoms`, `final_images`,
`ts_atoms`, the 2.2.1 optional `plots` and `profiles` fields, and the optional
`runtime` summary described below. The artifact
manifest is the durable, restart-safe record for the Python API; `artifacts`
is its structured output list and
`metadata` includes the backend provenance. After a successful API run, a stale
or unreadable pre-existing manifest is replaced with a synthesized completion
manifest, while a valid manifest written by that run is preserved. The CLI
adapter deliberately does not synthesize or replace manifests for legacy
workflows that did not write them themselves.

Path fix (2026-10-16): artifact paths remain relative to the run
workdir. When the manifest is stored elsewhere, including an absolute output
location, it records an optional top-level `path_base`: the relative path from
the manifest directory to that workdir. Manifest consumers resolve relative
artifact paths against `manifest.parent / path_base`; absolute artifact paths
are unchanged. Root-directory manifests omit the redundant `.` base. API
enrichment preserves the base, and the JSON envelope continues to provide its
absolute `workdir` and `artifact_manifest` without changing artifact strings.
Manifests without `path_base` keep the legacy manifest-directory interpretation.
An old nested manifest whose paths actually referred to a different workdir
must be given the correct base explicitly; consumers do not search for a
similarly named existing file. Older consumers must support `path_base` before
reading the new nested layout; the default root layout is unchanged.

`plots` is a tuple of rendered energy-plot PNG paths and `profiles` a tuple of
per-image (NEB/AutoNEB) or per-step (Sella/CCQN) energy/force summaries; both
are populated only when the corresponding `RunOptions` flag was set. In the
JSON handoff, they appear as optional `plots` and `profiles` keys only when
non-empty, so `atst-api-result-v1` documents produced without those options
stay byte-identical to the original schema.

`runtime` appears only for runs that requested runtime controls (`runtime`
YAML section, runtime CLI options, or `ATST_VISIBLE_DEVICES`). It carries the
compact summary `status`, `evidence` (the relative `runtime_evidence.json`
path), `attempt`, and `devices` (requested/inherited/effective plus the
allocation identity); the sidecar remains the detailed record. Runs without
runtime requests keep producing documents without that key.

The container is immutable, but ASE objects are mutable. `final_atoms`,
`final_images`, and `ts_atoms` are caller-owned snapshots: modifying one does
not modify ATST's internal workflow state. For image-parallel NEB and AutoNEB,
only the root rank receives in-memory `final_images` and `ts_atoms`; all ranks
receive status, metadata, and durable artifact paths.

`final_atoms` is populated only with an ASE `Atoms` snapshot. In particular, a
completed Relax run recovers its `final_relaxed.traj` result when the legacy
runner returns no value, while summary mappings such as the experimental DMF
result remain represented by output artifacts rather than `final_atoms`.

### Workflow stage records

The artifact manifest remains the durable authority for convergence facts. The
result document exposes `artifact_manifest` (an absolute path) together with
`artifacts` and `metadata`, and it deliberately does not copy `converged`
values: a consumer that needs a convergence answer reads the manifest's
`stages` list, or a summary built from the same file. The
`atst-api-result-v1` handoff document stays a bounded execution envelope.

Every entry of `stages` is one workflow stage and follows the same key
contract:

- `name`, `status` and `converged` are always present.
- Manifests written before 2.2.6 do not follow this contract: their stage
  records may omit `converged` (or carry no `stages` at all). A missing value
  means unknown, never "false" and never success; consumers must handle that
  legacy shape instead of assuming the key exists.
- `role`, `criterion`, `direction`, `iteration`, `subset`, `fmax`,
  `fmax_unit`, `steps`, `actual_steps`, `measured` and `measured_unit` are
  written only when the stage actually carries that fact. An absent optional
  key means "not applicable or not observed", never a zero or an invented
  default; `fmax_unit` is omitted whenever no threshold was recorded.
- `converged` is strictly `true`, `false` or `null`. `null` means unknown: the
  stage did not run, or its optimizer never reported a termination signal. The
  value is never truthiness-converted, so a consumer compares with `is True`
  and `is False` instead of testing the field directly.
- `status` describes execution only (`complete`, `skipped` or `failed`).
  `status: "complete"` means the stage ran to its end; it never means the stage
  converged, which only `converged` answers.

Workflow-level semantics of the records:

- One workflow owns exactly one top-level manifest. D2S aggregates its
  endpoint, rough-path, single-ended refinement and vibration stages into its
  own D2S manifest, and AutoNEB aggregates its per-iteration records; nested
  constituent workflows do not write a second top-level manifest.
- AutoNEB optimizes one window of the band per iteration, so each iteration
  record carries its image `subset`. The final `autoneb` record reuses the last
  executed iteration's scope and never claims whole-band convergence.
- IRC writes one record per executed direction (`forward`, `reverse`, or both),
  each with its own convergence signal and per-direction step count.
- **Since 2.2.9:** a standalone Dimer run
  records the optimizer's returned convergence signal
  and observed step count in its manifest. D2S records the same facts for its
  Dimer single-ended stage. A missing optimizer signal remains `null`; execution
  completion alone never implies convergence.

When an API run completes without a runner-written manifest, ATST synthesizes a
completion manifest whose single stage is the workflow name with
`status: "complete"` and `converged: null`: execution is complete, while the
convergence signal stayed outside the API's knowledge. Such a stage is an
execution record, not a convergence claim.

Single-stage workflows (`relax`, `sella`, `ccqn`) are serial-only. ATST does not
thread a communicator into them, and a multi-rank launch is not a supported
topology for those three calculations: the per-stage advisory may then repeat
once per rank, so launch them as a single process.

## Paths, MPI, and backends

Relative paths retain the calling process's current working directory
semantics, including ABACUS `check_input` preflight for a YAML path. The API
never changes directory to a YAML file's parent. Use absolute paths or
establish the desired current working directory before a call. This is
deliberately distinct from the legacy CLI adapter, whose `atst run --dry-run
--check-input config.yaml` continues to resolve relative preflight inputs from
the YAML file's parent.

The API never allocates resources or starts Slurm, `mpirun`, or `srun`. Start
the outer Python MPI launch yourself, then have every rank call the same API with
the same configuration. A calculator command configured in YAML may launch its
own ABACUS MPI subprocess; ATST does not start the outer image-parallel Python
launch. NEB requires one rank per interior image and AutoNEB one rank per
simultaneous image; existing serial fallback behavior is preserved.

Backend delegation has four invariants:

1. Configuration-driven ABACUS runs always use the installed `abacuslite`
   package; a missing or broken installation fails instead of selecting a
   bundled fallback.
2. `run_ccqn()` attaches the provided ASE calculator to a private atoms copy;
   it never rebuilds or reconfigures the calculator profile, command,
   pseudopotentials, orbitals, working directory, MPI settings, or I/O.
3. ATST does not re-export individual backend I/O functions. It remains the
   workflow, schema, artifact, and orchestration layer.
4. Configuration-driven ABACUS runs record `backend_source: external`. The
   top-level manifest `backend_identity` object (introduced in 2.2.9) has
   `calculator` (`abacus`, `dp`, or `supplied`), `identity_basis`
   (`configuration` or `calculator_instance`), `source` (`external`, `deepmd`,
   `caller`, or `unknown`), `calculator_type`, `backend_version`, `snapshot`,
   and `model`. In 2.3.1 `snapshot` is always `"unknown"` because the vendored
   provenance fields were retired. DP model facts can include absolute `path`,
   suffix-derived `kind`, `backend` (`pt`, `tf`, or `unknown`),
   configured/attached `head`, and `size_bytes`. Missing facts remain
   `unknown`. The `configuration` basis records resolved selection, not observed
   evaluation; the instance basis records the supplied calculator type. Model
   identity does not reload DeepPot or hash a large model file.

### `validate_ts(vibration_results, *, structure=None, fmax_threshold=0.05, imaginary_cutoff_cm1=50.0, output=None)`

The current 2.3.3 release exposes `validate_ts` as a lazy root import from
`atst_tools.api`. It screens stored vibration results and optional frozen
structure facts. It never calls a live calculator or starts new force or
vibration calculations. An ASE structure path supplies force evidence only
when it contains frozen `SinglePointCalculator` forces; otherwise stationarity
may remain `unknown`. Missing scope or force evidence also remains `unknown`.
The result is a scoped screen and cannot prove IRC connectivity. Explicit
vibration selections that include fixed atoms remain valid;
`scope.fixed_indices_in_selection` records that overlap and the stationarity
check stays `unknown` because the constraint scopes differ.

The legacy `status` field retains the existing pass/fail imaginary-frequency
count screen. Consumers that need to know whether requested checks had enough
evidence should inspect `requested_checks_status`, `scope`, and `stationarity`.

```python
from atst_tools.api import validate_ts

summary = validate_ts(
    "vibration_results.json",
    structure="frozen_ts.traj",
    fmax_threshold=0.05,
    imaginary_cutoff_cm1=50.0,
)
```

This additive entry point was introduced in 2.2.9 and is stable in 2.3.1.

## Errors and support boundary

Workflow execution and configuration-validation failures derive from `ATSTAPIError`.
The read-only `validate_ts` helper raises `TypeError` or `ValueError` for invalid
facts and propagates file I/O errors; it does not execute a workflow.
The configuration-building helper above retains its documented filesystem and
input exceptions. The companion model component
defines `ConfigValidationError` for schema/path problems,
`UnsupportedDependencyError` for unavailable optional runtime dependencies
(including DeePMD-kit's `deepmd` component, MPI launcher's `mpi4py` requirement,
and DMF's `cyipopt`/IPOPT requirement),
`MPIConfigurationError` for image-parallel topology problems, and
`WorkflowExecutionError` for a workflow or runtime failure. Each carries an
optional workflow name and diagnostic context; the original failure is chained
as its cause where available. These error types are available from
`atst_tools.api.models`; they are intentionally not additional stable root
imports beyond the names listed above. The CLI unwraps them to retain its
existing exception and message surface.

DMF remains experimental. `run_workflow()` preserves its current dependency
requirements and safety guards; it does not make DMF a general production PBC
or calculator-embedding API.

## Compatibility and Deprecation

The public Python API surface is additive across 2.2.x. In 2.3.1, existing
CLI commands, YAML fields/defaults, output names, relative-path behavior, MPI
rules, and exit contracts remain unchanged, but `abacuslite>=1.2.1,<2` becomes
a required runtime dependency and `BACKEND_SOURCE` is always `external`. Only
the stable root imports listed above receive the API compatibility promise.
The 2.2.1 additions (progress events, plotting helpers, and the
`profiles`/`plots` result extensions) are optional and do not change existing
behavior. A future removal or incompatible behavior change will be documented
and deprecated in a release before removal.
