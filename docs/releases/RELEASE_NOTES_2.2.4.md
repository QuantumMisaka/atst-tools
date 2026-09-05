# ATST-Tools 2.2.4 Release Notes

**Version**: 2.2.4
**Date**: 2026-09-06
**Status**: Published
**Branch**: `main`
**Tag**: `v2.2.4` → `eaac64a76215e33588d362a788c138464519a7ba`

## Summary

> 版本号语义（本仓库约定）：minor（2.x.0）保留给阶段性/重大功能发布；
> patch（2.2.x）承担小功能加入与新增优化，以及 bug 修复。2.2.4 按 patch
> 语义承载 portable MPI 诊断、安装 profile 和用户导航改进。

ATST-Tools 2.2.4 is a backward-compatible release that makes the
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
  identify the published 2.2.4 release and its exact tag. Existing exact-tag
  readiness and OIDC workflow contracts are unchanged.
- **abacuslite CI drift registration**: the snapshot checker now registers the
  documented point-KPT parser patch while continuing to reject unrelated drift;
  the tagged abacuslite CI run passed.

## Publication and Validation

- Tag `v2.2.4` points to `eaac64a76215e33588d362a788c138464519a7ba`.
- The [GitHub release](https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.2.4)
  was created for the exact tag.
- GitHub Tests run `33980730827`, abacuslite run `33980730831`, and PyPI
  publication run `33980788260` completed successfully.
- [PyPI 2.2.4 metadata](https://pypi.org/pypi/atst-tools/2.2.4/json) lists the
  wheel and source distribution. The [rendered PyPI project page](https://pypi.org/project/atst-tools/2.2.4/)
  exposes four absolute GitHub/Gitee guide and examples links. Gitee rendering
  verification was explicitly excluded from this release closure.
- Clean-environment verification in `/tmp/atst-224-pypi-verify.7qwIIs/venv`
  installed `atst-tools==2.2.4` from PyPI, passed `pip check`, reported
  `2.2.4` from `atst --version`, imported the package outside the repository,
  loaded the stable API imports, and confirmed that `mpi4py` is absent.
- The uploaded PyPI README is immutable and retains the candidate wording from
  the prepublication upload. The repository README is current; this is a
  cosmetic PyPI rendering limitation only and does not warrant a patch release,
  retag, or republish.

## Compatibility

- Package version: `2.2.4`.
- Python support remains `>=3.10`.
- Existing CLI, YAML, stable API, and serial-install behavior remain
  unchanged. `mpi4py` remains outside the base dependencies; image-parallel
  execution still requires the explicit `parallel` extra or an equivalent
  site-compatible environment.
