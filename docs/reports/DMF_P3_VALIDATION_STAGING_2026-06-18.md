# DMF P3 Validation Staging 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: Current staging evidence
**Owner**: ATST-Tools maintainers
**Scope**: P3 DMF production-validation harness and runnable case staging

## Summary

P3 requires at least two production-style DMF candidate comparisons against the
existing DP/ABACUS CI-NEB baselines before DMF can be considered for D2S rough
stage integration. This report records the staging infrastructure added for
that validation. It is not runtime completion evidence.

## Added Staging Assets

- `examples/18_dmf_production_validation/config_01_Li-Si_dmf_dp.yaml`
- `examples/18_dmf_production_validation/config_02_H2-Au_dmf_dp.yaml`
- `examples/18_dmf_production_validation/validation_manifest.yaml`
- `examples/18_dmf_production_validation/submit_dmf_dp_rush_1gpu.sbatch`
- `scripts/validate_dmf_candidates.py`
- `src/atst_tools/utils/dmf_validation.py`

The two staged cases reuse existing example endpoints and reference ledgers:

- `01_neb_Li-Si`
- `02_neb_H2-Au`

Both cases are periodic, so the staged DMF configs use the explicit
experimental PBC path:

- `pbc_mode: cartesian_unwrapped`
- `initial_path: linear`
- `remove_rotation_and_translation: false`
- `confirm_pbc_risk: true`

## Report Semantics

`scripts/validate_dmf_candidates.py` reads the manifest and compares each DMF
`tmax` candidate with:

- ABACUS references in `examples/reference_results.json`
- DP references in `examples/dp_reference_results.json`

The generated report records:

- DMF `tmax`, image count, initial path, PBC mode, and IPOPT status
- candidate energy and max force when present in the trajectory
- Cartesian RMSD to ABACUS and DP transition-state structures
- ABACUS and DP barrier baselines

The generated report always keeps `validated_ts: false`. DMF produces a TS
candidate only; refinement plus vibration/IRC validation remain required.

## Verified Locally

The staging assets were checked with:

```bash
/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/atst config validate \
  examples/18_dmf_production_validation/config_01_Li-Si_dmf_dp.yaml --print-normalized
/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/atst config validate \
  examples/18_dmf_production_validation/config_02_H2-Au_dmf_dp.yaml --print-normalized
python scripts/validate_dmf_candidates.py --help
pytest tests/unit/test_dmf_validation.py \
  tests/unit/test_examples_reference_results.py::test_reference_results_cover_current_examples \
  tests/unit/test_examples_dp_reference_results.py::test_dp_reference_results_cover_dp_examples \
  tests/unit/test_examples_dp_reference_results.py::test_dp_reference_results_pin_model_and_artifacts -q
```

## Remaining Work

- Submit `examples/18_dmf_production_validation/submit_dmf_dp_rush_1gpu.sbatch`.
  If `ATST_DMF_ATST` is unset, the job bootstraps a node-local clone of
  `dpeva-dpa4-test`, installs cached `cyipopt`/IPOPT packages with conda
  offline mode, and installs the current checkout before running the staged DMF
  cases.
- Inspect the generated `dmf_validation_report.json`.
- Add at least one ABACUS-side comparison or refinement/validation stage report
  covering barrier, TS mode, endpoint connection, walltime, and failure modes.
- Keep DMF marked experimental until those runtime checks are complete.
