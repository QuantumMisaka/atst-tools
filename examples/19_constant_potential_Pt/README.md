# Constant-potential Pt slab validation

This example derives a gate-compensated Pt slab from ABACUS v3.10.1
(`f71921fe848659deac8db319cd4311b55b5ad480`). `reference/` contains the
unmodified Pt slab and 113_PW_gatefield inputs; both originals use PW.
These are validation fixtures, not a claim of converged production accuracy.

## Materialize fixed-electron inputs

From this directory, with an existing Python environment:

```bash
python materialize.py /path/to/new-lcao --basis lcao --electrons 217
python materialize.py /path/to/new-pw --basis pw --electrons 217
python materialize.py /path/to/new-spin --basis lcao --electrons 217 --spin 2
```

The destination must be new. PP/ORB files are copied from `../data`; no upstream
checkout or developer scratch is required. `fixture.json` records provenance,
changes and content hashes. The PP declares 18 valence electrons per Pt, hence
12 Pt have N0=216. The common-Fermi spin fixture does not fix nupdown.

The official slab vacuum is along x. Explicit `efield_dir=0` puts the gate at
x=14 Å and the blocking interval at x=13–15 Å, outside the slab. The original
omits this key and inherits ABACUS's z default. The derived input explicitly
requests potential, charge and force output. LCAO adds the existing Pt orbital;
PW uses the same PP, geometry, mesh and cutoff. Gamma sampling is a bounded
algorithm validation setting; production k-mesh and cutoff convergence remain
system dependent.

## Energy boundary and diagnostics

The historical `reference_fcp` vacuum-aligned energy failed stationarity on
this fixture, including a dipole-corrected case with a flat vacuum potential.
`analyze_scan.py` retains that diagnostic for reproduction. Its former 0.02 eV
threshold was a provisional engineering choice, not a literature criterion.
Neither analysis script now supplies an implicit acceptance threshold or a
top-level scientific `passed` result. Successful exit means the diagnostic
completed. An optional `--tolerance-ev` screen requires `--tolerance-reason`;
it does not certify the physical model.

The explicit `compensated_gate` boundary uses the charge-dependent gate and
dipole terms of ABACUS v3.10.1:

```
mu = E_Fermi + gate_derivative + dipole_derivative
Omega = E_KohnSham - target_mu_ev * (N - N0)
```

This is the conjugate chemical potential of the slab plus compensating plate,
with `reference_electrode: custom`. It is not an automatic SHE/RHE calibration.
Use fixed cell and fixed gate/block/sawtooth parameters, zero external field,
and no implicit solvent. The normal axis may have an in-plane skew cell;
ions must remain outside the gate plane and dipole return region. `nspin=2`
requires a common Fermi level (no explicit `nupdown`).

For example, materialize five equally spaced fixed-N inputs with high-precision
density and explicit dipole parameters, then run ABACUS in the existing site
allocation before analyzing them:

```bash
python materialize.py /path/to/new-lcao --basis lcao --electrons 217 \
  --dipole --density-precision 12
python analyze_compensation.py /path/to/N216.9 /path/to/N216.95 \
  /path/to/N217 /path/to/N217.05 /path/to/N217.1 --output derivatives.json
```

The output reports both centered differences, their residual ratio and a
Richardson extrapolation. The latter assumes a smooth second-order regime;
check a third step and SCF precision to distinguish truncation from numerical
noise. Record raw energies and densities as well as derived results.

For the LCAO dipole fixture, h=0.1/0.05/0.025 electrons gave residuals
−0.775/−0.193/−0.0463 meV; the finest pair extrapolated to +0.00242 meV.
Near-neutral PW with a fixed 2 Ry block gave −3.183/−0.819 meV at
h=0.05/0.025 and an extrapolated −0.0303 meV. These are local consistency
observations, not universal error bounds or basis-convergence evidence.

`validate_forces.py` runs the actual CP calculator at displaced geometries:

```bash
python validate_forces.py /path/to/center-input /path/to/new-force-results \
  --target-mu 15.04597065792631 --initial-electrons 217 \
  --tolerance 1e-6 --surface gate
```

The shown target belongs specifically to the LCAO N=217 dipole fixture; derive
a new target for another boundary or basis. Each displacement reconverges N.
Gate-facing LCAO force residuals were +0.000612/+0.002313 eV/Å at
0.01/0.02 Å. Near-neutral PW residuals were −0.000564/+0.000515 eV/Å and
did not show clean second-order convergence; retain that numerical limitation.
Physical confinement also needs inspection: in the original weak-block PW
N=216.5→217.5 scan, most added charge occupied the gate region. A correct
energy derivative alone cannot establish a physically suitable electrode.

## Public relax/NEB integration inputs

`python materialize_adsorbate.py /path/to/new-endpoints` adds one H to each
of two symmetry-related triangle centers on the same Pt slab. All Pt atoms
(reported indices 1–12) are fixed and H (index 13) is mobile. Both directories
contain the same PP/ORB, cell, 2 Ry blocking potential and explicit dipole
boundary; N0=217 and the initial electronic guess is 217.1. Relax each
endpoint through the public tool before preparing the NEB. This fixture tests
constrained optimization, CP facts persistence and per-image electronic
convergence. Gamma sampling, the fixed thin substrate and the finite image
chain do not establish a production H diffusion barrier.
