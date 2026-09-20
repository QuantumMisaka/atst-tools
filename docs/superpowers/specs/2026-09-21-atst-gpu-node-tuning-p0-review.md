# GPU 节点调优 P0 复核：性能前提与 DP 并行 NEB 证据审查

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 审查（结论影响 P4/P5 验收边界；P0 接口冻结不受阻塞）
**责任人**: ATST-Tools maintainers

复核对象：[GPU 节点调优设计](2026-09-20-atst-gpu-node-tuning-design.md) 的性能前提、[runtime 接口冻结设计](2026-09-21-atst-runtime-interface-design.md)、[执行计划](../plans/2026-09-20-atst-gpu-node-tuning-plan.md) 的 P4/P5 目标。目的：回答"当前优化是否真的做到了高性能"，覆盖 GPU 调优与 DP 模型的 mpi4py 并行 NEB 两项。

## 1. 范围与方法

- 取证源：`/home/james/work/ft2dp-dpeva`（`STATUS.md`、`docs/tasks/ft2dp-v2.2.md`、`docs/tasks/reaction-network-dpa4.md`、`validation-pipeline/`、`Recnet/`）与 atst 仓库文档/测试。
- 本机不可达项：SAI 侧 `$R/validation-pipeline/reaction/d2s_runs/` 与 Slurm `sacct`（`/org/pku-jianghong/...` 未挂载），原稿 4 个作业（DP `1422694/1422849/1423160`、ABACUS `1423179`）的原始日志与逐案计时未读取。
- 所有数字均附来源；缺失证据一律标注，不做外推。

## 2. 关键证据

### 2.1 DP 推理成本（实测）

| 体系 | 硬件 | 成本 | 来源 |
| --- | --- | --- | --- |
| 16 原子 Fe(110) | SAI 4V100（1 卡） | **20.2 ms / E+F**（对照本机约 5×） | `Recnet/recnet_adapter/evidence/sai_gpu_check_20260916.log:20`；`STATUS.md:342` |
| 105 原子 | RTX 2070S（本机 GPU） | **120–184 ms / E+F**；TS(≤200 步)+vib(nfree=2) ≈ 分钟级/反应 | `docs/tasks/reaction-network-dpa4.md:35` |
| 16 原子（多头臂） | 本机 | ≈101 ms / E+F | `docs/tasks/reaction-network-dpa4.md:60` |

### 2.2 D2S 生产跑法（DP 模型 NEB 的现状）

| 项 | 事实 | 来源 |
| --- | --- | --- |
| launcher 形态 | `--gres=gpu:2 --ntasks=2 --qos=rush-1o2gpu`；循环内 `CUDA_VISIBLE_DEVICES=$((i%2))`；`CONC` 默认 2，**每进程独占 1 卡** | `validation-pipeline/reaction/run_d2s_campaign.sbatch:2-14,44-59` |
| NEB 并行 | `DyNEB(..., parallel=False)`（脚本内原样） | `validation-pipeline/reaction/d2s_run.py:123` |
| atst 侧配置 | 生产与烟测配置均 `parallel: false` | `validation-pipeline/reaction/runs/CH_CH/neb.yaml:15`；`validation-pipeline/reaction/runs/CH_CH/neb.smoke.yaml:15` |
| 并发断言 | “multiple cases can share the 2 GPUs and the wall time scales with CONC, not with the GPU count” | `validation-pipeline/reaction/run_d2s_campaign.sbatch:28-30`（注释，**无量化证据**） |
| 单反应墙钟 | 2–7 min（端点松弛 → IDPP(8) → 粗糙 NEB(1.0) → Sella(0.05) → 振动） | `STATUS.md:23`；`docs/tasks/ft2dp-v2.2.md:1516` |
| 体系规模 | 实测 `validation-pipeline/reaction/runs/{CH_CH,TS1_2H_to_CHCv_H,CCH2_CCH3}/IS.xyz` = **119 / 118 / 120 原子** | 本机实测（2026-09-21） |
| 逐案 `wall_s` | **无本地留档**（`meta.json` 在 SAI 侧 `d2s_runs/`） | 本机 `find` 无结果 |

### 2.3 ABACUS 单点成本（对照原稿“118 原子 6–13 min”）

| 口径 | 数字 | 来源 |
| --- | --- | --- |
| 110–125 原子，n=43，4V100/cusolver | **median 20.19 min** / p90 24.51 / p95 25.59 / max 50.24 | `docs/tasks/fe5c2-key-validation-probe.md:61` |
| 20/72/169 原子，4-GPU cusolver（160 步窗口未收敛） | 7:06 / 17:22 / 42:33 | `STATUS.md` R50 |
| 批 #1（`1423179`，18 例） | 12/18 完成时无逐案墙钟记录；批 #2（`1423859`）排队 | `STATUS.md:12` |

**结论 A**：原稿“118 原子单点 6–13 min”在本地既有记录中没有支持（同规模历史中位约 20 min）。该数字必须由 SAI 侧 `sacct`/日志或 P5 重测裁定；在此之前 P0–P6 文档不得引用。

## 3. 判定

### 3.1 GPU 调优前提：**未证实**，但方向正确

- DP 单次推理便宜（16 原子 ≈20 ms；105 原子 ≈120–184 ms），但单案调用量在 **10³ 量级**：NEB（8 图 × 步数 ≈ 240–1200 次）+ 振动 Hessian（全原子 `2×3N ≈ 708` 次）+ Sella（50–200 次）+ 端点松弛（100–400 次）≈ **1100–2500 次 E+F/案**。
- 按上述单价折算，GPU 侧约 **1–3 min/案**，与实测 2–7 min 同量级 → GPU 推理至少与 CPU 侧同量级，**“墙钟只随 CONC 缩放、与卡数无关”的注释没有任何测量支持**。
- 仓库内**没有推理侧 GPU 利用率/显存/占用采样**（`nvidia-smi` 仅出现在训练与安装脚本）；Recnet 生产 TS 链当前还跑在 CPU 分区（`submit.sh -p amd, ntasks=1, cpus=4`，见 `docs/tasks/ft2dp-v2.2.md` R268）。
- 因此 SPEC 把“5 case / 2 GPU 显著提速”“每卡多进程”降级为待验证假设是正确修订；P5 必须补“每卡 1/2/4 进程”的吞吐/利用率/显存曲线，并以成功 case/hour 与卡时/成功案为主指标。

### 3.2 DP 模型的 mpi4py 并行 NEB：**零证据（从未运行）**

- ft2dp-dpeva 全仓无 `parallel: true`、无与 DP 相关的 `mpirun`（唯一 `mpirun` 出现在 ABACUS 标注脚本）；D2S 与旧 atst NEB 链均为串行。
- 唯一的 DP + atst NEB 实跑是 5 图 20 步、9 原子烟测（job `1400925`，21 s、105 帧、能量有限），串行且体系不具代表性。
- atst 侧 image-parallel 的 E2E 证据只有 ABACUS 后端（Cy-Pt，jobs `461967`/`462244`，见 `docs/reports/NEB_IMAGE_PARALLEL_E2E_VALIDATION_2026-05-29.md`）；DP 后端无并行 E2E；`tests/unit/test_mpi_parallel.py` 覆盖的是拓扑校验与失败同步，不涉及 DP 计算器。
- 环境障碍真实存在：DP conda 栈多为 MPICH 构建，站点 launcher 为 ABACUS LTS OpenMPI；atst 文档明确要求 MPI 测试环境与 `atst-dev` 分离以避免 MPICH-based DeePMD 与 OpenMPI 冲突（`docs/reports/MPI4PY_ASE_NEB_PARALLEL_ATST_SUMMARY_2026-05-27.md:100-103`）。本机 `dpa4-dpmd-v100` 无 `mpi4py`。
- 收益条件（供 P4 定义验收）：NEB 每迭代对每个图各 1 次 E+F。**ranks 与卡数一一对应（≤图数）**时单步墙钟 ≈ 单图成本（最多接近图数倍加速）；**8 ranks 挤 1 卡**时 GPU 总吞吐不增（除非 MPS/批处理），收益主要是 CPU 侧重叠——与 SPEC“10 ranks/1 卡是压力实验，不是生产推荐”一致。

### 3.3 原稿作业证据的可达性

`1422694/1422849/1423160/1423179` 的原始记录位于 SAI（本机未挂载）。处置二选一：由维护者导出 `sacct` 与作业日志，或并入 P5 重测；在此之前这 4 个作业只作为“运行事实存在”的证据，不引用其数字。

## 4. 对在途文档的修订要求

1. SPEC §2：保留“待取证”表述，并补充结论 A（原稿 6–13 min 与本地 ~20 min 中位不符，待 `sacct` 或 P5 裁定）。
2. PLAN P5：新增三项测量——DP 推理并发曲线（1 卡 1/2/4 进程）；NEB 图数 × 卡数映射（4/8 图 × 1/2/4/8 卡）；推理侧 GPU 利用率/显存采样。
3. PLAN P4：新增“DP 后端 image-parallel NEB 首个 E2E”（含 mpi4py ABI 前置与“与串行同种子收敛等价”验收）。
4. 接口冻结文档：无阻塞改动；§4/§6 的“每卡多进程”与线程规则与本复核一致。

## 5. 结论

- “高性能”**尚未证实**：当前 DP 反应流程是**串行 NEB + case 级并发（每卡 1 案）**；GPU 与 CPU 谁主导单案墙钟没有测量结论，仓库也从未做过推理侧 GPU 采样。
- DP 模型的 mpi4py 并行 NEB 是**完全空白**：框架能力已在 ABACUS 后端验证，DP 后端缺环境（mpi4py ABI）、缺首个 E2E、缺收益曲线。
- 本复核不阻塞 P0 接口冻结，但为 P4/P5 增加了可验收的测量目标，并撤回原稿中未经复核的性能表述。

## 6. 未决

- SAI 侧 `sacct`/日志导出的授权与路径；
- “DP 推理并发曲线”是否提前到 P2 实现（建议：采样接口按接口文档 §7.2 在 P2 预留，测量留在 P5）。
