# ABACUS inner-parallelism scan on one V100 (2026-09-21, job 1438158)

Four runs of the same relax case (example 06 H2-Au, one SCF-ish step) on one
V100 card, varying only the inner parallelism: `mpi` ranks x `omp` threads.
The batch ran with `--ntasks=8` so the inner `mpirun -np N` found its slots.

| case | inner MPI | OMP | wall |
| --- | --- | --- | --- |
| abacus-mpi4-omp1 | 4 | 1 | 147.3 s |
| abacus-mpi4-omp2 | 4 | 2 | **145.8 s** |
| abacus-mpi2-omp4 | 2 | 4 | 224.3 s |
| abacus-mpi1-omp8 | 1 | 8 | 146.8 s |

Conclusion recorded in the SAI report 5g: this ABACUS workload does not scale
with the CPU budget - every arrangement up to 8 cores lands at ~146-147 s and
the 2x4 split is 50 % worse - so the example default (`mpi: 4, omp: 1`) stays,
and the CPU side is not where ABACUS time is won.

`cases/<case>/` holds the case report and the runtime sidecar (thread facts,
counters); `staging/` holds the manifest, the four configs and the sbatch entry.
