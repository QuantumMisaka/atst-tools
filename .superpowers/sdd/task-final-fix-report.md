# Final Documentation Fix Report

## Scope

Addressed the final documentation-review blockers in the user-documentation
boundary test and release-facing documentation. No source code or runtime
behavior changed.

## Root Cause and Resolution

- The user-documentation gate used case-folded substring matching, which missed
  common maintainer and site-operation vocabulary and could not preserve the
  scientific `CI-NEB` term.
- The same gate scanned all of `docs/index.md`, so valid Developer and Project
  Manager navigation could be treated as user-facing content.
- Replaced the string list with case-insensitive, word-boundary regular
  expressions; added explicit `CI-NEB` and `atst config validate` allowances;
  and restrict the index scan to the `User Path` section.
- Added parameterized regressions for `test`, `CI`, `module`, `partition`,
  `QOS`, `server`, `job`, and `validation-run`.
- Removed the now-blocked operations wording from user pages while keeping the
  developer guides as the maintenance entry points.
- Clarified that an unpinned PyPI install obtains the current published
  version, described 2.2.0 as a future release candidate, and linked the
  ABACUSLite wrapper to the existing validation-operations guide.

## Follow-up Regex Coverage

- Expanded `server` to `servers?` and `validation-run` to
  `validation[_ -]?runs?`.
- Added regressions for uppercase `SERVERS`, `validation runs`, and
  `validation_runs`; the existing regressions still prove `CI-NEB` and
  `atst config validate` are allowed.

## Files Changed

- `tests/unit/test_docs_governance.py`
- `README.md`
- `docs/releases/RELEASE_NOTES_2.2.0.md`
- `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`
- `docs/user/CLI_REFERENCE.md`
- `docs/user/CONFIG_REFERENCE.md`
- `docs/user/PYTHON_API_REFERENCE.md`

## Verification

- `pytest tests/unit/test_docs_governance.py -q` — 16 passed.
- `python scripts/check_docs_governance.py --root .` — passed.
- `git diff --check -- README.md docs examples/README.md AGENTS.md tests/unit/test_docs_governance.py` — passed.
- Conflict-marker scan over the affected documentation and test files — zero
  matches.

## Remaining Uncertainty

The term gate deliberately enforces documentation-layer boundaries rather than
semantic intent for every use of the listed words. Future user pages that need
one of these terms will require an explicit boundary decision and a focused
test update.
