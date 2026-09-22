## Publication Evidence

Pending: this candidate is not published. The maintainer tags `v2.2.8` on the
release commit; the tag push runs `publish-pypi.yml`, whose preflight (release
readiness, unit tests, documentation governance, sdist/wheel build,
distribution checks, wheel public API verification) must pass before the PyPI
publish job runs.

## Validation Matrix

| Gate | Result |
| :--- | :--- |
| `tests/unit` (repository default) | 1195 passed, 3 skipped (opt-in real-backend and root-only cases) |
| `tests/unit` + `tests/integration` with `ATST_RUN_MPI_TESTS=1` | passed on the review branch |
| `scripts/check_docs_governance.py` | passed |
| SAI V100 field evidence | jobs 1444708 (record channels), 1444802 (P2 closeout), 1445744/1445792 (PT thread budget, MPS probe, self-report); see the P2 closeout report and its slices |
| Independent review | full-branch review on `0f5fb51..e0920c2`; required change (evidence slices not tracked) fixed, remaining Minor findings tracked in the ledger |

MPS remains environment-dependent: the site's compute nodes did not expose the
MPS daemons during the afternoon runs, so the probe recorded a completed
negative; the MPS-positive reason path is covered by unit tests.

## Download

Pending publication: `atst_tools-2.2.8-py3-none-any.whl` and
`atst_tools-2.2.8.tar.gz` on PyPI.
