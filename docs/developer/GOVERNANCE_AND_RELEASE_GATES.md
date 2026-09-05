# Governance and Release Gates

This guide defines the boundary between checks that repository files can
prove, the existing independent governance review, and administrator actions
outside the repository. A green local or CI check is evidence for its own
mechanical contract; it is not evidence that an external setting or release
operation has happened. A current-family independent review is the normal
final check. An independent cross-family review is owner-judged advisory
evidence when the maintainer considers it useful, not a merge, push, or release
gate.

## Phase 1: local and CI mechanical gates

Run these checks from the repository root before asking for a release review:

```bash
conda run -n atst-dev python scripts/check_docs_governance.py
conda run -n atst-dev python scripts/check_release_readiness.py --tag v2.2.4
conda run -n atst-dev python -m pytest tests -q
conda run -n atst-dev python -m build
conda run -n atst-dev python -m twine check --strict dist/*
conda run -n atst-dev python scripts/verify_wheel_api.py
```

Run the readiness command from a checkout whose `HEAD` is the exact commit
targeted by the existing `v<version>` tag; the checker compares that peeled tag
commit with `HEAD` as well as checking the version and release note. The
published `v2.2.4` tag points to `eaac64a76215e33588d362a788c138464519a7ba`.
The 2026-09-05 record that `v2.2.3` pointed to the earlier published release
remains historical evidence. The checker is offline and does not create a tag,
push a commit, publish an artifact, or contact GitHub, Gitee, or PyPI.

The same mechanical contracts run in CI. The general workflow runs the full
pytest suite and `documentation-governance` runs
`python scripts/check_docs_governance.py`. The PyPI workflow accepts a pushed
tag or a manual `tag` input only, validates its exact `v<version>` form, and
resolves `refs/tags/<tag>`. After checkout, `release-preflight` runs the same
readiness checker (including tag-to-`HEAD` binding) in this order: release
readiness, pytest, documentation governance, build, strict Twine, and the
clean-wheel API gate. Only a successful preflight hands an artifact to the
`publish` job. The `publish` job is the only job that requests the `pypi`
Environment and `id-token: write`.

## Phase 2: cross-family governance review

Changes to `AGENTS.md`, a `SKILL.md`, a role contract, governance triggers,
reviewer routing, or another declared governance effect should receive the
existing governance review process when the maintainer judges that useful.
This guide describes that boundary; it does not replace the process.

After local checks pass, the maintainer may freeze the exact commit range and
use the existing `GOVERNANCE_REVIEW.md` launcher and its
`governance-review prepare`, `run`, `record-decision`, and `check` interfaces
as an optional convenience. The parent maintainer must inspect any reviewer
result against the frozen diff and evidence before accepting it. An
owner-confirmed frozen-diff review supplied through another channel is equally
valid advisory evidence when its reviewer is independent of every substantive
author family. A review is described as cross-family only when that independence
is established.
The launcher is an optional convenience, not a required step.

CI cannot establish model-family independence. CI cannot manufacture
model-family evidence. A missing, same-family, stale, or otherwise unavailable cross-family
review is recorded honestly as not performed or incomplete; it does not by
itself close a governance gate. A same-family review remains acceptable as the
normal current-family final check, but it must not be represented as
cross-family evidence. None of these cross-family review states blocks delivery
or release by itself; any actual findings still require maintainer review and
appropriate correction.

## Phase 3: GitHub, PyPI, and Gitee administrator/post-push checklist

The following are administrator or post-push responsibilities, not effects of
editing repository files:

1. On GitHub, configure `main` branch protection and required checks. Configure
   the `pypi` Environment with reviewers and tag restrictions, according to the
   repository's administrator policy.
2. In PyPI Trusted Publishing, verify the Trusted Publisher identity for
   `QuantumMisaka/atst-tools`, workflow filename, and `pypi` Environment match
   the workflow. Keep credentials out of repository files.
3. After the local mechanical checks pass and the maintainer has considered
   any owner-judged advisory evidence, the authorized maintainer may push the
   intended commit/tag or create the intended release. A main commit is not a
   release until a maintainer deliberately creates the exact
   `v<pyproject version>` tag; the local implementation does not push, create
   a tag, or create a release.
4. After publishing, the maintainer checks GitHub Actions and PyPI artifact
   metadata/rendering from the published ref. Gitee mirror synchronization and
   rendering are separate manual operations; they were explicitly excluded
   from the 2.2.4 release acceptance. This repository adds no Gitee
   synchronization automation.

At the 2026-09-06 release closure, `2.2.4` is published from the exact tag
above, with successful GitHub Tests run `33980730827`, abacuslite run
`33980730831`, and PyPI publication run `33980788260`. PyPI metadata and
rendering were verified; clean-environment installation and CLI/API checks are
recorded in the release notes. Gitee mirror/rendering verification was
explicitly excluded and is not represented as verified here.
