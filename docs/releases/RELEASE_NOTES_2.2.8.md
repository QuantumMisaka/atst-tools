# ATST-Tools 2.2.8 Release Notes

**Version**: 2.2.8
**Date**: 2026-09-22
**Status**: Release candidate (not published)
**Branch**: `main`
**Tag**: pending maintainer publication

## Summary

2.2.8 is a backward-compatible resource-and-evidence patch. It closes the GPU
node tuning P2 rows on SAI V100, hardens the DeepMD PyTorch backend path, and
makes the GPU facts visible under MPS:

- **Read-only model sharing and restart regression (P2).** A DP batch run as one
  shared worker over a read-only model directory leaves that directory byte- and
  mtime-identical (`dp.calculator_built=1`, `dp.calculator_reused=1`), and
  re-running one workdir recomputes equivalent energies (delta 1.6e-05 eV on the
  site) with its own attempt cache and artifacts.
- **Per-attempt evidence attribution.** `build_child_environment` publishes the
  resolved `ATST_ATTEMPT`, so an explicit attempt writes its cache directory and
  its evidence/result documents under the same attempt.
- **DP PyTorch backend hardening.** Artifact kinds are classified (`.pt`
  checkpoint, `.pth` frozen archive, `.pb` TF graph); a multi-task PT checkpoint
  without a usable `head` raises `DeepPotentialError` listing the available heads
  instead of deepmd's bare `AssertionError`; a version-locked frozen archive
  failing at the first evaluation is translated into an actionable error;
  `dp_model_identity()` exposes model facts without evaluating.
- **DP thread budget.** The runtime thread budget also sets
  `DP_INTRA_OP_PARALLELISM_THREADS` and `DP_INTER_OP_PARALLELISM_THREADS` next to
  OMP, so the DeepMD backend receives the same budget as the rest of the process.
- **MPS-aware GPU facts.** The host sampler probes MPS explicitly (process table
  plus the client pipe as positive evidence only, tri-state `detected`), names
  MPS when the compute table is empty, and records a `self_reported` torch
  allocator high-water mark without initialising CUDA.
- **Benchmark records carry channel fixtures.** `record` accepts a repeatable
  `--fixture-labeled LABEL=PATH` (directories get `file_count`/`tree_sha256`), and
  the site entry point passes `MODEL` as `dp_model` and `ABACUS_INPUTS` as
  `abacus_inputs`, so an ABACUS run is no longer recorded with the DP model hash.

## Compatibility

- Package version: `2.2.8`.
- Python support remains `>=3.10`; existing CLI, YAML and stable API contracts
  keep their return values, exit codes and artifact lists.
- Runs without runtime keys behave exactly as before; the new evidence keys
  (`telemetry.sampler.mps`, `self_reported`), the labeled record fixtures and the
  `DP_*_OP_PARALLELISM_THREADS` budget are additive.
- Behavior changes to note: a DeepMD multi-task checkpoint without a usable head
  now raises `DeepPotentialError` instead of deepmd's `AssertionError`; an empty
  compute-process table under MPS gets a new reason string; a directory passed to
  `record --fixture` is now hashed as a tree instead of being reported missing.

## Publication Evidence

Pending: this candidate is not published. The maintainer tags `v2.2.8` on the
release commit; the tag push runs `publish-pypi.yml`, whose preflight (release
readiness, unit tests, documentation governance, sdist/wheel build,
distribution checks, wheel public API verification) must pass before the PyPI
publish job runs.

## Validation Matrix

| Gate | Result |
| :--- | :--- |
| `tests/unit` (repository default) | 1195 passed, 3 skipped (opt-in real-backend and root-only cases) |
| `tests/unit` + `tests/integration` with `ATST_RUN_MPI_TESTS=1` | passed on the review branch |
| `scripts/check_docs_governance.py` | passed |
| SAI V100 field evidence | jobs 1444708 (record channels), 1444802 (P2 closeout), 1445744/1445792 (PT thread budget, MPS probe, self-report); see the P2 closeout report and its slices |
| Independent review | full-branch review on `0f5fb51..e0920c2`; required change (evidence slices not tracked) fixed, remaining Minor findings tracked in the ledger |

MPS remains environment-dependent: the site's compute nodes did not expose the
MPS daemons during the afternoon runs, so the probe recorded a completed
negative; the MPS-positive reason path is covered by unit tests.

## Download

Pending publication: `atst_tools-2.2.8-py3-none-any.whl` and
`atst_tools-2.2.8.tar.gz` on PyPI.
