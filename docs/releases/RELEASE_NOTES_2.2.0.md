# ATST-Tools 2.2.0 Release Notes

**Version**: 2.2.0
**Date**: 2026-07-22
**Branch**: `main`

## Summary

ATST-Tools 2.2.0 publishes the stable Python API with its final CLI and
image-parallel compatibility safeguards. The release remains additive: existing
YAML workflow and command-line entry points are retained.

## Highlights

- Adds a stable, schema-backed Python API for workflow execution and embedded
  CCQN use, with a clean-installed wheel release gate.
- Preserves legacy CLI behavior: CLI-owned workflows do not gain API artifact
  manifests, and missing or directory YAML paths retain their filesystem
  exceptions.
- Adds synchronized pre-run construction for parallel NEB and both ATST and
  native ASE AutoNEB backends so local calculator, engine, optimizer, and
  trajectory-writer failures exit all ranks before optimizer collectives.
- Classifies a missing `cyipopt` module as an optional dependency error while
  retaining solver/runtime failures as workflow execution errors.

## Validation

- Focused API, CLI, MPI, and package metadata tests in the `atst-dev`
  environment.
- `python scripts/verify_wheel_api.py --mpi-smoke` with a bounded two-rank
  optimizer-construction failure regression that clean-installs the wheel.
- `git diff --check` for source and documentation changes.

## Compatibility

- Package version: `2.2.0`.
- Python support remains `>=3.10`.
- Existing YAML schemas and normal single-rank CLI execution retain their
  established behavior.
