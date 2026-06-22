# DMF P4 D2S Vibration Validation 2026-06-18

**Version**: 2026-06-21
**Date**: 2026-06-21
**Status**: Experimental focused vibration validation
**Owner**: ATST-Tools maintainers
**Scope**: D2S `rough_method: dmf` with DP backend, Sella refinement, and focused vibration validation on SAI

## Summary

The experimental D2S rough-DMF route was rerun on the two staged periodic DP
systems with focused auto-index vibration enabled:

- `05_Li-Si_d2s_dmf_vib`
- `06_H2-Au_d2s_dmf_vib`

Both cases completed `rough_method: dmf -> Sella -> vibration` and wrote
`d2s_ts_validation.json` with `status: pass` for the expected one-imaginary-mode
criterion. The 2026-06-21 rerun also verifies the DMF `nmove` fix: each nested
DMF summary recorded `nmove=10`, `n_images=12`, and a 12-point final `t_eval`
grid. It is still not full production TS validation: IRC endpoint connection
and ABACUS comparison remain required.

## Runtime

| Field | Value |
| :--- | :--- |
| Slurm job | `533228` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n34` |
| Resources | `--nodes=1`, `--ntasks=1`, `--gpus-per-node=2`, `--qos=rush-1o2gpu` |
| Elapsed | `00:04:50` |
| MaxRSS | `14681544K` |
| AllocTRES | `billing=360,cpu=16,gres/gpu=2,mem=44G,node=1` |
| Environment bootstrap | Node-local clone of `dpeva-dpa4-test`, offline cached `cyipopt`/IPOPT install, editable ATST checkout install with `--no-build-isolation --no-deps` |
| Command path | `examples/18_dmf_production_validation/submit_d2s_dmf_sella_vib_dp_rush_1gpu.sbatch` |

The job log also emitted JAX/XLA CPU feature warnings from the DP runtime stack.
They did not stop either workflow or affect the Slurm exit status.

## Validation Metrics

| Case | DMF `tmax` | DMF images | Candidate energy (eV) | Candidate `fmax` (eV/A) | Sella frames | Final energy (eV) | Final `fmax` (eV/A) | Vibration indices | Imaginary modes |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| `05_Li-Si_d2s_dmf_vib` | `0.4994539946` | 12 | `-345.9688175917` | `0.1771646168` | 15 | `-345.9993293248` | `0.0200150889` | `[0]` (`Li`) | `314.1034 cm^-1` |
| `06_H2-Au_d2s_dmf_vib` | `0.5365625995` | 12 | `-203.0145640969` | `0.3150560714` | 8 | `-203.0613946766` | `0.0471686666` | `[0, 1]` (`H`, `H`) | `758.6052 cm^-1` |

`d2s_ts_validation.json` reported:

| Case | Status | Expected imaginary modes | Observed imaginary modes | `fmax` check |
| :--- | :--- | ---: | ---: | :--- |
| `05_Li-Si_d2s_dmf_vib` | `pass` | 1 | 1 | Not evaluated in vibration report |
| `06_H2-Au_d2s_dmf_vib` | `pass` | 1 | 1 | Not evaluated in vibration report |

The D2S artifact manifests recorded the expected chain:

- `dmf_path`
- `dmf_candidate`
- `dmf_summary`
- `dmf_artifact_manifest`
- `single_ended_trajectory`
- `vibration_results`
- `ts_validation`

## Interpretation

This run closes the immediate P4 vibration wiring risk: the D2S rough-DMF path
can pass its explicit `tmax` candidate through Sella and then run focused
auto-index vibration without requiring energy-bearing calculators on every DMF
path image. The focused index choice was:

- Li-Si: the moving `Li` atom from the actual `t_eval` nearest-neighbor index 5.
- H2-Au: the two `H` atoms from the actual `t_eval` nearest-neighbor index 6.

These are focused local-mode checks, not full-system vibrational analyses. They
are useful P4 evidence for workflow integration and local TS-like curvature, but
they do not prove endpoint connectivity.

## Remaining Work

- Run IRC or an equivalent endpoint-connection validation from refined
  candidates.
- Compare refined DMF-D2S candidates against ABACUS references, not only DP
  runtime outputs.
- Decide acceptance thresholds for barrier, TS mode, endpoint connection, and
  walltime before changing DMF or DMF-D2S from experimental to supported.
