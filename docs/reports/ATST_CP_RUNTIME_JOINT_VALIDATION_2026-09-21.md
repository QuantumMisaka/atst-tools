# ATST 恒电势 × runtime 联合验收（SAI 4V100，2026-09-21）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 联合验收通过（2/2 用例、负例拒绝成立）；附带 1 项 P2 交互缺陷（见 §5）
**责任人**: ATST-Tools maintainers

## 1. 目的与范围

关闭 [审阅地图](ATST_GPU_TUNING_BRANCH_REVIEW_MAP_2026-09-21.md) §4 的开放项
「恒电势 × 新 runtime 的运行组合验收」：此前两者只有 schema 级联合测试
（`tests/unit/test_joint_runtime_constant_potential.py`，SPEC §7A），没有一次真机组合运行。
本轮在 SAI 4V100 上以被冻结的 `constant_potential` 工作流 + 完整 `runtime` 段
（`devices`/`binding`/`threads`/`telemetry`）跑通两个用例，并附带一条
「分配外设备必须被拒」的负例。范围是**组合机制**，不是恒电势的科学验收。

## 2. 固定点与环境

| 项 | 值 |
| --- | --- |
| 代码固定点 | `e0abb71`（分支 `cp-runtime-joint-20260921`，站点克隆 `dirty=false`） |
| 用例配置 | 归档 `staging/cases-cp.json` + `cases/*/config.yaml`（sha256 见 `runs/bench_record.json` 的 `inputs.manifest`） |
| 科学 fixture | `examples/19_constant_potential_Pt`，`materialize.py --basis lcao --electrons 217 --dipole --density-precision 12` |
| 站点环境 | ABACUS `LTSv3.10.1-sm70-auto`（`bin_sm70_avx512`）、OpenMPI 5.0.8、DeepMD-kit 3.2.0；venv Python 3.13.15 / ase 3.29.0 / mpi4py 4.1.2 / numpy 2.5.2 |
| 作业 | `1435012`（验收，4V100，1 GPU、8 CPU、QOS `rush-1o2gpu`，wall 00:07:06）；`1435134`（OMP 根因诊断，00:00:39） |
| 成本 | 0.118 GPU·h（验收）+ 0.011 GPU·h（诊断） |

## 3. 用例与参数

两个用例共用同一 fixture 与补偿栅边界参数，只在目标数量与线程预算上不同：

| 参数 | `cp-gate-single` | `cp-gate-scan` |
| --- | --- | --- |
| 目标 | `target_mu_ev: 15.04597065792631` | `target_mu_values_ev: [15.0, 15.04597065792631, 15.1]` |
| `runtime` | `devices: [0]`、`binding: inherit`、`threads: auto`、`telemetry: true` | 同上，`threads: 8` |
| CP 控制 | `energy_boundary: compensated_gate`、`reference_electrode: custom`、`reference_electrons: 216`、初值 `nelec: 217`、`potential_tolerance_v: 1e-4`、`max_iterations: 12`、`capacitance_initial: 0.05 e/V`、Newton 界 `216.5/217.5/0.1` | 同左 |

目标值与 Newton 控制取自该 fixture 自身的 `validate_forces.py` 调用参数
（`--target-mu 15.04597065792631`、`--initial-electrons 217`），未自造标定。
ABACUS `INPUT` 变量逐条按 materialize 产物转写（`gate_flag 1`、`efield_dir 0`、
`zgate 0.7`、block 三联、`out_chg "1 12"`、`cal_force 1`、`scf_thr 1e-9`、`nspin 1`、
`basis_type lcao`、`ks_solver cusolver`）。

## 4. 结果

### 4.1 验收对照

| 判据（RUNBOOK §2） | 结果 |
| --- | --- |
| 两用例完成并写出 CP 产物 | ✅ `constant_potential_results.json` / `.log` / `_checkpoint.json` / `cp_*/point_*/result.json` / `atst_artifacts.json` 全部存在 |
| 每例 `runtime_evidence.json` 为 `complete` 且含设备/线程/采样事实 | ✅ 两例均 `status: complete`；`requested=inherited=effective=["0"]`、`caller_bound=true`、`allocation_identity=unverified`（站点未提供 `ATST_ALLOCATION_DEVICES`）；采样 68 / 344 个样本，显存峰值 412 / 572 MiB |
| 清单引用证据 sidecar | ✅ 两例 `atst_artifacts.json` 的 `metadata.runtime_evidence` 指向 `runtime_evidence.json` |
| `harness_summary.json` 2/2 且 `bench_record.json` 带修订与作业字段 | ✅ 2/2、`failed=0`、`wall_s=421.528`；记录 `revision.head=e0abb71`、`operator.job_id=1435012`、`partition=4V100`、`qos=rush-1o2gpu`、`approved_by=QuantumMisaka`、`allocated_gpu_hours=0.118` |
| 负例：分配外设备被拒 | ✅ `runtime.devices: [1]` 在 1 卡分配下以冻结消息拒绝：`device index 1 is outside the inherited visible set (size 1)`（位于任何 ABACUS 进程启动之前） |

### 4.2 关键数字

| 项 | `cp-gate-single` | `cp-gate-scan` |
| --- | --- | --- |
| wall / GPU 秒 | 70.1 s | 351.4 s |
| 完成点数 | 1 | 3 |
| `nelec`（每点） | 217.000000000 | 216.9977 / 217.0000 / 217.0027 |
| `residual_mu_eV` | −2.2e−09 | 2.8e−08 / 1.2e−08 / 2.2e−08 |
| ABACUS 构建 / 力调用 | 1 / 1 | 9 / 9 |
| 扫描分析 | — | `C = 1.8608e−03 e²/(eV·Å²)` = 2.98 µF/cm²；`identifiable: false`、`pzc_status: zero-charge-crossing-not-bracketed`（三点窗口不括零电荷点，不作科学结论） |

密度积分误差与补偿恒等式同时被校验并记录：
`density_electron_error = −5.0e−12`（容差 6.1e−08、精度 12）、
`gate_derivative_ev = −1.478`、`dipole_derivative_ev = 7.198`、
`compensation_derivative_ev = 5.720`（均为同一 run 内密度导出的 eV 量）。

## 5. 发现（P2，已修复）：ABACUS 的 `omp` schema 默认值使 `runtime.threads` 失效

**现象**：两例的 sidecar 都记录 `runtime_threads_overridden=1`、
`gauges.runtime_threads_effective=1.0`，最终环境为 `OMP_NUM_THREADS: "1"`，
同时 `MKL/OPENBLAS/NUMEXPR_NUM_THREADS` 保持 8；
worker stderr 首行为
`calculator omp=1 overrides the inherited OMP_NUM_THREADS=8`。
即：`runtime.threads: auto`（亲和掩码 8）与 `runtime.threads: 8` 都**没有**到达 ABACUS。

**根因**：`utils/config_schema.py:1020` 给 `calculator.abacus.omp` 设了
`Field(default=1)`。配置归一化后该字段恒为显式值，`calculators/factory.py:86`
的 `_effective_omp` 因此走「显式值优先」分支（`launch.apply_explicit_omp(1)`），
而冻结语义要求的是「显式 `calculator.*.omp` 优先，`runtime.threads` 的预算在隐式默认下保留」
（接口冻结 §OMP 优先级；DP 侧 `omp` 默认 `None`，不受影响）。
本地复现：`ConfigLoader.normalize(...)["calculator"]["abacus"]["omp"] == 1`，
`_effective_omp(section, None)` 在 `OMP_NUM_THREADS=8`/`ATST_THREADS_SOURCE=auto` 下返回 1。

**影响**：任何 ABACUS（含恒电势）运行都无法通过 `runtime.threads` 获得多线程预算，
证据里的 `threads_source` 与 `gauges.runtime_threads_effective` 会互相矛盾；
GPU 直跑场景（`ks_solver cusolver`）主要是 CPU 侧线性代数受损，站点上未测出失败，
但「runtime 预算生效」这一条无法在 ABACUS 后端上宣称成立。

**修复**（`5e26789`，维护者裁定按方案 A 实施）：`AbacusConfig.omp` 改为
`int | None = Field(default=None, gt=0)`，于是 `normalize_config` 在用户未写该键时
直接省略它（`model_dump(exclude_none=True)`），`_effective_omp` 也就不再看到"显式值"。
显式 `omp` 仍优先并照旧记录覆盖计数；有 runtime 预算时预算保留；两者都缺省时仍写历史默认 1
（由 `resolve_calculator_omp` 写入，而非 schema 物化）。新增三条回归测试：
归一化后的段保留预算、无任何预算时保持 1、schema 契约（未写即缺省、`gt=0` 仍生效）。

### 5.1 修复复验（2026-09-21，SAI 作业 1436782）

同一 fixture、同一目标 μ、同一 `runtime.threads: auto` 的单点用例在修复后重跑（`cp-gate-threads`，
新目录以避免旧 checkpoint 干扰）：

| fact | 修复前（1435012） | 修复后（1436782） |
| --- | --- | --- |
| `environment.threads.OMP_NUM_THREADS` | `1` | **`8`**（与 `cpu_affinity_count` 一致） |
| `MKL/OPENBLAS/NUMEXPR_NUM_THREADS` | 8 | 8 |
| `counters.runtime_threads_overridden` | 1 | **缺失** |
| `gauges.runtime_threads_effective` | 1.0 | **空** |
| worker stderr | `calculator omp=1 overrides the inherited OMP_NUM_THREADS=8` | **空** |
| `runtime.threads` 事实 | `auto` | `auto` |
| 单点 wall | 70.1 s | 32.9 s（同一用例，非受控对照，含缓存/节点差异） |
| CP 结果 | `complete`，残差 −2.2e−09 eV | `complete`，残差 +2.4e−10 eV |

负例（`runtime.devices: [1]`）在同一次作业中再次被拒。基准记录修订为 `5e26789`，
操作者字段（job/QOS）照旧写入；本段证据见归档 `reverify/`。

## 6. 边界与未覆盖

1. 科学结论边界：CP 结果自带 `profile_status: compensated_gate_pending_scientific_acceptance`，
   本轮只证明工作流与 runtime 的组合可运行、证据链完整，不构成恒电势的生产精度验收。
2. 只有 Gamma 采样、单一一套 fixture；未覆盖 `reference_fcp` 边界的真机组合。
3. 站点未提供 `ATST_ALLOCATION_DEVICES`，故 `allocation_identity=unverified`
   （caller-bound 收窄路径已覆盖；allocation token 路径由 P5 与负例覆盖）。
4. 站点遗留：作业 `1431952`/`1431646` 仍停在 `CG`（孤儿进程），与本轮无关但会占用节点。
5. host/SIF 成对、8 图×8 卡、8 ranks/1 卡压力行仍属 P5 未完成矩阵行。

## 7. 证据索引

归档目录 [data/ATST_CP_RUNTIME_20260921/](data/ATST_CP_RUNTIME_20260921/README.md)：
harness 汇总与记录、两例 harness case 报告与 worker 日志（含 OMP 警告原文）、
两例 runtime sidecar 与 CP 产物、staging 清单与作业脚本、负例配置、
两个作业的 `slurm-*.out`。

## 8. 复现命令

```bash
# 本地（材料化 fixture 与配置校验，无 GPU）
python examples/19_constant_potential_Pt/materialize.py <dest> --basis lcao \
  --electrons 217 --dipole --density-precision 12
PYTHONPATH=src conda run -n atst-dev python -m atst_tools.scripts.cli config validate <case>/config.yaml

# 站点（作业脚本见 staging/run-cp-joint.sbatch）
rsync -av staging内容 SAI-new-galileo02:~/atst-cp-runtime-20260921/
sbatch --export=ALL ~/atst-cp-runtime-20260921/run-cp-joint.sbatch
```
