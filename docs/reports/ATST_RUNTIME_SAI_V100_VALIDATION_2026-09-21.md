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

- 作业：1430846（失败，留档）、1430966、1431010、1431119、1431648（slots=4）、1431955/1432107（多卡 NEB 对照）、1432043（srun/mpiexec 探针）；ABACUS：1431200（成功）、1431647（三次重复；repeat-2 NEB 停滞取消）、1432820（NEB 补跑 ×2 成功）；1431188/1431190（时序/路径问题取消或失败，留档）；1431952/1431646（挂起与孤儿，留档）。
- 仓库归档：本报告的版本化证据切片见 [`docs/reports/data/ATST_SAI_V100_20260921/`](data/ATST_SAI_V100_20260921/README.md)（records/汇总/证据 sidecar/两次重复的 case 记录；records 的 `approved_by` 已填）。
- 站点路径：`~/atst-p5-20260921/work/{smoke,smoke2,smoke3,dp-matrix,dp-matrix2,abacus2}/runs/`
  （`sweep/`、`evidence/`、`bench_record.json`），日志 `~/atst-p5-20260921/slurm-<job>.out`。
- 记录：`bench_record.json`（`atst-bench-record-v1`）含修订 `4d77fee`、fixture 哈希、
  结果目录全树哈希与操作者字段（job/partition/QOS；批准人待维护者填写）。

## 8. 边界与后续

单节点 ×2 GPU、66 原子级 case、DP 矩阵 repeats=3；ABACUS 通道为单次有界跑
（完整示例 NEB 约 19 min/次）。后续：host/SIF 成对、8-rank/1 卡压力行（`mpiexec --oversubscribe`，注意
用 srun+pmix 方案避开重绑定挂起）。
站点 `mpiexec` 重绑定挂起问题需与站点/上游（PRRTE/PMIx + exec）进一步确认。ABACUS 作业的 record
fixture 当前传入了 DP 模型哈希（`MODEL` 变量），后续应按通道传入对应输入。
