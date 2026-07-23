# ATST-Tools Examples

This directory contains standardized examples for using `atst-tools` with ABACUS and Deep Potential (DP).
The examples are organized by chemical system and method to demonstrate the versatility of the toolkit.

## Directory Structure

*   `data/`: Centralized repository for Pseudopotentials (`.upf`) and Numerical Orbitals (`.orb`).
*   `<case>/inputs/`: Curated input structures and vectors referenced by `config*.yaml`.
*   `<case>/outputs/`: Curated completed-run outputs when an example is meant to be inspected without rerunning an expensive calculation.
*   `config.yaml`: ABACUS-backed example configuration.
*   `config_dp.yaml`: DP-backed example configuration when available. These use `../../temp_repos/dp_model/DPA-3.1-3M.pt` with `head: Omat24` for local runs; the model file is intentionally outside git.
*   Generated outputs such as `run_*`, `OUT.ABACUS`, `AutoNEB_iter`, `vib`, `vib_calc`, `*.traj`, `*.json`, and ABACUS/DP scratch files are ignored unless they are explicitly curated inputs or completed-run outputs.

### 1. Basic Examples (Li Diffusion)
*   `01_neb_Li-Si/`: **Li diffusion in Si**. A simple, fast-running NEB example suitable for getting started; the main NEB configs use bounded two-stage CI-NEB warm-up.

### 2. Surface Reactions (H2 on Au(111))
*   `02_neb_H2-Au/`: **H2 dissociation on Au(111)**. Demonstrates NEB on a metal surface; the main configs use two-stage CI-NEB, and `config_two_stage*.yaml` are short curated configurations.
*   `05_sella_H2-Au/`: Sella method for the same system.
*   `06_relax_H2-Au/`: Geometry optimization of the initial state.
*   `07_vibration_H2-Au/`: Vibrational analysis of the Transition State.
*   `12_ccqn_H2-Au/`: CCQN single-ended transition-state search for the same H2/Au system, including reactive-mode enumeration examples in `config_auto_modes*.yaml` and the embedded API companion `ccqn_api_auto_modes.py`.

### 3. Advanced Workflows (Cyclohexane on Pt@Graphene)
*   `03_autoneb_Cy-Pt/`: **Cyclohexane on Pt-doped Graphene**. Demonstrates the **AutoNEB** workflow for complex paths.
*   `08_d2s_Cy-Pt/`: **Double-to-Single (D2S)** workflow, combining rough NEB with precise Sella/Dimer/CCQN search.

### 4. Lightweight Commands and Auxiliary Workflows
*   `09_lightweight_cli/`: Local pre/post-processing examples for `atst neb`, summary commands, `atst dimer`, `atst relax post`, and `atst vibration post`.
*   `10_irc_H2/`: IRC YAML examples for `direction: both`, `forward`, `reverse`, and descent-mode IRC via `config_descent*.yaml` plus `inputs/descent_mode.npy`.
*   `11_vibration_ideal_gas_H2/`: Small-molecule vibration thermochemistry with `thermochemistry.model: ideal_gas`.
*   `15_md_Li-Si/`: Molecular dynamics templates for ASE-driven DP/ABACUS and ABACUS-native MD using the `01_neb_Li-Si` initial structure.
*   `16_dmf_nonperiodic/`: Experimental non-periodic Direct MaxFlux configuration. DMF writes a TS candidate only and requires follow-up validation.
*   `17_dmf_pbc_cartesian_unwrapped/`: Experimental fixed-cell PBC DMF guard example using `cartesian_unwrapped`; this is not production PBC validation.
*   `18_dmf_production_validation/`: Staged experimental DMF candidate-comparison configurations for Li-Si and H2-Au references.

### 5. Classic Transition State Search (CO on Pt(111))
*   `04_dimer_CO-Pt/`: **CO on Pt(111)**. A classic benchmark system for the **Dimer** method.

## Usage

1.  **Environment**: Ensure `atst-tools` is installed with Python 3.10 or newer, and that you have access to `abacus` or the optional calculator stack needed by the example.
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

    To run the DP variant, install `atst-tools[dp]` or provide an equivalent
    DeePMD-kit environment. From the repository root, fetch the pinned
    DPA-3.1-3M model first:

    ```bash
    python scripts/download_dp_model.py
    python scripts/download_dp_model.py --check-only
    ```

    Then run:

    ```bash
    atst run config_dp.yaml
    ```

## Suggested Learning Paths

### Local CLI learning path

This path does not require ABACUS or DP:

```bash
cd examples/09_lightweight_cli
atst neb make inputs/init.xyz inputs/final.xyz 3 -o inputs/init_neb_chain.traj --method linear
atst neb post inputs/neb_result.extxyz --n-max 1 --vib-analysis
atst neb post inputs/neb_result.extxyz --n-max 1 --plot --plot-label neb_energy_profile --energy-profile
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
ABACUS calculations.

### D2S transition-state path

```bash
atst config validate examples/08_d2s_Cy-Pt/config.yaml --print-normalized
atst run examples/08_d2s_Cy-Pt/config.yaml
```

D2S uses the configured calculator backend through `atst run`: rough NEB first,
then Dimer, Sella, or CCQN, with optional vibration follow-up.

### Experimental DMF candidate path

```bash
atst config validate examples/16_dmf_nonperiodic/config_dp.yaml --print-normalized
atst run --dry-run examples/16_dmf_nonperiodic/config_dp.yaml
```

`calculation.type: dmf` is experimental. It uses vendored PyDMF through the
ATST-Tools namespace, but still requires `cyipopt` and IPOPT at runtime. The
written `dmf_tmax.traj` is a TS candidate, not a validated TS. Periodic inputs
are rejected unless the experimental `pbc_mode: cartesian_unwrapped` risk
acknowledgement is set with fixed-cell, pre-unwrapped Cartesian endpoints.
`nmove` controls the final DMF evaluation grid, so a default standalone run
writes `nmove + 2` path images and records the final `t_eval` grid in
`dmf_summary.json`.

For the P2 PBC guard path:

```bash
atst config validate examples/17_dmf_pbc_cartesian_unwrapped/config_dp.yaml --print-normalized
atst run --dry-run examples/17_dmf_pbc_cartesian_unwrapped/config_dp.yaml
```

The PBC example requires `initial_path: linear`, identical endpoint cells/PBC
flags, `confirm_pbc_risk: true`, and `remove_rotation_and_translation: false`.
It is a configuration guard, not production evidence for periodic DMF.

`12_ccqn_H2-Au/ccqn_api_auto_modes.py` is the ATST-specific Python API
companion to `config_auto_modes.yaml`. It uses a lightweight ASE EMT fixture
and the repository-committed ASE-native `inputs/ccqn_init.extxyz`; it is not an
ABACUS production input. For a production calculator, create and configure the
calculator in the calling application, then pass it to `run_ccqn()` as defined
in the [Python API reference](../docs/user/PYTHON_API_REFERENCE.md). Production
ABACUS CCQN injection requires a caller-created, correctly configured
`abacuslite` ASE calculator plus the normal ABACUS pseudopotential, orbital,
executable/runtime, and site setup. ATST does not configure that calculator;
ATST-Tools does not install or require ABACUS as a package dependency.

For image-level MPI configuration and the maintained execution records, see the
[example validation operations guide](../docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md).

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
| `13_neb_parallel_Cy-Pt` | Cyclohexane dehydrogenation on Pt@Graphene | C, H, Pt | NEB image-parallel |
| `14_autoneb_parallel_Cy-Pt` | Cyclohexane dehydrogenation on Pt@Graphene | C, H, Pt | AutoNEB image-parallel |
| `15_md_Li-Si` | Li in Si diamond structure from `01_neb_Li-Si` | Li, Si | MD |
| `16_dmf_nonperiodic` | H2 non-periodic endpoint pair | H | DMF |
| `17_dmf_pbc_cartesian_unwrapped` | H2 fixed-cell toy endpoint pair | H | DMF PBC guard |
| `18_dmf_production_validation` | Li-Si and H2-Au staged P3 validation cases | Li, Si, H, Au | DMF validation |

## Reference Results

Reference values are collected in `reference_results.json`. Transition-state
reference structures are stored as reviewable `.extxyz` files under
`reference_structures/`. Their execution provenance and maintenance procedure
are documented in the
[example validation operations guide](../docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md).

DP-backed references are collected separately in `dp_reference_results.json`,
with curated structures under `dp_reference_structures/`. The pinned model
identity is recorded in `dp_model_manifest.json`; obtain the model as described
in the usage section before running a DP configuration.

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

| DP Example | Status | Main DP value | ABACUS comparison |
| :--- | :--- | :--- | :--- |
| `01_neb_Li-Si` | green | barrier `0.723182` eV, projected fmax `0.049976` eV/Ang | `+0.104836` eV; TS RMSD `0.002821` Ang |
| `02_neb_H2-Au` | yellow | barrier `0.647409` eV, projected fmax `0.069072` eV/Ang | `-0.477343` eV; TS RMSD `0.055256` Ang |
| `03_autoneb_Cy-Pt` | yellow | barrier `1.339684` eV, projected fmax `3.816353` eV/Ang | `+0.009614` eV; TS RMSD `0.100587` Ang |
| `04_dimer_CO-Pt` | green | final fmax `0.045176` eV/Ang | TS RMSD `0.033274` Ang |
| `05_sella_H2-Au` | green | final fmax `0.049454` eV/Ang | TS RMSD `0.052622` Ang |
| `06_relax_H2-Au` | green | final fmax `0.049054` eV/Ang | non-TS workflow |
| `07_vibration_H2-Au` | green | 205 valid cache files, ZPE `0.699170` eV | post-processing workflow |
| `08_d2s_Cy-Pt` | yellow | rough barrier `1.929739` eV, dimer fmax `0.052908` eV/Ang | rough barrier `-0.749073` eV; rough TS RMSD `0.150699` Ang |
| `10_irc_H2` | green | 5 IRC frames, final fmax `0.004265` eV/Ang | gas-phase auxiliary workflow |
| `11_vibration_ideal_gas_H2` | yellow | ideal-gas Gibbs free energy `-0.032443` eV | minimal H2 fixture with 5 filtered modes |
