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

## Narrow final-review follow-up

The artifact-name helper was tightened to bound extraction to the selected
`      - ` step, from its `uses: actions/{upload,download}-artifact@v4` line
through the next step. A regression test supplies a step with no `with.name`
followed by a later step containing `name: python-distributions`; the helper
must reject that fixture instead of leaking across the step boundary.

Final verification:

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
.....                                                                    [100%]

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

## Review follow-up

Review requested that the publisher's job-local permissions contain only the
OIDC grant, and that the static contracts scope assertions to individual job
blocks. The prior publisher incorrectly repeated `contents: read` alongside
`id-token: write`; this was removed while retaining the global read permission
and the read-only documentation job permission needed by checkout jobs.

The tests now extract top-level job blocks and assert that preflight owns all
release checks and artifact upload, while publish owns artifact download and
contains no checkout/build step. The permissions assertion requires exactly
`id-token: write`.

Review TDD evidence:

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
...F                                                                     [100%]
```

The RED failure showed the existing job permissions as
`contents: read` plus `id-token: write`. After the workflow fix:

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
....                                                                     [100%]

conda run -n atst-dev python -c 'import yaml, pathlib; paths = sorted(pathlib.Path(".github/workflows").glob("*.yml")); [yaml.safe_load(p.read_text()) for p in paths]; print("YAML OK:", ", ".join(map(str, paths)))'
YAML OK: .github/workflows/abacuslite-ase-interface.yml, .github/workflows/publish-pypi.yml, .github/workflows/tests.yml

conda run -n atst-dev python -m pytest tests -q
... [all tests passed; existing MPI and toolbox-dependent tests skipped by guards]
```

## Final review test hardening

The final review requested stronger ownership assertions without changing the
workflows. The existing job-block helper now scopes the general CI assertions
so `test` must own full pytest and `documentation-governance` must own the docs
checker. It also scopes the release artifact checks and compares the explicit
upload/download names, requiring both jobs to use `python-distributions`.

Post-hardening verification:

```text
conda run -n atst-dev python -m pytest tests/unit/test_ci_workflows.py -q
....                                                                     [100%]

conda run -n atst-dev python -c 'import yaml, pathlib; paths = sorted(pathlib.Path(".github/workflows").glob("*.yml")); [yaml.safe_load(p.read_text()) for p in paths]; print("YAML OK:", ", ".join(map(str, paths)))'
YAML OK: .github/workflows/abacuslite-ase-interface.yml, .github/workflows/publish-pypi.yml, .github/workflows/tests.yml
```
