# ATST-Tools 重构执行计划 (Refactoring Execution Plan)

**版本**: 1.1
**最后更新**: 2026-02-25
**当前状态**: 🚀 **Sprint 1 进行中 (In Progress)**

---

## 🎯 立即行动 (Next Actions)

当前首要任务是完成核心引擎的解耦，为后续功能扩展打下基础。

*   **Priority 0**: 集成 `abacuslite` 官方插件，摆脱对 `ase-abacus` 的依赖。
*   **Priority 1**: 实现 `CalculatorFactory`，统一管理 ABACUS 和 DP 的实例化逻辑。
*   **Priority 2**: 重构 `atst-run` 入口，使其支持通过 `config.yaml` 动态选择计算器。

---

## 🟢 Sprint 1: 核心引擎切换 (Core Engine Switch)

**目标**: 建立基于 `CalculatorFactory` 的统一计算器管理机制，集成 `abacuslite`，并实现 DP 的安全调用。

### 1.1 集成 `abacuslite` (Dependency Management)
*   **背景**: 废弃庞大的 `ase-abacus` submodule，转用轻量级官方插件，解决版本兼容性问题。
*   **执行步骤**:
    1.  [ ] **获取源码**: 从 `deepmodeling/abacus-develop` 仓库的 `interfaces/ASE_interface` 目录获取代码。
    2.  [ ] **Vendor 集成**: 将代码复制到 `src/atst_tools/external/abacuslite/`。
    3.  [ ] **依赖清理**: 移除 `.gitmodules` 中的 `deps/ase-abacus` 及相关配置。
    4.  [ ] **环境配置**: 在 `pyproject.toml` 中添加 `abacuslite` 所需依赖（如 `seekpath`, `scipy`）。

### 1.2 实现 `CalculatorFactory` (Design Pattern)
*   **背景**: 解耦 `main.py` 与具体计算器实现，支持多计算器扩展，实现“开闭原则”。
*   **执行步骤**:
    1.  [ ] **创建工厂**: 新建 `src/atst_tools/calculators/factory.py`。
    2.  [ ] **定义接口**: 实现 `get_calculator(name, config, **kwargs) -> Calculator`。
    3.  [ ] **ABACUS 适配**:
        *   在工厂中处理 `abacus` 类型。
        *   实现参数映射层：将旧版 config (`pp`, `basis`) 映射为 `abacuslite` 要求的 (`pseudopotentials`, `basissets`)。
    4.  [ ] **DeepMD 适配 (关键)**:
        *   **单例控制**: 实现 `_dp_instances` 缓存池。
        *   **逻辑**: 当 `parallel=False` (串行/多Image) 时，复用同一模型实例以节省显存；当 `parallel=True` (MPI并行) 时，强制返回新实例。

### 1.3 重构入口 `atst-run`
*   **背景**: `main.py` 目前逻辑混乱，强耦合。
*   **执行步骤**:
    1.  [ ] **配置升级**: 更新 `config.yaml` Schema，明确分离 `calculator` (引擎配置) 与 `calculation` (任务配置)。
    2.  [ ] **代码重构**: 修改 `src/atst_tools/scripts/main.py`，移除硬编码的 import，改为调用 `get_calculator`。
    3.  [ ] **回归测试**: 验证最简单的 SCF 任务能否跑通。

---

## 🟡 Sprint 2: 工作流迁移与修复 (Workflow Migration)

**目标**: 恢复并增强 DP 支持，迁移 Relax/Vibration 功能，达到 Feature Parity（功能对齐）。

### 2.1 恢复 Deep Potential 支持
*   **背景**: `ase-dp/` 下的功能目前在新架构中不可用，需移植到标准架构。
*   **执行步骤**:
    1.  [ ] **新建适配器**: 创建 `src/atst_tools/calculators/dp.py` (如果 Factory 逻辑复杂，可独立出此文件)。
    2.  [ ] **集成测试**: 编写 `tests/integration/test_dp_neb.py`，重点验证：
        *   单卡多 Image (Shared Calculator) 的显存占用。
        *   多卡多 Image (MPI) 的并行效率。

### 2.2 迁移 `Relax` (结构优化)
*   **背景**: 基础几何优化功能缺失。
*   **执行步骤**:
    1.  [ ] **新建模块**: `src/atst_tools/workflows/relax.py`。
    2.  [ ] **功能实现**: 封装 `ase.optimize`，支持 BFGS, FIRE, LBFGS 等优化器。
    3.  [ ] **轨迹保存**: 确保优化过程的 `Trajectory` 被正确保存，且支持断点续算。

### 2.3 迁移 `Vibration` (振动分析)
*   **背景**: 过渡态确认的关键步骤。
*   **执行步骤**:
    1.  [ ] **新建模块**: `src/atst_tools/workflows/vibration.py`。
    2.  [ ] **功能实现**: 封装 `ase.vibrations.Vibrations`。
    3.  [ ] **配置支持**: 支持从 config 读取 `delta` (位移步长) 和 `indices` (指定原子)。

---

## 🔵 Sprint 3: 清理与高级特性 (Cleanup & Advanced)

**目标**: 移除遗留代码，发布 v2.0，探索 Metadynamics。

### 3.1 彻底清理 (Purge)
*   **执行步骤**:
    1.  [ ] **删除遗留目录**: `ase-dp/`, `dimer/`, `neb/`, `relax/`, `sella/`, `vibration/`。
    2.  [ ] **更新示例**: 将 `examples/` 下的旧版脚本全部替换为基于 `atst-run` + `config.yaml` 的新示例。
    3.  [ ] **文档清洗**: 移除所有关于旧脚本的文档引用。

### 3.2 扩展功能 (Future)
*   **执行步骤**:
    1.  [ ] **Metadynamics**: 探索通过 `abacuslite` + `plumed` 支持元动力学计算。
    2.  [ ] **Band Structure**: 集成 `seekpath`，支持自动能带路径生成与计算。

---

## 🛡️ 开发规范与检查点 (Standards & Checkpoints)

### 目录结构预览
```text
src/atst_tools/
├── calculators/
│   ├── __init__.py
│   ├── factory.py          # [Core] 计算器工厂
│   ├── base.py
│   └── dp.py               # [New] DP 适配器
├── external/
│   └── abacuslite/         # [Vendor] ABACUS 官方插件
├── workflows/
│   ├── relax.py            # [New] 结构优化
│   └── vibration.py        # [New] 振动分析
└── scripts/
    └── main.py             # [Refactored] 统一入口
```

### 验证标准
1.  **安装测试**: `pip install .` 在新环境中无报错，且 `atst-run --help` 正常输出。
2.  **ABACUS 兼容性**: `atst-run` 能正确调用 `abacuslite` 并完成 NEB 计算。
3.  **DP 显存优化**: 在 8GB 显存 GPU 上，`atst-run` (DP模式) 能跑通 16 Image 的 NEB 计算（证明 Shared Instance 生效）。
