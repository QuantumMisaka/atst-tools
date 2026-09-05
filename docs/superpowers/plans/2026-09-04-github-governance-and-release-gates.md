# ATST-Tools GitHub Governance and Release Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make current stable-state documentation and GitHub CI mechanically enforceable before a PyPI upload, while documenting independent governance review as advisory evidence rather than a release gate.

**Spec:** `docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html` (R1-R7; decisions confirmed by the user on 2026-09-04).
**Status:** Task 5 本地实现完成：当前 main 是未发布工作；已补齐 exact tag/commit 绑定门禁，并将项目文档对齐 2026-09-05 已更新的 owner-judged advisory governance 策略。GitHub 设置、推送和后续发布验收仍待授权维护者执行。

**Architecture:** A small repository-local readiness checker owns exact tag-to-`HEAD`, tag/version/release-note consistency and is tested through temporary repository fixtures. General CI runs tests plus documentation governance on PR/main. The PyPI workflow resolves one exact tag namespace ref, performs all release checks and artifact creation before its OIDC-only publish job. Developer documentation separates optional, independent governance evidence from mandatory GitHub/PyPI release safety checks without trying to automate either.

**Tech Stack:** Python 3.10+, stdlib `tomllib`, pytest, GitHub Actions YAML, setuptools build, Twine.

## Global Constraints

- `pyproject.toml` remains the sole package-version source; current stable release is 2.2.3 until maintainers deliberately change it.
- Never push, tag, publish, alter GitHub Environment/branch-protection settings, or synchronize Gitee in this implementation.
- The workflow references the named `pypi` Environment and requests OIDC once those external settings are configured; no token or credential is added to repository files.
- CI may verify mechanical evidence only. Independent cross-family governance review is owner-judged advisory evidence; it never substitutes for authorization of a push, tag, publish, credential, or irreversible action.
- User documentation stays site-neutral and Gitee remains a manually synchronized same-content mirror.

---

## File Structure

| Path | Responsibility after implementation |
| --- | --- |
| `scripts/check_release_readiness.py` | Offline, reusable tag/version/release-note checker. |
| `tests/unit/test_release_readiness.py` | Fixture-based behavior tests for readiness failures and success. |
| `tests/unit/test_ci_workflows.py` | Structural contracts for main CI and PyPI preflight/publish separation. |
| `tests/unit/test_docs_governance.py` | Dynamic stable-version/document-fact contracts. |
| `.github/workflows/tests.yml` | PR/main/manual test and documentation-governance CI. |
| `.github/workflows/publish-pypi.yml` | Resolve, preflight/build, and least-privilege publish workflow. |
| `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md` | Human governance boundary, local gates, administrator-side settings, post-push checks. |
| `docs/developer/PYPI_RELEASE_AUTOMATION.md` | Current repository identity and actual workflow instructions. |
| `docs/developer/HANDOVER.md` / `DOCS_ARCHITECTURE.md` / `docs/index.md` | Current developer entrypoints and release checklist. |
| `docs/user/CONFIG_REFERENCE.md` | Correct maintenance date. |
| `docs/reports/DOCUMENTATION_STATUS_REPORT.md` | Registers the governing SPEC/plan and new developer gate entrypoint. |

## Task 1: Stable-document facts and local release-readiness contract

**Files:**
- Create: `scripts/check_release_readiness.py`
- Create: `tests/unit/test_release_readiness.py`
- Modify: `tests/unit/test_docs_governance.py`
- Modify: `README.md`, `docs/index.md`, `docs/user/CONFIG_REFERENCE.md`
- Modify: `docs/developer/PYPI_RELEASE_AUTOMATION.md`, `docs/developer/HANDOVER.md`, `docs/developer/DOCS_ARCHITECTURE.md`

**Test strategy:** Fixture repositories prove release readiness succeeds only for a v-prefixed tag matching `pyproject.toml` and an exact release note Compatibility line. Documentation tests derive the expected stable version from metadata and reject the old release-automation identity/trigger facts.

**Interfaces:** Produces `main(argv: Sequence[str] | None = None) -> int` in `check_release_readiness.py`; `--root PATH` makes fixture tests and CI use the same checker.

- [x] **Step 1: Write failing readiness and document-fact tests**

Add tests that create a temporary root with `pyproject.toml` version `9.8.7` and a release note. Assert `main(["--root", str(root), "--tag", "v9.8.7"]) == 0`; parameterize wrong tag, missing note, and wrong Compatibility line as nonzero. Extend docs governance so README badge/table, docs index release link, user guide, configuration reference, and API reference use the version loaded from root `pyproject.toml`; assert release automation contains `QuantumMisaka/atst-tools`, `v<version>`, and no `Owner: deepmodeling` / `Primary trigger: publishing a GitHub Release`.

- [x] **Step 2: Run focused tests to verify RED**

Run `conda run -n atst-dev python -m pytest tests/unit/test_release_readiness.py tests/unit/test_docs_governance.py -q`.

Expected: collection fails because the checker is absent, and documentation assertions expose stale release automation/date/link facts.

- [x] **Step 3: Implement the smallest checker and documentation correction**

Implement stdlib-only argument parsing and `tomllib` loading. Fail with one explanatory stderr message for each invalid contract; do not inspect git remotes or touch files. Rewrite release automation around `<version>` and actual tag-push/manual-ref workflow; update release entrypoint links/dates and add a concise developer gate link. Keep user prose limited to current stable version and installation facts.

- [x] **Step 4: Verify GREEN and owning suites**

Run `conda run -n atst-dev python -m pytest tests/unit/test_release_readiness.py tests/unit/test_docs_governance.py -q` and `conda run -n atst-dev python scripts/check_release_readiness.py --tag v2.2.3`.

Expected: both pass; command prints a release-ready confirmation without network access.

- [x] **Step 5: Commit Task 1**

```bash
git add scripts/check_release_readiness.py tests/unit/test_release_readiness.py \
  tests/unit/test_docs_governance.py README.md docs/index.md \
  docs/user/CONFIG_REFERENCE.md docs/developer/PYPI_RELEASE_AUTOMATION.md \
  docs/developer/HANDOVER.md docs/developer/DOCS_ARCHITECTURE.md
git commit -m "docs: align stable release and readiness facts"
```

## Task 2: GitHub CI and PyPI preflight separation

**Files:**
- Modify: `.github/workflows/tests.yml`
- Modify: `.github/workflows/publish-pypi.yml`
- Modify: `tests/unit/test_ci_workflows.py`

**Test strategy:** Static workflow contracts protect the reachable triggers, required commands, ordered release preflight, artifact handoff, and least-privilege publish boundary. YAML is not parsed by a new dependency; tests assert stable behavior tokens and job relationships already used by repository workflow tests.

**Interfaces:** Consumes Task 1 command `python scripts/check_release_readiness.py --tag "$RELEASE_TAG"`. Produces GitHub job names `test`, `documentation-governance`, `resolve-release`, `release-preflight`, and `publish` with explicit `needs` relations.

- [x] **Step 1: Write failing workflow-contract tests**

Extend `test_ci_workflows.py` with assertions that general CI has `push: branches: [main]`, a documentation-governance job running `python scripts/check_docs_governance.py`, and full pytest. Assert publisher defines resolve/preflight/publish jobs; preflight checks out `${{ needs.resolve-release.outputs.ref }}`, runs readiness, pytest, docs governance, build, Twine, and `scripts/verify_wheel_api.py`; publish needs preflight and has `id-token: write` only there.

- [x] **Step 2: Run the workflow tests to verify RED**

Run `conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q`.

Expected: FAIL because current workflows lack main push/docs job and release preflight separation.

- [x] **Step 3: Implement the two workflow contracts**

In `tests.yml`, retain PR/manual triggers and read-only permissions; add main push and a separate documentation-governance job with Python 3.10 and `.[test]`. In publisher, move ref resolution to an output job; preflight checks out that exact ref, installs `.[dev]`, executes the required checks in order, and uploads `dist/*`. Publish downloads that artifact and keeps `pypi` environment plus OIDC permission. Do not add Gitee, secrets, tags, releases, or checkout of an unverified ref.

- [x] **Step 4: Verify GREEN and YAML syntax**

Run `conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q` and `ruby -e 'require "yaml"; Dir[".github/workflows/*.yml"].each { |p| YAML.load_file(p); puts p }'` if Ruby/Psych is available; otherwise use Python's installed YAML parser only if available without adding a dependency.

Expected: contract tests pass and every workflow parses.

- [x] **Step 5: Commit Task 2**

```bash
git add .github/workflows/tests.yml .github/workflows/publish-pypi.yml tests/unit/test_ci_workflows.py
git commit -m "ci: gate releases before PyPI publishing"
```

## Task 3: Governance/release documentation and final gates

**Files:**
- Create: `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md`
- Modify: `docs/index.md`, `docs/developer/HANDOVER.md`, `docs/developer/PYPI_RELEASE_AUTOMATION.md`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`
- Modify: `docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html`
- Modify: `docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md`

**Test strategy:** Existing documentation governance and CI-contract suites protect linked active entrypoints. Manual verification confirms the documentation never claims push/tag/environment setup was performed.

**Interfaces:** Documents Task 1 checker, Task 2 jobs, existing `GOVERNANCE_REVIEW.md` launcher, and external administrator/post-push responsibilities without adding automation.

- [x] **Step 1: Add a focused documentation-entrypoint test**

Extend the relevant docs governance test so `docs/index.md` contains a local link to `developer/GOVERNANCE_AND_RELEASE_GATES.md` and the new guide names the checker plus `pypi` Environment boundary.

- [x] **Step 2: Run it to verify RED**

Run `conda run -n atst-dev python -m pytest tests/unit/test_docs_governance.py -q`.

Expected: FAIL because the new guide/link is absent.

- [x] **Step 3: Write the minimum durable guide and close the ledger**

Document three phases: local/CI mechanical checks, cross-family governance trigger/process, and GitHub/PyPI/Gitee post-push administrator checks. State explicitly that branch protection, pypi environment reviewers/tag restrictions, Trusted Publisher identity, tag/release, push, and mirror pull are not repository-file side effects. Register spec/plan and the guide in the documentation ledger; mark local implementation only after final verification, leaving external settings/render checks pending.

- [x] **Step 4: Run final verification**

Run:

```bash
git diff --check -- README.md docs .github scripts tests AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs .github scripts tests AGENTS.md
conda run -n atst-dev python scripts/check_docs_governance.py
conda run -n atst-dev python scripts/check_release_readiness.py --tag v2.2.3
conda run -n atst-dev python -m pytest tests -q
```

Also run a local wheel preflight: `conda run -n atst-dev python -m build`, `conda run -n atst-dev python -m twine check --strict dist/*`, and `conda run -n atst-dev python scripts/verify_wheel_api.py`; move any temporary `dist/` to `$HOME/scratch/atst-tools-release-gate-dist` rather than deleting it.

- [x] **Step 5: Commit Task 3**

```bash
git add docs/developer/GOVERNANCE_AND_RELEASE_GATES.md docs/index.md \
  docs/developer/HANDOVER.md docs/developer/PYPI_RELEASE_AUTOMATION.md \
  docs/reports/DOCUMENTATION_STATUS_REPORT.md \
  docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html \
  docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md \
  tests/unit/test_docs_governance.py
git commit -m "docs: govern GitHub release gates"
```

## Task 4: Immutable release-tag binding after final-review finding

**Decision source:** The whole-branch final review on 2026-09-05 found that `v2.2.3` already resolves to the pre-change baseline while `pyproject.toml` still declares `2.2.3`; it also found that a manual ref could reach the OIDC publisher. The user authorized continued implementation, but did not authorize a version bump, tag, push, or publication.

**Files:**
- Modify: `scripts/check_release_readiness.py`, `tests/unit/test_release_readiness.py`
- Modify: `.github/workflows/publish-pypi.yml`, `tests/unit/test_ci_workflows.py`
- Modify: `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md`, `docs/developer/PYPI_RELEASE_AUTOMATION.md`
- Modify: this plan and its linked design SPEC/status ledger as needed

**Ruling:** Keep `2.2.3` as the published stable version and treat the current main range as unreleased work. Do not invent `2.2.4` release notes or retag an immutable published release. The release path must require a future maintainer-created exact `v<pyproject version>` tag that resolves to the checked-out commit. Cost if wrong: a later maintenance release needs a separate deliberate patch-version/release-note task, but no published artifact is misrepresented today.

**Test strategy:** Fixture repositories create an annotated or lightweight tag and prove readiness accepts only a tag resolving to the checked-out commit; missing, malformed, or mismatched tags fail. Workflow contract tests prove the manual input is a tag (not arbitrary ref), is passed through `env`, is validated before `GITHUB_OUTPUT`, resolves `refs/tags/<tag>`, and checks the tag target after checkout before preflight can publish.

**Interfaces:** `check_release_readiness.py --tag v<version>` validates the exact repository tag and current `HEAD` in addition to metadata/release-note facts. The workflow dispatch input is named `tag`; the resolver emits one validated tag/ref for checkout.

- [x] **Step 1: Add focused failing tag-binding and workflow-contract tests**

Extend readiness fixtures with a minimal Git repository whose `HEAD` and `refs/tags/v9.8.7` initially match. Cover an absent tag and a tag pointing at another commit. Extend CI workflow tests for the tag-only dispatch input, env-mediated input handling, `refs/tags/` resolution, and post-checkout tag-to-`HEAD` verification.

- [x] **Step 2: Run RED**

```bash
conda run -n atst-dev python -m pytest tests/unit/test_release_readiness.py tests/unit/test_ci_workflows.py -q
```

Expected: failures show the checker does not inspect Git tags and the workflow still accepts arbitrary refs/direct expression interpolation.

- [x] **Step 3: Bind checker and publisher to an exact tag**

Use Git plumbing without network access to resolve only `refs/tags/<tag>` and its peeled commit; reject missing/non-commit tags and a target that differs from `HEAD`. In the workflow, accept only a `tag` input, place it in an env variable, validate the exact `v<version>` form before output, resolve the tag namespace, and run the same checker after checkout. Preserve preflight order, artifact handoff, least-privilege publish, and no-Gitee/no-secrets boundaries. Update developer instructions to say a main commit is not a release until a new exact tag is deliberately created; do not state a new version exists.

- [x] **Step 4: Verify GREEN**

Run focused tests, YAML parse, docs governance, and fixture readiness. The repository-root check for `v2.2.3` must now fail because the existing tag targets the old release; this is expected evidence, not a bypass. Then run the full suite and clean-wheel preflight; move generated `dist/` to `$HOME/scratch/atst-tools-release-gate-dist` rather than deleting it.

- [x] **Step 5: Commit Task 4**

```bash
git add scripts/check_release_readiness.py tests/unit/test_release_readiness.py .github/workflows/publish-pypi.yml tests/unit/test_ci_workflows.py docs/developer/GOVERNANCE_AND_RELEASE_GATES.md docs/developer/PYPI_RELEASE_AUTOMATION.md docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md
git commit -m "ci: bind releases to immutable tags"
```

### Task 5: Align project guidance with advisory governance policy

**Decision source:** On 2026-09-05 the maintainer updated the global governance contract: cross-family review is optional advisory evidence, not a hard merge/push/release gate. The maintainer instructed this project to continue; global contracts are owned elsewhere and are out of scope here.

**Files:**
- Modify: `tests/unit/test_docs_governance.py`
- Modify: `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md`, `docs/developer/PYPI_RELEASE_AUTOMATION.md`, `docs/developer/HANDOVER.md`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`
- Modify: `docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html`
- Modify: this plan

**Test strategy:** The existing documentation-governance suite becomes the contract owner. Its new behavior test must require that the project guide describes independent review as owner-judged advisory evidence, retains the honest CI boundary, accepts an owner-confirmed frozen-diff review as evidence, and does not make launcher use or a missing cross-family result a release gate. The test must still require explicit authorization/external administrator ownership for push, tag, publish, credentials, and GitHub/PyPI configuration.

**Interfaces:** Consumes the existing `GOVERNANCE_AND_RELEASE_GATES.md` entrypoint and `GOVERNANCE_REVIEW.md` reference. Produces consistent developer/release guidance only; no workflow, credential, tag, push, external setting, or global-contract change.

- [x] **Step 1: Write the failing documentation-policy test**

Extend `test_governance_release_gate_guide_is_linked_and_names_boundaries` (or add one focused sibling) to assert that the guide contains an advisory/owner-judged independent-review statement, says CI cannot manufacture model-family evidence, and identifies an owner-confirmed frozen-diff review as acceptable evidence. Assert it does not say a missing or same-family review closes a governance gate, and that the release guidance still names `pypi` Environment plus authorized maintainer/external administrator boundaries.

- [x] **Step 2: Run the focused test to verify RED**

Run:

```bash
conda run -n atst-dev python -m pytest tests/unit/test_docs_governance.py::test_governance_release_guidance_is_advisory_and_preserves_external_boundaries -q
```

Expected: FAIL because the current guide still says a failed, missing, same-family, or stale review closes the governance gate.

- [x] **Step 3: Replace stale hard-gate prose with the project boundary**

In the developer guide, describe a current-family independent review as the normal final check; permit an independent cross-family review when the maintainer judges it useful, and describe the launcher only as an optional convenience. State that an owner-confirmed, frozen-diff independent review supplied through another channel is valid advisory evidence. Keep CI mechanical-only and say it cannot prove reviewer independence. Update the PyPI guide, handover, report ledger, SPEC, and plan status/architecture/errors/rollout language so none calls cross-family review a mandatory release gate. Retain all exact-tag, preflight, OIDC, authorization, administrator-setting, and manual Gitee responsibilities.

- [x] **Step 4: Verify GREEN and documentation checks**

Run:

```bash
conda run -n atst-dev python -m pytest tests/unit/test_docs_governance.py -q
conda run -n atst-dev python scripts/check_docs_governance.py
git diff --check -- docs tests
rg -n "^<<<<<<<|^=======|^>>>>>>>" docs tests
```

Expected: all tests/checks pass; no conflict markers or whitespace errors. Do not run a release command for `v2.2.3`, because its intentional old-tag failure is unrelated to this documentation-only task.

- [x] **Step 5: Commit Task 5**

```bash
git add tests/unit/test_docs_governance.py \
  docs/developer/GOVERNANCE_AND_RELEASE_GATES.md \
  docs/developer/PYPI_RELEASE_AUTOMATION.md docs/developer/HANDOVER.md \
  docs/reports/DOCUMENTATION_STATUS_REPORT.md \
  docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html \
  docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md
git commit -m "docs: make governance review advisory"
```

## Plan Self-Review

- R1 is Task 1; R2/R4/R5 are Tasks 2 and 4; R3 spans Tasks 1–2 and 4; R6/R7 are Task 3.
- No task creates credentials, Gitee automation, tags, releases, or external administrator settings.
- Task 1 creates the exact script consumed by Task 2; Task 3 only documents established interfaces.
- The plan contains exact paths, tests, commands, and commit scopes; no placeholder, temporary production API, or unassigned requirement remains.

## Execution Handoff

User approved the design and requested continued implementation on 2026-09-04. Execute serially with fresh task review between tasks; governance-path edits receive the normal current-family final review, while any cross-family review is owner-judged advisory evidence. Push, tag, publish, credentials, and external settings remain separately authorized maintainer actions.
