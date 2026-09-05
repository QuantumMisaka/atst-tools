# Release CI repair report

Date: 2026-09-06

## Scope and source verification

- Changed only `scripts/check_abacuslite_snapshot.py`,
  `tests/unit/test_abacuslite_snapshot_ci.py`, and
  `src/atst_tools/external/ASE_interface/PATCHES.md` for the repair.
- The vendored runtime parser was not changed.
- `temp_repos/abacus-develop` was not changed; its HEAD is
  `27b2775e79ab7691539480068ee6e3a47e20bb5a`, not the pinned baseline.
- The pinned upstream tree was obtained in an isolated temporary archive from
  `https://github.com/deepmodeling/abacus-develop/archive/70f7ed69b5677c447afdc78e05240e93da660e66.tar.gz`.

## TDD evidence

### RED

Command:

```text
env PYTHONPATH=src pytest tests/unit/test_abacuslite_snapshot_ci.py::test_snapshot_checker_accepts_documented_point_kpoint_parser_patch -q
```

Exit code: `1`.

Observed failure: the checker reported drift in
`abacuslite/io/generalio.py`, showing the expected upstream capturing-group
regex and weight group 6 against the vendored non-capturing-group regex and
weight group 3.

### GREEN

Command:

```text
conda run -n atst-dev env PYTHONPATH=src python -m pytest tests/unit/test_abacuslite_snapshot_ci.py -vv --tb=short
```

Exit code: `0`.

```text
collected 10 items
============================== 10 passed in 0.08s ==============================
```

The same suite covers the exact documented patch acceptance plus altered
coordinate regex, wrong weight index, and unrelated-function drift rejection.

## Pinned snapshot check

Command:

```text
python scripts/check_abacuslite_snapshot.py \
  --upstream /tmp/abacuslite-pinned-tree.rIxDd9/abacus-develop-70f7ed69b5677c447afdc78e05240e93da660e66/interfaces/ASE_interface \
  --vendored src/atst_tools/external/ASE_interface
```

Exit code: `0`; output was empty.

## Focused KPT parser check

Command:

```text
conda run -n atst-dev env PYTHONPATH=src python -m pytest \
  tests/unit/test_reverse_config.py::test_build_config_point_kpt_passthrough \
  -vv --tb=short
```

Exit code: `0`.

```text
collected 1 item
============================== 1 passed in 0.39s ===============================
```

## Workflow-listed regression checks

Command:

```text
conda run -n atst-dev env PYTHONPATH=src python -m pytest \
  tests/unit/test_abacuslite_profile.py \
  tests/unit/test_abacus_io.py \
  tests/unit/test_abacuslite_io_reorder.py \
  tests/unit/test_abacuslite_snapshot_ci.py \
  tests/unit/test_abacuslite_ci.py \
  tests/unit/test_abacuslite_frame_selection.py \
  tests/unit/test_checker_efermi_whitelist.py -vv --tb=short
```

Exit code: `0`.

```text
collected 67 items
============================== 67 passed in 1.12s ==============================
```

Command:

```text
conda run -n atst-dev env PYTHONPATH=src python -m unittest \
  atst_tools.external.ASE_interface.abacuslite.io.generalio \
  atst_tools.external.ASE_interface.abacuslite.io.legacyio \
  atst_tools.external.ASE_interface.abacuslite.io.latestio \
  atst_tools.external.ASE_interface.abacuslite.utils.ksampling -v
```

Exit code: `0`.

```text
Ran 28 tests in 0.032s

OK (skipped=2)
```

The two skips are the existing pseudo/orbital tests in `generalio`; the KPT
round-trip test itself passed.
