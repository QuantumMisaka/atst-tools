# 文档系统架构与结构图

**版本**: 2.0.0
**日期**: 2026-05-15
**状态**: 维护
**责任人**: ATST-Tools maintainers

## 1. 目录层级
```text
docs/
├── index.md                            # 文档总入口
├── user/                               # 用户文档
│   ├── CLI_REFERENCE.md
│   ├── CONFIG_REFERENCE.md
│   └── USER_GUIDE_CN.md
├── developer/                          # 开发者文档
│   ├── DOCS_ARCHITECTURE.md
│   ├── DOCUMENTATION_STANDARDS.md
│   ├── HANDOVER.md
│   └── YAML_INPUT_GOVERNANCE.md
├── reports/                            # 审查、验收、状态报告
├── releases/                           # 发布说明
└── archive/                            # 归档文档
```

## 2. 角色与定位
- **用户向导**：面向最终用户，提供安装、运行指南及示例索引。
- **路线与计划**：面向管理者与开发者，统一项目状态、明确阶段目标与检查项。
- **评估与迁移**：面向旧版用户与维护者，提供 legacy 代码清单与功能差距闭环。
- **规范与模板**：面向文档编写者，统一格式、命名与元数据标准。
- **发布与归档**：面向版本管理，提供版本历史与查找入口。

## 3. 导航与索引
- **主入口**：[docs/index.md](../index.md)
- **用户向导**：[USER_GUIDE_CN.md](../user/USER_GUIDE_CN.md)
- **状态追踪**：[DOCUMENTATION_STATUS_REPORT.md](../reports/DOCUMENTATION_STATUS_REPORT.md)
- **阶段审查**：[PROJECT_REFACTOR_REVIEW_2026-05-15.md](../reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md)
- **开发规范**：[DOCUMENTATION_STANDARDS.md](DOCUMENTATION_STANDARDS.md)
- **YAML 输入治理**：[YAML_INPUT_GOVERNANCE.md](YAML_INPUT_GOVERNANCE.md)
- **发布说明**：[RELEASE_NOTES_2.0.0.md](../releases/RELEASE_NOTES_2.0.0.md)
