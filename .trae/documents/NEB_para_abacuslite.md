# NEB Image-Level Parallel Plan Merge Note

本文件中的关键信息已合并进入统一主文档：

- `.trae/documents/NEB_parallel_imple.md`

该主文档现统一包含以下内容：

- `abacuslite` 上游 NEB 示例确认与实现路线判断
- ASE / AutoNEB 并行设计约束
- v1 开发目标、方向与边界
- MPI bootstrap、topology 校验、image-index 目录策略
- endpoint / trajectory / cleanup 的 rank 0 同步要求
- 当前实现状态、环境要求、测试计划、文档更新要求

后续开发计划仅维护 `.trae/documents/NEB_parallel_imple.md`，避免并行维护多份计划造成信息分叉。
