# ATST-Tools Runtime 接口冻结设计（GPU 节点调优 P0）

**版本**: 2026-09-21（rev.3，两轮独立审查后定稿）
**日期**: 2026-09-21
**状态**: 草案（P0 交付；首轮审查 block → rev.2 修订 → 复审 approve with required changes → rev.3 闭合 N1–N10；P1 可启动，入口工作项先落 N1 规则）
**责任人**: ATST-Tools maintainers

设计来源：[GPU 节点调优设计](2026-09-20-atst-gpu-node-tuning-design.md)；执行计划：[GPU 节点优化开发与验证计划](../plans/2026-09-20-atst-gpu-node-tuning-plan.md)；审查记录：[P0 复核](2026-09-21-atst-gpu-node-tuning-p0-review.md)与独立设计审查（2026-09-21，findings 已逐条处理，见 §10）。本文冻结 P0 要求的接口语义，不表示代码、真实计算或发布已执行。实现与本文冲突时以本文为准；变更需回写本文并列 Ruling。

## 1. 实施基线与环境身份

- 实施基线（SPEC §11 R1）：`origin/main` = `2cf5b7e6`；验证以 `PYTHONPATH=src` 指向本仓源码为默认契约。
- 环境三元组（SPEC §11 R2）：每条证据记录（解释器路径与版本、`atst_tools.__file__`、dist 版本）。
- 2026-09-21 实测：

| 环境 | Python | atst-tools | 关键依赖 |
| --- | --- | --- | --- |
| `atst-dev` | 3.10.19 | dist 2.2.3，editable 指向 `deepmodeling` checkout（v2.2.4+1），需 `PYTHONPATH=src` 覆盖 | numpy 2.2.6、ase 3.28.0、pydantic 2.12.5、mpi4py 4.1.2、deepmd-kit 3.1.2、jax 0.6.2、torch 2.9.1；abacuslite 未安装（走 vendored） |
| `dpa4-dpmd-v100` | 3.12.13 | 未安装 | deepmd-kit 3.2.0b1.dev62+gac8e4301b、torch 2.11.0+cu126、numpy 2.4.6；无 ase/mpi4py（P5 需专门构成并登记） |
| 站点 ABACUS | — | — | LTS 3.10.1 与匹配 MPI 在 SAI 作业内核验（站点事实运行时查询，不预写） |

## 2. YAML `runtime` 段（唯一拼写）

```yaml
runtime:
  devices: [0]        # 可选：继承可见集合内的 0-based 逻辑序号，或完整 GPU UUID
  binding: inherit    # inherit / round_robin，默认 inherit
  threads: 4          # 可选：正整数
  telemetry:          # 可选：布尔简写或对象
    enabled: false
    interval_s: 1.0
```

| 字段 | 类型 | 默认 | 语义与用户可见描述（冻结，供生成参数表） |
| --- | --- | --- | --- |
| `runtime.devices` | null、int、str 或 list（int/str 混合） | null（inherit） | 设备请求：继承可见集合内的 0-based 逻辑序号或完整 GPU UUID；只决定请求，不扩大可用集合。 |
| `runtime.binding` | `inherit` 或 `round_robin` | `inherit` | 逐 rank 设备绑定策略；`round_robin` 仅限已核验的单节点共同设备池（P1 阶段 fail-closed）。 |
| `runtime.threads` | null 或 ≥1 整数 | null | 进程线程预算；在科学库初始化前生效，冲突优先级见 §6。 |
| `runtime.telemetry` | null、bool 或 `{enabled: bool=false, interval_s: float>0=1.0}` | false | 运行证据 sidecar 与 GPU 宿主采样开关。 |

`runtime` 本身必须是 mapping；未知子键由 strict schema 拒绝（`extra="forbid"`，沿用现有行为）。`true`/`false` 不接受为整数（不得被当作 1/0）——pydantic 默认会把 `devices: true` 收成 1，**实现必须用显式 validator 拒绝**（先例：`utils/config_schema.py:8,207,211` 的 `StrictBool`）；bool 与浮点条目统一复用 `runtime.devices entry '<token>' is not a valid 0-based device index or full GPU UUID`。

`devices` 值语法（YAML / CLI / env 三者一致）：

- 标量与列表元素为非负整数（0-based 逻辑序号）或完整物理 UUID（`GPU-` + 8-4-4-4-12 十六进制）。
- 列表保持顺序；重复元素拒绝；负数与浮点拒绝；`MIG-` 前缀拒绝（首期不支持 MIG 选择）。
- 空列表、CLI 空值、`ATST_VISIBLE_DEVICES=""` 一律视为“显式空请求”并拒绝；字段缺省 / 环境变量未设置 = inherit。
- 逻辑序号相对“继承可见集合”，与原子选择 1-based 规则无关。

校验消息（冻结，英文，`ConfigValidationError`）：

- `runtime must be a mapping`
- `runtime.devices must be a device index, GPU UUID or a list of them`
- `runtime.devices entry '<token>' is not a valid 0-based device index or full GPU UUID`
- `runtime.devices must not contain duplicate entries (<token>)`
- `runtime.devices must not be empty; omit the field to inherit all visible devices`
- `runtime.devices does not support MIG device selection ('<token>'); pass a full physical GPU UUID instead`
- `runtime.threads must be a positive integer`
- `runtime.binding '<mode>' is not one of: inherit, round_robin`
- `runtime.telemetry must be a boolean or a mapping with 'enabled'`
- `runtime.telemetry.enabled must be a boolean`
- `runtime.telemetry.interval_s must be a positive number`

错误类型规则（冻结）：语法/值域问题抛 `ConfigValidationError`；由环境与绑定判定触发的问题（§4 的 `explicit device selection is refused: ...`、§5 的绑定不一致与缺失标记场景）一律抛 `RuntimeBindingError`——`atst config validate` 只报告前者，不因换机器而失败。

## 3. CLI 与环境变量

`atst run` 与 `python -m atst_tools.api.runner` 增加以下可选选项：

- `--devices <spec>`：逗号分隔，语法同 YAML；空值 = 显式空请求（拒绝）。
- `--binding inherit|round_robin`
- `--threads <n>`
- `--telemetry` / `--no-telemetry`，`--telemetry-interval <sec>`

优先级（逐字段独立解析）：CLI > YAML `runtime.*` > `ATST_VISIBLE_DEVICES`（仅 devices）> 缺省。任何层级只决定“请求”，不能扩大可用集合。

环境变量：

| 变量 | 角色 | 语法 |
| --- | --- | --- |
| `ATST_VISIBLE_DEVICES` | 设备请求（同 `--devices`） | 同 `devices` |
| `ATST_ALLOCATION_DEVICES` | **外层提供的可信分配事实**（平台/harness），atst 只消费不生成 | 逗号分隔的 token 列表（UUID 或宿主序号，宿主命名空间），或 `count=<N>` 表示“数量已知、身份未知” |
| `ATST_RUNTIME_BOUND` | 内部绑定标记（由 coordinator 设置，见 §5） | `1`；只表达状态，不构成资源授权 |

其他子命令（`atst prepare`、`atst config validate`、`atst banner` 等）本期不新增 runtime 选项；`atst prepare` 不生成 `runtime` 段。

## 4. 设备解析语义

四层事实分开记录：requested / inherited / allocation / effective。解析在 bootstrap 内、科学库导入之前完成。

- `inherited`：`CUDA_VISIBLE_DEVICES` 的字面集合；未设置 = 整机可见。**已设置且非空 = 调用者已绑定（caller-bound）**。
- `allocation`：`ATST_ALLOCATION_DEVICES`（宿主命名空间）；未提供 = unknown。
- `effective`：最终写入 child 的集合；**恒为 inherited 的子集**（不变量）。

可采性规则（唯一权威表；`devices` 请求的可采性由本表裁决，不再出现在两张互斥表中）：

| allocation | inherited | 请求 | 行为 |
| --- | --- | --- | --- |
| token 列表（身份可验证） | 任意 | 显式 devices | 允许；收窄到 inherited ∩ allocation；越界或 token 不在可信集合内 → 拒绝 |
| 仅 `count=N` 且 `N >= 继承集合规模` | 任意 | 显式 devices | 放行：允许在继承集合内收窄（effective = 解析后的子集）；身份不可验证时记 `unverified`，不猜测宿主编号；可见集合未知且无法枚举时按 token 解析失败拒绝 |
| 仅 `count=N` 且 `N < 继承集合规模` | 任意 | 显式 devices / 共享 / 重绑定 | 拒绝：`explicit device selection is refused: the visible device set exceeds the trusted allocation and device identity is unverified` |
| unknown | caller-bound | 显式 devices（继承集合内收窄） | 允许；记录 `allocation_identity: "unverified"` |
| unknown | caller-bound | 请求出现继承集合之外的 token | 拒绝（fail-closed）：`... is not part of the inherited visible set` |
| unknown | 整机可见（env 未设置） | 显式 devices | 拒绝：`explicit device selection is refused: the visible device set is not caller-bound and the trusted allocation is unknown` |
| unknown | 任意 | inherit（无 devices） | 放行，原样沿用启动环境；记录 `allocation_identity: "unverified"` 或已知状态 |

- UUID token 采 fail-closed：必须能在 inherited 字面串或枚举结果中定位，否则拒绝（不得按字面透传给 child 导致零可见设备或静默落 CPU）。
- 序号越界消息：`device index <i> is outside the inherited visible set (size <n>)`。
- 表中由环境/绑定判定触发的“拒绝”行一律抛 `RuntimeBindingError`（YAML 语法问题才抛 `ConfigValidationError`）。
- **一致性校验基准（冻结）**：入口层在绑定前把继承集合与最终集合经 `ATST_INHERITED_DEVICES`、`ATST_EFFECTIVE_DEVICES` 传给 worker；校验式为“requested 在 inherited 基准上的解析结果 == effective == child 实际掩码”，**不得在收窄后的掩码上重新求序号**（否则恒真，无法发现绑错卡）。
- `binding: round_robin` 在 P1 为 **fail-closed**：`world.size <= 1`、无已核验单节点共同池、或 local rank 不可判定时抛 `RuntimeBindingError`（不静默按 inherit 执行）。local rank 来源冻结为 `OMPI_COMM_WORLD_LOCAL_RANK`、`SLURM_LOCALID`、`PMIX_LOCAL_RANK`（P4 可扩展）；轮转为 `local_rank % effective_count`。
- `round_robin` 的设备池 = 请求解析后的 effective 集合（`devices` 选池、逐 rank 在池内轮转）；**inherit 请求同样先与可信 allocation 求交**（空交集，或 `count < 可见集合` 且身份不可验证时拒绝），池为空或非 caller-bound 时拒绝。
- 无 GPU/无采样工具：显式 GPU 请求按执行错误失败；计量降级不冒充成功。

## 5. 进程、入口与嵌入 API（冻结进程模型分流）

**模式分流（SPEC §11 R6）**。触发口径（冻结）：**YAML `runtime` 段、任一 CLI runtime 选项、或 `ATST_VISIBLE_DEVICES` 三者任一出现**即视为“请求 runtime”（并写出证据 sidecar）；三者皆无 = 未请求。

1. **未请求 runtime**：`atst run` 保持现状进程内路径（`run_workflow_from_cli` 语义），不合成 manifest、不写 `atst_api_result.json`、退出码不变——旧调用逐字节兼容。
2. **请求 runtime**：进入隔离模式。轻量 coordinator 构造 child（CUDA mask、线程、cwd、缓存目录、`ATST_RUNTIME_BOUND=1`）→ 以 exec 进入唯一 worker（复用 `python -m atst_tools.api.runner` 协议与原子结果写）；**MPI 必须在 exec 之后由最终 worker 初始化**——在 `MPI_Init` 后 exec 会使 OpenMPI 丢失 PMIx 会话而挂起。一个工作流一个新解释器，不为每次力调用创建进程。

**内部标记 `ATST_RUNTIME_BOUND` 语义（冻结）**：只表达“本进程已由 atst 入口层完成绑定”，不构成资源授权。**最终工作进程必带该标记**；`atst run` 的 coordinator 与 **runner 直接入口**都必须在完成绑定后以 re-exec 方式让工作进程携带它（runner 自身不因 `--devices` 报“嵌入 API”错误）。标记存在时，worker 内 `run_workflow` 对 `runtime.*` 做**一致性校验**（按 §4 的基准；不符 → `RuntimeBindingError`），不再拒绝设备请求；标记不存在时（Python 嵌入或进程内调用），`runtime.devices`、`runtime.threads`、`runtime.binding: round_robin` 一律抛 `RuntimeBindingError`（`embedding API cannot rebind devices; run the workflow through 'atst run' or 'python -m atst_tools.api.runner' instead`）。

**入口与导入契约（P1 必须实现，且受测试固定）**：

- console script 维持单一 `atst`（`tests/unit/test_cli.py` 固定）；`scripts/cli.py` **顶层不得导入任何重依赖**（NumPy、ASE、matplotlib、`atst_tools.api`、`from atst_tools.scripts import main`、`utils.*` 中的重模块等；仅允许轻量模块，如 launcher 探测 `utils/mpi`），全部推迟到命令处理内，使 runtime 解析可先于科学库导入。
- `api/runner.py` 把 `from atst_tools.api import ...` 推迟到 runtime 解析之后（`main()` 内）。
- 新增轻量解析模块（建议 `atst_tools/runtime/`），包导入期不得引入 NumPy/ASE/DP/ABACUS/JAX；以 import smoke 测试固定。
- `mpi4py` bootstrap 允许先于设备绑定（MPI 初始化 ≠ CUDA 初始化）；CUDA/DP/ABACUS/JAX 初始化必须晚于绑定。

**缓存目录（冻结契约）**：每 attempt 一个可写目录 `<workflow_dir>/.atst_cache/attempt-<N>/`（2026-09-22 命名精度修正为实现的目录名；`<N>` 为下条 attempt 编号）；child 环境设 `JAX_COMPILATION_CACHE_DIR`、`NUMBA_CACHE_DIR`、`MPLCONFIGDIR` 指向其内。P1 可追加更多缓存键，但“每 attempt 独立可写目录”不变。

**attempt 编号**：取自 `ATST_ATTEMPT`（正整数，缺省/非法回退 1），用于缓存目录与证据归属；`build_child_environment` 必须把解析出的 attempt 一并发布到 child 环境（2026-09-22 修复：此前只派生缓存目录而未下传该变量；库调用者传入精选 `base` 时证据/结果文档会回落为 1）。

**worker 参数**：隔离模式下 coordinator 不把 runtime 选项回传给 worker（`--devices` 等由 coordinator 消费）；worker 的权威事实是 `ATST_RUNTIME_BOUND` + `ATST_INHERITED_DEVICES`/`ATST_EFFECTIVE_DEVICES`，一致性校验按 §4 基准执行。

**失败与取消**：worker 进程组有界终止，回收采样进程与槽位；MPI 初始化前死亡由 launcher/coordinator 的退出与超时处理。

**错误类型（冻结）**：`RuntimeBindingError(ATSTAPIError)`，加入 `atst_tools.api.__all__`（需同步更新 `tests/unit/test_api.py` 的等值断言；属纯增量 API 变化）。

## 6. 线程与 OMP 优先级（SPEC §11 R3）

| `calculator.*.omp` | `runtime.threads` | 生效 | 记录 |
| --- | --- | --- | --- |
| 显式 | 缺省 | calculator 值（现状） | — |
| 显式 | 显式且不同 | calculator 值 | fact `runtime_threads_overridden`（记录两值） |
| **缺省** | **显式** | **runtime 值**（导入前写入；工厂/驱动的隐式默认不得覆盖） | — |
| 缺省 | 缺省 | 不写 OMP，保持现状 | — |

进程级键：`OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`MKL_NUM_THREADS`、`NUMEXPR_NUM_THREADS` 取同一值。

实现细化（rev.5，独立审查 F7/F8 后）：显式 `omp` 覆盖继承预算时写 `runtime_threads_overridden` 计数 + `runtime_threads_effective` gauge 并输出英文 warning；**legacy 路径（无 runtime 请求）仍写旧默认 `1`**，只有 runtime 请求的 worker（`ATST_THREADS_SOURCE` 存在）才保留继承预算，避免改变无新键的旧调用行为。

**实现细化（rev.6，2026-09-21 P5 收尾裁定）**：批量 harness 的 per-case `threads` 属调用者显式预算——`bench/batch_runner.py::case_environment` 现在同时写 `ATST_THREADS_SOURCE=harness`，于是 manifest 给出的线程数会真正到达 ABACUS（此前缺该标记时，未显式写 `omp` 且无 `runtime` 段的用例会落到 legacy 1；P5 的 ABACUS 计时为单线程则是因示例配置显式写了 `omp: 1`——两条路径都由 sidecar 的 `threads_source` 与覆盖计数区分）。带 `runtime.threads` 的用例仍由 worker 覆盖该标记为 `explicit`/`auto`。**注意**：该改动改变了与 P5 既有 ABACUS 数字的可比性，修复后基线必须重测并在报告中标明（见 SAI 报告 §5b）。

现有 `OMP_NUM_THREADS` 写入点（完整清单）：`calculators/dp.py:92-94`、`calculators/factory.py:165`、`workflows/md.py:278`（另有 `utils/abacus_io.py:232` 仅用于 `--check-input` 子进程）。其中 `factory.py:159-165` 与 `md.py:278` 会把**缺省** omp 隐式写成 `1`，与上行第三行冲突——**P1 必须修改**：仅当 `calculator.*.omp` 为用户显式给出时才写 `omp` 值；缺省不得写（不得以“隐式默认 + fact 记录”的方式保留覆盖），保证 `runtime.threads` 不被静默覆盖。

## 7. Fixture 与运行证据

### 7.1 Fixture 候选（P5 定稿）

- DP 通用回归：`examples/dp_model_manifest.json` 的 `DPA-3.1-3M`（head `Omat24`，sha256 `86dd3a80…`）；本 checkout 无本地权重，P5 前经 `scripts/download_dp_model.py` 下载并按 `tests/unit/test_dp_model_manifest.py` 固定 url/sha256/size 校验。
- DP 科研候选（只读）：FT²DP 单头 100k。本机副本 `scratch_atp_upload/model.ckpt-100000.pt`（sha256 `13b74797…` 已实测一致）；SAI 钉版路径（pin 文档）为 `$R/models/ft2dp-v2.2/DPA4-Air-ZBL-FT2DPv2.2-single100k-v20260919/checkpoints/`。该模型为 DPA4/SeZM 类：`deepmd-kit 3.1.2` 加载报 `Unknown model type: dpa4`，需 3.2.0 级构建（本地 3.2.0b1.dev62/dev67 加载且单点一致，ΔE 7.6e-06 eV；SeZM 内建近邻表需可见 `libcuda.so`）。EMA `45667e7f…`（20 MB）本机无文件（2026-09-21 复核：本机仅有 `model/ft2dp-v2.2/FT2DPv2.2-dpa4-air-zbl-multi200k-v20260920/` 的 regular+EMA 包），且该 SAI 路径在 `galileouser02` 下不可读——EMA 需科研侧提供后复核，或改用 multi200k 包（待维护者裁决）；pin 记分卡记 EMA ≈ regular。使用前回读模型 manifest 核验 head/type map/单位/精度/格式；不得当作恒电势模型使用。
- 历史接入记录（atst 2.1.1 + deepmd `3.2.1.dev0+g687b5107`）来源：`ft2dp-dpeva/docs/superpowers/plans/2026-09-19-ft2dp-v2.2-model-validation.md:78`（未独立复核）。
- ABACUS 候选（按规模）：`examples/01_neb_Li-Si`、`02_neb_H2-Au`、`03_autoneb_Cy-Pt`、`08_d2s_Cy-Pt`、`06_relax_H2-Au`；原子数与输入身份在 P5 基线实测登记。
- 原稿作业证据待补：DP `1422694/1422849/1423160`、ABACUS `1423179` 的日志/输入/卡时（SAI 侧 `sacct`，本机不可达）；复核结论见 [P0 复核](2026-09-21-atst-gpu-node-tuning-p0-review.md)。

### 7.2 运行证据 sidecar（冻结）

- 触发：任一 runtime 维度出现请求（`runtime` 段、CLI runtime 选项或 `ATST_VISIBLE_DEVICES`）或 `telemetry.enabled=true` 时写出；缺省调用不新增文件、结果文档逐字节不变。
- 产物：同目录 `runtime_evidence.json`；manifest metadata 键 `runtime_evidence`（相对路径）；`atst-api-result-v1` 增加可选 `runtime` 摘要对象（只增字段）。
- 字段分层按 SPEC §6：workflow/stage、rank/worker、GPU device、process（可得）、allocation/batch。状态 `disabled | unavailable | partial | observed` 加 `reason/source`；缺失 = null，不填 0；显存峰值标记 `sampled_peak`（实现：`telemetry.sampler.memory_peak_mib = {value, source}`；有样本时 `source="sampled_peak"`，无样本时二者均为 null）。
- 采样所有权：**每 job 仅 local rank 0 启动一个宿主采样器**（其余 rank 不复制），默认关闭；`nvidia-smi` 缺失或权限不足时状态 `unavailable`。
- 实现状态（P2 首片，2026-09-21）：sidecar（schema `atst-runtime-evidence-v1`）、manifest 引用、环境/设备事实与宿主采样（rank 0 单例、默认关闭）已实现；计量写失败只写 stderr 警告、**不阻断科学运行**。P2 后续片均已交付：结果 envelope 可选 `runtime` 摘要（legacy 无此键）、阶段耗时 `phases`、力调用/模型构建计数（`counters`/`counters_mpi`）与显存采样峰值 `memory_peak_mib`。

结果 envelope 摘要（已实现）：请求过 runtime 的运行在 `atst-api-result-v1` 顶层增加可选 `runtime` 对象（`status`、`evidence` 相对路径、`attempt`、`devices` 事实）；未请求 runtime 的运行不产生该键（逐字节兼容）。`--dry-run` 与 runtime 选项组合按同一触发规则进入隔离路径并在 worker 内校验（`--dry-run` 转发给 worker）：隔离 dry-run 的结果文档带 `runtime` 摘要（`status="dry-run"`、`evidence=null`）但不写 sidecar（没有实际计算），legacy dry-run 仍然不写任何文件；"argparse 未识别 `--devices`"空洞已消除。

阶段耗时（首版粒度，已实现）：sidecar `phases` 记录 `dispatch_s`（科学 dispatch 墙钟）与 `attempt_s`（worker 起至完成的总墙钟）；更细的逐 workflow-stage 计时仍列为 P2 后续项，届时复用同一 `phases` 容器。

第二轮独立复核修复（2026-09-21，bench/services 聚焦）：① harness 在任何退出路径（取消/异常/中断）都终止存活 worker 进程组，sweep 也接入 SIGINT/SIGTERM 信号并传播停止；② harness/sweep 汇总在**运行开始**记录 atst 修订（`revision`），record 文档区分 `atst.record_time` 与 `atst.run_time`（含一致性标志），不再把"建记录时"的 git 状态冒充"测量时"；③ record 对结果目录做全树哈希（`tree_sha256`/`file_count`）并把缺失输入列为 `warnings`（CLI 以非零码提示）；④ legacy CLI 成功路径与 API 路径同样写出 `counters_mpi`/`phases`；⑤ `runtime` 摘要仅由拥有证据文件的 rank 0 附带；⑥ sweep 统计对零墙钟行健壮并回传 harness 生效的 CPU 预算；⑦ worker 一致性校验以 coordinator 记录的**合并后请求**为准（CLI 优先于 YAML），不再误拒合法组合；⑧ launcher 的 rank 数（声明或从 `-n` 解析）计入 CPU 线程预算；⑨ sweep 默认不产 per-case sidecar（`--case-telemetry` 显式开启），避免采样噪声污染计时。

MPI 计数汇总（P2 收口片）：除 rank 0 的进程级 `counters`/`gauges`（`counters_scope=process`）外，成功路径在失败同步 collective 之后对**全部 rank** 求和 canonical 计数，写入 `counters_mpi`（`scope=sum-over-ranks`、`world_size`、`counters`、`gauges`）；失败路径无此集体操作，只保留 rank 0 的进程级值（诚实降级）。

冻结消息一致性收口（2026-09-21，机械审计）：逐条比对本文 §2/§4 的冻结消息与实现，发现并修正 5 处偏差——① `runtime must be a mapping` 未实现（pydantic 原始消息）；② `runtime.telemetry.enabled must be a boolean` 与 ③ `runtime.telemetry.interval_s must be a positive number` 走 pydantic 原始消息且 union 泄漏额外 `runtime.telemetry.bool` 行；④ 非字符串设备 token 的 entry 消息缺引号（`entry 1.5` → `entry '1.5'`）；⑤ CLI `--telemetry-interval <非数字>` 泄漏 `could not convert string to float`。现全部按本文输出，并有契约测试锁住（`tests/unit/test_runtime_schema.py::test_runtime_section_uses_the_frozen_interface_messages`、`tests/unit/test_runtime_launch.py::test_telemetry_interval_uses_the_frozen_message_for_bad_values`）。

### 7.3 第三轮复核（外部审查 2026-09-21）修复记录

外部审查对 `f03b3e6` 提出 8 项（P1×4、P2×4）；逐条复现、修复并补回归：

1. **round_robin 绕过 allocation（P1）**：inherit + `round_robin` 现先与可信 allocation 求交（空交集或 `count < 可见集合` 即拒绝），与显式请求共用同一套可采性规则（§4）。
2. **runner 在 MPI 初始化后 re-exec（P1）**：`_process_rank()`（导入 mpi4py）推迟到重绑定 exec 之后；SAI 的 OpenMPI 挂起根因即此顺序，已修复。回归：入口顺序单测 + 真实 MPI 冒烟 `test_runner_direct_entry_completes_under_real_mpi`。
3. **进程组清理遗留子进程（P1）**：`_terminate_group` 先固化 pgid，宽限后对整组 SIGKILL 并确认组已空；新增“忽略 SIGTERM 的子进程”回归。
4. **默认 workdir 未隔离（P1）**：manifest 校验按“实际运行目录”（显式 workdir 或配置所在目录）判重，同目录多 case 直接拒绝。
5. **两种合法参数组合在 worker 失败（P2）**：`threads: auto` 视为请求而非按整数解析；worker 优先采用协调者记录的 `ATST_BINDING`（CLI 覆盖 YAML）。
6. **`--case-telemetry` 未透传（P2）**：harness 现在把 `case_telemetry` 传入子进程环境构造，关闭时不再注入 `ATST_TELEMETRY_ENABLED`。
7. **“卡时”语义（P2）**：`gpu_seconds` 明确为 per-case 设备秒；新增 `allocation.{devices,wall_s,gpu_seconds}`（分配卡数 × 批次墙钟），sweep 汇总同步聚合。
8. **证据切片未被 Git 跟踪（P2）**：`.gitignore` 增加归档例外并补提交 JSON（records/汇总/sidecar）。

验证：`tests/unit` 1099 passed / 2 skipped、`ATST_RUN_MPI_TESTS=1 tests/integration` 23 passed（新增 1 项）；并在 SAI 复验：此前挂起的 `mpiexec -n 4 + round_robin` 四卡用例（1434302）22 s 完成，`world_size=4`、`bound=true`。

## 8. 与恒电势在途工作的共享文件协调（SPEC §11 R4）

现状（2026-09-21 更新）：`sidereus/.worktrees/constant-potential-plan-review` 的 atst 子模块位于本地分支 `feature/constant-potential-integration`；其 29 个在途文件已经维护者指示提交为 **checkpoint `7bc3f92`**（提交时验证：CP 相关单测 105 passed、`check_docs_governance.py` 通过；工作树已 clean）。该 checkpoint 是安全存档，不等于已审查/已合入 main——合入 main 仍由恒电势 owner 决定。共享文件（GPU 侧 P1–P2 要碰的）：`utils/config_schema.py`（+304）、`api/services.py`、`calculators/factory.py`、`scripts/main.py`、`utils/neb_endpoints.py`、`utils/abacus_io.py`，以及用户文档 `docs/user/PYTHON_API_REFERENCE.md`、`docs/user/CONFIG_REFERENCE.md`、`docs/user/CLI_REFERENCE.md`、`docs/user/USER_GUIDE_CN.md`、`docs/index.md`、`examples/README.md`、`README.md`、`docs/reports/FEATURE_STATUS_MATRIX.md`、`docs/reports/DOCUMENTATION_STATUS_REPORT.md`。

GPU 侧在本清单之外新增/触及的文件：`src/atst_tools/runtime/*`（新）、`src/atst_tools/bench/*` 与 `examples/runtime_batch_cases.example.json`（P3 参考 harness，新增、无重叠）、`scripts/cli.py`（轻入口壳）+ `src/atst_tools/scripts/cli_impl.py`（旧实现迁入）、`api/runner.py`（lazy import + 选项）、`utils/config_docs.py` 与 `docs/user/YAML_INPUT_VARIABLES.md`（`runtime` 进入生成参数表：已实现）、`workflows/md.py`（OMP 写入点，见 §6）。

建议顺序：

1. 恒电势分支先提交其变更（当前完全未提交，存在丢失风险）；
2. GPU 侧先落地无重叠的新模块（runtime 解析/绑定/证据）、`scripts/cli.py` 与 `api/runner.py` 的入口推迟，以及本文档；
3. 恒电势合入后 GPU rebase，串行修改 `utils/config_schema.py`（新增 `runtime` 段）→ `scripts/main.py`（CLI 选项）→ `api/services.py`（plumbing）→ `calculators/factory.py`（绑定适配与 §6 的隐式默认修正）；
4. 文档最后合并，显式包含 `PYTHON_API_REFERENCE.md`、`CONFIG_REFERENCE.md`、`CLI_REFERENCE.md`、`USER_GUIDE_CN.md`、`docs/index.md`、`examples/README.md`、`YAML_INPUT_VARIABLES.md`、`FEATURE_STATUS_MATRIX.md` 与账本；注意 `tests/unit/test_docs_governance.py` 对用户入口文档（`README.md`、`docs/index.md`、`examples/README.md`）设有禁用词表（`job/jobs/partition/qos/server/sai/test/pytest/ci` 等），合并文案需过门禁。

字段归属：恒电势拥有 `calculation.type: constant_potential` 与 `calculator.constant_potential`；GPU 拥有 `runtime`；两者都只增可选字段，联合验收至少包含一条“同时启用仍严格校验”的测试（SPEC §7A）。`utils/abacus_io.py` 被恒电势分支占用（CP 语义校验），GPU 侧当前无重叠改动，合并时按恒电势版本为准。

### 8.1 合并预演（2026-09-21，只读）

用 `git merge-tree --write-tree` 对 `feature/gpu-node-tuning`（26 提交）与恒电势 checkpoint `7bc3f92`（1 提交）做预演：**无冲突**，合并树可提交（`6bd6487`，临时对象），且在合并树上运行 `tests/unit` 只有两项失败，均已确认在恒电势分支**单独**同样失败（与 GPU 侧无关）：

1. `test_examples_reference_results.py::test_reference_results_cover_current_examples` —— `examples/19_constant_potential_Pt/` 缺 `examples/reference_results.json` 条目；
2. `test_abacuslite_snapshot_ci.py::test_snapshot_checker_normalizes_registered_core_and_keeps_comment_churn` —— vendored `abacuslite/core.py` 的 CP 补丁使该归一化测试的前提失效，需随快照一起更新测试或注册。

这两项是**恒电势分支合入 main 的前置门禁**（其 owner 处理）；其工作树当时另有 8 个未提交文件，可能已含修复，以 owner 提交为准。预演工作树已清理；本仓保留只读引用 `rehearsal-cp` 便于复演。

### 8.2 复核（2026-09-21，GPU 侧 38 提交）

以当前端点复演（`feature/gpu-node-tuning` = `eaa7e22`，38 提交；CP checkpoint = `7bc3f92`）：`git merge-tree --write-tree` 仍**无冲突**（合并树 `bfa6e5c4`，临时提交 `7e976d5`，预演工作树事后已清理）。在合并树上运行共享面聚焦测试五个文件（`test_examples_reference_results`、`test_abacuslite_snapshot_ci`、`test_config`、`test_runtime_schema`、`test_constant_potential`，共 141 项）：仅 §8.1 记录的两项 CP 侧前置门禁失败，其余全部通过——GPU 的 `runtime` 字段与恒电势字段在同一棵树上互不破坏。

与 R4 的差异：GPU 侧共享改动（`utils/config_schema.py`、`api/services.py`、`calculators/factory.py`）已在本分支提前预置（未推送、未合入 main），上述预演证明与恒电势改动无文本冲突。合入 main 的次序仍按 §8：恒电势先合入，GPU 随其后，文档最后合并。

后续：CP 工作树在 checkpoint 之后另有 8 个在途改动（截至 2026-09-21 02:07：constant-potential restart 事实、IDPP、`workflows/relax.py`、`scripts/main.py` 与 CLI/CONFIG 文档），属恒电势 owner 在途工作，未进入本次预演；owner 提交后需再复演一次。两项前置门禁仍待恒电势 owner 处理。

### 8.3 恒电势合入 main 与 GPU rebase（2026-09-21）

恒电势开发者已完成合入：atst 侧 `main` = `7bc3f92` + `d30747b`（"fix(constant-potential): complete checkpoint recovery and constrained path validation"，工作树 clean；尚未推送远端），app-tools 父仓分支另有 `375ef7c6b`/`7e3009e32` 两个集成记录提交。§8.1 的两项前置门禁**均已由恒电势侧修复**：`examples/reference_results.json` 已含 `19_constant_potential_Pt` 条目；`tests/unit/test_abacuslite_snapshot_ci.py` 在 main 上通过（main 全量单测 943 项、0 失败）。

GPU 侧按其重放：`feature/gpu-node-tuning` 已 rebase 到 `main`（61 提交全部重放、**零冲突**），并在其上新增 SPEC §7A 要求的联合验收测试 `tests/unit/test_joint_runtime_constant_potential.py`（`reference_fcp` 与 `compensated_gate` 两条路径 × runtime 段；两方向的失败仍 fail-closed：空设备表/采样间隔/未知键与 `work_ref_source`/未知字段各自保留冻结消息）。合体树门禁：单测 1091 项 0 失败、真实 MPI 集成 22 项通过、wheel clean-install 公开 API 门通过。共享文件（`config_schema.py`/`services.py`/`factory.py`/用户文档）现按"恒电势先、GPU 后"的顺序落在 main 之上。

## 9. P0 验收对照表

| 场景 | 期望行为 |
| --- | --- |
| `CUDA_VISIBLE_DEVICES=2,3` + `runtime.devices: [0]` | effective = 继承集合第 0 个（宿主 2）；证据记录 inherited=[2,3]、requested=[0]、effective=<uuid 或 2>、allocation unverified |
| `CUDA_VISIBLE_DEVICES=2,3` + `devices: []` | `ConfigValidationError`：`runtime.devices must not be empty; omit the field to inherit all visible devices` |
| `CUDA_VISIBLE_DEVICES=2,3` + `devices: [2]` | `device index 2 is outside the inherited visible set (size 2)` |
| `CUDA_VISIBLE_DEVICES` 未设置（整机可见）+ `devices: [0]` | 拒绝：`explicit device selection is refused: the visible device set is not caller-bound and the trusted allocation is unknown` |
| `ATST_ALLOCATION_DEVICES=count=1` + visible 0,1,2,3 + `devices: [0]` | 拒绝：`... the visible device set exceeds the trusted allocation and device identity is unverified` |
| `ATST_ALLOCATION_DEVICES=<uuid>` 且与 visible 一致 + `devices: [<uuid>]` | 允许（收窄到 allocation ∩ inherited） |
| `CUDA_VISIBLE_DEVICES` 未设置 + 请求不存在/越界 UUID | 拒绝（fail-closed；不得字面透传） |
| `MIG-…` UUID 请求 | `runtime.devices does not support MIG device selection ('<token>'); ...` |
| `binding: round_robin` 且 `world.size == 1` 或无已核验共同池 | `RuntimeBindingError`（不静默按 inherit 执行） |
| 已初始化进程内 API + `runtime.devices` / `runtime.threads` / `binding: round_robin` | `RuntimeBindingError` 指向隔离入口；父进程 env/cwd 不变 |
| worker 内 `ATST_RUNTIME_BOUND=1` 且 `runtime.*` 与环境一致 | 正常执行（一致性校验通过，不抛错） |
| worker 内 `ATST_RUNTIME_BOUND=1` 但 `runtime.devices` 与环境不符 | `RuntimeBindingError` |
| `devices: [1,1]` | `runtime.devices must not contain duplicate entries (1)` |
| `ATST_VISIBLE_DEVICES=""` | 显式空请求错误；未设置 = inherit |
| `ATST_VISIBLE_DEVICES=1 atst run config.yaml`（仅 env 请求） | 进入隔离模式；requested=[1]；写出 sidecar；不得静默忽略 |
| `python -m atst_tools.api.runner --devices 1`（未绑定进程的直接入口） | 入口层绑定后 re-exec，最终 worker 携带 `ATST_RUNTIME_BOUND=1` 并成功执行；证据含 requested/effective |
| runner 直接入口 + 不可采请求（越界、整机可见且无 allocation、count<N 等） | `RuntimeBindingError` |
| `ATST_ALLOCATION_DEVICES=count=4` + visible 0–3 + `devices: [0]` | 放行（`N >= 规模`），effective = inherited |
| `ATST_ALLOCATION_DEVICES=count=1` + visible 0–3 + `devices: [0]` | 拒绝（`N < 规模` 且身份不可验证） |
| 不含 runtime 的既有 `atst run` | 进程内 legacy 路径；不新增 `atst_api_result.json`、不合成 manifest、退出码不变 |

表中所有“拒绝”凡由环境/绑定判定（非 YAML 语法）触发，一律抛 `RuntimeBindingError`；YAML 语法/值域错误抛 `ConfigValidationError`。

## 10. 审查处理与剩余未决

独立设计审查（2026-09-21）第一轮结论 block，第二轮复审结论 **approve with required changes**；本版（rev.3）处理清单：

| 审查项 | 处理 |
| --- | --- |
| B1 worker 与嵌入 API 冲突 | §5 冻结 `ATST_RUNTIME_BOUND` 语义与一致性校验 |
| B2 进程模型破坏旧调用 | §5 冻结模式分流（legacy 默认路径 / runtime 隔离模式），SPEC §11 R6 |
| B3 过度暴露两表互斥、allocation 命名空间未定义 | §4 单一权威表 + `ATST_ALLOCATION_DEVICES` 锚点与 `count=N`，SPEC §11 R5 |
| M1 runner/CLI 生效时机与入口 | §5 入口与导入契约（lazy import、`atst_tools/runtime/` 轻量模块） |
| M2 隐式 omp 覆盖 runtime.threads | §6 修订 + 写入点全清单 + P1 必改项 |
| M3 错误分类学 | §5 `RuntimeBindingError(ATSTAPIError)` 与公开面 |
| M4 UUID 字面透传 | §4 fail-closed |
| M5 §8 文件清单不完整 | §8 扩展清单 |
| M6 `runtime` 未进生成参数表 | §8 冻结“进入”+ `config_docs.py`/治理测试/description 文案 |
| M7 `round_robin` 静默降级 | §4 P1 fail-closed + local rank 来源 |
| m1–m8 | §2 消息补齐、§5 缓存契约与错误类型、§7.2 采样所有权与 sidecar 冻结、§8 文档门禁提示、§9 场景补齐、命名修正（`atst config validate`） |
| 复审 N1–N10 | N1 runner 直接入口的绑定/re-exec 规则、N2 env 通道纳入模式与 sidecar trigger、N3 一致性校验基准（`ATST_INHERITED_DEVICES`/`ATST_EFFECTIVE_DEVICES`）、N4 隐式 omp 二选一措辞、N5 count-only allocation 边界、N6 bool 显式 validator、N7 重依赖清单、N8 复核文档行号、N9 错误类型指派、N10 SPEC §4.1 指向 R5——已全部闭合 |
| 实现期细化（rev.4，2026-09-21 P1） | ① count-only allocation 覆盖可见集合时按“集合内收窄”实现（rev.3 的“effective = inherited”措辞作废，用户请求不被忽略）；② `round_robin` 的池 = 解析后的 effective 集合；③ attempt 编号来源 `ATST_ATTEMPT`（缺省 1）；④ worker 不接收 runtime 选项回传，marker + facts 为权威；⑤ 轻入口经 `api` PEP 562 惰性导出与 `cli.py`/`cli_impl.py` 拆分实现，import smoke 已固定该事实；⑥ OMP 优先级经 `_effective_omp` 落地：显式 `calculator.abacus.omp` 胜出，否则保留继承预算，缺省写 1（保持旧行为）。 |

剩余未决（可留 P2/P4）：sidecar 采样字段的具体实现与间隔自适应；`round_robin` 的逐 rank 掩码扩展与多节点拒绝矩阵（P4 fake-world）；P3 harness 与外层绑定的去重策略。
