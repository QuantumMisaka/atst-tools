# ATST-Tools 2.3.3 Release Notes

**Version**: 2.3.3
**Date**: 2026-11-09
**Status**: Release candidate; tag ready, publication pending
**Source**: `release/v2.3.3` (commit recorded at publication)
**Tag**: `v2.3.3`

## Summary

This patch release adds transition candidate and reaction-atom selection
primitives, the experimental ABACUS i-PI socket client, and stricter ordinary
ASE/ABACUS MD convergence validation.

- Add minimum-image displacement shares, anchored candidate analysis, path
  progress/quality, candidate metrics and complementary candidate ranking in
  `atst_tools.utils.analysis`.
- Add `detect_bond_changes` for formed, broken and changed bonds between
  initial and final frames, using ASE Cordero covalent radii, a minimum
  bond-length change tolerance and an optional molecule filter.
- Make CCQN `ic` auto reactive-bond selection prefer initial/product bond
  changes before falling back to proximity enumeration.
- Add the opt-in `calculator.abacus.socket` client for single, fixed-cell
  calculator workflows. It is experimental and requires an ABACUS build with
  `socket_driver`; NEB/AutoNEB/IRC/DMF/D2S and constant potential remain
  outside this route.
- Validate SCF convergence on every ordinary ASE-driven ABACUS MD force/stress
  evaluation. Missing or failed evidence is rejected before the integrator can
  consume unvalidated forces.
- Add the PyYAML test dependency and the vibration-restart transport
  documentation carried on `main`.

## Compatibility

- Package version: `2.3.3`.

The transition analysis helpers are additive Python utilities. Existing CLI
and YAML entry points remain available. `get_displacement_analysis` keeps its
legacy highest-energy selection, non-minimum-image default and global-norm
threshold behavior for existing D2S/CLI callers; `get_anchored_displacement_analysis`
is the new minimum-image/share API.

The socket client is opt-in and experimental. It does not change FileIO
behavior unless `calculator.abacus.socket` is explicitly enabled. Ordinary ASE
ABACUS MD intentionally rejects previously accepted runs whose per-evaluation
SCF evidence is missing or failed; converged-input behavior otherwise remains
unchanged. No runtime dependency version is raised in this release.

## Validation

- Full offline source unit suite: **1514 passed, 13 skipped** (1527 collected).
- Focused transition selection/CCQN tests: **35 passed**.
- Documentation governance: **passed**.
- Wheel/sdist build and strict Twine checks: **passed**.
- Clean-wheel public API gate: **passed** (temporary venv, installed-wheel
  import/origin, CLI/API dry runs, stored vibration screening, and H2/Au
  CCQN fixture).

The real-backend socket evidence and limits are recorded in
the [feature matrix](../reports/FEATURE_STATUS_MATRIX.md) and
[configuration reference](../user/CONFIG_REFERENCE.md#31-abacus-dft).

## Publication

The candidate distributions were built from the release source and checked
with strict Twine and the clean-wheel public API gate:

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| `atst_tools-2.3.3-py3-none-any.whl` | 373137 | `bf74b59f8a1f03860cea5bf0a20b1ea7ec0d289619a0f28a3eae006ba020d6d1` |
| `atst_tools-2.3.3.tar.gz` | 331210 | `317a42da6738db2cbf7f7cd7f9751cbeb5af62db28cd6690c38a4beef11de8b1` |

Tag and PyPI publication remain pending. After publication this section will
record the exact release commit, GitHub Actions run and PyPI URLs.
