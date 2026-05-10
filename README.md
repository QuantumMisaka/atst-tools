# ATST-Tools

ATST-Tools is a CLI + YAML toolkit for ASE-based transition-state and local
structure workflows. The 2.0 line is ABACUS-first: ABACUS is supported through
the vendored upstream `ASE_interface`/abacuslite backend, while DeePMD and other
machine-learning potentials are kept as secondary calculator targets.

The supported workflow entry point is:

```bash
atst-run config.yaml
```

## Scope

Current workflows:

- NEB / CI-NEB / DyNEB
- AutoNEB
- Dimer
- Sella
- D2S, a rough NEB to Dimer/Sella workflow
- Relax
- Vibration analysis

Electronic-structure post-processing workflows such as band structure, DOS, and
NSCF are outside the current ATST-Tools scope.

## Installation

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install -e .
```

Runtime requirements:

- Python 3.9+
- ASE, NumPy, SciPy, Matplotlib, ruamel.yaml, Sella
- ABACUS executable available in `PATH` for ABACUS calculations
- deepmd-kit only when using `calculator.name: dp`

The ABACUS ASE backend is bundled in
`src/atst_tools/external/ASE_interface`; no separate `ase-abacus` install is
needed.

## Quick Start

Validate a YAML file before spending compute time:

```bash
atst-run --dry-run examples/06_relax_H2-Au/config.yaml
```

Run a calculation:

```bash
cd examples/06_relax_H2-Au
atst-run config.yaml
```

List supported workflow types:

```bash
atst-run --list-types
```

Print a starter YAML template:

```bash
atst-run --show-template neb --calculator abacus
```

## YAML Shape

All production configs should use two top-level sections:

```yaml
calculation:
  type: relax
  init_structure: init.stru
  fmax: 0.05

calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: relax_run
    parameters:
      calculation: scf
      basis_type: lcao
      ks_solver: cusolver
      cal_force: 1
      pseudo_dir: ../data
      orbital_dir: ../data
      pseudopotentials:
        H: H_ONCV_PBE-1.0.upf
      basissets:
        H: H_gga_6au_100Ry_2s1p.orb
```

`calculator.name: abacus` is the primary supported path. For Slurm clusters,
wrap `atst-run config.yaml` in the site-specific job script and keep scheduler
details outside the YAML. On the SAI GPU environment, LCAO ABACUS examples use
`ks_solver: cusolver`.

## Analysis

Analyze an NEB trajectory and extract a transition-state guess:

```bash
atst-neb-post neb.traj --plot
```

Suggest vibration indices from the NEB displacement pattern:

```bash
atst-neb-post neb.traj --vib-analysis --vib-thr 0.10
```

## Documentation

- [Configuration reference](docs/CONFIG_REFERENCE.md)
- [Refactoring acceptance report](docs/REFACTORING_ACCEPTANCE_REPORT.md)
- [Machine-learning calculator plan](docs/ML_CALCULATOR_PLAN.md)

## License

LGPL-v3 License
