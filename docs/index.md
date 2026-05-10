# ATST-Tools Documentation

This is the maintained entry point for ATST-Tools documentation. Files under `.trae/` are temporary working notes and are not part of the formal documentation set.

## Users

- [CLI reference](user/CLI_REFERENCE.md)
- [Configuration reference](user/CONFIG_REFERENCE.md)
- [Chinese user guide](user/USER_GUIDE_CN.md)
- [Examples overview](../examples/README.md)

## Developers

- [Refactoring guide](developer/REFACTORING_GUIDE.md)
- [Documentation architecture](developer/DOCS_ARCHITECTURE.md)
- [Documentation standards](developer/DOCUMENTATION_STANDARDS.md)
- [Handover notes](developer/HANDOVER.md)
- [Development plans](developer/plans/)

## Reports

- [2026-05-10 review](reports/REVIEW_2026-05-10_2000.md)
- [Refactor acceptance report](reports/REFACTORING_ACCEPTANCE_REPORT.md)
- [2.0.0-rc acceptance notes](reports/ACCEPTANCE_2.0.0rc_CN.md)
- [Feature status matrix](reports/FEATURE_STATUS_MATRIX.md)
- [Documentation status report](reports/DOCUMENTATION_STATUS_REPORT.md)

## Releases

- [2.0.0-rc release notes](releases/RC_RELEASE_NOTES_2.0.0-rc.md)

## Archive

- [Legacy evaluation](archive/LEGACY_EVALUATION.md)
- [Code review archive](archive/CODE_REVIEW_20260227.md)

## ABACUS Backend Policy

ATST-Tools consumes the official ABACUS ASE interface through `abacuslite`. The resolver first tries an independently installed `abacuslite` package, then falls back to the vendored snapshot under `src/atst_tools/external/ASE_interface/abacuslite`.

The vendored snapshot is kept for 2.0.0-rc reproducibility on SAI and is not intended to be the only long-term integration mode. The upstream `ASE_interface` snapshot includes its own `pyproject.toml`, so developers can install it separately with `pip install .` when working directly on the backend. When `abacuslite` has a stable release channel, ATST-Tools should move it to an optional dependency or extra and retire the vendored fallback.
