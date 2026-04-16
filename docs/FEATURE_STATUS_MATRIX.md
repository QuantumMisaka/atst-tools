# ATST-Tools Feature Status Matrix

**Version**: 2.0.0-rc  
**Last Updated**: 2026-03-04

| Feature | Status | Description | Notes |
| :--- | :--- | :--- | :--- |
| **Relax** | ✅ Supported | Geometry Optimization | Uses ASE optimizers. |
| **Vibration** | ✅ Supported | Frequency Analysis | Finite difference method. |
| **NEB** | ✅ Supported | Nudged Elastic Band | CI-NEB supported. |
| **AutoNEB** | ✅ Supported | Automated NEB | Adaptive image handling. |
| **Dimer** | ✅ Supported | TS Search | Min-mode following. |
| **Sella** | ✅ Supported | Saddle Point Finder | Robust optimization. |
| **D2S** | ⚠️ Pending | Double-Ended to Single | Code exists but unlinked in CLI. |
| **MD** | ❌ Not Supported | Molecular Dynamics | Not implemented in `atst-run`. |