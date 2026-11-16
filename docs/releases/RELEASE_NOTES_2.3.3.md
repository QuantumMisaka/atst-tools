# ATST-Tools 2.3.3 Release Notes

**Version**: 2.3.3
**Date**: 2026-11-09
**Status**: Published on PyPI and GitHub
**Source**: `main`, release commit `6c71420142d138eea9dec5f6d98d1e8ee28cf989`
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

The tagged publication run
[42641517908](https://github.com/QuantumMisaka/atst-tools/actions/runs/42641517908)
completed successfully after release readiness, the full unit suite,
documentation governance, build, strict Twine and clean-wheel API gates.

- [PyPI 2.3.3](https://pypi.org/project/atst-tools/2.3.3/)
- [GitHub tag v2.3.3](https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.3.3)

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| `atst_tools-2.3.3-py3-none-any.whl` | 373137 | `ad8b3bbb7dc4092854666a1455fcdedd5db4000358306dfb4442982beef7c2d6` |
| `atst_tools-2.3.3.tar.gz` | 330908 | `dce230f6606c12f6539e32efd370a0a18e1e90e451aab4b88f96007a5bb6e770` |

### Unreleased Sella template follow-up (2026-11-16)

The generated standalone Sella YAML now uses `eta: 0.005`, matching the existing
standalone and D2S Sella runtime defaults. Explicit eta overrides, including
`0.002`, remain supported. Historical example settings and the separate IRC eta
configuration are unchanged. This source follow-up is not part of the published
artifact identities or validation counts above.

### Unreleased source follow-up (2026-11-12)

The local source now repairs stale periodic images in Fast IDPP, uses MIC
neighboring-frame tangents/springs, and reports the final returned geometry.
Generated bands and D2S rough NEB bands reject nonfinite geometry and severe
contacts before publication/calculator evaluation. Existing API/YAML signatures
remain unchanged; periodic optimization trajectories can change, and previously
accepted severely overlapping bands now raise an error. This follow-up is not
included in the candidate validation counts above and has not been published.
See the [repair evidence and limits](../reports/IDPP_DYNAMIC_MIC_2026-11-12.md).

The follow-up optimization defaults IDPP to ASE FIRE while retaining the
current objective and stopping tests (`optimizer="legacy"` restores fixed-step
Python behavior). YAML/CLI expose `idpp_optimizer`; explicit TS segmentation
uses MIC-length interval allocation by default (`image_distribution="equal"`
restores the historical half split). Ordinary IS/FS generation remains the
primary route. Supplied TS coordinates are retained, with no movement option;
frame counts and existing-chain/restart behavior are unchanged. These defaults
can change newly generated paths and iteration counts. Python `step_size` and
`max_disp` are legacy-mode controls. No dependency version is raised.
