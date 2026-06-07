# ATST-Tools 2.0.2 Release Notes

**Version**: 2.0.2
**Date**: 2026-06-05
**Branch**: `develop`

## Summary

ATST-Tools 2.0.2 is a 2.0.x maintenance release focused on NEB production
stability, ABACUS STRU input compatibility, and release-governed validation
evidence.

## Highlights

- Tuned the default two-stage NEB warm-up path: templates and examples now use
  bounded two-stage CI-NEB with `stage1_steps: 20` and `stage1_fmax: 0.20`.
- Added two-stage NEB artifact metadata for warm-up/final-stage convergence and
  actual optimizer step counts.
- Made artifact manifests robust to numpy scalar values.
- Added ABACUS `STRU` / `.stru` input support for `atst neb make` initial,
  final, and optional TS guess structures through the project abacuslite reader.
- Stabilized Fast IDPP periodic nearest-image tie handling and wrote optimized
  IDPP coordinates without applying endpoint constraints.
- Added STRU I/O compatibility review evidence documenting the current
  abacuslite boundary versus the legacy `ase-abacus` ASE I/O plugin behavior.
- Added SAI ABACUS LTS 3.10.1 two-stage NEB validation artifacts for 01/02/13
  examples, including serial/parallel consistency evidence.

## Validation

- Unit tests pass in the `atst-dev` environment with `pytest tests -q`.
- Documentation whitespace and conflict-marker checks pass for README, docs,
  examples README, and AGENTS.
- Version commands report `2.0.2` from the source tree.

## Compatibility

- Package version: `2.0.2`.
- Existing 2.0.1 YAML inputs remain valid. The two-stage NEB defaults are more
  production-oriented, and explicit YAML values continue to override defaults.
- `atst neb make` now accepts ordinary ASE-readable structure files and ABACUS
  `STRU` / `.stru` files. This does not claim full replacement of the
  `ase-abacus` fork's ASE I/O plugin API.
