# 16 DMF Nonperiodic Smoke

This example shows the experimental standalone Direct MaxFlux workflow:

```bash
atst config validate config_dp.yaml --print-normalized
atst run --dry-run config_dp.yaml
```

DMF output is a transition-state candidate, not a validated transition state.
Run Dimer, Sella, CCQN, vibration, and IRC validation before reporting a final
TS.

Runtime requires `cyipopt` and IPOPT in the active environment. ATST-Tools
vendors PyDMF under `atst_tools.external.pydmf`, but does not vendor IPOPT.

Periodic structures are rejected by default. The experimental
`pbc_mode: cartesian_unwrapped` path assumes fixed-cell, pre-unwrapped
Cartesian endpoints and must be explicitly confirmed in YAML.
