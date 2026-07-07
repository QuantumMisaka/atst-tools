# ATST-Tools 2.1.4 Release Notes

**Version**: 2.1.4
**Date**: 2026-07-07
**Branch**: `main`

## Summary

ATST-Tools 2.1.4 publishes the governed `main` branch after the experimental
DMF integration, abacuslite snapshot fixes, the ATST banner command, and CI
hardening work. This release keeps the package metadata aligned with the code
now available on `origin/main`.

## Highlights

- **Experimental DMF workflow**:
  - Adds `calculation.type: dmf` and D2S `rough_method: dmf` support for Direct
    MaxFlux candidate generation.
  - Vendors PyDMF under `src/atst_tools/external/pydmf` for source-tree
    reproducibility.
  - Adds DMF examples, validation utilities, and SAI-oriented production
    validation materials.

- **ABACUS / abacuslite backend fixes**:
  - Preserves abacuslite numbered backups.
  - Validates property keyword conflicts.
  - Removes unsupported dipole property handling.
  - Syncs vendored abacuslite keyword handling and magmom reorder behavior with
    upstream expectations.
  - Adds an abacuslite snapshot drift checker.

- **CLI and user experience**:
  - Adds `atst banner` and shared banner rendering.
  - Documents the banner command in CLI references and operational skill docs.

- **CI and governance**:
  - Runs the full unit suite on pull requests.
  - Adds abacuslite ASE interface checks for vendored backend changes.
  - Adds snapshot drift tests to guard the vendored abacuslite copy.

## Validation

- `conda run -n atst-dev python -c "import atst_tools; print(atst_tools.__version__)"`
- `conda run -n atst-dev pytest tests -q`
- `git diff --check -- pyproject.toml`

## Compatibility

- Package version: `2.1.4`.
- Python support remains `>=3.10`.
- YAML schema migration is not required for existing non-DMF workflows.
- DMF remains experimental. It requires `cyipopt`/IPOPT at runtime and produces
  TS candidates or rough paths, not independently validated transition states.
