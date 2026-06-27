# DMF P4 D2S Runtime Smoke 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: Experimental D2S rough-DMF runtime smoke
**Owner**: ATST-Tools maintainers
**Scope**: D2S `rough_method: dmf` with DP backend on SAI

## Summary

The experimental D2S rough-DMF path was exercised on the same two staged P3
systems:

- `03_Li-Si_d2s_dmf`: Li migration endpoint pair
- `04_H2-Au_d2s_dmf`: H2-Au endpoint pair

Both jobs ran `rough_method: dmf` followed by a short Sella refinement. This
proves runtime integration from DMF candidate generation into an existing
single-ended optimizer. It is not full production TS validation because
vibration/IRC and ABACUS comparison were intentionally not run.

## Runtime

| Field | Value |
| :--- | :--- |
| Slurm job | `526327` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n31` |
| Resources | `--nodes=1`, `--ntasks=1`, `--gpus-per-node=2`, `--qos=rush-1o2gpu` |
| Elapsed | `00:02:56` |
| MaxRSS | `14689704K` |
| Environment bootstrap | Node-local clone of `dpeva-dpa4-test`, offline cached `cyipopt`/IPOPT install, editable ATST checkout install with `--no-build-isolation --no-deps` |
| Command path | `examples/18_dmf_production_validation/submit_d2s_dmf_sella_dp_rush_1gpu.sbatch` |

## Smoke Metrics

**2026-06-21 correction note**: this early smoke table is pre-fix evidence. The
7-image DMF path came from PyDMF's default `nmove=5` because the ATST wrapper did
not yet forward YAML `nmove=10` to the final `DirectMaxFlux` solve. The rerun in
job `533228` covered the vibration-enabled D2S route and recorded `nmove=10`,
`n_images=12`, and a 12-point final `t_eval` grid for both staged nested DMF
runs; see `DMF_P4_D2S_VIBRATION_VALIDATION_2026-06-18.md`.

| Case | DMF `tmax` | DMF images | Candidate energy (eV) | Candidate `fmax` (eV/A) | Sella frames | Final energy (eV) | Final `fmax` (eV/A) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `03_Li-Si_d2s_dmf` | `0.4994841319` | 7 | `-345.9689114392` | `0.1713945366` | 15 | `-345.9993250631` | `0.0196170827` |
| `04_H2-Au_d2s_dmf` | `0.5554637732` | 7 | `-203.0063973218` | `0.2786037732` | 8 | `-203.0630985200` | `0.0361530291` |

Both D2S artifact manifests recorded the expected relationship:

- `dmf_path`
- `dmf_candidate`
- `dmf_summary`
- `dmf_artifact_manifest`
- `single_ended_trajectory`

The stage records were:

- `endpoint_optimization`: complete
- `rough_dmf`: complete, `experimental: true`
- `sella`: complete
- `vibration`: skipped

## Interpretation

This runtime smoke closes the implementation-level P4 wiring risk: D2S can use
standalone DMF as the rough path generator, pass the explicit `tmax` candidate
to Sella, and write a traceable manifest. The route remains experimental
because the job did not include normal-mode validation, IRC endpoint connection,
or ABACUS cross-checks.

Focused local-mode vibration validation was run afterward in Slurm job `526601`;
see `docs/reports/DMF_P4_D2S_VIBRATION_VALIDATION_2026-06-18.md`.

## Remaining Work

- Run longer refinement where needed and record convergence behavior rather
  than only a short smoke limit.
- Run IRC or equivalent endpoint-connection validation.
- Compare refined DMF-D2S candidates against ABACUS references before changing
  feature status beyond experimental.
