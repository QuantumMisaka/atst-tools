# ATST-Tools GPU 节点调优设计

**版本**: 2026-09-20（2026-09-21 迁入 atst-tools 规范源）
**日期**: 2026-09-20
**状态**: 设计（P0 接口收敛中；未实施、未形成性能结论）
**责任人**: ATST-Tools maintainers

> **迁移记录（2026-09-21）**：本设计已由发起方 ABACUS 文档目录迁入 atst-tools 规范源；对应执行计划见 [开发与验证计划](../plans/2026-09-20-atst-gpu-node-tuning-plan.md)，P0 接口冻结见 [runtime 接口冻结设计](2026-09-21-atst-runtime-interface-design.md)。原位置只保留交接说明，不得独立演进。文中引用的 ABACUS Toolbox 文档（`docs/guides/`、`docs/reports/`、`container/`）位于发起方仓库，本仓以文本路径引用，不复制副本。

**目标：** 在既有科学工作流和数值精度下，提高 DP 与 ABACUS 单节点任务吞吐，提供可复现的设备绑定、运行证据与外层编排接口。
**来源：** 维护者提出的 FT²DP 实测观察；本轮要求“综合所有相关信息，并系统性明确相关开发和工程化优化如何进行”。
**执行拆分：** [开发与验证计划草案](../plans/2026-09-20-atst-gpu-node-tuning-plan.md)。计划依赖设计确认，不表示代码、真实计算或发布已获授权。

## 1. 结论与范围

用户已确认先完成 atst 独立运行器，再接入平台。首期交付设备绑定、隔离进程入口、可组合的运行证据，以及独立批任务与 MPI 图像并行两类基准。ABACUS Toolbox 当前的一图一卡契约在平台接入阶段单独迁移，不能直接把 `n_gpu` 改成“可任意共享的卡数”。

区分三个优化目标：

- 独立 case 吞吐：DP 优先研究每卡多个独立进程；ABACUS 优先研究每卡一个独立单点或工作流。
- 单条路径延迟：研究 NEB/AutoNEB 图像并行、CPU 线程与模型加载开销，不假定共享 GPU 一定比串行快。
- 成本与可靠性：同时记录分配卡时、失败率和科学结果；GPU 利用率是诊断量，不是独立成功标准。

不改 fmax、算法、精度、物理判据；不实现跨节点调度、通用集群队列、跨进程推理服务或默认 MPS；不在本期开放平台资源自适应重分配。CUDA Graph、推理批处理、模型编译和持久 worker 留待阶段剖析证明收益后另定范围。

## 2. 已查明事实与证据缺口

取证范围为 SPEC 所在 `workplace/app-tools` checkout：父仓 HEAD `178bd48c8e992b4e051a29d4c4937e1778d7745b`，atst 工作树 HEAD `a633f06b9375e3f34dbd87f90f40ec6271b29cd4`。另一个 `sidereus/app-tools` checkout 不作为本设计的编辑目标。下表源码路径以 ABACUS 根为基准，atst 包路径相对于 `deps/atst-tools/src/atst_tools/`。

维护者接手复核（2026-09-21，对照表见 §11）：`a633f06` 即 atst `v2.2.6` 发布提交；atst `origin/main` 为 `2cf5b7e6`（v2.2.6 + 7 个未发布提交：CCQN `interp_direction`、Sella 事件、IDPP 性能修复等），已选定为实施基线（R1）；独立 checkout `9318177` = `v2.2.4+1`；`workplace/app-tools-forge` pin `4c96691` = `v2.2.5`。本文档中 atst 源码路径均以 `deps/atst-tools/src/atst_tools/` 为基准（`examples/` 与仓级 `scripts/` 除外）。

性能前提复核（2026-09-21，[P0 复核](2026-09-21-atst-gpu-node-tuning-p0-review.md)）：原稿“118 原子单点 6–13 min”无本地记录支持（同规模历史 median ≈20.19 min，n=43），须由 SAI `sacct`/日志或 P5 重测裁定；DP 模型的 mpi4py 并行 NEB 在 ft2dp-dpeva **从未运行**（全部 DP NEB 为 `parallel: false`），P4/P5 已相应增加验收项。

| 事实 | 实现或记录 | 对方案的影响 |
| --- | --- | --- |
| DP 在当前 Python 进程导入并实例化，存在进程内 calculator cache，`omp` 会写进程环境 | `calculators/dp.py` | 不能假设已有独立 DP 子进程；绑定早于科学库初始化 |
| 已有 `python -m atst_tools.api.runner`、`RunOptions`、版本化结果及原子结果写入 | `api/runner.py`、`api/models.py` | 复用进程协议，不另造 workflow/result 协议 |
| `run_workflow()` 明确不负责启动 MPI，接受已有 communicator | `api/services.py::run_workflow` | 保留嵌入 API，不暗中变成进程池 |
| CLI 导入链提前加载 NumPy、ASE、workflow 模块 | `scripts/cli.py`、`scripts/main.py`、`api/__init__.py` | 检查 bootstrap 和包导入链，不能仅在创建 calculator 前改环境 |
| NEB 校验 ranks 等于内部图数；AutoNEB 等于 active images / `n_simul` | `utils/mpi.py`、`mep/autoneb.py` | “10 图”定义为 10 个内部图，完整 band 为 12 个结构 |
| ABACUS 工厂已有 command/mpi/omp、MPI 环境清理和独立/内置 abacuslite 选择 | `calculators/factory.py`、`calculators/abacuslite_backend.py` | 原稿“只有 mpirun 命令”不完整，应扩展现有工厂 |
| ABACUS Toolbox 已使用 API runner，image 模式为每图单 GPU/单 ABACUS rank | `toolkits/transition_atst.py`；ABACUS Toolbox `docs/guides/abacus-runtime-resource-policy.md` §NEB And AutoNEB Image Parallelism | standalone 共享卡数不能直接传成现有平台 `n_gpu` |
| MLIP-Agent 拒绝用户设置 `n_gpu/n_cpu/partition` 等平台管理字段 | `../MLIP-Agent/mlip_agent_core/workflow_runtime_core.py::resAlloc`、`unified_execution_router.py::reject_user_resource_controls` | 原稿“kwargs 覆盖”撤回；复用 allocation 解析和 child mask 思路 |
| 已有 SIF 内 GPU 采样不可靠的记录，但当前 trial 代码仍包含有限采样 | ABACUS Toolbox `docs/reports/2026-08-09-resource-discovery-sif-gpu-activity-limitation.md`、`toolkits/resource_trial_job.py` | 历史“已回退”不等于当前无代码；零采样不能证明无 GPU 运算 |
| ABACUS 多卡收益与 workload、solver、K 并行有关 | ABACUS Toolbox `docs/reports/abacus-sai-pw-gpu-resource-benchmark-2026-07.md` | 小体系经验不能变成普遍的一任务一卡规定 |

原稿 FT²DP jobs `1422694/1422849/1423160`（DP）、`1423179`（ABACUS）保留为待取证线索。本轮没有读取其原始日志、输入、卡时或运行环境，不能把“5 case / 2 GPU 显著提速”“118 原子单点 6–13 min”视为已复核基准。D2S 原子规模以 fixture 为准，不能沿用原稿“120 原子量级”的假设。

## 3. 职责划分

```text
Slurm / ATP Router：GPU、CPU、内存、节点分配及站点策略
    └─ 外层运行者：case 队列、工作目录、进程生命周期、宿主采样
         └─ atst bootstrap：选择已获分配中的设备、绑定、启动 worker
              └─ API runner / workflow：科学流程、阶段计时、结果工件
                   ├─ DP：worker 内模型与 calculator
                   └─ ABACUS：现有 abacuslite 子进程 / 已验证 launcher
```

| 所有者 | 负责 | 不负责 |
| --- | --- | --- |
| atst-tools | 设备选择、轻量 bootstrap、worker 证据、MPI 映射验证、backend 适配 | 获取 Slurm allocation、修改 QOS、任意更换 solver |
| 独立 batch harness | 一个已有 allocation 内限流，逐 case 启停/取消/汇总，宿主采样 | 跨作业全局锁、申请额外卡、改变科学参数 |
| ABACUS Toolbox | 既有资源/输入 preflight、ATP 交接与后续兼容 | 套用 MLIP 训练模式、直接取消一图一卡门禁 |
| MLIP-Agent | Tool 资源规划，可信 allocation 到 child runtime 适配 | 把平台管理字段变成用户自由覆盖项 |
| Slurm / 平台 | allocation、隔离、站点 mapping、MPS 服务管理 | 由 atst 文档代替实际运行状态 |

首期 batch harness 放在 atst benchmark/example 层，单进程消费有限 case 清单、调用隔离 worker。它是验证与参考编排器，不新增生产 `atst batch` 公共接口。生产批队列继续由调用方拥有。

### 3.1 开发归属与计划交接

GPU runtime、backend 适配、独立 harness、双后端验收和 atst 发布准备由 **atst-tools 开发者负责**。ABACUS Agent 开发者是后续消费方，负责资源契约、文件交接与平台回归，不在 Toolbox 中先做另一套 GPU runtime。首期完成标准是 atst 的 CLI/API runner 独立可用，不以 Agent 工具或平台上线作为前置。

本 SPEC 与对应 PLAN 已于 2026-09-21 由发起方 ABACUS 文档目录迁入 atst-tools 规范源（`docs/superpowers/`），并在 atst 文档账本登记；发起方副本只保留交接说明，不再独立演进。发起方 `workplace/app-tools` 的 atst pin 保持 `a633f06`（v2.2.6）不动，atst 实施基线为 `2cf5b7e6`（v2.2.6 + 7 个未发布提交）；本次迁移不推送、不更新 gitlink、不改变发起方仓库状态。

## 4. 设备与进程契约

### 4.1 allocation、可见性与选择

分别记录请求（requested）、继承可见设备（inherited visible）、可信分配事实（allocation，如可得）、最终绑定（effective）。可见性掩码不等于调度授权，特别是平台 worker 过度暴露整节点时。

提议新增可选 `runtime` 配置段，概念字段为 `devices`、`binding`、`threads`、`telemetry`；准确拼写在 schema 实现前统一。`devices` 中整数是继承可见集合内的 **0-based CUDA 逻辑序号**，不受原子选择 1-based 规则影响。允许完整 GPU UUID 精确选择；MIG 首期不承诺支持，显式请求返回清晰的 unsupported 错误。

优先级为显式启动参数 > YAML `runtime.devices` > `ATST_VISIBLE_DEVICES` > inherit；只决定请求，不能扩大可用设备集合。`ATST_VISIBLE_DEVICES` 与参数使用同一种语法和逻辑序号语义，不直接复制成 CUDA mask。

例如继承 mask `2,3`，请求逻辑 `[0]` 应选第一个继承设备，在相同命名空间内解析为 `2` 或其完整 UUID，不能写成物理 `0`。容器/MPS 重映射时使用当前执行边界实际解析出的标识，禁止把宿主序号未经核验塞进容器。[CUDA 枚举规则](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html)明确可见列表决定逻辑序号。

无 mask 不代表无卡；显式空 mask 不当作缺失。需要枚举时由短命 helper 获取当前可见设备标识，不在 coordinator 初始化 CUDA 后再 fork。只有卡数没有身份时，不从卡数猜宿主编号。已知可见设备数超过可信 allocation 且无法确定获配设备身份时，新运行模式必须拒绝，不能 inherit 或任选第一卡；adapter 有可信身份时才可收窄。无冲突证据但身份未知时，standalone 的 inherit 仅原样沿用调用者启动环境、标记 allocation 身份未验证，不宣称调度隔离已验收；需要重绑定/共享池的请求仍拒绝。平台 adapter 若要求可信身份，则由平台明确提供后才能进入新模式。旧模式兼容不扩张新模式的权限。（可采性、错误类型与校验基准以 §11.2 R5 和 [runtime 接口冻结设计](2026-09-21-atst-runtime-interface-design.md) §4 为准。）

### 4.2 进程入口与嵌入 API

采用“轻量启动层 + 既有 API runner”，一项工作流一个新解释器进程，不为每次力调用创建进程。先构造 child env、cwd、线程与可写缓存目录，再导入 DP/JAX/ASE 和计算器。MPI 下由既有 launcher 启动每个 rank 的 bootstrap，在 MPI/CUDA 初始化前以 exec 进入最终 worker，不能把已初始化 communicator 跨普通 subprocess 传递。

处理 `python -m` 会执行包 `__init__` 的事实；以 import smoke 证明轻量入口未提前初始化科学后端，不能只移动一行环境设置。

- CLI `atst run` 和 `api.runner` 的显式 runtime 选项进入启动层；未指定新键的旧调用维持行为。
- 外层已正确绑定的 runner 不重复产生嵌套 worker；内部绑定标记只表达状态，不构成资源授权。
- 嵌入 `run_workflow(config, RunOptions(...))` 保持当前进程、communicator、callback 和返回类型。可消费/校验已绑定环境；更换设备请求报错并指向隔离入口，不临时污染调用者环境。
- Python 便利封装若需要，另提供显式进程启动 helper，复用 runner 文件结果；不能悄悄序列化自定义 calculator、communicator 或 callback。名称与返回类型在实现前收敛。
- `run_ccqn(atoms, calculator, ...)` 等对象入口沿用对象设备，不承担设备切换。

隔离入口保证 coordinator 环境和 cwd 不变；不追溯包装旧进程内 API 的所有历史全局状态行为。

### 4.3 线程、模型与缓存

线程控制在导入前生效；解析 cpuset 和实际预算，不把 GPU 数等同于 CPU 核数。batch 的并发 worker CPU 预算之和不超过可用集合；OMP、BLAS、DP intra/inter-op 分别记录。平台 4 核/GPU 默认和 SAI logical threads 不是同一口径。

任务独占 cwd、临时目录、可写 JIT/cache 路径和日志。只读模型可共享文件，不复制大模型，不跨进程共享 Python calculator。线程模式不能提供环境隔离。尽量减少每 worker 的重复模型加载是优化目标，并非现有保证：NEB/AutoNEB 并行挂载使用 `shared=False`，端点、active window 和最终补算可重复构建。先计量每 rank 构建次数、可追踪存活实例与显存，再决定生命周期优化；不能把启用全局 calculator cache 当成修复，以免 image 的 atoms/results 状态混用。

DP 按 TF/PT 后端分别验证线程、加载和显存，不把 TF 参数无条件用于 PT。[DeePMD 并行实现](https://docs.deepmodeling.com/projects/deepmd/en/v3.1.0/_modules/deepmd/env.html)供参考，执行以实际版本为准。`DP_INFER_BATCH_SIZE` 不是多个独立 ASE 工作流的自动合批接口。

Sella/JAX CPU 时间占比和是否实际用 GPU需测量。JAX GPU 预分配可能引起共享冲突，按实际后端比较 CPU JAX 或受控预分配，不全局修改所有工作流。[JAX 内存说明](https://docs.jax.dev/en/latest/gpu_memory_allocation.html)用于候选设计，具体环境行为由基准确认。

## 5. 两种并发及 ABACUS 适配

### 5.1 独立 case

将原稿 `gpu_concurrency` 拆成外层 harness 的“每卡同时运行 case 上限”和 MPI 的“每卡 rank 上限”。前者默认 1；DP 候选 2–6，逐步实验；ABACUS 首期默认每卡 1 case。多卡 ABACUS task 由 adapter 原子占有完整设备组，不混入首期单卡共享实验。

启动前绑定，退出后释放 harness 内槽位。OOM 分类依赖 backend/exit evidence；无法判断记 unknown，不用通用异常当 OOM。首期不自动重跑，降并发后的 retry 由显式 policy 或调用者发起，新 attempt 保留旧证据。取消处理工作进程组，限时终止并回收日志、采样进程和槽位，不杀整个节点进程。

### 5.2 MPI 图像

两种绑定模式：`inherit` 消费站点逐 rank 绑定；`round_robin` 仅用于已核验的单节点共同设备池。轮转为 `local_rank % device_count`，不用 global rank 假设节点布局。逐 rank 掩码不同优先 inherit，不重复轮转，不从单卡掩码扩展为四卡。

NEB 仍要求 `world.size == interior_images`；AutoNEB 要求 `world.size == n_simul`。10 内部图 / 4 卡是 10 ranks，各卡 3/3/2/2；10 ranks / 1 卡意味着 10 个独立进程模型上下文，驻留实例和内存可能更多，不能按恰好10份模型估算容量。共享需显式给足 rank-per-device 上限，与独立 case 默认并发 1 无关。10 图/1卡是容量允许时的压力实验，不是生产推荐。

端点准备也处于 rank 0 已绑定设备内；AutoNEB active window 变化后保持 rank 设备身份，image 目录独立。共享 MPI 首期不与独立 batch 并发叠加。

所有 rank 在优化器 collective 前校验配置/映射，复用既有失败同步 helper；MPI 初始化前死亡交给 launcher/coordinator 的退出和超时处理，不依赖尚未建立的 collective。rank 被杀或失联也需有界终止，不只覆盖 Python 异常。

### 5.3 ABACUS

继续使用 factory/profile 与 abacuslite。image 并行内 `mpi=1`、直接 ABACUS，保留 MPI 环境清理，不扩展 nested MPI。普通多卡 ABACUS 沿用已验证 launcher/solver，不因新增设备选择重写其 mapping。

预检分为静态配置冲突、实际 launcher/二进制/设备环境、实际计算容量探针。仅在命令需要 MPI 时检查 launcher。静态显存估计为 advisory，不能承诺排除所有 OOM；未知配置报告 unknown，已知不兼容组合提前报错，不静默换 solver 或转 CPU。

Toolbox 继续使用 resource discovery、preflight 和 SIF 环境 owner；standalone 不复制整套平台策略。MPS 由站点 adapter 管理，首期 atst 不启停服务，检测到 MPS 只记录并验证命名空间。[NVIDIA MPS 文档](https://docs.nvidia.com/deploy/mps/appendix-tools-and-interface-reference.html)说明设备重映射和进程归属需特别处理。

## 6. 计量与工件

复用 `atst_artifacts.json` metadata 和 `atst-api-result-v1` 可选扩展，不改科学结果字段或现有 status。运行中证据写 runtime sidecar，成功后引用到 manifest；失败保留 sidecar 与 runner error result，不伪造 completed artifact。

| 层级 | 最小记录 | 局限 |
| --- | --- | --- |
| workflow/stage | attempt、起止、阶段 wall、模型初始化耗时/构建次数、可追踪存活实例、力调用累计耗时/次数、退出原因 | Python对象存活不等于GPU分配已释放；CPU提交耗时不当作kernel时间，显式同步仅用于诊断 |
| rank/worker | global/local rank、image 关联、请求/生效 mask/UUID、来源、线程、backend/version | PID 只在私有原始日志关联，公开报告避免无关进程信息 |
| GPU device | 宿主采样时间、UUID、利用率、memory used、样本数/周期/覆盖时间 | 整卡值不能复制成每个共享任务的独占指标 |
| process（可得） | GPU 进程显存、RSS/CPU 时间、关联置信度 | MPS、容器 PID namespace、权限会阻断归属 |
| allocation/batch | 分配卡数与 wall、成功/失败数、吞吐、卡时/成功 case | 分配卡时和实际计算 GPU 时间分别报告 |

状态区分 disabled、unavailable、partial、observed，附 reason/source；缺失用 null，不填 0。显存峰值标记为 sampled peak，可能遗漏短峰。[nvidia-smi 文档](https://docs.nvidia.com/deploy/nvidia-smi/)是指标语义来源，GPU 利用率不等于算力占用比例。

每 batch/MPI job 一个宿主采样器，避免各 rank 重复轮询整节点。平台消费已有 observation 或外层 sampler；atst 只报告有权观察的事实。无 GPU/无采样工具时计量降级；显式 GPU 请求无可用设备则执行失败，两者不可混同。默认关闭 GPU 轮询，显式 telemetry 开启后输出来源。

## 7. 基准与验收

### 7.1 瓶颈与实验矩阵

先固定结构重复 energy/forces，拆开冷启动和稳态；再固定步数优化/NEB，观察计算、优化器、通信、IO；最后跑完整工作流，评价收敛、TS/振动和尾部耗时。微基准不替代完整流程收益。

| 组 | 对照 | 回答的问题 |
| --- | --- | --- |
| DP 单 case | 1 卡，线程档位；冷/热分别记录 | 是否 CPU/JIT/模型加载限制 |
| DP 独立批 | 同 allocation 每卡 1/2/3，容量允许再到 4–6；先 1 卡再 2/4 卡 | 共享能否提高成功吞吐和卡时效率 |
| ABACUS 独立批 | 同 4 卡 allocation 的串行队列与四卡各一 case；另报实际 1 卡作业成本 | gains 来自并发还是资源增加，E/F 是否一致 |
| MPI NEB | 相同 10 内部图：串行、10 ranks/4卡、容量允许的10 ranks/1卡 | 单 band 延迟、模型复制与同步开销 |
| AutoNEB | 固定输入与 `n_simul`，inherit/已验证共享布局 | active window 和端点阶段正确性 |
| 容器 | 候选最优点 host/SIF 成对运行 | 环境、mapping、观测是否保持 |

先选代表性 DP/ABACUS 小 fixture，固定结构、模型/head/精度、PP/ORB/KPT、solver、随机种子及软件环境；20 条反应大批次仅在小矩阵通过且预算确认后进行。记录 CPU 亲和性、主存、GPU 型号/显存、温度和共享条件。不同 allocation 附带 CPU/RAM 变化的实验分开解释，不能全归因于 GPU。

正式比较至少三次独立重复、交替顺序，保留全部失败和超时；预算不足只报探索结果。冷启动总 wall 与预热稳态分别报告。主指标为成功 case/hour、batch makespan、p50/p95（小样本不声称稳定尾分位）及 allocated GPU-hours/success。

### 7.2 科学与工程验收

固定输入 E/F/stress 与工作流收敛/势垒/TS/振动判据分层校验；每 fixture 在运行前登记单位、绝对/相对容差和依据。不将旧 PW 容差套到 DP/过渡态路径，不以字节级轨迹一致作为通用要求。

工程交付条件：设备身份正确、隔离、失败回收、MPI 无死锁、旧接口兼容、计量诚实。性能结论只对通过科学验收的 fixture 给出；原“墙钟减半、GPU≥40%”降为探索目标。无稳定收益也能形成有效报告，但不能宣告提速或据此改生产默认。

SAI QOS/CPU 配套只存在站点模板；真实基准前查询实时 Slurm。参考矩阵为 4V100 的 1–2 卡使用 `rush-1o2gpu`、4 卡使用 `rush-gpu`，来自指南快照，不是本轮实时验证。10 ranks/4卡不能机械套用整齐 ranks-per-GPU 的 mapping 脚本，应先验证 launcher binding。模板遵循 SAI guide 的提交环境、CPU/内存参数限制和变量传递方式，core 不硬编码。

### 7.3 SAI 测试环境与双后端交付

测试计划显式关联 `$sai-user-guide`：§2–§5 负责实时资源/QOS/提交，§7 负责环境，§8 负责存储，§10 的性能调优 reference 负责 mapping/MPS，§11 仅在涉及 SIF 时适用。指南属于维护者测试环境依据，不是终端用户安装 atst 的依赖。站点事实只在 SAI 作业准备阶段查询，不通过公网文档猜测当前配额。

| 验证层 | 环境责任 | 最小交付 |
| --- | --- | --- |
| atst 单元/CPU/MPI 替身 | atst 开发者按独立仓 AGENTS，维护验证基线为 `atst-dev` | 解析、进程、兼容和失败恢复证据 |
| ABACUS 实算 | SAI Slurm 作业内 ABACUS LTS 3.10.1 与匹配的 MPI/Python ABI，执行前核验实际版本 | 固定输入 E/F、短优化、独立批及 image 模式 |
| DP 实算 | 与选定模型匹配的 DeePMD/PT/TF/JAX 环境，记录实际解释器与依赖版本 | 单点 parity、relax/MD、NEB/Sella 和并发子集 |
| ABACUS Agent 集成 | 后续阶段遵循 ABACUS `abacus-env` 与本地 E2E owner | 包来源、端口、资源、平台交接 |

双后端都是首期验收对象，不能只测 DP 后宣称 ABACUS 也受益。“同时测”表示同一版本具备两条独立验收证据，不要求将两类 workload 同时混跑在同一 GPU；混合争用是后续实验。每一后端比较自己的 baseline/candidate：DP 与 DFT 预测误差属于模型验证问题，不作为 runtime 优化前后数值等价的替代指标。

DP fixture 建议两层：atst 已有 `examples/dp_model_manifest.json` 的通用模型用例用于可复现接入回归；FT²DP 科研模型用于真实规模和工作流基准。研究权重只读引用，不复制进 atst Git、公开示例或平台包，新增结果落独立 benchmark 目录，不覆盖科研原始产物。

已定位 FT²DP 的 `docs/checkpoints/2026-09-19-C075-ft2dp-v2.2-single100k-pin.md` 及 `docs/superpowers/plans/2026-09-19-ft2dp-v2.2-model-validation.md`。后者将模型命名为 `FT2DPv2.2-dpa4-air-zbl-single100k-v20260919`，regular checkpoint SHA-256 为 `13b7479796d36b9d5d9518106f24a1915e43810765dbc09cafda817046753e34`，历史接入记录为 atst 2.1.1 与 deepmd `3.2.1.dev0+g687b5107`；这只是已读项目记录，尚未回读远端权重/环境。执行前以模型包 manifest 核验 regular/EMA、head、type map、单位、精度、格式和输入适用域，不能用“deepmd>=3.1.3”代替 DPA4 运行兼容证明，也不自动选最新模型。

该项目记录 `.pt` Python 推理已接入，而 `.pt2` freeze 有历史失败；本期用已验证 `.pt` 路径，不把修复 freeze/LAMMPS 纳入 GPU 调优。普通 FT²DP 模型可测试 GPU 推理和反应流程；只有提供电子数条件和 μ/W 能力的模型才能验证恒电势推理，不能因同属 DP 就复用普通模型作此验收。

## 7A. 与在途恒电势开发的协调

对照 ABACUS 的 `docs/superpowers/specs/2026-09-20-abacus-constant-potential-design.html` 与 `docs/superpowers/plans/2026-09-20-abacus-constant-potential-development-plan.md`：当前为设计/知识阶段，算法尚未实现。两项工作在目标上正交：GPU 优化负责执行资源，恒电势负责电子数–电势循环与科学记账；存在共享代码和状态语义上的集成风险，不能声称完全无冲突。

| 交叉点 | 协作安排 | 集成验收 |
| --- | --- | --- |
| `config_schema.py` / `api/services.py` | GPU 增可选 runtime；恒电势增 calculation/backend，分别拥有字段，合入由 atst 维护者统筹 | 严格 schema 同时接受两类扩展，legacy 不退化 |
| API runner / bootstrap | GPU 只调整启动/环境边界，恒电势通过同一 runner 注册 dispatch | 结果 envelope、退出码、callback/communicator 语义保持 |
| calculator 重建与 cache | 恒电势可每轮重建 ABACUS calculator；GPU 计量不限制其数量，不缓存旧 `nelec` 的结果 | 同几何但不同电子数不复用旧 E/F，失败不复用前轮结果 |
| cwd / restart / 迭代 INPUT | runtime 只隔离 task/attempt；恒电势拥有内部 U/迭代目录和重启身份 | 不因缓存隔离破坏 restart，不让多任务覆盖 `log-cp` 或迭代 INPUT |
| NEB / U 扫描并发 | 外层 GPU 绑定独立 case/rank；每个 image/U 点持有自己的恒电势状态 | 电子数/电容初猜/收敛历史不串图；无隐式嵌套并发 |
| 后续平台共用 runner | 恒电势 Task 3.2 拟抽取 `toolkits/atst_runner.py` | GPU 平台适配消费届时共用入口，不复制/同时重写 transition launcher |

推进顺序：先共同确认 schema/runtime/result 边界；GPU bootstrap/证据与恒电势独立 calculator 算法可在分支隔离下推进，共享文件合入串行审查。恒电势基础单点不依赖 GPU 调优性能达标，GPU 独立基准也不依赖恒电势上线；两者可用后再增加恒电势单点/扫描的资源组合回归，最后考虑恒电势共享 NEB。

恒电势已有 O7（初始与迭代 INPUT 的 `nelec` 写入边界）仍由恒电势 owner 裁决；GPU 项目不能借 runtime 优化擅自解决或绕过该科学输入边界。其每轮重建 calculator 的 M0 验证也独立保留。

## 8. 平台映射与演进

| 平台概念 | atst 消费 | 接入安排 |
| --- | --- | --- |
| `GPU` / `resAlloc` | 已分配设备集合及 worker 可见性 | 保持平台权威，分开记录请求/实际 |
| ABACUS `n_gpu` | 普通任务逻辑 GPU；当前 image 模式为图数/rank 数 | 首期不重释，共享模式后续迁移 |
| MLIP `n_gpu/n_cpu` | 平台管理字段 | adapter 消费 runtime facts |
| CPU / 内存 | 线程预算与观测 | 不从 `mem_per_cpu` 推导显存 |
| `PARTITION` / QOS | 无 core 映射 | 仅平台/SAI adapter |
| `training_scale` | 无直接映射 | 训练并行不等于 ASE 推理并发 |
| torch `device` | backend 意图，解析为已绑定设备 | 不等于 allocation 或并发许可 |

顺序：standalone → 单节点实测 → atst 发布 → 经授权更新父仓 gitlink → Toolbox 回归 → 本地 E2E → 经授权的平台发布与观察。仅新增运行依赖确需镜像变化时插入非活动 SIF 槽位候选，不把重打 SIF 当作 atst 代码更新的必经步骤。准入见 ABACUS Toolbox 的 `docs/guides/release-and-platform-validation.md` 与 `container/2.0/docs/ADAM_ABACUS_SIF_REGISTRY.md`，不在此复写规则。

回滚按 opt-in runtime 和 adapter：关闭新模式恢复旧路径，不覆盖旧 attempt、不迁移旧缓存。已初始化进程不能就地换卡，使用新 attempt。平台共享模式失败则保留旧一图一卡入口，standalone 成功不代表平台已支持。

## 9. 保护对象与检查 owner

| 契约 | 失败模式 | enforcement owner |
| --- | --- | --- |
| 仅在可信集合内选择 | 错卡、越过 allocation、空 mask 被当缺省 | resolver 行为测试 + adapter 审查 |
| 初始化前绑定；嵌入 API 不偷偷换进程 | 父进程污染、改 mask 无效、callback 丢失 | bootstrap 子进程测试 + API 回归 |
| 区分 case/rank 并发 | 默认1与10/4冲突、显存争抢 | harness 测试 + MPI integration |
| rank 错误同步及超时 | barrier 永久等待、遗留 worker/采样器 | launcher/MPI 失败注入 |
| 采样标明范围/来源 | 整卡冒充任务数据、不可观测报0 | telemetry parser tests + 报告复核 |
| 科学门禁先于性能结论 | 低精度/失败任务制造虚假 speedup | fixture reviewer + benchmark 验收 |
| 平台分期迁移 | `n_gpu` 重释破坏 resAlloc/INPUT/MPI | adapter reviewer + 平台 E2E |

## 10. 待确认项与来源

已确认分期：首期 atst，平台后接。推荐具体方案为独立 harness、保留进程内 API、重绑定走显式进程入口、共享 opt-in、不自动重试、不新增生产 batch CLI；这些接口细节在 P0 收敛。同步改平台会增加 resAlloc、prepare、runner、SIF 和真实平台验证的协调成本。

真实计算前需确定 fixture、数值容差、卡时预算并补齐 FT²DP 原始记录；本轮不假定其已存在。实现前形成准确 schema/API 草案及兼容测试，本文概念字段不是当前可用参数。

本地证据见 §2；外部一手文档随各节链接，访问日期 2026-09-20。SAI 参考读取自 `/home/james/.codex/skills/sai-user-guide/SKILL.md`（2026-09-03 校准、含后续注记）；本 checkout canonical SAI skill 未初始化，home 快照不构成实时状态。ATP 参考为父仓 pinned `skills/asterfire-agent-skill/asterfire-agent-skill/SKILL.md`。方法读取本机 `using-superpowers`、`brainstorming`、`writing-plans`、`verification-before-completion`，不构成 atst 运行依赖。

补充取证：恒电势文档位于 `/home/james/work/sidereus/app-tools/toolbox/ABACUS` checkout；FT²DP 记录位于 `/home/james/work/ft2dp-dpeva`。独立 atst checkout `/home/james/work/deepmodeling/atst-tools` 当次 HEAD 为 `9318177798d1d087a061e298523b58a6f758cbd7`（2026-09-21 复核：`v2.2.4+1`，落后 `a633f06` 27 个提交、落后 `2cf5b7e6` 36 个提交），它不是“更新”的基线，且 `atst-dev` 环境的 editable 安装仍指向它（R2）。P0 已在维护者选定的实施基线 `2cf5b7e6` 上重新核对差异，未据旧 gitlink 编码。这些本机位置用于交接定位，不是终端用户路径要求。

## 11. 迁移与 Ruling 记录（维护者接手，2026-09-21）

### 11.1 迁移与 pin 对照

- 本 SPEC 与 [PLAN](../plans/2026-09-20-atst-gpu-node-tuning-plan.md) 于 2026-09-21 迁入 atst-tools 规范源并登记文档账本；P0 接口冻结文档为 [2026-09-21 atst runtime 接口冻结设计](2026-09-21-atst-runtime-interface-design.md)。
- 2026-09-21 实测各树 atst pin（同源仓库，仅 checkout 不同；当日 09:50 复核：7 棵树全部与表一致、无漂移）：

| 树 | 分支/HEAD | atst pin | 盘面 |
| --- | --- | --- | --- |
| `workplace/app-tools`（发起方当前树） | `docs/skills/kit-agent-file-id` @178bd48c | `a633f06` = v2.2.6 | SPEC/PLAN 当时为 untracked |
| `workplace/app-tools` `main` | main @ac6ff02e | `a633f06` = v2.2.6 | — |
| `workplace/app-tools-forge` | `forge-integration` @c25f1bc2 | `4c96691` = v2.2.5 | ABACUS 侧 phonon 在途 |
| `sidereus/app-tools`（实施工作区） | main @a72264846 | `2cf5b7e` = origin/main | clean |
| `sidereus/.worktrees/constant-potential-plan-review` | `review/constant-potential-plan-20260920` | `2cf5b7e` + checkpoint `7bc3f92`（子模块本地分支 `feature/constant-potential-integration`） | 29 个在途文件已存档为 `7bc3f92`；其后另有 8 个在途改动（2026-09-21 02:07，属恒电势 owner） |
| `sidereus/.worktrees/gate-ablation-20260919` | `refactor/manifest-gate-ablation-20260919` | `0fa1d81` | clean |
| `sidereus/.worktrees/sella-observability` | `fix/ccqn-user700-p0` | `2cf5b7e` | clean |
| `sidereus/.worktrees/transition-entry-surface-reduction` | `transition-entry-surface-reduction` | `da7cfd0` | clean |
| `deepmodeling/atst-tools`（atst-dev 安装源） | main @9318177 | v2.2.4+1 | 另有 worktree `atst-tools-python-api` @958844d |

### 11.2 Ruling

- **R1（实施基线）** 以 `sidereus/app-tools/toolbox/ABACUS/deps/atst-tools` 的 `origin/main` = `2cf5b7e6` 为唯一实施基线；发起方 pin（v2.2.6）、forge pin（v2.2.5）与独立 checkout（v2.2.4+1）仅作取证参考。理由：恒电势在途分支（基于 `2cf5b7e`）已修改本计划要触碰的同一批共享文件，避免跨基线分叉。错了的代价：若维护者改选 v2.2.6 基线，P0 已冻结的接口需按 §11.1 差值重新核对，实施需 rebase。
- **R2（验证环境）** `atst-dev` 当前 editable 安装指向独立 checkout（dist 2.2.3 / 代码 v2.2.4+1）。所有证据必须显式记录“解释器、包路径、dist 版本”三元组；本分支验证以 `PYTHONPATH=src` 覆盖为默认，`pip install -e .` 重指向动作与 P1 一并执行并登记。错了的代价：未重指向时，证据可能落在旧代码上（已实测 `tests/unit/test_config.py` 默认 4 failed、`PYTHONPATH=src` 56 passed）。
- **R3（线程优先级）** `calculator.*.omp` 显式设置时按其执行（保持 Toolbox 已验证契约）；`runtime.threads` 仅在该 calculator 未设置 `omp` 时作为进程默认，冲突以证据 fact 记录、不静默覆盖用户科学配置。依据：§4.3 与 P2 的“不静默覆盖用户已有科学配置”。错了的代价：若反转优先级，平台既有 `omp=ABACUS_CORES_PER_GPU` 行为会被新 runtime 默认值改变。
- **R4（共享文件顺序）** 与恒电势在途分支的共享文件清单与建议顺序见接口文档 §8：GPU 侧先做新增模块与文档，`config_schema.py`、`scripts/main.py`、`api/services.py`、`calculators/factory.py` 的共享改动在恒电势分支提交合入后串行落地。错了的代价：并行提交会在同一区域反复冲突并产生不可审阅的合并。
- **R5（设备请求可采性）** 显式 `devices` 的可采性由接口文档 §4 的单一权威表裁决：可信 allocation 下允许收窄；allocation 未知时仅允许对 caller-bound 掩码做集合内收窄；整机可见且无 allocation 事实时显式选择拒绝（不猜获配设备）；UUID 采 fail-closed。`ATST_ALLOCATION_DEVICES` 使用宿主命名空间 token 或 `count=<N>`。错了的代价：过宽会越过他人 allocation（错卡），过严会让 standalone 单卡用户无法 pin 设备（可退回复用外层 env 绑定）。
- **R6（进程模型分流）** 未请求 runtime 的既有 `atst run` 维持进程内 legacy 路径（不合成 manifest、不写 `atst_api_result.json`、退出码不变）；仅当存在 runtime 请求时进入隔离模式——触发口径为 YAML `runtime` 段、CLI runtime 选项或 `ATST_VISIBLE_DEVICES` 任一出现。最终工作进程必带 `ATST_RUNTIME_BOUND=1`（`atst run` coordinator 与 runner 直接入口均经绑定后 re-exec 实现），worker 经该标记做一致性校验而非重绑定。错了的代价：若把 legacy 路径也切到隔离模式，会破坏旧调用兼容与既有回归测试（`tests/unit/test_cli.py` 的 manifest 断言、runner 退出码契约）。
