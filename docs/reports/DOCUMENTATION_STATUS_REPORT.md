# 文档治理状态报告

**版本**: 2026-06-10
**日期**: 2026-06-10
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档是 ATST-Tools 当前文档治理状态的单一入口。它记录活跃文档职责、reports
L1-L4 分级、归档判据和本轮待删除复核结果。

## 1. 核心结论

- 本轮治理依据是已接受的
  `docs/superpowers/specs/2026-05-28-documentation-governance-design.md`。
- 活跃入口收敛到 `README.md`、`docs/index.md`、用户文档、开发者文档、当前状态
  reports 和 release notes。
- 当前 release 入口为 `docs/releases/RELEASE_NOTES_2.1.1.md`；2.0.0、2.0.1、2.0.2 和
  2.1.0 release notes 保留为历史版本说明。
- `docs/reports/FEATURE_STATUS_MATRIX.md` 是当前功能支持矩阵，覆盖 NEB/AutoNEB、
  Dimer、Sella、CCQN、D2S+CCQN、Relax、Vibration/TS validation、IRC、MD、
  artifact manifest、MPI image-level parallelism，并明确 GA 未支持。
- `docs/archive/pending_delete/` 是待删除复核区；本轮只移动和记录，不最终删除。

## 2. 活跃 User 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/user/USER_GUIDE_CN.md` | guide | 中文项目目标、10 分钟快速开始、后端说明、功能矩阵和参数入口。 |
| `docs/user/CLI_REFERENCE.md` | reference | `atst` CLI、轻量 post/summary/config/abacus 工具。 |
| `docs/user/CONFIG_REFERENCE.md` | reference | 手写 YAML 语义、workflow 行为、calculator 配置说明。 |
| `docs/user/YAML_INPUT_VARIABLES.md` | reference | 由 schema 生成的非 calculator YAML 字段总表。 |
| `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` | guide | ABACUS/abacuslite wrapper 边界、MPI/mpi4py 注意事项。 |

## 3. 活跃 Developer 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/developer/DOCS_ARCHITECTURE.md` | guide | 文档目录职责、目标读者、生命周期类型和导航原则。 |
| `docs/developer/DOCUMENTATION_STANDARDS.md` | guide | 元数据、生命周期、reports 分级、更新映射、归档流程和检查命令。 |
| `docs/developer/HANDOVER.md` | guide | workflow、YAML、CLI、backend、example、report、release 变更 checklist。 |
| `docs/developer/YAML_INPUT_GOVERNANCE.md` | guide | YAML schema、变量新增、文档导出和测试治理规则。 |
| `docs/developer/PYPI_RELEASE_AUTOMATION.md` | guide | PyPI 发布自动化流程。 |

## 4. Reports L1-L4 账本

### L1: 状态入口

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/FEATURE_STATUS_MATRIX.md` | 当前功能支持范围和限制。 |
| `docs/reports/DOCUMENTATION_STATUS_REPORT.md` | 当前文档治理账本。 |

### L2: 当前证据

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/DP_VALIDATION_2.0.0.md` | DP/DPA 示例级 SAI 验证和相关边界证据。 |
| `docs/reports/DPA3_DP_EXAMPLES_VALIDATION_2026-05-28.md` | DPA-3.1 DP examples 全量 config_dp runtime 验证、模型来源和 checksum 证据。 |
| `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md` | examples 与 main/LTS 3.10.1 对齐验证证据。 |
| `docs/reports/ISSUE_25_AUTONEB_FMAX_FIX_REPORT_2026-05-22.md` | Issue #25 最终修复、严格验证和 close response 依据。 |
| `docs/reports/CCQN_ABACUSLITE_VALIDATION_2026-05-26.md` | CCQN ABACUSLite smoke 验证证据。 |
| `docs/reports/MPI4PY_ASE_NEB_PARALLEL_ATST_SUMMARY_2026-05-27.md` | MPI image-level NEB/AutoNEB 并行设计、约束和验证总结。 |
| `docs/reports/P0_P1_EXAMPLE_RUNTIME_VALIDATION_2026-05-28.md` | P0/P1 示例 runtime 验证和当前示例扩展证据。 |
| `docs/reports/NEB_IMAGE_PARALLEL_E2E_VALIDATION_2026-05-29.md` | Cy-Pt image-level NEB/AutoNEB SAI 端到端验证、barrier 对比和 nested MPI 证据。 |
| `docs/reports/ZN_SEGMENTED_NEB_RUNTIME_STATUS_2026-05-30.md` | Zn migration 分段 NEB/AutoNEB runtime 状态和唯一运行证据。 |
| `docs/reports/TWO_STAGE_NEB_LTS3101_VALIDATION_2026-06-04.md` | 01/02/13 two-stage NEB 在 ABACUS LTS 3.10.1 和 4V100 上的实算能垒复现、串并行一致性和迭代步数证据。 |

### L3: 当前主题审查

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/IRC_INTEGRATION_REVIEW.md` | Sella IRC 集成定位和受控边界说明。 |
| `docs/reports/NEB_AUTONEB_NATIVE_ASE_BACKEND_REVIEW_2026-05-23.md` | native ASE backend selector 当前边界与默认迁移条件。 |
| `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md` | examples 复现复查和 abacuslite fallback 审计。 |
| `docs/reports/FAST_IDPP_ALGORITHM_COMPARISON_AND_FIX_2026-05-25.md` | FastIDPP 修复依据和 D2S 路径生成边界。 |
| `docs/reports/MACE_REACTION_KIT_TO_ATST_TOOLS_TRANSFER_REVIEW_2026-05-27.html` | MACE-Reaction-Kit P0/P1 核心完成状态和未来增强边界。 |
| `docs/reports/ATST_TOOLS_NEB_ASE_COMPARISON_REVIEW_2026-05-18.md` | ASE 3.28.0 与 ATST NEB/AutoNEB/Dimer 对齐审查细节。 |
| `docs/reports/ABACUS_STRU_IO_ASE_FORMAT_COMPATIBILITY_2026-06-04.md` | ABACUS STRU read/write 与 `ase-abacus` ASE I/O format 的 API/语义兼容性和功能点覆盖审查。 |
| `docs/reports/UNIT_TEST_MAINTENANCE_2026-06-10.md` | 单元测试维护、legacy NEB script 清理和默认测试边界审查。 |

### L4: 历史或已被取代材料

L4 材料不保留在活跃 `docs/reports/` 或 `docs/developer/plans/` 中。本轮移动到
`docs/archive/pending_delete/` 的文件见第 6 节。

## 5. 归档目录规则

| 目录 | 当前职责 | 规则 |
| :--- | :--- | :--- |
| `docs/archive/` | 有历史审计价值但不指导当前工作的文档 | 不作为 README 或 `docs/index.md` 的用户/开发者入口。 |
| `docs/archive/pending_delete/` | 已过时但待最终删除确认的文件 | 删除前确认无活跃链接、无唯一验证证据、结论已被吸收。 |

## 6. 本轮待删除复核结果

| 原路径 | 新路径 | 判据 |
| :--- | :--- | :--- |
| `docs/developer/plans/native-ase-backend.md` | `docs/archive/pending_delete/plans/native-ase-backend.md` | 计划主体已落地，后续边界由 native ASE backend review、用户配置文档和测试覆盖。 |
| `docs/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | `docs/archive/pending_delete/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | 仍以旧 refactor 阶段作为当前基线，已落后于 CCQN、并行 NEB、artifact manifest 等当前进展。 |
| `docs/reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md` | `docs/archive/pending_delete/reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md` | 阶段性 UX 任务已由用户文档、CLI reference 和 artifact manifest 实现吸收。 |
| `docs/reports/CY_PT_AUTONEB_MAIN_REPRODUCTION_REVIEW_2026-05-18.md` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_MAIN_REPRODUCTION_REVIEW_2026-05-18.md` | 早期负向复现结论已被后续 Issue #25 修复和严格验证取代。 |
| `docs/reports/CY_PT_AUTONEB_MAIN_ALIGNED_LTS3101_VALIDATION_2026-05-19.md` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_MAIN_ALIGNED_LTS3101_VALIDATION_2026-05-19.md` | 记录未达标的早期 main-aligned run，已被最终 strict validation 取代。 |
| `docs/reports/CY_PT_AUTONEB_FAILURE_ROOT_CAUSE_REVIEW_2026-05-18.html` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_FAILURE_ROOT_CAUSE_REVIEW_2026-05-18.html` | 根因分析已被最终修复报告吸收，继续活跃保存会与当前可复现结论冲突。 |
| `docs/reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md` | `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md` | 预修复评估和 validation plan 已被最终修复报告取代。 |
| `docs/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md` | `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md` | 早期 SAI validation 含阶段结论，已被最终 Issue #25 fix report 取代。 |
| `docs/reports/ZN_MIGRATION_NEB_ABACUS_VALIDATION_2026-05-26.md` | `docs/archive/pending_delete/reports/ZN_MIGRATION_NEB_ABACUS_VALIDATION_2026-05-26.md` | 初版单路径 Zn validation 状态已落后，后续分段 runtime 证据由 active Zn segmented report 保存。 |
| `docs/reports/EXAMPLES_INITIAL_GUESS_AUDIT_2026-05-26.md` | `docs/archive/pending_delete/reports/EXAMPLES_INITIAL_GUESS_AUDIT_2026-05-26.md` | 初猜审计结论已被 CCQN/Sella perturbed-input 验证、examples tests 和 reference results 吸收。 |
| `docs/reports/UNIT_TEST_COVERAGE_REVIEW_2026-05-25.md` | `docs/archive/pending_delete/reports/UNIT_TEST_COVERAGE_REVIEW_2026-05-25.md` | 覆盖率审查已落后于 P0/P1、MPI parallel 和 DP reference 测试补强，当前状态以测试套件和 feature reports 为准。 |
| `.trae/documents/CCQN-plan.md` | `docs/archive/pending_delete/trae/documents/CCQN-plan.md` | CCQN perturbed-input plan 已由 CCQN validation report、examples/reference results 和 tests 吸收。 |
| `.trae/documents/NEB_para_abacuslite.md` | `docs/archive/pending_delete/trae/documents/NEB_para_abacuslite.md` | 临时合并说明已被统一 NEB parallel plan 和正式 MPI/E2E reports 取代。 |
| `.trae/documents/NEB_parallel_imple.md` | `docs/archive/pending_delete/trae/documents/NEB_parallel_imple.md` | NEB/AutoNEB image-level parallel 实现已落地，后续依据为 MPI summary、E2E validation、用户文档和测试。 |
| `.trae/documents/Zn-NEB.md` and `.trae/specs/plan-zn-neb-calculations/*` | `docs/archive/pending_delete/trae/zn-neb/README.md` | 初版 Zn 单路径计划资料的统一入口，链接 active segmented runtime report。 |
| `.trae/documents/Zn-NEB.md` | `docs/archive/pending_delete/trae/zn-neb/Zn-NEB.md` | 初版 Zn 单路径计划已被分段 Zn runtime report 取代。 |
| `.trae/specs/plan-zn-neb-calculations/checklist.md` | `docs/archive/pending_delete/trae/zn-neb/checklist.md` | 初始 Zn spec checklist 已被分段方案取代，未完成项不再代表当前执行路径。 |
| `.trae/specs/plan-zn-neb-calculations/spec.md` | `docs/archive/pending_delete/trae/zn-neb/spec.md` | 初始 Zn calculation spec 已被分段方案取代。 |
| `.trae/specs/plan-zn-neb-calculations/tasks.md` | `docs/archive/pending_delete/trae/zn-neb/tasks.md` | 初始 Zn task list 已被分段 runtime report 取代。 |

## 7. 后续维护要求

- 每次新增 workflow、calculator backend 或 YAML 变量时，同步更新用户文档、开发者治理文档、示例和测试。
- 每次新增、归档或移动 report 时，同步更新本账本；只有核心入口才加入 `docs/index.md`。
- 阶段性审查文档完成任务后，先把结论吸收到长期文档或 release notes，再移出活跃集合。
- `pending_delete/` 中的文件在最终删除前，不得从活跃入口链接。
- 文档治理变更后运行 `python scripts/check_docs_governance.py`，确认活跃 reports
  账本、metadata、active links、pending-delete inventory 和 HTML report 基础解析一致。
