# Zn Migration NEB ABACUS Validation

**Version:** 2.0.0
**Date:** 2026-05-26  
**Workspace:** `temp_practices/zn_neb_atst_validation`  
**Status:** Smoke jobs moved to `4V100PX`; CI-NEB smoke completed and CI-NEB
production is running.
**Owner:** ATST-Tools maintainers

## Scope

This validation checks whether ATST-Tools can drive ABACUS through the
abacuslite ASE calculator for a user-provided Zn migration pathway from
`Zn1.cif` to `Zn2.cif`, then compare the resulting migration barrier with the
literature reference image in `paper_Zn_neb.jpg`.

The workflow covers:

- CI-NEB through `calculation.type: neb`.
- AutoNEB through `calculation.type: autoneb`.
- D2S through rough DyNEB plus Dimer refinement.

## Input Audit

- `Zn1.cif` and `Zn2.cif` both contain 197 atoms:
  `C174 H12 N8 O2 Zn1`.
- The two endpoints have the same atom order and identical cell.
- The Zn migration displacement is about 6.70 Angstrom under MIC; the remaining
  atom displacements are much smaller.
- `temp_practices` originally contained C/H/Zn PP/ORB files but lacked N/O
  files. N/O files were copied from the user-specified `$HOME/PP_ORB` source:
  `N_ONCV_PBE-1.0.upf`, `O.upf`, `N_gga_8au_100Ry_2s2p1d.orb`, and
  `O_gga_6au_100Ry_2s2p1d.orb`.
- Input checksums are recorded in
  `temp_practices/zn_neb_atst_validation/preflight/input_sha256.txt`.

## Environment Audit

- `atst --version`: `atst 2.0.0`.
- Python environment: `atst-dev`.
- ASE version: `3.28.0`.
- ABACUS backend: vendored abacuslite snapshot.
- SAI module: `abacus/LTSv3.10.1-sm70-auto`.
- ABACUS version: `v3.10.1`.
- Initial target Slurm partition/QOS: `4V100` / `rush-gpu`.
- Runtime target was switched to `4V100PX` after the user reported `4V100`
  was full. The `4V100PX` SAI MPS/rank-map script gives the same
  `ppr:8:l3cache:pe=1` mapping for `--ntasks=16`, `--gpus-per-node=4`.

## Preflight Results

- YAML validation and `atst run --dry-run` passed for smoke and production
  CI-NEB, AutoNEB, and D2S configs.
- `CalculatorFactory` preflight wrote an ABACUS `INPUT` with:
  `ks_solver cusolver`, `basis_type lcao`, `ecutwfc 150`,
  `kspacing 1.0 0.14 0.14`, and absolute PP/ORB directories.
- The generated `STRU` contains C/N/O/H/Zn species and matching orbital files.
- Targeted tests passed:
  `pytest tests/unit/test_abacuslite_profile.py tests/unit/test_neb_endpoints.py tests/unit/test_workflows.py -q -k 'not li_si_zero_endpoint_regression_changes_barrier'`
  reported 53 passing tests.
- The excluded regression depends on `examples/01_neb_Li-Si/neb.traj`, which is
  not present in this working tree.

## Submitted Smoke Jobs

The first smoke submission (`453888`-`453890`) briefly started on `4V100` and
failed before ATST execution because the sbatch scripts did not initialize the
environment modules shell function. The scripts were fixed by sourcing
`/etc/profile.d/modules.sh`, switched to `4V100PX`, and resubmitted.

| Job ID | Workflow | Script | Status |
| --- | --- | --- | --- |
| 453897 | CI-NEB smoke | `jobs/submit_smoke_cineb.sbatch` | Completed on `4V100PX` in 30:04 |
| 453898 | AutoNEB smoke | `jobs/submit_smoke_autoneb.sbatch` | Failed after endpoint single-points due to `results/results/SmokeAutoNEB_iter` path composition |
| 453912 | AutoNEB smoke retry | `jobs/submit_smoke_autoneb.sbatch` | Running on `4V100PX` after path fix |
| 453899 | D2S smoke | `jobs/submit_smoke_d2s.sbatch` | Running on `4V100PX` |

## Production Jobs

| Job ID | Workflow | Script | Status |
| --- | --- | --- | --- |
| 453948 | CI-NEB production | `jobs/submit_cineb.sbatch` | Running on `4V100PX` after CI-NEB smoke passed |

AutoNEB and D2S production jobs remain gated until their smoke jobs prove that
ABACUS starts correctly, writes outputs, and returns through ATST without
calculator-wrapper or Slurm-launch errors.

## Known Notes

- `atst neb make` generated 2-, 4-, and 8-intermediate-image IDPP chains.
  The IDPP helper did not reach its strict internal `1e-3` force target within
  the default 2000 iterations, so the paths should be treated as initial guesses
  rather than converged IDPP products.
- The literature comparison target is a barrier in the rough range
  `1.6-2.0 eV` from panels d/e of `paper_Zn_neb.jpg`; final numerical
  comparison awaits production results.
