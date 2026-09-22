# ATST GPU 调优 P2 收口与 record 通道验收（SAI 4V100，2026-09-22）

**版本**: 2026-09-22
**日期**: 2026-09-22
**状态**: 完成（只读模型共享、每 attempt 归属、重启回归三项现场断言通过；record 双通道夹具通过；MPS 归属给出站点结论但不可归因，见 §7）
**责任人**: ATST-Tools maintainers

## 1. 目的与范围

关闭 [GPU 节点调优计划](../superpowers/plans/2026-09-20-atst-gpu-node-tuning-plan.md) P2 的
两项未勾选行在现场的剩余部分（只读模型共享与重启回归、宿主 sampler 的 MPS 归属），并把
`scripts/sai_runtime_bench.sbatch` 的 record 夹具按通道落地到真实运行。范围是**运行机制与证据
归属**，不是性能或科学结论：本轮不复测 P5 的计时矩阵，也不声称任何加速比。

## 2. 固定点与环境

| 项 | 值 |
| --- | --- |
| 代码固定点 | `dev/gpu-tuning-closeout-20260922` `0fd205a`（站点克隆 `dirty=false`，见两条 record 的 `atst.record_time`） |
| 站点工作区 | `~/atst-p2-closeout-20260922/`（bundle 克隆 `atst-tools` + `configs/` + `cases/` + 只读模型副本） |
| 解释器 | 站点 venv Python 3.13.15 / ase 3.29.0 / mpi4py 4.1.2 / numpy 2.5.2；deepmd-kit 3.2.0（模块链） |
| 节点与配额 | `4v100n20`（4V100，1 GPU + 8 CPU），QOS `rush-1o2gpu` |
| 作业 | `1444802`（P2 收口，wall 28 s）、`1444708`（record 双通道，wall 2:43） |
| 模型 | FT²DP 单头 100k，`model.ckpt-100000.pt`，sha256 `13b74797…753e34`；作业内复制为只读（`444` 文件 / `555` 目录） |
| ABACUS 通道 | 仓库自带 `examples/06_relax_H2-Au`（`abacus/LTSv3.10.1-sm70-auto`，`mpi: 4`，`ks_solver: cusolver`） |

## 3. 用例与命令

用例清单与配置见证据切片 `docs/reports/data/ATST_P2_CLOSEOUT_20260922/`（`cases/`、`configs/`）。
两条入口脚本也在切片内：`run-p2-closeout.sbatch`、`run-record-channels.sbatch`。

| 段 | 入口 | 断言 |
| --- | --- | --- |
| 只读模型共享 | `atst_tools.bench.batch_runner --share-worker`（2 个 DP 用例，共用只读模型） | 模型目录（内容 sha256 + size + mtime）作业前后逐条不变；2/2 成功；`dp.calculator_reused ≥ 1` |
| 每 attempt 归属 | `atst run --devices/--threads/--telemetry`，同一 workdir 以 `ATST_ATTEMPT=1/2` 各跑一次 | 两份 sidecar 的 `attempt` 分别为 1/2；`.atst_cache/attempt-1` 与 `attempt-2` 同时存在；计数/阶段事实齐备 |
| 重启回归 | 同一绝对 workdir 连跑两个 batch（`--share-worker`） | 两次均 `succeeded`；末帧能量等价（容差 1e-3 eV，实测 1.6e-05 eV）；批级 `.atst_cache` 只有 `attempt-1`；用例目录自带 `atst_artifacts.json`/`runtime_evidence.json`/轨迹 |
| record 双通道 | `scripts/sai_runtime_bench.sbatch`（`MODEL` / `ABACUS_INPUTS`） | DP 记录只有 `dp_model` 且 sha256 = 模型实测值；ABACUS 记录只有 `abacus_inputs`（目录 `tree_sha256` + `file_count`）；两者 note 分别为 `fixtures=dp_model` / `fixtures=abacus_inputs`，warnings 为空 |
| MPS 现场 | `nvidia-smi -q`、`/tmp/nvidia-mps`、`ps -ef`、sampler 逐样本 `processes` | 见 §4.5 |

## 4. 结果

### 4.1 只读模型共享

模型目录摘要作业前后一致（`6a9f1871…f6a8`，含 mtime），2 个用例在**同一 worker 进程**顺序执行、
各 1 次构建/复用：`counters={'dp.calculator_built': 1, 'dp.calculator_reused': 1, 'dp.force_calls': 10}`，
`gauges={'dp.cached_instances': 1.0}`。即：一个 DP calculator 实例服务两个用例，且运行期不写模型目录。

### 4.2 每 attempt 的缓存与证据归属

`ATST_ATTEMPT` 1/2 两次运行分别产生 `attempt-1`、`attempt-2` 缓存目录，两份 sidecar 的 `attempt`
字段与目录一致（该一致性在单测层固定；库调用者传入精选 `base` 时修复前会回落为 1，本轮站点运行不区分该差异，修复见 §6）。两次运行 `threads_source=explicit`
（CLI 线程预算），`dp.force_calls=5` / 各 1 次构建。

### 4.3 重启回归

同一 workdir 连跑两个 batch：两次 `case_report.json` 均 `succeeded`（用例级 3.711 s / 3.721 s，批级 4.525 s / 4.573 s），末帧能量
−3498.2024201687445 eV 与 −3498.202403984692 eV（Δ=1.6e-05 eV，DP 在 GPU 上的重复计算噪声）；
批级缓存目录 `attempt-1` 唯一；用例目录保留自身 `atst_artifacts.json`、`runtime_evidence.json` 与轨迹，
没有沿用上一轮的 atoms/results（轨迹被本轮重写）。

### 4.4 record 双通道

| 通道 | `inputs.fixtures` |
| --- | --- |
| DP | `{"exists": true, "label": "dp_model", "sha256": "13b74797…753e34"}` |
| ABACUS | `{"exists": true, "label": "abacus_inputs", "file_count": 2, "sha256": null, "tree_sha256": "4972c5a0…ea2770"}` |

两条记录都带 `atst.record_time.head = 0fd205a`、`branch = dev/gpu-tuning-closeout-20260922`、`dirty = false`，
`warnings` 为空；ABACUS 通道不再记 DP 模型哈希（原缺陷见 SAI 报告 §8）。

### 4.5 MPS 归属现场结论

节点在跑 MPS：`nvidia-cuda-mps-control -d` 与 `nvidia-cuda-mps-server` 常驻（自 2026-09-11），
但 `nvidia-smi -q` 无 MPS 段、`/tmp/nvidia-mps` 不存在于作业命名空间，
`nvidia-smi --query-compute-apps` 在探测时刻返回空表。采样侧因此逐样本记
`{'unavailable': 3, 'observed': 1}`：可用时报进程行，不可用时记 `status=unavailable` +
`reason="no compute process was reported"`，**不填 0**。结论：本站在 MPS 下**无法稳定做计算进程
归因**，证据保留 `unavailable` 语义；显存峰值仍以采样峰值记录（如 `1078 MiB / sampled_peak`）。

## 5. 证据指针

| 主张 | 证据 |
| --- | --- |
| 只读模型目录未被写入 | `runs/share-second` + 作业日志 `atst-tools/slurm-1444802.out` §2（`model_dir_digest_before/after`） |
| 共享实例 | `runs/share-second/work/ro-a/runtime_evidence.json`、`ro-b/runtime_evidence.json` 的 `counters` |
| attempt 归属 | `runs/attempt-1-evidence.json`、`runs/attempt-2-evidence.json` 的 `attempt` 字段 |
| 重启等价性 | `runs/restart/{first,second}/relax_restart.traj`、`.../restart/case_report.json`、`batch_summary.json` |
| record 双通道 | `record-dp/runs/bench_record.json`、`record-abacus/runs/bench_record.json` |
| 断言执行过程 | `atst-tools/slurm-1444802.out`（P2 收口）、`atst-tools/slurm-1444708.out`（record 通道） |

## 6. 本轮代码变更

| 变更 | 说明 |
| --- | --- |
| `fix(runtime)`: `launch.build_child_environment` 发布 `ATST_ATTEMPT` | 缓存目录按 attempt 派生但该变量未下传，worker 的 sidecar/结果文档会在显式 attempt 下回落为 1；修复后两者一致（回归测试 `tests/unit/test_runtime_restart_isolation.py::test_every_attempt_of_one_workflow_directory_gets_its_own_cache`，去掉修复即失败） |
| `feat(bench)`: record 的通道夹具 | 新增可重复 `--fixture-labeled LABEL=PATH`（目录记 `file_count`/`tree_sha256`），`--fixture PATH` 逐字段不变；站点入口按通道传 `MODEL`→`dp_model`、`ABACUS_INPUTS`→`abacus_inputs`，label 集合写入 note |
| 新增测试 | `tests/unit/test_runtime_model_sharing.py`（4 项，含 `ATST_DP_TEST_MODEL` opt-in 真后端）、`tests/unit/test_runtime_restart_isolation.py`（5 项） |

## 7. 边界与未声称

- **MPS 归因**：本轮只给出站点事实（节点启用 MPS、逐样本可用性不稳定、缺失语义正确）。没有做到
  「MPS 下按进程归因」，也不声称任何归因精度。
- **版本字符串**：站点 venv 安装的是已发布 2.2.6 发行版，运行代码经 `PYTHONPATH` 指向分支；
  sidecar 的 `environment.atst_tools_version` 因 `dist` 元数据显示 2.2.6，权威身份以
  sidecar `atst_tools_path` 与 record 的 git 修订（`0fd205a`）为准。
- **只读模型共享仅覆盖 DP 通道**：ABACUS 通道没有模型文件，其共享面是伪势/轨道的只读输入。
- **未复测**：P5 计时矩阵、host/SIF 成对、DP TF 后端（仍缺 TF 原生制品，`condition-blocked`）、
  站点 `mpiexec` 重绑定（站点/上游确认中）。
- **能量数值**：4.3 的 Δ 是同一结构重复计算的 GPU 数值噪声（1e-05 eV 量级），不构成科学结论；
  断言用 1e-3 eV 容差并在日志中打印实测值。

## 8. 复现

```bash
# 本地（登录节点，仅校验脚本装配，不占算力）
DRY_RUN=1 MODEL=<model.pt> ABACUS_INPUTS=<dir> bash scripts/sai_runtime_bench.sbatch <work> <cases.json> 0
# 站点（1 GPU + 8 CPU，QOS rush-1o2gpu）
sbatch run-p2-closeout.sbatch      # MPS 探测 + 只读共享 + attempt 归属 + 重启回归
sbatch run-record-channels.sbatch  # record 双通道（DP / ABACUS）
```

`atst prepare/run` 的常规门禁不受影响；本报告的所有断言脚本随证据切片保存，可原样重跑。

## 9. 站点复验：DP PT 线程键与 MPS 归因（2026-09-22，作业 1445744/1445792）

固定点 `af82973`（`dev/gpu-tuning-closeout-20260922`）。用例：同一 DP relax（只读 FT²DP 模型）加
`atst run --devices 0 --threads 4 --telemetry`，断言全部读本轮 sidecar。证据切片
`docs/reports/data/ATST_PT_MPS_CLOSEOUT_20260922/`。

| 断言 | 结果 |
| --- | --- |
| deepmd 自荐线程键到达 DP 子环境 | ✅ `DP_INTRA_OP_PARALLELISM_THREADS` / `DP_INTER_OP_PARALLELISM_THREADS` / `OMP_NUM_THREADS` 均 = 4，`threads_source=explicit` |
| MPS 探测三态语义 | ✅（首轮 1445744 因断言过严中止，修正断言后 1445792 通过）现场 `detected=false`，三路探测（`/proc/*/cmdline`、`ps -ef`、客户端管道前缀）均完成——是「完成的否证」而非猜测 |
| 计算进程归因 | ✅ 本轮 `status=observed`（`nvidia-smi` 报出行）；MPS 下空表时 reason 点名 MPS 的路径由 `tests/unit/test_evidence_mps.py` 覆盖 |
| 自身归因 | ✅ `self_reported.status=observed`，`max_memory_allocated_mib=620.139`（torch 分配器口径，读取不触发 CUDA 初始化） |

边界：MPS 守护进程在当日下午两次作业（`4v100n18`/`4v100n26`）均不可见（当日上午作业 1444802 曾可见），
故「MPS 正向路径」尚未在站点观测到；探针在该情形下如实记 `detected=false` 并回落既有 reason，不产生错误归因。
TF 后端不做特意支持：线程预算与制品 kind 判定在算法层对 TF 同样生效，但不安排 TF 制品验证。
