# 12 H2-Au CCQN Auto-Mode Outputs

These files are curated from P0/P1 runtime validation for the CCQN automatic
reactive-mode examples.

Included files:

- `ccqn_auto_modes.traj`, `.log`, `_final.extxyz`, `_mode_manifest.json`, and diagnostics JSON: ABACUS auto-mode outputs from SAI job `461254`.
- `atst_artifacts_auto_modes.json`: ABACUS artifact manifest.
- `slurm-atst_ccqnauto-461254.out` and `.err`: successful Slurm logs.
- `ccqn_auto_modes_dp.traj`, `.log`, `_final.extxyz`, `_mode_manifest.json`, and diagnostics JSON: DP auto-mode outputs.
- `atst_artifacts_auto_modes_dp.json`: DP artifact manifest.

Quick checks from this example directory:

```bash
atst ccqn summary outputs/ccqn_auto_modes.traj --tail 5
atst ccqn summary outputs/ccqn_auto_modes_dp.traj --tail 5
```
