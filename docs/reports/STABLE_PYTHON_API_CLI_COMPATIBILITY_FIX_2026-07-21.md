# Stable Python API CLI Compatibility Fix 2026-07-21

**版本**: 2026-07-21
**日期**: 2026-07-21
**状态**: 当前主题审查
**责任人**: ATST-Tools maintainers

## Scope

This repair preserves the observable `atst run` behavior while workflows are
executed through the stable Python API.

## Root Cause and Resolution

`run_workflow()` correctly performs the ABACUS `--check-input` preflight as
part of its dry-run service. The CLI adapter logs successful YAML validation
only after the service returns, so a failed preflight never reports validation
success. The success record preserves the legacy payload
`Configuration is valid: calculation.type=%s, calculator.name=%s`.
The same service intentionally wraps execution failures
in `WorkflowExecutionError` for Python callers, but the CLI adapter re-raised
that API type rather than its legacy underlying error.

The CLI delegates validation and preflight execution to the API service, then
emits the established dry-run validation message only after that service
returns successfully. It still invokes the service exactly once for workflow
execution. At the CLI boundary only, a `WorkflowExecutionError` is translated
back to its original cause (and the existing IRC `SystemExit` presentation
remains unchanged). The service continues to expose typed API errors to Python
callers.

## Regression Coverage

- a failed `atst run --dry-run --check-input` does not log validation before
  propagating the original preflight exception;
- an ordinary workflow failure through `atst` exposes the original exception,
  not `WorkflowExecutionError` or its chained traceback;
- existing successful preflight, IRC boundary, and option-forwarding contracts
  remain covered.

## Verification

```bash
PYTHONPATH=src conda run -n atst-dev pytest tests/unit/test_cli.py -q -k \
  'check_input_failure_does_not_log_validation_before_legacy_error or \
  unwraps_api_workflow_error_for_cli_users or \
  dry_run_check_input_calls_abacus_preflight or \
  reports_irc_boundary_without_traceback or run_adapter_builds_cli_equivalent_options'
PYTHONPATH=src conda run -n atst-dev pytest tests -q
```

Both commands passed.  The full suite reported only two existing ASE NEB
default-method warnings.

## Task6 P2 documentation boundary

The stable CCQN API documentation now states the production injection
boundary consistently: callers provide a caller-created, correctly configured
`abacuslite` ASE calculator and complete the normal ABACUS pseudopotential,
orbital, executable/runtime, and site setup. ATST does not configure the
calculator, and ATST-Tools does not install or require ABACUS as a package
dependency. The EMT companion remains a lightweight, backend-free fixture.
