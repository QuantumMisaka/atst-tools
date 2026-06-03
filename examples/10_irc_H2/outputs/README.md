# 10 H2 Descent IRC Outputs

These files are curated from P0/P1 runtime validation for the descent IRC
examples.

Included files:

- `irc_descent.traj` and `norm_irc_descent.traj`: ABACUS descent IRC trajectory pair from SAI job `461256`.
- `atst_artifacts_descent.json`: ABACUS artifact manifest.
- `slurm-atst_ircdesc-461256.out` and `.err`: successful Slurm logs.
- `irc_descent_dp.traj` and `norm_irc_descent_dp.traj`: DP descent IRC trajectory pair.
- `atst_artifacts_descent_dp.json`: DP artifact manifest.

Quick checks from this example directory:

```bash
python -c "from ase.io import read; print(len(read('outputs/irc_descent.traj', index=':')))"
python -c "from ase.io import read; print(len(read('outputs/irc_descent_dp.traj', index=':')))"
```
