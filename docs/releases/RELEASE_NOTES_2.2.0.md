# ATST-Tools 2.2.0 Release Notes

**Version**: 2.2.0
**Date**: 2026-07-24
**Branch**: `main`
**Tag**: `v2.2.0`

## Summary

ATST-Tools 2.2.0 publishes the stable Python API with final CLI and
image-parallel compatibility safeguards. The release is additive: existing YAML
workflow and command-line entry points are retained.

## Highlights

- Adds a stable, schema-backed Python API for workflow execution and embedded
  CCQN use, with a clean-installed wheel release gate.
- Adds the installed `python -m atst_tools.api.runner` process boundary with
  root-only `atst-api-result-v1` JSON handoff, stable `0/2/1` exit codes, and
  no scheduler or MPI-launcher ownership.
- Preserves legacy CLI behavior: CLI-owned workflows do not gain API artifact
  manifests, missing or directory YAML paths retain their filesystem
  exceptions, and the installed `atst` console command exits successfully
  without printing a Python `WorkflowResult` representation.
- Adds synchronized pre-run construction for parallel NEB and both ATST and
  native ASE AutoNEB backends so local calculator, engine, optimizer, and
  trajectory-writer failures exit all ranks before optimizer collectives; the
  native ASE NEB receives the caller-supplied communicator.
- Classifies a missing `cyipopt` module as an optional dependency error while
  retaining solver/runtime failures as workflow execution errors.

## Validation

- Focused API, CLI, MPI, and package metadata tests in the `atst-dev`
  environment.
- `python scripts/verify_wheel_api.py --mpi-smoke` runs a bounded two-rank API runner dry-run, plus in-process optimizer- and engine-construction failure-synchronization regressions, from a clean wheel installation.
- `git diff --check` for source and documentation changes.

## Compatibility

- Package version: `2.2.0`.
- Python support remains `>=3.10`.
- Existing YAML schemas and normal single-rank CLI execution retain their
  established behavior.
