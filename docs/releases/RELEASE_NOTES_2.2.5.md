# ATST-Tools 2.2.5 Release Notes

**Version**: 2.2.5
**Date**: 2026-09-16
**Status**: Published (official no-cache clean-install verified)
**Branch**: `main`
**Tag**: `v2.2.5` → `4c966915c6f40984fc85806869f4766ecdd6ffc9`

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.5 按 patch
> 语义承载 abacuslite 周期性 SCF 帧身份校验修复及用户边界说明。

ATST-Tools 2.2.5 is a backward-compatible release for the vendored
abacuslite SCF frame-selection fix. When `calculation: scf` reads an accumulated
running log, it normalizes the current STRU and candidate frames to the same ASE
atom order, Cartesian Å coordinates, and cell, then accepts periodic-equivalent
frames using integer lattice translations in fractional coordinates. The
selector scans backward and returns the latest matching frame, including for
valid cross-cell transition-state and NEB movement.

The identity check remains fail-closed. Different structures or cells, wrong
atom counts, shapes, finite-value state, elements, or atom order, singular
cells, malformed frames, and non-integer residual displacements are not
silently accepted. The check does not wrap or mutate the STRU, candidate
`Atoms`, forces, cell, or transition-state/NEB coordinates. A custom
`stru_file` written by `write_input` is used for the corresponding check; the
default `STRU` behavior remains when no custom filename is supplied.

The candidate also carries the compatibility-preserving transition-workflow
advisory behavior developed in `fd7c8da`: Sella, CCQN, Sella IRC (per
direction), and final NEB can report an explicit non-convergence signal without
changing completion, exit-code, return-value, or artifact-manifest semantics.
Unknown signals remain un-inferred, and a completed workflow must not be read as
proof of scientific convergence.

## Compatibility

- Package version: `2.2.5`.
- Python support remains `>=3.10`.
- Existing CLI, YAML, stable API, and serial-install behavior remain unchanged.
- No `pbc_mode`, tolerance, or other new YAML configuration field is added; the
  PBC-aware identity selection is automatic for SCF results.
- Native `relax`, `md`, and `MD_dump` retain their existing last-frame
  semantics; the new identity check is limited to SCF frame selection.
- The advisory non-convergence messages do not change workflow completion or
  manifest status and do not assert that a scientific result is converged.

## Validation and Publication Matrix

The release commit completed the corrective rerun and final local pre-release
gate. The frozen STRU declaration-count revision has 32 focused core tests
passing; final core rebuild verification and independent review have passed.
The official no-cache clean-install from `https://pypi.org/simple` passed in a
fresh virtual environment. `pip check`, `atst --version`,
`atst_tools.package_version()`, the six stable root API imports, and
`python -m atst_tools.api.runner --help` all passed for 2.2.5; the package was
loaded from that environment's site-packages rather than the source checkout.
The published core and reviewed release source were byte-for-byte identical
(SHA256 `30c11b06623e4850b27a2882f19b14c1bad1d3756780d9c5655d3a2b6d70d7ad`).
SIF/SAI/platform validation remains out of scope for this release evidence.

| Evidence | Candidate status | Record after validation |
| :--- | :--- | :--- |
| Direct/Cartesian, orthogonal/triclinic, single/multi-atom periodic frame selection | Passed after corrective rerun | Core focused tests: 32 passed; final core rebuild verification and independent review passed |
| Fail-closed malformed frame, cell, order, shape, count, finite-value, and residual cases | Passed after corrective rerun | Focused and owning frame-selection tests; STRU declaration-count revision verified |
| Native relax/md/MD_dump behavior and custom `stru_file` | Passed after corrective rerun | Owning backend tests; STRU declaration-count revision verified |
| Vendored snapshot checker and package-mode parser checks | Passed after corrective rerun | Real upstream baseline checker exit 0; package-mode parser: 28 runs, 2 skips |
| Documentation governance, package metadata, build, Twine, and wheel API gates | Passed for local pre-release gate | Full tests: 666 passed, 19 conditional skips (685 total); docs/metadata passed; build/Twine/clean wheel API passed |
| Exact `v2.2.5` tag, GitHub Tests/abacuslite CI, and PyPI publication | Published | Release commit `4c966915c6f40984fc85806869f4766ecdd6ffc9`; [Tests](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311728), [abacuslite](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311733), and [Publish](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058399930) succeeded. [PyPI JSON](https://pypi.org/pypi/atst-tools/2.2.5/json) lists wheel SHA256 `d1fffe13a5f8aefbc125ec22f4d56f21db0b0f7364dfe032df0cf8a26246fe2a` (uploaded `2026-09-16T05:16:17.522320Z`) and sdist SHA256 `c028b6767cc35c98685f98e7b28e1b691bc1c310323abaad9ba2f32306f359da` (uploaded `2026-09-16T05:16:19.040843Z`). Official no-cache clean-install, CLI/API, dependency, and site-packages identity checks passed; the published core/source comparison matched SHA256 `30c11b06623e4850b27a2882f19b14c1bad1d3756780d9c5655d3a2b6d70d7ad`. |
| SIF rebuild, SAI runtime identity, and platform validation | Not performed | Separate Paimon/platform release evidence |

## Publication Boundary

This file records the published 2.2.5 release from the exact `v2.2.5` tag.
The official no-cache clean-install from PyPI and its CLI/API/dependency checks
are complete. The current SIF and SAI runtime have not been updated and
must not be represented as running the new matcher. Paimon/SIF/SAI integration
and platform validation remain separate follow-up work.
