# Issue #25 AutoNEB fmax Review

**Date**: 2026-05-18
**Issue**: `https://github.com/QuantumMisaka/atst-tools/issues/25`
**Scope**: `examples/03_autoneb_Cy-Pt`, ASE-native AutoNEB wrapper, ABACUS calculator workflow

## Finding

Issue #25 reports that `examples/03_autoneb_Cy-Pt` can diverge when run
serially with:

```yaml
calculation:
  type: autoneb
  n_simul: 1
  parallel: false
  optimizer: FIRE
  fmax: [1.00, 0.05]
  maxsteps: 10
```

The reported log column named `fmax` is the actual maximum force reported by
ASE's optimizer, not the YAML convergence threshold. The failure signature is
therefore a FIRE sub-optimization instability: energy rises and the actual
force grows quickly until ABACUS sees an unreasonable geometry.

## Source Assessment

Local inspection found:

- the current `03_autoneb_Cy-Pt/inputs/init_neb_chain.traj` matches the main
  branch legacy AutoNEB input in image count, atom count, endpoint energies, and
  constraints;
- the middle images carry empty `FixAtoms(indices=[])`, so the issue is not
  caused by losing a real fixed-substrate constraint during the refactor;
- the ASE-native refactor already fixes ATST-side AutoNEB risks around
  list-valued `fmax/maxsteps`, result freezing, and serial non-shared calculator
  directory isolation;
- ASE FIRE exposes `downhill_check` specifically to detect uphill steps caused
  by large timesteps, and `maxstep` controls the maximum geometry displacement
  per optimizer step.

## Implemented Response

ATST-Tools now exposes:

```yaml
calculation:
  optimizer_kwargs:
    downhill_check: true
    maxstep: 0.05
```

for AutoNEB. These kwargs are forwarded directly to the ASE optimizer
constructor. This keeps ATST's default behavior ASE-native while allowing the
ABACUS AutoNEB example to use a safer FIRE configuration for the issue #25
scenario.

## Validation Plan

Unit tests cover:

- schema/default governance for `calculation.optimizer_kwargs`;
- forwarding of `optimizer_kwargs` from `AutoNEBRunner` into the optimizer
  constructor;
- issue #25 serial AutoNEB schedule semantics for `n_simul=1`,
  `parallel=false`, `fmax=[1.00, 0.05]`, and `maxsteps=10`;
- `AbacusNEB` projected-force parity with ASE native `NEB` for a single
  middle-image band.

Runtime smoke validation still requires an ABACUS Slurm job on SAI 4V100. The
recommended acceptance check is that `run_autoneb_log_iter001.log` no longer
shows monotonic force growth toward tens of eV/Ang within the first 10 FIRE
steps and that ABACUS does not crash from an unreasonable structure.

## SAI Runtime Validation Update

A follow-up SAI validation report is available at `docs/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md`.

Key outcomes:

- `examples/03_autoneb_Cy-Pt` completed on SAI as job `422164` with exit code `0:0`.
- The current result is not numerically equivalent to the committed `main` result because the current YAML is a short-step stability example (`fmax: [1.00, 0.05]`, `maxsteps: 1`) while the historical main script used tighter non-climb `fmax` and no explicit one-step cap.
- A diagnostic serial run recorded 21 ASE FIRE `downhill_check` reset callback events before being stopped, proving that the parameter is active during real ABACUS calculations.
- The SAI run also required an ABACUS 3.10.1 banner-version parser compatibility fix in the vendored abacuslite wrapper.
