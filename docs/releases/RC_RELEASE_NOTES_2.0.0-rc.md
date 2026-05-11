# ATST-Tools 2.0.0-RC 发布说明

**版本**: 2.0.0-rc  
**日期**: 2026-05-11  
**范围**: `refactor/unify-structure` 分支 RC 收敛结论

## 概述

本版本为 2.0.0 正式版前的发布候选（RC）。本次收敛以 ABACUS 工作流稳定性、统一 CLI/YAML 入口、文档治理与证据链可追踪为重点，形成可发布的功能状态与已知限制边界。

## 功能状态

- 已支持：`NEB`、`AutoNEB`、`Dimer`、`Sella`、`D2S`、`Relax`、`Vibration`。
- 未支持：`MD`（暂未进入 `atst run`）。
- 统一入口：耗时工作流通过 `atst run config.yaml` 调度，轻量前后处理由 git-style 子命令承担。
- 计算器路径：ABACUS 为 RC 主路径，`CalculatorFactory` 支持 `abacuslite` 外部安装优先、vendored fallback；`dp` 保留接口并等待独立实算收敛。

来源报告：

- `docs/reports/FEATURE_STATUS_MATRIX.md`
- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`

## 验收回归

- 本地质量检查通过：`pytest tests -q`、`python -m compileall -q src/atst_tools tests`。
- SAI ABACUS 实算回归中，NEB/AutoNEB/Dimer/Sella/Relax/Vibration/D2S 与 ideal-gas vibration 用例均有成功完成记录。
- 端到端链路已验证：`ASE -> ATST-Tools CLI/YAML -> abacuslite -> ABACUS v3.10.1`。

来源报告：

- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`
- `docs/reports/EXAMPLES_REGRESSION_2026-05-11.md`
- `docs/reports/REVIEW_ENHANCEMENTS_2026-05-11.md`

## 已知限制

- IRC 在真实 ABACUS 下存在稳定性问题：可生成部分物理合理轨迹，但在 Sella IRC 后段触发异常，尚不满足 release-clean。
- DP/机器学习势以接口打通为主，完整实算回归在 ABACUS 收敛后单独推进。
- AutoNEB 原生续算仍依赖其原生轨迹集合与迭代目录，不应被单一导出链文件替代。

来源报告：

- `docs/reports/EXAMPLES_REGRESSION_2026-05-11.md`
- `docs/archive/reports/ACCEPTANCE_2.0.0rc_CN.md`

## 兼容迁移

- 从历史脚本迁移到统一入口：生产运行统一使用 `atst run` + YAML。
- 保留 legacy 配置兼容：支持 `abacus.*` 与 `calculator.abacus.*` 两种结构，并自动映射旧参数名（如 `pp`、`basis`）。
- ABACUS 后端迁移完成：由 `ase-abacus` 过渡到 `abacuslite`（外部安装优先 + vendored fallback）。

来源报告：

- `docs/reports/REFACTORING_ACCEPTANCE_REPORT.md`
- `docs/archive/reports/ACCEPTANCE_2.0.0rc_CN.md`

## 文档治理结论

- 已完成 `developer` 与 `reports` 全量分类并执行归档收敛。
- 发布说明采用固定章节模板，报告信息提炼进入对外发布口径，原始证据链保留在 `reports`/`archive`。
- `docs/index.md` 已收敛为“当前有效入口 + 历史归档入口”，并清理过时导航。

来源报告：

- `docs/reports/DOCUMENTATION_STATUS_REPORT.md`

## 发布建议

- 可作为 2.0.0 正式版候选继续推进。
- 正式发布前建议完成：IRC 稳健性处置策略落地（至少实现受控失败语义），并补充 DP 独立实算回归结论。
