# ATST-Tools 2.1.3 Release Notes

**Version**: 2.1.3
**Date**: 2026-06-27
**Branch**: `main`

## Summary

ATST-Tools 2.1.3 aligns the package metadata with the published 2.1.3
release tag and refreshes dependency governance. It raises the supported Python
baseline to 3.10, requires Sella 2.5 or newer for Sella-backed workflows, and
moves heavy feature-specific stacks into optional extras.

## Highlights

- **Dependency policy**:
  - Python support is now `>=3.10`, matching the current ASE, DeePMD-kit, and
    SAI `atst-dev` baseline.
  - Runtime dependencies now use explicit compatibility ranges.
  - `sella>=2.5,<3` is required by default because Sella is a first-class
    saddle-search and IRC backend.

- **Optional feature stacks**:
  - `atst-tools[plot]` installs Matplotlib for plotting helpers.
  - `atst-tools[dp]` installs DeePMD-kit for DP calculator workflows.
  - `atst-tools[parallel]` installs mpi4py for MPI image-level NEB/AutoNEB.
  - `atst-tools[dev]` and `atst-tools[release]` collect local test/build
    tooling.

- **Packaging hygiene**:
  - Package metadata tests now guard the dependency policy.
  - The project license metadata uses the modern SPDX string form.

## Validation

- `pytest tests/unit/test_package_metadata.py -q`
- `pytest tests/unit/test_examples_reference_results.py -q`
- `python -m build --outdir /tmp/atst-tools-deps-build`
- `python -m twine check --strict /tmp/atst-tools-deps-build/*`

## Compatibility

- Package version: `2.1.3`.
- Python 3.9 is no longer part of the supported metadata range.
- YAML schema migration is not required.
- DP, MPI, and plotting users should install the corresponding optional extra
  or provide an equivalent site-managed environment.
