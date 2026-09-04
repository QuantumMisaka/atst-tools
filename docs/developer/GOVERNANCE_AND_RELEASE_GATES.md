# Governance and Release Gates

This guide defines the boundary between checks that repository files can
prove, the existing independent governance review, and administrator actions
outside the repository. A green local or CI check is evidence for its own
mechanical contract; it is not evidence that an external setting or release
operation has happened.

## Phase 1: local and CI mechanical gates

Run these checks from the repository root before asking for a release review:

```bash
conda run -n atst-dev python scripts/check_docs_governance.py
conda run -n atst-dev python scripts/check_release_readiness.py --tag v2.2.3
conda run -n atst-dev python -m pytest tests -q
conda run -n atst-dev python -m build
conda run -n atst-dev python -m twine check --strict dist/*
conda run -n atst-dev python scripts/verify_wheel_api.py
```

For another version, replace `v2.2.3` with the matching `v<version>` tag. The
readiness checker is offline: it compares the tag with the version in
`pyproject.toml` and the corresponding release note. It does not create a tag,
push a commit, publish an artifact, or contact GitHub, Gitee, or PyPI.

The same mechanical contracts run in CI. The general workflow runs the full
pytest suite and `documentation-governance` runs
`python scripts/check_docs_governance.py`. The PyPI workflow resolves one ref,
then `release-preflight` checks that exact ref in this order: release
readiness, pytest, documentation governance, build, strict Twine, and the
clean-wheel API gate. Only a successful preflight hands an artifact to the
`publish` job. The `publish` job is the only job that requests the `pypi`
Environment and `id-token: write`.

## Phase 2: cross-family governance review

Changes to `AGENTS.md`, a `SKILL.md`, a role contract, governance triggers,
reviewer routing, or another declared governance effect require the existing
cross-family review process. This Task3 documentation itself describes that
boundary; it does not replace the process.

After local checks pass, freeze the exact commit range and use the existing
`GOVERNANCE_REVIEW.md` launcher and its `governance-review prepare`, `run`,
`record-decision`, and `check` interfaces. The parent maintainer must inspect
the reviewer result against the frozen diff and evidence before accepting the
decision. The reviewer must be independent of every substantive author family.

CI cannot establish model-family independence or manufacture a reviewer
result. A failed, missing, same-family, stale, or otherwise invalid review
keeps the governance gate closed. If an external family backend is unavailable
and the existing process falls back to a same-family review, record explicitly
that cross-family review is incomplete and requires follow-up; do not call the
cross-family gate passed.

## Phase 3: GitHub, PyPI, and Gitee administrator/post-push checklist

The following are administrator or post-push responsibilities, not effects of
editing repository files:

1. On GitHub, configure `main` branch protection and required checks. Configure
   the `pypi` Environment with reviewers and tag restrictions, according to the
   repository's administrator policy.
2. In PyPI Trusted Publishing, verify the Trusted Publisher identity for
   `QuantumMisaka/atst-tools`, workflow filename, and `pypi` Environment match
   the workflow. Keep credentials out of repository files.
3. After the governance gate is accepted, the authorized maintainer may push
   the intended commit/tag or create the intended release. The local Task3
   implementation does not push, create a tag, or create a release.
4. After publishing, the maintainer checks GitHub Actions and PyPI artifact
   metadata/rendering from the published ref, then performs the manual Gitee
   mirror pull and checks the Gitee rendering. This repository adds no Gitee
   synchronization automation.

At Task3 completion, branch protection, `pypi` Environment reviewers/tag
restrictions, Trusted Publisher identity, push/tag/release, Gitee mirror pull,
and GitHub/Gitee/PyPI rendering verification remain pending external work.
