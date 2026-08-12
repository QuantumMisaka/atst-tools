# ATST-Tools 2.2.3 Release Notes

**Version**: 2.2.3
**Date**: 2026-08-12
**Branch**: pending merge (`feat/atst-prepare-and-trajectory-stress`)
**Tag**: `v2.2.3`

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.3 按 patch
> 语义承载本批小功能与修复：`atst prepare` 反向配置生成（小功能加入）与
> NEB/AutoNEB 轨迹应力保留（根因 bug 修复）。

ATST-Tools 2.2.3 adds two additive capabilities. First, a new top-level
`atst prepare` command and its stable Python API
`atst_tools.api.build_config_from_abacus_dir` reverse-generate a runnable
transition (NEB) YAML from a completed ABACUS run directory
(`INPUT`/`STRU`/`KPT`/`PP`/`ORB`), so a transition config can be derived from
an existing ABACUS run instead of being written by hand. Second, the mep layer
now retains per-image stress on NEB/AutoNEB trajectories when the ABACUS
calculator is asked for it (`cal_stress=1`). The release is purely additive:
no existing CLI, stable API, or YAML behavior changed, and with `cal_stress=0`
the produced NEB/AutoNEB trajectories are identical to 2.2.x.

## Highlights

- **`atst prepare` reverse configuration generation**
  (`utils/reverse_config.py`, `scripts/cli.py`): `atst prepare <abacus_run_dir>
  --workflow neb --init-structure ... --final-structure ... --n-images N
  --no-gate -o out.yaml` builds a runnable transition YAML from a completed
  ABACUS run directory. `--workflow` currently accepts `neb` (default);
  `--init-structure`/`--final-structure` select the endpoints (default: the
  run directory's `STRU`), `--n-images` sets the interior image count (default
  5), `-o/--output` chooses the output path, and `--no-gate` skips the
  endpoint energy+forces gate. The command does not run ABACUS.
- **`build_config_from_abacus_dir` Python API** (`utils/reverse_config.py`,
  exposed as a stable `atst_tools.api` root import): the same reverse
  generation is available to Python callers via
  `build_config_from_abacus_dir(abacus_run_dir, *, workflow, init_structure,
  final_structure, n_images, gate_dirs)`. It is an additive root import; all
  existing stable root imports are unchanged.
- **Three technical floors**: the generated config keeps user-controlled ABACUS
  values verbatim, but applies `calculation` → `scf` and `cal_force` → `1`
  (structural requirements for NEB interior single-point force evaluation) and
  rejects line-mode `KPT` files (Gamma/MP grids and explicit point K points are
  accepted). `pseudo_dir`/`orbital_dir` and the STRU-derived
  `pseudopotentials`/`basissets` are resolved into the ABACUS top-level
  fields, not `parameters`.
- **Trajectory stress retention** (`mep/neb.py`, `mep/autoneb.py`):
  `AbacusNEB` collects per-image stress (including the image-parallel
  `world.sum` branch), `iterimages()` freezes interior images with cached
  stress, and AutoNEB's serial and parallel freezing carry that stress through.
  With `cal_stress=1`, NEB/AutoNEB trajectories carry per-image stress; with
  `cal_stress=0` behavior is unchanged from 2.2.x.

## Validation

- Full unit suite passes (reverse-config, API exposure, CLI, mep stress
  retention, workflow, and documentation-governance tests).
- `python scripts/check_docs_governance.py` passes.

## Compatibility

- Package version: `2.3.0`.
- Python support remains `>=3.10`.
- The new `atst prepare` command and `build_config_from_abacus_dir` API are
  additive; no existing CLI entry point, stable root import, or YAML field
  changed. NEB/AutoNEB trajectory behavior with `cal_stress=0` is identical to
  2.2.x; with `cal_stress=1` trajectories additionally carry per-image stress.
