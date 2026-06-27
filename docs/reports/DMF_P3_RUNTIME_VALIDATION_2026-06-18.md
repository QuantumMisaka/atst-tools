# DMF P3 Runtime Validation 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: Candidate-comparison evidence; candidate energy/force write fixed after job 525521
**Owner**: ATST-Tools maintainers
**Scope**: P3 Direct MaxFlux candidate runs on SAI with DP backend

## Summary

Two staged DMF candidate-generation cases completed on SAI Slurm and were
compared with existing ATST ABACUS and DP reference results:

- `01_neb_Li-Si`
- `02_neb_H2-Au`

This is P3 candidate-comparison evidence, not production TS validation. DMF
remains experimental because the generated candidates have not yet been refined
with Dimer/Sella/CCQN or validated by vibration/IRC.

## Runtime

| Field | Value |
| :--- | :--- |
| Slurm job | `525521` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n32` |
| Resources | `--nodes=1`, `--ntasks=1`, `--gpus-per-node=2`, `--qos=rush-1o2gpu` |
| Elapsed | `00:02:41` |
| MaxRSS | `14632788K` |
| Environment bootstrap | Node-local clone of `dpeva-dpa4-test`, offline cached `cyipopt`/IPOPT install, editable ATST checkout install with `--no-build-isolation --no-deps` |
| Command path | `examples/18_dmf_production_validation/submit_dmf_dp_rush_1gpu.sbatch` |

Two failed setup attempts preceded the successful run:

- `524936`: one-GPU bootstrap was killed during conda clone/transaction.
- `525006`: two-GPU bootstrap passed clone but compute-node conda could not
  reach conda-forge.
- `525153`: offline conda install passed, but pip build isolation tried to
  reach PyPI.
- `525187` and `525200`: DMF reached candidate generation, then exposed JSON
  serialization issues for NumPy arrays and bytes in IPOPT info; fixed by the
  DMF summary normalizer.

These failures are now covered by the current sbatch script and
`tests/unit/test_dmf_workflow.py`.

## Candidate Comparison

The completed job generated `dmf_validation_report.json` with schema
`atst-dmf-validation-suite-v1`, status `candidate_compared`, and two cases.

**2026-06-21 correction note**: the table below is pre-fix standalone evidence.
It shows 7 images because the ATST wrapper did not forward YAML `nmove=10` into
the final `DirectMaxFlux` solve, so PyDMF used its own default `nmove=5`. The
wrapper now forwards `nmove` and writes final `t_eval` to `dmf_summary.json`;
the post-fix D2S rough-DMF rerun in job `533228` recorded `nmove=10`,
`n_images=12`, and `t_eval` length 12 for both staged cases. A standalone rerun
attempt, job `533227`, failed during compute-node conda environment setup before
ATST execution (`tk` package cache file missing), so this report keeps the
original standalone numeric comparison as historical evidence only.

| Case | `tmax` | Images | IPOPT status | RMSD to ABACUS TS (A) | RMSD to DP TS (A) | ABACUS barrier (eV) | DP barrier (eV) |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | ---: |
| `01_neb_Li-Si` | `0.4994841198` | 7 | success | `0.0128141221` | `0.0126187834` | `0.618346` | `0.7231818847` |
| `02_neb_H2-Au` | `0.5554593655` | 7 | success | `0.0551754077` | `0.0253945726` | `1.124752` | `0.6474094018` |

Both cases used:

- `initial_path: linear`
- `pbc_mode: cartesian_unwrapped`
- `remove_rotation_and_translation: false`
- `confirm_pbc_risk: true`
- DP model `temp_repos/dp_model/DPA-3.1-3M.pt`, head `Omat24`

## Interpretation

The two candidates are geometrically close to existing reference transition
state structures under same-order Cartesian RMSD, especially for Li-Si. H2-Au
is also close to the DP reference and within `0.06 A` of the ABACUS reference.

The original job `525521` showed that candidate trajectories did not retain
single-point energy/force results in the written `dmf_tmax.traj`, so candidate
energy and force fields in that generated comparison report were `null`/not
finite. The workflow now evaluates the `tmax` candidate once before writing it
and records candidate `energy`/`fmax` in `dmf_summary.json`; this fix is covered
by `tests/unit/test_dmf_workflow.py`.

## Remaining P3/P4 Work

- Add or run a refinement stage from DMF `tmax` into Dimer/Sella/CCQN for at
  least the two completed cases.
- Run vibration/IRC validation on refined candidates and record TS mode,
  endpoint connection, walltime, and failure modes.
- `d2s.rough_method: dmf` now has unit-level runtime integration and remains
  experimental. Do not mark it supported until the refinement and vibration/IRC
  evidence above is available.
