# ATST-Tools 重构指南与路线图 (Refactoring Guide & Roadmap)

**版本**: 1.0  
**日期**: 2026-02-24  
**状态**: 进行中 (Phase 1 Completed)

---

## 1. 重构背景与愿景 (Background & Vision)

本项目（ATST-Tools）正处于从“科研脚本集合”向“现代 Python 工程项目”转型的关键阶段。我们的目标是构建一个基于 **ASE (Atomic Simulation Environment)** 的、高内聚低耦合的过渡态计算工具库，同时支持 **ABACUS** 和 **Deep Potential (DP)** 等多种计算器。

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
*   **最新进展 (Future Direction)**: ABACUS 官方仓库 (`deepmodeling/abacus-develop`) 已推出 **`abacuslite`** 插件（位于 `interfaces/ASE_interface`）。
    *   **优势**: 轻量级（独立包，非 ASE Fork）、官方维护、支持新特性（如 NSCF `fixed_density`）。
    *   **差异**:
        *   包名变更: `ase.calculators.abacus` -> `abacuslite.core`。
        *   参数变更: `pp` -> `pseudopotentials`, `basis` -> `basissets`, `basis_dir` -> `orbital_dir`。
    *   **决策**: 本项目应废弃 `ase-abacus` 子模块，转为依赖 `abacuslite`。由于 `abacuslite` 尚未发布到 PyPI，建议通过 Git 依赖或源码集成方式引入。

**Deep Potential (DP)**
*   **核心模块**: `deepmd.calculator.DP` (基于 `deepmd-kit` 官方库)。
*   **接口规范**: 继承自 `ase.calculators.calculator.Calculator`。
*   **关键约束**: 
    *   **并行场景 (parallel=True)**: 严禁共享实例。每个 MPI Rank 上的 Image 必须拥有独立的 Calculator 实例 (`allow_shared_calculator=False`)。
    *   **串行场景 (parallel=False)**: 强烈建议**启用实例共享** (`allow_shared_calculator=True`)。DeepMD 模型（尤其是 `DeepPot` 图对象）占用大量显存，若为每个 Image 创建独立实例，显存将随 Image 数量线性增长，极易 OOM。
    *   **实现策略**: 在 `calculators/factory.py` 中增加 `create_instance(..., shared=False)` 方法。若 `shared=True`，则返回单例对象。
*   **重构点**: 
    *   在 `calculators/factory.py` 中，对于 DP 类型的任务，工厂方法必须支持 `shared` 参数控制。
    *   需在 `pyproject.toml` 中添加 `deepmd-kit` 作为可选依赖 (`extras_require`)。

---

## 3. 重构路线图 (Refactoring Roadmap)

### Phase 1: 基础设施 (Foundation) ✅ **[已完成]**
*   **目标**: 建立标准的 Python 包结构与开发环境。
*   **成果**:
    *   [x] 创建 `pyproject.toml`，支持 `pip install .` 安装。
    *   [x] 建立 `tests/` 目录结构与 `pytest` 配置。
    *   [x] 配置 `.pre-commit-config.yaml` (Black, Isort, Flake8)。
    *   [x] 创建开发分支 `refactor/unify-structure`。

### Phase 2: 核心解耦 (Core Decoupling) 🚧 **[进行中]**
*   **目标**: 打破 `main.py` 与 `AbacusCalculator` 的强绑定，实现计算器插件化。
*   **任务**:
    1.  **定义计算器接口**: 在 `src/atst_tools/calculators/base.py` 中定义协议。
    2.  **实现工厂模式**: 创建 `src/atst_tools/calculators/factory.py`，根据 config 动态加载计算器 (ABACUS/DP)。
    3.  **重构配置结构**: 升级 `config.yaml` Schema，分离 `calculation` (任务) 与 `calculator` (计算引擎) 参数。
    4.  **重构入口**: 修改 `atst-run` 以适配工厂模式。

### Phase 3: 功能迁移与补全 (Migration) 📅 **[待启动]**
*   **目标**: 将遗留脚本的功能完全移植到新架构，达到 Feature Parity。
*   **任务**:
    1.  **DP 迁移**: 将 `ase-dp/*.py` 逻辑移植为 `DeepPotentialCalculator` 及相关 Workflow。
    2.  **Vibration 迁移**: 将 `vibration/vib_analysis.py` 重构为 `src/atst_tools/workflows/vibration.py`。
    3.  **Relax 迁移**: 新增 `src/atst_tools/workflows/relax.py`。
    4.  **工具迁移**: 整理 `neb_post.py` 等后处理脚本至 `src/atst_tools/utils`。

### Phase 4: 清理与发布 (Cleanup & Release) 📅 **[待启动]**
*   **目标**: 移除所有遗留代码，发布 v2.0 正式版。
*   **任务**:
    1.  **彻底删除**: `dimer/`, `neb/`, `relax/`, `sella/`, `vibration/`, `ase-dp/`。
    2.  **文档更新**: 全面更新 `docs/`，移除旧脚本使用说明，仅保留 `atst-run` 指南。
    3.  **示例更新**: 将 `examples/` 下的所有脚本示例更新为 YAML 配置驱动的示例。

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

### 6.1 创建与激活环境

```bash
# 1. 创建名为 atst-dev 的 Python 3.10 环境
conda create -n atst-dev python=3.10 -y

# 2. 激活环境
conda activate atst-dev

# 3. 安装核心依赖
pip install --upgrade pip
pip install "ase>=3.22.1" numpy scipy matplotlib ruamel.yaml
pip install pytest pre-commit  # 开发工具

# 4. 以可编辑模式安装本项目
# 确保在项目根目录执行
pip install -e .
```

### 6.2 常用开发命令

*   **运行测试**: `pytest`
*   **代码检查**: `pre-commit run --all-files`
*   **构建文档**: (待补充)

### 6.4 测试环境 (Testing Environment)

本项目依赖以下外部软件进行集成测试。开发人员可使用 Environment Modules 加载：

*   **ABACUS**: `module load abacus/v3.9.0.17-sm70-auto` (敏捷版) 或 `module load abacus/LTSv3.10.1-sm70-auto` (稳定版)
    *   用途: 验证 `AbacusCalculator` 及相关工作流。
    *   注意: 这是一个基于 CUDA 的版本，需在 GPU 节点运行。
    *   **版本兼容性**: `abacuslite` 接口已设计为兼容 v3.9.0.x (敏捷开发版) 和 LTS v3.10.x (长期支持版)。开发时应覆盖这两个版本的测试。
        *   v3.9.0.x: 采用 Legacy IO 模式。
        *   v3.10.x: 采用 Latest IO 模式 (支持更完善的结构文件格式)。
*   **DeepMD-kit**: `module load deepmd-kit/3.1.2`
    *   用途: 验证 DP 支持及 ASE 接口。
    *   注意: 加载此模块可能会自动配置好 Python 环境中的 deepmd-kit 库，无需重复 pip 安装。开发时请优先使用模块提供的环境。
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

### 6.5 扩展功能支持 (Future Capabilities)

基于 `abacuslite` 插件的分析，除了核心的 NEB/Sella 搜索外，本项目未来可轻松扩展以下功能：

*   **Metadynamics (元动力学)**:
    *   原理: 利用 `ase.calculators.plumed` 包装 `AbacusCalculator`。
    *   实现: 需安装 `plumed` 和 `py-plumed`。用户可通过 `config.yaml` 定义 CV (集合变量) 和 Bias (偏置势)。
    *   参考: `abacuslite/examples/metadynamics.py`。
*   **分子动力学 (MD)**:
    *   支持: NVE, NVT (Bussi/CSVR, Langevin), NPT。
    *   参考: `abacuslite/examples/md.py`, `constraintmd.py`。
*   **电子结构分析**:
    *   支持: Band Structure (能带), DOS (态密度)。
    *   特性: 支持 NSCF 计算 (`fixed_density` 方法) 和能带路径自动生成 (`seekpath` 集成)。
    *   参考: `abacuslite/examples/bandstructure.py`。

建议在 `src/atst_tools/workflows` 中预留这些模块的接口。
