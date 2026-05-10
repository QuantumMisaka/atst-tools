# Machine-Learning Calculator Implementation Plan

**Status**: Planned after ABACUS 2.0.0 acceptance  
**Primary baseline**: `main` branch `ase-dp/*.py` scripts  
**Target interface**: `atst run config.yaml`

## Background

The `main` branch already contains DeePMD-oriented scripts under `ase-dp/`:

- `relax_dp.py`
- `autoneb_dp.py`
- `autoneb_dpa2.py`
- `dimer_dpa2.py`
- `neb2dimer_dp.py`
- `neb2sella_dp.py`
- `sella_dp_run.py`
- `sella_dp_IRC.py`
- `vib_dp.py`
- `idealgas_dp.py`

Those scripts directly instantiate `deepmd.calculator.DP` or a DP-compatible
ASE calculator, set `OMP_NUM_THREADS`, and then run ASE optimizers, AutoNEB,
Dimer, Sella, or vibration analysis. The refactored project should preserve
those capabilities through the same workflow classes used by ABACUS, not by
reintroducing method-specific scripts.

## Design Principles

1. ABACUS remains the first release-blocking calculator.
2. Machine-learning potentials must use the same `calculation` YAML schema as
   ABACUS workflows.
3. Calculator-specific settings live only under `calculator.<engine>`.
4. The first ML calculator target is DeePMD-kit `DP`; other ASE ML calculators
   can be added through the same adapter contract later.
5. Expensive calculator objects may be shared only when ASE permits shared
   calculators for that workflow.

## Target YAML

```yaml
calculation:
  type: neb
  init_chain: init_neb_chain.traj
  fmax: 0.05
  max_steps: 200
  parallel: false

calculator:
  name: dp
  dp:
    model: /path/to/frozen_model.pb
    type_map: [H, C, O, Pt]
    omp: 4
    share_calculator: true
```

Required fields:

- `calculator.name: dp`
- `calculator.dp.model`

Optional fields:

- `type_map`: forwarded to `deepmd.calculator.DP`
- `omp`: sets `OMP_NUM_THREADS` before calculator construction
- `share_calculator`: enables reuse for workflows where ASE allows shared
  calculators, matching the intent of the main-branch scripts to avoid repeated
  model loading

## Implementation Tasks

1. Split the DP adapter out of `factory.py` into `src/atst_tools/calculators/dp.py`.
2. Preserve the current factory behavior:
   - import `deepmd.calculator.DP` lazily;
   - raise a clear installation error when deepmd-kit is unavailable;
   - cache calculators by absolute model path when sharing is enabled.
3. Extend DP parameters:
   - `type_map`;
   - `omp`;
   - `share_calculator`;
   - future `backend` selector if `deepmd_pt.utils.ase_calc.DPCalculator` must
     be supported for a specific model family.
4. Audit workflow sharing:
   - NEB/D2S can share calculators only when ASE accepts
     `allow_shared_calculator=True`;
   - ABACUS must keep per-image directories and must not share calculators;
   - Dimer, Sella, Relax, and Vibration can construct one calculator per active
     structure.
5. Convert the existing `examples/*/config_dp.yaml` files from absolute local
   model paths to documented placeholders or a small test fixture path outside
   git-tracked heavy assets.
6. Add unit tests for:
   - DP config validation;
   - lazy import error;
   - `type_map`, `omp`, and `share_calculator` handling;
   - factory cache identity and cache bypass.
7. Add integration validation on SAI after ABACUS acceptance:
   - use the `atst-dev` environment with deepmd-kit installed;
   - run `relax`, `neb`, `dimer`, `sella`, `vibration`, and `d2s` smoke cases;
   - record the results in the acceptance report.

## Migration Mapping From `main`

| Main script | Refactored target |
| :--- | :--- |
| `ase-dp/relax_dp.py` | `calculation.type: relax`, `calculator.name: dp` |
| `ase-dp/autoneb_dp.py`, `ase-dp/autoneb_dpa2.py` | `calculation.type: autoneb`, `calculator.name: dp` |
| `ase-dp/dimer_dpa2.py` | `calculation.type: dimer`, `calculator.name: dp` |
| `ase-dp/neb2dimer_dp.py` | `calculation.type: d2s`, `method: dimer`, `calculator.name: dp` |
| `ase-dp/neb2sella_dp.py` | `calculation.type: d2s`, `method: sella`, `calculator.name: dp` |
| `ase-dp/sella_dp_run.py` | `calculation.type: sella`, `calculator.name: dp` |
| `ase-dp/vib_dp.py` | `calculation.type: vibration`, `calculator.name: dp` |
| `ase-dp/idealgas_dp.py` | Out of transition-state scope unless a thermochemistry workflow is added |

## Acceptance Criteria

- `atst run --dry-run examples/*/config_dp.yaml` passes for all DP examples.
- Unit tests cover the DP adapter without requiring deepmd-kit.
- At least one DP smoke case runs on SAI before DP support is marked complete.
- Documentation states clearly that ABACUS is the primary backend for 2.0.0 and
  DP is supported after its own validation stage.
