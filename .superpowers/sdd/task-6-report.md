# Task 6 report: governed Python API documentation and CCQN example

## Scope

Published the maintained `atst_tools.api` user-reference path, an ATST-specific
H2/Au CCQN automatic-mode Python example, concise navigation links, and an
explicit lightweight-example verification registration.

## RED evidence

- `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py -q`
  failed with five expected failures: the API reference and example were absent,
  and README navigation had no API link.
- `PYTHONPATH=src conda run -n atst-dev pytest
  tests/unit/test_examples.py::test_ccqn_api_example_has_a_lightweight_verification_record -q`
  failed with the expected missing `api_example` registration.

## Integration decisions

- The reference makes `atst_tools.api` the sole stable root import surface and
  directs CLI/YAML users and embedded-Python users to the appropriate interface.
- Configuration-driven workflows retain external-abacuslite-first resolution;
  calculator-injected CCQN retains strict caller ownership of calculator setup.
- The committed H2/Au script uses ASE EMT only as a lightweight test fixture,
  imports ATST exclusively through `atst_tools.api`, and does not add an ABACUS
  runtime dependency. The example test stubs input loading and `run_ccqn()` so
  it verifies the public import/execution contract without an expensive saddle
  calculation or backend runtime.

## GREEN and governance evidence

- `PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_docs_api.py tests/unit/test_examples.py tests/unit/test_docs_governance.py -q` — 18 passed.
- Public validation snippet printed `relax`.
- `conda run -n atst-dev python scripts/check_docs_governance.py` — passed.
- `git diff --check -- README.md docs examples/README.md AGENTS.md` — silent.
- Conflict-marker scan over the governed paths — no matches.
- `PYTHONPATH=src conda run -n atst-dev pytest tests -q` — passed; two
  pre-existing ASE NEB default-method warnings only.

## Files changed

- Added `docs/user/PYTHON_API_REFERENCE.md`,
  `examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py`, and
  `tests/unit/test_docs_api.py`.
- Updated public navigation, CLI/API selection guidance, configuration bridge,
  example registration, and the documentation-governance ledger.
- Extended `tests/unit/test_examples.py` with the reference-record contract.

## Remaining uncertainty

The script's direct CCQN optimization is intentionally not run in the unit
suite: it would need a real calculator execution and can be costly. Its public
API invocation, automatic-mode options, and lightweight fixture path are
covered; a production ABACUS run remains the caller's separately configured
runtime responsibility.
