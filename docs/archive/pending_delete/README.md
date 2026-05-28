# Pending Delete Documentation

**Version**: 2026-05-28
**Date**: 2026-05-28
**Status**: Pending deletion review
**Owner**: ATST-Tools maintainers

This folder holds plans and reports that have been moved out of the active
documentation set because their conclusions are superseded by current
implementation, newer validation reports, or maintained reference documents.

Files here are not active project guidance. Keep them only while maintainers
decide whether they are still needed for historical auditability. If their
useful conclusions have already been absorbed into maintained docs, they can be
deleted in a later cleanup pass.

## Current Criteria

- The document describes a previous branch or stage as the current baseline.
- The document records an early failed validation that was superseded by a later
  successful validation or fix report.
- The document is an implementation plan whose tasks have landed and are now
  covered by maintained user/developer docs and tests.
- Keeping the document under active `docs/reports` or `docs/developer/plans`
  would mislead readers about the current project state.
- No active README, `docs/index.md`, user guide, developer guide, release note,
  or active report depends on it as current guidance.

## Final Deletion Checklist

Before deleting any file from this directory:

- Confirm no active Markdown link points to it.
- Confirm it contains no unique validation, environment, scientific, or testing
  evidence that still needs to be preserved.
- Confirm useful conclusions were absorbed into maintained docs, release notes,
  tests, or final reports.
- Record the decision in
  `docs/reports/DOCUMENTATION_STATUS_REPORT.md`.

## Current Contents

- `plans/native-ase-backend.md`: implementation plan now covered by the native
  ASE backend selector, schema/docs/tests, and maintained backend review.
- `reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md`: old refactor-stage baseline
  superseded by current feature reports, release notes, and status docs.
- `reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md`: stage report whose
  completed UX work is now covered by user docs and CLI references.
- `reports/CY_PT_AUTONEB_MAIN_REPRODUCTION_REVIEW_2026-05-18.md`: negative
  main-like reproduction report superseded by later Issue #25 fix validation.
- `reports/CY_PT_AUTONEB_MAIN_ALIGNED_LTS3101_VALIDATION_2026-05-19.md`: early
  main-aligned validation that did not meet target, superseded by later strict
  validation in the Issue #25 fix report.
- `reports/CY_PT_AUTONEB_FAILURE_ROOT_CAUSE_REVIEW_2026-05-18.html`: root-cause
  review superseded by the final fix report and current example references.
- `reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md`: pre-fix assessment
  superseded by the final Issue #25 fix report.
- `reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md`: early SAI
  validation superseded by the final Issue #25 fix report.
