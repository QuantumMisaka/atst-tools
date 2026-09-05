# PyPI Release Automation

ATST-Tools publishes release artifacts to PyPI through the
[QuantumMisaka/atst-tools](https://github.com/QuantumMisaka/atst-tools) GitHub
repository and PyPI Trusted Publishing. The workflow builds the source
distribution and wheel from an exact release tag, checks the artifacts with
Twine, and uploads them without a stored PyPI token.

The complete mechanical and human boundary is maintained in
[Governance and release gates](GOVERNANCE_AND_RELEASE_GATES.md). This page
describes the PyPI-specific part of that contract.

## Repository Workflow

The release workflow lives at `.github/workflows/publish-pypi.yml`.

- Primary trigger: pushing a `v*` tag.
- Manual trigger: `workflow_dispatch` with the `tag` input naming an
  already-created exact tag such as `v2.2.4`; arbitrary branches, commits, and
  refs are not accepted.
- Release guard: the workflow requires the tag to match
  `pyproject.toml` `[project].version`, resolves it under `refs/tags/`, and
  checks after checkout that it points to `HEAD`. The current repository state
  records the published `2.2.4` release; its exact tag and PyPI artifact are
  the publication evidence.
- Publishing job: uses the GitHub environment named `pypi` and requests
  `id-token: write` only for the PyPI upload job.
- Before publishing, `release-preflight` checks out the resolved ref and runs
  readiness, full pytest, documentation governance, build, strict Twine, and
  clean-wheel API checks in that order. The publisher receives only the checked
  distribution artifact.

## Local Readiness Gate

For a candidate commit with its deliberate local `v<version>` tag already
created, run the offline release gate from a checkout of that tagged commit:

```bash
python -m pip install ".[release]"
python scripts/check_release_readiness.py --tag v<version>
```

The `[release]` extra provides the build/release tooling and the Python 3.10
TOML compatibility parser. The checker verifies the exact local tag and its
target against `HEAD`, then checks `pyproject.toml` and requires the exact
package version line in `docs/releases/RELEASE_NOTES_<version>.md`. It reads
local files only and does not create tags, push commits, or contact GitHub or
PyPI.

This repository documentation does not configure the GitHub `pypi`
Environment, its reviewers or tag restrictions, or the PyPI Trusted Publisher
identity. Those settings remain administrator work.

## PyPI Setup

For a first upload, create a pending publisher at:

```text
https://pypi.org/manage/account/publishing/
```

Use these exact values:

```text
PyPI project name: atst-tools
Owner: QuantumMisaka
Repository name: atst-tools
Workflow filename: publish-pypi.yml
Environment name: pypi
```

The pending publisher creates the PyPI project on the first successful upload.
After the project exists, keep the publisher attached to the project and prefer
Trusted Publishing over API tokens.

## GitHub Setup

Create the GitHub environment before the first publish:

```text
Settings -> Environments -> New environment -> pypi
```

Recommended environment protection:

- Require maintainer review before deployment.
- Limit deployment branches/tags to release tags if the repository policy
  supports it.

## Publishing `<version>`

After the release branch is verified and the PyPI/GitHub setup above is
confirmed by an administrator, the authorized maintainer may consider the
normal current-family review and any owner-judged advisory cross-family
evidence before publishing. Cross-family review is not a release gate; an
owner-confirmed frozen-diff review from another channel is valid evidence when
available. Publish with one of these paths:

1. Push the checked exact tag `v<version>` to
   `https://github.com/QuantumMisaka/atst-tools`.
2. Or run `Publish Python package to PyPI` manually from the Actions tab with
   the `tag` input set to `v<version>`.

Neither push/tag/release nor a Gitee mirror pull is performed by this
repository-file workflow. For 2.2.4, GitHub Actions and PyPI artifact
metadata/rendering were checked; Gitee mirror/rendering was explicitly
excluded from release acceptance.

Verify the published package from a clean environment:

```bash
python -m pip install --no-cache-dir atst-tools==<version>
python -c "import atst_tools; print(atst_tools.package_version())"
atst --version
```

Both version commands should report `<version>`.
