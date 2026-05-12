# 文档治理审查报告（audit-document-governance）

**日期**: 2026-05-11  
**范围**: `docs/index.md`、`docs/developer/**`、`docs/reports/**`、`docs/releases/RC_RELEASE_NOTES_2.0.0-rc.md`

## 1. 核心结论

- 文档位置正确：用户文档、开发文档、报告、发布说明、归档均在既定目录。
- 文档职责清晰：`releases` 承担对外收敛结论，`reports` 保留证据链，`archive` 存放历史阶段材料。
- 状态可追踪：本报告给出逐文档处置（保留/归档/保留并改写/提炼到发布说明）及判据。
- 一致性复核通过：核心功能状态、回归结论、已知限制在 `developer`/`reports`/`releases` 间无明显冲突。

## 2. developer 文档分类结果

| 文档 | 处置 | 判据与理由 |
| :--- | :--- | :--- |
| `developer/YAML_INPUT_GOVERNANCE.md` | 保留 | 作为当前 YAML 输入治理与新增 `atst run` 功能点的开发规范入口。 |
| `developer/DOCS_ARCHITECTURE.md` | 保留 | 文档信息架构说明，属于长期维护元文档。 |
| `developer/DOCUMENTATION_STANDARDS.md` | 保留 | 文档编写与维护标准，长期有效。 |
| `developer/HANDOVER.md` | 保留并改写 | 原文存在失效引用与过时职责描述，需与当前索引同步。 |
| `developer/plans/CLI_DEV.md` | 归档 | 阶段性改造计划，已由实现与发布文档吸收。 |
| `developer/plans/ITERATION_1_PLAN.md` | 归档 | 时间窗口已结束，属历史冲刺计划。 |
| `developer/plans/DEVELOPMENT_PLAN_2026.md` | 归档 | 草案级长期规划，内容与现状偏差大。 |
| `developer/plans/REFACTORING_PLAN_DETAILED.md` | 归档 | 重构阶段计划文档，已完成且被后续文档取代。 |

## 3. reports 文档分类结果

| 文档 | 处置 | 判据与理由 |
| :--- | :--- | :--- |
| `reports/FEATURE_STATUS_MATRIX.md` | 保留 | 版本能力矩阵，属于发布判断基线事实。 |
| `reports/REFACTORING_ACCEPTANCE_REPORT.md` | 保留 | 端到端验收证据链核心文档。 |
| `reports/EXAMPLES_REGRESSION_2026-05-11.md` | 保留 | SAI 实算回归证据与已知问题（IRC）来源。 |
| `reports/REVIEW_ENHANCEMENTS_2026-05-11.md` | 保留 | 本轮增强实现与验证摘要，仍具追踪价值。 |
| `reports/DOCUMENTATION_STATUS_REPORT.md` | 保留并改写 | 作为文档治理单一入口，承载本次审查结论。 |
| `reports/ACCEPTANCE_2.0.0rc_CN.md` | 提炼到发布说明后归档 | 内容与发布结论高度重叠，保留历史证据即可。 |
| `reports/REVIEW_2026-05-10_2000.md` | 归档 | 过程中间审查稿，已被后续报告与实现覆盖。 |
| `reports/REVIEW_CLI_202605102252.md` | 归档 | CLI 决策中间稿，内容已沉淀进用户文档与实现。 |
| `reports/NEB_CLI_USAGE.md` | 归档 | 专题审查长文，关键结论已被增强报告吸收。 |

## 4. 写入发布说明内容清单

以下内容已提炼并写入 `releases/RC_RELEASE_NOTES_2.0.0-rc.md` 固定章节：

- 功能状态：来自 `FEATURE_STATUS_MATRIX.md` 与 `REFACTORING_ACCEPTANCE_REPORT.md`。
- 验收回归：来自 `REFACTORING_ACCEPTANCE_REPORT.md` 与 `EXAMPLES_REGRESSION_2026-05-11.md`。
- 已知限制：来自 `EXAMPLES_REGRESSION_2026-05-11.md`（IRC 可靠性）与 RC 验收报告。
- 兼容迁移：来自 `REFACTORING_ACCEPTANCE_REPORT.md` 的 legacy 兼容与 CLI/YAML 迁移事实。
- 文档治理结论：来自本报告的分类、归档与导航收敛决议。

## 5. 应归档文档清单

归档文档只作为历史记录保存在归档目录，不从活跃用户、开发者、报告或发布文档回链。

## 6. 一致性复核

- `reports` 中“功能支持范围”与 `releases` 中“功能状态”一致：RC 支持 NEB/AutoNEB/Dimer/Sella/D2S/Relax/Vibration，MD 未支持。
- `reports` 中“回归结论”与 `releases` 中“验收回归”一致：除 IRC 外其余核心示例在 SAI ABACUS 实算通过。
- `developer` 中架构与规范描述与当前代码组织及 CLI 入口一致。
