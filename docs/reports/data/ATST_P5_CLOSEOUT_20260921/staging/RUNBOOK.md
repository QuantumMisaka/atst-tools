# P5 closeout (2026-09-21, SAI 4V100, one GPU)

Two bounded groups from the P5 remaining list plus the post-fix ABACUS baseline:

1. `cases-abacus-threads.json` — `abacus-relax-h2au-omp1` (example as shipped,
   explicit `omp: 1`, expects `runtime_threads_overridden=1`) and
   `abacus-relax-h2au-t2` (same config without `omp`, manifest budget 2, expects
   `threads_source=harness` and `OMP_NUM_THREADS=2`).
2. `cases-neb-8rank-1card.json` — `dp-neb-chain10-serial` (reference) and
   `dp-neb-chain10-mpi8` (`mpiexec --oversubscribe -n 8`, one card, the pressure
   row that the local §15 test predicts to be a large negative return).

Submit: `sbatch --export=ALL run-p5-closeout.sbatch`
