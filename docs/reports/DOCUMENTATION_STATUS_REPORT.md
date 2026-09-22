# 文档治理状态报告

**版本**: 2.2.6
**日期**: 2026-09-20
**状态**: 已发布（PyPI clean-install 已验证）
**责任人**: ATST-Tools maintainers

本文档是 ATST-Tools 当前文档治理状态的单一入口。它记录活跃文档职责、reports
L1-L4 分级、归档判据和本轮待删除复核结果。

## 1. 核心结论

- 2026-09-21：接管 GPU 节点调优交接（发起方 ABACUS/Toolbox 文档目录）：[设计](../superpowers/specs/2026-09-20-atst-gpu-node-tuning-design.md)与[计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md)迁入本仓规范源并登记；P0 产出 [runtime 接口冻结设计](../superpowers/specs/2026-09-21-atst-runtime-interface-design.md)（`runtime` schema 与错误消息、CLI/env 优先级、设备解析与过度暴露边界、bootstrap/嵌入 API 语义、OMP 优先级、证据 sidecar、恒电势共享文件顺序、P0 验收对照表）。裁定实施基线 `origin/main` `2cf5b7e6`（v2.2.6 + 7 个未发布提交）；发现 `atst-dev` editable 安装仍指向旧 checkout（v2.2.4+1），验证以 `PYTHONPATH=src` 为默认并记录环境三元组。未开始代码实施、未运行真实 GPU、未推送；P0→P1 门为相称独立设计审查与恒电势共享文件顺序确认。

- 2026-09-21（P0 复核）：[性能前提与 DP 并行 NEB 证据审查](../superpowers/specs/2026-09-21-atst-gpu-node-tuning-p0-review.md)（取证源 `ft2dp-dpeva`）：原稿“118 原子单点 6–13 min”无本地记录支持（同规模 median ≈20.19 min，n=43）；DP 模型的 mpi4py 并行 NEB 从未运行（DP NEB 全为 `parallel: false`，image-parallel E2E 仅 ABACUS 后端）；推理侧无 GPU 利用率/显存采样。结论：高性能前提未证实；P4 增加“DP image-parallel NEB 首个 E2E”，P5 增加 DP 推理并发曲线、NEB 图数×卡数映射与推理侧采样三项验收。

- 2026-09-21（独立设计审查）：接口冻结文档经独立审查（同族、独立上下文）两轮：首轮 **block**（3 blocker：worker/嵌入 API 语义冲突、`atst run` 进程模型破坏旧调用兼容、过度暴露判定两表互斥且 allocation 命名空间未定义；7 major：入口生效时机、隐式 omp 覆盖、错误分类、UUID 透传、共享文件清单、生成参数表、`round_robin` 静默降级）；修订后复审结论 **approve with required changes**，其 N1–N10（runner 直接入口 re-exec 规则、env 通道 trigger、一致性校验基准、count-only allocation 边界、bool 校验、重依赖清单等）已在 rev.3 全部闭合。新增 SPEC §11 R5/R6；P0 交付完成，P1 入口工作项需先落 N1 规则。

- 2026-09-21（P1 实施）：runtime 层落地——设备请求解析与可采性（`src/atst_tools/runtime/devices.py`，含短命枚举 helper 与 `round_robin` fail-closed）、child 环境与 worker 计划（`runtime/launch.py`）、轻入口分流（`runtime/cli_dispatch.py`）、`runtime` YAML 段（`config_schema.py` + 重新生成的 `docs/user/YAML_INPUT_VARIABLES.md`）、`atst`/runner 入口（`cli.py` 轻壳 + `cli_impl.py`、`api` PEP 562 惰性导出、runner 惰性导入与绑定后 re-exec）、OMP 优先级修正（`factory.py`/`workflows/md.py` 的隐式默认不再覆盖 `runtime.threads`）。验证：`tests/unit` 951 项通过（新增 ~74 项行为测试：设备语义、可采性矩阵、child env 事实、入口 smoke、legacy 兼容、嵌入拒绝）；`check_docs_governance.py` 通过。用户可见文档与 SIF/平台内容按接口文档 §8 的合并顺序在恒电势合入后更新；真实 GPU 身份验收留 P5；未推送。

- 2026-09-21（P2 首片）：运行证据 sidecar（`src/atst_tools/runtime/evidence.py`，schema `atst-runtime-evidence-v1`）：环境三元组与依赖版本、设备/分配事实、`runtime.telemetry` 开关与 rank 0 单例宿主采样（`nvidia-smi` 缺失/失败记 `unavailable`，缺失值 null 不填 0）；成功时 manifest metadata 增加 `runtime_evidence` 引用并进入 API 结果元数据，失败保留 `partial` sidecar；计量写失败只警告、不阻断科学运行。测试 958 项通过（新增 9 项）。剩余：阶段耗时明细、力调用/模型构建计数、结果 envelope 的 `runtime` 摘要（P2 后续片）。

- 2026-09-21（P2 第二片）：进程级计数器 `src/atst_tools/runtime/counters.py`（线程安全、默认关闭、session 请求时启用）：DP 计算器的构建/复用与力调用（`dp.calculator_built/reused`、`dp.force_calls`）、ABACUS 计算器构建与子进程调用（`abacus.calculator_built/force_calls`）；sidecar 增加 `counters` 与 `counters_scope=process`（MPI 逐 rank、ABACUS 子进程内 SCF 不可观测的局限已在 docstring 标注）。测试 958 项通过。

- 2026-09-21（P3 首片）：独立 case 参考 harness `src/atst_tools/bench/harness.py`（2026-09-21 更名 `bench/batch_runner.py`）（manifest → 有限 case 队列；设备槽位（`slots_per_device` 默认 1）与 CPU 线程预算共同限流；每 case 独立目录、独立 worker 进程与 `harness_case.json`；OOM/超时/取消/跳过分类且不隐式重试；单例 `HostSampler`；`harness_summary.json` 保留全部任务与卡时；`SIGINT/SIGTERM` 有界终止进程组）。模板 `examples/runtime_batch_cases.example.json`；测试 `tests/unit/test_bench_batch_runner.py`（6 项，替身 worker：槽位时序、超时整组回收、取消、停止策略、环境与目录隔离）。全量 968 项通过。真实 SAI 作业运行与并发曲线留 P5。

- 2026-09-21（P4 首片）：逐 rank 运行时绑定——CLI/env 逗号分隔设备规格解析修正（真实 MPI 集成测试暴露并修复 `parse_device_tokens('0,1')`）；`round_robin` 增加多节点拒绝（`declared_node_count`，`SLURM_JOB_NUM_NODES`/`SLURM_NNODES`/`ATST_NODES`）；新增 `tests/integration/test_runtime_binding_mpi.py`（真实 MPICH 2-rank：rank 掩码互异、coordinator 逐 rank 生成隔离 worker 计划）；既有 17 项真实 MPI 失败同步回归本地全绿。P4 除“DP 后端 image-parallel NEB 首个 E2E”外各项已具备本地证据；站点 OpenMPI/SIF 与 DP 并行 E2E 留 P5。

- 2026-09-21（P2 收口片）：线程预算与采样细化——`runtime.threads: auto` 按 CPU affinity 解析（`cpu_affinity_count`），child env 记录 `ATST_THREADS_SOURCE` 并在证据中回显 `cpu_affinity_count`/`threads_source`；宿主采样增加计算进程行（`nvidia-smi --query-compute-apps`，`attribution=reported`，缺工具/权限/无进程分别记 `unavailable` 与原因）；P2 其余项以既有覆盖收口（ABACUS launcher/command 校验由 `tests/unit/test_factory.py` 16 项承载）。同时新增 P5 预备：`scripts/sai_runtime_bench.sbatch` 模板与计划内测量矩阵草案。全量 970 项通过。

- 2026-09-21（本地真实 GPU 验证）：`docs/reports/ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md`——RTX 2070 SUPER + DPA-3.1-3M 上以隔离路径完成 relax（−203.7575 eV，≈31.5 s），`runtime_evidence.json`（status=complete）记录 requested/inherited/effective、线程预算与 affinity、`dp.calculator_built=1`/`dp.force_calls=3`、26 个宿主采样与真实显存占用；manifest 携带 `runtime_evidence` 引用。另修复 `python -m atst_tools.scripts.cli` 缺少 `__main__` 入口（模块执行静默无操作）并新增回归测试。SAI V100/ABACUS/MPI 仍属 P5。

- 2026-09-21（DP image-parallel NEB 首跑）：同一报告 §6——本地 MPICH 3 ranks 完成 DP + `mpi4py` 图像并行 NEB（`world.size == interior_images`，`status=success`），证据记录 `mpi.world_size=3`、rank 0 计数（`dp.calculator_built/reused/force_calls`）与 45 个采样（峰值 3.2 GiB / 8 GiB）；与串行对照逐帧等价（max |ΔE| 1.4e-06 eV、|ΔF| 1.9e-06 eV/Å）。另修复 runner 直接入口 re-exec 的相对路径缺陷与 plan 构建晚于 chdir 的基准缺陷（均带回归测试）。P4 至此全部闭合；站点 OpenMPI/SIF 与收益曲线留 P5。

- 2026-09-21（P3 harness 真实 worker 实跑 + 本地并发观察）：报告 §7——`bench/harness.py`（今 `bench/batch_runner.py`）以真实 DP worker 跑同一 2-case 清单两遍（`--slots 1` vs `--slots 2`，隔离 `workdir`）：makespan 46.3 s → 30.3 s（≈1.5×），单案墙钟 ±2%，显存峰值不变，采样利用率 ≤20%；每 case 报告与 sidecar（含 `dp.cached_instances` gauge）齐全。修复三个 harness 缺陷（相对 `--out` 造成 worker 路径嵌套、串行完成被误判为"无进展"、case 运行目录语义未定义）；定稿语义：默认在配置文件目录运行、显式 `workdir` 相对批量输出目录、报告统一写 `<out>/<case_id>/`。新增实时站点快照与本地并发观察至 P5 预备段（非 P5 结论）。

- 2026-09-21（harness×MPI 组合）：报告 §8——P3 harness 以 case 级 `launcher: [mpiexec,-n,3]` 驱动 P4 的 3-rank DP NEB：`succeeded`（wall 60.0 s、`gpu_seconds=60.0`），rank 0 写 `atst_api_result.json`，sidecar 记录 `mpi.world_size=3`、计数与 79 个采样；新增 case 级 `launcher`/`args` 与 spawn 失败记账（`spawn_error` 不使批次崩溃），并新增真实 launcher 的集成测试 `tests/integration/test_bench_batch_runner_mpi.py`。P5 的 NEB 图数×卡数矩阵可直接复用该模板。

- 2026-09-21（本地推理成本剖面）：报告 §9——DPA-3.1-3M / 66 原子实测：deepmd 导入 0.09 s、模型加载 ≈5.1–5.3 s/worker、首次调用预热 4.8–8.0 s、稳态 E+F ≈0.56–0.58 s/call，运行期 GPU 利用率 ≤20%（桌面共享卡）；结论：单次延迟由 CPU/调度侧主导，且每 worker 有 ≈10–13 s 固定成本（解释了短 relax 的 ≈30 s 墙钟构成）。P5 需在 V100 与科学模型上重测该剖面。

- 2026-09-21（P1–P4 独立代码审查与修复）：同族独立 reviewer 审查 22 提交 diff，确认 8 项 findings 并全部修复——**F1 blocker**：YAML `runtime.binding: round_robin` 在 worker 一致性校验中被错误拒绝（`verify_bound_devices` 现按 rank 重放轮转，并新增真实 MPI 回归 `test_bound_worker_verifies_round_robin_facts_under_mpi`）；F2：count-only allocation 覆盖可见集合时不再要求 caller-bound；F3：harness 默认注入 `ATST_TELEMETRY_ENABLED`，无 YAML `runtime` 段的 case 也产出 sidecar；F4：`allocation_identity=verified` 仅在 token 列表时成立；F5：多槽 case 只分配互异设备；F6：`run_manifest` 异常路径在 finally 停止采样器；F7：显式 `omp` 覆盖继承预算时记录 `runtime_threads_overridden` 计数与 gauge；F8：legacy 路径保留旧默认（无 runtime 请求仍写 `OMP_NUM_THREADS=1`）。验证：`tests/unit` 全绿（约 1010 项）、`ATST_RUN_MPI_TESTS=1` 集成 21 项通过、wheel clean-install 公开发布门（含 `--mpi-smoke`）通过、本地 harness 复跑两份 case 均产出 sidecar。

- 2026-09-21（MPI 计数汇总）：成功路径在失败同步 collective 后对全部 rank 求和 canonical 计数并写入 sidecar `counters_mpi`（`scope=sum-over-ranks`、`world_size`）；真实 3-rank DP NEB 复跑验证 `dp.force_calls` 由 rank 0 的 9 汇总为 23、`dp.calculator_built=4`、`cached_instances` gauge 求和 1；失败路径保持 rank 0 进程级值（诚实降级）。同时把 runtime 选项补进 `docs/skills/atst-cli/SKILL.md`。

- 2026-09-21（恒电势合并预演）：只读 `git merge-tree` 预演 `feature/gpu-node-tuning`(26) × CP `7bc3f92`：无冲突；合并树上跑单测仅两项失败且**在 CP 分支单独同样失败**（`examples/19_constant_potential_Pt` 缺 reference 条目；vendored `core.py` 补丁与 abacuslite 快照归一化测试前提冲突）——列为恒电势合入 main 的前置门禁，详见接口文档 §8.1。预演工作树已清理，保留只读引用 `rehearsal-cp`。

- 2026-09-21（结果 envelope 摘要 + dry-run 语义）：请求 runtime 的运行在 `atst-api-result-v1` 增加可选 `runtime` 对象（status/evidence/attempt/devices；未请求则无此键，逐字节兼容，新增字节兼容测试）；`--dry-run` 与 runtime 选项组合改为进入隔离路径并在 worker 内校验（`--dry-run` 转发），修掉"legacy argparse 不识别 `--devices`"的用户陷阱。文档同步 `PYTHON_API_REFERENCE`/`CLI_REFERENCE`/接口文档。测试：`tests/unit` 全绿。

- 2026-09-21（阶段耗时首版）：sidecar 新增 `phases`（`dispatch_s` 科学 dispatch 墙钟、`attempt_s` worker 总墙钟）；`ensure_runtime_contract` 在 YAML 无 devices 时回退 CLI 记录的设备事实做一致性校验（隔离 dry-run 形状）。本地验证：`atst run --dry-run --devices 0` 结果文档带 `runtime.status=dry-run` 与绑定事实、不写 sidecar；legacy dry-run 仍不写任何文件。测试：`tests/unit` 全绿、集成 21 项通过、wheel 门通过。

- 2026-09-21（TF 维度定位 + 镜像解析器防漂移）：验证报告 §10——本机 TF 运行时可用（tensorflow 2.19.1、`deepmd.tf` 可导入）但无 TF 制品，`dp --pt convert-backend` 对 DPA-3.1-3M 失败（`KeyError: 'type_map'`，标准模型解析路径），TF 维度留待有制品时补测；新增镜像解析器防漂移测试（`tests/unit/test_runtime_dispatch.py` 结构比对 `atst run`/runner 的全部选项，缺一即失败）与 `--log-level` 转发断言。

- 2026-09-21（装包路径端到端复核）：验证报告 §11——干净安装 wheel 直连 runner（`--devices/--telemetry/--threads` + YAML `dp.omp`）跑通 DP relax：结果文档带 `runtime.status=complete`，sidecar 记录 `runtime_threads_overridden=1`、`runtime_threads_effective=4.0`；并修掉该复核发现的"DP `omp` 覆盖未记账"缺口（`apply_explicit_omp`，DP 工厂改用），新增两条工厂测试。

- 2026-09-21（并发扫描驱动器 + 本地重复测量）：新增 `src/atst_tools/bench/sweep.py`（变体交替顺序、每 (variant,repeat) 独立目录、`sweep_summary.json` 汇总 makespan/成功数/卡时/成功案每小时；3 项单测）。本地 3 repeats × slots 1,2 实测（报告 §12）：makespan 中位 44.58 s → 29.51 s（1.51×），两变体卡时几乎相同（44.6 vs 45.4），成功 6/6；边界为非 V100/单卡/2 变体，P5 仍须扩展。计划 P5 预备段登记该驱动器用法。

- 2026-09-21（benchmark record 生成器）：新增 `src/atst_tools/bench/record.py`（`atst-bench-record-v1`：git 修订/解释器与依赖版本/GPU 清单/manifest 与 fixture 哈希/结果目录摘要/操作者字段显式 null；原子写入；2 项单测）。计划 P5 预备段登记归档命令，作为 P5 记录清单（环境三元组、作业号、QOS、sacct、原始命令）的机械载体。

- 2026-09-21（归档记录实测）：对本地 §12 测量生成真实 `bench_record.json`（scratch 目录）：记录 atst `feature/gpu-node-tuning@36f4d26`（dirty=false）、解释器/依赖、GPU 清单、manifest 与 DPA-3.1-3M fixture 哈希、sweep/harness 结果摘要与显式 null 的操作者字段，验证记录构件在真实目录上可用。

- 2026-09-21（第二轮独立复核与修复）：聚焦 bench/services 的独立 reviewer 给 **approve with required changes**（F1 major：非取消退出路径不回收 worker；F2 major：record 的修订事实取自建记录时；F3–F9 minor：record 哈希覆盖/缺失表示、legacy 路径丢 `counters_mpi`/`phases`、非 root 自报 partial、sweep 零墙钟崩溃与生效预算、CLI+YAML devices 误拒、launcher rank 未计入线程预算、sweep per-case 采样噪声）——9 项全部修复并配回归测试（含真实 MPI 集成 21 项复跑通过）；接口文档 §7.2 增补修复摘要，计划 P5 段更新 sweep/record 语义。

- 2026-09-21（P5 一键入口 + MPI 超时回收回归）：`scripts/sai_runtime_bench.sbatch` 升级为"计时 sweep（默认 slots 1,2,3 × 3 repeats，无 per-case 采样）→ 证据 pass（--case-telemetry，产每 case sidecar）→ bench_record.json（自动带 SLURM/模型哈希）"，支持 `DRY_RUN=1` 自检与 `SLOTS/REPEATS/EVIDENCE_PASS/MODEL` 覆盖；本地用真实 DP case 完整跑通该链路（sweep/evidence/record 三件产物齐全、run_time 修订一致、无 warnings）。新增真实 MPI 回归 `test_harness_terminates_every_mpi_rank_on_timeout`（2-rank 超时后无残留 rank，补第二轮复核指出的测试缺口）。集成套件 22 项通过。

- 2026-09-21（恒电势共享顺序复核）：P0→P1 门的"恒电势共享文件顺序确认"完成复核——29 个在途文件的 checkpoint `7bc3f92`（40 个文件条目 = 21 新增 + 19 修改，含接口文档 §8 清单的全部共享文件）已落地；当前端点 `feature/gpu-node-tuning` `eaa7e22`（38 提交）× `7bc3f92` 的 merge-tree 预演**仍无冲突**（合并树 `bfa6e5c4`），合并树共享面聚焦五个测试文件 141 项中仅 §8.1 记录的两项 CP 侧前置门禁失败。CP 工作树 checkpoint 后另有 8 个在途改动（属恒电势 owner，截至 2026-09-21 02:07）；合入 main 仍由其决定。详见接口文档 §8.2。

- 2026-09-21（P5 前置：SAI 只读勘察）：`galileouser02` 下确认站点 ABACUS `abacus/LTSv3.10.1-sm70-auto`（NVHPC 25.7 GNU-branch / CUDA 12.9.1 / OpenMPI 5.0.8 / ELPA）与 DP 离线 env `deepmd-kit/3.1.2`（Python 3.12.12 + torch 2.8.0 + mpi4py 4.1.1；**无 ase/pydantic**，P5 需以 venv/conda env 补齐）；分区/QOS 现场快照（4V100 15 idle、16V100 多数 alloc；`rush-*` 1 天、`flood-*` 4 小时、`improper-gpu` 30 天）；`/org/pku-jianghong/liuzhaoqing`（FT²DP `$R`）不可读、家目录无 `.pt` → P5 权重与 fixture 需单向上传。本机登台包已备（wheel sha256 `6f43cca2…`、源码 tarball `17bb4d99…`（`1cf5c85`）、FT²DP 单头 100k `13b74797…`、DPA-3.1-3M `86dd3a80…`；单头 EMA 仍缺）。**未提交作业、未写入远端**；计划 P5 预备段登记。

- 2026-09-21（P5 前置续：FT²DP 本地接入 + 站点 env 复核）：**DPA4/SeZM 兼容性为选型硬条件**——站点 `deepmd-kit/3.1.2` 对 FT²DP 单头 100k 报 `Unknown model type: dpa4`，P5 底座改用 `deepmd-kit/3.2.0`（torch 2.13.0+cu126）+ `openmpi/5.0.8-nvhpc25.7-gnu-auto`（mpi4py 实测可用；Lmod 初始化路径 `/opt/modules/lmod/9.2.4/init/bash`，`/etc/profile.d/modules.sh` 不生效）。本地以 3.2.0b1.dev62 底座 venv 完成：atst 隔离 relax 冒烟（FT²DP 单头 100k、66 原子 H2-Au，E=−3498.0803 eV、sidecar `complete`）与 **FT²DP + mpi4py 3-rank 图像并行 NEB**（chain5，与串行逐帧等价 max|ΔE|=2.97e-05 eV、max|ΔF|=1.27e-05 eV/Å；小 band 并行更慢，每 rank ≈5 s 加载成本）；跨 3.2.0 dev 构建单点 ΔE 7.6e-06 eV。`scripts/sai_runtime_bench.sbatch` 已填入核实的 module 行（QOS 行留提交时确认）；运行手册与登台包在 `~/scratch/atst-p5-staging-20260921/`。**未提交作业、未写入远端**。

- 2026-09-21（HEAD 复核快照）：`d8cd59c` 上 `tests/unit` 1016 passed / 0 failed（2 documented skips）、`ATST_RUN_MPI_TESTS=1 tests/integration` 22 passed（真实 MPI，48.5 s）；wheel clean-install 公开 API 门在 `b9722d7` 复跑通过（src 自 `acc791a` 未变）。P5 执行仍待维护者授权与 fixture/容差/预算裁决。

- 2026-09-21（收尾复核 + AutoNEB 冒烟）：wheel clean-install 公开 API 门在 `b22523e`（含 harness workdir 修复后）复跑通过；FT²DP + AutoNEB 本地冒烟（66 原子 H2-Au 端点、`n_simul=2`/`n_max=4`）`status=success`、16.25 s、`dp.cached_instances=1`（图像间共享单 calculator）；并行 AutoNEB（`mpiexec -n 2`）同样通过（20.13 s，单卡略慢）。SAI 版 AutoNEB case 入清单草案（6 case）。报告 §16。

- 2026-09-21（FT²DP P5 预演）：以 P5 科学模型（FT²DP 单头 100k）+ 66 原子 H2-Au relax 在本地走通 P5 首两项测量的形状——计时扫描 slots 1/2/3（makespan 26.23 → 13.69 → 13.49 s，4/4 成功；两 case 在 slots=2 下完全重叠）与证据 pass（util ≤29%、显存峰值 3.4→4.8 GiB、threads 1/4 差异 ~7%）；生成 `atst-bench-record-v1` 归档（wheel 运行 → revision 为 null，故登台包新增 git bundle；本地克隆复验 sweep/record 的 record_time/run_time 均带真实 `head=e853852`/`branch`/`dirty=false`）。顺带修复：harness 现在拒绝共享非空 `workdir` 的 manifest（预防证据互相覆盖，含单测与模板说明）；全量单测 1017 passed / 2 skipped。详见验证报告 §14。

- 2026-09-21（NEB 图数×rank 数本地压力测试）：FT²DP 科学体系（χ-Fe₅C₂ 118 原子，`TS1_IS/FS` 插值 chain6/chain10）单卡对照——串行 16.97 s / 20.37 s，单卡 4 rank 69.20 s、8 rank 136.83 s（**4.1×/7.7× 负收益**），显存峰值 7.6–7.7 GiB 逼近 8 GiB 上限；并行侧 Σforce_calls 更少（18/26 vs 46/66），劣化来自同卡多上下文下每次调用延迟。P5 的"10 ranks / 1 卡"改按压力边界记录；chain6/chain10 已加入登台 fixtures。报告 §15。

- 2026-09-21（审阅地图 + 冷/热启动复核）：新增 [分支审阅地图](ATST_GPU_TUNING_BRANCH_REVIEW_MAP_2026-09-21.md)（49 提交分组、证据索引、开放门、复现命令、建议阅读顺序），作为 reviewer/合入入口；验证报告 §14 增补冷/热启动复核（全新目录 12.76 s vs 同目录重复 12.37/13.70 s，进程级缓存无显著影响）。

- 2026-09-21（冻结消息机械审计 + 修正）：逐条比对接口冻结 §2/§4 的用户可见消息与实现，发现 5 处偏差并修正——`runtime must be a mapping` 未实现；`telemetry.enabled`/`interval_s` 走 pydantic 原始消息且 union 泄漏 `runtime.telemetry.bool` 行；非字符串 token 缺引号；CLI 非数字 interval 泄漏 `could not convert string to float`。实现现与冻结文本逐条一致，新增契约测试锁定（`test_runtime_schema.py` 表格 12 例 + `test_runtime_launch.py` 4 例）；`tests/unit` 1019 passed / 2 skipped；wheel clean-install 公开 API 门与 `ATST_RUN_MPI_TESTS=1` 集成 22 项在 `2c807a9` 复跑通过。接口冻结文档 §7.2 补记收口说明。

- 2026-09-21（验收表覆盖加固）：对接口冻结 §9 验收对照表逐行核对测试覆盖，补上三处断言/用例——越界 UUID 的 fail-closed 消息（`explicit device selection is refused: '<uuid>' is not part of the inherited visible set`）、worker 失配的两条路径（replay 分支消息 + `resolved`/`recorded_effective` context）、`ATST_VISIBLE_DEVICES=""`/空白串的显式空请求与未设置=inherit。`tests/unit` 1021 passed / 2 skipped。

- 2026-09-21（sidecar 峰值字段落实现）：接口 §7.2 / SPEC §6 要求的"显存峰值标记 `sampled_peak`"此前无对应字段（19 份本地 sidecar 均无 `sampled_peak`）——现 `telemetry.sampler.memory_peak_mib = {value, source}`：有样本时 `value=max(memory_used_mib)`、`source="sampled_peak"`；无样本/遥测禁用时二者均为 null（不填 0），并有单测覆盖两种状态。

- 2026-09-21（线程键四键断言 + 文档标识符扫描）：接口 §6 冻结的“OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS 取同一值”此前只断言了 OMP 一键——现断言四键同值；另对接口文档中的 22 个环境变量/schema id/证据文件名做机械扫描，全部在源码中存在（无缺口）。

- 2026-09-21（登台包刷新至当前 HEAD）：wheel/tarball/bundle 重新由 `9aa1ef9` 导出（含全部契约修正），旧 e853852 套件移入 `superseded/`；`MANIFEST.sha256` 全量刷新；计划 P5 段的登台包条目不再内嵌易失哈希，改为指向 MANIFEST 并注明登台时重导出。

- 2026-09-21（登台包制品本体验证）：用刷新后的套件本体做端到端验证——① 安装 wheel 后**不设** `PYTHONPATH` 直跑（证明走 site-packages）：`status=complete`，sidecar `telemetry.sampler.memory_peak_mib={value:2641, source:'sampled_peak'}`；② 从 `9aa1ef9` bundle 克隆后运行 sweep+record：`record_time`/`run_time` 均带 `branch=feature/gpu-node-tuning`、`head=9aa1ef9…`、`dirty=false`，warnings 为空（slots=1 2/2 成功、27.1 s）。

- 2026-09-21（P5 清单/配置补齐与预解析）：登台 `configs/` 补齐 relax（t4/t8）、NEB（chain5，3-rank launcher）、AutoNEB 四份 SAI 路径配置并逐份通过 schema 归一化；`cases.p5.draft.json`（6 case）经 `bench.batch_runner.load_cases` 预解析通过（workdir 互异、launcher/timeout 正确）；MANIFEST 同步刷新。

- 2026-09-21（计划/接口文档陈旧状态清理）：P2 的 sidecar 条目（sidecar、phase 耗时、计数、结果 envelope 摘要、峰值标记）已全部交付——计划该项改 [x] 并列出第四/五片；计量生命周期项与 sampler 项补注已交付子项（计数/存活对象/显存峰值/独立 cache 已证，MPS 归属未知与重启回归留 P5）；接口文档 §7.2 的“留待 P2 后续片”改为逐项已交付说明。

- 2026-09-21（SPEC §11.1 pin 表复核）：对 7 棵树重新核对（workplace/app-tools 分支与 main、app-tools-forge、sidereus main 与 4 个 worktree。deepmodeling checkout）——**全部与表一致、无漂移**；恒电势 worktree 仍为 `7bc3f92` + 8 个在途文件。

- 2026-09-21（采样开销 A/B）：同一 2-case 清单、slots=1、各 3 次重复——关闭 per-case 采样中位 27.16 s、开启 `--case-telemetry` 中位 26.85 s（差 ≤0.4 s、<1.5%，方向为开更略快）→ 该规模下采样开销不可测；报告 §14 增补，P5 可复用该 A/B。

- 2026-09-21（恒电势合入 + GPU rebase + 联合验收）：恒电势开发者完成合入（atst `main` = `7bc3f92`+`d30747b`，父仓 `375ef7c6b`/`7e3009e32`；§8.1 两项门禁已被其修复，main 单测 943 项 0 失败）。GPU 分支 `git rebase main`：61 提交全部重放、零冲突；新增 SPEC §7A 联合验收测试（`reference_fcp`/`compensated_gate` × runtime，双向 fail-closed）。合体树门禁：单测 1091 项 0 失败、真实 MPI 集成 22 项、wheel clean-install 门通过。登台件按新 HEAD `cca0912` 重导出并克隆复验（含 CP+GPU 模块，冒烟 sidecar 正常）。接口文档 §8.3、计划集成检查点与交付日志同步。

- 2026-09-21（用户文档补全，§8 合并后收尾）：`CONFIG_REFERENCE` 的 telemetry 说明补上`telemetry.sampler.memory_peak_mib`（`sampled_peak` 标记）与 MPI `counters_mpi`；`FEATURE_STATUS_MATRIX` 的 Runtime 行修正阶段名（S5→P5）并注明已有本地真实 GPU 证据、SAI V100 身份验收待 P5；读者入口文档（README/index/examples README）保持只链接引用、不加受限词汇内容。

- 2026-09-21（**P5 现场执行，首轮完成**）：维护者“开跑”后于 SAI `galileouser02` 完成双通道——① 冒烟三连（1430846 首跑失败→定位 Lmod/`set -u` 缺陷并修→1430966 通过→1431010 修复设备事实后通过）；② DP 矩阵 1431119（4 case × slots 1/2/3 × 3 repeats，12/12 全通过；makespan 16.1/16.6/16.8 s，卡时 29–30.8 s；sidecar 含设备事实、threads、计数器与 `counters_mpi=35`、显存峰值 480–3296 MiB、利用率 ≤13.6%）；③ ABACUS 通道 1431200（示例 06 relax 172.8/171.0 s、示例 01 NEB 747.3/777.4 s，4/4 通过；利用率 29.5–45.2%）。新增现场报告 `docs/reports/ATST_RUNTIME_SAI_V100_VALIDATION_2026-09-21.md`；站点问题与修复：Lmod 在 `set -u` 下静默失效（`set +u` 包裹 + mpi4py 校验）、Slurm 槽位限制 MPI（`--oversubscribe`/`--ntasks`）、`ATST_SOURCE_ROOT` 让记录带真实修订、未绑定运行设备事实修复（`4d77fee`）、ABACUS 示例相对路径→登台绝对路径副本。计划 P5 清单按证据更新（6 项完成、3 项部分：host/SIF 成对、每卡 4 进程、多卡 NEB）。

- 2026-09-21（P5 第二批：slots=4 与多卡 NEB + 站点 MPI 发现）：① `slots=4`（1431648）12/12、makespan 15.80 s、卡时 29.16 s——站点并发曲线 1/2/3/4 全为 ≈16 s（该规模不随并发受益）；② 多卡 NEB 对照（4 内部图）：`srun --ntasks=4 --gpus-per-task=1` 因站点 **srun 默认 `--mpi=none`** 退化为 4 个独立串行 NEB（1431955，world=1）；改 `srun --mpi=pmix_v5 --gpus-per-task=1`（1432107）得到正确图像并行：`world_size=4`、`counters_mpi` Σ`dp.force_calls=38`、11.8/9.9 s；③ 探针（1432043）证实 `srun` 任务内无 PMI（`PMI_SIZE`/`PMIX_SIZE`/`OMPI_*` 全缺失、mpi4py size=1）；④ **站点 OpenMPI 下 MPI rank 内 re-exec 重绑定挂起**（1431952：两 rank 打印 pre-exec 后超时；本地 MPICH 同场景正常）——`mpiexec + runtime.binding` 在站点不可用，超时后 exec 过的 rank 成孤儿使取消作业长时间停留 `CG`（1431952/1431646 留档）；⑤ ABACUS 三次重复（1431647）完成 repeat-1 双例与 repeat-2 relax 后，repeat-2 NEB 在同节点出现孤儿进程后停滞 ~1h，已取消并补跑（1432820，NEB×2）。SAI 报告 §5/§5c/§6/§7/§8 与计划 P5 清单同步更新。

- 2026-09-21（P5 收尾：ABACUS 候选点重复完成）：NEB 补跑（1432820）成功 712.7/709.8 s，与 1431647 的 750.2 s 合为 3 点（中位 ≈712.7 s、离散 ~5%）；relax 共 4 点（172.8/171.0/171.7/172.6 s）。此前 repeat-2 NEB 的同节点停滞（孤儿进程同期出现）记为站点观察项。P5 清单中 DP/NEB/采样项完成，仅 host/SIF 成对留后续；SAI 报告与计划已收口。

- 2026-09-21（P5 交付物处理）：5 份 `bench_record.json` 补齐操作者字段（`approved_by=QuantumMisaka`、`allocated_gpu_hours` 由 sacct 计算：0.024–0.851、`sacct_excerpt`）；证据切片归档到 `docs/reports/data/ATST_SAI_V100_20260921/`（5 records + 4 sweep 汇总 + 7 份 sidecar + abacus4 两例 case 记录，共 1.6 MB，附 README 说明来源与站点全量路径）。

- 2026-09-21（**合入 main**）：按维护者指示，`feature/gpu-node-tuning`（71 提交，含 runtime 绑定/证据层、bench 工具链、契约修复与 P5 现场证据）以 **fast-forward 直接合入 `main`**（未建 PR）；`origin/main` 同步更新。后续开放项不变：host/SIF 成对、8 图×8 卡、8 ranks/1 卡压力行、站点 MPI re-exec 挂起问题的站点/上游确认。

- 2026-09-21（第三轮外部复核修复）：对 `f03b3e6` 的 8 项审查（P1×4、P2×4）逐条复现并修复——round_robin inherit 补 allocation 约束；runner 的 MPI 初始化推迟到重绑定 exec 之后（SAI OpenMPI 挂起根因）；进程组清理升级为 SIGKILL + 组空确认；manifest 按实际运行目录判重；`threads: auto` 与 CLI 绑定覆盖在 worker 侧修正；`case_telemetry` 透传；新增 `allocation.gpu_seconds` 指标（与 per-case `gpu_seconds` 分开）；证据切片 JSON 移入版本控制（`.gitignore` 例外）。验证：unit 1097 passed / 2 skipped（共 1099 收集）、integration 23（含真实 MPI 入口冒烟）、治理通过。接口文档 §7.3 记录逐条处置。

- 2026-09-21（修复后现场复验）：SAI 重跑此前挂起的 `mpiexec -n 4 + round_robin` 四卡用例（1434302）——22 s 完成、1/1 ×2，rank0 `bound=true`/`effective=['0']`/`world_size=4`、`counters_mpi` Σ38 次力调用；P1-2（runner MPI 初始化顺序）与 P1-1（allocation 约束）在站点闭环。修复提交 `0668d61` 已推送并 fast-forward 合入 `main`。

- 2026-09-22（**GPU 调优计划/报告状态口径对齐**）：把计划与报告的状态文本对齐到仓库内已有证据，不改结论、代码与测试。① 计划头部 `**状态**`/`Status` 由「执行中（P0）」改为「执行中（P0–P5 已完成，P6 进行中）」，并新增「剩余项（2026-09-22）」清单（TF 后端维度、DP 通道容器对照、FT²DP EMA 标 `condition-blocked`；只读模型共享/重启回归、MPS 归属、站点 `mpiexec` 重绑定确认、P6 交付/平台接入标 `open`）；② 计划 P5「候选正式点 / host/SIF 成对」行与「NEB 图数 × 卡数映射」行勾选并补证据指针（作业 1438496：同一 allocation 内 host 142 s vs SIF 153 s、末能量一致 −239256.2707 eV，SAI 报告 §5j；8 图×8 卡见 §5h）；③ 计划 P2「ABACUS 按实际 command 验证 launcher」行勾选，证据为 `tests/unit/test_factory.py` 的 8 个 ABACUS 工厂用例（本工作树实跑该文件 18 项通过）加站点 ABACUS 通道的实际运行（SAI 报告 §5b/§5d/§5j），依据即本报告 2026-09-21「P2 收口片」条目；④ 计划 P2「DP TF 维度」行保持未勾选并显式标注条件阻塞；⑤ SAI 报告头部状态由「首轮完成（host/SIF 成对留后续）」改为「已完成」并指向 §5j/§5h；⑥ `FEATURE_STATUS_MATRIX` 的 Runtime 行 Notes 同步：P5 矩阵按已完成口径，仍未闭合项（TF 后端维度、只读模型共享/重启回归、MPS 归属、站点 `mpiexec` 挂起）标 `open`/`condition-blocked`，并修正该行内已失效的 `calculator.abacus.omp` 缺陷描述（`5e26789` 已在 2.2.7 前修复，站点 1436782 复验）。**本登记取代 2026-09-21「合入 main」条目末尾的开放项列表。** 未改动：SAI 报告 §1–§8 正文（其中 §5i 的「保持开放」处置由 §5j 取代、§8 的后续清单亦已被 §5h/§5j 取代，属该报告正文口径，留待后续收口）、计划 P6 段与第 66/69/203/204 行、`src/`/`tests/`/`scripts/`。
- 2026-09-22（**PT 线程键与 MPS 归因站点复验**）：SAI 作业 1445744/1445792（固定点 `af82973`）——两个 `DP_*_OP_PARALLELISM_THREADS` 与 OMP 同值到达 DP 子环境（`threads_source=explicit`）；MPS 探测三态语义成立（现场 `detected=false` 且三路探测完成）；`self_reported` 记 torch 分配器高水位 620.139 MiB。证据切片 `docs/reports/data/ATST_PT_MPS_CLOSEOUT_20260922/`，报告 §9。维护者裁定：**TF 后端不做特意支持**，算法层兼容（计划该行改标 `not-planned`，矩阵同步）。边界：MPS 正向路径（`detected=true` + reason 点名 MPS）仅单测覆盖——当日下午两个节点均看不到 MPS 守护进程（当日上午作业曾可见），探针如实记否证。

- 2026-09-22（**DP PT 后端加固 + MPS 归因**）：优先项交付——① DP PT：制品 kind 判定（`.pt`/`.pth`/`.pb`）、多任务 head 缺失/错误的可操作错误（列出可用 heads + `dp --pt show` 指引）、冻结归档算子锁定错误的求值期翻译（`.pth`/`.pt` 差异化建议，其余错误 fail-open）、`dp_model_identity()` 事实 helper、实例属性 `atst_model_kind/backend/head`（`tests/unit/test_dp_pt_backend.py`，29 项）；线程键并入 `DP_INTRA/INTER_OP_PARALLELISM_THREADS`（`tests/unit/test_runtime_thread_env.py`，7 项）。② MPS：`probe_mps()` 三路保守探测（进程表 + 客户端管道仅作正证据；`detected` 可为 null）、空表 reason 点名 MPS、`self_reported` 本进程 torch 分配器高水位（不触发 CUDA 初始化）（`tests/unit/test_evidence_mps.py`，14 项）。行为变化：DP head 类失败由裸 `AssertionError` 变为 `DeepPotentialError(RuntimeError)`；guard 以子类实现（`isinstance(..., deepmd.calculator.DP)` 仍为真）。**未做/待续**：`dp_model_identity()` 与 `atst_model_*` 尚未接入 sidecar（默认运行路径保持零额外加载开销）；站点侧 MPS 探测与 `self_reported` 现场复验待下一轮 SAI 作业；TF 制品维度仍 `condition-blocked`。

- 2026-09-22（**P2 现场收口 + record 通道验收**）：在 SAI 4V100 执行作业 1444802/1444708 并断言通过——只读模型共享（`444`/`555` 模型目录摘要+mtime 前后不变、`dp.calculator_built=1`/`reused=1`）、`ATST_ATTEMPT` 缓存与证据归属一致、同一 workdir 重启回归末帧能量等价（Δ=1.6e-05 eV）、MPS 现场事实（节点启用 MPS，计算进程归因记 `unavailable` 不填 0）、record 双通道夹具（`dp_model` sha256 与 `abacus_inputs` tree 摘要，含 git 修订 `0fd205a`）。代码：修 `runtime/launch.py` 未下传 `ATST_ATTEMPT` 的归属缺口、`bench/record.py` 增可重复 `--fixture-labeled LABEL=PATH`（目录记 `file_count`/`tree_sha256`，`--fixture PATH` 逐字段不变）并把站点入口按通道接线；新增 `tests/unit/test_runtime_model_sharing.py`、`tests/unit/test_runtime_restart_isolation.py`（9 项，含去掉修复即失败的守卫）。文档：新增 [P2 收口报告](ATST_P2_CLOSEOUT_2026-09-22.md)与证据切片 `docs/reports/data/ATST_P2_CLOSEOUT_20260922/`；计划 P2 两行勾选、P6 文档行勾选并标注独立终审与共享 image 迁移仍 open；SAI 报告 §5i/§8 加取代标注；接口冻结文档缓存目录命名精度修正。分支 `dev/gpu-tuning-closeout-20260922`（未合入 main）。



- 2026-09-21（**2.2.7 发布收尾**）：① 官方无缓存 clean-install 复核——隔离 venv 执行 `pip install --no-cache-dir atst-tools==2.2.7`（27 个包、50 s），`atst --version` = `atst 2.2.7`、`package_version()` = 2.2.7、包从该 venv 的 site-packages 导入，且 2.2.7 新能力（`runtime.*`、`bench.batch_runner` 的 `--share-worker`、`batch_worker`、`calculator.abacus.omp` 缺省未设置）在发布物中可用；② 建 GitHub Release `v2.2.7`（此前 2.2.5/2.2.6 无 release 对象，GitHub "Latest" 一直停在 2.2.4，现已对齐）；③ 发布期复核 `docs/archive/pending_delete/`（24 个文件，README 已逐条给出"结论已被吸收"的理由）——本轮不删除，留待维护者决定；④ release notes 补齐 2.2.6 同款的 Publication Evidence / Validation Matrix / Download 三段（含 CI run id、PyPI sha256 与 clean-install 记录）。未做且属维护者/平台侧：Gitee 手动同步（本地无此 remote）、父仓 gitlink 更新、Paimon/SIF 平台验收。
- 2026-09-21（**2.2.7 已发布（PyPI）**）：tag `v2.2.7` → `af9c8fa6b82386a52055a5b3dced82eb3d8f4ef2`（推送后触发 `publish-pypi.yml`，run 35614555409）：Release preflight 成功（release readiness、unit tests、docs governance、sdist/wheel 构建、dist 检查、wheel 公开 API 校验），`pypi` environment 的 5 分钟 wait_timer 到点后 Publish 作业成功；PyPI 已上线 `atst_tools-2.2.7-py3-none-any.whl`（386,588 B）与 `atst_tools-2.2.7.tar.gz`（339,853 B），`info.version=2.2.7`、`requires-python=>=3.10`。发布后文档口径更新为「已发布」：release notes 头部、README badge/状态表/Release 行、`FEATURE_STATUS_MATRIX` 状态与首段、`USER_GUIDE_CN`、`CONFIG_REFERENCE`、`DOCS_ARCHITECTURE`。在途盘点：无未合并的 atst 代码，CP 候选随包发布且保持「开发候选」措辞。
- 2026-09-21（**发布准备：2.2.7 候选**）：在途盘点确认**无未合并的 atst 代码**（远端各分支 `ahead=0`，本地分支均为祖先；CP 候选代码已在 main，其平台/MPI 验收仍开放并按"开发候选"口径随包发布）。发布准备：`pyproject` 2.2.6→2.2.7；新增 `docs/releases/RELEASE_NOTES_2.2.7.md`（含脚本要求的精确 Compatibility 行）；README badge/状态表/Release 行、`docs/index.md`、`USER_GUIDE_CN`、`CONFIG_REFERENCE`、`PYTHON_API_REFERENCE`、`DOCS_ARCHITECTURE`、`PYPI_RELEASE_AUTOMATION`、`FEATURE_STATUS_MATRIX`（版本/状态/Runtime 行/CP 行）同步为 2.2.7 候选口径。门禁：unit 1131 passed / 2 skipped、integration 23 passed、docs governance、wheel clean-install、`check_release_readiness.py --tag v2.2.7`。
- 2026-09-21（**host/SIF 成对完成——P5 矩阵全部收口（作业 1438496）**）：同一 relax 用例在同一 allocation 内host（module ABACUS + venv Py3.13）142 s 与 SIF（`apptainer exec --nv -B /opt:/opt` + `--env LD_LIBRARY_PATH=$LD_LIBRARY_PATH` + 镜像 Py3.12.14）153 s 两遍，**末能量一致 −239256.2707 eV**，两侧 sidecar complete（各 1 次 build/力调用、OMP=8）。可用的 SIF 调用姿势与范围说明（该镜像是 ABACUS 交付、deepmd 不在其中，DP 通道走站点 module）已写入 SAI 报告 §5j；证据切片 `docs/reports/data/ATST_HOST_SIF_PAIR_20260921/`。至此 **P5 压力/收益矩阵无剩余行**。
- 2026-09-21（**host/SIF 勘察定位到精确阻塞点（镜像侧）**）：先厘清范围——该 SIF 是 **ABACUS** toolbox 交付（`Application: ABACUS`、`AtstToolsDelivery: toolbox`），**deepmd 不在其范围**（DP 通道走站点 module 环境，本轮所有 DP 运行即如此），故该行是 ABACUS 通道成对。SIF 内 atst 可导入（绑定检出 + PYTHONPATH，Python 3.12.14 / ase 3.29.0 / pydantic 2.13.5）、`/opt/apps` 可见；**`/opt/devtools` 在容器内不可见**（显式绑定亦然，判断为 `shared-layer2` 在 `/opt` 上的覆盖冲突），因此镜像自带的 ABACUS wrapper 报「readable ScaLAPACK library directory」、直接跑宿主二进制有 12 个未解析库；账号内 4 个镜像同一报错 ⇒ 启动上下文问题、非单个镜像损坏。**移交镜像归属方**（提供文档化 launcher/绑定或让 wrapper 从宿主环境读栈）；host 侧用例已多次跑通，非 atst 侧缺陷。证据与复现见 `docs/reports/data/ATST_HOST_SIF_RECON_20260921/`；SAI 报告 §5i 重写。
- 2026-09-21（**host/SIF 前置勘察（受阻，留精确阻塞点）**）：SIF `20260920-toolbox-atst` 内 atst 可导入（绑定检出 + PYTHONPATH；Python 3.12.14 / ase 3.29.0 / pydantic 2.13.5，无 deepmd → 仅 ABACUS 通道），但其 ABACUS 为 "SAI-native runtime provider" 包装：即使绑定 `/opt/modules`+`/opt/apps`+`/opt/devtools` 仍报`module did not provide a readable ScaLAPACK library directory`，容器内 `mpirun` 亦不可解析 → **该行移交 SIF 归属方（toolbox 交付）**，复现命令与输出见 `docs/reports/data/ATST_HOST_SIF_RECON_20260921/`；SAI 报告新增 §5i。P5 压力/收益矩阵至此仅剩这一行，且阻塞在容器侧而非 atst 侧。
- 2026-09-21（**主线站点收口：共享 worker 站点验证 + 8 图×8 卡（作业 1438378/1438379）**）：① 共享 worker 在站点对 3 例 CCQN 批 **17.38 s → 5.73 s（3.0×）**，后续 case 各 0.35 s；fail-closed 复验（持 0 号卡请求 `devices:[1]`）0.30 s 内被拒；② 8 图×8 卡（`rush-gpu` 16 卡上限，`srun --mpi=pmix_v5 --ntasks=8 --gpus-per-task=1` + `round_robin`）24.31 s vs 串行 26.63 s——**本 band 上仅 ≈1.1×**，与四卡行一致：图并行收益随每步工作量增长而非卡数；8 卡能力与逐 rank 绑定已验证。P5 压力/收益矩阵只剩 host/SIF 成对。新增两个证据切片与 SAI 报告 §5h。
- 2026-09-21（**主线：共享 worker 模式 `--share-worker`（摊薄启动）**）：批量执行器新增 opt-in 模式，整批 case 在**同一个 worker 进程**顺序执行，模型加载+首次调用预热只付一次。实现：新模块 `bench/batch_worker.py`（`--jobs`/`--out`，逐 case 写 `atst-api-result-v1`，逐 case 错误隔离、不重试）+ `batch_runner` 的 `--share-worker` 分支（单槽、发布绑定事实、超时/停止语义保留）。关键修复：共享 worker 以「已绑定进程」启动（复用 `runtime.launch.build_child_environment` 发布 `ATST_RUNTIME_BOUND` 等），使**带 `runtime:` 段的配置可用**，而矛盾请求仍逐 case fail-closed。验收：单测 1131 passed / 2 skipped（含「回退该修复即失败」的守卫证据）与真实 launcher 集成 2 passed；维护者真实 DP 端到端 A/B（2 例 CCQN，均带 `runtime` 段）：逐 case 68.2 s（36.5+31.7）vs 共享 **34.2 s**（27.7+3.1）——固定成本只付一次。HANDOVER §7.1 补该模式的语义与约束。
- 2026-09-21（**主线：ABACUS 内层并行扫描（作业 1438158）**）：同一 relax 用例在同一张 V100 上扫 `mpi × omp`：4×1 = 147.3 s、4×2 = 145.8 s、1×8 = 146.8 s（均在噪声内），**2×4 = 224.3 s（慢 50%）**。结论：该 ABACUS 负载不吃 CPU 预算，示例默认 `mpi: 4, omp: 1` 即为好选择，内层拆分无需调优。证据切片 `docs/reports/data/ATST_ABACUS_PARALLEL_SCAN_20260921/`；SAI 报告新增 §5g。
- 2026-09-21（**主线：DP 启动成本站点复测（作业 1437867）**）：同一构造路径在 V100 GPU torch 下（`torch 2.13.0+cu126`、`cuda:0`、`torch_threads=1`）构造 1.55 s、首调用 1.33 s、**稳态 0.028 s/调用**，**没有**本地那条 fuser 预热曲线——因为 TensorExpr fuser 只在 intra-op 线程 > 1 时工作。因此 §18 提出的 `no_jit` schema 杠杆在 GPU 目标上不成立（不推进），站点上值得做的仍是"摊薄每 case 启动"（启动 ≈2.9 s + CCQN CPU ≈2.5 s 构成 6.7 s 的整跑，推理可忽略）。证据：`docs/reports/data/ATST_CCQN_SAI_20260921/probe/`；SAI 报告新增 §5f，本地报告 §18 的杠杆① 已标注被否。
- 2026-09-21（**主线：DP 固定成本归因 spike（本地）**）：变体矩阵 + 归因链确认预热与体系规模无关、非 ASE/非 ATen，**是 TorchScript 惰性 JIT**——`no_jit=True` 用同一权重把每 worker 固定成本从 24 s 降到 ≈3 s（能量一致）；`DP_INFER_BATCH_SIZE` 与 `TORCHINDUCTOR_CACHE_DIR` 为无效项，tiny 预热不可摊还。两条修正：① §17 的"推理"实为 **CPU-only torch** 口径（本机 `torch.cuda.is_available()=False`），GPU 侧固定成本以 SAI §5e 的 ≈2.4 s 为准；② **进程内 `dp.omp` 不生效**（torch 已在线程池初始化后被导入），只有"进程外预置线程环境"通道有效（正是既有 worker 契约）。写入本地报告 §18；`no_jit` 在 GPU torch/站点模型的收益待站点探针。
- 2026-09-21（**主线：CCQN 固定成本 SAI 复测（作业 1437354）**）：把本地 §17 的分解搬到站点（V100 + FT2DP 单头 100k）：替身 pass（登录节点）2.56 s、真实 pass 6.71 s wall / 4.95 s dispatch、9 次力调用、峰值 1074 MiB、`threads_source=harness` → **每 worker 固定成本 ≈2.4 s**，而本地多任务 DPA-3.1-3M 是 15.6 s：固定成本随**模型规模**变化，CCQN 自身 CPU 段两端都只有 ~2.5 s。结论：摊薄 worker 初始化对"大模型 + 短 case"最值钱。该作业同时是产物更名后的首个新运行（`batch_summary.json`/`case_report.json`/`worker.{out,err}` 落盘，`bench_record` 正常）。证据切片 `docs/reports/data/ATST_CCQN_SAI_20260921/`；SAI 报告新增 §5e，本地报告 §17 指向复测结果。
- 2026-09-21（**产物名更名：harness_* → case_report/batch_summary/worker**）：按维护者「产物名也改了」的要求，`batch_runner` 新运行的产物改为 `case_report.json`、`batch_summary.json`、`worker.{out,err}`；`record.py` 读汇总时新增 `batch_summary.json` 并回退旧 `harness_summary.json`（新名优先），归档树照旧可读。两条历史拼写继续冻结：schema `atst-bench-harness-v1`（版本化文档标识）与证据取值 `ATST_THREADS_SOURCE=harness`（归档 sidecar 的 `threads_source`）。`docs/reports/data/**` 的归档切片保持旧名并已在切片 README 注明；HANDOVER §7.1、计划 P3 行同步。验证：bench 三件套单测 38 passed、真实 launcher 集成 2 passed、维护者在本机以真实 DP 用例跑通一批（1/1、38 s，落盘即为新名）并用 `record` 从新树建记录（0 warnings）、对三个归档旧树重试建记录同样 0 warnings。Ruling：该包为机械改名且已有新/旧双路径测试与真实探针，不再单设独立 reviewer。
- 2026-09-21（**主线起步：CCQN 成本分解（本地初测）**）：按「先看 CPU 段」的原目标，用 `examples/12_ccqn_H2-Au`（H₂+Au₆₄）拆解——替身 pass（瞬时 E/F）得 CCQN/ASE 自身 CPU ≈1.5 s + 0.08 s/调用；DP pass（DPA-3.1-3M，隔离 worker）9 次调用 29.8 s，其中 **per-worker 固定成本 ≈15.6 s**（模型加载 5.2 s + 首次调用预热 10.3 s）。结论：小体系 CCQN 的墙钟一半以上是 worker 初始化，CCQN 算法本身只 ≈2 s（≈7%）→ 杠杆是「摊薄 worker 初始化」，不是改写 CCQN；待 SAI FT²DP 复测。证据写入本地报告 §17；同时现场复验了 fail-closed 设备语义。
- 2026-09-21（**基准工具链更名：harness → batch_runner**）：按维护者裁定，`src/atst_tools/bench/harness.py` 更名 `bench/batch_runner.py`（类 `HarnessOptions` → `BatchOptions`），测试同步更名 `test_bench_batch_runner.py` / `test_bench_batch_runner_mpi.py`；术语定为「bench = 测量工具链、batch = 一次运行、harness = 历史名」。**当时**冻结不动：产物名 …、schema `atst-bench-harness-v1`、证据取值 `ATST_THREADS_SOURCE=harness`；其中产物名随后由维护者改判（见下一条登记），schema 与证据取值继续冻结。`bench/__init__.py`/`sweep.py`/`record.py`/站点 sbatch 注释与 5 处文档口径同步；新增 `docs/developer/HANDOVER.md` §7.1「基准工具链（bench）」登记清单字段、命令、产物与边界。门禁：unit 1101 passed / 2 skipped、integration 23 passed、docs governance 通过。
- 2026-09-21（**P5 收尾：harness 线程通道裁定 + 修复后 ABACUS 基线 + 8 ranks/1 卡站点行**）：裁定 manifest 的 per-case `threads` 为调用者显式预算——`bench/harness.py::case_environment` 补写 `ATST_THREADS_SOURCE=harness`（`1a62a72`，新增回归测试；接口文档 rev.6、示例清单 notes、审阅地图 §4 同步）。站点执行 J1436926（工具形状错误：`--ntasks=1` 使示例内部 `mpirun -np 4` 被 PRRTE 拒，ABACUS 组 0/2，留档）与 J1436941（`--ntasks=8`，两通道全通过）：ABACUS relax 两例 160.9 / 157.6 s（`omp: 1` 显式 vs manifest 预算 2；`threads_source=harness`、后者无覆盖计数），说明该示例再加线程仅 ≈2% 收益；DP 压力行 8 ranks/1 卡 11.2–13.6 s（串行）vs 16.3–20.5 s（8 rank），**1.2–1.8×**（本地 WSL2 为 7.7×，V100 显存峰值 16.6/32 GB）——修正本地外推；P5 剩余仅 host/SIF 成对与 8 图×8 卡。新增证据切片 `docs/reports/data/ATST_P5_CLOSEOUT_20260921/`；SAI 报告新增 §5d 并更新 §7/§8；计划 P5 清单同步。
- 2026-09-21（**omp 预算修复 + 站点复验**）：按维护者裁定的方案 A 修复联合验收发现的 P2——`AbacusConfig.omp` 由 `Field(default=1)` 改为 `int | None = None`，`normalize_config` 在用户未写该键时省略它，`_effective_omp` 不再把 schema 缺省当成显式（显式 omp 仍优先并记录覆盖；runtime 预算保留；两者都缺省仍写历史 1，改由 `resolve_calculator_omp` 写入）。新增三条回归测试（归一化段保留预算 / 无预算保持 1 / schema 契约含 `gt=0`），`CONFIG_REFERENCE` 的 abacus 表与 runtime 段同步（`5e26789`）。门禁：unit 1100 passed / 2 skipped、integration 23 passed、docs governance 与 wheel clean-install 通过。站点复验：SAI 作业 1436782（同一恒电势单点、`runtime.threads: auto`）确认 `OMP_NUM_THREADS=8`、无 `runtime_threads_overridden` 计数与 gauge、worker stderr 为空，单点 wall 70.1 s → 32.9 s（非受控对照）；分配外设备负例再次被拒；复验证据归档 `docs/reports/data/ATST_CP_RUNTIME_20260921/reverify/`。
- 2026-09-21（**恒电势 × runtime 真机组合验收**）：按维护者授权在 SAI 4V100 执行作业 1435012——`constant_potential` + `compensated_gate` 单点与三点扫描两用例 2/2 通过（wall 421.5 s、0.118 GPU·h，证据 sidecar 完整、清单引用、记录含 `e0abb71` 修订与操作者字段），并附分配外设备负例被拒（`device index 1 is outside the inherited visible set (size 1)`）。用例配置由 fixture 自带的 `validate_forces.py` 参数派生（目标 μ 15.04597065792631 eV、N0 216、初值 217），未自造标定。新增报告 `docs/reports/ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md` 与证据切片 `docs/reports/data/ATST_CP_RUNTIME_20260921/`（19 项：harness 汇总/记录、两例 case 报告与 worker 日志、sidecar、CP 产物、staging 与作业脚本、两个 job 日志）。**副产品 P2 缺陷**：`utils/config_schema.py:1020` 的 `omp: Field(default=1)` 使 `runtime.threads` 对 ABACUS 后端失效（sidecar `runtime_threads_overridden=1`、`runtime_threads_effective=1.0`；本地复现归因），已记入审阅地图 §4 第 3 项，待裁定后修复。
- 2026-09-21（复核方复验 + 成熟度/治理核对）：复核方对第三轮修复复验通过后，维护者做三项独立核对——① 格式与导入卫生按仓内 pin 的 black 23.9.1 / isort 5.12.0 归一（本分支新增模块与测试共 18 文件、5 处未用导入；AST 比对确认除被删导入外无行为变化），并在 `examples/README.md` 补登 `runtime_batch_cases.example.json` 模板（`5346fa9`）；② 路径引用审计：`src/`、`tests/`、`examples/`、`scripts/` 对本机与站点绝对路径零命中，`docs/` 命中只出现在运行记录与归档证据中（与该仓既有 `docs/reports/data/**`、`docs/superpowers/**` 做法一致）；③ 仓级建议（未改代码）：`.pre-commit-config.yaml` 的 isort 缺 `--profile black`、与 black 88 列不一致，故 pre-commit 在本仓无法整体全绿，属仓库级配置缺口。门禁复测：unit 1097 passed / 2 skipped、integration 23 passed、`check_docs_governance.py` 通过、`verify_wheel_api.py --mpi-smoke` 通过。成熟度结论：主体功能与双后端实测证据完整，**仍不按“开发完成/可验收关闭”处理**，开放项见审阅地图 §4。

- 2026-09-20（未发布开发）：CCQN manifest 增加实际方向来源、1-based 反应键/元素和初始结构身份；PRFO 修复半径更新晚一轮及使用更新后 Hessian 评价上一实际步的时序问题。用户语义见 `CONFIG_REFERENCE` 的 CCQN 小节；本地单元测试 875 passed / 2 skipped。集成方 app-tools 的 `2026-09-20-ccqn-chemical-semantics-toolbox-runtime-plan.md` 保存映射消费、Toolbox 分发试验和独立复核；无 PyPI/SIF/平台发布或真实 DFT 验收。

- 2026-09-20（未发布开发）：Sella 增加默认开启、可关闭的轻量 JSONL 事件；区分初始状态、实际优化迭代、直接观测的数值 Hessian 探测及未分类帧。配置与旧产物边界见 `CONFIG_REFERENCE` 的 Sella 小节；本批不升级 SIF/生产环境、不实施挂载，也不开展真实 ABACUS 计算。验证进度由集成方 app-tools 的 `2026-09-20-sella-observability-plan.md` 留存。

- 2026-09-20（未发布开发）：ATST 恒电势候选文档已补齐用户入口、严格 CP schema 语义、固定几何串行扫描产物、`reference_fcp`/`compensated_gate` 边界、固定晶胞 `relax`/`neb` 限制和失败/身份校验语义。`examples/19_constant_potential_Pt/` 是受限验证 fixture，不是生产基准；本条不表示 Paimon/public 工具链、PyPI、SIF 或平台验收完成。`YAML_INPUT_VARIABLES.md` 仍由现有非 calculator 导出器生成，CP calculator 字段由 `CONFIG_REFERENCE` 维护。


- 2026-09-17（发布后记录）：2.2.6 已从 release commit
  `a633f06b9375e3f34dbd87f90f40ec6271b29cd4` 推送并发布。GitHub
  [Tests](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052859)、
  [abacuslite](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206052923)
  和 [Publish](https://github.com/QuantumMisaka/atst-tools/actions/runs/35206151239)
  均成功；PyPI 两个 artifact、上传时间和 hash 见 2.2.6 release notes。官方无缓存
  clean-install、CLI/API、依赖与安装位置核验均通过；SIF/SAI/platform runtime 与真实
  ABACUS/MPI 验收未执行。
- 2026-09-17（发布前记录）：2.2.6 release candidate 的版本元数据、用户边界与导航已切换。
  候选范围：优化器收敛事实持久化（严格三态 `converged` + stage 身份字段，Sella/Relax/AutoNEB
  自写 owner manifest，API synthesized 显式 `converged: null`）、运行期诊断统一英文及机械门禁、
  稳定 API 阶段契约与交接 fixtures。本地全量测试、文档治理与 clean-wheel API 门禁已通过；
  tag、CI、PyPI、SIF/SAI 与真实 ABACUS/MPI 运行时验收尚未执行；不得把本候选描述为已发布。
- 2026-09-17：执行 [workflow convergence handoff plan](../superpowers/plans/2026-09-17-workflow-convergence-handoff-plan.md)（`feature/workflow-convergence`，基于 `origin/main` `cf86790`）：共享 convergence helper（三态记录 + 英文 advisory + root-only 发射）落地；Sella/CCQN/Relax/IRC/NEB/AutoNEB/D2S 的优化器返回值与阶段事实已持久化，Sella/Relax 也自写默认路径 manifest，复合工作流（D2S/AutoNEB）由顶层 workflow 唯一拥有 manifest；API synthesized 阶段显式 `converged: null` 并在 `PYTHON_API_REFERENCE` 记录阶段契约；运行期诊断全英文并有 AST 机械门禁；A4 交接 fixtures（`docs/reports/data/convergence_fixtures_20260917/`）已生成并有契约测试；clean-wheel 门禁验证了安装包中的三态阶段写出。剩余：Paimon 联合消费验收（由其开发者推进）、示例 curated 产物刷新（需要授权的真实 ABACUS/SAI 运行）、A6 下一 patch 发布（`FEATURE_STATUS_MATRIX` 与 release notes 在发布准备时更新），以及真实 MPI/ABACUS 运行时验收。本记录不表示发布或运行时验收完成。
- 2026-09-17：计划归档收口：7 个已在发布/文档/测试中吸收结论的旧计划与 2 个 `docs/developer/plans/` 遗留文件移入 `docs/archive/pending_delete/plans/`；活跃计划目录只保留仍待执行的计划，并要求在账本登记（`check_docs_governance.py` 机械校验）。

- 本轮治理依据是已接受的
  `docs/superpowers/specs/2026-05-28-documentation-governance-design.md`。
- 活跃入口收敛到 `README.md`、`docs/index.md`、用户文档、开发者文档、当前状态
  reports 和 release notes。
- 当前 release 入口为 `docs/releases/RELEASE_NOTES_2.2.6.md`（release candidate，未发布）；
  tag、CI、PyPI 与 SIF/SAI runtime 证据待维护者执行。此前已由 `v2.2.5` / `v2.2.4`
  发布的 release notes 保留为历史版本说明。
- `docs/reports/FEATURE_STATUS_MATRIX.md` 是当前功能支持矩阵，覆盖 NEB/AutoNEB、
  Dimer、Sella、CCQN、D2S+CCQN、Relax、Vibration/TS validation、IRC、MD、
  experimental DMF、artifact manifest、MPI image-level parallelism，并明确 GA 未支持。
- `docs/archive/pending_delete/` 是待删除复核区；本轮只移动和记录，不最终删除。
- 2026-08-09：`endpoint_singlepoint` 语义更新（`auto` 只信任 ATST 标记端点并重算
  未标记/外来结果；`never` 保留用户提供的可读端点结果）已同步至
  `config_schema.py`（重新生成 `YAML_INPUT_VARIABLES.md`）、
  `docs/user/CONFIG_REFERENCE.md`（含 `atst_endpoint_result` 信任标记机制说明）与
  `docs/user/ABACUSLITE_WRAPPER_GUIDE.md`。
- 2026-08-12：2.2.3 阶段性发布（`atst prepare` 反向配置生成 + 轨迹应力保留）。
  新增 `atst prepare` 顶层命令与 `build_config_from_abacus_dir` 稳定 API，文档同步至
  `docs/user/CLI_REFERENCE.md`、`docs/user/USER_GUIDE_CN.md`、
  `docs/user/CONFIG_REFERENCE.md` 与 `docs/reports/FEATURE_STATUS_MATRIX.md`；
  新增 `docs/releases/RELEASE_NOTES_2.2.3.md`。YAML schema 未变，不重新生成
  `YAML_INPUT_VARIABLES.md`。
- 2026-09-05：GitHub 治理与发布门禁已在本地实现 exact tag-to-HEAD 绑定；2.2.3
  仍为已发布稳定版本，当前 main 作为未发布工作，旧 tag 不代表当前 main。
  当前模型家族独立审查作为正常终审；跨家族审查是维护者按需判断的 owner-judged
  advisory evidence，不构成合入、推送或发布门禁。发布、推送、外部设置和跨渠道
  渲染检查仍待维护者执行。
- 2026-09-06（发布前记录）：2.2.4 release candidate 已准备；active version metadata 和导航已切换
  至 2.2.4，补充 portable MPI 缺失依赖诊断与 Serial/DP/image-parallel 安装边界。
  `parallel` extra 已在 2.2.3 存在，本候选不承诺修复任意 MPI ABI 崩溃；exact tag 和
  PyPI 发布确认仍待维护者执行。
- 2026-09-06（发布后结案）：`v2.2.4` 指向
  `eaac64a76215e33588d362a788c138464519a7ba`；GitHub Tests run `33980730827`、
  abacuslite run `33980730831` 和 PyPI publication run `33980788260` 成功。PyPI
  JSON 列出 wheel 与 sdist，渲染页显示四个绝对 GitHub/Gitee 用户指南与示例链接；
  Gitee 渲染按维护者明确指示排除。clean-install、CLI/API 版本和 base 安装无
  `mpi4py` 已完成验证。tag commit 同时登记了 point-KPT parser CI drift 修复。
  PyPI 已上传 README 不可变，仍保留发布前 candidate wording；这是已知 cosmetic
  限制，仓库 README 已更新，不触发新 patch、retag 或 republish。
  [GitHub release](https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.2.4)
  已创建。
- 2026-09-16（发布前记录）：2.2.5 release candidate 的 active version metadata、
  用户边界和导航已切换。候选范围包括 abacuslite 的 PBC-aware SCF 帧身份校验：在
  统一 ASE 原子序、Cartesian Å 和晶胞后接受整数晶格平移，反向选择最新匹配帧；真实
  错结构、错胞、错序、数量/shape/finite、奇异晶胞和 malformed frame 继续
  fail-closed。native relax/md/MD_dump 仍为末帧语义，不新增配置开关。候选同时保留
  Sella、CCQN、Sella IRC 各方向及最终 NEB 的确定性未收敛 advisory 语义：不改变完成
  返回、退出码或 manifest 状态，也不把完成误报为科学收敛。代码回归、snapshot/package
  checks、exact tag、CI、PyPI 以及 SIF/SAI 验证均尚未完成；不得把本候选描述为已发布或
  已完成运行时验收。
- 2026-09-16（发布后记录）：2.2.5 已从 release commit
  `4c966915c6f40984fc85806869f4766ecdd6ffc9` 推送并发布。GitHub [Tests](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311728)、[abacuslite](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058311733) 和 [Publish](https://github.com/QuantumMisaka/atst-tools/actions/runs/35058399930) 均成功；PyPI 两个 artifact、上传时间和 hash 见 2.2.5 release notes。官方无缓存 clean-install、CLI/API、依赖检查及安装位置核验均通过；SIF/SAI/platform runtime 未执行。
- 2026-09-04：新增 GitHub 治理与发布门禁开发者入口，区分本地/CI 机械检查、
  AGENTS/SKILL 等治理契约的按需跨家族人工审阅，以及 GitHub/PyPI/Gitee 管理员和
  发布后责任；外部设置、发布动作和跨渠道渲染检查仍待维护者执行。

## 2. 活跃 User 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/user/USER_GUIDE_CN.md` | guide | 中文项目目标、10 分钟快速开始、后端说明、功能矩阵和参数入口；含未发布恒电势候选边界。 |
| `docs/user/CLI_REFERENCE.md` | reference | `atst` CLI、轻量 post/summary/config/abacus 工具。 |
| `docs/user/PYTHON_API_REFERENCE.md` | reference | 稳定 `atst_tools.api` 十个 root imports（含 `build_config_from_abacus_dir` 的 NEB-only 配置生成边界）、CLI/API/runner 选择、JSON handoff、结果、artifact、MPI 和 backend delegation 边界；2026-09-20 补齐已存在导出的文档，不新增 API 或发行版本。 |
| `docs/user/CONFIG_REFERENCE.md` | reference | 手写 YAML 语义、workflow 行为、calculator 配置说明；恒电势参数、边界、产物和失败语义的规范入口。 |
| `docs/user/YAML_INPUT_VARIABLES.md` | reference | 由 schema 生成的非 calculator YAML 字段总表。 |
| `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` | guide | ABACUS/abacuslite wrapper 边界、MPI/mpi4py 注意事项。 |

## 3. 活跃 Developer 文档

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/developer/DOCS_ARCHITECTURE.md` | guide | 文档目录职责、目标读者、生命周期类型和导航原则。 |
| `docs/developer/DOCUMENTATION_STANDARDS.md` | guide | 元数据、生命周期、reports 分级、更新映射、归档流程和检查命令。 |
| `docs/developer/HANDOVER.md` | guide | workflow、YAML、CLI、backend、example、report、release 变更 checklist。 |
| `docs/developer/EXAMPLE_VALIDATION_OPERATIONS.md` | guide | 示例本地维护检查、SAI/Slurm 执行模式、curated-output 溯源和证据报告生命周期；不作为用户快速上手。 |
| `docs/developer/YAML_INPUT_GOVERNANCE.md` | guide | YAML schema、变量新增、文档导出和测试治理规则。 |
| `docs/developer/PYPI_RELEASE_AUTOMATION.md` | guide | PyPI 发布自动化流程。 |
| `docs/developer/GOVERNANCE_AND_RELEASE_GATES.md` | guide | 本地/CI 机械门禁、按需跨家族治理审阅证据，以及 GitHub/PyPI/Gitee 外部管理员和发布后 checklist。 |

## 4. Reports L1-L4 账本

### L1: 状态入口

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/FEATURE_STATUS_MATRIX.md` | 当前功能支持范围和限制，含未发布恒电势候选状态。 |
| `docs/reports/DOCUMENTATION_STATUS_REPORT.md` | 当前文档治理账本。 |

### L2: 当前证据

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/ATST_RUNTIME_LOCAL_GPU_VALIDATION_2026-09-21.md` | 隔离运行路径在本地真实 GPU（RTX 2070 SUPER + DPA-3.1-3M）的 end-to-end 证据：设备请求/绑定、线程预算、DP 推理计数、宿主采样与 manifest 引用；SAI V100/ABACUS/MPI 仍属 P5。 |
| `docs/reports/ATST_GPU_TUNING_BRANCH_REVIEW_MAP_2026-09-21.md` | GPU 节点调优分支审阅地图（已 fast-forward 合入 `main`）：提交分组、证据索引、开放门与复现命令，含第三轮外部审查/第四轮复验与治理核对的留痕。 |
| `docs/reports/ATST_CP_RUNTIME_JOINT_VALIDATION_2026-09-21.md` | 恒电势 × runtime 真机联合验收（SAI 1435012）：两用例 2/2、分配外设备负例被拒、证据与记录索引；§5/§5.1 记录 ABACUS `omp` 默认值缺陷、修复（`5e26789`）与站点复验（1436782，`OMP_NUM_THREADS=8`）。 |
| `docs/reports/ATST_RUNTIME_SAI_V100_VALIDATION_2026-09-21.md` | P5 现场验收（SAI 4V100）：冒烟三连、DP 矩阵（12/12）与 ABACUS 双示例（4/4）、站点问题与修复、证据清单与后续（host/SIF、多卡、每卡 4 进程）。 |
| `docs/reports/DP_VALIDATION_2.0.0.md` | DP/DPA 示例级 SAI 验证和相关边界证据。 |
| `docs/reports/ATST_P2_CLOSEOUT_2026-09-22.md` | GPU 调优 P2 现场收口（SAI 1444802）与 record 双通道验收（SAI 1444708）：只读模型共享、`ATST_ATTEMPT` 缓存/证据归属、重启回归、MPS 现场事实与通道夹具；证据切片 `docs/reports/data/ATST_P2_CLOSEOUT_20260922/`。 |
| `docs/reports/DPA3_DP_EXAMPLES_VALIDATION_2026-05-28.md` | DPA-3.1 DP examples 全量 config_dp runtime 验证、模型来源和 checksum 证据。 |
| `docs/reports/EXAMPLES_MAIN_BRANCH_COMPARISON_LTS3101_2026-05-19.md` | examples 与 main/LTS 3.10.1 对齐验证证据。 |
| `docs/reports/ISSUE_25_AUTONEB_FMAX_FIX_REPORT_2026-05-22.md` | Issue #25 最终修复、严格验证和 close response 依据。 |
| `docs/reports/CCQN_ABACUSLITE_VALIDATION_2026-05-26.md` | CCQN ABACUSLite smoke 验证证据。 |
| `docs/reports/MPI4PY_ASE_NEB_PARALLEL_ATST_SUMMARY_2026-05-27.md` | MPI image-level NEB/AutoNEB 并行设计、约束和验证总结。 |
| `docs/reports/P0_P1_EXAMPLE_RUNTIME_VALIDATION_2026-05-28.md` | P0/P1 示例 runtime 验证和当前示例扩展证据。 |
| `docs/reports/NEB_IMAGE_PARALLEL_E2E_VALIDATION_2026-05-29.md` | Cy-Pt image-level NEB/AutoNEB SAI 端到端验证、barrier 对比和 nested MPI 证据。 |
| `docs/reports/ZN_SEGMENTED_NEB_RUNTIME_STATUS_2026-05-30.md` | Zn migration 分段 NEB/AutoNEB runtime 状态和唯一运行证据。 |
| `docs/reports/TWO_STAGE_NEB_LTS3101_VALIDATION_2026-06-04.md` | 01/02/13 two-stage NEB 在 ABACUS LTS 3.10.1 和 4V100 上的实算能垒复现、串并行一致性和迭代步数证据。 |
| `docs/reports/DMF_ENVIRONMENT_SMOKE_2026-06-18.md` | DMF cache-local 环境、`cyipopt`/IPOPT、vendored PyDMF NumPy/torch import 和 EMT runtime smoke 证据；不作为 P3 生产验证。 |
| `docs/reports/DMF_P3_VALIDATION_STAGING_2026-06-18.md` | DMF P3 两案例 production-validation staging、候选结构对比脚本、SAI sbatch 入口和剩余 runtime 验证要求；不作为完成证据。 |
| `docs/reports/DMF_P3_RUNTIME_VALIDATION_2026-06-18.md` | DMF P3 两案例 SAI runtime candidate-comparison 证据、Slurm job 525521、ABACUS/DP reference RMSD 对比和剩余 refinement/vibration/IRC 缺口。 |
| `docs/reports/DMF_P4_D2S_RUNTIME_SMOKE_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI runtime smoke 证据、Slurm job 526327、Sella refinement 接通和剩余 vibration/IRC/ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_VIBRATION_VALIDATION_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI focused vibration 验证证据、Slurm job 526601、Sella 后局域一虚频检查和剩余 IRC/ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_IRC_ENDPOINT_VALIDATION_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 SAI descent-IRC endpoint connection 证据、Slurm job 526657、局域反应原子端点 RMSD 检查和剩余 ABACUS 验证缺口。 |
| `docs/reports/DMF_P4_D2S_ABACUS_COMPARISON_2026-06-18.md` | DMF-D2S `rough_method: dmf` 两案例 ABACUS LTS 3.10.1 single-point comparison 证据；记录 job 526738 的初始 H2-Au raw-force failure、job 526921 的 H2-Au ABACUS Sella corrective refinement，以及 job 527093 的 refined constrained-force comparison pass。 |
| `docs/reports/DMF_RISK_REVIEW_2026-06-19.md` | DMF 风险审查和 DP Slurm 复现实证；记录 job 529051 中 wrapped endpoint、H index swap、fixed slab endpoint 三个 H2-Au 风险案例的 600 秒 timeout，以及 PBC+CFBENM schema guard 和 tmax rounded-index 未触发风险。 |

### L3: 当前主题审查

| 文档 | 当前职责 |
| :--- | :--- |
| `docs/reports/IRC_INTEGRATION_REVIEW.md` | Sella IRC 集成定位和受控边界说明。 |
| `docs/reports/NEB_AUTONEB_NATIVE_ASE_BACKEND_REVIEW_2026-05-23.md` | native ASE backend selector 当前边界与默认迁移条件。 |
| `docs/reports/EXAMPLES_REPRODUCTION_RECHECK_AND_ABACUSLITE_AUDIT_2026-05-24.md` | examples 复现复查和 abacuslite fallback 审计。 |
| `docs/reports/FAST_IDPP_ALGORITHM_COMPARISON_AND_FIX_2026-05-25.md` | FastIDPP 修复依据和 D2S 路径生成边界。 |
| `docs/reports/MACE_REACTION_KIT_TO_ATST_TOOLS_TRANSFER_REVIEW_2026-05-27.html` | MACE-Reaction-Kit P0/P1 核心完成状态和未来增强边界。 |
| `docs/reports/DMF_DIRECT_MAXFLUX_RESEARCH_2026-06-17.html` | Direct MaxFlux/PyDMF 算法、周期体系边界和 ATST-Tools 实验性集成可行性研判。 |
| `docs/reports/ATST_TOOLS_NEB_ASE_COMPARISON_REVIEW_2026-05-18.md` | ASE 3.28.0 与 ATST NEB/AutoNEB/Dimer 对齐审查细节。 |
| `docs/reports/ABACUS_STRU_IO_ASE_FORMAT_COMPATIBILITY_2026-06-04.md` | ABACUS STRU read/write 与 `ase-abacus` ASE I/O format 的 API/语义兼容性和功能点覆盖审查。 |
| `docs/reports/UNIT_TEST_MAINTENANCE_2026-06-10.md` | 单元测试维护、legacy NEB script 清理和默认测试边界审查。 |
| `docs/reports/STABLE_PYTHON_API_CLI_COMPATIBILITY_FIX_2026-07-21.md` | Stable Python API 路由下的 `atst run` 日志、异常和 exit 兼容性修复及回归证据。 |

### Spec / Plan / Review 登记

| 文档 | 生命周期 | 当前职责 |
| :--- | :--- | :--- |
| `docs/superpowers/specs/2026-09-21-atst-gpu-node-tuning-p0-review.md` | review | P0 复核（性能前提与 DP 并行 NEB 证据审查）：GPU 调优前提未证实、DP mpi4py 并行 NEB 零证据、原稿作业记录不可达；结论已回写 SPEC §2 与 PLAN P4/P5 验收项。 |
| `docs/superpowers/specs/2026-09-21-atst-runtime-interface-design.md` | spec | P0 接口冻结（接手 GPU 节点调优）：`runtime` schema 与冻结错误消息、CLI/env 优先级、设备解析与过度暴露边界、bootstrap 与嵌入 API 语义、OMP 优先级、证据 sidecar、恒电势共享文件顺序、P0 验收对照表；待相称独立设计审查。 |
| `docs/superpowers/specs/2026-09-20-atst-gpu-node-tuning-design.md` | spec | GPU 节点调优设计（2026-09-21 自发起方迁入）：设备与进程契约、独立 case 与 MPI 并发、分层计量、基准与科学验收、恒电势协调；pin 对照与 Ruling 见 §11。 |
| `docs/superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md` | plan | 执行中（P0–P5 已完成，P6 进行中）：先 atst 后平台的分期计划（P0–P6）；P0–P5 已交付并以本地 + SAI V100 证据闭合（P5 压力/收益矩阵见 SAI 报告 §5h/§5j）；P2 的只读模型共享、重启回归与 MPS 归属已于 2026-09-22 现场收口（见 [P2 收口报告](ATST_P2_CLOSEOUT_2026-09-22.md)）。未闭合项（TF 后端维度与 DP 容器对照为 `condition-blocked`；站点 `mpiexec` 重绑定确认、P6 的独立终审与共享 image 迁移为 `open`）见计划头部「剩余项（2026-09-22）」。 |
| `docs/superpowers/plans/2026-09-17-workflow-convergence-handoff-plan.md` | plan | 执行中：A2/A3/A4 代码与文档已落地（含 Sella/Relax durable record、synthesized unknown 语义、API 阶段契约与交接 fixtures）；剩余 Paimon 联合消费验收、A5/A6 收尾；不引入 Paimon/调度依赖。 |
| `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design.html` | spec | abacuslite 力读取一致性与跨仓维护设计（R1-R8 / D1-D8 / P1-P8），含 CI 基线单一事实源 `ABACUSLITE_SNAPSHOT.md`（R4/P6）与文档账本登记要求（R7/P8）。 |
| `docs/superpowers/specs/2026-08-04-abacuslite-cross-repo-and-force-read-design-review.md` | review | spec 两轮审查结论与 P1-P8 缺口补强记录；全部结论已落入 spec。 |
| `docs/superpowers/plans/2026-08-04-abacuslite-force-read-and-cross-repo-plan.md` | plan | abacuslite 力读取一致性与跨仓维护分阶段实施计划（Task 1-9），含 Task 5 CI 基线单一事实源改造。 |
| `docs/superpowers/specs/2026-09-04-user-distribution-and-mpi-installation-design.html` | spec | 本地实施完成，2.2.4 已发布；GitHub/PyPI 外部验收已登记，Gitee 渲染按授权范围排除：GitHub 规范源 / 维护者手动拉取的 Gitee 同内容只读镜像 / PyPI 分发、跨渠道用户入口、串行与 image-parallel MPI 安装分层，以及 SAI 维护证据边界设计。 |
| `docs/superpowers/specs/2026-09-04-github-governance-and-release-gates-design.html` | spec | 本地实施完成，待 GitHub 设置与发布后外部验收：GitHub 治理、按需跨家族审阅证据、发布前机械门禁和 GitHub/PyPI/Gitee 发布后责任边界。 |

### L4: 历史或已被取代材料

L4 材料不保留在活跃 `docs/reports/`、`docs/developer/plans/` 或
`docs/superpowers/plans/` 中。本轮移动到
`docs/archive/pending_delete/` 的文件见第 6 节。

## 5. 归档目录规则

| 目录 | 当前职责 | 规则 |
| :--- | :--- | :--- |
| `docs/archive/` | 有历史审计价值但不指导当前工作的文档 | 不作为 README 或 `docs/index.md` 的用户/开发者入口。 |
| `docs/archive/pending_delete/` | 已过时但待最终删除确认的文件 | 删除前确认无活跃链接、无唯一验证证据、结论已被吸收。 |

## 6. 本轮待删除复核结果

| 原路径 | 新路径 | 判据 |
| :--- | :--- | :--- |
| `docs/superpowers/plans/2026-07-02-abacuslite-backend-upstream-issue-fixes.md` | `docs/archive/pending_delete/plans/2026-07-02-abacuslite-backend-upstream-issue-fixes.md` | 计划自记 implementation 完成；vendored 补丁身份与上游同步纪律由 `PATCHES.md`、`ABACUSLITE_SNAPSHOT.md` 和 2026-08-04 跨仓计划承载。 |
| `docs/superpowers/plans/2026-07-05-atst-cli-banner.md` | `docs/archive/pending_delete/plans/2026-07-05-atst-cli-banner.md` | `atst banner` 已发布并有 CLI 测试与用户文档覆盖。 |
| `docs/superpowers/plans/2026-07-05-ci-test-development.md` | `docs/archive/pending_delete/plans/2026-07-05-ci-test-development.md` | snapshot-drift checker、abacuslite 工作流和通用 PR 测试工作流已上线；结论由 HANDOVER 与 CI 契约承载。 |
| `docs/superpowers/plans/2026-07-22-abacus-agent-atst-api-adoption.md` | `docs/archive/pending_delete/plans/2026-07-22-abacus-agent-atst-api-adoption.md` | runner 消费已落地：toolbox 通过 `python -m atst_tools.api.runner` 与 JSON handoff 接入。 |
| `docs/superpowers/plans/2026-09-04-user-distribution-and-mpi-installation.md` | `docs/archive/pending_delete/plans/2026-09-04-user-distribution-and-mpi-installation.md` | 执行完成并已发布 2.2.4；结论已吸收到 README、用户指南和 release notes。 |
| `docs/superpowers/plans/2026-09-04-github-governance-and-release-gates.md` | `docs/archive/pending_delete/plans/2026-09-04-github-governance-and-release-gates.md` | 仓库侧治理门禁已实施并被 2.2.4/2.2.5 发布实际使用；剩余管理员设置不在仓库可验证范围。 |
| `docs/superpowers/plans/2026-09-16-abacuslite-periodic-frame-validation-225-release.md` | `docs/archive/pending_delete/plans/2026-09-16-abacuslite-periodic-frame-validation-225-release.md` | 已随 2.2.5 发布完成；证据保存在 release notes 与账本发布记录。 |
| `docs/developer/plans/DMF-integrate-and-test-plan.md` | `docs/archive/pending_delete/plans/DMF-integrate-and-test-plan.md` | DMF 已作为 experimental workflow 与 D2S rough method 落地，当前边界由 FEATURE_STATUS_MATRIX 和 DMF 报告承载。 |
| `docs/developer/plans/Direct-MaxFlux-方法调研.md` | `docs/archive/pending_delete/plans/Direct-MaxFlux-方法调研.md` | 临时问答笔记，已由 DMF research report 和维护文档取代。 |
| `docs/developer/plans/native-ase-backend.md` | `docs/archive/pending_delete/plans/native-ase-backend.md` | 计划主体已落地，后续边界由 native ASE backend review、用户配置文档和测试覆盖。 |
| `docs/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | `docs/archive/pending_delete/reports/PROJECT_REFACTOR_REVIEW_2026-05-15.md` | 仍以旧 refactor 阶段作为当前基线，已落后于 CCQN、并行 NEB、artifact manifest 等当前进展。 |
| `docs/reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md` | `docs/archive/pending_delete/reports/USER_EXPERIENCE_REINFORCEMENT_2026-05-15.md` | 阶段性 UX 任务已由用户文档、CLI reference 和 artifact manifest 实现吸收。 |
| `docs/reports/CY_PT_AUTONEB_MAIN_REPRODUCTION_REVIEW_2026-05-18.md` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_MAIN_REPRODUCTION_REVIEW_2026-05-18.md` | 早期负向复现结论已被后续 Issue #25 修复和严格验证取代。 |
| `docs/reports/CY_PT_AUTONEB_MAIN_ALIGNED_LTS3101_VALIDATION_2026-05-19.md` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_MAIN_ALIGNED_LTS3101_VALIDATION_2026-05-19.md` | 记录未达标的早期 main-aligned run，已被最终 strict validation 取代。 |
| `docs/reports/CY_PT_AUTONEB_FAILURE_ROOT_CAUSE_REVIEW_2026-05-18.html` | `docs/archive/pending_delete/reports/CY_PT_AUTONEB_FAILURE_ROOT_CAUSE_REVIEW_2026-05-18.html` | 根因分析已被最终修复报告吸收，继续活跃保存会与当前可复现结论冲突。 |
| `docs/reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md` | `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_FMAX_REVIEW_2026-05-18.md` | 预修复评估和 validation plan 已被最终修复报告取代。 |
| `docs/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md` | `docs/archive/pending_delete/reports/ISSUE_25_AUTONEB_SAI_VALIDATION_2026-05-18.md` | 早期 SAI validation 含阶段结论，已被最终 Issue #25 fix report 取代。 |
| `docs/reports/ZN_MIGRATION_NEB_ABACUS_VALIDATION_2026-05-26.md` | `docs/archive/pending_delete/reports/ZN_MIGRATION_NEB_ABACUS_VALIDATION_2026-05-26.md` | 初版单路径 Zn validation 状态已落后，后续分段 runtime 证据由 active Zn segmented report 保存。 |
| `docs/reports/EXAMPLES_INITIAL_GUESS_AUDIT_2026-05-26.md` | `docs/archive/pending_delete/reports/EXAMPLES_INITIAL_GUESS_AUDIT_2026-05-26.md` | 初猜审计结论已被 CCQN/Sella perturbed-input 验证、examples tests 和 reference results 吸收。 |
| `docs/reports/UNIT_TEST_COVERAGE_REVIEW_2026-05-25.md` | `docs/archive/pending_delete/reports/UNIT_TEST_COVERAGE_REVIEW_2026-05-25.md` | 覆盖率审查已落后于 P0/P1、MPI parallel 和 DP reference 测试补强，当前状态以测试套件和 feature reports 为准。 |
| `.trae/documents/CCQN-plan.md` | `docs/archive/pending_delete/trae/documents/CCQN-plan.md` | CCQN perturbed-input plan 已由 CCQN validation report、examples/reference results 和 tests 吸收。 |
| `.trae/documents/NEB_para_abacuslite.md` | `docs/archive/pending_delete/trae/documents/NEB_para_abacuslite.md` | 临时合并说明已被统一 NEB parallel plan 和正式 MPI/E2E reports 取代。 |
| `.trae/documents/NEB_parallel_imple.md` | `docs/archive/pending_delete/trae/documents/NEB_parallel_imple.md` | NEB/AutoNEB image-level parallel 实现已落地，后续依据为 MPI summary、E2E validation、用户文档和测试。 |
| `.trae/documents/Zn-NEB.md` and `.trae/specs/plan-zn-neb-calculations/*` | `docs/archive/pending_delete/trae/zn-neb/README.md` | 初版 Zn 单路径计划资料的统一入口，链接 active segmented runtime report。 |
| `.trae/documents/Zn-NEB.md` | `docs/archive/pending_delete/trae/zn-neb/Zn-NEB.md` | 初版 Zn 单路径计划已被分段 Zn runtime report 取代。 |
| `.trae/specs/plan-zn-neb-calculations/checklist.md` | `docs/archive/pending_delete/trae/zn-neb/checklist.md` | 初始 Zn spec checklist 已被分段方案取代，未完成项不再代表当前执行路径。 |
| `.trae/specs/plan-zn-neb-calculations/spec.md` | `docs/archive/pending_delete/trae/zn-neb/spec.md` | 初始 Zn calculation spec 已被分段方案取代。 |
| `.trae/specs/plan-zn-neb-calculations/tasks.md` | `docs/archive/pending_delete/trae/zn-neb/tasks.md` | 初始 Zn task list 已被分段 runtime report 取代。 |

## 7. 后续维护要求

- 每次新增 workflow、calculator backend 或 YAML 变量时，同步更新用户文档、开发者治理文档、示例和测试。
- 每次新增、归档或移动 report 或 spec/plan 时，同步更新本账本；活跃计划必须登记在
  “Spec / Plan / Review 登记”表内；只有核心入口才加入 `docs/index.md`。
- 阶段性审查文档完成任务后，先把结论吸收到长期文档或 release notes，再移出活跃集合。
- `pending_delete/` 中的文件在最终删除前，不得从活跃入口链接。
- 文档治理变更后运行 `python scripts/check_docs_governance.py`，确认活跃 reports
  账本、spec/plan 登记、metadata、active links、pending-delete inventory 和 HTML
  report 基础解析一致。
