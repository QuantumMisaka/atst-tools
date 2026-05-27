# Zn Migration NEB Calculation Spec

## Why
用户需要复现文献中 Zn 原子的迁移过程和迁移能垒（约 1.6 - 2.0 eV），并提供了起点结构 `Zn1.cif` 和终点结构 `Zn2.cif`，这两个体系是约有200原子的二维材料吸附体系，展示了Zn离子在石墨烯片层之间的迁移。计算需基于 ABACUS 并在 SAI 超算服务器上运行，同时要求对比 CI-NEB、AutoNEB 和 D2S 三种方法的计算表现。此规划旨在验证 ATST-Tools 工具对于该体系的可行性，并生成完整的工作流配置文件和作业提交脚本，从而保证顺利计算和文献对标。

## What Changes
- 验证计算可行性：ABACUS LCAO 方法（开启 cusolver 加速）对于 ~200 原子的体系，结合 SAI `4V100PX` 节点计算效率极高，完全可行。
- 为 CI-NEB、AutoNEB 和 D2S 分别建立计算配置（YAML 配置文件）。
- 规划生成初始 NEB 路径的步骤（利用 `atst neb make` 工具进行插值）。
- 编写适配 SAI 集群 `4V100PX` 分区的 `sbatch` 提交脚本（遵守 QOS 规范及 MPI+CUDA-MPS 资源映射规范）。其中 ABACUS 计算任务采用单节点四卡进行，计算命令需根据 SAI 服务器的要求设置。

## Impact
- Affected specs: 验证并在实际科研体系中应用 ATST-Tools 的 NEB 相关工作流（CI-NEB, AutoNEB, D2S）。
- Affected code: 计划在 `temp_practices` 目录下生成用于三种 NEB 计算策略的子文件夹、配置文件和 `sbatch` 脚本。

## ADDED Requirements
### Requirement: Zn Migration Calculation Scheme
该方案需满足：
1. **输入参数配置**：提取并匹配 `INPUT` 参数至 YAML 文件，并检查缺失的赝势及轨道文件（如 N, O 元素的补充）。
2. **CI-NEB 方案**：采用 `calculation.type: neb` 并设置 `climb: true`，利用 `atst run` 运行。
3. **AutoNEB 方案**：采用 `calculation.type: autoneb`，动态增加插点图像。
4. **D2S 方案**：采用 `calculation.type: d2s`，先进行粗糙 NEB，再利用 Dimer 或 Sella 搜索精确过渡态。
5. **服务器适配**：`sbatch` 脚本需按 `sai-user-guide` 要求，设置 `--partition=4V100PX`, `--qos=rush-gpu` 等，并将合适的 `mpirun` 命令传递给 atst-tools。
