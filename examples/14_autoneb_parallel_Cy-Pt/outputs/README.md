# 14 AutoNEB Parallel Outputs

These files are curated from the completed SAI validation run:

- Job: `462244`
- Partition: `4V100`
- Launch: `mpirun -np 4 --map-by $MAP_OPT atst run config.yaml`
- ABACUS per image: single process, `OMP_NUM_THREADS=8`

Included files:

- `run_autoneb_parallel_single_gpu000.traj` ... `run_autoneb_parallel_single_gpu009.traj`: final AutoNEB image files.
- `summary_14_autoneb_parallel.json`: `atst neb summary --autoneb-prefix` output for the final images.
- `slurm-462244.out`: Slurm stdout/stderr log from the completed job.

Quick check from this example directory:

```bash
atst neb summary --autoneb-prefix outputs/run_autoneb_parallel_single_gpu
```
