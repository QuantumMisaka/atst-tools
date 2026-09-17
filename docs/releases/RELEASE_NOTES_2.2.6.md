# ATST-Tools 2.2.6 Release Notes

**Version**: 2.2.6
**Date**: 2026-09-17
**Status**: Published (PyPI clean-install verified)
**Branch**: `main`
**Tag**: `v2.2.6` → `a633f06b9375e3f34dbd87f90f40ec6271b29cd4`

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.6 按 patch
> 语义承载优化器收敛事实的持久化、统一英文运行期诊断与 API 交接契约。

ATST-Tools 2.2.6 is a backward-compatible workflow-observability release. It
persists the optimizer-owned convergence facts that workflows previously only
printed:

- Every relevant workflow now records its optimizer termination signal as a
  manifest stage with a strict tri-state `converged` value (`true`/`false`/
  `null`). `null` means unknown and is never inferred from trajectories or raw
  force maxima.
- Stage records identify their scope: workflow stage name and role, criterion
  provenance, IRC `direction` (`forward`/`reverse`), AutoNEB image `subset`,
  thresholds (`fmax`, `fmax_unit`), and stage-local step counts. NEB keeps its
  existing stage fields; Sella/CCQN/Relax/IRC/AutoNEB/D2S add the same shape.
- Sella and Relax now write their own `atst_artifacts.json` record (previously
  only an API-synthesized completion manifest existed); AutoNEB writes the
  single top-level manifest for its per-iteration records and last-iteration
  final scope. Composite workflows (D2S, AutoNEB) remain the only writer of
  their top-level manifest; nested refinements cannot overwrite it.
- When the API synthesizes a missing completion manifest, its stage now carries
  an explicit `converged: null` (execution complete, convergence unknown).

The release also unifies program-visible runtime diagnostics to English:
`print`/warning/logging output, exception messages and CLI help text are
English across the package, and an AST gate
(`tests/unit/test_program_output_language.py`) enforces it mechanically.
Documentation keeps its existing language. The vendored abacuslite snapshot
(`src/atst_tools/external/`) is outside this contract.

Convergence advisories remain diagnostic only: they do not change completion,
exit codes, return values or manifest execution status, and an explicit
non-convergence signal is not a scientific verdict on the structure.

## Compatibility

- Package version: `2.2.6`.
- Python support remains `>=3.10`; existing CLI, YAML and stable API contracts
  keep their return values, exit codes and artifact lists.
- No new YAML configuration field is added. Sella/Relax standalone runs now
  write `atst_artifacts.json` in the process working directory; existing
  manifests remain readable and the manifest schema stays
  `atst-artifacts-v1`.
- Stage records gain optional fields (`role`, `criterion`, `direction`,
  `iteration`, `subset`, `measured`, ...) and `vibration`/`md`/`dmf` stages now
  carry `converged: null`; pre-2.2.6 manifests may omit `converged` entirely and
  consumers must treat a missing value as unknown.
- Program-visible diagnostic language changes from Chinese to English. This is
  the only user-visible behavior change in this release; it does not alter
  values, decisions or workflow results.
- `D2SWorkflow.optimize_endpoints()` keeps its original 2-tuple return; the new
  endpoint stage records are exposed through an attribute.

## Publication Evidence

- GitHub Tests run [`35206052859`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052859)
  and abacuslite run [`35206052923`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052923)
  succeeded on the release commit before tagging.
- Publish workflow run [`35206151239`](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206151239)
  completed: release preflight (readiness, unit tests, documentation governance,
  build, strict Twine, clean-wheel API gate) and the PyPI upload job succeeded.
- PyPI artifacts:
  - `atst_tools-2.2.6-py3-none-any.whl`, uploaded 2026-09-17T09:44:27Z,
    sha256 `e4998a9b8d4a5a71c37ff08ad2571d74d4d958f34e1dbfd4ab14f19aa581a4d3`.
  - `atst_tools-2.2.6.tar.gz`, uploaded 2026-09-17T09:44:28Z,
    sha256 `e30ccba828335eb5170b60239d96be1286ef7f08fd921cbdadb786b48316f099`.
- Official no-cache clean-install verification in an isolated venv: `atst --version`
  reported `atst 2.2.6`, `atst_tools.package_version()` reported `2.2.6`, the
  package imported from the venv `site-packages`, and the six stable root
  imports loaded successfully.

## Validation Matrix

SIF/SAI and real ABACUS/MPI runtime acceptance are not claimed by this document.

| Evidence | Candidate status |
| :--- | :--- |
| Full test suite (`pytest tests`) | 826 passed, 19 skipped (opt-in MPI launcher / ABACUS run-dir / cross-repo checks skipped) |
| Documentation governance (`check_docs_governance.py`) | Passed |
| Clean-wheel public API gate (`scripts/verify_wheel_api.py`) | Passed locally and in the publish preflight, including the installed-wheel tri-state stage check |
| Language gate (`test_program_output_language.py`) | Passed; package runtime strings are English outside the vendored snapshot |
| Independent reviews (workflow facts, API/stage contract, fixtures) | Completed; findings resolved or explicitly deferred |
| Real MPI launcher smoke | Not executed (`mpiexec` unavailable on the verification host) |
| Real ABACUS/DP/SIF/SAI runtime acceptance | Not performed |

## Download

```bash
python -m pip install atst-tools==2.2.6
```
