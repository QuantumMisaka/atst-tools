# ATST-Tools 重构指南与路线图 (Refactoring Guide & Roadmap)

**版本**: 1.2
**日期**: 2026-02-27
**状态**: 🚀 **RC 发布候选 (Release Candidate)**

---

## 1. 重构背景与愿景 (Background & Vision)

本项目（ATST-Tools）正处于从“科研脚本集合”向“现代 Python 工程项目”转型的关键阶段。我们的目标是构建一个基于 **ASE (Atomic Simulation Environment)** 的、高内聚低耦合的分子模拟工具库，**重点聚焦于过渡态计算相关功能**，同时支持 **ABACUS** 和 **Deep Potential (DP)** 等多种计算器。

**核心哲学 (Zen of Python)**:
- **Explicit is better than implicit**: 统一通过 `config.yaml` 显式定义工作流，而非隐藏在脚本硬编码中。
- **Simple is better than complex**: 对用户屏蔽底层的 MPI/并行处理细节，提供简洁的 CLI 入口。
- **There should be one-- and preferably only one --obvious way to do it**: 消除 `legacy` 目录下的重复脚本，确保 `atst-run` 是唯一的执行入口。

---

## 2. 现状评估 (Current Status Assessment)

### 2.1 架构断层 (The "Limbo" State)
项目目前呈现“新旧共存”的分裂状态：
*   **新架构 (`src/atst_tools`)**: 
    *   ✅ **优势**: 模块化设计 (`mep`, `workflows`, `calculators`)，统一入口 (`atst-run`)。
    *   ❌ **缺陷**: **强耦合 ABACUS**，导致无法扩展支持 DP；功能覆盖率仅约 60%。
*   **旧脚本 (`dimer/`, `neb/`, `ase-dp/` 等)**:
    *   ✅ **优势**: 功能完整，包含 DP 支持及振动分析等辅助工具。
    *   ❌ **缺陷**: 代码大量重复，参数硬编码，维护成本极高，严重污染项目根目录。

### 2.2 关键功能缺失 (Critical Gaps)
对比旧脚本，新架构目前存在以下严重缺失：
1.  **Deep Potential (DP) 支持**: `src` 中完全缺失 DP 适配器，导致无法复现 `ase-dp/` 中的功能。
2.  **振动分析 (Vibration)**: `vibration/vib_analysis.py` 尚未迁移，用户无法在新工作流中进行振动频率分析。
3.  **结构优化 (Relax)**: `relax/relax_run.py` 尚未迁移，基础的几何优化功能缺失。

### 2.3 技术债务 (Technical Debt)
1.  **根目录污染**: `dimer`, `neb`, `sella` 等文件夹与 `src` 并存，易导致 import 混淆。
2.  **配置结构缺陷**: `config.yaml` 将 ABACUS 参数直接平铺，缺乏 `calculator` 层的抽象，难以兼容其他计算器。
3.  **测试缺失**: 重构前未建立测试体系，导致重构过程缺乏回归保障。

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
    *   [x] **重构入口**: 修改 `atst-run` 以适配工厂模式。

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
    *   [x] **文档更新**: 全面更新 `docs/`，移除旧脚本使用说明，仅保留 `atst-run` 指南。
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
│   ├── abacus.py
│   └── dp.py
├── mep/               # 核心算法 (NEB, Dimer, Sella)
├── workflows/         # 高级工作流 (D2S, AutoNEB, Vib, Relax)
├── utils/             # 通用工具 (IO, Config, Plot)
└── scripts/           # CLI 入口 (仅包含参数解析与调度)
```

### 4.2 开发规范
*   **代码风格**: 严格遵循 PEP 8，使用 `black` 格式化，`flake8` 检查。
*   **类型提示**: 新增代码必须包含 Type Hints。
*   **测试驱动**: 修复 Bug 或新增功能时，必须在 `tests/` 下添加对应的单元测试。
*   **Import 规范**: 禁止使用相对引用跨越顶层模块，统一使用绝对引用 (e.g., `from atst_tools.utils import ...`)。

### 4.3 外部依赖集成策略 (Vendor Integration Strategy)

本项目采用 **"Vendor / Soft Fork"** 模式集成 `abacuslite`，而非作为外部 pip 依赖引入。这主要是为了解决版本兼容性与快速热修复的需求。

*   **上游仓库**: `deepmodeling/abacus-develop` (`interfaces/ASE_interface/abacuslite`)
*   **本地路径**: `src/atst_tools/external/ASE_interface/`
*   **同步策略**:
    1.  **按需同步**: 仅当上游有重大 Bug 修复或本项目需要的新功能时，手动从上游拉取代码。
    2.  **保留补丁**: 同步时必须小心保留本地的 `import` 路径修正（例如 `from atst_tools.external...`）。
    3.  **完整快照**: 保留整个 `ASE_interface` 目录，包含 `abacuslite/`、上游示例、测试和说明文档，便于后续与上游同步和独立验证。
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
**关键依赖**: `pytest`, `deepmd-kit`, `ase`, `abacuslite` (vendored)

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
