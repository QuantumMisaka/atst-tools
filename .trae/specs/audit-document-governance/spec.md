# 文档治理审查与发布收敛 Spec

## Why
当前 `docs/developer` 与 `docs/reports` 同时包含长期文档、阶段性审查与历史计划，边界不清。需要建立可执行的治理判据，确保核心文档位置正确且内容与已实现功能一致。

## What Changes
- 建立“核心文档有效性审查”流程，验证索引、位置、职责与实现状态一致性。
- 建立 `docs/developer` 与 `docs/reports` 的归档判据与分类清单（保留/归档/迁移摘要）。
- 定义发布层收敛规则：将跨文档的阶段结论沉淀到 `docs/releases/RC_RELEASE_NOTES_2.0.0-rc.md` 的固定章节。
- 规范 `docs/index.md` 导航，仅保留当前有效文档入口，历史文档通过 `docs/archive/` 暴露。

## Impact
- Affected specs: 文档治理流程、发布文档维护流程、归档策略。
- Affected code: `docs/index.md`、`docs/developer/*.md`、`docs/reports/*.md`、`docs/releases/RC_RELEASE_NOTES_2.0.0-rc.md`、`docs/archive/`。

## ADDED Requirements
### Requirement: 文档治理机制可验证
系统 SHALL 提供一套可重复执行的文档审查机制，用于确认核心文档“位置正确 + 内容正确 + 状态可追踪”。

#### Scenario: 核心文档位置与职责检查
- **WHEN** 维护者执行文档审查
- **THEN** 可依据明确清单验证 `index/user/developer/reports/releases/archive` 的定位是否符合治理规范

#### Scenario: 功能状态一致性检查
- **WHEN** 维护者比对报告与实现状态
- **THEN** 可识别“文档声称已完成但实现未完成”或“实现已完成但文档未更新”的漂移项

### Requirement: 归档分类规则
系统 SHALL 对 `docs/developer` 与 `docs/reports` 文档给出“保留、归档、发布提炼”三类处置决策，并记录决策理由。

#### Scenario: 阶段性计划归档
- **WHEN** 计划文档所述任务已结束或被后续计划替代
- **THEN** 该文档进入 `docs/archive/`，并在索引中以“历史计划”归档入口呈现

#### Scenario: 审查报告发布提炼
- **WHEN** `reports` 中存在重复或重叠的阶段审查结论
- **THEN** 将可发布信息提炼到发布说明固定章节，原报告保留或归档按时效判定

### Requirement: 发布报告固定章节
系统 SHALL 在 `docs/releases/RC_RELEASE_NOTES_2.0.0-rc.md` 中维护固定章节，承接来自 `reports` 的最终发布信息。

#### Scenario: 结果收敛
- **WHEN** 维护者整理本轮审查结论
- **THEN** 发布说明至少包含“功能实现状态、验收/回归结果、已知限制、迁移与兼容性、文档治理结论”五类信息

## MODIFIED Requirements
### Requirement: 文档索引入口管理
`docs/index.md` 必须仅呈现当前有效入口；历史文档不得与当前入口混排，而应通过 `archive` 分区进行访问。

## REMOVED Requirements
### Requirement: 将一次性审查文档长期作为一级导航
**Reason**: 一次性审查文档时效性强，长期占据一级入口会降低导航清晰度并放大状态漂移风险。  
**Migration**: 将其结论提炼进 `releases` 对应章节；原文档按“仍在生效/仅历史参考”判定保留于 `reports` 或迁移到 `archive`。
