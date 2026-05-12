# ATST-Tools

ATST-Tools is a pip-installable CLI + YAML toolkit for ASE-based atomistic
workflows. Its current 2.0.0 target is to provide a governed, extensible
replacement for the legacy script collection, with ABACUS and DeePMD-kit
calculators exposed through the same `atst run CONFIG.yaml` interface.

## Project Status

- **Current release target**: 2.0.0.
- **Functional baseline**: transition-state, relaxation, vibration, IRC, and
  lightweight trajectory utilities have been refactored from the legacy main
  branch into a package layout.
- **Primary calculator backend**: ABACUS through `abacuslite`; ATST-Tools first
  tries an installed `abacuslite` package and then falls back to the vendored
  snapshot under `src/atst_tools/external/ASE_interface/abacuslite`.
- **Machine-learning potential backend**: DeePMD-kit through its Python ASE
  calculator interface, including optional multi-head model selection.
- **Configuration governance**: user-facing workflow inputs are defined by the
  Pydantic schema in `src/atst_tools/utils/config_schema.py`, and generated
  into user documentation.

## Version Governance

The package version has a single source of truth:
`pyproject.toml` -> `[project].version`.

Runtime entry points read the governed package version through
`atst_tools.package_version()`: source-tree runs read `pyproject.toml`, while
installed-package runs use distribution metadata generated from the same field.
`atst --version` and Python imports therefore do not carry a separate
hard-coded package version. The YAML `config_version` is a separate
schema-compatibility marker and is currently `2.0.0`.

For the 2.0.0 line, PyPI uses the PEP 440 package version `2.0.0`, while
human-facing docs and YAML schema references use `2.0.0`.

## Built-in Workflows

The main execution entry point is:

```bash
atst run CONFIG.yaml
```

Supported `calculation.type` values include:

- `neb`: NEB and DyNEB path optimization with endpoint single-point governance.
- `autoneb`: AutoNEB path refinement and final-chain export support.
- `d2s`: rough NEB plus Dimer/Sella single-ended transition-state search.
- `dimer`: ASE Dimer transition-state search.
- `sella`: Sella transition-state search.
- `relax`: structure optimization.
- `vibration`: ASE vibration and thermochemistry post-processing.
- `irc`: Sella-based intrinsic reaction coordinate tracing.

Lightweight helpers live under:

```bash
atst neb ...
atst dimer ...
atst relax ...
atst vibration ...
atst traj ...
```

## Install

For development:

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install -e .
```

For a distributable artifact:

```bash
python -m build
pip install dist/atst_tools-2.0.0-py3-none-any.whl
```

## Quick Start

```bash
cd examples/06_relax_H2-Au
atst run config.yaml
```

Validate a config without starting a calculation:

```bash
atst run --dry-run examples/06_relax_H2-Au/config.yaml
```

Print a schema-governed template:

```bash
atst run --show-template neb --calculator abacus
```

## Documentation

Start from [docs/index.md](docs/index.md).

Key entry points:

- [User guide](docs/user/USER_GUIDE_CN.md)
- [Configuration reference](docs/user/CONFIG_REFERENCE.md)
- [YAML input variables](docs/user/YAML_INPUT_VARIABLES.md)
- [YAML input governance](docs/developer/YAML_INPUT_GOVERNANCE.md)
- [2.0.0 release notes](docs/releases/RELEASE_NOTES_2.0.0.md)

## License

LGPL-v3 License
