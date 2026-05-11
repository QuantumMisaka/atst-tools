# Tasks
- [x] Task 1: 建立文档审查清单并完成现状盘点
  - [x] SubTask 1.1: 盘点 `docs/index.md`、`docs/developer`、`docs/reports`、`docs/releases` 的文档角色与入口关系
  - [x] SubTask 1.2: 对照当前实现状态，识别文档声称与实现不一致项
  - [x] SubTask 1.3: 形成“核心文档位置与状态一致性”结论

- [x] Task 2: 形成 developer/reports 归档分类决策
  - [x] SubTask 2.1: 对 `docs/developer` 输出逐文档处置：保留 / 归档 / 保留并改写
  - [x] SubTask 2.2: 对 `docs/reports` 输出逐文档处置：保留 / 归档 / 提炼到发布说明
  - [x] SubTask 2.3: 给出每个处置项的判据与理由（时效性、重复性、是否为基线事实）

- [x] Task 3: 更新发布文档收敛结构
  - [x] SubTask 3.1: 在 `docs/releases/RC_RELEASE_NOTES_2.0.0-rc.md` 增补固定章节模板（功能状态、验收回归、已知限制、兼容迁移、文档治理结论）
  - [x] SubTask 3.2: 从 `docs/reports` 提炼可发布结论并写入对应章节
  - [x] SubTask 3.3: 保持原始证据链可追踪（在发布说明中引用来源报告）

- [x] Task 4: 执行归档与导航收敛
  - [x] SubTask 4.1: 按分类决策移动应归档文档至 `docs/archive/`
  - [x] SubTask 4.2: 更新 `docs/index.md`，仅保留有效入口并新增“历史归档”导航
  - [x] SubTask 4.3: 校验相对链接可用，避免失效跳转

- [x] Task 5: 验证与交付
  - [x] SubTask 5.1: 逐项核对 `checklist.md` 全部通过
  - [x] SubTask 5.2: 进行一次文档一致性复核（核心功能状态、发布结论、归档结果一致）
  - [x] SubTask 5.3: 产出最终审查结论（包含归档清单与发布写入清单）

# Task Dependencies
- Task 2 依赖 Task 1（先有盘点与一致性结论，才能分类）。
- Task 3 依赖 Task 2（先完成分类与提炼边界，才能写发布说明）。
- Task 4 依赖 Task 2 与 Task 3（归档与导航需与发布收敛同步）。
- Task 5 依赖 Task 1-4。
