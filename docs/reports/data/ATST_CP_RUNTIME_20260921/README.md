# Constant-potential x runtime joint acceptance archive (2026-09-21)

Evidence slice for the run described in
`docs/reports/ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md`, collected from
SAI `galileouser02` (job 1435012, 4V100, 1 GPU, plus the diagnostic job
1435134 that located the OMP override).

## Contents

| path | what it is |
| --- | --- |
| `runs/harness_summary.json` | batch harness summary (2/2 succeeded, 421.528 s) |
| `runs/bench_record.json` | benchmark record with the run revision `e0abb71`, job/QOS fields and the operator fields |
| `runs/<case>/harness_case.json`, `harness_worker.err`, `harness_worker.out` | per-case harness report; the `.err` files carry the `calculator omp=1 overrides the inherited OMP_NUM_THREADS=8` warning |
| `cases/<case>/runtime_evidence.json` | runtime sidecar (`status: complete`; device facts, thread facts, counters, host samples) |
| `cases/<case>/constant_potential_results.json`, `constant_potential.log`, `constant_potential_checkpoint.json`, `atst_artifacts.json` | CP workflow artifacts (one target / three targets) |
| `cases/<case>/config.yaml`, `fixture.json` | the exact staged case configuration and the materialized fixture hashes |
| `staging/cases-cp.json`, `run-cp-joint.sbatch`, `config.negative.yaml`, `probe-omp.sbatch`, `probe_eval_omp.py` | staged manifest, acceptance job script, allocation-refusal negative config and the OMP diagnostic probe |
| `slurm-1435012.out`, `slurm-1435134.out` | job logs (module list, job facts, the refusal message, the probe output) |
| `reverify/**` | OMP fix re-verification (job 1436782, revision `5e26789`): the single-point case sidecar, CP result, harness report, the now-empty worker stderr, the record and the reduced manifest/config |

## Provenance

* Fixture: `examples/19_constant_potential_Pt` materialized with
  `--basis lcao --electrons 217 --dipole --density-precision 12`; the resulting
  `fixture.json` records the UPF/orbital/input hashes.
* Case machine paths are the SAI ones (`/home/galileo-group/galileouser02/...`)
  as recorded during the run; they are evidence content, not repository
  configuration.
* The `atst_api_result.json` copies were left out: their content is already
  covered by `harness_case.json` and the runtime sidecars.
