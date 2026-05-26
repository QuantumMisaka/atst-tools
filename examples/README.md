# ATST-Tools Examples

This directory contains standardized examples for using `atst-tools` with ABACUS and Deep Potential (DP).
The examples are organized by chemical system and method to demonstrate the versatility of the toolkit.

## Directory Structure

*   `data/`: Centralized repository for Pseudopotentials (`.upf`) and Numerical Orbitals (`.orb`).
*   `<case>/inputs/`: Curated input structures and vectors referenced by `config*.yaml`.
*   `config.yaml`: ABACUS-backed example configuration.
*   `config_dp.yaml`: DP-backed example configuration when available. These use `../../temp_repos/dp_model/DPA-3.1-3M.pt` with `head: Omat24` for local validation; the model file is intentionally outside git.
*   Generated outputs such as `run_*`, `OUT.ABACUS`, `AutoNEB_iter`, `vib`, `vib_calc`, `*.traj`, `*.json`, Slurm logs, and ABACUS/DP scratch files are ignored unless they are explicitly curated inputs.

### 1. Basic Examples (Li Diffusion)
*   `01_neb_Li-Si/`: **Li diffusion in Si**. A simple, fast-running NEB example suitable for quick testing and getting started.

### 2. Surface Reactions (H2 on Au(111))
*   `02_neb_H2-Au/`: **H2 dissociation on Au(111)**. Demonstrate NEB on a metal surface.
*   `05_sella_H2-Au/`: Sella method for the same system.
*   `06_relax_H2-Au/`: Geometry optimization of the initial state.
*   `07_vibration_H2-Au/`: Vibrational analysis of the Transition State.
*   `12_ccqn_H2-Au/`: CCQN single-ended transition-state search for the same H2/Au system.

### 3. Advanced Workflows (Cyclohexane on Pt@Graphene)
*   `03_autoneb_Cy-Pt/`: **Cyclohexane on Pt-doped Graphene**. Demonstrates the **AutoNEB** workflow for complex paths.
*   `08_d2s_Cy-Pt/`: **Double-to-Single (D2S)** workflow, combining rough NEB with precise Sella/Dimer/CCQN search.

### 4. Lightweight Commands and Auxiliary Workflows
*   `09_lightweight_cli/`: Local pre/post-processing examples for `atst neb`, summary commands, `atst dimer`, `atst relax post`, and `atst vibration post`.
*   `10_irc_H2/`: IRC YAML examples for `direction: both`, `forward`, and `reverse`.
*   `11_vibration_ideal_gas_H2/`: Small-molecule vibration thermochemistry with `thermochemistry.model: ideal_gas`.

### 5. Classic Transition State Search (CO on Pt(111))
*   `04_dimer_CO-Pt/`: **CO on Pt(111)**. A classic benchmark system for the **Dimer** method.

## Usage

1.  **Environment**: Ensure `atst-tools` is installed and you have access to `abacus` or `deepmd-kit`.
2.  **Inputs**: Each example keeps runnable inputs under `inputs/`; generated trajectories and ABACUS scratch directories are ignored.
3.  **Data**: The shared `data/` directory is referenced by relative paths (e.g., `../data`) in `config.yaml`.
4.  **Validate first**:
    ```bash
    atst config validate 06_relax_H2-Au/config.yaml --print-normalized
    atst run --dry-run 06_relax_H2-Au/config.yaml
    ```
5.  **Run**:
    ```bash
    cd 01_neb_Li-Si
    atst run config.yaml
    ```

    To run the DP variant, make sure `temp_repos/dp_model/DPA-3.1-3M.pt` exists
    and deepmd-kit is available, then run:

    ```bash
    atst run config_dp.yaml
    ```

## Suggested Learning Paths

### Local CLI smoke test

This path does not require ABACUS or DP:

```bash
cd examples/09_lightweight_cli
atst neb make inputs/init.xyz inputs/final.xyz 3 -o inputs/init_neb_chain.traj --method linear
atst neb post inputs/neb_result.extxyz --n-max 1 --vib-analysis
atst neb summary inputs/neb_result.extxyz --n-max 1 --tail 5
atst relax post inputs/relax_result.extxyz --output-format traj --output restart.traj
atst relax summary inputs/relax_result.extxyz --tail 5
```

### ABACUS workflow path

```bash
atst config validate examples/01_neb_Li-Si/config.yaml --print-normalized
atst abacus prepare examples/01_neb_Li-Si/config.yaml \
  --structure examples/01_neb_Li-Si/inputs/init_neb_chain.traj \
  --output-dir /tmp/atst-abacus-input
atst run examples/01_neb_Li-Si/config.yaml
atst abacus collect examples/01_neb_Li-Si/run_neb --output abacus_results.json
```

`atst abacus prepare` and `collect` are helper commands. They do not launch
ABACUS or submit Slurm jobs.

### D2S transition-state path

```bash
atst config validate examples/08_d2s_Cy-Pt/config.yaml --print-normalized
atst run examples/08_d2s_Cy-Pt/config.yaml
```

D2S uses the configured calculator backend through `atst run`: rough NEB first,
then Dimer, Sella, or CCQN, with optional vibration follow-up.

## Chemical Systems Summary

| Example Directory | System | Elements | Method |
| :--- | :--- | :--- | :--- |
| `01_neb_Li-Si` | Li diffusion in Si diamond structure | Li, Si | NEB |
| `02_neb_H2-Au` | H2 dissociation on Au(111) | H, Au | NEB |
| `03_autoneb_Cy-Pt` | Cyclohexane dehydrogenation on Pt@Graphene | C, H, Pt | AutoNEB |
| `04_dimer_CO-Pt` | CO oxidation/diffusion on Pt(111) | C, O, Pt | Dimer |
| `05_sella_H2-Au` | H2 dissociation on Au(111) | H, Au | Sella |
| `06_relax_H2-Au` | H2 on Au(111) | H, Au | Relax |
| `07_vibration_H2-Au` | H2 on Au(111) (TS) | H, Au | Vibration |
| `08_d2s_Cy-Pt` | Cyclohexane on Pt@Graphene | C, H, Pt | D2S |
| `09_lightweight_cli` | Minimal local fixtures | H | Lightweight CLI |
| `10_irc_H2` | H2 TS fixture | H | IRC |
| `11_vibration_ideal_gas_H2` | H2 gas molecule | H | Vibration + IdealGasThermo |
| `12_ccqn_H2-Au` | H2 dissociation on Au(111) | H, Au | CCQN |

## Reference Results

Reference values are collected in `reference_results.json`. Transition-state
reference structures are stored as reviewable `.extxyz` files under
`reference_structures/`. The quantitative values below are from the SAI `4V100`
validation using ABACUS LTS 3.10.1 with GPU `ks_solver: cusolver`.

| Example | Reference | TS index | Main-comparable value | Structure |
| :--- | :--- | ---: | :--- | :--- |
| `01_neb_Li-Si` | NEB barrier | 2 | `0.618346` eV (`+0.000019` eV vs main) | `reference_structures/01_neb_Li-Si_ts.extxyz` |
| `02_neb_H2-Au` | NEB barrier | 4 | `1.124752` eV (`+0.003972` eV vs main) | `reference_structures/02_neb_H2-Au_ts.extxyz` |
| `03_autoneb_Cy-Pt` | AutoNEB barrier | 5 | `1.330070` eV (`+0.002184` eV vs main) | `reference_structures/03_autoneb_Cy-Pt_ts.extxyz` |
| `04_dimer_CO-Pt` | Dimer final TS | n/a | final fmax `0.033976` eV/Ang; energy delta `-0.001867` eV vs main | `reference_structures/04_dimer_CO-Pt_final_ts.extxyz` |
| `05_sella_H2-Au` | Sella perturbed TS search | n/a | final fmax `0.035438` eV/Ang; RMSD `0.007952` Ang to reference TS | `reference_structures/05_sella_H2-Au_final_ts.extxyz` |
| `08_d2s_Cy-Pt` | D2S first rough barrier + Sella | 6 | first rough barrier `2.678812` eV (`+0.000017` eV vs main); Sella fmax `0.039662` eV/Ang | `reference_structures/08_d2s_Cy-Pt_rough_ts.extxyz` |
| `12_ccqn_H2-Au` | CCQN perturbed TS search | n/a | matches `05_sella_H2-Au`: energy delta `0.004049` eV, RMSD `0.007682` Ang; RMSD `0.000334` Ang to reference TS | `reference_structures/05_sella_H2-Au_final_ts.extxyz` |

`06_relax_H2-Au`, `07_vibration_H2-Au`, `09_lightweight_cli`,
`10_irc_H2`, and `11_vibration_ideal_gas_H2` do not have like-for-like
main-branch TS/barrier baselines. They remain listed in `reference_results.json`
with validation status or auxiliary output references.
