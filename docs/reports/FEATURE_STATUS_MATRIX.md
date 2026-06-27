# ATST-Tools Feature Status Matrix

**Version**: 2.1.3
**Last Updated**: 2026-06-27
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
| **D2S** | ✅ Supported | Double-Ended to Single | `atst run` dispatches endpoint optimization, rough DyNEB, then Dimer, Sella, or CCQN refinement. |
| **IRC** | ✅ Supported | Intrinsic Reaction Coordinate | Sella backend and descent backend are supported, with controlled boundary diagnostics and artifact manifests. |
| **MD** | ✅ Supported | Molecular Dynamics | Supports ASE-driven MD with ABACUS/DP calculators and ABACUS-native MD input/run/output orchestration. |
| **Artifact Manifests** | ✅ Supported | Workflow output registry | Implemented for NEB, D2S, CCQN, Vibration, IRC, and MD. |
| **Image-Level MPI Parallelism** | ✅ Supported | ASE NEB/AutoNEB image parallelism | Requires MPI-launched Python and compatible `mpi4py`; ABACUS nested MPI remains site-launcher dependent. |
| **GA** | ❌ Not Supported | Genetic Algorithm | ASE 3.28.0 moved GA implementation to the standalone `ase-ga` project; ATST-Tools does not expose GA workflows. |
