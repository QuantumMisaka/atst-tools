# Pd(111) TS to flat CO2 endpoint regression

These 39-atom geometries reproduce a periodic-image bookkeeping defect in
`Fast_IDPPSolver`: four intermediate images could compress Pd16–Pd28 to
0.205 Å while the fixed translation made the solver measure 8.302 Å.
Atom labels above are 1-based. The cell is skewed and the final endpoint has
wrapped slab atoms. Keep the original atom ordering, Cartesian coordinates,
cell, PBC and fixed-atom constraints.

Source: the maintainer's SAI-galileo02 run on 2026-11-12, under
`/org/galileo-group/galileouser02/adam-cli-local/runs/paimon-paper-pd-co-d2s-clean-20261112-v1/bde8a43192f04d0495292c6b62d88ff9/task/PdCO_D2S_clean/PdCO_NEB_explore_flatFS/prepared_endpoints/`:

- `ts_guess.extxyz`: `ts_guess/ts_guess.extxyz`.
- `final.extxyz`: `final/final.extxyz`.
- `init.extxyz`: `init/init.extxyz`; added for ordinary two-endpoint generation
  and retained-TS sampling regression.

The fixtures retain only geometry and constraints; cached energies, forces,
magnetic initialization and frame-role metadata were removed. Replaying the
IDPP solver needs no calculator or DFT executable. The regression asserts
convergence and Pd–Pd separation above 2 Å rather than an exact trajectory.
The baseline and repaired measurements are recorded in the
[repair report](../../../docs/reports/IDPP_DYNAMIC_MIC_2026-11-12.md).
