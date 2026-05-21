## ATST-Tools developing guide

### 简介

ATST-Tools (ASE Transition State Tools for ABACUS and ML potentials)：建立用 ASE 等科学计算 Python Package 调用 ABACUS / DeePMD-kit 作为第一性原理/机器学习势计算后端，完成高阶科学计算工作流的封装 Python Code。

### 仓库状态

ATST-Tools 目前处于重构状态，从main branch出发的过渡态计算功能重构基本完成。后续动作：
- 优化 user interface，使用 CLI + YAML inputs 进行工作流交互，并在examples/目录下留下示例交互模式。
- 对于 abacus 的 ase interfaces，ATST-Tools 将从 ase-abacus 迁移到 abacuslite，基本定位是 abacuslite CLI wrapper。在这一设计下，ATST-Tools将尽可能不重写 ASE 的已有实现，尽可能做到 ASE-native。
- 适当拓展基于ase的分子动力学计算功能
- 将原有main branch的Python脚本集重构为一套正式的，可快速pip install拉取的代码仓库
- temp_repos 不同步到git仓库，其中放置开发时可参考代码仓库

### 开发要求

- 代码设计需遵循Zen of Python原则。
- 代码库尽可能集成和封装，CLI设计尽可能兼顾易用和可扩展，仓库核心代码架构需要具备足够可扩展性。
- Unit Test覆盖度足够且粒度合适，Example中需要覆盖项目各方面功能并作为用户快速上手入口。
- 核心代码库各个函数需要具有精练且完整的，Google Style的docstring。
- 项目一段开发任务结束后，需要基于项目文档治理机制，在docs/的合适位置完成更新。

### 开发测试环境

- 项目当前开发测试在SAI超级计算机登录节点。服务器上有可直接使用的ABACUS LTS 3.10.1 和 DeePMD-kit 3.1.3
- 项目所属Python环境在atst-dev conda env。
- 开展调用ABACUS和DeePMD-kit的测试需要将任务通过slurm脚本交到4V100节点上，使用GPU节点计算。对于ABACUS，你需要在INPUT中设置ks_solver cusolver (在默认的basis lcao下)。

### 基本边界
- 重构在refractor/unify-structure branch下进行，main分支不做改动，作为基线参考
temp_repo下存放有本项目的可参考代码库，该目录下内容不进入git仓库。
- abacuslite 将成为项目的 ABACUS-ASE backend。它位于temp_repos/abacus-develop/interfaces/ASE_interface。此backend在项目代码中保留一份，但优先使用环境内的abacuslite。
- ase-abacus 为项目main分支采用的legacy ABACUS-ASE backend，它位于temp_repos/ase-abacus，该仓库仅与main分支一同作为参考功能基线，不能参与项目开发。