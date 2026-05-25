# ATST-Tools 2.0.0 Release Notes

**Version**: 2.0.0  
**Date**: 2026-05-25  
**Branch**: `develop`

## Summary

ATST-Tools 2.0.0 completes the transition from the legacy script collection to
a pip-installable ASE workflow package. Production calculations use the unified
`atst run CONFIG.yaml` entry point, while `atst neb`, `atst dimer`,
`atst relax`, `atst vibration`, and `atst traj` provide lightweight
pre/post-processing utilities.

## Major Capabilities

- **ASE workflow package**: NEB/DyNEB, AutoNEB, Dimer, Sella, D2S, Relax,
  Vibration, and Sella-backed IRC are available through the CLI/YAML interface.
- **Calculator backends**: ABACUS is integrated through `abacuslite`; DeePMD-kit
  is integrated through `deepmd.calculator.DP`.
- **YAML governance**: user-facing inputs are defined by Pydantic schema models,
  normalized before dispatch, and exported to user documentation.
- **NEB endpoint governance**: chains made from pure structures are repaired by
  endpoint single-point calculations before NEB/AutoNEB starts.
- **D2S endpoint optimization**: optional endpoint optimization is enabled by
  default and skipped when endpoint structures already carry valid results.
- **DP multi-head support**: DPA/DPA3 multi-head models pass `calculator.dp.head`
  directly to DeePMD-kit; the 2.0.0 validation path uses DPA-3.1-3M with the
  `Omat24` head.

## IRC Integration Position

The IRC workflow intentionally follows the main-branch application pattern:
read a TS structure, assign an ASE calculator, construct `sella.IRC`, run
forward and/or reverse directions, then write a normalized trajectory for
combined runs. ATST-Tools owns the orchestration, YAML configuration, calculator
construction, trajectory naming, restart handling, and diagnostics. The IRC
integration algorithm itself is delegated to the upstream Sella package.

Known flat-endpoint and inner-loop stops are reported as controlled
`IRCBoundaryError` diagnostics with the Sella exception type and trajectory
frame count. These diagnostics indicate that ATST-Tools reached the current
supported Sella-backed IRC boundary; they are not treated as calculator factory
or YAML orchestration failures.

## Validation Status

- Local unit tests, example dry-runs, and compile checks pass in the `atst-dev`
  environment.
- ABACUS examples have existing SAI GPU validation evidence for the core
  workflows.
- DP examples were run on SAI GPU with
  `temp_repos/dp_model/DPA-3.1-3M.pt` and `head: Omat24`. NEB, AutoNEB,
  Dimer, Sella, D2S, Relax, and Vibration completed; the IRC example reaches a
  controlled Sella IRC boundary reported as `IRCBoundaryError`.
- The 2.0.0 release-ready process builds sdist/wheel artifacts and installs the
  wheel in a clean virtual environment for CLI smoke checks.
- Final release verification on 2026-05-25 confirmed the local test suite,
  example YAML dry-runs, compile checks, CLI version, and sdist/wheel build
  from the `develop` release branch.

## Supported Workflows

| Workflow | Status | Notes |
| :--- | :--- | :--- |
| NEB / DyNEB | Supported | Endpoint single-point governance enabled by default. |
| AutoNEB | Supported | Final-chain export is available through `atst neb post`. |
| Dimer | Supported | Can consume displacement vectors from NEB post-processing. |
| Sella | Supported | ASE/Sella saddle search through `atst run`. |
| D2S | Supported | Rough DyNEB followed by Dimer or Sella. |
| Relax | Supported | ASE optimizer based structure optimization. |
| Vibration | Supported | Harmonic and ideal-gas thermochemistry helpers. |
| IRC | Supported | Sella-backed application mode with controlled boundary diagnostics. |
| MD | Not included | Planned as a post-2.0.0 ASE workflow extension. |

## Installation

Development install:

```bash
pip install -e .
```

Wheel install after local build:

```bash
python -m build
pip install dist/atst_tools-2.0.0-py3-none-any.whl
```

ABACUS users need an executable ABACUS runtime plus pseudopotential/orbital
files referenced by YAML. DP users need DeePMD-kit installed and a model file
available outside git-tracked paths.
