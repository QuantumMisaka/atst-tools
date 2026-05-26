# 文档治理状态报告

**版本**: 2.0.0
**日期**: 2026-05-15
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档是 ATST-Tools 当前文档治理状态的单一入口。它记录活跃文档职责、归档判据和本阶段归档结果，避免用户入口、开发者入口、报告入口和发布说明之间出现职责重叠。

## 1. 核心结论

- 活跃文档入口已收敛到 `docs/index.md`、`README.md`、用户文档、开发者文档、当前报告和发布说明。
- 历史审查材料只保留为历史记录，不作为活跃导航目标。
- 当前阶段新增 `PROJECT_REFACTOR_REVIEW_2026-05-15.md`，用于承接本轮项目状态、归档建议、main 分支对比、输入输出差异和后续补强点。
- `Calculator_Review.md` 与 `YAML_CONFIGURATION_REVIEW.md` 已完成阶段任务，已移出活跃 `docs/reports`。

## 2. 活跃 Developer 文档

| 文档 | 处置 | 当前职责 |
| :--- | :--- | :--- |
| `developer/YAML_INPUT_GOVERNANCE.md` | 保留 | YAML schema、变量新增、文档导出和测试治理规则。 |
| `developer/DOCS_ARCHITECTURE.md` | 保留 | 当前文档树结构、职责和导航说明。 |
| `developer/DOCUMENTATION_STANDARDS.md` | 保留 | 文档元数据、命名、归档隔离和维护流程规范。 |
| `developer/HANDOVER.md` | 保留 | 文档维护职责和例行维护流程。 |

## 3. 活跃 Reports 文档

| 文档 | 处置 | 当前职责 |
| :--- | :--- | :--- |
| `reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | 保留 | 本阶段项目审查、归档判据、main 对比、输入输出差异和开发补强建议。 |
| `reports/DOCUMENTATION_STATUS_REPORT.md` | 保留 | 文档治理状态单一入口。 |
| `reports/FEATURE_STATUS_MATRIX.md` | 保留 | 2.0.0 当前功能支持矩阵。 |
| `reports/DP_VALIDATION_2.0.0.md` | 保留 | DP/DPA 示例级 SAI 验证和相关边界证据。 |
| `reports/IRC_INTEGRATION_REVIEW.md` | 保留 | Sella IRC 集成定位和受控边界说明。 |

## 4. 本阶段归档结果

| 文档 | 处置 | 判据 |
| :--- | :--- | :--- |
| `Calculator_Review.md` | 归档 | Calculator 结论已被用户配置参考、DP 验证报告和阶段审查报告吸收。 |
| `YAML_CONFIGURATION_REVIEW.md` | 归档 | YAML 配置治理结论已被 YAML 输入治理规范、用户配置参考和阶段审查报告吸收。 |

归档后的文件不再从活跃文档入口回链。需要查证历史过程时，应通过版本控制或归档目录直接检索。

## 5. 一致性复核

- 功能支持范围与发布说明一致：2.0.0 支持 NEB、AutoNEB、Dimer、Sella、D2S、Relax、Vibration、IRC；MD 尚未进入 `atst run`。
- YAML 治理与实现一致：`ConfigLoader.normalize()` 在分发前应用 schema 默认值和校验，非 calculator 变量文档由 schema 生成。
- Calculator 说明与实现一致：ABACUS 通过 `abacuslite`，DP 通过 `deepmd.calculator.DP`。
- 文档索引与当前文件位置一致：活跃索引不再指向已归档报告。

## 6. 后续维护要求

- 每次新增 workflow、calculator backend 或 YAML 变量时，同步更新用户文档、开发者治理文档、示例和测试。
- 每次新增或归档报告时，同步更新 `docs/index.md` 与本状态报告。
- 阶段性审查文档完成任务后，应先把结论吸收到长期文档或发布说明，再移出活跃 reports 集合。
