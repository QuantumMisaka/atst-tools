# PyPI Release Automation

ATST-Tools publishes release artifacts to PyPI through GitHub Actions and PyPI
Trusted Publishing. The workflow builds the source distribution and wheel from a
GitHub release tag, checks the artifacts with Twine, and uploads them without a
stored PyPI token.

## Repository Workflow

The release workflow lives at `.github/workflows/publish-pypi.yml`.

- Primary trigger: publishing a GitHub Release.
- Manual trigger: `workflow_dispatch` with a `v`-prefixed tag or ref, used for
  already-created tags such as `v2.0.0`.
- Release guard: the workflow requires the release tag to match
  `pyproject.toml` `[project].version`. For example, `v2.0.0` must match
  `2.0.0`.
- Publishing job: uses the GitHub environment named `pypi` and requests
  `id-token: write` only for the PyPI upload job.

## PyPI Setup

For a first upload, create a pending publisher at:

```text
https://pypi.org/manage/account/publishing/
```

Use these exact values:

```text
PyPI project name: atst-tools
Owner: deepmodeling
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

## Publishing 2.0.0

The `v2.0.0` tag already exists. After the workflow is merged into the default
branch and the PyPI/GitHub setup above is complete, publish with one of these
paths:

1. Create and publish a GitHub Release from tag `v2.0.0`.
2. Or run `Publish Python package to PyPI` manually from the Actions tab with
   input `v2.0.0`.

Verify the published package from a clean environment:

```bash
python -m pip install --no-cache-dir atst-tools==2.0.0
python -c "import atst_tools; print(atst_tools.package_version())"
atst --version
```

Both version commands should report `2.0.0`.
