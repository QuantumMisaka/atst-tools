# ATST-Tools User Experience Reinforcement Report

**Date**: 2026-05-15
**Branch**: `refactor/unify-structure`
**Basis**: `docs/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md`

## Summary

This stage reinforces ATST-Tools as a pip-installable, YAML-driven workflow
toolkit with a clearer user path from installation to workflow execution. The
main implementation additions are:

- `atst config validate` for normalized YAML inspection.
- `atst abacus prepare` for ABACUS `INPUT`, `KPT`, and `STRU` generation.
- `atst abacus collect` for conservative ABACUS run-directory summaries.
- A maintained repository skill at `docs/skills/atst-cli/SKILL.md`.
- Updated user documentation and examples around installation, help, examples,
  and abacuslite wrapper boundaries.

## abacuslite Integration Status

ATST-Tools currently resolves ABACUS support by importing an installed
`abacuslite` package first and falling back to the vendored snapshot under
`src/atst_tools/external/ASE_interface/abacuslite`.

The project can use ABACUS as an ASE calculator backend for YAML workflows:

- NEB / AutoNEB
- D2S
- Dimer / Sella
- Relax
- Vibration
- IRC

The new `atst abacus` helpers extend user-facing wrapper coverage without
turning ATST-Tools into a full ABACUS CLI replacement.

## Wrapper Role Decision

ATST-Tools should be maintained as a layered abacuslite wrapper:

- **Own**: workflow orchestration, schema validation, defaults, examples,
  restart conventions, common ABACUS input preparation, and conservative output
  collection.
- **Delegate**: numerical calculation to ABACUS, IO backend behavior to
  abacuslite, optimizer algorithms to ASE/Sella, and model inference to
  DeePMD-kit.
- **Do not own**: Slurm submission policy, site module loading, complete ABACUS
  output databases, or full abacuslite API exposure.

This positioning lets ATST-Tools accelerate ASE + ABACUS workflows while
keeping a maintainable boundary.

## User Experience Improvements

### Installation and first-run checks

The README and Chinese user guide now direct users to:

```bash
pip install -e .
atst --version
atst run --dry-run CONFIG.yaml
atst config validate CONFIG.yaml --print-normalized
```

This makes the installed command, schema validation, and normalized defaults
visible before users submit expensive jobs.

### Examples

`examples/README.md` now provides learning paths:

- local lightweight CLI smoke test
- ABACUS workflow path
- D2S transition-state path

`examples/09_lightweight_cli/README.md` includes the new `config` and `abacus`
helpers as commands that do not launch ABACUS.

### Help and reference docs

`docs/user/CLI_REFERENCE.md` documents the new public commands:

- `atst config validate`
- `atst abacus prepare`
- `atst abacus collect`

`docs/user/ABACUSLITE_WRAPPER_GUIDE.md` records the wrapper boundary and the
current abacuslite integration state.

## Remaining Reinforcement Points

- Add richer fixtures for real ABACUS output parsing once stable small output
  examples are available.
- Consider a workflow output manifest after the run layer is ready to emit one
  consistently.
- Keep `docs/skills/atst-cli/SKILL.md` synchronized when CLI command behavior
  changes.
- Keep Slurm examples as site documentation rather than core CLI behavior unless
  a stable cross-site abstraction is designed.

## Validation Targets

Required checks for this stage:

```bash
conda run -n atst-dev pytest tests/unit/test_cli.py -q
conda run -n atst-dev pytest tests -q
atst --help
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
```
