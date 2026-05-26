# Issue #25 AutoNEB SAI Validation

**Date**: 2026-05-18  
**Environment**: SAI `4V100`, ABACUS `LTSv3.10.1-sm70-auto`, `atst-dev`, ASE `3.28.0`  
**Example**: `examples/03_autoneb_Cy-Pt`  
**Validation workspace**: `temp_sai_issue25_validation/`

## Scope

This report validates three questions with SAI ABACUS calculations:

1. Whether `examples/03_autoneb_Cy-Pt` finishes stably on the current branch.
2. Whether the current-branch result is consistent with the committed `main` branch result.
3. Whether `optimizer_kwargs.downhill_check: true` actually takes effect during a real ABACUS AutoNEB run.

## Runtime Fix Required Before Validation

The first SAI submission exposed a separate ABACUS wrapper compatibility issue before AutoNEB physics could be tested.
The vendored abacuslite `AbacusProfile.parse_version()` only accepted legacy stdout matching `ABACUS version ...`.
SAI ABACUS `LTSv3.10.1` prints a banner-style line such as `ABACUS v3.10.1`, which caused calculator construction to fail with:

```text
AttributeError: 'NoneType' object has no attribute 'group'
```

The project now accepts both version formats and raises a diagnostic `RuntimeError` for unknown formats. This was verified with `tests/unit/test_abacuslite_profile.py`.

## Jobs

| Purpose | Directory | Job ID | Final State | Notes |
|---|---:|---:|---:|---|
| Current example, unmodified config | `temp_sai_issue25_validation/current_example_run3` | `422164` | `COMPLETED 0:0`, `01:10:10` | Completed with `=== AutoNEB Calculation Finished ===` |
| `downhill_check` callback diagnostic | `temp_sai_issue25_validation/current_issue25_diagnostic_run3` | `422165` | `CANCELLED` after evidence capture, `01:21:07` | Stopped after 21 callback reset events to avoid wasting GPU time |

Failed setup attempts were retained in `current_example`, `current_issue25_diagnostic`, `current_example_run2`, and `current_issue25_diagnostic_run2` for auditability. They failed before meaningful AutoNEB validation due to missing copied `examples/data` files and the ABACUS version parser issue above.

## Current Branch Stability

The current example run used the repository config as-is:

```yaml
calculation:
  n_simul: 4
  n_max: 10
  parallel: true
  optimizer: FIRE
  optimizer_kwargs:
    downhill_check: true
    maxstep: 0.05
  fmax: [1.00, 0.05]
  climb: true
  maxsteps: 1
```

SAI result:

- Slurm job `422164` completed successfully with exit code `0:0`.
- AutoNEB stdout reached `=== AutoNEB Calculation Finished ===`.
- The run produced all ten final trajectory files `run_autoneb000.traj` through `run_autoneb009.traj`.

Conclusion: the current branch no longer reproduces the issue #25 failure mode where the Cy-Pt AutoNEB case crashes before completion.

## Comparison Against `main` Branch Result

The `main` branch committed result was extracted from `examples/Cy-Pt@graphene/autoneb/run_autoneb*.traj` into `temp_sai_issue25_validation/main_baseline` and analyzed with the same script as the current run.

| Metric | `main` committed result | Current branch SAI run | Difference |
|---|---:|---:|---:|
| Image count | 10 | 10 | 0 |
| Highest-energy image | 5 | 5 | 0 |
| Forward barrier | 1.327886 eV | 2.336211 eV | +1.008325 eV |
| Max final-image force | 0.233195 eV/Ang | 5.097634 eV/Ang | +4.864439 eV/Ang |
| Max image RMSD vs `main` | n/a | 0.211342 Ang | n/a |

Conclusion: the current branch run is topologically similar enough to place the highest image at the same index, but it is not numerically consistent with the `main` committed result.

The dominant reason is that the two workflows are not equivalent:

- `main:examples/Cy-Pt@graphene/autoneb/autoneb_run.py` uses `fmax = [0.20, 0.05]` and does not explicitly cap each AutoNEB sub-optimization to one step.
- Current `examples/03_autoneb_Cy-Pt/config.yaml` uses `fmax: [1.00, 0.05]` and `maxsteps: 1`.
- The current run therefore finishes as a short-step workflow smoke/stability example, not as a converged reproduction of the historical `main` result.

## `downhill_check` Effectiveness

A diagnostic run was launched with the same structure and ABACUS setup, but with issue #25-like serial settings so that FIRE could take multiple steps in each sub-optimization:

```yaml
calculation:
  n_simul: 1
  parallel: false
  maxsteps: 10
  fmax: [1.00, 0.05]
  optimizer_kwargs:
    downhill_check: true
    maxstep: 0.05
```

The launcher injected a real ASE `position_reset_callback` into `optimizer_kwargs`. This callback wrote `downhill_check_events.jsonl` whenever ASE FIRE detected an uphill energy step and reset positions.

Evidence before stopping the diagnostic job:

- Job `422165` ran for `01:21:07` before manual stop.
- It reached AutoNEB iteration 005.
- `downhill_check_events.jsonl` contained 21 callback events.
- Each event records `energy > energy_last`, which is exactly the ASE FIRE condition for reset under `downhill_check=True`.

Representative events:

```json
{"energy": -11865.5556413736, "energy_last": -11865.5979441357, "delta_energy": 0.042302762100007385, "current_norm": 112.98863654213795, "reset_norm": 112.98761895531813}
{"energy": -11866.092870638, "energy_last": -11866.1293732497, "delta_energy": 0.036502611699688714, "current_norm": 112.83426761176791, "reset_norm": 112.8349330098452}
{"energy": -11866.1157903701, "energy_last": -11866.1161221068, "delta_energy": 0.00033173669908137526, "current_norm": 112.83474529339172, "reset_norm": 112.8347500925946}
```

Conclusion: `downhill_check` is not merely accepted by the YAML schema or forwarded to ASE; it is exercised in real ABACUS AutoNEB calculations and triggers actual FIRE reset callbacks.

## Final Assessment

- Issue #25's original crash-oriented failure is resolved for the current example: the unmodified current branch case finishes on SAI.
- Current example output should not be claimed as numerically equivalent to the `main` committed result because the current YAML is intentionally a short-step stability example and differs from the historical script controls.
- `downhill_check` is active in real SAI ABACUS runs. The diagnostic callback proves actual uphill-step reset events.
- The ABACUS 3.10.1 banner-version parser compatibility fix is necessary for the current SAI production environment and is covered by a targeted unit test.

## Reproduction Artifacts

- Current completed run analysis: `temp_sai_issue25_validation/current_example_run3/analysis.json`
- Main baseline analysis: `temp_sai_issue25_validation/main_baseline/analysis.json`
- Downhill callback events: `temp_sai_issue25_validation/current_issue25_diagnostic_run3/downhill_check_events.jsonl`
- Analysis script: `temp_sai_issue25_validation/scripts/analyze_autoneb.py`
