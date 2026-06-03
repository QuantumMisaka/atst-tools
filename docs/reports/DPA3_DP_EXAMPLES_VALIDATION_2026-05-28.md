# DPA-3.1 DP Examples Validation

**Version**: 2.0.0
**Date**: 2026-05-28
**Status**: Maintained
**Owner**: ATST-Tools maintainers

## Scope

Validated all `examples/*/config_dp.yaml` cases that call the DeePMD-kit DP
calculator with `temp_repos/dp_model/DPA-3.1-3M.pt`.

The model source is pinned in `examples/dp_model_manifest.json`:

```text
https://store.aissquare.com/models/35b4ce45-4f59-4868-9fd7-a0c0f5ad9464/DPA-3.1-3M.pt
```

The validation ran on SAI Slurm GPU nodes with `partition=4V100PX`,
`qos=flood-1o2gpu`, one GPU per case, and the current checkout forced through
`PYTHONPATH=src`. The model checksum was:

```text
86dd3a804d78ca5d203ebf98747e8f16dff9713ba8950097ceb760b161e19907
```

## Jobs

| Case | Job | Result |
| :--- | :--- | :--- |
| `01_neb_Li-Si` | `461555` | completed |
| `02_neb_H2-Au` | `461556` | completed |
| `03_autoneb_Cy-Pt` | `461654` | completed |
| `04_dimer_CO-Pt` | `461558` | completed |
| `05_sella_H2-Au` | `461559` | completed |
| `06_relax_H2-Au` | `461560` | completed |
| `07_vibration_H2-Au` | `461561` | completed |
| `08_d2s_Cy-Pt` | `461562` | completed |
| `10_irc_H2` | `461563` | completed |
| `11_vibration_ideal_gas_H2` | `461564` | completed |

## Results

The curated machine-readable results are stored in
`examples/dp_reference_results.json`; reviewable structures are stored in
`examples/dp_reference_structures/`.

| Case | Status | DP value | ABACUS comparison |
| :--- | :--- | :--- | :--- |
| `01_neb_Li-Si` | green | barrier `0.723182` eV, projected fmax `0.049976` eV/Ang | `+0.104836` eV; TS RMSD `0.002821` Ang |
| `02_neb_H2-Au` | yellow | barrier `0.647409` eV, projected fmax `0.069072` eV/Ang | `-0.477343` eV; TS RMSD `0.055256` Ang |
| `03_autoneb_Cy-Pt` | yellow | barrier `1.339684` eV, projected fmax `3.816353` eV/Ang | `+0.009614` eV; TS RMSD `0.100587` Ang |
| `04_dimer_CO-Pt` | green | final fmax `0.045176` eV/Ang | TS RMSD `0.033274` Ang |
| `05_sella_H2-Au` | green | final fmax `0.049454` eV/Ang | TS RMSD `0.052622` Ang |
| `06_relax_H2-Au` | green | final fmax `0.049054` eV/Ang | non-TS workflow |
| `07_vibration_H2-Au` | green | 205 valid cache files, ZPE `0.699170` eV | post-processing workflow |
| `08_d2s_Cy-Pt` | yellow | rough barrier `1.929739` eV, dimer fmax `0.052908` eV/Ang | rough barrier `-0.749073` eV; rough TS RMSD `0.150699` Ang |
| `10_irc_H2` | green | 5 IRC frames, final fmax `0.004265` eV/Ang | gas-phase auxiliary workflow |
| `11_vibration_ideal_gas_H2` | yellow | ideal-gas Gibbs free energy `-0.032443` eV | minimal H2 fixture with 5 filtered modes |

## Fixes Made During Validation

Three issues were found by real DP execution and fixed before curating results:

- DP NEB and AutoNEB examples now use `endpoint_singlepoint: always` so endpoint
  energies are recomputed with DP instead of mixing DP image energies with stale
  ABACUS endpoint energies.
- Ideal-gas thermochemistry now passes a non-periodic copy of the input atoms to
  ASE `IdealGasThermo`, so ABACUS `STRU` inputs can be post-processed correctly.
- AutoNEB final image files are frozen with explicit energy and force results
  before writing, so summary commands can read finite final image data without a
  live calculator.

## Model Decision

`DPA-3.1-3M.pt` is worth keeping as an external validation asset because it
executes every DP-backed example and produces physically plausible workflow
references. It is not strong enough to treat as a universal DFT substitute for
strict transition-state convergence in these fixtures: `02_neb_H2-Au`,
`03_autoneb_Cy-Pt`, and `08_d2s_Cy-Pt` are intentionally marked yellow.

Do not add the 45 MiB checkpoint directly to normal git. If the project needs
the checkpoint under version control, use Git LFS or an artifact store and keep
the current checksum pinned in `examples/dp_model_manifest.json` and
`examples/dp_reference_results.json`.
