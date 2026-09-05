# ATST-Tools 2.2.4 Release Notes

**Version**: 2.2.4
**Date**: 2026-09-06
**Status**: Release candidate; publication pending
**Branch**: `main`
**Tag**: pending maintainer creation (`v2.2.4`)

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.4 按 patch
> 语义承载 portable MPI 诊断、安装 profile 和用户导航改进。

ATST-Tools 2.2.4 is a backward-compatible release candidate that makes the
optional image-parallel installation boundary and its recovery path easier to
follow. The existing `parallel` extra was already present in 2.2.3; this
release does not add a second distribution, move `mpi4py` into the base
installation, or claim to repair arbitrary MPI ABI crashes.

## Highlights

- **Portable installation and navigation**: the README and user guide now
  distinguish Serial, DP, and externally launched image-parallel profiles,
  and provide absolute GitHub/Gitee guide and example links for package-page
  readers. The repository and PyPI publication boundaries remain explicit.
- **MPI preflight and recovery guidance**: image-parallel users are directed
  to verify `mpi4py` import and a two-rank launcher before running a workflow.
  When `mpi4py` is missing under an MPI launcher, the runtime diagnostic names
  `atst-tools[parallel]`, the site MPI implementation shared by the launcher
  and ABACUS, and an `MPICC` source rebuild command.
- **Release governance facts**: active version metadata and release navigation
  now identify 2.2.4 as a candidate until its exact tag and PyPI artifact
  confirm publication. Existing exact-tag readiness and OIDC workflow
  contracts are unchanged.

## Validation

- The full test suite, documentation-governance checker, and whitespace check
  pass for the release-preparation tree.
- No external scheduler, site MPI runtime, GitHub setting, tag, push, or PyPI
  publication is part of this local preparation commit.

## Compatibility

- Package version: `2.2.4`.
- Python support remains `>=3.10`.
- Existing CLI, YAML, stable API, and serial-install behavior remain
  unchanged. `mpi4py` remains outside the base dependencies; image-parallel
  execution still requires the explicit `parallel` extra or an equivalent
  site-compatible environment.
