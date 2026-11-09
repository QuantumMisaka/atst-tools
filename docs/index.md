# ATST-Tools Documentation

Start with the repository [README](../README.md) for installation and a first
example. Use this index to choose a user, developer or project-status path.

The primary documentation is in English. For a complete Chinese walkthrough,
from installation to result inspection and troubleshooting, use the
[中文用户指南](user/USER_GUIDE_CN.md).

## Start Here

| Goal | Entry |
| --- | --- |
| Run a first calculation and inspect its results | [Examples usage guide](../examples/README.md#usage) |
| Follow a complete walkthrough in Chinese | [中文用户指南](user/USER_GUIDE_CN.md) |
| Choose a workflow and sample inputs | [Examples overview](../examples/README.md) |
| Python or agent integration | [Python API reference](user/PYTHON_API_REFERENCE.md) |
| Contribute code | [Developer handover](developer/HANDOVER.md) |
| Check current support and validation limits | [Feature status matrix](reports/FEATURE_STATUS_MATRIX.md) |

## User Path

- [README quick start](../README.md)
- [Chinese user guide](user/USER_GUIDE_CN.md)
- [Examples overview](../examples/README.md)
- [CLI reference](user/CLI_REFERENCE.md)
- [Stable Python API reference](user/PYTHON_API_REFERENCE.md)
- [Configuration reference](user/CONFIG_REFERENCE.md)
- [YAML input variables](user/YAML_INPUT_VARIABLES.md)
- [ABACUSLite wrapper guide](user/ABACUSLITE_WRAPPER_GUIDE.md)

## Developer Path

- [Source architecture](../src/atst_tools/README.md)
- [Developer handover](developer/HANDOVER.md)
- [Example validation operations](developer/EXAMPLE_VALIDATION_OPERATIONS.md)
- [YAML input governance](developer/YAML_INPUT_GOVERNANCE.md)
- [Documentation guide](developer/DOCUMENTATION.md)
- [Governance and release gates](developer/GOVERNANCE_AND_RELEASE_GATES.md)
- [PyPI release automation](developer/PYPI_RELEASE_AUTOMATION.md)
- [Maintained atst-cli skill](skills/atst-cli/SKILL.md)

## Status and Releases

- [Feature status matrix](reports/FEATURE_STATUS_MATRIX.md): the current
  supported/partial/experimental boundary and per-capability validation scope.
- [2.3.3 release notes](releases/RELEASE_NOTES_2.3.3.md): transition candidate
  selection, socket-driver boundary and artifact verification.
- [2.3.1 release notes](releases/RELEASE_NOTES_2.3.1.md): FCP reference parity
  and installed-package verification.
- [2.3.0 release notes](releases/RELEASE_NOTES_2.3.0.md): external-backend migration release.
- Historical notes: [2.2.5](archive/releases/RELEASE_NOTES_2.2.5.md),
  [2.2.4](archive/releases/RELEASE_NOTES_2.2.4.md).

Validation reports under `reports/` are evidence, not a required reading path.
Start from the feature matrix and follow the relevant report only when needed.

## Backend

ATST-Tools uses the installed `abacuslite` package as its ABACUS ASE backend.
Input/output setup, frame matching and parallel execution are described in the
[ABACUSLite wrapper guide](user/ABACUSLITE_WRAPPER_GUIDE.md).
Contributor responsibilities are maintained in [AGENTS.md](../AGENTS.md).
