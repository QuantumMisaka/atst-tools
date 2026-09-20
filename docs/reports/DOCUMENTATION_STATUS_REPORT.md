# 文档治理状态报告

**版本**: 2.2.6
**日期**: 2026-09-17
**状态**: 已发布（PyPI clean-install 已验证）
**责任人**: ATST-Tools maintainers

本文档是 ATST-Tools 当前文档治理状态的单一入口。它记录活跃文档职责、reports
L1-L4 分级、归档判据和本轮待删除复核结果。

## 1. 核心结论

- 2026-09-20（未发布开发）：CCQN manifest 增加实际方向来源、1-based 反应键/元素和初始结构身份；PRFO 修复半径更新晚一轮及使用更新后 Hessian 评价上一实际步的时序问题。用户语义见 `CONFIG_REFERENCE` 的 CCQN 小节；本地单元测试 875 passed / 2 skipped。集成方 app-tools 的 `2026-09-20-ccqn-chemical-semantics-toolbox-runtime-plan.md` 保存映射消费、Toolbox 分发试验和独立复核；无 PyPI/SIF/平台发布或真实 DFT 验收。

- 2026-09-20（未发布开发）：Sella 增加默认开启、可关闭的轻量 JSONL 事件；区分初始状态、实际优化迭代、直接观测的数值 Hessian 探测及未分类帧。配置与旧产物边界见 `CONFIG_REFERENCE` 的 Sella 小节；本批不升级 SIF/生产环境、不实施挂载，也不开展真实 ABACUS 计算。验证进度由集成方 app-tools 的 `2026-09-20-sella-observability-plan.md` 留存。


- 2026-09-17（发布后记录）：2.2.6 已从 release commit
  `a633f06b9375e3f34dbd87f90f40ec6271b29cd4` 推送并发布。GitHub
  [Tests](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052859)、
  [abacuslite](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052923)
  和 [Publish](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206151239)
  均成功；PyPI 两个 artifact、上传时间和 hash 见 2.2.6 release notes。官方无缓存
  clean-install、CLI/API、依赖与安装位置核验均通过；SIF/SAI/platform runtime 与真实
  ABACUS/MPI 验收未执行。
- 2026-09-17（发布前记录）：2.2.6 release candidate 的版本元数据、用户边界与导航已切换。
  候选范围：优化器收敛事实持久化（严格三态 `converged` + stage 身份字段，Sella/Relax/AutoNEB
  自写 owner manifest，API synthesized 显式 `converged: null`）、运行期诊断统一英文及机械门禁、
  稳定 API 阶段契约与交接 fixtures。本地全量测试、文档治理与 clean-wheel API 门禁已通过；
  tag、CI、PyPI、SIF/SAI 与真实 ABACUS/MPI 运行时验收尚未执行；不得把本候选描述为已发布。
- 2026-09-17：执行 [workflow convergence handoff plan](../superpowers/plans/2026-09-17-workflow-convergence-handoff-plan.md)（`feature/workflow-convergence`，基于 `origin/main` `cf86790`）：共享 convergence helper（三态记录 + 英文 advisory + root-only 发射）落地；Sella/CCQN/Relax/IRC/NEB/AutoNEB/D2S 的优化器返回值与阶段事实已持久化，Sella/Relax 也自写默认路径 manifest，复合工作流（D2S/AutoNEB）由顶层 workflow 唯一拥有 manifest；API synthesized 阶段显式 `converged: null` 并在 `PYTHON_API_REFERENCE` 记录阶段契约；运行期诊断全英文并有 AST 机械门禁；A4 交接 fixtures（`docs/reports/data/convergence_fixtures_20260917/`）已生成并有契约测试；clean-wheel 门禁验证了安装包中的三态阶段写出。剩余：Paimon 联合消费验收（由其开发者推进）、示例 curated 产物刷新（需要授权的真实 ABACUS/SAI 运行）、A6 下一 patch 发布（`FEATURE_STATUS_MATRIX` 与 release notes 在发布准备时更新），以及真实 MPI/ABACUS 运行时验收。本记录不表示发布或运行时验收完成。
- 2026-09-17：计划归档收口：7 个已在发布/文档/测试中吸收结论的旧计划与 2 个 `docs/developer/plans/` 遗留文件移入 `docs/archive/pending_delete/plans/`；活跃计划目录只保留仍待执行的计划，并要求在账本登记（`check_docs_governance.py` 机械校验）。

- 本轮治理依据是已接受的
  `docs/superpowers/specs/2026-05-28-documentation-governance-design.md`。
- 活跃入口收敛到 `README.md`、`docs/index.md`、用户文档、开发者文档、当前状态
  reports 和 release notes。
- 当前 release 入口为 `docs/releases/RELEASE_NOTES_2.2.6.md`（release candidate，未发布）；
  tag、CI、PyPI 与 SIF/SAI runtime 证据待维护者执行。此前已由 `v2.2.5` / `v2.2.4`
  发布的 release notes 保留为历史版本说明。
- `docs/reports/FEATURE_STATUS_MATRIX.md` 是当前功能支持矩阵，覆盖 NEB/AutoNEB、
  Dimer、Sella、CCQN、D2S+CCQN、Relax、Vibration/TS validation、IRC、MD、
  experimental DMF、artifact manifest、MPI image-level parallelism，并明确 GA 未支持。
- `docs/archive/pending_delete/` 是待删除复核区；本轮只移动和记录，不最终删除。
- 2026-08-09：`endpoint_singlepoint` 语义更新（`auto` 只信任 ATST 标记端点并重算
  未标记/外来结果；`never` 保留用户提供的可读端点结果）已同步至
  `config_schema.py`（重新生成 `YAML_INPUT_VARIABLES.md`）、
  `docs/user/CONFIG_REFERENCE.md`（含 `atst_endpoint_result` 信任标记机制说明）与
  `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`。
- 2026-08-12：2.2.3 阶段性发布（`atst prepare` 反向配置生成 + 轨迹应力保留）。
  新增 `atst prepare` 顶层命令与 `build_config_from_abacus_dir` 稳定 API，文档同步至
  `docs/user/CLI_REFERENCE.md`、`docs/user/USER_GUIDE_CN.md`、
  `docs/user/CONFIG_REFERENCE.md` 与 `docs/reports/FEATURE_STATUS_MATRIX.md`；
  新增 `docs/releases/RELEASE_NOTES_2.2.3.md`。YAML schema 未变，不重新生成
  `YAML_INPUT_VARIABLES.md`。
- 2026-09-05：GitHub 治理与发布门禁已在本地实现 exact tag-to-HEAD 绑定；2.2.3
  仍为已发布稳定版本，当前 main 作为未发布工作，旧 tag 不代表当前 main。
  当前模型家族独立审查作为正常终审；跨家族审查是维护者按需判断的 owner-judged
  advisory evidence，不构成合入、推送或发布门禁。发布、推送、外部设置和跨渠道
  渲染检查仍待维护者执行。
- 2026-09-06（发布前记录）：2.2.4 release candidate 已准备；active version metadata 和导航已切换
  至 2.2.4，补充 portable MPI 缺失依赖诊断与 Serial/DP/image-parallel 安装边界。
  `parallel` extra 已在 2.2.3 存在，本候选不承诺修复任意 MPI ABI 崩溃；exact tag 和
  PyPI 发布确认仍待维护者执行。
- 2026-09-06（发布后结案）：`v2.2.4` 指向
  `eaac64a76215e33588d362a788c138464519a7ba`；GitHub Tests run `33980730827`、
  abacuslite run `33980730831` 和 PyPI publication run `33980788260` 成功。PyPI
  JSON 列出 wheel 与 sdist，渲染页显示四个绝对 GitHub/Gitee 用户指南与示例链接；
  Gitee 渲染按维护者明确指示排除。clean-install、CLI/API 版本和 base 安装无
  `mpi4py` 已完成验证。tag commit 同时登记了 point-KPT parser CI drift 修复。
  PyPI 已上传 README 不可变，仍保留发布前 candidate wording；这是已知 cosmetic
  限制，仓库 README 已更新，不触发新 patch、retag 或 republish。
  [GitHub release](https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.2.4)
  已创建。
- 2026-09-16（发布前记录）：2.2.5 release candidate 的 active version metadata、
  用户边界和导航已切换。候选范围包括 abacuslite 的 PBC-aware SCF 帧身份校验：在
  统一 ASE 原子序、Cartesian Å 和晶胞后接受整数晶格平移，反向选择最新匹配帧；真实
  错结构、错胞、错序、数量/shape/finite、奇异晶胞和 malformed frame 继续
  fail-closed。native relax/md/MD_dump 仍为末帧语义，不新增配置开关。候选同时保留
  Sella、CCQN、Sella IRC 各方向及最终 NEB 的确定性未收敛 advisory 语义：不改变完成
  返回、退出码或 manifest 状态，也不把完成误报为科学收敛。代码回归、snapshot/package
  checks、exact tag、CI、PyPI 以及 SIF/SAI 验证均尚未完成；不得把本候选描述为已发布或
  已完成运行时验收。
- 2026-09-16（发布后记录）：2.2.5 已从 release commit
  `4c966915c6f40984fc85806869f4766ecdd6ffc9` 推送并发布。GitHub [Tests](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311728)、[abacuslite](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311733) 和 [Publish](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058399930) 均成功；PyPI 两个 artifact、上传时间和 hash 见 2.2.5 release notes。官方无缓存 clean-install、CLI/API、依赖检查及安装位置核验均通过；SIF/SAI/platform runtime 未执行。
- 2026-09-04：新增 GitHub 治理与发布门禁开发者入口，区分本地/CI 机械检查、
  AGENTS/SKILL 等治理契约的按需跨家族人工审阅，以及 GitHub/PyPI/Gitee 管理员和
  发布后责任；外部设置、发布动作和跨渠道渲染检查仍待维护者执行。

## 2. 活跃 User 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/user/USER_GUIDE_CN.md` | guide | 中文项目目标、10 分钟快速开始、后端说明、功能矩阵和参数入口。 |
| `docs/user/CLI_REFERENCE.md` | reference | `atst` CLI、轻量 post/summary/config/abacus 工具。 |
| `docs/user/PYTHON_API_REFERENCE.md` | reference | 稳定 `atst_tools.api` 十个 root imports（含 `build_config_from_abacus_dir` 的 NEB-only 配置生成边界）、CLI/API/runner 选择、JSON handoff、结果、artifact、MPI 和 backend delegation 边界；2026-09-20 补齐已存在导出的文档，不新增 API 或发行版本。 |
| `docs/user/CONFIG_REFERENCE.md` | reference | 手写 YAML 语义、workflow 行为、calculator 配置说明。 |
| `docs/user/YAML_INPUT_VARIABLES.md` | reference | 由 schema 生成的非 calculator YAML 字段总表。 |
| `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` | guide | ABACUS/abacuslite wrapper 边界、MPI/mpi4py 注意事项。 |

## 3. 活跃 Developer 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/developer/DOCS_ARCHITECTURE.md` | guide | 文档目录职责、目标读者、生命周期类型和导航原则。 |
| `docs/developer/DOCUMENTATION_STANDARDS.md` | guide | 元数据、生命周期、reports 分级、更新映射、归档流程和检查命令。 |
| `docs/developer/HANDOVER.md` | guide | workflow、YAML、CLI、backend、example、report、release 变更 checklist。 |
| `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md` | guide | 示例本地维护检查、SAI/Slurm 执行模式、curated-output 溯源和证据报告生命周期；不作为用户快速上手。 |
| `docs/developer/YAML_INPUT_GOVERNANCE.md` | guide | YAML schema、变量新增、文档导出和测试治理规则。 |
| `docs/developer/PYPI_RELEASE_AUTOMATION.md` | guide | PyPI 发布自动化流程。 |
| `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md` | guide | 本地/CI 机械门禁、按需跨家族治理审阅证据，以及 GitHub/PyPI/Gitee 外部管理员和发布后 checklist。 |

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
| `docs/reports/DMF_ENVIRONMENT_SMOKE_2026-06-18.md` | DMF cache-local 环境、`cyipopt`/IPOPT、vendored PyDMF NumPy/torch import 和 EMT runtime smoke 证据；不作为 P3 生产验证。 |
| `docs/reports/DMF_P3_VALIDATION_STAGING_2026-06-18.md` | DMF P3 两案例 production-validation staging、候选结构对比脚本、SAI sbatch 入口和剩余 runtime 验证要求；不作为完成证据。 |
| `docs/reports/DMF_P3_RUNTIME_VALIDATION_2026-06-18.md` | DMF P3 两案例 SAI runtime candidate-comparison 证据、Slurm job 525521、ABACUS/DP reference RMSD 对比和剩余 refinement/vibration/IRC 缺口。 |
| `docs/reports/DMF_P4_D2S_RUNTIME_SMOKE_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI runtime smoke 证据、Slurm job 526327、Sella refinement 接通和剩余 vibration/IRC/ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_VIBRATION_VALIDATION_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI focused vibration 验证证据、Slurm job 526601、Sella 后局域一虚频检查和剩余 IRC/ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_IRC_ENDPOINT_VALIDATION_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI descent-IRC endpoint connection 证据、Slurm job 526657、局域反应原子端点 RMSD 检查和剩余 ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_ABACUS_COMPARISON_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 ABACUS LTS 3.10.1 single-point comparison 证据；记录 job 526738 的初始 H2-Au raw-force failure、job 526921 的 H2-Au ABACUS Sella corrective refinement，以及 job 527093 的 refined constrained-force comparison pass。 |
| `docs/reports/DMF_RISK_REVIEW_2026-06-19.md` | DMF 风险审查和 DP Slurm 复现实证；记录 job 529051 中 wrapped endpoint、H index swap、fixed slab endpoint 三个 H2-Au 风险案例的 600 秒 timeout，以及 PBC+CFBENM schema guard 和 tmax rounded-index 未触发风险。 |

### L3: 当前主题审查

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/IRC_INTEGRATION_REVIEW.md` | Sella IRC 集成定位和受控边界说明。 |
| `docs/reports/NEB_AUTONEB_NATIVE_ASE_BACKEND_REVIEW_2026-05-23.md` | native ASE backend selector 当前边界与默认迁移条件。 |
| `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md` | examples 复现复查和 abacuslite fallback 审计。 |
| `docs/reports/FAST_IDPP_ALGORITHM_COMPARISON_AND_FIX_2026-05-25.md` | FastIDPP 修复依据和 D2S 路径生成边界。 |
| `docs/reports/MACE_REACTION_KIT_TO_ATST_TOOLS_TRANSFER_REVIEW_2026-05-27.html` | MACE-Reaction-Kit P0/P1 核心完成状态和未来增强边界。 |
| `docs/reports/DMF_DIRECT_MAXFLUX_RESEARCH_2026-06-17.html` | Direct MaxFlux/PyDMF 算法、周期体系边界和 ATST-Tools 实验性集成可行性研判。 |
| `docs/reports/ATST_TOOLS_NEB_ASE_COMPARISON_REVIEW_2026-05-18.md` | ASE 3.28.0 与 ATST NEB/AutoNEB/Dimer 对齐审查细节。 |
| `docs/reports/ABACUS_STRU_IO_ASE_FORMAT_COMPATIBILITY_2026-06-04.md` | ABACUS STRU read/write 与 `ase-abacus` ASE I/O format 的 API/语义兼容性和功能点覆盖审查。 |
| `docs/reports/UNIT_TEST_MAINTENANCE_2026-06-10.md` | 单元测试维护、legacy NEB script 清理和默认测试边界审查。 |
| `docs/reports/STABLE_PYTHON_API_CLI_COMPATIBILITY_FIX_2026-07-21.md` | Stable Python API 路由下的 `atst run` 日志、异常和 exit 兼容性修复及回归证据。 |

### Spec / Plan / Review 登记

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/superpowers/plans/2026-09-17-workflow-convergence-handoff-plan.md` | plan | 执行中：A2/A3/A4 代码与文档已落地（含 Sella/Relax durable record、synthesized unknown 语义、API 阶段契约与交接 fixtures）；剩余 Paimon 联合消费验收、A5/A6 收尾；不引入 Paimon/调度依赖。 |
| `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design.html` | spec | abacuslite 力读取一致性与跨仓维护设计（R1-R8 / D1-D8 / P1-P8），含 CI 基线单一事实源 `ABACUSLITE_SNAPSHOT.md`（R4/P6）与文档账本登记要求（R7/P8）。 |
| `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design-review.md` | review | spec 两轮审查结论与 P1-P8 缺口补强记录；全部结论已落入 spec。 |
| `docs/superpowers/plans/2026-08-04-abacuslite-force-read-and-cross-repo-plan.md` | plan | abacuslite 力读取一致性与跨仓维护分阶段实施计划（Task 1-9），含 Task 5 CI 基线单一事实源改造。 |
| `docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html` | spec | 本地实施完成，2.2.4 已发布；GitHub/PyPI 外部验收已登记，Gitee 渲染按授权范围排除：GitHub 规范源 / 维护者手动拉取的 Gitee 同内容只读镜像 / PyPI 分发、跨渠道用户入口、串行与 image-parallel MPI 安装分层，以及 SAI 维护证据边界设计。 |
| `docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html` | spec | 本地实施完成，待 GitHub 设置与发布后外部验收：GitHub 治理、按需跨家族审阅证据、发布前机械门禁和 GitHub/PyPI/Gitee 发布后责任边界。 |

### L4: 历史或已被取代材料

L4 材料不保留在活跃 `docs/reports/`、`docs/developer/plans/` 或
`docs/superpowers/plans/` 中。本轮移动到
`docs/archive/pending_delete/` 的文件见第 6 节。

## 5. 归档目录规则

| 目录 | 当前职责 | 规则 |
| :--- | :--- | :--- |
| `docs/archive/` | 有历史审计价值但不指导当前工作的文档 | 不作为 README 或 `docs/index.md` 的用户/开发者入口。 |
| `docs/archive/pending_delete/` | 已过时但待最终删除确认的文件 | 删除前确认无活跃链接、无唯一验证证据、结论已被吸收。 |

## 6. 本轮待删除复核结果

| 原路径 | 新路径 | 判据 |
| :--- | :--- | :--- |
| `docs/superpowers/plans/2026-07-02-abacuslite-backend-upstream-issue-fixes.md` | `docs/archive/pending_delete/plans/2026-07-02-abacuslite-backend-upstream-issue-fixes.md` | 计划自记 implementation 完成；vendored 补丁身份与上游同步纪律由 `PATCHES.md`、`ABACUSLITE_SNAPSHOT.md` 和 2026-08-04 跨仓计划承载。 |
| `docs/superpowers/plans/2026-07-05-atst-cli-banner.md` | `docs/archive/pending_delete/plans/2026-07-05-atst-cli-banner.md` | `atst banner` 已发布并有 CLI 测试与用户文档覆盖。 |
| `docs/superpowers/plans/2026-07-05-ci-test-development.md` | `docs/archive/pending_delete/plans/2026-07-05-ci-test-development.md` | snapshot-drift checker、abacuslite 工作流和通用 PR 测试工作流已上线；结论由 HANDOVER 与 CI 契约承载。 |
| `docs/superpowers/plans/2026-07-22-abacus-agent-atst-api-adoption.md` | `docs/archive/pending_delete/plans/2026-07-22-abacus-agent-atst-api-adoption.md` | runner 消费已落地：toolbox 通过 `python -m atst_tools.api.runner` 与 JSON handoff 接入。 |
| `docs/superpowers/plans/2026-09-04-user-distribution-and-mpi-installation.md` | `docs/archive/pending_delete/plans/2026-09-04-user-distribution-and-mpi-installation.md` | 执行完成并已发布 2.2.4；结论已吸收到 README、用户指南和 release notes。 |
| `docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md` | `docs/archive/pending_delete/plans/2026-09-04-github-governance-and-release-gates.md` | 仓库侧治理门禁已实施并被 2.2.4/2.2.5 发布实际使用；剩余管理员设置不在仓库可验证范围。 |
| `docs/superpowers/plans/2026-09-16-abacuslite-periodic-frame-validation-225-release.md` | `docs/archive/pending_delete/plans/2026-09-16-abacuslite-periodic-frame-validation-225-release.md` | 已随 2.2.5 发布完成；证据保存在 release notes 与账本发布记录。 |
| `docs/developer/plans/DMF-integrate-and-test-plan.md` | `docs/archive/pending_delete/plans/DMF-integrate-and-test-plan.md` | DMF 已作为 experimental workflow 与 D2S rough method 落地，当前边界由 FEATURE_STATUS_MATRIX 和 DMF 报告承载。 |
| `docs/developer/plans/Direct-MaxFlux-方法调研.md` | `docs/archive/pending_delete/plans/Direct-MaxFlux-方法调研.md` | 临时问答笔记，已由 DMF research report 和维护文档取代。 |
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
- 每次新增、归档或移动 report 或 spec/plan 时，同步更新本账本；活跃计划必须登记在
  “Spec / Plan / Review 登记”表内；只有核心入口才加入 `docs/index.md`。
- 阶段性审查文档完成任务后，先把结论吸收到长期文档或 release notes，再移出活跃集合。
- `pending_delete/` 中的文件在最终删除前，不得从活跃入口链接。
- 文档治理变更后运行 `python scripts/check_docs_governance.py`，确认活跃 reports
  账本、spec/plan 登记、metadata、active links、pending-delete inventory 和 HTML
  report 基础解析一致。
