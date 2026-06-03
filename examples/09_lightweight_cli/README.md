# Lightweight CLI Examples

This case demonstrates commands that do not launch ABACUS or DP calculations.
They are intended for local pre-processing, post-processing, and restart
preparation.

Run from this directory:

```bash
atst neb make inputs/init.xyz inputs/final.xyz 3 -o inputs/init_neb_chain.traj --method linear
atst neb make inputs/init.xyz inputs/final.xyz 3 --ts inputs/ts.xyz -o inputs/init_neb_chain_ts.traj --method linear
atst neb post inputs/neb_result.extxyz --n-max 1 --vib-analysis --write-latest neb_latest
atst neb post inputs/neb_result.extxyz --n-max 1 --plot --plot-label neb_energy_profile --energy-profile
atst traj transform inputs/neb_result.extxyz --neb --n-max 1 --format extxyz --output-prefix latest_band
atst traj collect inputs/init.xyz inputs/ts.xyz inputs/final.xyz -o collection.traj --no-calc
atst dimer make-from-neb inputs/neb_result.extxyz --n-max 1 --output-traj dimer_init.traj
atst relax post inputs/relax_result.extxyz --output-format traj --output restart.traj
atst vibration post vibration_post.yaml --output vibration_results.json
```

`atst relax post` is also the recommended way to extract a restart structure
from TS relax trajectories produced by Dimer or Sella.

The `vib/cache.*.json` files are a minimal synthetic ASE vibration cache for
the H2 post-processing command above. They are included only so
`atst vibration post` can run locally without launching ABACUS or DP; use the
validated workflow examples and `reference_results.json` for scientific
reference values.

When `atst neb make` starts from pure structures, the endpoint energies and
forces in the generated chain are placeholders. `atst run` automatically
performs endpoint single-point calculations before NEB/AutoNEB starts, so use
the generated chain through the YAML workflow rather than bare ASE NEB.

Configuration and ABACUS helper commands are also lightweight:

```bash
atst config validate ../06_relax_H2-Au/config.yaml --print-normalized
atst abacus prepare ../06_relax_H2-Au/config.yaml --structure ../06_relax_H2-Au/inputs/init.stru --output-dir abacus_input
atst abacus collect abacus_input --output abacus_results.json
```

`atst abacus prepare` writes `INPUT`, `KPT`, and `STRU`; `collect` writes a
JSON file summary. Neither command launches ABACUS.
