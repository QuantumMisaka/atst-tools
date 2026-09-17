# ATST-Tools Feature Status Matrix

**Version**: 2.2.6
**Last Updated**: 2026-09-17
**Status**: Published (PyPI clean-install verified)
**Owner**: ATST-Tools maintainers

The 2.2.6 package was published from tag `v2.2.6` at commit
`a633f06b9375e3f34dbd87f90f40ec6271b29cd4`. It records optimizer convergence
facts across workflows, writes owner manifests for Sella/Relax/AutoNEB, and
unifies runtime diagnostics to English. GitHub Tests, abacuslite, PyPI
publication and the official no-cache clean-install verification passed;
SIF/SAI/platform runtime evidence has not been performed. The 2.2.5 release
evidence stays in the 2.2.5 release notes.

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
| **ABACUSLite SCF frame identity** | ✅ Supported | Periodic-aware running-log frame selection | Published in 2.2.5. `calculation: scf` accepts integer lattice translations in the current cell, including valid cross-cell transition-state/NEB movement, and selects the latest matching frame. Different structures and malformed, non-finite, singular, shape, count, cell, element, or order data remain fail-closed. Native `relax`/`md`/`MD_dump` retain last-frame semantics; no new configuration knob. |
| **DMF** | 🧪 Experimental | Direct MaxFlux TS candidate/path optimizer | Standalone `calculation.type: dmf` and D2S `rough_method: dmf` are available for candidate generation. Outputs are TS candidates, not validated TS results. PBC support is limited to explicit `cartesian_unwrapped` experimental mode. Requires `cyipopt`/IPOPT at runtime. |
| **Artifact Manifests** | ✅ Supported | Workflow output registry | Implemented for NEB, D2S, CCQN, Vibration, IRC, MD, AutoNEB, Sella, Relax, and experimental DMF. |
| **Convergence Stage Records** | ✅ Supported | Optimizer-owned convergence facts in manifest stages | Every optimize workflow records a strict tri-state `converged` (`true`/`false`/`null`) plus stage identity (`role`, `criterion`, IRC `direction`, AutoNEB `subset`, thresholds, stage-local steps). `null` is unknown and never inferred from trajectories or raw force maxima; advisories are diagnostic only and never change completion or exit codes. Documented in `docs/user/PYTHON_API_REFERENCE.md`; contract fixtures in `docs/reports/data/convergence_fixtures_20260917/`. New in 2.2.6; additive stage fields. |
| **English Runtime Diagnostics** | ✅ Supported | Program-visible output language | `print`/warning/logging output, exception messages and CLI help are English across the package, enforced by `tests/unit/test_program_output_language.py`; documentation keeps its existing language and the vendored abacuslite snapshot is excluded. New in 2.2.6; the printed diagnostics language is the only user-visible change. |
| **API Process Runner** | ✅ Supported | External-host API handoff | `python -m atst_tools.api.runner` writes root-only `atst-api-result-v1` JSON and preserves caller-owned scheduler/MPI launch. |
| **NDJSON Progress Events** | ✅ Supported | Structured progress observability | `RunOptions(progress=True)` / runner `--progress` emit one JSON line per event (`workflow_start`, then one `image_step` per NEB/AutoNEB band image) and forward the same mapping to `progress_callback`. |
| **Plotting Helpers** | ✅ Supported | Energy visualization | Stable `neb_energy_profile`, `sella_energy_curve`, `ccqn_energy_curve` API helpers plus the `python -m atst_tools.utils.plot` CLI adapter; matplotlib is an optional `[plot]` extra. |
| **Result Profiles/Plots Extensions** | ✅ Supported | Opt-in result-envelope fields | `RunOptions(profiles=True)` / `--profiles` and `RunOptions(plots=True)` / `--plots` add optional per-image/per-step summaries and plot PNG paths to `atst-api-result-v1` documents without changing the established fields. |
| **Image-Level MPI Parallelism** | ✅ Supported | ASE NEB/AutoNEB image parallelism | Requires MPI-launched Python and compatible `mpi4py`; ABACUS nested MPI remains site-launcher dependent. |
| **Portable MPI Diagnostics** | ✅ Supported | Recovery guidance for missing `mpi4py` in image-parallel launches | Names the explicit `parallel` extra and site-compatible `MPICC` source rebuild; does not promise arbitrary MPI ABI compatibility. New in 2.2.4; additive diagnostic/documentation change. |
| **atst prepare** | ✅ Supported | Reverse config generation from an ABACUS run directory | `atst prepare` and `atst_tools.api.build_config_from_abacus_dir` generate runnable transition YAML (currently NEB) from `INPUT`/`STRU`/`KPT`/`PP`/`ORB`. User-controlled ABACUS values are kept verbatim with three technical floors (`calculation`→`scf`, `cal_force`→`1`, KPT line-mode rejected) and an optional endpoint energy+forces gate (`--no-gate` skips it). New in 2.2.3; backward-compatible. |
| **Trajectory Stress Retention** | ✅ Supported | NEB/AutoNEB trajectories carry per-image stress when the ABACUS calculator requests it | `cal_stress=1` retains per-image stress on NEB/AutoNEB trajectories (serial and image-parallel); `cal_stress=0` behavior is identical to 2.2.x. New in 2.2.3; additive. |
| **GA** | ❌ Not Supported | Genetic Algorithm | ASE 3.28.0 moved GA implementation to the standalone `ase-ga` project; ATST-Tools does not expose GA workflows. |
