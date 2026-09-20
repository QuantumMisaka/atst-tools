# ATST GPU 节点优化开发与验证计划

**版本**: 2026-09-20（2026-09-21 迁入 atst-tools 规范源）
**日期**: 2026-09-20
**状态**: 执行中（P0）
**责任人**: ATST-Tools maintainers

> **迁移记录（2026-09-21）**：本计划已由发起方 ABACUS 文档目录迁入 atst-tools 规范源并在文档账本登记；设计源为 [GPU 节点调优设计](../specs/2026-09-20-atst-gpu-node-tuning-design.md)，P0 接口冻结为 [runtime 接口冻结设计](../specs/2026-09-21-atst-runtime-interface-design.md)。原位置只保留交接说明，不得独立演进。

**Goal:** 先交付 atst 单节点设备隔离、运行证据和可复现优化，再分阶段接入平台。
**Spec:** [GPU 节点调优设计](../specs/2026-09-20-atst-gpu-node-tuning-design.md)；分期范围已确认，具体接口设计待实施前收敛。
**Authorization:** 2026-09-20 用户要求系统明确开发/工程化方案，并确认“先 atst，后平台接入”；本轮为设计与计划整理，未开始代码实施、真实计算、依赖同步或发布。
**Architecture:** 保留进程内 API，扩展轻量进程启动边界；设备选择、case 并发、MPI rank 绑定、宿主计量各有 owner。
**Verification:** CPU 行为/子进程测试 → site-compatible MPI 测试 → 经授权的 GPU 数值/性能基准 → 后续平台 E2E。
Status: in_progress (P0)

**实施 owner：** atst-tools 维护者已接手 P0–P5 与 P6 的 atst 交付部分（2026-09-21 迁移完成，规范源为本仓）；ABACUS/MLIP-Agent 开发者仅承接后续平台适配。不要求在 ABACUS Toolbox 内实施通用 runtime；实施基线为 `origin/main` `2cf5b7e6`（SPEC §11 R1）。
**测试环境依据：** 显式使用 `$sai-user-guide`（§2–§5、§7–§8、性能调优 reference；涉及 SIF 时 §11）；双后端与 FT²DP fixture 规则见 SPEC §7.3，恒电势协调见 §7A。

## 组件与边界

atst 路径以下均相对于 `deps/atst-tools`；源码落点相对 `src/atst_tools/`（如 `scripts/cli.py` 指 `src/atst_tools/scripts/cli.py`，仓级 `scripts/` 只放 CI/治理脚本）。下表为预期修改位置，不强制创建指定的新模块。

| 组件 | 修改位置 | 交付责任 |
| --- | --- | --- |
| 设备解析/启动 | `src/atst_tools/` 下轻量 runtime 模块、包初始化、`scripts/cli.py`、`api/runner.py` | 初始化前绑定、隔离启动及错误诊断 |
| YAML/API | `utils/config_schema.py`、`api/models.py`、`api/services.py` | 可选 runtime schema、保持嵌入 API 与既有结果兼容 |
| backend | `calculators/dp.py`、`factory.py`、`abacuslite_backend.py` | 线程/模型/command 适配，不重写 solver |
| MPI | `utils/mpi.py`、`scripts/main.py`、`mep/autoneb.py` | 图像 ownership、绑定验证、失败同步 |
| 证据 | `utils/artifacts.py`、API result metadata、workflow instrumentation | stage/rank 证据与采样来源 |
| 基准 | `examples/` 或 `scripts/` 的独立 harness 与 fixture manifest | 已有 allocation 内有限队列、清理、宿主采样和汇总 |
| 后续平台 | ABACUS `toolkits/transition_atst.py` 等、MLIP runtime adapter | 单独变更各自 owner 契约；首期不修改 |

## P0：冻结可实现的输入/执行边界

依赖：无。交付设备选择、runtime schema 与进程入口的准确草案，整理已有测试与代表 fixture。

- [x] 读取实施工作树的 AGENTS 与文档入口，记录 atst/DP/ABACUS/ASE/MPI/JAX 实际版本（2026-09-21：接口文档 §1 记录 `atst-dev`、`dpa4-dpmd-v100` 实测清单与“解释器、包路径、dist 版本”三元组要求）。
- [x] atst 维护者选定实际基线（2026-09-21 复核各树 pin 后裁定 `2cf5b7e6`，SPEC §11 R1）；runner/schema/model manifest 差异已按该基线核对。
- [x] 与恒电势约定共享文件合入顺序和字段归属：清单与顺序见接口文档 §8；29 个在途文件已由维护者指示 checkpoint 提交（`7bc3f92`，验证 105 passed + 治理通过）；**合入 main 仍由恒电势 owner 决定**，共享面落点仍按 §8 顺序（恒电势先、GPU 后）。2026-09-21 复核（接口文档 §8.2）：`feature/gpu-node-tuning` `eaa7e22`（38 提交）× `7bc3f92` 的 merge-tree 预演仍无冲突，合并树共享面聚焦 141 项仅 §8.1 的两项 CP 侧门禁失败。
- [x] 定义参数类型、CLI/YAML/env 优先级、inherit/空值/UUID/非法 ordinal 行为；概念字段转成唯一 schema（接口文档 §2–§4）。
- [x] 定义 CLI 和 runner bootstrap 的一次性 exec/child 路径，核查包导入链；嵌入 API 保持不隐式启动进程（接口文档 §5）。
- [x] 选 DP 模型/backend/head 和 ABACUS fixture；列出原稿 job 证据待补项，不把假设写为基线（接口文档 §7）。
- [x] 双后端 fixture 均进入验收清单；DP 包含通用回归与只读 FT²DP 钉版 `.pt` 候选，回读模型 manifest 核实身份和运行兼容（接口文档 §7；权重回读在执行阶段完成）。沿用科研目录只读输入，新结果单独存放，不将普通 FT²DP 势标为恒电势模型。
- [x] 准备现有 legacy API/CLI/YAML 基线和代码 owner 测试；相称独立设计审查后进入 P1。基线套件已执行（`PYTHONPATH=src` + `atst-dev`，877 collected、exit 0）；独立设计审查 2026-09-21 完成：**block**（3 blocker + 7 major）→ rev.2 修订（SPEC §11 R5/R6）→ 复审 **approve with required changes**，N1–N10 已在 rev.3 全部闭合；P1 已在其后实施（实施记录见账本）。

验收：开发者能明确处理 `CUDA_VISIBLE_DEVICES=2,3` + 逻辑0、显式空掩码、过度暴露、已初始化 API、自定义 communicator/callback，无需临场决定产品语义（逐场景对照表见接口文档 §9）。P0 只做本地静态设计，不需要运行 GPU。

## P1：设备解析与进程隔离

依赖：P0。对应 SPEC §4。

- [x] 先写行为测试：mask 顺序、UUID、缺失/空值、越界/重复、可信 allocation 收窄及 unsupported MIG；已知过度暴露但无获配身份必须拒绝，未知身份的 standalone inherit 保留未验证标记，不能用于共享池（`tests/unit/test_runtime_devices.py`、`test_runtime_launch.py`、`test_runtime_dispatch.py`、`test_runtime_schema.py`；全量 951 项通过）。
- [x] 实现纯解析与必要短命枚举 helper；coordinator 不初始化 CUDA，不扩大可见性/分配（`src/atst_tools/runtime/devices.py`，枚举仅经 `nvidia-smi` 短命查询且可注入替身）。
- [x] 调整轻量 bootstrap/import 链，复用 API runner；启动前设置 child env/cwd/cache/threads（`runtime/launch.py` 构造 child env 与 worker 命令；`scripts/cli.py` 变为轻入口、重实现在 `cli_impl.py`；`api/__init__` PEP 562 惰性导出；runner 惰性导入并在绑定后 re-exec 自身）。
- [x] 子进程替身记录实际 env 与 import 顺序；验证父进程 env/cwd 不变，失败和取消不遗留子进程（`test_runtime_entry.py`：stand-in 记录 env/facts；导入 smoke 断言 NumPy/ASE/JAX 等未加载；父进程 env 快照相等；exec 语义不留子进程）。
- [x] 验证未指定新字段的 CLI/API 输出、callback、communicator 和 manifest 消费行为；embedded rebinding 明确拒绝（legacy 运行不新增 `atst_api_result.json`/`atst_artifacts.json`；`ensure_runtime_contract` 的嵌入拒绝与 worker 一致性校验）。

验收：CPU 替身证明执行边界和兼容（已完成，见上）；真实 GPU 身份验收留到 P5，不以 mock 宣称 GPU 已验证。用户可见文档（`CONFIG_REFERENCE`、`CLI_REFERENCE`、`USER_GUIDE_CN`）按接口文档 §8 在恒电势合入后的文档合并步更新；`YAML_INPUT_VARIABLES.md` 已随 schema 重新生成。

## P2：线程/backend 与运行证据

依赖：P1。对应 SPEC §4.3、§5.3、§6。

- [ ] 在初始化前应用明确的线程预算，覆盖 CPU affinity/cpuset 与 DP TF/PT 差异；不静默覆盖用户已有科学配置（线程预算/affinity 已实现并验证；TF 维度本地不可达——TF 运行时在但无 TF 制品，`dp --pt convert-backend` 对 DPA-3.1 失败，见验证报告 §10；留待 P5 有制品时补测）。
- [ ] 计量端点、active window 和最终补算的模型构建次数、存活对象与显存；保留合法进程内复用，验证独立可写缓存和只读模型共享。若优化生命周期，补跨 image 的 atoms/results 状态隔离与重启回归，不承诺未经证明的每 worker 单实例。
- [ ] ABACUS 按实际 command 验证 launcher；复用现有 MPI 清理、profile 和 backend 选择。
- [ ] 增加 opt-in runtime sidecar、阶段耗时、初始化/力调用计数与版本来源；成功关联 manifest，失败保留部分证据（首片 2026-09-21：`runtime/evidence.py` 的 sidecar `atst-runtime-evidence-v1`、manifest `runtime_evidence` 引用、环境/设备事实、rank 0 单例宿主采样、失败保留 `partial`、计量失败不阻断运行；第二片：`runtime/counters.py` 进程级计数器（`dp.calculator_built/reused`、`dp.force_calls`、`abacus.calculator_built/force_calls`）随 sidecar 输出并标注 `counters_scope=process`；第三片：MPI 成功路径在 collective 后输出 `counters_mpi`（rank 求和，含 `world_size`）；剩余：阶段耗时明细与结果 envelope 的 `runtime` 摘要）。
- [ ] 宿主 sampler/parser 区分 device/process，覆盖缺工具、权限不足、短任务无样本、MPS 归属未知和采样失败。

验收：计量失败不掩盖科学运行结果；显式 GPU 不可用仍报执行错误；现有结果消费者可忽略新增可选字段。线程调优带来的真实收益由 P5 证明。

## P3：独立 case 参考 harness

依赖：P1/P2。对应 SPEC §3、§5.1。

- [x] 有限清单包含 case id、输入、输出目录、设备槽位、线程和超时；不引入跨作业服务（`src/atst_tools/bench/harness.py` 的 `CaseSpec`/manifest；模板 `examples/runtime_batch_cases.example.json`）。
- [x] 每卡并发默认1，显式候选2–6；调度以 GPU 和 CPU 可用预算共同限流（`slots_per_device` 默认 1；`cpu_budget` 取 `ATST_BATCH_CPU_BUDGET` 或 `sched_getaffinity`，线程和在途数超预算即等待）。
- [x] 子进程测试验证槽位上限、独立目录、结果汇总、失败继续/停止策略、取消和超时后回收（`tests/unit/test_bench_harness.py`：替身 worker 记录 start/end 时序、超时后整组回收（子进程 PID 消失）、取消标记；停止策略 `stop_on_failure`）。
- [x] OOM/unknown 分类保持证据，不默认 retry；显式 retry 使用新 attempt（`classify_exit` 记 `oom`/`exit N`/`signal N`/`unknown`；无隐式重试，attempt 字段留给显式新行）。
- [x] 一个 allocation 一个 sampler，记录全部任务结果和卡时，失败 case 不从分母/清单消失（`HostSampler` 单例；`harness_summary.json` 含 cases_total/succeeded/failed/timed_out/skipped、gpu_seconds、逐 case 行；skipped case 也写 `harness_case.json`）。

验收：有限 batch 完成或有界退出；无外部排队/重新申请资源，无全节点进程清理（结构保证 + CPU 替身测试；真实 SAI 作业运行留 P5）。生产 batch CLI 不在本阶段。

## P4：MPI 绑定与图像语义

依赖：P1/P2；可与 P3 独立推进。对应 SPEC §5.2。

- [x] 保持 NEB interior / AutoNEB `n_simul` rank 数约束，明确内部图和端点计数（`utils/mpi.py::validate_image_parallel_world` 与 `mep/autoneb.py` 校验保持；`tests/unit/test_mpi_parallel.py` 覆盖拓扑）。
- [x] 实现 inherit 与单节点共同池 round-robin；验证 local rank、逐 rank 可见性和共享上限（`runtime/devices.py::_apply_round_robin`；真实 MPICH 2-rank 集成测试 `tests/integration/test_runtime_binding_mpi.py` 断言 rank 掩码互异；共享上限由池语义与调用方槽位共同约束）。
- [x] CPU fake-world 覆盖10/4、10/1、越界、不同 rank mask、零设备、多节点拒绝共享模式（越界/零设备/多节点拒绝在解析层；10/4 与 10/1 拓扑与逐 rank 掩码在 `test_mpi_parallel.py` 与真实 MPI 集成测试中覆盖）。
- [x] 使用真实 MPI + 无 GPU calculator 验证端点、active window、rank-local 配置异常、rank 崩溃和超时回收（既有 `tests/integration/test_mpi_failure_sync.py` 17 项：端点同步、rank-local 配置/链读取/manifest/预检失败释放、AutoNEB active window、超时回收；本地 MPICH 全绿）。
- [x] 验证每图 ABACUS 内部仍单 rank，无 nested MPI；DP 各 rank 模型上下文独立，容量以实测驻留为准（atst 侧契约由 `calculators/factory.py` 的 command/mpi 与既有 image 语义测试保证；DP 驻留容量测量归 P5）。
- [x] DP 后端 image-parallel NEB 首个 E2E（P0 复核新增）：本地 MPICH 3 ranks 完成（`world.size == interior_images == 3`，`mpi.world_size=3` 记录于证据），与串行对照逐帧等价（max |ΔE| 1.4e-06 eV / |ΔF| 1.9e-06 eV/Å），并修复 runner re-exec 相对路径与 chdir 基准两个缺陷；证据见 `docs/reports/ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md` §6。站点 OpenMPI/SIF 与收益/容量曲线仍在 P5 测量。

验收：科学计算前错误在各 rank 或 launcher 层有界结束；fake-world 不替代真实 MPI 证据。10 ranks/1 GPU 只在后续容量许可时计算。

## P5：经授权的 SAI GPU 基准

依赖：P2/P3/P4 通过。对应 SPEC §7。

- [ ] 真实运行前确定 fixture、各项数值容差、最大并发/时长/卡时与停止条件，实时核验 QOS 和实际 CPU/GPU 配额。
- [ ] 依据 SAI guide 核验提交方式、module/MPI、存储与 sampler；分别记录 ABACUS 环境和模型匹配 DP 环境，不能以版本下限代替 DPA4 加载验证。
- [ ] 先单 worker 身份/数值验证，再短矩阵；出现 OOM、数值不合格或并发收益饱和时停止扩大该分支。
- [ ] 固定配置对比冷启动/稳态和同 allocation 吞吐；分开报告增加资源的收益。
- [ ] 候选正式点至少三次交替重复，保留失败；host/SIF 成对验证，采样开/关检查观测开销。
- [ ] 归档输入/环境身份、原始结果、采样、汇总与可重跑命令；报告适用范围，不输出通用每卡并发默认值。
- [ ] DP 推理并发曲线（P0 复核新增）：同 allocation 每卡 1/2/4 个独立进程；记录 GPU 利用率、显存、成功 case/hour 与卡时/成功案；不采信“墙钟只随 CONC 缩放”的无据断言。
- [ ] NEB 图数 × 卡数映射（P0 复核新增）：4/8 内部图 × 1/2/4/8 卡；验证“图数 ≤ 卡数”的延迟收益与 8 ranks/1 卡的压力边界。
- [ ] 推理侧 GPU 采样（P0 复核新增）：利用率/显存/样本覆盖，复用 P2 sampler；无采样工具时记 `unavailable`、不得填 0。

验收：工程和科学门禁通过后才可比较性能；无显著提升如实报告，不强行满足“2倍/40%”。首次基准不自动扩展到20条反应或改用其它账号/分区。

ABACUS 与 DP 分别形成 baseline/candidate 证据；允许先完成一条作为阶段交付，但首期“双后端完成”必须两条均通过。无需混跑两种后端，也不要求两种势的能量彼此相等。FT²DP 的模型科学精度评估仍归科研项目，GPU 优化负责同模型/同方法前后等价。

### P5 预备（草案，2026-09-21；真实运行前仍待维护者裁决 fixture/容差/预算）

启动入口：`scripts/sai_runtime_bench.sbatch <work_dir> [cases.json] [devices]`（一条命令跑完"计时 sweep → 证据 pass → 归档记录"，站点 QOS/module 行按 `$sai-user-guide` 现场填写；`DRY_RUN=1` 可先自检命令）。默认时序：计时 sweep（`SLOTS=1,2,3` × `REPEATS=3`，无 per-case 采样）→ 证据 pass（首个 slots 变体 × 1 次，`--case-telemetry`，产出每 case sidecar）→ `bench_record.json`（自动带 SLURM job/partition/QOS 与 `MODEL` fixture 哈希）。清单模板 `examples/runtime_batch_cases.example.json`。每 case 产物：`harness_case.json` + `atst_api_result.json` + `runtime_evidence.json`（证据 pass）+ 批次 `harness_summary.json`。

**SAI 只读勘察结果（2026-09-21，账号 `galileouser02`；未写入远端、未提交作业）**：

- ABACUS：`module load abacus/LTSv3.10.1-sm70-auto`（NVHPC 25.7 GNU-branch / CUDA 12.9.1 / OpenMPI 5.0.8 / ELPA 2025.06；`ABACUS_HOME=/opt/apps/abacus/abacus-develop-LTSv3.10.1`，可执行在 `bin_sm70_avx512`，与 4V100 的 sm70 匹配）。
- Python/DP：**须选 DPA4/SeZM 可加载的构建**——`deepmd-kit/3.1.2` 对 FT²DP 单头 100k 报 `Unknown model type: dpa4`（本地实测）；`module load deepmd-kit/3.2.0` → `/opt/apps/conda_env/deepmd-kit-3.2.0`（Python 3.12.12、deepmd-kit 3.2.0、torch 2.13.0+cu126、mpi4py、numpy；**无 ase/pydantic**）。Lmod 入口实测为 `source /opt/modules/lmod/9.2.4/init/bash; module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps`（`/etc/profile.d/modules.sh` 不生效）；`conda/anaconda3` 24.9.2 为只读 base，用户 env 目录 `~/.conda/envs`。MPI 配对：加载 `openmpi/5.0.8-nvhpc25.7-gnu-auto` 后该 env 的 mpi4py 可用（实测 `from mpi4py import MPI` → Open MPI 5.0.8）；`mpiexec` 同目录。P5 环境计划：以 3.2.0 env 为底座建 venv（`--system-site-packages`），pip 安装 `ase`、`pydantic`、`sella` 与本分支 wheel（登台包见下）。
- MPI/容器：模块化 OpenMPI（默认 `5.0.10-nvhpc26.3-gnu-cuda12-auto`，ABACUS 模块自载 `5.0.8-nvhpc25.7-gnu-auto`）、宿主 `/usr/mpi/openmpi-4.1.7rc1`；`module load apptainer/1.4.4`。
- 分区/QOS（现场快照）：4V100 35 节点（15 idle / 7 alloc / 13 mix）、8V100V0 14（11 idle）、16V100 80（8 idle，多数 alloc）；`rush-cpu` MaxWall 2 天、`improper-gpu` 30 天、`rush-gpu`/`rush-4gpu`/`rush-1o2gpu` 1 天（gres/gpu 16/4/2）、`flood-gpu`/`flood-1o2gpu` 4 小时。账号当前有 2 个恒电势作业占 4V100（QOS `rush-1o2gpu`）；P5 排期需避让同一 QOS 额度。
- 可达性：家目录可写；**`/org/pku-jianghong/liuzhaoqing`（FT²DP `$R`）在本账号下不可读**，组共享（`share/data*`、`share/demo-data`）无 DP 权重，家目录无 `.pt`。→ P5 权重与 fixture 需单向上传。
- 既有镜像：`~/abacus-sif-builds/20260920-toolbox-atst/abacus-adam-sai-toolbox-atst.sif`（1.5 GB，2026-09-20，ATST-free Toolbox 构建）可供 P5 的 SIF 通道；镜像构建使用 QOS `improper-gpu`。家目录中的 atst-tools 副本为 v2.2.3 普通拷贝（无 git、无 `runtime/`），不可作 P5 源。
- 登台包（本地已备，授权后单向拷贝）：`~/scratch/atst-p5-staging-20260921/`——`wheel/atst_tools-2.2.6-py3-none-any.whl`（sha256 `6f43cca2…`）与 `atst-tools-gpu-node-tuning-1cf5c85.tar.gz`（sha256 `17bb4d99…`；由 HEAD 重新导出）；权重 regular 单头 100k（`ft2dp-dpeva/scratch_atp_upload/model.ckpt-100000.pt`，62 MB，sha256 `13b74797…`；`mission_20260920/FT2DPv2.2-single100k-model.ckpt-100000.pt` 为同一文件）；EMA 单头 100k（pin `45667e7f…`）本机仍无（pin 记分卡记 EMA ≈ regular，故默认 regular-only、EMA 复核后补；本机另有 multi200k regular+EMA 包，可提请替代）；通用回归模型 `temp_repos/dp_model/DPA-3.1-3M.pt` 已在本地（sha256 `86dd3a80…`）。

**本地 FT²DP 接入证据（2026-09-21，非 P5 结论；详见验证报告 §13）**：在 `deepmd-kit 3.2.0b1.dev62` 底座 venv（补装 ase/pydantic/sella/mpi4py）上经 atst 隔离 runtime 完成——① 66 原子 H2-Au relax 冒烟：`status=success`、E=−3498.0803 eV、`attempt_s=10.25`、`dp.force_calls=1`、sidecar `complete`；② **FT²DP + mpi4py 图像并行 NEB**（chain5，3 内部图 × 6 步）：串行 16.61 s / 3-rank 20.56 s，逐帧等价 max|ΔE|=2.97e-05 eV、max|ΔF|=1.27e-05 eV/Å；小 band 上并行更慢（每 rank ≈5 s 模型加载），P5 的图数×卡数矩阵需在大 band/真实负载下验证；③ 跨 3.2.0 dev 构建单点一致（ΔE 7.6e-06 eV、ΔF 2.0e-06 eV/Å）。环境注意：SeZM 内建近邻表需可见 `libcuda.so`（本地 WSL 为 `/usr/lib/wsl/lib`；SAI 由 driver/module 提供）；relax 需 `sella`；mpi4py 需与 launcher 一致的 `libmpi`。

**P5 开跑前待裁决（拟值，可直接批注）**：

| 决策点 | 拟值 | 依据 |
| --- | --- | --- |
| DP fixture | FT²DP 单头 100k regular × 66 原子 H2-Au；可选加 Fe4O6/Fe5C2 科学夹具 | §13 本地已通；EMA ≈ regular |
| ABACUS fixture | `examples/06_relax_H2-Au`（cusolver/LCAO）+ `examples/01_neb_Li-Si`（image-parallel） | 站点 module LTSv3.10.1 与既有示例 |
| 数值容差 | DP 并行等价 max\|ΔE\| ≤ 1e-4 eV、max\|ΔF\| ≤ 1e-4 eV/Å；ABACUS host/SIF 阈值开跑前另定 | §13 实测 2.97e-05 / 1.27e-05（余量 ≥3×） |
| 时长/卡时 | 首轮单作业 ≤2 h、QOS `rush-1o2gpu`（≤2 GPU）；`SLOTS=1,2,3 × REPEATS=3`，NEB 矩阵按 4/8 图逐步扩展 | 4V100 现场 15 idle；避让 CP 作业 |
| 停止条件 | OOM、数值门禁失败、或"成功 case/hour 不升且卡时/成功案上升"即停该分支 | 计划原停止条件 |
| 记录 | job/QOS/sacct/批准人写入 `bench_record.json` 操作者字段 | record 生成器已支持 |

并发/重复矩阵入口：`python -m atst_tools.bench.sweep --manifest cases.json --out runs --devices 0,1 --slots 1,2,3 --repeats 3 [--cpu-budget N]`（变体间交替顺序、每 (variant,repeat) 独立目录、汇总 `sweep_summary.json`；默认不产 per-case sidecar 以避免采样噪声，`--case-telemetry` 显式开启；本地已用 3 repeats × slots 1,2 实测，见验证报告 §12）。

归档记录入口：`python -m atst_tools.bench.record --manifest cases.json --out bench_record.json --run-dir runs/sweep --fixture <model.pt> --job-id <slurm id> --qos <qos>`——把 atst 修订（区分 record_time 与 run_time，后者来自 harness/sweep 汇总在运行开始记录的 `revision`）、解释器与依赖版本、GPU 清单、manifest/fixture 哈希、结果目录全树哈希与"操作者字段"（job/partition/QOS/分配卡时/sacct 摘要/批准人）写进一份可复核的 `atst-bench-record-v1` 文档；未提供的操作者字段显式写 null、缺失输入列 `warnings` 并以非零码提示，便于 P5 收尾时逐项补齐。

harness 语义：case 默认在配置文件所在目录运行（ATST 相对路径按 cwd 解析），显式 `workdir` 则相对批量输出目录解析；报告/日志/`atst_api_result.json` 一律在 `<out>/<case_id>/`。站点资源现场事实见上方 SAI 只读勘察块。

本地迷你并发观察（**非 P5 结论**，66 原子/单张 2070S/2 slots，详见 `docs/reports/ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md` §7）：单案墙钟 ±2%，makespan 46.3 s → 30.3 s。P5 仍须在 V100 上按矩阵重复测量。

本地推理成本剖面（**非 P5 结论**，同报告 §9）：模型加载 ≈5 s/worker、首次调用预热 ≈5–8 s、稳态 E+F ≈0.57 s/call（66 原子/DPA-3.1-3M），运行期 GPU 利用率 ≤20% → 单次延迟由 CPU/调度侧主导；P5 需在 V100 上按模型世代与线程档位重测，并报告 `DP_INFER_BATCH_SIZE`。

测量矩阵（SPEC §7.1）与本轮证据缺口对应：

| 组 | 对照 | 记录 |
| --- | --- | --- |
| DP 单 case | 1 卡 × 线程档位（`runtime.threads` 1/4/auto） | 冷/热启动、`dp.force_calls`、wall、GPU 利用率/显存样本 |
| DP 独立批 | 每卡 1/2/3 进程（容量允许再到 4–6） | 成功 case/hour、卡时/成功案、OOM/unknown 分类、并发曲线 |
| ABACUS 独立批 | 串行队列 vs 四卡各一 case | E/F 一致性、wall、实际卡时 |
| MPI NEB | 串行 vs 10 ranks/4 卡 vs 10 ranks/1 卡 | 单 band 延迟、模型复制/内存、`world.size == interior_images`（本地模板已通：case 级 `launcher: [mpiexec,-n,3]` + `slots: 1`，见报告 §8） |
| AutoNEB | inherit / 已验证共享布局 | active window 正确性、端点阶段 |
| 容器 | host/SIF 成对 | 环境/mapping/观测一致性 |

记录清单（每条证据）：环境三元组（解释器/包路径/dist 版本）、作业号与 QOS、`sacct` 卡时、`runtime_evidence.json`、失败原因分类、原始命令。原稿作业 `1422694/1422849/1423160/1423179` 的 `sacct`/日志导出仍是待补项。

## P6：atst 交付及后续平台接入

依赖：P5；平台部分独立排期/授权。

- [ ] 更新 atst `CONFIG_REFERENCE.md`、schema 生成参数表、用户指南、examples、FEATURE_STATUS_MATRIX 与文档账本；发布说明区分 CPU/mock、MPI、GPU、SIF 验证范围。
- [ ] 相称独立终审，按 atst 版本规则发布；父仓依赖同步与 gitlink 更新独立执行。
- [ ] 平台先消费单任务绑定/运行证据，再单独设计共享 image 的参数、resAlloc/prepare/runner 迁移；不重释现有 `n_gpu`。
- [ ] 核对恒电势 Task 3.2 共用 `toolkits/atst_runner.py` 抽取进展，平台 GPU 适配复用届时的 owner 入口；不另造 runner。
- [ ] 更新对应 owner guide 与交接测试，经本地 E2E、授权的平台发布验证后再宣称平台支持；只有新增依赖确需镜像变化时才插入非活动 SIF 候选。

验收：standalone、SIF、本地 E2E、平台验证分别标注；可关闭 opt-in 回到旧入口。缺性能证据不修改生产默认。

## 环境与验收命令

本轮文档检查使用 ABACUS 规定的 `abacus-env`，每次新 shell 显式 `conda run -n abacus-env`，并先完成解释器、`adam_community/ase/docstring_parser` 和 `adam-cli` 预检。执行文档门禁：

```bash
conda run -n abacus-env make docs-check
```

atst 开发者应在独立仓执行其验收：AGENTS 的 image MPI 维护基线为 `atst-dev`，科研 DP 模型另使用已核验的匹配运行时并记录环境身份；不得强行用通用 DeePMD 版本替代 DPA4 环境。ABACUS 后续集成门禁仍为 `abacus-env`，两者证据分别标注，不要求把所有后端装进同一个 conda 环境。若实际从 ABACUS 子树发起受其规则约束的测试，仍执行上层 `abacus-env` 规则，缺依赖不静默 fallback；改在独立仓维护验证不冒充本仓验收。真实计算遵循 Slurm 与授权边界。

（2026-09-21 补充，SPEC §11 R2）`atst-dev` 的 editable 安装当前指向 `/home/james/work/deepmodeling/atst-tools`（dist 2.2.3 / 代码 v2.2.4+1），不等于实施基线。本分支的单元与集成验证默认以 `PYTHONPATH=src` 覆盖并以基线工作树为代码源；所有证据条目必须记录“解释器、包路径、dist 版本”三元组；`pip install -e .` 重指向在 P1 执行并登记。

精确 pytest 命令在 P0 依据现有 suite 与新增行为确定，不为未创建的测试虚构可运行命令。YAML 变更同步参数生成及 `tests/unit/test_config.py`；atst 文档治理脚本为 `scripts/check_docs_governance.py`，运行环境按其 owner 规则执行。

## 与恒电势的集成检查点

依据 SPEC §7A，GPU runtime 与恒电势算法没有性能验收上的相互前置依赖；共享文件由 atst 维护者串行集成，不要求等待整个恒电势项目完成。

- [ ] P0 对齐 runtime/calculation 字段和结果扩展；恒电势每轮允许新 calculator，不受“单模型实例”限制。
- [ ] P2/P4 审查 cache、任务目录、restart、rank/image 状态，不能将 `nelec` 或前轮 E/F 混用。
- [ ] 两项实现都可用后，运行恒电势单点/扫描与新 runtime 的组合回归；恒电势 NEB 共享另在其 P1 科学验收后验证。

恒电势 O7、M0 后端事实及电势收敛容差由恒电势 owner 解决；本计划不修改其算法或授权范围。组合回归尚未满足时只交付已验证的固定电荷/普通 DP runtime，不泛称恒电势已获优化支持。

## 本轮交付记录

2026-09-20：已完成源码/文档取证及分期方案，用户已确认先 atst 后平台；开发项均未执行。原始 FT²DP 作业、真实硬件和性能数值未复核。本计划用于后续实施交接，不作为性能验收报告。

独立文档复核提出两项实质修订：模型实例数量不得从 rank 数直接推定；已知 allocation 过度暴露但身份未知不能沿用 inherit。均已对照源码/契约修正到 SPEC 和 P1/P2/P4；最终复核和文档门禁结果随本轮交付说明报告。

2026-09-21（维护者接手执行 P0）：SPEC 与 PLAN 迁入 atst 规范源并登记账本；P0 完成基线裁定（SPEC §11 R1）、验证环境约定（R2）、线程优先级（R3）、共享文件顺序（R4），接口冻结文档产出。P0 剩余项：与恒电势 owner 确认共享文件字段/顺序（等待其分支提交）、legacy 基线测试清单执行登记、相称独立设计审查（P0→P1 门）。未开始 P1 代码实施、未运行真实 GPU、未推送。
