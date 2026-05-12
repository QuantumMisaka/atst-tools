# ATST-Tools 项目文档

## 1. 项目概述 (Project Overview)

**ATST-Tools (Advanced ASE Transition State Tools)** 是一个基于 Python 的工具集，旨在为 **ABACUS** 和 **Deep-Potential** 计算器提供高级的过渡态（Transition State, TS）搜索和分析功能。该项目基于 **ASE (Atomic Simulation Environment)** 框架构建，并扩展了 ASE 原有的 NEB 和 Dimer 方法，使其更适配 ABACUS 和 DP 的计算流程。

**v2.0.0 重大更新**：
*   **重构架构**: 引入了 `CalculatorFactory`，实现了计算引擎（ABACUS/DP）与工作流的完全解耦。
*   **统一入口**: 所有计算任务统一通过 `atst run` 命令行工具和 `config.yaml` 配置文件驱动。
*   **功能对齐**: 完整支持 Deep Potential (DP) 工作流，包括显存优化的多 Image 并行计算。
*   **新工作流**: 新增了结构优化 (Relax) 和振动分析 (Vibration) 模块。

## 2. 核心功能 (Core Features)

### 2.1 计算引擎支持
*   **ABACUS**: 通过官方 `abacuslite` 插件集成，支持最新的 ABACUS 输入格式。
*   **Deep Potential (DP)**: 内置 DP 适配器，支持 `deepmd-kit` 模型。
    *   **Smart Sharing**: 在串行模式下自动复用模型实例，大幅降低显存占用（支持单卡跑通 16+ Images）。

### 2.2 过渡态搜索 (MEP)
*   **NEB (Nudged Elastic Band)**: 支持传统的 NEB、CI-NEB (Climbing Image) 和 IT-NEB (Improved Tangent)。
*   **AutoNEB**: 自动化的 NEB 工作流，动态增加图像并聚焦鞍点。
*   **Dimer / Sella**: 支持从 NEB 路径最高点出发，使用 Dimer 或 Sella 方法进行精确鞍点搜索。

### 2.3 辅助工作流
*   **Relax**: 几何结构优化，支持 BFGS, FIRE, LBFGS 等多种优化器。
*   **Vibration**: 振动频率分析与零点能 (ZPE) 计算，支持自定义原子选区。

## 3. 快速上手 (Quick Start)

### 3.1 安装
```bash
# 推荐创建独立环境
conda create -n atst python=3.10
conda activate atst

# 安装本项目
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install .
```

### 3.2 运行任务
所有任务均通过 `atst run` 命令执行，由配置文件指定任务类型。

#### 示例 1: ABACUS NEB 计算
创建 `config.yaml`:
```yaml
calculation:
  type: neb
  init_chain: init_neb_chain.traj
  climb: true
  fmax: 0.05
  parallel: true  # 开启 MPI 并行

calculator:
  name: abacus
  abacus:
    command: abacus
    mpi: 4
    omp: 1
    directory: run_neb
    parameters:
        calculation: scf
        ecutwfc: 60
        pseudopotentials:
           H: H_ONCV_PBE-1.0.upf
           Au: Au_ONCV_PBE-1.0.upf
        basissets:
           H: H_gga_6au_100Ry_2s1p.orb
           Au: Au_gga_7au_100Ry_4s2p2d1f.orb
```
运行:
```bash
atst run config.yaml
```

#### 示例 2: Deep Potential 结构优化
创建 `config_relax.yaml`:
```yaml
calculation:
  type: relax
  init_structure: init.stru
  fmax: 0.01
  optimizer: BFGS

calculator:
  name: dp
  dp:
    model: frozen_model.pb
    head: null  # DPA/DPA3 multi-head 模型按需设置
    share_calculator: true
```
运行:
```bash
atst run config_relax.yaml
```

### 3.3 配置 Schema（字段说明）
`atst run` 会通过 Pydantic schema 校验并补齐 YAML 默认值。除结构输入、NEB 初始链/生成输入、DP model 等必须由用户指定的变量外，常用算法变量都有默认值。完整字段表见 `docs/user/CONFIG_REFERENCE.md`。

- calculation
  - type: neb|autoneb|dimer|sella|relax|vibration|d2s
  - init_chain|init_structure: 初始路径或结构文件
  - climb/fmax/optimizer/parallel: 算法控制参数
- calculator
  - name: abacus|dp
  - abacus: command|mpi|omp|directory|parameters（pseudopotentials|basissets|xc|ecutwfc 等）
  - dp: model|head|type_map|type_dict|omp|share_calculator

### 3.4 示例索引 (Example Index)
- **NEB (Li-Si)**: `examples/01_neb_Li-Si/config.yaml`
- **NEB (H2-Au)**: `examples/02_neb_H2-Au/config.yaml`
- **AutoNEB**: `examples/03_autoneb_Cy-Pt/config.yaml`
- **Dimer**: `examples/04_dimer_CO-Pt/config.yaml`
- **Sella**: `examples/05_sella_H2-Au/config.yaml`
- **Relax**: `examples/06_relax_H2-Au/config.yaml`
- **Vibration**: `examples/07_vibration_H2-Au/config.yaml`
- **D2S**: `examples/08_d2s_Cy-Pt/config.yaml` (Pending integration)

## 4. 目录结构 (Directory Structure)

```text
src/atst_tools/
├── calculators/       # 计算器适配层
│   ├── factory.py     # 核心工厂类
│   └── ...
├── external/          # 第三方依赖
│   └── abacuslite/    # ABACUS 官方插件
├── mep/               # 核心算法 (NEB, Dimer, Sella)
├── workflows/         # 高级工作流
│   ├── relax.py       # 结构优化
│   ├── vibration.py   # 振动分析
│   └── d2s.py         # Double-to-Single
└── scripts/           # CLI 入口
    └── main.py        # atst run 主程序
```

## 5. 开发指南 (Development)

请参考 [YAML 输入治理规范](../developer/YAML_INPUT_GOVERNANCE.md) 和 [文档架构](../developer/DOCS_ARCHITECTURE.md) 了解架构设计与后续扩展方向。
更多关于文档编写与维护规范，请参阅 [文档架构](../developer/DOCS_ARCHITECTURE.md)。

### 测试
```bash
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/integration/test_dp_neb.py
```
