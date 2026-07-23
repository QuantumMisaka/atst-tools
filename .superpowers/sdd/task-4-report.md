# Task 4 report: embedded CCQN Python API

## Scope

Implemented the supplied-calculator CCQN service while preserving the legacy
YAML and `AbacusCCQN` factory path.  The public API now exposes the already
declared `run_ccqn(atoms, calculator, options=CCQNOptions())` behavior.

## RED evidence

After adding the injection and public-result tests, before production changes,
ran:

```bash
PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_ccqn.py tests/unit/test_api.py -q
```

Result: exit code 1. The legacy constructor rejected `calculator=` with the
expected `TypeError`, and the public service raised its expected
`NotImplementedError` placeholder.

Before extracting the options converter, ran:

```bash
PYTHONPATH=src conda run -n atst-dev pytest \
  tests/unit/test_api.py::test_ccqn_options_config_maps_only_supported_ccqn_schema_fields -q
```

Result: exit code 1 with the expected missing
`services._ccqn_options_to_config` attribute.

## Implementation

- Extended `AbacusCCQN` additively with an optional `calculator` argument.
  The legacy `calculator=None` path still creates the calculator through
  `CalculatorFactory` with its existing arguments.  An injected calculator is
  returned directly and is attached only to an optimization copy.
- Added `run_ccqn()` as the embedded public service.  It copies caller atoms,
  supplies exactly the caller calculator, does not pass calculator-name,
  directory, MPI, or I/O settings, returns a detached final-structure
  snapshot, and records `backend_source: provided`.
- Added `_ccqn_options_to_config()` to map every emitted API option to an
  existing CCQN schema field.  The test asserts both the full emitted mapping
  and the schema-field boundary.
- Added regressions for no-factory injection, original-atoms ownership,
  supplied backend provenance, and reactive-mode option mapping.

## Verification

Focused API and CCQN tests:

```bash
PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_ccqn.py tests/unit/test_api.py -q
```

Result: exit code 0, 37 tests passed.

CCQN/API plus workflow compatibility:

```bash
PYTHONPATH=src conda run -n atst-dev pytest \
  tests/unit/test_ccqn.py tests/unit/test_api.py tests/unit/test_workflows.py -q
```

Result: exit code 0, 94 tests passed.

Full source suite:

```bash
PYTHONPATH=src conda run -n atst-dev pytest tests -q
git diff --check
```

Result: both commands exited 0.  The source suite completed through 100% with
only the two pre-existing ASE NEB default-method warnings.

## Files changed

- `src/atst_tools/mep/ccqn.py`
- `src/atst_tools/api/services.py`
- `tests/unit/test_ccqn.py`
- `tests/unit/test_api.py`

## Remaining uncertainty

None within Task 4's boundary.  The public API intentionally owns neither
calculator reconstruction nor calculator configuration; direct factory use
remains limited to the preserved configuration-driven legacy path.
