# ATST-Tools Runtime 接口冻结设计（GPU 节点调优 P0）

**版本**: 2026-09-21
**日期**: 2026-09-21
**状态**: 草案（P0 交付；待相称独立设计审查后进入 P1）
**责任人**: ATST-Tools maintainers

设计来源：[GPU 节点调优设计](2026-09-20-atst-gpu-node-tuning-design.md)；执行计划：[GPU 节点优化开发与验证计划](../plans/2026-09-20-atst-gpu-node-tuning-plan.md)。本文冻结 P0 要求的接口语义（schema 拼写、优先级、解析边界、进程路径、证据与协调顺序），不表示代码、真实计算或发布已执行。实现与本文冲突时以本文为准；变更需回写本文并列 Ruling。

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

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `runtime.devices` | null、int、str 或 list（int/str 混合） | null（inherit） | 设备请求；只决定请求，不扩大可用集合 |
| `runtime.binding` | `inherit` 或 `round_robin` | `inherit` | MPI 逐 rank 绑定策略；`round_robin` 仅限已核验的单节点共同设备池 |
| `runtime.threads` | null 或 ≥1 整数 | null | 进程线程预算；科学库初始化前生效（优先级见 §6） |
| `runtime.telemetry` | null、bool 或 `{enabled: bool=false, interval_s: float>0=1.0}` | false | GPU 宿主采样与运行证据 sidecar 开关 |

`devices` 值语法（YAML / CLI / env 三者一致）：

- 标量或列表；元素为非负整数（0-based 逻辑序号）或完整物理 UUID（`GPU-` + 8-4-4-4-12 十六进制）。
- 列表保持顺序；重复元素拒绝；负数拒绝；`MIG-` 前缀拒绝（首期不支持 MIG 选择）。
- 空列表、CLI 空值、`ATST_VISIBLE_DEVICES=""` 一律视为“显式空请求”并拒绝；字段缺省 / 环境变量未设置 = inherit。两者不可混同。
- 逻辑序号相对“继承可见集合”，与原子选择 1-based 规则无关。

校验消息（冻结，英文，`ConfigValidationError`）：

- `runtime.devices must be a device index or GPU UUID string`
- `runtime.devices entry '<token>' is not a valid 0-based device index or full GPU UUID`
- `runtime.devices must not contain duplicate entries (<token>)`
- `runtime.devices must not be empty; omit the field to inherit all visible devices`
- `runtime.devices does not support MIG device selection ('<token>'); pass a full physical GPU UUID instead`
- `runtime.threads must be a positive integer`
- `runtime.binding '<mode>' is not one of: inherit, round_robin`
- `runtime.telemetry.interval_s must be a positive number`

## 3. CLI 与环境变量

`atst run` 与 `python -m atst_tools.api.runner` 增加以下可选选项；未指定时行为与现状逐字节一致：

- `--devices <spec>`：逗号分隔，语法同 YAML；空值 = 显式空请求（拒绝）。
- `--binding inherit|round_robin`
- `--threads <n>`
- `--telemetry` / `--no-telemetry`，`--telemetry-interval <sec>`

优先级（逐字段独立解析）：CLI > YAML `runtime.*` > `ATST_VISIBLE_DEVICES`（仅 devices）> 缺省。任何层级只决定“请求”，不能扩大可用集合。`ATST_VISIBLE_DEVICES` 与参数同语法、同逻辑序号语义，不是 CUDA mask 的直接复制。

其他子命令（`atst prepare`、`atst config validate`、`atst banner` 等）本期不新增 runtime 选项；`atst prepare` 不生成 `runtime` 段。

## 4. 设备解析语义

四层事实分开记录：requested / inherited / allocation / effective。解析在 bootstrap 内、科学库导入之前完成：

1. 读 `CUDA_VISIBLE_DEVICES`（未设置 = 全部可见）；需要身份时用短命 helper 枚举 UUID，coordinator 不初始化 CUDA。
2. 解析 requested（§3 优先级）；无请求 = inherit。
3. allocation 事实：平台 adapter 提供时可用；首期仅接受外层显式传入 `ATST_ALLOCATION_DEVICES`（同语法），未提供 = unknown。
4. 过度暴露判定：

| inherited 与 allocation 关系 | 请求形态 | 行为 |
| --- | --- | --- |
| 身份未知，visible 数 > 可信 allocation | 显式 devices，或共享/重绑定请求 | 拒绝：`explicit device selection is refused: ...` |
| 身份未知，visible 数 > 可信 allocation | 纯 inherit、无冲突证据 | 原样沿用启动环境，记录 `allocation_identity: "unverified"` |
| 有可信 allocation | 显式 devices | 收窄到 inherited ∩ allocation；越界报错 |
| 无 allocation 事实 | 显式 devices（ordinal） | 允许；记录 allocation unknown；ordinal 越界报错 |

- `effective` 永远是 inherited 的子集；序号越界消息：`device index <i> is outside the inherited visible set (size <n>)`。
- UUID 请求在无法枚举身份时按字面 token 传递并标记 `identity: "literal"`。
- 无 GPU/无采样工具：显式 GPU 请求按执行错误失败；计量降级不冒充成功。

## 5. 进程与启动边界

- `atst run`：轻量 coordinator 解析配置/CLI → 构造 child（CUDA mask、线程、cwd、可写 JIT/cache 目录、telemetry 开关）→ 以 exec 进入唯一 worker 进程，复用 `python -m atst_tools.api.runner` 协议与原子结果写。一个工作流一个新解释器，不为每次力调用创建进程。
- 导入链：绑定先于 NumPy/ASE/DP/ABACUS/JAX 初始化；`atst_tools/__init__.py` 保持轻量（当前为 metadata-only）；新 runtime 模块不得在包导入期触发重依赖，P1 用 import smoke 测试固定。
- MPI：既有 launcher 每 rank 启动 bootstrap，rank 在 MPI/CUDA 初始化前绑定并 exec；communicator 不跨普通 subprocess 传递；NEB/AutoNEB 的 rank 约束与失败同步 helper 不变。
- 嵌入 API：`run_workflow(config, RunOptions(...))` 保持当前进程、communicator、callback 和返回类型；YAML 含 `runtime.devices` 或 `runtime.threads` 时抛 `RuntimeBindingError`（`embedding API cannot rebind devices; run the workflow through 'atst run' or 'python -m atst_tools.api.runner' instead`），不污染调用者环境；`runtime.telemetry` 只读记录。
- 失败与取消：worker 进程组有界终止，回收采样进程与槽位；MPI 初始化前死亡由 launcher/coordinator 的退出与超时处理。

## 6. 线程与 OMP 优先级（SPEC §11 R3）

| `calculator.*.omp` | `runtime.threads` | 生效 | 记录 |
| --- | --- | --- | --- |
| 显式 | 缺省 | calculator 值（现状） | — |
| 显式 | 显式且不同 | calculator 值 | fact `runtime_threads_overridden`（记录两值） |
| 缺省 | 显式 | runtime 值（导入前写入） | — |
| 缺省 | 缺省 | 不写 OMP，保持现状 | — |

进程级键：`OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`MKL_NUM_THREADS`、`NUMEXPR_NUM_THREADS` 取同一值。`calculator.omp` 的既有写入点（`calculators/dp.py:92-94`、`calculators/factory.py:165`）保持不变，冲突只记录、不覆盖用户科学配置。

## 7. Fixture 与运行证据

### 7.1 Fixture 候选（P5 定稿）

- DP 通用回归：`examples/dp_model_manifest.json` 的 `DPA-3.1-3M`（head `Omat24`，sha256 `86dd3a80…`）。
- DP 科研候选（只读）：`FT2DPv2.2-dpa4-air-zbl-single100k-v20260919` 的 `checkpoints/model.ckpt-100000.pt`（regular，sha256 `13b74797…`；EMA `45667e7f…`），位于 `/home/james/work/ft2dp-dpeva/models/…`。使用前回读模型 manifest 核验 head/type map/单位/精度/格式与运行兼容；历史接入记录为 atst 2.1.1 + deepmd `3.2.1.dev0+g687b5107`，不得当作恒电势模型使用。
- ABACUS 候选（按规模）：`examples/01_neb_Li-Si`、`02_neb_H2-Au`、`03_autoneb_Cy-Pt`、`08_d2s_Cy-Pt`、`06_relax_H2-Au`；原子数与输入身份在 P5 基线实测登记，不用原稿“120 原子量级”假设。
- 原稿作业证据待补：DP `1422694/1422849/1423160`、ABACUS `1423179` 的日志/输入/卡时；未补齐前不作为基线。

### 7.2 运行证据 sidecar

- 触发：存在 `runtime` 段、显式 runtime 选项或 `telemetry.enabled=true` 时写出；缺省调用不新增文件、结果文档逐字节不变。
- 位置与引用：`runtime_evidence.json` 与 artifact manifest 同目录；manifest metadata 增加可选 `runtime_evidence` 相对路径；`atst-api-result-v1` 增加可选 `runtime` 摘要对象（只增字段）。
- 字段分层按 SPEC §6：workflow/stage、rank/worker、GPU device、process（可得）、allocation/batch。状态 `disabled | unavailable | partial | observed` 加 `reason/source`；缺失 = null，不填 0；显存峰值标记 `sampled_peak`。
- 采样所有权：每 job 一个宿主采样器（不按 rank 复制），默认关闭；`nvidia-smi` 缺失或权限不足时状态 `unavailable`。

## 8. 与恒电势在途工作的共享文件协调（SPEC §11 R4）

现状（2026-09-21）：`sidereus/.worktrees/constant-potential-plan-review` 的 atst 子模块在本地分支 `feature/constant-potential-integration` 上有 29 个未提交文件，含本计划 P1–P2 要改的共享文件：`utils/config_schema.py`（+304）、`api/services.py`、`calculators/factory.py`、`scripts/main.py`、`utils/neb_endpoints.py`，以及双方都会更新的用户文档。

建议顺序：

1. 恒电势分支先提交其变更（当前完全未提交，存在丢失风险）；
2. GPU 侧先落地无重叠的新模块（设备解析/绑定/证据）与单测、以及本文档；
3. 恒电势合入后 GPU rebase，按顺序串行修改 `config_schema.py`（新增 `runtime` 段）→ `scripts/main.py`（CLI 选项）→ `api/services.py`（plumbing）→ `calculators/factory.py`（绑定适配）；
4. 文档（`CONFIG_REFERENCE`、`CLI_REFERENCE`、`USER_GUIDE_CN`、README、`FEATURE_STATUS_MATRIX`、文档账本）最后合并，避免双方重复编辑。

字段归属：恒电势拥有 `calculation.type: constant_potential` 与 `calculator.constant_potential`；GPU 拥有 `runtime`；两者都只增可选字段，联合验收至少包含一条“同时启用仍严格校验”的测试（SPEC §7A）。

## 9. P0 验收对照表

| 场景 | 期望行为 |
| --- | --- |
| `CUDA_VISIBLE_DEVICES=2,3` + `runtime.devices: [0]` | effective = 继承集合第 0 个（宿主 2）；证据记录 inherited=[2,3]、requested=[0]、effective=<uuid 或 2> |
| `CUDA_VISIBLE_DEVICES=2,3` + `devices: []` | `ConfigValidationError`：`runtime.devices must not be empty; omit the field to inherit all visible devices` |
| `CUDA_VISIBLE_DEVICES=2,3` + `devices: [2]` | `device index 2 is outside the inherited visible set (size 2)` |
| visible=0,1,2,3、allocation 未知、`devices: [0]`（共享/重绑定请求） | 拒绝：`explicit device selection is refused: ...` |
| 同上但纯 inherit 且无冲突证据 | 放行，证据 `allocation_identity: "unverified"` |
| `MIG-…` UUID 请求 | `runtime.devices does not support MIG device selection ('<token>'); ...` |
| 已初始化进程内 API + `runtime.devices` | `RuntimeBindingError` 指向隔离入口；父进程 env/cwd 不变 |
| 自定义 communicator/callback | 行为不变；`RunOptions.world` 原样使用 |
| `devices: [1,1]` | `runtime.devices must not contain duplicate entries (1)` |
| `ATST_VISIBLE_DEVICES=""` | 显式空请求错误；未设置 = inherit |

## 10. 未决与待审查项

- sidecar 文件名、位置与 manifest 键名（`runtime_evidence`）待审查确认；
- `round_robin` 校验时机（bootstrap，依赖 world size）与逐 rank 掩码写法待 P4 以 fake-world 测试固定；
- `ATST_ALLOCATION_DEVICES` 作为首期可信分配输入的命名与保留性待审查；
- `telemetry.interval_s` 默认 1.0 s；
- 是否允许 `--devices` 出现在 `atst validate`（默认否）。
