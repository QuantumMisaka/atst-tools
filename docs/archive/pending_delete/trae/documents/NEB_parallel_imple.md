# NEB/AutoNEB Image-Level Parallel Unified Development Plan

## Summary

目标是在 `feat/neb-parallel` 上实现 ABACUS-backed 普通 NEB 和 AutoNEB 的 image 级 MPI 并行。依据 ASE 3.28.0
文档、源码和 `abacuslite` 自带示例，本轮采用“一 Python MPI rank 对应一个 active interior image”的 v1 安全模型，
并将 `abacuslite + ASE` 明确为唯一实现主线，不恢复 legacy `ase-abacus`。

本计划为统一版主文档，合并以下两类信息：

- `NEB_parallel_imple.md` 中关于 ASE 设计约束、实现状态、测试与文档治理的完整基线。
- `NEB_para_abacuslite.md` 中关于 `abacuslite` 上游示例、目录策略和工程落地方向的确认结论。

## 开发目标与方向

### 目标 1：明确实现主线

- 以 `abacuslite + ASE` 为普通 NEB 和 AutoNEB image 并行的正式实现路径。
- 普通 NEB 复用 ASE 原生 `NEB(..., parallel=True)` / ATST `AbacusNEB(..., parallel=True)`。
- AutoNEB 继续复用 ASE AutoNEB 调度与现有 ATST wrapper 设计，不重写 ASE 已有并行机制。
- 不恢复、不引入 legacy `ase-abacus` 作为本轮开发路径。

### 目标 2：建立稳定的 MPI Python 启动链路

- 在任何 ASE import 前完成 MPI-aware Python bootstrap，确保 ASE `world` 能识别真实 MPI communicator。
- 统一在 MPI launcher 环境下优先导入 `mpi4py`，避免 ASE 退化到 `DummyMPI()`。
- 当检测到 MPI launcher 但缺少 `mpi4py` 时，给出明确错误和环境修复提示。

### 目标 3：收紧 v1 并行拓扑边界

- 普通 NEB 采用严格一对一模型：`world.size == len(images) - 2`。
- AutoNEB 采用严格一对一模型：`world.size == n_simul == len(to_run) - 2`。
- 明确 v1 不支持“多个 Python ranks 组成一个 image group”再交给 ABACUS 子进程使用。
- grouped-rank / per-image subcommunicator / site wrapper 方案作为后续增强项，不纳入本轮交付。

### 目标 4：统一 calculator 和目录策略

- 并行普通 NEB 和 AutoNEB 都采用 image-index 优先的工作目录命名。
- 普通 NEB 并行模式下，每个 rank 只为自己负责的一个 interior image 挂载 calculator。
- AutoNEB 并行 active sub-NEB 中，每个 rank 只为自己负责的一个 active image 挂载 calculator。
- 目录策略优先使用 `{base_dir}/image_{global_image_index:03d}`，保持 restart、诊断和日志定位友好。

### 目标 5：补齐并行文件写入同步

- endpoint single-point 的实际文件写入仅允许 rank 0 执行。
- AutoNEB 的初始 `prefix*.traj` 写入和 cleanup 仅允许 rank 0 执行。
- rank 0 完成写入后使用 `world.barrier()`，确保其他 ranks 只消费一致状态，不并发写同一目录。

### 目标 6：保留串行兼容性并明确非目标

- 串行 `atst run` 兼容性继续保留。
- 严格 topology 校验仅在 effective ASE parallel mode 下生效。
- DyNEB 动态优化仍只用于串行；并行普通 NEB 必须走 `NEB/AbacusNEB`，不是 DyNEB。
- DP、D2S image 并行不进入本轮实现。
- 生产长跑和科学结果回归不作为本轮验收目标，本轮以机制正确性和 smoke 为准。

## 上游依据与关键判断

### 已确认的上游参考行为

- `abacuslite` 自带示例 `src/atst_tools/external/ASE_interface/examples/neb.py` 已展示普通 NEB image 级并行可行。
- 示例核心形态为：
  - `AbacusProfile(command='mpirun -np 8 abacus_2p', ...)`
  - 每个 replica 挂载 `Abacus(..., directory=here / f'neb-{irep}')`
  - `neb = NEB(replica, k=0.05, climb=False, parallel=True)`
  - `FIRE(neb, trajectory='neb.traj').run(...)`

### 由上游行为得到的结论

- ASE `NEB(images, parallel=True)` 和 `AutoNEB(..., parallel=True)` 本身支持 image 级并行。
- `abacuslite + ASE` 路线本身能够承载普通 NEB image 并行，不需要恢复 legacy `ase-abacus`。
- `abacuslite` 示例是普通 NEB 的上游参考实现，应作为目录策略和 calculator 绑定策略依据。
- 工作目录命名应从“rank 优先”收敛为“image 优先”。
- 示例中的 `mpirun -np 8 abacus_2p` 属于 ABACUS calculator 子进程并行，不等于 Python image 并行 bootstrap。

### 当前已知问题与设计边界

- `atst-dev` 当前缺少 `mpi4py`，因此普通 `mpirun python` 下 ASE 可能看到 `world.size == 1`。
- 本轮 v1 不支持多 Python rank 组成一个 image 组供单 image 的 ABACUS backend 使用。
- 多 MPI per image 后续作为独立增强项处理，不作为默认支持路径。

## ASE 设计约束

### MPI bootstrap 约束

- 必须在任何 ASE import 前导入：

  ```python
  from mpi4py import MPI
  ```

- 依据 ASE `ase.parallel._get_comm()` 机制，只有 `mpi4py` 已在 `sys.modules` 中时才会选择 `MPI4PY()`，否则会退化为
  `DummyMPI()`。

### 普通 NEB 拓扑约束

- ASE 普通 NEB 源码使用如下 rank 到 image 的映射：

  ```python
  i = world.rank * (nimages - 2) // world.size + 1
  root = (i - 1) * world.size // (nimages - 2)
  ```

- 为避免未计算 image 或重复计算 image，ATST v1 强制 `world.size == len(images) - 2`。

### AutoNEB 拓扑约束

- ASE AutoNEB 源码允许 `world.size` 是 active image 数的整数倍。
- 但由于 ABACUS subprocess backend 当前没有 per-image subcommunicator，ATST v1 强制
  `world.size == n_simul == len(to_run) - 2`，避免进入 grouped-rank 分支。

### 算法边界

- DyNEB 动态优化仅用于串行场景。
- 并行普通 NEB 必须走 `NEB/AbacusNEB`，不能切换为 DyNEB 作为替代。

## 具体实现方案

### 1. MPI bootstrap helper

- 新增无 ASE 依赖的 MPI bootstrap helper，例如 `src/atst_tools/utils/mpi.py`。
- helper 负责：
  - 检测 OpenMPI / PMI / PMIx launcher 环境。
  - 若检测到 MPI launcher，则在任何 ASE import 前执行 `from mpi4py import MPI`。
  - 若 MPI launcher 下缺少 `mpi4py`，抛出明确 `RuntimeError`，提示使用 ABACUS LTS 同源 OpenMPI 编译安装。

### 2. 入口模块 bootstrap

- 在所有可能作为入口并提前 import ASE 的模块顶部调用 bootstrap：
  - `src/atst_tools/scripts/cli.py`
  - `src/atst_tools/scripts/main.py`
  - `src/atst_tools/mep/neb.py`
  - `src/atst_tools/mep/autoneb.py`

### 3. topology 校验 helper

- 将 topology 校验抽成 helper，并在构造 ASE NEB 前执行：

  ```python
  from ase.parallel import world

  n_interior = len(images) - 2
  if parallel and world.size != n_interior:
      raise ValueError(
          f"MPI ranks ({world.size}) must equal "
          f"interior images ({n_interior})"
      )
  ```

- 这里的 `parallel` 指传给 ASE 的 effective parallel flag。
- 非 MPI 串行运行仍允许降级为串行 warning，不强制抛错。

### 4. 普通 NEB calculator 挂载规则

- `effective_parallel=False`：
  - 保持当前串行 per-image directory 或 DP shared calculator 行为。
- `effective_parallel=True`：
  - 只给 `world.rank` 对应的 interior image 挂 calculator。
  - 工作目录使用全局 image index，例如 `{base_dir}/image_{global_image_index:03d}`。
  - 该策略与 `abacuslite` 示例中每个 image 独立 `neb-{irep}` 的思路一致，但更利于 restart 和诊断。

### 5. AutoNEB runner 约束与同步

- 增加 `n_simul` 正整数校验。
- `effective_parallel=True` 时要求 `world.size == n_simul`。
- 在 `_execute_one_neb()` 内再次校验 `len(to_run) - 2 == world.size`，避免误入 ASE grouped-rank 分支。
- rank 0 负责初始 `prefix*.traj` 写入和 cleanup，随后执行 `world.barrier()`。
- 并行 active sub-NEB 中，每个 rank 只给自己负责的 active image 挂 calculator。

### 6. endpoint single-point 同步

- 并行模式下只允许 rank 0 执行 endpoint single-point 文件写入。
- 写入完成后执行 `world.barrier()`，再让所有 ranks 读取或接收一致 endpoint 结果。
- 避免多 rank 同时写同一 endpoint 目录。

## 当前实现状态

- 已实现 MPI bootstrap helper。
- 已实现入口模块 bootstrap。
- 已实现普通 NEB / AutoNEB topology 校验。
- 已实现普通 NEB 和 AutoNEB 的 image-index ABACUS 工作目录。
- 已实现普通 NEB 与 AutoNEB endpoint single-point 的 rank 0 同步。
- 已实现 AutoNEB 初始 trajectory 写入和 cleanup 的 rank 0 保护。
- 已实现 AutoNEB active sub-NEB 每 rank 只挂载一个 active image calculator。
- 已新增用户文档和实现报告。
- 仍需通过 SAI 4V100 Slurm smoke 验证真实 ABACUS 运行链路。

## 环境与运行边界

### 建议开发环境

- 新建隔离环境 `atst-neb-mpi`，不改当前 `atst-dev`：

  ```bash
  conda create -n atst-neb-mpi python=3.10
  conda activate atst-neb-mpi
  module load abacus/LTSv3.10.1-sm70-auto
  python -m pip install -e .
  MPICC="$(which mpicc)" python -m pip install --no-binary=mpi4py mpi4py
  ```

### MPI 绑定要求

- 必须绑定 SAI `abacus/LTSv3.10.1-sm70-auto` 对应的同源 OpenMPI，已确认目标链路为 OpenMPI 5.0.8。
- 最小检查命令：

  ```bash
  mpirun -np 4 python -c 'from mpi4py import MPI; from ase.parallel import world; print(world.rank, world.size)'
  ```

- 期望输出 4 行，且 `world.size == 4`。

### 两层 MPI 的明确区分

- 外层：
  - `mpirun -np N atst run config.yaml`
  - 负责 ASE image 级并行。
- 内层：
  - `calculator.abacus.mpi: M`
  - 负责单个 image 的 ABACUS 子进程并行。
- `abacuslite` 示例中的 `AbacusProfile(command='mpirun -np 8 abacus_2p')` 属于内层 MPI。

### v1 运行建议

- 官方 smoke 配置优先使用 `calculator.abacus.mpi: 1`。
- 这样可避免外层 Python MPI 与内层 ABACUS MPI 嵌套干扰。
- 多 MPI per image 作为后续独立增强项推进。

## 测试与验收计划

### 单元测试

- MPI launcher 环境下 bootstrap 能在 ASE import 前导入 `mpi4py`。
- MPI launcher 环境下缺少 `mpi4py` 时，错误信息明确且可操作。
- 普通 NEB 在 `world.size != len(images) - 2` 时抛出 `ValueError`。
- 普通 NEB 并行时每个 rank 只给一个 interior image 挂载 calculator。
- AutoNEB 在 `world.size != n_simul` 或 active `to_run` image 数不匹配时抛出 `ValueError`。
- AutoNEB 初始文件写入和 cleanup 仅在 rank 0 发生。

### 本地验证

```bash
conda run -n atst-dev pytest tests -q
conda run -n atst-dev atst run --dry-run examples/01_neb_Li-Si/config.yaml
conda run -n atst-dev atst run --dry-run examples/03_autoneb_Cy-Pt/config.yaml
```

### SAI 4V100 Slurm smoke

- 普通 NEB：
  - 4 个 interior images。
  - `mpirun -np 4 atst run config.yaml`
  - `max_steps: 1`
  - `calculator.abacus.mpi: 1`
- AutoNEB：
  - `n_simul: 4`
  - `mpirun -np 4 atst run config.yaml`
  - `maxsteps: 1`
  - `calculator.abacus.mpi: 1`
- 两个 smoke 均要求：
  - 加载 `abacus/LTSv3.10.1-sm70-auto`
  - 使用 4V100
  - ABACUS LCAO 输入包含 `ks_solver: cusolver`

### 验收标准

- 日志显示 `world.size == 4`。
- 不出现串行降级 warning。
- 产生 4 个 image-index ABACUS 工作目录。
- 任务能够正常完成一步优化。

## 文档更新要求

- 新增调研/实现报告，记录以下内容：
  - v1.5.1 legacy 基线
  - ASE 3.28.0 文档与源码判断
  - SAI MPI 环境
  - 最终设计边界
  - `abacuslite` upstream NEB example confirmation
- 更新 `docs/user/CONFIG_REFERENCE.md`：
  - `parallel: true` 在 MPI 环境下是严格 image 并行
  - 普通 NEB 要求 rank 数等于 interior images
  - AutoNEB 要求 rank 数等于 `n_simul`
- 更新 `docs/user/ABACUSLITE_WRAPPER_GUIDE.md` 和 `examples/README.md`：
  - 给出 `atst-neb-mpi` 环境创建命令
  - 说明外层 / 内层 MPI 区分
  - 提供 SAI Slurm smoke 模板
  - 明确多 MPI per image 暂不作为默认支持路径

## 假设、边界与非目标

- 本轮只覆盖 ABACUS-backed 普通 NEB 和 AutoNEB image 级并行。
- `abacuslite` 示例仅作为普通 NEB 的可行性依据和目录策略参考。
- AutoNEB 仍按 ASE AutoNEB 调度与 ATST wrapper 约束实现。
- DP、D2S image 并行不进入本轮实现。
- 串行 `atst run` 兼容性保留。
- 严格 topology 校验只在 effective ASE parallel mode 下生效。
- 多 Python ranks per image、per-image subcommunicator、multi-MPI-per-image 默认支持均不在本轮范围内。
