# PyPI Release Automation

ATST-Tools publishes release artifacts to PyPI through the
[QuantumMisaka/atst-tools](https://github.com/QuantumMisaka/atst-tools) GitHub
repository and PyPI Trusted Publishing. The workflow builds the source
distribution and wheel from a pushed release tag, checks the artifacts with
Twine, and uploads them without a stored PyPI token.

## Repository Workflow

The release workflow lives at `.github/workflows/publish-pypi.yml`.

- Primary trigger: pushing a `v*` tag.
- Manual trigger: `workflow_dispatch` with a `v`-prefixed tag or ref, used for
  an already-created tag such as `v2.2.3`.
- Release guard: the workflow requires the release tag to match
  `pyproject.toml` `[project].version`. For example, the current stable tag
  `v2.2.3` must match `2.2.3`.
- Publishing job: uses the GitHub environment named `pypi` and requests
  `id-token: write` only for the PyPI upload job.

## Local Readiness Gate

Before pushing `v<version>`, run the offline release gate from the repository
root:

```bash
python -m pip install ".[release]"
python scripts/check_release_readiness.py --tag v<version>
```

The `[release]` extra provides the build/release tooling and the Python 3.10
TOML compatibility parser. The checker verifies the tag against
`pyproject.toml` and requires the exact package version line in
`docs/releases/RELEASE_NOTES_<version>.md`. It reads local files only and does
not create tags, push commits, or contact GitHub or PyPI.

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
complete, publish with one of these paths:

1. Push the checked tag `v<version>` to
   `https://github.com/QuantumMisaka/atst-tools`.
2. Or run `Publish Python package to PyPI` manually from the Actions tab with
   input `v<version>`.

Verify the published package from a clean environment:

```bash
python -m pip install --no-cache-dir atst-tools==<version>
python -c "import atst_tools; print(atst_tools.package_version())"
atst --version
```

Both version commands should report `<version>`.
