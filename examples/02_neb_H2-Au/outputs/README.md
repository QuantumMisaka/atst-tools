# 02 H2-Au Two-Stage NEB Outputs

These files are curated from P0/P1 runtime validation for the two-stage NEB
examples.

Included files:

- `neb_two_stage_abacus_smoke.traj`: ABACUS smoke trajectory from SAI job `461313`.
- `atst_artifacts_two_stage_abacus_smoke.json`: ABACUS artifact manifest.
- `slurm-atst_neb2stage-461313.out` and `.err`: successful Slurm logs.
- `neb_two_stage_dp.traj`: DP smoke trajectory.
- `atst_artifacts_two_stage_dp.json`: DP artifact manifest.

Quick checks from this example directory:

```bash
atst neb summary outputs/neb_two_stage_abacus_smoke.traj --n-max 1
atst neb summary outputs/neb_two_stage_dp.traj --n-max 8
```
