# DMF P4 D2S ABACUS Comparison 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: ABACUS comparison complete; refined suite passed
**Owner**: ATST-Tools maintainers
**Scope**: ABACUS LTS 3.10.1 single-point comparison for refined DMF-D2S candidates

## Summary

The refined DMF-D2S candidates were compared against existing ABACUS reference
evidence using ABACUS LTS 3.10.1 single-point calculations on SAI:

- `01_neb_Li-Si`: passed barrier, reference-TS RMSD, and candidate force checks.
- `02_neb_H2-Au`: initially passed barrier and reference-TS RMSD checks but
  failed the raw candidate force check; a targeted ABACUS Sella refinement and
  constrained-force re-collection then passed the barrier, RMSD, and
  free-coordinate force checks.

The ABACUS comparison gate is complete for the two-case P4 evidence set. The
route remains experimental because `rough_method: dmf` is an opt-in rough stage
and has not replaced the default `rough_method: neb` production path.

## Runtime

| Field | Value |
| :--- | :--- |
| Slurm job | `526738` |
| State | `COMPLETED`, exit `0:0` |
| Partition/node | `4V100`, `4v100n16` |
| Resources | `--nodes=1`, `--ntasks=4`, `--gpus-per-node=4`, `--qos=rush-gpu` |
| Elapsed | `00:03:51` |
| MaxRSS | `7241720K` |
| AllocTRES | `billing=720,cpu=32,gres/gpu=4,mem=88G,node=1` |
| Command path | `examples/18_dmf_production_validation/submit_d2s_dmf_abacus_compare_rush_gpu.sbatch` |
| Report path | `examples/18_dmf_production_validation/dmf_abacus_comparison_report.json` |

Earlier job `526700` failed in the Python collection layer after ABACUS had
completed the first Li-Si SCF. Root cause: ABACUS LTS did not emit
`eig_occ.txt`, so the generic collector could not parse the run. The comparison
script now falls back to parsing `!FINAL_ETOT_IS` and the `TOTAL-FORCE` table
from `running_scf.log`.

Corrective H2-Au refinement and refined comparison:

| Field | Value |
| :--- | :--- |
| H2-Au Sella job | `526921`, `COMPLETED`, exit `0:0`, elapsed `00:15:46` |
| Refined comparison job | `527093`, `COMPLETED`, exit `0:0`, elapsed `00:03:47`, MaxRSS `7171748K` |
| Refined comparison script | `examples/18_dmf_production_validation/submit_d2s_dmf_abacus_refined_compare_rush_gpu.sbatch` |
| Refined report path | `examples/18_dmf_production_validation/dmf_abacus_comparison_refined_report.json` |

Two `sbatch --export=...` refined submissions, `527052` and `527075`, were
cancelled by Slurm before script output with `CANCELLED by 0`; the hardcoded
refined sbatch script ran normally.

## Acceptance Thresholds

| Check | Threshold |
| :--- | ---: |
| Barrier delta vs ABACUS reference | `0.50 eV` |
| Cartesian RMSD to ABACUS reference TS | `0.20 A` |
| Candidate max force | `0.10 eV/A` |

## Results

Initial comparison, before H2-Au corrective refinement:

| Case | Status | Candidate barrier (eV) | Barrier delta (eV) | RMSD to ABACUS TS (A) | Candidate `fmax` (eV/A) |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `01_neb_Li-Si` | `pass` | `0.6164607262` | `-0.0018852738` | `0.0032293864` | `0.0838711199` |
| `02_neb_H2-Au` | `fail` | `1.4249472824` | `0.3001952824` | `0.0581137310` | `0.5577982091` |

Refined comparison, after H2-Au ABACUS Sella refinement:

| Case | Status | Candidate barrier (eV) | Barrier delta (eV) | RMSD to ABACUS TS (A) | Candidate `fmax` (eV/A) |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `01_neb_Li-Si` | `pass` | `0.6164607262` | `-0.0018852738` | `0.0032293864` | `0.0838711263` |
| `02_neb_H2-Au` | `pass` | `1.1994820058` | `0.0747300058` | `0.0316904594` | `0.0992859778` |

For constrained systems, the comparison force gate uses ASE constrained forces
from the collected ABACUS single-point structure. H2-Au has fixed Au slab atoms
(`FixAtoms(indices=2..33)`): the raw ABACUS force table still contains a fixed
layer maximum of `0.4329508075 eV/A`, while the free-coordinate constrained
`fmax` is `0.0992859778 eV/A`.

## Remaining Work

- Keep DMF-D2S marked experimental and opt-in unless additional production
  cases broaden the evidence set and the project explicitly changes the support
  matrix.
- Preserve the raw-force failed report and refined constrained-force report so
  future maintainers can audit the fixed-layer force semantics.
