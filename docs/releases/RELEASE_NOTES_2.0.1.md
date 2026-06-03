# ATST-Tools 2.0.1 Release Notes

**Version**: 2.0.1
**Date**: 2026-06-02
**Branch**: `develop`

## Summary

ATST-Tools 2.0.1 is a focused 2.0.x maintenance and feature-completion release.
It updates the package version to reflect the post-2.0.0 workflow, validation,
and documentation-governance additions. The obsolete YAML `config_version`
marker was removed; the active schema is governed by the installed package
version.

## Highlights

- Completed the P0/P1 transition-state workflow iteration: CCQN automatic
  reactive-mode enumeration, product alignment, mode manifests, diagnostics,
  artifact manifests, TS validation, NEB two-stage warm-up, endpoint relaxation,
  and descent IRC examples.
- Added and validated CCQN support as a standalone workflow and D2S refinement
  option, including perturbed H2-Au ABACUS validation against the Sella example.
- Added DPA-3.1 DP example validation evidence and curated DP reference results
  for the supported DP-backed examples.
- Added image-level MPI NEB/AutoNEB support and Cy-Pt SAI E2E validation
  examples with curated outputs.
- Added documentation governance checks, report ledger maintenance, and
  archival cleanup for superseded plans and outdated reports.

## Validation

- Unit tests pass in `atst-dev` with `pytest tests -q`.
- Documentation governance checks pass with
  `python scripts/check_docs_governance.py`.
- Active evidence reports cover DP/DPA3 examples, P0/P1 runtime smoke,
  CCQN ABACUS validation, and image-level MPI NEB/AutoNEB E2E validation.

## Compatibility

- Package version: `2.0.1`.
- YAML `config_version` has been removed. The installed package version defines
  the active YAML schema, and unknown top-level fields are rejected during schema
  validation.
- Existing 2.0.0 YAML inputs remain valid unless they relied on intentionally
  archived temporary plans or outdated validation notes.
