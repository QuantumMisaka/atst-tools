# ATST-Tools 2.2.7 Release Notes

**Version**: 2.2.7
**Date**: 2026-09-21
**Status**: Release candidate (not published)
**Branch**: candidate working tree; no release tag yet
**Tag**: pending maintainer publication

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.7 按 patch
> 语义承载共享 GPU 节点上的资源绑定与运行证据（GPU 节点调优 P0–P5）、
> 基准工具链，以及恒电势开发候选。

ATST-Tools 2.2.7 is a backward-compatible resource-and-measurement release.
It makes runs on shared GPU nodes bind their resources explicitly and record
what they actually used:

- **`runtime` resource binding.** An optional `runtime` YAML section (plus
  `--devices/--binding/--threads/--telemetry` on `atst run` and the API
  runner) resolves device requests against the caller's binding
  (`CUDA_VISIBLE_DEVICES`) and the trusted allocation facts
  (`ATST_ALLOCATION_DEVICES`). Explicit selection is refused when the visible
  set is not caller-bound or the request leaves the trusted/allocation set;
  `binding: round_robin` maps `local_rank` onto the resolved pool per rank and
  fails closed for multi-node shapes or unknown local ranks.
- **Worker isolation and budgets.** Runtime runs execute in an isolated worker
  whose devices, thread budget and cache directories are applied before the
  scientific stack is imported, with a coordinator/worker consistency check
  that fails closed when the bound facts do not match.
- **Run evidence.** `runtime_evidence.json` records the environment triple,
  device facts (requested/inherited/allocation/effective), process-scope
  counters (`dp.*`, `abacus.*` builds and force calls, MPI-summed values),
  workflow phases, host GPU samples and the sampled memory peak. Runs without
  runtime keys keep the legacy in-process path and write no extra files.
- **Benchmark toolchain (`atst_tools.bench`).** `batch_runner` executes a finite
  case manifest inside one existing allocation (device slots, CPU budget,
  timeouts, per-case reports, batch summary); `sweep` drives variant x repeat
  matrices; `record` writes a self-describing benchmark record (revision,
  manifest/fixture hashes, result-tree hash, operator fields). The
  `--share-worker` mode runs a whole batch in one worker process so the model
  load and first-call warm-up are paid once (measured 3.0x on a small batch).
- **Budget fixes.** `calculator.abacus.omp` is unset by default, so a
  `runtime.threads` budget now reaches the ABACUS backend; the batch manifest's
  per-case `threads` is marked as a caller budget. The runner defers MPI
  initialisation until after the rebind exec, which removes the site OpenMPI
  hang.
- **Constant-potential development candidate (ABACUS-only).** A fixed-geometry
  single-point/serial-scan workflow, fixed-cell `compensated_gate` `relax`/`neb`
  routing, an atomic completed-point checkpoint with strict restart validation,
  and per-point artifacts. It ships as a development candidate: no
  Paimon/public tool-chain, platform or MPI acceptance claim is made, and the
  legacy `reference_fcp` boundary stays reference-only.
- Also in this line: the IDPP nearest-image translation scan is vectorised
  (bitwise identical), and the vendored abacuslite snapshot carries the periodic
  frame-selection patch recorded in its `PATCHES.md`.

Measurement evidence for this line (SAI 4V100 and a local GPU) is archived under
`docs/reports/data/` and summarised in the runtime validation reports.

## Compatibility

- Package version: `2.2.7`.
- Python support remains `>=3.10`; existing CLI, YAML and stable API contracts
  keep their return values, exit codes and artifact lists.
- Runs without runtime keys behave exactly as before; the new `runtime` section,
  the benchmark modules and the constant-potential candidate are opt-in
  additions.
- The only default-value change is `calculator.abacus.omp`, which is now unset
  instead of 1: an explicit `omp` still wins, a runtime thread budget now
  reaches ABACUS, and runs without any budget keep the historical single thread.
