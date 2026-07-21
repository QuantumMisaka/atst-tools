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

## Installation

ATST-Tools requires Python 3.10 or later:

```bash
pip install atst-tools
pip install "atst-tools[parallel]"  # only for externally launched MPI workflows
```

The package installs the workflow layer, not a universal calculation backend.
Install and configure the ASE calculator runtime required by your calculation.
For configuration-driven ABACUS work, that includes the normal executable,
pseudopotential, orbital, and site runtime setup. The embedded CCQN API accepts
an already-created ASE calculator, so its configuration remains the caller's
responsibility.

## Stable imports

Only these six names are stable root imports in this release:

```python
from atst_tools.api import (
    CCQNOptions,
    RunOptions,
    WorkflowResult,
    run_ccqn,
    run_workflow,
    validate_config,
)
```

Workflow, calculator, MEP, and vendored implementation packages are not stable
integration surfaces. Do not couple an application to their constructors or
helper functions; use the names above instead.

### `validate_config(config_source)`

Accepts either a YAML path or a mapping and returns a detached, normalized
configuration dictionary using the installed ATST schema and defaults. It does
not mutate a supplied mapping.

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
`WorkflowResult`. It supports every current `calculation.type`: NEB, AutoNEB,
Dimer, Sella, CCQN, D2S, Relax, Vibration, IRC, MD, and experimental DMF.
`RunOptions` exposes the CLI-equivalent controls:

- `dry_run`, `restart`, `check_input`, and `check_input_timeout` select the
  same workflow/preflight behaviors as the command path.
- `abacus_executable` overrides the executable used only for ABACUS
  check-input preflight.
- `world` accepts an existing communicator for embedding or tests. It is not a
  scheduler or launcher interface.

```python
from atst_tools.api import RunOptions, run_workflow

result = run_workflow("config.yaml", RunOptions(dry_run=True))
print(result.status, result.artifact_manifest)
```

### `run_ccqn(atoms, calculator, options=CCQNOptions())`

Runs ATST's CCQN single-ended transition-state search with caller-provided ASE
`Atoms` and calculator objects. `CCQNOptions` mirrors the CCQN schema controls:
`fmax`, `max_steps`, `trajectory`, `logfile`, `final_structure`,
`e_vector_method`, `reactive_bonds`, `auto_reactive_bonds`, `product_atoms`,
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

## Results and artifacts

`WorkflowResult` is a frozen container with `workflow`, `status`, `is_root`,
`artifact_manifest`, `artifacts`, `metadata`, `final_atoms`, `final_images`,
and `ts_atoms` fields. The artifact manifest is the durable, restart-safe
record; `artifacts` is its structured output list and `metadata` includes the
backend provenance.

The container is immutable, but ASE objects are mutable. `final_atoms`,
`final_images`, and `ts_atoms` are caller-owned snapshots: modifying one does
not modify ATST's internal workflow state. For image-parallel NEB and AutoNEB,
only the root rank receives in-memory `final_images` and `ts_atoms`; all ranks
receive status, metadata, and durable artifact paths.

## Paths, MPI, and backends

Relative paths retain the calling process's current working directory
semantics. The API never changes directory to a YAML file's parent. Use
absolute paths or establish the desired current working directory before a
call.

The API never launches Slurm, `mpirun`, `srun`, or nested calculator MPI. Start
the outer MPI job yourself, then have every rank call the same API with the
same configuration. NEB requires one rank per interior image and AutoNEB one
rank per simultaneous image; existing serial fallback behavior is preserved.

Backend delegation has four invariants:

1. Configuration-driven ABACUS runs preserve external-abacuslite-first
   resolution, followed by the vendored fallback only when the external package
   is unavailable.
2. `run_ccqn()` attaches the provided ASE calculator to a private atoms copy;
   it never rebuilds or reconfigures the calculator profile, command,
   pseudopotentials, orbitals, working directory, MPI settings, or I/O.
3. ATST does not re-export individual backend I/O functions. It remains the
   workflow, schema, artifact, and orchestration layer.
4. Metadata records `backend_source` as `external` or `vendored` for
   configuration-driven ABACUS results and `provided` for calculator injection.

## Errors and support boundary

Public API failures derive from `ATSTAPIError`. The companion model module
defines `ConfigValidationError` for schema/path problems,
`MPIConfigurationError` for image-parallel topology problems, and
`WorkflowExecutionError` for a workflow or runtime failure. Each carries an
optional workflow name and diagnostic context; the original failure is chained
as its cause where available.

DMF remains experimental. `run_workflow()` preserves its current dependency
requirements and safety guards; it does not make DMF a general production PBC
or calculator-embedding API.

## Compatibility and Deprecation

This first release is additive: existing CLI commands, YAML fields/defaults,
output names, relative-path behavior, MPI rules, and exit contracts remain
unchanged. Only the six root imports in this document receive the stable API
compatibility promise. Additions may be made in compatible releases; a future
removal or incompatible behavior change will be documented and deprecated in a
release before removal.
