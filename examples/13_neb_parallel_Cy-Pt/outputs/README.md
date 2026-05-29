# 13 NEB Parallel Outputs

These files are curated from the completed SAI validation run:

- Job: `461967`
- Partition: `8V100V0`
- Launch: `mpirun -np 5 --map-by ppr:1:node atst run config.yaml`
- ABACUS per image: inner `mpirun -np 4`, `OMP_NUM_THREADS=8`

Included files:

- `neb_parallel_nested_mpi.traj`: final NEB image chain.
- `summary_13_neb_parallel_8v100_fmax012.json`: `atst neb summary` output for the final chain.
- `slurm-461967.out`: Slurm stdout/stderr log from the completed job.

Quick check from this example directory:

```bash
atst neb summary outputs/neb_parallel_nested_mpi.traj --n-max 5 --strict
```
