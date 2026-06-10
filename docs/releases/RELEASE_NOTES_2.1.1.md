# ATST-Tools 2.1.1 Release Notes

**Version**: 2.1.1
**Date**: 2026-06-10
**Branch**: `main`

## Summary

ATST-Tools 2.1.1 is a maintenance release focused on unit test improvements,
legacy code cleanup, and small robustness enhancements to the Dimer module.
It keeps full backward compatibility with 2.1.0 inputs.

## Highlights

- **Unit test maintenance**:
  - Added `tests/helpers.py` with shared test fixtures (`DummyCalc`, `FakeWorld`, `FakeReducingWorld`)
  - Added root artifact leak guard in `conftest.py` to prevent `md_final.traj` and `md_post_summary.json` from polluting the repository root
  - Enhanced test coverage for `reactive_modes.py`, `post.py`, `dimer.py`, and `autoneb.py`
  - Added `test_reactive_modes.py` for reactive modes analysis path
  - Added governance tests to verify legacy NEB scripts are not exposed

- **Legacy code cleanup**:
  - Deleted unregistered `neb_make.py` and `neb_post.py` scripts (functionality is available via unified `atst` CLI)

- **Dimer module improvements**:
  - Stricter validation for displacement vectors (requires one vector per atom)
  - Better calculator directory precedence (calc_config directory overrides backend_config directory)
  - Explicit error for unsupported `init_eigenmode_method` values

- **Documentation**:
  - Added `UNIT_TEST_MAINTENANCE_2026-06-10.md` report
  - Updated `DOCUMENTATION_STATUS_REPORT.md`

## Validation

- All unit tests pass in the `atst-dev` environment
- Documentation governance checks pass
- No root artifacts left by test runs
- Version commands report `2.1.1` from the source tree

## Compatibility

- Package version: `2.1.1`.
- Fully backward compatible with 2.0.x and 2.1.0 inputs. No YAML semantics changed.
- All existing workflows (NEB, AutoNEB, Dimer, Sella, CCQN, D2S, Relax, Vibration, IRC, MD) remain unchanged.
