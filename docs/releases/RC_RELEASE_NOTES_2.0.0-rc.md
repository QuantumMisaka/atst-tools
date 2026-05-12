# ATST-Tools 2.0.0-rc 发布说明

**版本**: 2.0.0-rc
**日期**: 2026-05-12
**范围**: `refactor/unify-structure` 分支 RC 收敛结论

## 概述

本版本为 2.0.0 正式版前的发布候选（RC）。本次收敛以 ABACUS 工作流稳定性、统一 CLI/YAML 入口、文档治理与证据链可追踪为重点，形成可发布的功能状态与已知限制边界。

## 与 main 分支对比的主要变更

### 架构重构
- **完全重写代码架构**：从独立脚本集重构为可 `pip install` 的标准 Python 包
- **统一入口**：新增 `atst run config.yaml` 单一调度命令，支持所有工作流类型
- **计算器工厂**：新增 `CalculatorFactory`，实现 ABACUS 与 DeepMD 无缝切换
- **模块化设计**：
  - `src/atst_tools/calculators/`：计算器适配层
  - `src/atst_tools/mep/`：过渡态搜索算法封装
  - `src/atst_tools/workflows/`：高级工作流（Relax/Vibration/D2S/IRC）
  - `src/atst_tools/scripts/`：CLI 入口
  - `src/atst_tools/utils/`：共享工具

### 新增功能
- **YAML 配置统一管理接口**：基于 Pydantic schema 的集中式配置治理，支持类型校验、默认值填充、文档自动生成
  - `src/atst_tools/utils/config_schema.py`：定义所有 YAML 字段类型、默认值和说明
  - `src/atst_tools/utils/config.py`：`ConfigLoader` 提供 `load()`/`normalize()`/`validate()` 接口
  - `docs/user/YAML_INPUT_VARIABLES.md`：由 schema 自动生成的完整变量文档
  - `--dry-run` 模式在运行前完成配置校验和规范化
- **D2S 工作流**：从双端粗搜索到单端精搜索的完整集成流程
- **Relax 工作流**：结构优化，支持 BFGS/FIRE/LBFGS 优化器
- **Vibration 工作流**：振动频率分析，支持 Harmonic 与理想气体热化学
- **IRC 工作流**：内禀反应坐标追踪（实验性）
- **轻量 CLI 子命令**：`atst neb-make`、`atst neb-post`、`atst relax-post`、`atst vibration-post`
- **热化学分析**：支持 Harmonic 与理想气体模型的自由能、熵、焓计算

### ABACUS 集成
- **后端迁移**：从 `ase-abacus` 过渡到官方 `abacuslite`
- **策略升级**：优先使用外部安装的 `abacuslite`，内置 vendored fallback 保证可重现性
- **配置兼容**：支持旧参数名自动映射（`pp`→`pseudopotentials`，`basis`→`basissets`）
- **SAI 优化**：默认配置适配 SAI GPU 环境（`ks_solver: cusolver`）

### DeepMD 集成
- **接口打通**：完整支持 `calculator.name: dp`，与 ABACUS 使用同一套工作流
- **配置支持**：`model`、`type_map`、`type_dict`、`head`、`omp` 等参数
- **显存优化**：支持 `share_calculator: true`，串行 NEB 时复用模型实例，大幅降低显存占用
- **状态说明**：接口已完成，完整实算回归在 ABACUS 收敛后单独推进

### 文档与示例
- **完整文档体系**：
  - 用户文档：配置参考、CLI 参考、中文用户指南
  - 开发文档：重构指南、架构说明、文档标准
  - 报告：功能矩阵、验收报告、回归报告
- **标准化示例**：examples/ 目录重构为统一结构，包含 Li 扩散、H₂ 解离、环己烷脱氢等系统
- **证据链保留**：当前验收报告与回归结果保留在 `docs/reports/`

### 测试与质量
- **单元测试覆盖**：新增 70+ 单元测试，覆盖 CLI、配置、工厂、工作流、工具函数
- **SAI 实算回归**：所有核心工作流（NEB/AutoNEB/Dimer/Sella/Relax/Vibration/D2S）在 SAI GPU 上完成实算验证
- **配置验证**：`--dry-run` 模式检查配置有效性，避免提交错误作业

### 移除与迁移
- **删除遗留脚本**：移除 `neb/`、`relax/`、`sella/`、`vibration/`、`source/` 目录下的独立脚本
- **迁移历史示例**：旧示例数据重构为统一的 `examples/data/` 与 `examples/[case]/inputs/` 结构
- **Git 治理**：大量生成文件（.traj、OUT.ABACUS、.err/.out）加入 .gitignore

## 功能状态

- **已支持**：`NEB`、`AutoNEB`、`Dimer`、`Sella`、`D2S`、`Relax`、`Vibration`。
- **未支持**：`MD`（暂未进入 `atst run`）。
- **统一入口**：耗时工作流通过 `atst run config.yaml` 调度，轻量前后处理由 git-style 子命令承担。
- **计算器路径**：
  - ABACUS 为 RC 主路径，`CalculatorFactory` 支持 `abacuslite` 外部安装优先、vendored fallback；
  - DP 接口已完成，`share_calculator` 显存优化支持，完整实算收敛待后续。

来源报告：

- `docs/reports/FEATURE_STATUS_MATRIX.md`
- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`
- `docs/reports/YAML_CONFIGURATION_REVIEW.md`

## 验收回归

- **本地质量检查通过**：`pytest tests -v`（70+ 测试通过）、`python -m compileall -q src/atst_tools tests`。
- **SAI ABACUS 实算回归**：NEB/AutoNEB/Dimer/Sella/Relax/Vibration/D2S 与 ideal-gas vibration 用例均有成功完成记录。
- **端到端链路已验证**：`ASE -> ATST-Tools CLI/YAML -> abacuslite -> ABACUS v3.10.1`。
- **DP 接口验证**：单元测试覆盖，配置通过 `--dry-run`，实算回归计划在 ABACUS 验证完成后进行。

来源报告：

- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`
- `docs/reports/EXAMPLES_REGRESSION_2026-05-11.md`
- `docs/reports/REVIEW_ENHANCEMENTS_2026-05-11.md`

## 已知限制

- **IRC**：在真实 ABACUS 下存在稳定性问题，可生成部分物理合理轨迹，但在 Sella IRC 后段触发异常，尚不满足 release-clean。
- **DP/机器学习势**：以接口打通为主，完整实算回归在 ABACUS 收敛后单独推进；当前所有工作流已支持 DP 配置。
- **AutoNEB**：原生续算仍依赖其原生轨迹集合与迭代目录，不应被单一导出链文件替代。

来源报告：

- `docs/reports/EXAMPLES_REGRESSION_2026-05-11.md`

## 兼容迁移

- **从历史脚本迁移到统一入口**：生产运行统一使用 `atst run` + YAML，参考 `examples/` 中的配置模板。
- **保留 legacy 配置兼容**：支持 `abacus.*` 与 `calculator.abacus.*` 两种结构，并自动映射旧参数名（如 `pp`、`basis`）。
- **ABACUS 后端迁移完成**：由 `ase-abacus` 过渡到 `abacuslite`（外部安装优先 + vendored fallback）。
- **DP 配置迁移**：旧 `ase-dp/` 脚本的功能已迁移到 `calculator.name: dp`，支持同样参数。

来源报告：

- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`

## 文档治理结论

- **已完成** `developer` 与 `reports` 全量分类并执行归档收敛。
- **发布说明** 采用固定章节模板，报告信息提炼进入对外发布口径，原始证据链保留在 `reports`/`archive`。
- **`docs/index.md`** 已收敛为“当前有效入口 + 历史归档入口”，并清理过时导航。

来源报告：

- `docs/reports/DOCUMENTATION_STATUS_REPORT.md`

## 发布条件确认

✅ **所有核心功能已完成并通过 SAI 实算验证**
✅ **统一 CLI/YAML 入口已就绪**
✅ **YAML 配置统一管理接口已实现（Pydantic schema + ConfigLoader）**
✅ **单元测试覆盖充足（70+ 测试通过）**
✅ **文档体系完整，发布说明已更新**
✅ **ABACUS 后端从 ase-abacus 迁移到 abacuslite**
✅ **DP 接口已打通并支持显存优化**
✅ **D2S 工作流已集成**
✅ **文档治理已完成**

**结论：具备发布 2.0.0-rc 的条件**
