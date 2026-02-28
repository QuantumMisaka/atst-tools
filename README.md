# ATST-Tools

**Advanced ASE Transition State Tools for ABACUS (and Deep-Potential).**

ATST-Tools provides a robust, configuration-driven workflow for performing transition state searches (NEB, Dimer, Sella) and related calculations (Relax, Vibration) using the ASE interface. It is designed to work seamlessly with **ABACUS** and **DeepMD-kit**.

> **Note**: This project focuses on **Transition State Calculations** (NEB, Dimer, Sella, Vibration) and standard MD/Relaxation. Advanced electronic structure analysis (e.g., Band Structure, DOS, NSCF) is **NOT** currently supported.

## Installation

### Prerequisites
1.  **Python 3.9+**
2.  **ABACUS**: Ensure `abacus` is in your PATH (for DFT calculations).
3.  **DeepMD-kit** (Optional): For using Deep Potential models.

### Install from Source
Clone the repository and install in editable mode:

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install -e .
```

*Note: The ABACUS interface (`abacuslite`) is now bundled internally, so no external ASE-ABACUS dependency is required.*

## Usage

ATST-Tools uses a single entry point `atst-run` driven by a `config.yaml` file.

### 1. Prepare Configuration
Create a `config.yaml` file. See `examples/` for comprehensive templates.

**Example (NEB with ABACUS):**
```yaml
calculation:
  type: neb
  init_chain: init_neb_chain.traj
  climb: true
  fmax: 0.05
  parallel: true

calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_neb
    parameters:
        calculation: scf
        ecutwfc: 100
        basis_type: lcao
        ks_solver: genelpa
        dft_functional: pbe
        # ... other parameters
        pseudo_dir: ../data
        orbital_dir: ../data
        pseudopotentials:
           H: H_ONCV_PBE-1.0.upf
           Au: Au_ONCV_PBE-1.0.upf
        basissets:
           H: H_gga_6au_100Ry_2s1p.orb
           Au: Au_gga_7au_100Ry_4s2p2d1f.orb
```

### 2. Run Calculation
```bash
atst-run config.yaml
```

### 3. Analysis
Use the provided utility scripts to analyze results.

**Analyze NEB barrier and extract TS:**
```bash
atst-neb-post neb.traj --plot
```

**Identify atoms for Vibration analysis:**
Use the `--vib-analysis` flag to find which atoms have significant displacement in the NEB mode, which helps in setting the `indices` parameter for vibration tasks.
```bash
atst-neb-post neb.traj --vib-analysis --vib-thr 0.10
```

## Features

- **Calculators**: 
  - **ABACUS**: Full support via `abacuslite` (LCAO/PW).
  - **Deep Potential**: Support for `.pb` / `.pt` models with efficient instance sharing.
- **Workflows**:
  - **NEB**: CI-NEB, DyNEB, AutoNEB.
  - **Dimer**: Improved Dimer method.
  - **Sella**: Integration with Sella optimizer.
  - **Relax**: Geometry optimization.
  - **Vibration**: Vibrational mode analysis.
  - **D2S**: Double-to-Single ended workflow (NEB -> Sella/Dimer).

## Documentation

See `docs/` for more details.

## License

LGPL-v3 License
