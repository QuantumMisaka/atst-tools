# Zn NEB Pending-Delete Notes

**Status**: Superseded planning archive
**Active evidence**: `../../../../reports/ZN_SEGMENTED_NEB_RUNTIME_STATUS_2026-05-30.md`

This directory keeps the initial `.trae` planning materials for the Zn
migration NEB calculation in one reviewable location. These files are not the
current execution source of truth.

## Completion Status

- The initial single-path plan in `Zn-NEB.md` was partially completed: input
  feasibility, ABACUS/ATST configuration planning, and smoke/production
  workflow design were documented.
- The original goal of completing CI-NEB, AutoNEB, and D2S production runs as
  three independent routes was not completed as written.
- The task was superseded by the segmented nspin=2 route recorded in the active
  runtime report. That report preserves the current evidence: a complete mixed
  main path from Segment A AutoNEB final plus Segment B/C climbing NEB, with
  D2S/CCQN retained only as auxiliary evidence.

## Files

- `Zn-NEB.md`: initial single-path validation plan.
- `spec.md`: initial Zn migration calculation spec.
- `tasks.md`: initial task breakdown and completion state.
- `checklist.md`: initial checklist. The unchecked production items are
  superseded by the segmented runtime report rather than still-active tasks.

## Review Rule

Before deleting this directory, confirm that
`docs/reports/ZN_SEGMENTED_NEB_RUNTIME_STATUS_2026-05-30.md` remains the active
evidence entry and that no maintained document links to these superseded notes
as current guidance.
