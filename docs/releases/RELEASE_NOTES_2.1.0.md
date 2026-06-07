# ATST-Tools 2.1.0 Release Notes

**Version**: 2.1.0
**Date**: 2026-06-07
**Branch**: `develop`

## Summary

ATST-Tools 2.1.0 is a feature release focused on expanding ASE-native
workflows with molecular dynamics support and a dedicated MD
post-processing path. It keeps the project on the governed YAML/CLI/document
structure while extending the runtime surface in a way that remains backward
compatible with existing 2.0.x inputs.

## Highlights

- Added `calculation.type: md` with two execution paths:
  ASE-driven MD using ABACUS or DeePMD-kit calculators, and ABACUS-native MD
  using abacuslite-managed input preparation and run monitoring.
- Added `atst md summary` and `atst md post` for trajectory summary and
  conversion/post-processing.
- Wired MD workflow completion to trigger the summary post-processing step
  automatically after successful runs.
- Added the Li-Si MD example set based on the existing `01_neb_Li-Si` initial
  structure, covering ASE+DP, ASE+ABACUS, and ABACUS-native configurations.
- Updated the feature matrix, CLI reference, configuration reference, examples
  overview, and documentation governance records to reflect the new MD support.

## Validation

- Unit tests pass in the `atst-dev` environment for the MD workflow and
  MD post-processing coverage.
- Documentation governance checks pass for the active user, developer, and
  project-manager entry points.
- Version commands report `2.1.0` from the source tree after the version bump.

## Compatibility

- Package version: `2.1.0`.
- Existing 2.0.x YAML inputs remain valid. The new MD workflow is additive and
  does not change the semantics of existing NEB, AutoNEB, Dimer, Sella, CCQN,
  D2S, Relax, Vibration, or IRC inputs.
- GA remains unsupported. The ASE 3.28.0 GA implementation is still outside
  the project's supported workflow set.
