# ATST Runtime SAI V100 验证 2026-09-21（P5 现场）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 首轮完成（DP 与 ABACUS 双通道、含多卡 NEB；host/SIF 成对留后续）
**责任人**: ATST-Tools maintainers

## 1. 目的与范围

GPU 节点调优计划 P5 的现场验收：在 SAI 4V100 上以站点环境（Lmod、OpenMPI、
4V100 队列）运行 ATST 的一键基准入口（`scripts/sai_runtime_bench.sbatch`：
计时 sweep → 证据 pass → 自描述记录），验证设备绑定、线程预算、DP/ABACUS
双后端、MPI（mpi4py 图像并行 NEB）与证据链。所有运行使用冻结分支
`feature/gpu-node-tuning`（站点侧以 `ATST_SOURCE_ROOT` 指向 git 检出让记录
携带真实修订）。

## 2. 站点与环境

| 项 | 值 |
| --- | --- |
| 账号/登录 | `galileouser02` @ `login-01.mr-sai.ai`（家目录 `/org/galileo-group/galileouser02`） |
| 分区/队列 | `4V100`（35 节点）、QOS `rush-1o2gpu`（≤2 GPU、MaxWall 1 天） |
| 模块 | `cuda/12.9.1`、`nvhpc/26.3-gnu-cuda12-tuned`、`openmpi/5.0.10-nvhpc26.3-gnu-cuda12-auto`、`deepmd-kit/3.2.0`；ABACUS 通道另加 `abacus/LTSv3.10.1-sm70-auto`（自带 OpenMPI 5.0.8） |
| Python 环境 | venv（`--system-site-packages` on `deepmd-kit/3.2.0`，Python 3.13）：ase 3.29.0、pydantic 2.13.4、sella、mpi4py 4.1.2（Open MPI 5.0.8）、numpy 2.5.2；atst wheel 2.2.6（运行走源码检出） |
| 模型 | FT²DP 单头 100k `model.ckpt-100000.pt`（sha256 `13b74797…`，站点加载 `ntypes=118` 通过） |
| 夹具 | `init_H2-Au.stru`、`chain5.traj`、`endpoints_H2Au.traj`（+科学体系 chain6/chain10 备用） |

## 3. 运行方法

```
sbatch --ntasks=8 --time=<预算> --qos=rush-1o2gpu \
  scripts/sai_runtime_bench.sbatch <work_dir> <cases.json> 0,1
# 环境：ATST_SOURCE_ROOT=<clone>、PYTHON_BIN=<venv>/bin/python、MODEL=<model.pt>
#       ABACUS_MODULE=1（ABACUS 通道）、SLOTS/REPEATS/EVIDENCE_PASS 覆盖默认矩阵
```

## 4. 冒烟（单 case，逐层验证）

| 作业 | 目的 | 结果 |
| --- | --- | --- |
| 1430846 | 首跑（发现 Lmod/`set -u` 缺陷） | 失败：所有 case `cannot load MPI library`（详见 §6） |
| 1430966 | 修复后重跑 | 17 s，`ok=1/1`，record 写出（修订为空，因走 wheel） |
| 1431010 | 启用 `ATST_SOURCE_ROOT` + 设备事实修复后 | 15 s，`ok=1/1`；sidecar `inherited=['0']/effective=['0']`、`caller_bound=true`；record 修订 `4d77fee`、`dirty=false` |

## 5. DP 矩阵（4 case × slots 1/2/3 × 3 repeats + 证据 pass）

作业 1431119（2:49，`4V100` ×1 节点 ×2 GPU）：

| 变体 | makespan 中位 | 成功 | 卡时中位 |
| --- | --- | --- | --- |
| slots=1 | 16.11 s | 12/12 | 29.06 |
| slots=2 | 16.56 s | 12/12 | 29.97 |
| slots=3 | 16.75 s | 12/12 | 30.81 |
| slots=4 | 15.80 s | 12/12 | 29.16 |

单 case 墙钟中位（三变体）：relax t4 ≈ 6.2–6.7 s、relax t8 ≈ 6.2–6.9 s、
AutoNEB ≈ 6.8–7.3 s、NEB 3-rank ≈ 9.9 s。证据 pass（每 case sidecar）：

| case | 设备 | threads | `dp.force_calls` | 显存峰值 | 利用率均值 | MPI |
| --- | --- | --- | --- | --- | --- | --- |
| dp-relax-ft2dp-t4 | `['0']` | 4 | 9 | 480 MiB | 0.1% | ws=1 |
| dp-relax-ft2dp-t8 | `['1']` | 8 | 9 | 1096 MiB | 0.0% | ws=1 |
| dp-autoneb-h2au | `['0']` | 4 | 28 | 1096 MiB | 13.6% | ws=1 |
| dp-neb-ft2dp-mpi3 | `['1']` | 4 | 13（Σ35） | 3296 MiB | 12.0% | ws=3 |

观察：**V100 上这批小 case 不随并发受益**（makespan 持平 ~16–17 s，卡时随
slots 略增）；线程 4→8 无差异；显存上限 ≈3.3 GiB（3-rank NEB）；利用率
≤14%，与本地结论（延迟受 CPU/调度与固定加载成本主导）一致。**收益假设仍
只在多卡/大体系上成立**。

## 5c. 多卡 NEB（4 内部图 × 4 卡）

| 作业 | 启动方式 | 结果 |
| --- | --- | --- |
| 1431646 | `mpiexec --oversubscribe -n 4` + 配置内 `runtime.binding: round_robin` | **挂起**（19 分钟后取消；见 §6.5） |
| 1431955 | `srun --ntasks=4 --gpus-per-task=1`（无 `--mpi`） | 名义成功但 **退化为 4 个独立串行 NEB**（`world_size=1`；18.8 s；无 `counters_mpi`） |
| 1432107 | `srun --mpi=pmix_v5 --ntasks=4 --gpus-per-task=1 --cpu-bind=none` | **正确**：`world_size=4`、rank0 掩码 `['0']`、`counters_mpi` Σ`dp.force_calls=38`；11.8 s（计时）/9.9 s（证据） |

探针（1432043）解释了差异：站点 `srun` 默认 `--mpi=none`，任务里 `PMI_SIZE`/`PMIX_SIZE`/`OMPI_*` 全缺失、mpi4py 退化为 size 1；同一进程用 `mpiexec -n 2` 启动则是 size 2。**站点多卡 MPI 需显式 `srun --mpi=pmix_v5`（或 `mpiexec`）**；`--gpus-per-task=1` 由 Slurm 按任务分发单卡掩码，配合“配置不请求 runtime”即可避开重绑定路径。

## 5b. ABACUS 通道（示例 06 relax 与 01 NEB，host module 版）

作业 1431200（25:31；`--ntasks=8`、`ABACUS_MODULE=1`：
`abacus/LTSv3.10.1-sm70-auto` 与之自带 `openmpi/5.0.8`、`elpa`、`fftw`、`libxc`）：

| case | 计时 pass | 证据 pass | 设备 | threads | ABACUS 调用 | 显存峰值 | 利用率均值 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| abacus-relax-h2au | 172.8 s | 171.0 s | `['0']` | 1（配置 `omp: 1`） | 1 | 2198 MiB | 45.2%（165 样本） |
| abacus-neb-li-si-parallel | 747.3 s | 777.4 s | `['1']` | 1（配置 `omp: 1`） | 44（calculator built 5） | 2198 MiB | 29.5%（753 样本） |

两例在计时与证据两遍均 `succeeded`（4/4）；600 s 级 NEB 单 band 的墙钟与该
示例的历史 SAI 记录（≈18.7 min）同量级。threads 记录为 1 是预期的
R3 行为（`calculator.abacus.omp: 1` 显式值优先于 case 线程预算）。
首轮失败（1431190，0/2）源于示例配置使用相对输入路径，而 case workdir
在批量输出目录内；已改为登台绝对路径副本（`configs/abacus_relax_h2au.yaml`、
`configs/abacus_neb_li_si.yaml`）。

**候选点重复（≥3 次）**：NEB 三次（750.2 s @1431647 r1、712.7 / 709.8 s @1432820），
中位 ≈712.7 s（~11.9 min），离散 ~5%；relax 四点（172.8 / 171.0 s @1431200，
171.7 / 172.6 s @1431647），中位 ≈172 s。1431647 的 repeat-2 NEB 曾在同节点出现
孤儿进程后停滞约 1 h（无输出、workdir 为空），取消后补跑 1432820 正常——该停滞
与孤儿 MPI 进程同期出现，列为站点观察项。

**修复后现场复验（2026-09-21，作业 1434302）**：第三轮审查修复后重跑同一
`mpiexec --oversubscribe -n 4` + `runtime.binding: round_robin` 用例（4 卡）——
**22 s 完成、两遍 1/1**；rank0 证据 `bound=true`、`binding=round_robin`、
`inherited=['0','1','2','3']`、`effective=['0']`、`world_size=4`、
`counters_mpi` Σ`dp.force_calls=38`。此前 1431646 的挂起确认为入口顺序缺陷所致，已闭环。

## 5d. P5 收尾：修复后 ABACUS 基线 + 8 ranks/1 卡压力行（2026-09-21）

作业 **1436941**（4V100、1 GPU、`--ntasks=8`、`ABACUS_MODULE=1`）。此前作业 1436926 因
`--ntasks=1` 被 PRRTE 以"not enough slots available"拒绝（示例配置内部为 `mpirun -np 4`）
而 0/2 失败，留档于证据切片 `job-1436926/`；补上 P5 的 `--ntasks=8` 形状后两通道全部通过。

**（a）修复后 ABACUS relax 基线**（`omp` 优先级修复 `5e26789` + harness 线程标记 `1a62a72` 之后）：

| case | 配置 `omp` | 生效 OMP | `threads_source` | 覆盖计数 | wall |
| --- | --- | --- | --- | --- | --- |
| abacus-relax-h2au-omp1 | 显式 `1` | 1 | `harness` | 1（预期：显式值优先） | 160.9 s |
| abacus-relax-h2au-t2 | 缺省 | **2** | `harness` | 无 | 157.6 s |

两例均 4 个内部 MPI rank、`cpu_affinity_count=8`、显存峰值 2198 MiB、`abacus.force_calls=1`。
对照 P5 原记录（172.8 / 171.0 s，同配置）说明：**该示例在 4 rank 基础上再加 OMP 线程收益 ≈ 2%
（噪声级）**——H2-Au relax 的墙钟由 SCF 本身的串行工作决定，本用例不值得再堆线程；
`t2` 用例同时证明 manifest 的 per-case `threads` 现在确实到达 ABACUS（证据记 `threads_source=harness`）。

**（b）8 image-parallel ranks / 1 卡（站点压力行）**，FT²DP 单头 100k、`chain10`（8 内部图）、
`max_steps: 2`、每 rank 1 线程、同一张卡、`mpiexec --oversubscribe -n 8`：

| 作业 | 串行参考 | 8 ranks / 1 卡 | 比值 | Σ`dp.force_calls` | 显存峰值 |
| --- | --- | --- | --- | --- | --- |
| 1436926 | 13.57 s | 16.27 s | 1.20× | 66 → 26 | 2078 / 16646 MiB |
| 1436941 | 11.17 s | 20.51 s | 1.84× | 66 → 26 | 2078 / 16646 MiB |

**这条站点结果修正了本地 §15 的外推**：本机（WSL2 + RTX 2070 SUPER 8 GB）单卡 8 rank 相对串行
是 7.7× 负收益，而 V100（32 GB HBM）上同一形状只有 **1.2–1.8×**、且两次测量离散就接近该量级——
说明本地劣化主要来自**显存上限与桌面驱动/多上下文行为**，不是"单卡多 rank 必然不可用"。
因此 P5 矩阵中"图数 ≤ 卡数"的收益假设仍须按卡型/显存实测，`8 ranks / 1 卡` 一栏按
"温和负收益、显存是绑定资源"记录（16646 MiB ≈ 32 GB 的一半）。本行证据同时含
`counters_mpi`（`world_size=8`、Σ`dp.force_calls=26`、`dp.calculator_built=9`）。

**站点观察**：两个作业的批次 shell 里 `nproc=2`，而 worker 内亲和掩码为 8
（`cpu_affinity_count=8`）——站点 Slurm 绑定在不同进程层不一致，记为观察项，不据此改代码。

## 5e. CCQN 固定成本复测（2026-09-21，作业 1437354）

把本地报告 §17 的 CCQN 分解搬到站点（V100 + FT2DP 单头 100k，一个 case、9 次力调用、
`reactive_bonds: 1-2`、`max_steps: 8`）：

| 量 | 本地（DPA-3.1-3M，2070S） | 站点（FT2DP 单头 100k，V100） |
| --- | --- | --- |
| 替身 pass（只留 CCQN/ASE CPU 逻辑） | 2.27 s（9 次调用） | **2.56 s**（登录节点，9 次调用） |
| 真实 pass | 35.5 s wall / 29.8 s dispatch | **6.71 s wall / 4.95 s dispatch** |
| 每 worker 固定成本（加载 + 预热） | ≈15.6 s | **≈2.4 s（推算：4.95 − 2.56）** |
| `dp.force_calls` / `calculator_built` / `cached_instances` | 9 / 1 / 1 | 9 / 1 / 1 |
| 采样 | 25 样本 / 29.8 s，峰值 4573 MiB | 5 样本 / 4.9 s，峰值 1074 MiB |
| `threads_source` | — | `harness`（新线程标记在站点生效，worker stderr 为空） |

**结论**：固定成本随**模型**而非框架变化——多任务 DPA-3.1-3M 在本机要 15.6 s，而站点小模型只要
≈2.4 s；CCQN 自身的 CPU 逻辑两端都只有 ~2.3–2.6 s。所以"摊薄 worker 初始化"这条杠杆对
**大模型 + 短 case** 最值钱，对小模型/长 case 收益有限。本次同时验证了产物更名后的首个新运行：
`runs/batch_summary.json`、`runs/ccqn-h2au-ft2dp/case_report.json`、`worker.{out,err}` 均按新名落盘，
`bench_record` 正常生成。

## 5f. DP 启动成本在 GPU 侧的形态（2026-09-21，作业 1437867）

承接本地 §18 的归因（TorchScript fuser 预热）在站点复测同一模型（FT²DP 单头 100k、66 原子、
`atst_tools.calculators.factory` 同一条构造路径）：

```json
{"torch": "2.13.0+cu126", "torch_cuda": true, "deepmd_device": "cuda:0", "torch_threads": 1}
{"construct_s": 1.551, "calls_s": [1.326, 0.028, 0.028, 0.028, 0.028], "natoms": 66}
```

| 量 | 本地 CPU-only torch（§18） | 站点 GPU torch（本节） |
| --- | --- | --- |
| 构造 | 4.2 s（含 `torch.jit.script` 1.8 s） | **1.55 s** |
| 首调用 | 6.8–17 s 的 fuser 预热曲线 | **1.33 s** |
| 稳态 | 0.56 s/调用（4 线程） | **0.028 s/调用** |
| 预热曲线 | 明显（24 s 才进稳态） | **不存在**（第 2 次即 0.028 s） |

**解释**：TorchScript 的 TensorExpr fuser 只在 intra-op 线程数 > 1 时工作；站点这个作业
`torch_threads=1`（批次 step 只拿到 2 CPU、torch 取 1），因此 fuser 不参与，本地看到的那条
20 s 预热曲线在 GPU/单线程路径上根本不出现。稳态 0.028 s/调用也解释了 §5e 的算术：
CCQN 一个 case（9 次调用）的墙钟几乎全由"启动"（构造 ≈1.6 s + 首调用 ≈1.3 s ≈2.9 s）
与 CCQN 自身 CPU 逻辑（≈2.5 s）构成，推理本身可以忽略。

**结论（含对 §18 建议的修正）**：本地 spike 提出的"暴露 eager/`no_jit` 路径"这条杠杆**在本站点路径上不成立**
（没有可省的预热），故**不推进该 schema 变更**；GPU 节点上值得做的仍是**摊薄每 case 的启动**
（同一进程跑多个 case）。若未来有 CPU-torch + 多线程的消费场景，再重新评估 `no_jit`。

## 5g. ABACUS 内层并行扫描（mpi × omp，2026-09-21，作业 1438158）

同一 relax 用例（示例 06 H2-Au、单步）、同一张 V100，只改内层并行（`--ntasks=8` 保证内部
`mpirun -np N` 有槽位）：

| 用例 | 内层 MPI | OMP | wall |
| --- | --- | --- | --- |
| abacus-mpi4-omp1 | 4 | 1 | 147.3 s（与 P5 的 171–173 s 同量级，节点/时机差异） |
| abacus-mpi4-omp2 | 4 | 2 | **145.8 s** |
| abacus-mpi2-omp4 | 2 | 4 | **224.3 s** |
| abacus-mpi1-omp8 | 1 | 8 | 146.8 s |

**结论**：这个 ABACUS 负载（LCAO + `cusolver`、66 原子）**不吃 CPU 预算**——从 4 核到 8 核的所有
排布都落在 ≈146–147 s（差异在噪声内），而 2 rank × 4 线程反而慢 50%。因此示例默认
（`mpi: 4, omp: 1`）就是好的选择，不必再做内层拆分调优；ABACUS 的时间不在 CPU 侧赢。
证据切片 `docs/reports/data/ATST_ABACUS_PARALLEL_SCAN_20260921/`。

## 6. 站点问题与修复（本次 P5 产生）

1. **Lmod 在 Slurm 批脚本里对 `set -u` 静默失效**（首跑 1430846 全灭）：
   Lmod init 与 module 求值会解引用 `LD_LIBRARY_PATH` 等变量，`set -euo
   pipefail` 下加载被跳过且被 `|| true` 掩盖。修复：模块块用站点 SIF 构建
   脚本同款 `set +u` 包裹，并在加载后**显式校验** `from mpi4py import MPI`。
2. **Slurm 分配槽位限制 MPI 启动**：`--ntasks=1` 下 `mpiexec -n 3` 报
   "not enough slots"；NEB launcher 现用 `mpiexec --oversubscribe -n 3`，
   ABACUS 通道以 `--ntasks=8` 提交（其内部 `mpirun -np 4`）。
3. **记录修订为空**：走 wheel 安装时 `bench_record.revision` 为 null；入口新增
   `ATST_SOURCE_ROOT`，从 git 检出运行后记录携带真实 `head/branch/dirty`。
4. **MPI rank 内 re-exec 重绑定在站点 OpenMPI 下挂起**（根因含本仓入口顺序缺陷：runner 曾在 exec 前初始化 MPI；2026-09-21 外部审查 P1-2 已修复，见接口文档 §7.3）：带 `runtime.*` 请求的 runner 会先做绑定再 `execve`。探针（1431952）显示
   `mpiexec -n 2` 下两 rank 打印 `pre-exec ok` 后**不再有输出并超时**（exec 后 PMIx 会话失效）；本地 MPICH 同场景正常（round_robin NEB 完成）。
   影响：站点的 `mpiexec + runtime.binding/--devices` 组合不可用；多卡 NEB 改用 `srun --mpi=pmix_v5 --gpus-per-task=1` 方案（§5c）。
   连带现象：超时杀掉 mpiexec 后，exec 过的 rank 会成为孤儿进程，取消作业长时间停留在 `CG`（1431952/1431646 留档）。
5. **未绑定进程内运行的设备事实为空**：`device_facts` 只读协调者事实，
   丢弃了 `CUDA_VISIBLE_DEVICES`；已修复（`inherited == effective == 字面掩码`，
   并加单测），站点与本地行为一致。

## 7. 证据清单

- 修复后收尾作业：1436926（ABACUS 组因 `--ntasks=1` 被 PRRTE 拒；DP 压力行通过，留档）、1436941（两通道全通过）；切片 [`docs/reports/data/ATST_P5_CLOSEOUT_20260921/`](data/ATST_P5_CLOSEOUT_20260921/README.md)。
- 作业：1430846（失败，留档）、1430966、1431010、1431119、1431648（slots=4）、1431955/1432107（多卡 NEB 对照）、1432043（srun/mpiexec 探针）；ABACUS：1431200（成功）、1431647（三次重复；repeat-2 NEB 停滞取消）、1432820（NEB 补跑 ×2 成功）；1431188/1431190（时序/路径问题取消或失败，留档）；1431952/1431646（挂起与孤儿，留档）。
- 仓库归档：本报告的版本化证据切片见 [`docs/reports/data/ATST_SAI_V100_20260921/`](data/ATST_SAI_V100_20260921/README.md)（records/汇总/证据 sidecar/两次重复的 case 记录；records 的 `approved_by` 已填）。
- 站点路径：`~/atst-p5-20260921/work/{smoke,smoke2,smoke3,dp-matrix,dp-matrix2,abacus2}/runs/`
  （`sweep/`、`evidence/`、`bench_record.json`），日志 `~/atst-p5-20260921/slurm-<job>.out`。
- 记录：`bench_record.json`（`atst-bench-record-v1`）含修订 `4d77fee`、fixture 哈希、
  结果目录全树哈希与操作者字段（job/partition/QOS；批准人待维护者填写）。

## 8. 边界与后续

单节点 ×2 GPU、66 原子级 case、DP 矩阵 repeats=3；ABACUS 通道为单次有界跑
（完整示例 NEB 约 19 min/次）。**后续仅剩：host/SIF 成对与 8 图×8 卡**（8 ranks/1 卡压力行已于 2026-09-21 完成，见 §5d；host/SIF 需要站点侧 SIF 与挂载配合，8 图×8 卡需要站点协调超过 QOS 的卡数）。
站点 `mpiexec` 重绑定挂起问题需与站点/上游（PRRTE/PMIx + exec）进一步确认。ABACUS 作业的 record
fixture 当前传入了 DP 模型哈希（`MODEL` 变量），后续应按通道传入对应输入。
