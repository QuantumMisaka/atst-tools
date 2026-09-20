# ATST GPU 节点调优分支审阅地图（2026-09-21）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 维护（审阅/合入入口；P5 未执行、未推送）
**责任人**: ATST-Tools maintainers

## 1. 用途与分支事实

面向将要审阅 `feature/gpu-node-tuning` 的维护者与独立 reviewer：给出提交分组、
证据索引、建议阅读顺序与已知开放门。本分支尚未推送，未改变父仓 gitlink。

| 项 | 值 |
| --- | --- |
| 基线 | `origin/main` = `2cf5b7e6`（v2.2.6 + 7 个未发布提交，SPEC §11 R1） |
| 分支头（写本文时） | `eb37c61`（49 提交：16 feat / 11 fix / 3 test / 19 docs）；实时值以 `git log -1` / `git rev-list --count 2cf5b7e..HEAD` 为准 |
| 变更规模 | 52 文件，+9080 / −950（`git diff --stat 2cf5b7e..HEAD`） |
| 规范源 | [SPEC](../superpowers/specs/2026-09-20-atst-gpu-node-tuning-design.md)（§11 Ruling）、[接口冻结](../superpowers/specs/2026-09-21-atst-runtime-interface-design.md)（rev.5）、[计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md) |
| 主要证据 | [P0 复核](../superpowers/specs/2026-09-21-atst-gpu-node-tuning-p0-review.md)；[本地 GPU 验证报告](ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md) §4–§16 |
| 账本 | [DOCUMENTATION_STATUS_REPORT.md](DOCUMENTATION_STATUS_REPORT.md)（每次变更登记） |

门禁现状（2026-09-21 实测）：`tests/unit` **1017 passed / 2 documented skips**；
`ATST_RUN_MPI_TESTS=1 tests/integration` **22 passed**（真实 MPI）；
`scripts/verify_wheel_api.py --mpi-smoke` 在 `b22523e` 通过；
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

## 4. 已知开放门（不属本分支完成范围）

1. **P5（SAI V100 基准）尚未执行**：需维护者授权与 fixture/容差/预算裁决（计划 P5 提案表）；
   登台包（wheel/tarball/git bundle/权重/fixtures/6-case 清单/手册）已备。
2. **恒电势合入 main** 由其 owner 决定；两项前置门禁（`examples/reference_results.json` 缺
   `19_constant_potential_Pt` 条目；vendored abacuslite `core.py` 补丁与快照归一化测试前提）与
   8 个在途文件仍在其工作树；合并预演（只读）无文本冲突。
3. **TF 后端维度**：缺 TF 原生制品（`dp --pt convert-backend` 对 DPA-3.1 类模型失败）。
4. **FT²DP 单头 EMA**：本机无文件、SAI 钉版路径在 `galileouser02` 下不可读；pin 记分卡记
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
