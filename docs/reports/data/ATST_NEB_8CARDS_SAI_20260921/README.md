# NEB 8 interior graphs across 8 V100 cards (2026-09-21, job 1438379)

The last P5 scaling row: FT2DP single-head model, `chain10` (8 interior
images), `max_steps: 2`, one thread per rank, `rush-gpu` (16 GPUs per job).

| case | shape | wall | counters |
| --- | --- | --- | --- |
| dp-neb-chain10-serial | 1 process | 26.63 s | 66 `dp.force_calls` |
| dp-neb-chain10-8cards | `srun --mpi=pmix_v5 --ntasks=8 --gpus-per-task=1`, `round_robin` | **24.31 s** | Σ26 `dp.force_calls`, `world_size=8` |

Image parallelism across eight cards buys only ~1.1x here: the band is small
(two steps, 26 force calls) and each rank pays its own model load and MPI
start-up.  Together with the 4-card row (11.8/9.9 s vs ~11-13 s serial) the
conclusion is that the "one image per card" benefit grows with the work per
step, not with the card count at this fixture size.

`runs/` holds the batch summary, the record, per-case reports and the runtime
sidecars (round-robin device facts per rank, MPI-summed counters, sampled
peaks); `staging/` holds the manifest, the two configs and the sbatch entry.
