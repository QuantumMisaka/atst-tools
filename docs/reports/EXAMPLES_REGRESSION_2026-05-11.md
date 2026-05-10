# Examples Regression Report - 2026-05-11

## Scope

This report records the examples governance and regression checks for the 2026-05-11 enhancement pass.

## Baseline Artifacts

Ignored baseline outputs were present in the established examples before cleanup/governance work, including:

- `examples/01_neb_Li-Si/neb.traj`
- `examples/02_neb_H2-Au/neb.traj`
- `examples/03_autoneb_Cy-Pt/run_autoneb*.traj`
- `examples/04_dimer_CO-Pt/dimer.traj`
- `examples/05_sella_H2-Au/sella.traj`
- `examples/06_relax_H2-Au/relax.traj`
- `examples/07_vibration_H2-Au/vibration_results.json`
- `examples/08_d2s_Cy-Pt/neb_rough.traj` and `dimer.traj`

These files remain treated as generated outputs, not curated inputs.

## Current-Code Checks

- All curated `examples/*/config*.yaml` files validate through the unit test suite.
- New lightweight example inputs were added under `examples/09_lightweight_cli/`.
- New IRC examples were added under `examples/10_irc_H2/` for `both`, `forward`, and `reverse`.
- New small-molecule thermochemistry example was added under `examples/11_vibration_ideal_gas_H2/`.
- Lightweight commands were rerun on a temporary copy of `examples/09_lightweight_cli/`:
  - `atst neb make` generated a 5-image chain.
  - `atst neb post` reported a 0.4 eV example barrier and suggested vibration atom indices.
  - `atst dimer make-from-neb` wrote `dimer_init.traj` and `displacement_vector.npy`.
  - `atst relax post` extracted the last frame with energy `-1.1 eV` and max force `0.001 eV/Ang`.

## Runtime Status

The local non-Slurm verification path passed in `atst-dev`: unit tests, compile checks, CLI help/list/template smoke checks, and dry-run checks. Full ABACUS/Slurm reruns are environment- and queue-dependent and should be treated as the final release validation gate.

## Regression Conclusion

The code-level regression surface covered by lightweight commands, YAML validation, restart helpers, and post-processing is healthy. No new generated outputs are intended to be committed.
