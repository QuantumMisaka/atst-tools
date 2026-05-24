  # Examples Reference Results and Native ASE Backend Experiment Plan

  ## Summary

  Add stable reference outputs for all examples using examples/README.md plus a machine-readable examples/
  reference_results.json. For TS/barrier examples, include barrier or final TS energy, TS index where applicable,
  TS fmax, structure RMSD to main, Slurm validation job, and a reference TS/final-structure artifact. For non-TS
  examples, explicitly mark that no like-for-like TS/barrier baseline exists and record the available validation
  level.

  Current NEB/AutoNEB is not a naked ASE call: AbacusNEB subclasses ASE NEB and backports a real-force fix;
  AbacusAutoNEB subclasses ASE AutoNEB and substitutes AbacusNEB internally while preserving ASE scheduling/result-
  freezing. Issue #25 was partly exposed by wrapper risks that have now been fixed, but the direct symptom was FIRE
  sub-optimization instability under the reported serial settings. Direct native ASE use is feasible as an
  experimental backend, not as an immediate default replacement.

  ## Key Changes

  - Add examples/reference_results.json with one entry per example:
      - 01/02/03/08: barrier, TS index, TS fmax, band fmax where available, validation job, ABACUS version, solver,
        reference structure file.
      - 04/05: final TS energy, final fmax, RMSD to main final TS, validation job, reference structure file.
      - 06/07/10/11: no barrier/TS baseline; record config/schema validation or relevant non-TS output references.
      - 09: mark as local CLI fixture, not ABACUS validation.
  - Add curated text structure files under examples/reference_structures/, using .extxyz so they are reviewable and
    not blocked by the global *.traj ignore rule.
  - Add calculation.neb_backend: "atst" | "ase" to NEBCalculation and AutoNEBCalculation, defaulting to "atst".
  - Implement native ASE experimental behavior:
      - ordinary NEB: choose ASE NEB when neb_backend: ase, otherwise current AbacusNEB;
      - AutoNEB: choose ASE AutoNEB when neb_backend: ase, otherwise current AbacusAutoNEB;
      - keep ABACUS calculator attachment, endpoint single-point handling, optimizer selection, and output
        conventions managed by ATST runners.
  - For native AutoNEB, keep calculator directories deterministic by resolving the global image index through
    object identity in AutoNEBRunner, since ASE native AutoNEB.attach_calculators() receives only image objects,
    not global indices.
  - Document that native ASE backend is experimental and ABACUS-focused in this round; do not make it the default.

  ## Risk Assessment

  - AbacusNEB exists because installed ASE 3.28.0 lacks the development real-force backport used by this project.
    Native ASE NEB may lose unconstrained real_forces behavior needed for reliable trajectory/result inspection.
  - ASE native AutoNEB internally constructs ordinary ASE NEB; it does not expose allow_shared_calculator and does
    not know ATST’s ABACUS directory policy. This is manageable for ABACUS with separate calculators, but risky for
    shared-calculator DP paths.
  - Native AutoNEB interpolation differs from current legacy-compatible wrapper where ATST uses unconstrained
    interpolation. Results may differ, so native backend should be compared, not assumed equivalent.
  - Direct replacement is not recommended until native backend passes unit tests plus at least 01_neb_Li-Si and
    03_autoneb_Cy-Pt SAI regression runs against the existing reference values.

  ## Test Plan

  - Unit tests:
      - schema accepts neb_backend for neb and autoneb, defaults to "atst", rejects unknown values;
      - run_neb() constructs AbacusNEB by default and ASE NEB when neb_backend: ase;
      - AutoNEBRunner constructs AbacusAutoNEB by default and ASE AutoNEB when neb_backend: ase;
      - native AutoNEB calculator attachment maps each image to stable image_### directories;
      - examples/reference_results.json parses as JSON and contains all current example directories.
  - Documentation checks:
      - examples/README.md reference table matches keys in examples/reference_results.json;
      - no placeholder values remain.
  - Runtime acceptance:
      - conda run -n atst-dev pytest tests -q;
      - atst config validate examples/01_neb_Li-Si/config.yaml --print-normalized;
      - optional SAI follow-up for native backend: run 01_neb_Li-Si and 03_autoneb_Cy-Pt with neb_backend: ase,
        compare to the new reference JSON before considering native ASE as a default candidate.

  ## Assumptions

  - “每个案例” means all directories listed in examples/README.md, including non-TS and lightweight examples.
  - Reference values should be versioned in project docs/examples, not only left in temp_* validation directories.
  - Existing AbacusNEB/AbacusAutoNEB remain the default because they are the validated path for ABACUS LTS 3.10.1
    results.
  - Native ASE support is an experimental comparison path, not a behavioral migration in this step.