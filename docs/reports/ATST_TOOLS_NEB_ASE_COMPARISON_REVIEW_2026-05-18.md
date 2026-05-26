# ATST-Tools NEB / AutoNEB / Dimer ASE Comparison Review

**Date**: 2026-05-18
**Scope**: `src/atst_tools/mep/neb.py`, `src/atst_tools/mep/autoneb.py`,
`src/atst_tools/mep/dimer.py`
**Status**: Updated review after upgrading `atst-dev` to ASE 3.28.0 and implementing the ATST-Tools alignment fixes
**Baseline command evidence**: `conda run -n atst-dev python -c "import ase; print(ase.__version__)"`
reports `3.28.0`.

## 1. Executive Summary

`atst-dev` has been upgraded from `ase==3.27.0` to the current PyPI production
release `ase==3.28.0`. This changes the production baseline used by this report:
ASE 3.28.0 now includes the NEB default-method update from legacy `aseneb` toward
`improvedtangent`, plus a zero-norm tangent guard in `ImprovedTangentMethod`.

The upgrade alone did not remove the main ATST-Tools risks identified in the
previous review because `AbacusNEB.get_forces()` remained a local fork of ASE
internals. The implementation has therefore been narrowed to an ASE 3.28.0
compatible wrapper with only the necessary development-branch fixes backported.

Cross-comparison result:

| Workflow | ATST-Tools implementation | ASE 3.28.0 production baseline | `temp_repos/ase` development baseline |
| :--- | :--- | :--- | :--- |
| NEB | `AbacusNEB(NEB)` now mirrors ASE 3.28.0 `get_forces()` plus the upstream real-force backport; no custom stress `iterimages()` path | default method now maps to `improvedtangent`; no unconstrained-force trajectory fix | adds unconstrained `real_forces` collection in serial/threaded/MPI paths |
| AutoNEB | `AbacusAutoNEB(AutoNEB)` keeps ASE 3.28.0 scheduling/result-freezing semantics and substitutes `AbacusNEB` only | same execution semantics as current development branch for ATST-relevant behavior | only docstring/typing changes relative to 3.28.0 |
| Dimer | `AbacusDimer` wraps ASE `DimerControl`, `MinModeAtoms`; local `MinModeTranslate` subclass carries the development guard | no divergence/NaN-step guard in `MinModeTranslate.step()` | adds divergence and NaN-step protections |

Implemented remediation:

1. Raised the package baseline to `ase>=3.28.0`.
2. Backported ASE development commits `57d55d02d` / `e7d9968ca` into `AbacusNEB`.
3. Restored ASE AutoNEB list-valued `fmax/maxsteps` schedule semantics and result-freezing.
4. Isolated serial non-shared AutoNEB calculator directories by image index.
5. Fixed Dimer displacement masks, propagated `max_num_rot`, and backported commits `0072551d6` / `849c29d51`.

## 2. Source Baseline

The updated comparison used these sources:

| Source | Version / revision | Path |
| :--- | :--- | :--- |
| ATST-Tools | current `develop` checkout | `src/atst_tools/mep/` |
| Installed ASE in `atst-dev` | `ase==3.28.0` | `/home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/lib/python3.10/site-packages/ase/mep/` |
| GitLab ASE mirror | `3.28.0-344-g8e83f5a49`, commit `8e83f5a4925f074ebef132594e06d4b29e0aeac0` | `temp_repos/ase/ase/mep/` |

Relevant `temp_repos/ase` commits after the `3.28.0` tag:

| Commit | Meaning for ATST-Tools |
| :--- | :--- |
| `57d55d02d` / `e7d9968ca` | Fix NEB trajectory forces by storing unconstrained `real_forces`. |
| `0072551d6` / `849c29d51` | Add Dimer divergence and NaN-step protections in `MinModeTranslate.step()`. |
| `7735505be` and docstring commits | Documentation/typing cleanup in MEP modules; no ATST-relevant execution behavior change. |

The project dependency declaration is now `ase>=3.28.0`, matching the validated
production baseline in `atst-dev`.

## 3. What ASE 3.28.0 Already Changes

Compared with ASE 3.27.0, production ASE 3.28.0 includes several NEB changes
that matter to ATST-Tools:

- `BaseNEB`, `DyNEB`, and `NEB` now default `method=None`, which emits a warning
  and maps to `improvedtangent`.
- `aseneb` is described as legacy behavior.
- `ImprovedTangentMethod.get_tangent()` avoids division by zero when the tangent
  norm is zero.
- AutoNEB and Dimer changes from 3.27.0 to 3.28.0 are mostly typing/docstring
  cleanup for ATST-relevant paths.

Impact inside ATST-Tools:

- `D2SWorkflow.run_rough_neb()` uses ASE `DyNEB` directly, but passes
  `method=algorism`; the YAML default is already `improvedtangent`, so 3.28.0
  mostly reinforces the intended default.
- `run_neb()` uses `AbacusNEB` and passes `method=algorism`; normal YAML-driven
  NEB also keeps the project default `improvedtangent`.
- Direct low-level calls to `AbacusNEB(...)` now default to `method=None`, so
  ASE 3.28.0 selects the current production default rather than ATST hardcoding
  legacy `aseneb`.

## 4. NEB Cross-Comparison

### 4.1 ASE 3.28.0 Production Behavior

ASE 3.28.0 `BaseNEB.get_forces()` still follows the classic ASE structure:

- checks duplicate calculators unless `allow_shared_calculator=True`;
- evaluates interior image forces and energies;
- initializes preconditioners through `PreconImages`;
- computes NEB projected forces through `NEBState` and the selected method;
- stores trajectory forces as constrained image forces through
  `self.real_forces[1:-1] = forces`.

Thus, despite the 3.28.0 default-method improvement, production ASE 3.28.0 does
not include the development-branch fix that stores unconstrained forces for
constrained NEB images.

### 4.2 `temp_repos/ase` Development Behavior

`temp_repos/ase` changes `BaseNEB.get_forces()` by allocating a full
`real_forces = np.zeros((nimages, natoms, 3))` array and filling it with:

```python
real_forces[i] = images[i].get_forces(apply_constraint=False)
```

in serial, threaded, and MPI branches. It also broadcasts `real_forces[i]` in
MPI mode and stores `self.real_forces = real_forces` before `iterimages()` writes
trajectory images.

This is directly relevant to ATST-Tools because NEB trajectories are used for
post-processing, restart, D2S transition-state guesses, and downstream
vibration/analysis preparation. If constrained atoms are present, constrained
and unconstrained forces can differ materially.

### 4.3 ATST-Tools `AbacusNEB`

`AbacusNEB` inherits from ASE `NEB`, but overrides the whole `get_forces()` body.
After this implementation pass, the override is intentionally limited to ASE
3.28.0 `BaseNEB.get_forces()` plus the `temp_repos/ase` real-force fix:

- the ASE duplicate-calculator guard is restored;
- `real_forces` uses ASE development's full `(nimages, natoms, 3)` layout;
- serial, threaded, and MPI branches assign unconstrained forces through
  `get_forces(apply_constraint=False)`;
- MPI broadcasts `real_forces[i]`;
- the custom stress-writing `iterimages()` override has been removed, so
  trajectory freezing follows ASE's native `BaseNEB.iterimages()` lifecycle.

This remains a small fork while production ASE 3.28.0 lacks the real-force fix.
When a future validated ASE release includes commits `57d55d02d` / `e7d9968ca`,
`AbacusNEB` can likely drop the override entirely and become a pure alias/wrapper.

### 4.4 NEB Issue Assessment

| Priority | Issue | Current status | Validation | Follow-up |
| :--- | :--- | :--- | :--- | :--- |
| P0 | Serial/threaded `AbacusNEB.real_forces` was uninitialized | Fixed locally by backporting `57d55d02d` / `e7d9968ca`. | `test_abacus_neb_iterimages_preserves_unconstrained_forces`. | Remove local override after production ASE ships the same fix. |
| P1 | `AbacusNEB` forks whole `get_forces()` | Reduced to an upstream-synced fork with explicit commit provenance. | Workflow unit tests plus future upstream-sync diff review. | Prefer deletion when the validated ASE baseline contains the backport. |
| P1 | Direct `AbacusNEB(...)` default remained `aseneb` | Fixed: default is `method=None`. | Direct construction/import review. | Keep YAML default `improvedtangent` for explicit workflows. |
| P2 | Broad `ase>=3.22.1` allowed older behavior | Fixed in packaging: `ase>=3.28.0`. | Config/package review. | Revisit lower bound only with an explicit compatibility matrix. |

## 5. AutoNEB Cross-Comparison

### 5.1 ASE 3.28.0 vs `temp_repos/ase`

For ATST-relevant execution behavior, ASE 3.28.0 and `temp_repos/ase` AutoNEB
are effectively the same. The observed diff in `ase/mep/autoneb.py` is limited
to docstring and typing cleanup.

ASE AutoNEB still:

- writes unused images to iteration history;
- attaches calculators to `to_run` interior images;
- constructs ordinary ASE `NEB`;
- attaches per-image trajectories;
- chooses list-valued `fmax` and `maxsteps` according to `many_steps`;
- calls `neb.distribute()` after optimization to freeze results for the next
  AutoNEB iteration.

### 5.2 ATST-Tools `AbacusAutoNEB`

ATST-Tools intentionally changes AutoNEB by:

- constructing `AbacusNEB` instead of ASE `NEB`;
- creating `iter_folder` before history writes;
- passing `allow_shared_calculator`.

The implementation now keeps ASE 3.28.0 behavior for the previously divergent
parts:

- list-valued `fmax` is preserved instead of collapsed to the last value;
- list-valued `maxsteps` is accepted by the config schema;
- `_execute_one_neb()` chooses first or second schedule values according to
  `many_steps`;
- ASE's `store_E_and_F_in_spc` / `neb.distribute()` result-freezing lifecycle is
  restored;
- serial non-shared images receive deterministic `image_###` calculator
  directories;
- aggressive post-subrun deletion of calculator directories has been removed.

The `iter_folder.mkdir()` change remains justified; it matches the earlier DP
validation finding where AutoNEB attempted to write iteration trajectories before
the directory existed.

### 5.3 AutoNEB Issue Assessment

| Priority | Issue | Current status | Validation | Follow-up |
| :--- | :--- | :--- | :--- | :--- |
| P0 | Serial non-shared AutoNEB images shared one calculator directory | Fixed with per-image directories. | `test_autoneb_runner_uses_unique_serial_abacus_directories`. | Preserve this policy for all file-backed calculators. |
| P1 | ASE `many_steps` schedule semantics were lost | Fixed for both `fmax` and `maxsteps`. | `test_abacus_autoneb_preserves_ase_fmax_and_maxsteps_schedule`. | Keep schema/docs aligned with ASE schedule semantics. |
| P1 | ASE `neb.distribute()` replacement was removed | Fixed by rebinding `store_E_and_F_in_spc`. | AutoNEB schedule unit test exercises the lifecycle hook. | Add a heavier restart/readback smoke when calculator fixtures are available. |
| P2 | Cleanup deleted calculator directories aggressively | Fixed by removing post-subrun `rmtree`. | Code review plus future failed-run smoke. | Add optional cleanup policy only if disk-pressure evidence requires it. |

## 6. Dimer Cross-Comparison

### 6.1 ASE 3.28.0 Production Behavior

ATST-Tools Dimer relies on ASE's Dimer kernel:

- `DimerControl`;
- `MinModeAtoms`;
- `MinModeTranslate`.

ASE 3.28.0 does not include the development-branch divergence and NaN-step
guard in `MinModeTranslate.step()`.

### 6.2 `temp_repos/ase` Development Behavior

`temp_repos/ase` adds:

```python
if norm(direction) == np.inf:
    raise RuntimeError('Dimer calculation diverged')
...
if norm(step) > self.max_step or np.isnan(norm(step)):
    step = direction * self.max_step
```

This is a stability improvement for divergent Dimer searches. ATST-Tools now
vendors this small guard in a local `MinModeTranslate` subclass until a validated
production ASE release includes the same behavior.

### 6.3 ATST-Tools `AbacusDimer`

ATST-Tools adds workflow setup around ASE:

- calculator construction through `CalculatorFactory`;
- displacement-vector loading through `atst run`;
- masks from constraints or explicit moving atom indices;
- trajectory naming through YAML;
- D2S integration from the highest-energy NEB image.

The wrapper previously had an ATST-side mask helper bug:

```python
d_mask = self.displacement_vector != np.zeros(3)
d_mask = d_mask[:, 0].tolist()
```

Only the x component determined whether an atom was considered moving. This has
been fixed by using the vector norm per atom.

The wrapper now passes `max_num_rot` to `DimerControl` for both displacement and
Gaussian initial eigenmode paths.

### 6.4 Dimer Issue Assessment

| Priority | Issue | Current status | Validation | Follow-up |
| :--- | :--- | :--- | :--- | :--- |
| P1 | `set_d_mask_by_displacement()` checked only x component | Fixed with vector norm. | `test_dimer_displacement_mask_uses_all_vector_components`. | Consider a nonzero tolerance if noisy displacement files become common. |
| P1 | Runtime ASE lacks Dimer divergence/NaN-step fix | Fixed locally by subclass backporting `0072551d6` / `849c29d51`. | Code review; add pathological Dimer step fixture if needed. | Remove subclass after production ASE includes the guard. |
| P2 | `max_num_rot` was stored but not passed to `DimerControl` | Fixed. | `test_dimer_passes_max_num_rot_to_dimer_control`. | Keep config schema and DimerControl API compatibility checked. |

## 7. What Upgrading To ASE 3.28.0 Solves

The upgrade meaningfully improves the production baseline, but the local
implementation fixes were still required for ATST-specific wrappers.

Solved or improved by ASE 3.28.0:

- Production ASE now treats `improvedtangent` as the default NEB method when no
  method is specified.
- Production ASE now guards `ImprovedTangentMethod` against zero tangent norm.
- Direct ATST use of ASE `DyNEB` or `NEB` without an explicit method would align
  better with current ASE recommendations.

Still not solved by ASE 3.28.0 alone, but now handled in ATST-Tools:

- `AbacusNEB.real_forces` persistence for constrained images.
- AutoNEB directory reuse in serial non-shared mode.
- AutoNEB list-valued `fmax/maxsteps` schedule behavior in ATST's override.
- Dimer displacement-mask helper logic.
- Dimer `max_num_rot` propagation to `DimerControl`.
- Dimer divergence/NaN-step guard from the development branch after 3.28.0.

## 8. Implementation Summary

Implemented code changes:

- `pyproject.toml`: raised dependency lower bound to `ase>=3.28.0`.
- `src/atst_tools/mep/neb.py`: replaced the previous stress-oriented fork with
  an ASE 3.28.0-compatible `get_forces()` carrying only commits `57d55d02d` /
  `e7d9968ca`.
- `src/atst_tools/mep/autoneb.py`: restored ASE schedule selection,
  `seriel_writer`, and `store_E_and_F_in_spc`; removed aggressive calculator
  directory deletion; isolated serial non-shared calculator directories.
- `src/atst_tools/mep/dimer.py`: fixed vector-mask construction, propagated
  `max_num_rot`, and added the Dimer step guard from commits `0072551d6` /
  `849c29d51`.
- `src/atst_tools/utils/config_schema.py`: allowed two-value
  `calculation.autoneb.maxsteps` schedules and validates positivity/length.

Residual design decision:

- `AbacusNEB.get_forces()` should be deleted once ATST-Tools aligns to a future
  production ASE release that already includes the real-force fix. Until then,
  the fork is documented with exact upstream commit provenance.

## 9. Verification Plan

Minimum unit coverage to add:

| Test | Expected assertion | Status |
| :--- | :--- | :--- |
| Constrained NEB real-force persistence | `iterimages()` interior images retain unconstrained forces, not constrained zeroed values. | Added. |
| Serial AutoNEB calculator directories | non-shared serial images receive unique directories. | Added. |
| AutoNEB schedule handling | list-valued `fmax/maxsteps` selects first or second element according to `many_steps`. | Added. |
| Dimer displacement mask | nonzero displacement in any Cartesian component marks atom as moving. | Added. |
| Dimer control propagation | configured `max_num_rot` reaches `DimerControl` when supported. | Added. |

Recommended runtime validation after code fixes:

- `conda run -n atst-dev pytest tests/unit -q`;
- one short DP NEB smoke test;
- one short ABACUS NEB or AutoNEB Slurm smoke test on SAI 4V100;
- one Dimer smoke test recording ASE version and final trajectory readability.

## 10. Evidence Collected During Updated Review

Commands run during the updated review:

```bash
conda run -n atst-dev python -c "import inspect, ase; from ase.mep.neb import NEB; print(ase.__version__); print(inspect.getsourcefile(NEB))"
git -C temp_repos/ase describe --tags --always --dirty
git -C temp_repos/ase rev-parse HEAD
diff -u /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/lib/python3.10/site-packages/ase/mep/neb.py temp_repos/ase/ase/mep/neb.py
diff -u /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/lib/python3.10/site-packages/ase/mep/autoneb.py temp_repos/ase/ase/mep/autoneb.py
diff -u /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/lib/python3.10/site-packages/ase/mep/dimer.py temp_repos/ase/ase/mep/dimer.py
git -C temp_repos/ase log --oneline 3.28.0..HEAD -- ase/mep/neb.py ase/mep/autoneb.py ase/mep/dimer.py
```

Observed facts:

- `atst-dev` imports production ASE `3.28.0`.
- `temp_repos/ase` is `3.28.0-344-g8e83f5a49`, commit
  `8e83f5a4925f074ebef132594e06d4b29e0aeac0`.
- Production ASE 3.28.0 and `temp_repos/ase` still differ in NEB
  unconstrained-force persistence.
- Production ASE 3.28.0 and `temp_repos/ase` still differ in Dimer
  divergence/NaN-step protection.
- Production ASE 3.28.0 and `temp_repos/ase` AutoNEB execution behavior is
  effectively the same for ATST-relevant paths.

This report now reflects the runtime implementation changes described above.
