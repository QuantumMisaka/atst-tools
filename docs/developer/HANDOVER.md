# Documentation Handover and Maintenance

**Version**: 2026-10-20
**Date**: 2026-10-20
**Status**: Maintained
**Owner**: ATST-Tools maintainers

This is the maintainers' daily checklist. Before changing a feature, YAML
input, CLI, backend, example, report, or release, use the corresponding section
to identify the documentation that must be updated.

## 1. Daily entry points

2.3.3 release preparation includes the ordinary ASE/ABACUS MD per-evaluation
SCF validity guard, the experimental i-PI socket client, and the transition
candidate/reaction-atom selection helpers. The MD guard reuses CP's
convergence-evidence reader, keeps converged-input YAML/API compatible, and
intentionally rejects previously accepted unvalidated forces. Re-run short
real-backend MD acceptance before downstream Toolbox publication.

- User entry points: [README.md](../../README.md), [docs/index.md](../index.md),
  [USER_GUIDE_CN.md](../user/USER_GUIDE_CN.md).
- Configuration entry points: [CONFIG_REFERENCE.md](../user/CONFIG_REFERENCE.md)
  and [YAML_INPUT_VARIABLES.md](../user/YAML_INPUT_VARIABLES.md).
- Source entry point: [source architecture](../../src/atst_tools/README.md)
  explains module purposes, key components, call paths, and where to make
  changes. Update it when adding a directory or changing responsibilities.
- Developer entry points: [YAML_INPUT_GOVERNANCE.md](YAML_INPUT_GOVERNANCE.md),
  [DOCUMENTATION.md](DOCUMENTATION.md),
  [EXAMPLE_VALIDATION_OPERATIONS.md](EXAMPLE_VALIDATION_OPERATIONS.md), and
  [GOVERNANCE_AND_RELEASE_GATES.md](GOVERNANCE_AND_RELEASE_GATES.md).
- Project status: [FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md).

The README covers installation and the first run. User references own the
configuration, backend, and API details. The feature matrix shows current
support and links to validation reports; downstream platform publication and
acceptance facts remain in their respective reports. GitHub is the development
source of truth; maintainers sync Gitee manually. PyPI distributes only the
Python package; get examples from the repository. Follow the
[documentation language policy](DOCUMENTATION.md#language-policy) for English
primary references and the Chinese user guide.

## 1.1 Prepare a new checkout for CPU development

For a GitHub checkout, create a Python 3.10+ environment and install the project
and test dependencies in editable mode. These commands need no ABACUS, GPU,
SAI, or `mpi4py` and are suitable for ordinary CPU-only unit tests.

If `atst_tools` is already installed from another checkout, use
`PYTHONPATH=src` or `pip install -e .` before running worktree tests. Confirm
that `atst_tools.__file__` points to the current worktree.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -c "import atst_tools; print(atst_tools.__file__)"
python -m pytest tests/unit -q
```

`atst_tools.__file__` should resolve under the current checkout's
`src/atst_tools`. This environment verifies only ordinary tests that do not
need calculation backends. Verify ABACUS/DP, image-level MPI, and site runtime
separately under the evidence boundaries in
[EXAMPLE_VALIDATION_OPERATIONS.md](EXAMPLE_VALIDATION_OPERATIONS.md). Never
report unexecuted site or calculation checks as passing.

The CLI and Python API share `atst_tools.workflows.execution`. The service
layer selects the caller's MPI world before dispatching to execution helpers;
the CLI layer handles arguments, templates, and output. Standalone
`validate_ts` / `atst vibration validate` reads existing results; it is not an
automatic workflow postprocessing step.

## 1.2 External handoffs from completed plans

Two completed implementation plans were archived on 2026-10-16. The handoffs
below remain open; archiving the plans did not complete external acceptance.

| Handoff | Owner and closure condition | ATST-Tools responsibility |
| --- | --- | --- |
| abacuslite implementation | Maintain calculator/parser repairs in the independent `QuantumMisaka/abacuslite` repository; this repository owns only the ATST adapter and legacy import forwarding. | Backend checklist here; historical snapshot ledgers remain audit evidence. |
| Later abacuslite SIF/harness delivery | The parent repository's ABACUS owner handles delivery and acceptance. A previous direct SAI force-read check passed, but does not replace later platform delivery. | Backend snapshot and version notes; do not reopen the completed implementation here. |
| Convergence consumption | The Paimon owner completes fixture mapping and joint acceptance. Parent companion plan: `toolbox/ABACUS/docs/superpowers/plans/2026-09-17-matesbench-toolbox-hardening-plan.md`. | [API stage facts](../user/PYTHON_API_REFERENCE.md) and `docs/reports/data/convergence_fixtures_20260917/`; actual runtime and curated artifact updates need their own evidence. |
| GPU P6 platform migration | The ABACUS/MLIP-Agent owner completes shared image parameters/runner, guide, handoff tests, and E2E/platform acceptance. | [Active plan](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md), retaining conditional DP container/FT²DP items. |

Keep the current design sources until their decisions are absorbed into
long-lived references; code delivery alone does not decide archival. See the
[local integration closeout](../reports/MAIN_REVIEW_FIXES_2026-10-16.md#6-本地合入与在途收口2026-10-16)
for item-level disposition.

<a id="2-新增或修改-workflow"></a>
## 2. Add or change a workflow

- Integrate with the discriminated union and type table in
  `utils/config_schema.py`; update the CLI template and `api/services.py`
  dispatch. Check result adaptation, composite artifacts, and profiles/plots
  according to the feature. A new workflow must produce its own stage facts and
  manifest instead of asking the API to infer convergence from trajectories.
- Define input/restart identity, frozen results, and artifact path contracts.
  The outer composite workflow owns the top-level manifest; child tasks return
  stage facts. Verify scientific execution parity between CLI and API while
  preserving each interface's existing output contract.
- Update the supported workflows and quick start in `README.md`.
- Update `docs/user/USER_GUIDE_CN.md`, `CLI_REFERENCE.md`, and
  `CONFIG_REFERENCE.md`.
- Add or update `examples/<case>/config*.yaml` and `examples/README.md`.
- Update `docs/reports/FEATURE_STATUS_MATRIX.md`.
- Add or update workflow and example tests and any necessary validation report.
- Keep runtime messages (print/warning/logging/exceptions) in English. When
  changing convergence or diagnostic text, update tests that lock semantic
  tokens.
- Reuse `utils/geometry.py` for fixed-cell preparation: input tolerance
  `1e-5 Å` with `rtol=0`, retaining values within tolerance; adjust only the
  necessary periodic vectors in internal run copies for NEB. Prepare geometry
  before endpoint checks or calculations. After cell/PBC changes, discard old
  SPC, endpoint labels, and constant-potential facts. The caller passes its
  existing world to coordinate root warnings and existing failure sync; the
  geometry primitive must not create a communicator. See the lasting
  [configuration reference](../user/CONFIG_REFERENCE.md#22-nudged-elastic-band-neb).

## 3. Add or change a YAML field

- Change `src/atst_tools/utils/config_schema.py`.
- Regenerate `docs/user/YAML_INPUT_VARIABLES.md`.
- Explain semantics, the effect of defaults, and common combinations in
  `docs/user/CONFIG_REFERENCE.md`.
- Update example YAML.
- Run `tests/unit/test_config.py` and relevant workflow/example tests.

## 4. Add or change the CLI

- Update `docs/user/CLI_REFERENCE.md`.
- Update operational examples in `docs/skills/atst-cli/SKILL.md`.
- Update the README's short command list if needed.
- Add CLI tests or update existing command tests.

## 4.1 Add or change the stable Python API or process runner

- Preserve stable root imports in `atst_tools.api.__all__`; the runner must not
  become a new root import or change `atst` CLI behavior.
- Update `docs/user/PYTHON_API_REFERENCE.md`, the README, Chinese user guide,
  release notes, and feature matrix. Explain the JSON schema, exit codes,
  manifest authority, and MPI responsibility boundary.
- Check `python -m atst_tools.api.runner` with API/document, clean-wheel, and
  actual MPI gates. The runner only consumes the API; it must never launch
  Slurm, `mpirun`, or `srun`.

## 5. Add or change a calculator backend

See the [2.3.1 release notes](../releases/RELEASE_NOTES_2.3.1.md) for
publication and installed-package validation. The
[integration closeout](../reports/ABACUSLITE_230_CLOSEOUT_2026-10-19.md)
records historical worktree disposition. Main superseded the old
`integrate/abacuslite-atst229-20261017` branch and incorporated its scientific
repairs. Continue from current main; do not restore that branch's vendored
fallback.

- Update the README backend section and project boundary.
- Update calculator configuration in `docs/user/CONFIG_REFERENCE.md`.
- Update runtime dependencies and environment boundaries in
  `docs/user/USER_GUIDE_CN.md`.
- Update feature/status reports and calculator factory tests.
- If the backend involves ABACUS/DP environments, add a validation report or
  record the relevant boundary in an existing report.
- Release 2.3.1 declares `abacuslite>=1.2.1,<2` as a runtime dependency. ABACUS
  uses only the independently installed package. Missing or broken imports
  must fail without fallback. The old
  `atst_tools.external.ASE_interface.abacuslite` root, `core`,
  `io.generalio`/`latestio`/`legacyio`, and `utils.ksampling` module paths are
  thin forwarding layers. Paimon's direct `generalio` import remains usable
  and resolves to the same object as in the independent package.
- The `installed-abacuslite-consumer` job in `.github/workflows/tests.yml`
  builds an ATST wheel. Normal PR/push runs use published abacuslite 1.2.1;
  the scheduled run tracks the latest PyPI version in the compatible range;
  manual `abacuslite_ref` runs can build a candidate wheel from a coordinated
  commit. There is one external installation environment. Invoke
  `scripts/run_abacuslite_consumer.py --atst-root ROOT --backend external --report JSON`
  from outside the checkout, then run `--verify-report JSON`. There is no live
  vendored lane or two-report comparison.
- The runner checks installed ATST/abacuslite site-packages provenance,
  installed-file fingerprints, ATST wheel hash, absence of old-path imports
  in the first runtime consumer, independent numerical constants for raw
  SCF/MD fixtures, complete offline test case IDs/results, and pytest start/end
  provenance. Tests run from the repository root for relative documentation
  and example paths. `ATST_TEST_INSTALLED_WHEEL=1` and a shared child-process
  environment helper retain installed provenance; lazy `sitecustomize`
  prevents source shadowing. Reuse that helper in new Python subprocess tests.
  Explicit legacy forwarding tests may import compatibility paths, but they
  do not constitute a second implementation.
- `ABACUSLITE_SNAPSHOT.md` and `PATCHES.md` retain frozen history. Paired
  acceptance wheel hashes, raw logs, and 2026-10-17 results remain in Git
  history. The old drift checker, vendored implementation CI, and snapshot
  mutation tests are retired; test new parser repairs in the independent
  abacuslite repository.
- When maintaining abacuslite property-derived keywords, compare explicit
  inputs and derived values using ABACUS switch semantics: `True`, `1`, and
  `"1"` are equivalent. `False`/`0` still conflicts with the `"1"`
  automatically required by a `forces` or `stress` request.

## 6. Add or change dependencies

- Keep default `dependencies` limited to light runtime dependencies needed
  for an ordinary installation. Put heavy backends, MPI, plotting, and
  publication tools in `[project.optional-dependencies]` where possible.
- Sella is a first-class workflow backend. Keep `sella>=2.5,<3` in default
  dependencies unless there is clear compatibility evidence for a rollback.
- DP workflows use the `dp` extra; MPI image-level parallelism uses `parallel`;
  NEB plotting helpers use `plot`.
- Basic installation tests must not require `mpi4py`. Before validating image
  parallelism with the `parallel` extra, users must confirm an MPI import and
  launcher compatible with their site.
- When changing dependency ranges, update the README,
  `docs/user/USER_GUIDE_CN.md`, and this file.
- Add or update package metadata tests and run build checks:
  `pytest tests/unit/test_package_metadata.py -q`, `python -m build`, and
  `python -m twine check --strict dist/*`.
- For a release that includes the stable Python API, run
  `python scripts/verify_wheel_api.py`. It builds a wheel in a temporary
  directory, installs it into a temporary venv (resolving dependencies from
  the configured index by default), and checks public root imports, a
  controlled H2/Au public API example, installed API runner JSON handoff,
  and explicit CLI/API parity. It leaves no build artifacts in the worktree.
  If `mpi4py` and `mpiexec` are ready in the release environment, also run
  `python scripts/verify_wheel_api.py --mpi-smoke`. This time-limited two-rank
  smoke check verifies that an image-parallel NEB/AutoNEB rank-0 endpoint
  failure or rank-local optimizer construction failure makes every rank exit
  with a typed API failure. It explicitly skips when no launcher is found.

## 7. Add or change an example

- Update the learning path, directory descriptions, and chemical systems
  table in `examples/README.md`.
- For local example maintenance checks, SAI/Slurm runs, curated outputs, or
  run provenance, consult
  `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md`. The examples README does
  not carry these maintainer operations.
- Update `examples/reference_results.json`, or state that the example has no
  reference result yet.
- Keep new inputs under `inputs/` or another controlled path; do not commit
  generated output.
- Run example parsing, dry-run, or reference-result tests.

<a id="71-新增或修改基准工具链bench"></a>
## 7.1 Add or change the benchmark tooling

Terminology set on 2026-09-21: **bench** is the measurement toolkit
(`atst_tools.bench`); **batch** is one run of a manifest within an existing
allocation. **Harness** is a historical name for these modules and artifacts.
Keep it only in the frozen strings below; do not use it in new prose or code.

The three tools are:

| Tool | Command | Purpose |
| --- | --- | --- |
| Batch runner | `python -m atst_tools.bench.batch_runner --manifest cases.json --out runs --devices 0,1 --slots 1 --cpu-budget 8 --threads 2` | Execute a case manifest inside an existing allocation: slot scheduling, timeout cleanup, per-case reports, and batch summary. |
| Variant sweep | `python -m atst_tools.bench.sweep --manifest cases.json --out runs/sweep --devices 0,1 --slots 1,2,3 --repeats 3` | Alternate the order of a variant × repeat matrix and write `sweep_summary.json`. |
| Measurement record | `python -m atst_tools.bench.record --manifest cases.json --out runs/bench_record.json --run-dir runs --job-id … --partition … --qos …` | Record revision, branch, dirty state, manifest and fixture hashes, result-tree hash, and operator fields. |

Site one-command entry point: `scripts/sai_runtime_bench.sbatch` (timed sweep
→ evidence pass → record).

Channel fixtures (2026-09-22): repeatable `record --fixture` keeps the
per-field behavior of file fixtures; directory fixtures record `file_count`
and `tree_sha256`. Repeatable `--fixture-labeled LABEL=PATH` writes entries
to `inputs.fixtures` in CLI order alongside `--fixture`, with an additional
`label`. Directory PATH entries also record `file_count`/`tree_sha256`;
missing-fixture warning text is unchanged. Accordingly,
`scripts/sai_runtime_bench.sbatch` passes `MODEL` as `dp_model=` and
`ABACUS_INPUTS` (file or directory) as `abacus_inputs=`. It writes the label
set into `--note`; the ABACUS channel is no longer recorded as a DP model hash.

Manifest template: `examples/runtime_batch_cases.example.json`. Fields:
`case_id`, `config`, `slots`, `threads`, `timeout_s`, `workdir`, `launcher`,
`ranks`, and `env`. **Every case needs its own work directory**; without
`workdir`, use the configuration directory. The path-collision fix recorded
on 2026-10-16 rejects duplicate resolved paths, including explicit/default
directories and symlink aliases; it shipped in
[2.2.9](../releases/RELEASE_NOTES_2.2.9.md). A `case_id` must be a safe single
path component, may contain internal spaces, and must pass through the
progress protocol intact. `env` may carry ordinary custom values. The batch
controls managed device, thread, cache, and binding facts; YAML/runtime,
explicit `omp`, and runner arguments cannot exceed that budget or rewrite
coordinator-managed input/output locations. Resolve a relative `config` once
against the batch launch cwd when loading the manifest. Preflight and both
workers use the same absolute path, avoiding a same-name different file after
`chdir`. See the [repair validation report](../reports/MAIN_REVIEW_FIXES_2026-10-16.md)
for evidence and compatibility details.

Account for threads as `case.threads × ranks`. Prefer the case's explicit
`ranks`; otherwise infer it from launcher rank arguments, defaulting to 1
when unrecognized. Bench does not automatically audit backend subprocess
counts launched by arbitrary calculator commands. Budget nested ABACUS MPI
resources explicitly. This is a scheduling budget, not an operating-system
CPU isolation boundary.

New runs produce `<out>/<case_id>/case_report.json` per case,
`batch_summary.json` for the batch, and `worker.out` / `worker.err` in each
case report directory. A case with `runtime.telemetry` also produces
`runtime_evidence.json`; the batch side can produce `bench_record.json`.

**Shared worker mode (`--share-worker`, added 2026-09-21)** runs all cases
sequentially in one worker process, paying model loading and first-call warmup
once. In a maintainer measurement, a two-case CCQN batch fell from 68.2 s to
34.2 s; the second case took 3.1 s. It requires `--slots 1` and rejects
per-case `launcher`, inconsistent per-case `env`, over-budget threads, and
empty `--devices`. The shared worker starts as an already-bound process:
`runtime.launch.build_child_environment` publishes `ATST_RUNTIME_BOUND`,
`ATST_INHERITED_DEVICES`, `ATST_EFFECTIVE_DEVICES`, and `ATST_BINDING`. Thus
configurations with `runtime:` can run, while requests that conflict with
the binding **fail closed per case** (for example, requesting `devices: [1]`
when only device 0 is held). A single process has no rank rotation, so
configured `round_robin` has no rotation effect. `--timeout` and
`--stop-on-failure` still apply: a timeout kills the worker, marks that case
`timeout`, and marks the others `failed` / `shared worker exited`. Additional
artifacts are `<out>/batch_jobs.json` and `<out>/worker.out|err`; each case
report gains `"shared_worker": true`.

Historical names: before 2026-09-21, these artifacts were named
`harness_case.json`, `harness_summary.json`, and `harness_worker.{out,err}`.
Archived slices in `docs/reports/data/**` retain those names. `bench_record`
accepts both old and new summary filenames, preferring the new one. Two
historical spellings are **frozen**: the schema string
`atst-bench-harness-v1` is a versioned document identifier, not a module
name, and the evidence value `ATST_THREADS_SOURCE=harness` is the archived
sidecar's `threads_source`.

Boundary: bench is not a production queue or scheduler. It does not request
resources or queue across jobs, and it does not add a public `atst batch`
interface. Scientific logic belongs in `workflows/`. Regression tests:
`tests/unit/test_bench_batch_runner.py` and
`tests/integration/test_bench_batch_runner_mpi.py`.

## 8. Add a report or move an old report

- State the date, environment, and evidence scope in every new report.
- Link a report from `docs/index.md` only when it is a core entry point or
  current high-priority evidence.
- Absorb findings from a superseded report before moving it to
  `docs/archive/reports/`.
- Put new specs/plans under `docs/superpowers/specs/` or
  `docs/superpowers/plans/`. When complete, absorb their conclusions and move
  them to `docs/archive/`.

## 9. Prepare a release

- Use `[project].version` in `pyproject.toml` as the sole package version
  source. `atst_tools.package_version()` reads it in the source tree and reads
  distribution metadata after installation.
- Update `docs/releases/RELEASE_NOTES_<version>.md`.
- Update the README badge, version text, and release scope.
- Run the offline gate: `python scripts/check_release_readiness.py --tag v<version>`.
- Complete local and CI mechanical gates in
  [GOVERNANCE_AND_RELEASE_GATES.md](GOVERNANCE_AND_RELEASE_GATES.md). An
  independent review by the current model family is the usual final review.
  For AGENTS, SKILL, or governance contract changes, the maintainer may seek
  cross-family review as owner-judged advisory evidence. Portable review
  evidence bound to a frozen diff is as valid as launcher output; absence of
  cross-family review does not block delivery.
- Administrators/maintainers handle GitHub branch protection, `pypi`
  Environment approval/tag restrictions, PyPI Trusted Publisher, push/tag/
  release, manual Gitee synchronization, and post-publication rendering
  checks. Editing repository files does not perform those actions.
- If the release changes examples or curated outputs, verify execution
  evidence and provenance against
  `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md`.
- Update `FEATURE_STATUS_MATRIX.md`.
- Run documentation link, format, and relevant tests.

## 10. Minimum checks

```bash
git diff --check -- README.md docs examples/README.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md
python scripts/check_docs_governance.py
```

If the YAML schema changes:

```bash
conda run -n atst-dev python -m atst_tools.utils.config_docs --output docs/user/YAML_INPUT_VARIABLES.md
conda run -n atst-dev pytest tests/unit/test_config.py -q
```

If runtime messages change (print/warning/logging/exceptions/CLI text):

```bash
conda run -n atst-dev pytest tests/unit/test_program_output_language.py -q
```
