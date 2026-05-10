# ATST-Tools Examples

This directory contains standardized examples for using `atst-tools` with ABACUS and Deep Potential (DP).
The examples are organized by chemical system and method to demonstrate the versatility of the toolkit.

## Directory Structure

*   `data/`: Centralized repository for Pseudopotentials (`.upf`) and Numerical Orbitals (`.orb`).
*   `<case>/inputs/`: Curated input structures and vectors referenced by `config*.yaml`.

### 1. Basic Examples (Li Diffusion)
*   `01_neb_Li-Si/`: **Li diffusion in Si**. A simple, fast-running NEB example suitable for quick testing and getting started.

### 2. Surface Reactions (H2 on Au(111))
*   `02_neb_H2-Au/`: **H2 dissociation on Au(111)**. Demonstrate NEB on a metal surface.
*   `05_sella_H2-Au/`: Sella method for the same system.
*   `06_relax_H2-Au/`: Geometry optimization of the initial state.
*   `07_vibration_H2-Au/`: Vibrational analysis of the Transition State.

### 3. Advanced Workflows (Cyclohexane on Pt@Graphene)
*   `03_autoneb_Cy-Pt/`: **Cyclohexane on Pt-doped Graphene**. Demonstrates the **AutoNEB** workflow for complex paths.
*   `08_d2s_Cy-Pt/`: **Double-to-Single (D2S)** workflow, combining rough NEB with precise Sella/Dimer search.

### 4. Classic Transition State Search (CO on Pt(111))
*   `04_dimer_CO-Pt/`: **CO on Pt(111)**. A classic benchmark system for the **Dimer** method.

## Usage

1.  **Environment**: Ensure `atst-tools` is installed and you have access to `abacus` or `deepmd-kit`.
2.  **Inputs**: Each example keeps runnable inputs under `inputs/`; generated trajectories and ABACUS scratch directories are ignored.
3.  **Data**: The shared `data/` directory is referenced by relative paths (e.g., `../data`) in `config.yaml`.
4.  **Run**:
    ```bash
    cd 01_neb_Li-Si
    atst-run config.yaml
    ```

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
