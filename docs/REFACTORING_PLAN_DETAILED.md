# ATST-Tools 重构执行计划 (Refactoring Execution Plan)

**版本**: 1.0  
**日期**: 2026-02-25  
**状态**: 规划中  

本文档详细拆解了 `REFACTORING_GUIDE.md` 中的重构路线，将其转化为可执行的三个 Sprint（冲刺阶段）。

---

## 🟢 Sprint 1: 核心引擎切换 (Core Engine Switch)
**目标**: 建立基于 `CalculatorFactory` 的统一计算器管理机制，集成 `abacuslite`，并实现 DP 的安全调用。

### 1.1 集成 `abacuslite` (Dependency Management)
*   **背景**: 废弃庞大的 `ase-abacus` submodule，转用轻量级官方插件。
*   **任务**:
    1.  从 `deepmodeling/abacus-develop` 获取 `abacuslite` 源码。
    2.  将其 "Vendor" (内嵌) 到 `src/atst_tools/external/abacuslite` 目录，确保项目自包含。
    3.  移除 `.gitmodules` 中的 `deps/ase-abacus`。
    4.  在 `pyproject.toml` 中添加 `seekpath` 等 `abacuslite` 所需依赖。

### 1.2 实现 `CalculatorFactory` (Design Pattern)
*   **背景**: 解耦 `main.py` 与具体计算器实现，支持多计算器扩展。
*   **任务**:
    1.  创建 `src/atst_tools/calculators/factory.py`。
    2.  定义统一接口 `get_calculator(name, config, **kwargs)`。
    3.  **ABACUS 适配**: 调用 `abacuslite`，处理参数映射 (`pp` -> `pseudopotentials`)。
    4.  **DeepMD 适配**:
        *   引入 `shared` 参数控制。
        *   **Parallel=False**: 实现单例模式，复用 `DP` 实例（节省显存）。
        *   **Parallel=True**: 强制返回新实例（保证安全）。

### 1.3 重构入口 `atst-run`
*   **背景**: `main.py` 目前逻辑混乱，强耦合。
*   **任务**:
    1.  更新 `config.yaml` 规范，分离 `calculator` 配置块。
    2.  修改 `src/atst_tools/scripts/main.py`，使用 Factory 创建计算器。
    3.  通过单元测试验证基础 SCF 计算。

---

## 🟡 Sprint 2: 工作流迁移与修复 (Workflow Migration)
**目标**: 恢复并增强 DP 支持，迁移 Relax/Vibration 功能，达到 Feature Parity（功能对齐）。

### 2.1 恢复 Deep Potential 支持
*   **背景**: `ase-dp/` 下的功能目前在新架构中不可用。
*   **任务**:
    1.  在 `main.py` 中启用 `type: dp` 支持。
    2.  编写 `tests/integration/test_dp_neb.py`，验证 NEB 在串行（共享实例）和并行（独立实例）下的稳定性。

### 2.2 迁移 `Relax` (结构优化)
*   **背景**: 基础功能缺失。
*   **任务**:
    1.  创建 `src/atst_tools/workflows/relax.py`。
    2.  实现基于 `ase.optimize` 的通用优化流程（支持 BFGS, FIRE 等）。
    3.  集成 `Trajectory` 保存逻辑。

### 2.3 迁移 `Vibration` (振动分析)
*   **背景**: 过渡态确认的关键步骤。
*   **任务**:
    1.  创建 `src/atst_tools/workflows/vibration.py`。
    2.  封装 `ase.vibrations.Vibrations`。
    3.  支持从 `config.yaml` 读取 `delta` (位移量) 和 `indices` (原子索引)。

---

## 🔵 Sprint 3: 清理与高级特性 (Cleanup & Advanced)
**目标**: 移除遗留代码，发布 v2.0，探索 Metadynamics。

### 3.1 彻底清理 (Purge)
*   **任务**:
    1.  删除根目录下的 `ase-dp/`, `dimer/`, `neb/`, `relax/`, `sella/`, `vibration/`。
    2.  删除 `examples/` 下的旧版脚本，替换为 YAML 配置驱动的新示例。

### 3.2 扩展功能 (Future)
*   **任务**:
    1.  初步支持 `Metadynamics` (通过 `abacuslite` + `plumed`)。
    2.  支持 `Band Structure` 计算工作流。

---

## 🛡️ 开发规范与检查点

### 代码结构变更预览
```text
src/atst_tools/
├── calculators/
│   ├── __init__.py
│   ├── factory.py          # [NEW] 核心工厂
│   ├── base.py
│   └── dp.py               # [NEW] DP 适配器
├── external/
│   └── abacuslite/         # [NEW] 内嵌官方插件
├── workflows/
│   ├── relax.py            # [NEW]
│   └── vibration.py        # [NEW]
└── scripts/
    └── main.py             # [REFACTORED]
```

### 验证标准
1.  **安装测试**: `pip install .` 在新环境中无报错。
2.  **ABACUS 测试**: `atst-run config_abacus.yaml` 能成功跑通 NEB。
3.  **DP 测试**: `atst-run config_dp.yaml` 能在 8GB 显存 GPU 上跑通 16 Image 的串行 NEB（证明共享实例生效）。
