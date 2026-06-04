# Two-stage NEB LTS 3.10.1 validation

**Date**: 2026-06-04
**Version**: 1
**Status**: active evidence
**Owner**: ATST-Tools maintainers
**Environment**: SAI 4V100, ABACUS LTS 3.10.1, `ks_solver=cusolver`, `atst-dev`
**Runtime directory**: `validation_runs/two_stage_neb_lts3101_20260603/`
**Tracked attachments**: `docs/reports/data/two_stage_neb_lts3101_20260603/`

This report records the real-run validation of the two-stage NEB defaults on
examples 01, 02, and 13. The tested workflow uses bounded ordinary NEB warm-up
followed by CI-NEB refinement. Stage 1 stops when either `stage1_fmax` is reached
or `stage1_steps` is exhausted.

## Summary

All final validation jobs ran on the SAI `4V100` partition and completed with
Slurm state `COMPLETED` and exit code `0:0`.

| Case | Mode | Job ID | Elapsed | Barrier (eV) | Reference (eV) | Delta (eV) | Two-stage optimizer steps |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| `01_neb_Li-Si` | serial | `479036` | `00:08:12` | 0.620255893 | 0.618346 | +0.001910 | warm-up 3 + CI 10 |
| `02_neb_H2-Au` | parallel | `479014` | `01:46:33` | 1.130763523 | 1.124752 | +0.006012 | warm-up 20 + CI 61 |
| `02_neb_H2-Au` | serial | `479037` | `17:14:06` | 1.130762745 | 1.124752 | +0.006011 | warm-up 20 + CI 61 |
| `13_neb_parallel_Cy-Pt` | parallel | `479015` | `00:01:46` | 1.322674549 | 1.322675 | -0.000000 | warm-up 0 + CI 0 |

The 02 serial and parallel barriers differ by about `7.8e-7 eV`, confirming that
the image-level parallel execution reproduces the serial energy profile within
sub-meV precision for this run.

The tracked attachment directory contains the lightweight reproducibility and
audit files for each final 4V100 run: `config.yaml`, `submit.sbatch`,
`summary.json`, and `atst_artifacts.json`. It also contains
`sacct_4v100_jobs.txt` with the final Slurm completion state. Large raw runtime
files under `validation_runs/`, such as ABACUS work directories, trajectory
files, and GPU monitor logs, remain intentionally untracked.

## Barrier reproducibility

The two-stage NEB settings reproduce the expected reaction barriers for the
tested examples:

- 01 Li-Si differs from the stored reference by about `0.002 eV`.
- 02 H2-Au differs from the stored reference by about `0.006 eV`; serial and
  parallel results are mutually consistent.
- 13 Cy-Pt matches the stored parallel-reference barrier within rounding.

For 02, the highest-energy image is image 5 in these runs while the stored
reference reports transition-state image 4. The barrier remains consistent, so
this is treated as an image-discretization/index shift rather than a barrier
reproduction failure.

The 02 `summary.json` reports projected NEB fmax values of about `0.0511 eV/A`,
slightly above the nominal `0.05 eV/A` target, while the artifact manifest marks
the CI stage as converged. For strict reporting, this case should be polished by
restarting from the final band with a few additional CI-NEB steps.

## Iteration and runtime impact

The two-stage workflow should not be described as universally reducing NEB
optimizer iterations.

- 01 benefits clearly in this validation: it used 13 total optimizer steps and
  completed in `00:08:12`, compared with the historical LTS 3.10.1 reference
  runtime of `00:18:41`.
- 13 was already within the configured force threshold at the initial band, so
  both stages used zero optimizer steps.
- 02 does not show a step-count reduction. The warm-up stage exhausted the
  default `stage1_steps=20` without reaching `stage1_fmax=0.2`, then CI-NEB used
  61 additional steps. The serial runtime, `17:14:06`, is close to the historical
  strict reference runtime of `16:45:17`.

The large walltime improvement for `02_neb_H2-Au` in parallel mode comes from
image-level parallelism, not from two-stage reducing optimizer iterations.

## Practical conclusion

`stage1_steps=20` is a reasonable bounded warm-up default. The 02 H2-Au result
shows that 3-5 warm-up steps would be too short for a difficult band when
`stage1_fmax=0.2` is used. The default should therefore remain a step cap, not a
promise of stage-1 convergence.

Two-stage NEB is useful as a stable warm-up strategy and preserves barrier
reproducibility on the tested examples. It can reduce work on easier cases, but
hard cases still require case-specific validation and may not need fewer
optimizer iterations than direct CI-NEB.
