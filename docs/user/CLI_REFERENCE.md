# ATST-Tools CLI Reference

ATST-Tools exposes one console command: `atst`. The previous standalone commands are removed; their behavior is now available through git-style subcommands under this entry point.

## Workflow Execution

```bash
atst run config.yaml
atst run --dry-run config.yaml
atst run --restart config.yaml
atst run --list-types
atst run --show-template neb --calculator abacus
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
  --output-structure inputs/dimer_init.traj \
  --output-vector inputs/displacement_vector.npy
```

This command extracts the highest-energy NEB image and a normalized displacement vector for a Dimer calculation. The Dimer calculation itself remains a YAML workflow through `atst run`.

## Vibration Tools

```bash
atst vibration post config.yaml
atst vibration post config.yaml --write-modes
```

This command rebuilds vibration summary and thermochemistry JSON from existing ASE vibration cache files. It does not launch new force calculations.
