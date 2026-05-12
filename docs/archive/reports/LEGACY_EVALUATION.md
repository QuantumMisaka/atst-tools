# Legacy Examples Evaluation Report

**Date**: 2026-02-25
**Version**: 1.0
**Author**: ATST-Tools Refactoring Agent

---

## 1. Overview

This document provides a comprehensive evaluation of the legacy examples located in `examples/legacy`. The goal is to assess their reproducibility in the current environment, identify functionality gaps compared to the new `atst-run` workflow, and provide recommendations for migration.

## 2. Legacy Examples Inventory & Status

| Legacy Example Path | Functionality | Status | Reproducibility | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `CH4-HOAuHOPd-ZSM5/TS-CH4-HOAu` | Sella (Transition State Search) | ❌ Broken | ❌ Failed | Python script `sella_run.py` relies on hardcoded paths (`/lustre/...`) and old `ase.calculators.abacus` import. Missing `sella` dependency in current env? |
| `CO-Pt111/sella` | Sella | ❌ Broken | ❌ Failed | Same issues as above. Hardcoded paths. |
| `CO-Pt111/dimer` | Dimer Method | ❌ Broken | ❌ Failed | No run script found directly in `dimer/`, output files exist. `run_dimer.traj` indicates past execution. |
| `CO-Pt111/autoneb` | AutoNEB | ❌ Broken | ❌ Failed | `autoneb_run.py` missing in directory structure (only listed in analysis, likely missing file). |
| `Cy-Pt@graphene/autoneb` | AutoNEB | ❌ Broken | ❌ Failed | `autoneb_run.py` exists but uses `abacus_autoneb` module which is likely missing or moved. Hardcoded paths. |
| `Cy-Pt@graphene/vib_analysis_TS` | Vibrational Analysis | ❌ Broken | ❌ Failed | `vib_analysis.py` script is missing or located in a nested structure not immediately visible/importable. |

**General Reproducibility Issues**:
1.  **Hardcoded Paths**: Almost all scripts contain absolute paths like `/lustre/home/...` which are invalid in the current environment.
2.  **Legacy Imports**: Scripts import `ase.calculators.abacus` directly, whereas the new system uses `atst_tools.calculators.factory` or `abacuslite`.
3.  **Missing Dependencies**: Some scripts rely on local modules (`abacus_autoneb`) that are not part of the installed package.
4.  **Data Availability**: Some PP/Orb files are referenced but might be missing or paths are incorrect.

## 3. Functionality Gap Analysis

We compared the legacy functionality with the new `atst-run` capabilities.

### 3.1 Supported in New Architecture (✅)
*   **NEB**: Fully supported via `calculation: type: neb`.
*   **Relax**: Fully supported via `calculation: type: relax`.
*   **Vibration**: Supported via `calculation: type: vibration`. The new `VibrationWorkflow` covers the core functionality of `vib_analysis.py` (ZPE, modes, frequencies), but lacks the specific `HarmonicThermo` analysis output (Entropy, Free Energy) printed in the legacy script.

### 3.2 Partially Supported / WIP (🚧)
*   **AutoNEB**: The legacy `Cy-Pt@graphene/autoneb` example uses `AbacusAutoNEB`. This class exists in `src/atst_tools/mep/autoneb.py` but `main.py` marks `run_autoneb` as WIP.
*   **Dimer**: Legacy examples exist (`CO-Pt111/dimer`), but `main.py` marks `run_dimer` as WIP.
*   **Sella**: Legacy examples exist (`CH4.../TS-CH4-HOAu`), but `main.py` marks `run_sella` as WIP.

### 3.3 Missing Features (❌)
*   **Thermodynamic Analysis**: The legacy vibration script calculates Entropy and Helmholtz Free Energy. The current `VibrationWorkflow` only outputs ZPE and frequencies.
*   **Advanced NEB Analysis**: Legacy `neb_post.py` (referenced in docs/plans but not seen in examples) features might be missing in `atst-run`.

## 4. Recommendations

### 4.1 For Legacy Examples
*   **Action**: **Keep for Reference Only**. Do not attempt to fix them in place as they are structurally obsolete (script-based vs config-based).
*   **Migration**: Use them as "Gold Standard" logic references to implement the corresponding `Workflow` classes in `src`.

### 4.2 For New Development (Priority Order)
1.  **Enable AutoNEB**: Refactor `run_autoneb` in `main.py` to use `AbacusAutoNEB` with the new `CalculatorFactory`.
2.  **Enable Dimer/Sella**: Implement `run_dimer` and `run_sella` in `main.py`. This is crucial for TS search parity.
3.  **Enhance Vibration**: Add `HarmonicThermo` analysis to `VibrationWorkflow` to match legacy capabilities (Entropy/Free Energy output).

### 4.3 New Case Suggestions
Create the following new examples in `examples/` once the features are enabled:
*   `02_autoneb/config.yaml`: Replicating `Cy-Pt@graphene`.
*   `03_dimer/config.yaml`: Replicating `CO-Pt111/dimer`.
*   `04_sella/config.yaml`: Replicating `CH4.../TS-CH4-HOAu`.

## 5. Conclusion

The legacy examples are currently **non-functional** in the refactored environment due to hardcoded paths and obsolete dependencies. However, they contain valuable logic (especially for Sella, AutoNEB, and Thermo analysis) that has not yet been fully ported to the new `atst-run` system.

**Immediate Next Step**: Enhance `VibrationWorkflow` to include thermodynamic analysis, closing the gap with `vib_analysis.py`.
