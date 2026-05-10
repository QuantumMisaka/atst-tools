# Lightweight CLI Examples

This case demonstrates commands that do not launch ABACUS or DP calculations.
They are intended for local pre-processing, post-processing, and restart
preparation.

Run from this directory:

```bash
atst neb make inputs/init.xyz inputs/final.xyz 3 -o inputs/init_neb_chain.traj --method linear
atst neb post inputs/neb_result.extxyz --n-max 1 --vib-analysis
atst dimer make-from-neb inputs/neb_result.extxyz --n-max 1 --output-traj dimer_init.traj
atst relax post inputs/relax_result.extxyz --output-format traj --output restart.traj
atst vibration post vibration_post.yaml --output vibration_results.json
```

`atst relax post` is also the recommended way to extract a restart structure
from TS relax trajectories produced by Dimer or Sella.
