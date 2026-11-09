# ATST-Tools

[![Version](https://img.shields.io/badge/version-2.3.3-blue)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-LGPL--v3-blue)](#license)

ATST-Tools is an **ASE transition-state workflow toolkit** for ABACUS and
DeePMD-kit. Run calculations from YAML with the `atst` command, or use the
[Python API](docs/user/PYTHON_API_REFERENCE.md) to integrate the same workflows
into another program.

```bash
atst run config.yaml
```

Chinese guide: [中文 · GitHub](https://github.com/QuantumMisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md)
· [Gitee](https://gitee.com/jamesmisaka/atst-tools/blob/main/docs/user/USER_GUIDE_CN.md).
Examples: [GitHub](https://github.com/QuantumMisaka/atst-tools/tree/main/examples)
· [Gitee](https://gitee.com/jamesmisaka/atst-tools/tree/main/examples).

## What You Can Run

| Workflow | `calculation.type` |
| :--- | :--- |
| NEB / DyNEB and adaptive-image NEB | `neb`, `autoneb` |
| Dimer, Sella and CCQN saddle searches | `dimer`, `sella`, `ccqn` |
| Double-ended to single-ended TS search | `d2s` |
| Structure relaxation | `relax` |
| Vibrations and thermochemistry | `vibration` |
| Intrinsic reaction coordinates | `irc` |
| ASE-driven or ABACUS-native molecular dynamics | `md` |
| Experimental Direct MaxFlux path search | `dmf` |
| ABACUS constant-potential single points and serial scans | `constant_potential` |

Constant-potential fixed-cell relaxation, serial NEB and ASE-driven MD
use the explicit `compensated_gate` boundary. See the
[configuration reference](docs/user/CONFIG_REFERENCE.md#211-constant-potential-evaluation)
for setup and supported boundaries.

Local commands prepare paths and ABACUS inputs, inspect trajectories, and
summarize existing results. See the [CLI reference](docs/user/CLI_REFERENCE.md).
A transition-state candidate can be screened with `atst vibration validate`
using saved vibration results; workflow completion alone does not establish a
validated TS. Current support and experimental limits are summarized in the
[feature matrix](docs/reports/FEATURE_STATUS_MATRIX.md).

## Installation

Requires Python 3.10 or later:

```bash
pip install atst-tools
atst --version
```

| Use | Installation |
| :--- | :--- |
| Serial workflows, including serial NEB/AutoNEB | `pip install atst-tools` |
| DeePMD-kit calculator | `pip install "atst-tools[dp]"` |
| Image-parallel NEB/AutoNEB | `pip install "atst-tools[parallel]"` |

The default installation includes `abacuslite>=1.2.1,<2` and Sella; it does not
install `mpi4py`. ABACUS calculations also need an ABACUS executable and the
pseudopotential/orbital files referenced by the configuration. DP calculations
need a compatible model. Image-parallel runs require a matching MPI runtime;
DMF additionally requires `cyipopt` and IPOPT. See the
[MPI setup guide](docs/user/ABACUSLITE_WRAPPER_GUIDE.md#neb-image-level-mpi) for
image-parallel setup and the [examples guide](examples/README.md#usage) for
backend inputs.

## Quick Start

Obtain examples at the tag matching your installed version (shown for 2.3.3):

```bash
git clone --branch v2.3.3 https://github.com/QuantumMisaka/atst-tools.git
cd atst-tools
```

First try a local path-preparation command; it needs no ABACUS, DP model or GPU:

```bash
cd examples/09_lightweight_cli
atst neb make inputs/init.xyz inputs/final.xyz 3 -o first_chain.traj --method linear
atst neb summary inputs/neb_result.extxyz --n-max 1 --tail 5
cd ../..
```

`first_chain.traj` contains five initial-guess frames. To inspect a calculation
configuration, enter its example directory so relative input paths resolve:

```bash
cd examples/06_relax_H2-Au
atst config validate config.yaml --print-normalized
atst run --dry-run config.yaml
# After configuring the ABACUS runtime and compute resources:
atst run config.yaml
```

This example uses four ABACUS MPI ranks, the GPU `cusolver` solver and a
one-step optimization limit. Validation and dry-run do not launch ABACUS;
check the resulting convergence status separately. Follow the
[examples guide](examples/README.md#usage) to inspect results and choose other
methods or DP variants. A complete walkthrough is also available in the
[Chinese guide](docs/user/USER_GUIDE_CN.md#3-10-分钟快速上手).

## Documentation

| Task | Reference |
| :--- | :--- |
| Configure a calculation | [Configuration reference](docs/user/CONFIG_REFERENCE.md) · [All YAML fields](docs/user/YAML_INPUT_VARIABLES.md) |
| Use CLI commands | [CLI reference](docs/user/CLI_REFERENCE.md) |
| Configure ABACUS input/output and parallelism | [ABACUS wrapper guide](docs/user/ABACUSLITE_WRAPPER_GUIDE.md) |
| Embed workflows or use the JSON process runner | [Python API](docs/user/PYTHON_API_REFERENCE.md) |
| Check support and releases | [Feature matrix](docs/reports/FEATURE_STATUS_MATRIX.md) · [2.3.3 release notes](docs/releases/RELEASE_NOTES_2.3.3.md) |
| Contribute | [Developer handover](docs/developer/HANDOVER.md) · [Source architecture](src/atst_tools/README.md) |

The primary documentation is in English, with a [Chinese user guide](docs/user/USER_GUIDE_CN.md).
The [documentation index](docs/index.md) organizes user, developer and project
status material. GitHub is the development source; Gitee is a manually updated
mirror. PyPI distributes the Python package; obtain examples from the repository.

## References

If you publish work that uses the transition-state workflows in ATST-Tools,
please cite the underlying methods alongside ATST-Tools itself:

- ATST-Tools and the double-to-single (D2S) transition-state workflow:
  Liu, Z.-Q.; Deng, Z.; Zhao, H.; Wang, H.; Chen, M.; Jiang, H.
  *FT²DP: Large Atomic Model Fine-Tuned Machine Learning Potential for
  Accelerating Atomistic Simulation of Iron-Based Fischer–Tropsch Synthesis.*
  J. Mater. Inform. **5** (2), 27 (2025).
  <https://doi.org/10.20517/jmi.2024.105>
- Sella saddle-point search:
  Hermes, E. D.; Sargsyan, K.; Najm, H. N.; Zádor, J.
  *Sella, an Open-Source Automation-Friendly Molecular Saddle Point Optimizer.*
  J. Chem. Theory Comput. **18** (11), 6974-6988 (2022).
  <https://doi.org/10.1021/acs.jctc.2c00395>
- CCQN (cone-shaped constrained quasi-Newton) transition-state optimization:
  Wu, Y.; Wang, H. *Cone-Shaped Constrained Quasi-Newton Method: Efficient
  and Robust Single-Ended Transition State Optimization Algorithm.*
  J. Chem. Theory Comput. **21** (18), 9054-9065 (2025).
  <https://doi.org/10.1021/acs.jctc.5c01015>

## License

LGPL-v3 License.
