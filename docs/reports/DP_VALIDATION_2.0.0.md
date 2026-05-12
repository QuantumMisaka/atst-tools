# DP Validation Report for 2.0.0

**Date**: 2026-05-12  
**Environment**: SAI GPU node, `atst-dev`, DeePMD-kit Python interface  
**Model**: `temp_repos/dp_model/DPA-3.1-3M.pt`  
**Head**: `Omat24`

## Scope

This report records the DeePMD-kit calculator validation used to close
ATST-Tools 2.0.0. The model file and generated runtime outputs remain outside
git tracking under `temp_repos/` and example runtime directories.

The validation covers the existing `atst run` workflow surface with DP-backed
ASE calculators:

| Example | Workflow | Result | Notes |
| :--- | :--- | :--- | :--- |
| `01_neb_Li-Si` | NEB | Passed | DP job completed on SAI GPU. |
| `02_neb_H2-Au` | NEB | Passed | DP job completed on SAI GPU. |
| `03_autoneb_Cy-Pt` | AutoNEB | Passed | Short smoke run completed after fixing iteration directory creation. |
| `04_dimer_CO-Pt` | Dimer | Passed | DP job completed on SAI GPU. |
| `05_sella_H2-Au` | Sella saddle search | Passed | DP job completed on SAI GPU. |
| `06_relax_H2-Au` | Relax | Passed | DP job completed on SAI GPU. |
| `07_vibration_H2-Au` | Vibration | Passed | DP job completed on SAI GPU. |
| `08_d2s_Cy-Pt` | D2S | Passed | DP rough DyNEB plus single-ended search completed. |
| `10_irc_H2` | Sella IRC | Controlled boundary | Sella raised `RuntimeError: MGS failed`; ATST-Tools reports it as `IRCBoundaryError`. |
| `11_vibration_ideal_gas_H2` | Vibration / thermochemistry | Passed | DP job completed on SAI GPU. |

## DeePMD-kit Interface Findings

ATST-Tools uses `deepmd.calculator.DP` as the ASE calculator entry point:

```python
DP(model=model_file, head=head, type_dict=type_dict)
```

DeePMD-kit auto-detects the model backend from the supplied model file. The
project therefore does not expose a separate backend selector. DPA multi-head
models are configured through `calculator.dp.head`; the validation model
requires an explicit head and was run with `Omat24`.

## AutoNEB Finding

The first AutoNEB DP run exposed a project-side workflow bug: later AutoNEB
iterations attempted to write `AutoNEB_iter/run_autoneb...iterXXX.traj` before
ensuring that `iter_folder` existed. The workflow now creates the iteration
directory before every per-iteration NEB execution. A follow-up AutoNEB smoke
run reached `n_max`, executed the CI-NEB phase, and finished normally.

The observed AutoNEB checkpoint during monitoring was iteration-level
optimization inside the generated `AutoNEB_iter/` directory, not a deadlock.
The job completed after six AutoNEB iterations.

## IRC Finding

The IRC workflow follows the main-branch Sella application pattern: read a TS
structure, attach an ASE calculator, construct `sella.IRC`, run the requested
direction, and write normalized output trajectories. In the DP validation case,
Sella stopped in its internal eigensolver with `RuntimeError: MGS failed`.

ATST-Tools now detects traceback frames originating from the Sella package and
raises a controlled `IRCBoundaryError` that preserves the direction, generated
frame count, and original exception. This confirms that the failure boundary is
inside Sella's IRC algorithm rather than in ATST-Tools calculator construction,
YAML dispatch, or trajectory orchestration.

## Release Checks

- `atst --version` reports `2.0.0`.
- All example YAML files pass `atst run --dry-run`.
- Unit tests pass in `atst-dev`.
- `python -m compileall -q src/atst_tools tests` passes.
- `python -m build` produces 2.0.0 sdist and wheel artifacts.
- The 2.0.0 wheel installs into a clean virtual environment and exposes the CLI.
