# 17 DMF PBC Cartesian Unwrapped Smoke

This example documents the experimental P2 PBC guard path for DMF:

```bash
atst config validate config_dp.yaml --print-normalized
atst run --dry-run config_dp.yaml
```

It is a toy fixed-cell input for schema and runtime-guard validation. It is not
production evidence for periodic DMF and does not claim MIC-aware or
fractional-coordinate support.

Required PBC settings:

- `pbc_mode: cartesian_unwrapped`
- `confirm_pbc_risk: true`
- `remove_rotation_and_translation: false`
- `initial_path: linear`

The endpoint cells and PBC flags must match exactly. Coordinates are consumed
as supplied Cartesian positions, so users are responsible for pre-unwrapping
the path into the intended periodic image before running.
