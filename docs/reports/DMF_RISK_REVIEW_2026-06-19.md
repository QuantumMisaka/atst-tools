# DMF Risk Review 2026-06-19

**Version**: 2026-06-19
**Date**: 2026-06-19
**Status**: Risk review complete; three runtime risks reproduced
**Owner**: ATST-Tools maintainers
**Scope**: DP-backed Slurm reproduction of DMF algorithm/input risks

## Summary

This review audited the current experimental DMF implementation and constructed
risk cases from `examples/18_dmf_production_validation`.

Three H2-Au endpoint/indexing variants reproduced a real runtime risk: DMF
entered IPOPT evaluation and failed to produce complete `summary/path/tmax`
artifacts within a 600 second per-case timeout. Existing normal DMF evidence for
the same example family finishes in a few minutes for the full suite, so these
timeouts are treated as confirmed risk signals rather than ordinary runtime
variance.

The PBC + FBENM/CFBENM risk is already guarded by schema validation:
`pbc_mode: cartesian_unwrapped` requires `initial_path: linear`.

The existing successful D2S-DMF `tmax` outputs do not show a rounded-image
selection problem at the current `0.05 A` threshold.

## Runtime Evidence

| Field | Value |
| :--- | :--- |
| Main Slurm job | `529051` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n36` |
| Elapsed | `00:31:05` |
| MaxRSS | `11461384K` |
| Submission script | `examples/18_dmf_production_validation/submit_dmf_risk_cases_dp_rush_1gpu.sbatch` |
| JSON report | `examples/18_dmf_production_validation/dmf_risk_case_report.json` |

Earlier bootstrap/probing jobs were not used as algorithm evidence:

| Job | Outcome | Note |
| :--- | :--- | :--- |
| `529024` | Failed | Initial `cyipopt`/IPOPT environment solve failed. |
| `529027` | Failed | Clone/install route tried unavailable package downloads. |
| `529030` | Cancelled manually | First wrapped endpoint case exceeded 20 minutes with no artifacts before per-case timeout handling was added. |
| `529050` | Cancelled by Slurm | `sbatch --export=...` submission cancelled before script output. |

## Risk Cases

| Case | Constructed risk | Result | Confirmed |
| :--- | :--- | :--- | :--- |
| `H2-Au_wrapped_final_image` | Final H atom shifted by one cell vector; same physical image but long Cartesian endpoint displacement. | `timeout`, exit `124`, `600 s`, no complete artifacts. | Yes |
| `H2-Au_swapped_H_indices` | Equivalent H atoms swapped in final endpoint; DMF follows same-order Cartesian atom mapping. | `timeout`, exit `124`, `600 s`, no complete artifacts. | Yes |
| `H2-Au_inconsistent_fixed_slab` | Fixed Au slab atom displaced by `0.10 A` between endpoints. | `timeout`, exit `124`, `600 s`, no complete artifacts. | Yes |
| `Li-Si_pbc_cfbenm` | PBC `cartesian_unwrapped` with `initial_path: cfbenm`. | Rejected during config validation. | Guard covered |

## Existing Evidence Checks

The review also checked whether existing successful DMF-D2S outputs are using a
continuous `tmax` candidate that differs materially from the rounded path image
used by follow-up tools:

| Case | `tmax` | Rounded index | Candidate vs rounded RMSD (A) | Threshold (A) | Confirmed |
| :--- | ---: | ---: | ---: | ---: | :--- |
| `Li-Si_d2s_dmf_vib` | `0.4994840661` | `3` | `0.0001064860` | `0.05` | No |
| `H2-Au_d2s_dmf_vib` | `0.5554598450` | `3` | `0.0251282706` | `0.05` | No |

## Current Risk Assessment

The current DMF layer correctly advertises itself as experimental, but it still
has important sharp edges:

- It assumes same-order Cartesian endpoint correspondence. It does not detect
  atom permutation equivalence, wrapped final images, or shortest-image endpoint
  consistency.
- In `cartesian_unwrapped` PBC mode it relies on user-provided pre-unwrapped
  Cartesian endpoints. The runtime guard prevents unsupported FBENM/CFBENM
  paths, but it does not validate that endpoints are already in a consistent
  image.
- It does not preflight constrained endpoint consistency. A fixed slab atom can
  be displaced between endpoints and only surface as a difficult optimizer case.
- The run layer now has a risk-review timeout harness, but the production DMF
  workflow itself still depends on IPOPT limits and does not classify these
  input risks before optimization starts.

## Recommendations

- Keep DMF marked experimental in the feature matrix.
- Add endpoint preflight checks before considering broader support:
  same atom count/symbol order, fixed-atom endpoint displacement, endpoint
  Cartesian displacement outliers, and explicit warnings for PBC
  `cartesian_unwrapped` without prior unwrap evidence.
- Do not add automatic atom reordering or MIC corrections silently. Those change
  the scientific path definition and should be explicit preprocessing choices.
- Preserve the timeout harness for future regression checks so risky inputs fail
  with diagnosable evidence rather than hanging a Slurm allocation.
