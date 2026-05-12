# ATST-Tools 重构指南与路线图 (Refactoring Guide & Roadmap)

**版本**: 1.2
**日期**: 2026-02-27
**状态**: 已归档；重构任务已完成

> 本文档记录 ATST-Tools 从科研脚本集合重构为正式 Python package 的历史路线与完成状态。后续活跃开发规范请参考 `docs/developer/` 下的专题文档；YAML 输入治理规范已迁移到 `docs/developer/YAML_INPUT_GOVERNANCE.md`。

---

## 1. 项目概述 (Project Overview)

ATST-Tools 是一个基于 **ASE (Atomic Simulation Environment)** 的、高内聚低耦合的分子模拟工具库，**重点聚焦于过渡态计算相关功能**，同时支持 **ABACUS** 和 **Deep Potential (DP)** 等多种计算器。

**核心哲学 (Zen of Python)**:
*   **Explicit is better than implicit**: 统一通过 `config.yaml` 显式定义工作流，而非隐藏在脚本硬编码中。
*   **Simple is better than complex**: 对用户屏蔽底层的 MPI/并行处理细节，提供简洁的 CLI 入口。
*   **There should be one-- and preferably only one --obvious way to do it**: 确保 `atst run` 是唯一的执行入口。

**版本**: 2.0.0-rc

---

## 2. 现状评估 (Current Status Assessment)

### 2.1 重构完成 (Refactoring Complete)
项目已完成从“科研脚本集合”到“现代 Python 包”的完整重构：
*   **新架构 (`src/atst_tools`)**: 
    *   ✅ **模块化设计**: `mep/`, `workflows/`, `calculators/`, `utils/`, `scripts/` 清晰分离。
    *   ✅ **统一入口**: `atst run config.yaml` 作为唯一执行入口，支持所有工作流。
    *   ✅ **计算器解耦**: `CalculatorFactory` 支持 ABACUS/DP 无缝切换。
    *   ✅ **功能覆盖率**: NEB/AutoNEB/Dimer/Sella/D2S/Relax/Vibration/IRC 全部实现。
*   **旧脚本**: 已全部删除，根目录保持整洁。

### 2.2 功能完整性 (Feature Completeness)
✅ 所有核心功能已实现并通过 SAI 实算回归验证：
1.  **Deep Potential (DP)**: 完整支持，`share_calculator` 显存优化已实现。
2.  **振动分析 (Vibration)**: 支持 Harmonic 和理想气体模型的热化学分析。
3.  **结构优化 (Relax)**: 支持 BFGS/FIRE/LBFGS 优化器。
4.  **D2S 工作流**: 从粗搜索到精搜索的完整流程已实现。

### 2.3 技术质量 (Technical Quality)
1.  **根目录整洁**: 仅保留必要文件，所有功能集中在 `src/atst_tools/`。
2.  **配置统一管理**: 基于 Pydantic schema 的 `config.yaml` 结构，支持类型校验和文档自动生成。
3.  **测试覆盖**: 70+ 单元测试覆盖 CLI、配置、工厂、工作流、工具函数。

### 2.4 ASE 接口集成现状 (Current ASE Integration)

**ABACUS**
*   **核心模块**: 目前项目依赖 `ase-abacus` 子模块（`deps/ase-abacus`），这是一个包含 ABACUS 支持的 ASE 完整 Fork 版本。
*   **最新进展**: ABACUS 官方仓库 (`deepmodeling/abacus-develop`) 已推出 **`abacuslite`** 插件。
    *   **优势**: 轻量级、官方维护。
    *   **决策**: 本项目应废弃 `ase-abacus` 子模块，转为依赖 `abacuslite`。
    *   **限制**: 目前集成仅专注于**能量与力**的计算，以支持几何优化和过渡态搜索。**NSCF、能带、态密度等高级电子结构分析功能暂不支持**。

**Deep Potential (DP)**
*   **核心模块**: `deepmd.calculator.DP` (基于 `deepmd-kit` 官方库)。
*   **接口规范**: 继承自 `ase.calculators.calculator.Calculator`。
*   **关键约束**: 
    *   **并行场景 (parallel=True)**: 严禁共享实例。
    *   **串行场景 (parallel=False)**: 强烈建议**启用实例共享** (`allow_shared_calculator=True`)。

---

## 3. 重构路线图 (Refactoring Roadmap)

### Phase 1: 基础设施 (Foundation) ✅ **[已完成]**
*   **目标**: 建立标准的 Python 包结构与开发环境。
*   **成果**:
    *   [x] 创建 `pyproject.toml`，支持 `pip install .` 安装。
    *   [x] 建立 `tests/` 目录结构与 `pytest` 配置。
    *   [x] 配置 `.pre-commit-config.yaml` (Black, Isort, Flake8)。
    *   [x] 创建开发分支 `refactor/unify-structure`。

### Phase 2: 核心解耦 (Core Decoupling) ✅ **[已完成]**
*   **目标**: 打破 `main.py` 与 `AbacusCalculator` 的强绑定，实现计算器插件化。
*   **成果**:
    *   [x] **定义计算器接口**: 在 `src/atst_tools/calculators/base.py` 中定义协议。
    *   [x] **实现工厂模式**: 创建 `src/atst_tools/calculators/factory.py`，根据 config 动态加载计算器 (ABACUS/DP)。
    *   [x] **重构配置结构**: 升级 `config.yaml` Schema，分离 `calculation` (任务) 与 `calculator` (计算引擎) 参数。
    *   [x] **重构入口**: 修改 `atst run` 以适配工厂模式。

### Phase 3: 功能迁移与补全 (Migration) ✅ **[已完成]**
*   **目标**: 将遗留脚本的功能完全移植到新架构，达到 Feature Parity。
*   **成果**:
    *   [x] **DP 迁移**: 将 `ase-dp/*.py` 逻辑移植为 `DeepPotentialCalculator` 及相关 Workflow。
    *   [x] **Vibration 迁移**: 将 `vibration/vib_analysis.py` 重构为 `src/atst_tools/workflows/vibration.py`。
    *   [x] **Relax 迁移**: 新增 `src/atst_tools/workflows/relax.py`。
    *   [x] **工具迁移**: 整理 `neb_post.py` 等后处理脚本至 `src/atst_tools/utils`。

### Phase 4: 清理与发布 (Cleanup & Release) ✅ **[已完成]**
*   **目标**: 移除所有遗留代码，发布 v2.0 正式版。
*   **成果**:
    *   [x] **彻底删除**: `dimer/`, `neb/`, `relax/`, `sella/`, `vibration/`, `ase-dp/`。
    *   [x] **文档更新**: 全面更新 `docs/`，移除旧脚本使用说明，仅保留 `atst run` 指南。
    *   [x] **示例更新**: 将 `examples/` 下的所有脚本示例更新为 YAML 配置驱动的示例。

---

## 4. 技术规范与约束 (Technical Standards)

### 4.1 目录结构标准
```text
src/atst_tools/
├── calculators/       # 计算器适配层 (Abacus, DP, etc.)
│   ├── __init__.py
│   ├── base.py        # 抽象基类
│   ├── factory.py     # 工厂入口
│   ├── abacuslite_backend.py  # ABACUS 后端
│   └── dp.py          # DeepMD 后端
├── mep/               # 核心算法 (NEB, AutoNEB, Dimer, Sella)
├── workflows/         # 高级工作流 (D2S, IRC, Relax, Vibration)
├── utils/             # 通用工具 (IO, Config, IDPP, Thermochemistry, etc.)
├── scripts/           # CLI 入口 (main.py, cli.py)
└── external/          # vendored 依赖 (abacuslite ASE_interface)
```

### 4.2 开发规范
*   **代码风格**: 严格遵循 PEP 8，使用 `black` 格式化，`flake8` 检查。
*   **类型提示**: 新增代码必须包含 Type Hints。
*   **测试驱动**: 修复 Bug 或新增功能时，必须在 `tests/` 下添加对应的单元测试。
*   **Import 规范**: 禁止使用相对引用跨越顶层模块，统一使用绝对引用 (e.g., `from atst_tools.utils import ...`)。

### 4.3 外部依赖集成策略 (Backend Integration Strategy)

本项目采用 **外部安装优先 + vendored fallback** 的过渡策略集成 `abacuslite`。运行时优先导入用户环境中独立安装的 `abacuslite`；如果不可用，再回退到 `src/atst_tools/external/ASE_interface/` 中的快照。

*   **上游仓库**: `deepmodeling/abacus-develop` (`interfaces/ASE_interface/abacuslite`)
*   **本地 fallback 路径**: `src/atst_tools/external/ASE_interface/`
*   **解析入口**: `src/atst_tools/calculators/abacuslite_backend.py`
*   **长期方向**: 当 `abacuslite` 有稳定发布源后，将其改为 optional dependency 或 extras，并逐步移除 vendored fallback。
*   **同步策略**:
    1.  **按需同步**: 仅当上游有重大 Bug 修复或本项目需要的新功能时，手动从上游拉取代码。
    2.  **保持上游形态**: `ASE_interface` 本身带 `pyproject.toml`，可单独 `pip install .`；ATST-Tools 只消费该 backend。
    3.  **完整快照**: 2.0.0-rc 保留整个 `ASE_interface` 目录，包含 `abacuslite/`、上游示例、测试和说明文档，便于后续与上游同步和独立验证。
    4.  **文档记录**: 每次同步需在 `CHANGELOG` 或 Commit Message 中注明上游 Commit ID。

---

## 5. 迁移指南 (Migration Quick Guide)

对于开发者，如何判断代码应该放在哪里？

*   **是新的计算引擎？** -> `src/atst_tools/calculators/`
*   **是新的过渡态搜索算法？** -> `src/atst_tools/mep/`
*   **是多步骤的复杂任务？** -> `src/atst_tools/workflows/`
*   **是简单的文件处理？** -> `src/atst_tools/utils/`

**注意**: 严禁在项目根目录创建新的功能文件夹。

---

## 6. 开发环境配置 (Development Environment)

为了保证开发一致性，本项目推荐使用 `conda` 管理开发环境。

### 6.1 已配置的开发环境 (Pre-configured Environment)

**环境名称**: `atst-dev`
**Python 版本**: 3.10
**关键依赖**: `pytest`, `deepmd-kit`, `ase`, `abacuslite` (external install or vendored fallback)

### 6.2 激活与测试

1.  **激活环境**:
    ```bash
    conda activate atst-dev
    ```

2.  **安装项目 (Editable Mode)**:
    在项目根目录下执行，确保源码修改即时生效：
    ```bash
    pip install -e .
    ```

3.  **运行测试**:
    执行全套单元测试（包含 DP 集成测试）：
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/src && pytest tests/
    ```

### 6.3 常用开发命令

*   **运行测试**: `pytest`
*   **代码检查**: `pre-commit run --all-files`
*   **构建文档**: (待补充)

### 6.4 测试环境 (Testing Environment)

本项目依赖以下外部软件进行集成测试。开发人员可使用 Environment Modules 加载：

*   **ABACUS**: `module load abacus/LTSv3.10.1-sm70-auto`
    *   用途: 验证 `AbacusCalculator` 及相关工作流。
    *   注意: 这是一个基于 CUDA 的版本，需在 GPU 节点运行；默认 LCAO 示例使用 `ks_solver: cusolver`。
*   **DeepMD-kit**: `module load deepmd-kit/3.1.2`
    *   用途: 验证 DP 支持及 ASE 接口。
*   **MPI**: `module load openmpi/4.1.6-nvhpc24.3` (或系统默认)
    *   用途: 支持 ABACUS 的并行运行。

**推荐测试流程**:
```bash
# 1. 加载模块
module load abacus/v3.9.0.17-sm70-auto
module load deepmd-kit/3.1.2

# 2. 运行测试
pytest tests/integration
```

### 6.5 暂不支持的功能与未来规划 (Unsupported / Future Capabilities)

虽然 `abacuslite` 理论上支持更多功能，但本项目当前**仅专注于**过渡态与结构优化。以下功能在当前版本中**不支持且不计划支持**：

*   **电子结构分析 (Electronic Structure)**:
    *   ❌ NSCF (Non-Self-Consistent Field)
    *   ❌ Band Structure (能带)
    *   ❌ DOS (态密度)

以下功能在当前版本中**不支持，但有计划支持**：

*   **Metadynamics (元动力学)**:
    *   ❌ PLUMED 接口集成
*   **高级分子动力学 (Advanced MD)**:
    *   ❌ 约束 MD (Constraint MD)

建议开发者集中精力优化 NEB/Sella/Dimer 等核心工作流的稳定性，而非扩展上述非核心功能。
