# 文档系统交接与维护

**版本**: 2026-06-27
**日期**: 2026-06-27
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档是维护者日常 checklist。任何功能、YAML、CLI、backend、example、report 或
release 变更，都先从对应小节确认需要同步的文档。

## 1. 日常入口

- 用户入口：[README.md](../../README.md)、[docs/index.md](../index.md)、
  [USER_GUIDE_CN.md](../user/USER_GUIDE_CN.md)。
- 参数入口：[CONFIG_REFERENCE.md](../user/CONFIG_REFERENCE.md) 和
  [YAML_INPUT_VARIABLES.md](../user/YAML_INPUT_VARIABLES.md)。
- 开发入口：[YAML_INPUT_GOVERNANCE.md](YAML_INPUT_GOVERNANCE.md)、
  [DOCUMENTATION_STANDARDS.md](DOCUMENTATION_STANDARDS.md)。
- 项目状态入口：[FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md) 和
  [DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)。

## 2. 新增或修改 workflow

- 更新 `README.md` 的支持列表和 quick start 说明。
- 更新 `docs/user/USER_GUIDE_CN.md`、`CLI_REFERENCE.md`、`CONFIG_REFERENCE.md`。
- 添加或更新 `examples/<case>/config*.yaml` 和 `examples/README.md`。
- 更新 `docs/reports/FEATURE_STATUS_MATRIX.md`。
- 添加或更新 workflow 测试、example 测试和必要验证报告。

## 3. 新增或修改 YAML 字段

- 修改 `src/atst_tools/utils/config_schema.py`。
- 重新生成 `docs/user/YAML_INPUT_VARIABLES.md`。
- 在 `docs/user/CONFIG_REFERENCE.md` 解释语义、默认值影响和常见配置组合。
- 更新示例 YAML。
- 运行 `tests/unit/test_config.py` 和相关 workflow/example tests。

## 4. 新增或修改 CLI

- 更新 `docs/user/CLI_REFERENCE.md`。
- 更新 `docs/skills/atst-cli/SKILL.md` 中的操作片段。
- 必要时更新 README 的轻量命令列表。
- 添加 CLI 测试或更新现有命令测试。

## 4.1 新增或修改稳定 Python API / process runner

- 保持 `atst_tools.api.__all__` 的既有稳定 root imports；runner 不得成为新的
  root import 或改变 `atst` CLI 行为。
- 更新 `docs/user/PYTHON_API_REFERENCE.md`、README、中文用户指南、release notes
  和功能状态账本，说明 JSON schema、退出码、manifest 权威性与 MPI 责任边界。
- 对 `python -m atst_tools.api.runner` 运行 API/document、clean-wheel 和实际 MPI
  门禁；runner 只能消费 API，绝不启动 Slurm、`mpirun` 或 `srun`。

## 5. 新增或修改 calculator backend

- 更新 README backend section 和项目边界说明。
- 更新 `docs/user/CONFIG_REFERENCE.md` 的 calculator 配置说明。
- 更新 `docs/user/USER_GUIDE_CN.md` 的运行时依赖和环境边界。
- 更新 feature/status reports 和 calculator factory tests。
- 若 backend 涉及 ABACUS/DP 环境，补充验证报告或在现有报告中记录边界。
- `abacuslite` vendored ASE interface 变更需同步运行
  `.github/workflows/abacuslite-ase-interface.yml` 覆盖的 pytest 回归测试、
  package-mode upstream-style parser tests 和 snapshot drift check；不要直接使用
  上游 `xtest.sh`，因为 ATST vendored copy 使用包内相对导入，直接脚本模式会
  绕过包上下文。
- 同步 `temp_repos/abacus-develop/interfaces/ASE_interface` 时，先运行
  `conda run -n atst-dev python scripts/check_abacuslite_snapshot.py --upstream temp_repos/abacus-develop/interfaces/ASE_interface --vendored src/atst_tools/external/ASE_interface`。
  若上游 reference commit 更新，同步更新
  `.github/workflows/abacuslite-ase-interface.yml` 的 `ABACUS_DEVELOP_REF`。
- 维护 `abacuslite` property-derived keywords 时，显式用户输入与自动派生值需按
  ABACUS 开关语义比较，例如 `True`、`1`、`"1"` 等价；但 `False`/`0` 与请求
  `forces` 或 `stress` 自动需要的 `"1"` 仍应作为冲突报错。

## 6. 新增或修改依赖

- 默认 `dependencies` 只放普通安装必须具备的轻量运行时依赖；重型后端、
  MPI、绘图和发布工具优先进入 `[project.optional-dependencies]`。
- Sella 是一等 workflow backend，默认依赖需保持 `sella>=2.5,<3`，除非有
  明确兼容性回退证据。
- DP 工作流使用 `dp` extra，MPI image-level parallelism 使用 `parallel`
  extra，NEB plotting helper 使用 `plot` extra。
- 修改依赖范围时，更新 README、`docs/user/USER_GUIDE_CN.md` 和本文件。
- 添加或更新 package metadata 测试，并运行构建检查：
  `pytest tests/unit/test_package_metadata.py -q`、`python -m build` 和
  `python -m twine check --strict dist/*`。
- 对包含稳定 Python API 的 release，运行
  `python scripts/verify_wheel_api.py`；它在临时目录构建 wheel、在临时 venv
  non-network clean-install，并验证六个稳定 root imports 和 H2/Au 的 EMT
  public API example path 和 installed API runner JSON handoff，不在工作树保留 build artifact。若 release 环境已
  准备 `mpi4py` 和 `mpiexec`，额外运行
  `python scripts/verify_wheel_api.py --mpi-smoke`；该 two-rank smoke 限时，
  验证 image-parallel NEB/AutoNEB 的 rank-0 endpoint failure 以及 rank-local
  optimizer construction failure 会使所有 rank 以 typed API failure 退出，且在
  找不到 launcher 时明确跳过。

## 7. 新增或修改 example

- 更新 `examples/README.md` 的学习路径、目录说明和 chemical systems 表。
- 更新 `examples/reference_results.json`，或明确该 example 暂无 reference 结果。
- 保证新增输入在 `inputs/` 或受控路径下，生成输出不进入 git。
- 运行 example 解析、dry-run 或 reference-result 测试。

## 8. 新增 report 或移动旧 report

- 判断 report 级别：L1 状态入口、L2 当前证据、L3 当前主题审查、L4 历史材料。
- 更新 `docs/reports/DOCUMENTATION_STATUS_REPORT.md`。
- 只有当 report 是核心入口或当前重点证据时，才从 `docs/index.md` 链接。
- 被取代的 report 先吸收结论，再移到 `docs/archive/` 或
  `docs/archive/pending_delete/`。

## 9. 准备 release

- 更新 `docs/releases/RELEASE_NOTES_<version>.md`。
- 更新 README badge、版本说明和 release scope。
- 更新 `FEATURE_STATUS_MATRIX.md` 和 `DOCUMENTATION_STATUS_REPORT.md`。
- 复核 `docs/archive/pending_delete/README.md`，确认是否最终删除待删除文件。
- 运行文档链接、格式和相关测试。

## 10. 最小检查

```bash
git diff --check -- README.md docs examples/README.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md
python scripts/check_docs_governance.py
```

若修改 YAML schema：

```bash
conda run -n atst-dev python -m atst_tools.utils.config_docs --output docs/user/YAML_INPUT_VARIABLES.md
conda run -n atst-dev pytest tests/unit/test_config.py -q
```
