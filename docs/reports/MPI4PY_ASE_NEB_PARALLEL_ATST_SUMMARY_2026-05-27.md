# MPI4PY ASE NEB Parallel ATST Summary

**版本**: 2.0.0
**日期**: 2026-05-27
**状态**: 维护
**责任人**: ATST-Tools maintainers

本文档总结截至 2026-05-27 ATST-Tools 中基于 `mpi4py + ASE`
实现 NEB / AutoNEB image 级并行的设计、实现、测试、SAI 实算验证、
nested MPI 尝试和后续 D2S 扩展判断。文档面向维护者和需要在 SAI
上复现并行工作流的高级用户。

## 1. 背景与核心约束

ATST-Tools 的 NEB image 级并行采用 ASE 原生 MPI 模式：

- Python 进程本身必须由外层 MPI launcher 启动。
- 正确入口是 `mpirun -np N atst run config.yaml`。
- 换言之，必须是用户在作业脚本或命令行中执行 `mpirun atst run`。
- `atst run` 内部不负责再启动 image 级 Python MPI。
- `calculator.abacus.command` 只负责单个 image 的 ABACUS 子进程命令。
- ATST-Tools 不提供 Slurm 提交命令；Slurm 脚本由用户或站点维护。

这一区分是后续所有实现的边界：

```text
outer MPI:
  mpirun -np N atst run config.yaml
  controls ASE image scheduling and mpi4py/ase.parallel.world

inner ABACUS command:
  calculator.abacus.command
  controls one image's ABACUS subprocess
```

因此，不允许通过在 `atst run` 内部设置 `mpirun` 来启动 image 级
NEB 并行；只能让外层 MPI 先创建 Python world，然后 ATST/ASE 使用该
world 调度 images。

## 2. abacuslite 与 ASE 原生依据

vendored abacuslite 示例
`src/atst_tools/external/ASE_interface/examples/neb.py` 已经展示了普通
NEB image 级并行的核心模式：

- 为每个 image 构造一个独立 `Abacus` calculator。
- 使用独立 image 目录，例如 `neb-{irep}`。
- 通过 ASE `NEB(replica, parallel=True)` 运行。

这确认了 `abacuslite + ASE` 本身能够支撑 ordinary NEB image 并行。
ATST-Tools 在此基础上保留 image-isolated directory 模型，同时增加
YAML 输入治理、endpoint 结果治理、rank 拓扑检查、AutoNEB 编排和
真实 ABACUS/mpi4py 环境下的结果同步修复。

## 3. Runtime Topology

ATST v1 采用严格的一 rank 一 active image 模型。

普通 NEB：

```text
world.size == len(init_chain) - 2
```

AutoNEB：

```text
world.size == calculation.n_simul
world.size == len(active_to_run) - 2
```

这样做的原因是避免进入 ASE AutoNEB 的 grouped-rank 分支。当前实现
不支持多个 Python ranks 共同服务一个 image，也不支持一个 rank
同时负责多个 active images。

## 4. MPI Bootstrap 与 ASE World

新增的 MPI 辅助逻辑集中在 `src/atst_tools/utils/mpi.py`：

- `mpi_launcher_detected()` 检测当前进程是否由 MPI launcher 启动。
- `bootstrap_mpi_for_ase()` 在 ASE 解析 `ase.parallel.world` 前导入
  `mpi4py`。
- `get_ase_world()` 返回 ASE 当前 MPI communicator。
- `validate_image_parallel_world()` 统一校验 rank 数与 active image 数。
- `rank_owns_local_image()` 判断当前 rank 是否拥有指定 local image。

关键点是 ASE 会惰性解析并行后端。如果 `mpi4py` 没有在 ASE 解析
`ase.parallel.world` 前导入，ASE 可能退回串行 world。ATST 因此在
CLI 和 NEB/AutoNEB 模块入口处 bootstrap `mpi4py`。

当 MPI launcher 已存在但缺少 `mpi4py` 时，ATST 抛出带修复建议的
`RuntimeError`，要求用户使用与 ABACUS LTS OpenMPI 栈一致的环境：

```bash
conda create -n atst-neb-mpi python=3.10
conda activate atst-neb-mpi
module load abacus/LTSv3.10.1-sm70-auto
python -m pip install -e .
MPICC="$(which mpicc)" python -m pip install --no-binary=mpi4py mpi4py
```

该环境应与 `atst-dev` 分开维护，避免 MPICH-based DeePMD packages 与
ABACUS LTS OpenMPI 栈冲突。

## 5. Ordinary NEB 实现

普通 NEB 的入口仍是 `atst run` 中的 `run_neb()`。

并行模式判断：

```text
effective_parallel = calculation.parallel and world.size > 1
```

当 `parallel: true` 但 `world.size == 1` 时，ATST 给出 warning 并串行
运行 image 计算。当 `effective_parallel` 为真时：

- 调用 `validate_image_parallel_world(world, len(init_chain) - 2, "NEB")`。
- 日志输出 `Image-level NEB parallelism active: world.size=..., interior_images=...`。
- endpoint single-point repair 由 rank 0 执行，再同步给所有 ranks。
- 每个 rank 只给自己拥有的 image attach calculator。
- image 目录保持 `image_001`、`image_002`、`image_003` 形式。

ATST 默认使用 `AbacusNEB`，也保留 `neb_backend: ase` 作为 native ASE
backend 选项。ABACUS 场景优先使用 ATST wrapper，因为它修复了真实
mpi4py 场景下广播同步和 ABACUS 结果数组形状的问题。

## 6. AbacusNEB Result Sync

ASE 原生 NEB 在并行场景中依赖 broadcast 同步。真实 ABACUS 计算中，
不同 rank 上存在未计算 image 和 result array 形状不一致的问题。

ATST 的 `AbacusNEB.get_forces()` 改为 reduction-based sync：

- 所有 rank 初始化完整的 `forces`、`energies`、`real_forces` 容器。
- 当前 rank 只计算自身 owned image。
- 用 `world.sum(...)` 汇总各 rank 的局部数组。
- 标量能量使用 `world.sum_scalar`，没有该接口时回退到 `world.sum`。

这样避免了广播 root 与数组 shape 不匹配造成的实际 MPI 失败。

## 7. AutoNEB 实现

AutoNEB 的入口是 `AutoNEBRunner` 和 `AbacusAutoNEB`。

关键运行时规则：

- `n_simul: null` 时使用 `world.size`。
- `parallel: true` 且 `world.size > 1` 时要求 `world.size == n_simul`。
- 每次 `_execute_one_neb()` 前再次校验 `world.size == len(to_run) - 2`。
- rank 0 负责初始文件写入、cleanup、endpoint repair 等共享文件操作。
- 其他 ranks 在必要位置 barrier，不重复写共享文件。
- active images 用 `_atst_autoneb_index` 标记真实 image index。
- calculator attach 只发生在当前 rank owned image 上。

AutoNEB 还额外修复了两个 ASE 兼容问题：

- 初始化读取同步后的 image 文件时强制 `read(..., parallel=False)`。
- AutoNEB result freezing 使用 reduction，不再使用广播。

## 8. ABACUS Calculator Command 边界

ABACUS calculator 通过 abacuslite backend 执行。ATST 的 command
构造逻辑位于 `src/atst_tools/calculators/factory.py`：

- 如果 `command` 中包含 `{mpi}`，直接格式化为 `command.format(mpi=mpi)`。
- 如果 `mpi > 1` 且 command 是裸 executable，自动包装为
  `mpirun -np <mpi> <command>`。
- 如果外层 Python 已经 MPI-launched，且 ABACUS 是裸单进程命令，
  ATST 会用 `env -u ... abacus` 清理外层 MPI 变量。
- 如果用户显式提供 `mpirun`、`mpiexec`、`srun`，ATST 不二次包装。

这意味着：

- `mpirun -np N atst run ...` 是外层 image MPI。
- `calculator.abacus.command: mpirun -np {mpi} abacus` 是内层 ABACUS MPI。
- 两者职责不同，可以同时存在，但资源拓扑必须由用户和站点脚本保证。

版本探测由 `ATSTAbacusProfile` 管理。运行命令可以是 MPI-wrapped，
但默认版本探测会回退到裸 `abacus --version`。当 command 太复杂时，
建议显式设置：

```yaml
version_command: abacus --version
```

## 9. Error Boundary

ATST 对 image 级并行 rank 数不匹配做主动报错。

统一错误来自：

```text
Image-level parallelism requires MPI ranks (...) to equal active interior images (...). Context: ...
```

已覆盖的边界：

- 普通 NEB：`world.size != len(init_chain) - 2`。
- AutoNEB runner 初始化：`world.size != n_simul`。
- AutoNEB active band：`world.size != len(to_run) - 2`。
- `n_simul <= 0` 被 schema 拒绝。

当前 CLI 对这些 `ValueError` 没有统一转成无 traceback 的用户错误。
因此实际 CLI 行为是清晰错误信息加 Python traceback，并以非零退出。
如需更好的 UX，可后续在 `atst run` 层捕获这类配置/拓扑错误并
`SystemExit`。

## 10. Unit Tests 与 Local Validation

新增和扩展的关键测试覆盖：

- `tests/unit/test_mpi_parallel.py`
  - `mpi4py` 缺失时的 bootstrap error。
  - 普通 NEB rank 数必须等于 interior images。
  - AutoNEB rank 数必须等于 `n_simul`。
  - AutoNEB active band 拒绝 grouped-rank execution。
  - rank-owned calculator attach。
  - endpoint sync 只由 rank 0 写文件。
  - `AbacusNEB` 使用 reductions，不使用 broadcasts。
  - AutoNEB result freezing 使用 reductions。
- `tests/unit/test_factory.py`
  - `{mpi}` command template。
  - 显式 `srun` 不二次包装。
  - 外层 MPI 下裸 `abacus` 会清理 MPI env。
- `tests/unit/test_abacuslite_profile.py`
  - wrapped command 的 version probe 使用裸 executable。
- `tests/unit/test_config.py`
  - `n_simul: 0` 被拒绝。

本地验证命令：

```bash
conda run -n atst-dev env PYTHONPATH=$PWD/src pytest tests -q
conda run -n atst-dev env PYTHONPATH=$PWD/src atst run --dry-run examples/01_neb_Li-Si/config.yaml
conda run -n atst-dev env PYTHONPATH=$PWD/src atst run --dry-run examples/03_autoneb_Cy-Pt/config.yaml
conda run -n atst-dev env PYTHONPATH=$PWD/src atst run --dry-run examples/01_neb_Li-Si/config_parallel_smoke.yaml
conda run -n atst-dev env PYTHONPATH=$PWD/src atst run --dry-run examples/03_autoneb_Cy-Pt/config_parallel_smoke.yaml
conda run -n atst-dev env PYTHONPATH=$PWD/src atst run --dry-run examples/01_neb_Li-Si/config_parallel_long.yaml
git diff --check
```

截至 2026-05-26，本地全量测试结果为 `188 passed`。

维护的并行 smoke 输入包括：

- `examples/01_neb_Li-Si/config_parallel_smoke.yaml`
- `examples/03_autoneb_Cy-Pt/config_parallel_smoke.yaml`
- `examples/01_neb_Li-Si/config_parallel_long.yaml`

这些配置保持 ABACUS 为 one process per image，普通 NEB 通过
`mpirun -np 3 atst run config_parallel_smoke.yaml` 启动，AutoNEB 通过
`mpirun -np 4 atst run config_parallel_smoke.yaml` 启动。它们是 nested
MPI 前的基础验证入口。

## 11. SAI 普通 NEB 与 AutoNEB 实算

SAI 环境：

- ABACUS: `abacus/LTSv3.10.1-sm70-auto`
- ABACUS version: `v3.10.1`
- Python env: `atst-neb-mpi`
- GPU: `Tesla V100-SXM2-32GB`
- 初始 smoke 均使用 `calculator.abacus.mpi: 1`，避免先引入 nested MPI。

MPI visibility check：

```bash
mpirun -np 4 python -c 'from mpi4py import MPI; from ase.parallel import world; print(world.rank, world.size)'
```

期望并已观测到 ASE `world.size == 4`。

SAI 4V100 validation 结果：

| Job | Workflow | Result | Evidence |
| --- | --- | --- | --- |
| `454736` | NEB smoke | `COMPLETED 0:0`, `00:01:21` | `world.size=3, interior_images=3`, `NEB calculation finished` |
| `455156` | NEB long | `COMPLETED 0:0`, `00:14:31` | 允许 50 optimizer steps，post barrier `0.6183455223 eV` |
| `455373` | AutoNEB smoke | `COMPLETED 0:0`, `00:14:20` | `world.size=4, n_simul=4`, `AutoNEB Calculation Finished` |

这些 smoke 目录中的 ABACUS 日志确认：

- ABACUS version 为 `v3.10.1`。
- 计算运行在 `Tesla V100-SXM2-32GB` GPU 节点上。
- 初始 smoke 阶段每个 image 使用 one local ABACUS MPI process。

AutoNEB smoke 结束时出现 UCX warning：

```text
UCX WARN unexpected tag-receive descriptor ... was not matched
```

但 Slurm exit code 为 `0:0`，并且 workflow 完成。这类 warning 当前
作为 MPI runtime cleanup 噪声记录，不视为功能失败。

## 12. Nested MPI 实践

nested MPI 指同时使用：

```text
outer: mpirun -np 3 atst run config.yaml
inner: each image runs mpirun -np 4 abacus
```

验证目录：

```text
validation_runs/neb_nested_mpi_20260527/
```

目标：

- example: `examples/01_neb_Li-Si`
- partition: `4V100PX`
- qos: `rush-gpu`
- Slurm resources: `nodes=3`, `ntasks=12`, `gpus-per-node=4`
- outer Python ranks: `3`
- inner ABACUS ranks per image: `4`

最终成功 job：

| Job | State | ExitCode | Elapsed |
| --- | --- | --- | --- |
| `456739` | `COMPLETED` | `0:0` | `00:00:29` |

成功 evidence：

```text
Image-level NEB parallelism active: world.size=3, interior_images=3
NEB calculation finished
```

每个 image 的 ABACUS stderr：

```text
image_001/abacus.err: Local MPI proc number: 4
image_002/abacus.err: Local MPI proc number: 4
image_003/abacus.err: Local MPI proc number: 4
```

每个 image 的 ABACUS SCF log 均完成：

```text
Total Time : 0 h 0 mins 11 secs
```

### 12.1 失败尝试

| Job | Result | Cause |
| --- | --- | --- |
| `456452` | `FAILED 1:0` | 数据路径错误，且内层继承 SAI `MAP_OPT` 后出现 PPR/slot 冲突 |
| `456695` | `FAILED 1:0` | 数据路径修复后，仍因 inner launcher 使用 Slurm 全局 slot accounting 失败 |
| `456723` | `FAILED 1:0` | 直接 unset Slurm 变量导致 PRRTE Slurm RAS 组件找不到 `SLURM_NODELIST` |
| `456739` | `COMPLETED 0:0` | 成功：inner launcher 使用 isolated/local mapping 并禁用 Slurm RAS |

失败错误包括：

```text
All nodes which are allocated for this job are already filled.
Your job failed to map ... Mapper result: Out of resource
While trying to determine what resources are available, the SLURM resource allocator expects ...
```

这些失败说明服务器预置的顶层 ABACUS MPI 命令不能原样作为 nested
inner command。

## 13. SAI Server Template 与 Nested MPI 命令

SAI 预置 ABACUS 模板 `/opt/sbatch_examples/gpu_abacus.sbatch` 的核心是：

```bash
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash
module load abacus/LTSv3.10.1-sm70-auto
mpirun -np $SLURM_NTASKS --map-by $MAP_OPT abacus
```

这适合顶层 Slurm ABACUS job，但不能直接放入
`calculator.abacus.command`：

- abacuslite 使用 `subprocess.check_call(argv, shell=False)`，不会展开
  `$SLURM_NTASKS` 和 `$MAP_OPT`。
- `$MAP_OPT` 是按整个 Slurm allocation 计算的，不是按单个 image 的
  inner subprocess 计算的。
- 多个 image 并发启动 inner `mpirun` 时，Slurm/PRRTE 会认为全局资源
  已被填满或 mapping policy 超限。

成功 wrapper 使用：

```bash
mpirun \
  -np "${inner_np}" \
  --host "localhost:${inner_np}" \
  --oversubscribe \
  -map-by slot \
  --bind-to none \
  -mca ras ^slurm \
  -mca plm isolated \
  -mca rmaps_base_oversubscribe 1 \
  -mca coll_hcoll_enable 0 \
  abacus
```

其中关键参数是：

- `--host localhost:{mpi}`：将 inner ABACUS MPI 限制在当前 image rank
  所在节点。
- `-mca ras ^slurm`：禁用 inner launcher 的 Slurm resource allocator。
- `-mca plm isolated`：让 inner launcher 作为本地 isolated job 启动。
- `-mca rmaps_base_oversubscribe 1`：允许该 isolated launcher 按本地
  host slot 运行。
- `env -u OMPI_* -u PMI_* -u PMIX_*`：避免 ABACUS 子进程继承 outer
  Python MPI world 元数据。

### 13.1 可直接写入 YAML 的推荐命令

当前 ATST 架构可以不使用 wrapper，而是把完整命令写入 YAML：

```yaml
calculator:
  name: abacus
  abacus:
    command: env -u OMPI_COMM_WORLD_SIZE -u OMPI_COMM_WORLD_RANK -u OMPI_COMM_WORLD_LOCAL_RANK -u OMPI_COMM_WORLD_LOCAL_SIZE -u OMPI_UNIVERSE_SIZE -u PMI_SIZE -u PMI_RANK -u PMIX_RANK -u PMIX_NAMESPACE -u MPI_LOCALRANKID mpirun -np {mpi} --host localhost:{mpi} --oversubscribe -map-by slot --bind-to none -mca ras ^slurm -mca plm isolated -mca rmaps_base_oversubscribe 1 -mca coll_hcoll_enable 0 abacus
    version_command: abacus --version
    mpi: 4
    omp: 1
```

该命令会被 `_build_abacus_command()` 中的 `{mpi}` 模板逻辑原样格式化。
由于 abacuslite 使用 argv list 执行，不依赖 shell expansion，所以这种
写法比 `$SLURM_NTASKS` / `$MAP_OPT` 更稳定。

## 14. D2S 扩展评估

D2S 当前流程：

1. endpoint optimization 或 endpoint singlepoint。
2. rough double-ended NEB。
3. single-ended Dimer 或 Sella。
4. optional vibration。

当前 D2S rough NEB 使用：

```text
DyNEB(..., dynamic_relaxation=True, parallel=False)
```

因此 D2S image 级并行可行，但应作为显式并行模式实现：

- endpoint optimization / endpoint singlepoint 由 rank 0 执行并同步结果。
- rough double-ended NEB 在 parallel 模式下切换到 `AbacusNEB`。
- `world.size == neb.n_images`，其中 `neb.n_images` 是 intermediate images 数。
- single-ended Dimer/Sella/CCQN 作为 rank-0-only serial tail。
- 非 0 ranks 在 rough NEB 后 barrier，然后等待/返回，不进入 single-ended optimizer。

限制：

- 并行 D2S rough NEB 不应继续使用 DyNEB dynamic relaxation。
- `scale_fmax > 0` 在并行模式下应拒绝或明确提示不支持。
- 当前 D2S schema 只支持 `method: dimer | sella`；如果要把 `ccqn`
  作为顶层 method，需要先扩展 schema 和 workflow。

## 15. 当前结论

ATST 中 `mpi4py + ASE` image 级 NEB/AutoNEB 并行已完成核心落地：

- 普通 NEB image parallel 可用。
- AutoNEB image parallel 可用。
- rank 数 mismatch 有主动报错边界。
- ABACUS 子进程不会意外加入 outer Python MPI world。
- SAI 4V100 smoke/long jobs 已完成验证。
- nested MPI 在 SAI 4V100PX 上可用，但需要专门的 inner ABACUS command。

推荐生产使用顺序：

1. 先用 `calculator.abacus.mpi: 1` 验证 image 级并行。
2. 再开启 nested MPI per image。
3. nested MPI 下避免直接使用 `/opt/sbatch_examples/gpu_abacus.sbatch`
   的 `$SLURM_NTASKS` / `$MAP_OPT` 命令作为 inner command。
4. 在 SAI OpenMPI/PRRTE 栈上使用 `-mca ras ^slurm -mca plm isolated`
   隔离 inner launcher。

## 16. 后续建议

- 将 nested MPI 推荐命令补充到用户级 ABACUS wrapper guide。
- 为 CLI 增加并行拓扑错误的无 traceback `SystemExit` 包装。
- 为 D2S 增加显式 `neb.parallel` 设计和 rank-0 serial tail。
- 如需长期支持 nested MPI，可考虑提供文档化的 site command recipe，
  但不在 ATST 内置 Slurm submit 或站点特定 launcher。
- 保持 examples 的官方 smoke 配置默认 `calculator.abacus.mpi: 1`，
  nested MPI 作为高级 SAI 配置记录在文档中。
