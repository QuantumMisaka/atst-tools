# Cy-Pt AutoNEB Main-Aligned ABACUS LTS 3.10.1 Validation

**Date**: 2026-05-19  
**Case**: `examples/03_autoneb_Cy-Pt`  
**Environment**: SAI `4V100`, `abacus/LTSv3.10.1-sm70-auto`, `atst-dev`, ASE `3.28.0`  
**Acceptance target**: final forward barrier within `0.1 eV` of the `main` branch baseline `1.327886 eV`.

## Summary

The example configuration has been realigned with the proven `main` branch
AutoNEB and ABACUS settings where ABACUS LTS 3.10.1 supports them.

Confirmed identical inputs:

- `examples/03_autoneb_Cy-Pt/inputs/init_neb_chain.traj` has the same git blob
  as `main:examples/Cy-Pt@graphene/autoneb/init_neb_chain.traj`:
  `f7041d4b9bdf19b75b7f2964721423cf624e2536`.
- C/H/Pt pseudopotential and orbital files in `examples/data` match the `main`
  branch files by `sha256`.

Confirmed parameter alignment:

- AutoNEB uses `fmax: [0.20, 0.05]`, `n_simul: 4`, `n_max: 10`,
  `algorism: improvedtangent`, `optimizer: FIRE`, `climb: true`, and
  `maxsteps: 10000`.
- ABACUS uses the main settings `ecutwfc: 100`, `ks_solver: genelpa`,
  `smearing_method: gaussian`, `scf_nmax: 100`, `init_wfc: atomic`,
  `init_chg: atomic`, `out_chg: -1`, `out_mul: 0`, `out_bandgap: 0`,
  and `out_wfc_lcao: 0`.
- Legacy `xc: pbe` was replaced by ABACUS LTS 3.10.1-compatible
  `dft_functional: pbe`. A dry-run abacuslite INPUT check confirmed that
  `dft_functional pbe` is written and no `xc` key is written.

The full validation target was **not met**. Two SAI runs with main-aligned
parameters did not reach a complete 10-image AutoNEB final path. Both were
stopped after the first AutoNEB iteration showed no practical path toward the
`fmax=0.20 eV/Ang` stage threshold.

## Updated Example Configuration

`examples/03_autoneb_Cy-Pt/config.yaml` now records the main-aligned LTS 3.10.1
input deck. Because the current `atst-dev` environment has no `mpi4py`, current
ATST cannot reproduce the legacy `main` MPI-launched Python image-parallel model
exactly; ordinary `atst run` reports ASE `world.size == 1`. The example therefore
keeps `n_simul: 4` and ABACUS `mpi: 4`, but current image execution remains
serial unless the Python/MPI environment is upgraded.

The example keeps `optimizer_kwargs.downhill_check: true` as an allowed FIRE
stabilization setting. The first validation branch also tested `maxstep: 0.05`,
but that made the first AutoNEB iteration plateau.

## SAI Runs

| Run | Workspace | Job | Stabilization | State | Runtime | Result |
|---|---|---:|---|---|---:|---|
| maxstep branch | `temp_sai_cypt_main_aligned_20260519` | `424588` | `downhill_check: true`, `maxstep: 0.05` | `CANCELLED` | `02:03:03` | Plateau in iteration 001 at `fmax ~4.296 eV/Ang` |
| downhill-only branch | `temp_sai_cypt_main_aligned_downhill_20260519` | `424969` | `downhill_check: true` | `CANCELLED` | `01:20:39` | Plateau in iteration 001 at `fmax ~3.21 eV/Ang` |

Both jobs loaded:

```text
abacus/LTSv3.10.1-sm70-auto
```

The generated ABACUS INPUT for real image calculations included:

```text
dft_functional pbe
ks_solver genelpa
smearing_method gaussian
scf_nmax 100
init_wfc atomic
init_chg atomic
out_chg -1
```

## Iteration 001 Evidence

### Branch 1: `downhill_check + maxstep=0.05`

This branch avoided catastrophic divergence but stalled. The last observed
records were:

| Step | Energy/eV | fmax/eV/Ang |
|---:|---:|---:|
| 13 | -11864.706073 | 4.306753 |
| 14 | -11864.706337 | 4.295525 |
| 15 | -11864.706262 | 4.298734 |
| 16 | -11864.706328 | 4.295926 |
| 17 | -11864.706309 | 4.296729 |

This is far from the main-aligned first-stage threshold `0.20 eV/Ang`.

### Branch 2: `downhill_check` only

Removing `maxstep` allowed larger FIRE moves, but the first iteration still did
not approach convergence:

| Step | Energy/eV | fmax/eV/Ang |
|---:|---:|---:|
| 7 | -11864.687360 | 3.367872 |
| 8 | -11864.689276 | 3.214751 |
| 9 | -11864.689066 | 3.242125 |
| 10 | -11864.689255 | 3.213467 |
| 11 | -11864.689211 | 3.210918 |

This branch also did not enter normal AutoNEB image insertion. It remained at
the initial six `run_autoneb*.traj` files.

## Assessment

The key-parameter-aligned LTS 3.10.1 runs did not produce a final path, so no
barrier can be compared against the `main` branch within the requested `0.1 eV`
threshold.

The new evidence narrows the issue:

1. `xc: pbe` can be replaced by `dft_functional: pbe` for ABACUS LTS 3.10.1,
   and abacuslite writes the supported key correctly.
2. The initial chain and C/H/Pt PP/ORB files are not the source of the mismatch;
   they are byte-identical to the `main` branch inputs.
3. FIRE stabilization changes the failure mode from explosive divergence to
   plateauing, but it still does not recover the legacy main convergence path.
4. The remaining non-aligned execution-stack differences are substantial:
   ABACUS 3.10.1 vs the legacy ABACUS 3.4.2-era run, abacuslite vs legacy
   `ase-abacus`, and serial current ATST execution vs MPI-launched Python in
   `main`.

## Follow-Up

To further isolate the gap, the next useful experiment is not another long
single-branch rerun. It should first restore MPI Python image parallelism in
`atst-dev` or provide an equivalent current ATST launch path where ASE
`world.size == 4`. After that, rerun the same main-aligned LTS 3.10.1 config.

If MPI Python remains unavailable, the current branch can keep the updated
example as the closest LTS-compatible main-aligned input deck, but documentation
should state that it has not reproduced the `main` branch barrier under the
current server stack.
