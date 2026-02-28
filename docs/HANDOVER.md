# 文档系统交接与维护

## 1. 维护职责
- **路线与计划**：架构负责人（REFACTORING_GUIDE.md, REFACTORING_PLAN_DETAILED.md）
- **用户向导与示例**：工作流维护者（ATST_Tools_Documentation_CN.md）
- **发布说明与归档**：版本管理员（releases/RC_RELEASE_NOTES_<version>.md）

## 2. 例行流程
- **每次功能变更 PR**：更新相关文档及 `DOCUMENTATION_STATUS_REPORT.md`。
- **RC 冻结**：统一文档标签为 RC，输出发布说明并归档到 `releases/`。
- **正式发布**：将 RC 发布说明转换为 Release Notes，更新状态为“已发布”。

## 3. 工具与检查项
- **预提交检查**：
  - 链接有效性：所有 Markdown 链接是否指向存在的文件。
  - 格式检查：使用 `markdownlint` 或类似工具。
- **文档状态追踪**：以 `DOCUMENTATION_STATUS_REPORT.md` 为单一信息入口，定期刷新。

## 4. 紧急修订
- **发现与实现不一致**：立即修正文档状态，并在下一版补齐示例或测试。
- **关键路径错误**：优先修复安装/运行指南中的路径错误。
