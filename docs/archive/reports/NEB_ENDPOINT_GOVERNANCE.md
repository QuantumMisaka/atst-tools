## NEB Endpoint Result Governance

Review date: 2026-05-11

ATST-Tools keeps `atst neb make` as a lightweight interpolation command. It does not create calculators or launch ABACUS/DP. When the input endpoints are pure structures, `neb make` writes placeholder endpoint results so the chain can be serialized, but these placeholders are not scientifically valid for NEB.

### Confirmed Problem

ASE NEB/DyNEB does not optimize endpoint images, while improved tangent and barrier analysis read endpoint energies. Using `0 eV / 0 force` placeholders as endpoint results corrupts the energy profile.

The issue was reproduced with `examples/01_neb_Li-Si`:

| Endpoint data | Barrier from final band |
| --- | --- |
| Real endpoint energies | about `0.754 eV` |
| Endpoint energies forced to `0 eV` | `0.0 eV` |

This means the failure mode is not necessarily a Python exception. It is an algorithmic failure: the NEB path can be optimized or analyzed against a meaningless energy profile.

### Implemented Policy

| Workflow | Endpoint policy |
| --- | --- |
| Ordinary NEB | `endpoint_singlepoint: auto` by default; missing/placeholder endpoint results are computed before `AbacusNEB` is constructed. |
| AutoNEB | Same `endpoint_singlepoint` policy before initial `prefix*.traj` files are written. |
| D2S rough DyNEB | Endpoint optimization is enabled by default and skipped when endpoints already have meaningful results. If disabled, endpoint single-point validation still protects DyNEB from placeholders. |

Supported `endpoint_singlepoint` values:

| Value | Behavior |
| --- | --- |
| `auto` | Compute only missing/placeholder endpoint results and print a warning. |
| `always` | Recompute both endpoint results. |
| `never` | Reject missing/placeholder endpoint results. |

### Boundary

`atst neb make` remains a preprocessing command. It may produce a geometrically useful chain from pure structures, but the chain becomes a calculation-ready NEB input only after `atst run` has repaired endpoint results or after the user supplies endpoints with real energy/force data.
