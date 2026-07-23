# User and Developer Documentation Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate active user documentation from maintainer testing and SAI validation material while keeping the project state and navigation accurate and readable.

**Spec:** none — requirements supplied directly by the user on 2026-07-23.

**Architecture:** User entry points describe installation, configuration, execution, results, capability boundaries, and generic scheduler ownership. Developer documentation owns test commands, CI, coverage, SAI-specific environment/module/partition/job evidence, and release-maintenance instructions. Existing `docs/reports/` remains the durable location for historical validation evidence; a concise developer operations guide links to it rather than duplicating it.

**Tech Stack:** Markdown, pytest documentation-governance tests, repository documentation checker.

## Global Constraints

- Active user entry points are `README.md`, `docs/index.md` user path, `docs/user/`, and `examples/README.md`.
- User-facing text must not directly contain test-suite/CI/coverage commands or SAI-specific modules, partitions, QOS, server/job identifiers, or validation-run instructions.
- User-facing text may retain generic operational boundaries such as caller-owned Slurm/MPI scheduling when necessary to explain product behavior.
- Developer documents may contain test and SAI operational material and must link to the user guides and active validation reports instead of duplicating user workflows.
- Release state must be internally consistent: the unmerged 2.2.0 branch is a release candidate, not a published PyPI release.
- Keep scientific capability limitations (for example experimental DMF and transition-state validation semantics) readable to users; do not misclassify those as software-test content.
- Preserve existing public commands, YAML contracts, APIs, and examples; this task changes documentation and documentation tests only.

---

### Task 1: Normalize top-level and user-guide boundaries

**Files:**
- Modify: `README.md`
- Modify: `docs/index.md`
- Modify: `docs/user/USER_GUIDE_CN.md`
- Modify: `docs/user/CONFIG_REFERENCE.md`
- Modify: `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`

**Test strategy:**
- Behavior boundary: users can find installation, CLI/API, configuration, examples, and product limitations without seeing test commands, CI/coverage prose, SAI runtime instructions, or SAI-specific ABACUS settings.
- Existing suite to extend: `tests/unit/test_docs_governance.py` in Task 3; no test change belongs to this task because the acceptance rule spans Task 2's examples entry point as well.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: active user navigation and current release notes.
- Produces: user-facing paths that link generic operational boundaries to a future developer operations guide rather than embedding maintainer evidence.

- [ ] **Step 1: Record the user-facing removals in the task report before editing**

Identify and record these existing locations: README `Validation` section and release/installable wording; `docs/index.md` user-path SAI wording; `USER_GUIDE_CN.md` development environment, SAI GPU, and `pytest` section; `CONFIG_REFERENCE.md` SAI note and schema-governance section; `ABACUSLITE_WRAPPER_GUIDE.md` CI and SAI module setup. The report must state where each item will be relocated or removed.

- [ ] **Step 2: Rewrite user prose with the required boundaries**

Apply these concrete transformations:

```markdown
| Release candidate | `2.2.0` is pending merge and publication; see [release notes](../../releases/RELEASE_NOTES_2.2.0.md). |
```

Replace user-path `local/SAI` wording with `local and site environments`. Replace SAI-specific ABACUS advice with a generic statement that a site-compatible GPU solver must be chosen according to the installed ABACUS documentation. Replace development/test sections with links to the developer handover and operations guide. Keep `atst config validate`, because it is a user command that validates a YAML input rather than a project test-suite command.

- [ ] **Step 3: Check navigational and factual consistency manually**

Confirm each user entry still links to installation, CLI, API, configuration, examples, and feature status. Confirm every sentence about 2.2.0 agrees with `docs/releases/RELEASE_NOTES_2.2.0.md` being pending merge.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/index.md docs/user/USER_GUIDE_CN.md docs/user/CONFIG_REFERENCE.md docs/user/ABACUSLITE_WRAPPER_GUIDE.md
git commit -m "docs: separate user guidance from maintainer operations"
```

### Task 2: Split example learning from SAI validation operations

**Files:**
- Modify: `examples/README.md`
- Create: `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md`
- Modify: `docs/developer/HANDOVER.md`
- Modify: `docs/reports/DOCUMENTATION_STATUS_REPORT.md`

**Test strategy:**
- Behavior boundary: `examples/README.md` is a concise runnable learning map; detailed SAI, Slurm, partition, QOS, job, smoke and validation operations live only in the developer guide and point at existing reports.
- Existing suite to extend: `tests/unit/test_docs_governance.py` in Task 3.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: Task 1 user/developer boundary and existing `docs/reports/` validation evidence.
- Produces: `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md`, the sole active developer entry for repository example validation operations.

- [ ] **Step 1: Inventory the example-only maintainer material**

Record every block in `examples/README.md` that describes SAI, `sbatch`, modules, partitions/QOS, job IDs, curated validation provenance, or smoke/production-validation staging. Preserve only ordinary prerequisites, configuration validation, basic run commands, learning paths, and scientifically relevant experimental limitations in the examples README.

- [ ] **Step 2: Create the developer operations guide**

Create `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md` with these sections:

```markdown
# Example Validation Operations

## Scope
## Local maintainer checks
## SAI and site-specific execution
## Curated-output provenance
## Evidence reports and lifecycle
```

Move, rather than duplicate, detailed SAI command patterns and state that partitions, QOS, module names, and job IDs are historical/site evidence rather than public user requirements. Link to the relevant active reports. Do not make the guide a second user quick-start.

- [ ] **Step 3: Update developer governance navigation**

Add the operations guide to `Handover`'s example/release checklist and to the active-developer table in `DOCUMENTATION_STATUS_REPORT.md`. Keep `docs/index.md` developer navigation as a concise pointer if Task 1 needs it to reach the new guide.

- [ ] **Step 4: Run a focused readability review**

Read `examples/README.md` from top to bottom. It must contain neither `SAI`, `sbatch`, job IDs, partition/QOS names, nor `pytest`/coverage/CI instructions, and it must retain a first-run configuration-validation plus workflow-run path.

- [ ] **Step 5: Commit**

```bash
git add examples/README.md docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md docs/developer/HANDOVER.md docs/reports/DOCUMENTATION_STATUS_REPORT.md docs/index.md
git commit -m "docs: move example validation operations to developer guide"
```

### Task 3: Automate documentation-layering acceptance and final navigation audit

**Files:**
- Modify: `tests/unit/test_docs_governance.py`
- Modify: `docs/developer/DOCUMENTATION_STANDARDS.md`
- Modify: `docs/index.md` only if the new guide is not yet reachable from the developer path
- Modify: `docs/superpowers/plans/2026-07-23-user-developer-documentation-layering.md`

**Test strategy:**
- Behavior boundary: active user entry points cannot regress by adding maintainer test-suite/CI/coverage instructions or SAI-specific infrastructure content; developer operations content remains discoverable.
- Existing suite to extend: `tests/unit/test_docs_governance.py`.
- New test file justification: none; this suite owns documentation governance.
- Temporary probes: none.

**Interfaces:**
- Consumes: Task 1's user paths and Task 2's developer operations guide.
- Produces: an executable governance rule with an explicit allow-list for generic product terms, plus maintained documentation standards.

- [ ] **Step 1: Write the failing governance test**

Add a test that reads `README.md`, `docs/index.md`, every active Markdown file under `docs/user/`, and `examples/README.md`; it must fail if these paths contain case-insensitive SAI-specific terms or maintainer-only terms such as `pytest`, `coverage`, `.github/workflows`, `sbatch`, `8V100V0`, `rush-gpu`, or `huge-gpu`. It must separately assert that `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md` exists and is linked from the developer handover and documentation status report.

- [ ] **Step 2: Run the governance test and verify RED**

```bash
PYTHONPATH=src conda run --no-capture-output -n atst-dev pytest tests/unit/test_docs_governance.py -q
```

Expected: FAIL because the pre-layering active user documents still contain forbidden maintainer/server terms.

- [ ] **Step 2.1: Repair the plan's repository-relative release-notes link**

The plan is under `docs/superpowers/plans/`; its Task 1 release-notes link must
use `../../releases/RELEASE_NOTES_2.2.0.md`, not a path rooted from the
repository. This repair is required so the repository-wide documentation
governance checker can traverse the plan.

- [ ] **Step 3: Make the test pass with the completed Task 1 and Task 2 document split**

Do not weaken the forbidden-term list to accommodate stale user material. If the test identifies a remaining user-facing leak, move it to the developer guide or an existing report, then keep the user prose product-focused.

- [ ] **Step 4: Run the owning suite and governance checker**

```bash
PYTHONPATH=src conda run --no-capture-output -n atst-dev pytest tests/unit/test_docs_governance.py tests/unit/test_docs_api.py -q
conda run --no-capture-output -n atst-dev python scripts/check_docs_governance.py
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
```

Expected: all tests/checks pass and the conflict search is empty.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_docs_governance.py docs/developer/DOCUMENTATION_STANDARDS.md docs/index.md
git commit -m "test: enforce user documentation boundaries"
```

## Final acceptance

- [ ] Run `PYTHONPATH=src conda run --no-capture-output -n atst-dev pytest tests/unit -q`.
- [ ] Run `PYTHONPATH=src conda run --no-capture-output -n atst-dev pytest tests/integration -q`.
- [ ] Run `conda run --no-capture-output -n atst-dev python scripts/check_docs_governance.py`.
- [ ] Confirm user paths have no direct test-suite/CI/coverage/SAI-server operational content and retain readable install-to-run navigation.
- [ ] Confirm developer paths describe testing, release, example-validation operations, and links to evidence reports.
