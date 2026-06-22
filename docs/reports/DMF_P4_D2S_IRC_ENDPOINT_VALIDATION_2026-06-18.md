# DMF P4 D2S IRC Endpoint Validation 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: Experimental endpoint-connection validation
**Owner**: ATST-Tools maintainers
**Scope**: D2S `rough_method: dmf` with DP backend, Sella refinement, focused vibration, and descent-IRC endpoint checks on SAI

## Summary

The two refined DMF-D2S candidates from the focused vibration validation were
used as starting points for ATST descent-IRC endpoint validation:

- `07_Li-Si_d2s_dmf_irc`
- `08_H2-Au_d2s_dmf_irc`

For each case, `prepare_dmf_irc_inputs.py` wrote the final Sella TS structure
and a local mode vector derived from the DMF path around `tmax`. ATST then ran
`calculation.type: irc` with `backend: descent` in both directions. The endpoint
validator compared the two relaxed branches against the original reactant and
product endpoints on the reactive atoms.

Both cases passed the configured `0.25 A` reactive-atom RMSD threshold. This
adds endpoint-connection evidence to the P4 DMF-D2S path, but the route remains
experimental until ABACUS comparison is complete.

## Runtime

| Field | Value |
| :--- | :--- |
| Slurm job | `526657` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n33` |
| Resources | `--nodes=1`, `--ntasks=1`, `--gpus-per-node=2`, `--qos=rush-1o2gpu` |
| Elapsed | `00:02:07` |
| MaxRSS | `11250456K` |
| AllocTRES | `billing=360,cpu=16,gres/gpu=2,mem=44G,node=1` |
| Command path | `examples/18_dmf_production_validation/submit_d2s_dmf_irc_dp_rush_1gpu.sbatch` |
| Report path | `examples/18_dmf_production_validation/dmf_irc_endpoint_report.json` |

Two earlier attempts failed during environment bootstrap before scientific work:

- `526652`: missing Python/libuuid/python_abi constraints for offline
  `cyipopt`/IPOPT install.
- `526654`: Slurm spool working directory caused `pip install -e ../..` to
  target `/var/spool`.

The final script uses the same constrained offline install pattern as the
successful P4 vibration job and `cd "$SLURM_SUBMIT_DIR"`.

## Endpoint Metrics

| Case | Reactive indices | Assignment | Init RMSD (A) | Final RMSD (A) | Threshold (A) | Status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| `07_Li-Si_d2s_dmf_irc` | `[0]` (`Li`) | `swapped` | `0.0229157057` | `0.0240723773` | `0.25` | `pass` |
| `08_H2-Au_d2s_dmf_irc` | `[0, 1]` (`H`, `H`) | `swapped` | `0.2464814461` | `0.1158427670` | `0.25` | `pass` |

The suite report recorded:

| Field | Value |
| :--- | :--- |
| `schema_version` | `atst-dmf-irc-endpoint-suite-v1` |
| `validated_endpoint_connection` | `true` |
| `status` | `pass` |
| `case_count` | `2` |

## Interpretation

This run closes the immediate P4 endpoint-connection gap for the DP-backed
DMF-D2S route. It is intentionally a focused descent-IRC check on the reactive
atoms selected by the previous vibration run, not a full-system Sella IRC
production acceptance run.

The H2-Au initial endpoint RMSD is close to the `0.25 A` threshold, so it should
remain visible in future acceptance decisions. It passed the predeclared
threshold but should not be overinterpreted as ABACUS-level production evidence.

## Remaining Work

- Compare refined DMF-D2S candidates against ABACUS references.
- Decide final supported-status acceptance thresholds for barrier, TS mode,
  endpoint connection, walltime, and failure handling.
- Keep DMF and DMF-D2S marked experimental until ABACUS comparison is complete.
