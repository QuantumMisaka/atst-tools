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

`neb`, `autoneb`, `d2s`, `dimer`, `sella`, `relax`, `vibration`, `irc`, and
`md` can all use `calculator.name: abacus`.

## Vendored Backend Notes

ATST-Tools still resolves an independently installed `abacuslite` package before
the vendored fallback. An external `abacuslite` package may differ from the
vendored snapshot.

As of 2026-07-23, the vendored snapshot is synchronized with upstream
`deepmodeling/abacus-develop` commit `70f7ed69b5677c447afdc78e05240e93da660e66`
after normalizing ATST package-layout differences. It intentionally preserves these local
differences from `temp_repos/abacus-develop/interfaces/ASE_interface/abacuslite`:

- Relative imports so the package works under `atst_tools.external`.
- First-occurrence species grouping for generated STRU files.
- ASE `FixAtoms` and `FixCartesian` constraints written as ABACUS mobility flags.
- Tolerant legacy ABACUS band-row parsing.

The synchronized snapshot accepts both dotted and undotted prerelease banners
such as `v3.11.0-beta.1` and `v3.11.0-beta1`; its fixed-density helper also
uses `OUT.ABACUS` as the explicit charge-file directory expected by current
upstream behavior.

ATST workflow YAML already defaults NEB, AutoNEB, and the D2S rough DyNEB path
to ASE's recommended `improvedtangent` method. Direct `AbacusNEB(...)`
construction now pins the same default explicitly, so its behavior does not
depend on an ASE release's implicit default.

The vendored snapshot also carries upstream-sync fixes for numbered backup
rotation, property-derived ABACUS keyword conflict detection, unsupported TDDFT
`dipole` de-advertising, and `read_abacus_out` calculator `magmoms` reordering
when atoms are sorted during result parsing.

## Wrapper Boundary

ATST-Tools is a layered wrapper around abacuslite:

- It owns YAML validation, schema defaults, workflow dispatch, restart helpers,
  trajectory naming, and common pre/post-processing.
- It uses abacuslite as the ASE calculator backend for ABACUS calculations.
- It exposes conservative ABACUS input/output helpers for repeated user tasks.
- It does not replace ABACUS, abacuslite, a scheduler, or site-specific job
  launchers.

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

## NEB Image-Level MPI

The vendored abacuslite tree includes a working NEB pattern in
`src/atst_tools/external/ASE_interface/examples/neb.py`: each image receives an
independent `Abacus` calculator directory, and ASE runs `NEB(...,
parallel=True)`. ATST-Tools follows this image-isolated directory model for
ABACUS-backed NEB and AutoNEB.

Use an MPI-enabled Python environment compatible with the site launcher and
the installed ABACUS runtime. For ordinary NEB, the outer MPI world size must
equal the number of interior images; for AutoNEB, it must equal
`calculation.n_simul`. Start with `calculator.abacus.mpi: 1`; increasing it
adds a second, inner MPI layer for each ABACUS image calculation.

The outer launcher remains outside ATST-Tools. Configure the ABACUS subprocess
separately with `calculator.abacus.command`. When a bare single-process
`abacus` command runs inside an image-level MPI workflow, ATST-Tools clears the
outer MPI launcher environment for the ABACUS subprocess so it remains a
one-image calculation.

For site setup, example validation, and maintainer operations, use the
[developer handover](../developer/HANDOVER.md) and the forthcoming
[example validation operations guide](../developer/EXAMPLE_VALIDATION_OPERATIONS.md).

## Non-Goals

- No scheduler submission command is provided in this layer.
- No site-specific module loading is encoded in YAML.
- No complete ABACUS output database is built from run directories.
- No guarantee is made that every abacuslite IO function is exposed at the CLI.

Future expansion should keep this boundary: add helpers only when they reduce a
repeated ATST workflow step and can be tested without launching expensive
calculations.
