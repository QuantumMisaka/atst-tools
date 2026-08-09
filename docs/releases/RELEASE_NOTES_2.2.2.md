# ATST-Tools 2.2.2 Release Notes

**Version**: 2.2.2
**Date**: 2026-08-10
**Branch**: `main`
**Tag**: `v2.2.2`

## Summary

> 版本号语义（本仓库约定）：patch（2.2.x）承担小功能加入与新增优化，以及 bug
> 修复。2.2.2 是 NEB/AutoNEB 端点结果治理与 climbing-image 阶段健壮性的
> bug 修复发布。

ATST-Tools 2.2.2 hardens NEB-family endpoint-result handling and the AutoNEB
climbing-image phase. A chain uploaded from outside ATST (e.g. an example or a
foreign trajectory) can carry readable endpoint energies that are inconsistent
with the run's calculator (a stale value ~472 eV above the path was observed);
under `endpoint_singlepoint: auto` those stale values previously entered the
band profile, made an endpoint the highest-energy image, and crashed the
AutoNEB CI phase with an obscure `AssertionError`. 2.2.2 fixes both the data
path (endpoints are recomputed unless explicitly marked by ATST) and the
failure path (the CI phase now fails with a clear diagnostic instead of an
assert).

## Highlights

- **Endpoint policy semantics** (`utils/neb_endpoints.py`): `auto` now trusts
  only endpoint results explicitly marked by ATST as `computed`/`optimized`/
  `provided`; missing, placeholder, or unmarked (uploaded-chain/foreign)
  results are recomputed with the current run's calculator so the path and its
  endpoints stay consistent. `always` recomputes both endpoints; `never`
  preserves user-provided readable endpoint results (and raises only when an
  endpoint lacks meaningful energy/force results). The trust marker is the
  per-image `atst_endpoint_result` attribute that ATST workflows write.
- **Marker preservation** (`mep/autoneb.py`, `workflows/d2s.py`): legacy
  endpoint-condition copy and D2S re-freeze paths no longer default unmarked
  endpoints to `provided`, so foreign readable values are recomputed under
  `auto` and are not overwritten by stale caches after recomputation.
- **Graceful CI failure** (`mep/autoneb.py`): the climbing-image phase replaces
  `assert climb_safe` with a clear `ValueError` explaining that the highest-
  energy image is an endpoint (inconsistent endpoint results or no interior
  transition state) and how to proceed.
- **Documentation**: `endpoint_singlepoint` semantics and the
  `atst_endpoint_result` trust marker are documented in `CONFIG_REFERENCE.md`,
  `YAML_INPUT_VARIABLES.md` (regenerated from the schema), and
  `ABACUSLITE_WRAPPER_GUIDE.md`.

## Validation

- Full unit suite passes (endpoint policy, AutoNEB CI boundary, D2S, workflow,
  and documentation-governance tests).
- Real-environment validation (SAI, ABACUS LTS 3.10.1): an AutoNEB run with a
  stale-endpoint chain recomputed both endpoints to the run's SCF energies and
  completed the CI phase with exit 0 (previously crashed at the same point).
- Doc governance check (`scripts/check_docs_governance.py`) passes.

## Compatibility

- Package version: `2.2.2`.
- Python support remains `>=3.10`.
- The `endpoint_singlepoint` YAML values (`auto`/`always`/`never`) and the
  stable `atst_tools.api` root imports are unchanged; the `auto` default now
  recomputes unmarked endpoint results (behavioral hardening for foreign
  chains). The ASE-native AutoNEB backend (`neb_backend="ase"`) still inherits
  the upstream ASE CI assert and is not covered by this release.
