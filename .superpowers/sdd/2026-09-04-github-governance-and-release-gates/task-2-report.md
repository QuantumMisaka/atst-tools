# Task 2 Report: GitHub CI and PyPI preflight separation

## Result

Task 2 is complete. The release workflow now resolves the release ref,
performs all local gates against that exact ref, hands the resulting
distributions to a separate publisher, and grants the PyPI OIDC token only to
that publisher job.

## Changes

- `.github/workflows/tests.yml`
  - Retained pull-request and manual triggers and read-only contents access.
  - Added `push` for `main`.
  - Renamed the test job to `test` and added a separate
    `documentation-governance` job using Python 3.10, `.[test]`, and
    `python scripts/check_docs_governance.py`.
- `.github/workflows/publish-pypi.yml`
  - Split `resolve-release`, `release-preflight`, and `publish` jobs.
  - The preflight checks out `${{ needs.resolve-release.outputs.ref }}` and
    runs `check_release_readiness.py --tag "$RELEASE_TAG"`, full pytest,
    documentation governance, build, strict Twine checks, and
    `scripts/verify_wheel_api.py` in that order.
  - The preflight uploads `dist/*`; `publish` downloads that artifact and
    depends only on `release-preflight`.
  - `id-token: write` exists only on `publish`; no secrets, Gitee integration,
    tag/release/push operations, or external GitHub settings were added.
- `tests/unit/test_ci_workflows.py`
  - Added static contracts for triggers, job names/dependencies, exact ref
    handoff, gate order, artifact handoff, and OIDC least privilege.

## TDD evidence

### RED

After adding the workflow contracts, the required focused command failed as
expected because the existing workflows lacked the `main` push/docs job and
release job separation:

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
.FFF                                                                     [100%]
```

The original full-pytest contract passed during this RED run.

### GREEN and verification

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
....                                                                     [100%]
```

Ruby/Psych was unavailable (`ruby: command not found`), so the permitted
fallback parser was used without adding a dependency:

```text
conda run -n atst-dev python -c 'import yaml, pathlib; paths = sorted(pathlib.Path(".github/workflows").glob("*.yml")); [yaml.safe_load(p.read_text()) for p in paths]; print("YAML OK:", ", ".join(map(str, paths)))'
YAML OK: .github/workflows/abacuslite-ase-interface.yml, .github/workflows/publish-pypi.yml, .github/workflows/tests.yml
```

Additional checks passed:

```text
conda run -n atst-dev python -m pytest tests -q
... [all tests passed; MPI and toolbox-dependent tests skipped by their existing guards]

git diff --check -- .github/workflows/tests.yml .github/workflows/publish-pypi.yml tests/unit/test_ci_workflows.py
```

The workflow-only forbidden-token scan found no added secrets, Gitee,
`git tag`/`git push`, release creation, or external GitHub settings.

## Remaining uncertainty

Local checks do not execute GitHub Actions or establish repository branch
protection and PyPI Trusted Publisher configuration. Those remain external
deployment gates by design.
