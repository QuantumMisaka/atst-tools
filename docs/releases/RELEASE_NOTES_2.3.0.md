# ATST-Tools 2.3.0 Release Notes

**Version**: 2.3.0
**Date**: 2026-08-03
**Branch**: pending merge (`feat/agent-facing-progress`)
**Tag**: `v2.3.0`

## Summary

ATST-Tools 2.3.0 extends the stable Python API with agent-facing observability
and visualization capabilities: structured NDJSON progress events, energy-plot
helpers, and opt-in result-envelope extensions. The release is additive:
existing YAML workflows, command-line entry points, the stable root imports,
and the `atst-api-result-v1` handoff schema are retained.

## Highlights

- Adds structured NDJSON progress events to the Python API and the installed
  process runner. `RunOptions(progress=True)` emits one JSON line per event
  (`workflow_start`, then one `image_step` per NEB/AutoNEB band image) to a
  caller-supplied stream and forwards the same mapping to
  `progress_callback`, so Python consumers never parse stdout. The runner
  exposes the same event set through `--progress`.
- Adds the `atst_tools.utils.plot` visualization module and the stable
  `neb_energy_profile`, `sella_energy_curve`, and `ccqn_energy_curve` API
  helpers. Trajectory energies are read from frozen calculator results and are
  never recomputed. matplotlib remains an optional `[plot]` extra and is never
  required to import `atst_tools.api`.
- Adds opt-in `profiles`/`plots` result-envelope extensions to the API runner.
  `RunOptions(profiles=True)` adds a per-image (NEB/AutoNEB) or per-step
  (Sella/CCQN) energy and force summary; `RunOptions(plots=True)` renders the
  workflow energy plot PNG and records its relative path in the result
  document and artifact manifest. Both extensions only ever add optional
  fields, so documents produced without them stay byte-identical to the
  original `atst-api-result-v1` schema.
- Wraps profiles/plots rendering best-effort so a missing optional dependency
  or unreadable input omits the extension instead of failing a completed
  workflow.

## Validation

- Focused API, runner, plot, and package metadata tests in the `atst-dev`
  environment; the full unit suite covers the new progress, plot, and result
  extension contracts.
- The release gate continues to run `python scripts/verify_wheel_api.py
  --mpi-smoke`, which performs a bounded two-rank API runner dry-run plus
  in-process optimizer- and engine-construction failure-synchronization
  regressions from a clean wheel installation.
- `git diff --check` for source and documentation changes.

## Compatibility

- Package version: `2.3.0`.
- Python support remains `>=3.10`.
- The nine stable `atst_tools.api` root imports and the existing YAML schemas
  retain their established behavior; 2.3.0 additions are purely optional.
