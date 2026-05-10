# ATST-Tools CLI Reference

ATST-Tools exposes one console command: `atst`. The previous standalone commands are removed; their behavior is now available through git-style subcommands under this entry point.

## Workflow Execution

```bash
atst run config.yaml
atst run --dry-run config.yaml
atst run --restart config.yaml
atst run --list-types
atst run --show-template neb --calculator abacus
atst run --show-template irc --calculator abacus
```

`atst run` executes YAML-driven workflows. `--restart` temporarily sets `calculation.restart: true` without editing the YAML file.

## NEB Tools

```bash
atst neb make INIT FINAL N_IMAGES -o inputs/init_neb_chain.traj
atst neb post neb.traj --plot --vib-analysis
```

`atst neb make` performs structure interpolation only. `atst neb post` reads an existing NEB trajectory, reports the barrier, extracts the TS guess, and can suggest vibration atom indices.

## Dimer Tools

```bash
atst dimer make-from-neb neb.traj \
  --output-traj inputs/dimer_init.traj \
  --output-vector inputs/displacement_vector.npy
```

This command extracts the highest-energy NEB image and a normalized displacement vector for a Dimer calculation. The Dimer calculation itself remains a YAML workflow through `atst run`.
`--output-structure` is accepted as a hidden compatibility alias during the refactor period.

## Relax Tools

```bash
atst relax post relax.traj --output-format stru --output STRU
atst relax post sella.traj --ind -1 --output-format traj --output restart.traj
```

`atst relax post` extracts one frame from a relaxation, Dimer, or Sella trajectory, prints the energy and maximum atomic force, and writes a restart structure. This is the lightweight path for preparing TS relax / Single-End Methods restart inputs.

## Vibration Tools

```bash
atst vibration post config.yaml
atst vibration post config.yaml --write-modes
```

This command rebuilds vibration summary and thermochemistry JSON from existing ASE vibration cache files. It does not launch new force calculations.
It supports the same thermochemistry configuration as `calculation.type: vibration`, including harmonic corrections and ideal-gas corrections for small molecules.

## Workflow CLI Boundary

`neb make/post`, `dimer make-from-neb`, `relax post`, and `vibration post` are lightweight commands. They do not create calculators or submit jobs. Dimer, Sella, D2S, Relax, Vibration, and IRC calculations remain YAML workflows through `atst run`.
