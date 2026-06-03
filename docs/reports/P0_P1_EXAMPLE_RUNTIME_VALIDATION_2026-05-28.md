# P0/P1 Example Runtime Validation - 2026-05-28

**Version**: 2.0.0
**Date**: 2026-05-28
**Status**: Maintained
**Owner**: ATST-Tools maintainers

## Scope

This report records the example additions and runtime checks for the P0/P1
transition-state workflow enhancements:

- `examples/02_neb_H2-Au/config_two_stage*.yaml`: ordinary NEB warm-up followed
  by CI-NEB.
- `examples/10_irc_H2/config_descent*.yaml`: descent IRC backend driven by a
  curated mode vector.
- `examples/12_ccqn_H2-Au/config_auto_modes*.yaml`: CCQN automatic reactive
  mode enumeration.

The DP variants provide fast local smoke checks. The ABACUS variants were
validated through SAI Slurm on `4V100` with ABACUS LTS 3.10.1.

## Static Validation

Commands:

```bash
conda run -n atst-dev pytest tests/unit/test_examples.py tests/unit/test_examples_reference_results.py -q
conda run -n atst-dev pytest tests/unit -q
```

Results:

- Targeted example tests: `19 passed`.
- Full unit tests: `230 passed`.

## DP Smoke Checks

All DP checks used `../../temp_repos/dp_model/DPA-3.1-3M.pt` with
`head: Omat24`.

| Example | Command | Result | Output evidence |
| --- | --- | --- | --- |
| Two-stage NEB | `atst run config_two_stage_dp.yaml` | exit `0` | `outputs/neb_two_stage_dp.traj`: 40 frames; `outputs/atst_artifacts_two_stage_dp.json`: workflow `neb` |
| Descent IRC | `atst run config_descent_dp.yaml` | exit `0` | `outputs/irc_descent_dp.traj`: 2 frames; `outputs/norm_irc_descent_dp.traj`: 2 frames; workflow `irc` |
| CCQN auto modes | `atst run config_auto_modes_dp.yaml` | exit `0` | `outputs/ccqn_auto_modes_dp.traj`: 3 frames; `selected_mode.reactive_bonds_1based`: `[[2, 61]]`; 8 candidate modes; 2 diagnostic steps |

## ABACUS Slurm Smoke Checks

Submission environment:

- `#SBATCH --partition=4V100`
- `#SBATCH --qos=rush-1o2gpu`
- `#SBATCH --nodes=1`
- `#SBATCH --ntasks=1`
- `#SBATCH --gpus-per-node=1`
- `module load abacus/LTSv3.10.1-sm70-auto`
- `conda run -n atst-dev atst run <config>`
- `OMP_NUM_THREADS=8`

| Example | Config | Job ID | Slurm state | Elapsed | Output evidence |
| --- | --- | --- | --- | --- | --- |
| Descent IRC | `examples/10_irc_H2/config_descent.yaml` | `461256` | `COMPLETED`, exit `0:0` | `00:01:13` | `outputs/irc_descent.traj`: 2 frames; `outputs/norm_irc_descent.traj`: 2 frames; `outputs/atst_artifacts_descent.json`: workflow `irc` |
| CCQN auto modes | `examples/12_ccqn_H2-Au/config_auto_modes.yaml` | `461254` | `COMPLETED`, exit `0:0` | `00:07:32` | `outputs/ccqn_auto_modes.traj`: 3 frames; `selected_mode.reactive_bonds_1based`: `[[2, 61]]`; 8 candidate modes; 2 diagnostic steps |
| Two-stage NEB | `examples/02_neb_H2-Au/config_two_stage.yaml` | `461313` | `COMPLETED`, exit `0:0` | `00:07:43` | `outputs/neb_two_stage_abacus_smoke.traj`: 6 frames; manifest stage names `ordinary_neb_warmup=complete`, `ci_neb=complete` |

## Implementation Notes

- The ABACUS two-stage NEB example uses a curated 3-image smoke chain,
  `inputs/init_neb_chain_smoke.traj`, extracted from the existing H2/Au NEB
  chain. The DP variant keeps the full chain and demonstrates the 3-step
  warm-up setting.
- The descent IRC mode vector is `inputs/descent_mode.npy` with an H-H stretch
  direction. It validates the descent backend wiring and output generation; it
  is not a strict Sella IRC path.
- The CCQN auto mode example intentionally omits `reactive_bonds`; the workflow
  enumerates molecule-surface H-Au pairs and writes the selected mode plus all
  candidates to the mode manifest.
- Early Slurm submissions failed because `sbatch --wrap` used `/bin/sh`, which
  lacks `source` and `module`. The successful submissions wrap the command in
  `bash -lc`.
- One earlier full-chain NEB smoke submission was cancelled after it proved too
  expensive for a smoke check. It was replaced by the curated 3-image chain.

## Conclusion

The new examples are valid YAML inputs and all three feature paths were checked
with both DP runtime smoke and ABACUS/Slurm smoke runs. The ABACUS runs confirm
that the examples can execute on SAI `4V100` and produce the expected trajectory,
manifest, mode enumeration, and diagnostic artifacts.
