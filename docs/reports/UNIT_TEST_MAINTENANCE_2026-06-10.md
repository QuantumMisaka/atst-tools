# Unit Test Maintenance Report 2026-06-10

**版本**: 2026-06-10
**日期**: 2026-06-10
**状态**: 当前主题审查
**责任人**: ATST-Tools maintainers

## Scope

本轮维护聚焦默认单元测试的纯逻辑路径覆盖和 legacy 测试治理。默认测试仍保持登录节点可运行，不提交 Slurm，不依赖真实 ABACUS、DeePMD-kit 或 GPU。

## Changes

- 新增 `tests/helpers.py`，集中 `DummyCalc`、`FakeWorld`、`FakeReducingWorld` 等轻量测试 fixture，并迁移高重复 MPI/workflow 测试用法。
- 在 `tests/conftest.py` 增加根目录 artifact 泄漏守卫，防止 `md_final.traj` 和 `md_post_summary.json` 由测试落到仓库根目录。
- 补充 `utils/reactive_modes.py`、`utils/post.py`、`mep/dimer.py` 和 `mep/autoneb.py` 的轻量控制分支测试。
- 删除未注册 console script 模块 `src/atst_tools/scripts/neb_make.py` 和 `src/atst_tools/scripts/neb_post.py`，保留 `atst` git-style CLI 作为唯一公开入口。
- 增加治理测试，确认 `pyproject.toml` 只暴露 `atst`，且 active docs 不再把 legacy NEB modules 作为当前入口。

## Coverage Policy

本轮不为覆盖率数字引入真实优化器数值路径或外部后端 mock 大网。覆盖重点是可维护、确定性的核心分支：参数解析、fallback、目录选择、MPI/AutoNEB 控制流和 legacy 入口约束。

## Verification

本轮验证命令：

```bash
conda run -n atst-dev pytest tests/unit/test_reactive_modes.py tests/unit/test_post_analysis_io.py tests/unit/test_workflows.py tests/unit/test_mpi_parallel.py -q
conda run -n atst-dev pytest tests -q
conda run -n atst-dev pytest tests --collect-only -q
conda run -n atst-dev python -m coverage run --source=src/atst_tools -m pytest tests -q
conda run -n atst-dev python -m coverage report --show-missing
conda run -n atst-dev python scripts/check_docs_governance.py
git diff --check -- tests src docs
rg -n "^<<<<<<<|^=======|^>>>>>>>" tests src docs
find . -maxdepth 1 -type f \( -name 'md_final.traj' -o -name 'md_post_summary.json' -o -name '.coverage' \) -print
```

结果记录：

- 目标测试组、全量测试和 collect-only 均通过。
- coverage 含 vendored `external/ASE_interface` 时总覆盖率为 72%；按本轮口径排除 vendored external 后，项目代码覆盖率为 83%。
- 文档治理检查通过。
- `git diff --check -- tests src docs` 通过。
- 冲突标记搜索无匹配。
- 根目录未残留 `md_final.traj`、`md_post_summary.json` 或 `.coverage`。
