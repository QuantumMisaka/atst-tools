# ATST-Tools Documentation

This is the maintained entry point for ATST-Tools documentation. Files under `.trae/` are temporary working notes and are not part of the formal documentation set.

## Users

- [CLI reference](user/CLI_REFERENCE.md)
- [Configuration reference](user/CONFIG_REFERENCE.md)
- [ABACUSLite wrapper guide](user/ABACUSLITE_WRAPPER_GUIDE.md)
- [Chinese user guide](user/USER_GUIDE_CN.md)
- [Examples overview](../examples/README.md)
- [Maintained atst-cli skill](skills/atst-cli/SKILL.md)

## Developers

- [Documentation architecture](developer/DOCS_ARCHITECTURE.md)
- [Documentation standards](developer/DOCUMENTATION_STANDARDS.md)
- [YAML input governance](developer/YAML_INPUT_GOVERNANCE.md)
- [Handover notes](developer/HANDOVER.md)

## Reports

- [Documentation governance report](reports/DOCUMENTATION_STATUS_REPORT.md)
- [2026-05-15 refactor stage review](reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md)
- [2026-05-15 user experience reinforcement report](reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md)
- [Feature status matrix](reports/FEATURE_STATUS_MATRIX.md)
- [Sella IRC integration review](reports/IRC_INTEGRATION_REVIEW.md)
- [DP validation report for 2.0.0](reports/DP_VALIDATION_2.0.0.md)
- [Examples vs main branch validation on ABACUS LTS 3.10.1](reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md)
  ([metrics JSON](reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.metrics.json))

## Releases

- [2.0.0 release notes](releases/RELEASE_NOTES_2.0.0.md)

## ABACUS Backend Policy

ATST-Tools consumes the official ABACUS ASE interface through `abacuslite`. The resolver first tries an independently installed `abacuslite` package, then falls back to the vendored snapshot under `src/atst_tools/external/ASE_interface/abacuslite`.

The vendored snapshot is kept for 2.0.0 reproducibility on SAI and is not intended to be the only long-term integration mode. The upstream `ASE_interface` snapshot includes its own `pyproject.toml`, so developers can install it separately with `pip install .` when working directly on the backend. When `abacuslite` has a stable release channel, ATST-Tools should move it to an optional dependency or extra and retire the vendored fallback.
