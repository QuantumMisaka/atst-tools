# NEB/AutoNEB Native ASE Backend Review

**Date**: 2026-05-23  
**Scope**: ordinary NEB and AutoNEB execution for ABACUS-backed examples

## Summary

ATST-Tools does have project-local NEB/AutoNEB implementation layers:

- `AbacusNEB` subclasses ASE `NEB` and overrides `get_forces()`.
- `AbacusAutoNEB` subclasses ASE `AutoNEB` and overrides the internal NEB
  execution path so AutoNEB constructs `AbacusNEB` instead of ASE `NEB`.

These layers are not separate scientific algorithms. They are compatibility
wrappers around ASE. The current validated default remains `neb_backend: atst`.
Native ASE execution is now exposed only as an experimental selector:

```yaml
calculation:
  type: neb        # or autoneb
  neb_backend: ase # default is atst
```

## Why The Local Wrappers Exist

`AbacusNEB` exists because the installed SAI `atst-dev` environment uses
ASE `3.28.0`, whose production `NEB` does not include the development
real-force fix that ATST-Tools needs for constrained-image result persistence.
The local override mirrors ASE `3.28.0` with the development real-force
backport.

`AbacusAutoNEB` exists because ASE `AutoNEB` internally constructs ordinary
ASE `NEB`. ATST-Tools needs to substitute `AbacusNEB`, keep ABACUS calculator
directories deterministic, preserve result freezing, and support project
calculator-sharing policy.

## Relation To Issue #25

Issue #25 was not caused by a wholly independent ATST NEB algorithm. The
reported `fmax` was ASE/FIRE's actual maximum force during AutoNEB
sub-optimization, and the immediate failure mode was optimizer instability
under the reported serial settings.

The refactor did expose wrapper risks that could amplify AutoNEB problems:

- list-valued `fmax` / `maxsteps` schedule semantics;
- AutoNEB `store_E_and_F_in_spc` / `neb.distribute()` result freezing;
- serial ABACUS image directory isolation;
- over-aggressive cleanup of calculator directories.

Those risks have been fixed and tested. The final main-like `03_autoneb_Cy-Pt`
validation job `433962` completed and reproduced the main branch barrier within
`0.002184` eV.

## Native ASE Feasibility

Directly calling ASE native `NEB` and `AutoNEB` with ABACUS calculators is
feasible in principle. The ABACUS interface is an ASE calculator through
abacuslite, so ASE optimizers can drive it.

The risk is not calculator construction itself. The risks are behavioral:

- native ASE `NEB` in ASE `3.28.0` lacks the local real-force backport;
- native ASE `AutoNEB` constructs native `NEB`, so it bypasses the
  `AbacusNEB` compatibility path;
- native ASE `AutoNEB` does not know ATST's ABACUS image directory policy;
- DP shared-calculator behavior is more fragile under native AutoNEB because
  ASE's internal NEB construction does not receive ATST's
  `allow_shared_calculator` policy. ATST-Tools therefore disables calculator
  sharing for native AutoNEB even when the DP calculator would normally share;
- interpolation/result details may differ from the currently validated wrapper.

Therefore native ASE support is implemented as an experimental backend selector,
not as a default replacement.

## Acceptance Path Before Default Migration

Do not make `neb_backend: ase` the default until it has passed:

1. Unit tests for schema, backend selection, and ABACUS image-directory mapping.
2. `01_neb_Li-Si` native ASE SAI run compared against
   `examples/reference_results.json`.
3. `03_autoneb_Cy-Pt` native ASE SAI run compared against
   `examples/reference_results.json`.
4. A constrained-image trajectory check proving native ASE output preserves the
   force data needed by ATST post-processing, or an ASE version bump that
   includes the upstream real-force fix.
