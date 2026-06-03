# CCQN ABACUSLite Validation
**Version**: 2.0.0
**Date**: 2026-05-26
**Status**: Maintained
**Owner**: ATST-Tools maintainers

## Summary

This report records the first CCQN implementation smoke validation in
ATST-Tools. The goal was to confirm that `calculation.type: ccqn` can run
through the existing `CalculatorFactory -> abacuslite -> ABACUS` path on SAI
GPU resources.

## Environment

- Repository branch: `develop`.
- Python environment: `atst-dev`.
- ABACUS module: `abacus/LTSv3.10.1-sm70-auto`.
- ABACUS version: `v3.10.1`.
- Slurm jobs: `454178` for the initial optimizer-step smoke, `454238` for the
  first Sella-final confirmation, and `454726` for the curated perturbed-input
  Sella/CCQN validation.
- Final validation partition/node: `4V100PX`, `4v100pxn05`.
- Final validation state: `COMPLETED`, exit code `0:0`, elapsed `00:36:19`.
- ABACUS device evidence: `RUNNING WITH DEVICE  : GPU / Tesla V100-SXM2-16GB`.

## Input

- Configs: `examples/05_sella_H2-Au/config.yaml` and
  `examples/12_ccqn_H2-Au/config.yaml`.
- Structures: `examples/05_sella_H2-Au/inputs/sella_init.stru` and
  `examples/12_ccqn_H2-Au/inputs/ccqn_init.stru`.
- Perturbation: the H-H distance is increased by `0.002` Ang from
  `1.143598293` Ang to `1.145598293` Ang; the input RMSD to
  `examples/reference_structures/05_sella_H2-Au_final_ts.extxyz` is
  `0.000101` Ang. The Au `FixAtoms` constraints are preserved.
- CCQN settings: `e_vector_method: ic`, `reactive_bonds: "1-2"`,
  `accept_initial_converged: false`, `fmax: 0.05`.
- ABACUS settings include `basis_type: lcao`, `ks_solver: cusolver`,
  `cal_force: 1`, and the same H2/Au Sella example settings.

## Result

The final validation job completed through `atst run config.yaml` and wrote:

- `examples/12_ccqn_H2-Au/ccqn.traj`
- `examples/12_ccqn_H2-Au/ccqn.log`
- `examples/12_ccqn_H2-Au/ccqn_final.extxyz`
- `examples/12_ccqn_H2-Au/run_ccqn/OUT.ABACUS/running_scf.log`

ASE trajectory inspection found 9 Sella frames and 14 CCQN frames, so both
examples now exercise the optimizer rather than accepting an already converged
saddle point. The final structures match within the planned thresholds:

- Sella final energy `-239255.127237` eV and fmax `0.035438` eV/Ang.
- CCQN final energy `-239255.123188` eV and fmax `0.046243` eV/Ang.
- Sella-vs-CCQN final RMSD `0.007682` Ang and energy difference
  `0.004049` eV.
- Sella final RMSD to the stored reference TS: `0.007952` Ang.
- CCQN final RMSD to the stored reference TS: `0.000334` Ang.

The earlier job `454178` used `config_smoke.yaml` and advanced the ASE optimizer
for two CCQN steps from the Sella input STRU. It remains useful as an optimizer
step smoke test. Job `454238` documented that CCQN could accept the existing
Sella final TS, but job `454726` is now the curated example result recorded in
`examples/reference_results.json`.
