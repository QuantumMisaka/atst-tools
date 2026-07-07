# ATST-Tools Documentation

This is the maintained entry point for ATST-Tools documentation. Files under
`.trae/` are temporary working notes and are not part of the formal
documentation set.

## User Path

Use this path when you want to install ATST-Tools, choose an example, validate a
YAML file, and run a workflow.

1. [README quick start](../README.md) for project scope, supported workflows,
   installation, and minimal commands.
2. [Chinese user guide](user/USER_GUIDE_CN.md) for a 10-minute local/SAI
   onboarding path.
3. [Examples overview](../examples/README.md) for runnable NEB, AutoNEB, Dimer,
   Sella, CCQN, D2S, Relax, Vibration, IRC, MD, experimental DMF, DP, and MPI
   examples.
4. [CLI reference](user/CLI_REFERENCE.md) for `atst run`, `atst config`,
   `atst abacus`, and lightweight helper commands.
5. [Configuration reference](user/CONFIG_REFERENCE.md) for hand-written YAML
   semantics and common patterns.
6. [YAML input variables](user/YAML_INPUT_VARIABLES.md) for the generated
   schema field table.
7. [ABACUSLite wrapper guide](user/ABACUSLITE_WRAPPER_GUIDE.md) for ABACUS
   backend boundaries and MPI notes.

## Developer Path

Use this path when you need to modify a workflow, YAML schema, calculator
backend, CLI command, example, or documentation.

1. [README for developers](../README.md#for-developers) for extension points.
2. [Handover checklist](developer/HANDOVER.md) for routine maintenance tasks.
3. [YAML input governance](developer/YAML_INPUT_GOVERNANCE.md) for schema,
   generated docs, examples, and config tests.
4. [Documentation standards](developer/DOCUMENTATION_STANDARDS.md) for metadata,
   lifecycle, report levels, archive rules, and verification commands.
5. [Documentation architecture](developer/DOCS_ARCHITECTURE.md) for directory
   responsibilities and target audiences.
6. [Maintained atst-cli skill](skills/atst-cli/SKILL.md) for operational CLI
   usage and validation snippets.
7. [PyPI release automation](developer/PYPI_RELEASE_AUTOMATION.md) for release
   publishing.

## Project Manager Path

Use this path when you need to judge current feature support, validation
evidence, documentation health, release scope, or cleanup priorities.

1. [Feature status matrix](reports/FEATURE_STATUS_MATRIX.md) for current
   supported, partial, and unsupported capabilities.
2. [Documentation governance report](reports/DOCUMENTATION_STATUS_REPORT.md) for
   the active documentation ledger, report levels, archive state, and
   pending-delete status.
3. [2.1.4 release notes](releases/RELEASE_NOTES_2.1.4.md) for version-level
   delivery scope.
4. Current validation reports linked from the governance report when judging a
   specific feature, backend, or environment.

## Backend Policy

ATST-Tools consumes the official ABACUS ASE interface through `abacuslite`. The
resolver first tries an independently installed `abacuslite` package, then
falls back to the vendored snapshot under
`src/atst_tools/external/ASE_interface/abacuslite`.

The vendored snapshot is kept for 2.0.x reproducibility on SAI and is not
intended to be the only long-term integration mode. When `abacuslite` has a
stable release channel, ATST-Tools should move it to an optional dependency or
extra and retire the vendored fallback.
