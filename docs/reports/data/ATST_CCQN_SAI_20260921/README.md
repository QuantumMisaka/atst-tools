# CCQN fixed-cost re-check on SAI (2026-09-21)

Evidence for the V100 re-check of the local decomposition in
`docs/reports/ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md` section 17:
one CCQN case (H2+Au64, `reactive_bonds: 1-2`, `max_steps: 8`) against the
FT2DP single-head 100k model, run through the batch runner on one V100.

| path | what it is |
| --- | --- |
| `case_report.json`, `batch_summary.json` | per-case report and batch summary - the first run written with the post-rename artifact names (`worker.out` / `worker.err` live next to the case report on SAI) |
| `runtime_evidence.json` | runtime sidecar: 9 `dp.force_calls`, 1 calculator build, sampler 5 samples over 4.9 s, peak 1074 MiB, `threads_source=harness` |
| `ccqn_ft2dp.log`, `slurm-1437354.out` | CCQN steps (all inside one second) and the job facts |
| `staging/` | the manifest, case configs (with and without the `runtime` section), the sbatch entry and the stand-in driver used for the login-node pass |

Machine paths inside the staged configs are the SAI ones.  The login-node
stand-in pass (no GPU) measured 2.56 s for the same nine force calls.
