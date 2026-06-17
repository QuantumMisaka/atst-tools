# ATST-Tools 2.1.2 Release Notes

**Version**: 2.1.2
**Date**: 2026-06-17
**Branch**: `main`

## Summary

ATST-Tools 2.1.2 is a patch release for ABACUS preflight validation and
command handling. It adds an opt-in `abacus --check-input` dry-run path and
keeps `calculator.abacus.version_command` out of generated ABACUS `INPUT`
files.

## Highlights

- **ABACUS dry-run preflight**:
  - Added `atst run --dry-run --check-input` for ABACUS configurations.
  - Added `--check-input-timeout` and `--abacus-executable` controls.
  - Resolves representative structure and ABACUS data paths relative to the
    config file before running the check in a temporary work directory.

- **ABACUS command handling**:
  - Rejects shell-style leading environment assignments in
    `calculator.abacus.command`; use `calculator.abacus.omp`, explicit `env`,
    or a site wrapper instead.
  - Handles env-wrapped single-process ABACUS commands when stripping outer MPI
    environment variables.
  - Preserves explicit `version_command` handling for version probing.

- **ABACUS INPUT generation**:
  - Treats top-level `calculator.abacus.version_command` as ATST metadata so it
    is not written to ABACUS `INPUT`.
  - Keeps `calculator.abacus.parameters` as the ABACUS INPUT pass-through area.

## Validation

- `env PYTHONPATH=src pytest tests/unit -q`
- `git diff --check`
- Documentation conflict-marker check over active docs
- `env PYTHONPATH=src python -m atst_tools.scripts.cli --version`

## Compatibility

- Package version: `2.1.2`.
- Fully backward compatible with 2.0.x, 2.1.0, and 2.1.1 inputs.
- No YAML schema migration is required.
