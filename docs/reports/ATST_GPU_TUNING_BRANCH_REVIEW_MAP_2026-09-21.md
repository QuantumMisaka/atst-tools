# ATST GPU 节点调优分支审阅地图（2026-09-21）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 维护（审阅/合入入口；已合入 `main`，P5 首轮完成，剩余矩阵行见 §4）
**责任人**: ATST-Tools maintainers

## 1. 用途与分支事实

面向将要审阅 `feature/gpu-node-tuning` 的维护者与独立 reviewer：给出提交分组、
证据索引、建议阅读顺序与已知开放门。分支提交已推送 `origin` 并以 fast-forward 直接合入 `main`（未建 PR）；父仓 `app-tools` 的 gitlink 仍指向恒电势合入点，需其维护者另行更新。

| 项 | 值 |
| --- | --- |
| 基线（写本文时） | `main` 已含恒电势合入 = `7bc3f92` + `d30747b`（原基线 `origin/main` = `2cf5b7e6`；SPEC §11 R1）；本分支已 rebase 于其之上，并于 2026-09-21 以 fast-forward **直接合入 `main`**（未建 PR）；实时值以 `git log -1` 为准 |
| 分支头（写本文时） | `eb37c61`（49 提交）；后续新增契约审计与联合验收提交，提交数以 `git rev-list --count main..HEAD` 为准 |
| 变更规模 | 52 文件，+9080 / −950（`git diff --stat 2cf5b7e..HEAD`） |
| 规范源 | [SPEC](../superpowers/specs/2026-09-20-atst-gpu-node-tuning-design.md)（§11 Ruling）、[接口冻结](../superpowers/specs/2026-09-21-atst-runtime-interface-design.md)（rev.5）、[计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md) |
| 主要证据 | [P0 复核](../superpowers/specs/2026-09-21-atst-gpu-node-tuning-p0-review.md)；[本地 GPU 验证报告](ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md) §4–§16 |
| 账本 | [DOCUMENTATION_STATUS_REPORT.md](DOCUMENTATION_STATUS_REPORT.md)（每次变更登记） |

门禁现状（2026-09-21 对 `1a62a72` 复测）：`tests/unit` **1101 passed / 2 documented skips**
（共 1099 项收集）；`ATST_RUN_MPI_TESTS=1 tests/integration` **23 passed**（真实 MPI）；
`scripts/verify_wheel_api.py --mpi-smoke` 通过；
`scripts/check_docs_governance.py` 通过。复现命令见 §5。

## 2. 提交分组（主题）

**A. P0 接口与裁定（docs）**：`a31f7e8` 迁移交接 + 冻结接口；`a3c56a0` P0 性能复核与 rev.2；
`1e53044` rev.3 闭合 N1–N10；`f8738ad` 恒电势 checkpoint 与共享文件顺序；后续端点复核
`e85aa90`、SAI 勘察 `b9722d7`、哈希/回退修正 `d8cd59c`/`a7b3a81`。

**B. runtime 核心（feat/fix，P1–P2）**：`4be66a0` 设备解析与 launch 计划；`9cfdc4d` `runtime` schema 段 +
生成参数表；`9b3683e` CLI/runner 绑定；`46b59cf` 证据 sidecar；`4848568` 计数器；`fe84c63` MPI 计数汇总；
`a0b3051`/`b087482`/`e4e1638` 证据事实与相位；`249422b` P4 逐 rank 绑定；`fb484fd` auto threads 与计算进程采样；
`fd2444e`/`2dd39fe` fail-closed；`1bb58ce` worker re-exec 路径；`196b3d2` DP omp 记账；`4bd83c4`/`afe984a`
结果 envelope 与 dry-run；修复轮 `38d0c10`（F1–F8）。

**C. bench 工具链（feat/fix，P3–P5 预备）**：`a3256fd` 有限 case harness；`dbb5f2c` MPI launcher case；
`fbe45e8` 运行语义与调度守卫；`2e2ee07` sweep；`36f4d26` record；`2a25504` 一键 sbatch + MPI 超时回归；
`acc791a`（F1–F9 修复轮）；`eaa7e22` record 失败分支；`e853852` workdir 防覆盖；`a7b3a81` python 回退。

**D. 测试**：`6892036` CLI 模块入口；`36e7dd0` 镜像 parser 防漂移；`eaa7e22`、`e853852` 等行为回归。

**E. 本地证据与记录（docs）**：`1e913c2`/`c267507`/`5d9aa26`/`1d58f32`/`e175408`（合入预演）/
`b22523e`（NEB 图数×rank 压力）/`0d93993`（FT²DP 并发预演）/`35db15e`/`eb37c61`（AutoNEB）等。

## 3. 证据索引（主题 → 证据）

| 验收/主题 | 证据位置 |
| --- | --- |
| 接口语义（schema、错误、优先级、进程模型分流） | 接口冻结 §2–§9（rev.5）+ `tests/unit/test_runtime_*.py`（含冻结消息契约测试） |
| 设备可采性与逐 rank 绑定 | 接口冻结 §4 权威表；`tests/unit/test_runtime_devices.py`；`tests/integration/test_runtime_binding_mpi.py` |
| P1 本地真实 GPU 隔离路径与证据链 | 验证报告 §4–§5 |
| DP + mpi4py 图像并行 NEB（首个 E2E） | 报告 §6（与串行逐帧等价 max\|ΔE\| 1.4e-06 eV） |
| harness 并发、成本剖面、重复测量 | 报告 §7–§9、§12、§14 |
| wheel 端到端、CLI 漂移防回归 | 报告 §11；`scripts/verify_wheel_api.py` |
| FT²DP（DPA4/SeZM）接入 | 报告 §13、§16；接口冻结 §7.1 |
| NEB 图数 × rank 数压力边界 | 报告 §15（单卡 4/8 rank 为 4.1×/7.7× 负收益） |
| SAI 环境勘察与 P5 登台 | 计划 P5 预备段；`~/scratch/atst-p5-staging-20260921/RUNBOOK.md` |
| 恒电势 × runtime 真机组合 | [联合验收报告](ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md)（SAI 1435012，2/2 + 负例）与 [证据切片](data/ATST_CP_RUNTIME_20260921/README.md) |

**第三轮外部审查（2026-09-21，对 `f03b3e6`）**：8 项（P1×4、P2×4）已全部复现并修复，逐条处置见接口文档 §7.3；修复提交随后按"直接合入 main"惯例落地。

**第四轮：复核方复验 + 维护者独立核对（2026-09-21）**：复核方对第三轮修复复验通过。维护者随后做三项独立核对——
① 格式与导入卫生按仓内 pin 的 black 23.9.1 / isort 5.12.0 归一（本分支新增模块与测试共 18 个文件，含 5 处未用导入；
AST 级比对确认除被删导入外无行为变化），并在 `examples/README.md` 补登 `runtime_batch_cases.example.json` 模板（`5346fa9`）；
② 路径引用审计：`src/`、`tests/`、`examples/`、`scripts/` 对本机与站点绝对路径 **零命中**；`docs/` 内命中仅出现在
运行记录（本机 `~/scratch`、本机 ABACUS/DP 模块路径）与归档证据 JSON（SAI 作业与工作目录）中，与该仓既有做法一致
（`docs/reports/data/convergence_fixtures_20260917/`、`docs/superpowers/**` 的既有 spec/plan 同样记录工作机路径）；
③ 仓级建议（未改代码）：`.pre-commit-config.yaml` 的 isort 未带 `--profile black` / `line-length 88`，
与 black 的 88 列不一致，故 pre-commit 在该仓无法整体全绿——属仓库级配置缺口，非本分支引入。

## 4. 已知开放门（不属本分支完成范围）

1. **P5（SAI V100 基准）首轮与收尾已完成**（2026-09-21：冒烟 + DP 矩阵 12/12 + ABACUS 双示例 4/4 + 多卡 NEB + per-card 4 进程 + ABACUS 3 重复 + 修复后 ABACUS 基线与 8 ranks/1 卡压力行，见 [SAI 报告](ATST_RUNTIME_SAI_V100_VALIDATION_2026-09-21.md) §5d）；**剩余仅两项**：host/SIF 成对（需站点 SIF/挂载配合）、8 图×8 卡（需站点协调超出 QOS 的卡数）。
2. ~~恒电势合入 main~~ **已完成**（2026-09-21：`main` = `7bc3f92`+`d30747b`；两项前置门禁已被恒电势侧修复，
   `examples/reference_results.json` 含 `19_constant_potential_Pt`，abacuslite 快照测试在 main 上通过）。
   GPU 分支已 rebase 于其上并新增 §7A 联合验收测试；分支与 `main` 均已推送 `origin`（未建 PR）。
   **运行组合验收已完成**（2026-09-21：SAI 1435012，`compensated_gate` 单点 + 三点扫描 2/2、分配外设备负例被拒；见[联合验收报告](ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md)）。
3. ~~`calculator.abacus.omp` 默认值使 `runtime.threads` 失效~~ **已修复并复验**（2026-09-21，`5e26789`）：schema 改为 `int | None = None`（缺省不写，legacy 1 由 `resolve_calculator_omp` 写），新增三条回归测试；SAI 作业 1436782 用同一恒电势单点用例复跑确认 `OMP_NUM_THREADS=8`、无 `runtime_threads_overridden`、无覆盖 warning（对照见[联合验收报告](ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md) §5.1）。
4. ~~批量 harness 的 per-case `threads` 通道~~ **已裁定并实现**（`1a62a72`）：manifest 的线程预算按调用者显式预算处理（`case_environment` 写 `ATST_THREADS_SOURCE=harness`），未写 `omp` 且无 `runtime` 段的用例不再落回 legacy 1；带 `runtime.threads` 的用例仍由 worker 覆盖为 `explicit`/`auto`。站点复验见 SAI 报告 §5d(a)：`abacus-relax-h2au-t2` 生效 `OMP_NUM_THREADS=2`、无覆盖计数。注：P5 的 ABACUS 计时为单线程是因其示例配置**显式**写了 `omp: 1`（另一条路径），本改动对它们无影响。
5. **TF 后端维度**：缺 TF 原生制品（`dp --pt convert-backend` 对 DPA-3.1 类模型失败）。
6. **FT²DP 单头 EMA**：本机无文件、SAI 钉版路径在 `galileouser02` 下不可读；pin 记分卡记
   EMA ≈ regular，故默认 regular-only。

## 5. 复现命令

```bash
cd <atst-tools worktree>
PYTHONPATH=src conda run -n atst-dev python -m pytest tests/unit -q
ATST_RUN_MPI_TESTS=1 PYTHONPATH=src conda run -n atst-dev python -m pytest tests/integration -q
conda run -n atst-dev python scripts/check_docs_governance.py
timeout 1800 conda run -n atst-dev python scripts/verify_wheel_api.py --mpi-smoke
# P5 入口（需授权；先 DRY_RUN=1 自检）：
#   DRY_RUN=1 bash scripts/sai_runtime_bench.sbatch <work_dir> <cases.json> 0,1
```

## 6. 建议阅读顺序（reviewer）

1. 接口冻结文档 §2–§5、§7.2（冻结语义与证据约定）；
2. `src/atst_tools/runtime/{devices,launch,cli_dispatch,evidence,counters}.py`——重点看可采性表、
   worker 一致性校验与 re-exec、证据状态机（null 语义）；
3. `src/atst_tools/bench/{harness,sweep,record}.py`——重点看进程组回收、槽位/CPU 预算、record 的
   修订与哈希语义；
4. 两轮独立审查记录（F1–F8 / F1–F9）与其回归测试；
5. 验证报告 §4–§16（证据）、计划 P5 段（下一步）与本文 §4（开放门）。
