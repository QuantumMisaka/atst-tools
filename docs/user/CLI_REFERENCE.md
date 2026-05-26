# ATST-Tools CLI Reference

ATST-Tools exposes one console command: `atst`. The previous standalone commands are removed; their behavior is now available through git-style subcommands under this entry point.

## Workflow Execution

```bash
atst run config.yaml
atst run --dry-run config.yaml
atst run --restart config.yaml
atst run --list-types
atst run --show-template neb --calculator abacus
atst run --show-template ccqn --calculator abacus
atst run --show-template irc --calculator abacus
```

`atst run` executes YAML-driven workflows. `--dry-run` validates the
configuration without launching calculators. `--restart` temporarily sets
`calculation.restart: true` without editing the YAML file. `--list-types`
prints supported workflow types. `--show-template` accepts `neb`, `autoneb`,
`dimer`, `sella`, `ccqn`, `d2s`, `relax`, `vibration`, or `irc`; combine it with
`--calculator {abacus,dp}` to choose the template backend. `--log-level`
accepts `DEBUG`, `INFO`, `WARNING`, or `ERROR`.

## Configuration Tools

```bash
atst config validate config.yaml
atst config validate config.yaml --print-normalized
atst config validate config.yaml --output used_config.yaml
```

`atst config validate` validates the same schema used by `atst run`. With
`--print-normalized` or `--output`, it emits the configuration after schema
defaults have been applied. This is the recommended way to confirm the exact
workflow settings before launching expensive ABACUS or DP calculations.

## ABACUS Tools

```bash
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input --force
atst abacus collect run_neb --output abacus_results.json
atst abacus collect run_neb --output abacus_results.json --structure final.extxyz
```

`atst abacus prepare` reads `calculator.abacus` from an ATST YAML file and
writes `INPUT`, `KPT`, and `STRU` with the active `abacuslite` writer. It does
not run ABACUS.

`atst abacus collect` scans an ABACUS run directory, records the presence of
`INPUT`, `KPT`, `STRU`, and `running*.log` files, then writes a JSON summary. If
the output directory has the files required by the active `abacuslite` reader,
it also parses the last frame and can write it through ASE with `--structure`.
The command copies parse inputs into a temporary directory before calling the
reader so original ABACUS outputs are not modified.

## NEB Tools

```bash
atst neb make INIT FINAL N_IMAGES -o inputs/init_neb_chain.traj --method [IDPP|linear]
atst neb make INIT FINAL N_IMAGES --ts TS_GUESS -o inputs/init_neb_chain.traj
atst neb make INIT FINAL N_IMAGES --from-chain old_neb.traj -o inputs/init_neb_chain.traj
atst neb post neb.traj --n-max 5 --plot --vib-analysis
atst neb post neb.traj --n-max 5 --write-latest neb_latest
atst neb post --autoneb-prefix run_autoneb --write-neb-init-chain init_neb_chain.traj
```

`atst neb make` performs structure interpolation only. If the input endpoints are pure structures without energy/force results, the output chain marks endpoint results as placeholders. `atst run` repairs those placeholders by running endpoint single-point calculations before NEB/AutoNEB starts; do not pass placeholder chains directly to bare ASE NEB.
`--method` accepts `IDPP` (default) or `linear`. `IDPP` starts from the aligned linear interpolation and then runs the in-repository Fast IDPP solver; `linear` writes the aligned linear interpolation directly. Use `-o/--output` to choose the output trajectory and `--format` to override ASE input format detection.
`atst neb make` also supports `--fix HEIGHT:DIR`, `--mag ELEMENT:MOMENT[,ELEMENT:MOMENT...]`, `--from-chain`, `--ts`, and `--no-align`. `sort_tol` and pymatgen autosort are intentionally not part of the refactored CLI.

`atst neb post` reads an existing NEB trajectory, reports the barrier, extracts the TS guess, and can suggest vibration atom indices. It supports `--n-max`, `--plot`, `--plot-all`, `--view`, `--vib-analysis`, `--vib-thr`, `--output-prefix`, and `--strict-band`. It can analyze ordinary NEB trajectories or explicit AutoNEB final image files with `--autoneb-prefix` / `--autoneb-files`. It writes restartable chains only when requested with `--write-neb-init-chain` or `--write-latest`.

## Trajectory Tools

```bash
atst traj collect inputs/*.cif -o collection.traj
atst traj collect frames/*.stru -o collection.traj --no-calc
atst traj transform collection.traj --format extxyz --output-prefix collection
atst traj transform neb.traj --neb --n-max 5 --format cif --output-prefix latest_band
```

`collect` builds a deterministic multi-frame trajectory from sorted input paths. Use `--no-calc` to drop attached calculators before writing. `transform` converts trajectories to `traj`, `extxyz`, or per-frame `stru`/`cif` files with `--format {traj,extxyz,stru,cif}` and `--output-prefix`. With `--neb`, it reuses the shared latest-band selector used by NEB restart and post-processing; pass `--n-max` when the band size cannot be inferred.

## Dimer Tools

```bash
atst dimer make-from-neb neb.traj \
  --output-traj inputs/dimer_init.traj \
  --output-vector inputs/displacement_vector.npy
```

This command extracts the highest-energy NEB image and a normalized displacement vector for a Dimer calculation. It accepts `--n-max`, `--output-traj`, `--output-vector`, and `--norm`. The Dimer calculation itself remains a YAML workflow through `atst run`.
`--output-structure` is accepted as a hidden compatibility alias during the refactor period.

## Relax Tools

```bash
atst relax post relax.traj --output-format stru --output STRU
atst relax post sella.traj --ind -1 --output-format traj --output restart.traj
```

`atst relax post` extracts one frame from a relaxation, Dimer, or Sella trajectory, prints the energy and maximum atomic force, and writes a restart structure. Use `--ind` to choose the frame, `--output-format {stru,cif,poscar,traj,xyz}` to choose the writer, and `--output` to choose the path. This is the lightweight path for preparing TS relax / Single-End Methods restart inputs.

## Vibration Tools

```bash
atst vibration post config.yaml
atst vibration post config.yaml --write-modes
```

This command rebuilds vibration summary and thermochemistry JSON from existing ASE vibration cache files. It does not launch new force calculations. Use `--write-modes` to write ASE vibration mode trajectories and `--output` to choose the JSON path.
It supports the same thermochemistry configuration as `calculation.type: vibration`, including harmonic corrections and ideal-gas corrections for small molecules.

## Workflow CLI Boundary

`config validate`, `abacus prepare/collect`, `neb make/post`, `dimer make-from-neb`, `relax post`, and `vibration post` are lightweight commands. They do not create workflow calculators, run ABACUS/DP, or submit jobs. Dimer, Sella, CCQN, D2S, Relax, Vibration, and IRC calculations remain YAML workflows through `atst run`.
