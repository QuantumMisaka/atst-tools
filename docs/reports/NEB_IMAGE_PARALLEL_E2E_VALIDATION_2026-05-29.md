# NEB Image-Parallel E2E Validation 2026-05-29

**Version**: 1.0.0
**Date**: 2026-05-29
**Status**: Maintained
**Owner**: ATST-Tools maintainers

## Scope

This report records the end-to-end SAI validation for the Cy-Pt image-level
parallel examples:

- `examples/13_neb_parallel_Cy-Pt`: ordinary NEB launched as
  `mpirun -np 5 atst run config.yaml`, with five image ranks and inner ABACUS
  `mpi: 4`, `omp: 8`.
- `examples/14_autoneb_parallel_Cy-Pt`: AutoNEB launched as
  `mpirun -np 4 atst run config.yaml`, with `n_simul: 4` and single-process
  ABACUS, `omp: 8`.

The baseline comparison target is `examples/03_autoneb_Cy-Pt`.

The curated final outputs are copied into the example directories for quick
inspection:

- `examples/13_neb_parallel_Cy-Pt/outputs/`
- `examples/14_autoneb_parallel_Cy-Pt/outputs/`

The full work directories, including larger intermediate iteration files and
monitoring logs, remain under `validation_runs/cypt_parallel_e2e_20260528/`.

## Slurm Runs

| Case | Job | Partition | Status | Elapsed | Notes |
| --- | ---: | --- | --- | --- | --- |
| 03 baseline AutoNEB | 460989 | 4V100 | COMPLETED 0:0 | 06:43:14 | serial image scheduling, inner ABACUS mpi=16 |
| 13 NEB image-parallel | 461967 | 8V100V0 | COMPLETED 0:0 | 00:03:28 | outer `mpirun -np 5`, inner ABACUS mpi=4 |
| 14 AutoNEB image-parallel | 462244 | 4V100 | COMPLETED 0:0 | 00:37:16 | restart from completed single-GPU image files, outer `mpirun -np 4` |

Earlier exploratory 13/14 runs were intentionally cancelled after they exposed
path-quality and convergence-threshold issues. The final examples use a
prepared Cy-Pt NEB chain for 13, `fmax: 0.12` for 13, and `fmax: [0.20, 0.20]`
for 14. These thresholds are smoke-validation settings matched to the 03
baseline barrier, not stricter production convergence settings.

## Barrier Comparison

All final summaries were generated with `atst neb summary`.

| Case | Barrier / eV | TS image | Projected NEB fmax / eV A^-1 | Delta to 03 / eV |
| --- | ---: | ---: | ---: | ---: |
| 03 baseline | 1.322674610 | 5 | 0.132246856 | 0.000000 |
| 13 NEB image-parallel | 1.322674549 | 4 | 0.114133292 | -0.000000 |
| 14 AutoNEB image-parallel | 1.322099097 | 5 | 0.184590292 | -0.000576 |

Both 13 and 14 are within the accepted loose science threshold of 0.15 eV
relative to 03. The 13 result is effectively identical because it uses the
prepared double-end chain derived from the validated 03 path.

## Nested MPI Evidence

13 was run on `8V100V0` after the user requested moving the job from `4V100`.
The log records:

- `Image-level NEB parallelism active: world.size=5, interior_images=5`
- five ABACUS calculator instances using the vendored abacuslite backend
- `NEB calculation finished`

Each image rank used the ABACUS command template containing local isolated
inner MPI:

```bash
mpirun -np {mpi} --host localhost:{mpi} --oversubscribe -map-by slot \
  --bind-to none -mca ras ^slurm -mca plm isolated \
  -mca rmaps_base_oversubscribe 1 -mca coll_hcoll_enable 0 abacus
```

This keeps image-level parallelism controlled exclusively by outer
`mpirun atst run`; ATST does not start image-level MPI internally.

## Error Boundaries

Rank-count mismatch exits correctly:

- NEB mismatch job 460977 failed with
  `Image-level parallelism requires MPI ranks (4) to equal active interior images (5). Context: NEB.`
- AutoNEB mismatch job 460984 failed with
  `Image-level parallelism requires MPI ranks (3) to equal active interior images (4). Context: AutoNEB n_simul.`

These are expected hard errors and prevent silent partial image scheduling.

## ABACUS Efficiency

Per-image ABACUS `time.json` totals:

| Mode | Samples | Mean / s | Median / s | Min / s | Max / s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 03 baseline, 16 ranks on 4V100 | 8 | 28.962 | 27.752 | 27.675 | 33.313 |
| 13 final, 4 ranks on 8V100V0 | 5 | 167.932 | 162.934 | 160.793 | 190.952 |
| 14 final, 1 rank on 4V100 | 8 | 203.934 | 200.469 | 187.621 | 221.131 |
| exploratory 13, 4 ranks on 4V100 | 5 | 66.415 | 64.294 | 60.160 | 81.312 |

The final 8V100V0 13 run proves nested MPI correctness on that partition, but
it is slower than the earlier 4V100 exploratory nested-MPI run. The most direct
four-card versus single-card comparison from the same 4V100 hardware is the
exploratory 13 four-rank sample versus 14 single-rank sample: mean walltime
improves from 203.934 s to 66.415 s, about 3.07x speedup and about 77% parallel
efficiency for four ranks.

## Implementation Notes

Real runs exposed and fixed two MPI-sensitive paths:

- In `run_neb`, `calculation.make` generation is rank-0-only under effective
  image-level MPI, followed by a world barrier.
- IDPP chain generation reads and writes ASE trajectories with
  `parallel=False`, avoiding collective ASE I/O deadlocks when only rank 0
  creates the initial chain.

The final examples avoid runtime chain generation for 13 by carrying the
prepared chain as `inputs/cy_pt_neb_5_images.traj`.

## Conclusion

The 03, 13, and 14 validation tasks completed with exit code 0. The final 13
and 14 barriers match the 03 baseline well within the accepted threshold, and
the logs verify that image-level parallelism is launched by outer `mpirun atst
run` while ABACUS execution remains user-configurable through the calculator
command.
