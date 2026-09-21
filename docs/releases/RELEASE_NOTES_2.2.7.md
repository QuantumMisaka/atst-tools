# ATST-Tools 2.2.7 Release Notes

**Version**: 2.2.7
**Date**: 2026-09-21
**Status**: Published (PyPI clean-install verified)
**Branch**: `main`
**Tag**: `v2.2.7` → `af9c8fa6b82386a52055a5b3dced82eb3d8f4ef2`

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

## Publication Evidence

- GitHub Tests run [`35614550222`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35614550222)
  and abacuslite ASE Interface run [`35614550226`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35614550226)
  succeeded on the release commit `af9c8fa6b82386a52055a5b3dced82eb3d8f4ef2`
  before tagging.
- Publish workflow run [`35614555409`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35614555409)
  completed: the release preflight (readiness, unit tests, documentation
  governance, sdist/wheel build, distribution checks, clean-wheel API gate) and
  the PyPI upload job succeeded once the `pypi` environment's five-minute wait
  timer elapsed.
- GitHub Release: [`v2.2.7`](https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.2.7).
- PyPI artifacts:
  - `atst_tools-2.2.7-py3-none-any.whl`, uploaded 2026-09-21T14:55:26Z,
    sha256 `b3b8edfa0bb97947c82d9ad24ced0211cf4c550b3821a563ff53aca9f532f45e`.
  - `atst_tools-2.2.7.tar.gz`, uploaded 2026-09-21T14:55:28Z,
    sha256 `a5dddcd3d2a4448652177f0c51489861fd4fbced144040ab28a7fe335976672b`.
- Official no-cache clean-install verification in an isolated venv:
  `pip install --no-cache-dir atst-tools==2.2.7` resolved and installed 27
  packages; `atst --version` reported `atst 2.2.7`, `atst_tools.package_version()`
  reported `2.2.7`, the package imported from that venv's site-packages, and both
  the stable root imports and the new `runtime`/`bench` modules loaded - the
  `--share-worker` flag is present and `calculator.abacus.omp` is unset by
  default in the published wheel.

## Validation Matrix

Platform/Paimon tool-chain and SIF-side deployment acceptance are not claimed by
this document; the runtime evidence below was collected on a shared SAI 4V100
node and on a local GPU.

| Evidence | Status |
| :--- | :--- |
| Full unit suite (`pytest tests/unit`) | 1131 passed, 2 skipped |
| Integration suite with the real MPI launcher (`ATST_RUN_MPI_TESTS=1`) | 23 passed |
| Documentation governance (`scripts/check_docs_governance.py`) | Passed locally and in the publish preflight |
| Clean-wheel public API gate (`scripts/verify_wheel_api.py --mpi-smoke`) | Passed locally and in the publish preflight |
| Release readiness (`scripts/check_release_readiness.py --tag v2.2.7`) | Passed locally and in the publish preflight |
| Official no-cache clean-install from PyPI | Passed (isolated venv, 2.2.7) |
| SAI 4V100 runtime evidence (P5: DP matrix, ABACUS examples, multi-card NEB, 8 ranks on one card, 8 graphs x 8 cards, host/SIF pairing) | Archived under `docs/reports/data/` and summarised in the SAI and local validation reports |
| Constant-potential x runtime joint acceptance (SAI) | Passed for the compensated-gate single point and the three-point scan; no platform chain claim |
| Platform/Paimon tool-chain acceptance, SIF-side deployment, Gitee mirror sync | Not performed (maintainer/platform-side actions) |

## Download

```bash
python -m pip install atst-tools==2.2.7
```
