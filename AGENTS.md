## ATST-Tools developing guide

### 简介

ATST-Tools 仓库的目的是：建立用 ASE 等科学计算 Python Package 调用 ABACUS / DeePMD-kit 作为第一性原理/机器学习势计算后端，完成高阶科学计算工作流的封装Python Code。其中优先实现对 ABACUS 的支持，其次是机器学习势。

### 仓库状态

ATST-Tools 目前处于重构状态，重构的主要目标是：
- 保留原有的基于ase的过渡态计算功能：
    - (CI-)NEB, DyNEB, AutoNEB
        - NEB部分在原仓库内单独实现，在迁移后要求直接基于ASE已有实现，舍弃此前加入的额外新内容
        - NEB的image级并行相关设置需要保留
    - Dimer
        - 直接基于ASE已有实现
    - Sella
        - 通过pip install sella引入sella库后使用
- 将原有main branch的Python脚本集重构为一套正式的，可快速pip install拉取的代码仓库
- 优化 user interface，使用 CLI + YAML inputs 进行工作流交互，并在examples/目录下留下示例交互模式。
- 对于 abacus 的 ase 支持，ATST-Tools 将从 ase-abacus 迁移到 abacuslite。开发环境下，abacuslite 会在 temp_repos/abacus-develop/interfaces/ASE_interface 目录下。
- temp_repos 不同步到git仓库，其中放置开发时可参考代码仓库，如ase-abacus。
- 先解决 abacus 接入，再解决机器学习势计算。

### 代码风格要求

- 代码设计需遵循Zen of Python原则
- 尽可能集成和封装
- 架构设计具备足够可扩展性
- Unit Test覆盖度足够且粒度合适

### 开发测试环境

项目当前开发测试在SAI超级计算机登录节点。服务器上有可直接使用的ABACUS LTS 3.10.1。
项目所属Python环境在atst-dev conda env。
开展调用ABACUS的测试需要将任务通过slurm脚本交到4V100节点上，使用GPU节点计算，并在ABACUS INPUT中设置ks_solver cusolver (在默认的basis lcao下)。

DeePMD相关开发与测试暂缓。

### 基本边界
README内容暂时不迭代，先收敛项目本身。项目开发文档集中在docs/目录下，部分审阅文档和计划在.trae下。