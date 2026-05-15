# ABACUSLite Wrapper Guide

## Current Integration State

ATST-Tools integrates ABACUS through `abacuslite`. Runtime resolution is:

1. Import an independently installed `abacuslite` package.
2. If unavailable, fall back to the vendored snapshot under
   `src/atst_tools/external/ASE_interface/abacuslite`.

This means ABACUS-backed workflows can run through ASE calculators without
requiring users to write Python calculator boilerplate. The supported workflow
entry point remains:

```bash
atst run CONFIG.yaml
```

`neb`, `autoneb`, `d2s`, `dimer`, `sella`, `relax`, `vibration`, and `irc` can
all use `calculator.name: abacus`.

## Wrapper Boundary

ATST-Tools is a layered wrapper around abacuslite:

- It owns YAML validation, schema defaults, workflow dispatch, restart helpers,
  trajectory naming, and common pre/post-processing.
- It uses abacuslite as the ASE calculator backend for ABACUS calculations.
- It exposes conservative ABACUS input/output helpers for repeated user tasks.
- It does not replace ABACUS, abacuslite, Slurm, or site-specific job launchers.

## Common Commands

Inspect the normalized config before launching a run:

```bash
atst config validate config.yaml --print-normalized
```

Prepare ABACUS input files from the ABACUS calculator block:

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
```

This writes:

- `INPUT` from `calculator.abacus.parameters`.
- `KPT` from `calculator.abacus.kpts` or `parameters.kpts`.
- `STRU` from the supplied structure and `pseudopotentials` / `basissets`.

Collect a conservative output summary:

```bash
atst abacus collect run_abacus --output abacus_results.json
```

The summary records detected `INPUT`, `KPT`, `STRU`, and `running*.log` files.
When the directory contains the files required by the active abacuslite reader,
the command parses the final frame and can export it:

```bash
atst abacus collect run_abacus --output abacus_results.json --structure final.extxyz
```

The collector copies parse inputs into a temporary directory before invoking
abacuslite readers, so original ABACUS outputs are not modified.

## Complex Workflows

Complex workflows are still launched with `atst run`:

```bash
atst run examples/01_neb_Li-Si/config.yaml
atst run examples/08_d2s_Cy-Pt/config.yaml
atst run examples/10_irc_H2/config.yaml
```

For D2S, ATST-Tools uses the same ABACUS calculator backend through rough NEB
and the selected single-ended method. For NEB and AutoNEB, endpoint
single-point governance repairs placeholder endpoint results before ASE NEB
construction when configured with `endpoint_singlepoint: auto` or `always`.

## Non-Goals

- No Slurm submission command is provided in this layer.
- No site-specific module loading is encoded in YAML.
- No complete ABACUS output database is built from run directories.
- No guarantee is made that every abacuslite IO function is exposed at the CLI.

Future expansion should keep this boundary: add helpers only when they reduce a
repeated ATST workflow step and can be tested without launching expensive
calculations.
