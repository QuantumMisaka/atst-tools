# Examples Initial-Guess Audit
**Date**: 2026-05-26
**Status**: Maintained

## Summary

This audit records the follow-up check after finding that
`05_sella_H2-Au` and `12_ccqn_H2-Au` originally started from the stored Sella
final TS. Those two examples have been changed to use the same perturbed H2/Au
TS guess while preserving the fixed Au atoms.

## Findings

| Example | Finding | Action |
| :--- | :--- | :--- |
| `01_neb_Li-Si` | NEB path workflow; endpoint inputs are not single-ended TS guesses. | No change. |
| `02_neb_H2-Au` | NEB path workflow; endpoint inputs are not single-ended TS guesses. | No change. |
| `03_autoneb_Cy-Pt` | AutoNEB path workflow; endpoint inputs are not single-ended TS guesses. | No change. |
| `04_dimer_CO-Pt` | Single-ended TS example already starts away from its stored final TS; previous audit found input RMSD about `0.081` Ang. | No change. |
| `05_sella_H2-Au` | Previously a final-TS confirmation. Now uses a verified perturbed H2 input with RMSD `0.000101` Ang to the stored TS and gives a 9-frame Sella trajectory in job `454726`. | Fixed. |
| `07_vibration_H2-Au` | Vibration workflow intentionally starts from a TS-like structure. | No change. |
| `08_d2s_Cy-Pt` | D2S path workflow; not the same single-ended initial-guess issue. | No change. |
| `10_irc_H2` | IRC workflow intentionally starts from a TS. | No change. |
| `12_ccqn_H2-Au` | Previously accepted the stored Sella final TS in one frame. Now uses the same perturbed input as `05_sella_H2-Au`, sets `accept_initial_converged: false`, and gives a 14-frame CCQN trajectory in job `454726`. | Fixed. |

## Validation

Slurm job `454726` completed on `4V100PX` node `4v100pxn05` with exit code
`0:0`. ABACUS logs include `RUNNING WITH DEVICE  : GPU / Tesla V100-SXM2-16GB`.
The final Sella/CCQN structures match with RMSD `0.007682` Ang and energy
difference `0.004049` eV, both within the planned thresholds.
