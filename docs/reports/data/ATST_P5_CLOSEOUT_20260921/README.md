# P5 closeout archive (2026-09-21)

Evidence for the two bounded follow-ups of the GPU node tuning P5 list plus the
post-fix ABACUS baseline:

* `job-1436941/runs-abacus` — `abacus-relax-h2au-omp1` (example config with its
  explicit `omp: 1`, override counter as expected) against
  `abacus-relax-h2au-t2` (same config without `omp`, so the manifest budget 2 is
  delivered through `ATST_THREADS_SOURCE=harness`).  Both ran with four inner
  MPI ranks; the sidecars show the thread facts, the CP relax input and the
  ABACUS stdout/stderr.
* `job-1436941/runs-neb8` and `job-1436926/runs-neb8` — the remaining pressure
  row: eight image-parallel DP ranks on one V100 card against the serial
  reference on the same chain, twice (11.2/20.5 s and 13.6/16.3 s).
* `job-1436926/slurm-1436926.out` — the first attempt, kept on purpose: without
  `--ntasks >= 4` the ABACUS example's inner `mpirun -np 4` is refused by PRRTE
  ("not enough slots available"), so both ABACUS cases failed in 13.7 s.
* `staging/` — the manifests, the four case configs, the job script and its
  runbook, i.e. everything needed to reproduce both groups.

Machine paths inside the evidence are the SAI ones
(`/home/galileo-group/galileouser02/...`) as recorded during the run.

> 2026-09-21 补充：切片里 staging 脚本引用的 `atst_tools.bench.harness` 已更名为 `atst_tools.bench.batch_runner`（产物名与 schema 字符串保持 `harness_*` 不变）。
