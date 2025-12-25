# ATST-Tools 项目文档

## 1. 项目概述 (Project Overview)

**ATST-Tools (Advanced ASE Transition State Tools)** 是一个基于 Python 的工具集，旨在为 **ABACUS** 和 **Deep-Potential** 计算器提供高级的过渡态（Transition State, TS）搜索和分析功能。该项目基于 **ASE (Atomic Simulation Environment)** 框架构建，并扩展了 ASE 原有的 NEB 和 Dimer 方法，使其更适配 ABACUS 的计算流程，同时引入了 Sella 等第三方库的集成。

**核心功能：**
*   **NEB (Nudged Elastic Band)**: 支持传统的 NEB、CI-NEB (Climbing Image)、IT-NEB (Improved Tangent) 以及 DyNEB (Dynamic NEB)。支持串行和基于 MPI 的并行计算。
*   **AutoNEB**: 自动化的 NEB 工作流，能够动态增加图像（Image）并自动聚焦于鞍点搜索。
*   **单端搜索 (Single-Ended Search)**: 集成了 **Dimer** 方法和 **Sella** 库，支持从单点（通常是 NEB 的最高点）出发精确搜索过渡态。
*   **Double-to-Single (D2S)**: 提供从粗糙 NEB 到高精度单端搜索（Dimer/Sella）的平滑过渡工作流。
*   **辅助分析**: 包括振动分析（Vibration Analysis）、结构弛豫（Relaxation）以及反应路径分析（IRC）。

## 2. 目录结构分析 (Directory Structure Analysis)

项目根目录 `/home/james/DeepModeling/ATST-Tools/` 下的主要结构如下：

*   **`source/`**: 核心代码库。包含了对 ASE 类的继承和修改，以及针对 ABACUS 的适配类。
    *   `abacus_neb.py`: 定义 `AbacusNEB` 类，用于 ABACUS 的 NEB 计算。
    *   `abacus_autoneb.py`: 定义 `AbacusAutoNEB` 类，用于 ABACUS 的 AutoNEB 计算。
    *   `my_neb.py`: 自定义的 `NEB` 和 `DyNEB` 类，修复/增强了 ASE 原生代码（特别是并行部分）。
    *   `my_autoneb.py`: 自定义的 `AutoNEB` 类，优化了图像添加逻辑和文件操作。
    *   `abacus_dimer.py` / `my_dimer.py`: Dimer 方法的 ABACUS 适配和核心逻辑。
    *   `neb2vib.py`: 用于从 NEB 链中识别振动原子的辅助工具。

*   **`neb/`**: NEB 计算的工作流脚本。
    *   `neb_make.py`: 前处理脚本，用于生成初始 NEB 路径（支持 IDPP 和线性插值）。
    *   `neb_run.py`: 运行脚本，执行 NEB 计算。
    *   `neb_post.py`: 后处理脚本，分析能垒、绘制能带图、提取 TS 结构。
    *   `autoneb_run.py`: AutoNEB 的运行脚本。

*   **`dimer/`**: Dimer 方法的工作流脚本。
    *   `neb2dimer.py`: 将 NEB 结果转换为 Dimer 计算的输入。
    *   `dimer_run.py`: 执行 Dimer 计算。

*   **`sella/`**: Sella 方法的工作流脚本。
    *   `sella_run.py`: 执行 Sella 优化。
    *   `sella_IRC.py`: 执行 IRC（内禀反应坐标）分析。

*   **`ase-dp/`**: 针对 Deep-Potential (DP) 势函数的适配脚本。
    *   包含 `relax_dp.py`, `autoneb_dp.py` 等，逻辑与 ABACUS 版本类似，但计算器换成了 DP。

*   **`relax/`**: 结构弛豫脚本。
    *   `relax_run.py`: 使用 ASE 的优化器（如 QuasiNewton/BFGS）配合 ABACUS 进行结构优化。

*   **`vibration/`**: 振动分析脚本。
    *   `vib_analysis.py`: 计算频率和热力学性质。

*   **`examples/`**: 示例目录，包含不同体系（如 H2-Au111, Li-diffu-Si）的计算示例。

## 3. 核心模块与实现细节 (Core Modules & Implementation Details)

### 3.1. NEB 与 DyNEB (`source/my_neb.py`)
该模块对 ASE 的 `NEB` 类进行了深度定制。
*   **并行化优化**: 增强了 MPI 并行支持，确保在多核环境下正确分发计算任务。
*   **DyNEB (Dynamic NEB)**: 实现了动态 NEB 算法，允许在串行计算中跳过已经收敛的图像，从而节省计算资源。
*   **Force/Stress 处理**: 增加了对 Stress（应力）的处理，这对于变胞 NEB 或需要关注压强的体系很重要。

### 3.2. AutoNEB (`source/my_autoneb.py`)
改进了 ASE 的 AutoNEB 逻辑：
*   **图像添加策略**: 在 `run()` 方法中，根据弹簧长度或能量差动态插入新图像。
*   **文件管理**: 优化了迭代过程中的文件保存 (`prefixXXXiter00i.traj`) 和清理逻辑，避免产生过多垃圾文件。
*   **断点续算**: 支持从现有的轨迹文件中恢复计算。

### 3.3. ABACUS 适配 (`source/abacus_*.py`)
这些文件充当了 ASE 和 ABACUS 之间的桥梁。
*   **`AbacusNEB` / `AbacusAutoNEB`**: 封装了计算器设置（`AbacusProfile`），处理并行环境下的目录管理（如 `run_rank0`, `run_rank1` 等），并提供了统一的 `run()` 接口来启动优化器（如 FIRE 或 BFGS）。

### 3.4. Dimer 方法 (`source/my_dimer.py`)
实现了 Dimer 方法的核心逻辑：
*   **`DimerControl`**: 管理 Dimer 搜索的参数（旋转次数、步长等）。
*   **`MinModeAtoms`**: 扩展了 `Atoms` 类，用于存储和更新最小模式（Minimum Mode）信息。
*   **`MinModeTranslate`**: 专门的优化器，用于沿着最小模式方向推动系统向鞍点移动。

## 4. 工作流与使用指南 (Workflows & Usage)

### 4.1. NEB 计算流程
1.  **准备初末态**: 准备好初始态（IS）和末态（FS）的结构文件（如 `STRU` 或 `traj`）。
2.  **生成路径 (`neb_make.py`)**:
    ```bash
    python neb_make.py -i IS_STRU FS_STRU -n 8 -m IDPP -o init_neb_chain.traj
    ```
    *   `-n`: 中间图像数量。
    *   `-m`: 插值方法，推荐 `IDPP`。
3.  **运行计算 (`neb_run.py`)**:
    *   修改 `neb_run.py` 中的参数（如 `mpi`, `fmax`, `climb=True`）。
    *   执行: `mpirun -np 16 python neb_run.py` (或提交作业脚本)。
4.  **后处理 (`neb_post.py`)**:
    ```bash
    python neb_post.py neb.traj
    ```
    *   输出能垒、绘制能带图、保存过渡态结构。

### 4.2. AutoNEB 计算流程
1.  **生成初始路径**: 同样使用 `neb_make.py`，但只需包含初末态即可。
2.  **运行计算 (`autoneb_run.py`)**:
    *   脚本会自动管理图像的增加和优化。
    *   执行: `mpirun -np 16 python autoneb_run.py`。
3.  **后处理**: 使用 `neb_post.py --autoneb ...` 处理生成的多个轨迹文件。

### 4.3. 单端搜索 (Dimer / Sella)
通常建议先运行粗糙的 NEB，然后选取最高点作为单端搜索的起点（D2S 策略）。

*   **准备输入 (`neb2dimer.py` / `neb2sella...`)**:
    ```bash
    python neb2dimer.py neb.traj
    ```
    *   这将生成 `dimer_init.traj` 和位移向量 `displacement_vector.npy`。
*   **运行 Dimer (`dimer_run.py`)**:
    *   读取 `dimer_init.traj`，加载位移向量，启动 `AbacusDimer`。
*   **运行 Sella (`sella_run.py`)**:
    *   读取初始结构，配置 Sella 优化器进行鞍点搜索。

## 5. 依赖与环境 (Dependencies & Environment)

*   **Python**: 3.11 - 3.12
*   **核心依赖**:
    *   `ase`: 原子模拟环境。
    *   `pymatgen` & `pymatgen-analysis-diffusion`: 用于 IDPP 插值。
    *   `sella`: 用于 Sella 优化方法。
    *   `abacus`: ABACUS 的 ASE 接口（通常包含在 ASE 安装中，或作为独立包）。
*   **环境变量**:
    *   必须将 `source/` 目录添加到 `PYTHONPATH` 中，以便脚本能找到自定义的模块。
    ```bash
    export PYTHONPATH=/path/to/ATST-Tools/source:$PYTHONPATH
    ```

## 6. 当前状态与注意事项 (Current Status & Notes)

*   **开发状态**: 项目处于活跃开发中 (v1.5.0)。
*   **并行计算**:
    *   NEB 支持 MPI 并行（每个图像一个或多个核心）。在 `neb_run.py` 中通过 `mpi` 参数设置每个图像使用的核心数，总使用核心数 = `mpi` * `n_images`（如果并行开启）。
    *   DyNEB 只能串行运行（`parallel=False`），但在资源有限时效率更高。
*   **已知问题**:
    *   轨迹文件中可能会丢失 Stress 信息（已在自定义类中尝试修复）。
    *   GPAW 和 ABACUS 的 MPI 环境需要兼容（如果混合使用）。
*   **推荐实践**:
    *   使用 **QuasiNewton (BFGSLineSearch)** 作为默认的弛豫优化器。
    *   对于复杂反应，推荐使用 **IT-NEB** (Improved Tangent) 算法。
    *   利用 **D2S (Double-to-Single)** 工作流来提高 TS 搜索的精度和效率。
