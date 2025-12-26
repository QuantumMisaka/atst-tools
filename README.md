# ATST-Tools

Advanced ASE Transition State Tools for ABACUS (and Deep-Potential).

## Installation

### Prerequisites
1. **ASE with ABACUS Support**: You must install the ASE version adapted for ABACUS.
   ```bash
   cd deps/ase-abacus
   pip install .
   ```
2. **Core Dependencies**:
   ```bash
   pip install -e .
   ```

### Optional Dependencies
- **DeepMD-kit**: For using Deep Potential models.

## Usage

ATST-Tools now supports a configuration-driven workflow.

### 1. Prepare Configuration
Create a `config.yaml` file (see `examples/` for templates):

```yaml
calculation:
  type: neb
  init_chain: init_neb_chain.traj
  climb: true
  fmax: 0.05
  parallel: true

abacus:
  command: abacus
  mpi: 4
  parameters:
    calculation: scf
    nspin: 2
    xc: pbe
    # ... other DFT parameters
```

### 2. Run Calculation
Execute the unified entry point:

```bash
atst-run config.yaml
```

This command will automatically dispatch the task (NEB, AutoNEB, or Dimer) based on your configuration.

## Features

- **NEB**: Supports CI-NEB, IT-NEB, and DyNEB (Dynamic NEB).
  - *New*: Correctly handles stress tensor for variable cell NEB (not supported in standard ASE).
- **AutoNEB**: Automated NEB workflow with automatic image addition and path smoothing.
  - *New*: Automatic cleanup of bulky ABACUS calculation directories.
- **Dimer**: Improved Dimer method for ABACUS.
- **Sella**: Integration with Sella library for efficient saddle point search.

## Documentation

For detailed algorithm descriptions, see [ASE Documentation](https://wiki.fysik.dtu.dk/ase/).

## License

LGPL-v3 License
