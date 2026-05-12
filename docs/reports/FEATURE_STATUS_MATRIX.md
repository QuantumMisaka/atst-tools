# ATST-Tools Feature Status Matrix

**Version**: 2.0.0
**Last Updated**: 2026-05-12

| Feature | Status | Description | Notes |
| :--- | :--- | :--- | :--- |
| **Relax** | ✅ Supported | Geometry Optimization | Uses ASE optimizers. |
| **Vibration** | ✅ Supported | Frequency Analysis | Finite difference method. |
| **NEB** | ✅ Supported | Nudged Elastic Band | CI-NEB supported. |
| **AutoNEB** | ✅ Supported | Automated NEB | Adaptive image handling. |
| **Dimer** | ✅ Supported | TS Search | Min-mode following. |
| **Sella** | ✅ Supported | Saddle Point Finder | Robust optimization. |
| **D2S** | ✅ Supported | Double-Ended to Single | `atst run` dispatches rough DyNEB followed by Dimer or Sella. |
| **IRC** | ✅ Supported | Intrinsic Reaction Coordinate | Sella-backed application mode with controlled boundary diagnostics. |
| **MD** | ❌ Not Supported | Molecular Dynamics | Not implemented in `atst run`. |
