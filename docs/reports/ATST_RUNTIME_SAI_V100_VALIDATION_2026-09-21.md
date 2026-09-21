# ATST Runtime SAI V100 验证 2026-09-21（P5 现场）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 首轮完成（DP 与 ABACUS 双通道均通过；多卡/SIF 留后续）
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
4. **未绑定进程内运行的设备事实为空**：`device_facts` 只读协调者事实，
   丢弃了 `CUDA_VISIBLE_DEVICES`；已修复（`inherited == effective == 字面掩码`，
   并加单测），站点与本地行为一致。

## 7. 证据清单

- 作业：1430846（失败，留档）、1430966、1431010、1431119；ABACUS：1431200（成功）；1431188 因默认矩阵时长不匹配取消、1431190 因相对路径失败（均留档）。
- 站点路径：`~/atst-p5-20260921/work/{smoke,smoke2,smoke3,dp-matrix,dp-matrix2,abacus2}/runs/`
  （`sweep/`、`evidence/`、`bench_record.json`），日志 `~/atst-p5-20260921/slurm-<job>.out`。
- 记录：`bench_record.json`（`atst-bench-record-v1`）含修订 `4d77fee`、fixture 哈希、
  结果目录全树哈希与操作者字段（job/partition/QOS；批准人待维护者填写）。

## 8. 边界与后续

单节点 ×2 GPU、66 原子级 case、DP 矩阵 repeats=3；ABACUS 通道为单次有界跑
（完整示例 NEB 约 19 min/次）。后续：多卡 NEB"图数 ≤ 卡数"矩阵（如 10 ranks/4 卡）、ABACUS
host/SIF 成对、8-rank/1 卡压力行（以 `--oversubscribe` 运行）、ABACUS 候选点
≥3 次交替重复（单次完整 NEB ≈13 min，预算允许时补）。ABACUS 作业的 record
fixture 当前传入了 DP 模型哈希（`MODEL` 变量），后续应按通道传入对应输入。
