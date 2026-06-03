# 文档系统架构与结构图

**版本**: 2026-05-28
**日期**: 2026-05-28
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档说明 ATST-Tools 文档树的职责边界。它服务于三类读者：用户、开发者和项目管理者。

## 1. 目标读者

- **用户**：安装 ATST-Tools，选择示例，编写 YAML，运行 ABACUS/DP 工作流，理解 CLI 行为。
- **开发者**：扩展 workflow、calculator backend、YAML schema、CLI、examples、tests 和文档。
- **项目管理者**：判断功能支持状态、验证证据、发布范围、文档健康度和下一步优先级。

## 2. 目录职责

```text
docs/
├── index.md                            # 三类读者的文档入口
├── user/                               # 用户指南、CLI/YAML 参考、backend 使用边界
├── developer/                          # 开发规范、文档治理、YAML 治理、发布和交接
│   └── plans/                          # 仍计划执行的开发计划
├── reports/                            # 当前仍有证据价值的状态、验证、审查报告
├── releases/                           # 版本级发布说明
├── skills/                             # 可复用操作说明和 agent/developer quick reference
└── archive/                            # 历史归档；pending_delete/ 为待删除复核区
```

| 路径 | 职责 | 不应承载 |
| :--- | :--- | :--- |
| `docs/index.md` | 文档总入口和三条阅读路径 | 完整历史报告清单、临时计划 |
| `docs/user/` | 用户手册、CLI/YAML 参考、ABACUS/DP 使用说明 | 阶段性开发计划、失败复盘 |
| `docs/developer/` | 开发规范、治理规则、维护 checklist | 阶段验证报告 |
| `docs/developer/plans/` | 仍要执行的计划 | 已完成计划、历史设想 |
| `docs/reports/` | 当前状态页、验证证据、仍有效的工程审查 | 已被最终报告取代的中间记录 |
| `docs/releases/` | release notes | 日常开发报告 |
| `docs/skills/` | 可复用操作手册 | 项目状态报告 |
| `docs/archive/` | 有审计价值的历史材料 | 活跃入口依赖的文档 |
| `docs/archive/pending_delete/` | 已过时但待最终删除确认的文件 | 仍有当前证据价值的文件 |

## 3. 生命周期类型

新文档必须在文首或首段能判断生命周期类型：

| 类型 | 含义 | 典型位置 |
| :--- | :--- | :--- |
| `guide` | 长期维护的用户或开发者指南 | `docs/user/`, `docs/developer/` |
| `reference` | 长期查表材料，例如 CLI/YAML 字段 | `docs/user/` |
| `status` | 当前状态入口 | `docs/reports/` |
| `validation` | 运行、单测、环境或科学验证证据 | `docs/reports/` |
| `review` | 边界分析、迁移审查、方案权衡 | `docs/reports/` |
| `plan` | 尚待执行的计划 | `docs/developer/plans/` |
| `release` | 版本级发布记录 | `docs/releases/` |
| `archive` | 不再指导当前工作的历史材料 | `docs/archive/` |

## 4. 导航原则

- `README.md` 和 `docs/index.md` 只链接活跃入口，不列完整历史报告清单。
- 完整 reports 账本放在
  [DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)。
- 用户路径不得要求先阅读 `docs/reports/` 才能运行示例。
- 开发者路径从 [HANDOVER.md](HANDOVER.md) 和
  [YAML_INPUT_GOVERNANCE.md](YAML_INPUT_GOVERNANCE.md) 开始。
- 项目管理路径从
  [FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md) 和
  [DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)
  开始。
- 活跃入口不得链接 `docs/archive/` 或 `docs/archive/pending_delete/`，治理账本和
  pending-delete 说明除外。

## 5. 状态入口

- 主入口：[docs/index.md](../index.md)
- 中文用户指南：[USER_GUIDE_CN.md](../user/USER_GUIDE_CN.md)
- CLI 参考：[CLI_REFERENCE.md](../user/CLI_REFERENCE.md)
- YAML 语义参考：[CONFIG_REFERENCE.md](../user/CONFIG_REFERENCE.md)
- YAML 参数总表：[YAML_INPUT_VARIABLES.md](../user/YAML_INPUT_VARIABLES.md)
- 功能矩阵：[FEATURE_STATUS_MATRIX.md](../reports/FEATURE_STATUS_MATRIX.md)
- 文档治理账本：[DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)
- 发布说明：[RELEASE_NOTES_2.0.1.md](../releases/RELEASE_NOTES_2.0.1.md)
