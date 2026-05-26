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
  Sella-matching example confirmation.
- Final confirmation partition/node: `4V100PX`, `4v100bkn01`.
- Final confirmation state: `COMPLETED`, exit code `0:0`, elapsed `00:01:55`.
- ABACUS device evidence: `RUNNING WITH DEVICE  : GPU / Tesla V100-SXM2-32GB`.

## Input

- Config: `examples/12_ccqn_H2-Au/config.yaml`.
- Structure: `examples/reference_structures/05_sella_H2-Au_final_ts.extxyz`.
- CCQN settings: `e_vector_method: ic`, `reactive_bonds: "1-2"`,
  `accept_initial_converged: true`, `fmax: 0.05`.
- ABACUS settings include `basis_type: lcao`, `ks_solver: cusolver`,
  `cal_force: 1`, and the same H2/Au Sella example settings.

## Result

The final confirmation job completed through `atst run config.yaml` and wrote:

- `examples/12_ccqn_H2-Au/ccqn.traj`
- `examples/12_ccqn_H2-Au/ccqn.log`
- `examples/12_ccqn_H2-Au/ccqn_final.extxyz`
- `examples/12_ccqn_H2-Au/run_ccqn/OUT.ABACUS/running_scf.log`

ASE trajectory inspection found 1 frame because the input is already a
force-converged Sella final TS and `accept_initial_converged` is enabled. The
CCQN final structure matches the Sella reference structure with:

- final energy `-239255.122869` eV;
- final fmax `0.048260` eV/Ang;
- RMSD to `examples/reference_structures/05_sella_H2-Au_final_ts.extxyz`:
  `0.000000000` Ang.

The earlier job `454178` used `config_smoke.yaml` and advanced the ASE optimizer
for two CCQN steps from the Sella input STRU. It remains useful as an optimizer
step smoke test, while job `454238` is the curated example result recorded in
`examples/reference_results.json`.
