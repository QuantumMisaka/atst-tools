# ATST-Tools Feature Status Matrix

**Version**: 2.2.3
**Last Updated**: 2026-08-12
**Status**: Maintained
**Owner**: ATST-Tools maintainers

| Feature | Status | Description | Notes |
| :--- | :--- | :--- | :--- |
| **Relax** | ✅ Supported | Geometry Optimization | Uses ASE optimizers. |
| **Vibration** | ✅ Supported | Frequency Analysis and TS validation | Finite difference method with JSON results, TS validation, and artifact manifest support. |
| **NEB** | ✅ Supported | Nudged Elastic Band | CI-NEB, two-stage NEB, endpoint single-point repair, optional endpoint relaxation, native ASE selector, artifact manifest, ABACUS STRU inputs for `atst neb make`, and MPI image-level parallelism are supported. |
| **AutoNEB** | ✅ Supported | Automated NEB | Adaptive image handling, native ASE selector, endpoint single-point repair, and MPI image-level parallelism are supported. |
| **Dimer** | ✅ Supported | TS Search | Min-mode following. |
| **Sella** | ✅ Supported | Saddle Point Finder | Robust optimization. |
| **CCQN** | ✅ Supported | Constrained Cone Quasi-Newton TS Search | Standalone workflow and D2S refinement option, including reactive-mode enumeration, product alignment, diagnostics, mode manifest, and artifact manifest. |
| **D2S** | ✅ Supported | Double-Ended to Single | `atst run` dispatches endpoint optimization, rough DyNEB, then Dimer, Sella, or CCQN refinement. Experimental `rough_method: dmf` can replace rough DyNEB but is not a supported production default. |
| **IRC** | ✅ Supported | Intrinsic Reaction Coordinate | Sella backend and descent backend are supported, with controlled boundary diagnostics and artifact manifests. |
| **MD** | ✅ Supported | Molecular Dynamics | Supports ASE-driven MD with ABACUS/DP calculators and ABACUS-native MD input/run/output orchestration. |
| **DMF** | 🧪 Experimental | Direct MaxFlux TS candidate/path optimizer | Standalone `calculation.type: dmf` and D2S `rough_method: dmf` are available for candidate generation. Outputs are TS candidates, not validated TS results. PBC support is limited to explicit `cartesian_unwrapped` experimental mode. Requires `cyipopt`/IPOPT at runtime. |
| **Artifact Manifests** | ✅ Supported | Workflow output registry | Implemented for NEB, D2S, CCQN, Vibration, IRC, and MD. |
| **API Process Runner** | ✅ Supported | External-host API handoff | `python -m atst_tools.api.runner` writes root-only `atst-api-result-v1` JSON and preserves caller-owned scheduler/MPI launch. |
| **NDJSON Progress Events** | ✅ Supported | Structured progress observability | `RunOptions(progress=True)` / runner `--progress` emit one JSON line per event (`workflow_start`, then one `image_step` per NEB/AutoNEB band image) and forward the same mapping to `progress_callback`. |
| **Plotting Helpers** | ✅ Supported | Energy visualization | Stable `neb_energy_profile`, `sella_energy_curve`, `ccqn_energy_curve` API helpers plus the `python -m atst_tools.utils.plot` CLI adapter; matplotlib is an optional `[plot]` extra. |
| **Result Profiles/Plots Extensions** | ✅ Supported | Opt-in result-envelope fields | `RunOptions(profiles=True)` / `--profiles` and `RunOptions(plots=True)` / `--plots` add optional per-image/per-step summaries and plot PNG paths to `atst-api-result-v1` documents without changing the established fields. |
| **Image-Level MPI Parallelism** | ✅ Supported | ASE NEB/AutoNEB image parallelism | Requires MPI-launched Python and compatible `mpi4py`; ABACUS nested MPI remains site-launcher dependent. |
| **atst prepare** | ✅ Supported | Reverse config generation from an ABACUS run directory | `atst prepare` and `atst_tools.api.build_config_from_abacus_dir` generate runnable transition YAML (currently NEB) from `INPUT`/`STRU`/`KPT`/`PP`/`ORB`. User-controlled ABACUS values are kept verbatim with three technical floors (`calculation`→`scf`, `cal_force`→`1`, KPT line-mode rejected) and an optional endpoint energy+forces gate (`--no-gate` skips it). New in 2.2.3; backward-compatible. |
| **Trajectory Stress Retention** | ✅ Supported | NEB/AutoNEB trajectories carry per-image stress when the ABACUS calculator requests it | `cal_stress=1` retains per-image stress on NEB/AutoNEB trajectories (serial and image-parallel); `cal_stress=0` behavior is identical to 2.2.x. New in 2.2.3; additive. |
| **GA** | ❌ Not Supported | Genetic Algorithm | ASE 3.28.0 moved GA implementation to the standalone `ase-ga` project; ATST-Tools does not expose GA workflows. |
