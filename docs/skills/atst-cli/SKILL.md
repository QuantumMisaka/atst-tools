---
name: atst-cli
description: Use when operating, testing, documenting, or extending the ATST-Tools command-line interface for ASE workflows with ABACUS/abacuslite or DeePMD-kit backends.
---

# ATST CLI Skill

Use this skill for ATST-Tools CLI work in this repository.

## Environment

- Work from the repository root.
- Prefer the project environment: `conda activate atst-dev`.
- If the default Python cannot import `ase`, run checks with
  `conda run -n atst-dev <command>`.
- Do not modify `main`; active refactor work belongs on `refactor/unify-structure`
  or a derived branch.

## First Checks

```bash
git branch --show-current
git status --short
atst --version
atst --help
```

Before launching expensive calculations, validate YAML:

```bash
atst run --dry-run CONFIG.yaml
atst config validate CONFIG.yaml --print-normalized
```

## Workflow Commands

Use `atst run CONFIG.yaml` for calculator-backed workflows:

- `neb`, `autoneb`
- `d2s`
- `dimer`, `sella`
- `relax`
- `vibration`
- `irc`

ABACUS workflows use `calculator.name: abacus` and the active `abacuslite`
backend. DP workflows use `calculator.name: dp` and `deepmd.calculator.DP`.

## Lightweight Commands

These do not launch ABACUS or DP:

```bash
atst config validate CONFIG.yaml --print-normalized
atst abacus prepare CONFIG.yaml --structure STRUCTURE --output-dir DIR
atst abacus collect RUN_DIR --output abacus_results.json
atst neb make INIT FINAL N_IMAGES -o init_neb_chain.traj
atst neb post neb.traj --n-max N --vib-analysis
atst dimer make-from-neb neb.traj --n-max N --output-traj dimer_init.traj
atst relax post relax.traj --output-format traj --output restart.traj
atst vibration post config.yaml --output vibration_results.json
atst traj collect frames/*.xyz -o collection.traj --no-calc
atst traj transform collection.traj --format extxyz --output-prefix collection
```

## ABACUS Wrapper Boundary

ATST-Tools is a layered wrapper:

- It owns YAML validation, workflow orchestration, restart helpers, examples,
  and common ABACUS input/output helpers.
- It uses abacuslite as the ABACUS ASE calculator backend.
- It does not replace ABACUS, abacuslite, Slurm, or site-specific job launchers.

Read `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` before changing this boundary.

## Validation

For CLI changes, run targeted tests first:

```bash
conda run -n atst-dev pytest tests/unit/test_cli.py -q
```

Before reporting completion, run:

```bash
conda run -n atst-dev pytest tests -q
atst --help
atst config validate examples/06_relax_H2-Au/config.yaml --print-normalized
```

Update docs when command behavior, config shape, or wrapper boundaries change:

- `README.md`
- `docs/user/CLI_REFERENCE.md`
- `docs/user/CONFIG_REFERENCE.md`
- `docs/user/USER_GUIDE_CN.md`
- `examples/README.md`
