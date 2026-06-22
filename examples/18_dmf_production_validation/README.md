# DMF Production Validation Staging

This directory stages the P3 DMF validation cases. It does not mark DMF as
production supported.

The two initial cases reuse existing ATST reference systems:

- `01_neb_Li-Si`
- `02_neb_H2-Au`

Both are periodic, so the DMF configs intentionally use the experimental
`pbc_mode: cartesian_unwrapped` path with `initial_path: linear`,
`remove_rotation_and_translation: false`, and `confirm_pbc_risk: true`.

Run on a SAI GPU node, not on a login node:

```bash
cd examples/18_dmf_production_validation
sbatch submit_dmf_dp_rush_1gpu.sbatch
```

If `ATST_DMF_ATST` is unset, the sbatch script creates a node-local clone of
`dpeva-dpa4-test`, installs cached `cyipopt`/IPOPT packages with conda offline
mode, installs the current checkout in editable mode, and uses that `atst`
executable. Set `ATST_DMF_ATST=/path/to/atst` to reuse a prebuilt
compute-node-visible environment.

After the DMF jobs complete, the submission script writes
`dmf_validation_report.json` by comparing the DMF `tmax` candidates with
`examples/reference_results.json` and `examples/dp_reference_results.json`.
The report records candidate comparison evidence only.

An additional P4 smoke path exercises experimental D2S `rough_method: dmf`
followed by a short Sella refinement:

```bash
cd examples/18_dmf_production_validation
sbatch submit_d2s_dmf_sella_dp_rush_1gpu.sbatch
```

This verifies runtime integration from DMF candidate generation into an
existing single-ended optimizer. It is still not full production TS validation:
longer refinement, IRC endpoint validation, and ABACUS comparison remain
required before treating DMF-D2S as a supported production path.

The focused P4 vibration path extends that smoke with auto-selected local
vibration indices after Sella:

```bash
cd examples/18_dmf_production_validation
sbatch submit_d2s_dmf_sella_vib_dp_rush_1gpu.sbatch
```

This checks for one local imaginary mode in the selected `tmax` neighborhood.
It still does not validate IRC endpoint connection or ABACUS agreement.

The focused P4 endpoint-connection path derives local descent-IRC modes from
the DMF path around `tmax`, runs both descent directions, and compares the
relaxed branch endpoints against the original endpoints:

```bash
cd examples/18_dmf_production_validation
sbatch submit_d2s_dmf_irc_dp_rush_1gpu.sbatch
```

This is still DP-backed experimental evidence. ABACUS comparison remains
required before treating DMF-D2S as a supported production path.

The ABACUS single-point comparison path evaluates the refined DMF-D2S TS
candidates with ABACUS LTS 3.10.1 and compares barrier, reference-TS RMSD, and
candidate force:

```bash
cd examples/18_dmf_production_validation
sbatch submit_d2s_dmf_abacus_compare_rush_gpu.sbatch
```

Li-Si passed this comparison in job `526738`, while H2-Au initially failed the
raw ABACUS force gate. The targeted H2-Au corrective ABACUS Sella run is staged
as:

```bash
cd examples/18_dmf_production_validation
sbatch submit_h2au_dmf_abacus_sella_rush_gpu.sbatch
```

After that refinement, rerun the refined comparison path:

```bash
cd examples/18_dmf_production_validation
sbatch submit_d2s_dmf_abacus_refined_compare_rush_gpu.sbatch
```

Job `527093` passed the refined two-case comparison. For constrained slab
systems, the force gate uses the collected ABACUS single-point forces after ASE
constraints are applied, so fixed Au slab forces are not counted as free
optimization degrees of freedom.

The focused DMF risk-review path constructs intentionally problematic variants
from the H2-Au and Li-Si examples:

```bash
cd examples/18_dmf_production_validation
sbatch submit_dmf_risk_cases_dp_rush_1gpu.sbatch
```

It writes `dmf_risk_case_report.json`. Job `529051` confirmed three H2-Au
runtime risks with 600 second per-case timeouts: wrapped final image, swapped H
indices, and inconsistent fixed-slab endpoint. The PBC `cartesian_unwrapped` +
`cfbenm` case is rejected by schema validation, and existing successful
DMF-D2S `tmax` outputs did not exceed the rounded-image RMSD threshold.
