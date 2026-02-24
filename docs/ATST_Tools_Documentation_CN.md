# ATST-Tools 项目文档

## 1. 项目概述 (Project Overview)

**ATST-Tools (Advanced ASE Transition State Tools)** 是一个基于 Python 的工具集，旨在为 **ABACUS** 和 **Deep-Potential** 计算器提供高级的过渡态（Transition State, TS）搜索和分析功能。该项目基于 **ASE (Atomic Simulation Environment)** 框架构建，并扩展了 ASE 原有的 NEB 和 Dimer 方法，使其更适配 ABACUS 的计算流程，同时引入了 Sella 等第三方库的集成。

**v2.0.0 重大更新**：引入了基于配置文件的统一工作流，简化了脚本编写过程，通过 `atst-run` 命令行工具即可完成大部分计算任务。

**核心功能：**
*   **NEB (Nudged Elastic Band)**: 支持传统的 NEB、CI-NEB (Climbing Image)、IT-NEB (Improved Tangent) 以及 DyNEB (Dynamic NEB)。支持串行和基于 MPI 的并行计算。
*   **AutoNEB**: 自动化的 NEB 工作流，能够动态增加图像（Image）并自动聚焦于鞍点搜索。
*   **单端搜索 (Single-Ended Search)**: 集成了 **Dimer** 方法和 **Sella** 库，支持从单点（通常是 NEB 的最高点）出发精确搜索过渡态。
*   **Double-to-Single (D2S)**: 提供从粗糙 NEB 到高精度单端搜索（Dimer/Sella）的平滑过渡自动工作流。
*   **辅助分析**: 包括振动分析（Vibration Analysis）、结构弛豫（Relaxation）以及反应路径分析（IRC）。

## 2. 目录结构分析 (Directory Structure Analysis)

项目根目录 `/home/james/DeepModeling/ATST-Tools/` 下的主要结构如下：

*   **`src/atst_tools/`**: 核心代码库。
    *   **`calculators/`**: 计算器适配模块。
        *   `abacus.py`: 定义 `AbacusCalculator` 辅助类，用于配置和生成 ABACUS 计算器。
    *   **`mep/`**: 最小能量路径（Minimum Energy Path）搜索核心逻辑。
        *   `neb.py`: 包含 `AbacusNEB` 类，修复/增强了 ASE 原生 NEB 代码（特别是并行部分和 Stress 处理）。
        *   `autoneb.py`: 包含 `AbacusAutoNEB` 类，优化了图像添加逻辑和文件操作。
        *   `dimer.py`: Dimer 方法的 ABACUS 适配和核心逻辑。
        *   `sella.py`: Sella 库的适配接口。
    *   **`workflows/`**: 复杂工作流模块。
        *   `d2s.py`: 实现 Double-to-Single (D2S) 工作流逻辑。
    *   **`utils/`**: 工具模块（IDPP 插值、配置加载等）。
    *   **`scripts/`**: 命令行工具入口脚本。
        *   `main.py`: `atst-run` 的入口。
        *   `neb_make.py`: `atst-neb-make` 的入口。
        *   `neb_post.py`: `atst-neb-post` 的入口。

*   **`examples/`**: 示例目录。
    *   `config_templates/`: `config.yaml` 配置文件模板。
    *   `slurm_templates/`: 作业提交脚本模板。
    *   包含不同体系（如 H2-Au111, Li-diffu-Si）的计算示例。

## 3. 核心模块与实现细节 (Core Modules & Implementation Details)

### 3.1. NEB 与 DyNEB (`src/atst_tools/mep/neb.py`)
该模块对 ASE 的 `NEB` 类进行了深度定制。
*   **并行化优化**: 增强了 MPI 并行支持，确保在多核环境下正确分发计算任务。
*   **DyNEB (Dynamic NEB)**: 实现了动态 NEB 算法，允许在串行计算中跳过已经收敛的图像，从而节省计算资源。
*   **Force/Stress 处理**: 增加了对 Stress（应力）的处理，这对于变胞 NEB 或需要关注压强的体系很重要。

### 3.2. AutoNEB (`src/atst_tools/mep/autoneb.py`)
改进了 ASE 的 AutoNEB 逻辑：
*   **图像添加策略**: 动态插入新图像。
*   **文件管理**: 优化了迭代过程中的文件保存 (`prefixXXXiter00i.traj`) 和清理逻辑，避免产生过多垃圾文件。
*   **断点续算**: 支持从现有的轨迹文件中恢复计算。

### 3.3. ABACUS 适配 (`src/atst_tools/calculators/abacus.py`)
这些文件充当了 ASE 和 ABACUS 之间的桥梁。
*   **`AbacusCalculator`**: 封装了计算器设置（`AbacusProfile`），处理并行环境下的目录管理（如 `run_atst-rankX`），并提供了统一的接口来启动优化器。

### 3.4. Dimer 方法 (`src/atst_tools/mep/dimer.py`)
实现了 Dimer 方法的核心逻辑：
*   **`AbacusDimer`**: 适配了 ABACUS 计算器的 Dimer 搜索。

## 4. 工作流与使用指南 (Workflows & Usage)

v2.0.0 推荐使用 **Configuration-Driven** 工作流。

### 4.1. 通用步骤

1.  **安装**:
    ```bash
    pip install .
    ```
2.  **准备初末态**: 准备好初始态（IS）和末态（FS）的结构文件。
3.  **生成路径**:
    ```bash
    atst-neb-make -i IS_STRU FS_STRU -n 8 -m IDPP -o init_neb_chain.traj
    ```
4.  **准备配置文件**: 创建 `config.yaml`。
    ```yaml
    calculation:
      type: neb  # 可选: neb, autoneb, dimer, sella, d2s
      init_chain: init_neb_chain.traj
      climb: true
      fmax: 0.05
      parallel: true
      optimizer: FIRE

    abacus:
      command: abacus
      mpi: 4
      omp: 1
      parameters:
        calculation: scf
        ecutwfc: 100
        # ... 其他 DFT 参数
    ```
5.  **运行计算**:
    ```bash
    atst-run config.yaml
    ```
    (建议在 Slurm 脚本中运行)

### 4.2. NEB 计算
*   配置 `type: neb`。
*   支持 `algorism: improvedtangent` (IT-NEB) 或 `aseneb`。
*   运行结束后使用 `atst-neb-post neb.traj` 进行分析。

### 4.3. AutoNEB 计算
*   配置 `type: autoneb`。
*   程序会自动管理图像增加。

### 4.4. D2S (Double-to-Single) 工作流
*   配置 `type: d2s`。
*   该工作流会自动：
    1.  运行粗糙 NEB (fmax 较大)。
    2.  找到最高能垒点。
    3.  自动转换为 Dimer 或 Sella 任务进行精细搜索。

## 5. 依赖与环境 (Dependencies & Environment)

*   **Python**: >= 3.9
*   **核心依赖**:
    *   `ase`: 原子模拟环境。
    *   `numpy`, `scipy`, `matplotlib`
    *   `ruamel.yaml`: 配置文件解析。
    *   `sella`: Sella 优化库。
    *   `abacus` (ASE 接口): 需单独安装适配 ABACUS 的 ASE 版本。
*   **安装**:
    直接在项目根目录运行 `pip install .` 即可自动安装依赖并配置命令行工具。不再需要手动设置 `PYTHONPATH`。

## 6. 当前状态与注意事项 (Current Status & Notes)

*   **版本**: v2.0.0 (Beta)
*   **并行计算**:
    *   NEB 支持 MPI 并行（每个图像一个或多个核心）。在 `config.yaml` 中通过 `mpi` 参数设置每个图像使用的核心数。
*   **已知问题**:
    *   轨迹文件中可能会丢失 Stress 信息（已在自定义类中尝试修复）。
*   **推荐实践**:
    *   使用 **FIRE** 或 **BFGS** 作为优化器。
    *   对于复杂反应，推荐使用 **IT-NEB**。
    *   尝试使用 **D2S** 工作流来自动化搜索过程。
