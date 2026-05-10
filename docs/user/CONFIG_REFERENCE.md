# ATST-Tools Configuration Reference

**Version**: 2.0.0-rc  
**Last Updated**: 2026-05-11
**Status**: Release Candidate

This document provides a comprehensive reference for the `config.yaml` file used by `atst run`. The configuration is divided into two main sections: `calculation` (task definition) and `calculator` (engine configuration). New configurations should use this two-section layout; root-level `abacus` is retained only as a migration path for legacy inputs.

---

## 1. Top-Level Structure

```yaml
calculation:
  type: <task_type>  # Required. Options: neb, autoneb, dimer, sella, d2s, relax, vibration, irc
  # ... task specific parameters ...

calculator:
  name: <engine_name> # Required. Options: abacus, dp
  # ... engine specific parameters ...
```

Useful CLI checks:

```bash
atst run --dry-run config.yaml
atst run --list-types
atst run --show-template neb --calculator abacus
```

---

## 2. Calculation Section

The `calculation` section defines the type of task and its parameters.

### 2.1 Common Parameters (All Types)
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `type` | string | **Required** | Task type: `neb`, `autoneb`, `dimer`, `sella`, `d2s`, `relax`, `vibration`, `irc`. |
| `fmax` | float | `0.05` | Maximum force convergence criterion (eV/Å). |
| `optimizer` | string | `FIRE` | Optimization algorithm: `FIRE`, `BFGS`, `QuasiNewton`, etc. |
| `trajectory` | string | `None` | Path to save the optimization trajectory (e.g., `opt.traj`). |
| `parallel` | bool | `False` | Enable parallel execution (e.g., for NEB images). |
| `restart` | bool | `false` | Resume from workflow checkpoints when supported. CLI equivalent: `atst run --restart config.yaml`. |

### 2.2 Nudged Elastic Band (NEB)
**Type**: `neb`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_chain` | string | **Required** | Path to the initial chain file (e.g., `init_neb_chain.traj`). |
| `climb` | bool | `True` | Enable Climbing Image NEB (CI-NEB). |
| `k` | float | `0.1` | Spring constant for the band (eV/Å²). |
| `algorism` | string | `improvedtangent` | Tangent method. |
| `trajectory` | string | `neb.traj` | NEB trajectory. Restart uses the latest band from this file when available. |

### 2.3 AutoNEB
**Type**: `autoneb`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `prefix` | string | `autoneb` | Prefix for output files and directories. |
| `init_chain` | string | **Required** | Path to the initial guess chain. |
| `n_simul` | int | `1` | Number of images to optimize simultaneously. |
| `n_max` | int | `10` | Maximum number of images in the band. |
| `maxsteps` | int | `100` | Maximum optimization steps per iteration. |
| `iter_folder` | string | `AutoNEB_iter` | Folder to store iteration results. |

### 2.4 Dimer Method
**Type**: `dimer`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure (e.g., `dimer_init.traj`). |
| `init_eigenmode_method` | string | `displacement` | Method to initialize eigenmode: `displacement`. |
| `displacement_vector` | string | `None` | Path to numpy file containing displacement vector (e.g., `vector.npy`). |
| `trajectory` | string | `dimer.traj` | Dimer trajectory. Restart uses the last frame when available. |

### 2.5 Sella (Saddle Point Finder)
**Type**: `sella`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure. |
| `eta` | float | `0.002` | Sella parameter (step size control). |
| `order` | int | `1` | Saddle point order (1 for TS). |
| `trajectory` | string | `sella.traj` | Sella trajectory. Restart uses the last frame when available. |

### 2.6 Structure Relaxation (Relax)
**Type**: `relax`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the initial structure file. |
| `trajectory` | string | `relax.traj` | Relaxation trajectory. Restart uses the last frame when available. |

### 2.7 Vibration Analysis
**Type**: `vibration`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | Path to the optimized structure. |
| `delta` | float | `0.01` | Displacement step size (Å). |
| `nfree` | int | `2` | Number of displacements per degree of freedom (2 or 4). |
| `indices` | list[int] | `None` | List of atom indices to vibrate. If None, all atoms are vibrated. |
| `name` | string | `vib` | Name prefix for vibration files. |
| `temperature` | float | `300.0` | Temperature for thermodynamic analysis (K). |
| `restart` | bool | `false` | Reuse existing ASE vibration cache files. The default removes stale cache files before running. |

Thermochemistry is controlled by an optional nested block:

```yaml
calculation:
  type: vibration
  init_structure: inputs/ts_opt.stru
  thermochemistry:
    model: harmonic        # harmonic or ideal_gas
    temperature: 300.0
    ignore_imag_modes: true
```

`model: harmonic` uses ASE `HarmonicThermo` and reports ZPE, entropy, internal energy, and Helmholtz free energy. This is the default for surfaces, adsorbates, TS local modes, and solid-like approximations.

For isolated small molecules, use `model: ideal_gas`:

```yaml
thermochemistry:
  model: ideal_gas
  temperature: 298.15
  pressure: 101325.0
  geometry: linear          # monatomic, linear, or nonlinear
  symmetrynumber: 2
  spin: 0
  ignore_imag_modes: true
```

This uses ASE `IdealGasThermo` and includes translational, rotational, and vibrational degrees of freedom in the reported Gibbs free energy.

### 2.8 D2S (Double-Ended to Single-Ended)
**Type**: `d2s`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `method` | string | `dimer` | Single-ended method: `dimer` or `sella`. |
| `init_file` | string | **Required** | Initial state structure file. |
| `final_file` | string | **Required** | Final state structure file. |
| `neb` | dict | `{}` | Configuration for the rough DyNEB phase. |
| `dimer` | dict | `{}` | Configuration for Dimer phase (if method=dimer). |
| `sella` | dict | `{}` | Configuration for Sella phase (if method=sella). |

### 2.9 IRC
**Type**: `irc`

IRC follows the legacy main-branch `sella_IRC.py` behavior through YAML. It starts from a TS structure, runs Sella IRC forward, reverse, or both directions, and writes a normalized trajectory for the combined mode.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `init_structure` | string | **Required** | TS structure used as the IRC starting point. |
| `trajectory` | string | `irc_log.traj` | IRC trajectory. Restart appends from the last frame. |
| `normalized_trajectory` | string | `norm_<trajectory>` | Output for normalized forward/reverse trajectory when `direction: both`. |
| `direction` | string | `both` | `both`, `forward`, or `reverse`. |
| `fmax` | float | `0.05` | IRC convergence criterion. |
| `max_steps` | int | `1000` | Steps per IRC direction. |
| `dx` | float | `0.1` | IRC step size. |
| `eta` | float | `0.0001` | Sella IRC parameter. |
| `gamma` | float | `0.1` | Sella IRC parameter. |
| `irctol` | float | `0.01` | IRC tolerance. |
| `keep_going` | bool | `false` | Forwarded to `sella.IRC`. |

---

## 3. Calculator Section

The `calculator` section configures the underlying compute engine (DFT or ML Potential).

### 3.1 ABACUS (DFT)
**Name**: `abacus`
> **Note**: For backward compatibility, parameters can also be placed under an `abacus` root key instead of `calculator.abacus`.
> On the SAI GPU validation environment, LCAO examples use `ks_solver: cusolver`.
> ATST-Tools imports an independently installed `abacuslite` package first and falls back to the vendored `src/atst_tools/external/ASE_interface/abacuslite` snapshot if that import is unavailable.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `command` | string | `abacus` | Command to execute ABACUS (e.g., `mpirun -np 4 abacus`). |
| `mpi` | int | `1` | Number of MPI processes (deprecated, use `command` to specify mpirun). |
| `omp` | int | `1` | Number of OpenMP threads per process. |
| `directory` | string | `.` | Working directory for the calculator. |
| `kpts` | list[int] | `[1, 1, 1]` | K-points sampling (e.g., `[3, 3, 3]`). |
| `pseudopotentials` | dict | **Required** | Map of element symbol to UPF file name. |
| `basissets` | dict | **Required** | Map of element symbol to ORB file name (for LCAO). |
| `pseudo_dir` | string | `.` | Directory containing pseudopotential files. |
| `orbital_dir` | string | `.` | Directory containing basis set files. |
| `parameters` | dict | `{}` | Key-value pairs for ABACUS `INPUT` file (e.g., `ecutwfc`, `scf_thr`). |

### 3.2 Deep Potential (DP)
**Name**: `dp`

DP support is planned and validated after the ABACUS-first 2.0.0 acceptance path.
The intended implementation is documented in `../developer/plans/ML_CALCULATOR_PLAN.md`.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `model` | string | **Required** | Absolute path to the frozen model file (`.pb` or `.pt`). |
| `type_map` | list[string] | `None` | Optional element type map passed to deepmd-kit. |
| `omp` | int | `1` | Planned OpenMP thread count for DP evaluation. |
| `share_calculator` | bool | `true` | Planned calculator reuse policy for workflows where ASE permits sharing. |

---

## 4. Example Configuration

See `examples/` directory for full working examples of each calculation type.

```yaml
# minimal_example.yaml
calculation:
  type: relax
  init_structure: init.stru
  fmax: 0.01

calculator:
  name: dp
  dp:
    model: /path/to/graph.pb
```
