# Validation Report for atst-tools and abacuslite Integration

**Date:** 2026-05-10  
**Environment:** `atst-dev` (Conda)  
**ABACUS Module:** `abacus/LTSv3.10.1-sm70-auto`  
**Git Branch:** `refactor/unify-structure`

## 1. Environment Status

- **Conda Environment**: `atst-dev` exists and is the project test environment.
- **Python Imports**:
  - `atst_tools`: PASSED
  - vendored `abacuslite`: PASSED via `src/atst_tools/external/ASE_interface`
  - `deepmd`: PASSED (`deepmd-kit` is installed in `atst-dev`)

## 2. abacuslite Interface Verification

Location: `src/atst_tools/external/ASE_interface`

The complete upstream `ASE_interface` snapshot is now copied into this repository.
Its runtime package is imported through `atst_tools.external.ASE_interface.abacuslite`.

## 3. atst-tools Examples Verification

Location: `examples/`

### ABACUS Calculator (DFT)

- **Status**: Slurm smoke validation started on SAI
- **Cases**: all tracked `examples/*/config.yaml`
- **SAI note**: LCAO examples use `ks_solver: cusolver` for GPU nodes.
- **Completed evidence**: jobs `394339`, `394340`, `394341`, `394342`, and
  `394344` completed with exit code `0:0`.
- **In-flight evidence**: job `394343` is still running. Failed jobs `394345`
  and `394346` were diagnosed, fixed, and resubmitted as `394371` and `394370`.
  The rerun jobs are running.

### DP Calculator (Deep Potential)

- **Status**: Deferred
- **Reason**: Project priority is ABACUS-first. DP imports and config parsing are covered; real DP workflow validation follows after ABACUS examples pass.

## 4. Completed Local Checks

- `atst-run --help`: PASSED
- `pytest tests -q`: PASSED
- `python -m compileall -q src/atst_tools tests`: PASSED
- Example YAML parse and validation tests: PASSED

## 5. Next Steps

1. Let SAI jobs `394343`, `394370`, and `394371` finish.
2. Update `docs/REFACTORING_ACCEPTANCE_REPORT.md` with their final pass/fail status.
