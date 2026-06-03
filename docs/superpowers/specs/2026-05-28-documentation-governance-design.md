# ATST-Tools Documentation Governance Design

**Version**: 2026-05-28
**Date**: 2026-05-28
**Status**: Accepted
**Owner**: ATST-Tools maintainers

This accepted design is the source of truth for the 2026-05-28 documentation
governance pass.

## Goal

Define a maintainable documentation management model for ATST-Tools that serves
three audiences:

- **Users**: install ATST-Tools, run workflows, reproduce examples, and
  understand CLI/YAML usage.
- **Developers**: extend workflows, calculator backends, YAML schema, tests,
  examples, and documentation without drifting from project conventions.
- **Project managers**: judge feature status, validation evidence, release
  scope, documentation health, and next priorities.

The model prioritizes fast onboarding while keeping enough governance to prevent
stale reports, outdated plans, and duplicated guidance from becoming active
project documentation.

## 1. Principles

ATST-Tools documentation has two layers:

- **Entry layer**: short, current, stable documents that help users and
  developers start quickly.
- **Evidence layer**: validation reports, reviews, release notes, archive
  material, and pending-delete material used for traceability and project
  decisions.

The entry layer must not require readers to browse historical reports before
they can use or extend the project. Reports can support trust and auditability,
but should not become the primary user path.

The evidence layer can be detailed, but every active report must justify why it
still belongs in the active documentation set. A report stays active only when
it proves current functionality, records a current environment boundary, or
defines an engineering decision that still affects development.

## 2. Directory Responsibilities

| Path | Role | Contains | Does Not Contain |
| :--- | :--- | :--- | :--- |
| `docs/index.md` | Documentation entry point | Active reading paths and key links | Full historical report inventory or temporary plans |
| `docs/user/` | User manuals | CLI, YAML, ABACUS/DP usage, Chinese user guide | Development plans or experiment postmortems |
| `docs/developer/` | Developer manuals | Documentation standards, YAML governance, release automation, handover | Stage validation reports |
| `docs/developer/plans/` | Active plans | Plans that are still intended for implementation | Completed plans or historical ideas |
| `docs/reports/` | Active evidence | Current status reports, validation evidence, active boundary reviews | Superseded plans or old failed-run records |
| `docs/releases/` | Release notes | Version-level change summaries | Daily development reports |
| `docs/skills/` | Operational quick references | Reusable agent/developer workflow guidance | Project status reports |
| `docs/archive/` | Historical archive | Old documents with audit value | Documents linked from active entry points |
| `docs/archive/pending_delete/` | Deletion review area | Stale documents awaiting final deletion review | Documents with unique active evidence value |

New documents must declare a lifecycle type:

- `guide`: long-lived user or developer guidance.
- `reference`: long-lived lookup material, such as CLI or YAML references.
- `status`: current state pages, such as feature or documentation status.
- `validation`: runtime, unit, environment, or scientific validation evidence.
- `review`: boundary analysis, migration assessment, or engineering trade-off
  review.
- `plan`: work that is still intended for implementation.
- `release`: version-scoped release documentation.
- `archive`: historical material outside active guidance.

## 3. Document Lifecycle

When a new document is created, it must define:

- Target audience: user, developer, or project manager.
- Lifecycle type: one of the types listed above.
- Active lifetime: long-term maintained, valid for one version, archived after
  task completion, or retained only for audit.
- Destination for absorbed conclusions: the long-lived document or final report
  that should eventually inherit its conclusions.

### Active Criteria

A document may remain in an active directory if at least one condition applies:

- Users or developers need it to perform current work.
- Project managers need it to judge current feature status, validation status,
  or release boundaries.
- It is the current unique validation evidence for a feature or environment.
- It defines a maintenance rule or interface boundary that is still valid.
- It is an unfinished plan that is still intended for execution.

### Archive Criteria

Move a document to `docs/archive/` when it has historical audit value but should
not guide current work. Typical cases include old branch notes, old architecture
descriptions, previous release review material, or reports whose conclusions
have been absorbed into maintained docs.

### Pending-Delete Criteria

Move a document to `docs/archive/pending_delete/` when all of these are true:

- Its conclusions have been superseded by later implementation, later reports,
  or maintained references.
- Keeping it active would mislead users, developers, or project managers.
- It has no unique validation, environment, scientific, or testing evidence that
  is still needed.
- It is not linked from active entry documents.

Documents in `pending_delete/` are not deleted immediately. Before final
deletion, maintainers must confirm no active links remain, no unique evidence
would be lost, conclusions have been absorbed elsewhere, and
`DOCUMENTATION_STATUS_REPORT.md` records the decision.

## 4. Fast Onboarding Paths

### User Path: Run Something In 10 Minutes

The user reading path is:

1. `README.md`: project positioning, supported workflows, installation, minimal
   YAML, and quick commands.
2. `docs/user/USER_GUIDE_CN.md`: Chinese quick start and SAI/ABACUS/DP notes.
3. `examples/README.md`: learning paths for local CLI, ABACUS workflows, DP
   smoke runs, D2S/CCQN/IRC, and MPI image-level parallel examples.
4. `docs/user/CONFIG_REFERENCE.md`: hand-written YAML semantics.
5. `docs/user/YAML_INPUT_VARIABLES.md`: generated schema field reference.

Users should not need to read `docs/reports/` before running workflows.
Reports may be linked only as validation evidence.

### Developer Path: Modify The Right Place In 30 Minutes

The developer reading path is:

1. `README.md` `For Developers`: extension points for schema, calculators,
   workflows, CLI commands, and examples.
2. `docs/developer/HANDOVER.md`: maintenance checklist and routine commands.
3. `docs/developer/YAML_INPUT_GOVERNANCE.md`: rules for schema and YAML field
   changes.
4. `docs/developer/DOCUMENTATION_STANDARDS.md`: document creation, movement,
   metadata, and verification rules.
5. `docs/skills/atst-cli/SKILL.md`: CLI operation and validation quick
   reference.
6. `tests/` and `examples/`: executable behavior and usage patterns.

Developers may follow active reports for current boundaries, such as native ASE
backend behavior, MPI image-level parallelism, or final Issue #25 validation.
They should not rely on early failed-run reports when a final report exists.

### Project Manager Path: Judge Status And Priority

The project manager reading path is:

1. `docs/reports/FEATURE_STATUS_MATRIX.md`: current feature support range.
2. `docs/reports/DOCUMENTATION_STATUS_REPORT.md`: documentation governance
   state, active reports, archive status, and pending-delete status.
3. `docs/releases/RELEASE_NOTES_2.0.1.md`: current version-level delivery scope.
4. Current validation reports: DP validation, Issue #25 final fix, MPI parallel
   summary, MACE transfer review, and other active evidence reports.
5. `docs/archive/pending_delete/README.md`: release-time deletion review list.

## 5. Update Workflow And Checklist

Documentation updates are tied to code-change categories.

| Change Type | Required Documentation Checks |
| :--- | :--- |
| Add or modify YAML fields | `config_schema.py`, generated `YAML_INPUT_VARIABLES.md`, `CONFIG_REFERENCE.md`, examples, `test_config.py` |
| Add workflow | README support list, `USER_GUIDE_CN.md`, `CLI_REFERENCE.md`, `CONFIG_REFERENCE.md`, examples, feature matrix, tests |
| Add CLI command | `CLI_REFERENCE.md`, `docs/skills/atst-cli/SKILL.md`, README command list, CLI tests |
| Add calculator backend | README backend section, `CONFIG_REFERENCE.md`, user guide, feature/status reports, factory tests |
| Add example | `examples/README.md`, `examples/reference_results.json` or explicit no-reference note, example tests |
| Add validation report | `DOCUMENTATION_STATUS_REPORT.md`, optionally `docs/index.md`, and replacement decision for older reports |
| Fix important bug | Final fix report or update to existing active report, feature/status matrix when relevant, regression test |
| Prepare release | Release notes, feature matrix, documentation status, pending-delete review |

The minimum verification set for documentation-only changes is:

```bash
git diff --check -- README.md docs examples/README.md
python -c "<markdown link checker script>"
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md
```

If an HTML report changes, parse it with Python's standard HTML parser.

If YAML schema changes, regenerate generated YAML docs and run focused config
tests:

```bash
conda run -n atst-dev python -m atst_tools.utils.config_docs --output docs/user/YAML_INPUT_VARIABLES.md
conda run -n atst-dev pytest tests/unit/test_config.py -q
```

## 6. Report Levels And Retention

Active reports are divided into four levels.

### L1: Status Entry

These are the compact state entry points:

- `docs/reports/FEATURE_STATUS_MATRIX.md`
- `docs/reports/DOCUMENTATION_STATUS_REPORT.md`

They are long-lived, linked from `docs/index.md`, and must be considered after
feature or documentation governance changes.

### L2: Current Evidence

These prove current functionality, runtime behavior, or important environment
boundaries. Examples include DP validation, Issue #25 final fix, MPI image-level
parallel summary, CCQN ABACUSLite validation, native ASE backend review, and
examples main/LTS validation.

L2 reports may appear in `docs/index.md`, but the index should list only the
most important evidence. The full active report inventory belongs in
`DOCUMENTATION_STATUS_REPORT.md`.

### L3: Topic Review

These contain deep background, migration analysis, algorithm comparison, or
coverage review. Examples include MACE transfer review, FastIDPP comparison and
fix, unit test coverage review, NEB/ASE comparison review, and initial-guess
audit.

L3 reports remain in `docs/reports/` while their topic is current. They usually
do not belong in README. Whether they appear in `docs/index.md` depends on
whether the topic is actively being developed.

### L4: Historical Or Superseded Material

These are early failures, old plans, old stage reviews, or intermediate reports
covered by final reports.

They must move to `docs/archive/` or `docs/archive/pending_delete/`, must not be
linked from README or `docs/index.md`, and should be referenced only when the
historical context is necessary.

## 7. First Implementation Scope

The first implementation pass should update governance and entry documents only:

- `docs/index.md`: add user, developer, and project manager reading paths.
- `docs/developer/DOCS_ARCHITECTURE.md`: document directory responsibilities,
  lifecycle types, and the three target audiences.
- `docs/developer/DOCUMENTATION_STANDARDS.md`: document metadata, lifecycle,
  update mapping, archive/pending-delete rules, and verification commands.
- `docs/developer/HANDOVER.md`: provide daily maintenance checklists for feature
  changes, YAML changes, examples, reports, and releases.
- `docs/reports/DOCUMENTATION_STATUS_REPORT.md`: act as the governance ledger,
  including L1-L4 report inventory and pending-delete status.
- `docs/archive/pending_delete/README.md`: maintain the deletion review list.
- `README.md`: keep quick-start content light and link to the documentation
  entry and governance report.

The first pass should not rewrite the bodies of `CONFIG_REFERENCE.md`,
`CLI_REFERENCE.md`, or `USER_GUIDE_CN.md` unless a broken link or obvious
current-state error is found. It should not delete pending-delete files. It
should not introduce a documentation build system.

## 8. Acceptance Criteria

The documentation governance implementation is acceptable when:

- `docs/index.md` gives clear reading paths for users, developers, and project
  managers.
- Developers can tell which documents to update for workflow, schema, CLI,
  calculator backend, example, report, bug fix, and release changes.
- Project managers can determine current feature state from
  `FEATURE_STATUS_MATRIX.md` and documentation state from
  `DOCUMENTATION_STATUS_REPORT.md`.
- Active `docs/reports/` no longer contains obviously stale plans or superseded
  reports.
- `docs/archive/` and `docs/archive/pending_delete/` have distinct written
  meanings.
- Active Markdown links resolve.
- `git diff --check -- README.md docs examples/README.md` passes.
- Modified HTML reports parse with Python's standard HTML parser.
