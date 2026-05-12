# Examples Regression Report - 2026-05-11

## Scope

This report records the examples governance and real ABACUS regression rerun for the 2026-05-11 enhancement pass.

## Backup And Rerun Layout

Before rerunning the examples, the previous generated outputs were backed up under:

- `temp_example_rerun_20260511_013301/backup_previous_examples/`

The rerun was performed on isolated copies of the examples, not in `examples/` directly:

- Main rerun: `temp_example_rerun_20260511_013301/runs_attempt2/`
- IRC retry: `temp_example_rerun_20260511_013301/runs_attempt3_irc/10_irc_H2/`

All generated outputs remain ignored artifacts and are not intended to be committed.

## Slurm And ABACUS Conditions

ABACUS jobs were submitted to SAI Slurm on the `4V100` partition with one GPU allocation:

- `#SBATCH --partition=4V100`
- `#SBATCH --qos=rush-1o2gpu`
- `#SBATCH --nodes=1`
- `#SBATCH --ntasks=1`
- `#SBATCH --gpus-per-node=1`
- `module load abacus/LTSv3.10.1-sm70-auto`
- `conda activate atst-dev`
- `OMP_NUM_THREADS=8`
- ABACUS calculator settings patched in the rerun copies: `mpi: 1`, `omp: 8`

The first submission attempt used an explicit CPU option and SAI cancelled those jobs. The successful rerun scripts removed explicit CPU and memory requests, following SAI policy. Slurm still allocated `cpu=8` automatically for the single-GPU jobs.

ABACUS logs confirmed GPU execution and the intended process/thread layout, for example `RUNNING WITH DEVICE : GPU / Tesla V100-SXM2-32GB` and `Local MPI proc number: 1, OpenMP thread number: 8`.

## Baseline Artifacts

The previous generated outputs were captured in the backup directory before rerun. Key baseline values were:

| Case | Backup artifact | Frames / key result |
| --- | --- | --- |
| `01_neb_Li-Si` | `neb.traj` | 10 frames, final E `-7052.603598` eV, fmax `0.056372` eV/Ang |
| `02_neb_H2-Au` | `neb.traj` | 20 frames, final E `-239255.885770` eV, fmax `0.045665` eV/Ang |
| `04_dimer_CO-Pt` | `dimer.traj` | 2 frames; trajectory has no stored energy/force calculator results |
| `05_sella_H2-Au` | `sella.traj` | 104 frames, final E `-239255.026850` eV, fmax `0.375061` eV/Ang |
| `06_relax_H2-Au` | `relax.traj` | 2 frames, final E `-239256.270741` eV, fmax `0.234846` eV/Ang |
| `07_vibration_H2-Au` | `vibration_results.json` | ZPE `0.1935885253` eV; harmonic free energy `0.1759986606` eV |
| `08_d2s_Cy-Pt` | `neb_rough.traj` | 24 frames, final E `-11866.435419` eV, fmax `0.048716` eV/Ang |

## Rerun Results

| Case | Job | Slurm state | Elapsed | Key output |
| --- | --- | --- | --- | --- |
| `01_neb_Li-Si` | `395603` | `COMPLETED 0:0` | `00:01:47` | `neb.traj`: 10 frames, final E `-7052.603598` eV, fmax `0.056372` eV/Ang |
| `02_neb_H2-Au` | `395604` | `COMPLETED 0:0` | `00:39:16` | `neb.traj`: 20 frames, final E `-239255.885770` eV, fmax `0.045665` eV/Ang |
| `03_autoneb_Cy-Pt` | `395605` | `COMPLETED 0:0` | `01:10:52` | Final AutoNEB images include `run_autoneb009.traj`: E `-11866.435419` eV, fmax `0.048166` eV/Ang |
| `04_dimer_CO-Pt` | `395606` | `COMPLETED 0:0` | `00:34:04` | `dimer.traj`: 2 frames; log reached `MinModeTranslate` step 1, E `-211834.295360` eV, max force `0.7271` eV/Ang |
| `05_sella_H2-Au` | `395607` | `COMPLETED 0:0` | `04:00:46` | `sella.traj`: 104 frames, final E `-239255.016429` eV, fmax `0.372460` eV/Ang |
| `06_relax_H2-Au` | `395608` | `COMPLETED 0:0` | `00:47:10` | `relax.traj` and `final_relaxed.traj`: final E `-239256.270742` eV, fmax `0.234847` eV/Ang |
| `07_vibration_H2-Au` | `395609` | `COMPLETED 0:0` | `00:32:36` | ZPE `0.1935885166` eV; harmonic free energy `0.1759986433` eV at 300 K |
| `08_d2s_Cy-Pt` | `395610` | `COMPLETED 0:0` | `00:43:27` | `IS_opt.traj`: E `-11866.830063` eV; `FS_opt.traj`: E `-11866.435420` eV; `neb_rough.traj`: 24 frames; Dimer log reached `MinModeTranslate` step 1 |
| `10_irc_H2` | `395611` | `FAILED 1:0` | `00:02:13` | IRC produced 3 frames, final E `-31.699963` eV, fmax `0.002113` eV/Ang, then raised `IRCInnerLoopConvergenceFailure` |
| `10_irc_H2` retry with `keep_going: true` | `395617` | `FAILED 1:0` | `00:01:26` | IRC produced 4 frames, final E `-31.699963` eV, fmax `0.000000` eV/Ang, then Sella raised `AssertionError` in `restricted_step.get_s()` |
| `11_vibration_ideal_gas_H2` | `395612` | `COMPLETED 0:0` | `00:01:15` | ZPE `0.2783335292` eV; ideal-gas Gibbs free energy `-0.0340721783` eV at 298.15 K |

## Regression Assessment

The real ABACUS rerun confirms that the governed examples for NEB, AutoNEB, Dimer, Sella, Relax, Vibration, D2S, and ideal-gas vibration/thermochemistry remain executable on SAI `4V100` with single-card ABACUS settings.

Numerical comparison against the backed-up outputs shows the existing examples were not materially broken by the development pass:

- `01_neb_Li-Si`, `02_neb_H2-Au`, `06_relax_H2-Au`, and `08_d2s_Cy-Pt` reproduce the backed-up final energies and force levels to the recorded precision.
- `07_vibration_H2-Au` reproduces ZPE and harmonic thermochemistry within numerical noise.
- `05_sella_H2-Au` completes with the same frame count and comparable final force level; the final energy differs by about `0.010421` eV from the backup, consistent with a fresh Sella/ABACUS run path rather than a structural failure.
- Dimer trajectories currently do not persist calculator results in a way ASE can read back as energy/force values; the Slurm logs and workflow completion are therefore used as the regression evidence.

The IRC example is not release-clean under real ABACUS. It starts and writes physically meaningful frames, but the Sella IRC backend raises an exception after the path reaches a flat endpoint. Adding `keep_going: true` avoids the first convergence exception but still fails later inside Sella restricted-step handling. This should remain an open workflow issue before claiming IRC production readiness.

### IRC Failure Confirmation

The IRC failure was checked against the Slurm logs, generated trajectories, current ATST workflow code, and installed Sella implementation:

- ABACUS force calls completed before the Python exception. The failure is raised inside Sella IRC, not by Slurm or ABACUS.
- The default run fails at `sella.optimize.irc.IRCInnerLoopConvergenceFailure` after writing 3 trajectory frames.
- The `keep_going: true` retry writes 4 frames, warns that the IRC inner loop is no longer trustworthy, then fails at `sella.optimize.restricted_step.IRCTrustRegion.get_s()` with `AssertionError`.
- The H-H distance evolves from `0.900000` Ang in the TS input to about `0.7511` Ang in the generated frames, while fmax drops to near zero. The follow-up Sella step then hits a zero-gradient/flat-endpoint condition (`invalid value encountered in divide` in Sella IRC).
- Current ATST code correctly passes `dx`, `eta`, `gamma`, `irctol`, and `keep_going` into `sella.IRC`, but it has no workflow-level handling for this endpoint exception and therefore exits nonzero.

Confirmed conclusion: IRC support is functionally wired but not robust enough for release claims. The immediate fix should be to define endpoint/partial-path semantics for `atst run` IRC: either stop cleanly when the endpoint is reached and keep the valid partial trajectory, or catch the known Sella endpoint exceptions and report a controlled nonzero diagnostic with restart guidance. The current `10_irc_H2` example should remain a failing regression marker until that behavior is implemented and rerun on ABACUS.

## Current-Code Checks

- `pytest tests -q`: passed.
- `python -m compileall -q src/atst_tools tests`: passed.
- `git diff --check`: passed.
- All curated `examples/*/config*.yaml` files validate through the unit test suite.
- Lightweight command examples under `examples/09_lightweight_cli/` remain covered by unit tests and local smoke checks.

## Conclusion

The example set is mostly healthy for release validation after the documentation, CLI, and workflow governance changes. The blocking runtime finding is IRC robustness with the Sella backend under real ABACUS; all other rerun examples completed successfully on the requested SAI GPU resources.
