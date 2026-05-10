# ATST-Tools Refactor Acceptance Report

**Date**: 2026-05-10  
**Branch**: `refactor/unify-structure`

## Engineering Design

ATST-Tools is organized as a pip-installable Python package under `src/atst_tools`.
The primary user interface is `atst-run config.yaml`, where YAML selects both the workflow and calculator.
The package separates CLI dispatch, workflow orchestration, MEP method wrappers, calculator construction, and shared utilities.

ABACUS support is the first-class calculator path. The complete upstream ABACUS `ASE_interface` snapshot is vendored under `src/atst_tools/external/ASE_interface`, and `CalculatorFactory` constructs ABACUS calculators through that vendored abacuslite backend. DP/DeepMD support remains available through `calculator.name: dp`, but real DP workflow validation is secondary to ABACUS validation.

## Main-Branch Coverage

| Main capability | Refactored status |
| :--- | :--- |
| NEB / CI-NEB / DyNEB | Supported through ASE-native NEB/DyNEB wrappers and `atst-run` |
| AutoNEB | Supported through ASE AutoNEB integration |
| Dimer | Supported through ASE Dimer classes |
| Sella | Supported through the `sella` package |
| NEB-to-Dimer/Sella D2S | Supported as `calculation.type: d2s` |
| Relax | Supported as `calculation.type: relax` |
| Vibration analysis | Supported as `calculation.type: vibration` |
| DP scripts | Config and factory support present; real validation deferred |

## Improvements Over `main`

- Standard Python package layout with editable install support.
- Unified CLI/YAML workflow instead of method-specific hardcoded scripts.
- ABACUS backend migrated away from legacy `ase-abacus` toward the vendored official abacuslite ASE interface.
- ABACUS examples are adjusted for SAI GPU validation with `ks_solver: cusolver`.
- D2S is integrated into `atst-run` and follows the intended rough NEB to single-ended search structure.
- Unit tests now cover config validation, calculator construction, CLI dispatch, core workflows, and example YAML parsing.

## Validation Status

SAI environment facts confirmed:

- Conda env: `atst-dev`
- ABACUS module: `abacus/LTSv3.10.1-sm70-auto`
- ABACUS version: `v3.10.1`
- OpenMPI from module: `5.0.8`
- `deepmd-kit` is installed in `atst-dev`

Local checks completed:

- `atst-run --help` imports and runs successfully.
- `pytest tests -q` passes.
- `python -m compileall -q src/atst_tools tests` passes.
- All tracked example YAML files parse and validate.

SAI Slurm smoke validation was launched for every tracked example with the
SAI ABACUS module and the `atst-dev` environment. To keep validation bounded,
geometry-search examples use smoke limits such as `max_steps: 1`.

| Example | Workflow | Job ID | Status at report time | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| `examples/01_neb_Li-Si` | NEB | `394339` | `COMPLETED`, exit `0:0` | `FIRE` step 0 and 1 printed; `=== NEB Calculation Finished ===` |
| `examples/02_neb_H2-Au` | NEB | `394340` | `COMPLETED`, exit `0:0` | ABACUS output directories and `running_scf.log` generated for NEB images |
| `examples/03_autoneb_Cy-Pt` | AutoNEB | `394341` | `COMPLETED`, exit `0:0` | `autoneb_run/OUT.ABACUS/running_scf.log` generated |
| `examples/04_dimer_CO-Pt` | Dimer | `394342` | `COMPLETED`, exit `0:0` | `dimer_run/OUT.ABACUS/running_scf.log` generated |
| `examples/05_sella_H2-Au` | Sella | `394343` | `RUNNING` | `sella_run/OUT.ABACUS/running_scf.log` generated |
| `examples/06_relax_H2-Au` | Relax | `394344` | `COMPLETED`, exit `0:0` | `relax_run/OUT.ABACUS/running_scf.log` generated |
| `examples/07_vibration_H2-Au` | Vibration | `394371` | `RUNNING` after fix | Previous job `394345` failed on stale zero-byte ASE vibration cache; workflow now cleans cache by default |
| `examples/08_d2s_Cy-Pt` | D2S | `394370` | `RUNNING` after fix | Previous job `394346` failed because ASE DyNEB reads endpoint energies; D2S now attaches endpoint calculators |

The completed NEB case verifies the end-to-end `ASE -> ATST-Tools CLI/YAML ->
vendored abacuslite -> ABACUS v3.10.1` path on SAI. The rerun vibration and
D2S jobs were left in Slurm so their terminal status can be collected when
they finish.
