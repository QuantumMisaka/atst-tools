# ATST-Tools Refactor Stage Review

**Version**: 2.0.0
**Date**: 2026-05-15
**Status**: Maintained review
**Owner**: ATST-Tools maintainers

This report records the May 2026 review of the `refactor/unify-structure`
branch. It focuses on project status, documentation governance, improvements
relative to `main`, workflow input/output changes, and development work that
should be considered after the 2.0.0 refactor stage.

## 1. Current Project Status

The project is on branch `refactor/unify-structure` and has reached the 2.0.0
package refactor state. The repository now exposes a formal Python package under
`src/atst_tools`, an installable console command, governed examples, and a
structured documentation tree.

Current supported workflow surface:

| Workflow | Current status | Entry point |
| :--- | :--- | :--- |
| NEB / DyNEB | Supported | `atst run CONFIG.yaml` |
| AutoNEB | Supported | `atst run CONFIG.yaml` |
| Dimer | Supported | `atst run CONFIG.yaml` |
| Sella | Supported | `atst run CONFIG.yaml` |
| D2S | Supported | `atst run CONFIG.yaml` |
| Relax | Supported | `atst run CONFIG.yaml` |
| Vibration | Supported | `atst run CONFIG.yaml` |
| IRC | Supported with controlled Sella boundary diagnostics | `atst run CONFIG.yaml` |
| MD | Not implemented in `atst run` | Future extension |

The calculator boundary is also clearer than in `main`:

- ABACUS uses `abacuslite`; installed `abacuslite` is preferred and the vendored
  snapshot is a fallback for 2.0.0 reproducibility.
- DeePMD-kit uses `deepmd.calculator.DP`; model backend selection is delegated to
  DeePMD-kit, while ATST-Tools governs `model`, `head`, `type_map` or
  `type_dict`, `omp`, and `share_calculator`.
- ABACUS INPUT parameters remain pass-through under `calculator.abacus.parameters`.

Verification evidence available in the repository includes unit tests, example
YAML validation, SAI ABACUS evidence, and DP/DPA smoke validation. The review
reran the unit test suite in `atst-dev` during this governance pass.

## 2. Documentation Governance Review

The documentation tree is mostly converged, but the previous governance pass
left several temporary or transitional report files in active locations. The
active documentation set should not link to archived reports, and long-term
developer documentation should describe the current tree rather than past
working directories.

### Active Documents to Keep

| File | Reason |
| :--- | :--- |
| `docs/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | Current stage review and next-development baseline. |
| `docs/reports/DOCUMENTATION_STATUS_REPORT.md` | Single documentation governance status entry. |
| `docs/reports/FEATURE_STATUS_MATRIX.md` | Compact current feature support matrix. |
| `docs/reports/DP_VALIDATION_2.0.0.md` | 2.0.0 DP/DPA validation evidence. |
| `docs/reports/IRC_INTEGRATION_REVIEW.md` | Current IRC integration boundary and behavior. |
| `docs/developer/YAML_INPUT_GOVERNANCE.md` | Current schema and YAML variable governance rules. |
| `docs/developer/DOCS_ARCHITECTURE.md` | Current documentation tree responsibilities. |
| `docs/developer/DOCUMENTATION_STANDARDS.md` | Long-term documentation maintenance rules. |
| `docs/developer/HANDOVER.md` | Maintenance responsibility handoff. |

### Documents to Archive

| File | Archive reason |
| :--- | :--- |
| `Calculator_Review.md` | Calculator findings are now absorbed by user references, DP validation, and this review. |
| `YAML_CONFIGURATION_REVIEW.md` | YAML findings are now absorbed by YAML governance, config references, and this review. |

Both files are useful historical evidence, but they no longer need to be active
navigation targets.

## 3. Refactor Improvements Relative to `main`

The refactor materially improves both developer maintenance and user experience.

For users:

- The primary workflow interface changes from editing many task-specific Python
  scripts to running `atst run CONFIG.yaml`.
- The same top-level YAML shape is used across NEB, AutoNEB, Dimer, Sella, D2S,
  Relax, Vibration, and IRC.
- Example cases are numbered and curated as `examples/<case>/config.yaml`,
  optional `config_dp.yaml`, and `inputs/`.
- Lightweight local operations are exposed through commands such as `atst neb
  make`, `atst neb post`, `atst dimer make-from-neb`, `atst relax post`,
  `atst vibration post`, and `atst traj transform`.
- `--dry-run`, `--list-types`, and `--show-template` make the CLI easier to
  inspect before launching expensive SAI jobs.

For developers:

- Package code is grouped by responsibility under `calculators`, `mep`,
  `workflows`, `scripts`, and `utils`.
- YAML variables are governed by Pydantic schema models and normalized before
  workflow dispatch.
- Generated YAML variable documentation reduces drift between code and docs.
- Calculator construction is centralized in `CalculatorFactory`.
- Unit tests cover schema validation, examples, factories, restart helpers,
  endpoint governance, CLI dispatch, and workflow behavior.
- Runtime outputs and scratch directories are excluded by `.gitignore`, while
  curated examples and fixtures remain versioned.

These changes align with the refactor requirements: formal package structure,
CLI plus YAML interaction, reusable examples, ABACUS backend migration to
`abacuslite`, DP calculator support, and more maintainable workflow modules.

## 4. Workflow Input and Output Differences

The refactor intentionally preserves the most important ASE trajectory concepts
from `main`, but changes how inputs are provided and how some outputs are
accepted as stable artifacts.

| Workflow | `main` pattern | Refactored pattern | Output difference |
| :--- | :--- | :--- | :--- |
| NEB | `neb_make.py`, `neb_run.py`, `neb_post.py` | `calculation.type: neb` plus optional `atst neb make/post` | Core `neb.traj` remains; endpoint result repair is now governed before NEB starts. |
| AutoNEB | `autoneb_run.py` and manual collection from `run_autoneb*.traj` | `calculation.type: autoneb` with YAML `prefix` and `iter_folder` | Core `run_autoneb*.traj` and `AutoNEB_iter/*` remain; final-chain extraction is explicit through CLI post-processing. |
| Dimer | `neb2dimer.py` then `dimer_run.py` | `calculation.type: dimer` and `atst dimer make-from-neb` | Main produced `run_dimer.traj`; examples now use configurable `dimer.traj`. TS structure export is a post-processing command. |
| Sella | `sella_run.py` | `calculation.type: sella` | Main produced `run_sella.traj`; examples now use configurable `sella.traj`. |
| D2S | `neb2dimer_abacus.py` or `neb2sella_abacus.py` | `calculation.type: d2s` | Output names change most: current workflow uses `IS_opt.traj`, `FS_opt.traj`, `neb_rough.traj`, and `dimer.traj` or `sella.traj`; optional vibration writes JSON. |
| Relax | `relax_run.py` or DP-specific scripts | `calculation.type: relax` | Current workflow writes `relax.traj`, `relax.log`, and `final_relaxed.traj`; structure export is handled by `atst relax post`. |
| Vibration | `vib_analysis.py` and console output | `calculation.type: vibration` and `atst vibration post` | ASE cache remains; stable machine-readable `vibration_results.json` is added. |
| IRC | `sella_IRC.py` | `calculation.type: irc` | `irc_log.traj` and `norm_irc_log.traj` remain; Sella boundary failures are reported as controlled diagnostics. |

The most visible output changes are in D2S and post-processing. This is a
reasonable tradeoff for a governed CLI/YAML package, but migration documentation
should continue to make these file-name changes explicit.

## 5. Potential Development Reinforcement Points

The project is suitable for continued development from the refactor branch. The
highest-value reinforcement points are below.

### P0: Documentation Governance Closure

- Keep active docs free of links to archived reports.
- Keep `DOCUMENTATION_STATUS_REPORT.md` synchronized with actual file locations.
- Keep `DOCS_ARCHITECTURE.md` aligned with the current directory tree.

### P1: Reproducibility and User-Facing Outputs

- Add `atst run --print-normalized-config` or a `used_config.yaml` artifact so
  users can capture the exact normalized configuration used in production runs.
- Add a small workflow output manifest documenting expected trajectory, log,
  scratch, and final validation files per workflow.
- Add a migration table from main-branch script outputs to 2.0.0 outputs,
  especially for D2S and single-ended workflows.

### P1: Workflow Ergonomics

- Add optional final-structure export settings for Relax, Dimer, Sella, and D2S
  so users can request `stru`, `cif`, `traj`, or `extxyz` outputs from YAML.
- Consider a consistent `results_file` field for workflows that can produce
  compact JSON summaries, similar to vibration.
- Add better restart summaries that print which checkpoint was consumed.

### P1: Packaging and Backend Policy

- Move the vendored `abacuslite` fallback toward an optional dependency once
  upstream packaging is stable.
- Consider package extras such as `atst-tools[dp]` or documented environment
  markers for calculator-specific stacks.
- Continue treating `temp_repos` as development-only reference material.

### P2: Scientific Workflow Expansion

- Add ASE-based MD only after defining the YAML schema, output policy, restart
  behavior, examples, and SAI submission expectations.
- Add longer DP and ABACUS benchmark/regression cases outside the unit-test
  layer, because full scientific validation is too expensive for ordinary CI.
- Improve IRC recovery only if the project decides to own behavior beyond
  Sella's current boundary.

### P2: Internal Quality

- Keep tightening Google-style docstrings in first-party modules.
- Remove lower-level legacy compatibility branches once migration support is no
  longer needed.
- Continue adding focused tests when modifying schema variables, workflow output
  names, restart behavior, or calculator construction.

## 6. Review Conclusion

The refactor has achieved the core project goal: ATST-Tools is no longer a
collection of independent research scripts, but a maintainable Python package
with governed CLI/YAML workflows and testable backend abstractions.

The remaining work is not a blocker for continuing development, but it should be
handled deliberately. Documentation governance should stay strict, output naming
should be made more explicit for migration users, and future MD or advanced IRC
work should start from schema and example design rather than ad hoc scripts.
