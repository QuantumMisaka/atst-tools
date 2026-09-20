# ATST Runtime 本地真实 GPU 验证 2026-09-21

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 维护（P1/P2 本地真实设备证据；SAI V100 基准仍属 P5）
**责任人**: ATST-Tools maintainers

## 1. 目的

在真实 GPU 上验证隔离运行路径（`atst run --devices/--threads/--telemetry`）
的设备解析、环境绑定、DP 推理与运行证据链路，作为
[GPU 节点调优计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md)
P1/P2 验收的本地真实设备证据。本报告不代表 SAI V100、ABACUS、MPI 或平台
验收。

## 2. 环境

| 项 | 值 |
| --- | --- |
| 主机 GPU | 1 × NVIDIA GeForce RTX 2070 SUPER（8 GiB，驱动 572.70，UUID `GPU-26530a40-880d-9be7-85c5-0e07cd25af54`） |
| Python | 3.10.19（`atst-dev`），源码经 `PYTHONPATH=src` 指向基线工作树 |
| 关键依赖 | ase 3.28.0、numpy 2.2.6、pydantic 2.12.5、deepmd-kit 3.1.2、mpi4py 4.1.2 |
| 模型 | `examples/dp_model_manifest.json` 的 `DPA-3.1-3M`（head `Omat24`，sha256 `86dd3a80…`，`scripts/download_dp_model.py` 校验下载） |
| 输入 | `examples/06_relax_H2-Au/inputs/init.stru` 副本（H2-Au 小体系） |

## 3. 命令

```bash
cd ~/scratch/atst-gpu-local-20260921
CUDA_VISIBLE_DEVICES=0 PYTHONPATH=<repo>/src \
  python -m atst_tools.scripts.cli run config.yaml \
  --devices 0 --telemetry --threads 4
```

配置：`calculation.type=relax`、`fmax 0.2`、`max_steps 20`、DP 计算器
（`head: Omat24`、`omp: 4`）；`--devices 0` 为“可见集合内逻辑序号”。

## 4. 结果

工作流成功（`atst-api-result-v1` `status=success`，relax 收敛，末态能量
−203.7575 eV，wall ≈ 31.5 s），并产出完整证据链：

```text
runtime_evidence.json  status=complete  workflow=relax
devices: bound=true  caller_bound=true  requested=["0"]（--devices）
         inherited=["0"]  effective=["0"]  allocation_identity=unverified
threads: OMP/OPENBLAS/MKL/NUMEXPR=4（source=explicit），cpu_affinity_count=32
counters: dp.calculator_built=1  dp.force_calls=3  counters_scope=process
sampler:  observed，26 samples / 30.5 s
          gpu: uuid=GPU-26530a40…  utilization=6%  memory=3408/8192 MiB
          processes: unavailable（宿主未报告计算进程，记原因不填 0）
manifest metadata: runtime_evidence=runtime_evidence.json
cache: .atst_cache/attempt-1（每 attempt 独立可写目录）
```

## 5. 结论与局限

- 隔离路径在真实 GPU 上完成“请求 → 收窄 → child 绑定 → DP 推理 → 证据”
  全链路；旧调用（无 runtime 键）路径未受影响（全量单测）。
- 局限：单卡 RTX 2070 SUPER、单进程、无 MPI/ABACUS/SIF 参与；采样为宿主
  范围（整卡）值，进程归属在当前环境不可用；未测量并发/吞吐。
- 后续：SAI 4V100 的并发曲线、NEB 图数×卡数映射、DP image-parallel NEB
  E2E 与 ABACUS 侧基准按计划 P5 执行（需维护者确认 fixture/容差/预算）。

## 6. MPI image-parallel DP NEB（同日追加）

P0 复核指出的“DP 模型的 mpi4py 并行 NEB 从未运行”在本机首次打通：
同一模型、5 帧链（3 内部图）、MPICH 拉起 3 个 rank，每 rank 走
`runtime` 绑定路径（`--devices 0`，单设备池）后运行 NEB：

```bash
CUDA_VISIBLE_DEVICES=0 mpiexec -n 3 python -m atst_tools.api.runner \
  --config config.yaml --workdir runD --result-json result.json \
  --devices 0 --telemetry --threads 4
```

结果（`runD`）：`status=success`，FIRE 6 步（`max_steps=6`，未达 `fmax=0.5`
收敛判据，按配置有界结束并给出英文警示），轨迹 35 帧；`runtime_evidence.json`
记录 `mpi.world_size=3`/`local_rank=0`、`bound=true`、
`requested=["0"]/inherited=["0"]/effective=["0"]`、rank 0 进程计数
（`dp.calculator_built=2`、`dp.calculator_reused=1`、`dp.force_calls=9`）
与 45 个宿主采样（峰值 3219/8192 MiB，3 个 rank 共享一卡）。

串行等价对照（同配置 `mpiexec -n 1`，串行回退告警可见）：35 帧逐帧比较
`max |ΔE| = 1.4e-06 eV`、`max |ΔF| = 1.9e-06 eV/Å`，即与串行数值等价。

本轮同时修复两个真实缺陷（均带回归测试）：

1. runner 直接入口 re-exec 时把相对 `--config`/`--workdir` 传给了子进程，
   子进程在工作目录内解析导致 “Configuration file …/<workdir>/config.yaml
   not found” 并产出嵌套目录；
2. plan 构建发生在 chdir 之后，路径基准错误（现已按调用者目录解析为绝对路径，
   且在进入工作目录之前完成 plan）。

局限：3 ranks 共享单张消费级 GPU，未测吞吐/加速比，也未涉及站点 OpenMPI、
SIF、ABACUS 与 4×V100；这些仍按计划 P5 执行。

## 7. 本地并发小实验（P3 harness 实跑；非 P5 结论）

P3 harness 以**真实 worker**（非替身）在本机跑同一清单两遍：`--slots 1`
（串行）与 `--slots 2`（两个 case 共享 GPU 0，隔离 `workdir`）。case 为
66 原子 H2-Au / DPA-3.1-3M / relax 12 步（fmax 0.2 与 0.3）。

| 变体 | makespan | caseA wall | caseB wall | 采样峰值显存 | 利用率 mean/max |
| --- | --- | --- | --- | --- | --- |
| 串行（slots=1） | 46.3 s | 30.7 s | 15.6 s | 3219 MiB | 14.8% / 20% |
| 并发（slots=2） | 30.3 s | 30.3 s | 16.2 s | 3214 MiB | 10.9% / 18% |

- 两个 case 共享一卡时**单案墙钟几乎不变**（±2%），批次 makespan 46.3 s →
  30.3 s（≈1.5×）；显存峰值无增长；GPU 利用率本身很低（≤20%），说明这类
  小体系 DP 推理在消费级卡上远未饱和。
- 每 case 报告（`harness_case.json` + `atst_api_result.json`）与 sidecar
  （`runtime_evidence.json`，含 `dp.calculator_built`/`dp.force_calls` 与
  `dp.cached_instances` gauge）齐全；批次汇总保留全部 case 与卡时。
  （复跑确认：harness 默认注入 `ATST_TELEMETRY_ENABLED`，即使 case 的 YAML
  没有 `runtime` 段也会写出 sidecar——审查 F3 的修复验证。）
- **边界（不可外推）**：单张 RTX 2070 SUPER、66 原子、12 步短程 relax、
  2 slots、单次重复、无 ABACUS。它只支持"P5 值得测每卡多进程"这一假设，
  不构成 V100/生产体系或并发默认值的结论；P5 仍按矩阵做 ≥3 次交替重复。

本轮同时定稿 harness 运行语义（实现与文档一致）：case 默认在**配置文件所在
目录**运行（ATST 相对 YAML 路径按 cwd 解析）；显式 `workdir`（相对批量输出
目录）用于隔离并发场景；报告、worker 日志与 `atst_api_result.json` 一律写入
`<out>/<case_id>/`。

## 8. harness 驱动的 MPI 图像并行 case（P3×P4 组合，本地）

用 P3 harness 直接驱动 §6 的 3-rank DP NEB（case 级 `launcher:
["mpiexec","-n","3"]`、`slots: 1`、隔离 `workdir`）：

```bash
python -m atst_tools.bench.harness --manifest cases.json --out runs \
  --devices 0 --slots 1 --cpu-budget 16
```

结果：`succeeded`，wall 60.0 s、`gpu_seconds=60.0`（1 卡槽 × wall）、
`atst_api_result.json` 由 rank 0 写出；sidecar 记录 `mpi.world_size=3`、
rank 0 计数（`dp.calculator_built=2`、`dp.calculator_reused=1`、
`dp.force_calls=9`）与 79 个采样。

复跑（含 rank 求和）：sidecar 新增 `counters_mpi`（`scope: sum-over-ranks`，
`world_size=3`）——`dp.force_calls` 由 rank 0 的 9 汇总为 **23**、
`dp.calculator_built` 4、`dp.calculator_reused` 1、
`dp.cached_instances`（gauge 求和）1，即 3 个 rank 的独立模型上下文与调用
总量第一次有了作业级证据；`counters`/`gauges` 仍保留 rank 0 的进程级原始值。

实现侧同步补齐（均带测试）：case 级 `launcher`/`args`（`"mpiexec -n 3"` 或
列表皆可）；worker 启动失败（缺 launcher/二进制）记为该 case 的
`spawn_error` 失败证据，而不是让整批崩溃；`tests/integration/
test_bench_harness_mpi.py` 覆盖真实 launcher 下的 dry-run case。站点侧注意：
`launcher` 需要绝对路径或已 `module load`（P5 现场按 `$sai-user-guide` 填写）。

## 9. DP 单次推理成本剖面（本地微测量；回答"谁主导墙钟"）

对同一张 66 原子 H2-Au 结构、DPA-3.1-3M（PT 后端）做逐次计时（每次
`rattle` 强制重算 E+F）：

| 量 | 实测（本机 1×RTX 2070 SUPER，桌面共享该卡） |
| --- | --- |
| `import deepmd` | 0.09 s |
| 模型加载（每 worker） | ≈ 5.1–5.3 s |
| 首次调用（预热/编译/邻居表） | ≈ 4.8–8.0 s（前 3 次合计 ≈ 19.5 s） |
| 稳态 E+F | ≈ **0.56–0.58 s/call**（中位 2.67 s 含预热） |
| 运行期 GPU 利用率 | ≤ 20%（`nvidia-smi` 采样；卡上另有桌面 Xwayland ≈3.2 GiB） |

结论与影响：

- 对 66 原子、DPA-3.1-3M 这类模型，**单次 E+F 延迟由 CPU/调度侧主导**
  （0.57 s/call 而 GPU 利用率 ≤20%）——与 P0 复核中"Sella 成本在 CPU 侧"
  的直觉部分一致，但主导项是 DP 推理调用本身，而不是 Sella/JAX 的坐标运算
  （`atst-dev` 里 jax 为 CPU-only，Sella 的 jacfwd/vmap 亦走 CPU）。
- 每 worker 存在 ≈10–13 s 的固定成本（模型加载 + 首次调用预热），解释了
  12 步 relax（3 次力调用）为何仍需 ≈30 s：3×冷调用 ≈19.5 s + 加载 ≈5 s。
- 因此"每卡多进程"对小体系几乎无单案减速（§7），而真正的大收益方向是
  摊薄固定成本与多卡摊分调用（P5 测量）。

边界：消费级卡 + 桌面共享、DPA-3.1-3M 类别、batch=1、无 ABACUS；ft2dp
记录的 105 原子 120–184 ms/call 属更小模型世代，两者不可直接比较。P5 必须
在 V100 与 FT²DP/科学 fixture 上重测该剖面，并记录 `DP_INFER_BATCH_SIZE`
与线程档位。

## 10. TF 后端维度：本地不可达（已定位原因）

计划 P2 要求“DP 按 TF/PT 后端分别验证线程、加载和显存”。本机现状：

- `atst-dev` 同时具备 `tensorflow 2.19.1`、`torch` 与 `deepmd.tf`（导入成功），
  故 **TF 运行时可用**；PT 路径已由 §4/§6/§7 验证。
- 缺少 TF 格式模型制品。尝试用 `dp --pt convert-backend DPA-3.1-3M.pt x.pb`
  现场产出时失败：`KeyError: 'type_map'`，栈底为
  `deepmd/pt/model/model/__init__.py:250 get_standard_model`——该转换入口按
  标准（DPA-1/2 风格）PT 模型解析，不支持 DPA-3.1 多任务模型类；与 FT²DP
  记录中 `.pt2` freeze/转换工具的历史缺陷一致。

结论：TF 后端验证需要 TF 原生制品（例如来自科研侧 freeze 流程），本地无法
由现有 `.pt` 制品派生；列为 P5 站点侧的可选项（若届时存在 TF 模型），
本轮不做未经验证的 TF 声明。

## 11. 装包路径（wheel）直连 runner 的端到端复核

用干净安装的 wheel（`pip install <wheel>` 到独立 venv）直连
`python -m atst_tools.api.runner --devices 0 --telemetry --threads 2`
跑 66 原子 DP relax（YAML 同时给 `calculator.dp.omp: 4`）：

- 结果文档 `status=success` 且 `runtime.status=complete`、`evidence` 指向 sidecar；
- sidecar：`counters.dp.calculator_built=1`、`dp.force_calls=3`、
  **`runtime_threads_overridden=1`** 与 gauge `runtime_threads_effective=4.0`
  （显式 `dp.omp=4` 覆盖 runtime 预算 2，冻结 §6 的记录要求在此路径落地），
  `environment.threads.OMP_NUM_THREADS=4`、`threads_source=explicit`；
- 另有一次故意用错相对输入路径的对照运行：错误以 `status=error` 文档 + 退出码
  2 呈现（错误路径行为正确）。

该复核发现的 DP `omp` 覆盖未记账缺口已修复（`runtime/launch.py::
apply_explicit_omp`，DP 工厂改用；ABACUS/MD 走 `resolve_calculator_omp`），
并新增两条工厂级测试（覆盖记账、无 `omp` 时保留继承预算）。

## 12. 重复交替并发测量（本地，3 repeats × 2 variants）

新增 P5 用驱动器 `src/atst_tools/bench/sweep.py`（变体间交替顺序、每
(variant, repeat) 独立目录、汇总 makespan/成功数/卡时/成功案每小时）后，
在本机对同一 2-case 清单实测：

```bash
python -m atst_tools.bench.sweep --manifest cases_isolated.json --out sweep_local \
  --devices 0 --slots 1,2 --repeats 3 --cpu-budget 16
```

| 变体 | makespan 三次值 | 中位 | 成功 | 卡时中位 | 成功案/小时 中位 |
| --- | --- | --- | --- | --- | --- |
| slots=1（每卡 1 案） | 43.88 / 44.59 / 44.58 s | **44.58 s** | 6/6 | 44.58 | 161.5 |
| slots=2（每卡 2 案） | 29.74 / 29.51 / 29.50 s | **29.51 s** | 6/6 | 45.44 | 244.0 |

运行顺序为 (1,2) → (2,1) → (1,2)，符合冻结矩阵的"交替重复"要求；两个变体
卡时几乎相同（44.6 vs 45.4）而 makespan 缩短 1.51×，与 §7/§9 的"该模型/
该卡远未饱和、共卡几乎零单案代价"一致。

边界：单张 RTX 2070 SUPER、66 原子、2 个变体、3 repeats；**不构成 V100 或
生产体系的默认并发结论**。P5 仍按矩阵扩展到 1/2/3(–6) 变体、更多卡与
FT²DP/ABACUS fixture，并把 `DP_INFER_BATCH_SIZE`、线程档位与仓库快照写入
汇总。

本轮同时用新增的 `python -m atst_tools.bench.record` 为上述测量生成了归档
记录 `bench_record.json`（位于该次运行的 scratch 目录）：`atst-bench-record-v1`
文档记录 atst 修订（`feature/gpu-node-tuning` @ `36f4d26`，dirty=false）、
解释器与依赖版本、宿主机 GPU 清单（RTX 2070 SUPER UUID）、manifest 与
DPA-3.1-3M fixture 的 sha256、两个结果目录的摘要（sweep 变体中位 44.582 /
29.507 s，均为 6/6 成功）以及显式为 null 的操作者字段（job/partition/QOS/
卡时/sacct/批准人），供 P5 站点运行时逐项补齐。

## 13. FT²DP 单头 100k 本地接入（2026-09-21 追加；非 P5 结论）

P5 的 DP 科研候选（FT²DP 单头 100k，sha256 `13b74797…`，62 MB）在本机做了
三层验证，全部通过后可作为 P5 的加载基线。

**13.1 运行时兼容性（DPA4/SeZM）**。该 checkpoint 是 DPA4/SeZM 类模型：

- `deepmd-kit 3.1.2`（`atst-dev`）加载即失败：`RuntimeError: Unknown model type: dpa4`；
- `deepmd-kit 3.2.0b1.dev62+gac8e4301b`（`dpa4-dpmd-v100`）与
  `3.2.0b1.dev67+g73de44b1f`（`dpeva-dpa4`）均可加载（加载时提示 missing keys，
  均为 checkpoint 旧字段），同一结构单点一致：Fe4O6_bulk_10at 上
  E = −127.61422944 / −127.61423707 eV、Fmax = 0.70834083 / 0.70833883 eV/Å
  （ΔE = 7.6e-06 eV、ΔF = 2.0e-06 eV/Å）。

**13.2 atst 隔离路径冒烟**。以 `dpa4-dpmd-v100` 为底座建 venv
（`--system-site-packages`，补装 `ase 3.29.0`、`pydantic 2.13.4`、`sella`、
`mpi4py 4.1.2`），`PYTHONPATH=src`、`CUDA_VISIBLE_DEVICES=0` 下跑 66 原子
H2-Au relax（`fmax 0.5`）：`status=success`、E = −3498.0803 eV、
`attempt_s = 10.25`、`counters.dp.force_calls = 1`；sidecar
`atst-runtime-evidence-v1` 状态 `complete`（设备事实 inherited/effective
`["0"]`、线程 4、`dp.calculator_built = 1`）。

环境注意（P5 运行手册已并入）：SeZM 内建近邻表需要可见 `libcuda.so`
（WSL 为 `/usr/lib/wsl/lib`，缺失时报 `failed to compute neighbors`）；
relax 工作流需要 `sella`；mpi4py 需要与 launcher 一致的 `libmpi`。

**13.3 FT²DP + mpi4py 图像并行 NEB**（chain5：3 内部图、6 步、
`endpoint_singlepoint: always`）：

| 变体 | 墙钟 | `dp.force_calls` | 备注 |
| --- | --- | --- | --- |
| 串行（`parallel: false`，1 rank） | 16.61 s | 62（rank 0） | 单 calculator 复用 |
| 图像并行（`parallel: true`，3 ranks） | 20.56 s | 23（`counters_mpi` rank 求和） | 每 rank 建模型 |

35 帧逐帧对照：**max |ΔE| = 2.97e-05 eV、max |ΔF| = 1.27e-05 eV/Å**，
即该模型在图像并行下与串行等价。小 band 上并行反而慢 24%：每 rank 有
≈5 s 模型加载固定成本，与 §9 的墙钟构成一致；"图数 ≤ 卡数"的收益必须在
P5 的大 band/真实 GPU 负载下按矩阵验证。

边界：单张 RTX 2070 SUPER（WSL2）、3 内部图、6 步短程 NEB、单次测量；
不构成 V100/生产结论，也不改变 P5 的重复与矩阵要求。

## 14. FT²DP P5 预演：并发/线程矩阵与预算（本地，非 P5 结论）

用 P5 的科学模型（FT²DP 单头 100k）与 66 原子 H2-Au relax（`fmax 0.05`、
8 步、`dp.force_calls = 9`）预演 P5 前两项验收的测量形状；命令与产物在
`~/scratch/atst-p5-staging-20260921/batch-ft2dp/`（wheel 安装方式，
`atst_tools 2.2.6`，pytest 之外的独立 venv）。

**14.1 计时扫描（`slots 1/2/3` × 2 repeats，无 per-case 采样）**

| 变体 | makespan 中位 | 成功 | 卡时中位 |
| --- | --- | --- | --- |
| slots=1 | 26.23 s | 4/4 | 26.19 |
| slots=2 | 13.69 s | 4/4 | 27.07 |
| slots=3 | 13.49 s | 4/4 | 26.89 |

两个 case（threads 1 与 4）在 slots=2 下几乎完美重叠（批次墙钟 ≈ 单 case 墙钟）；
slots=3 不再改善——清单只有 2 个 case，可并发度上限即 2。

**14.2 证据 pass（`slots 1/2`，`--case-telemetry`）**

| 变体 | case | attempt | `dp.force_calls` | GPU util mean/max | 显存峰值 |
| --- | --- | --- | --- | --- | --- |
| slots=1 | t1 | 10.83 s | 9 | 13.7% / 29% | 3996 MiB |
| slots=1 | t4 | 10.04 s | 9 | 7.7% / 15% | 3379 MiB |
| slots=2 | t1 | 10.52 s | 9 | 9.8% / 20% | 4803 MiB |
| slots=2 | t4 | 10.54 s | 9 | 9.8% / 20% | 4803 MiB |

单 case 墙钟几乎不随并发变化（±5%）；显存峰值由 ~3.4–4.0 GiB 升到 4803 MiB
（两个 SeZM 模型同时驻留）；利用率仍 ≤29%，与 §9/§12 的"该规模远未饱和"一致。
threads 1→4 在该模型/该规模上只差 ~7%（每 worker ≈5 s 模型加载固定成本主导）。

**14.3 顺带修掉的证据完整性缺陷**：首轮预演发现两个 case 若共享同一
`workdir` 值，会在同一 (variant, repeat) 内互相覆盖 sidecar/traj/结果文件。
`bench/harness.py` 现在拒绝重复的非空 `workdir`（错误信息列出冲突值与
case id），示例模板与单测同步更新；本节数据即用修复后的版本重跑。

**14.4 归档记录**：`batch-ft2dp/bench_record.json`（`atst-bench-record-v1`）记录
解释器/依赖、GPU 清单（2070S UUID）、manifest 与 FT²DP 权重 sha256、结果目录
全树哈希与显式 null 的操作者字段；由于从 wheel 运行，`revision` 三键为 null ——
登台手册因此改为在 SAI 克隆 git bundle，使 P5 记录携带真实 `head/branch/dirty`；本地已用 bundle 克隆复验：同一清单重跑后 `record_time`/`run_time` 均为 `branch=feature/gpu-node-tuning`、`head=e853852`、`dirty=false`。

边界：单张消费级卡、2 个 case、2 repeats；P5 仍须在 V100 上按 ≥3 次交替重复
执行并覆盖 ABACUS 通道，本节的数字只证明测量形状与工具链可用。
