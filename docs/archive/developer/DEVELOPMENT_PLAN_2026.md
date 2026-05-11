# ATST-Tools 后续开发规划与架构升级方案

**版本**: 1.0  
**日期**: 2026-03-07  
**状态**: 草案 (Draft)  
**维护者**: ATST Team

---

## 1. 现状综述与痛点分析 (Situation Analysis)

### 1.1 现有架构 (Architecture)
本项目基于 `ASE` 框架，采用模块化设计，核心组件如下：
*   **Calculators**: 采用工厂模式 (`CalculatorFactory`) 统一管理 `abacuslite` (Vendor集成) 和 `DeepMD`。
*   **Workflows**: 封装了 `Relax`, `NEB`, `Vibration`, `D2S` 等高阶工作流。
*   **CLI**: 统一入口 `atst run`，通过 `config.yaml` 驱动任务。

### 1.2 基础设施与资源 (Infrastructure)
*   **计算资源**:
    *   **登录节点**: CPU-Only (Intel Xeon w9-3575X 88核, 754GB 内存)，禁止重负载计算。
    *   **GPU 节点**: `4V100` (4x V100 32GB) 和 `8V100V0` (8x V100 32GB) 分区，资源充裕。
    *   **调度系统**: Slurm，支持 QoS (`rush-gpu`, `huge-gpu` 等)。
*   **环境约束**:
    *   **ABACUS 版本**: `abacus/v3.9.0.17-sm70-auto` (GPU版) 和 `abacus/LTSv3.10.1-sm70-auto`。
    *   **运行要求**: 必须通过 `sbatch` 提交作业，且需加载特殊的 CUDA-MPS 映射脚本 (`/opt/sai_config/mps_mapping.d/...`)。
*   **依赖管理**: 采用 `conda` 环境 (`atst-dev`)，核心依赖包括 `ase`, `abacuslite` (vendored), `deepmd-kit`。

### 1.3 核心痛点 (Critical Pain Points)
1.  **运行适配困难**: 当前 `atst run` 默认使用 `mpirun` 直接启动，未适配集群的 `sbatch` + `mps_mapping` 模式，导致在登录节点无法运行，在计算节点可能因映射错误低效。
2.  **功能缺失**: `RelaxWorkflow` 仅支持原子坐标优化，不支持 **Cell-Relax (晶胞弛豫)**。
3.  **逻辑缺陷**: NEB 工作流在处理端点（Initial/Final Image）时未挂载 Calculator，导致 `get_forces()` 报错。
4.  **D2S 未闭环**: `d2s` 模块逻辑存在但未接入 `main.py`。

---

## 2. 开发规划 (Development Roadmap)

### 2.1 阶段一：核心修复与功能补全 (Core Fixes & Features)
**周期**: 2周 (Week 1-2)  
**目标**: 修复已知 Bug，实现 Relax/NEB/D2S 全功能闭环。

*   **Task 1.1: 修复 NEB 端点计算 Bug** (Priority: P0)
    *   **问题**: `ase.mep.NEB` 需要端点能量，但 `atst-tools` 未给端点挂载 Calculator。
    *   **方案**: 在 `run_neb` 中显式计算端点能量，或为端点 Image 赋予 Calculator（注意避免重复计算）。
    *   **验收**: `test_run_cli/neb` 案例成功运行无报错。

*   **Task 1.2: 实现 Cell-Relax 支持** (Priority: P0)
    *   **需求**: 支持优化晶胞参数。
    *   **方案**: 
        *   引入 `ase.filters.FrechetCellFilter` 或 `UnitCellFilter`。
        *   在 `config.yaml` 的 `relax` 部分新增 `variable_cell: true` 及 `mask` 参数。
        *   修改 `RelaxWorkflow`，若开启 `variable_cell` 则将 `atoms` 包装为 `Filter` 对象后传给 Optimizer。
    *   **验收**: 复现 `cellrelax.py` 案例，晶胞参数发生变化。

*   **Task 1.3: D2S 工作流接入** (Priority: P1)
    *   **需求**: 将 `d2s` 接入 `main.py`。
    *   **方案**: 在 `main.py` 的分发逻辑中增加 `elif calc_type == 'd2s':` 分支，实例化 `D2SWorkflow` 并运行。
    *   **验收**: `examples/08_d2s_Cy-Pt` 可通过 `atst run` 启动。

### 2.2 阶段二：集群适配与测试升级 (HPC Integration & Testing)
**周期**: 2周 (Week 3-4)  
**目标**: 完美适配 Slurm 环境，建立分层测试体系。

*   **Task 2.1: Slurm 作业提交辅助** (Priority: P1)
    *   **需求**: 用户在登录节点也能方便地提交 `atst run` 任务。
    *   **方案**:
        *   开发 `atst-submit` 命令或 `atst run --submit` 参数。
        *   自动生成符合 `/opt/sbatch_examples/gpu_abacus.sbatch` 规范的脚本。
        *   关键参数自动注入：`#SBATCH --partition`, `source mps_mapping.d`, `mpirun -map-by $MAP_OPT`。
    *   **验收**: `atst-submit config.yaml` 能成功投递作业并正确运行 ABACUS。

*   **Task 2.2: 建立 E2E 测试集** (Priority: P1)
    *   **内容**: 创建 `tests/e2e/`，包含 Relax, Cell-Relax, NEB, D2S 的最小化案例。
    *   **策略**: 使用 `EMT` Calculator (ASE内置) 替代真实的 ABACUS/DP，以在无 GPU 环境下快速验证工作流逻辑。

### 2.3 阶段三：性能优化与高级特性 (Performance & Advanced)
**周期**: 4周 (Week 5-8)  
**目标**: 提升并行效率，探索 Metadynamics。

*   **Task 3.1: ABACUS 并行优化** (Priority: P2)
    *   **痛点**: 目前 `mpirun` 调用方式较为僵硬。
    *   **方案**: 支持通过 Slurm 环境变量自动获取核数，优化 `CalculatorFactory` 的 MPI 参数传递。

*   **Task 3.2: Metadynamics 预研** (Priority: P3)
    *   **内容**: 调研 `abacuslite` 对 PLUMED 的支持，评估在 `atst-tools` 中集成 Metadynamics 工作流的可行性。

---

## 3. 协作规范与交付标准 (Collaboration Standards)

### 3.1 代码规范
*   **Style**: 严格遵循 PEP 8，使用 `black` 格式化。
*   **Docstring**: 所有新增类与函数必须包含 Google Style Docstring。
*   **Typing**: 核心模块必须包含 Type Hints。

### 3.2 版本控制
*   **分支模型**: Trunk-based development。
    *   `main`: 稳定主干，随时可发布。
    *   `feat/xxx`: 功能开发分支。
    *   `fix/xxx`: 修复分支。
*   **Commit Message**: Conventional Commits (e.g., `feat: add cell relax support`, `fix: neb endpoint calculator`).

### 3.3 文档维护
*   **同步更新**: 代码变更必须同步更新 `docs/` 下的对应文档。
*   **示例驱动**: 新功能必须在 `examples/` 下提供可运行的最小示例。

---

## 4. 资源需求 (Resource Requirements)

| 资源类型 | 规格/数量 | 用途 |
| :--- | :--- | :--- |
| **计算节点** | 1节点 (V100 GPU) | 真实物理场景 (ABACUS/DP) 的集成测试 |
| **开发人力** | 1-2 人 | 核心功能开发与测试编写 |
| **CI Runner** | Standard Linux | 运行 Lint, Unit Test, E2E (EMT) |

---

## 5. 附录：任务清单 (Task List)

- [ ] Task 1.1: 修复 NEB 端点 Calculator 问题
- [ ] Task 1.2: 实现 Cell-Relax (FrechetCellFilter)
- [ ] Task 1.3: 接入 D2S 工作流
- [ ] Task 2.1: 编写基于 EMT 的 E2E 测试
- [ ] Task 2.2: 完善文档与示例一致性检查脚本
