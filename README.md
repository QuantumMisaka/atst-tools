# ATST-Tools

[![Version](https://img.shields.io/badge/version-2.1.4-blue)](pyproject.toml)
[![Unit test coverage](https://img.shields.io/badge/unit%20test%20coverage-66%25-yellowgreen)](#validation)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-LGPL--v3-blue)](#license)

ATST-Tools is a pip-installable **ASE transition-state workflow toolkit** for
ABACUS and DeePMD-kit calculators. It turns the project's legacy script
collection into one governed command-line interface:

```bash
atst run CONFIG.yaml
```

Use it when you want repeatable NEB, AutoNEB, Dimer, Sella, CCQN, D2S,
relaxation, vibration, IRC, MD, or experimental DMF calculations driven by YAML
instead of one-off Python scripts.

## At A Glance

| Area | Current 2.1.4 status |
| :--- | :--- |
| Package | Installable Python package from PyPI with the `atst` console command. |
| Main interface | `atst run CONFIG.yaml` for all calculator-backed workflows. |
| Lightweight tools | `atst config`, `atst abacus`, `atst neb`, `atst traj`, `atst dimer`, `atst relax`, `atst vibration`. |
| Calculators | ABACUS through `abacuslite`; DeePMD-kit through `deepmd.calculator.DP`. |
| Configuration | Pydantic-governed YAML schema with generated user documentation. |
| Validation | Unit tests, example dry-runs, SAI ABACUS evidence, and DP/DPA smoke validation. |
| Release | `2.1.4`, documented in [release notes](docs/releases/RELEASE_NOTES_2.1.4.md). |

## What You Can Run

| `calculation.type` | Workflow | Notes |
| :--- | :--- | :--- |
| `neb` | NEB / DyNEB | Endpoint single-point governance is enabled by default. |
| `autoneb` | AutoNEB | Adaptive image insertion plus final-chain post-processing. |
| `d2s` | Double-ended to single-ended TS search | Rough NEB followed by Dimer, Sella, or CCQN. |
| `dimer` | ASE Dimer | Single-ended transition-state search. |
| `sella` | Sella saddle search | Uses the external `sella` package. |
| `ccqn` | CCQN saddle search | Cone-shaped constrained quasi-Newton TS optimization. |
| `relax` | Structure optimization | ASE optimizer based relaxation. |
| `vibration` | Vibrations and thermochemistry | Harmonic and ideal-gas helpers. |
| `irc` | Sella IRC | Sella-backed IRC orchestration with controlled boundary diagnostics. |
| `md` | Molecular dynamics | ASE-driven MD with ABACUS/DP calculators, or ABACUS native MD input/run/output orchestration. |
| `dmf` | Direct MaxFlux | Experimental TS candidate/path optimizer; non-periodic first and not a validated TS result. |

Local pre/post-processing commands are intentionally lightweight. They do not
construct calculators or submit expensive calculations:

```bash
atst neb make ...
atst neb post ...
atst traj collect ...
atst traj transform ...
atst dimer make-from-neb ...
atst relax post ...
atst vibration post ...
atst config validate ...
atst abacus prepare ...
atst abacus collect ...
```

## Installation

### From PyPI (Recommended)

```bash
pip install atst-tools
```

ATST-Tools requires Python 3.10 or newer. Sella-backed workflows install
`sella>=2.5` with the default package because Sella is a first-class workflow
backend.

Optional feature stacks are installed explicitly:

```bash
pip install "atst-tools[plot]"      # NEB plotting helpers
pip install "atst-tools[dp]"        # DeePMD-kit calculator workflows
pip install "atst-tools[parallel]"  # MPI image-level NEB/AutoNEB
```

### Development Install

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install -e ".[dev]"
```

### Wheel Install

Build a local release artifact:

```bash
python -m build
pip install dist/atst_tools-2.1.4-py3-none-any.whl
```

ATST-Tools itself installs the Python workflow layer. Real calculations also
need the selected calculator runtime:

- **ABACUS**: an executable ABACUS installation plus pseudopotential/orbital
  files referenced by YAML.
- **DP / DeePMD-kit**: install `atst-tools[dp]` or provide a compatible
  DeePMD-kit Python installation, plus a model file outside git-tracked paths.
- **MPI image parallelism**: install `atst-tools[parallel]` in an MPI-compatible
  Python environment and launch ATST with one Python rank per active image.
- **DMF**: ATST-Tools vendors PyDMF, but runtime still requires `cyipopt` and
  IPOPT, for example from conda-forge.

## Quick Start

Choose the path that matches what you need:

| Need | Start here |
| :--- | :--- |
| Run a workflow in 10 minutes | [Chinese user guide](docs/user/USER_GUIDE_CN.md) |
| Pick an example | [Examples overview](examples/README.md) |
| Check supported features | [Feature status matrix](docs/reports/FEATURE_STATUS_MATRIX.md) |
| Look up YAML semantics | [Configuration reference](docs/user/CONFIG_REFERENCE.md) |
| Look up every schema field | [YAML input variables](docs/user/YAML_INPUT_VARIABLES.md) |
| Use CLI helper commands | [CLI reference](docs/user/CLI_REFERENCE.md) |
| Embed a workflow in Python | [Stable Python API reference](docs/user/PYTHON_API_REFERENCE.md) |
| Browse all documentation paths | [Documentation index](docs/index.md) |

Run a small relaxation example:

```bash
cd examples/06_relax_H2-Au
atst run config.yaml
```

Validate an input without launching the calculation:

```bash
atst run --dry-run examples/06_relax_H2-Au/config.yaml
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
```

Embed the same schema validation from Python when a calling program needs a
structured result rather than terminal output:

```python
from atst_tools.api import validate_config

config = validate_config("examples/06_relax_H2-Au/config.yaml")
print(config["calculation"]["type"])
```

Use CLI/YAML for normal interactive or scheduled calculations; use the API for
embedding. The [stable Python API reference](docs/user/PYTHON_API_REFERENCE.md)
defines result ownership, MPI, artifacts, and calculator delegation.

Print a schema-governed template:

```bash
atst run --show-template neb --calculator abacus
atst run --show-template neb --calculator dp
atst run --show-template dmf --calculator dp
```

List available workflow types:

```bash
atst run --list-types
```

Print the project banner and contributor credits:

```bash
atst banner
```

## Minimal YAML Shape

Every production workflow uses the same top-level structure:

```yaml
calculation:
  type: neb
  init_chain: inputs/init_neb_chain.traj
  fmax: 0.05
  max_steps: 100
  climb: true
  two_stage: true
  stage1_steps: 20
  stage1_fmax: 0.20

calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_neb
    kpts: [2, 2, 2]
    parameters:
      calculation: scf
      ecutwfc: 100
      basis_type: lcao
```

The governed schema defines defaults, types, and descriptions for user-facing
inputs. See [YAML input variables](docs/user/YAML_INPUT_VARIABLES.md) for the
generated reference and [configuration reference](docs/user/CONFIG_REFERENCE.md)
for hand-written guidance.

## Calculator Backends

### ABACUS

ABACUS is integrated through `abacuslite`. ATST-Tools first tries an installed
`abacuslite` package and then falls back to the vendored snapshot under
`src/atst_tools/external/ASE_interface/abacuslite`.

Typical example files use:

```yaml
calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    pseudo_dir: ../data
    orbital_dir: ../data
```

ATST-Tools is a layered `abacuslite` wrapper. Calculator-backed workflows such
as NEB, D2S, Dimer, Sella, CCQN, Relax, Vibration, and IRC still run through
`atst run CONFIG.yaml`; local ABACUS helpers support safe input preparation and
result collection:

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
atst abacus collect run_neb --output abacus_results.json
```

These helper commands do not run ABACUS and do not submit Slurm jobs.

### DeePMD-kit / DP

DP support uses the official ASE calculator entry point,
`deepmd.calculator.DP`. DeePMD-kit detects the model backend from the model
file. Multi-head DPA/DPA3 models are configured through `calculator.dp.head`.

```yaml
calculator:
  name: dp
  dp:
    model: ../../temp_repos/dp_model/DPA-3.1-3M.pt
    head: Omat24
    omp: 4
    share_calculator: true
```

The 2.0.0 DP validation used DPA-3.1-3M with the `Omat24` head. The pinned
download source, checksum, expected size, and local path are recorded in
`examples/dp_model_manifest.json`. Model files and runtime outputs are
intentionally not tracked by git.

```bash
python scripts/download_dp_model.py
python scripts/download_dp_model.py --check-only
```

## Examples

The [examples directory](examples/README.md) is the fastest way to learn the
project:

| Directory | Workflow focus |
| :--- | :--- |
| `examples/01_neb_Li-Si` | Quick NEB smoke case. |
| `examples/02_neb_H2-Au` | Surface NEB example. |
| `examples/03_autoneb_Cy-Pt` | AutoNEB workflow. |
| `examples/04_dimer_CO-Pt` | Dimer transition-state search. |
| `examples/05_sella_H2-Au` | Sella saddle search. |
| `examples/06_relax_H2-Au` | Geometry relaxation. |
| `examples/07_vibration_H2-Au` | Surface vibration analysis. |
| `examples/08_d2s_Cy-Pt` | Rough NEB plus single-ended TS search. |
| `examples/09_lightweight_cli` | Local helper command examples. |
| `examples/10_irc_H2` | IRC YAML examples. |
| `examples/11_vibration_ideal_gas_H2` | Ideal-gas thermochemistry example. |
| `examples/12_ccqn_H2-Au` | CCQN single-ended saddle search. |
| `examples/13_neb_parallel_Cy-Pt` | SAI NEB image-parallel example. |
| `examples/14_autoneb_parallel_Cy-Pt` | SAI AutoNEB image-parallel example. |
| `examples/15_md_Li-Si` | ASE-driven and ABACUS-native MD templates starting from the `01_neb_Li-Si` initial structure. |

Each calculation example uses `config.yaml` for ABACUS and, where available,
`config_dp.yaml` for DP.

## Validation

The 2.1.4 README badges reflect the current governed project state:

- Version badge: `pyproject.toml` -> `[project].version` -> `2.1.4`.
- Unit test coverage badge: measured with
  `coverage run --source=src/atst_tools -m pytest tests -q`, then reported with
  `coverage report --omit='src/atst_tools/external/*'`.
- Current first-party unit test coverage: `66%`.
- Full source-tree coverage including the vendored `abacuslite` snapshot:
  `43%`.

The vendored `src/atst_tools/external/ASE_interface` tree is kept for ABACUS
backend reproducibility and is not treated as first-party ATST-Tools coverage.
Pull requests run the maintained unit suite through `.github/workflows/tests.yml`.
Changes touching the vendored ABACUS ASE interface also run
`.github/workflows/abacuslite-ase-interface.yml`, which checks ATST regression
tests, package-mode abacuslite unittests, and snapshot drift against the pinned
`deepmodeling/abacus-develop` ASE interface reference.

## For Developers

The main extension points are deliberately small:

| Task | Start here |
| :--- | :--- |
| Add or change YAML inputs | `src/atst_tools/utils/config_schema.py` |
| Regenerate YAML docs | `python -m atst_tools.utils.config_docs` |
| Add a calculator backend | `src/atst_tools/calculators/` |
| Add an `atst run` workflow | `src/atst_tools/scripts/main.py` and `src/atst_tools/workflows/` |
| Add lightweight CLI commands | `src/atst_tools/scripts/cli.py` plus focused command modules |
| Add examples | `examples/<case>/config.yaml` and curated `inputs/` |

Developer governance starts from these maintained entry points:

- [Documentation index](docs/index.md)
- [Handover checklist](docs/developer/HANDOVER.md)
- [YAML input governance](docs/developer/YAML_INPUT_GOVERNANCE.md)
- [Documentation standards](docs/developer/DOCUMENTATION_STANDARDS.md)
- [Documentation architecture](docs/developer/DOCS_ARCHITECTURE.md)
- [ABACUS wrapper guide](docs/user/ABACUSLITE_WRAPPER_GUIDE.md)
- [Maintained atst-cli skill](docs/skills/atst-cli/SKILL.md)

Project status and validation entry points:

- [Feature status matrix](docs/reports/FEATURE_STATUS_MATRIX.md)
- [Documentation governance report](docs/reports/DOCUMENTATION_STATUS_REPORT.md)
- [DP validation report](docs/reports/DP_VALIDATION_2.0.0.md)
- [Issue #25 AutoNEB fmax fix report](docs/reports/ISSUE_25_AUTONEB_FMAX_FIX_REPORT_2026-05-22.md)
- [MPI image-level NEB parallel summary](docs/reports/MPI4PY_ASE_NEB_PARALLEL_ATST_SUMMARY_2026-05-27.md)

## Version Governance

The package version has one source of truth:

```text
pyproject.toml -> [project].version
```

Runtime entry points read that governed package version through
`atst_tools.package_version()`. Source-tree runs read `pyproject.toml`, while
installed-package runs use distribution metadata generated from the same field.
There is no YAML-level `config_version`; user YAML is governed directly by the
installed package schema, and unknown top-level fields are rejected.

## Project Boundary

ATST-Tools owns workflow orchestration, YAML validation, calculator construction,
trajectory naming, restart handling, ABACUS input/output helpers, examples, and
documentation. Numerical engines remain external:

- ABACUS owns first-principles electronic-structure calculations.
- DeePMD-kit owns DP model loading and inference.
- ASE owns the core optimizer and transition-state method implementations.
- Sella owns its saddle-search and IRC algorithms.

## References

If you publish work that uses the transition-state workflows in ATST-Tools,
please cite the underlying methods alongside ATST-Tools itself:

- Sella saddle-point search:
  Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
  Jónsson, H. *Sella, an Open-Source Chemical Kinetics Environment.*
  J. Chem. Theory Comput. **18** (8), 4914-4930 (2022).
  <https://doi.org/10.1021/acs.jctc.2c00395>
- CCQN (cone-shaped constrained quasi-Newton) transition-state optimization:
  Wu, Y.; Wang, H. *Cone-Shaped Constrained Quasi-Newton Method: Efficient
  and Robust Single-Ended Transition State Optimization Algorithm.*
  J. Chem. Theory Comput. (2025).
  <https://doi.org/10.1021/acs.jctc.5c01015>

## License

LGPL-v3 License.
