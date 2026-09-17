# Workflow Convergence Handoff Implementation Plan

**Goal:** Preserve optimizer convergence facts across ATST workflows and their public artifacts, with unified English runtime diagnostics and backward-compatible CLI/API execution semantics.
**Spec:** none - requirements supplied directly in the 2026-09-17 maintainer discussion of MatESBench A4-5, extended by the 2026-09-17 maintainer decisions that (a) all program-visible runtime strings in ATST-Tools are English and (b) convergence stage facts and advisories are owned by one shared helper, not per-workflow implementations.
**Authorization:** The maintainer requested development plans in ATST and the Paimon consumer repository. This document is the producer-side handoff, not evidence that implementation, dependency installation, computation, push, tagging or publication has been authorized or completed. On 2026-09-17 the ATST maintainer directed that this plan be revised against the actual repository state before implementation.
**Architecture:** Follow ATST's ASE-native workflow architecture; record facts at optimizer boundaries and reuse artifact manifest stages, stable API and summary adapters. A single convergence helper (`utils/convergence.py`) owns stage-record construction, English advisory rendering and root-only emission; workflows only capture optimizer-owned signals. ATST remains independent of Paimon, ATP, Slurm and outer MPI launchers.
**Verification:** Focused behavior-first regressions, workflow/API/summary tests, a package-level program-output language check, standalone documentation checks, clean-wheel API/runner checks and applicable MPI tests under the repository development/release pipeline.

**Date:** 2026-09-17
**Status:** in progress (A0 complete; docs/pipeline groundwork landed on `feature/workflow-convergence`)
**Owner:** ATST maintainers/developer; Paimon developer owns consumer mapping and joint acceptance.

## 1. Scope and ownership

The motivating defect is information loss between optimizer termination and artifact consumers, not a request to change optimization algorithms or certify transition states.

Repository-grounded starting facts, inspected at `4c96691` (the published `v2.2.5` release commit; `origin/main` is one docs commit later at `cf86790`, which records the verified 2.2.5 publication):

- Sella, CCQN, IRC and NEB already emit Chinese explicit-false advisories (`mep/sella.py`, `mep/ccqn.py`, `workflows/irc.py`, `scripts/main.py`); Relax, AutoNEB and D2S emit none.
- Sella, Relax and AutoNEB write no artifact manifest. Their API runs currently receive an api-synthesized `{"name": <workflow>, "status": "complete"}` stage with no convergence facts. Manifest coverage today is NEB, D2S, CCQN, Vibration, IRC and MD (`FEATURE_STATUS_MATRIX.md`).
- CCQN writes `atst_artifacts.json` whenever it runs, including as a D2S refinement; D2S then overwrites that file. Composite workflows therefore need an explicit manifest-owner rule before constituent facts are added.
- `sella>=2.5,<3` and `ase>=3.28` are pinned; `Sella.run()` returns the converged bool, while the current post-run `dyn.converged()` call reads Sella's projected forces and must not be assumed to be calculation-free across versions.
- Package-internal Chinese runtime strings are bounded: the four advisories above plus the `utils/reverse_config.py` error messages (`atst prepare`); `scripts/cli.py` output is already English.

| Workflow | Observed baseline | Required work |
|---|---|---|
| Sella | Advisory reads convergence via post-run `dyn.converged()`, then returns final atoms | Consume the `run()` return; persist the authoritative signal and available step/criterion facts; keep projected-force/constraint semantics |
| CCQN | run() signal drives advisory; manifest stage is execution-complete only | Persist signal through the shared helper; preserve force plus PRFO-mode semantics |
| NEB / CI-NEB | Manifest stages already contain converged/fmax/steps/actual_steps | Reuse existing facts; migrate advisory to the shared helper and English; align consumer documentation |
| AutoNEB | Internal qn.run() return values are discarded; no manifest | Capture local/stage outcomes with iteration/subset identity; define the final required optimization scope; create the top-level record through the owner rule |
| ATST Relax | opt.run() return value is discarded; no manifest | Capture convergence and add explicit-false advisory; define the durable record path |
| IRC | Sella direction signals drive text warnings; descent ignores return values | Persist per-direction facts with backend-specific criteria |
| D2S / endpoint optimization | Endpoint and rough-path run() results can be discarded | Preserve constituent stage facts without changing intentional coarse-stage continuation; dimer refinement stays explicitly unknown |

Native ABACUS relax/cell-relax in Paimon is not ATST Relax and is outside this producer implementation.
Dimer, DMF and unrelated algorithm changes are not added merely because they also optimize structures.
No automatic restart, extra force evaluation, new scientific-success gate, scheduler integration or algorithm rewrite is included.

Starting inspection used ATST commit `4c96691`; 2.2.5 is now published, so additive compatible work targets the next patch release (expected 2.2.6) subject to A6 confirmation. Execution starts from `origin/main` in a dedicated development branch/worktree, carrying this plan and its ledger registration; do not patch an installed site-packages copy or silently advance Paimon's gitlink.
Paimon companion plan is in the app-tools repository at
`toolbox/ABACUS/docs/superpowers/plans/2026-09-17-matesbench-toolbox-hardening-plan.md`.
This is a consumer pointer, not an external filesystem dependency or a second ATST specification.

## 2. Components and responsibilities

| Expected locations | Responsibility |
|---|---|
| `utils/convergence.py` (new; equivalent factoring acceptable) | The only owner of stage records and advisories: record construction/serialization, English advisory rendering (false emits, true/unknown stay silent), root-only emission via `utils/mpi.py::run_rank_zero_section`, explicit non-executed/skipped semantics. It must accept only already-captured facts and must never read `Atoms`, forces, calculators or trajectories. |
| `mep/sella.py`, `mep/ccqn.py`, `workflows/relax.py`, `workflows/irc.py` under `src/atst_tools/` | Capture the optimizer-owned termination signal at the optimizer boundary and hand facts/criterion provenance to the shared helper; no workflow-local message prose |
| `scripts/main.py`, `mep/autoneb.py`, `workflows/d2s.py` | Preserve multi-stage/direction/iteration identity, final-stage role and MPI ownership; D2S owns its single top-level manifest |
| `utils/artifacts.py`, `utils/summary.py`, `api/models.py`, `api/services.py`, `api/runner.py` | Durable stage facts, top-level manifest authority, compatible serialization/projection, api-synthesized (execution-complete, convergence-unknown) semantics |
| `tests/unit/test_convergence.py` (new), `test_workflows.py`, `test_api.py`, `test_api_runner.py`, `test_summary.py`, `test_mpi_parallel.py` | Helper contract, behavioral, compatibility and rank-safety acceptance |
| `utils/reverse_config.py` and the four existing advisory sites | Bounded language sweep to English runtime strings (part of the repo-level rule) |
| API/workflow documentation, examples where relevant, feature/documentation ledgers, `AGENTS.md`/HANDOVER rule registration | Public meaning, language rule, compatibility and actual capability status |

Prefer a small reusable fact/diagnostic helper; do not introduce a parallel workflow engine or results database.

## 3. Producer-consumer contract

Use existing manifest `stages` as the durable source, preserving NEB's existing `name`, `status`,
`converged`, `fmax`, `steps` and `actual_steps` meanings. `status=complete` describes execution.
`converged` is strictly true, false or null; unavailable/non-boolean signals must not become false through truthiness conversion. Keep `schema_version = atst-artifacts-v1`; new fields are additive and optional.

Centralization requirements:

- The shared helper is the only place that renders convergence advisories and constructs stage records. Workflows supply the optimizer-owned signal, criterion identity, thresholds, step counts and stage/direction/iteration identity; they do not format messages.
- The helper must not compute scientific convergence, must not call `Atoms.get_forces()`/`converged()`/trajectories, and must not trigger any calculator or SCF request. Missing measured quantities stay unavailable.
- Root-only emission reuses the existing rank-zero section helper; no new MPI collective is introduced in a root-only callback.

Representation requirements:

- Each record must identify the workflow stage and, where applicable, IRC direction or AutoNEB iteration/image subset.
It must distinguish intermediate/coarse optimization from the final required stage(s), with criterion provenance and applicable thresholds.
Step counts refer to that stage/direction; cumulative counters require a recorded baseline and delta, not relabeling the cumulative value.
Additional names/serialization for criterion, stage role and direction are to be settled by ATST A1 in the existing API reference with executable fixtures, then consumed by Paimon without inventing alternate fields.

- Existing final Atoms/images return contracts, CLI exit codes and successful execution envelope remain compatible. Existing manifests remain readable.
- The manifest is authoritative and has exactly one owner: the top-level workflow. Nested optimizations (D2S refinement, AutoNEB iterations, NEB endpoint relaxation) must not write or overwrite the top-level manifest; the owner aggregates their records.
- API output must preserve/discover the same durable record through its existing manifest handoff and documented optional projections; do not create competing convergence values. A synthesized manifest (`manifest_source: api_synthesized`) means execution complete with convergence unknown; it is not a convergence claim.
- The summary adapter must retain records without recomputing scientific convergence from trajectory existence or raw force maxima.
- Extra measured quantities are optional, finite and unit-labeled, and identify whether they are projected forces, constraint residuals or another optimizer-owned quantity.
- Final true means that optimizer's stopping criteria were reported satisfied; it is not a claim of a scientifically validated target TS or correct reaction connectivity.
- No blanket AND over every stage. Warmup/coarse/intermediate false stays visible but cannot override a successfully converged final stage. Required final false or missing observations must not be hidden by intermediate true.
- A skipped or unexecuted stage is not a converged stage; endpoint/constituent stages that did not run are recorded `skipped` (or omitted), not `complete`.
- Explicit false produces a concise **English** advisory from the same facts. Unknown is represented structurally and must not emit an invented non-convergence warning.
- D2S `method: dimer` refinement facts remain unknown unless the dimer optimizer exposes an already-available termination observation; no raw-force re-judgment is allowed for it.

Language requirements (repo-level maintainer decision):

- Every program-visible runtime string is English: `print`, warnings, logging, exception messages, CLI help/error text. Documentation keeps its current language (`README`, `docs/`, release notes); new/changed code comments and docstrings are English.
- The sweep is bounded to the package: the four existing advisories and the `utils/reverse_config.py` messages. `external/` is out of scope.
- Tests lock stable English semantic tokens, not full prose.

Example of the intended warning style, not a string-locked interface:

```text
Warning: CCQN finished without satisfying its optimizer convergence criteria
(fmax=0.05 eV/Angstrom, steps=100, max_steps=100).
Execution completion does not imply optimizer convergence.
```

## 4. Tasks

### A0: Establish the ATST execution baseline

**Dependencies:** none. **Delivery:** standalone repository worktree, environment/source identity and scoped validation commands.

- [x] Read `AGENTS.md`, `docs/developer/HANDOVER.md`, `GOVERNANCE_AND_RELEASE_GATES.md` and relevant API/workflow references at the actual base.
- [x] Use the repository's `atst-dev` maintenance environment for implementation checks; record interpreter, imported source, ASE/Sella/ATST versions and MPI availability. Do not treat Paimon's abacus-env as automatically equivalent.
- [x] Record the actual base commit and worktree state. Current facts: 2.2.5 is published from `4c96691`; `origin/main` is `cf86790`; the local checkout/inspection base is one commit behind and this plan plus its ledger registration are uncommitted. Move the work to a development branch/worktree based on `origin/main` and carry both files; do not rebase onto the release commit.
- [x] Separate offline tests, clean-install checks and authorized real ABACUS/DP/MPI calculations. No new package installation or real job is implied by this plan.

### A1: Define compatible stage records, helper interface and fixtures

**Files:** `utils/convergence.py` interface, artifacts/summary/API adapters and `docs/user/PYTHON_API_REFERENCE.md`; nearest existing tests.
**Dependencies:** A0. **Delivery:** documented field meanings, helper interface and representative JSON fixtures agreed with the Paimon consumer owner.

- [ ] Inspect the existing NEB manifest and summary stage pass-through before adding fields.
- [ ] Define the helper interface: fact/criterion inputs, record construction, advisory emission, root-rank handling; no message formatting outside the helper.
- [ ] Add regression fixtures for true/false/null, missing legacy records, skipped stages, ordinary→CI NEB, AutoNEB stage identities, forward/backward IRC, api-synthesized manifests, and D2S constituent ownership.
- [ ] Define a bounded final-stage selection policy for each workflow, including AutoNEB execution modes; record unknown where completion of the required scope cannot be established. Do not invent a generic scientific-success aggregate.
- [ ] Ensure JSON-safe values, per-stage units/provenance, legacy readers, `atst-artifacts-v1` compatibility and stable root imports remain valid.
- [ ] Deliver the agreed fixtures/field reference to the consumer owner. Routine field naming is an ATST-owned implementation decision; changes to execution/scientific gating require renewed design discussion.

**Verification:** artifact → summary/API round-trip preserves facts; no optional extension changes legacy return objects or forces consumers to parse diagnostic text.

### A2: Implement the shared helper and capture single-stage optimizer facts

**Files:** `utils/convergence.py`, `tests/unit/test_convergence.py`, Sella, CCQN, ATST Relax and shared artifact/diagnostic support.
**Dependencies:** A1.

- [ ] TDD the helper first: true/false/unknown, skipped/non-executed, root-only emission, no calculator access, JSON-safe records.
- [ ] Migrate the existing Sella/CCQN advisories to the helper; add the Relax explicit-false advisory. Sella consumes the `Sella.run()` return (verified bool in the pinned `sella>=2.5,<3` + ASE `>=3.28`) instead of the post-run `dyn.converged()` call.
- [ ] Preserve Sella's own projected-force/constraint semantics and CCQN's force plus PRFO-mode semantics. Never replace them with a common raw-force threshold check.
- [ ] Record facts before optimizer objects leave scope; retain existing final structure/Atoms contracts.
- [ ] Prove that reporting/serialization does not issue extra calculator requests and that inability to obtain optional diagnostics does not corrupt a completed workflow.

**Verification:** helper and workflow tests pass; warning occurrence matches deterministic false, while true/unknown semantics remain distinct; English tokens replace the previous Chinese advisory tokens in the four existing test sites.

### A3: Capture staged and directional facts

**Files:** NEB entry in `scripts/main.py`, both AutoNEB execution paths, IRC Sella/descent backends, D2S constituent optimizations and endpoint optimization paths.
**Dependencies:** A1; reuse A2 mechanisms.

- [ ] Keep NEB's existing stage fields and use final-stage scope for its primary advisory; migrate the NEB warning to the shared helper and English.
- [ ] Capture AutoNEB optimizer outcomes per iteration/subset and identify final refinement/smoothing scope in supported modes; no last-subset shortcut to whole-band convergence.
- [ ] Preserve per-direction IRC signals, backend identity and stage-local step deltas; migrate the IRC warning to the shared helper. Descent convergence cannot be described as Sella IRC basin confirmation.
- [ ] Record endpoint and rough-path outcomes in D2S without introducing a new stop gate or erasing intentional rough-stage continuation. D2S remains the only writer of its top-level manifest; constituent CCQN must not overwrite it.
- [ ] Keep partial/failed execution information distinct; do not manufacture records for later stages that did not run or conceal an exception with a success record.
- [ ] Verify root-only artifacts/advisories and rank-consistent control flow for parallel NEB/AutoNEB.

**Verification:** staged and directional fixtures include mixed outcomes and absent final stages; serial and MPI regressions preserve existing workflow behavior and do not duplicate warnings across ranks.

### A4: Complete public handoff and consumer acceptance

**Files:** artifact summary, stable API models/services/runner and owning suites; API/workflow docs.
**Dependencies:** A2/A3.

- [ ] Verify direct CLI, stable Python API, process runner and artifact summary expose the same authoritative records or documented manifest reference; document the api-synthesized (execution complete, convergence unknown) meaning.
- [ ] Keep existing API result schema/root imports compatible; additions are optional and documented. No ATP/evidence vocabulary or Paimon import enters ATST.
- [ ] Provide the Paimon owner candidate commit/source identity, field reference and real serialized examples, including legacy/unknown, multi-stage and synthesized-manifest cases.
- [ ] Run producer-consumer fixture agreement with the Paimon evidence/summary tests; consumer presentation must not alter backend values or infer TS validation.

**Verification:** results survive clean serialization and restart/history boundaries without stale convergence facts being reused as current-run outcomes.

### A5: Repository validation, language sweep and documentation closeout

**Dependencies:** A2–A4. **Delivery:** reviewed ATST candidate; publication remains a separate state.

- [ ] Review/merge temporary tests into owning suites. Run focused tests and then `conda run -n atst-dev python -m pytest tests -q` using the repository's opt-in boundaries for external calculations.
- [ ] Complete the bounded English sweep: replace the four workflow advisories through the helper, translate `utils/reverse_config.py` runtime messages, and remove remaining Chinese runtime strings inside `src/atst_tools` (excluding `external/`).
- [ ] Add a deterministic program-output language check (e.g. `tests/unit/test_program_output_language.py`) that scans package `print`/warning/logging/exception message arguments for CJK characters; do not flag docstrings or `external/`.
- [ ] Follow HANDOVER §4.1 for API/document, clean-wheel runner and applicable MPI checks; use `scripts/verify_wheel_api.py` and its MPI mode where supported and authorized. Missing launcher/dependencies must be reported, not counted as passing MPI validation.
- [ ] Register the language rule and plan/spec registration path in `AGENTS.md`, `docs/developer/HANDOVER.md` and `docs/developer/DOCUMENTATION_STANDARDS.md`; update `docs/developer/DOCS_ARCHITECTURE.md` so `docs/superpowers/{specs,plans}` is the active spec/plan location. AGENTS.md edits follow the normal independent review boundary.
- [ ] Update API/workflow docs, relevant examples, `FEATURE_STATUS_MATRIX.md` (including the Artifact Manifests row for any newly durable workflow) and `DOCUMENTATION_STATUS_REPORT.md`; record the user-visible diagnostics-language change in release notes later. Avoid touching YAML schema/generated parameter tables unless an actual input change is required.
- [ ] Run `conda run -n atst-dev python scripts/check_docs_governance.py`, `conda run -n atst-dev pytest tests/unit/test_docs_governance.py -q`, and `git diff --check`.
- [ ] Obtain independent review of semantic compatibility, new calculation avoidance, multi-rank safety and language-rule completeness; resolve important findings before consumer integration.

### A6: Maintainer-controlled release and downstream rollout

**Dependencies:** A5 and explicit release/integration authorization.

- [ ] Select the version from the actual release line; 2.2.5 is published, so additive compatible work follows the next patch sequence unless the maintainer decides otherwise. Do not preassign a tag from this historical base.
- [ ] Follow `GOVERNANCE_AND_RELEASE_GATES.md`: version source, release notes/ledgers, readiness checks, build/twine checks, clean-wheel/API validation and applicable CI/MPI evidence. Release notes must state the user-visible runtime-diagnostics language change and the new optional manifest fields.
- [ ] Push/tag/PyPI publication remain maintainer actions; report actual artifact identity separately from an unpushed source commit.
- [ ] Paimon owner consumes the reviewed version/commit, updates its dependency declarations and validates the actual installed package/SIF before platform release. ATST does not build a Paimon-specific second runtime path.

## 5. Acceptance, rollback and handoff

Acceptance requires producer facts, durable artifacts, API/summary round-trip and consumer agreement, not merely English warning output. The shared helper must be the single advisory/record owner, no report-time calculator access may occur, and the language sweep must leave no Chinese runtime strings in the package outside `external/`.
No changes to optimizer algorithms, execution success codes, scheduler ownership or scientific acceptance gates are part of this work.
On incompatibility, retain/restore a previously validated producer-consumer runtime combination; do not backfill historical manifests with invented convergence.

The handoff package contains the reviewed commit/version, affected workflows, field documentation,
true/false/unknown and multi-stage fixtures, verification evidence and limitations, including whether
MPI/real backend/package publication were actually exercised. Implementation completion and
Paimon SIF/platform acceptance are independently recorded.

## 6. Execution record (2026-09-17)

Baseline and workspace:

- Base: `origin/main` `cf86790` (2.2.5 published). Execution branch: `feature/workflow-convergence` in the primary `deps/atst-tools` checkout.
- Ruling: an app-tools worktree (`.worktrees/atst-workflow-convergence`) was created and then abandoned, because `apply_patch` and child-agent workspaces bind to the primary working directory; isolation is provided by the feature branch on the clean published base. Cost if wrong: no second checkout for parallel branches; recoverable by re-creating a worktree at any commit.
- Environment ruling: `conda run -n atst-dev` resolves `atst_tools` to `/home/james/work/deepmodeling/atst-tools/src` through editable 2.2.3 metadata. Every verification run must use `env PYTHONPATH="$PWD/src" conda run -n atst-dev python ...` and confirm `atst_tools.__file__`. Available: ase 3.28.0, sella 2.5.0, mpi4py 4.1.2.
- Base verification: `env PYTHONPATH="$PWD/src" conda run -n atst-dev python -m pytest tests -q` passes with the repository's expected opt-in skips (MPI launcher, ABACUS run-dir, toolbox utils).

Prerequisites landed before implementation (commits `beb58a7`, `740089e`):

- `AGENTS.md`: corrected abacuslite/ase-abacus statements, added the English runtime-output rule, added `docs/superpowers/{specs,plans}` registration obligations, and added the documentation-governance check command.
- `docs/developer/DOCS_ARCHITECTURE.md`, `DOCUMENTATION_STANDARDS.md`, `HANDOVER.md`: plan/spec location moved to `docs/superpowers/`, active-plan registration requirement, language rule.
- Completed plans and legacy `docs/developer/plans/` files archived into `docs/archive/pending_delete/plans/` with ledger and pending-delete registration.
- `scripts/check_docs_governance.py`: new active-plan registration check with fixture tests; manual publish workflow default tag refreshed.

## 7. Plan delivery record

This file records planned work only. Documentation validation for this delivery is recorded separately from future workflow implementation evidence.

Revision record, 2026-09-17 (ATST maintainer-directed, grounded in repository state at `4c96691`/`origin/main` `cf86790`):

- Replaced the upstream draft's per-workflow advisory implementations with one mandatory shared helper (`utils/convergence.py`) owning records, English rendering and root-only emission; workflows only capture facts.
- Extended the language requirement from "English advisories" to the repo-level rule that all program-visible runtime strings are English, with a bounded sweep and a deterministic language check.
- Added the durable-record ownership rule for workflows that write no manifest today (Sella/Relax/AutoNEB) and the single top-level manifest owner rule for composite workflows (D2S/AutoNEB/NEB endpoints), including api-synthesized semantics.
- Recorded the real publication baseline (2.2.5 published; work targets the next patch release) and the requirement to start from `origin/main` rather than the stale local checkout.
- Bounded D2S `method: dimer` out of fact capture (remains unknown) and clarified skipped/non-executed stage semantics and `atst-artifacts-v1` compatibility.
